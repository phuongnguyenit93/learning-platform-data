# Thay task lỗi thời và kiểm tra tương thích sau nâng cấp Ant hoặc JDK

## 1. Vì sao bảo trì build Ant cần được thực hiện có kiểm chứng?

Một dự án Java có thể sử dụng Apache Ant trong nhiều năm mà không thay đổi đáng kể cấu trúc `build.xml`. Trong thời gian đó, phiên bản Ant, JDK, thư viện bên thứ ba, hệ điều hành và công cụ CI có thể thay đổi. Những task từng chạy được có thể bị đánh dấu lỗi thời, phụ thuộc vào chương trình đã bị loại khỏi JDK hoặc thay đổi hành vi khi dùng toolchain mới.

Giả sử một dự án đang xây dựng ổn định với Ant cũ và JDK cũ. Sau khi chuyển sang Ant mới hoặc JDK mới, có thể gặp những tình huống như:

- Task `<copydir>` hoặc `<deltree>` còn trong build nhưng được Ant khuyến nghị thay bằng task hiện đại.
- Target sinh mã JNI vẫn gọi công cụ `javah` đã không còn trong các bản JDK hiện đại.
- Script phụ thuộc `tools.jar` hoặc `rt.jar`, trong khi JDK từ Java 9 có cấu trúc module khác.
- Task `<scriptdef>` dùng engine JavaScript vốn có sẵn ở JDK cũ, nhưng engine tương ứng không còn đi kèm JDK mới.
- Bộ kiểm thử cũ sử dụng reflection vào API nội bộ của JDK và lỗi khi chạy trên runtime mới.
- Thay task copy/move/delete khiến tên tệp, thời gian sửa đổi hoặc danh sách tệp trong JAR thay đổi ngoài dự kiến.
- Lệnh Ant báo `BUILD SUCCESSFUL` nhưng đầu ra bị thiếu resource, chứa file cũ hoặc không khởi chạy được.

**Mục tiêu bảo trì** không chỉ là làm cho cảnh báo biến mất. Một thay đổi có giá trị khi build **vẫn thực hiện đúng công việc cần làm**, sản phẩm đầu ra **đáp ứng hợp đồng cũ hoặc thay đổi có chủ đích**, và dự án có thể được xây dựng, kiểm thử, đóng gói trên các môi trường mà nhóm cam kết hỗ trợ.

Trong bài học này, ta thực hiện một quy trình có thể lặp lại:

1. Kiểm kê phiên bản toolchain, task lỗi thời và tích hợp phụ thuộc JDK.
2. Xác định task thay thế và sự khác biệt về ý nghĩa trước khi sửa XML.
3. Chuyển từng nhóm task sang cấu hình mới, giữ cấu trúc đầu ra cần thiết.
4. Kiểm chứng clean build, incremental build, test, artifact và khả năng chạy.
5. Chạy ma trận phiên bản Ant/JDK và có phương án xử lý lỗi hoặc quay lại phiên bản trước.

## 2. Phân biệt lỗi thời, bị loại bỏ và không còn tương thích

Ba trạng thái này khác nhau, nên cách xử lý cũng khác nhau.

| Trạng thái | Ý nghĩa | Ví dụ | Hướng xử lý |
| --- | --- | --- | --- |
| **Deprecated trong Ant** | Task còn được nhận diện nhưng tài liệu khuyến nghị không dùng cho cấu hình mới | `<copydir>`, `<copyfile>`, `<deltree>`, `<rename>` | Thay bằng task hiện đại và kiểm tra lại tham số |
| **Bị loại khỏi môi trường JDK** | Task hoặc lệnh gọi một công cụ không còn được phân phối cùng JDK mới | `javah`, `rmic`, `pack200` theo từng mốc JDK | Thay quy trình sinh/đóng gói bằng cơ chế hiện hành |
| **Không tương thích phiên bản** | Task vẫn tồn tại nhưng thư viện, API, compiler, module hoặc runtime thay đổi | Task bên thứ ba dùng reflection sâu; script dựa vào engine JavaScript cũ | Nâng phiên bản thư viện, đổi API hoặc thiết kế lại bước build |
| **Cảnh báo cấu hình** | Build chạy được nhưng đang phụ thuộc vào hành vi ngầm có thể đổi | Không khai báo `includeantruntime` hoặc dùng `source`/`target` không phù hợp | Khai báo tường minh và kiểm thử trên toolchain đích |

**Không đồng nhất “deprecated” với “không chạy được”.** Một task deprecated có thể vẫn hoạt động trên phiên bản Ant hiện tại. Tuy nhiên, nó có chi phí bảo trì: người mới khó hiểu, khả năng hỗ trợ trong tương lai kém và thường có lựa chọn thay thế rõ ràng hơn.

Ngược lại, một lỗi phát sinh sau khi nâng JDK **không nhất thiết là lỗi do Ant**. Ví dụ, Ant chỉ điều phối `javac` hoặc `java`; nguyên nhân gốc có thể nằm ở source code, thư viện build phụ trợ, annotation processor, công cụ JDK bị loại bỏ hoặc ứng dụng dưới kiểm thử.

## 3. Kiểm kê hiện trạng trước khi thay đổi

### 3.1. Ghi rõ toolchain đang dùng

Trên từng môi trường quan trọng, bắt đầu bằng:

```bash
ant -version
java -version
javac -version
ant -diagnostics
```

Lệnh `ant -version` cho biết Ant launcher đang gọi phiên bản nào. `java -version` cho thấy runtime của lệnh Java trên đường dẫn hiện tại; `javac -version` giúp phát hiện compiler khác phiên bản. `ant -diagnostics` cung cấp thêm thông tin chẩn đoán môi trường Ant, các thư viện phụ trợ và thông số Java.

Nếu CI chạy Ant qua wrapper, script hoặc IDE, cũng cần kiểm tra **đường dẫn JDK thực tế** mà tiến trình Ant sử dụng, bởi `JAVA_HOME` và chương trình `java` trên `PATH` có thể trỏ đến nơi khác nhau. Hãy ghi nhận phiên bản JDK/Ant của môi trường cũ và môi trường đích trước khi kết luận về lỗi tương thích.

Kết quả chẩn đoán có thể chứa đường dẫn nội bộ hoặc thông tin cấu hình của máy; khi đưa vào issue hoặc tài liệu công khai, chỉ chia sẻ phần cần thiết.

### 3.2. Xem danh sách target và quan hệ phụ thuộc

```bash
ant -p
ant -noinput -verbose -f build.xml verify
```

`ant -p` hiển thị những target có thể liệt kê từ buildfile; mức hiển thị phụ thuộc description của target. Lệnh `-verbose` cho phép hiểu target/task nào thực sự chạy. Trong dự án lớn, không chỉ đọc `build.xml` ở thư mục gốc: task có thể được khai báo trong file import, macro, antlib hoặc cấu hình được sinh ra.

Sơ đồ tư duy:

```text
build.xml
   |
   +-- import/include các file XML khác
   |
   +-- target compile --> javac / compiler
   |
   +-- target resources --> copy / filters / file selectors
   |
   +-- target test --> junit / java / custom test task
   |
   +-- target dist --> jar / zip / tar / signing
   |
   +-- taskdef/typedef --> JAR, antlib và thư viện ngoài
```

Task được đăng ký bằng `<taskdef>` có thể **không thuộc Ant core**. Nếu chỉ nâng Ant mà giữ nguyên JAR plugin cũ, vẫn có thể gặp lỗi class loading, thiếu dependency hoặc API không tương thích.

### 3.3. Tìm các task đáng xem xét

Trong repository có công cụ tìm kiếm `rg`, ví dụ:

```bash
rg -n -g '*.xml' '<(copydir|copyfile|deltree|rename|javah|rmic|javadoc2)\b' .
rg -n -g '*.xml' '<(taskdef|typedef|scriptdef|import|include)\b' .
rg -n -g '*.xml' '(tools\.jar|rt\.jar|pack200|source=|target=)' .
```

Các lệnh này là **gợi ý kiểm kê**, không phải bộ kiểm tra XML đầy đủ: task có thể dùng namespace, được sinh động, viết trong macro hoặc nằm ở file không có phần mở rộng `.xml`. Cũng cần xem script CI, shell, Dockerfile, cấu hình IDE và nơi thiết lập `ANT_HOME`/`JAVA_HOME`.

Tạo một bảng theo dõi:

| Vị trí | Cơ chế cũ | Phụ thuộc | Rủi ro | Quyết định |
| --- | --- | --- | --- | --- |
| `build.xml` / `resources` | `copydir` | Ant core | Đầu vào và mtime có thể thay đổi khi chuyển | Đổi sang `copy` + `fileset` |
| `build.xml` / `clean` | `deltree` | Ant core | Xóa sai thư mục khi chuyển | Đổi sang `delete` và kiểm tra đường dẫn |
| `native.xml` | Lệnh `javah` | JDK cũ | Không còn công cụ trên JDK mới | Dùng `javac -h` |
| `test.xml` | Custom test runner | Plugin JAR | API/classpath không tương thích | Nâng plugin và chạy lại test |

Mỗi hàng cần có **đầu ra cần giữ nguyên hoặc cần thay đổi có chủ đích**. Không nên thay hàng loạt bằng tìm-kiếm-thay-thế nếu chưa xác định ý nghĩa tham số của task cũ.

## 4. Bảng thay thế các task Ant deprecated thường gặp

| Task cũ | Mục đích | Task thay thế | Điểm phải kiểm tra |
| --- | --- | --- | --- |
| `<copydir>` | Sao chép cây thư mục | `<copy>` với `todir` và `<fileset>` | Includes/excludes, filter, timestamps, thư mục rỗng, ghi đè |
| `<copyfile>` | Sao chép một file | `<copy file="..." tofile="..."/>` | Điều kiện ghi đè, khi file nguồn không tồn tại |
| `<deltree>` | Xóa đệ quy thư mục | `<delete dir="..."/>` | Phạm vi đường dẫn và thứ tự target clean |
| `<rename>` | Đổi tên hoặc di chuyển file | `<move file="..." tofile="..."/>` | Xử lý file đích đã có, di chuyển qua filesystem |
| `<javadoc2>` | Sinh JavaDoc theo cách cũ | `<javadoc>` | Tham số công cụ, charset/doclint, JDK hiện hành |

Đây là những trường hợp phù hợp để minh họa việc đổi task. Với mọi task khác, cần xem tài liệu **đúng phiên bản Ant đang dùng** để xác định nó có thật sự deprecated hay có thay đổi tương thích nào. Không nên tự coi mọi task lâu đời là lỗi thời.

### 4.1. Thay `copydir` bằng `copy` và `fileset`

**Cấu hình cũ:**

```xml
<copydir src="src/resources"
         dest="build/classes"
         includes="**/*.properties"/>
```

**Cấu hình mới:**

```xml
<copy todir="build/classes"
      overwrite="false"
      preservelastmodified="true">
    <fileset dir="src/resources">
        <include name="**/*.properties"/>
    </fileset>
</copy>
```

`<fileset>` giữ đường dẫn tương đối của các file được chọn. Vì vậy `src/resources/config/app.properties` trở thành `build/classes/config/app.properties`. Nếu thay bằng `<copy file="...">` cho từng file mà bỏ mất cấu trúc thư mục, chương trình có thể không còn tìm được resource qua classpath.

Các thuộc tính cần suy nghĩ cẩn thận:

- `overwrite` quyết định việc ghi lại đích dù được xem là mới hơn nguồn; mặc định của `copy` không phải luôn ghi đè bằng mọi giá.
- `preservelastmodified` bảo toàn mtime nguồn; nếu cần sản phẩm nén tái lập byte, timestamp entry phải được chuẩn hóa ở khâu đóng gói hoặc staging.
- `filtering`, `<filterset>` và `<filterchain>` thay đổi **nội dung** file; chỉ bật nếu bản build cũ thực sự làm điều đó.
- `includeEmptyDirs` ảnh hưởng đến thư mục rỗng, có thể là phần thiết yếu của gói phân phối.
- `flatten="true"` gom file về một thư mục và có nguy cơ trùng tên; không bật chỉ để làm cấu hình ngắn hơn.

### 4.2. Thay `copyfile` bằng `copy`

**Cũ:**

```xml
<copyfile src="config/default.properties"
          dest="build/classes/app.properties"/>
```

**Mới:**

```xml
<copy file="config/default.properties"
      tofile="build/classes/app.properties"
      overwrite="true"/>
```

`overwrite="true"` ở đây là một **lựa chọn có chủ đích** nếu build phải dùng đúng cấu hình đầu vào hiện tại. Với tài nguyên bình thường, có thể chọn `overwrite="false"` và dùng tiêu chí mtime để tránh sao chép không cần thiết. Khi nâng cấp, hãy so đầu ra và xác định cách cũ xử lý file đích đã có, thay vì áp đặt cùng một giá trị cho mọi task copy.

Nếu giá trị cấu hình tùy theo môi trường, không hardcode nhầm file `dev` cho bản `prod`:

```xml
<property name="build.profile" value="dev"/>
<copy file="config/${build.profile}/app.properties"
      tofile="build/classes/app.properties"
      overwrite="true"/>
```

Trong CI, có thể chọn bằng `ant -Dbuild.profile=prod verify`. Nên kiểm tra tên profile hợp lệ bằng `<fail>`/`<condition>` để tránh âm thầm dùng sai cấu hình.

### 4.3. Thay `deltree` bằng `delete`

**Cũ:**

```xml
<deltree dir="build"/>
```

**Mới:**

```xml
<target name="clean">
    <delete dir="build" quiet="true"/>
</target>
```

`<delete dir="...">` xóa cả cây thư mục. Không dùng nó với đường dẫn được ghép từ biến chưa được kiểm tra hoặc mặc định rỗng, vì target `clean` có thể làm mất dữ liệu ngoài ý muốn. Với thư mục cần xóa **chọn lọc**, dùng `<delete>` lồng `<fileset>` để giới hạn pattern.

Ví dụ chỉ xóa file `.tmp`:

```xml
<delete>
    <fileset dir="build" includes="**/*.tmp"
             erroronmissingdir="false"/>
</delete>
```

Đừng nhầm “clean phải xóa mọi thứ” với “có thể xóa tùy ý”. Nên cố định vị trí output trong cây build của dự án và giữ việc xóa trong phạm vi đó.

### 4.4. Thay `rename` bằng `move`

**Cũ:**

```xml
<rename src="build/output.tmp"
        dest="build/output.txt"/>
```

**Mới:**

```xml
<move file="build/output.tmp"
      tofile="build/output.txt"
      overwrite="true"/>
```

`<move>` hỗ trợ di chuyển file và tập file. Cần kiểm tra:

- File đích đã tồn tại thì ghi đè, bỏ qua hay báo lỗi theo đặc tả?
- Việc di chuyển có thể đi qua filesystem khác; không nên mặc định đây luôn là phép đổi tên nguyên tử.
- Quyền file, timestamp và symbolic link có cần giữ như cũ?
- Bản build có bước khác đang dùng đường dẫn nguồn trước khi move không?

Với file output phục vụ các target tiếp theo, hãy bảo đảm thứ tự phụ thuộc `depends` phản ánh thời điểm tên file mới xuất hiện.

### 4.5. Chuyển task JavaDoc cũ

**Cũ:**

```xml
<javadoc2 sourcepath="src"
          destdir="build/docs/api"
          packagenames="demo.*"/>
```

**Mới:**

```xml
<javadoc sourcepath="src"
         destdir="build/docs/api"
         packagenames="demo.*"
         encoding="UTF-8"
         charset="UTF-8"
         docencoding="UTF-8"/>
```

`<javadoc>` vẫn gọi công cụ tài liệu của JDK; thay task chỉ giải quyết cú pháp Ant. JDK mới có thể thay đổi chế độ kiểm tra tài liệu, API có sẵn và cách hiển thị HTML. Vì vậy cần xem build có lỗi doclint hoặc cảnh báo cần giải quyết, và nếu tài liệu API là artifact phát hành thì kiểm tra cả cấu trúc đầu ra.

## 5. Các công cụ JDK cũ cần thay hoặc thiết kế lại

Không phải vấn đề nào cũng giải quyết bằng một task Ant khác. Một số công cụ từng nằm trong JDK đã biến mất hoặc được thay bằng cơ chế mới.

| Phụ thuộc cũ | Thay đổi ở JDK hiện đại | Hướng bảo trì |
| --- | --- | --- |
| `javah` | Công cụ bị loại bỏ từ JDK 10 | Dùng `javac -h` để sinh JNI header |
| `rmic` | Công cụ `rmic` bị loại bỏ từ JDK 15 | Loại bước tạo static stub cũ; xem lại thiết kế Java RMI và runtime hỗ trợ |
| `pack200`/`unpack200` | Công cụ/API Pack200 bị loại bỏ từ JDK 14 | Phân phối JAR/ZIP chuẩn hoặc dùng cơ chế đóng gói khác phù hợp |
| `tools.jar`/`rt.jar` | Không còn cấu trúc JAR đó từ JDK 9 | Dùng module/API chính thức, cập nhật thư viện phụ thuộc |
| Nashorn có sẵn trong JDK | Engine Nashorn bị loại bỏ từ JDK 15 | Cung cấp engine độc lập tương thích hoặc thay script task bằng task Java |
| Sử dụng API nội bộ JDK | Module system và encapsulation mạnh hơn trên JDK mới | Nâng dependency, chuyển sang API được hỗ trợ |

Các mốc ở bảng giúp khoanh vùng nguyên nhân; với từng dự án, cần kiểm tra phiên bản JDK nguồn/đích và cách plugin dùng công cụ. Không phải mọi dự án dùng RMI hoặc JavaScript đều cần cùng một phương án thay thế.

### 5.1. Sinh JNI header bằng `javac -h`

Quy trình cũ có thể dùng task `<javah>` sau khi đã biên dịch class. Với JDK hiện đại, công cụ `javac` tự sinh JNI header qua tùy chọn `-h`.

Ví dụ Java:

```java
package demo;

public class NativeBridge {
    public native int add(int a, int b);
}
```

Chạy bằng công cụ JDK:

```bash
mkdir -p build/classes build/headers
javac -d build/classes -h build/headers src/demo/NativeBridge.java
```

Lệnh `mkdir -p` ở đây dùng trong shell Unix; khi thực thi nhiều hệ điều hành, để Ant tạo thư mục bằng `<mkdir>` rồi gọi compiler. Tại Ant, có thể cấu hình `<javac>` với compiler arguments tương ứng:

```xml
<target name="compile-native-bridge">
    <mkdir dir="build/classes"/>
    <mkdir dir="build/headers"/>
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false"
           release="17">
        <compilerarg value="-h"/>
        <compilerarg path="build/headers"/>
    </javac>
</target>
```

Đây là **mẫu cơ chế** cho JDK hỗ trợ `javac -h`. Nếu target có nhiều source, file sinh tự động, annotation processor hoặc incremental compile, hãy xác định rõ compiler được gọi lại khi signature native thay đổi. File header có thể còn sót nếu phương thức native bị xóa; quy trình clean build và kiểm tra danh sách header là cần thiết.

### 5.2. Không để build phụ thuộc JAR nội bộ của JDK

Một cấu hình cũ đôi khi thêm:

```xml
<pathelement location="${java.home}/../lib/tools.jar"/>
```

Với JDK 9 trở lên, cấu trúc cũ có thể không còn. Nếu code gọi compiler API, hãy cân nhắc `javax.tools.JavaCompiler` trong module `java.compiler` hoặc công cụ chuẩn của JDK, tùy nhu cầu. Nếu đây là thư viện bên thứ ba, nâng lên phiên bản hỗ trợ JDK đích thường thích hợp hơn việc tìm cách tự sao chép `tools.jar`.

Không xem việc thêm một chuỗi `--add-opens` vào JVM là lời giải lâu dài cho mọi lỗi reflection. Tham số này có thể hữu ích để khoanh vùng hoặc duy trì tạm thời, nhưng nên nâng dependency và chuyển API khi có lựa chọn chính thức.

### 5.3. Script task và engine ngôn ngữ

Một build cũ có thể chứa:

```xml
<scriptdef name="generate-info" language="javascript">
    // ...
</scriptdef>
```

Nếu trước đó dựa vào engine JavaScript có sẵn trong JDK, khi nâng runtime có thể gặp lỗi **không tìm thấy scripting engine**. Cần xác định engine được Ant sử dụng và classpath của engine đó. Các hướng xử lý là khai báo dependency script engine tương thích, thay bằng task Ant có sẵn, hoặc viết custom Ant task bằng Java cho logic quan trọng cần bảo trì dài hạn.

Việc thay bằng task Java thuần thường giúp hành vi và test dễ xác định hơn, nhưng vẫn cần so sánh dữ liệu sinh ra trước/sau nếu đó là một phần artifact.

## 6. Nâng cấp compiler: `source`/`target` và `release`

Một build Ant đời cũ có thể:

```xml
<javac srcdir="src"
       destdir="build/classes"
       source="8"
       target="8"/>
```

`source` giới hạn mức cú pháp; `target` điều khiển phiên bản class file. Nhưng cặp này **không đủ để đảm bảo** mã biên dịch trên JDK mới chỉ gọi API tồn tại ở Java 8. Một chương trình có thể tạo bytecode mức 8 nhưng vẫn gọi API thư viện chuẩn xuất hiện sau Java 8, dẫn đến lỗi khi chạy trên JDK 8.

Với JDK 9 trở lên, `javac --release N` được thiết kế để kiểm tra mức ngôn ngữ, bytecode và API platform của mức đích. Trong Ant hỗ trợ thuộc tính `release`, cấu hình có thể là:

```xml
<javac srcdir="src"
       destdir="build/classes"
       encoding="UTF-8"
       includeantruntime="false"
       release="17"/>
```

Khi dùng `release`, tránh khai báo đồng thời `source` và `target` cho cùng compiler invocation; tổ hợp tùy chọn mâu thuẫn có thể khiến `javac` báo lỗi. `release=17` cũng đòi hỏi compiler đủ mới để hỗ trợ mức 17. Không thể dùng compiler JDK 11 để xuất bytecode Java 17.

Đặc biệt:

- Compile với `--release 17` trên JDK 21 **không thay thế** việc test trên JVM 17.
- API của **dependency bên ngoài JDK** vẫn phải được kiểm tra riêng; `--release` không biến một thư viện Java 21 thành thư viện Java 17.
- Annotation processor, compiler plugin, thư viện tùy biến có thể phụ thuộc API/JDK của chính môi trường build.
- `includeantruntime="false"` giúp classpath compiler ít phụ thuộc tình cờ vào các JAR của Ant đang chạy.

Nếu vẫn cần build cho JDK 8, hãy đặt `release="8"` trên compiler có hỗ trợ mức đó, rồi kiểm thử thực sự trên runtime 8 theo chính sách dự án. Chỉ chọn các JDK đang được tổ chức và dependency hỗ trợ; bản Java không còn được hỗ trợ về bảo mật cần có chính sách quản lý riêng.

## 7. Ví dụ thực hành: chuyển build cũ sang cấu hình Ant dễ bảo trì

### 7.1. Cấu trúc dự án

Ta dùng dự án Java nhỏ:

```text
ant-maintenance-demo/
├── build.xml
├── src/
│   └── demo/
│       └── App.java
└── resources/
    └── app.properties
```

**`resources/app.properties`:**

```properties
app.mode=production
```

**`src/demo/App.java`:**

```java
package demo;

import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        Properties config = new Properties();
        try (InputStream in =
                     App.class.getResourceAsStream("/app.properties")) {
            if (in == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            config.load(in);
        }

        String mode = config.getProperty("app.mode");
        if (!"production".equals(mode)) {
            throw new IllegalStateException("Unexpected mode: " + mode);
        }

        if (args.length == 1 && "--self-test".equals(args[0])) {
            System.out.println("SMOKE_TEST_OK");
        } else {
            System.out.println("Application mode=" + mode);
        }
    }
}
```

Chương trình cố ý dùng tài nguyên trong classpath và một chế độ smoke test. Nếu thao tác `copy` hoặc đóng gói bị lỗi, ứng dụng sẽ ném exception, JVM thoát khác 0 và Ant có thể chặn bản build.

### 7.2. Cấu hình cũ minh họa

Một phần build file cũ có thể có dạng:

```xml
<target name="clean">
    <deltree dir="build"/>
</target>

<target name="resources">
    <copydir src="resources"
             dest="build/classes"/>
</target>

<target name="rename-output">
    <rename src="build/tmp/result.jar"
            dest="build/dist/app.jar"/>
</target>
```

Đây chỉ là đoạn minh họa cách dùng task cũ. Khi thay, cần giữ những đường dẫn và file mà các target khác phụ thuộc. Không nên chuyển sang một file XML mới mà bỏ qua target thực sự làm chương trình chạy được.

### 7.3. `build.xml` sau bảo trì

Ví dụ hoàn chỉnh dưới đây dùng `<delete>`, `<copy>`, `<javac>`, `<jar>` và `<java>`; không cần `copydir`, `copyfile` hay `deltree`. Chạy trên Ant hỗ trợ `<javac release="17">` và JDK 17 trở lên.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-maintenance-demo" default="verify" basedir=".">
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="java.release" value="17"/>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="src"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               release="${java.release}"
               debug="true"/>
    </target>

    <target name="resources" depends="compile">
        <copy todir="${classes.dir}"
              overwrite="false">
            <fileset dir="resources" includes="**/*"/>
        </copy>
    </target>

    <target name="package" depends="resources">
        <jar destfile="${dist.dir}/app.jar"
             basedir="${classes.dir}"
             duplicate="fail">
            <manifest>
                <attribute name="Main-Class" value="demo.App"/>
                <attribute name="Implementation-Version" value="1.0.0"/>
            </manifest>
        </jar>
    </target>

    <target name="smoke" depends="package">
        <java jar="${dist.dir}/app.jar"
              fork="true"
              failonerror="true">
            <arg value="--self-test"/>
        </java>
    </target>

    <target name="verify" depends="smoke">
        <checksum file="${dist.dir}/app.jar"
                  algorithm="SHA-256"
                  property="artifact.sha256"/>
        <echo message="Artifact SHA-256: ${artifact.sha256}"/>
    </target>
</project>
```

**Cách chạy:**

```bash
ant -version
java -version
ant -noinput clean verify
java -jar build/dist/app.jar
jar tf build/dist/app.jar
```

Với đầu vào ở trên, `smoke` phải in `SMOKE_TEST_OK`. Lệnh `java -jar` phải in `Application mode=production`. Danh sách entry của JAR cần có `demo/App.class`, `app.properties` và `META-INF/MANIFEST.MF`.

Lệnh `clean verify` cố ý tạo lại artifact từ đầu để xác nhận build không phụ thuộc class hoặc resource của lần chạy trước. Khi áp dụng cho dự án thật, thay smoke test mẫu bằng unit test, integration test và kiểm tra hợp đồng artifact đang dùng.

### 7.4. Nếu cần di chuyển artifact thì dùng `move` ở target riêng

Ví dụ ở mục 7.3 cho `<jar>` ghi trực tiếp vào vị trí đích cuối, nên không cần bước đổi tên. Nếu quy trình thật yêu cầu một file tạm trước khi xuất bản:

```xml
<target name="publish-local" depends="package">
    <mkdir dir="build/published"/>
    <move file="build/dist/app.jar"
          tofile="build/published/app.jar"
          overwrite="true"/>
</target>
```

Không gọi target `publish-local` trước `smoke` nếu smoke vẫn trỏ vào `build/dist/app.jar`: lúc đó build sẽ kiểm tra file đã được di chuyển đi. Cần thiết kế lại dependency và đường dẫn theo **thứ tự thực tế** của quy trình đóng gói.

## 8. Kiểm tra tương thích ngay sau nâng Ant

### 8.1. Nâng Ant khác với nâng JDK

Hai bước này nên được quan sát độc lập khi có thể:

| Giai đoạn | Ant | JDK | Điều cần xác nhận |
| --- | --- | --- | --- |
| Baseline | Bản cũ | Bản cũ | Build/test/artifact hiện tại hợp lệ |
| A | Bản mới | Bản cũ, nếu Ant mới hỗ trợ | Task, cú pháp, antlib và thay đổi từ Ant |
| B | Bản mới | Bản JDK mục tiêu | Compiler, runtime, tool JDK và thư viện |
| C | Bản mới | Các JDK chính thức hỗ trợ | Ma trận tương thích và phát hành |

**Không phải mọi tổ hợp trong bảng đều khả thi.** Phiên bản Ant mới có thể yêu cầu mức Java tối thiểu cao hơn JDK cũ. Khi đó chọn một bước chuyển được nhà phát triển Ant hỗ trợ và ghi rõ giới hạn, thay vì cố ép Ant mới chạy trên runtime không phù hợp.

Mỗi giai đoạn nên dùng cùng revision mã nguồn, cùng dữ liệu đầu vào và các dependency đã được cố định. Nếu vừa nâng Ant, nâng JDK, nâng plugin test và thay đổi source code trong một lần, việc khoanh vùng nguyên nhân khi build hỏng sẽ khó hơn nhiều.

### 8.2. Kiểm tra taskdefs và thư viện Ant tùy chỉnh

Các cấu hình cũ có thể chứa:

```xml
<taskdef name="custom-check"
         classname="com.example.build.CustomCheck"
         classpath="tools/build-support.jar"/>
```

Khi nâng Ant/JDK, cần xác nhận:

- JAR của custom task đã được biên dịch cho phiên bản Java tương thích.
- Các dependency kèm theo nằm trên classpath của task, không vô tình lấy từ `ANT_HOME/lib` trên một máy riêng.
- Class không sử dụng API nội bộ của Ant/JDK đã thay đổi.
- Các task tùy chọn như `<junit>`, `<junitlauncher>`, SSH, Ivy hoặc code generation có bộ thư viện phù hợp phiên bản Ant.
- Bản cập nhật không sinh classpath conflict do lặp một thư viện với hai phiên bản.

Nếu Ant báo `taskdef class ... cannot be found`, `NoClassDefFoundError`, `UnsupportedClassVersionError` hoặc `ClassNotFoundException`, cần xem **classpath và mức bytecode** của task trước khi sửa tên XML. Nếu một task Ant vẫn tồn tại nhưng code của task không tương thích Java, chỉ đổi tên task sẽ không giải quyết vấn đề.

### 8.3. Kiểm tra file import, property và điều kiện

Khi chuyển version, những thay đổi nhỏ cũng có thể làm sai logic:

- Thứ tự đặt property: Ant properties có tính chất **đặt một lần**, nên override từ CLI có thể bị ảnh hưởng nếu script tự tái định nghĩa các giá trị bằng cơ chế khác.
- `<import>`, `<include>` và target trùng tên: cần kiểm tra target cuối cùng được gọi và quan hệ phụ thuộc.
- Macro `<macrodef>` có thể bọc task cũ; tìm task ở XML cấp cao chưa chắc tìm hết.
- Pattern của `fileset`, đường dẫn và encoding có thể cho kết quả khác giữa OS, đặc biệt nếu file tên có chữ hoa/thường hoặc ký tự Unicode.
- Target dùng `if`/`unless` có thể chạy hoặc bị bỏ qua do property được đặt khác trước; `BUILD SUCCESSFUL` không chứng minh task đã thực thi.

Chạy `ant -noinput -verbose verify` giúp quan sát quá trình trong quá trình điều tra. Không cần duy trì chế độ log quá chi tiết ở mọi lượt CI nếu chi phí và độ nhiễu lớn; bật khi cần khoanh vùng.

## 9. Kiểm tra tương thích sau nâng JDK

### 9.1. Compiler, classpath và bytecode

Khi chuyển từ JDK 8 lên JDK mới hoặc giữa các JDK LTS, cần kiểm tra:

- Cú pháp và API được dùng bởi source code.
- Giá trị `release`/`source`/`target`.
- Annotation processors, code generator và công cụ biên dịch ngoài.
- Phiên bản các dependency được đặt trên compile classpath và runtime classpath.
- Quy trình kiểm thử thực sự chạy trên JDK đích.

Các lỗi thường gặp:

| Lỗi hoặc dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `invalid target release` | Compiler JDK quá cũ cho mức release yêu cầu | In `javac -version`, giảm target hoặc nâng compiler |
| `UnsupportedClassVersionError` | Class/dependency được biên dịch cho Java mới hơn runtime | Xem mức bytecode và JDK chạy test |
| `NoClassDefFoundError` | Thư viện không có trên runtime/module path hoặc bị loại khỏi JDK | Kiểm tra dependency/runtime classpath |
| `InaccessibleObjectException` | Thư viện reflection vào thành phần JDK bị đóng | Nâng thư viện, dùng API được hỗ trợ |
| `NoSuchMethodError` | Các bản dependency không tương thích nhị phân | Kiểm tra dependency resolution và classpath |
| Task báo không tìm thấy `javah`/`rmic` | Công cụ JDK đã bị loại bỏ | Thay bước build, không chỉ sửa PATH |

Chú ý: `NoClassDefFoundError` và `NoSuchMethodError` cũng có thể đến từ thư viện bên thứ ba có version mâu thuẫn, không phải vì JDK vừa nâng. Cần đọc stack trace và xác định đúng class/module gây lỗi.

### 9.2. Java module system và reflective access

Từ Java 9, JDK có hệ thống module. Khi chạy ứng dụng hoặc build plugin trên JDK mới, việc truy cập package nội bộ của JDK có thể không còn được phép như trước. Một số thư viện đời cũ dùng reflection, instrumentation hoặc bytecode enhancement có thể phát sinh lỗi runtime dù trước đó biên dịch được.

Quy trình xử lý ưu tiên:

1. Xác định dependency hoặc đoạn mã gây truy cập bị chặn từ stack trace.
2. Kiểm tra bản thư viện tương thích JDK đích và cập nhật theo hướng dẫn của dự án đó.
3. Chuyển sang API chính thức khi có thể.
4. Nếu tạm dùng `--add-opens` hay `--add-exports`, ghi rõ phạm vi, lý do, thời điểm cần loại bỏ và kiểm thử trong CI; không coi đây là cách thay thế cho việc nâng thư viện vĩnh viễn.

### 9.3. Javadoc và warning chuyển thành lỗi

Build có thể thất bại tại bước tài liệu API khi JDK mới kiểm tra tag, liên kết hoặc cú pháp mạnh hơn. Nếu có target `javadoc`, thử chạy riêng target đó và xem loại cảnh báo. Chỉ tắt kiểm tra khi đã biết hậu quả; mục tiêu là xuất được tài liệu đúng, không đơn thuần đạt mã thoát 0.

### 9.4. Script, encoding và timezone

Sau nâng JDK, khác biệt locale mặc định, character set hoặc xử lý ký tự có thể làm file sinh khác nhau. Một số JDK mới dùng UTF-8 làm default charset, trong khi hệ thống cũ phụ thuộc encoding bản địa.

Với file nguồn, chỉ rõ:

```xml
<javac srcdir="src"
       destdir="build/classes"
       encoding="UTF-8"
       includeantruntime="false"
       release="17"/>
```

Với task copy có filter, tài liệu sinh hoặc file cấu hình, hãy định nghĩa charset ở task tương ứng nếu có hỗ trợ. Một định dạng văn bản có encoding cố định nên được kiểm tra bằng cả nội dung lẫn byte, đặc biệt khi có tiếng Việt.

## 10. Kiểm tra sau khi thay task: đừng chỉ dựa vào `BUILD SUCCESSFUL`

Một phép kiểm chứng tốt gồm ít nhất bốn lớp.

### 10.1. Clean build

```bash
ant -noinput clean verify
```

Clean build phải thật sự tạo class, resource và artifact từ trạng thái đã xóa đầu ra. Kiểm tra:

- Đúng số file nguồn và module được biên dịch.
- Không thiếu resource hoặc script phân phối.
- Target test thực sự chạy và lỗi test làm Ant thất bại.
- JAR/WAR/ZIP có đúng cấu trúc, manifest, version, tên file và vị trí.

### 10.2. Incremental build

```bash
ant -noinput verify
```

Kiểm tra thêm các thay đổi nhỏ mà không chạy `clean`:

1. Sửa file Java và xác nhận class/JAR được cập nhật.
2. Sửa một file resource và xác nhận artifact chứa phiên bản mới.
3. Thêm file mới vào tập tài nguyên và xác nhận nó được đóng gói nếu phù hợp.
4. Xóa hoặc đổi tên file nguồn/resource và kiểm tra đầu ra không còn chứa bản cũ.
5. Đổi cấu hình biên dịch hoặc dependency và xác nhận không tái sử dụng class cũ sai điều kiện.

Điểm quan trọng: cơ chế incremental của một số task Ant dựa trên **mtime**. Thay task `copy` và các flag liên quan đến timestamp có thể khiến file bị bỏ qua ngoài ý muốn hoặc bị copy lại mọi lần. Nếu xóa source nhưng class cũ vẫn còn trong thư mục build, JAR có thể chứa dữ liệu không còn thuộc mã nguồn hiện hành. Clean build và incremental build cần được kiểm chứng **riêng**.

### 10.3. Kiểm thử hành vi

Chạy unit test, integration test và smoke test từ artifact. Ví dụ với dự án ở mục 7:

```bash
ant -noinput clean verify
java -jar build/dist/app.jar
```

Nếu resource `app.properties` bị mất, chương trình sẽ báo lỗi thay vì chỉ in thành công. Đây là bằng chứng trực tiếp cho một phần hợp đồng sản phẩm.

Với ứng dụng WAR/EAR, kiểm tra cấu trúc `WEB-INF`/`META-INF`, thư viện và deployment descriptor; chạy trên application server đích khi thuộc cam kết hỗ trợ. Với thư viện JAR, cân nhắc API compatibility hoặc consumer test.

### 10.4. So sánh artifact

Xem danh sách entry:

```bash
jar tf build/dist/app.jar
```

Lấy checksum:

```bash
sha256sum build/dist/app.jar
```

Trên PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 build/dist/app.jar
```

**Checksum bằng nhau** là bằng chứng mạnh về byte đầu ra giống nhau. **Checksum khác nhau** chưa đủ để khẳng định code sai vì JAR có metadata như timestamp, thứ tự entry, manifest và cách nén có thể đổi giữa toolchain. Nếu yêu cầu phát hành là reproducible build, phải chuẩn hóa metadata và kiểm tra nguyên nhân khác hash. Nếu thay đổi có chủ đích làm artifact khác, hãy so danh sách entry, nội dung, API và hành vi theo đặc tả.

Đặc biệt, nâng JDK có thể tạo bytecode khác dù source giống nhau. Khi hợp đồng chỉ yêu cầu tương thích chức năng, không nên ép mọi phiên bản JDK phải tạo cùng hash nếu quy trình chưa được thiết kế để làm điều đó.

## 11. Ví dụ ma trận kiểm tra Ant và JDK trong CI

Để phân biệt lỗi do Ant và JDK, lý tưởng là thử các tổ hợp thực sự được hỗ trợ:

| Job | Ant | JDK | Mục tiêu |
| --- | --- | --- | --- |
| Baseline | Phiên bản đang sản xuất | JDK đang sản xuất | Bằng chứng hiện trạng |
| Ant mới | Ant mục tiêu | JDK tương thích cũ | Phát hiện thay đổi hành vi Ant |
| JDK mới | Ant mục tiêu | JDK mục tiêu | Kiểm tra compiler/runtime |
| Tương thích mở rộng | Ant mục tiêu | Các JDK còn được hỗ trợ | Bảo đảm không phá vỡ người dùng |

Không phải mọi phiên bản Ant/JDK tùy ý đều ghép được; hãy kiểm tra mức Java tối thiểu theo tài liệu chính thức của phiên bản Ant. Cấu hình matrix phải xuất phát từ phạm vi hỗ trợ của **sản phẩm**, không chạy một tích Descartes lớn chỉ vì kỹ thuật CI cho phép.

Ví dụ rút gọn với GitHub Actions, kiểm tra JDK 17 và 21 trên Ubuntu/Windows bằng một bản Ant cố định:

```yaml
name: Ant and JDK compatibility

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  compatibility:
    name: ${{ matrix.os }} / JDK ${{ matrix.jdk }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        jdk: ['17', '21']

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.jdk }}

      - name: Install pinned Ant
        shell: pwsh
        run: |
          $antVersion = '1.10.15'
          $filename = "apache-ant-$antVersion-bin.zip"
          $url = "https://archive.apache.org/dist/ant/binaries/$filename"
          $archive = Join-Path $env:RUNNER_TEMP $filename
          Invoke-WebRequest -Uri $url -OutFile $archive
          Expand-Archive -LiteralPath $archive -DestinationPath $env:RUNNER_TEMP
          $antHome = Join-Path $env:RUNNER_TEMP "apache-ant-$antVersion"
          "ANT_HOME=$antHome" >> $env:GITHUB_ENV
          (Join-Path $antHome 'bin') >> $env:GITHUB_PATH

      - name: Identify runtime
        shell: pwsh
        run: |
          java -version
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          javac -version
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          ant -version
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

      - name: Clean build and verify
        shell: pwsh
        run: |
          ant -noinput clean verify
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

      - name: Run packaged JAR
        shell: pwsh
        run: |
          java -jar build/dist/app.jar
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Ví dụ sử dụng PowerShell Core (`pwsh`) trên hai hệ điều hành để tránh khác biệt giữa shell Unix và Windows. Trong CI thực tế, cần **xác thực checksum hoặc chữ ký** của bản Ant tải về bằng thông tin được quản lý đáng tin cậy, cân nhắc ghim action bằng commit SHA và dùng runner/image đã được tổ chức chấp thuận. Giá trị `1.10.15` minh họa một phiên bản Ant được chỉ định rõ; không mặc định đó là phiên bản mới nhất tại mọi thời điểm.

Nếu dự án cam kết hỗ trợ macOS hoặc nhiều vendor JDK, bổ sung các ô tương ứng. Cũng cần test các target ngoài `verify` nếu tài liệu API, native packaging, database migration hoặc release publishing là một phần quan trọng của quy trình nâng cấp.

## 12. Các lỗi thường gặp sau thay task và nâng toolchain

| Triệu chứng | Khả năng nguyên nhân | Việc nên kiểm tra |
| --- | --- | --- |
| `Problem: failed to create task or type ...` | Tên task không hợp lệ, thiếu antlib hoặc plugin | XML namespace, `taskdef`, classpath, bản Ant |
| `ClassNotFoundException`/`NoClassDefFoundError` | Thư viện custom task thiếu hoặc sai bản | JAR của task và dependency |
| `UnsupportedClassVersionError` | Class được build cho JDK cao hơn runtime | Compiler, `release` và bản JVM đang chạy |
| `invalid target release` | `javac` quá cũ so với mức đích | `javac -version` và mức `release` |
| Không tìm thấy `javah` | JDK đã bỏ công cụ | Sinh header với `javac -h` |
| Test script JavaScript không chạy | Thiếu engine scripting | `scriptdef`, JDK và script engine classpath |
| Clean build đạt, incremental build thiếu cập nhật | Mtime, `uptodate`/`copy`, stale class/resource | Thay đổi file và xem output trước/sau |
| JAR tồn tại nhưng ứng dụng lỗi | Sai cấu trúc resource/manifest hoặc runtime dependency | `jar tf`, smoke test `java -jar` |
| Chỉ Windows lỗi | Đường dẫn, shell, encoding, filesystem | So với job Linux cùng JDK |
| Chỉ JDK mới lỗi | API JDK, module encapsulation, dependency | Stack trace, compiler/runtime version |
| Hash JAR khác sau nâng | Timestamp, thứ tự entry, bytecode, manifest, nén | Phân tích archive và nội dung class/resource |
| Target không chạy dù build xanh | Điều kiện `if`/`unless` hoặc dependency không đúng | `ant -verbose`, target graph, property |

Đọc **lỗi đầu tiên có ý nghĩa** trong log và so với môi trường gần nhất chỉ khác một yếu tố. Nếu đồng thời đổi JDK, Ant, nguồn và dependency thì cần tạo một nhánh thử nghiệm độc lập để tìm thay đổi gây ra lỗi.

## 13. Chiến lược bảo trì an toàn cho dự án lớn

### 13.1. Tách thay đổi cấu trúc và thay đổi chức năng

Một pull request chỉ thay `copydir` thành `copy` dễ review hơn PR vừa thay task, vừa đổi nội dung artifact, vừa chuyển JDK và nâng các thư viện nghiệp vụ. Nếu buộc thay đồng thời vì phụ thuộc phiên bản, hãy mô tả rõ sự phụ thuộc và tác động.

Ví dụ chia thành các bước:

1. Ghi baseline: kết quả test, danh sách artifact, checksum, phiên bản Ant/JDK.
2. Thay các task deprecated đơn giản: copy/delete/move; so đầu ra.
3. Nâng thư viện custom task và task tùy chọn.
4. Nâng Ant; kiểm tra các target.
5. Nâng JDK/`release` và xử lý công cụ bị loại.
6. Chạy ma trận CI, kiểm tra artifact cuối và ghi nhận thay đổi có chủ đích.

Thứ tự thực tế có thể khác tùy tương thích của phiên bản Ant/JDK; cần chọn lộ trình mà mỗi giai đoạn vẫn có thể xây dựng và kiểm tra được.

### 13.2. Có phương án rollback

Nên giữ thông tin phiên bản Ant/JDK và cấu hình CI cũ để có thể quay lại nhanh trong trường hợp phát hiện lỗi phát hành. Khi sửa `build.xml`, version control cho phép quay lại từng thay đổi. Nếu đang nâng dependency, dùng phiên bản cố định hoặc lock/checksum để tránh “rollback buildfile” nhưng vẫn nhận thư viện đã thay.

Rollback không phải giải pháp dài hạn cho JDK đã ngừng hỗ trợ, nhưng là biện pháp vận hành có thể cần dùng trong khoảng thời gian xử lý sự cố được kiểm soát.

### 13.3. Ưu tiên task đa nền tảng

Nhiều công việc có thể thực hiện bằng task core của Ant:

- `<copy>` thay lệnh `cp`/`copy` trong shell.
- `<delete>` thay các lệnh xóa khác nhau trên Linux/Windows.
- `<mkdir>` để tạo thư mục.
- `<move>` để di chuyển file.
- `<path>`/`<pathelement>` để dựng classpath.

Task Ant không loại bỏ mọi khác biệt OS, nhưng thường giúp giới hạn cách diễn giải đường dẫn và exit code. Nếu buộc gọi lệnh ngoài bằng `<exec>`, khai báo rõ điều kiện hệ điều hành, công cụ cần cài và cách xử lý lỗi.

### 13.4. Tài liệu hóa quyết định

Với mỗi thay đổi task hoặc toolchain, nên ghi:

| Trường | Ví dụ |
| --- | --- |
| Thành phần cũ | `<copydir>` trong target `resources` |
| Thay thế | `<copy>` + `<fileset>` |
| Lý do | Task cũ deprecated, khó bảo trì |
| Khác biệt cần quan tâm | `includes`, `overwrite`, mtime |
| Kết quả kiểm tra | Clean/incremental build, resource list, smoke test |
| Môi trường đã xác nhận | Ant cụ thể, JDK 17/21, OS đích |
| Rủi ro còn lại | Ví dụ chưa kiểm tra Windows ARM64 |

Một bản ghi như vậy giúp người khác tiếp tục nâng cấp sau này mà không phải suy đoán tại sao một thuộc tính được đặt thành `true` hoặc `false`.

## 14. Bài thực hành

### Bài 1: Chuyển task mà giữ nguyên đầu ra

Tạo dự án mục 7, sau đó viết một target phụ bằng `copydir` để sao chép resource (chỉ dùng để quan sát cơ chế cũ). Chuyển sang `copy` + `fileset`. So số lượng file, đường dẫn tương đối, nội dung và khả năng chạy JAR.

### Bài 2: Phát hiện file đầu ra cũ

Chạy `ant clean verify`, sau đó thử xóa `resources/app.properties` hoặc đổi tên rồi chạy `ant verify` mà không clean. Quan sát vì sao file đã copy từ lần trước có thể còn ở `build/classes`. Khắc phục bằng chiến lược clean/prune đầu ra phù hợp trước giai đoạn phát hành, rồi so với clean build từ cùng source.

### Bài 3: Kiểm tra mức JDK

Chạy build mẫu với JDK 17 và JDK 21, giữ `release=17`. Thử đặt `-Djava.release=21` khi đang dùng compiler JDK 17 và ghi nhận lỗi. Giải thích sự khác nhau giữa runtime/compiler thực tế và mức Java đích.

### Bài 4: Kiểm tra mã thoát

Tạm thay `app.mode=production` bằng giá trị sai trong file nguồn của bài thực hành. Chạy `ant clean verify` và xác nhận target `smoke` thất bại do `failonerror="true"`. Khôi phục cấu hình, chạy lại và xác nhận build thành công.

### Bài 5: Rà soát dự án Ant đang bảo trì

Chọn một dự án sử dụng nhiều file XML, `taskdef` hoặc antlib. Lập danh sách task core lỗi thời, custom task và công cụ JDK cũ. Đề xuất cách thay, kiểm tra được bằng test/đầu ra, và ma trận phiên bản Ant/JDK cần có. Không thay task chưa hiểu semantics hoặc chưa xác định đầu ra mong muốn.

## 15. Ghi nhớ

Bảo trì Apache Ant sau một đợt nâng Ant hoặc JDK cần tách hai việc:

- **Thay các task deprecated bằng task hiện đại có semantics rõ ràng**, ví dụ `copydir` → `copy`, `copyfile` → `copy`, `deltree` → `delete`, `rename` → `move` và `javadoc2` → `javadoc`.
- **Kiểm chứng tương thích thật sự của toolchain và artifact**, gồm compiler level, công cụ JDK bị loại, module/API, custom task, clean/incremental build, test và khả năng chạy trên runtime được hỗ trợ.

Một bản build báo thành công chỉ chứng minh những task đã chạy không báo lỗi. Bảo trì chỉ hoàn tất khi **sản phẩm đầu ra vẫn đúng**, các môi trường cam kết hỗ trợ đã được kiểm tra và các thay đổi hành vi có chủ đích được ghi lại để người sau có thể tiếp tục bảo trì.

## Tài liệu tham khảo

- [Apache Ant Manual — Deprecated Tasks](https://ant.apache.org/manual/deprecated.html): danh sách task lỗi thời và hướng thay thế.
- [Apache Ant — Copy](https://ant.apache.org/manual/Tasks/copy.html): sao chép file/resource, `fileset`, mtime và filter.
- [Apache Ant — Delete](https://ant.apache.org/manual/Tasks/delete.html): xóa file hoặc cây thư mục.
- [Apache Ant — Move](https://ant.apache.org/manual/Tasks/move.html): di chuyển và đổi tên.
- [Apache Ant — Javac](https://ant.apache.org/manual/Tasks/javac.html): `release`, `source`, `target` và cấu hình compiler.
- [Apache Ant — Javadoc](https://ant.apache.org/manual/Tasks/javadoc.html): tạo tài liệu API.
- [Apache Ant — Java](https://ant.apache.org/manual/Tasks/java.html): chạy JVM con, classpath, xử lý exit code.
- [Apache Ant — Running Ant](https://ant.apache.org/manual/running.html): lệnh Ant và tham số chẩn đoán.
- [OpenJDK JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): cơ chế `javac --release`.
- [OpenJDK JEP 313 — Remove the Native-Header Generation Tool](https://openjdk.org/jeps/313): chuyển từ `javah` sang `javac -h`.
- [OpenJDK JEP 367 — Remove the Pack200 Tools and API](https://openjdk.org/jeps/367): loại bỏ Pack200.
- [OpenJDK JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): tác động đến script engine.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): những thay đổi trong truy cập API nội bộ của JDK.

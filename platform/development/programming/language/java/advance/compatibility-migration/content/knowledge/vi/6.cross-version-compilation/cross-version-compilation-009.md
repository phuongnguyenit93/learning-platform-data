# Thư viện phụ thuộc có bytecode cao hơn mức hỗ trợ đã công bố

Một ứng dụng có thể được biên dịch thành công với target Java 17 nhưng vẫn không chạy được trên Java 17 vì một thư viện phụ thuộc chứa class file được biên dịch cho Java 21. Tình huống này thường xuất hiện khi nâng version dependency, khi một thư viện cập nhật build JDK mà quên giữ mức runtime tối thiểu, hoặc khi dependency bắc cầu thay đổi mà ứng dụng không chủ động nâng cấp.

**Thư viện phụ thuộc có bytecode cao hơn mức hỗ trợ đã công bố** là trường hợp artifact được tuyên bố hỗ trợ một runtime nhất định, nhưng một hoặc nhiều class mà runtime đó cần nạp lại có class-file version vượt quá khả năng của runtime. Mức hỗ trợ được công bố có thể nằm trong tài liệu, release note, metadata của package hoặc hợp đồng của sản phẩm. Khi bytecode thực tế không đáp ứng mức đó, consumer có thể không khởi động được hoặc chỉ lỗi khi đi vào một luồng chức năng cụ thể.

Đây là vấn đề của toàn bộ dependency graph, không chỉ thư viện mà ứng dụng khai báo trực tiếp. Một thư viện chính có thể được biên dịch cho Java 17 nhưng kéo theo dependency chỉ chạy trên Java 21. Nếu không kiểm tra artifact đã resolve, việc xác nhận source code của ứng dụng dùng --release 17 vẫn chưa chứng minh sản phẩm hỗ trợ Java 17.

## 1. Hiểu đúng mức Java tối thiểu của một thư viện

Khi nhà cung cấp ghi “requires Java 17” hoặc “supports Java 17+”, thông tin đó thường có nghĩa runtime Java 17 trở lên nằm trong phạm vi hỗ trợ của thư viện. Để thực hiện cam kết này, các class cần được nạp trên Java 17 phải dùng class-file format mà Java 17 hiểu, và các API, module, dependency cùng hành vi runtime cũng phải tương thích.

Có ít nhất ba điều kiện riêng cần xem xét:

1. **Class-file compatibility:** JVM có đọc được định dạng .class không?
2. **API compatibility:** code có gọi API Java SE hoặc API thư viện mà runtime đích thực sự cung cấp không?
3. **Runtime behavior compatibility:** dependency có hoạt động đúng với semantics, module system, TLS, reflection, GC và các đặc điểm runtime của JDK đích không?

Class-file version là điều kiện cần để JVM nạp class, nhưng chưa đủ để chứng minh thư viện chạy được. Một class có major version 61 vẫn có thể gọi một method chỉ có từ Java 21 nếu nó được biên dịch theo cách không giới hạn API phù hợp; khi chạy Java 17, lỗi có thể là NoSuchMethodError thay vì UnsupportedClassVersionError.

### 1.1. Class-file major version

Mỗi class file có header chứa magic number, minor version và major version. Major version cho biết định dạng class file. Một số mốc phổ biến:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Với các release Java hiện đại, có thể quy đổi major version sang release bằng cách lấy major trừ 44. Ví dụ major 61 tương ứng Java 17; major 65 tương ứng Java 21. Khi phân tích class thực tế, dùng javap -verbose hoặc đọc header của class file để xác minh thay vì suy đoán từ tên JAR.

Nếu JVM phải nạp class có major version cao hơn mức hỗ trợ, nó có thể ném UnsupportedClassVersionError. Ví dụ, Java 17 hỗ trợ class-file major 61; nếu class cần nạp có major 65, JVM Java 17 không hiểu định dạng class đó.

### 1.2. Compiler version không đồng nghĩa target version

Một thư viện được build bằng JDK 21 vẫn có thể hỗ trợ Java 17 nếu tác giả biên dịch đúng với --release 17 và các dependency cũng tương thích. Ngược lại, một thư viện build bằng JDK 17 không tự động hỗ trợ Java 17 nếu nó kéo dependency chỉ chạy trên Java 21.

Do đó, không thể kết luận mức runtime tối thiểu chỉ từ:

- Tên version của artifact.
- JDK dùng trong CI của nhà cung cấp.
- Giá trị maven.compiler.source hoặc target nhìn thấy trong một POM.
- Giá trị sourceCompatibility hoặc targetCompatibility của một project Gradle.
- Việc ứng dụng của consumer biên dịch thành công.

Cần kiểm tra bytecode trong artifact đã resolve, API được sử dụng và dependency bắc cầu ở đúng runtime mục tiêu.

## 2. Vì sao dependency có thể phá vỡ runtime floor?

### 2.1. Thư viện trực tiếp được build bằng release cao hơn

Ứng dụng khai báo:

~~~text
orders-api
  └── com.vendor:payment-client:5.0
~~~

Nhà cung cấp tuyên bố payment-client:5.0 hỗ trợ Java 17, nhưng class PaymentClient trong JAR có major version 65. Ứng dụng chạy trên Java 17 sẽ không nạp được class này khi đường code sử dụng nó được thực thi.

Một nguyên nhân phổ biến là pipeline của thư viện dùng JDK mới nhưng build không đặt --release hoặc target tương ứng. Artifact vẫn được publish với version hợp lệ, POM vẫn resolve bình thường, nhưng bytecode không phù hợp với cam kết runtime.

### 2.2. Dependency bắc cầu nâng mức Java tối thiểu

Ví dụ:

~~~text
orders-api
  └── payment-client:5.0       (base bytecode Java 17)
        └── transport-core:4.2 (base bytecode Java 21)
~~~

Ứng dụng không khai báo transport-core trực tiếp. Build tool tự resolve nó qua dependency của payment-client. Nếu runtime Java 17 phải nạp một class của transport-core, ứng dụng có thể lỗi dù source của orders-api và bytecode của payment-client đều ở major 61.

Một dependency graph cần được xem như một tập artifact có quan hệ phụ thuộc, không phải một danh sách các dependency trực tiếp. Cần kiểm tra cả runtime classpath, dependency được chọn sau conflict resolution và các variant mà build tool resolve.

### 2.3. Version mới thay đổi bytecode nhưng không thay đổi tên artifact

Nhà cung cấp có thể giữ cùng group, artifact và tên thư viện nhưng phát hành version mới với baseline Java cao hơn. Nếu release note không nêu rõ mức Java tối thiểu, consumer có thể nâng version theo quy trình cập nhật dependency thông thường và chỉ phát hiện lỗi ở môi trường runtime cũ.

Không nên mặc định các version cùng major hoặc minor của một thư viện giữ nguyên runtime floor. Kiểm tra support matrix và artifact của đúng version đã resolve.

### 2.4. Nhiều class trong cùng JAR có mức bytecode khác nhau

Một JAR thông thường có thể chứa class file được tạo từ nhiều module hoặc bước build khác nhau. Class chính có thể có major 61 nhưng một helper class, class lồng nhau, package phụ hoặc generated class có major 65. Chỉ kiểm tra một class đại diện có thể bỏ sót vấn đề.

Các class được nạp lười theo đường code. Vì vậy, ứng dụng có thể khởi động và chạy health check thành công, nhưng chỉ lỗi khi một tính năng cụ thể nạp class có bytecode cao hơn runtime.

### 2.5. Multi-release JAR

Multi-release JAR là cơ chế cho phép một thư viện cung cấp implementation khác nhau cho các JDK khác nhau. JAR có manifest Multi-Release: true và có thể chứa:

~~~text
library.jar
├── META-INF/MANIFEST.MF
├── com/example/Parser.class
└── META-INF/versions/
    ├── 17/com/example/Parser.class
    └── 21/com/example/Parser.class
~~~

Class trong thư mục gốc là implementation nền. JVM chọn implementation trong META-INF/versions/N phù hợp với release đang chạy, theo quy tắc multi-release JAR. Với runtime Java 17, class trong versions/21 không được chọn; class nền hoặc bản version cao nhất không vượt quá 17 sẽ được dùng.

Vì vậy, scanner báo class major 65 trong META-INF/versions/21 chưa đủ để kết luận JAR không hỗ trợ Java 17. Cần xác minh manifest có Multi-Release: true và tính đúng view mà runtime đích sẽ chọn. Ngược lại, nếu class nền có major 65, JAR sẽ không chạy trên Java 17 dù bên trong có thư mục versions/17.

## 3. Các biểu hiện khi runtime floor bị vi phạm

| Thời điểm | Biểu hiện | Nguyên nhân có thể |
|---|---|---|
| Compile | bad class file ... wrong version 65.0, should be 61.0 | Compiler cũ không đọc được class file dependency mới hơn |
| Startup | UnsupportedClassVersionError | JVM nạp class có major/minor không được hỗ trợ |
| Startup hoặc khi dùng tính năng | NoSuchMethodError / NoSuchFieldError | Class file đọc được nhưng API runtime không có member mà bytecode tham chiếu |
| Startup hoặc lúc khởi tạo | NoClassDefFoundError | Thiếu class bắc cầu, lỗi khởi tạo trước đó hoặc class loader không tìm thấy class |
| Chỉ ở một nhánh chức năng | Lỗi xuất hiện khi class được nạp lần đầu | Class loading diễn ra lười; đường code chưa được chạy khi smoke test |
| Chỉ ở runtime cụ thể | Một môi trường chạy, môi trường khác lỗi | Runtime, dependency resolution hoặc multi-release view khác nhau |

Một lỗi UnsupportedClassVersionError thường cho biết class file cụ thể và phiên bản mà JVM mong đợi. Hãy ghi nhận tên class và nguồn JAR trong stack trace hoặc class loading log để tìm đúng artifact gây lỗi.

Không phải mọi lỗi “Java version” đều do major version. NoSuchMethodError thường là dấu hiệu compile-time và runtime đang dùng các version API khác nhau; ClassNotFoundException có thể là classpath/module path; InaccessibleObjectException liên quan reflective access và module system. Cần phân loại trước khi thay đổi dependency hoặc runtime.

## 4. Kiểm tra dependency graph thực tế

Trước khi quét bytecode, hãy xác định chính xác artifact và version mà build đã resolve. Version khai báo trong file build có thể là version range, constraint, platform/BOM hoặc version bị conflict resolution thay thế.

### 4.1. Với Gradle

Liệt kê runtime dependency:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm lý do một dependency được chọn:

~~~bash
./gradlew dependencyInsight \
  --dependency transport-core \
  --configuration runtimeClasspath
~~~

Đối với cấu hình compile, kiểm tra thêm compileClasspath. Dependency có thể xuất hiện ở compile nhưng không có ở runtime hoặc ngược lại do scope, variant, exclusion và cấu hình project.

Gradle Module Metadata có thể công bố variant với thuộc tính org.gradle.jvm.version. Thuộc tính này giúp Gradle lựa chọn variant phù hợp với JVM target khi metadata và consumer được cấu hình tương thích. Tuy nhiên, không phải mọi thư viện đều publish metadata này; Maven POM hoặc repository mirror có thể chỉ cung cấp thông tin khác. Không coi dependency graph resolve thành công là bằng chứng bytecode đã được kiểm tra đầy đủ.

### 4.2. Với Maven

Liệt kê dependency tree:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Xem cả dependency compile nếu cần:

~~~bash
mvn dependency:tree -Dscope=compile
~~~

Để xem POM hiệu lực sau khi áp dụng parent, profile và property:

~~~bash
mvn help:effective-pom
~~~

POM có thể giúp tìm version, scope, exclusion và cấu hình build của dependency. Tuy nhiên, các cấu hình compiler trong POM của thư viện không phải lúc nào cũng được truyền thành một cam kết runtime có thể được mọi consumer kiểm tra. Hãy đối chiếu support matrix của nhà cung cấp với bytecode thực tế.

### 4.3. Kiểm tra đúng artifact đã resolve

Sau khi có dependency graph, lấy đường dẫn JAR từ cache hoặc thư mục dependency đã resolve. Kiểm tra tọa độ group/artifact/version, checksum nếu có và repository nguồn. Tránh phân tích một JAR cùng tên nhưng được tải từ cache cũ hoặc thư mục thủ công khác.

Với Gradle, có thể dùng dependency report, build scan hoặc task/cấu hình in artifact file của configuration. Với Maven, có thể dùng dependency plugin để build classpath hoặc xem file trong local repository. Ghi lại artifact cụ thể trước khi kết luận.

## 5. Kiểm tra class-file version trong dependency JAR

### 5.1. Kiểm tra một class đã biết bằng javap

Nếu biết fully qualified class name:

~~~bash
javap -verbose -classpath transport-core-4.2.jar com.vendor.transport.TransportClient
~~~

Tìm:

~~~text
minor version: 0
major version: 65
~~~

Major 65 tương ứng class-file format Java 21. Nếu runtime floor cần hỗ trợ là Java 17 và đây là class được runtime Java 17 chọn để nạp, dependency đang vượt quá mức hỗ trợ đó.

javap có thể đọc class trong JAR qua classpath. Cần chỉ rõ đúng artifact và tên lớp. Với class không có trong JAR hoặc class trùng tên, kết quả có thể đến từ nguồn khác trong classpath; giữ classpath tối giản để tránh nhầm lẫn.

### 5.2. Liệt kê class trong JAR

Xem danh sách entry:

~~~bash
jar --list --file transport-core-4.2.jar
~~~

Lệnh này giúp tìm package và class cần phân tích. Nhưng một JAR có thể chứa hàng trăm hoặc hàng nghìn class; kiểm tra thủ công từng class không thực tế. Có thể dùng một script đọc header class file để thống kê major version của tất cả entry .class.

Ví dụ Python dùng thư viện chuẩn zipfile:

~~~python
from pathlib import Path
from zipfile import ZipFile
import sys

MAGIC = b"\xca\xfe\xba\xbe"

for jar_name in sys.argv[1:]:
    path = Path(jar_name)
    print(f"JAR: {path}")

    with ZipFile(path) as archive:
        for entry in archive.namelist():
            if not entry.endswith(".class"):
                continue

            header = archive.read(entry)[:8]
            if len(header) < 8 or header[:4] != MAGIC:
                continue

            minor = int.from_bytes(header[4:6], "big")
            major = int.from_bytes(header[6:8], "big")
            java_release = major - 44
            preview = minor == 65535

            print(
                f"  {entry}: major={major}, minor={minor}, "
                f"approx_java={java_release}, preview={preview}"
            )
~~~

Lưu script thành inspect_class_versions.py, rồi truyền một hoặc nhiều JAR:

~~~bash
python inspect_class_versions.py transport-core-4.2.jar payment-client-5.0.jar
~~~

Script đọc header của mọi class entry, kể cả class lồng nhau và class nằm trong thư mục version của multi-release JAR. Nó không cần giải nén toàn bộ JAR ra disk. Công thức major trừ 44 dùng cho các class-file version hiện đại được liệt kê trong ví dụ; hãy xem đây là cách quy đổi nhanh, đồng thời lưu major/minor gốc để đối chiếu chính xác.

Script trên chỉ báo version từng entry, chưa tự quyết định class nào runtime sẽ chọn trong multi-release JAR. Cần đọc manifest và xử lý META-INF/versions/N theo release đích trước khi đánh dấu entry là vi phạm.

### 5.3. Diễn giải kết quả scanner

Giả sử runtime floor là Java 17:

| Entry trong JAR | Major version | Diễn giải sơ bộ |
|---|---:|---|
| com/vendor/Client.class | 61 | Định dạng phù hợp Java 17 |
| com/vendor/Helper.class | 65 | Không phù hợp nếu đây là class được Java 17 nạp |
| META-INF/versions/21/com/vendor/Client.class | 65 | Có thể hợp lệ nếu JAR là multi-release và Java 17 không chọn entry này |
| META-INF/versions/17/com/vendor/Client.class | 61 | View Java 17 có thể dùng entry này nếu manifest và cấu trúc JAR hợp lệ |

Với multi-release JAR, cần:

1. Đọc META-INF/MANIFEST.MF và xác nhận Multi-Release: true.
2. Nhóm entry theo logical class name, bỏ prefix META-INF/versions/N/ để nhận diện các bản thay thế.
3. Với runtime Java N, chọn entry versioned có N lớn nhất nhưng không vượt quá runtime N; nếu không có thì dùng entry ở thư mục gốc.
4. Kiểm tra class-file version của entry được chọn. Các entry version cao hơn runtime sẽ không được runtime đó chọn.

Nếu manifest không bật multi-release, không diễn giải các entry dưới META-INF/versions/ như implementation thay thế được JVM chọn. Đối chiếu theo quy tắc JAR multi-release và công cụ/runtime cụ thể.

### 5.4. Preview class file

Class file dùng preview feature có thể mang minor version: 65535. Chúng yêu cầu runtime cùng Java release tương ứng và thường cần --enable-preview. Một class preview của Java 21 không trở thành class portable chỉ vì major version của nó không vượt quá mức runtime; điều kiện preview phải được đáp ứng riêng.

Nếu inventory phát hiện minor version 65535, ghi nhận release tạo class, cách compiler bật preview và cấu hình runtime. Không chỉ so sánh major version rồi kết luận tương thích.

## 6. Đọc metadata và bytecode để xác minh API

Class-file version trả lời JVM có đọc được định dạng hay không. Để hiểu class tham chiếu API nào, có thể dùng thêm các chế độ của javap.

~~~bash
javap -p -s -classpath transport-core-4.2.jar com.vendor.transport.TransportClient
javap -c -classpath transport-core-4.2.jar com.vendor.transport.TransportClient
javap -verbose -classpath transport-core-4.2.jar com.vendor.transport.TransportClient
~~~

- -p hiển thị cả member private.
- -s hiển thị JVM descriptor của field và method.
- -c hiển thị bytecode instruction.
- -verbose hiển thị constant pool, version và các attribute chi tiết.

Khi điều tra NoSuchMethodError, so sánh descriptor mà consumer đã biên dịch tham chiếu với method trong class runtime thực tế. Khi điều tra API Java SE mới, jdeps có thể hỗ trợ phân tích phụ thuộc package/module và JDK internals:

~~~bash
jdeps --multi-release 17 --jdk-internals transport-core-4.2.jar
~~~

jdeps hữu ích cho dependency analysis và JDK internal API, nhưng không thay thế scanner class-file major version. Một JAR có thể có major version phù hợp mà vẫn tham chiếu API không tồn tại trên runtime đích; ngược lại, JAR có entry version cao trong phần multi-release dành cho JDK mới không nhất thiết phá runtime cũ.

## 7. Tìm class được nạp và artifact gây lỗi

Khi một ứng dụng có nhiều version của cùng thư viện, phân tích nhầm JAR có thể dẫn đến kết luận sai. Trên HotSpot/OpenJDK JDK 9 trở lên, bật class loading log trong môi trường kiểm thử:

~~~bash
java -Xlog:class+load=info -cp app.jar com.example.Main
~~~

Với JDK cũ hơn:

~~~bash
java -verbose:class -cp app.jar com.example.Main
~~~

Log giúp xác định class được nạp từ JAR hoặc thư mục nào. Sau đó dùng javap và scanner trên chính artifact đó. Nếu lỗi chỉ xảy ra ở một chức năng, cần thực thi luồng đó để kích hoạt việc nạp class liên quan; startup thành công không chứng minh toàn bộ dependency graph đã tương thích.

Khi runtime có custom class loader, plugin loader, application server hoặc module layer, class source có thể không đơn giản là classpath của lệnh khởi chạy. Kết hợp log class loading với cấu hình loader và thông tin deployment.

## 8. Các chiến lược xử lý dependency vượt runtime floor

Sau khi xác định artifact và class gây lỗi, chọn cách xử lý theo hợp đồng hỗ trợ của sản phẩm.

### 8.1. Dùng version dependency còn hỗ trợ runtime đích

Tìm release cũ hơn có support matrix phù hợp và xác minh bytecode của artifact cùng các dependency bắc cầu. Pin version cụ thể, kiểm tra security/bug fixes và ghi nhận thời hạn sử dụng nếu đây là giải pháp chuyển tiếp.

Không hạ version một cách mù quáng. Version cũ có thể chứa lỗ hổng hoặc lỗi đã được sửa; cần cân nhắc rủi ro và chọn release được nhà cung cấp hỗ trợ.

### 8.2. Chọn variant phù hợp

Một số thư viện publish nhiều variant hoặc multi-release JAR. Chọn đúng variant dành cho runtime mục tiêu, xác minh metadata và entry thực tế. Với Gradle, kiểm tra thuộc tính variant như org.gradle.jvm.version nếu publisher cung cấp Gradle Module Metadata. Với Maven, xác nhận artifact/version classifier hoặc profile thực tế được nhà cung cấp công bố.

Không giả định mọi repository hoặc consumer đều sử dụng cùng metadata. Hãy kiểm tra file đã được resolve và bytecode bên trong.

### 8.3. Yêu cầu upstream phát hành artifact đúng baseline

Nếu thư viện công bố hỗ trợ Java 17 nhưng base class được build thành major 65, cung cấp bằng chứng cụ thể cho upstream: tọa độ artifact, checksum, class entry, major/minor version, runtime mục tiêu và thông báo lỗi. Nhà cung cấp có thể phát hành lại artifact với --release 17 hoặc điều chỉnh support matrix.

Chỉ rebuild từ source khi có quyền và khả năng kiểm soát toàn bộ build/dependency. Biên dịch source của thư viện với --release 17 không tự sửa các dependency bắc cầu vẫn chứa bytecode Java 21.

### 8.4. Nâng runtime floor của ứng dụng

Nếu dependency mới thực sự yêu cầu Java 21 và sản phẩm có thể nâng runtime, cập nhật support statement của ứng dụng, toolchain, container image, CI/CD, deployment, kiểm thử và hướng dẫn vận hành. Cần xác minh mọi process liên quan cùng đáp ứng baseline mới, bao gồm batch, worker và công cụ quản trị.

Đây là thay đổi phạm vi hỗ trợ của sản phẩm; cần đánh giá consumer còn chạy Java 17 trước khi rollout.

### 8.5. Tách dependency thành process riêng

Nếu ứng dụng chính phải tiếp tục chạy Java 17 nhưng một thành phần chỉ hỗ trợ Java 21, có thể tách thành process/service độc lập chạy Java 21 và giao tiếp qua API hoặc message contract. Cách này tạo ranh giới runtime rõ ràng nhưng tăng chi phí vận hành, giao tiếp, quan sát và xử lý lỗi phân tán.

### 8.6. Không dùng shading hoặc bytecode downgrade như giải pháp mặc định

Shading/relocation đổi package hoặc tên class để tránh xung đột; nó không tự hạ class-file version và không backport API mới. Công cụ hạ bytecode có thể thay đổi header nhưng không thể tự tạo ra API Java cũ tương đương, cũng không đảm bảo semantics, verifier và module behavior đúng. Chỉ xem xét các kỹ thuật này khi có quy trình kỹ thuật được kiểm chứng cho đúng thư viện và runtime.

## 9. Kiểm thử dependency trên runtime thấp nhất được công bố

Để chứng minh một ứng dụng hỗ trợ Java 17, cần kiểm tra trên Java 17 thực tế hoặc runtime tương đương được hỗ trợ. Build thành công trên JDK 21 không đủ.

Một chiến lược kiểm tra có thể gồm:

1. Resolve dependency graph sạch từ repository đã cấu hình; lưu tọa độ và checksum của artifact.
2. Quét class-file version của các JAR runtime, phân biệt base entry và multi-release entry.
3. Biên dịch source của ứng dụng với --release 17 hoặc cấu hình build tương đương.
4. Chạy test trên JDK 17 bằng executable/container image được pin.
5. Thực thi các luồng chức năng có thể nạp dependency tùy chọn hoặc lazy-loaded.
6. Kiểm tra class loading log khi cần xác định artifact thực tế.
7. Chạy integration/contract test với hệ thống ngoài, TLS, reflection và module access có liên quan.
8. Lặp lại trên các môi trường deployment đại diện và lưu bằng chứng.

Scanner bytecode là bộ lọc tĩnh hữu ích, nhưng không thay thế chạy thử. Một dependency có thể có class version phù hợp nhưng vẫn gọi API không có trên Java 17; một class version cao nằm trong nhánh multi-release dành cho Java 21 có thể hoàn toàn hợp lệ với runtime Java 17.

## 10. Checklist điều tra dependency có bytecode quá mới

- [ ] Đã xác định runtime floor được công bố cho ứng dụng và từng thư viện quan trọng.
- [ ] Đã lấy dependency graph và version artifact thực tế được resolve.
- [ ] Đã kiểm tra dependency bắc cầu trong runtime classpath.
- [ ] Đã quét class-file major/minor version của các JAR liên quan.
- [ ] Đã phân biệt class nền với entry trong multi-release JAR và xác minh manifest.
- [ ] Đã xác định class cụ thể gây lỗi và nguồn artifact của class đó.
- [ ] Đã phân biệt UnsupportedClassVersionError với lỗi API linkage, classpath và module.
- [ ] Đã kiểm tra preview class file nếu có.
- [ ] Đã đánh giá API Java SE và dependency khác ngoài class-file version.
- [ ] Đã chọn giải pháp phù hợp: version cũ, variant đúng, upstream fix, nâng runtime floor hoặc tách process.
- [ ] Đã chạy ứng dụng và luồng chức năng trên runtime thấp nhất cần hỗ trợ.
- [ ] Đã lưu artifact/version/checksum, lệnh kiểm tra và kết quả test.

## 11. Kết luận

Một thư viện chỉ thực sự đáp ứng mức Java tối thiểu đã công bố khi các class được runtime đích chọn có bytecode và API tương thích, đồng thời toàn bộ dependency graph hoạt động trên runtime đó. Hãy kiểm tra artifact đã resolve, quét class-file version, hiểu đúng multi-release JAR, xác định class thực sự được nạp và chạy các luồng chức năng trên runtime thấp nhất cần hỗ trợ. Khi phát hiện bytecode quá mới, xử lý tại nguồn dependency hoặc điều chỉnh rõ ràng runtime floor; không dựa vào việc ứng dụng của mình biên dịch thành công để kết luận thư viện tương thích.
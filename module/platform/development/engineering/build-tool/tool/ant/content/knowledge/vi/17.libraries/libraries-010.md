# Cố định phiên bản và chuẩn bị thư viện cho build ngoại tuyến

Một build Ant chỉ thật sự có thể chạy ổn định khi các thư viện mà nó cần đã được xác định rõ và có sẵn trong môi trường build. Nếu build tải dependency mới nhất từ Internet mỗi lần chạy, kết quả có thể thay đổi khi phiên bản trên máy chủ thay đổi, mạng gặp sự cố hoặc một repository không truy cập được.

Cách tổ chức đáng tin cậy là cố định phiên bản của từng dependency, lưu danh sách thư viện cùng thông tin kiểm tra, chuẩn bị đầy đủ các tệp cần thiết trước khi ngắt mạng và cấu hình build chỉ sử dụng những thành phần đã có tại chỗ. Nhờ vậy, cùng một mã nguồn có thể được build trên máy phát triển, máy chủ CI hoặc môi trường mạng hạn chế với kết quả có thể dự đoán hơn.

Trong Apache Ant, bản thân core Ant không tự động giải quyết và tải dependency ứng dụng như một dependency manager. Build file thường khai báo classpath từ các JAR đã có trên đĩa. Nếu dự án tích hợp Apache Ivy hoặc công cụ resolve khác, việc tải và lưu cache là trách nhiệm của công cụ đó. Cần thiết kế rõ bước chuẩn bị dependency và bước build ngoại tuyến.

## 1. Vì sao phải cố định phiên bản thư viện?

Một ứng dụng Java thường phụ thuộc vào nhiều thư viện bên ngoài: logging, xử lý JSON, kết nối cơ sở dữ liệu, test framework hoặc các API chuyên biệt. Mỗi thư viện có thể có nhiều phiên bản, và các phiên bản khác nhau không nhất thiết tương thích với nhau.

Nếu build sử dụng tên phiên bản không cố định hoặc lấy một JAR tùy ý từ thư mục, các vấn đề sau có thể xảy ra:

- Build hôm nay thành công nhưng ngày mai thất bại vì repository đã phát hành phiên bản mới.
- Một thư viện được cập nhật làm thay đổi API hoặc hành vi lúc chạy.
- Hai thư viện phụ thuộc vào các phiên bản khác nhau của cùng một thư viện nền.
- Máy phát triển có JAR mới hơn máy CI nên kết quả không giống nhau.
- Môi trường ngoại tuyến không thể lấy dependency còn thiếu.
- Một tệp JAR bị thay thế nhưng build không phát hiện được.

Cố định phiên bản có nghĩa là ghi rõ phiên bản cụ thể mà dự án đã chọn và dùng đúng tệp tương ứng. Ví dụ:

| Không cố định | Cố định |
|---|---|
| `commons-lang3.jar` không rõ phiên bản | `commons-lang3-3.14.0.jar` |
| `junit.jar` tùy máy | `junit-4.13.2.jar` |
| Lấy bản mới nhất từ repository | Ghi rõ tọa độ, phiên bản và checksum đã duyệt |
| Dùng mọi JAR trong thư mục | Khai báo rõ từng JAR cần thiết |

Tên file có phiên bản giúp con người nhận diện dependency, nhưng tên file một mình chưa đủ để chứng minh nội dung bên trong đúng. Nên kết hợp với checksum SHA-256 và một danh sách dependency được quản lý cùng mã nguồn.

## 2. Xác định toàn bộ dependency của dự án

### 2.1. Phân biệt dependency trực tiếp và dependency bắc cầu

Dependency trực tiếp là thư viện mà dự án chủ động sử dụng. Dependency bắc cầu là thư viện khác được một dependency trực tiếp yêu cầu.

Ví dụ:

~~~text
Ứng dụng
  |
  +-- thư viện JSON
  |      |
  |      +-- thư viện annotations
  |
  +-- thư viện logging API
         |
         +-- logging implementation
~~~

Nếu chỉ sao chép thư viện JSON và logging API mà bỏ quên dependency bắc cầu, ứng dụng có thể biên dịch được nhưng lỗi khi chạy. Vì vậy, danh sách offline phải bao gồm toàn bộ thư viện cần cho từng giai đoạn, không chỉ các JAR mà mã nguồn import trực tiếp.

Với mỗi dependency, ghi nhận:

- Tên thư viện và phiên bản.
- Nguồn lấy thư viện, ví dụ repository nội bộ hoặc kho artifact được phê duyệt.
- Tệp JAR chính xác.
- Các dependency bắc cầu cần thiết.
- Phạm vi sử dụng: compile, runtime, test hoặc công cụ build.
- Checksum SHA-256.
- Điều kiện giấy phép hoặc thông tin phân phối nếu dự án yêu cầu.

### 2.2. Tách dependency theo mục đích

Không nên gom mọi JAR vào một classpath duy nhất. Một cấu trúc đơn giản:

~~~text
my-ant-project/
├── build.xml
├── config/
│   └── dependencies.lock.properties
├── lib/
│   ├── compile/
│   │   └── commons-lang3-3.14.0.jar
│   ├── runtime/
│   │   └── logging-implementation-1.0.0.jar
│   └── test/
│       └── junit-4.13.2.jar
├── src/
│   ├── main/java/
│   └── test/java/
└── build/
~~~

Ý nghĩa:

- `lib/compile`: thư viện cần để biên dịch mã nguồn.
- `lib/runtime`: thư viện cần khi chạy ứng dụng.
- `lib/test`: thư viện chỉ dùng để biên dịch hoặc chạy test.
- `config/dependencies.lock.properties`: danh sách phiên bản, tên tệp và checksum được chốt.

Một thư viện có thể cần ở cả compile và runtime. Khi đó, hãy thể hiện nó trong các classpath tương ứng. Không đưa JUnit hoặc công cụ test vào artifact ứng dụng chỉ vì chúng nằm chung một thư mục lib.

## 3. Tạo danh sách dependency cố định

### 3.1. Dùng một tệp lock do dự án quản lý

Với build Ant thuần, có thể lưu tên tệp và checksum trong property file. Ví dụ `config/dependencies.lock.properties`:

~~~properties
commons.lang.jar=commons-lang3-3.14.0.jar
commons.lang.sha256=PASTE_APPROVED_64_HEX_SHA256_HERE

junit.jar=junit-4.13.2.jar
junit.sha256=PASTE_APPROVED_64_HEX_SHA256_HERE
~~~

Các giá trị SHA-256 trong ví dụ là chỗ giữ chỗ, không phải checksum thực. Trước khi dùng, hãy thay bằng digest lấy từ artifact đã được xác minh qua nguồn đáng tin cậy. Build bên dưới sẽ thất bại nếu checksum không khớp.

Tệp lock cần được review và quản lý phiên bản cùng mã nguồn. Khi nâng cấp một thư viện, hãy cập nhật phiên bản, tên tệp, checksum và dependency bắc cầu liên quan trong cùng một thay đổi. Không cập nhật riêng một JAR mà bỏ qua danh sách dependency.

### 3.2. Không dùng tên file chung chung

Tránh đổi tên mọi JAR thành `library.jar`, `common.jar` hoặc `latest.jar`. Tên chung làm mất dấu phiên bản và khiến việc phát hiện thư viện bị thay thế khó hơn.

Tên tệp nên phản ánh artifact và phiên bản. Nếu nhà cung cấp phát hành một tên file không chứa phiên bản, hãy lưu metadata tương ứng trong lock file và kiểm tra checksum. Không dựa vào tên thư mục để suy đoán phiên bản.

### 3.3. Ghi nhận cả dependency bắc cầu

Một lock file đầy đủ nên liệt kê mọi JAR cần thiết, kể cả dependency bắc cầu. Ví dụ:

~~~properties
json.api.jar=json-api-2.1.0.jar
json.api.sha256=...

annotations.jar=annotations-24.1.0.jar
annotations.sha256=...

logging.api.jar=logging-api-1.0.0.jar
logging.api.sha256=...
~~~

Dấu `...` chỉ biểu thị phần cần điền trong tài liệu minh họa. Trong dự án thật, phải dùng digest SHA-256 đầy đủ và đã được kiểm tra. Không để giá trị thiếu trong lock file của build phát hành.

Nếu dùng công cụ quản lý dependency, hãy lưu lock/descriptor tương ứng và bảo đảm tất cả dependency bắc cầu được resolve về phiên bản cụ thể. Việc chỉ cố định dependency trực tiếp nhưng để dependency bắc cầu tự chọn phiên bản có thể vẫn tạo ra kết quả khác nhau giữa các lần build.

## 4. Khai báo classpath bằng tên JAR cụ thể

Ant hỗ trợ data type `path` để gom các đường dẫn. Có thể nạp lock file rồi khai báo classpath rõ ràng:

~~~xml
<project name="offline-build" default="compile" basedir=".">

    <property name="lib.dir" location="${basedir}/lib" />
    <property name="build.dir" location="${basedir}/build" />
    <property name="classes.dir" location="${build.dir}/classes" />

    <property file="${basedir}/config/dependencies.lock.properties" />

    <path id="application.compile.classpath">
        <pathelement location="${lib.dir}/compile/${commons.lang.jar}" />
    </path>

    <target name="compile">
        <mkdir dir="${classes.dir}" />

        <javac srcdir="${basedir}/src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="application.compile.classpath" />
        </javac>
    </target>

</project>
~~~

Build file tham chiếu tên JAR đã chốt trong lock file. Nếu nâng phiên bản, chỉ cần cập nhật lock file sau khi dependency mới được duyệt và chuẩn bị trong thư mục lib.

Đối với classpath quan trọng, nên khai báo từng JAR bằng `pathelement` thay vì lấy mọi tệp khớp `*.jar`. Wildcard có thể vô tình đưa JAR cũ, JAR trùng hoặc JAR không thuộc dependency đã duyệt vào classpath. Thứ tự classpath cũng có thể ảnh hưởng đến lớp nào được nạp khi nhiều JAR chứa cùng một class.

Ví dụ path tách riêng compile và test:

~~~xml
<path id="application.compile.classpath">
    <pathelement location="${lib.dir}/compile/commons-lang3-3.14.0.jar" />
</path>

<path id="test.compile.classpath">
    <path refid="application.compile.classpath" />
    <pathelement location="${lib.dir}/test/junit-4.13.2.jar" />
</path>
~~~

Cấu hình trên chỉ minh họa cách chia classpath. Hãy thay danh sách JAR bằng đúng dependency mà dự án sử dụng.

## 5. Kiểm tra thư viện tồn tại trước khi build

Một build ngoại tuyến cần phát hiện dependency thiếu ngay từ đầu, thay vì chờ compiler báo lỗi package hoặc class không tồn tại.

Task `available` có thể kiểm tra tệp đã có trên đĩa:

~~~xml
<target name="verify-library-files">
    <available file="${lib.dir}/compile/${commons.lang.jar}"
               type="file"
               property="commons.lang.present" />

    <fail unless="commons.lang.present"
          message="Missing library: ${commons.lang.jar}" />
</target>
~~~

Sau đó, target compile có thể phụ thuộc vào bước kiểm tra:

~~~xml
<target name="compile" depends="verify-library-files">
    <mkdir dir="${classes.dir}" />
    <javac srcdir="${basedir}/src/main/java"
           destdir="${classes.dir}"
           includeantruntime="false">
        <classpath refid="application.compile.classpath" />
    </javac>
</target>
~~~

Cách này tạo lỗi rõ ràng khi thiếu JAR. Với nhiều dependency, hãy kiểm tra từng tệp hoặc gom các kiểm tra thành một target có thông báo riêng cho từng thư viện.

## 6. Kiểm tra tính toàn vẹn bằng SHA-256

### 6.1. Vì sao cần checksum?

Checksum là dấu vân tay được tính từ nội dung tệp. Nếu một JAR bị thay thế, tải thiếu hoặc hỏng trong quá trình sao chép, checksum thường sẽ khác với giá trị đã ghi nhận.

SHA-256 phù hợp để kiểm tra tính toàn vẹn của artifact. Nó không chứng minh nhà phát hành là ai nếu digest lấy từ cùng một nguồn không đáng tin cậy. Hãy lấy artifact và checksum từ nguồn được phê duyệt, kiểm tra chữ ký hoặc metadata xác thực của nhà cung cấp nếu có, rồi ghi lại digest đã duyệt trong lock file.

### 6.2. Tính checksum bằng công cụ hệ điều hành

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\lib\compile\commons-lang3-3.14.0.jar -Algorithm SHA256
~~~

Trên Linux:

~~~bash
sha256sum lib/compile/commons-lang3-3.14.0.jar
~~~

Trên macOS:

~~~bash
shasum -a 256 lib/compile/commons-lang3-3.14.0.jar
~~~

Kết quả là một chuỗi hex 64 ký tự cho SHA-256. Hãy lưu giá trị đã xác minh vào lock file và review thay đổi cùng với việc nâng cấp thư viện.

### 6.3. Kiểm tra checksum ngay trong Ant

Ant có task `checksum` để tính digest của tệp. Ví dụ:

~~~xml
<target name="verify-commons-lang">
    <available file="${lib.dir}/compile/${commons.lang.jar}"
               type="file"
               property="commons.lang.present" />

    <fail unless="commons.lang.present"
          message="Missing ${commons.lang.jar}" />

    <checksum file="${lib.dir}/compile/${commons.lang.jar}"
              algorithm="SHA-256"
              property="commons.lang.actual.sha256" />

    <condition property="commons.lang.checksum.valid">
        <equals arg1="${commons.lang.actual.sha256}"
                arg2="${commons.lang.sha256}" />
    </condition>

    <fail unless="commons.lang.checksum.valid"
          message="SHA-256 mismatch for ${commons.lang.jar}" />
</target>
~~~

Trong ví dụ, `commons.lang.sha256` lấy từ lock file và `commons.lang.actual.sha256` được Ant tính từ JAR hiện có. Nếu hai giá trị không khớp, build dừng.

Đặt bước checksum trước compile, test và package. Khi có nhiều JAR, lặp lại kiểm tra cho từng artifact hoặc tạo các target kiểm tra riêng để thông báo lỗi xác định được tệp nào sai.

### 6.4. Không tự động chấp nhận checksum mới

Khi checksum sai, không nên tự động tính digest mới rồi ghi đè lock file để build tiếp tục. Điều đó có thể hợp thức hóa một JAR bị thay thế ngoài ý muốn.

Quy trình nâng cấp đúng là:

1. Xác định phiên bản dependency cần thay đổi.
2. Lấy artifact từ nguồn được phê duyệt.
3. Xác minh nguồn và checksum.
4. Cập nhật tên file, version, digest và dependency liên quan.
5. Review thay đổi lock file.
6. Chạy build trong môi trường ngoại tuyến để xác nhận bundle đầy đủ.

## 7. Chuẩn bị thư viện cho môi trường ngoại tuyến

### 7.1. Tạo dependency bundle đầy đủ

Trước khi đưa build vào môi trường không có Internet, chuẩn bị một bundle gồm:

- Tất cả JAR compile.
- Tất cả JAR runtime.
- Tất cả JAR test nếu cần chạy test ngoại tuyến.
- Dependency bắc cầu của từng nhóm.
- Thư viện custom Ant task hoặc compiler adapter nếu build cần.
- Lock file chứa version, tên artifact và checksum.
- Tài liệu nguồn gốc và giấy phép của các thư viện theo quy định dự án.

Ví dụ bundle:

~~~text
offline-build-bundle/
├── lib/
│   ├── compile/
│   │   ├── commons-lang3-3.14.0.jar
│   │   └── annotations-24.1.0.jar
│   ├── runtime/
│   │   └── logging-implementation-1.0.0.jar
│   └── test/
│       └── junit-4.13.2.jar
├── ant-tools/
│   └── custom-ant-task.jar
├── config/
│   └── dependencies.lock.properties
└── README-offline.md
~~~

Tên và phiên bản trong ví dụ chỉ minh họa cách bố trí. Bundle thực tế phải chứa đúng artifact và phiên bản của dự án.

### 7.2. Lấy dependency từ nguồn được kiểm soát

Có thể chuẩn bị thư viện theo một trong các cách:

- Lưu các JAR đã duyệt trong repository dự án nếu chính sách repository cho phép.
- Tải từ artifact repository nội bộ trước khi chuyển bundle vào môi trường ngoại tuyến.
- Tạo gói dependency riêng có version và checksum, sau đó lưu trong kho artifact nội bộ.
- Dùng cache của dependency resolver nếu đã xác nhận cache chứa đầy đủ mọi artifact cần thiết.

Không nên sao chép thư mục lib từ một máy phát triển không rõ lịch sử. Máy đó có thể chứa JAR thử nghiệm, bản snapshot hoặc dependency cũ mà build file không khai báo.

### 7.3. Phân biệt thư viện ứng dụng và thư viện của Ant

Ant runtime có thể cần thư viện để nạp custom task hoặc task mở rộng. Các thư viện đó không nhất thiết là dependency của ứng dụng.

Ví dụ, `-lib` thêm JAR hoặc thư mục vào classpath của Ant:

~~~text
ant -lib ant-tools/custom-ant-task.jar offline-build
~~~

Tùy chọn `-lib` giúp Ant nạp task hoặc thành phần mở rộng. Nó không tự động thêm JAR vào classpath của ứng dụng khi chạy và không thay thế phần tử `<classpath>` của task javac hoặc java.

Khi chuẩn bị offline bundle, hãy phân loại riêng:

- Ant distribution và custom task libraries.
- JDK/compiler.
- Application compile/runtime libraries.
- Test framework và test libraries.
- Công cụ hệ điều hành mà script build gọi.

Nếu thiếu custom task JAR, Ant có thể không đọc được build file ngay cả khi toàn bộ thư viện ứng dụng đã có.

## 8. Cố định cả Ant, JDK và công cụ build

Thư viện ứng dụng không phải yếu tố duy nhất ảnh hưởng tới kết quả. Cần xác định phiên bản của:

- Apache Ant.
- JDK chạy Ant.
- JDK compiler nếu task javac fork sang executable riêng.
- Compiler adapter hoặc custom Ant task.
- Test runner.
- Công cụ native được gọi từ `<exec>`, script hoặc task khác.
- Hệ điều hành hoặc image/container của runner nếu yêu cầu tái lập nghiêm ngặt.

Ghi nhận phiên bản bằng các lệnh:

~~~text
ant -version
java -version
javac -version
ant -diagnostics
~~~

Nếu `fork="true"` và task javac có thuộc tính `executable`, hãy kiểm tra trực tiếp executable compiler được chỉ định. Nếu dùng compiler in-process, JDK khởi chạy Ant quyết định compiler được nạp.

Plain Ant không cung cấp một lệnh chung để tự tải mọi dependency và không có một tùy chọn `-offline` toàn cục đảm bảo mọi task không truy cập mạng. Build ngoại tuyến cần được thiết kế để các target không gọi bước tải từ xa. Nếu dự án dùng Ivy hoặc resolver khác, hãy cấu hình riêng chế độ offline/cache của công cụ đó và xác nhận mọi dependency đã có tại chỗ.

## 9. Không tải dependency trong target build ngoại tuyến

Một build file có thể vô tình truy cập mạng qua các task hoặc script như:

- Task tải tệp từ URL.
- Script shell hoặc PowerShell gọi curl, wget hoặc API.
- Dependency resolver được cấu hình để resolve từ remote repository.
- Task custom tự tải dữ liệu hoặc plugin.
- Bước build gọi dịch vụ bên ngoài để lấy schema, code generator hoặc metadata.

Trong chế độ ngoại tuyến, những bước này phải được bỏ khỏi luồng build hoặc thay bằng artifact đã chuẩn bị trước. Không nên để target compile tự tải JAR khi thiếu vì như vậy build không còn thực sự ngoại tuyến.

Có thể tách rõ target chuẩn bị dependency và target build:

~~~xml
<target name="prepare-dependencies">
    <!-- Chỉ chạy ở môi trường có quyền truy cập artifact repository. -->
    <!-- Tải/copy dependency đã được phê duyệt vào thư mục lib. -->
</target>

<target name="verify-offline-dependencies">
    <!-- Chỉ kiểm tra file và checksum đã có tại chỗ. -->
</target>

<target name="offline-build" depends="verify-offline-dependencies">
    <antcall target="compile" />
    <antcall target="test" />
    <antcall target="package" />
</target>
~~~

Các comment trên biểu thị vị trí của bước chuẩn bị, không phải task tải thực thi. Target offline-build chỉ nên kiểm tra và sử dụng file đã có. Nếu dùng `antcall`, cần bảo đảm các target được gọi không âm thầm kích hoạt bước tải dependency.

Một cách tổ chức khác là dùng một build file riêng cho chuẩn bị dependency và build file chính cho compile/test/package. Dù chọn cách nào, cần giữ ranh giới rõ ràng để người vận hành biết bước nào cần mạng.

## 10. Kiểm tra offline bằng môi trường sạch

Một build chạy được trên máy đã sử dụng lâu ngày chưa chứng minh dependency bundle đầy đủ. Máy có thể đang dùng JAR trong thư mục cache cá nhân, Ant lib, IDE hoặc một repository cục bộ không được đóng gói.

Quy trình xác nhận nên thực hiện trên workspace sạch:

1. Tạo workspace mới từ mã nguồn và bundle dependency đã phát hành.
2. Cài đúng phiên bản Ant và JDK đã quy định.
3. Không dùng cache cá nhân hoặc thư mục lib ngoài bundle.
4. Ngắt mạng hoặc chạy trong môi trường không có route tới repository bên ngoài.
5. Chạy target verify dependency và kiểm tra checksum.
6. Chạy compile, test và package.
7. Lưu log, phiên bản công cụ và kết quả build cùng artifact.

Ví dụ:

~~~text
ant -version
java -version
javac -version
ant verify-offline-dependencies
ant clean offline-build
~~~

Tên target trong ví dụ cần được định nghĩa trong build file của dự án. Nếu target clean xóa output, hãy bảo đảm nó chỉ xóa thư mục build do dự án quản lý, không xóa bundle dependency.

Không nên chỉ tắt mạng sau khi build đã chạy thành công một lần trên cùng workspace. Cache hoặc output cũ có thể che giấu dependency bị thiếu. Workspace sạch giúp xác nhận build thực sự chỉ dùng các đầu vào đã đóng gói.

## 11. Quản lý cập nhật phiên bản

Cố định dependency không có nghĩa là không bao giờ nâng cấp. Nó có nghĩa mọi thay đổi phiên bản phải được chủ động thực hiện và có thể truy vết.

Khi nâng một thư viện:

1. Xem release notes và yêu cầu Java tối thiểu của phiên bản mới.
2. Kiểm tra tương thích với các dependency liên quan.
3. Lấy đúng artifact từ nguồn được duyệt.
4. Kiểm tra checksum hoặc chữ ký.
5. Cập nhật lock file và thư mục bundle.
6. Chạy test, kiểm tra runtime và build offline.
7. Ghi lại lý do nâng cấp và phiên bản cũ/mới trong commit hoặc tài liệu thay đổi.

Không dùng tên động như `latest`, `RELEASE` hoặc snapshot không được khóa cho một build cần tái lập. Nếu buộc phải dùng snapshot trong quá trình phát triển, hãy tách khỏi cấu hình phát hành và không coi snapshot là dependency cố định.

### 11.1. Tránh xung đột phiên bản

Hai thư viện có thể phụ thuộc vào hai phiên bản khác nhau của cùng một artifact. Nếu cả hai JAR được đưa vào classpath, thứ tự nạp có thể làm một phiên bản che khuất phiên bản còn lại.

Không nên giải quyết xung đột bằng cách đặt tất cả JAR vào một thư mục rồi dùng `*.jar`. Hãy xác định dependency graph, chọn phiên bản tương thích, loại bỏ bản trùng và khai báo classpath có chủ đích.

### 11.2. Lưu lịch sử thay đổi

Có thể lưu một bảng trong tài liệu dependency:

| Artifact | Phiên bản cũ | Phiên bản mới | Lý do |
|---|---|---|---|
| commons-lang3 | 3.13.0 | 3.14.0 | Bản sửa lỗi đã được kiểm tra |
| junit | 4.13.1 | 4.13.2 | Cập nhật bản vá |
| logging implementation | 1.0.0 | 1.1.0 | Thay đổi theo yêu cầu ứng dụng |

Các giá trị trong bảng chỉ minh họa. Hãy ghi đúng lịch sử thật của dự án và liên kết thay đổi với commit hoặc bản phát hành tương ứng.

## 12. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Build ngoại tuyến báo thiếu class hoặc package | Thiếu JAR trực tiếp hoặc dependency bắc cầu | Bổ sung dependency vào bundle và lock file |
| Build chỉ thành công trên máy phát triển | Máy có cache hoặc JAR ngoài bundle | Thử trên workspace sạch và loại bỏ classpath ngoài dự án |
| Checksum không khớp | JAR bị thay thế, tải hỏng hoặc lock file chưa cập nhật | Xác minh nguồn artifact; chỉ cập nhật digest sau khi duyệt |
| Chạy được nhưng lỗi NoClassDefFoundError | Runtime dependency chưa được đóng gói hoặc classpath chạy thiếu JAR | Kiểm tra application runtime classpath và bundle phát hành |
| Ant không nhận custom task | Thiếu JAR trong Ant runtime classpath | Chuẩn bị custom task library và cấu hình `-lib` hoặc taskdef |
| Phiên bản thư viện trên CI khác local | Dùng wildcard, tên file chung hoặc cấu hình dependency khác nhau | Dùng tên artifact cụ thể và lock file thống nhất |
| Lỗi trùng class hoặc hành vi không ổn định | Nhiều phiên bản cùng có mặt trên classpath | Loại bản trùng, chọn một phiên bản và khai báo thứ tự rõ |
| Build vẫn truy cập Internet | Một target, script hoặc resolver còn resolve từ xa | Tách bước tải khỏi offline build và kiểm tra khi mạng bị ngắt |
| Test không chạy ngoại tuyến | Chưa chuẩn bị JUnit hoặc dependency của test runner | Bổ sung toàn bộ test dependency và Ant task tương ứng |
| Build dùng compiler khác phiên bản dự kiến | JAVA_HOME, PATH hoặc executable fork không thống nhất | Ghi rõ JDK và kiểm tra compiler thực tế |
| Bundle thiếu metadata giấy phép | Chỉ sao chép JAR mà không lưu thông tin phân phối | Bổ sung license, notice và nguồn artifact theo chính sách dự án |

## 13. Quy trình mẫu cho một dự án Ant ngoại tuyến

Một quy trình thực tế có thể chia thành hai giai đoạn.

**Giai đoạn chuẩn bị có mạng:**

1. Xác định dependency trực tiếp và bắc cầu.
2. Chọn phiên bản tương thích và ghi vào lock file.
3. Lấy JAR từ repository được phê duyệt.
4. Kiểm tra checksum/chữ ký và lưu metadata.
5. Đặt JAR vào thư mục compile/runtime/test tương ứng.
6. Đóng gói bundle cùng phiên bản Ant, JDK hoặc hướng dẫn cài toolchain cần thiết.

**Giai đoạn build không có mạng:**

1. Lấy mã nguồn và dependency bundle đã chuẩn bị.
2. Cài đúng Ant và JDK.
3. Kiểm tra mọi JAR tồn tại và checksum khớp.
4. Chạy compile, test và package mà không resolve từ xa.
5. Lưu log và artifact để truy vết.

Sơ đồ:

~~~text
Môi trường có mạng
    |
    +-- Chọn phiên bản dependency
    |
    +-- Lấy artifact từ nguồn được duyệt
    |
    +-- Kiểm tra checksum / chữ ký
    |
    +-- Tạo lock file và dependency bundle
              |
              v
       Môi trường ngoại tuyến
              |
              +-- Lấy mã nguồn + bundle
              |
              +-- Kiểm tra Ant/JDK
              |
              +-- Verify file và checksum
              |
              +-- Compile
              |
              +-- Test
              |
              +-- Package
~~~

Cách chia này giúp việc cập nhật dependency diễn ra ở một bước có kiểm soát. Build ngoại tuyến chỉ sử dụng các artifact đã được chuẩn bị và xác minh.

## 14. Nguyên tắc duy trì

- Cố định phiên bản cụ thể cho mọi thư viện trực tiếp và bắc cầu.
- Lưu tên artifact, nguồn, phạm vi sử dụng và checksum trong lock file.
- Phân biệt compile, runtime, test và Ant task libraries.
- Khai báo classpath bằng tên JAR cụ thể, tránh wildcard không kiểm soát.
- Xác minh SHA-256 trước khi compile hoặc package.
- Không tự động chấp nhận checksum mới khi phát hiện mismatch.
- Chuẩn bị JDK, Ant, custom task và công cụ native cần thiết ngoài các JAR ứng dụng.
- Tách bước tải dependency khỏi target build ngoại tuyến.
- Không giả định Ant core có một tùy chọn offline toàn cục hoặc tự quản lý dependency.
- Kiểm tra trên workspace sạch khi mạng bị ngắt.
- Review mọi nâng cấp dependency cùng lock file và metadata giấy phép.

Một build Ant ngoại tuyến đáng tin cậy cần có đủ đầu vào, biết chính xác phiên bản đang dùng và xác nhận được nội dung artifact trước khi thực thi. Khi dependency được khóa, lưu trữ và kiểm tra rõ ràng, build sẽ ít phụ thuộc vào mạng, cache cá nhân và trạng thái repository bên ngoài.


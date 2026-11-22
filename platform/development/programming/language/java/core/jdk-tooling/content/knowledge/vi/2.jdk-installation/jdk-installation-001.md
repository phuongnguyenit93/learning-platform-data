# Chọn bản JDK

## 1. Mục tiêu: chọn đúng phiên bản và đúng bản phân phối

Khi chọn JDK, cần quyết định bốn việc riêng biệt:

1. **Phiên bản Java (Java release):** ví dụ Java 17, 21 hoặc một release khác. Phiên bản quyết định cú pháp ngôn ngữ, API chuẩn và định dạng bytecode mà trình biên dịch có thể tạo ra.
2. **Bản phân phối (JDK distribution):** đơn vị xây dựng, đóng gói, phát hành bản cập nhật và có thể cung cấp hỗ trợ cho JDK, chẳng hạn Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, BellSoft Liberica, Microsoft Build of OpenJDK hoặc Red Hat build of OpenJDK.
3. **Hệ điều hành và kiến trúc CPU:** Windows, macOS, Linux; x86-64 hay ARM64; định dạng gói cài đặt và thư viện hệ thống tương thích.
4. **Mục đích sử dụng:** JDK đầy đủ cho phát triển và build, hay runtime image nhỏ hơn cho môi trường chỉ chạy ứng dụng.

Không nên dùng tên nhà cung cấp để suy ra phiên bản Java. Nhiều nhà cung cấp có thể phát hành các bản phân phối khác nhau của cùng một Java release. Ngược lại, cùng một nhà cung cấp có thể cung cấp nhiều release và nhiều loại gói cài đặt.

Mục tiêu là chọn một JDK đáp ứng yêu cầu của dự án, có cập nhật bảo mật và hỗ trợ phù hợp, cài được trên môi trường cần dùng, đồng thời có thể tái lập nhất quán trên máy lập trình, CI và production.

## 2. Xác định phiên bản Java mà dự án yêu cầu

Hãy kiểm tra cấu hình hiện có trước khi tải JDK. Các vị trí thường chứa thông tin phiên bản gồm:

- Gradle: cấu hình Java toolchain, **sourceCompatibility**, **targetCompatibility** hoặc **options.release** trong các file build.
- Maven: thuộc tính **maven.compiler.release**, cấu hình Maven Compiler Plugin và Maven Toolchains Plugin nếu dự án sử dụng.
- Spring Boot hoặc framework khác: bảng tương thích giữa phiên bản framework, thư viện và Java.
- CI/CD: phiên bản JDK trong workflow, build agent hoặc container image.
- Dockerfile và manifest triển khai: phiên bản runtime được dùng khi chạy ứng dụng.
- Tài liệu kỹ thuật của dự án: phiên bản tối thiểu, phiên bản được kiểm thử và phiên bản được hỗ trợ trong production.

Cần phân biệt ba phiên bản có thể khác nhau:

- **JDK dùng để chạy công cụ build:** JVM khởi chạy Gradle hoặc Maven. Bản thân phiên bản Gradle/Maven và plugin có thể đặt ra yêu cầu Java riêng.
- **JDK dùng để biên dịch:** compiler thực sự tạo bytecode. Dự án có thể khóa phiên bản này bằng toolchain.
- **Java runtime dùng để chạy ứng dụng:** JVM trên máy chủ hoặc trong container production.

Ví dụ, một máy có thể chạy Gradle bằng JDK mới hơn nhưng cấu hình toolchain để biên dịch ứng dụng bằng một JDK cũ hơn. Điều đó chỉ hợp lệ khi phiên bản Gradle, plugin, compiler và cấu hình dự án đều hỗ trợ cách kết hợp ấy. Không được giả định rằng cài một JDK là mọi công cụ sẽ tự động dùng đúng JDK đó.

### Phiên bản nguồn, bytecode và API đích

Nếu cần chạy ứng dụng trên Java release N, bytecode tạo ra phải tương thích với runtime N. Chỉ đặt mức cú pháp hoặc bytecode chưa chắc đã giới hạn đầy đủ API chuẩn mà chương trình được phép gọi.

Với javac từ Java 9 trở lên, tùy chọn **--release N** là cách rõ ràng để biên dịch theo một release đích: compiler giới hạn cú pháp, bytecode và API chuẩn tương ứng với release đó. Ví dụ:

~~~bash
javac --release 17 Main.java
java Main
~~~

Lệnh trên minh họa việc biên dịch mã nguồn theo Java 17; để chạy được, máy chạy chương trình cần có runtime tương thích với bytecode được tạo ra và classpath đầy đủ.

Nếu build bằng JDK mới hơn nhưng bỏ qua cấu hình release, compiler có thể mặc định tạo bytecode theo phiên bản JDK mới. Ứng dụng khi đó có thể chạy tốt trên máy phát triển nhưng thất bại trên máy chủ dùng Java cũ hơn.

Một JDK mới thường có thể chạy bytecode cũ, nhưng vẫn cần kiểm thử. API bị loại bỏ, thay đổi hành vi, encapsulation mạnh hơn, tùy chọn JVM và khác biệt của thư viện bên thứ ba có thể làm ứng dụng cũ gặp lỗi khi nâng runtime. Không nên xem việc nâng JDK là thao tác chỉ đổi đường dẫn cài đặt.

## 3. Chọn LTS hay release tính năng

Java có nhịp phát hành feature release định kỳ. Không phải mọi release đều có cùng thời hạn hỗ trợ. Khái niệm **LTS (Long-Term Support)** thể hiện cam kết hỗ trợ dài hạn của nhà cung cấp đối với một release; thời gian hỗ trợ, loại cập nhật và điều kiện sử dụng phụ thuộc vào từng nhà cung cấp và gói phân phối.

**Ưu tiên LTS** khi:

- Ứng dụng chạy production trong thời gian dài.
- Tổ chức cần một phiên bản ổn định để chuẩn hóa trên nhiều nhóm và môi trường.
- Chu kỳ nâng cấp framework, thư viện hoặc hạ tầng diễn ra chậm.
- Cần kế hoạch cập nhật bảo mật và hỗ trợ rõ ràng.

**Cân nhắc release tính năng mới hơn** khi:

- Dự án cần một tính năng Java mới chưa có trong LTS đang dùng.
- Nhóm có khả năng nâng cấp và kiểm thử theo chu kỳ phát hành ngắn.
- Framework, thư viện, plugin build và môi trường triển khai đã xác nhận tương thích.
- Tổ chức chấp nhận rõ ràng thời hạn hỗ trợ và kế hoạch chuyển sang release kế tiếp.

Không có một release phù hợp cho mọi dự án. Hãy chọn release còn được nhà cung cấp hỗ trợ trong khoảng thời gian dự kiến vận hành, đồng thời tương thích với framework, thư viện và nền tảng triển khai. Đừng chọn chỉ vì số phiên bản lớn nhất hoặc vì một máy lập trình cá nhân đã cài sẵn.

Trước khi quyết định, kiểm tra trang lifecycle/roadmap chính thức của nhà cung cấp. Xác nhận ngày kết thúc cập nhật bảo mật, chính sách phát hành bản vá, điều kiện hỗ trợ thương mại và lộ trình nâng cấp. Tên gọi LTS của hai nhà cung cấp không tự động đồng nghĩa với cùng một thời hạn hỗ trợ.

## 4. Chọn nhà cung cấp và bản phân phối JDK

OpenJDK là dự án mã nguồn mở của nền tảng Java. Nhiều nhà cung cấp xây dựng, kiểm thử, đóng gói và phát hành các bản phân phối dựa trên OpenJDK. Vì vậy, khi nói “dùng OpenJDK”, cần làm rõ bản build cụ thể đến từ đâu, được cập nhật và hỗ trợ như thế nào.

Một số bản phân phối thường gặp:

| Bản phân phối | Đặc điểm cần xem xét |
|---|---|
| Oracle JDK | Bản phân phối của Oracle; cần đọc điều khoản cấp phép, chính sách cập nhật và lựa chọn hỗ trợ áp dụng cho đúng release và mục đích sử dụng. |
| Eclipse Temurin | Bản build OpenJDK của dự án Eclipse Adoptium; có nhiều nền tảng và định dạng gói. Kiểm tra ma trận release, nền tảng và chính sách hỗ trợ hiện hành. |
| Amazon Corretto | Bản phân phối OpenJDK do Amazon cung cấp; xem lịch cập nhật, nền tảng được hỗ trợ và chính sách hỗ trợ của Amazon. |
| Azul Zulu | Bản phân phối OpenJDK của Azul, có các lựa chọn nền tảng và dịch vụ hỗ trợ khác nhau. |
| BellSoft Liberica JDK | Bản phân phối OpenJDK của BellSoft; có nhiều loại gói, cần chọn đúng thành phần và nền tảng. |
| Microsoft Build of OpenJDK | Bản build OpenJDK do Microsoft phát hành; kiểm tra release, hệ điều hành và vòng đời hỗ trợ công bố. |
| Red Hat build of OpenJDK | Phù hợp để xem xét khi tổ chức sử dụng hệ sinh thái và hợp đồng hỗ trợ của Red Hat; cần kiểm tra phiên bản và nền tảng được chứng nhận. |

Danh sách trên là ví dụ về các nhà cung cấp, không phải bảng xếp hạng chất lượng. Một bản phân phối phù hợp phải được đánh giá theo nhu cầu thực tế:

- **Cập nhật bảo mật:** nhà cung cấp có công bố bản vá, lịch phát hành và quy trình xử lý lỗ hổng rõ ràng không?
- **Vòng đời hỗ trợ:** release cần dùng được hỗ trợ đến khi nào? Có hỗ trợ thương mại hoặc SLA nếu tổ chức yêu cầu không?
- **Nền tảng:** có đúng hệ điều hành, kiến trúc CPU, libc và loại container cần triển khai không?
- **Tính tương thích:** có được framework, thư viện, hệ điều hành hoặc nền tảng triển khai của dự án chứng nhận không?
- **Giấy phép:** có được dùng trong môi trường nội bộ, thương mại, production và phân phối lại theo cách dự án cần không?
- **Nguồn cung cấp:** có checksum, chữ ký hoặc thông tin provenance để xác minh gói tải xuống không?
- **Vận hành:** có package repository, container image, quy trình cập nhật và cách cài đặt tự động phù hợp không?

Oracle JDK và các bản build OpenJDK không nên được xem là giống nhau về giấy phép, hỗ trợ hoặc cách phát hành cập nhật. Điều khoản có thể thay đổi theo release và mục đích sử dụng. Hãy đọc đúng giấy phép của artifact sẽ cài, thay vì dựa vào một nhận định chung như “Java luôn miễn phí” hoặc “Oracle JDK luôn phải trả phí”.

Nếu tổ chức đã có tiêu chuẩn nhà cung cấp, hãy dùng tiêu chuẩn đó. Nếu chưa có, hãy chọn một bản phân phối OpenJDK được duy trì bởi nhà cung cấp đáng tin cậy, có lifecycle và cập nhật bảo mật công khai, hỗ trợ đầy đủ nền tảng của dự án và đáp ứng yêu cầu giấy phép. Dùng nhất quán cùng nhà cung cấp và cùng release trên máy lập trình, CI và production giúp giảm sai khác khó truy vết.

## 5. Chọn hệ điều hành, kiến trúc và định dạng cài đặt

Chọn đúng release nhưng sai kiến trúc vẫn khiến JDK không chạy được. Trước khi tải, xác định:

- Hệ điều hành và phiên bản hệ điều hành.
- Kiến trúc CPU: x86-64/AMD64 hay ARM64/AArch64.
- Môi trường dùng JDK: máy vật lý, máy ảo, container hay runner CI.
- Thư viện hệ thống mà bản build yêu cầu, chẳng hạn glibc hay musl trên Linux.
- Định dạng cài đặt mà quy trình quản lý máy hỗ trợ.

Một số lựa chọn phổ biến:

| Nền tảng | Định dạng thường gặp | Lưu ý |
|---|---|---|
| Windows | MSI hoặc ZIP | MSI thuận tiện cho cài đặt hệ thống; ZIP hữu ích khi cần nhiều JDK song song hoặc không có quyền cài đặt. |
| macOS | PKG hoặc archive | Chọn đúng bản Intel hoặc Apple Silicon/ARM64; không suy ra kiến trúc chỉ từ tên thiết bị. |
| Linux | DEB, RPM hoặc archive | Chọn đúng họ bản phân phối, kiến trúc và thư viện hệ thống. Package manager giúp quản lý cập nhật; archive phù hợp với cài đặt riêng. |
| Container | Base image JDK/JRE | Chọn image phù hợp với kiến trúc và hệ điều hành nền; kiểm soát tag và digest để build có thể tái lập. |

Trên Linux/macOS, có thể xem kiến trúc bằng:

~~~bash
uname -m
~~~

Các giá trị thường gặp là **x86_64** cho x86-64 và **aarch64** cho ARM64. Trên Windows, có thể xem biến môi trường kiến trúc hoặc thông tin System trong Windows. Cần phân biệt kiến trúc của hệ điều hành đang chạy với kiến trúc của image/container đích.

Khi tải JDK, lấy từ trang chính thức hoặc repository được tổ chức phê duyệt. Đối chiếu checksum hoặc chữ ký do nhà cung cấp công bố trước khi cài đặt, nhất là khi dùng archive tải thủ công hoặc đưa artifact vào CI. Không sử dụng bản cài không rõ nguồn gốc.

Với container, không nên chỉ dùng một tag trôi nổi mà không có quy ước cập nhật. Tag có thể được cập nhật theo thời gian; pin digest giúp tái lập chính xác image, còn quy trình cập nhật định kỳ giúp tiếp nhận bản vá bảo mật. Cần cân bằng khả năng tái lập và việc không bỏ lỡ cập nhật.

## 6. Chọn JDK đầy đủ hay chỉ runtime

JDK đầy đủ bao gồm runtime và các công cụ phát triển như:

- **javac:** biên dịch mã nguồn Java.
- **java:** khởi chạy chương trình Java.
- **jshell:** môi trường tương tác để thử biểu thức và đoạn mã.
- **javadoc:** tạo tài liệu API.
- **jar:** tạo và thao tác với file JAR.
- **jlink:** tạo runtime image tùy biến theo các module cần thiết.
- **jdeps:** phân tích phụ thuộc module/package.

Đối với môi trường phát triển, build và kiểm thử, nên dùng JDK đầy đủ vì cần compiler và các công cụ đi kèm. Môi trường production chỉ chạy ứng dụng có thể dùng runtime image nhỏ hơn nếu đã xác định đầy đủ module, native library và công cụ chẩn đoán cần thiết.

Các bản Java hiện đại không nhất thiết được phân phối dưới dạng JRE riêng như cách cài đặt Java cũ. Có thể sử dụng JDK đầy đủ hoặc tạo runtime image phù hợp bằng công cụ như **jlink**. Không nên tải một gói được quảng cáo là “JRE” mà chưa kiểm tra nội dung, nguồn cung cấp và khả năng tương thích.

Một nguyên tắc thực tế là build bằng JDK đầy đủ, kiểm thử trên runtime giống production và chỉ tối giản runtime image sau khi xác nhận ứng dụng chạy được trong image đó. Việc giảm kích thước image không được làm mất module, chứng thư CA, timezone data, native library hoặc công cụ vận hành mà ứng dụng cần.

## 7. Thiết lập JDK nhất quán trong dự án

Cài nhiều JDK trên cùng máy là tình huống bình thường. Vấn đề là terminal, IDE, Gradle/Maven và ứng dụng có thể đang dùng những JDK khác nhau.

### JAVA_HOME và PATH

**JAVA_HOME** nên trỏ đến thư mục gốc của JDK, không phải thư mục **bin**. Đưa thư mục **bin** của JDK mong muốn vào PATH theo thứ tự ưu tiên phù hợp. Khi đổi JDK, cần mở terminal mới hoặc nạp lại cấu hình shell để môi trường được cập nhật.

Không nên hard-code đường dẫn cài JDK của một máy cá nhân vào source code. Dùng cơ chế toolchain của build tool để khai báo phiên bản compiler cần thiết; tài liệu cài đặt của dự án nên ghi rõ cách chuẩn bị JDK.

### Gradle toolchain

Với Gradle Kotlin DSL, có thể khai báo JDK dùng để biên dịch như sau:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
~~~

Ví dụ dùng Java 21 làm toolchain và release đích. Khi áp dụng, thay số phiên bản theo yêu cầu thật của dự án và kiểm tra phiên bản Gradle/plugin hỗ trợ cấu hình đó. Toolchain giúp build chọn đúng compiler; nó không tự thay đổi mọi JVM đang chạy trên máy. JVM khởi chạy Gradle vẫn phải đáp ứng yêu cầu của chính phiên bản Gradle đang dùng.

### Maven

Có thể khai báo release đích của compiler trong cấu hình Maven:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Đây là ví dụ cho release 21. Cần dùng phiên bản Maven Compiler Plugin phù hợp và đảm bảo JDK chạy Maven có compiler/API tương thích với cấu hình. Nếu cần chọn một JDK cụ thể khi máy có nhiều JDK, hãy xem xét Maven Toolchains Plugin và cấu hình toolchain tương ứng.

Ngoài cấu hình build, hãy đặt Project SDK trong IDE, JDK của CI và runtime trong Docker/deployment theo cùng tiêu chuẩn của dự án. Ghi rõ release, nhà cung cấp và cách cài đặt trong tài liệu onboarding để thành viên mới không phải tự đoán.

## 8. Quy trình lựa chọn thực tế

Thực hiện theo thứ tự sau để tránh tải nhầm hoặc cài nhiều lần:

1. **Đọc yêu cầu của dự án.** Xác định Java release tối thiểu, release đích khi biên dịch, yêu cầu của framework, build tool và môi trường production.
2. **Chọn nhóm release.** Ưu tiên release LTS còn được hỗ trợ nếu ứng dụng cần vận hành dài hạn. Chọn feature release khi dự án có nhu cầu cụ thể và chấp nhận nhịp nâng cấp tương ứng.
3. **Chọn nhà cung cấp.** Đối chiếu lifecycle, bản vá bảo mật, giấy phép, hỗ trợ thương mại, nền tảng và tiêu chuẩn của tổ chức.
4. **Chọn artifact.** Chọn đúng hệ điều hành, CPU architecture, loại gói và JDK/runtime cần dùng.
5. **Xác minh nguồn tải.** Kiểm tra checksum hoặc chữ ký trước khi cài.
6. **Chuẩn hóa môi trường.** Cấu hình JAVA_HOME, PATH, IDE, Gradle/Maven toolchain, CI và runtime triển khai.
7. **Kiểm thử trên môi trường đích.** Build, chạy test và khởi động ứng dụng bằng đúng release/runtime dự kiến cho production.
8. **Ghi lại quyết định.** Lưu nhà cung cấp, release, kiến trúc, nguồn cài đặt, cách cập nhật và mốc cần xem xét nâng cấp.

### Ví dụ quyết định

Giả sử một dịch vụ mới có yêu cầu chạy trên Java 21 và tổ chức muốn dùng LTS trong production. Quyết định có thể được ghi như sau:

- Release đích: Java 21.
- Bản phân phối: bản JDK 21 từ nhà cung cấp đã được tổ chức phê duyệt, có cập nhật bảo mật và lifecycle đáp ứng thời gian vận hành.
- Máy phát triển và CI: dùng cùng nhà cung cấp/release hoặc cấu hình toolchain tương đương.
- Compiler: đặt release đích là 21.
- Production: chạy trên runtime Java 21 tương thích; nếu dùng runtime image tối giản, phải kiểm thử image đó.
- Nâng cấp: theo dõi bản vá của nhà cung cấp, kiểm thử định kỳ và có kế hoạch chuyển release trước khi hết hỗ trợ.

Nếu dự án hiện tại yêu cầu Java 17 nhưng máy lập trình đã cài Java 21, không tự ý nâng phiên bản đích chỉ vì JDK 21 đang có sẵn. Giữ đúng release mà dự án hỗ trợ, cấu hình toolchain hoặc **--release** phù hợp, rồi kiểm thử trên runtime thực tế mà ứng dụng cần hỗ trợ.

## 9. Kiểm tra JDK sau khi cài đặt

Mở terminal mới và kiểm tra cả runtime lẫn compiler:

~~~bash
java --version
javac --version
~~~

Trên Windows, có thể xác định executable đang được tìm thấy bằng:

~~~powershell
where.exe java
where.exe javac
$env:JAVA_HOME
~~~

Trên Linux/macOS:

~~~bash
which -a java
which -a javac
echo "$JAVA_HOME"
~~~

Sau đó kiểm tra công cụ build:

~~~bash
./gradlew --version
mvn --version
~~~

Chỉ chạy lệnh tương ứng với build tool mà dự án sử dụng. Kết quả cần được đối chiếu với release dự kiến. Nếu **java** có nhưng **javac** không có, PATH có thể đang trỏ đến runtime-only hoặc một cài đặt không đầy đủ. Nếu **java** và **javac** báo các phiên bản khác nhau, có thể PATH đang tìm thấy hai bản cài khác nhau.

Khi cần xác định JVM mà một tiến trình Java đang sử dụng, xem cấu hình chạy của tiến trình, biến môi trường và đường dẫn executable thực tế. **JAVA_HOME** chỉ là một biến môi trường; một launcher hoặc IDE có thể được cấu hình để dùng đường dẫn khác.

Không kết luận chỉ từ việc lệnh **java** chạy thành công. Hãy xác nhận compiler, build tool, IDE và runtime triển khai đều dùng phiên bản phù hợp.

## 10. Những lỗi thường gặp khi chọn JDK

- **Nhầm Java release với nhà cung cấp:** Java 21 là release; Temurin, Corretto hay Oracle JDK là tên bản phân phối/nhà cung cấp.
- **Chọn bản mới nhất mà không kiểm tra tương thích:** framework, plugin, thư viện hoặc runtime production có thể chưa hỗ trợ.
- **Nhầm JDK chạy build với release đích:** Gradle chạy bằng một JVM không có nghĩa ứng dụng được biên dịch cho cùng release đó.
- **Chỉ đặt source/target mà quên API đích:** có thể vô tình gọi API chỉ tồn tại ở JDK mới; dùng **--release** khi cần giới hạn theo release.
- **Tải sai kiến trúc:** gói x86-64 không chạy như gói ARM64 trên mọi môi trường.
- **Cài nhiều JDK nhưng không kiểm soát PATH:** terminal có thể chạy một JDK khác với IDE hoặc CI.
- **Dùng runtime-only để build:** thiếu **javac** và các công cụ phát triển.
- **Không xem giấy phép và lifecycle:** một bản cài chạy được hôm nay có thể không đáp ứng yêu cầu cập nhật, hỗ trợ hoặc phân phối của tổ chức.
- **Không kiểm tra nguồn tải:** archive không rõ nguồn gốc có thể bị thay đổi hoặc không đúng artifact dự kiến.
- **Dùng container tag không có quy trình cập nhật:** build có thể khó tái lập hoặc bỏ lỡ bản vá bảo mật.

## 11. Checklist trước khi chốt lựa chọn

- [ ] Đã xác định release mà dự án, framework và thư viện hỗ trợ.
- [ ] Đã phân biệt JVM chạy build, JDK biên dịch và runtime production.
- [ ] Đã chọn LTS hoặc feature release dựa trên chu kỳ vận hành và kế hoạch nâng cấp.
- [ ] Đã xác nhận lifecycle, cập nhật bảo mật và điều khoản giấy phép của đúng nhà cung cấp/release.
- [ ] Đã chọn đúng hệ điều hành, kiến trúc CPU và loại gói cài đặt.
- [ ] Đã tải từ nguồn tin cậy và kiểm tra checksum/chữ ký.
- [ ] Đã cấu hình JAVA_HOME, PATH, IDE và toolchain.
- [ ] Đã kiểm tra java --version, javac --version và build tool.
- [ ] Đã build/test bằng cấu hình tương ứng với môi trường triển khai.
- [ ] Đã ghi lại phiên bản và quy trình cập nhật để nhóm có thể tái lập.

Chọn JDK đúng là chọn một tổ hợp có chủ đích giữa Java release, bản phân phối, nền tảng và chính sách hỗ trợ. Khi các yếu tố này được ghi rõ và dùng nhất quán, việc build, chạy, nâng cấp và xử lý sự cố sẽ dễ dự đoán hơn.
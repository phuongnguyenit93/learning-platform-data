# JDK Distribution (bản phân phối JDK)

## Mục tiêu

Sau bài này, bạn có thể giải thích OpenJDK và JDK distribution khác nhau thế nào, phân biệt JVM/JRE/JDK, đọc thông tin nhà cung cấp từ một bản cài đặt, chọn JDK phù hợp với dự án, và kiểm tra cấu hình khi máy có nhiều JDK.

## 1. JDK distribution là gì?

**JDK distribution** là một bản JDK được một tổ chức hoặc nhà cung cấp xây dựng, kiểm thử, đóng gói và phát hành để người dùng cài đặt. Hầu hết các bản phân phối phổ biến hiện nay lấy mã nguồn từ dự án **OpenJDK**, sau đó nhà cung cấp tạo binary cho các hệ điều hành và kiến trúc CPU cụ thể, duy trì các bản cập nhật, công bố chính sách hỗ trợ và cung cấp phương thức cài đặt.

Có thể hình dung chuỗi phát hành như sau:

1. **Java SE specification** mô tả hành vi và API mà một nền tảng Java tương thích phải cung cấp.
2. **OpenJDK** là dự án phát triển mã nguồn mở của JDK, nơi cộng đồng và nhiều nhà cung cấp cùng đóng góp.
3. **JDK distribution** là bản build cụ thể từ mã nguồn đó, có thể kèm bản vá, cấu hình build, công cụ đóng gói, installer, container image và cam kết cập nhật riêng.
4. **Ứng dụng Java** được biên dịch và chạy trên một bản phân phối JDK/JRE phù hợp.

Tên “OpenJDK” đôi khi được dùng để chỉ dự án/mã nguồn, đôi khi chỉ một bản binary được build từ mã nguồn OpenJDK. Vì vậy, khi so sánh hai bản tải về, hãy xem tên nhà cung cấp, phiên bản đầy đủ, giấy phép và lịch hỗ trợ thay vì chỉ nhìn chữ “OpenJDK”.

### JVM, JRE và JDK

| Thành phần | Vai trò |
|---|---|
| JVM (Java Virtual Machine) | Máy ảo thực thi bytecode Java, quản lý bộ nhớ, garbage collection, class loading và các hoạt động runtime |
| JRE (Java Runtime Environment) | Môi trường để chạy ứng dụng Java, gồm JVM và các thư viện runtime cần thiết |
| JDK (Java Development Kit) | Bộ công cụ phát triển, gồm runtime cùng compiler và các công cụ như javac, javadoc, jshell, jdb, jlink, jpackage và công cụ chẩn đoán |

JRE vẫn là một khái niệm hữu ích để mô tả môi trường chạy ứng dụng, nhưng không phải nhà cung cấp nào cũng phát hành một gói JRE riêng cho mọi phiên bản. Nhiều dự án hiện cài JDK đầy đủ trên máy phát triển và tạo runtime image tối giản khi đóng gói ứng dụng.

Khi học Java, biên dịch mã nguồn hoặc chạy Gradle/Maven, hãy cài **JDK**. Chỉ cài một gói runtime rút gọn có thể khiến bạn có lệnh java nhưng thiếu javac hoặc các công cụ phát triển khác.

## 2. Vì sao có nhiều bản phân phối?

Các bản phân phối cùng nhắm tới một phiên bản Java SE có thể tương thích ở cấp API nhưng vẫn khác nhau ở những điểm quan trọng:

- **Bản cập nhật và bảo mật:** thời điểm phát hành bản vá, chính sách backport, thời gian duy trì từng phiên bản và quy trình xử lý lỗ hổng.
- **Hỗ trợ:** chỉ cung cấp binary miễn phí, có hỗ trợ cộng đồng, hay có hợp đồng hỗ trợ thương mại và SLA.
- **Giấy phép:** giấy phép mã nguồn không tự động quyết định toàn bộ điều khoản của binary, gói cài đặt hoặc dịch vụ hỗ trợ.
- **Nền tảng:** Windows, Linux, macOS, AIX; x64, ARM64, s390x, ppc64le; glibc hay musl; installer, archive, package repository hoặc container image.
- **Máy ảo và cấu hình build:** HotSpot, OpenJ9 hoặc các thành phần tối ưu hóa riêng; tùy chọn GC, compiler, profiling và monitoring.
- **Thành phần đi kèm:** JavaFX, Java Mission Control, công cụ native image hoặc các biến thể JDK rút gọn.
- **Quy trình kiểm thử và chứng nhận:** mức độ kiểm thử tương thích, nền tảng được chứng nhận và phạm vi hỗ trợ chính thức.

Không nên kết luận một bản phân phối nhanh hơn hoặc an toàn hơn chỉ dựa vào tên nhà cung cấp. Kết quả còn phụ thuộc phiên bản, workload, cấu hình JVM, hệ điều hành, phần cứng và các thư viện native mà ứng dụng sử dụng.

### TCK kiểm tra điều gì?

**Technology Compatibility Kit (TCK)** là bộ kiểm thử dùng để xác minh một implementation có đáp ứng các yêu cầu tương thích của đặc tả Java tương ứng hay không. Với Java SE, TCK/JCK tập trung vào tính tương thích của API và hành vi được đặc tả.

TCK không phải benchmark hiệu năng, không chứng minh một binary không có lỗi, và không thay thế việc kiểm thử ứng dụng thực tế. Khi yêu cầu sản phẩm cần Java SE compatibility, hãy kiểm tra trạng thái chứng nhận của đúng phiên bản và nền tảng mà bạn định triển khai.

## 3. Một số JDK distribution phổ biến

Các lựa chọn dưới đây đều có chỗ đứng trong hệ sinh thái Java. Đây là danh sách tham khảo, không phải bảng xếp hạng.

| Bản phân phối | Tổ chức | Điểm cần biết |
|---|---|---|
| **Eclipse Temurin** | Eclipse Adoptium | Bản build OpenJDK đa nền tảng, được kiểm thử tương thích Java SE; thường là lựa chọn trung lập, dễ dùng cho học tập và phát triển ứng dụng thông thường |
| **Amazon Corretto** | Amazon | Bản phân phối OpenJDK miễn phí, có chính sách LTS và cập nhật bảo mật/performance do Amazon công bố; được TCK chứng nhận |
| **Azul Zulu** | Azul | Các bản build OpenJDK cho nhiều nền tảng; có lựa chọn tải binary và các gói hỗ trợ thương mại |
| **BellSoft Liberica JDK** | BellSoft | Bản build OpenJDK với nhiều biến thể như Lite, Standard và Full; cần chọn đúng biến thể nếu dự án cần JavaFX hoặc thành phần bổ sung |
| **Microsoft Build of OpenJDK** | Microsoft | Bản phân phối OpenJDK miễn phí; Microsoft công bố binary đã qua kiểm thử tương thích Java SE, hỗ trợ nhiều hệ điều hành và kiến trúc |
| **Oracle JDK** | Oracle | Bản phân phối của Oracle. Điều khoản sử dụng phụ thuộc phiên bản, bản cập nhật và mục đích sử dụng; cần đọc giấy phép của đúng binary |
| **Oracle OpenJDK** | Oracle/OpenJDK | Các binary OpenJDK do Oracle phát hành theo giấy phép mã nguồn mở; đây là lựa chọn riêng với Oracle JDK |
| **IBM Semeru Runtimes** | IBM | Dùng thư viện lớp OpenJDK cùng máy ảo Eclipse OpenJ9. Có Open Edition và Certified Edition với giấy phép khác nhau |
| **GraalVM** | Oracle và cộng đồng GraalVM | Phù hợp khi cần Graal compiler, polyglot runtime hoặc Native Image để tạo executable native; đây là lựa chọn chuyên biệt hơn một JDK phổ thông |

Một số nhà cung cấp khác như Red Hat và SAP cũng phát hành JDK distribution phục vụ hệ điều hành, nền tảng hoặc hệ sinh thái doanh nghiệp của họ.

### HotSpot, OpenJ9 và GraalVM

**HotSpot** là máy ảo được dùng trong nhiều bản phân phối OpenJDK phổ biến. **OpenJ9** là implementation JVM khác, được dùng trong IBM Semeru Runtimes. Khác biệt về bộ nhớ, thời gian khởi động, throughput và cách tối ưu có thể ảnh hưởng đến workload thực tế.

**GraalVM** cung cấp Graal compiler và các khả năng bổ sung như Native Image. Native Image phân tích các lớp và phương thức có thể truy cập để tạo executable native cho một hệ điều hành và kiến trúc cụ thể. Nó có thể giảm thời gian khởi động và footprint trong một số trường hợp, nhưng quá trình build cần cấu hình và kiểm thử riêng; không phải ứng dụng Java nào cũng chuyển sang native image mà không cần điều chỉnh.

Khi thay đổi giữa các implementation JVM, hãy chạy lại test, benchmark và kiểm tra thư viện native/JNI. Cùng một Java SE version không có nghĩa mọi đặc tính vận hành đều giống nhau.

## 4. Đọc phiên bản Java và phân biệt phiên bản vendor

Một bản JDK thường có nhiều thành phần trong chuỗi phiên bản:

- **Feature release:** phiên bản nền tảng như 17, 21 hoặc 25.
- **Update release:** bản cập nhật bảo mật và sửa lỗi, ví dụ 21.0.1 hoặc 21.0.13.
- **Build number:** số build của một bản phát hành cụ thể, thường nằm sau dấu cộng hoặc trong chuỗi nhận diện của nhà cung cấp.
- **Vendor/build label:** tên và cách đánh số riêng của nhà cung cấp.

Không phải mọi vendor đều biểu diễn build number giống nhau. Vì vậy, khi chuyển từ distribution này sang distribution khác, hãy đối chiếu **Java feature version và update version**, không chỉ so sánh toàn bộ chuỗi phiên bản do vendor hiển thị.

Lệnh kiểm tra cơ bản:

~~~bash
java -version
javac -version
~~~

Để xem thông tin runtime chi tiết hơn:

~~~bash
java -XshowSettings:properties -version
~~~

Trong phần system properties, chú ý các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| java.version | Phiên bản Java runtime đang chạy |
| java.specification.version | Phiên bản đặc tả Java SE, thường là 17, 21 hoặc 25 |
| java.vendor | Nhà cung cấp của runtime |
| java.home | Thư mục runtime mà tiến trình Java đang sử dụng |
| java.vm.name | Tên implementation của JVM |
| java.vm.vendor | Nhà cung cấp của JVM |

Lệnh java -version cho biết runtime đang được tìm thấy qua PATH. Lệnh javac -version cho biết compiler đang được tìm thấy. Hai lệnh có thể trỏ đến hai bản cài đặt khác nhau nếu máy có nhiều JDK.

## 5. Feature release và LTS

Java có nhịp phát hành feature release khoảng sáu tháng một lần. Một số phiên bản được các nhà cung cấp đánh dấu **Long-Term Support (LTS)** và duy trì lâu hơn các feature release thông thường.

Các mốc LTS phổ biến trong hệ sinh thái hiện đại gồm Java 8, 11, 17, 21 và 25. Tuy nhiên, thời hạn cập nhật và hỗ trợ không giống nhau giữa các nhà cung cấp.

Cần phân biệt ba khái niệm:

1. **LTS của phiên bản Java:** phiên bản được vendor chọn để duy trì trong thời gian dài.
2. **Security updates:** bản cập nhật vá lỗ hổng và lỗi; cần kiểm tra ngày phát hành và thời điểm kết thúc cập nhật của vendor.
3. **Commercial support:** dịch vụ hỗ trợ có hợp đồng, SLA, tư vấn hoặc xử lý sự cố. LTS miễn phí không đồng nghĩa với việc mọi hình thức hỗ trợ đều miễn phí.

Đối với ứng dụng mới, thường nên chọn một LTS còn được cập nhật, phù hợp với framework và môi trường triển khai. Đối với hệ thống hiện có, phải kiểm tra yêu cầu của framework, thư viện, máy chủ ứng dụng và pipeline trước khi nâng phiên bản.

## 6. Giấy phép và chi phí: phải kiểm tra đúng bản build

Đừng suy luận giấy phép chỉ từ tên Java hoặc từ việc một bản tải về không yêu cầu thanh toán.

- Mã nguồn OpenJDK chủ yếu được phát hành theo GPLv2 kèm Classpath Exception (GPLv2+CPE), nhưng từng binary và gói bổ sung vẫn cần được kiểm tra theo điều khoản của nhà cung cấp.
- Một số nhà cung cấp phát hành binary miễn phí cho cả mục đích thương mại và production, nhưng dịch vụ hỗ trợ doanh nghiệp có thể là dịch vụ trả phí.
- Oracle JDK và Oracle OpenJDK là hai lựa chọn riêng. Oracle JDK có chính sách giấy phép thay đổi theo phiên bản và bản cập nhật.
- Theo Oracle Java SE Licensing FAQ được cập nhật ngày 20-10-2026, Oracle JDK 25 trở lên được cung cấp theo Oracle No-Fee Terms and Conditions (NFTC); với Java 21, các bản cập nhật từ 21.0.13 trở đi có điều khoản khác với các bản đến 21.0.12. Hãy đọc FAQ và giấy phép đi kèm chính binary bạn tải, đặc biệt khi triển khai production hoặc phân phối JDK cùng sản phẩm.

Khi đánh giá chi phí, hãy tách riêng:

- Phí tải xuống và sử dụng binary.
- Quyền sử dụng trong development, testing, production và redistribution.
- Thời gian nhận security updates.
- Hợp đồng hỗ trợ, SLA và trách nhiệm xử lý sự cố.
- Chi phí nâng cấp khi phiên bản hết thời gian hỗ trợ.

Đối với tổ chức, nên lưu lại tên distribution, phiên bản đầy đủ, URL tải, checksum, giấy phép áp dụng và chính sách cập nhật trong hồ sơ dependency/software inventory.

## 7. Chọn distribution theo nhu cầu

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Học Java, làm bài tập hoặc dự án cá nhân | Một bản LTS phổ biến, dễ cài và có tài liệu rõ ràng; Eclipse Temurin là điểm bắt đầu trung lập thường dùng |
| Dự án chạy trên AWS | Cân nhắc Amazon Corretto nếu lịch hỗ trợ và nền tảng đáp ứng yêu cầu |
| Dự án chạy trên Azure hoặc hệ sinh thái Microsoft | Cân nhắc Microsoft Build of OpenJDK sau khi kiểm tra phiên bản và nền tảng được hỗ trợ |
| Doanh nghiệp dùng RHEL hoặc cần hỗ trợ từ nhà cung cấp hệ điều hành | Kiểm tra Red Hat build of OpenJDK và điều khoản hỗ trợ tương ứng |
| Cần OpenJ9 hoặc muốn thử đặc tính JVM khác | Đánh giá IBM Semeru Open Edition/Certified Edition bằng workload thực tế |
| Cần Native Image hoặc polyglot runtime | Đánh giá GraalVM và kiểm tra giới hạn tương thích của framework/thư viện |
| Hợp đồng hoặc sản phẩm yêu cầu Oracle Java | Dùng đúng bản Oracle JDK được hợp đồng hỗ trợ và xác minh điều khoản của bản cập nhật |

Nếu không có ràng buộc vendor, hãy chọn theo thứ tự sau:

1. Chọn Java feature version mà dự án/framework hỗ trợ.
2. Chọn một distribution còn được cập nhật bảo mật cho phiên bản đó.
3. Kiểm tra giấy phép phù hợp với mục đích sử dụng.
4. Kiểm tra hệ điều hành, CPU architecture, container base image và các thư viện native.
5. Xác định có cần hỗ trợ thương mại hoặc SLA hay không.
6. Chạy test và benchmark của ứng dụng trước khi chuẩn hóa distribution cho production.

Một dự án nên pin phiên bản JDK rõ ràng trong tài liệu, CI và container image. Tránh dùng nhãn latest cho môi trường production nếu pipeline không kiểm soát việc thay đổi phiên bản.

## 8. Cài đặt và xác minh trên máy phát triển

### Chọn đúng gói cài đặt

Trước khi tải, xác định:

- Java feature version dự án yêu cầu.
- Hệ điều hành và kiến trúc CPU: Windows/Linux/macOS, x64/ARM64...
- Loại gói: installer, archive, package manager hay container image.
- Gói JDK đầy đủ hay runtime rút gọn.
- Có cần JavaFX, native tools hoặc một biến thể đặc biệt không.

Ưu tiên trang tải chính thức của nhà cung cấp. Với môi trường doanh nghiệp, hãy kiểm tra checksum/chữ ký số và lưu lại phiên bản cụ thể để có thể tái lập môi trường.

### Thiết lập JAVA_HOME và PATH

**JAVA_HOME** nên trỏ đến thư mục gốc của JDK, ví dụ thư mục cài đặt chứa bin, lib và các thành phần khác. Không đặt JAVA_HOME trỏ thẳng vào thư mục bin hoặc file java.exe.

PATH cần chứa thư mục bin của JDK đang muốn sử dụng. Nếu máy có nhiều JDK, thứ tự các mục trong PATH quyết định lệnh java và javac nào được gọi trước.

Ví dụ trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
java -version
javac -version
java -XshowSettings:properties -version 2>&1 | Select-String 'java.vendor|java.version|java.home'
~~~

Ví dụ trên Windows Command Prompt:

~~~bat
echo %JAVA_HOME%
where java
where javac
java -version
javac -version
~~~

Ví dụ trên Linux/macOS:

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
java -XshowSettings:properties -version 2>&1 | grep -E 'java.vendor|java.version|java.home'
~~~

Sau khi thay đổi biến môi trường, mở terminal mới hoặc nạp lại cấu hình shell để nhận giá trị mới. Trên Windows, cũng cần kiểm tra các đường dẫn JDK cũ trong PATH vì chúng có thể đứng trước JAVA_HOME/bin.

### Kiểm tra JDK có đầy đủ công cụ

Ngoài java và javac, có thể kiểm tra:

~~~bash
jshell --version
jlink --version
jpackage --version
~~~

Nếu java chạy được nhưng javac không tồn tại, máy có thể đang dùng runtime-only package hoặc PATH chưa trỏ đến JDK. Hãy kiểm tra đường dẫn của từng lệnh trước khi cài lại.

### Kiểm tra JDK mà IDE và build tool đang dùng

JDK được dùng trong terminal không nhất thiết là JDK mà IDE hoặc build tool sử dụng.

- IntelliJ IDEA có Project SDK và Gradle JVM riêng.
- Gradle có thể dùng Java toolchain để chọn compiler/runtime cho từng project.
- Maven có thể dùng Maven Toolchains hoặc cấu hình compiler plugin.
- CI runner và Docker image có thể cung cấp JDK khác với máy phát triển.

Khi build thành công ở IDE nhưng thất bại trong terminal hoặc CI, hãy kiểm tra JVM được từng công cụ báo ra. Với Maven, dùng mvn -version; với Gradle, dùng gradle -version để xem JVM đang chạy build.

## 9. Những lỗi thường gặp

### java và javac khác phiên bản

**Dấu hiệu:** java -version báo một major version nhưng javac -version báo major version khác.

**Nguyên nhân thường gặp:** PATH có nhiều JDK; thư mục bin của bản cũ đứng trước bản mới; JAVA_HOME và PATH không đồng nhất.

**Cách xử lý:** kiểm tra đường dẫn thực tế bằng where/Get-Command/command -v, sửa JAVA_HOME và thứ tự PATH, mở terminal mới rồi kiểm tra lại cả hai lệnh.

### IDE hoặc Gradle dùng JDK khác terminal

**Dấu hiệu:** lệnh java trong terminal đúng phiên bản nhưng build trong IDE báo thiếu API hoặc không hỗ trợ phiên bản source/target.

**Nguyên nhân thường gặp:** Project SDK, Gradle JVM, Maven runner hoặc toolchain đang chọn một JDK khác.

**Cách xử lý:** kiểm tra cấu hình JDK của từng công cụ và khai báo toolchain rõ ràng trong build nếu dự án cần môi trường nhất quán.

### UnsupportedClassVersionError

**Dấu hiệu:** runtime không thể nạp class vì class file được biên dịch bằng phiên bản Java mới hơn.

**Nguyên nhân:** compile bằng JDK mới nhưng chạy bằng runtime cũ hơn.

**Cách xử lý:** nâng runtime lên phiên bản tương thích, hoặc biên dịch với target phù hợp. Ví dụ, JDK 17 trở lên có thể dùng javac --release 17 để tạo bytecode và giới hạn API theo Java 17.

### Không tương thích với thư viện native hoặc kiến trúc CPU

**Dấu hiệu:** lỗi khi nạp thư viện JNI, lỗi linker hoặc container không khởi động dù Java version đúng.

**Nguyên nhân:** binary native được build cho OS/CPU/libc khác, hoặc distribution không có gói phù hợp.

**Cách xử lý:** đối chiếu kiến trúc CPU, libc, hệ điều hành và phiên bản native library; dùng đúng image/package cho nền tảng triển khai.

### Chuyển distribution nhưng vẫn thấy vendor cũ

**Dấu hiệu:** đã cài distribution mới nhưng java.vendor hoặc java -version vẫn hiển thị vendor cũ.

**Nguyên nhân:** shell đang tìm thấy một bản java khác qua PATH, service/IDE chưa được cấu hình lại, hoặc process cũ chưa khởi động lại.

**Cách xử lý:** kiểm tra java.home, đường dẫn executable, JAVA_HOME, PATH và cấu hình của service/IDE. Khởi động lại tiến trình sau khi đổi môi trường.

## 10. Checklist khi đổi JDK distribution

Khi thay Temurin bằng Corretto, Zulu, Liberica, Microsoft Build of OpenJDK hoặc một distribution khác, thực hiện lần lượt:

1. Ghi lại Java feature version, update version, vendor và JVM hiện tại.
2. Xác nhận distribution mới có cùng Java SE version mà ứng dụng yêu cầu.
3. Đọc giấy phép, lịch security update và phạm vi hỗ trợ của đúng phiên bản.
4. Kiểm tra OS, CPU architecture, libc, package format và container image.
5. Cài bản mới song song nếu cần để có thể so sánh và rollback.
6. Cập nhật JAVA_HOME, PATH, IDE, Gradle/Maven toolchain, CI và Dockerfile.
7. Chạy unit test, integration test, test bảo mật/TLS và các luồng có dùng JNI hoặc JavaFX.
8. Chạy benchmark đại diện nếu thay đổi JVM implementation hoặc cấu hình GC.
9. Kiểm tra log, JFR/monitoring và memory usage sau khi triển khai thử.
10. Ghi lại phiên bản, checksum, nguồn tải và cách rollback.

Đừng chỉ kiểm tra rằng ứng dụng khởi động được. Hãy xác nhận các luồng quan trọng, hiệu năng, logging, certificate, timezone, native library và quy trình cập nhật bảo mật vẫn đáp ứng yêu cầu.

## 11. Tài liệu tham khảo chính thức

- [OpenJDK Project](https://openjdk.org/) — mã nguồn, dự án và hoạt động phát triển OpenJDK.
- [JDK Release Information](https://ops.java/releases/) — lịch phát hành và thông tin Java SE.
- [Eclipse Temurin Downloads](https://adoptium.net/temurin/releases/) và [Supported Platforms](https://adoptium.net/supported-platforms) — phiên bản, gói cài đặt và nền tảng được hỗ trợ.
- [Eclipse Temurin Support](https://adoptium.net/support/) — lịch phát hành, cập nhật và vòng đời hỗ trợ.
- [Amazon Corretto](https://aws.amazon.com/corretto/) và [Corretto FAQs](https://aws.amazon.com/corretto/faqs/) — đặc tính, TCK, giấy phép và lịch LTS.
- [Microsoft Build of OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/overview) — nền tảng, binary và kiểm thử tương thích.
- [Azul Zulu Migration Guide](https://docs.azul.com/core/install/migrate-to-azul-zulu) — nhận diện và chuyển đổi giữa các distribution.
- [Liberica JDK](https://bell-sw.com/libericajdk/) — các biến thể và nền tảng của Liberica.
- [IBM Semeru Runtimes Release Notes](https://www.ibm.com/support/pages/semeru-runtimes-release-notes) — thành phần OpenJDK/OpenJ9 và edition.
- [GraalVM Native Image](https://www.graalvm.org/latest/reference-manual/native-image/) — cách tạo executable native và các giới hạn cần xem xét.
- [Oracle Java SE Licensing FAQ](https://www.oracle.com/java/technologies/javase/jdk-faqs.html) — điều khoản Oracle JDK theo phiên bản và bản cập nhật.

Chính sách hỗ trợ, phiên bản khả dụng và giấy phép có thể thay đổi. Khi cài đặt hoặc triển khai, hãy đối chiếu tài liệu chính thức tại thời điểm tải binary và lưu lại đúng điều khoản áp dụng cho bản build đang dùng.

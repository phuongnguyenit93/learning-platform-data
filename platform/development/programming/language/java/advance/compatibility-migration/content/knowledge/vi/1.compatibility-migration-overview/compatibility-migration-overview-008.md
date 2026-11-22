# Kiến thức đầu vào và trình tự học

Trong module **Java Advance Compatibility Migration**, bài học này xác định những kiến thức cần có trước khi bắt đầu chuyển đổi ứng dụng Java sang một phiên bản JDK mới hơn, đồng thời đề xuất trình tự học và thực hành để quá trình chuyển đổi có thể được kiểm soát.

Chuyển đổi phiên bản Java không chỉ là thay JDK rồi biên dịch lại. Ứng dụng còn phụ thuộc vào API của nền tảng, thư viện bên thứ ba, công cụ build, framework, máy chủ ứng dụng, cấu hình JVM và môi trường triển khai. Vì vậy, người học cần hiểu cả mã nguồn lẫn môi trường chạy của ứng dụng. Các bước dưới đây không giả định một cặp phiên bản Java cụ thể; hãy thay phiên bản đích bằng phiên bản mà dự án đang hướng tới.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Xác định kiến thức Java, JVM, build và kiểm thử cần dùng trong một dự án migration.
- Phân biệt tương thích mã nguồn, tương thích nhị phân, tương thích hành vi và tương thích vận hành.
- Thu thập thông tin về phiên bản Java hiện tại, phiên bản đích, thư viện và môi trường chạy.
- Đọc release notes và tài liệu migration để tìm thay đổi có thể ảnh hưởng đến ứng dụng.
- Dùng các công cụ JDK để nhận diện API lỗi thời, phụ thuộc vào API nội bộ và vấn đề liên quan đến module.
- Xây dựng trình tự chuyển đổi có thể kiểm chứng bằng build, test và thử nghiệm trên môi trường gần với production.

## 2. Kiến thức đầu vào

Không cần trở thành chuyên gia về mọi thành phần của JVM trước khi bắt đầu. Tuy nhiên, cần nắm được những nền tảng sau để hiểu nguyên nhân lỗi và chọn cách xử lý phù hợp.

### 2.1. Ngôn ngữ Java và thư viện chuẩn

Người học nên sử dụng thành thạo các nội dung sau:

- Cấu trúc chương trình, package, class, interface, kế thừa, đa hình và phạm vi truy cập.
- Generics, collections, exception handling và cách tổ chức API giữa các module.
- Annotation, reflection và dynamic proxy ở mức đủ để đọc hiểu cách framework sử dụng chúng.
- Lambda, functional interface và Stream API nếu ứng dụng đang dùng các tính năng này.
- I/O, NIO, networking, serialization và xử lý tài nguyên.
- Concurrency cơ bản: thread, executor, synchronization, concurrent collections và các vấn đề về visibility.

Những kiến thức này giúp nhận ra thay đổi trong thư viện chuẩn, hành vi của reflection, xử lý luồng dữ liệu, đồng thời và serialization. Khi đọc một lỗi migration, cần phân biệt lỗi do cú pháp hoặc API Java với lỗi do framework hay thư viện bên ngoài.

### 2.2. JDK, JVM và bytecode

Hãy hiểu vai trò của các thành phần chính:

- **JDK (Java Development Kit):** bộ công cụ phát triển, gồm compiler và các công cụ phục vụ build, phân tích, đóng gói, chẩn đoán.
- **JVM (Java Virtual Machine):** môi trường thực thi bytecode, quản lý class loading, bộ nhớ, garbage collection và thực thi mã.
- **Bytecode:** mã trung gian được compiler tạo ra và JVM nạp để chạy. Phiên bản class file phải được JVM đích hỗ trợ.
- **Class loader:** cơ chế nạp và liên kết class; thứ tự và phạm vi class loader có thể ảnh hưởng đến ứng dụng server hoặc framework.
- **Classpath và module path:** hai cơ chế tìm kiếm và tổ chức lớp/thư viện. Module System cần được hiểu nếu dự án dùng module hoặc gặp vấn đề về truy cập module.
- **JVM options:** tham số heap, garbage collector, logging, system properties, mở package và các tuỳ chọn runtime khác.

Phân biệt phiên bản JDK dùng để biên dịch với phiên bản JDK dùng để chạy. Một ứng dụng có thể được biên dịch bằng một JDK nhưng triển khai trên JDK khác; cấu hình build và runtime phải được ghi nhận riêng. Việc class file có thể được JVM đọc không đảm bảo toàn bộ API, thư viện và hành vi của ứng dụng tương thích.

### 2.3. Build và quản lý dependency

Nắm được công cụ mà dự án đang sử dụng, thường là Maven hoặc Gradle:

- Cách khai báo dependency trực tiếp và dependency bắc cầu.
- Phạm vi dependency, phiên bản, repository và cơ chế giải quyết xung đột.
- Plugin biên dịch, đóng gói, kiểm thử, tạo mã và phân tích tĩnh.
- Cách build tái lập trong máy cá nhân và CI.
- Cách tạo JAR/WAR, quản lý tài nguyên và cấu hình profile hoặc build variant.

Migration có thể thất bại trước khi biên dịch mã ứng dụng nếu Maven/Gradle wrapper, plugin, compiler plugin hoặc công cụ CI chưa hỗ trợ JDK mới. Vì thế, dependency của ứng dụng và dependency của quy trình build đều cần được kiểm tra.

### 2.4. Framework và môi trường triển khai

Lập danh sách những thành phần chạy cùng ứng dụng, ví dụ:

- Framework và thư viện nền tảng như web framework, dependency injection, ORM và logging.
- Application server, servlet container, message broker client và database driver.
- Thư viện có mã native, JNI, agent giám sát, agent bảo mật và công cụ profiling.
- Hệ điều hành, container image, biến môi trường, chứng thư, truststore và cấu hình mạng.
- Các dịch vụ bên ngoài mà ứng dụng giao tiếp qua HTTP, JDBC, messaging hoặc giao thức khác.

Một thư viện có thể tương thích với mã nguồn nhưng chưa tương thích với phiên bản JDK đích. Tương tự, ứng dụng chạy được trên máy phát triển chưa chắc chạy được trong container hoặc application server thực tế.

### 2.5. Kiểm thử và chẩn đoán

Người học cần biết cách chạy và đọc kết quả của:

- Unit test để kiểm tra hành vi của từng thành phần.
- Integration test để kiểm tra kết nối cơ sở dữ liệu, filesystem, message broker và dịch vụ ngoài.
- Contract hoặc end-to-end test để kiểm tra giao tiếp giữa các hệ thống.
- Kiểm thử hiệu năng để so sánh latency, throughput, mức sử dụng CPU và bộ nhớ.
- Log, stack trace, thread dump, heap dump và thông tin khởi động JVM.

Trước khi migration, cần có một bộ kiểm thử nền chạy được trên phiên bản hiện tại. Nếu không có kết quả baseline, rất khó xác định lỗi hoặc thay đổi hiệu năng xuất hiện do migration hay đã tồn tại từ trước.

## 3. Các loại tương thích cần phân biệt

Một thay đổi có thể đạt một loại tương thích nhưng vẫn thất bại ở loại khác. Hãy phân loại vấn đề trước khi quyết định sửa mã nguồn, nâng dependency hay thay đổi cấu hình.

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ vấn đề |
| --- | --- | --- |
| Tương thích mã nguồn (source compatibility) | Mã nguồn có biên dịch được với compiler và API của phiên bản đích không? | API bị loại bỏ, chữ ký phương thức thay đổi, compiler không chấp nhận cách sử dụng cũ. |
| Tương thích nhị phân (binary compatibility) | Các class đã biên dịch có liên kết và nạp được với class/thư viện ở môi trường mới không? | Thiếu class hoặc method, thay đổi kiểu dữ liệu, `NoSuchMethodError`, `NoClassDefFoundError`. |
| Tương thích hành vi (behavioral compatibility) | Chương trình có tiếp tục cho kết quả và hành vi mong đợi không? | Thay đổi mặc định về charset, locale, timezone, TLS, serialization hoặc xử lý lỗi. |
| Tương thích vận hành (operational compatibility) | Ứng dụng có khởi động, giám sát và vận hành ổn định trong môi trường đích không? | JVM option không còn được hỗ trợ, agent chưa tương thích, container thiếu công cụ hoặc cấu hình bộ nhớ không phù hợp. |
| Tương thích hệ sinh thái (ecosystem compatibility) | Các framework, plugin, driver và công cụ đi kèm có hỗ trợ tổ hợp phiên bản mới không? | Plugin build cũ, framework chưa hỗ trợ JDK đích, driver hoặc thư viện native không hoạt động. |

Ví dụ: dự án có thể biên dịch thành công sau khi nâng JDK, nhưng khi chạy lại gặp `IllegalAccessError` do thư viện dựa vào API nội bộ hoặc truy cập phản chiếu bị giới hạn. Đây là dấu hiệu cho thấy kết quả biên dịch chưa đủ để kết luận migration thành công.

## 4. Trình tự học và thực hành đề xuất

Nên học theo thứ tự từ hiểu hệ thống hiện tại đến phân tích thay đổi, sau đó mới thực hiện chuyển đổi và xác nhận kết quả. Mỗi giai đoạn cần tạo ra một đầu ra cụ thể để làm căn cứ cho giai đoạn tiếp theo.

### Bước 1: Xác định phạm vi và baseline

Trước tiên, ghi lại:

- JDK hiện tại dùng để build và JDK đang chạy ứng dụng.
- Phiên bản Java đích và lý do nâng cấp.
- Cách build, cách chạy, cách triển khai và các môi trường cần hỗ trợ.
- Module chính, service liên quan và các dependency quan trọng.
- Bộ kiểm thử hiện có cùng kết quả build/test trên phiên bản hiện tại.

Thực hành bằng cách chạy các lệnh kiểm tra phiên bản trong đúng môi trường dự án:

```bash
java -version
javac -version
mvn -version
./gradlew --version
```

Chỉ chạy lệnh tương ứng với công cụ dự án đang dùng. Trên Windows, Gradle wrapper thường được gọi bằng `gradlew.bat --version`. Lưu ý rằng kết quả `java -version` và `javac -version` có thể đến từ các JDK khác nhau nếu `PATH` hoặc cấu hình toolchain chưa thống nhất.

**Đầu ra cần có:** bản ghi phiên bản hiện tại/đích, sơ đồ thành phần ở mức tổng quan và kết quả build/test baseline.

### Bước 2: Ôn lại kiến trúc Java liên quan đến ứng dụng

Tập trung vào những phần ứng dụng thực sự sử dụng: class loading, reflection, module access, concurrency, serialization, networking, security provider và JVM options. Không cần đọc toàn bộ đặc tả JVM nếu dự án không có nhu cầu tương ứng.

Thực hành bằng cách chọn một luồng nghiệp vụ quan trọng, lần theo đường đi từ mã nguồn qua framework và thư viện đến runtime. Ghi lại các điểm có phụ thuộc vào reflection, API nội bộ, native library hoặc cấu hình JVM.

**Đầu ra cần có:** danh sách các cơ chế Java/JVM mà ứng dụng phụ thuộc và vị trí có thể bị ảnh hưởng khi nâng phiên bản.

### Bước 3: Tìm hiểu thay đổi giữa phiên bản hiện tại và phiên bản đích

Đọc tài liệu chính thức của từng phiên bản nằm trên đường nâng cấp, đặc biệt là release notes, migration guide, tài liệu API và ghi chú về thay đổi bảo mật hoặc runtime. Với bước nhảy qua nhiều phiên bản, không nên chỉ đọc tài liệu của phiên bản đích; một thay đổi có thể đã xuất hiện ở phiên bản trung gian.

Khi đọc tài liệu, phân loại mỗi thay đổi theo nhóm:

- API được thêm, deprecated, đánh dấu for removal hoặc bị loại bỏ.
- Thay đổi compiler, bytecode, module system và quy tắc truy cập.
- Thay đổi hành vi mặc định của thư viện chuẩn hoặc JVM.
- Thay đổi về bảo mật, TLS, thuật toán mật mã và chứng thư.
- Thay đổi garbage collector, logging, monitoring hoặc JVM options.
- Thay đổi yêu cầu phiên bản của framework, plugin và thư viện.

Không phải thay đổi nào trong release notes cũng tác động đến dự án. Hãy liên kết từng mục với mã nguồn, dependency hoặc cấu hình thực tế để xác định mức độ liên quan.

**Đầu ra cần có:** danh sách thay đổi có liên quan, mức độ ảnh hưởng, cách kiểm tra và người/phần việc chịu trách nhiệm xử lý.

### Bước 4: Kiểm kê và phân tích dependency

Kiểm tra dependency trực tiếp, dependency bắc cầu, plugin build, framework, application server, driver, agent và thư viện native. Với mỗi thành phần, ghi nhận phiên bản hiện tại, phiên bản hỗ trợ JDK đích theo tài liệu của nhà cung cấp, phiên bản dự kiến nâng và các ràng buộc đi kèm.

Có thể dùng các công cụ đi kèm JDK để hỗ trợ phân tích:

```bash
# Tìm phụ thuộc vào API nội bộ của JDK trong một JAR
jdeps --recursive --jdk-internals path/to/application.jar

# Tìm API deprecated trong JAR theo release được chỉ định
jdeprscan --release <target-release> path/to/application.jar

# Xem mô tả module của JAR, nếu JAR có thông tin module phù hợp
jar --describe-module --file path/to/application.jar
```

Thay `path/to/application.jar` bằng đường dẫn artifact thực tế và `<target-release>` bằng release cần kiểm tra mà công cụ đang dùng hỗ trợ. Tùy phiên bản JDK, cú pháp và phạm vi release được hỗ trợ có thể khác nhau; hãy xem `--help` hoặc tài liệu của chính JDK đó trước khi đưa lệnh vào CI.

Các công cụ trên chỉ hỗ trợ phát hiện một số nhóm vấn đề. Chúng không chứng minh rằng toàn bộ dependency tương thích, không phát hiện đầy đủ mọi thay đổi hành vi và không thay thế việc đọc tài liệu của nhà cung cấp.

**Đầu ra cần có:** ma trận dependency và danh sách cảnh báo cần xử lý hoặc xác minh.

### Bước 5: Nâng công cụ build và dependency theo thứ tự có kiểm soát

Kiểm tra khả năng hỗ trợ JDK đích của Maven/Gradle wrapper, compiler plugin, test plugin, plugin đóng gói, công cụ phân tích và CI runner. Sau đó xác định phiên bản phù hợp của framework và dependency chính.

Khi cấu hình mục tiêu biên dịch, ưu tiên cơ chế khai báo rõ release API và bytecode cần hỗ trợ. Với `javac`, tuỳ chọn `--release` giúp biên dịch theo tập API nền tảng và định dạng class file của release được chọn trong phạm vi JDK hiện tại hỗ trợ:

```bash
javac --release <target-release> -d out src/example/App.java
```

Trong dự án Maven hoặc Gradle, cấu hình tương ứng thường nằm ở compiler plugin hoặc Java toolchain. Hãy kiểm tra tài liệu phiên bản plugin đang dùng thay vì sao chép cấu hình từ một dự án khác.

Thay đổi theo từng nhóm nhỏ và build lại sau mỗi thay đổi có ý nghĩa. Khi nhiều dependency cùng thay đổi, ghi lại lý do và quan hệ phụ thuộc để có thể xác định nguồn gốc nếu phát sinh lỗi.

**Đầu ra cần có:** build script và dependency được cập nhật, cùng log build có thể tái lập.

### Bước 6: Xử lý mã nguồn và cấu hình runtime

Dựa trên lỗi compiler, cảnh báo phân tích và tài liệu migration để xử lý từng vấn đề. Các nhóm thường gặp gồm:

- Thay API đã deprecated hoặc bị loại bỏ bằng API được hỗ trợ.
- Loại bỏ phụ thuộc vào package nội bộ của JDK bằng API công khai hoặc giải pháp được thư viện hỗ trợ.
- Điều chỉnh reflection và module access theo cách đóng gói, module descriptor và chính sách truy cập của ứng dụng.
- Nâng framework/driver thay vì sửa trực tiếp mã của thư viện bên thứ ba.
- Cập nhật JVM options, system properties, cấu hình bảo mật và thiết lập môi trường.
- Xác minh charset, locale, timezone, TLS, serialization và các giá trị mặc định có thể ảnh hưởng kết quả nghiệp vụ.

Không nên xem việc thêm tuỳ chọn mở quyền truy cập module hoặc tắt một kiểm soát bảo mật là cách sửa mặc định. Nếu cần dùng một tuỳ chọn tương thích tạm thời, hãy ghi rõ nguyên nhân, phạm vi, rủi ro và kế hoạch loại bỏ.

**Đầu ra cần có:** thay đổi mã nguồn/cấu hình có giải thích, cùng danh sách vấn đề đã xử lý và vấn đề còn tồn tại.

### Bước 7: Kiểm thử trên JDK đích

Chạy build sạch và toàn bộ bộ kiểm thử phù hợp. Kiểm tra tối thiểu:

- Ứng dụng khởi động, nạp cấu hình và kết nối được với các dịch vụ phụ thuộc.
- Luồng nghiệp vụ quan trọng cho kết quả như baseline.
- Xử lý lỗi, logging, serialization và giao tiếp mạng hoạt động đúng.
- Xác thực, phân quyền, TLS và các thiết lập bảo mật vẫn đáp ứng yêu cầu.
- Không phát sinh lỗi liên kết class, lỗi truy cập module hoặc cảnh báo runtime chưa được giải thích.
- Hiệu năng và mức sử dụng tài nguyên nằm trong ngưỡng chấp nhận được.

Ví dụ lệnh kiểm tra tổng quát:

```bash
# Maven
mvn clean verify

# Gradle
./gradlew clean check
```

Chạy lệnh phù hợp với cấu trúc dự án và đảm bảo tiến trình thực sự dùng JDK đích. Nếu test phụ thuộc vào database, broker hoặc dịch vụ ngoài, môi trường kiểm thử cần được chuẩn bị tương đương với điều kiện mà test yêu cầu.

**Đầu ra cần có:** kết quả build/test, báo cáo lỗi còn lại và so sánh hiệu năng với baseline khi cần.

### Bước 8: Thử nghiệm triển khai và chuẩn bị phát hành

Triển khai lên môi trường thử nghiệm gần với production, bao gồm JDK distribution, container image, biến môi trường, JVM options, chứng thư, agent và cách giám sát. Theo dõi log khởi động, lỗi runtime, latency, throughput, CPU, heap và garbage collection.

Trước khi phát hành, cần xác định:

- Điều kiện chấp nhận migration và các chỉ số cần theo dõi.
- Cách triển khai từng bước hoặc giới hạn phạm vi người dùng nếu hệ thống hỗ trợ.
- Cách quay lại artifact, image và cấu hình runtime trước đó.
- Người chịu trách nhiệm xử lý sự cố và dữ liệu cần thu thập khi rollback.

**Đầu ra cần có:** biên bản thử nghiệm, tiêu chí phát hành, phương án rollback và xác nhận của các bên phụ trách.

## 5. Bảng theo dõi học tập và migration

Có thể dùng bảng sau để theo dõi tiến độ. Mỗi dòng nên gắn với bằng chứng cụ thể như log, kết quả test, tài liệu nhà cung cấp hoặc thay đổi trong repository.

| Giai đoạn | Nội dung cần nắm | Bằng chứng hoàn thành |
| --- | --- | --- |
| Baseline | JDK hiện tại/đích, cách build và chạy, test hiện có | Bản ghi môi trường và kết quả build/test nền |
| Java/JVM | Bytecode, class loading, module, reflection, memory và JVM options liên quan | Mô tả các cơ chế ứng dụng đang sử dụng |
| Release changes | API, runtime, bảo mật và thay đổi hành vi giữa các phiên bản | Danh sách thay đổi có liên quan đến dự án |
| Dependency | Thư viện, plugin, framework, driver, agent và native library | Ma trận phiên bản và trạng thái hỗ trợ |
| Build/code | Toolchain, compiler, dependency và mã nguồn | Build sạch trên JDK đích |
| Verification | Unit, integration, end-to-end, bảo mật và hiệu năng | Báo cáo kiểm thử và các sai khác đã được giải thích |
| Rollout | Môi trường triển khai, giám sát và rollback | Kết quả thử nghiệm cùng kế hoạch phát hành |

Một ma trận dependency tối thiểu có thể gồm các cột: tên thành phần, vai trò, phiên bản hiện tại, phiên bản dự kiến, bằng chứng hỗ trợ JDK đích, vấn đề đã biết, hành động và trạng thái. Không đánh dấu một thư viện là tương thích chỉ vì nó tải được hoặc build không báo lỗi.

## 6. Cách học hiệu quả

### Học trên một ứng dụng nhỏ trước

Tạo hoặc chọn một ứng dụng Java nhỏ có build, test, một vài dependency và cấu hình runtime. Thực hiện các bước kiểm kê, phân tích và nâng JDK trên ứng dụng này để hiểu quy trình trước khi áp dụng cho hệ thống lớn. Nếu dự án có nhiều module, chọn một module đại diện nhưng vẫn phải kiểm tra các dependency dùng chung.

### Giữ lại kết quả trước và sau chuyển đổi

Lưu phiên bản JDK, build log, test report, cấu hình và số liệu hiệu năng của baseline. Sau migration, chạy lại cùng kịch bản trong điều kiện tương đương. So sánh kết quả giúp phát hiện thay đổi hành vi hoặc hiệu năng mà compiler không thể chỉ ra.

### Phân loại lỗi trước khi sửa

Khi gặp lỗi, xác định nó thuộc compiler, dependency resolution, class loading/linking, module access, runtime behavior, security hay deployment. Sau đó tìm tài liệu của đúng thành phần và phiên bản liên quan. Cách phân loại này tránh việc sửa mã nguồn khi nguyên nhân thực tế nằm ở plugin, driver hoặc cấu hình runtime.

### Ưu tiên bằng chứng có thể kiểm tra

Ghi lại lệnh đã chạy, JDK thực tế được sử dụng, phiên bản dependency, log và kết quả test. Với một kết luận về khả năng hỗ trợ, ưu tiên tài liệu chính thức của dự án hoặc nhà cung cấp. Nếu chưa có bằng chứng, đánh dấu là chưa xác minh thay vì mặc định tương thích.

## 7. Những sai lầm thường gặp

- **Chỉ kiểm tra biên dịch:** build thành công không xác nhận binary, behavioral hay operational compatibility.
- **Bỏ qua dependency bắc cầu:** thư viện gián tiếp có thể dùng API nội bộ hoặc yêu cầu runtime cũ.
- **Quên plugin và công cụ CI:** build ở máy cá nhân thành công nhưng pipeline không chạy được vì wrapper, plugin hoặc runner chưa hỗ trợ.
- **Chỉ đọc tài liệu phiên bản đích:** bước nâng qua nhiều release có thể tích luỹ nhiều thay đổi.
- **Nâng mọi thứ cùng lúc:** khi JDK, framework, driver và build plugin thay đổi đồng thời, việc tìm nguyên nhân lỗi sẽ khó hơn.
- **Dựa vào một công cụ quét:** `jdeps` và `jdeprscan` hữu ích nhưng không thể phát hiện toàn bộ thay đổi hành vi hay bảo đảm mọi thư viện hoạt động đúng.
- **Bỏ qua kiểm thử vận hành:** ứng dụng khởi động được vẫn có thể gặp lỗi về TLS, cấu hình bộ nhớ, hiệu năng, agent hoặc container.
- **Không có phương án quay lại:** nếu chỉ lưu artifact mới mà không giữ artifact và cấu hình cũ, việc phục hồi sẽ chậm và rủi ro hơn.

## 8. Tiêu chí sẵn sàng bắt đầu migration

Trước khi chuyển sang công việc migration thực tế, hãy xác nhận các điều kiện sau:

- [ ] Đã xác định JDK hiện tại, JDK đích và môi trường triển khai cần hỗ trợ.
- [ ] Build và test baseline chạy được hoặc các lỗi nền đã được ghi nhận rõ.
- [ ] Đã lập danh sách module, framework, dependency, plugin, driver, agent và thư viện native liên quan.
- [ ] Đã đọc tài liệu thay đổi giữa các phiên bản trong phạm vi nâng cấp.
- [ ] Đã xác định các điểm sử dụng API deprecated, API nội bộ, reflection hoặc cấu hình JVM nhạy cảm.
- [ ] Đã có kế hoạch nâng toolchain và dependency theo từng nhóm có thể kiểm chứng.
- [ ] Đã xác định bộ kiểm thử và chỉ số dùng để so sánh sau chuyển đổi.
- [ ] Đã chuẩn bị môi trường thử nghiệm, tiêu chí phát hành và phương án rollback.

Nếu một điều kiện chưa đáp ứng, hãy ghi rõ phần còn thiếu và cách thu thập bằng chứng. Khi hoàn thành các điều kiện trên, người học có đủ nền tảng để bước vào các công việc phân tích và thực hiện Java compatibility migration một cách có hệ thống.

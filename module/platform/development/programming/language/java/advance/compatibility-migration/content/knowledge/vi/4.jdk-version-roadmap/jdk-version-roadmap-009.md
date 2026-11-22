# Đánh giá JDK mới hơn theo tài liệu của đúng phiên bản

Khi cân nhắc nâng cấp một ứng dụng Java lên JDK mới hơn, việc đầu tiên không phải là đọc một bài tổng quan chung về phiên bản Java mới nhất. Cần xác định chính xác JDK đích, sau đó đọc bộ tài liệu tương ứng với đúng phiên bản và đúng nhà cung cấp. Mỗi bản phát hành có thể bổ sung API, thay đổi hành vi runtime, loại bỏ tùy chọn JVM, thay đổi bảo mật hoặc đặt ra yêu cầu mới cho thư viện và công cụ build. Một thông tin đúng với JDK hiện tại có thể không đúng với phiên bản mà dự án dự định sử dụng.

Đánh giá dựa trên tài liệu phiên bản giúp trả lời những câu hỏi cụ thể: tính năng nào đã có trong JDK đích, thay đổi nào tác động đến ứng dụng, thành phần nào cần nâng cấp cùng, rủi ro nào phải kiểm thử và điều kiện nào cần đáp ứng trước khi chuyển môi trường chạy.

## 1. Xác định chính xác JDK đích trước khi đọc tài liệu

“Nâng cấp Java” là một mô tả chưa đủ cụ thể để lập kế hoạch. Trước tiên cần ghi rõ:

- **Feature release:** ví dụ JDK 17, JDK 21 hoặc JDK 25.
- **Nhà cung cấp và bản phân phối:** ví dụ Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK hoặc bản phân phối khác.
- **Bản cập nhật:** số phiên bản đầy đủ, ngày phát hành hoặc build tương ứng với môi trường dự kiến.
- **Nền tảng:** hệ điều hành, kiến trúc CPU, môi trường container hoặc máy chủ.
- **Phạm vi sử dụng:** JDK dùng để biên dịch, JDK dùng để chạy production, hay cả hai.
- **Mốc hiện tại:** JDK và bản cập nhật đang dùng trong build, test, staging và production.

Ví dụ, “chuyển từ Java 17 lên Java 21” vẫn cần được cụ thể hóa thành một bản phân phối, bản cập nhật và nền tảng triển khai. Các bản phân phối OpenJDK thường chia sẻ nền tảng mã nguồn và đặc tả Java, nhưng có thể khác nhau về lịch cập nhật, chính sách hỗ trợ, gói cài đặt, chứng thư CA, tùy chọn build, công cụ quản trị và cam kết hỗ trợ thương mại.

Phân biệt **feature release** với **update release**. Feature release đưa vào một tập thay đổi ngôn ngữ, API, JVM và công cụ. Update release thường tập trung vào sửa lỗi và bảo mật, nhưng vẫn có thể ảnh hưởng hành vi ở những trường hợp cụ thể. Vì vậy, tài liệu của feature release là điểm khởi đầu; release notes và security advisories của đúng update/build vẫn cần được kiểm tra trước khi triển khai.

Không nên mặc định mọi nhà cung cấp có cùng chính sách LTS hoặc thời gian hỗ trợ. LTS là nhãn và cam kết hỗ trợ theo chính sách của nhà cung cấp/phân phối. Hãy kiểm tra lịch hỗ trợ của đúng vendor và đúng dòng JDK mà tổ chức sẽ vận hành.

## 2. Chọn đúng bộ tài liệu cho phiên bản đích

Không có một tài liệu duy nhất mô tả toàn bộ tác động của JDK mới. Cần ghép nhiều nguồn, mỗi nguồn trả lời một nhóm câu hỏi.

### 2.1. Migration Guide

Migration Guide của phiên bản đích thường là tài liệu nên đọc đầu tiên. Nó tập trung vào những thay đổi mà người đang nâng cấp từ các phiên bản trước cần biết, chẳng hạn:

- Tính năng hoặc module đã bị loại bỏ, bị deprecated hoặc thay đổi trạng thái.
- Thay đổi mặc định của compiler, JVM, thư viện chuẩn và công cụ.
- Tùy chọn command-line cũ không còn được hỗ trợ hoặc không còn tác dụng.
- Các thay đổi về encapsulation, reflection, security, networking và serialization.
- Hành vi có thể làm ứng dụng cũ cần sửa code hoặc cấu hình.
- Hướng dẫn thay thế API hoặc tùy chọn đã bị loại bỏ.

Migration Guide thường không liệt kê mọi lỗi đã được sửa hoặc mọi chi tiết của từng bản cập nhật. Hãy dùng nó để lập danh sách khu vực cần điều tra, sau đó kiểm tra release notes và tài liệu chuyên biệt tương ứng.

### 2.2. Release Notes của đúng JDK và đúng vendor

Release Notes mô tả nội dung của một bản phát hành cụ thể. Cần đọc phần thay đổi, lỗi đã biết, lỗi đã sửa, vấn đề bảo mật và các ghi chú dành riêng cho nền tảng hoặc nhà cung cấp.

Khi kiểm tra, hãy chú ý:

- Thay đổi có thể ảnh hưởng tới ứng dụng đang dùng API hoặc hành vi cũ.
- Bug fix có làm thay đổi kết quả trong một trường hợp mà ứng dụng đang dựa vào hay không.
- Tùy chọn JVM, GC, compiler, TLS, certificate hoặc charset có thay đổi không.
- Có giới hạn, lỗi đã biết hoặc workaround nào áp dụng cho hệ điều hành/kiến trúc đang dùng không.
- Bản cập nhật có sửa một lỗ hổng nhưng đồng thời vô hiệu hóa thuật toán, giao thức hoặc cấu hình yếu mà ứng dụng vẫn sử dụng không.

Không đọc release notes của một vendor rồi mặc định toàn bộ chi tiết đóng gói và hỗ trợ giống vendor khác. Phần đặc tả Java có thể chung, nhưng phần cài đặt, cập nhật, hỗ trợ và một số ghi chú vận hành có thể riêng.

### 2.3. JEP — Java Enhancement Proposals

JEP mô tả mục tiêu, phạm vi và thiết kế của một thay đổi lớn trong OpenJDK. JEP hữu ích để hiểu vì sao một tính năng được thêm, thay đổi hoặc loại bỏ, những lựa chọn thiết kế nào đã được cân nhắc và giới hạn của tính năng.

Khi dùng JEP để đánh giá, hãy xác minh:

1. JEP đang ở trạng thái nào và đã được đưa vào bản phát hành nào.
2. Phiên bản mục tiêu có thực sự chứa thay đổi đó không.
3. Phần nào là mục tiêu thiết kế, phần nào là hành vi được triển khai.
4. Có JEP tiếp theo hoặc release note nào thay đổi, hoàn thiện hay giới hạn tính năng không.

Một JEP được đề xuất hoặc đang ở trạng thái preview/incubator không đồng nghĩa API đã ổn định hoặc được bật mặc định trong JDK đích. Không lập kế hoạch dựa trên tiêu đề JEP mà chưa kiểm tra trạng thái và tài liệu của bản phát hành thực tế.

### 2.4. API Documentation và đặc tả Java

Javadoc của đúng phiên bản giúp xác nhận lớp, interface, method, constructor, exception, module và trạng thái API. Khi ứng dụng phụ thuộc một API cụ thể, hãy đọc tài liệu của đúng JDK đích thay vì chỉ đọc trang Javadoc mới nhất.

Các nguồn liên quan gồm:

- Java SE API Specification/Javadoc cho thư viện chuẩn.
- Java Language Specification cho cú pháp và ngữ nghĩa ngôn ngữ.
- Java Virtual Machine Specification cho bytecode, class file và hành vi JVM.
- Tài liệu module system khi ứng dụng sử dụng JPMS.
- Tài liệu công cụ như `javac`, `java`, `javadoc`, `jdeps`, `jdeprscan`, `jlink`, `jpackage` và `jshell`.

API docs trả lời “API nào tồn tại và có hợp đồng gì”; migration guide và release notes trả lời “điều gì thay đổi khi chuyển phiên bản”. Cần dùng cả hai để đánh giá đầy đủ.

### 2.5. Tài liệu hỗ trợ của framework và thư viện

JDK tương thích với Java SE không có nghĩa toàn bộ ứng dụng sẽ hoạt động với JDK đó. Cần kiểm tra ma trận hỗ trợ và release notes của Spring Boot, Spring Framework, Hibernate, Jackson, Netty, Tomcat/Jetty, logging framework, test framework, JDBC driver, build plugin và các thư viện khác đang sử dụng.

Với mỗi thành phần, xác minh:

- Phiên bản thấp nhất hỗ trợ JDK đích.
- Phiên bản được khuyến nghị và các giới hạn đã biết.
- Yêu cầu nâng cấp đồng thời hoặc thay đổi cấu hình.
- Tương thích của agent, annotation processor, bytecode enhancer và plugin build.
- Hành vi đã thay đổi hoặc API bị deprecated/removed.
- Phiên bản có bản vá bảo mật và còn được hỗ trợ.

Không suy ra tương thích từ việc dependency tải được hoặc Gradle build thành công. Một thư viện có thể biên dịch được nhưng không hoạt động đúng khi runtime mới áp dụng kiểm tra module, reflection, TLS hoặc thay đổi API.

## 3. Đọc tài liệu theo lộ trình từ phiên bản hiện tại đến phiên bản đích

Nếu dự án nâng cấp qua nhiều feature release, hãy đọc thay đổi của từng phiên bản trung gian. Một thay đổi có thể xuất hiện từ phiên bản trước đó và chỉ trở thành lỗi khi ứng dụng cuối cùng chuyển lên phiên bản đích.

Ví dụ, khi đi từ JDK 11 lên JDK 21, không nên chỉ đọc tài liệu JDK 21. Cần xem các thay đổi quan trọng từ 12 đến 21, xác định thay đổi nào tác động trực tiếp và thay đổi nào đã được xử lý trong các lần nâng cấp trước. Tương tự, nếu đi từ JDK 17 lên JDK 25, cần xem chuỗi feature release ở giữa chứ không chỉ so sánh hai đầu.

Một cách làm có hệ thống:

1. Ghi phiên bản hiện tại và phiên bản đích đầy đủ.
2. Liệt kê các feature release nằm giữa hai mốc.
3. Thu thập Migration Guide và Release Notes của từng mốc cần đi qua.
4. Đánh dấu các thay đổi có thể ảnh hưởng đến API, bytecode, runtime, security, build và deployment.
5. Đọc sâu JEP/API docs đối với các thay đổi liên quan trực tiếp đến mã nguồn hoặc cấu hình đang dùng.
6. Đối chiếu release notes của đúng vendor/update build ở bước chuẩn bị phát hành.

Không cần ghi lại toàn bộ mọi tính năng mới của từng phiên bản. Chỉ cần hiểu đủ thay đổi có liên quan đến hệ thống và lưu nguồn để reviewer có thể kiểm tra lại.

## 4. Các nhóm thay đổi cần rà soát trong tài liệu JDK

### 4.1. Ngôn ngữ Java và compiler

Đọc các thay đổi liên quan đến cú pháp, type system, inference, annotation processing, compiler diagnostics và quy tắc biên dịch. Xác định source level và target bytecode mà dự án đang sử dụng.

Các câu hỏi cần trả lời:

- Source code hiện tại có biên dịch được với compiler mới không?
- Có cảnh báo mới hoặc lỗi biên dịch do thay đổi quy tắc không?
- Annotation processor, Lombok, MapStruct, QueryDSL hoặc công cụ sinh mã có hỗ trợ compiler đích không?
- Có API hoặc cú pháp mới mà nhóm định sử dụng không, và nó có phù hợp với baseline Java mà các module khác cần hỗ trợ không?
- Có dùng preview feature hoặc incubator API không?

Preview feature có thể thay đổi hoặc bị loại bỏ ở release sau. Khi thử nghiệm preview, phải bật theo đúng cơ chế của phiên bản tương ứng cho cả biên dịch và chạy, đồng thời không coi đó là API ổn định cho production. Incubator module cũng cần được đánh giá riêng về khả năng thay đổi và yêu cầu module/runtime.

### 4.2. Thư viện chuẩn và API bị loại bỏ

Kiểm tra API mới, API deprecated, API deprecated for removal và API đã bị loại bỏ. Một phương thức vẫn có thể tồn tại nhưng được khuyến cáo không dùng; một API khác có thể đã biến mất hoàn toàn trong phiên bản đích.

Tìm các phụ thuộc vào:

- Package hoặc module từng được cung cấp trong JDK nhưng đã chuyển ra thư viện ngoài hoặc bị loại bỏ.
- API nội bộ trong `sun.*`, `com.sun.*` hoặc các implementation detail không phải hợp đồng Java SE.
- Reflection truy cập field/method không public của JDK hoặc thư viện bên thứ ba.
- API có thay đổi về nullability, exception, thứ tự, mặc định hoặc semantics.
- Các công cụ và runtime component không còn được đóng gói như trước.

Ví dụ lịch sử cho thấy việc loại bỏ có thể ảnh hưởng nhiều hơn một dòng code: một số module Java EE/CORBA được loại khỏi JDK 11; Nashorn bị loại khỏi JDK 15; các thay đổi encapsulation mạnh hơn xuất hiện trong các phiên bản sau. Đây chỉ là ví dụ theo mốc lịch sử, không phải danh sách đầy đủ cho JDK đích. Luôn đối chiếu migration guide đúng phiên bản.

### 4.3. JVM, bytecode và module system

Đọc thay đổi về class file version, verifier, class loading, garbage collection, JIT, memory model, CDS, container awareness và module system. Đặc biệt chú ý khi ứng dụng dùng:

- Java agent hoặc công cụ instrumentation/bytecode transformation.
- Reflection sâu, dynamic proxy, JNI hoặc native library.
- OSGi, JPMS, custom classloader hoặc plugin architecture.
- Các cờ JVM không chuẩn hoặc cờ đã bị deprecated/removed.
- Thư viện phụ thuộc vào internal JDK API.

JDK mới có thể đóng gói API công khai giống trước nhưng thay đổi quyền truy cập tới implementation nội bộ. Nếu ứng dụng dựa vào nội bộ đó, việc chuyển runtime có thể gây lỗi `IllegalAccessError`, `InaccessibleObjectException` hoặc lỗi liên kết khác. Hãy tìm giải pháp bằng API công khai hoặc nâng cấp thư viện phụ thuộc; chỉ dùng tùy chọn mở package khi có lý do, phạm vi và kế hoạch loại bỏ rõ ràng.

### 4.4. Bảo mật và giao thức mạng

Đọc các ghi chú về TLS, cipher suite, certificate, keystore/truststore, thuật toán mật mã, LDAP, serialization, deserialization filter, xác thực và security provider. Bản cập nhật bảo mật có thể vô hiệu hóa thuật toán yếu hoặc thay đổi mặc định, khiến một hệ thống đối tác cũ không kết nối được.

Kiểm tra:

- TLS version và cipher suite mà server/client đang thương lượng.
- Certificate chain, CA, hostname verification và thời hạn chứng thư.
- Thuật toán hash, signature, key size và provider mật mã.
- Cơ chế xác thực của HTTP, LDAP, database và message broker.
- Cách xử lý dữ liệu serialize từ nguồn không tin cậy.
- Security property và file cấu hình như `java.security`.

Không khắc phục lỗi bằng cách tắt kiểm tra certificate hoặc bật lại thuật toán yếu một cách rộng rãi. Trước hết cần xác định thay đổi cụ thể trong release notes, kiểm tra cấu hình hai đầu và phối hợp nâng cấp phía đối tác.

### 4.5. Charset, locale, timezone và định dạng dữ liệu

Đọc thay đổi liên quan tới default charset, locale data, timezone database, định dạng ngày giờ, Unicode và quy tắc xử lý số. Một thay đổi mặc định có thể làm file hoặc dữ liệu được tạo trên phiên bản mới khác với dữ liệu cũ dù source code không đổi.

Ví dụ, JEP 400 chuẩn hóa UTF-8 làm default charset từ JDK 18 trong các môi trường được mô tả. Nếu ứng dụng trước đây dựa vào charset mặc định của hệ điều hành, việc nâng cấp có thể thay đổi cách đọc/ghi file. Nên chỉ định charset tường minh cho giao thức và file có hợp đồng, ví dụ dùng `StandardCharsets.UTF_8`, thay vì phụ thuộc default.

Kiểm tra thêm:

- Timestamp được lưu dưới UTC hay local time.
- Cách xử lý daylight saving time và timezone database mới.
- Locale ảnh hưởng đến parse/format ngày, số thập phân và tiền tệ.
- Unicode normalization và ký tự ngoài ASCII.
- Serialization của ngày giờ, enum và số có precision cao.

### 4.6. Garbage collector, hiệu năng và tài nguyên

JDK mới có thể thay đổi mặc định hoặc cải tiến G1, ZGC, Shenandoah, JIT, thread scheduling, memory ergonomics và cách JVM nhận diện giới hạn container. Không nên kết luận hiệu năng sẽ tốt hơn chỉ vì JDK mới có benchmark tốt.

Hãy kiểm tra các cờ JVM hiện dùng, heap sizing, metaspace, direct memory, thread pool, startup time, throughput, pause time và footprint. Một cờ cũ có thể không còn tác dụng; một mặc định mới có thể làm thay đổi mức sử dụng CPU hoặc RAM trong container.

Đánh giá bằng workload đại diện và cùng điều kiện đo: dữ liệu, concurrency, CPU/memory limit, số instance, warm-up, GC log và metric. So sánh không chỉ thời gian phản hồi trung bình mà cả p95/p99, throughput, allocation rate, GC pause, startup và mức tiêu thụ tài nguyên.

### 4.7. Công cụ JDK và cách đóng gói ứng dụng

Kiểm tra các công cụ build, debug, packaging và runtime. Những thay đổi về `javac`, `java`, `javadoc`, `jdeps`, `jdeprscan`, `jlink`, `jpackage`, JShell hoặc công cụ giám sát có thể ảnh hưởng pipeline và quy trình vận hành.

Nếu dự án tạo runtime image tùy chỉnh bằng `jlink`, cần xác minh module closure và service binding. Nếu dùng `jpackage`, cần kiểm tra installer, service integration và khác biệt nền tảng. Nếu đóng gói container, kiểm tra base image, libc, CA certificates, timezone data, font, user permissions và kiến trúc CPU.

## 5. Dùng công cụ JDK để kiểm tra các phát hiện từ tài liệu

Tài liệu cho biết điều gì có thể thay đổi; công cụ giúp xác định ứng dụng đang phụ thuộc vào phần nào. Các lệnh sau là ví dụ phổ biến, cần kiểm tra option có sẵn trong JDK đang dùng trước khi chạy.

### 5.1. Xác nhận môi trường thực tế

~~~bash
java -version
javac -version
./gradlew --version
~~~

Với Maven, có thể kiểm tra phiên bản Maven và JDK mà tiến trình Maven đang sử dụng. Trong CI, container và production, hãy ghi lại phiên bản thực tế thay vì chỉ dựa vào máy phát triển.

### 5.2. Tìm phụ thuộc vào API nội bộ

~~~bash
jdeps --jdk-internals path/to/application.jar
~~~

`jdeps` có thể phát hiện tham chiếu tới internal JDK API trong bytecode được quét. Kết quả giúp tìm thư viện hoặc class cần thay thế. Nó không phát hiện được mọi trường hợp truy cập động qua reflection, tên class tạo từ chuỗi, JNI hoặc hành vi phát sinh chỉ ở runtime. Cần kết hợp tìm kiếm mã nguồn, kiểm tra dependency và integration test.

### 5.3. Tìm API deprecated trong bytecode

~~~bash
jdeprscan --release <target-release> path/to/application.jar
~~~

`jdeprscan` hỗ trợ tìm tham chiếu tới API deprecated theo release được chỉ định, tùy phiên bản công cụ. Có thể dùng các tùy chọn như `--for-removal` khi phù hợp. Hãy đọc `jdeprscan --help` của JDK đang chạy để xác nhận cú pháp và phạm vi hỗ trợ. Kết quả không thay thế việc đọc migration guide: một số thay đổi hành vi hoặc cấu hình không được thể hiện dưới dạng tham chiếu API deprecated.

### 5.4. Biên dịch theo API của phiên bản đích

Với `javac`, tùy chọn `--release` cho phép chọn ngôn ngữ, bytecode và tập API nền tảng tương ứng với release mục tiêu mà compiler hỗ trợ:

~~~bash
javac --release <target-release> -d out @sources.txt
~~~

Trong Gradle, nên cấu hình Java toolchain cho JDK dùng để build và cấu hình release target cho compiler. Trong Maven, dùng cấu hình compiler plugin phù hợp. Cần phân biệt:

- **JDK/toolchain:** compiler và công cụ nào thực sự chạy.
- **Source level:** cú pháp Java nào được chấp nhận.
- **Target bytecode:** class file được tạo cho runtime nào.
- **Release/API baseline:** API Java SE nào được phép tham chiếu khi biên dịch.

Chỉ đặt `source` và `target` không tự giới hạn API nền tảng có thể gọi. Nếu mục tiêu là bảo đảm bytecode không tham chiếu API mới hơn baseline, hãy dùng `--release` hoặc cơ chế tương đương của build tool.

## 6. Lập bảng đối chiếu tài liệu với ứng dụng

Đọc tài liệu mà không nối với code/config hiện tại sẽ tạo ra một danh sách thay đổi chung chung. Hãy lập bảng phát hiện để mỗi thay đổi có một bằng chứng trong hệ thống hoặc được ghi rõ là chưa xác định.

| Trường | Nội dung cần ghi |
|---|---|
| JDK hiện tại/đích | Feature release, vendor, update/build và nền tảng |
| Nguồn tài liệu | Migration Guide, Release Notes, JEP, API docs hoặc vendor note |
| Mục thay đổi | Tiêu đề, mục hoặc mã JEP cụ thể |
| Nhóm ảnh hưởng | Source, binary, API, JVM, security, network, data, build hoặc deployment |
| Dấu vết trong ứng dụng | Class, dependency, cấu hình, JVM flag, schema hoặc endpoint liên quan |
| Tình trạng sử dụng | Đang dùng, chỉ có trong classpath, chưa xác minh hoặc không dùng |
| Tác động | Build failure, runtime failure, thay đổi hành vi, bảo mật hoặc vận hành |
| Hành động | Sửa code, nâng dependency, đổi cấu hình, phối hợp đối tác hoặc chấp nhận có kiểm soát |
| Kiểm thử | Unit, integration, contract, performance, security hoặc deployment test |
| Owner/trạng thái | Người xác nhận, mức độ ưu tiên và bằng chứng hoàn tất |

Ví dụ minh họa:

| Phát hiện từ tài liệu | Dấu vết cần tìm | Hướng xử lý |
|---|---|---|
| Internal API bị encapsulate mạnh hơn | Reflection, import package nội bộ, agent | Thay bằng API công khai hoặc nâng thư viện; kiểm thử runtime |
| Default charset thay đổi | `FileReader`, `FileWriter`, `new String(bytes)` không chỉ định charset | Chỉ định charset theo hợp đồng; kiểm thử file có ký tự ngoài ASCII |
| TLS/security default thay đổi | Client HTTP, JDBC, truststore, cipher config | Kiểm tra thương lượng TLS và certificate với môi trường thật |
| API bị loại bỏ | Source code, dependency bytecode, generated code | Nâng cấp hoặc thay API; biên dịch và kiểm thử với JDK đích |
| JVM option thay đổi | `JAVA_TOOL_OPTIONS`, startup script, container args | Xác minh option và đo hiệu năng trên workload đại diện |

Các ví dụ này minh họa phương pháp đối chiếu, không phải kết luận về bất kỳ JDK đích cụ thể nào. Phiên bản mục tiêu quyết định thay đổi nào thực sự áp dụng.

## 7. Xác định mức độ ảnh hưởng và ưu tiên xử lý

Không phải mọi mục trong release notes đều có cùng mức độ rủi ro. Có thể đánh giá theo bốn yếu tố:

1. **Mức liên quan:** ứng dụng có dùng API, option hoặc hành vi được đề cập không?
2. **Mức tác động:** nếu thay đổi ảnh hưởng, kết quả là lỗi build, lỗi khởi động, lỗi một chức năng, sai dữ liệu hay mất kết nối toàn hệ thống?
3. **Khả năng phát hiện:** test hiện tại có tái hiện được không, hay chỉ xuất hiện dưới tải, dữ liệu hiếm hoặc môi trường production?
4. **Khả năng phục hồi:** có rollback được không, dữ liệu mới có đọc được bởi phiên bản cũ không và có thể triển khai lại an toàn không?

Một thay đổi có thể được phân loại như sau:

- **Cần xử lý trước migration:** có bằng chứng ứng dụng đang phụ thuộc vào hành vi/API bị loại bỏ hoặc thay đổi và không có đường tương thích.
- **Cần kiểm thử xác nhận:** có khả năng ảnh hưởng nhưng chưa có bằng chứng lỗi; cần test trên JDK đích.
- **Cần phối hợp hệ thống khác:** thay đổi liên quan provider, consumer, database, vendor hoặc nền tảng nằm ngoài quyền kiểm soát của nhóm.
- **Không áp dụng:** đã xác minh ứng dụng không dùng tính năng đó hoặc tính năng không thuộc cấu hình/phân phối đang triển khai. Ghi lại lý do và bằng chứng.
- **Chưa rõ:** thiếu dữ liệu về code, runtime, owner hoặc cấu hình; không được tự chuyển thành “không áp dụng”.

Ưu tiên các thay đổi ảnh hưởng bảo mật, tính toàn vẹn dữ liệu, khả năng khởi động, kết nối liên hệ thống và khả năng rollback. Một cảnh báo deprecated có thể chưa làm ứng dụng lỗi ngay, nhưng nếu API đã được đánh dấu for removal trong lộ trình gần, cần đưa vào kế hoạch xử lý trước khi tiếp tục nâng cấp.

## 8. Kiểm thử xác nhận trên JDK đích

Sau khi đọc tài liệu và lập danh sách phát hiện, hãy chạy ứng dụng bằng đúng JDK đích. Không nên chỉ biên dịch với compiler mới rồi chạy production trên runtime cũ, hoặc ngược lại, nếu mục tiêu migration là thay cả hai.

Một bộ kiểm thử có thể gồm:

- **Build test:** compile toàn bộ module, annotation processor, generated source, test source và packaging task.
- **Unit test:** tập trung vào API, xử lý ngày giờ, charset, serialization, reflection và logic phụ thuộc hành vi runtime.
- **Integration test:** kết nối database, message broker, HTTP service, object storage, identity provider và các adapter quan trọng.
- **Contract test:** kiểm tra request/response, event schema, file format và các phiên bản provider/consumer được hỗ trợ.
- **Data migration test:** đọc dữ liệu cũ, ghi dữ liệu mới, chạy backfill, replay message và kiểm tra rollback.
- **Security test:** TLS, certificate, authentication, authorization, crypto provider và deserialization.
- **Performance test:** startup, throughput, p95/p99 latency, GC pause, memory và CPU trong môi trường tương đương production.
- **Operational test:** health check, shutdown, restart, rolling deployment, logging, metrics, tracing, alert và backup/restore.

Nên dùng dữ liệu đại diện và môi trường gần production. Test với database rỗng hoặc mock service có thể bỏ qua lỗi do dữ liệu lịch sử, certificate, quota, network policy hoặc cấu hình vendor thực tế.

Nếu hệ thống có nhiều provider/consumer, hãy kiểm tra các tổ hợp phiên bản có thể cùng tồn tại trong quá trình rollout và rollback. Ví dụ, provider mới với consumer cũ, provider cũ với consumer mới, và cặp phiên bản mới. Không cần kiểm tra một tổ hợp không thể xuất hiện trong kiến trúc triển khai, nhưng cần ghi rõ cơ sở loại trừ.

## 9. Những sai lầm thường gặp khi đọc tài liệu JDK

**Chỉ đọc trang giới thiệu tính năng mới.** Trang tổng quan thường tập trung vào điểm nổi bật, không liệt kê đầy đủ thay đổi tương thích. Cần đọc migration guide và release notes.

**Dùng tài liệu của phiên bản mới nhất thay cho phiên bản đích.** Javadoc mới nhất có thể chứa API chưa tồn tại trong JDK mà dự án sẽ triển khai. Hãy mở tài liệu đúng release.

**Đọc JEP nhưng không kiểm tra trạng thái triển khai.** JEP có thể là đề xuất, preview, incubator hoặc đã thay đổi qua các release. Cần xác nhận nó đã được đưa vào JDK đích và có trạng thái nào.

**Chỉ so sánh source code.** Cấu hình JVM, build plugin, agent, container image, certificate và database driver cũng có thể bị ảnh hưởng.

**Coi cảnh báo deprecated là lỗi ngay lập tức.** Deprecated không luôn có nghĩa API đã bị xóa, nhưng cần kiểm tra mức độ, mốc removal và kế hoạch thay thế.

**Coi không có lỗi compile là tương thích đầy đủ.** Binary, hành vi runtime, bảo mật, dữ liệu và hiệu năng cần bằng chứng riêng.

**Bỏ qua bản cập nhật của vendor.** Feature release giống nhau không đảm bảo chính sách hỗ trợ, bản vá, gói cài đặt và ghi chú vận hành giống nhau.

**Không lưu lại nguồn và quyết định.** Khi reviewer không biết kết luận dựa trên mục nào trong tài liệu, nhóm sẽ khó xác minh hoặc cập nhật đánh giá khi target JDK thay đổi.

## 10. Checklist đánh giá một JDK mới hơn

Trước khi đề xuất nâng cấp, hãy xác nhận các điểm sau:

- [ ] Đã xác định JDK hiện tại và JDK đích gồm vendor, feature release, update/build và nền tảng.
- [ ] Đã kiểm tra chính sách hỗ trợ và vòng đời của đúng bản phân phối.
- [ ] Đã đọc Migration Guide và Release Notes của phiên bản đích.
- [ ] Đã đọc các release notes trung gian nếu nâng qua nhiều feature release.
- [ ] Đã xác minh JEP liên quan đã được triển khai và đúng trạng thái trong JDK đích.
- [ ] Đã đối chiếu API docs, language/JVM specification khi thay đổi liên quan.
- [ ] Đã kiểm tra ma trận tương thích của framework, thư viện, driver, plugin và agent.
- [ ] Đã rà soát API deprecated/removed, internal API, reflection và JVM flags.
- [ ] Đã rà soát TLS, certificate, crypto, charset, locale, timezone và serialization.
- [ ] Đã kiểm tra build toolchain, bytecode target, container image và cấu hình triển khai.
- [ ] Đã chạy build/test trên JDK đích và kiểm thử các tích hợp quan trọng.
- [ ] Đã ghi rủi ro, bằng chứng, owner, phương án xử lý và điều kiện rollback.

## 11. Đầu ra của bước đánh giá

Kết quả không nên chỉ là nhận xét “JDK mới có nhiều cải tiến” hoặc “ứng dụng có vẻ tương thích”. Hãy tạo một bản đánh giá có thể dùng trực tiếp để ra quyết định:

1. **Target baseline:** JDK, vendor, update/build, OS/architecture và vai trò build/runtime.
2. **Nguồn tham khảo:** liên kết hoặc đường dẫn nội bộ tới Migration Guide, Release Notes, JEP, API docs, vendor support matrix và tài liệu framework.
3. **Danh sách thay đổi liên quan:** mỗi thay đổi có phiên bản, mục tài liệu và nhóm ảnh hưởng.
4. **Bằng chứng trong ứng dụng:** dependency, class, cấu hình, JVM option, schema hoặc runtime trace liên quan.
5. **Đánh giá tương thích:** source, binary, behavior, security, data, performance và operations.
6. **Kế hoạch xử lý:** thay đổi code/config, nâng dependency, phối hợp hệ thống khác và thứ tự triển khai.
7. **Kế hoạch kiểm thử:** môi trường, dữ liệu, tổ hợp phiên bản, tiêu chí pass/fail và người chịu trách nhiệm.
8. **Quyết định:** có thể nâng cấp, cần điều kiện trước khi nâng cấp, hoặc hoãn vì blocker đã được chứng minh.

Mỗi kết luận cần phân biệt rõ giữa sự thật đã xác minh, nhận định dựa trên tài liệu và câu hỏi còn mở. Nếu chưa biết một thư viện có tương thích hay không, hãy ghi “chưa xác minh” và chỉ rõ cần kiểm tra release notes hoặc chạy test nào. Không biến việc chưa tìm thấy lỗi thành bằng chứng rằng không có rủi ro.

Đánh giá JDK mới hơn theo tài liệu đúng phiên bản là bước chuyển từ việc nghe nói về tính năng sang quyết định kỹ thuật có căn cứ. Khi target được xác định chính xác, tài liệu được đọc theo đúng release và mọi thay đổi được nối với code, dependency, dữ liệu cùng môi trường chạy, nhóm có thể dự đoán tác động, kiểm thử đúng trọng tâm và chọn lộ trình nâng cấp an toàn hơn.

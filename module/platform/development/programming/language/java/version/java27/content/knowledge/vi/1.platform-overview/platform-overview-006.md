# Lộ trình từ mã nguồn đến ứng dụng Java chạy thực tế

## 1. Nhìn toàn bộ vòng đời của một ứng dụng Java

Một ứng dụng Java đi qua nhiều bước trước khi có thể chạy ổn định trong môi trường thật. Lập trình viên viết mã nguồn, trình biên dịch chuyển mã nguồn thành bytecode, bộ kiểm thử xác nhận hành vi, công cụ build đóng gói chương trình và môi trường triển khai cung cấp JVM cùng cấu hình cần thiết. Sau khi phát hành, ứng dụng tiếp tục cần được giám sát và cập nhật.

~~~mermaid
flowchart LR
    A[Ma nguon .java] --> B[Build va resolve dependencies]
    B --> C[Compile thanh bytecode .class]
    C --> D[Test va kiem tra chat luong]
    D --> E[Dong goi artifact]
    E --> F[Chuan bi runtime va cau hinh]
    F --> G[Deploy va khoi dong JVM]
    G --> H[Theo doi va van hanh]
    H -->|Sua loi hoac nang cap| A
~~~

Mỗi bước tạo ra một đầu ra có thể kiểm tra. Mã nguồn là đầu vào của quá trình build; bytecode là đầu vào của JVM; artifact là đơn vị được lưu trữ và chuyển giao; cấu hình cùng tài nguyên môi trường quyết định cách ứng dụng hoạt động khi chạy. Hiểu rõ ranh giới này giúp xác định lỗi đang nằm ở mã nguồn, build, đóng gói hay triển khai.

## 2. Chuẩn bị môi trường phát triển

Để phát triển và biên dịch ứng dụng nhắm đến Java 27, hãy cài đặt JDK 27 phù hợp với hệ điều hành và kiến trúc máy. JDK cung cấp cả runtime lẫn các công cụ phát triển như **java**, **javac**, **jar**, **javadoc**, **jlink** và **jpackage**. Kiểm tra môi trường bằng:

~~~bash
java --version
javac --version
~~~

Hai lệnh cần hiển thị phiên bản phù hợp với JDK dự kiến sử dụng. Nếu máy có nhiều JDK, cần kiểm tra **PATH**, **JAVA_HOME** và cấu hình của IDE hoặc build tool; lệnh **java** chạy trong terminal có thể trỏ đến JDK khác với JDK mà IDE đang dùng.

Cần phân biệt ba lựa chọn có liên quan:

- **JDK dùng để chạy build:** cung cấp công cụ biên dịch và thực thi Maven hoặc Gradle.
- **Phiên bản API và bytecode mục tiêu:** xác định mã nguồn được biên dịch theo mức Java nào.
- **Runtime khi triển khai:** JVM thực sự chạy ứng dụng trong máy chủ, container hoặc máy người dùng.

Với module này, Java 27 là phiên bản mục tiêu. Khi build bằng JDK 27, cấu hình **--release 27** giúp trình biên dịch kiểm soát cú pháp, định dạng bytecode và tập API Java được phép sử dụng theo phiên bản đó. Runtime triển khai cũng phải hỗ trợ phiên bản bytecode và API mà ứng dụng yêu cầu.

## 3. Tổ chức mã nguồn và khai báo điểm bắt đầu

Một dự án nhỏ có thể bắt đầu với cấu trúc đơn giản:

~~~text
orders-app/
├── src/
│   ├── main/java/com/example/orders/Main.java
│   └── test/java/com/example/orders/MainTest.java
├── pom.xml
└── README.md
~~~

**src/main/java** chứa mã nguồn ứng dụng; **src/test/java** chứa mã kiểm thử. Maven sử dụng cấu trúc này theo mặc định. Gradle cũng thường áp dụng cùng quy ước, giúp công cụ build tìm đúng mã nguồn mà không cần cấu hình đường dẫn riêng.

Một chương trình dòng lệnh tối thiểu có thể khai báo điểm bắt đầu bằng phương thức **main**:

~~~java
package com.example.orders;

public class Main {
    public static void main(String[] args) {
        String environment = args.length == 0 ? "local" : args[0];
        System.out.printf("Orders application running in %s%n", environment);
    }
}
~~~

Khi JVM khởi chạy lớp này, nó gọi **main** và truyền các đối số dòng lệnh vào **args**. Ứng dụng lớn thường có thêm lớp cấu hình, tầng nghiệp vụ, tầng truy cập dữ liệu và điểm khởi tạo riêng; nguyên tắc vẫn là xác định rõ điểm bắt đầu và cách các thành phần được kết nối.

## 4. Quản lý thư viện và quá trình build

Ứng dụng thực tế thường sử dụng thư viện ngoài JDK để xử lý HTTP, JSON, cơ sở dữ liệu, logging hoặc các nhu cầu chuyên biệt. Build tool quản lý những thư viện này, tải artifact từ repository, giải quyết phụ thuộc bắc cầu và thực hiện các tác vụ theo một quy trình nhất quán.

Hai lựa chọn phổ biến là Maven và Gradle. Hãy chọn một công cụ làm chuẩn cho từng dự án, lưu cấu hình build cùng mã nguồn và sử dụng Maven Wrapper (**mvnw**) hoặc Gradle Wrapper (**gradlew**) để nhóm phát triển và CI chạy cùng phiên bản build tool.

Với Maven, có thể khai báo phiên bản Java mục tiêu trong **pom.xml**:

~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đồng thời, dự án cần khai báo phiên bản Maven Compiler Plugin tương thích với Java 27 trong phần **build/plugins** hoặc **pluginManagement**. Không nên phụ thuộc vào phiên bản plugin mặc định cũ của môi trường build.

Với Gradle Groovy DSL, cấu hình toolchain và mức API biên dịch như sau:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 27
    options.encoding = 'UTF-8'
}
~~~

Toolchain giúp Gradle chọn JDK phù hợp cho các tác vụ Java. Máy build phải có JDK 27 hoặc được cấu hình cơ chế cung cấp toolchain phù hợp. Cần xác nhận phiên bản Maven/Gradle và plugin đang dùng đã hỗ trợ Java 27 trước khi đưa cấu hình vào pipeline.

Build tool thường đảm nhiệm các công việc sau:

1. Đọc cấu hình dự án và tải các dependency đã khai báo.
2. Biên dịch mã nguồn chính và mã nguồn kiểm thử.
3. Chạy kiểm thử và các bước kiểm tra được cấu hình.
4. Đóng gói artifact để chuyển sang bước phát hành.

Các lệnh thường dùng là **./mvnw clean verify** với Maven hoặc **./gradlew clean build** với Gradle. Trên Windows có thể chạy **mvnw.cmd clean verify** hoặc **gradlew.bat clean build**. Kết quả build cần có thể tái lập trên máy lập trình viên và máy CI; vì vậy nên khóa phiên bản dependency, kiểm soát repository, lưu wrapper và tránh phụ thuộc vào thư viện được cài thủ công trên một máy.

## 5. Biên dịch mã nguồn thành bytecode

Java không chạy trực tiếp tệp **.java** trong quy trình triển khai thông thường. **javac** kiểm tra mã nguồn, phân giải kiểu và biên dịch thành bytecode trong các tệp **.class**. Bytecode được thiết kế để JVM có thể nạp và thực thi trên những hệ điều hành hỗ trợ cùng nền tảng Java.

Với ví dụ không có dependency ngoài, có thể biên dịch trực tiếp:

~~~bash
javac --release 27 -d out src/main/java/com/example/orders/Main.java
~~~

Lệnh trên ghi các tệp **.class** vào thư mục **out**. Chạy lớp đã biên dịch bằng:

~~~bash
java -cp out com.example.orders.Main production
~~~

**-d** chỉ định thư mục đầu ra; **-cp** (hoặc **--class-path**) chỉ định nơi JVM tìm lớp và thư viện. Với dự án có dependency, cần đưa các thư viện cần thiết vào classpath hoặc module path theo cấu trúc ứng dụng.

Ưu tiên **--release** khi cần biên dịch cho một phiên bản Java xác định. Chỉ đặt riêng **-source** và **-target** có thể chưa đủ để ngăn mã nguồn sử dụng API mới hơn phiên bản runtime mục tiêu. Nếu ứng dụng được thiết kế theo Java Platform Module System, build cần biên dịch và chạy theo module path; nếu không, classpath vẫn là lựa chọn hợp lệ cho nhiều ứng dụng. Chỉ thêm **module-info.java** khi dự án có nhu cầu ranh giới module, khai báo phụ thuộc hoặc đóng gói module rõ ràng.

## 6. Kiểm thử và kiểm tra chất lượng trước khi đóng gói

Biên dịch thành công chỉ chứng minh mã nguồn vượt qua các kiểm tra của trình biên dịch. Nó không chứng minh logic nghiệp vụ đúng, truy vấn dữ liệu an toàn hoặc tích hợp với dịch vụ ngoài hoạt động như mong đợi.

Một pipeline có chất lượng thường kết hợp:

- **Unit test:** kiểm tra hành vi của một lớp hoặc thành phần nhỏ, tập trung vào đầu vào, đầu ra và các trường hợp biên.
- **Integration test:** kiểm tra tương tác giữa ứng dụng với cơ sở dữ liệu, HTTP server, hệ thống tệp hoặc dịch vụ được thay thế bằng môi trường kiểm thử.
- **Static analysis và compiler warnings:** phát hiện lỗi tiềm ẩn, cách dùng API không phù hợp và vấn đề về chất lượng mã.
- **Kiểm tra dependency:** phát hiện phiên bản không tương thích, thư viện có lỗ hổng đã biết hoặc artifact không rõ nguồn gốc.
- **Kiểm tra cấu hình phát hành:** xác nhận cấu hình production, quyền truy cập, biến môi trường và tài nguyên bắt buộc.

Kiểm thử nên chạy trong môi trường gần với runtime triển khai. Nếu build bằng JDK 27 nhưng production dùng runtime khác, cần xác nhận tương thích bằng kiểm thử thực tế trên đúng runtime đó. Với tính năng preview, phải chủ động bật đúng cờ khi biên dịch và chạy; do tính chất giới hạn tương thích của preview, không nên đưa chúng vào sản phẩm production nếu chưa có quyết định và kế hoạch nâng cấp rõ ràng.

## 7. Đóng gói thành artifact có thể chuyển giao

Sau khi kiểm thử đạt yêu cầu, build tool đóng gói bytecode và metadata thành artifact. Với ứng dụng Java phổ biến, định dạng thường gặp là JAR. Một JAR có thể chứa các lớp, tài nguyên và manifest; manifest có thể khai báo lớp khởi chạy để hỗ trợ lệnh **java -jar**.

Ví dụ đóng gói thư mục **out** thành JAR có điểm bắt đầu:

~~~bash
jar --create --file orders-app.jar --main-class com.example.orders.Main -C out .
java -jar orders-app.jar
~~~

JAR trên chỉ chứa các lớp trong **out**. Nếu ứng dụng sử dụng thư viện bên ngoài, những dependency đó cũng phải được cung cấp khi chạy. Có thể phát hành JAR mỏng kèm thư mục thư viện và cấu hình classpath, hoặc cấu hình plugin build để tạo executable/fat JAR phù hợp. Không nên giả định rằng mọi JAR đều tự chứa toàn bộ dependency.

Tùy loại sản phẩm, artifact có thể là:

| Loại đầu ra | Cách sử dụng |
|---|---|
| JAR thư viện | Được dự án khác khai báo làm dependency |
| JAR ứng dụng | Được khởi chạy bằng JVM cùng dependency cần thiết |
| Runtime image tùy chỉnh | Chứa runtime và các module cần cho ứng dụng |
| Bộ cài ứng dụng | Cung cấp cách cài đặt và khởi chạy trên nền tảng đích |
| Container image | Đóng gói ứng dụng cùng runtime và cấu hình chạy |

Với ứng dụng modular, **jlink** có thể tạo runtime image chỉ gồm các module cần thiết. **jpackage** hỗ trợ đóng gói ứng dụng thành bộ cài hoặc application image cho nền tảng đích; công cụ có thể tạo runtime image phù hợp hoặc sử dụng runtime image đã chuẩn bị. Cần kiểm tra yêu cầu hệ điều hành, kiến trúc CPU, thư viện native và quyền truy cập trước khi phát hành gói cài đặt.

## 8. Chuẩn bị runtime và cấu hình triển khai

JVM nạp các lớp từ artifact và các vị trí được cấu hình, kiểm tra bytecode, liên kết kiểu và khởi tạo lớp khi cần. Trong quá trình thực thi, JVM có thể diễn giải bytecode và biên dịch các đoạn mã thường chạy thành mã máy bằng JIT. Vì vậy, ứng dụng cần một runtime tương thích, đủ bộ nhớ, quyền truy cập và kết nối đến những dịch vụ mà nó sử dụng.

Ba cách triển khai thường gặp:

1. **Chạy trên máy chủ có JDK/runtime cài sẵn:** phù hợp với môi trường được quản lý tập trung. Cần cố định phiên bản runtime và cấu hình đường dẫn thực thi rõ ràng.
2. **Phân phối runtime image hoặc bộ cài:** phù hợp khi muốn cung cấp ứng dụng độc lập hơn với môi trường Java cài sẵn. Có thể dùng **jlink** cho runtime modular tùy chỉnh và **jpackage** cho gói cài đặt.
3. **Chạy trong container:** phù hợp với dịch vụ triển khai qua nền tảng container. Thường dùng multi-stage build để tách môi trường biên dịch khỏi image chạy, chỉ đưa artifact và runtime cần thiết vào image cuối.

Không nên nhúng mật khẩu, token hoặc khóa riêng vào mã nguồn, JAR hay image. Hãy đưa cấu hình môi trường ra khỏi artifact và lấy bí mật từ cơ chế quản lý secrets phù hợp. Tài khoản chạy ứng dụng nên có quyền tối thiểu; giới hạn CPU, bộ nhớ, số kết nối và dung lượng tạm cần phù hợp với tải dự kiến.

## 9. Tự động hóa build và phát hành bằng CI/CD

CI/CD đưa các bước build, kiểm thử và phát hành vào pipeline tự động. Một pipeline cơ bản có thể thực hiện theo thứ tự:

1. Lấy mã nguồn từ commit đã được review.
2. Cài hoặc chọn đúng JDK 27 và phiên bản build tool được dự án hỗ trợ.
3. Khôi phục cache dependency một cách an toàn và chạy build sạch.
4. Chạy unit test, integration test, phân tích tĩnh và kiểm tra bảo mật dependency.
5. Tạo artifact, ghi nhận phiên bản, checksum và thông tin build.
6. Lưu artifact bất biến vào kho lưu trữ hoặc registry.
7. Triển khai vào môi trường thử nghiệm, chạy smoke test rồi mới phát hành theo quy trình của tổ chức.

Artifact đã kiểm thử nên được chuyển tiếp giữa các môi trường thay vì build lại với cấu hình khác nhau ở từng nơi. Cách làm này giúp xác định chính xác phiên bản nào đã được kiểm thử và phiên bản nào đang chạy. Việc phát hành cần có cơ chế rollback hoặc chuyển lưu lượng về phiên bản ổn định nếu smoke test hay kiểm tra sau triển khai thất bại.

## 10. Vận hành và theo dõi ứng dụng

Triển khai thành công mới là điểm bắt đầu của giai đoạn vận hành. Ứng dụng cần ghi log có cấu trúc và ngữ cảnh đủ để truy vết yêu cầu; cung cấp metric về độ trễ, lưu lượng, lỗi và tài nguyên; đồng thời truyền trace qua các ranh giới dịch vụ khi hệ thống có nhiều thành phần.

Với dịch vụ chạy lâu dài, cần có health check phù hợp, xử lý tín hiệu dừng và graceful shutdown để hoàn tất hoặc hủy tác vụ đúng cách, đóng kết nối và giải phóng tài nguyên. Cần theo dõi heap, mức sử dụng CPU, thời gian GC, số thread, pool kết nối và giới hạn của container. Các tham số JVM nên được điều chỉnh dựa trên số liệu đo trong môi trường gần production thay vì sao chép một bộ cờ cố định cho mọi ứng dụng.

Khi có lỗi, hãy đối chiếu triệu chứng với từng lớp của vòng đời:

| Triệu chứng | Khu vực cần kiểm tra trước |
|---|---|
| **javac** báo lỗi | Mã nguồn, phiên bản compiler, dependency và cấu hình **--release** |
| **ClassNotFoundException** hoặc **NoClassDefFoundError** | Classpath/module path, dependency và cách đóng gói |
| **UnsupportedClassVersionError** | Runtime đang cũ hơn mức bytecode ứng dụng yêu cầu |
| Ứng dụng khởi động nhưng gọi dịch vụ thất bại | Biến môi trường, DNS, mạng, chứng thư, thông tin xác thực và timeout |
| Ứng dụng chậm hoặc hết bộ nhớ | Log, metric, heap dump, thread dump và dữ liệu profiling |

Sau mỗi lần cập nhật JDK, thư viện hoặc cấu hình triển khai, cần chạy lại kiểm thử tương thích và theo dõi hành vi sau phát hành. Điều này giúp phát hiện sớm thay đổi về API, hành vi runtime, hiệu năng hoặc yêu cầu hệ thống.

## 11. Checklist hoàn thành một bản phát hành Java

- [ ] JDK dùng để build và phiên bản Java mục tiêu được khai báo rõ ràng.
- [ ] Maven/Gradle Wrapper và phiên bản plugin tương thích được lưu trong repository.
- [ ] Dependency có phiên bản xác định và được kiểm tra nguồn gốc.
- [ ] Build sạch, kiểm thử và phân tích chất lượng đều đạt.
- [ ] Artifact có điểm khởi chạy và dependency cần thiết.
- [ ] Runtime triển khai tương thích với bytecode và API được sử dụng.
- [ ] Cấu hình và secrets được cấp từ môi trường triển khai.
- [ ] CI lưu artifact có thể truy vết và triển khai theo quy trình có rollback.
- [ ] Log, metric, health check và graceful shutdown đã được kiểm tra.

Một ứng dụng Java chỉ sẵn sàng chạy thực tế khi toàn bộ chuỗi từ mã nguồn, build, kiểm thử, đóng gói đến runtime và vận hành được kiểm soát. Mỗi artifact cần có thể truy vết về mã nguồn và cấu hình đã tạo ra nó; mỗi môi trường chạy cần được xác nhận tương thích với phiên bản Java mà ứng dụng sử dụng.

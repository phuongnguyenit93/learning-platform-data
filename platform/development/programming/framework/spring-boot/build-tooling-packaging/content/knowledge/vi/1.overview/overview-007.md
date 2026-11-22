# Ranh giới với cấu hình ứng dụng, kiểm thử chuyên sâu và Native Image

## 1. Bài học này nằm ở đâu?

Trong chủ đề **Spring Boot Build Tooling Packaging**, build tooling là phần sử dụng Gradle/Maven cùng các plugin để biên dịch, xử lý tài nguyên, quản lý dependency và tạo sản phẩm có thể phân phối (artifact). Packaging là công đoạn tổ chức những gì cần thiết thành executable JAR/WAR hoặc làm đầu vào cho container image. Đối với một ứng dụng Spring Boot chạy trên JVM, câu hỏi trung tâm là: **“Lấy những thành phần nào, đóng gói theo cấu trúc nào, và tạo ra tệp chạy được bằng cách nào?”**

Có ba lĩnh vực thường đi sát build/packaging nhưng có trách nhiệm riêng:

1. **Cấu hình ứng dụng** quyết định ứng dụng hành xử thế nào khi khởi chạy và trong từng môi trường.
2. **Kiểm thử chuyên sâu** kiểm chứng logic, hợp đồng API, tương tác hệ thống và các thuộc tính chất lượng.
3. **Native Image** là một hướng biên dịch/triển khai chuyên biệt, đòi hỏi AOT và điều kiện tương thích riêng.

Mục tiêu ở đây là nhận diện ranh giới, điểm giao nhau và cách chọn đúng công cụ khi xử lý tình huống. Các chủ đề về binding cấu hình, kỹ thuật test chi tiết hay tinh chỉnh GraalVM sẽ được học ở phần chuyên sâu tương ứng.

## 2. Bản đồ trách nhiệm

| Khía cạnh | Build Tooling & Packaging | Cấu hình ứng dụng | Kiểm thử chuyên sâu | Native Image |
| --- | --- | --- | --- | --- |
| Câu hỏi cần trả lời | Tạo artifact nào, gồm classes/resources/dependencies nào, có khởi chạy được không? | Ứng dụng dùng cổng, profile, endpoint, logging, kết nối nào? | Chức năng, tích hợp, hiệu năng và hành vi lỗi có đúng không? | Biên dịch ứng dụng thành mã máy độc lập với JVM ra sao? |
| Đầu vào thường gặp | `build.gradle`, `pom.xml`, mã nguồn, tài nguyên, dependencies, cấu hình plugin | `application.yml`, `application.properties`, biến môi trường, tham số dòng lệnh, secret bên ngoài | Test source, test fixture, mock, database/test container, tiêu chí chấp nhận | Cấu hình GraalVM Native Build Tools, Spring AOT, reachability hints, toolchain |
| Đầu ra | Executable JAR/WAR, metadata/layers; có thể dùng tạo OCI image | Giá trị cấu hình và các bean/hành vi có hiệu lực khi chạy | Kết quả test, báo cáo lỗi, bằng chứng chất lượng | Native executable hoặc container image chứa native executable |
| Nơi xử lý chính | Gradle/Maven task và Spring Boot plugin | Spring `Environment`, hệ thống cấu hình của ứng dụng | Test framework, test suite và quy trình CI | Chuỗi build AOT + native compiler/buildpacks |
| Thành công tối thiểu | Artifact tạo đúng định dạng và có thể được khởi chạy trong môi trường phù hợp | Cấu hình được nạp đúng và hoạt động đúng ý định | Các khẳng định/tiêu chí kiểm thử được thỏa mãn | Native artifact được biên dịch và chạy đúng trên nền tảng đích |

Các cột có thể phối hợp trong cùng pipeline nhưng **không thay thế nhau**. Một JAR đóng gói thành công chưa chứng minh mọi API hoặc cấu hình production đúng; một bộ test xanh chưa chứng minh artifact đã phân phối đúng; một OCI image chưa mặc nhiên là Native Image.

## 3. Ranh giới với cấu hình ứng dụng

### 3.1. Build-time khác runtime

**Build-time** xử lý cấu trúc artifact: compiler/toolchain, phiên bản dependency, class khởi động, tên tệp, tài nguyên và layout đóng gói. **Runtime** xử lý hành vi khi ứng dụng chạy: cổng HTTP, kết nối cơ sở dữ liệu, profile, mức log, khóa cấu hình tính năng và thông tin xác thực.

Ví dụ một dự án **đã áp dụng** plugin `org.springframework.boot` và plugin `java` có thể đặt tên executable JAR bằng Gradle Groovy DSL:

```groovy
// build.gradle (đoạn cấu hình packaging)
tasks.named('bootJar') {
    archiveFileName = 'demo-app.jar'
}
```

Trong khi đó, cấu hình mặc định của ứng dụng nằm ở đường dẫn:

```yaml
# src/main/resources/application.yml
server:
  port: 8080
logging:
  level:
    root: INFO
```

Sau khi đã có mã Spring Boot hợp lệ và dependencies cần thiết, có thể chạy:

```bash
./gradlew bootJar
java -jar build/libs/demo-app.jar --server.port=9090
```

Lệnh thứ nhất tạo executable JAR. Lệnh thứ hai **khởi chạy** artifact, đồng thời truyền cổng HTTP 9090 qua command-line property; đối với ứng dụng web tuân theo cấu hình thông thường, giá trị này có thể ghi đè mặc định 8080 trong file YAML. Đoạn Gradle chỉ minh họa cách đặt tên artifact, **không phải** toàn bộ cấu hình dự án độc lập. Trên Windows, dùng `gradlew.bat` thay cho `./gradlew` nếu cần.

Cần phân biệt **“đóng gói một file cấu hình”** với **“quyết định giá trị sẽ có hiệu lực”**. Theo quy ước, tài nguyên ở `src/main/resources` được xử lý và đưa vào classpath, thường là `BOOT-INF/classes` của executable JAR. Spring Boot vẫn có thể đọc các nguồn cấu hình bên ngoài JAR như environment variables, tệp cấu hình ngoài và command-line arguments. Thứ tự ưu tiên phụ thuộc nguồn cấu hình và quy tắc Spring Boot; không suy đoán rằng giá trị nằm trong JAR luôn thắng hoặc luôn thua mọi nguồn khác.

### 3.2. Thay đổi nào cần build lại?

- **Đổi tên artifact, dependency runtime, class khởi động, layout JAR, tài nguyên được đóng gói:** thuộc build/packaging; thường cần tạo lại artifact.
- **Đổi cổng, URL dịch vụ, mức log hoặc thông tin môi trường:** ưu tiên cấu hình runtime bên ngoài; với JVM application thông thường có thể dùng cùng artifact cho nhiều môi trường.
- **Đổi mã Java, cấu trúc bean hoặc tài nguyên nằm trong gói:** cần build artifact mới.
- **Thay đổi cấu hình ảnh hưởng tới bean selection khi ứng dụng đã AOT/native:** phải xem lại hạn chế AOT vì một số điều kiện đã được đánh giá ở build-time; không áp dụng máy móc nguyên tắc đổi mọi cấu hình mà không cần rebuild.

Không đưa mật khẩu/token thật trực tiếp vào `build.gradle`, `application.yml` được đóng gói hoặc tham số task ghi vào log chỉ để việc build dễ hơn. Cấu hình nhạy cảm nên được cấp qua cơ chế secret phù hợp ở môi trường chạy.

### 3.3. Build profile và Spring profile là hai khái niệm khác

Tùy chọn, task, profile của Maven/Gradle điều chỉnh **quá trình tạo artifact**; Spring profile điều chỉnh **cấu hình và bean được chọn** theo ứng dụng. Chúng có thể được phối hợp rõ ràng qua pipeline nhưng không tự động có cùng tên, không đồng nghĩa và không nhất thiết kích hoạt lẫn nhau. Ví dụ, chạy task Gradle với một property phục vụ packaging không tự động kích hoạt Spring profile có tên trùng property đó.

## 4. Ranh giới với kiểm thử chuyên sâu

### 4.1. Task build có liên quan test, nhưng packaging không quyết định chiến lược test

Trong dự án Gradle Java/Spring Boot theo cấu hình thông thường:

```bash
./gradlew test       # chạy các test được cấu hình trong task test
./gradlew bootJar    # tạo executable JAR, không mặc nhiên chạy task test
./gradlew check      # chạy các kiểm tra được gắn vào check
./gradlew build      # thường kết hợp assemble và check
```

Task `bootJar` đóng gói ứng dụng; task `test` thực thi các test mà dự án đã khai báo. Với Java plugin, `build` phụ thuộc `assemble` và `check`, còn `check` thường kéo theo `test`. Tuy nhiên task có thể được tùy biến, test có thể bị vô hiệu hóa hoặc bỏ qua, và kiểm thử tích hợp có thể dùng task riêng. Vì vậy, **không kết luận “đã chạy bootJar là đã test”** và cũng không kết luận “build xanh thì toàn bộ tích hợp production đã được kiểm chứng”.

Với Maven, lifecycle `package` thông thường chạy các pha kiểm thử đơn vị trước khi đóng gói nếu không bị bỏ qua; kiểm thử tích hợp và xác nhận ở pha `verify` chỉ xảy ra theo cấu hình plugin/lifecycle của dự án. Lệnh `spring-boot:repackage` tập trung vào cách tái đóng gói artifact, không tự trở thành một bộ kiểm thử nghiệp vụ.

### 4.2. Chọn mức kiểm thử theo rủi ro

| Tình huống | Bằng chứng thích hợp | Vì sao packaging không đủ |
| --- | --- | --- |
| Hàm tính toán sai với đầu vào biên | Unit test có assert rõ ràng | Class có mặt trong JAR không chứng minh kết quả logic |
| Endpoint trả HTTP status/body không đúng | Web/API test, contract test | Đóng gói controller không kiểm chứng hợp đồng |
| Ứng dụng không kết nối được database thật | Integration test trong môi trường có dependency tương thích | Build không đảm bảo hạ tầng, credential, schema lúc chạy |
| Chạy ổn khi tải thấp nhưng nghẽn khi tải cao | Load/performance test theo mục tiêu cụ thể | Artifact hợp lệ không đo được thông lượng/độ trễ |
| JAR build được nhưng thiếu file cấu hình hoặc thư viện | Kiểm tra nội dung artifact và smoke test khởi động | Kiểm thử đơn vị vẫn có thể xanh trong khi gói phát hành sai |

Ví dụ pipeline cơ bản trước khi phát hành có thể chạy `./gradlew test` rồi `./gradlew bootJar`, kiểm tra artifact tạo ra và chạy smoke test với cấu hình gần môi trường đích. Nếu dùng `./gradlew build` thì cần xác nhận các task test thực sự nằm trong dependency graph của dự án. Testcontainers, mock server, test slices, kiểm thử bảo mật và đánh giá hiệu năng là những kỹ thuật test riêng: build tool có thể *gọi* chúng nhưng không tự thiết kế dữ liệu thử, tình huống biên hay assert.

### 4.3. Đọc đúng tín hiệu lỗi

- **Biên dịch/resolve dependency/task packaging thất bại:** ưu tiên kiểm tra build script, toolchain, dependency graph, main class và cách tạo archive.
- **Test case thất bại:** đọc assertion, test fixture, log và nguyên nhân tại lớp hành vi/tích hợp.
- **JAR tạo thành công nhưng ứng dụng không khởi động:** kiểm tra đồng thời log runtime, cấu hình, classpath, dịch vụ phụ thuộc và môi trường chạy; không mặc định đây là lỗi Gradle.
- **Chỉ lỗi ở môi trường CI/prod:** so sánh Java runtime, đường dẫn, environment, quyền truy cập, secret và cách chạy artifact trước khi sửa packaging.

## 5. Ranh giới với Native Image

### 5.1. Ba đích đầu ra thường bị nhầm lẫn

| Đích | Đặc điểm | Cách chạy/triển khai |
| --- | --- | --- |
| **Spring Boot executable JAR trên JVM** | Chứa mã bytecode, resources, thư viện và Boot launcher; thường có `BOOT-INF/classes` và `BOOT-INF/lib` | `java -jar app.jar` trên JVM tương thích |
| **OCI container image chạy JVM** | Đóng gói application và môi trường chạy trong một image, ví dụ tạo qua Cloud Native Buildpacks | Chạy image bằng container runtime; bên trong vẫn có JVM |
| **GraalVM Native Image** | Mã máy được biên dịch trước cho hệ điều hành/kiến trúc đích, kết hợp Spring AOT và thông tin reachability | Chạy native executable trực tiếp hoặc trong container |

Lệnh Gradle `bootBuildImage` dùng Cloud Native Buildpacks để tạo **OCI image**. Ở cấu hình JVM thông thường, nó tạo image chạy JVM; khi tích hợp GraalVM Native Image plugin và cấu hình phù hợp, quy trình có thể tạo native image. Vì vậy tên “image” trong `bootBuildImage` **không đồng nghĩa** với “Native Image” của GraalVM. Task này cũng cần môi trường container/buildpack thích hợp (theo tài liệu plugin, thường cần Docker daemon).

### 5.2. Vì sao native cần một nhánh kiến thức riêng?

JVM có cơ chế nạp lớp và reflection động; quá trình biên dịch native cần biết trước nhiều cấu trúc để chọn mã và tài nguyên có thể truy cập. **Spring AOT** phân tích ứng dụng tại build-time, tạo code/cấu hình hỗ trợ, trong đó có hints cho reflection, resource, proxy hoặc serialization khi cần. **GraalVM Native Build Tools** và toolchain native đảm nhiệm bước biên dịch thực tế.

Nếu dự án áp dụng plugin GraalVM Native Image tương thích và cấu hình Spring Boot AOT, task như `nativeCompile` có thể được dùng để tạo native executable; task `nativeTest` phục vụ hướng kiểm thử native khi được thiết lập. Những task này **không xuất hiện chỉ vì** ứng dụng đã có `bootJar` hay chỉ vì thêm một property runtime.

AOT có thể cố định một số quyết định về bean graph/điều kiện ở thời điểm build. Với cấu hình tác động đến `@Profile`, `@ConditionalOnProperty` hoặc việc tạo bean, cần phân biệt giá trị được phân tích trong AOT với giá trị người vận hành muốn đổi về sau. Một số property thuần túy phục vụ runtime vẫn có thể thay đổi, nhưng các thay đổi làm khác đồ thị bean cần được thiết kế, thử nghiệm và đôi khi build lại native image.

### 5.3. Đánh giá native bằng tiêu chí thực tế

Native Image thường được cân nhắc khi cần tối ưu cold start, footprint hoặc cách triển khai, nhưng có chi phí biên dịch/toolchain, tương thích reflection/dynamic loading, reachability hints, khác biệt thư viện native và giới hạn nền tảng OS/architecture. Không khẳng định native luôn nhanh hơn ở mọi workload, ít RAM hơn trong mọi tình huống, hoặc thay thế kiểm thử JVM. Nên đánh giá trên mục tiêu đo được: thời gian khởi động, mức bộ nhớ, throughput, khả năng chẩn đoán, kích thước artifact và độ ổn định nghiệp vụ.

**Điểm dừng của bài này:** nhận biết vì sao Native Image đòi hỏi pipeline và kiểm thử riêng. Cấu hình chi tiết GraalVM, hints, AOT testing, buildpacks native và tối ưu runtime thuộc bài chuyên sâu.

## 6. Luồng điển hình và ranh giới chịu trách nhiệm

```text
Mã nguồn + dependencies + tài nguyên
                |
                v
      Gradle/Maven + Boot plugin
          |               |
          v               v
     chạy test       tạo executable JAR/WAR
     (nếu gắn          |           |
     vào pipeline)     |           +--> tạo OCI image chạy JVM
                       |
                       +--> chạy trên JVM với cấu hình runtime
                       |
                       +--> nhánh AOT + GraalVM Native Build Tools
                                      |
                                      v
                              native executable/image
```

Sơ đồ mô tả các **nhánh có thể có**, không có nghĩa chỉ gọi một task sẽ thực thi toàn bộ các bước. Artifact phải được kiểm tra theo cách nó được chạy thực tế; cấu hình môi trường, điều kiện hệ thống và bộ test phù hợp thuộc các trách nhiệm bổ sung.

Xét ba yêu cầu thường gặp:

1. **“Cùng một bản phát hành chạy cổng 8080 tại dev và 9090 tại staging.”** Dùng cơ chế cấu hình runtime Spring Boot (chẳng hạn biến môi trường hoặc tham số dòng lệnh). Không cần tách hai JAR chỉ vì khác cổng, với điều kiện ứng dụng JVM và quy trình triển khai cho phép ghi đè.
2. **“Bản phát hành thiếu thư viện khi chạy `java -jar`.”** Kiểm tra dependency scope/classpath, output của `bootJar`, nội dung archive và cách thực thi. Việc sửa `server.port` không giải quyết lỗi thiếu thư viện.
3. **“Muốn giảm thời gian cold start bằng native.”** Xác định tiêu chí hiệu năng, kiểm tra hỗ trợ Spring AOT/GraalVM của dependencies và hạ tầng build, thiết kế native pipeline và test riêng. Chỉ đổi phần mở rộng `.jar` hay chuyển JAR vào container không tạo native executable.

## 7. Cách tự kiểm tra sau khi học

Khi gặp một thay đổi hoặc sự cố, lần lượt trả lời:

1. **Điều gì cần thay đổi?** Nội dung/định dạng artifact, giá trị runtime, độ tin cậy hành vi hay cơ chế biên dịch native?
2. **Thay đổi xảy ra lúc nào?** Compile/package, build image, khởi động hay trong request đang chạy?
3. **Ai sở hữu cấu hình?** Gradle/Maven plugin, Spring Environment, framework kiểm thử hay AOT/native toolchain?
4. **Cần chứng cứ nào?** Archive inspection, chạy `java -jar`, test assertion, integration/smoke test hay benchmark native?
5. **Có thể tái sử dụng artifact không?** Với cấu hình JVM ngoại vi thường có; với mã/dependency thay đổi hoặc AOT bean conditions có thể cần build lại.
6. **Có làm đúng phạm vi không?** Không xử lý lỗi test bằng cách tắt test, không đưa secret vào artifact, không chuyển sang native chỉ để sửa một lỗi cấu hình runtime.

### Những ngộ nhận cần tránh

- **“Build thành công nghĩa là ứng dụng production đúng.”** Build chỉ xác nhận các task đã chạy thành công; cần biết task nào đã được thực thi và đã test điều gì.
- **“`bootJar` và `jar` là một.”** `bootJar` của Spring Boot tạo executable archive với launcher và dependencies theo layout Boot; task `jar` thông thường tạo plain archive theo cấu hình Java plugin. Với các cấu hình plugin phổ biến, tệp plain có classifier `plain` để tránh trùng tên.
- **“Đặt biến trong `application.yml` là đang cấu hình build tool.”** Nó thường là runtime application config được đóng gói như resource; build script mới điều khiển packaging.
- **“Có Docker/OCI image là đã có Native Image.”** Container là hình thức phân phối; native/JVM là cách chạy bên trong.
- **“Native chỉ là bật một flag.”** Native cần AOT/toolchain phù hợp, hỗ trợ thư viện, hints khi cần và kiểm thử riêng.
- **“Chạy `bootJar` đã bao gồm mọi test.”** `bootJar` tập trung tạo archive; việc chạy test phải được xác định trong graph của các task thực tế.

## 8. Tài liệu chính thống để đào sâu

- Spring Boot Gradle Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Testing: https://docs.spring.io/spring-boot/reference/testing/
- Spring Boot Gradle Plugin — Packaging OCI Images: https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html
- Spring Boot Gradle Plugin — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- Spring Boot — Introducing GraalVM Native Images: https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html
- Gradle — The Base Plugin (lifecycle tasks): https://docs.gradle.org/current/userguide/base_plugin.html

Các API, task và hành vi chính xác cần đối chiếu với **phiên bản Spring Boot/Gradle/Maven/GraalVM đang dùng trong dự án** trước khi áp dụng hướng dẫn chi tiết.
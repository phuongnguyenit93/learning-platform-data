# Thu nhỏ ví dụ tái hiện và xác định lỗi thuộc ứng dụng, Spring hay GraalVM

## 1. Vì sao cần một ví dụ tái hiện nhỏ?

Một lỗi chỉ xuất hiện khi build hoặc chạy Spring Boot Native Image thường có nhiều lớp tham gia: code ứng dụng, Spring AOT, auto-configuration, thư viện bên thứ ba, reachability metadata, GraalVM Native Image builder, C compiler/linker và môi trường container. Nếu gửi cả repository lớn cùng log hàng nghìn dòng, người khác khó xác định thành phần gây lỗi và khó kiểm tra một giả thuyết cụ thể.

Một **minimal reproducible example (MRE)** là dự án nhỏ nhất vẫn tái hiện được lỗi với các bước chạy rõ ràng. MRE giúp:

- Xác nhận lỗi có thể lặp lại từ một checkout sạch.
- Loại dependency và cấu hình không liên quan.
- Phân biệt lỗi nghiệp vụ của ứng dụng với lỗi AOT/native.
- Kiểm tra một phiên bản Spring/GraalVM hoặc một thay đổi metadata cụ thể.
- Tạo báo cáo đủ thông tin để maintainer có thể chạy mà không cần truy cập hệ thống nội bộ.

Mục tiêu của chẩn đoán là tìm ra **điều kiện nhỏ nhất làm lỗi xuất hiện**, sau đó xác định lớp sở hữu hành vi đó. Không kết luận “lỗi GraalVM” chỉ vì ứng dụng chạy được trên JVM nhưng thất bại trên native executable; lỗi có thể là metadata thiếu, thư viện chưa hỗ trợ Native Image hoặc cấu hình AOT của ứng dụng.

Sau bài học, bạn có thể:

- Tạo baseline JVM/AOT/native với cùng phiên bản dependency.
- Thu nhỏ dự án bằng cách loại từng dependency, bean, cấu hình và luồng code.
- Phân loại lỗi thuộc ứng dụng, Spring Boot/Spring Framework, thư viện bên thứ ba, GraalVM hay môi trường build.
- Thu thập log và diagnostics đúng mức cần thiết.
- Viết MRE, README tái hiện và issue report có thể hành động.
- Kiểm tra lỗi bằng một ma trận phiên bản thay vì nâng cấp nhiều thành phần cùng lúc.

## 2. Bắt đầu bằng cách mô tả chính xác triệu chứng

Trước khi thay đổi code, ghi lại bốn điều:

1. **Hành động:** lệnh nào được chạy, profile nào active, endpoint/test nào được gọi?
2. **Kết quả thực tế:** build fail, process crash, request trả sai, exception nào xuất hiện?
3. **Kết quả mong đợi:** ứng dụng cần làm gì trong cùng điều kiện?
4. **Điều kiện xuất hiện:** JVM hay native, local hay CI, Linux hay Windows, build sạch hay build có cache?

Không dùng mô tả chung như “native image không chạy”. Hãy ghi một triệu chứng quan sát được, ví dụ:

> `./mvnw -Pnative package` build thành công. Khi chạy `./target/order-service` và gửi `POST /orders`, ứng dụng ném `MissingReflectionRegistrationError` tại `OrderPluginInvoker.invokeCode`. Cùng test chạy thành công trên JVM với đúng dependency tree.

Hoặc:

> `process-aot` thất bại khi phân tích một `@Configuration` trong Spring Boot 4.2.0. Lỗi không xuất hiện khi chạy test JVM thông thường. Một dự án Spring Boot mới chỉ có configuration class đó cũng tái hiện được lỗi.

Hai mô tả trên dẫn tới các hướng kiểm tra khác nhau. Trường hợp đầu tiên ưu tiên reachability metadata; trường hợp thứ hai ưu tiên Spring AOT và cấu trúc configuration.

## 3. Chụp lại môi trường trước khi thay đổi

Native Image nhạy với phiên bản JDK, GraalVM, Native Build Tools, OS, kiến trúc và toolchain native. Một báo cáo chỉ có Spring Boot version là chưa đủ.

### 3.1. Thông tin cần ghi

| Nhóm | Thông tin |
|---|---|
| Ứng dụng | Git commit, branch, module gây lỗi, Maven/Gradle command và profile |
| Spring | Spring Boot version, Spring Framework version, Spring AOT/plugin version |
| Java | JDK vendor, version, distribution và architecture |
| GraalVM | Distribution (GraalVM Community/Oracle GraalVM), version, `native-image` version |
| Build tool | Maven/Gradle wrapper version, Native Build Tools plugin version |
| Nền tảng | OS, kernel, CPU architecture, libc, C compiler và linker |
| Native config | Build arguments, runtime arguments, reachability metadata và class-initialization options |
| Runtime | Container base image, environment variables liên quan, command và input tái hiện |

### 3.2. Thu thập thông tin bằng lệnh

Trên Linux runner:

```bash
java -version
native-image --version
./mvnw -version
./gradlew --version
uname -a
uname -m
ldd --version
gcc --version
```

Nếu dự án dùng Maven:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree -Dverbose > target/dependency-tree.txt
```

Nếu dự án dùng Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath > build/runtime-dependencies.txt
./gradlew buildEnvironment > build/build-environment.txt
```

Ghi lại các option native mà plugin thực sự truyền cho builder. Nếu cần kiểm tra command line được tạo, bật verbose output hoặc dùng `native-image --dry-run` trong một lần build tương đương. Không chỉ sao chép cấu hình từ `pom.xml`/`build.gradle`: parent POM, convention plugin, environment variables và CI có thể bổ sung option khác.

### 3.3. Giữ nguyên một baseline có thể lặp lại

Trước khi giảm dependency hoặc nâng version:

- Commit hoặc lưu patch hiện tại.
- Giữ Maven Wrapper/Gradle Wrapper và lockfiles.
- Dùng cùng JDK/GraalVM distribution và cùng native toolchain.
- Dùng cùng OS/architecture và container base image.
- Ghi lại command đầy đủ cùng exit code.
- Chạy ít nhất hai lần từ trạng thái sạch nếu lỗi có tính ngẫu nhiên.

Nếu lỗi chỉ xuất hiện trong CI, thử chạy trong cùng builder container hoặc runner image. Không kết luận lỗi của GraalVM khi local và CI đang dùng hai bản GraalVM hoặc hai libc khác nhau.

## 4. Dùng ma trận để khoanh vùng lớp gây lỗi

### 4.1. Bốn phép kiểm tra cơ bản

Chạy cùng một luồng nghiệp vụ hoặc test theo các chế độ sau:

| Chế độ | Câu hỏi cần trả lời |
|---|---|
| JVM thông thường | Code và dependency có hoạt động khi không dùng AOT/native không? |
| Spring AOT trên JVM | Mã generated bởi Spring AOT có khởi tạo và chạy đúng không? |
| Native build | GraalVM có phân tích và biên dịch được ứng dụng không? |
| Native runtime | Executable có chạy đúng luồng gây lỗi trên đúng input không? |

Không phải dự án nào cũng cần tách riêng AOT JVM thành một pipeline dài. Tuy nhiên, khi native build/runtime fail, việc kiểm tra AOT-generated code trên JVM giúp xác định lỗi xảy ra trước hay trong bước GraalVM compilation.

### 4.1.1. Chạy Spring AOT-generated code trên JVM

Đây là phép kiểm tra hữu ích vì không cần chờ GraalVM compile native image:

Với Maven dùng `spring-boot-starter-parent`:

```bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/order-service.jar
```

Với Gradle, bảo đảm build có Spring Boot AOT plugin. Plugin `org.graalvm.buildtools.native` tự áp dụng AOT plugin; nếu chỉ muốn chạy AOT trên JVM, có thể áp dụng `org.springframework.boot.aot` trực tiếp. Sau khi tạo executable JAR:

```bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/order-service.jar
```

Kiểm tra log startup có dòng `Starting AOT-processed ...` để xác nhận generated code đang được dùng. JAR phải chứa generated AOT assets; chỉ đặt `spring.aot.enabled=true` trên một JAR build thông thường là chưa đủ.

Chế độ AOT cố định classpath và bean graph theo build time. Các `@Profile` và `@ConditionalOnProperty` ảnh hưởng bean creation phải được cấu hình khi AOT processing chạy. Vì vậy, một lỗi do profile/runtime condition có thể xuất hiện ở AOT JVM dù JVM thường hoạt động.

### 4.2. Ma trận diễn giải kết quả

| JVM thường | AOT JVM | Native build | Native runtime | Hướng điều tra đầu tiên |
|---|---|---|---|---|
| Fail | Không cần chạy | Không cần chạy | Không cần chạy | Logic ứng dụng, cấu hình hoặc dependency; native chưa phải nguyên nhân đầu tiên |
| Pass | Fail | Thường chưa cần | Không cần chạy | Spring AOT contract, bean discovery, condition, generated initializer hoặc hint registrar |
| Pass | Pass | Fail | Không cần chạy | Native Image analysis, unsupported API, class initialization, toolchain hoặc build configuration |
| Pass | Pass | Pass | Fail | Runtime metadata, resource, reflection, proxy, serialization, security provider, charset/locale hoặc runtime environment |
| Pass | Pass | Pass | Pass local, fail container | OS/libc, file permission, DNS, truststore, timezone, filesystem, architecture hoặc container base image |

Ma trận này chỉ định hướng, không tự động xác định owner. Một thư viện bên thứ ba có thể chạy tốt trên JVM nhưng thiếu metadata native; đó là vấn đề tương thích của dependency hoặc metadata, chưa chắc là lỗi trong GraalVM compiler.

### 4.3. Thử thay đổi một trục phiên bản mỗi lần

Khi nghi ngờ regression, giữ các thành phần khác cố định và thử:

- Spring Boot patch/minor version khác, cùng GraalVM.
- GraalVM/JDK version khác, cùng Spring Boot và dependency.
- Native Build Tools version khác, cùng builder.
- OS/container base image khác, cùng code và version.

Nếu thay Spring Boot và GraalVM cùng lúc, bạn không biết thay đổi nào làm lỗi biến mất. Ghi kết quả thành bảng nhỏ và lưu log của từng tổ hợp.

## 5. Thu nhỏ dự án theo từng bước

Spring Boot khuyến nghị tạo một ứng dụng vanilla từ `start.spring.io`, sau đó thêm dần code và dependency cho đến khi lỗi xuất hiện. Đây là cách giảm nhiễu hiệu quả hơn việc gửi một ứng dụng production đã có nhiều năm thay đổi.

### 5.1. Tạo một project nền

Tạo project mới với:

- Đúng Spring Boot version đang nghi ngờ.
- Cùng Java version.
- Cùng Maven hoặc Gradle.
- Chỉ thêm starter tối thiểu cần để tái hiện.
- Một test hoặc `CommandLineRunner` nhỏ kích hoạt hành vi gây lỗi.

Ví dụ cấu trúc tối thiểu:

```text
native-reproducer/
  pom.xml
  mvnw
  src/
    main/
      java/com/example/reproducer/
        ReproducerApplication.java
        ReproducerService.java
    test/
      java/com/example/reproducer/
        ReproducerApplicationTests.java
```

Không copy toàn bộ `application.yml`, `@Configuration` hoặc dependency tree của ứng dụng lớn ngay từ đầu. Chỉ đưa vào phần cần thiết để tái hiện triệu chứng.

### 5.2. Thêm lại từng thành phần

Thêm lần lượt:

1. Class hoặc method nhỏ kích hoạt lỗi.
2. Một dependency liên quan trực tiếp.
3. Bean/configuration cần để khởi tạo dependency.
4. Resource, reflection, proxy hoặc serializer có liên quan.
5. Auto-configuration hoặc starter còn thiếu.
6. Test/input tái hiện chính xác.

Sau mỗi lần thêm, chạy lại đúng command. Khi lỗi xuất hiện, giữ lại thay đổi cuối cùng và thử loại riêng từng phần của thay đổi đó.

### 5.3. Loại bỏ dependency không liên quan

Kiểm tra dependency tree và thử loại:

- Starter không liên quan tới luồng lỗi.
- Logging appender hoặc monitoring agent không cần thiết để tái hiện.
- Test library không liên quan.
- Kotlin, Lombok hoặc code generation nếu không phải điều kiện gây lỗi.
- SDK nội bộ, dependency snapshot hoặc artifact không công khai.

Không xóa hàng loạt dependency cùng lúc. Nếu lỗi biến mất, bạn sẽ không biết dependency nào hoặc tương tác nào là nguyên nhân. Dùng dependency tree trước và sau để chứng minh project đã được thu nhỏ.

### 5.4. Loại configuration và bean theo nhóm

Nếu lỗi xảy ra trong Spring AOT hoặc context startup, thử bỏ từng nhóm:

- `@Configuration` và `@Import` không liên quan.
- `@ConditionalOnClass`, `@ConditionalOnProperty`, `@Profile`.
- `BeanFactoryPostProcessor` và `BeanDefinitionRegistryPostProcessor` tùy chỉnh.
- `FactoryBean`, supplier hoặc bean được đăng ký bằng API động.
- `@ConfigurationProperties` và nested properties.
- AOP, transaction, security hoặc serialization configuration.

Nếu việc bỏ một configuration làm lỗi biến mất, thêm lại từng bean/import trong configuration đó để tìm điểm kích hoạt. Ghi lại profile và property active vì điều kiện có thể được đánh giá trong quá trình AOT build.

### 5.5. Giảm external infrastructure

Nếu cần database, Redis, Kafka hoặc HTTP server bên ngoài, tạo môi trường nhỏ bằng Docker Compose hoặc Testcontainers. Chỉ giữ service thực sự cần cho lỗi. Nếu lỗi xảy ra trước khi kết nối external service, bỏ hẳn service đó khỏi MRE.

Không yêu cầu maintainer truy cập VPN, private registry hoặc cloud account của bạn. Thay endpoint nội bộ bằng service local có hành vi tương đương, hoặc cung cấp stub nhỏ nếu nó vẫn giữ được lỗi.

### 5.6. Xác nhận MRE từ checkout sạch

Một MRE chỉ đáng tin khi người khác có thể chạy lại:

```bash
git clone <reproducer-repository>
cd native-reproducer
./mvnw test
./mvnw -Pnative package
./target/reproducer
```

Với Gradle:

```bash
git clone <reproducer-repository>
cd native-reproducer
./gradlew test
./gradlew nativeCompile
./build/native/nativeCompile/reproducer
```

Thay đường dẫn executable bằng output directory thực tế của dự án. README phải nêu rõ lệnh nào pass, lệnh nào fail và kết quả mong đợi.

## 6. Xác định lỗi thuộc lớp nào

### 6.1. Lỗi thuộc ứng dụng

Dấu hiệu thường gặp:

- JVM test cũng tái hiện cùng kết quả sai.
- Input hoặc cấu hình của ứng dụng không hợp lệ.
- Lỗi biến mất khi sửa logic nghiệp vụ mà không đổi Spring/GraalVM.
- MRE không cần AOT/native để tái hiện.

Hướng xử lý: viết test cho logic, xác định contract đầu vào, kiểm tra concurrency/resource lifecycle và sửa code ứng dụng. Nếu JVM pass nhưng native fail, vẫn kiểm tra code app dùng dynamic feature hoặc class initialization trước khi chuyển owner.

### 6.2. Lỗi thuộc Spring Boot hoặc Spring Framework

Dấu hiệu:

- JVM thường hoạt động nhưng Spring AOT processing hoặc generated initializer thất bại.
- MRE mới chỉ dùng Spring và một configuration tối thiểu vẫn tái hiện.
- Lỗi liên quan bean discovery, conditions, configuration properties, proxy/AOP, generated code hoặc auto-configuration.
- Thay Spring Boot/Spring Framework version làm lỗi xuất hiện hoặc biến mất trong khi GraalVM được giữ nguyên.

Hướng xử lý:

1. Kiểm tra tài liệu AOT và known limitations của đúng Spring Boot version.
2. Kiểm tra generated sources/classes và runtime hints do AOT tạo.
3. So sánh một patch version trước/sau nếu nghi regression.
4. Kiểm tra [Spring AOT smoke tests](https://github.com/spring-projects/spring-aot-smoke-tests) để xem loại ứng dụng tương tự có được kiểm tra hay không.
5. Tạo MRE và báo Spring nếu lỗi vẫn tái hiện trên version còn được hỗ trợ.

Spring Boot không chứa sẵn hints cho mọi thư viện bên thứ ba; framework dựa vào Reachability Metadata Repository và metadata do thư viện cung cấp. Vì vậy, một lỗi thiếu reflection metadata trong dependency không tự động là lỗi Spring.

### 6.3. Lỗi thuộc thư viện bên thứ ba

Dấu hiệu:

- Lỗi tập trung trong một thư viện hoặc SDK cụ thể.
- Code dùng thư viện theo cách động mà metadata không bao phủ.
- Dependency hoạt động trên JVM nhưng fail native ở reflection, JNI, proxy, serialization hoặc resource loading.
- Một MRE Java nhỏ không cần Spring vẫn tái hiện với cùng thư viện.

Hướng xử lý:

1. Kiểm tra thư viện có trong [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata) không.
2. Kiểm tra metadata có đúng version thư viện đang dùng không.
3. Chạy với `--exact-reachability-metadata` và `-XX:MissingRegistrationReportingMode=Warn` để xác định registration thiếu.
4. Tạo metadata tối thiểu trong ứng dụng để xác nhận giả thuyết.
5. Nếu metadata thuộc trách nhiệm thư viện, báo maintainer hoặc đóng góp metadata vào repository tương ứng.

Không thêm wildcard reflection/resource lớn để làm lỗi biến mất rồi kết luận thư viện đã tương thích. Hãy xác định member/resource thực sự cần và kiểm thử luồng production.

### 6.4. Lỗi thuộc GraalVM Native Image

Dấu hiệu mạnh hơn gồm:

- Một chương trình Java nhỏ, không phụ thuộc Spring, tái hiện lỗi với cùng GraalVM/JDK.
- Build compiler crash, internal error hoặc tạo kết quả sai dù input và API được hỗ trợ.
- Lỗi vẫn tồn tại sau khi metadata, class initialization và toolchain đã được kiểm tra.
- Thay GraalVM patch version làm lỗi xuất hiện/biến mất trong khi các thành phần khác giữ nguyên.

Hướng xử lý:

1. Chạy diagnostics mode và thu thập build output.
2. Tạo MRE không có Spring nếu có thể.
3. Kiểm tra version/OS/architecture và toolchain được hỗ trợ.
4. Tìm issue đã tồn tại trong GraalVM.
5. Nếu chưa có, gửi issue kèm command, logs và MRE.

GraalVM hướng dẫn chỉ gửi Native Image runtime issue sau khi đã kiểm tra các trường hợp phổ biến như missing metadata, `java.home`/classpath, URL protocol và security provider. Dùng `--diagnostics-mode` để tạo dữ liệu chẩn đoán class initialization, substitutions và các thông tin build liên quan.

### 6.5. Lỗi thuộc môi trường build hoặc runtime

Dấu hiệu:

- Chỉ fail trên một OS, architecture, libc hoặc container base image.
- Local pass nhưng CI fail do compiler/linker, permission, memory, filesystem hoặc network.
- Native executable build trên máy này không chạy trên máy khác do CPU instruction set hoặc ABI khác.
- Lỗi xảy ra trước khi application code được gọi.

Hướng xử lý: tái hiện trong cùng container image, so sánh `native-image --version`, `gcc`/`clang`, linker, libc, architecture, environment variables và resource limits. Không gắn lỗi này cho Spring hoặc GraalVM trước khi loại được khác biệt môi trường.

## 7. Chẩn đoán missing reachability metadata

### 7.1. Khi nào nghi ngờ metadata thiếu?

Các lỗi thường liên quan:

- `MissingReflectionRegistrationError` hoặc reflection không tìm thấy member.
- `MissingResourceException` hoặc resource bundle không có trong image.
- `MissingJNIRegistrationError`.
- Dynamic proxy hoặc serialization fail ở runtime.
- Lỗi chỉ xuất hiện khi chạy một feature chưa được gọi trong các test JVM.

Đầu tiên kiểm tra dependency có metadata do thư viện hoặc Reachability Metadata Repository cung cấp chưa. Sau đó bật exact reachability metadata để phát hiện các dynamic access thiếu registration.

### 7.2. Bật exact reachability metadata

Với GraalVM for JDK 23 trở lên:

```bash
native-image --exact-reachability-metadata -jar target/order-service.jar order-service
```

Có thể giới hạn phạm vi theo package:

```bash
native-image --exact-reachability-metadata=com.example.orders -jar target/order-service.jar order-service
```

Sau khi build, chạy executable ở chế độ cảnh báo:

```bash
./order-service -XX:MissingRegistrationReportingMode=Warn
```

Chế độ `Warn` giúp liệt kê các vị trí có thể thiếu registration trong kịch bản đã chạy. Không phải mọi cảnh báo đều cần thêm metadata; tập trung vào lỗi gây hành vi sai và các đường code được ứng dụng sử dụng.

Để phát hiện lỗi metadata bị code bắt bằng `catch (Throwable)` rồi bỏ qua, chạy integration test với:

```bash
./order-service -XX:MissingRegistrationReportingMode=Exit
```

Với GraalVM trước JDK 23, tên option và thời điểm áp dụng khác: tài liệu cũ dùng `-H:ThrowMissingRegistrationErrors=` và `-H:MissingRegistrationReportingMode=Warn` ở build time. Không sao chép cờ JDK 23+ sang GraalVM cũ mà không kiểm tra `native-image --help` và tài liệu đúng version.

### 7.3. Không sửa metadata trước khi xác nhận nguồn gốc

Khi một registration bị thiếu:

1. Xác định stack trace bắt đầu từ code ứng dụng hay thư viện.
2. Xác định class/member/resource/proxy chính xác được truy cập động.
3. Kiểm tra metadata đã có từ dependency hoặc Spring AOT chưa.
4. Tạo hint tối thiểu trong MRE.
5. Chạy lại native test cho feature đó.

Nếu hint tối thiểu làm lỗi biến mất, đã có bằng chứng cho giả thuyết metadata. Sau đó quyết định hint thuộc ứng dụng, Spring integration hay thư viện. Đừng commit toàn bộ output Tracing Agent mà chưa review.

## 8. Chẩn đoán lỗi class initialization

### 8.1. Phân biệt build-time và runtime initialization

Native Image có thể khởi tạo một số class trong quá trình build để lưu trạng thái vào image heap. Nếu static initializer đọc file, environment variable, timezone, DNS, random seed hoặc secret của máy build, dữ liệu đó có thể bị capture và làm runtime behavior khác dự kiến.

Dấu hiệu:

- Log báo class đã được initialize at build time ngoài dự kiến.
- Native executable dùng giá trị environment của máy build.
- Static field chứa file handle, socket, thread hoặc object không hợp lệ khi chạy.
- Ứng dụng fail sau khi thay đổi timezone, locale, hostname hoặc config ở runtime.

### 8.2. Trace class initialization

Dùng:

```bash
native-image \
  --trace-class-initialization=com.example.orders.LegacyRegistry \
  -jar target/order-service.jar order-service
```

Hoặc bật diagnostics mode để có thêm thông tin về class initialization và substitutions:

```bash
native-image --diagnostics-mode -jar target/order-service.jar order-service
```

Khi cần tìm class nào tạo instance của một kiểu đáng ngờ trong lúc build:

```bash
native-image \
  --trace-object-instantiation=com.example.orders.LegacyRegistry \
  -jar target/order-service.jar order-service
```

Các option này có thể thay đổi theo GraalVM version. Đặt đúng tên class đầy đủ và chỉ trace class liên quan; trace toàn bộ ứng dụng tạo output rất lớn.

### 8.3. Thử runtime initialization có mục tiêu

Nếu chứng minh được static state phải được tạo theo môi trường runtime, có thể thử:

```bash
native-image \
  --initialize-at-run-time=com.example.orders.LegacyRegistry \
  -jar target/order-service.jar order-service
```

Đây là phép thử chẩn đoán và có thể trở thành cấu hình cuối nếu phù hợp. Không chuyển cả package sang runtime initialization để che một lỗi; điều đó có thể làm startup chậm hơn và không giải quyết nguyên nhân của static state bị capture.

## 9. Thu thập build diagnostics và report

### 9.1. Bật verbose và diagnostics mode

```bash
native-image \
  --verbose \
  --diagnostics-mode \
  -jar target/order-service.jar \
  order-service
```

- `--verbose` hiển thị command/tool invocation và thông tin build chi tiết hơn.
- `--diagnostics-mode` tạo diagnostics output về class initialization, substitutions và các thông tin liên quan đến quá trình build.

Giữ nguyên thư mục diagnostics cùng build log khi tạo MRE. Không chỉ gửi đoạn cuối log vì nguyên nhân thường xuất hiện trước dòng lỗi tổng kết.

### 9.2. Build report

Với GraalVM distribution hỗ trợ Build Report:

```bash
native-image --emit build-report -jar target/order-service.jar order-service
```

Build Report cung cấp thông tin các giai đoạn build và nội dung executable, ví dụ code area, image heap, resources và SBOM. Tài liệu hiện hành lưu ý Build Report không có trong GraalVM Community Edition; nếu dùng CE, bỏ qua bước này và dùng các log/report khác.

### 9.3. Build output JSON cho CI và so sánh phiên bản

Native Image có thể ghi machine-readable build output:

```bash
native-image \
  -H:BuildOutputJSONFile=target/native-build-output.json \
  -jar target/order-service.jar \
  order-service
```

File JSON hữu ích khi so sánh số lượng reachable types/methods, thời gian các phase hoặc theo dõi regression qua nhiều build. Dùng schema tương ứng với GraalVM version để đọc file; không parse human-readable console log như một API ổn định.

### 9.4. Cấu hình trong Maven và Gradle

Với Maven Native Build Tools:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--verbose</buildArg>
            <buildArg>--diagnostics-mode</buildArg>
            <buildArg>--exact-reachability-metadata</buildArg>
            <buildArg>-H:BuildOutputJSONFile=target/native-build-output.json</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Với Gradle Native Build Tools:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.addAll(
                    '--verbose',
                    '--diagnostics-mode',
                    '--exact-reachability-metadata',
                    '-H:BuildOutputJSONFile=build/native-build-output.json'
            )
            runtimeArgs.add('-XX:MissingRegistrationReportingMode=Warn')
        }
    }
}
```

Đây là cấu hình chẩn đoán tạm thời. Sau khi tìm được nguyên nhân, giữ lại những option có giá trị cho CI và bỏ các option tạo report lớn nếu không còn cần. Với GraalVM trước JDK 23, thay exact reachability/missing registration flags bằng option tương ứng của version đó.

## 10. Kiểm tra giới hạn và tương thích trước khi báo lỗi upstream

### 10.1. Kiểm tra version còn được hỗ trợ

Trước khi báo Spring Boot bug, xác nhận Spring Boot version còn được hỗ trợ trong dự án open source hoặc có chính sách support phù hợp. Nếu đang dùng version đã hết hỗ trợ, thử một version được hỗ trợ trước khi kết luận regression.

### 10.2. Kiểm tra known limitations

Spring Boot duy trì trang [Spring Boot with GraalVM](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-with-GraalVM) ghi nhận các giới hạn đã biết. Kiểm tra thư viện, tính năng hoặc JDK API đang dùng có nằm trong danh sách không.

Spring Boot cũng ghi rõ hints do Spring AOT tạo không thay thế metadata cho mọi thư viện bên thứ ba. Nếu lỗi nằm trong dependency, kiểm tra reachability metadata repository và issue của thư viện trước.

### 10.3. Dùng Spring AOT smoke tests làm đối chiếu

Repository [spring-aot-smoke-tests](https://github.com/spring-projects/spring-aot-smoke-tests) chứa các smoke tests cho Spring AOT và Native Image theo các nhánh Spring Boot. Nếu có sample gần với loại ứng dụng đang lỗi, kiểm tra xem smoke test tương tự có pass với version hiện tại không.

Smoke test pass không chứng minh ứng dụng của bạn đúng; nó chỉ giúp xác nhận một cấu hình framework phổ biến đã được kiểm tra. Smoke test fail trên cùng version có thể là dấu hiệu để điều tra Spring hoặc GraalVM.

### 10.4. Thử MRE không có Spring khi cần phân biệt GraalVM

Nếu nghi lỗi compiler/runtime của GraalVM, viết một chương trình Java nhỏ dùng API hoặc dependency nghi ngờ nhưng không khởi tạo Spring ApplicationContext. Nếu MRE đó vẫn fail với cùng GraalVM version, khả năng vấn đề nằm ở Native Image hoặc dependency tăng lên.

Nếu lỗi chỉ xuất hiện khi Spring AOT tạo initializer/bean graph, giữ lại Spring trong MRE và thử các Boot version khác. Không loại Spring ra khỏi ví dụ nếu việc loại Spring cũng loại luôn điều kiện gây lỗi.

## 11. Viết issue report có thể hành động

Một issue report tốt cho maintainer biết cách tái hiện mà không phải hỏi lại nhiều vòng.

### 11.1. Nội dung tối thiểu

| Mục | Nội dung cần ghi |
|---|---|
| Summary | Một câu mô tả lỗi và giai đoạn xảy ra |
| Versions | Spring Boot, Spring Framework, JDK, GraalVM, Native Build Tools |
| Environment | OS, architecture, libc, compiler/linker, container base image |
| Reproducer | Link MRE công khai hoặc patch tối thiểu |
| Steps | Lệnh đầy đủ theo đúng thứ tự |
| Expected | Kết quả mong đợi |
| Actual | Exception, exit code, log và thời điểm xuất hiện |
| JVM comparison | Cùng test/luồng chạy trên JVM có pass không? |
| AOT comparison | Spring AOT processing/JVM có pass không? |
| Native details | Build args, runtime args, diagnostics output và metadata liên quan |
| Version matrix | Version cuối cùng pass và version đầu tiên fail nếu đã xác định |

### 11.2. README cho MRE

Ví dụ README ngắn:

```markdown
# Native Image reproducer

## Environment
- Spring Boot: 4.2.0
- Java: 25
- GraalVM: Oracle GraalVM for JDK 25, exact build version
- OS/architecture: Linux x86_64
- Build: Maven Wrapper

## Reproduce
1. Run `./mvnw test` — passes.
2. Run `./mvnw -Pnative package` — passes.
3. Run `./target/reproducer`.
4. Send `POST /reproduce` — fails with the exception below.

## Expected
The endpoint returns HTTP 200 with the generated value.

## Actual
The native executable throws `MissingReflectionRegistrationError`.

## Logs
See `logs/native-runtime.log` and `logs/native-build.log`.
```

Thay version ví dụ bằng version thực tế. Không để placeholder hoặc mô tả mơ hồ trong MRE được gửi upstream.

### 11.3. Không gửi dữ liệu nhạy cảm

Trước khi công khai MRE/log:

- Xóa token, password, private key và certificate nội bộ.
- Thay hostname, account ID và endpoint nội bộ bằng giá trị giả lập.
- Xóa dữ liệu khách hàng và payload production.
- Kiểm tra build log có in environment variables hoặc command line chứa secret không.
- Không đính kèm artifact nội bộ nếu chưa có quyền công khai.

Nếu lỗi liên quan bảo mật, không công khai chi tiết khai thác trước khi theo quy trình báo cáo lỗ hổng của dự án.

## 12. Bảng quyết định: báo cho ai?

| Bằng chứng mạnh nhất | Owner nên kiểm tra đầu tiên | Bằng chứng cần gửi |
|---|---|---|
| JVM thường cũng fail với cùng input | Nhóm ứng dụng | Unit test, input, stack trace và logic mong đợi |
| JVM pass, Spring AOT JVM fail trong MRE chỉ có Spring | Spring Boot/Framework | MRE, generated AOT output, Boot/Framework version matrix |
| JVM/AOT pass, native runtime báo thiếu registration trong một dependency | Maintainer dependency hoặc Reachability Metadata Repository | Stack trace, exact metadata warning, dependency tree, metadata tối thiểu |
| Plain Java MRE không có Spring vẫn làm GraalVM crash/sai kết quả | GraalVM Native Image | MRE Java, native-image command, diagnostics mode, GraalVM/JDK/OS details |
| Chỉ fail trên một runner/container/architecture | Platform/build infrastructure | Runner image, libc/toolchain, cgroup/resource limit, container reproduction |
| Lỗi biến mất khi nâng một dependency riêng lẻ | Maintainer dependency đó | Version cuối pass/đầu fail, dependency tree và MRE |

Nếu bằng chứng chưa đủ, tiếp tục thu nhỏ MRE và thử version matrix. Không gán owner chỉ dựa trên tên class xuất hiện ở dòng đầu stack trace; cần xác định component nào tạo hành vi sai hoặc thiếu metadata.

## 13. Bài thực hành: điều tra lỗi reflection trong order-service

**Bối cảnh:** `order-service` chạy trên JVM bình thường. Native executable build thành công nhưng endpoint export đơn hàng ném `MissingReflectionRegistrationError` khi gọi một plugin theo tên class.

### Bước 1 — Chụp baseline

Ghi Spring Boot, Spring Framework, JDK, GraalVM, Native Build Tools, OS/architecture, build args và dependency tree. Chạy test JVM và ghi kết quả.

### Bước 2 — Bật exact metadata reporting

Build với `--exact-reachability-metadata`, chạy executable với `-XX:MissingRegistrationReportingMode=Warn`, rồi gọi endpoint export. Ghi stack trace đầy đủ và class/member được báo thiếu.

### Bước 3 — Tạo MRE

Tạo Spring Boot project mới từ Initializr. Thêm một class plugin, một invoker dùng reflection và một endpoint hoặc test gọi invoker. Không thêm database, messaging hay security nếu chúng không liên quan.

### Bước 4 — Xác định owner

- Nếu plain Java dùng cùng reflection cũng fail native, kiểm tra metadata và GraalVM.
- Nếu plain Java pass nhưng Spring AOT/native fail, kiểm tra generated hints và cách Spring đăng ký plugin.
- Nếu lỗi nằm trong plugin SDK, kiểm tra metadata do SDK cung cấp.

### Bước 5 — Kiểm chứng giả thuyết

Thêm một hint tối thiểu cho đúng constructor/method được gọi. Chạy lại native endpoint và test với `MissingRegistrationReportingMode=Exit`. Nếu lỗi biến mất, đã xác nhận metadata là nguyên nhân trực tiếp.

### Bước 6 — Hoàn thiện issue report

Đưa MRE, README, dependency tree, version matrix và log liên quan vào issue. Ghi rõ JVM pass, AOT pass/fail và native result để maintainer có thể xác định giai đoạn gây lỗi.

### Phiếu kết quả

| Hạng mục | Kết quả cần ghi |
|---|---|
| Spring Boot / Framework | _(ghi)_ |
| JDK / GraalVM | _(ghi)_ |
| Native Build Tools | _(ghi)_ |
| JVM test | PASS/FAIL |
| Spring AOT | PASS/FAIL |
| Native build | PASS/FAIL |
| Native runtime | PASS/FAIL |
| Exact metadata warning | _(ghi)_ |
| MRE tái hiện từ checkout sạch | PASS/FAIL |
| Thành phần nghi ngờ | Application / Spring / Library / GraalVM / Environment |
| Version cuối pass / đầu fail | _(ghi)_ |
| Issue report đủ thông tin | PASS/FAIL |

## 14. Ghi nhớ

Hãy mô tả triệu chứng trước, chụp môi trường và dependency tree, rồi chạy ma trận JVM, Spring AOT và Native Image. Thu nhỏ dự án bằng cách tạo ứng dụng mới và thêm lại từng dependency, configuration, bean và luồng code cho tới khi lỗi xuất hiện. Một MRE phải chạy được từ checkout sạch và ghi rõ lệnh pass/fail.

Lỗi JVM thường hướng về ứng dụng hoặc dependency; lỗi trong Spring AOT hướng về Spring configuration/generated code; lỗi native runtime có thể là missing metadata hoặc khác biệt môi trường; chỉ kết luận GraalVM khi một chương trình Java nhỏ cũng tái hiện được vấn đề trong Native Image. Dùng exact reachability metadata, diagnostics mode, class-initialization tracing và build reports để thu thập bằng chứng. Gửi issue cùng MRE, version matrix và log đã loại dữ liệu nhạy cảm.

### Tài liệu tham khảo chính thức

- [Spring Boot — How To Get Help](https://github.com/spring-projects/spring-boot/wiki/How-To-Get-Help)
- [Spring Boot — Advanced Native Images Topics and Known Limitations](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Ahead-of-Time Processing With the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html)
- [Spring Boot — With GraalVM: Known Limitations](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-with-GraalVM)
- [Spring AOT Smoke Tests](https://github.com/spring-projects/spring-aot-smoke-tests)
- [GraalVM — Troubleshoot Native Image Run-Time Errors](https://www.graalvm.org/latest/reference-manual/native-image/guides/troubleshoot-run-time-errors/)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM — Native Image Build Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/)
- [GraalVM — Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/)
- [GraalVM — Specify Class Initialization Explicitly](https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/)
- [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata)
- [GraalVM — Contributing and Reporting Bugs](https://github.com/oracle/graal/blob/master/CONTRIBUTING.md)

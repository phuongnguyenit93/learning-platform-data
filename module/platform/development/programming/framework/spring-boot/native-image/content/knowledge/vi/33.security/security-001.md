# Dữ liệu đọc lúc khởi tạo build có thể trở thành một phần của image heap

GraalVM Native Image có thể thực thi một phần code trong lúc tạo executable. Nếu static initializer của class chạy ở build time, trạng thái static được tạo ra có thể được lưu vào **image heap** và đi theo binary đến môi trường triển khai. Điều này hữu ích khi dữ liệu là hằng số an toàn, nhưng trở thành rủi ro nếu class initializer đọc password, API token, private key, thông tin môi trường build hoặc dữ liệu chỉ nên được lấy khi ứng dụng khởi động.

Một native executable vì thế có thể chứa dữ liệu nhạy cảm dù source code không có literal secret. Ví dụ, một class đọc biến môi trường trong static initializer rồi gán vào static field có thể đưa giá trị từ máy CI vào image nếu class được khởi tạo trong lúc build.

Bài này giải thích image heap, class initialization, sự khác nhau giữa Spring AOT và GraalVM build-time initialization, cách chuyển class nhạy cảm sang runtime initialization, cách nạp secret an toàn cho Spring Boot và cách kiểm tra artifact trước khi phát hành.

## 1. Build time, runtime và image heap

Native Image không chỉ biên dịch bytecode. Trong quá trình phân tích và tạo executable, builder có thể thực thi code Java. Những thao tác đó được gọi là **build-time execution**. Khi class được khởi tạo ở giai đoạn này, static initializer chạy trên JVM của tiến trình build.

Image heap là vùng trạng thái ban đầu được đóng gói trong native executable. Nó có thể chứa:

- Object được tạo trong lúc build và còn reachable từ code ứng dụng.
- Static state của class đã được khởi tạo ở build time.
- Các object constant được nhúng trong method code.
- Metadata và các object phục vụ runtime.

Khi executable khởi động, image heap ban đầu được nạp vào runtime. Do đó, dữ liệu có thể tồn tại trong binary trước khi ứng dụng nhận bất kỳ request hay runtime configuration nào.

Không phải mọi object tạm thời được tạo trong build đều được lưu lại. Object chỉ còn trong image nếu nó reachable từ các root mà Native Image giữ lại, chẳng hạn static field hoặc constant được nhúng. Tuy nhiên, nếu một static field giữ tham chiếu tới secret, toàn bộ object graph reachable từ field đó có thể trở thành một phần của image.

### Sơ đồ vòng đời dữ liệu

~~~mermaid
flowchart TD
    A["CI build environment"] --> B["native-image builder"]
    B --> C["Class initializer chạy ở build time"]
    C --> D["Đọc property, env, file hoặc dữ liệu khác"]
    D --> E["Gán vào static field / object reachable"]
    E --> F["Image heap"]
    F --> G["Native executable được phát hành"]
    G --> H["Runtime trên máy đích"]
    H --> I["Dữ liệu build-time vẫn tồn tại"]
    J["Runtime environment / secret store"] --> K["Runtime initialization"]
    K --> L["Ứng dụng nhận cấu hình theo môi trường triển khai"]
~~~

Ví dụ, nếu static initializer đọc System.getProperty("partner.token") trong lúc build và class được khởi tạo tại build time, giá trị đó có thể được lưu vào image heap. Khi chạy executable, truyền một system property khác không nhất thiết thay đổi static field đã được snapshot.

## 2. Khi nào class được khởi tạo ở build time?

Trong Java, class được khởi tạo khi nó được sử dụng lần đầu theo quy tắc của JVM. Với Native Image, class application mặc định được khởi tạo ở runtime, ngoại trừ những class mà Native Image chứng minh là an toàn để khởi tạo ở build time. Các class JDK và một số class runtime có chính sách riêng.

Class có thể được khởi tạo tại build time khi:

- Được chỉ định rõ bằng --initialize-at-build-time.
- Static initializer của nó được gọi bởi một class đã được khởi tạo ở build time.
- Native Image xác định initializer là an toàn theo phân tích của compiler.
- Framework hoặc thư viện đóng góp class-initialization configuration.

Ví dụ, cấu hình sau yêu cầu builder khởi tạo class cụ thể trong lúc tạo image:

~~~bash
native-image \
  --initialize-at-build-time=com.example.catalog.StaticCatalog \
  -cp target/classes \
  com.example.catalog.Application
~~~

Khi class được khởi tạo ở build time, các static field đã được gán có thể trở thành trạng thái trong executable. Nếu initializer đọc dữ liệu từ môi trường build, binary có thể mang theo dữ liệu đó.

### Không nhầm việc load class với khởi tạo class

JVM có thể load class mà chưa chạy static initializer. Việc class xuất hiện trong classpath hoặc được tham chiếu trong bytecode không tự động có nghĩa static initializer đã chạy tại build time.

Điểm cần điều tra là **class initialization policy** và thời điểm initializer thực sự được thực thi. Dùng diagnostics để xác định nguyên nhân thay vì suy luận chỉ từ việc class có mặt trong image.

## 3. Ví dụ: system property bị snapshot vào image

Tạo class có static field đọc system property:

~~~java
package com.example.security;

public final class BuildSnapshot {

    private static final String MARKER;

    static {
        MARKER = System.getProperty("demo.marker", "unset");
    }

    private BuildSnapshot() {
    }

    public static String marker() {
        return MARKER;
    }
}
~~~

Ứng dụng in giá trị:

~~~java
package com.example;

import com.example.security.BuildSnapshot;

public class Application {

    public static void main(String[] args) {
        System.out.println(BuildSnapshot.marker());
    }
}
~~~

Build native với một giá trị minh họa, không phải secret:

~~~bash
native-image \
  --initialize-at-build-time=com.example.security.BuildSnapshot \
  -Ddemo.marker=build-value \
  -cp target/classes \
  com.example.Application
~~~

Chạy executable với giá trị khác:

~~~bash
./application -Ddemo.marker=runtime-value
~~~

Nếu BuildSnapshot đã được khởi tạo trong lúc build, chương trình vẫn in build-value. Static field đã được tạo và snapshot vào image heap; runtime property không chạy lại initializer đó.

Đây là mô hình có thể gây rò rỉ nếu thay demo.marker bằng database password, API token, encryption key hoặc thông tin nhận diện môi trường build.

### Cách sửa cho class cần dữ liệu runtime

Yêu cầu class chỉ được khởi tạo khi executable chạy:

~~~bash
native-image \
  --initialize-at-run-time=com.example.security.BuildSnapshot \
  -cp target/classes \
  com.example.Application
~~~

Khi đó initializer được chạy ở runtime và đọc system property của tiến trình native. Đây là một biện pháp kỹ thuật cho class cụ thể; thiết kế tốt hơn vẫn là tránh giữ secret trong static field.

## 4. Những dữ liệu không nên được snapshot

Hãy xem xét mọi dữ liệu có thể thay đổi giữa build và deployment, đặc biệt:

| Dữ liệu | Vì sao không nên snapshot |
| --- | --- |
| Database password | Có thể là credential của môi trường build hoặc staging, không phải production |
| API token, OAuth client secret | Binary có thể bị sao chép và token có thể bị trích xuất |
| Private key, HMAC key, encryption key | Lộ khóa có thể cho phép giả mạo chữ ký hoặc giải mã dữ liệu |
| Secret manager response | Có thể trả secret theo identity của build agent |
| Random seed, nonce state | Có thể bị cố định giữa nhiều executable hoặc replica |
| Hostname, IP, region, tenant ID | Binary bị gắn với máy hoặc môi trường build |
| License token | Có thể bị phát hành cùng artifact và tái sử dụng ngoài phạm vi |
| File path hoặc certificate riêng của tổ chức | Có thể làm binary phụ thuộc vào hạ tầng build hoặc lộ thông tin nội bộ |

Không phải mọi giá trị cấu hình đều là bí mật. Hằng số như tên metric, định dạng giao thức hoặc bảng dữ liệu công khai thường phù hợp để snapshot nếu không chứa dữ liệu theo môi trường.

Quy tắc thực tế: nếu giá trị phải khác nhau giữa dev, staging, production, tenant hoặc replica, hãy đọc nó ở runtime thay vì trong static initializer.

## 5. Phân biệt Spring AOT với GraalVM build-time initialization

Hai cơ chế cùng có chữ AOT/build time nhưng thực hiện công việc khác nhau.

**Spring AOT** phân tích ApplicationContext trong lúc build, đánh giá cấu hình và điều kiện bean, rồi sinh Java source, bytecode và RuntimeHints để ứng dụng khởi động hiệu quả hơn. Một số quyết định về bean graph được cố định theo classpath và Environment ở build time.

**GraalVM Native Image build-time initialization** chạy static initializer của class trong lúc tạo native executable. Static state và object reachable được giữ trong image heap.

Hai cơ chế có thể xuất hiện trong cùng pipeline nhưng không đồng nghĩa:

| Cơ chế | Kết quả được tạo | Rủi ro cần quản lý |
| --- | --- | --- |
| Spring AOT processing | Generated code, bytecode, hints và quyết định về bean graph | Profile/condition phụ thuộc Environment build time |
| GraalVM class initialization | Static state và object được giữ trong image heap | Secret hoặc trạng thái môi trường build có thể được snapshot |
| Native Image resource inclusion | File/resource được đóng gói vào executable | File cấu hình hoặc certificate không nên phân phối có thể bị nhúng |
| Build argument/system property | Giá trị được truyền cho tiến trình builder | Có thể xuất hiện trong log, process metadata hoặc được static initializer đọc |

Không nên kết luận rằng mọi property Spring đọc trong processAot tự động trở thành secret trong image heap. Spring AOT thường sinh cấu trúc bean và mã khởi tạo; image heap là cơ chế lưu object của Native Image. Tuy nhiên, nếu callback, processor hoặc static initializer đọc secret trong build, hoặc giá trị được ghi vào generated source/resource, dữ liệu vẫn có thể bị đóng gói theo đường đó.

### Điều gì bị cố định trong Spring AOT?

Spring AOT đánh giá các điều kiện ảnh hưởng tới bean graph, ví dụ @Profile và @ConditionalOnProperty, trong môi trường build. Bean được chọn khi AOT processing có thể vẫn được đăng ký khi chạy executable, kể cả khi runtime environment khác.

Vì vậy:

- Dùng runtime properties cho endpoint, timeout, password và token của bean đã được tạo.
- Không dùng secret value làm điều kiện quyết định bean có tồn tại hay không.
- Chọn profile và feature condition khi build theo thiết kế deployment rõ ràng.
- Không gọi secret manager hoặc database từ callback AOT chỉ để tạo bean graph.

## 6. Thiết kế Spring Boot để đọc secret tại runtime

Tránh cách khai báo sau:

~~~java
public final class PartnerCredentials {

    public static final String API_TOKEN =
            System.getenv("PARTNER_API_TOKEN");

    private PartnerCredentials() {
    }
}
~~~

Nếu class này được khởi tạo tại build time, token có thể được giữ trong static field và đóng gói vào image.

Dùng cấu hình được inject vào bean thay thế:

~~~java
package com.example.partner;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner")
public record PartnerProperties(
        URI endpoint,
        String apiToken
) {
}
~~~

Đăng ký properties:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Inject vào service:

~~~java
@Service
public class PartnerClient {

    private final PartnerProperties properties;

    public PartnerClient(PartnerProperties properties) {
        this.properties = properties;
    }

    public void submit(Order order) {
        String endpoint = properties.endpoint().toString();
        String token = properties.apiToken();

        // Gửi request bằng HTTP client đã được cấu hình.
        // Không log token hoặc đưa token vào exception message.
    }
}
~~~

Cấu hình endpoint không nhạy cảm trong application.yml:

~~~yaml
partner:
  endpoint: https://partner.example.internal
~~~

Cấp token bằng environment variable tại thời điểm chạy:

~~~bash
# The deployment platform injects PARTNER_API_TOKEN from its secret store
# when the native process starts. No literal token is stored in the image.
~~~

Spring Boot relaxed binding ánh xạ PARTNER_API_TOKEN vào partner.api-token. Giá trị được lấy từ môi trường của tiến trình native khi cấu hình bean runtime được bind.

### Dùng secret được mount thành file

Trong container hoặc Kubernetes, secret có thể được mount thành file. Spring Boot hỗ trợ config tree:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Nếu thư mục chứa file có tên partner.api-token, nội dung file được ánh xạ thành property partner.api-token. Mount secret vào container lúc chạy để cùng một binary có thể dùng credential khác nhau theo môi trường.

Không đưa file secret vào source tree, Docker build context, executable JAR, resource directory hoặc native-image builder container.

## 7. Chuyển class nhạy cảm sang runtime initialization

Nếu thư viện hoặc class hiện tại đọc dữ liệu nhạy cảm trong static initializer, có thể yêu cầu GraalVM trì hoãn khởi tạo class đó.

### Native Image command line

~~~bash
native-image \
  --initialize-at-run-time=com.example.security.SecretBootstrap \
  -cp target/classes \
  com.example.Application
~~~

Có thể chỉ định nhiều class bằng danh sách phân tách dấu phẩy:

~~~bash
native-image \
  --initialize-at-run-time=com.example.security.SecretBootstrap,com.example.crypto.RuntimeKeyProvider \
  -cp target/classes \
  com.example.Application
~~~

Có thể chỉ định package, nhưng package rule ảnh hưởng nhiều class hơn. Ưu tiên class cụ thể để hạn chế tác động hiệu năng và tránh thay đổi chính sách khởi tạo của thành phần không liên quan.

### Maven Native Build Tools

Thêm argument vào cấu hình plugin đang dùng:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--initialize-at-run-time=com.example.security.SecretBootstrap</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Nếu POM đã có native-maven-plugin, hãy bổ sung argument vào cấu hình hiện tại thay vì khai báo plugin trùng lặp.

### Gradle Native Build Tools

Ví dụ Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.security.SecretBootstrap"
            )
        }
    }
}
~~~

Ví dụ Kotlin DSL:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.security.SecretBootstrap"
            )
        }
    }
}
~~~

Tên binary và DSL có thể thay đổi theo cấu hình/phiên bản plugin. Xác nhận option thực sự được truyền tới Native Image bằng build log.

### Lưu ý về class hierarchy

Chính sách class initialization chịu ảnh hưởng của superclass, superinterface có default method và subclass liên quan. Khi chuyển một class sang runtime initialization, các lớp liên quan có thể cũng bị ảnh hưởng theo quy tắc của Native Image.

Ngoài ra, instance của class được khởi tạo ở runtime không được tồn tại sẵn trong image heap. Nếu class đã được khởi tạo hoặc instance đã được tạo trong quá trình build, chỉ thêm option runtime có thể làm phát sinh lỗi. Hãy tìm nơi class bị khởi tạo sớm và loại bỏ việc tạo instance đó khỏi build-time path.

Không thêm --initialize-at-build-time cho toàn bộ package hoặc toàn bộ ứng dụng chỉ để tăng tốc. Chỉ cho phép build-time initialization đối với class đã xác minh không đọc secret, không phụ thuộc máy build và không tạo trạng thái runtime cần làm mới.

## 8. TrustStore là một trường hợp đặc biệt

GraalVM Native Image mặc định capture TrustStore của host build và nhúng nội dung đó vào executable. Nếu build trên máy có root CA nội bộ, binary có thể mang theo bộ chứng chỉ đó khi phát hành.

Điều này có thể hữu ích nếu mọi deployment phải dùng cùng trust anchor. Tuy nhiên, nó có thể tạo ra các vấn đề:

- Binary được gắn với trust configuration của máy build.
- Cập nhật root CA trên máy runtime không nhất thiết cập nhật TrustStore đã capture.
- Chứng chỉ nội bộ có thể tiết lộ thông tin về hạ tầng tổ chức.
- Các môi trường khác nhau có thể cần truststore khác nhau.

Có thể chọn file TrustStore ở build time bằng system property javax.net.ssl.trustStore. Nếu muốn thay TrustStore ở runtime, cấu hình các system properties javax.net.ssl.trustStore* và bảo đảm file TrustStore tồn tại, có thể đọc được trong runtime filesystem.

Khi một trong các property runtime như javax.net.ssl.trustStoreType, javax.net.ssl.trustStoreProvider hoặc javax.net.ssl.trustStorePassword được đặt, GraalVM cũng yêu cầu javax.net.ssl.trustStore trỏ tới file có thể truy cập. Nếu không, runtime có thể ném UnsupportedFeatureError.

TrustStore chứa certificate công khai, không đồng nghĩa với private key. Không nhúng private key hoặc password của keystore vào image. Nếu cần mTLS, cấp private key/keystore qua secret mount hoặc secret manager lúc chạy.

## 9. Build trong môi trường không chứa production secret

GraalVM khuyến nghị chạy Native Image builder trong môi trường build chuyên biệt, chẳng hạn container, không chứa dữ liệu nhạy cảm ngay từ đầu.

Một pipeline an toàn nên:

1. Dùng runner/build container riêng cho native build.
2. Không đưa production API token, database password hoặc private key vào environment của job build.
3. Nếu cần credential để tải dependency, chỉ cấp trong bước fetch dependency và thu hồi khỏi environment trước khi chạy Native Image.
4. Không truyền secret qua -D argument hoặc command line nếu công cụ có thể ghi lại arguments trong log.
5. Không để secret trong file properties được đóng gói, resource folder hoặc Docker build context.
6. Không upload build log, heap report hoặc intermediate files có thể chứa secret lên nơi công khai.
7. Dùng artifact repository và release storage có quyền truy cập giới hạn.

Một container builder không tự động an toàn nếu nó được truyền toàn bộ CI environment hoặc mount thư mục chứa secret. Điều quan trọng là tiến trình Native Image không được nhìn thấy production secret trong lúc build.

### Tách credential build và credential runtime

Credential dùng để tải artifact từ Maven repository là credential build. Token gọi payment service hoặc database là credential runtime. Hai loại này cần scope, thời hạn và quyền khác nhau.

Nếu builder cần truy cập private dependency repository, hãy dùng token chỉ có quyền đọc package, thời hạn ngắn và chỉ tồn tại trong bước tải dependency. Không tái sử dụng token đó làm credential của ứng dụng.

## 10. Phát hiện class khởi tạo sớm và kiểm tra image heap

### In class initialization report

GraalVM cung cấp option diagnostic để theo dõi class initialization:

~~~bash
native-image \
  -H:+PrintClassInitialization \
  -cp target/classes \
  com.example.Application
~~~

Báo cáo giúp xác định class nào được khởi tạo ở build time hoặc runtime và nguyên nhân/chính sách liên quan. Dùng nó để tìm class nhạy cảm xuất hiện trong nhóm build-time initialized.

Đây là diagnostics cho class initialization, không phải công cụ tự động phát hiện mọi secret trong binary. Hãy kết hợp với review source code, build environment và kiểm thử runtime.

### Native Image Build Report

Trên GraalVM edition hỗ trợ Build Report, có thể thêm:

~~~bash
native-image \
  --emit build-report \
  -H:+PrintClassInitialization \
  -cp target/classes \
  com.example.Application
~~~

Build Report có phần Image Heap, cho phép xem object type, số lượng và dung lượng; có thể tìm class cụ thể để kiểm tra instance có nằm trong image heap không. Phần Resources giúp kiểm tra file nào đã được nhúng. Build Report không hiển thị nội dung mọi field, vì vậy nó không chứng minh binary không chứa secret.

Build Report không có trong GraalVM Community Edition. Với edition không hỗ trợ report, dùng class initialization diagnostics, build output và quy trình kiểm thử riêng.

### Kiểm tra nội dung binary

Không dựa vào một lệnh strings để kết luận artifact sạch. Secret có thể được mã hóa, chia nhỏ, nén hoặc lưu trong object representation khác. Ngược lại, một chuỗi xuất hiện trong binary cũng chưa chắc là credential đang hoạt động.

Có thể dùng tìm kiếm chuỗi như một lớp kiểm tra phụ với giá trị marker giả trong môi trường lab, nhưng kiểm soát nguồn dữ liệu và class initialization mới là biện pháp chính.

## 11. Quy trình audit một native build

Khi review một artifact có nguy cơ chứa dữ liệu build-time, đi theo trình tự:

| Bước | Cần xác minh | Bằng chứng |
| --- | --- | --- |
| 1. Review source | Static initializer, static field và callback build-time có đọc secret không? | Code review, grep các API truy cập environment/file/network |
| 2. Review build environment | Native Image process có nhìn thấy production secret không? | CI environment allowlist, container mounts, job permissions |
| 3. Review class initialization | Class nhạy cảm có được khởi tạo tại build time không? | -H:+PrintClassInitialization |
| 4. Review image heap | Có instance của class chứa dữ liệu nhạy cảm không? | Build Report Image Heap nếu edition hỗ trợ |
| 5. Review resources | Secret file, private config hoặc truststore nào được nhúng? | Build Report Resources, embedded resource metadata |
| 6. Runtime test | Runtime secret có được nạp theo môi trường triển khai không? | Test với hai giá trị marker khác nhau |
| 7. Artifact review | Artifact, log và intermediate có bị public hoặc chia sẻ quá rộng không? | Access policy, checksum, retention và provenance |

Nếu phát hiện credential thật trong image, hãy coi credential đó đã bị lộ. Thu hồi/rotate credential, build lại binary từ môi trường sạch và đánh giá các artifact/log đã được phân phối.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Native binary vẫn dùng token của CI sau khi deploy | Static field đã được snapshot ở build time | Chuyển secret sang runtime configuration và runtime initialization |
| Thay environment variable khi chạy nhưng giá trị không đổi | Class đã được khởi tạo trước và static field đã nằm trong image heap | Kiểm tra class initialization report và dùng --initialize-at-run-time cho class phù hợp |
| Native build lỗi khi chuyển class sang runtime initialization | Instance của class vẫn được tạo trong build-time path hoặc hierarchy có xung đột | Tìm initializer/callback tạo instance; điều chỉnh class policy và dependency |
| Profile production không bật đúng bean | Spring AOT đã đánh giá profile/condition ở build time | Chọn profile lúc AOT processing và thiết kế bean graph phù hợp |
| TrustStore trên runtime khác với dự kiến | Native Image đã capture TrustStore của build host | Cấu hình TrustStore runtime và mount file tương ứng |
| Runtime báo UnsupportedFeatureError khi đặt truststore property | Thiếu file TrustStore runtime hoặc path không truy cập được | Đặt javax.net.ssl.trustStore trỏ tới file tồn tại |
| Secret không tìm thấy trong output build | Secret đã bị nén/mã hóa hoặc không nằm ở dạng chuỗi dễ tìm | Không dựa vào strings; kiểm tra source, class initialization và build environment |
| Build report không có Image Heap tab | Edition không hỗ trợ Build Report | Dùng diagnostics và công cụ phù hợp với GraalVM edition |

## 13. Bài thực hành: chứng minh dữ liệu build-time khác runtime

Mục tiêu là tạo một class demo đọc system property trong static initializer, sau đó quan sát sự khác biệt giữa build-time initialization và runtime initialization. Chỉ dùng marker giả, không dùng credential thật.

### Phần A — tạo class demo

Dùng class BuildSnapshot ở mục 3. Build class bằng Maven hoặc Gradle để có file class trong output directory.

### Phần B — build với build-time initialization

~~~bash
native-image \
  --initialize-at-build-time=com.example.security.BuildSnapshot \
  -Ddemo.marker=build-value \
  -cp target/classes \
  com.example.Application
~~~

Chạy:

~~~bash
./application -Ddemo.marker=runtime-value
~~~

Ghi lại output. Giá trị vẫn là build-value vì static field được tạo ở build time.

### Phần C — build với runtime initialization

Xóa executable cũ hoặc dùng tên output khác, sau đó build lại:

~~~bash
native-image \
  --initialize-at-run-time=com.example.security.BuildSnapshot \
  -cp target/classes \
  com.example.Application
~~~

Chạy với giá trị runtime:

~~~bash
./application -Ddemo.marker=runtime-value
~~~

Lần này output là runtime-value, vì class initializer được chạy khi executable sử dụng class ở runtime.

### Phần D — áp dụng vào Spring Boot

1. Tạo một ConfigurationProperties record chứa endpoint và API token.
2. Inject properties vào service bằng constructor.
3. Cấp token qua environment variable hoặc config tree lúc chạy.
4. Xác nhận không có static field đọc token.
5. Tạo một class demo riêng có static initializer đọc marker để kiểm tra class initialization diagnostics.
6. Build native với -H:+PrintClassInitialization.
7. Nếu GraalVM edition hỗ trợ, thêm --emit build-report và review Image Heap/Resources.
8. Chạy cùng binary trong hai môi trường với hai marker khác nhau và xác nhận cấu hình runtime được nạp theo môi trường.
9. Review CI job để bảo đảm production secret không có mặt trong native-image process.

### Câu hỏi tự kiểm tra

1. Image heap chứa những loại object nào?
2. Vì sao static field được gán trong build-time initializer có thể nằm trong executable?
3. Load class khác initialize class như thế nào?
4. --initialize-at-build-time có thể làm lộ dữ liệu nào?
5. Vì sao không phải mọi object tạm thời được tạo trong build đều được giữ trong image heap?
6. Spring AOT khác GraalVM build-time class initialization ở điểm nào?
7. Vì sao property ảnh hưởng @ConditionalOnProperty cần được quyết định ở build time?
8. Khi nào nên dùng --initialize-at-run-time?
9. Vì sao cần tránh static final field chứa API token đọc từ environment?
10. TrustStore của host build được xử lý như thế nào trong Native Image?
11. -H:+PrintClassInitialization và Build Report giúp điều tra những gì?
12. Vì sao không thể dùng strings để chứng minh một native binary không chứa secret?

**Tiêu chí đạt:** giải thích được cách Native Image thực thi static initializer và lưu state vào image heap; phân biệt Spring AOT với GraalVM class initialization; nhận diện được secret hoặc dữ liệu theo môi trường có nguy cơ bị snapshot; chuyển class nhạy cảm sang runtime initialization khi cần; nạp secret qua runtime configuration/secret mount; kiểm tra class initialization, image heap và resources; đồng thời xây dựng được quy trình native build không tiếp xúc với production secret.

## Tài liệu chính thức

- GraalVM — Security Considerations in Native Image: https://www.graalvm.org/latest/security-guide/native-image/
- GraalVM — Native Image Basics: https://www.graalvm.org/latest/reference-manual/native-image/basics/
- GraalVM — Specify Class Initialization Explicitly: https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/
- GraalVM — Class Initialization in Native Image: https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/ClassInitialization/
- GraalVM — Certificate Management in Native Image: https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/CertificateManagement/
- GraalVM — Native Image Build Report: https://www.graalvm.org/latest/reference-manual/native-image/overview/build-report/
- Spring Boot — Ahead-of-Time Processing With the JVM: https://docs.spring.io/spring-boot/reference/packaging/aot.html
- Spring Boot — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/how-to/aot.html
- Spring Framework — Ahead-of-Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html

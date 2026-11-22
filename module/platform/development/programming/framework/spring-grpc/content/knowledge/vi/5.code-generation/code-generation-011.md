# Quản lý version protoc và plugin trong Spring gRPC

Trong ứng dụng **Spring gRPC**, mã Java được sinh từ Protocol Buffers phụ thuộc vào nhiều thành phần có phiên bản riêng: **`protoc`**, plugin **`protoc-gen-grpc-java`**, thư viện **`protobuf-java`**, các thư viện **grpc-java** và Spring gRPC starter. Nếu chỉ nâng một thành phần mà không kiểm tra các thành phần còn lại, dự án có thể sinh mã thành công nhưng không biên dịch, hoặc biên dịch được nhưng lỗi khi chạy.

Quản lý version tốt nghĩa là xác định rõ **công cụ nào sinh mã**, **runtime nào thực thi mã đó**, **Spring starter quản lý dependency nào**, và cách xác minh phiên bản thực tế mà build đã phân giải. Bài này tập trung vào version alignment và quy trình nâng cấp có kiểm soát cho gRPC Java code generation.

## 1. Phân biệt các thành phần và version

| Thành phần | Vai trò |
| --- | --- |
| `protoc` | Đọc schema, resolve import và gọi generator |
| `protoc-gen-grpc-java` | Sinh service descriptor, server base và client stub |
| `protobuf-java` | Runtime cho message class: builder, parser, serialization |
| `grpc-protobuf` | Marshaller kết nối protobuf message với grpc-java |
| `grpc-stub` | Stub base, `StreamObserver` và API client/server |
| `grpc-api` | Channel, status, metadata, descriptor và API cốt lõi |
| gRPC transport | HTTP/2, kết nối, TLS và thực thi network call |
| Spring gRPC starter | Tích hợp Spring, auto-configuration và dependency management tùy starter |

Hai version generator phải được quản lý riêng:

- `protoc` thường được phân giải từ artifact `com.google.protobuf:protoc`.
- `protoc-gen-grpc-java` thường được phân giải từ artifact `io.grpc:protoc-gen-grpc-java`.

`protobuf-java` là runtime của message class; nó không phải phiên bản protoc. Tương tự, `grpc-stub` là thư viện ứng dụng sử dụng, không phải executable plugin.

## 2. Nguyên tắc version alignment

Quản lý ít nhất ba nhóm version:

1. **Codegen toolchain:** protoc, gRPC Java generator và plugin build điều phối generation.
2. **Java runtime:** protobuf Java runtime, grpc-java API/stub/protobuf và transport.
3. **Spring integration:** Spring Boot/Spring gRPC starter cùng BOM hoặc dependency constraints mà starter cung cấp.

Nguyên tắc thực tế:

- Pin version cụ thể cho `protoc` và `protoc-gen-grpc-java`; không dùng `latest`, version động hoặc snapshot trong build phát hành.
- Dùng một version line grpc-java nhất quán cho `grpc-api`, `grpc-stub`, `grpc-protobuf` và transport, thường thông qua grpc BOM.
- Đảm bảo generated message tương thích với `protobuf-java` runtime. Không dùng runtime cũ hơn mức code được sinh yêu cầu.
- Kiểm tra compatibility guidance của phiên bản generator/runtime khi nâng cấp; đừng giả định mọi version khác nhau đều tương thích chỉ vì Java compile pass.
- Nếu Spring gRPC starter đã quản lý grpc-java hoặc protobuf dependency, ưu tiên version management của starter/BOM; tránh override riêng lẻ mà không có kiểm thử.

**Generator version và runtime version cần được xem xét cùng nhau**, nhưng không phải mọi thành phần phải có cùng số version. Protobuf và grpc-java thuộc hai dòng phát hành độc lập.

## 3. Gradle: khai báo và tập trung version

Cấu hình minh họa trong `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'com.google.protobuf' version '0.9.5'
}

def protobufVersion = '4.30.2'
def grpcVersion = '1.71.0'

dependencies {
    implementation "com.google.protobuf:protobuf-java:$protobufVersion"
    implementation platform("io.grpc:grpc-bom:$grpcVersion")
    implementation 'io.grpc:grpc-protobuf'
    implementation 'io.grpc:grpc-stub'

    // Chỉ thêm transport nếu starter chưa cung cấp/quản lý nó.
    runtimeOnly 'io.grpc:grpc-netty-shaded'
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:$protobufVersion"
    }
    plugins {
        grpc {
            artifact = "io.grpc:protoc-gen-grpc-java:$grpcVersion"
        }
    }
    generateProtoTasks {
        all().configureEach { task ->
            task.plugins {
                grpc {}
            }
        }
    }
}
```

Các version ở đây chỉ là **ví dụ cấu hình**, không phải khuyến nghị phiên bản mới nhất. Khi dùng Spring Boot/Spring gRPC starter, kiểm tra BOM của ứng dụng trước khi thêm grpc BOM hoặc khai báo version trực tiếp. Tránh để hai BOM quản lý cùng artifact theo các version khác nhau mà không hiểu thứ tự ưu tiên.

### 3.1. Dùng version catalog

Với Gradle nhiều module, tập trung version trong `gradle/libs.versions.toml`:

```toml
[versions]
protobuf = "4.30.2"
grpc = "1.71.0"
protobuf-plugin = "0.9.5"

[libraries]
protobuf-java = { module = "com.google.protobuf:protobuf-java", version.ref = "protobuf" }
grpc-bom = { module = "io.grpc:grpc-bom", version.ref = "grpc" }
grpc-protobuf = { module = "io.grpc:grpc-protobuf" }
grpc-stub = { module = "io.grpc:grpc-stub" }

[plugins]
protobuf = { id = "com.google.protobuf", version.ref = "protobuf-plugin" }
```

Version catalog giảm khả năng module client và server dùng toolchain khác nhau ngoài ý muốn. Tuy nhiên, nó **không tự khóa toàn bộ dependency graph**; có thể kết hợp dependency locking nếu cần build tái lập chặt hơn.

### 3.2. Kiểm tra version Gradle thực sự phân giải

Khai báo trong build file chưa chắc là version cuối cùng trên runtime classpath. Dependency khác hoặc BOM khác có thể ảnh hưởng kết quả:

```bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency grpc-stub

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency protobuf-java
```

Đọc kết quả để xác định version được chọn, dependency yêu cầu version khác, BOM/constraint nào quyết định kết quả và có conflict nào được Gradle giải quyết. Nếu generated code lỗi liên kết, kiểm tra cả compile classpath và runtime classpath; hai configuration có thể khác nhau.

## 4. Maven: quản lý version bằng properties và BOM

Trong Maven, dùng properties để tập trung version codegen và runtime:

```xml
<properties>
    <protobuf.version>4.30.2</protobuf.version>
    <grpc.version>1.71.0</grpc.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-bom</artifactId>
            <version>${grpc.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.protobuf</groupId>
        <artifactId>protobuf-java</artifactId>
        <version>${protobuf.version}</version>
    </dependency>
    <dependency>
        <groupId>io.grpc</groupId>
        <artifactId>grpc-protobuf</artifactId>
    </dependency>
    <dependency>
        <groupId>io.grpc</groupId>
        <artifactId>grpc-stub</artifactId>
    </dependency>
</dependencies>
```

Khai báo plugin codegen cũng dùng cùng properties:

```xml
<plugin>
    <groupId>org.xolstice.maven.plugins</groupId>
    <artifactId>protobuf-maven-plugin</artifactId>
    <version>0.6.1</version>
    <configuration>
        <protocArtifact>
            com.google.protobuf:protoc:${protobuf.version}:exe:${os.detected.classifier}
        </protocArtifact>
        <pluginId>grpc-java</pluginId>
        <pluginArtifact>
            io.grpc:protoc-gen-grpc-java:${grpc.version}:exe:${os.detected.classifier}
        </pluginArtifact>
    </configuration>
</plugin>
```

Plugin vẫn cần execution bind vào phase `generate-sources` với goals sinh message và gRPC stub. Nếu Spring Boot parent hoặc Spring gRPC BOM đã quản lý protobuf/grpc-java, hãy dùng version management mà dự án đã chọn thay vì nhập thêm một BOM xung đột.

### 4.1. OS classifier và executable plugin

`protoc` và `protoc-gen-grpc-java` là executable artifacts, nên Maven thường cần classifier theo nền tảng. `os-maven-plugin` cung cấp classifier phù hợp để chọn artifact theo hệ điều hành và kiến trúc.

Nếu build chạy trên Linux CI nhưng developer dùng Windows, cần bảo đảm Maven phân giải binary tương ứng cho từng môi trường. Không commit executable của một hệ điều hành vào build dùng chung và không hardcode đường dẫn tuyệt đối của máy cá nhân.

### 4.2. Kiểm tra dependency tree

```bash
mvn dependency:tree

mvn dependency:tree -Dincludes=io.grpc:grpc-stub,com.google.protobuf:protobuf-java
```

Kiểm tra version hiệu lực của `grpc-api`, `grpc-stub`, `grpc-protobuf`, transport và `protobuf-java`. Nếu một starter kéo version khác, xác định artifact nào quản lý nó trước khi override. Exclusion tùy tiện có thể làm mất thư viện mà starter cần.

## 5. Tương thích giữa generated code và runtime

Generated Java gọi API trong protobuf và grpc-java runtime. Nếu generator tạo source tham chiếu đến method hoặc class không có trong runtime trên classpath, compile hoặc runtime sẽ thất bại.

| Lỗi | Nguyên nhân có thể |
| --- | --- |
| `cannot find symbol` trong generated message | Protobuf runtime thiếu API mà generated code cần, hoặc generator/runtime lệch |
| `NoSuchMethodError` | Runtime thực tế khác API mà class đã biên dịch tham chiếu |
| `NoClassDefFoundError` | Thiếu dependency runtime hoặc dependency bị exclude |
| Lỗi liên quan `javax.annotation.Generated` | Generator dùng annotation API không có trên compile classpath |
| Stub compile được nhưng lỗi khi gọi | grpc-java runtime/transport không đồng bộ hoặc cấu hình runtime sai |
| Plugin không chạy trên CI | Sai OS classifier, executable hoặc artifact repository |

Không thể kết luận mọi lỗi generated code đều do version. Trước khi thay version, xác minh:
1. Schema và import paths có đúng không?
2. Generator nào thực sự được chạy và version nào?
3. Generated output có được tái tạo từ trạng thái sạch không?
4. Compile/runtime classpath đang chứa version nào?
5. Spring starter có áp dụng dependency management hoặc auto-configuration nào?

### Generated code và runtime không nhất thiết cùng version number

Protobuf và grpc-java có lịch phát hành riêng. Không đặt cùng một con số version cho `protobuf-java` và `grpc-stub` chỉ để “đồng bộ”. Hãy dùng version đã được kiểm chứng của từng dòng và tuân theo compatibility guidance tương ứng. Với grpc-java, dùng một grpc BOM/version line nhất quán cho các module grpc-java trong cùng ứng dụng là cách quản lý phổ biến.

## 6. Nâng cấp toolchain có kiểm soát

Không nâng tất cả phiên bản trong một lần nếu không cần thiết. Một quy trình dễ review:

1. **Ghi nhận baseline:** protoc, gRPC plugin, protobuf runtime, grpc-java BOM, Spring Boot/starter và JDK hiện tại.
2. **Xác định mục tiêu nâng:** bảo mật, bug fix, tính năng generator hoặc yêu cầu tương thích.
3. **Kiểm tra release notes/compatibility:** xác định thay đổi breaking và version runtime tối thiểu.
4. **Nâng generator có chủ đích:** pin version mới trong Gradle/Maven, giữ schema không đổi để dễ nhận diện diff.
5. **Clean generation:** xóa output cũ, sinh lại toàn bộ source và xem diff.
6. **Căn chỉnh runtime:** cập nhật protobuf/grpc-java dependencies theo yêu cầu của generated code và Spring starter.
7. **Compile và test:** chạy unit tests, integration tests và kiểm tra một RPC unary/streaming.
8. **Xác minh CI:** chạy trên môi trường sạch, gồm OS/architecture được hỗ trợ.
9. **Ghi nhận thay đổi:** lưu version mới, lý do, kết quả test và lưu ý migration.

Nên tách việc nâng generator khỏi việc thay đổi schema nghiệp vụ. Nếu cùng lúc đổi field, RPC path và plugin, khi test lỗi sẽ khó xác định nguyên nhân.

## 7. Ví dụ kiểm tra sau khi nâng version

Giả sử dự án có service unary `StockService.GetStock` và server-streaming `WatchStock`. Sau khi nâng generator:

```bash
# Gradle
./gradlew clean generateProto compileJava compileTestJava test

# Maven
mvn clean generate-sources compile test
```

Sau build, kiểm tra:
- Có đủ message class và `StockServiceGrpc`.
- Server implementation vẫn override đúng chữ ký generated API.
- Client blocking/async stub vẫn gọi được method.
- Status lỗi được giữ đúng, ví dụ `INVALID_ARGUMENT` hoặc `NOT_FOUND`.
- Streaming có terminal callback đúng và không bị kết thúc ngoài ý muốn.
- TLS, metadata, interceptor và deadline không bị thay đổi do dependency/runtime upgrade.

Một integration test grpc-java đơn giản có thể xác nhận generated stub vẫn gọi được server:

```java
@Test
void generatedStubCallsStockService() {
    StockReply reply = blockingStub.getStock(
            StockRequest.newBuilder()
                    .setSku("BOOK-101")
                    .build());

    assertEquals("BOOK-101", reply.getSku());
}
```

Test giả định `blockingStub` trỏ đến test server đã khởi tạo và `StockReply` được trả về theo hợp đồng. Để kiểm tra version upgrade đầy đủ, cần thêm test lỗi, streaming và Spring application context nếu starter/auto-configuration cũng được nâng.

## 8. Dependency locking và tính tái lập

Pin version trực tiếp giúp tránh version động, nhưng dependency transitive vẫn có thể thay đổi nếu metadata/artifact repository thay đổi hoặc build không khóa resolution. Với Gradle, có thể bật dependency locking:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi cấu hình, tạo/cập nhật lock state bằng task phù hợp của dự án, review file lock và commit khi tổ chức yêu cầu. Không cập nhật lock file âm thầm cùng với thay đổi không liên quan.

Với Maven, properties và BOM giúp tập trung version; Maven Enforcer Plugin có thể kiểm tra dependency convergence hoặc version policy. Rule convergence cần theo chuẩn tổ chức vì một số dependency có thể được thiết kế để dùng nhiều version trong các module tách biệt.

Ngoài dependency, pin Gradle Wrapper/Maven Wrapper và JDK toolchain. Build có version dependency rõ ràng nhưng chạy bằng build tool/JDK tùy ý vẫn có thể cho kết quả khác.

## 9. Checklist chẩn đoán version mismatch

| Quan sát | Kiểm tra đầu tiên |
| --- | --- |
| Chỉ message code lỗi | `protoc` và `protobuf-java`, generated output cũ hay mới |
| Chỉ `*Grpc.java` lỗi | `protoc-gen-grpc-java` và grpc-java API/stub runtime |
| Compile pass, runtime fail | Runtime dependency graph, transport và classpath khi chạy |
| Local pass, CI fail | OS classifier, JDK, wrapper, artifact repository |
| Spring context không khởi động | Starter/BOM, auto-configuration và dependency conflict |
| Sau nâng plugin có diff lớn | Version generator, options và schema inputs |
| `NoSuchMethodError` | Xác định JAR thực tế cung cấp class/method tại runtime |
| `UNAVAILABLE` sau upgrade | Transport, TLS, target và server readiness; không mặc định là lỗi codegen |

Luôn lấy bằng chứng từ dependency graph và log build. Đừng chỉ nhìn version khai báo trong một file vì version cuối cùng có thể được chọn bởi BOM, constraint, parent POM hoặc dependency khác.

## 10. Bài tập thực hành

1. Ghi lại version `protoc`, `protoc-gen-grpc-java`, `protobuf-java` và các grpc-java artifacts của một dự án.
2. Cố ý khai báo grpc-java artifacts lệch version trong bản thực hành; dùng Gradle `dependencyInsight` hoặc Maven `dependency:tree` để tìm nguồn conflict.
3. Chuyển các version về một grpc BOM thống nhất; chạy compile và integration test.
4. Nâng riêng `protoc-gen-grpc-java` nhưng giữ nguyên schema; clean generation và phân loại generated diff.
5. Nâng protobuf compiler/runtime theo một tổ hợp tương thích; chạy test parse/serialize cho message.
6. Kiểm tra Maven executable classifier trên Windows và Linux CI; xác nhận plugin binary được phân giải đúng nền tảng.
7. Bật Gradle dependency locking hoặc quy tắc Maven convergence; xác nhận build tái lập từ checkout sạch.
8. Viết test unary và server-streaming sau upgrade; kiểm tra success, status lỗi, deadline và terminal callback.

### Ghi nhớ

**Quản lý version protoc và plugin là quản lý một toolchain gồm generator và runtime.** Pin `protoc` cùng `protoc-gen-grpc-java`; căn chỉnh `protobuf-java` và các grpc-java artifacts theo compatibility guidance và BOM/starter của Spring; kiểm tra version thực tế qua dependency graph; nâng cấp từng bước với clean generation, diff, compile và integration tests. Version được khai báo chỉ là ý định cấu hình—version được build phân giải và sử dụng mới là điều cần xác minh.

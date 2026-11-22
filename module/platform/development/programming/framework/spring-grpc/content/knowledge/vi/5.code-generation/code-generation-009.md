# Lặp lại code generation có xác định trong Spring gRPC

Trong một dự án **Spring gRPC**, cùng một hợp đồng Protocol Buffers cần tạo ra cùng một bộ Java source khi build lại với cùng đầu vào và cùng bộ công cụ. Tính chất này gọi là **deterministic code generation**: nếu schema, import graph, tùy chọn generator và phiên bản công cụ không đổi, generated source nên ổn định và có thể so sánh theo từng byte.

Điều này giúp nhóm tránh tình trạng hai developer sinh ra hai bộ `StockServiceGrpc.java` khác nhau dù cùng làm việc trên một hợp đồng; đồng thời giúp nhận diện thay đổi nào đến từ schema và thay đổi nào đến từ nâng cấp generator.

Bài học tập trung vào việc làm cho quá trình sinh mã **lặp lại có xác định**: kiểm soát đầu vào, pin toolchain, giữ import path ổn định, tái sinh từ output sạch và kiểm tra kết quả bằng diff/hash. Nội dung áp dụng cho gRPC Java codegen trong cả Gradle và Maven.

## 1. Deterministic code generation nghĩa là gì?

Một lần code generation nhận các đầu vào chính:

- Tệp `.proto` và toàn bộ schema được import.
- Proto source roots và cách phân giải import.
- Phiên bản `protoc`, `protoc-gen-grpc-java` và generator khác nếu có.
- Các tùy chọn Java/gRPC generator và cấu hình output.
- Môi trường thực thi có liên quan đến plugin, gồm binary theo hệ điều hành/kiến trúc và build tool.

Nếu các đầu vào đó giống nhau, generated source nên giống nhau theo từng tệp, lý tưởng là **byte-for-byte**. Có thể kiểm tra bằng cách sinh hai lần từ trạng thái sạch rồi so sánh output.

Cần phân biệt ba mức:

| Mức | Điều được kiểm tra | Ví dụ |
| --- | --- | --- |
| Deterministic codegen | Cùng đầu vào và generator tạo cùng source | Hai lần sinh `StockRequest.java` có cùng hash |
| Reproducible build | Cùng source/toolchain tạo artifact build giống nhau theo tiêu chí đã định | JAR có cùng nội dung và metadata |
| Runtime consistency | Client/server thực thi hợp đồng và chính sách tương thích | RPC trả status đúng theo điều kiện nghiệp vụ |

**Code generation ổn định không tự động làm JAR reproducible hoặc runtime giống nhau.** JAR còn phụ thuộc compiler, resource processing, timestamps, packaging và plugin khác; runtime còn phụ thuộc dữ liệu, network, TLS, deadline và trạng thái dịch vụ.

## 2. Nguồn gây khác biệt giữa hai lần sinh mã

| Nguồn thay đổi | Biểu hiện | Cách kiểm soát |
| --- | --- | --- |
| `protoc` hoặc gRPC plugin version khác | API, annotation, comment hoặc cấu trúc source thay đổi | Pin chính xác version generator |
| Proto source root khác | Đường dẫn logic hoặc generated comment thay đổi | Chuẩn hóa root và working directory |
| Import path khác | Resolve sang schema khác hoặc cùng schema qua hai tên | Dùng canonical import path, tránh root chồng lấn |
| Proto dependency không cố định | Cùng import nhưng nội dung schema thay đổi | Dùng artifact version bất biến |
| Generator options khác | Java package, outer class hoặc output layout khác | Quản lý options trong build configuration |
| Plugin binary theo OS/architecture khác | Có thể tạo khác biệt nếu binary không tương đương | Pin artifact và kiểm tra CI matrix |
| Output cũ còn sót | File đã xóa trong proto vẫn còn ở generated directory | Xóa output trước lần xác minh sạch |
| Sửa generated source thủ công | Lần sinh sau ghi đè hoặc diff khó giải thích | Chỉ sửa .proto hoặc mã ứng dụng |
| Dependency động | Build hôm nay và ngày mai dùng generator khác | Không dùng version động/snapshot cho toolchain phát hành |

Generated Java đôi khi chứa thông tin về phiên bản generator, tên source hoặc annotation. Vì vậy, nâng cấp plugin có thể tạo diff dù schema không đổi. Đó là thay đổi do **toolchain**, không nhất thiết là thay đổi API protobuf.

## 3. Khóa đầu vào của code generation

### 3.1. Quản lý schema và import

Đặt schema trong source control và thống nhất proto root. Ví dụ:

```text
src/main/proto/
├── common/v1/money.proto
└── orders/v1/order.proto
```

Trong `order.proto`, mọi module dùng cùng một import path:

```proto
import "common/v1/money.proto";
```

Không để máy developer import từ thư mục cục bộ ngoài repository trong khi CI import từ một bản khác. Nếu schema đến từ artifact bên ngoài, pin version cụ thể và bảo đảm artifact không bị thay thế nội dung dưới cùng version.

### 3.2. Pin generator versions

Với Gradle, khai báo version rõ ràng cho plugin, protoc và gRPC plugin:

```groovy
plugins {
    id 'java'
    id 'com.google.protobuf' version '0.9.5'
}

def protobufVersion = '4.30.2'
def grpcVersion = '1.71.0'

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
        ofSourceSet('main').configureEach { task ->
            task.plugins {
                grpc {}
            }
        }
    }
}
```

Với Maven, pin plugin và executable artifacts trong `pom.xml`:

```xml
<properties>
    <protobuf.version>4.30.2</protobuf.version>
    <grpc.version>1.71.0</grpc.version>
</properties>

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

Các version trong ví dụ là minh họa. Dự án cần chọn bộ version đã được xác nhận tương thích với protobuf runtime, grpc-java runtime và Spring gRPC starter. **Pin generator** và **pin runtime** là hai việc liên quan nhưng khác nhau: generator tạo source, runtime cung cấp API mà source gọi tới.

Không dùng version động hoặc snapshot cho toolchain phát hành. Gradle Wrapper và Maven Wrapper cũng nên được commit để các máy dùng cùng build tool version.

### 3.3. Ổn định options và đường dẫn

Giữ các tùy chọn schema như `java_package`, `java_multiple_files` và `java_outer_classname` trong source control. Không phụ thuộc vào biến môi trường hoặc đường dẫn tuyệt đối chỉ tồn tại trên máy cá nhân.

Thống nhất:

- Một proto root chính cho main sources.
- Một canonical import path cho mỗi schema.
- Các thư mục dependency được khai báo rõ trong build.
- Generator options được cấu hình trong Gradle/Maven, không nhập thủ công lúc chạy.

## 4. Làm cho Gradle sinh mã ổn định

Gradle protobuf plugin quản lý generation qua task graph. Cấu hình gọn cho main source set:

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
        ofSourceSet('main').configureEach { task ->
            task.plugins {
                grpc {}
            }
        }
    }
}
```

Cấu hình giới hạn gRPC plugin cho proto task của `main`. Nếu test source set cũng cần stub, cấu hình rõ ràng cho `test` hoặc dùng `all().configureEach`. Tránh áp dụng plugin cho source set không cần thiết vì điều đó làm tăng output và phạm vi thay đổi.

Lệnh kiểm tra sạch:

```bash
./gradlew --version
./gradlew clean generateProto
./gradlew compileJava
```

`clean` loại output cũ để lần generation không dựa vào file còn sót. `generateProto` sinh message và gRPC source; `compileJava` xác nhận compiler nhìn thấy chúng. Với dự án dùng wrapper, gọi `./gradlew` thay vì Gradle cài toàn cục không được kiểm soát.

## 5. Làm cho Maven sinh mã ổn định

Maven cần pin protobuf plugin, protoc artifact, gRPC plugin artifact và OS classifier plugin. Hai goals thường được gắn ở phase `generate-sources`:

```xml
<execution>
    <id>generate-protobuf-and-grpc</id>
    <phase>generate-sources</phase>
    <goals>
        <goal>compile</goal>
        <goal>compile-custom</goal>
    </goals>
</execution>
```

Khi xác minh từ đầu:

```bash
mvn --version
mvn clean generate-sources
mvn compile
```

`mvn clean` xóa `target`, buộc generation tạo output mới. `generate-sources` gọi Java generator và custom gRPC plugin theo execution đã cấu hình; `compile` xác nhận generated roots được Maven compiler nhận.

Dùng Maven Wrapper (`mvnw`/`mvnw.cmd`) và pin version trong wrapper properties. Nếu dùng `os-maven-plugin` để chọn binary, kiểm soát version extension và classifier mà CI phân giải.

## 6. So sánh hai lần generation

Một kiểm tra trực tiếp là chạy generation hai lần từ trạng thái sạch, lưu bản đầu ra thứ nhất ra thư mục tạm **bên ngoài build output**, rồi so sánh với lần thứ hai.

Ví dụ cho Gradle trên shell kiểu Unix:

```bash
set -eu

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

./gradlew clean generateProto
cp -R build/generated/source/proto/main "$tmp/first"

./gradlew clean generateProto
diff -ru "$tmp/first" build/generated/source/proto/main
```

Nếu `diff` không in khác biệt và exit code bằng 0, hai lần generation trong cùng môi trường tạo cùng cây file. Nếu có khác biệt, giữ lại hai bản output và tìm nguyên nhân trước khi cập nhật baseline.

Với Maven, dùng output root của protobuf Maven plugin:

```bash
set -eu

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mvn clean generate-sources
cp -R target/generated-sources/protobuf "$tmp/first"

mvn clean generate-sources
diff -ru "$tmp/first" target/generated-sources/protobuf
```

Đường dẫn có thể thay đổi nếu plugin hoặc project tùy chỉnh output. Hãy dùng đúng generated roots thực tế. Trên Windows có thể thực hiện cùng quy trình bằng PowerShell, so sánh danh sách đường dẫn tương đối cùng SHA-256 của từng file.

**Kiểm tra này chứng minh repeatability trong cùng môi trường**, chưa chứng minh mọi hệ điều hành hoặc mọi JDK đều tạo cùng output. Để kiểm tra cross-platform, chạy cùng bước trên CI matrix và so sánh generated source artifacts giữa các môi trường được hỗ trợ.

## 7. Dùng hash để phát hiện drift

Khi cần lưu bằng chứng trong CI, có thể tạo manifest chứa đường dẫn tương đối và SHA-256 cho từng generated source:

```bash
find build/generated/source/proto/main -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > build/codegen-manifest.sha256
```

Manifest giúp xác định tệp nào thay đổi giữa hai lần generation và nội dung mỗi tệp có cùng hash hay không. Dùng đường dẫn tương đối thay cho absolute path để manifest không phụ thuộc workspace.

Khi so sánh hai manifest, bảo đảm cùng cách chuẩn hóa đường dẫn và line endings. Nếu khác biệt chỉ là line endings, hãy xác định nguyên nhân và thống nhất policy; không bỏ qua khác biệt để làm test pass.

Manifest có thể được lưu như artifact CI, nhưng không nhất thiết phải commit mọi generated file hoặc hash vào repository. Nó là bằng chứng kiểm tra, không thay thế schema và build configuration.

## 8. Phân tích diff khi nâng cấp generator

Khi nâng `protoc` hoặc `protoc-gen-grpc-java`, generated source có thể thay đổi dù `.proto` không đổi. Quy trình nâng cấp an toàn:

1. Ghi nhận version cũ của protoc, gRPC plugin và runtime.
2. Chạy clean generation bằng toolchain cũ và lưu output/manifest.
3. Chỉ thay đổi version generator cần nâng trong một thay đổi có chủ đích.
4. Chạy clean generation bằng toolchain mới.
5. So sánh diff; phân loại thay đổi do annotation, API, comment, package hoặc output layout.
6. Biên dịch và chạy integration tests với runtime tương thích.
7. Cập nhật version lock/BOM cùng ghi chú phát hành nếu API generated thay đổi.

Không gộp việc đổi schema, generator và runtime vào một thay đổi lớn nếu không cần thiết; tách nguyên nhân giúp reviewer hiểu diff và rollback dễ hơn.

| Dạng diff | Cần kiểm tra |
| --- | --- |
| Chỉ thay generated comment/version marker | Xác nhận do generator version và có chủ đích |
| Thay chữ ký method/stub API | Kiểm tra source compatibility và client/server code |
| Thay package hoặc tên lớp | Kiểm tra `java_package`, options và import |
| Thay method descriptor/RPC path | Kiểm tra protobuf package, service/method và wire compatibility |
| File cũ còn tồn tại sau khi xóa message | Output cũ chưa được clean hoặc task không quản lý output đầy đủ |
| Nhiều file đổi ngoài dự kiến | Kiểm tra generator options, import roots và dependency versions |

## 9. CI: xác minh generation từ môi trường sạch

Một job CI dành cho code generation nên:

- Dùng JDK và build tool version đã được chỉ định.
- Phân giải protoc/plugin từ artifact version cụ thể.
- Checkout toàn bộ proto dependencies cần thiết.
- Chạy clean generation và compilation.
- Chạy lại generation để so sánh output nếu dự án yêu cầu kiểm chứng deterministic.
- Chạy unit/integration tests để kiểm tra generated stub hoạt động với server.
- Lưu log, manifest hoặc generated output diff khi thất bại.

Ví dụ lệnh pipeline:

```bash
# Gradle
./gradlew --no-daemon clean generateProto compileJava test

# Maven
./mvnw -B clean generate-sources compile test
```

Đây là lệnh minh họa; CI thực tế có thể dùng `build` hoặc `verify` và các profile tương ứng. Nếu cần so sánh hai lần sinh, thêm bước lặp sạch và diff ở mục 6.

Không dựa vào generated output còn sót từ cache/workspace của job trước để kết luận generation ổn định. Cache có thể dùng để tăng tốc, nhưng cần có đường kiểm tra clean build độc lập.

## 10. Deterministic codegen không giải quyết điều gì?

Code generation ổn định chỉ bảo đảm **source output** dưới một tập đầu vào/toolchain đã xác định. Nó không bảo đảm:

- Client cũ tương thích với server mới sau khi thay đổi hợp đồng.
- Mọi RPC luôn có cùng response khi dữ liệu hoặc trạng thái hệ thống khác nhau.
- Deadline, retry, cancellation, TLS hay interceptor được cấu hình đúng.
- JAR có timestamp và metadata giống nhau giữa mọi build.
- Plugin tùy chỉnh không phụ thuộc môi trường nếu nó tự đọc thời gian, biến môi trường hoặc file ngoài khai báo.

Với plugin generator do nhóm tự viết, tránh đưa dữ liệu không xác định vào output như timestamp hiện tại, absolute workspace path, random identifier hoặc thứ tự duyệt file không ổn định. Nếu thông tin đó cần cho debugging, đặt trong log hoặc build metadata riêng thay vì source được sinh.

## 11. Checklist xử lý khi output không ổn định

| Dấu hiệu | Câu hỏi chẩn đoán |
| --- | --- |
| Cùng schema nhưng source khác giữa máy | Protoc/plugin version và binary classifier có giống nhau không? |
| CI sinh thêm hoặc mất file | Proto inputs/import roots có giống nhau không? Output cũ có được clean không? |
| Generated comment chứa path khác | Build đang dùng root/working directory nào? |
| Diff xuất hiện sau nâng version | Generator có đổi API hoặc marker không? |
| Build local pass, CI fail | CI có lấy đủ proto dependency và artifact không? |
| Hash thay đổi nhưng nội dung nhìn giống | Có khác line endings, encoding hoặc file ordering không? |
| Build lặp lại vẫn tạo output cũ | Task inputs/outputs hoặc lifecycle binding có chính xác không? |
| Generated source ổn định nhưng RPC lỗi | Lỗi thuộc runtime, service registration, channel hay contract compatibility? |

Khi phát hiện khác biệt, lưu cả hai bộ generated output, manifest, tool versions và command/task đã chạy. Đừng chỉ chạy lại cho đến khi diff biến mất; cần xác định **đầu vào hoặc bước nào tạo ra khác biệt**.

## 12. Bài tập thực hành

1. Pin version protoc và `protoc-gen-grpc-java` trong Gradle; chạy `clean generateProto` hai lần và so sánh hai cây output.
2. Thực hiện quy trình tương tự với Maven `clean generate-sources` và `diff -ru`.
3. Thay đổi một comment trong `.proto`, sinh lại và quan sát file nào đổi; giải thích vì sao schema source là input của generator.
4. Thay đổi `java_package` rồi so sánh generated paths và Java imports. Phân biệt thay đổi package Java với thay đổi protobuf RPC path.
5. Nâng riêng gRPC generator version, lưu diff và xác định phần nào là marker/tooling change, phần nào ảnh hưởng API.
6. Chạy cùng generation trên hai môi trường CI được hỗ trợ, tạo SHA-256 manifest và so sánh.
7. Tạo import root trỏ đến schema local bên ngoài repository, quan sát vì sao CI sạch không tái tạo được; thay bằng dependency được quản lý.
8. Với custom generator, thử đưa timestamp hiện tại vào comment output, nhận diện nguyên nhân không deterministic rồi loại bỏ dữ liệu biến thiên.
9. Viết CI job chạy clean generation, compile, integration test và một lần repeat/diff; lưu manifest khi có khác biệt.

### Ghi nhớ

**Lặp lại code generation có xác định nghĩa là cùng schema, import graph, options và generator toolchain phải tạo ra cùng generated source.** Hãy pin phiên bản protoc/plugin, chuẩn hóa proto roots và import paths, giữ dependency bất biến, không sửa generated output và kiểm tra hai lần sinh từ trạng thái sạch bằng diff hoặc hash. Gradle và Maven đều hỗ trợ quy trình này; CI cần tái tạo từ source độc lập với workspace cũ. Tính deterministic của generated source là nền tảng để review thay đổi và build đáng tin cậy, nhưng vẫn cần kiểm thử runtime và tương thích hợp đồng riêng.

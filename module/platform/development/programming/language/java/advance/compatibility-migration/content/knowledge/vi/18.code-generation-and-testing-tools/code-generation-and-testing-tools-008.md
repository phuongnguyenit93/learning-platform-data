# Kiểm tra lại nguồn và class được sinh khi thay phiên bản công cụ

Trong một dự án Java, không phải mọi file `.java` hoặc `.class` đều do lập trình viên viết trực tiếp. Annotation processor sinh mapper, builder hoặc metamodel; công cụ OpenAPI/Protobuf/JAXB sinh client và data models từ schema; bytecode enhancer sửa class sau khi compile; Mockito, ORM và AOP có thể sinh proxy khi runtime. Khi nâng phiên bản những công cụ này để hỗ trợ JDK mới, **artifact được tạo ra có thể thay đổi dù mã nghiệp vụ giữ nguyên**.

Rủi ro không chỉ là build không thành công. Một generator có thể thay method signature, annotation, constructor, visibility, mapping null, enum conversion hoặc định dạng dữ liệu mà không làm lộ lỗi compile tại module hiện tại. Binary client đã phát hành có thể gặp `NoSuchMethodError`; integration tests có thể thất bại do proxy hoặc reflection; hoặc serializer tạo output khác làm consumer cũ không còn đọc an toàn.

Bài học hướng dẫn kiểm tra lại **generated source, class file, JAR cuối cùng và hành vi runtime** khi thay JDK, compiler, generator, annotation processor, build plugin hoặc công cụ sinh/biến đổi bytecode. Trọng tâm là xác định output thực tế, so sánh có kiểm soát và kiểm thử hợp đồng với consumer.

## 1. Sinh mã có nhiều loại và nhiều giai đoạn

~~~text
Source / annotations / schema / templates
                  |
     +------------+-------------+
     |                          |
Annotation processor      Schema generator
(MapStruct, QueryDSL)     (OpenAPI, XJC, protoc)
     |                          |
     +----------+---------------+
                |
                v
          Generated .java
                |
                v
           javac / compiler
                |
                v
             .class
                |
         +------+------+
         |             |
    Enhancer/agent   Packaging
         |             |
         +------+------+
                |
                v
         Artifact JAR/WAR
                |
                v
          JVM at runtime
                |
                v
       Proxy / class generation
~~~

| Nguồn sinh mã | Ví dụ | Đầu ra cần kiểm tra |
|---|---|---|
| Annotation processing | MapStruct, Dagger, QueryDSL, JPA metamodel | Generated `.java`, resources, compiled `.class` |
| Compiler/AST transforms | Lombok, compiler extensions | Compiled class, public members, metadata |
| Schema-driven generation | Protobuf/gRPC, OpenAPI, JAXB/XJC, WSDL | API source, wire serialization, DTOs |
| Bytecode libraries | ASM, Byte Buddy, CGLIB | Bytecode, class hierarchy, runtime proxies |
| Post-compile enhancement | ORM enhancement, weaving, instrumentation | `.class` sau enhancement |
| Packaging transforms | Shading, relocation, obfuscation | Tên class/package và JAR đã phát hành |
| Test runtime generation | Mockito inline/subclass mocks, agents | Runtime-generated classes và test behavior |

**Không nên chỉ kiểm tra thư mục generated source.** Một số công cụ không tạo `.java` mà tạo hoặc sửa trực tiếp class file; một số chỉ sinh class trong JVM khi test/ứng dụng đang chạy.

## 2. Vì sao đổi phiên bản công cụ có thể làm ứng dụng khác đi?

Một phiên bản mới có thể:

- Đổi tên package, class, method, field hoặc constructor được sinh.
- Thay parameter/return type, generic signature hoặc method descriptor.
- Thu hẹp quyền truy cập hoặc thêm `final`, `static`, `synthetic`, bridge method.
- Sinh bytecode cho JDK mới hơn mức runtime còn hỗ trợ.
- Thay null handling, collection copying, enum mapping hoặc date/time conversion.
- Thay annotation/metadata mà DI, ORM, serialization hoặc reflection phụ thuộc.
- Đổi strategy tạo proxy, subclass hay cách gắn Java agent.
- Đổi mapping giữa schema và Java model, ví dụ presence của field hoặc unknown enum.
- Thêm runtime dependency, class helper hoặc class loader requirement.
- Sinh file có timestamp, absolute path, thứ tự không ổn định gây vấn đề tái lập.

### 2.1. Ví dụ: không đổi API nhưng đổi nghĩa của mapper

Generated implementation bản cũ:

~~~java
public ProductDto convert(Product product) {
    if (product == null) {
        return null;
    }
    ProductDto dto = new ProductDto();
    dto.setName(product.getName());
    return dto;
}
~~~

Generated implementation bản mới:

~~~java
public ProductDto convert(Product product) {
    ProductDto dto = new ProductDto();
    if (product != null) {
        dto.setName(product.getName());
    }
    return dto;
}
~~~

Ví dụ chỉ minh họa hai chính sách null handling, không phải mô tả một release cụ thể. Chữ ký public của `convert(Product)` không đổi, nhưng kết quả khi input `null` khác nhau. Không có lỗi linkage để cảnh báo.

### 2.2. Ví dụ: API của generated class đổi

Giả sử binary consumer cũ gọi một method với descriptor:

~~~text
(Lcom/example/model/Order;)Lcom/example/model/OrderDto;
~~~

Generator mới đổi method nhận thêm `MappingContext`. Binary consumer chưa biên dịch lại vẫn tìm descriptor cũ; nếu method cũ không còn, JVM có thể ném `NoSuchMethodError`.

Vì vậy cần phân biệt hai loại compatibility:

- **Binary/source compatibility:** class/member có còn để client compile/link không?
- **Behavioral/data compatibility:** cùng lời gọi có còn cho kết quả, dữ liệu và tác dụng phụ phù hợp không?

## 3. Ghi nhận đầy đủ input của generator

Để biết thay đổi đến từ đâu, cần xác định tất cả đầu vào:

~~~text
Generator / plugin version ---+
JDK và compiler version ------+
Annotations và source --------+
OpenAPI/XSD/proto schema -----+--> Generated output
Generator options/templates --+
Processor classpath ----------+
Locale/encoding/environment --+
Incremental/cache state ------+
~~~

| Nhóm | Cần ghi |
|---|---|
| JDK | Version, vendor, patch, compiler target/release |
| Build | Maven/Gradle version, plugin versions |
| Generator | CLI, library, annotation processor, template version |
| Input | Git commit, schema/IDL revision, source annotations |
| Config | Naming, null, enum, date/time, target language options |
| Processor dependencies | Processor path, transitive dependencies |
| Runtime constraints | Supported JDKs, module path, frameworks |
| Output | Generated source, resources, classes, final artifact |
| Pipeline | Code enhancement, shading, obfuscation, packaging |

Không nên kết luận “generator version X làm thay đổi class” nếu giữa hai build còn đổi cả schema, JDK, compiler flags hoặc dependency graph mà chưa có cách phân biệt tác động.

## 4. Tạo baseline và candidate bằng build sạch

Quy trình cơ bản:

~~~text
Cùng source/schema snapshot
          |
    +-----+------+
    |            |
    v            v
Generator cũ   Generator mới
JDK/tool cũ    JDK/tool mục tiêu
    |            |
Clean build   Clean build
    |            |
    v            v
Source cũ     Source mới
Class cũ      Class mới
JAR cũ        JAR mới
    |            |
    +-----+------+
          |
          v
So diff source + bytecode + API
          |
          v
Thử consumer và hành vi runtime
~~~

**Build sạch** rất quan trọng: incremental build có thể giữ file sinh từ bản cũ khiến người kiểm tra tưởng bản mới vẫn tạo ra chúng.

### 4.1. Maven

Các lệnh minh họa để chạy trong môi trường thử nghiệm:

~~~bash
mvn -version
mvn clean compile
mvn clean package
~~~

Những vị trí output thường gặp:

~~~text
target/generated-sources/annotations/
target/generated-sources/<generator>/
target/generated-test-sources/
target/classes/
target/test-classes/
target/*.jar
~~~

Tùy plugin, generated source còn có thể được ghi ở vị trí riêng hoặc trong module chuyên chứa generated code.

### 4.2. Gradle

~~~bash
./gradlew --version
./gradlew clean classes
./gradlew clean build
~~~

Để loại trừ khả năng cache hoặc incremental logic che mất thay đổi:

~~~bash
./gradlew clean classes --no-build-cache --rerun-tasks
~~~

Các thư mục thường gặp:

~~~text
build/generated/sources/annotationProcessor/java/main/
build/generated/sources/annotationProcessor/java/test/
build/classes/java/main/
build/classes/java/test/
build/libs/
~~~

Không cần tắt cache vĩnh viễn. Mục tiêu là tạo baseline đáng tin trước khi xem bản nâng cấp.

### 4.3. Tách hai môi trường

Có thể dùng worktree/CI jobs độc lập để mỗi bản có thư mục build riêng. Nếu so cùng source với hai generator, chỉ thay những version cần đánh giá; nếu bắt buộc nâng JDK và tool cùng lúc, ghi rõ và bổ sung ma trận kiểm thử khi cần.

## 5. So generated source theo mức ảnh hưởng

Bắt đầu từ file được **thêm, xóa, đổi tên**, sau đó mới so nội dung.

Ví dụ khi có hai thư mục snapshot:

~~~bash
git diff --no-index --stat snapshots/old/generated snapshots/new/generated
git diff --no-index snapshots/old/generated snapshots/new/generated
~~~

Với `git diff --no-index`, exit code khác 0 có thể chỉ báo có khác biệt, không có nghĩa command thực thi hỏng.

Phân loại output:

| Loại diff | Cần kiểm tra |
|---|---|
| Timestamp/header | Reproducibility; có thể chỉ là nhiễu |
| Imports/formatting | Có làm thay đổi compile behavior không? |
| File/class bị xóa | Client/DI/framework còn phụ thuộc không? |
| Constructor/method mới | API và overload resolution |
| Method bị đổi tham số | Descriptor, binary consumer cũ |
| Access modifier đổi | Compile/link access, JPMS |
| Annotation/metadata đổi | ORM, DI, serialization, reflection |
| Mapping implementation đổi | Null, enum, collection, numeric conversions |
| Serialization template đổi | Wire format, backward/forward compatibility |
| Generic type đổi | Source/API compatibility, reflection |
| Package/namespace đổi | Client import và framework discovery |

Một thay đổi vài dòng có thể quan trọng hơn hàng ngàn dòng format khác. Ngược lại, timestamp làm toàn bộ file đổi hash chưa chắc ảnh hưởng kết quả chạy.

### 5.1. Đừng sửa generated source để chữa lỗi gốc

Thông thường generated source là sản phẩm của schema/annotation/options/templates. Việc sửa tay vào `target/generated-sources` hoặc `build/generated` sẽ bị lần build sau ghi đè. Hãy sửa source of truth hoặc cấu hình generator.

Ngoại lệ là dự án chủ động commit generated source như nguồn được quản lý; khi đó phải có quy trình regenerate, review diff và đồng bộ version generator.

## 6. So file class sau compile và sau enhancement

Generated `.java` giống nhau không đảm bảo `.class` giống nhau. Compiler JDK, `--release`, bytecode weaving, instrumentation và packaging có thể thay kết quả.

### 6.1. Xem major version

~~~bash
javap -verbose -classpath target/classes com.example.generated.OrderMapperImpl
~~~

Ví dụ class file major version:

| Java | Major |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

Nếu artifact được công bố hỗ trợ Java 17 nhưng có một generated class major 65, Java 17 có thể gặp `UnsupportedClassVersionError` khi tải class đó.

**Kiểm tra artifact cuối**, không chỉ class viết tay. Nếu generator hoặc dependency JAR được build cho runtime cao hơn target, `--release 17` của main compiler không tự biến dependency đó thành Java 17-compatible.

### 6.2. Xem descriptor và modifier

~~~bash
javap -classpath target/classes -p -s com.example.generated.OrderMapperImpl
javap -classpath target/classes -p -verbose com.example.generated.OrderMapperImpl
~~~

- `-s` hiển thị JVM field/method descriptors.
- `-p` hiển thị cả member không public.
- `-verbose` hiển thị constant pool và metadata.
- `-c` hiển thị bytecode instructions khi cần phân tích logic.

Với binary compatibility, method name và descriptor đặc biệt quan trọng. Một method tên giống cũ nhưng khác tham số hoặc kiểu trả về vẫn có thể gây `NoSuchMethodError` cho binary cũ.

### 6.3. So JAR cuối cùng

~~~bash
jar --list --file target/application.jar
~~~

Đối chiếu class, resources, service provider metadata và dependency relocation. Với shaded/fat JAR, class trong JAR phát hành có thể khác `target/classes` vì build plugin đã relocate hoặc transform thêm.

### 6.4. Công cụ so API

Những công cụ như Revapi hoặc japicmp giúp so sánh JAR ở mức API/ABI và phát hiện nhiều thay đổi gây ảnh hưởng nhị phân. Tuy nhiên, không thể thay thế test với null handling, serialization semantics, ORM state transitions hoặc runtime-generated proxies.

## 7. Maven: kiểm soát annotation processor

Một annotation processor cần được khai báo và quản lý phiên bản cùng với build. Ví dụ Maven Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.0</version>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>org.mapstruct</groupId>
                <artifactId>mapstruct-processor</artifactId>
                <version>1.6.3</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Đây là cấu hình minh họa; bản plugin/processor cần phù hợp với dự án thực tế. Nếu source dùng annotations và interface từ MapStruct, dependency API tương ứng cũng cần được khai báo hợp lệ.

### 7.1. Vì sao cần processor path riêng?

Một annotation processor là công cụ **build-time**; nó thường không cần có mặt trong runtime artifact. Tách processor path có các lợi ích:

- Đảm bảo version processor được pin rõ.
- Tránh vô tình chạy processor khác từ compile dependencies.
- Giảm rủi ro classpath conflict.
- Dễ truy ra vì sao generated code đổi.
- Tránh đóng gói công cụ build vào runtime.

Khi đổi JDK/compiler, quy tắc phát hiện annotation processor có thể thay đổi. Hãy cấu hình processing tường minh thay vì giả định mọi processor sẽ tự chạy như ở compiler cũ.

### 7.2. Generated test sources cũng cần kiểm tra

Nếu processor chạy tại `testCompile` hoặc plugin sinh fixtures/test helpers, phải so:

~~~text
target/generated-test-sources/
target/test-classes/
~~~

Một công cụ test mới có thể sinh class khác mà main artifact không thay đổi; điều đó vẫn có thể làm test flaky hoặc bị lỗi trên JDK mới.

## 8. Gradle: processor path, toolchain và incremental build

Ví dụ Java Gradle project:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.mapstruct:mapstruct:1.6.3'
    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Các khái niệm tách biệt:

- `implementation`: thư viện/API được source sử dụng.
- `annotationProcessor`: processor chạy khi compile.
- `java.toolchain`: JDK cho các tác vụ Java toolchain-aware.
- `options.release`: mức Java language/API/bytecode cho compiler.

Một processor khai báo task inputs/outputs không đầy đủ có thể dẫn tới incremental build thiếu generated files sau khi source thay đổi. Vì vậy cần chạy cả clean build và một lượt incremental representative trước khi chấp nhận cấu hình mới.

## 9. Generator dựa trên schema: kiểm tra code và dữ liệu truyền

### 9.1. Protobuf và gRPC

Khi đổi `protoc` hoặc gRPC Java plugin, cần xem:

- Generated packages, class names và Java outer class names.
- Method signatures của client/server stubs.
- Field numbers và wire types.
- Optional/oneof và presence semantics.
- Unknown field preservation.
- Enum values, default và unknown enum handling.
- Runtime Protobuf/gRPC library version.

Code Java có thể thay đổi nhưng wire protocol vẫn tương thích; chiều ngược lại, schema có thể đổi nghĩa của field dù Java API nhìn gần giống. Vì vậy so source chưa đủ: phải dùng serialization fixtures giữa producer/consumer các version.

### 9.2. OpenAPI Generator

Kiểm tra:

- Model class, operation name, package.
- HTTP path, method, header/query parameter.
- JSON field naming, serializer annotations.
- Nullability và required/optional behavior.
- Enum và validation.
- Date/time type mapping.
- Response error handling.
- Runtime HTTP client dependencies.

Cần chạy contract test trên payload thực tế, gồm missing/unknown fields, null, nested objects và các HTTP status quan trọng. Không nên chỉ test client có compile.

### 9.3. JAXB/XJC/WSDL và namespace migration

Khi đổi XML binding generator, kiểm tra annotation namespace `javax.*` so với `jakarta.*`, XML element names, adapters, date/time conversion, QName và khả năng marshal/unmarshal.

Một generated class dùng Jakarta annotations có thể không hoạt động với một framework consumer cũ chỉ xử lý Javax annotations; đây là thay đổi API và runtime integration, không phải vấn đề đơn thuần của compiler.

### 9.4. JPA metamodel và ORM enhancement

Khi nâng annotation processor/enhancer của ORM, cần kiểm tra generated metamodel attributes, reflection access, proxy subclass, lazy loading, dirty tracking, serialization và behavior của equals/hashCode. Đặc biệt với JPMS, proxy/agent có thể gặp thêm vấn đề `exports` hoặc `opens`.

## 10. Bytecode transformers và test tools

Các thư viện như ASM/Byte Buddy, mocking framework hoặc coverage agent phải hiểu class file version do JDK mới tạo ra. Công cụ quá cũ có thể báo:

~~~text
Unsupported class file major version ...
java.lang.VerifyError: ...
java.lang.ClassFormatError: ...
~~~

Không phải mọi trường hợp đều do bytecode được sinh sai; đôi khi công cụ đọc class chưa hỗ trợ class file mới, hoặc plugin test khởi động agent với cơ chế đã thay đổi.

Khi nâng công cụ để hỗ trợ JDK mới, hãy kiểm tra:

- Test có còn mock final/static/constructor theo hợp đồng không?
- Proxy có được định nghĩa bởi đúng class loader/module?
- Có cần mở package cho reflection theo chính sách JPMS không?
- Instrumentation có thay đổi method/field/annotation của class?
- Agent có còn hoạt động trên runtime mục tiêu và policy dynamic attachment không?
- Class bytecode cuối có hợp lệ và tương thích với target không?

**Runtime-generated class không nhất thiết có trên disk.** Cần integration test hoặc cơ chế dump bytecode do thư viện hỗ trợ, nếu muốn nghiên cứu chi tiết. Không đoán flag dump hoặc thêm quyền JVM trên production chỉ để “thử”.

## 11. Chẩn đoán lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `cannot find symbol` | Generated class/method không còn | Input annotation, output source, plugin config |
| `NoSuchMethodError` | Descriptor trong binary không khớp generated class mới | `javap -s -p`, ABI diff |
| `NoSuchFieldError` | Field bị xóa/đổi kiểu | Field descriptors, consumer |
| `IllegalAccessError` | Modifier hoặc module exports thay đổi | Access flags, package, module |
| `UnsupportedClassVersionError` | Bytecode cao hơn JVM target | Major version, toolchain, `--release` |
| `VerifyError` | Bytecode vi phạm verifier | Transformer, stack frames, agent |
| `ClassFormatError` | Class file malformed hoặc không được công cụ đọc đúng | Generator/library, artifact |
| `NoClassDefFoundError` | Generated class/dependency thiếu hoặc initialization failure | Packaging, runtime classpath, cause |
| `ClassCastException` | Proxy/loader/type hierarchy khác | Interfaces, class loader identity |
| `InaccessibleObjectException` | Reflection bị JPMS chặn | `opens`, framework version |
| `InvalidClassException` | Java serialization form không tương thích | Fields, `serialVersionUID` |
| JSON/XML/protocol mismatch | Generator đổi dữ liệu được sinh | Fixtures và contract tests |
| Mock test fail trên JDK mới | Bytecode agent/mock engine không phù hợp | Dependency versions, runtime, agent logs |

Đừng gộp mọi sự cố thành “JDK mới lỗi”. Cần xác định điểm phát sinh: generation, compilation, packaging, loading, linking hoặc runtime behavior.

## 12. Kiểm tra source và binary consumer riêng biệt

### 12.1. Biên dịch consumer source với artifact mới

Tạo module sample tiêu thụ các generated API công khai. Khi biên dịch lại, compiler giúp tìm các tên class, constructor, method hoặc generic signatures không còn hợp lệ.

### 12.2. Chạy consumer binary cũ với artifact mới

Nếu thư viện đã có client được biên dịch sẵn:

~~~text
Thư viện v1 + generator v1
            |
            v
Compile Client.class
            |
            v
Giữ nguyên Client.class
            |
            v
Thay thư viện bằng v2
            |
            v
Chạy Client.class cũ trên thư viện v2
~~~

Chỉ như vậy mới kiểm tra được binary compatibility của artifact cũ. Nếu biên dịch lại client, lỗi có thể xuất hiện ở compile phase và không kiểm tra được điều kiện mà binary production gặp.

### 12.3. Hành vi quan trọng cần test

- Null, empty, default values.
- Enum lạ và unknown fields.
- Collection ordering và mapping nested object.
- Currency/number precision, timezone, locale.
- JSON/XML/Protobuf round-trip giữa các version.
- ORM proxy, lazy loading và dirty tracking.
- Dependency injection discovery.
- Serialization/reflection/annotation metadata.
- Test agent và mocking behavior.

Một generated class có public API không đổi vẫn có thể làm mất dữ liệu hoặc thay authorization mapping; cần contract tests cho các thuộc tính nghiệp vụ quan trọng.

## 13. Reproducible build và output noise

Generated files có thể khác nhau chỉ vì timestamp, đường dẫn tuyệt đối hoặc thứ tự duyệt file. Chỉ so raw hash sẽ cho nhiều tín hiệu giả. Tuy nhiên, output thiếu ổn định còn ảnh hưởng caching và khả năng kiểm chứng supply chain.

Nên:

1. Pin version generator và compiler/build plugin.
2. Tắt timestamp hoặc volatile header khi công cụ hỗ trợ.
3. Cố định input ordering, encoding và các options liên quan.
4. Ghi JDK/vendor/build và schema revision.
5. Nếu normalize output trước khi so, chỉ loại phần nhiễu đã hiểu; không loại annotation hoặc metadata có thể ảnh hưởng runtime.
6. Kiểm tra build sạch ở môi trường thứ hai.
7. Kiểm tra một incremental build representative sau clean build.

**Build sạch đúng** và **incremental build đúng** là hai điều kiện khác nhau. Một processor có cache key sai có thể sinh output đúng khi clean nhưng để lại file stale khi source được thay đổi.

## 14. Quy trình thực tế khi nâng generator hoặc test tool

### Bước 1: Kiểm kê tool

Liệt kê annotation processors, schema generators, bytecode transformers, agent, mocking/coverage frameworks và packaging plugins. Ghi version, output path, input schema và nhóm consumer.

### Bước 2: Lưu baseline

Giữ cùng source revision/schema và build bằng bộ công cụ cũ trong thư mục sạch. Lưu generated source, compiled classes, artifact, API report và test fixtures quan trọng.

### Bước 3: Nâng công cụ có kiểm soát

Thay đúng generator/plugin/dependency cần thử. Nếu còn đổi JDK, ghi rõ để phân biệt tác động. Tránh đồng thời sửa schema hoặc business logic nếu mục tiêu chỉ là kiểm tra generator.

### Bước 4: Tạo candidate bằng clean build

Bảo đảm không dùng stale files hoặc build cache chưa được kiểm soát. Ghi metadata của compiler và tool.

### Bước 5: So generated source

Xem file thêm/xóa/đổi tên, code changes, metadata, null/enum mapping, public API.

### Bước 6: So class file và artifact cuối

Kiểm tra major version, descriptors, modifiers, runtime annotations, transformed classes và nội dung JAR. Dùng API diff tool nếu artifact có consumer ngoài.

### Bước 7: Chạy cross-version tests

Biên dịch source consumer mới và chạy binary consumer cũ với artifact mới; chạy serialization/contract tests trên fixtures v1/v2. Với bytecode agents/proxy, chạy trực tiếp trên JDK mục tiêu.

### Bước 8: Kiểm tra reproducibility và incremental

Xác nhận output ổn định ở CI runner sạch và thay input thực sự làm generated files cập nhật đúng. Nếu có noise, xác định nguyên nhân trước khi tạo snapshot checks.

### Bước 9: Cập nhật tài liệu compatibility

Nếu API hoặc wire format thay đổi, ghi migration instructions, release notes, consumer impact và yêu cầu JDK mới. Không gọi một thay đổi phá vỡ là “chỉ nâng plugin”.

## 15. Những hiểu nhầm thường gặp

**“Source nghiệp vụ không đổi thì artifact không đổi.”** Không. Generator/compiler/enhancer có thể tạo source và bytecode khác.

**“Chỉ cần xem generated .java.”** Không nếu công cụ sửa `.class` trực tiếp hoặc sinh proxy lúc runtime.

**“Build xanh chứng minh binary compatibility.”** Không. Binary client cũ có thể gặp `NoSuchMethodError` trên JAR mới.

**“API y hệt là hành vi y hệt.”** Không. Mapper/serializer có thể thay semantics của null, enum và default values.

**“`--release 17` bảo đảm mọi class trong JAR đều chạy trên 17.”** Không nếu dependency hoặc post-processor tạo bytecode cao hơn.

**“Processor trong dependencies luôn được chạy.”** Không nên giả định. Cấu hình processor discovery, path và version compiler rất quan trọng.

**“Incremental build thành công có nghĩa generated output mới được tái tạo đúng.”** Không nếu stale files hoặc cache.

**“Chỉ cần so hash JAR.”** Hash khác không cho biết hợp đồng thay đổi thế nào; hash giống không chứng minh toàn bộ runtime behavior.

**“Nâng Mockito/Byte Buddy chỉ ảnh hưởng test.”** Công cụ test có thể sinh class/agent trên runtime mới; lỗi thuộc testing infrastructure cần phân biệt với regression nghiệp vụ.

## 16. Checklist khi thay phiên bản công cụ sinh mã

- [ ] Đã xác định tool và output liên quan: source, class, resource, proxy.
- [ ] Đã cố định Git revision, schema, templates và generator options.
- [ ] Đã ghi JDK/compiler/build plugin/generator versions cũ và mới.
- [ ] Đã tạo hai build sạch không reuse stale generated output.
- [ ] Đã so danh sách generated files được thêm/xóa/đổi tên.
- [ ] Đã xem các thay đổi trong generated source, constructor và method.
- [ ] Đã kiểm tra class file major version của artifact cuối.
- [ ] Đã so public API/ABI, descriptor, visibility và runtime annotations.
- [ ] Đã kiểm tra enhancement, shading và runtime-generated proxy.
- [ ] Đã xác nhận annotation processor path và generated source directories.
- [ ] Đã chạy source consumer build và binary consumer compatibility tests.
- [ ] Đã kiểm tra serialization/protocol fixtures và read–modify–write behavior.
- [ ] Đã chạy unit/integration tests cho null, enum, ORM, DI, reflection.
- [ ] Đã thử trên runtime JDK tối thiểu và runtime mục tiêu.
- [ ] Đã xử lý timestamp/path noise hợp lý, không che thay đổi có ý nghĩa.
- [ ] Đã kiểm tra reproducible và incremental builds.
- [ ] Đã lưu diff, test evidence và migration notes khi cần.

## 17. Kết luận

Thay version annotation processor, schema generator, compiler plugin, bytecode enhancer hoặc test tool là thay đổi **đầu vào của quá trình tạo artifact**, không chỉ là sửa cấu hình build. Nó có thể làm generated Java source, class file, public API hoặc serialization behavior thay đổi mà không có chỉnh sửa source nghiệp vụ.

Đối với Java Advance Compatibility Migration, hãy luôn kiểm tra **generated source thực tế**, **class file/JAR sau tất cả bước biến đổi** và **hợp đồng runtime của consumer**. So baseline/candidate bằng build sạch, dùng `javap` và API diff để kiểm tra binary, chạy test dữ liệu/serialization cùng binary client cũ, rồi xác minh proxy/agent trên JDK đích. Chỉ khi có đủ bằng chứng ở các tầng này mới có thể coi việc nâng công cụ sinh mã là an toàn trong phạm vi hệ thống được hỗ trợ.

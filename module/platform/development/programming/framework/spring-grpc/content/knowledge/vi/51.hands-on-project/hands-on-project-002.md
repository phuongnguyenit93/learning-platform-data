# Sinh generated message và stub trong Gradle

Trong Spring gRPC, file .proto là nguồn hợp đồng để sinh hai nhóm Java code khác nhau: protobuf message classes biểu diễn request/response và gRPC classes cung cấp stub cho client cùng base class cho server. Gradle cần chạy đúng compiler protoc và plugin protoc-gen-grpc-java, đưa output vào source set tương ứng rồi biên dịch chúng cùng mã ứng dụng.

Bài này thiết lập quy trình đó bằng protobuf Gradle plugin. Kết quả mong đợi là developer chỉ quản lý proto source và cấu hình build; mỗi lần build, Gradle tự sinh message, descriptor và stub nhất quán cho client/server. Nội dung áp dụng cho dự án Java Spring gRPC; phần service business và cấu hình runtime server được triển khai ở các bước tiếp theo.

## 1. Phân biệt protoc, plugin Gradle và plugin gRPC Java

Ba thành phần có vai trò riêng:

| Thành phần | Vai trò |
| --- | --- |
| protoc | Compiler đọc .proto, kiểm tra schema và sinh protobuf message Java qua Java builtin |
| protoc-gen-grpc-java | Protoc plugin sinh gRPC service descriptor, client stubs và server base class |
| com.google.protobuf Gradle plugin | Tạo task Gradle, nối proto source set với compiler/plugin và đăng ký generated source để Java compile sử dụng |

Chỉ chạy Java builtin của protoc sẽ sinh message classes nhưng không sinh OrderServiceGrpc hay service base class. Ngược lại, gRPC plugin cần schema đã được protoc xử lý và runtime dependencies tương ứng.

Các phiên bản phải được pin rõ ràng:
- Phiên bản protobuf Gradle plugin điều khiển integration với Gradle.
- Phiên bản protoc xác định compiler và code generation cho protobuf Java.
- Phiên bản protoc-gen-grpc-java nên đồng bộ với dòng gRPC Java runtime dùng trong ứng dụng.
- Protobuf Java runtime phải tương thích với protoc đã sinh code.

Không để build tải một compiler không xác định hoặc dùng version khác nhau giữa developer workstation và CI. Dùng Gradle Wrapper và khai báo version tập trung trong build configuration hoặc version catalog của dự án.

## 2. Đặt proto vào đúng source set

Với source set main mặc định, đặt file proto dưới src/main/proto:

```text
src/
  main/
    java/
      com/myshop/order/
    proto/
      shop/order/v1/order_service.proto
  test/
    java/
    proto/
build/
  generated/
    source/
      proto/
```

Thư mục src/main/proto là proto source mặc định của protobuf Gradle plugin. File trong src/test/proto thuộc test source set và được sinh riêng khi dự án có contract/proto chỉ dùng trong test.

Không đặt file .proto trong src/main/java hoặc thư mục generated. Proto là input source được review và version hóa; generated Java là build output. Nếu một proto import file khác, import path phải phân giải được từ proto source roots hoặc dependency được cấu hình cho task.

Ví dụ file nhỏ để kiểm tra generation:

```proto
syntax = "proto3";

package shop.greeting.v1;

option java_multiple_files = true;
option java_package = "com.myshop.greeting.v1";
option java_outer_classname = "GreetingProto";

service GreetingService {
  rpc SayHello(HelloRequest) returns (HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
```

package tạo namespace protobuf và tham gia full gRPC method name. java_package quyết định package của Java generated classes. java_multiple_files = true sinh mỗi message thành class riêng; nếu không bật, message classes thường nằm trong outer class được sinh từ proto file. java_outer_classname đặt tên outer descriptor class ổn định.

## 3. Cấu hình protobuf Gradle plugin bằng Groovy DSL

Ví dụ build.gradle:

```groovy
plugins {
    id 'java'
    id 'com.google.protobuf' version '<protobuf-gradle-plugin-version>'
}

def protobufVersion = '<protobuf-version>'
def grpcVersion = '<grpc-java-version>'

dependencies {
    implementation platform('io.grpc:grpc-bom:' + grpcVersion)

    implementation 'com.google.protobuf:protobuf-java:' + protobufVersion
    implementation 'io.grpc:grpc-protobuf'
    implementation 'io.grpc:grpc-stub'

    // Chỉ cần transport này khi ứng dụng chạy client/server qua Netty.
    runtimeOnly 'io.grpc:grpc-netty-shaded'

    testImplementation 'org.junit.jupiter:junit-jupiter:<junit-version>'
}

protobuf {
    protoc {
        artifact = 'com.google.protobuf:protoc:' + protobufVersion
    }

    plugins {
        grpc {
            artifact = 'io.grpc:protoc-gen-grpc-java:' + grpcVersion
        }
    }

    generateProtoTasks {
        all().each { task ->
            task.plugins {
                grpc {}
            }
        }
    }
}

test {
    useJUnitPlatform()
}
```

Thay các placeholder version bằng phiên bản đã được dự án phê duyệt và pin. Ví dụ dùng BOM của gRPC Java để giữ các thư viện grpc-* cùng một release train; protobuf compiler và protobuf runtime được khai báo riêng vì chúng thuộc hệ version protobuf. Nếu dự án dùng Spring Boot dependency management hoặc version catalog, đưa các version vào cơ chế quản lý tập trung thay vì khai báo lặp.

Trong cấu hình trên:
- protoc.artifact chọn compiler protobuf Java.
- plugins.grpc.artifact chọn executable protoc-gen-grpc-java.
- generateProtoTasks thêm gRPC plugin vào mọi proto generation task, bao gồm source set main và test nếu có.
- Java builtin được protobuf Gradle plugin cấu hình cho Java project; plugin grpc bổ sung gRPC-specific generated source.
- grpc-protobuf và grpc-stub là compile dependencies cho generated gRPC code và application.
- grpc-netty-shaded cung cấp network transport Netty khi runtime cần; nó không phải compiler plugin.

Nếu dùng Kotlin DSL trong build.gradle.kts, cấu trúc khái niệm giống nhau nhưng cú pháp khai báo plugin/task khác Groovy DSL. Dùng cú pháp tương ứng với phiên bản protobuf Gradle plugin trong dự án, không trộn snippet Groovy vào file Kotlin DSL.

## 4. Hiểu output: message classes và gRPC stubs

Sau khi generation thành công, output mặc định thường nằm dưới build/generated/source/proto theo source set và generator:

| Output | Nội dung |
| --- | --- |
| build/generated/source/proto/main/java | Message classes, enum, outer descriptor class |
| build/generated/source/proto/main/grpc | gRPC service descriptor, client stubs và server base class |
| build/generated/source/proto/test/java | Message classes được sinh từ src/test/proto |
| build/generated/source/proto/test/grpc | gRPC classes được sinh từ test proto |

Tên thư mục chính xác có thể phụ thuộc source set và cấu hình plugin, nhưng nguyên tắc là Java builtin và gRPC plugin có output riêng. Generated files là output của task, không phải nơi sửa code.

Với ví dụ GreetingService, các class quan trọng gồm:
- HelloRequest và HelloReply: protobuf messages có builder, getter, parser và serialization.
- GreetingProto: outer descriptor class vì ví dụ đã đặt java_outer_classname.
- GreetingServiceGrpc: class gRPC sinh từ service definition.
- GreetingServiceGrpc.GreetingServiceBlockingStub: client stub đồng bộ.
- GreetingServiceGrpc.GreetingServiceStub: client stub bất đồng bộ.
- GreetingServiceGrpc.GreetingServiceImplBase: base class để server override method.

Nếu chỉ thấy HelloRequest nhưng không thấy GreetingServiceGrpc, kiểm tra cấu hình plugin grpc trong generateProtoTasks. Nếu không thấy message classes, kiểm tra Java builtin, source root và protoc task.

## 5. Chạy task generation và compile

Các lệnh thường dùng:

```bash
./gradlew clean generateProto
./gradlew compileJava
./gradlew test
```

Trên Windows có thể chạy Gradle Wrapper bằng .\gradlew.bat với cùng task names. generateProto sinh source từ proto thuộc main source set; compileJava biên dịch application cùng generated source đã được plugin nối vào source set. test biên dịch và chạy test source set.

Thông thường compile task đã phụ thuộc generated source task cần thiết. Chạy generateProto riêng hữu ích khi kiểm tra code generation; chạy compileJava xác minh generated code và dependency thực sự tương thích. Không cần tự thêm thư mục build/generated/... vào sourceSets nếu protobuf Gradle plugin đã tự đăng ký output.

Khi cần xem task graph hoặc log compiler:

```bash
./gradlew tasks --all
./gradlew generateProto --info
```

Không chỉnh sửa file trong build/generated. Khi proto thay đổi, Gradle đánh giá input/output và chạy lại task tương ứng. clean xóa output generated; build sau đó sinh lại từ proto source.

## 6. Sử dụng generated message và stub

Sau khi build, client tạo message bằng builder và gọi qua generated stub:

```java
HelloRequest request = HelloRequest.newBuilder()
        .setName("Lan")
        .build();

GreetingServiceGrpc.GreetingServiceBlockingStub stub =
        GreetingServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(1, TimeUnit.SECONDS);

HelloReply reply = stub.sayHello(request);
System.out.println(reply.getMessage());
```

channel là ManagedChannel đã được cấu hình và quản lý lifecycle ở tầng ứng dụng. Stub là immutable về call options; withDeadlineAfter trả về stub mới mang deadline cho call. Không tạo một ManagedChannel mới cho từng request.

Server kế thừa generated base class và override method:

```java
public final class GreetingGrpcService
        extends GreetingServiceGrpc.GreetingServiceImplBase {

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {
        HelloReply response = HelloReply.newBuilder()
                .setMessage("Hello, " + request.getName())
                .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
```

Generated base class cung cấp RPC method signatures theo proto. Service implementation chỉ viết business logic và tuân thủ observer lifecycle; không sửa generated source. Trong Spring gRPC, service implementation được đăng ký theo cơ chế của starter/framework đang dùng, còn Gradle generation vẫn là bước build độc lập.

## 7. Dependency và annotation khi compile

Generated message code cần protobuf runtime. Generated gRPC code cần các API gRPC như MethodDescriptor, Channel, stub, StreamObserver và server definitions; do đó grpc-protobuf và grpc-stub phải nằm trên compile classpath.

Một số phiên bản generator tạo annotation javax.annotation.Generated. Với JDK không còn cung cấp annotation đó mặc định, compiler có thể báo thiếu package javax.annotation. Chỉ khi gặp lỗi này và generator của dự án thực sự tham chiếu annotation đó, thêm compile-only dependency phù hợp, ví dụ:

```groovy
compileOnly 'javax.annotation:javax.annotation-api:1.3.2'
```

Không thêm dependency annotation theo thói quen nếu generated code hiện tại không cần. Cũng không đưa transport implementation vào compile dependencies của module chỉ chứa contract nếu module đó không mở channel/server.

## 8. Proto imports và nhiều module Gradle

Nếu proto import well-known types như Timestamp, FieldMask hoặc Empty, protoc có include path tương ứng trong distribution; dùng đúng import path chuẩn, ví dụ google/protobuf/timestamp.proto. Với proto nội bộ, bảo đảm task có source root hoặc artifact chứa file import.

Trong multi-module project, chọn một nguồn contract duy nhất:
- Một module contract chứa proto và có thể publish proto artifact hoặc generated Java contract artifact.
- Client và server phụ thuộc cùng version contract đã phát hành.
- Tránh copy cùng file proto vào nhiều module rồi generate nhiều bản class cùng package.
- Nếu module downstream cần import proto từ module upstream, cấu hình dependency/proto source path rõ ràng và version hóa.
- Khi nâng contract, kiểm tra generated API và compatibility trước khi nâng cả client lẫn server.

Không commit generated source nếu chính sách repository không yêu cầu. Thông thường chỉ commit .proto và build configuration; generated files nằm trong build/ và được tái tạo trong CI. Nếu tổ chức publish generated code như artifact, artifact phải gắn với đúng proto version và compiler/plugin versions.

## 9. Chẩn đoán lỗi generation thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Có message class nhưng không có GreetingServiceGrpc | Chưa cấu hình grpc plugin cho generation task | Kiểm tra protobuf.plugins.grpc và generateProtoTasks |
| Không có generated Java nào | Proto source sai vị trí, protoc task không chạy hoặc proto compile lỗi | Kiểm tra src/main/proto, task output và log --info |
| Import .proto không tìm thấy | Thiếu proto source root/dependency hoặc import path sai | Kiểm tra import path và task include roots |
| Java compile báo thiếu io.grpc.* | Thiếu grpc-stub/grpc-protobuf hoặc version dependency lệch | Kiểm tra compile classpath và BOM |
| Compile báo thiếu javax.annotation.Generated | Generator version tạo annotation nhưng JDK không cung cấp | Xác nhận generated source rồi thêm compileOnly annotation API nếu cần |
| Client/server generated API không giống nhau | Hai module dùng proto hoặc generator version khác | So sánh contract artifact và version compiler/plugin |
| IDE báo đỏ nhưng Gradle compile pass | IDE chưa đồng bộ Gradle source/task model | Reload Gradle project và kiểm tra output task |

Khi debug, ưu tiên xem task input/output và lỗi protoc gốc. Không sửa generated file để chữa lỗi vì lần build sau sẽ ghi đè và che khuất nguyên nhân.

## 10. Checklist hoàn thành

- [ ] .proto nằm trong src/main/proto hoặc source root được cấu hình rõ.
- [ ] Protobuf package và Java package được khai báo có version.
- [ ] java_multiple_files và outer class được chọn có chủ đích.
- [ ] Protobuf Gradle plugin được pin version.
- [ ] Protoc version tương thích protobuf runtime.
- [ ] Protoc-gen-grpc-java được cấu hình và đồng bộ gRPC Java runtime.
- [ ] generateProtoTasks áp dụng plugin grpc cho source set cần thiết.
- [ ] Message classes và gRPC stub được sinh ở output tương ứng.
- [ ] Compile classpath có protobuf/gRPC API cần thiết.
- [ ] generateProto, compileJava và test chạy thành công.
- [ ] Không sửa generated output trực tiếp.
- [ ] Multi-module dùng một nguồn contract và version rõ ràng.

**Tự kiểm tra**

**Câu 1.** Vì sao chỉ cấu hình protoc Java builtin chưa đủ để có gRPC stub?

*Đáp án:* Java builtin sinh protobuf message classes. Stub và server base class được sinh bởi protoc-gen-grpc-java, vì vậy phải khai báo plugin grpc và áp dụng nó cho các generation task.

**Câu 2.** src/main/proto khác build/generated/source/proto thế nào?

*Đáp án:* src/main/proto chứa source contract được review và version hóa. build/generated/source/proto là output do Gradle tạo từ source đó và có thể xóa/sinh lại.

**Câu 3.** GreetingServiceGrpc và HelloRequest được sinh bởi thành phần nào?

*Đáp án:* HelloRequest do protobuf Java builtin sinh; GreetingServiceGrpc do protoc-gen-grpc-java sinh từ service definition.

**Câu 4.** Vì sao client và server cần dùng cùng version contract artifact?

*Đáp án:* Cùng contract version giúp generated method path, request/response types và semantics nhất quán. Nếu hai module tự copy/generate từ schema khác nhau, runtime có thể lệch dù mỗi module compile riêng.

**Câu 5.** Có nên sửa trực tiếp file generated khi compile lỗi không?

*Đáp án:* Không. Generated file sẽ bị tạo lại ở lần build tiếp theo. Hãy sửa proto, compiler/plugin configuration hoặc dependency tương ứng rồi generate lại.

Gradle generation tạo cầu nối tái lập giữa protobuf contract và Java application code. Khi proto source, protoc, gRPC generator và runtime dependencies được pin và cấu hình nhất quán, client có message/stub để gọi RPC còn server có base class để triển khai handler. Đây là bước nền tảng để phát triển và kiểm thử service Spring gRPC một cách ổn định trong local build lẫn CI.

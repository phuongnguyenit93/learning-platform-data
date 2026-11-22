# Generated code không khớp proto

Trong Spring gRPC, file `.proto` là hợp đồng dùng chung giữa client và server. Từ hợp đồng này, build tạo ra hai nhóm mã Java: các lớp message của Protocol Buffers và các lớp gRPC stub/base class cho service. Khi mã được sinh ra không phản ánh nội dung proto hiện tại, ứng dụng có thể báo thiếu lớp hoặc method lúc biên dịch, hoặc client gọi đến một RPC mà server không nhận diện được lúc chạy.

Bài này hướng dẫn lần theo toàn bộ đường đi từ proto đến mã Java, tìm đúng nguyên nhân lệch và tạo lại mã một cách có thể lặp lại trong dự án Spring gRPC.

## Nhận diện vấn đề

Các biểu hiện thường gặp gồm:

- IDE hoặc compiler không tìm thấy message, enum, service stub hay method vừa thêm vào proto.
- Mã Java vẫn có field hoặc RPC cũ dù file `.proto` đã được sửa.
- Lớp message được sinh ra nhưng lớp `*Grpc` hoặc các stub không xuất hiện.
- Import trong service implementation trỏ đến package khác với package mà generator vừa tạo.
- Mã được sinh ra không biên dịch vì gọi API runtime không tồn tại, hoặc có lỗi tương thích giữa mã sinh và thư viện protobuf/gRPC.
- Client biên dịch thành công nhưng nhận status `UNIMPLEMENTED` khi gọi một RPC mới.

Không phải mọi lỗi trên đều có cùng nguyên nhân. Lỗi thiếu symbol thường liên quan đến đầu vào hoặc cấu hình sinh mã; lỗi tương thích thường liên quan đến phiên bản; `UNIMPLEMENTED` thường cần kiểm tra hợp đồng và service thực sự được đăng ký ở server.

## Hiểu đúng các đầu ra được sinh

Quy trình có dạng:

```text
*.proto
   |
   +-- protoc ----------------------> Java message / enum / descriptor
   |
   +-- protoc-gen-grpc-java --------> Java service base class / stubs
                                           |
                                           v
                                  compile và chạy ứng dụng
```

`protoc` sinh mã cho các message, enum và descriptor. Plugin `protoc-gen-grpc-java` sinh mã cho service, gồm lớp có hậu tố `Grpc`, lớp base để server triển khai và các loại client stub. Vì vậy, chỉ có `protoc` mà chưa cấu hình plugin gRPC có thể tạo được message nhưng không tạo được stub.

Ví dụ hợp đồng:

```proto
syntax = "proto3";

package inventory.v1;

option java_package = "com.acme.inventory.v1";
option java_multiple_files = true;
option java_outer_classname = "InventoryProto";

service InventoryService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
}

message GetItemRequest {
  string id = 1;
}

message GetItemResponse {
  string id = 1;
  string name = 2;
}
```

Với các tùy chọn trên, những kiểu Java thường được tham chiếu như sau:

```java
import com.acme.inventory.v1.GetItemRequest;
import com.acme.inventory.v1.GetItemResponse;
import com.acme.inventory.v1.InventoryServiceGrpc;

InventoryServiceGrpc.InventoryServiceBlockingStub stub = ...;
GetItemResponse response = stub.getItem(
    GetItemRequest.newBuilder().setId("item-42").build()
);
```

Các tùy chọn Java ảnh hưởng trực tiếp đến tên và vị trí lớp:

| Thành phần proto | Ảnh hưởng đến mã Java |
| --- | --- |
| `package` | Tên đầy đủ của service/message trong protobuf; với gRPC, nó tham gia tạo service name trên wire. |
| `option java_package` | Package Java được sinh ra. Nếu bỏ qua, generator suy ra package Java từ quy tắc mặc định của protobuf, không nhất thiết trùng package mà ứng dụng đang import. |
| `option java_multiple_files = true` | Mỗi message/enum cấp cao nhất được sinh thành lớp Java riêng. |
| `option java_multiple_files = false` hoặc không khai báo | Message/enum thường nằm bên trong lớp wrapper ngoài cùng. Ví dụ có thể phải dùng `InventoryProto.GetItemRequest`. |
| `option java_outer_classname` | Đặt tên lớp wrapper chứa descriptor và, tùy cấu hình, các kiểu lồng nhau. Nếu không khai báo, tên được suy ra từ tên file proto. |
| `service InventoryService` | Plugin gRPC sinh lớp `InventoryServiceGrpc`; tên RPC trong service quyết định các method trên stub và descriptor. |

Đặc biệt, `package` và `java_package` phục vụ hai mục đích khác nhau. Đổi `java_package` có thể làm import Java thay đổi; đổi protobuf `package` có thể làm tên service đầy đủ thay đổi, từ đó ảnh hưởng đến đường dẫn RPC trên mạng.

## Quy trình chẩn đoán và khắc phục

### 1. Xác nhận build đang đọc đúng file proto

Trước tiên, tìm file `.proto` mà build thực sự đưa vào quá trình sinh mã. Kiểm tra:

- File đang sửa có nằm trong thư mục proto source mà build tool cấu hình hay không.
- Có một bản proto khác cùng tên hoặc cùng định nghĩa message/service trong module khác hay không.
- Các `import` trong proto có đang lấy schema từ đúng dependency/version hay không.
- Build đa module có đang chạy ở đúng module chứa proto hay không.

Một lỗi dễ bỏ sót là sửa file trong thư mục tài liệu hoặc thư mục ví dụ, trong khi Gradle/Maven lại sinh mã từ một thư mục proto khác. Hãy xác nhận đường dẫn đầu vào từ cấu hình build và log của task sinh mã, thay vì chỉ dựa vào tên file.

### 2. Tạo lại mã từ đầu vào hiện tại

Mã trong thư mục generated là kết quả của build. Khi proto đổi, hãy chạy task sinh mã hoặc build sạch để loại bỏ đầu ra cũ.

Với Gradle và protobuf Gradle plugin:

```bash
# macOS / Linux
./gradlew clean generateProto compileJava

# Windows
gradlew.bat clean generateProto compileJava
```

Với Maven, khi plugin protobuf được gắn vào lifecycle `compile`:

```bash
mvn clean compile
```

Nếu dự án có task hoặc profile riêng cho việc sinh proto, hãy dùng đúng task/profile đã cấu hình. Một lần build sạch từ command line bằng Gradle Wrapper hoặc Maven Wrapper giúp xác định lỗi thuộc build hay chỉ thuộc cache/index của IDE.

Các thư mục đầu ra phổ biến là:

| Build tool | Message Java | gRPC Java |
| --- | --- | --- |
| Gradle protobuf plugin | `build/generated/source/proto/main/java` | `build/generated/source/proto/main/grpc` |
| protobuf-maven-plugin | `target/generated-sources/protobuf/java` | `target/generated-sources/protobuf/grpc-java` |

Đường dẫn có thể khác nếu dự án đổi source set, module, classifier hoặc cấu hình output. Kiểm tra cấu hình và log của build nếu không thấy các thư mục này.

Sau khi chạy, mở file được sinh và kiểm tra phần khai báo package, tên lớp, tên field và RPC có phản ánh proto đang dùng không. Đừng sửa trực tiếp file generated: lần build sau sẽ ghi đè và thay đổi sẽ không còn truy vết được từ hợp đồng.

### 3. Kiểm tra plugin sinh gRPC đã được bật

Nếu message Java xuất hiện nhưng không có lớp `*Grpc`, kiểm tra cấu hình plugin. Với Gradle protobuf plugin, cấu hình tối thiểu về ý tưởng gồm cả artifact `protoc`, plugin gRPC và việc gắn plugin vào các task sinh mã:

```groovy
plugins {
    id 'java'
    id 'com.google.protobuf' version '<protobuf-gradle-plugin-version>'
}

def protobufVersion = '<protobuf-version>'
def grpcVersion = '<grpc-version>'

dependencies {
    implementation "com.google.protobuf:protobuf-java:${protobufVersion}"
    implementation "io.grpc:grpc-protobuf:${grpcVersion}"
    implementation "io.grpc:grpc-stub:${grpcVersion}"
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:${protobufVersion}"
    }
    plugins {
        grpc {
            artifact = "io.grpc:protoc-gen-grpc-java:${grpcVersion}"
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
```

Đây là phần cấu hình minh họa cho một dự án dùng protobuf Gradle plugin trực tiếp. Nếu Spring gRPC starter hoặc dependency management của Spring Boot đã quản lý một số thư viện runtime, hãy giữ cách quản lý phiên bản thống nhất của dự án và chỉ bổ sung cấu hình sinh mã còn thiếu.

Với Maven, `protobuf-maven-plugin` cần chạy cả goal `compile` để sinh message và `compile-custom` để gọi plugin gRPC. Cấu hình thường có dạng:

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
  <executions>
    <execution>
      <goals>
        <goal>compile</goal>
        <goal>compile-custom</goal>
      </goals>
    </execution>
  </executions>
</plugin>
```

Ví dụ Maven trên dùng biến classifier theo hệ điều hành; dự án cần cấu hình extension cung cấp `${os.detected.classifier}` (thường là `os-maven-plugin`) và khai báo các property phiên bản tương ứng. Hãy đối chiếu với phiên bản plugin và quy ước hiện có của dự án trước khi sao chép cấu hình.

### 4. So khớp package và tên kiểu được sinh

Khi compiler báo `cannot find symbol` dù file generated có tồn tại, kiểm tra trực tiếp dòng `package` ở đầu file generated và đối chiếu với import trong code ứng dụng.

Ví dụ, nếu proto khai báo:

```proto
option java_package = "com.acme.inventory.api";
option java_multiple_files = true;
```

thì import message cần dùng package `com.acme.inventory.api`. Nếu `java_multiple_files` không bật, hãy kiểm tra lớp wrapper ngoài cùng và tham chiếu message theo cấu trúc lồng nhau được sinh ra.

Với service, kiểm tra đủ ba yếu tố: tên protobuf `package`, tên `service`, và tên RPC. Nếu client import đúng lớp nhưng gọi method không tồn tại, có thể client đang dùng stub được sinh từ một phiên bản proto khác hoặc từ một service khác có tên gần giống.

### 5. Đồng bộ phiên bản generator và runtime

Mã generated phụ thuộc vào API của thư viện protobuf và gRPC. Nếu generator và runtime lệch phiên bản, compiler có thể báo thiếu class/method hoặc mã sinh ra có thể không tương thích khi chạy.

Kiểm tra riêng các nhóm sau:

- Phiên bản `protoc` được build tool tải hoặc gọi.
- Phiên bản `protobuf-java` trên compile/runtime classpath.
- Phiên bản `protoc-gen-grpc-java` dùng để sinh stub.
- Các thư viện runtime `grpc-*` mà ứng dụng sử dụng, chẳng hạn `grpc-stub` và `grpc-protobuf`.
- Phiên bản Spring gRPC/Spring Boot BOM nếu dự án dùng dependency management để quản lý các thư viện trên.

Giữ `protoc` và `protobuf-java` trong dải phiên bản tương thích theo hướng dẫn của protobuf; giữ plugin `protoc-gen-grpc-java` cùng phiên bản với bộ thư viện gRPC Java runtime tương ứng. Không nâng riêng một dependency gRPC trong khi các dependency còn lại vẫn bị BOM hoặc một module khác khóa ở phiên bản cũ.

Có thể xem dependency tree để tìm nhiều phiên bản cùng xuất hiện:

```bash
# Gradle
./gradlew dependencies --configuration compileClasspath

# Maven
mvn dependency:tree -Dincludes=com.google.protobuf,io.grpc
```

Đối chiếu phiên bản thực tế trong dependency tree với phiên bản artifact được khai báo trong cấu hình generator. Việc chỉ xem phiên bản khai báo trong `build.gradle` hoặc `pom.xml` chưa đủ nếu dependency management hoặc dependency bắc cầu đã thay thế phiên bản khi resolve.

### 6. Kiểm tra lỗi `UNIMPLEMENTED` ở runtime

Nếu code client và server đều biên dịch nhưng lời gọi RPC trả về `UNIMPLEMENTED`, kiểm tra:

1. Client và server có được sinh từ đúng phiên bản proto hay không.
2. Tên protobuf `package`, tên `service` và tên RPC có khớp ở hai phía không.
3. Server có triển khai đúng lớp `*Grpc.*ImplBase` mới được sinh ra không.
4. Service implementation có được đăng ký vào Spring application context và được Spring gRPC đưa vào server không.
5. Client có đang kết nối đến đúng instance/môi trường server đã triển khai phiên bản mới không.

gRPC định danh method bằng đường dẫn có dạng `/package.Service/Method`. Vì thế, đổi protobuf package, service hoặc method có thể khiến client gọi một đường dẫn mà server cũ không phục vụ. Trong tình huống này, tạo lại mã ở client chưa đủ; cần build và triển khai server từ cùng hợp đồng đã thống nhất.

## Bảng tra cứu nhanh

| Triệu chứng | Nguyên nhân nên kiểm tra đầu tiên | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy lớp message mới | Build đọc nhầm proto hoặc chưa sinh lại mã | Xác nhận proto source, chạy clean và task sinh mã. |
| Có message nhưng thiếu `*Grpc` | Plugin `protoc-gen-grpc-java` chưa khai báo hoặc chưa gắn vào task | Kiểm tra plugin gRPC và task `compile-custom`/`generateProtoTasks`. |
| Import sai package | `java_package` hoặc `java_multiple_files` khác với giả định của code | Đọc package và cấu trúc lớp trong file generated rồi sửa import/cấu hình proto có chủ đích. |
| Field/method cũ vẫn còn | Đầu ra cũ, build sai module hoặc IDE đang dùng source generated cũ | Chạy clean bằng wrapper, kiểm tra output của đúng module, đồng bộ lại IDE. |
| Generated code không biên dịch | Runtime protobuf/gRPC không tương thích với generator | Kiểm tra dependency tree và đồng bộ phiên bản theo BOM/compatibility guidance. |
| Client nhận `UNIMPLEMENTED` | Client/server khác service name hoặc server chưa đăng ký RPC mới | So khớp package/service/method và xác nhận server đang chạy đúng bản build. |

## Ví dụ xử lý một thay đổi cụ thể

Giả sử nhóm thêm RPC `GetItem` vào `InventoryService`, nhưng IDE báo `getItem(...)` không tồn tại trên `InventoryServiceBlockingStub`.

1. Mở proto mà build đang sử dụng và xác nhận `rpc GetItem(...)` nằm trong đúng `service InventoryService`.
2. Kiểm tra task sinh gRPC đã chạy; nếu chỉ thấy `GetItemRequest.java` và `GetItemResponse.java` mà không có `InventoryServiceGrpc.java`, quay lại cấu hình plugin gRPC.
3. Chạy `clean` và sinh mã bằng wrapper của dự án.
4. Mở `InventoryServiceGrpc.java` vừa sinh, xác nhận có method tương ứng và kiểm tra package của lớp.
5. Kiểm tra compile classpath để bảo đảm `grpc-stub`, `grpc-protobuf` và plugin gRPC dùng các phiên bản tương thích.
6. Build lại module chứa server và xác nhận implementation kế thừa base class mới. Nếu client vẫn nhận `UNIMPLEMENTED`, xác nhận instance server mà client đang gọi đã được triển khai bản mới.

Quy trình này tách được ba câu hỏi: build có đọc đúng hợp đồng không, generator có tạo đúng API không, và server đang chạy có thực sự cung cấp API đó không.

## Phòng tránh lỗi tái diễn

- Đặt proto trong một source set rõ ràng và quản lý import proto qua dependency có version.
- Quản lý phiên bản protoc, plugin gRPC và runtime tập trung bằng property hoặc BOM phù hợp.
- Đưa bước sinh mã vào lifecycle build để CI luôn tạo mã từ proto trong cùng lần build.
- Không commit hoặc chỉnh tay generated source nếu quy ước dự án không yêu cầu; luôn coi proto và cấu hình generator là nguồn sự thật.
- Khi thay đổi `package`, `service`, `rpc` hoặc các tùy chọn Java, review ảnh hưởng đến cả import Java lẫn tương thích client/server.
- Trong CI, build sạch module chứa proto và chạy kiểm thử tích hợp có ít nhất một lời gọi RPC quan trọng.

Khi gặp mã generated không khớp proto, hãy xác nhận đúng đầu vào, tái sinh mã, kiểm tra cấu hình package/plugin, rồi mới kiểm tra phiên bản runtime và server đang chạy. Làm theo thứ tự này giúp khoanh vùng lỗi từ nguồn hợp đồng đến thời điểm RPC thực thi.

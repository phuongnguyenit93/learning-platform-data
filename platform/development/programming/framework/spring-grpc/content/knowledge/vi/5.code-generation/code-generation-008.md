# Đường dẫn proto và import path trong Spring gRPC

Trong dự án **Spring gRPC**, một tệp `.proto` có thể import message, enum hoặc service được khai báo ở tệp khác. Để `protoc` tìm đúng các tệp đó, build phải cung cấp **proto source root** và các **import path** chính xác. Sai import path khiến generation dừng trước khi Java compiler chạy; nhiều root chồng lấn còn có thể làm cùng một schema được nhận diện dưới các đường dẫn logic khác nhau.

Bài này tập trung vào cách tổ chức đường dẫn proto, viết câu lệnh `import`, cung cấp schema dùng chung và kiểm tra trên CLI, Gradle, Maven. Trọng tâm là **protoc tìm tệp nào và tìm từ đâu**.

## 1. Proto source root và import path

Một **proto source root** là thư mục gốc mà từ đó các đường dẫn trong câu lệnh `import` được phân giải. Với cấu trúc:

```text
src/main/proto/
├── common/
│   └── v1/
│       └── money.proto
└── orders/
    └── v1/
        └── order.proto
```

Nếu `order.proto` cần kiểu tiền tệ trong `money.proto`, khai báo:

```proto
syntax = "proto3";

package learning.orders.v1;

import "common/v1/money.proto";

message Order {
  string order_id = 1;
  learning.common.v1.Money total = 2;
}
```

Đường dẫn import `common/v1/money.proto` được tính **từ proto source root**, tức `src/main/proto` trong ví dụ. Nó không được tính từ thư mục chứa `order.proto`. Vì vậy, không viết `import "../common/v1/money.proto"` theo thói quen relative import của một số ngôn ngữ khác.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Proto source root | Thư mục được truyền qua `-I` hoặc `--proto_path` |
| Import path | Đường dẫn logic bên trong root, ghi trong chuỗi `import` |
| Input file path | Tệp `.proto` mà lệnh protoc được yêu cầu biên dịch |
| Protobuf package | Namespace của message/service trong hợp đồng |
| Java package | Package của generated Java classes, thường do `java_package` quyết định |

## 2. Chọn import root bằng protoc

Từ thư mục gốc dự án, lệnh minh họa:

```bash
protoc \
  -I=src/main/proto \
  --java_out=build/generated/java \
  orders/v1/order.proto
```

`-I` là dạng viết tắt của `--proto_path`. Khi protoc xử lý `orders/v1/order.proto`, nó hiểu tên tệp theo root đã cung cấp. Khi gặp `import "common/v1/money.proto"`, nó tìm `common/v1/money.proto` dưới root đó.

Nếu schema dùng thêm tệp ở thư mục khác, truyền nhiều root:

```bash
protoc \
  -I=src/main/proto \
  -I=third_party/proto \
  --java_out=build/generated/java \
  orders/v1/order.proto
```

Nếu tệp phụ nằm ở `third_party/proto/google/type/date.proto`, import là:

```proto
import "google/type/date.proto";
```

Đường dẫn trong `import` phải tương đối tới một root đã khai báo. Không đưa đường dẫn tuyệt đối của máy lập trình viên vào schema; dùng đường dẫn logic ổn định để mọi máy và CI có thể phân giải cùng một hợp đồng.

### Vì sao cần chọn root chung?

Nếu mọi proto nằm dưới `src/main/proto`, chỉ cần một `-I`. Không cần thêm từng thư mục con `common/v1` và `orders/v1`. Nếu chỉ truyền `-I=src/main/proto/orders/v1`, tệp có thể được nhận diện như `order.proto` thay vì `orders/v1/order.proto`; đường dẫn import chuẩn khi đó không còn khớp.

Hãy chọn root chung ổn định cho toàn bộ schema. Input file và các câu `import` nên được biểu diễn nhất quán theo root đó.

## 3. Proto path khác protobuf package và Java package

Ba khái niệm này độc lập:

| Khai báo | Ví dụ | Dùng để |
| --- | --- | --- |
| Đường dẫn file | `common/v1/money.proto` | Vị trí schema trong repository |
| Protobuf package | `learning.common.v1` | Namespace message/service và tên RPC đầy đủ |
| Java package | `vn.example.shared.money.v1` | Package của mã Java được sinh |

Ví dụ nội dung `money.proto`:

```proto
syntax = "proto3";

package learning.common.v1;

option java_package = "vn.example.shared.money.v1";
option java_multiple_files = true;

message Money {
  string currency_code = 1;
  int64 units = 2;
  int32 nanos = 3;
}
```

Dù file ở `common/v1/money.proto`, protobuf package là `learning.common.v1` và Java package là `vn.example.shared.money.v1`. Trong schema consumer, import theo đường dẫn từ root và tham chiếu type bằng protobuf namespace:

```proto
import "common/v1/money.proto";

message Order {
  learning.common.v1.Money total = 1;
}
```

Không viết `vn.example.shared.money.v1.Money` trong `.proto`; đó là tên Java xuất hiện sau generation. Thay đổi proto root không tự đổi Java package hoặc tên RPC; đổi protobuf package/service/method có thể đổi RPC path dù file vẫn nằm nguyên vị trí.

## 4. Tổ chức schema dùng chung

Với dịch vụ Spring gRPC, nên phân chia schema theo domain và version:

```text
src/main/proto/
├── common/v1/
│   ├── money.proto
│   └── pagination.proto
├── orders/v1/
│   └── order.proto
└── inventory/v1/
    └── stock.proto
```

Các consumer import bằng đường dẫn logic từ root:

- `orders/v1/order.proto` import `common/v1/money.proto`.
- `inventory/v1/stock.proto` import `common/v1/pagination.proto`.
- Các domain dùng chung một định nghĩa `Money` thay vì duy trì các bản sao tương tự.

Khi nhiều module dùng một schema, đặt nó trong thư mục hoặc artifact contract riêng rồi đưa vào import path của từng module. Tránh copy cùng một file proto sang nhiều nơi; các bản sao có thể lệch dần và làm client/server dùng schema khác nhau.

### Proto dependency khác Java dependency

Một thư viện proto dùng chung cần cung cấp **các tệp .proto với đường dẫn nội bộ ổn định**. Chỉ có generated Java JAR thường chưa đủ để protoc giải quyết câu `import`, trừ khi artifact cũng đóng gói proto resources hoặc build có cơ chế include tương ứng.

Ví dụ thư mục ngoài source root chính:

```text
third_party/proto/
└── acme/
    └── identity/v1/
        └── identity.proto
```

Schema consumer viết:

```proto
import "acme/identity/v1/identity.proto";
```

CLI cần thêm `-I=third_party/proto`. Với Gradle/Maven, cần cấu hình include path hoặc proto dependency theo plugin đang dùng. Nếu generated code tham chiếu Java class của dependency đó, ứng dụng còn phải khai báo Java artifact tương ứng trên compile classpath. **Cung cấp proto source và cung cấp Java classes là hai việc khác nhau.**

## 5. Well-known types và schema bên ngoài

Protocol Buffers có một số schema chuẩn như:

- `google/protobuf/timestamp.proto`
- `google/protobuf/duration.proto`
- `google/protobuf/empty.proto`
- `google/protobuf/struct.proto`

Ví dụ:

```proto
syntax = "proto3";

package learning.orders.v1;

import "google/protobuf/timestamp.proto";

message OrderEvent {
  string order_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
}
```

Các tệp well-known types thường đi cùng bản phân phối protoc và được protobuf Java runtime hỗ trợ. Nếu protoc báo không tìm thấy `google/protobuf/timestamp.proto`, hãy kiểm tra include files của binary và import roots mà build plugin cung cấp; không tự tạo một schema giả để né lỗi.

Các schema như Google API annotations hoặc proto của thư viện bên ngoài có thể không nằm trong include mặc định. Cần lấy dependency chứa proto nguồn và thêm đúng root vào import path. Thêm Java artifact vào `implementation` không tự làm cho tệp proto xuất hiện trong include path của protoc.

## 6. Cấu hình proto root và dependency trong Gradle

Với protobuf Gradle plugin, main proto source mặc định là `src/main/proto`. Nếu cần thêm thư mục schema:

```groovy
sourceSets {
    main {
        proto {
            srcDir 'src/shared-proto'
        }
    }
}
```

Cấu hình này bổ sung `src/shared-proto` vào proto sources của main. Import path được phân giải từ các roots mà plugin truyền cho protoc; chuỗi import phải tương ứng với cấu trúc bên trong các roots đó.

Nếu thư viện proto đóng gói file .proto trong JAR, protobuf Gradle plugin hỗ trợ configuration `protobuf` để cung cấp proto files cho generation:

```groovy
dependencies {
    // JAR cần chứa proto resources theo đường dẫn import đã thống nhất.
    protobuf files('libs/shared-protos.jar')

    // Nếu generated Java cần class từ thư viện này,
    // khai báo Java artifact trên compile classpath.
    implementation files('libs/shared-protos-java.jar')
}
```

Hai cấu hình có ý nghĩa khác nhau:

- `protobuf` cung cấp schema nguồn để protoc tìm import.
- `implementation` cung cấp class/library cho Java compiler và runtime.

Không phải mọi Java JAR đều chứa proto files. Xác nhận nội dung artifact và đường dẫn nội bộ trước khi thêm dependency. Nếu dùng source set tùy chỉnh, gắn proto roots và dependency scope vào đúng source set; không đưa test-only schema vào main chỉ để import hoạt động.

Kiểm tra bằng task thực tế:

```bash
./gradlew generateProto
./gradlew compileJava
```

Nếu CLI chạy được nhưng Gradle lỗi, hãy kiểm tra proto source directories và dependencies mà task generation nhận được; đừng giả định Gradle dùng đúng mọi `-I` bạn đã truyền ở một lần chạy protoc thủ công.

## 7. Cấu hình proto root bổ sung trong Maven

Với `protobuf-maven-plugin`, proto source root mặc định thường là `src/main/proto`. Khi có thư mục include bổ sung, có thể cấu hình plugin để thêm proto path. Ví dụ minh họa cho phiên bản plugin hỗ trợ `additionalProtoPathElements`:

```xml
<configuration>
    <protoSourceRoot>
        ${project.basedir}/src/main/proto
    </protoSourceRoot>
    <additionalProtoPathElements>
        <additionalProtoPathElement>
            ${project.basedir}/third_party/proto
        </additionalProtoPathElement>
    </additionalProtoPathElements>
    <protocArtifact>
        com.google.protobuf:protoc:4.30.2:exe:${os.detected.classifier}
    </protocArtifact>
    <pluginId>grpc-java</pluginId>
    <pluginArtifact>
        io.grpc:protoc-gen-grpc-java:1.71.0:exe:${os.detected.classifier}
    </pluginArtifact>
</configuration>
```

Tham số include cần đối chiếu với phiên bản `protobuf-maven-plugin` của dự án. Nếu plugin version không hỗ trợ cấu hình đó, dùng đúng cơ chế include/dependency mà phiên bản hiện tại cung cấp; không thêm XML element không được nhận diện.

Chạy generation và compilation:

```bash
mvn generate-sources
mvn compile
```

Nếu import không tìm thấy, xem log lệnh protoc mà Maven plugin thực thi để xác nhận root thực tế, working directory, proto source root và thư mục bổ sung.

## 8. Kiểm thử import path bằng CLI

Một cách nhanh để tách lỗi đường dẫn khỏi lỗi Spring là chạy protoc trực tiếp. Với:

```text
src/main/proto/
├── common/v1/money.proto
└── orders/v1/order.proto
```

Chạy từ project root:

```bash
protoc \
  -I=src/main/proto \
  --descriptor_set_out=build/order-descriptor.pb \
  --include_imports \
  orders/v1/order.proto
```

Nếu command thành công, protoc đã tìm được input file và các import được tham chiếu. `--include_imports` khiến descriptor set chứa descriptor phụ thuộc, hữu ích để xác minh import graph. Bước này chưa sinh Java, chưa gọi gRPC plugin và chưa kiểm tra runtime.

Để kiểm tra generation Java và gRPC plugin:

```bash
protoc \
  -I=src/main/proto \
  --java_out=build/generated/java \
  --plugin=protoc-gen-grpc-java=/path/to/protoc-gen-grpc-java \
  --grpc-java_out=build/generated/grpc \
  orders/v1/order.proto
```

Nếu plugin nằm trong `PATH` với tên quy ước, có thể bỏ `--plugin`. Trong dự án thật, nên để Gradle/Maven quản lý binary thay vì hardcode đường dẫn máy cá nhân.

## 9. Lỗi import path thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `File does not reside within any path specified using --proto_path` | Input file không nằm dưới proto root | Bổ sung đúng `-I` hoặc dùng input path tương đối với root |
| `Import "common/v1/money.proto" was not found` | Root không chứa đường dẫn logic đó | Kiểm tra cấu trúc thư mục và import string |
| `Import "google/protobuf/timestamp.proto" was not found` | Thiếu well-known type include hoặc protoc distribution không đầy đủ | Kiểm tra protoc artifact và include files |
| CLI chạy được nhưng Gradle/Maven lỗi | Build plugin không truyền cùng include roots | Xem source root, dependency và log command protoc |
| Developer chạy được nhưng CI lỗi | Import dựa vào file ngoài repository hoặc path cục bộ | Đưa proto dependency vào repository/artifact được quản lý |
| Windows chạy được, Linux CI lỗi | Sai chữ hoa/thường của tên file/đường dẫn | Đảm bảo import path khớp chính xác case của file |
| Một proto bị nhận dưới hai tên logic | Roots chồng lấn hoặc import cùng file bằng hai path | Chuẩn hóa canonical import path |
| Java package đúng nhưng import proto lỗi | Nhầm `java_package` với proto include path | Kiểm tra `-I` và chuỗi `import` |

### Canonical import path

Một schema nên được import bằng **một đường dẫn logic thống nhất**. Nếu file nằm tại `src/main/proto/common/v1/money.proto`, mọi consumer nên dùng `common/v1/money.proto`. Không tạo thêm root ở `src/main/proto/common` rồi import cùng file như `v1/money.proto` ở nơi khác.

Nhiều root chồng lấn và một file xuất hiện dưới các tên logic khác nhau làm khó kiểm soát descriptor, có thể gây duplicate definitions hoặc khác biệt giữa máy phát triển và CI. Dùng một root chung, tránh shadowing cùng tên import và không duy trì nhiều bản sao schema.

## 10. Quy trình kiểm thử thực tế

Khi thêm import mới vào một dịch vụ Spring gRPC:

1. Đặt tệp phụ thuộc dưới proto root đã thống nhất, ví dụ `src/main/proto/common/v1/money.proto`.
2. Trong schema consumer, dùng `import "common/v1/money.proto";`.
3. Chạy protoc với `-I` trỏ đến root và xuất descriptor set có `--include_imports`.
4. Chạy Gradle `generateProto` hoặc Maven `generate-sources` để kiểm tra build plugin truyền đúng include paths.
5. Chạy Java compile để xác nhận generated classes và Java dependencies đều có mặt.
6. Chạy integration test gọi RPC sử dụng message được import; kiểm tra success và lỗi nghiệp vụ.
7. Chạy cùng build trên CI hoặc môi trường sạch để chắc chắn không phụ thuộc đường dẫn cục bộ.

Một test nhỏ xác nhận message import đã sinh có thể được sử dụng:

```java
import org.junit.jupiter.api.Test;
import vn.example.shared.money.v1.Money;
import vn.example.springgrpc.orders.v1.Order;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderProtoImportTest {

    @Test
    void importedMessageCanBeUsed() {
        Money money = Money.newBuilder()
                .setCurrencyCode("VND")
                .setUnits(125_000)
                .build();

        Order order = Order.newBuilder()
                .setOrderId("ORD-100")
                .setTotal(money)
                .build();

        assertEquals("VND",
                order.getTotal().getCurrencyCode());
    }
}
```

Ví dụ giả định `Money` và `Order` được sinh từ hai proto có `java_package` tương ứng. Test xác nhận Java generated types nhìn thấy nhau trên compile/test classpath; nó **không** thay thế kiểm tra import path của protoc. Muốn xác nhận import path, phải chạy generation từ schema và build plugin thực tế.

## 11. Bài tập tự kiểm tra

1. Tạo `common/v1/money.proto` và `orders/v1/order.proto` dưới `src/main/proto`. Import `Money` từ `Order` bằng đường dẫn tính từ root.
2. Chạy protoc mà không truyền `-I=src/main/proto`. Đọc lỗi và giải thích vì sao input/import không được resolve.
3. Thêm `-I=third_party/proto` và import một file phụ trong thư mục đó. Xác nhận đường dẫn import bắt đầu từ root mới.
4. Giữ nguyên protobuf package nhưng đổi `java_package`. Quan sát Java import thay đổi trong khi protobuf import path không đổi.
5. Cấu hình Gradle `sourceSets.main.proto.srcDir` để thêm root phụ, sau đó chạy `generateProto`.
6. Đưa proto resources vào JAR và cung cấp qua cấu hình `protobuf` của Gradle. Phân biệt dependency schema với dependency Java generated classes.
7. Cấu hình Maven include root bổ sung theo phiên bản plugin đang dùng; xác nhận log protoc chứa root cần thiết.
8. Tạo hai đường dẫn logic khác nhau cùng trỏ đến một schema qua roots chồng lấn. Nhận diện vấn đề và chuẩn hóa canonical import path.
9. Chạy generation trên Windows và Linux CI để phát hiện sai khác chữ hoa/thường.
10. Viết test sử dụng message import và integration test gọi RPC nhận message đó; phân biệt điều gì được xác minh ở từng test.

### Ghi nhớ

**Import path được phân giải tương đối từ proto source roots, không phải từ Java package và cũng không mặc định tương đối với thư mục của tệp đang import.** Dùng `-I`/`--proto_path` trong protoc, khai báo proto roots/dependencies đúng source set trong Gradle hoặc include roots tương ứng trong Maven. Chuẩn hóa canonical import path, quản lý schema phụ thuộc có phiên bản và kiểm tra generation trên môi trường sạch để client/server Spring gRPC luôn dùng cùng hợp đồng.

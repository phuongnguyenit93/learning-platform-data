# Cấu hình Spring client channel

Trong dự án này, bạn sẽ xây dựng một gRPC client trong ứng dụng Spring Boot và quản lý `ManagedChannel` bằng Spring container. Client sẽ đọc địa chỉ đích và các giới hạn từ cấu hình, chọn transport security theo profile, tái sử dụng channel để gọi RPC và đặt deadline cho từng lời gọi.

Mục tiêu là tạo một cấu hình có thể dùng trong ứng dụng thật: channel có vòng đời rõ ràng, stub được inject vào service, môi trường local có thể chạy plaintext, môi trường triển khai dùng TLS, và lỗi kết nối có thể được phân loại khi vận hành. Ví dụ dùng grpc-java API tích hợp trực tiếp với Spring Boot; nếu dự án đã chuẩn hóa một Spring gRPC starter thì có thể dùng cơ chế channel factory tương ứng, nhưng không trộn hai cách quản lý cùng một channel.

## Kết quả cần đạt

Sau khi hoàn thành, ứng dụng cần đáp ứng các điều kiện sau:

- Đọc target, chế độ plaintext/TLS và giới hạn message từ `application.yml`.
- Tạo một `ManagedChannel` dùng chung trong vòng đời Spring application context.
- Tạo generated stub từ channel và inject vào client service.
- Đặt deadline cho mỗi RPC thay vì chờ vô hạn.
- Đóng channel khi Spring context dừng.
- Có thể đổi endpoint và chế độ bảo mật theo profile mà không sửa code nghiệp vụ.
- Có kiểm thử cho lời gọi thành công, status lỗi và vòng đời channel.

## 1. Chuẩn bị dự án

Ví dụ giả định dùng Java 17 trở lên và Spring Boot 3.x. Hãy dùng phiên bản grpc-java/protobuf tương thích với Java, Spring Boot và toolchain đang được dự án quản lý; các module grpc-java nên được căn phiên bản bằng BOM thay vì khai báo phiên bản rời rạc cho từng dependency.

Các dependency runtime chính:

```xml
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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>io.grpc</groupId>
        <artifactId>grpc-netty-shaded</artifactId>
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

`grpc.version` cần được khai báo trong phần properties hoặc dependency management chung của dự án theo phiên bản đã chọn. Nếu dự án chưa có bước sinh mã protobuf, có thể cấu hình Maven plugin như sau; các property version cần được khóa theo toolchain mà dự án đã kiểm tra tương thích:

```xml
<properties>
    <grpc.version>REPLACE_WITH_COMPATIBLE_VERSION</grpc.version>
    <protobuf.version>REPLACE_WITH_COMPATIBLE_VERSION</protobuf.version>
    <os.maven.plugin.version>REPLACE_WITH_COMPATIBLE_VERSION</os.maven.plugin.version>
    <protobuf.maven.plugin.version>REPLACE_WITH_COMPATIBLE_VERSION</protobuf.maven.plugin.version>
</properties>

<build>
    <extensions>
        <extension>
            <groupId>kr.motd.maven</groupId>
            <artifactId>os-maven-plugin</artifactId>
            <version>${os.maven.plugin.version}</version>
        </extension>
    </extensions>
    <plugins>
        <plugin>
            <groupId>org.xolstice.maven.plugins</groupId>
            <artifactId>protobuf-maven-plugin</artifactId>
            <version>${protobuf.maven.plugin.version}</version>
            <configuration>
                <protocArtifact>com.google.protobuf:protoc:${protobuf.version}:exe:${os.detected.classifier}</protocArtifact>
                <pluginId>grpc-java</pluginId>
                <pluginArtifact>io.grpc:protoc-gen-grpc-java:${grpc.version}:exe:${os.detected.classifier}</pluginArtifact>
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
    </plugins>
</build>
```

Nếu dự án đã có quy trình sinh mã, tiếp tục dùng quy trình đó và bảo đảm generated code tương thích với runtime.

Tạo cấu trúc tối thiểu:

```text
src/main/
├── proto/
│   └── catalog.proto
├── java/com/example/catalog/
│   ├── CatalogClientApplication.java
│   ├── config/
│   │   ├── CatalogGrpcClientProperties.java
│   │   └── CatalogGrpcClientConfiguration.java
│   └── client/
│       └── CatalogClient.java
└── resources/
    ├── application.yml
    └── application-local.yml
```

Lớp khởi động Spring Boot chỉ cần đăng ký component scan cho package chứa client và cấu hình:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogClientApplication.class, args);
    }
}
```

## 2. Khai báo hợp đồng protobuf

Tạo `src/main/proto/catalog.proto`:

```protobuf
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "com.example.catalog.grpc";
option java_outer_classname = "CatalogProto";

service Catalog {
  rpc GetCatalog (CatalogRequest) returns (CatalogReply);
}

message CatalogRequest {
  string catalog_id = 1;
}

message CatalogReply {
  string catalog_id = 1;
  string display_name = 2;
}
```

Chạy bước generate code của build để tạo `CatalogGrpc`, `CatalogRequest` và `CatalogReply` trong package `com.example.catalog.grpc`. Client chỉ phụ thuộc vào các class được sinh từ hợp đồng; không tự tạo class message thay thế protobuf.

## 3. Đưa cấu hình vào Spring properties

Tạo `CatalogGrpcClientProperties.java`:

```java
package com.example.catalog.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.grpc.client")
public class CatalogGrpcClientProperties {

    @NotBlank
    private String target;

    private boolean usePlaintext;

    @Min(1024)
    private int maxInboundMessageSize = 4 * 1024 * 1024;

    public String getTarget() {
        return target;
    }

    public void setTarget(String target) {
        this.target = target;
    }

    public boolean isUsePlaintext() {
        return usePlaintext;
    }

    public void setUsePlaintext(boolean usePlaintext) {
        this.usePlaintext = usePlaintext;
    }

    public int getMaxInboundMessageSize() {
        return maxInboundMessageSize;
    }

    public void setMaxInboundMessageSize(int maxInboundMessageSize) {
        this.maxInboundMessageSize = maxInboundMessageSize;
    }
}
```

`@ConfigurationProperties` gom các thuộc tính liên quan đến một client vào một kiểu dữ liệu có thể kiểm tra. `@NotBlank` buộc target phải có giá trị; `@Min` ngăn cấu hình giới hạn message quá nhỏ hoặc không hợp lệ theo quy ước của ví dụ. `usePlaintext` mặc định là `false`, vì vậy cấu hình mặc định yêu cầu transport security.

## 4. Cấu hình channel thành Spring bean

Tạo `CatalogGrpcClientConfiguration.java`:

```java
package com.example.catalog.config;

import com.example.catalog.grpc.CatalogGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogGrpcClientProperties.class)
public class CatalogGrpcClientConfiguration {

    @Bean(name = "catalogChannel", destroyMethod = "shutdown")
    public ManagedChannel catalogChannel(CatalogGrpcClientProperties properties) {
        ManagedChannelBuilder<?> builder = ManagedChannelBuilder
            .forTarget(properties.getTarget())
            .maxInboundMessageSize(properties.getMaxInboundMessageSize());

        if (properties.isUsePlaintext()) {
            builder.usePlaintext();
        } else {
            builder.useTransportSecurity();
        }

        return builder.build();
    }

    @Bean
    public CatalogGrpc.CatalogBlockingStub catalogBlockingStub(
            @Qualifier("catalogChannel") ManagedChannel channel) {
        return CatalogGrpc.newBlockingStub(channel);
    }
}
```

Spring tạo channel một lần khi cần bean và tái sử dụng nó cho các RPC. `destroyMethod = "shutdown"` yêu cầu Spring bắt đầu đóng channel khi application context được hủy. `shutdown()` ngừng nhận lời gọi mới và cho các RPC đang chạy cơ hội kết thúc; nếu ứng dụng cần một thời gian drain được kiểm soát chặt, hãy bổ sung chính sách chờ `awaitTermination` trong quy trình shutdown của ứng dụng.

`maxInboundMessageSize` là giới hạn message mà client nhận, thường áp dụng cho response từ server. Nó không phải giới hạn tổng dữ liệu của stream và không thay thế giới hạn buffer ở tầng ứng dụng.

## 5. Cấu hình endpoint theo môi trường

Trong `application.yml`, khai báo target mặc định và giữ TLS là lựa chọn mặc định:

```yaml
spring:
  application:
    name: catalog-client

catalog:
  grpc:
    client:
      target: "${CATALOG_GRPC_TARGET:dns:///catalog.internal:8443}"
      use-plaintext: false
      max-inbound-message-size: 4194304
```

Trong `application-local.yml`, bật plaintext chỉ cho server local:

```yaml
catalog:
  grpc:
    client:
      target: dns:///localhost:9090
      use-plaintext: true
```

Kích hoạt profile local khi chạy máy phát triển, ví dụ bằng biến môi trường `SPRING_PROFILES_ACTIVE=local`. Môi trường staging/production nên đặt `CATALOG_GRPC_TARGET` tới endpoint thật và giữ `use-plaintext: false`. Không bật plaintext trên mạng production hoặc mạng có dữ liệu nhạy cảm.

Với TLS, chứng thư server phải được client tin cậy và tên host trong chứng thư phải khớp với target kết nối. Nếu hạ tầng dùng private CA hoặc mutual TLS, cấu hình trust certificate và client certificate bằng transport builder phù hợp, chẳng hạn `NettyChannelBuilder` cùng `GrpcSslContexts`; không tắt xác minh chứng thư để né lỗi handshake.

## 6. Inject stub và gọi RPC có deadline

Tạo `CatalogClient.java`:

```java
package com.example.catalog.client;

import com.example.catalog.grpc.CatalogGrpc;
import com.example.catalog.grpc.CatalogReply;
import com.example.catalog.grpc.CatalogRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Service
public class CatalogClient {

    private final CatalogGrpc.CatalogBlockingStub stub;

    public CatalogClient(CatalogGrpc.CatalogBlockingStub stub) {
        this.stub = stub;
    }

    public CatalogReply getCatalog(String catalogId) {
        CatalogRequest request = CatalogRequest.newBuilder()
            .setCatalogId(catalogId)
            .build();

        try {
            return stub
                .withDeadlineAfter(2, TimeUnit.SECONDS)
                .getCatalog(request);
        } catch (StatusRuntimeException exception) {
            Status.Code code = Status.fromThrowable(exception).getCode();
            // Ghi nhận code và request/trace ID; không log token hoặc payload nhạy cảm.
            // Chuyển đổi sang exception nghiệp vụ tại ranh giới phù hợp nếu cần.
            throw exception;
        }
    }
}
```

Stub grpc-java là immutable; `withDeadlineAfter` tạo một stub dẫn xuất với `CallOptions` mới cho lời gọi đó. Vì vậy có thể dùng chung stub được inject, đồng thời đặt deadline khác nhau theo từng thao tác. Deadline hai giây chỉ là giá trị minh họa: hãy tính theo ngân sách latency của request đầu cuối và thời gian mà server cần để hoàn thành.

`Status.fromThrowable` giúp phân loại status mà không phải phân tích chuỗi message. Ví dụ, `UNAVAILABLE` có thể là lỗi kết nối tạm thời, `DEADLINE_EXCEEDED` cho biết ngân sách thời gian đã hết, `UNAUTHENTICATED`/`PERMISSION_DENIED` liên quan xác thực hoặc quyền, còn `RESOURCE_EXHAUSTED` có thể là giới hạn message hoặc quota. Chỉ retry khi lỗi có thể phục hồi và thao tác an toàn khi thực hiện lại; dùng backoff, jitter và giới hạn số lần thử.

## 7. Thêm interceptor khi cần metadata dùng chung

Nếu mọi RPC cần correlation ID hoặc trace metadata, có thể đăng ký `ClientInterceptor` trên channel builder trước khi gọi `build()`:

```java
ManagedChannelBuilder<?> builder = ManagedChannelBuilder
    .forTarget(properties.getTarget())
    .intercept(correlationIdClientInterceptor);
```

Interceptor chỉ nên bổ sung metadata thực sự dùng chung. Token xác thực theo từng người dùng nên được cung cấp qua cơ chế credential hoặc security context của request, tránh lưu một token người dùng vào channel dùng chung. Không ghi giá trị authorization vào log. Nếu có nhiều client channel, dùng qualifier riêng cho từng channel và stub để tránh inject nhầm đích.

## 8. Kiểm thử cấu hình

Tổ chức kiểm thử thành ba lớp:

| Loại kiểm thử | Cách thực hiện | Điều cần xác minh |
|---|---|---|
| Binding/configuration test | Tạo Spring context với target và chế độ transport cụ thể | Properties được bind, validation hoạt động và channel được tạo |
| In-process gRPC test | Dùng `InProcessServerBuilder` và `InProcessChannelBuilder` cùng service giả | Stub gọi đúng method, truyền request và nhận response; không cần socket thật |
| Transport integration test | Chạy server thật với TLS hoặc plaintext trong môi trường kiểm thử | DNS/target, certificate, handshake, timeout và cấu hình mạng hoạt động |

Với in-process test, thêm dependency `grpc-inprocess` cùng phiên bản grpc-java đã chọn ở scope test. Có thể đăng ký một implementation giả của service `Catalog` để trả `CatalogReply` cố định. Khi kiểm thử deadline, làm cho service giả phản hồi chậm hơn deadline và xác minh client nhận `DEADLINE_EXCEEDED`. Khi kiểm thử lỗi, cho service trả status có chủ đích và xác minh client phân loại đúng code.

Các kiểm tra nên có:

1. Application context khởi động thành công khi target hợp lệ.
2. Target rỗng hoặc cấu hình không hợp lệ làm ứng dụng báo lỗi sớm.
3. Nhiều lời gọi dùng cùng một channel bean; không tạo channel mới trong mỗi request.
4. RPC thành công trả về đúng dữ liệu protobuf.
5. RPC chậm vượt deadline trả `DEADLINE_EXCEEDED`.
6. Server không sẵn sàng trả status phù hợp và log có trace/request ID để điều tra.
7. Khi Spring context đóng, channel được shutdown.
8. Profile local bật plaintext; profile production giữ transport security.

## 9. Chạy và kiểm tra dự án

1. Xác nhận bước generate protobuf tạo ra `CatalogGrpc` và các message Java.
2. Khởi chạy một gRPC server có triển khai `Catalog/GetCatalog` tại target được cấu hình.
3. Chạy Spring Boot với profile local hoặc cấu hình endpoint staging đã cấp chứng thư hợp lệ.
4. Gọi `CatalogClient.getCatalog("books")` từ controller, command-line runner hoặc integration test.
5. Kiểm tra response, deadline, status khi server dừng và log khi kết nối lỗi.
6. Dừng Spring application và xác minh channel được đóng.

Nếu chưa có server, có thể dùng in-process test server để hoàn thành phần kiểm thử client trước. Không dùng plaintext trên môi trường triển khai thật chỉ để làm cho kết nối chạy được.

## 10. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `UNAVAILABLE` khi khởi động RPC | Sai target/port, DNS không phân giải hoặc server chưa lắng nghe | Kiểm tra target, DNS, port và trạng thái server |
| TLS handshake thất bại | CA không được tin cậy, chứng thư hết hạn hoặc hostname không khớp | Kiểm tra trust chain, SAN, thời hạn chứng thư và cấu hình mTLS |
| `DEADLINE_EXCEEDED` | Deadline quá ngắn, server chậm hoặc dependency downstream bị nghẽn | Đối chiếu latency từng chặng và ngân sách deadline |
| `RESOURCE_EXHAUSTED` khi nhận response | Response vượt giới hạn inbound của client hoặc quota bị áp dụng | Đo kích thước message, kiểm tra receiver limit và quota |
| Mỗi request lại mở kết nối mới | Channel được tạo bên trong method xử lý request | Đưa channel thành Spring singleton bean và inject stub |
| Ứng dụng treo khi dừng | RPC/stream còn hoạt động hoặc shutdown không có thời hạn | Dừng nhận request mới, đặt deadline và drain RPC trước khi kết thúc |

## Tiêu chí hoàn thành

- [ ] Generated stub được sinh từ `catalog.proto` và compile cùng runtime grpc-java tương thích.
- [ ] `CatalogGrpcClientProperties` bind và validate cấu hình.
- [ ] `ManagedChannel` được tạo thành Spring bean, tái sử dụng và shutdown theo lifecycle.
- [ ] Blocking stub được inject vào `CatalogClient`.
- [ ] Mỗi RPC có deadline và status được phân loại bằng `Status.fromThrowable`.
- [ ] Local profile dùng plaintext; cấu hình mặc định/production dùng TLS.
- [ ] Có kiểm thử thành công, lỗi status, deadline và channel shutdown.

Khi dự án hoàn thành, việc đổi endpoint, giới hạn message hoặc transport mode chỉ cần thay đổi cấu hình theo môi trường. Client service tập trung vào hợp đồng RPC và xử lý kết quả; Spring container chịu trách nhiệm tạo, chia sẻ và đóng channel đúng vòng đời ứng dụng.

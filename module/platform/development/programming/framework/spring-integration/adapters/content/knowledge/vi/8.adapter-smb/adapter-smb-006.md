# Đường dẫn UNC và ánh xạ thư mục trong Spring Integration SMB

## 1. Bài toán và mục tiêu

Đối tác cung cấp thư mục Windows share:

```text
\\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv
```

Ứng dụng Spring Boot cần lấy tệp CSV này về máy chạy ứng dụng để nhập dữ liệu; sau khi nhập xong, ứng dụng lại xuất một tệp xác nhận tới:

```text
\\fs01.corp.example\exchange\outgoing\partner-a\orders-20261123.ack
```

Khi lập trình, ta phải trả lời các câu hỏi cụ thể: phần nào là **máy chủ**, phần nào là **share**, phần nào là **thư mục remote**? Trên Linux container không có ổ `Z:` như máy nhân viên Windows thì tải file về đâu? Nếu một adapter đang trỏ vào share `exchange`, tại sao không được lặp `exchange` trong cấu hình `remoteDirectory`? Làm sao ánh xạ đúng tệp giữa các thư mục `incoming/outgoing/archive` mà không ghi nhầm dữ liệu của đối tác khác?

Bài thuộc chương **Adapter SMB** của module `SPRING_INTEGRATION_ADAPTERS`. Module hướng tới việc kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành luồng file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, cũng như hợp đồng message, lỗi và vòng đời kết nối. Ở đây, trọng tâm là **đường dẫn UNC và quy tắc ánh xạ đường dẫn remote ↔ local** khi sử dụng Spring Integration SMB.

Sau bài học, bạn có thể:

- Phân tích đường dẫn UNC `\\server\share\folder\file` thành host, share, remote directory và file name.
- Phân biệt UNC, URI `smb://`, đường dẫn local trên Windows/Linux và ổ đĩa đã map.
- Cấu hình `SmbSessionFactory.setShareAndDir(...)`, `remoteDirectory(...)`, `localDirectory(...)` chính xác.
- Vẽ được đường đi của `Message<File>` khi SMB inbound tải tệp về local và khi outbound ghi lên share.
- Dùng outbound gateway cho các thao tác theo đường dẫn như `ls/get/mv`, kể cả trường hợp thư mục phân cấp.
- Thiết kế ánh xạ theo đối tác, tránh tên trùng, traversal, nhầm share và mất metadata nguồn.
- Kiểm tra lỗi đường dẫn, quyền đọc/ghi, ký tự phân cách và khác biệt môi trường Windows/Linux.

## 2. Cấu trúc của đường dẫn UNC

**UNC (Universal Naming Convention)** là cách biểu diễn tài nguyên mạng trong Windows. Dạng phổ biến:

```text
\\server\share\directory\subdirectory\filename.ext
  └──┘  └──┘ └──────────────────┘ └────────┘
   host  share  đường dẫn trong share   tên file
```

Với ví dụ:

```text
\\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv
```

ta tách được:

| Thành phần | Giá trị | Vai trò |
|---|---|---|
| Server/host | `fs01.corp.example` | Máy chủ SMB, DNS hoặc IP có thể kết nối |
| Port | `445` (thường gặp) | Cổng SMB qua TCP; không nằm trong đường dẫn UNC thông thường |
| Share | `exchange` | Tên tài nguyên được chia sẻ trên server |
| Thư mục remote | `incoming/partner-a` | Đường dẫn con tương đối trong share |
| File name | `orders-20261123.csv` | Tên tệp cần đọc |
| UNC đầy đủ | `\\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv` | Cách Windows thể hiện vị trí tài nguyên |

Hai dấu `\\` đầu là ký hiệu UNC; những dấu `\` tiếp theo phân cách thành phần trên Windows. Khi ghi **chuỗi ký tự Java**, dấu `\` phải được escape:

```java
String unc = "\\\\fs01.corp.example\\exchange\\incoming\\partner-a\\orders-20261123.csv";
System.out.println(unc);
// \\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv
```

Chuỗi Java này chỉ là cách **biểu diễn** UNC. Trong Spring Integration SMB, thông thường ta không cần truyền nguyên chuỗi này vào adapter. Ta cấu hình host/share cho `SmbSessionFactory`, còn thư mục và tên file cho endpoint.

### 2.1. UNC và URI SMB khác nhau

Một SMB client có thể diễn đạt cùng tài nguyên qua dạng URI:

```text
UNC:     \\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv
SMB URI: smb://fs01.corp.example/exchange/incoming/partner-a/orders-20261123.csv
```

URI dùng dấu `/`; ký tự đặc biệt cần được mã hóa đúng quy tắc URI. Spring Integration dùng thư viện Java CIFS/SMB bên dưới; lớp `SmbConfig` chứa host, domain, credential và `shareAndDir` để xây dựng thông tin kết nối. **Không tự tạo URI có nhúng password để đưa vào log hoặc cấu hình công khai.**

Ví dụ định dạng URI ở trên chỉ dùng để hình dung điểm đến; code dùng các setter của `SmbSessionFactory`. Domain/tài khoản xác thực là thông tin **riêng**, không phải tên thư mục hoặc tên share:

```text
host     = fs01.corp.example
share    = exchange
domain   = CORP
username = svc_smb_integration
password = <secret từ hệ thống cấu hình>
```

### 2.2. Các đường dẫn dễ bị nhầm

| Giá trị | Định dạng | Có phải tham số remoteDirectory của SMB adapter? |
|---|---|---|
| `\\fs01\exchange\incoming` | UNC của Windows | **Không**. Đây là toàn bộ host/share/path |
| `smb://fs01/exchange/incoming` | URI của client SMB | **Không** cho trường `remoteDirectory` trong cấu hình mẫu |
| `incoming/partner-a` | Đường dẫn tương đối bên trong share | **Có**, khi factory đã trỏ tới share `exchange` |
| `C:/app/data/smb-inbox` | Đường dẫn local trên Windows | Dùng cho `localDirectory` |
| `/var/lib/app/smb-inbox` | Đường dẫn local trên Linux | Dùng cho `localDirectory` |
| `Z:\incoming` | Đường dẫn ổ mạng map trong một phiên Windows | Không nên dựa vào trong client Spring Integration SMB |

**Sai lầm phổ biến:** dùng `remoteDirectory("\\\\fs01\\exchange\\incoming")` khi factory đã có host/share. Khi đó endpoint có thể ghép sai path hoặc tìm một thư mục không tồn tại. Tham số remote cần bám theo **gốc đã cấu hình cho session**.

## 3. Chọn một điểm gốc nhất quán

Trong các ví dụ của bài, ta quy ước:

```text
Windows File Server: fs01.corp.example
Share:               exchange
Inbound directory:   incoming/partner-a
Outbound directory:  outgoing/partner-a
Archive directory:   archive/partner-a
Local inbound dir:   ./data/smb-inbox/partner-a
Local outbox dir:    ./data/smb-outbox/partner-a
```

Và xây dựng quan hệ:

```mermaid
flowchart LR
    subgraph SMB["SMB server: \\fs01\exchange"]
      A["incoming/partner-a/*.csv"]
      B["outgoing/partner-a/*.ack"]
      C["archive/partner-a/*.csv"]
    end
    subgraph APP["Máy chạy Spring Boot"]
      D["./data/smb-inbox/partner-a/"]
      E["Xử lý / nhập dữ liệu"]
      F["./data/smb-outbox/partner-a/"]
    end
    A -->|Inbound: tải về| D
    D --> E
    E --> F
    F -->|Outbound: gửi lên| B
    A -.->|Gateway mv khi đã xử lý| C
```

Hãy xem bảng ánh xạ trước khi viết cấu hình:

| Hành động | Đường dẫn Windows/SMB remote | Đường dẫn local |
|---|---|---|
| Đọc báo cáo | `\\fs01\exchange\incoming\partner-a\orders.csv` | `./data/smb-inbox/partner-a/orders.csv` |
| Tạo bản xác nhận | Chưa có remote | `./data/smb-outbox/partner-a/orders.ack` |
| Gửi xác nhận | `\\fs01\exchange\outgoing\partner-a\orders.ack` | Nguồn: `./data/smb-outbox/partner-a/orders.ack` |
| Archive sau import | Nguồn: `incoming/partner-a/orders.csv` → đích: `archive/partner-a/orders.csv` | Không bắt buộc tạo thêm bản sao local |

Ở đây, `incoming`, `outgoing` và `archive` là **ba thư mục khác nhau trong cùng một share**; chúng không phải ba tên share. Nếu đối tác thật sự cung cấp ba share riêng, cần đặt factory/điểm kết nối tương ứng chứ không chỉ thay `remoteDirectory`.

### 3.1. Vai trò của `setShareAndDir(...)`

API `SmbConfig.setShareAndDir(...)` nhận thông tin share, có thể gắn với đường dẫn gốc bên trong share theo cấu hình client. Để dễ kiểm soát và tránh nhân đôi thư mục, bài này dùng:

```java
factory.setShareAndDir("exchange");
```

Sau đó endpoint quyết định đường dẫn tương đối như `incoming/partner-a`. Nếu một dự án chọn `setShareAndDir("exchange/base")` để cố định thư mục gốc sâu hơn, toàn bộ `remoteDirectory` và request path phải được rà lại theo **điểm gốc mới**. Không ghép `base` lần thứ hai; kiểm chứng bằng lệnh `ls` trong môi trường lab trước khi ghi file.

### 3.2. Dấu `/` trong remote path

Trên Windows, người dùng quen với `\`. Trong cấu hình Java DSL của Spring Integration SMB, ví dụ chính thức dùng những path như `"smbSource"` hoặc `"smbTarget"`; khi có nhiều cấp, ưu tiên thống nhất dấu `/` để thể hiện **đường dẫn remote nội bộ share**:

```text
Đúng theo quy ước của bài: incoming/partner-a
Không trộn lẫn:         incoming\partner-a
Không đưa cả UNC:       \\fs01\exchange\incoming\partner-a
```

Thành phần remote-file của Spring Integration có cơ chế xử lý separator theo giao thức/endpoint; khi dùng cấu hình nâng cao như `remote-file-separator`, cần đảm bảo separator nhất quán. Không giả định dấu `\` trên Windows luôn phù hợp khi nó đi qua SpEL, YAML, Java string literal hoặc client SMB.

## 4. Cấu hình Java DSL có ánh xạ đường dẫn rõ ràng

Ví dụ dưới đây theo Spring Integration 6.x và Spring Boot 3.x tương thích. Chọn version `spring-integration-smb` phù hợp dependency management của dự án.

**Gradle:**

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-smb'
}
```

### 4.1. Định nghĩa cấu hình theo môi trường

**`application.yml`:**

```yaml
demo:
  smb:
    host: ${SMB_HOST:fs01.corp.example}
    port: ${SMB_PORT:445}
    domain: ${SMB_DOMAIN:CORP}
    username: ${SMB_USERNAME}
    password: ${SMB_PASSWORD}
    share: ${SMB_SHARE:exchange}
    inbound-dir: ${SMB_INBOUND_DIR:incoming/partner-a}
    outbound-dir: ${SMB_OUTBOUND_DIR:outgoing/partner-a}
    local-inbound-dir: ${SMB_LOCAL_INBOUND_DIR:./data/smb-inbox/partner-a}
```

Trong production, tất cả host/share/path phải lấy từ cấu hình đáng tin cậy; `SMB_USERNAME` và `SMB_PASSWORD` phải được cấp từ secret manager hoặc phương thức bảo vệ secret phù hợp. Giá trị mặc định ở đây để minh họa đường dẫn, không phải cấu hình thật của doanh nghiệp.

**Quan hệ quan trọng:**

```text
SmbSessionFactory(host, share = exchange)
    + inbound-dir = incoming/partner-a
    + remote filename = orders-20261123.csv
    = \\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv

local-inbound-dir = ./data/smb-inbox/partner-a
    + local filename = orders-20261123.csv
    = ./data/smb-inbox/partner-a/orders-20261123.csv
```

### 4.2. Khai báo session factory

**`SmbPathConfig.java`:**

```java
import java.io.File;

import jcifs.DialectVersion;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.remote.FileExistsMode;
import org.springframework.integration.smb.dsl.Smb;
import org.springframework.integration.smb.session.SmbSessionFactory;

@Configuration
@EnableIntegration
public class SmbPathConfig {

    @Bean
    SmbSessionFactory smbSessionFactory(
            @Value("${demo.smb.host}") String host,
            @Value("${demo.smb.port}") int port,
            @Value("${demo.smb.domain}") String domain,
            @Value("${demo.smb.username}") String username,
            @Value("${demo.smb.password}") String password,
            @Value("${demo.smb.share}") String share) {

        SmbSessionFactory factory = new SmbSessionFactory();
        factory.setHost(host);
        factory.setPort(port);
        factory.setDomain(domain);
        factory.setUsername(username);
        factory.setPassword(password);
        factory.setShareAndDir(share);
        factory.setSmbMinVersion(DialectVersion.SMB210);
        factory.setSmbMaxVersion(DialectVersion.SMB311);
        return factory;
    }

    @Bean
    IntegrationFlow smbInboundFlow(
            SmbSessionFactory factory,
            @Value("${demo.smb.inbound-dir}") String remoteDir,
            @Value("${demo.smb.local-inbound-dir}") String localDir) {

        return IntegrationFlow
                .from(Smb.inboundAdapter(factory)
                        .remoteDirectory(remoteDir)
                        .localDirectory(new File(localDir))
                        .autoCreateLocalDirectory(true)
                        .preserveTimestamp(true)
                        .regexFilter("(?i).*\\.csv$"),
                    endpoint -> endpoint
                        .id("smbInboundEndpoint")
                        .poller(Pollers.fixedDelay(10_000)
                            .maxMessagesPerPoll(5)))
                .handle(message -> {
                    File localFile = (File) message.getPayload();
                    System.out.println(
                        "Tệp đã tải về local: " + localFile.getAbsolutePath());
                })
                .get();
    }

    @Bean
    IntegrationFlow smbOutboundFlow(
            SmbSessionFactory factory,
            @Value("${demo.smb.outbound-dir}") String remoteDir) {

        return IntegrationFlow.from("sendSmbFiles")
                .handle(Smb.outboundAdapter(factory, FileExistsMode.FAIL)
                        .remoteDirectory(remoteDir)
                        .autoCreateDirectory(true)
                        .fileNameExpression("payload.name")
                        .useTemporaryFileName(true))
                .get();
    }
}
```

Hai flow này dùng **cùng một share** và xác thực bằng cùng `SmbSessionFactory`. Trong cấu hình production có thể bọc factory bằng `CachingSessionFactory` và inject wrapper vào cả hai flow nếu cần tái sử dụng session; việc có hay không cache không làm thay đổi phép ánh xạ đường dẫn.

### 4.3. Diễn giải từng path trong code

| Cấu hình | Ở đâu? | Kết quả |
|---|---|---|
| `factory.setHost("fs01.corp.example")` | Session factory | Kết nối đến SMB server |
| `factory.setShareAndDir("exchange")` | Session factory | Chọn share gốc |
| `.remoteDirectory("incoming/partner-a")` | Inbound adapter | Liệt kê/tải từ thư mục remote |
| `.localDirectory(new File("./data/smb-inbox/partner-a"))` | Inbound adapter | Lưu tệp đã đồng bộ ở máy ứng dụng |
| `.autoCreateLocalDirectory(true)` | Inbound adapter | Tạo thư mục **local** khi cần |
| `.remoteDirectory("outgoing/partner-a")` | Outbound adapter | Ghi tệp vào thư mục đích **trên share** |
| `.autoCreateDirectory(true)` | Outbound adapter | Tạo thư mục **remote** khi cần và tài khoản đủ quyền |
| `.fileNameExpression("payload.name")` | Outbound adapter | Giữ tên file từ `File` payload local khi gửi lên share |

**Không đánh đồng hai cờ auto-create**: `autoCreateLocalDirectory(true)` tạo thư mục trên ổ đĩa của ứng dụng; `autoCreateDirectory(true)` của outbound tạo thư mục trên Windows share. Nếu ghi remote không được cấp quyền tạo directory, nên yêu cầu quản trị viên chuẩn bị thư mục thay vì mở rộng quyền vô điều kiện.

### 4.4. Khi cần gọi outbound từ service Java

Ở ứng dụng có `@IntegrationComponentScan`, định nghĩa:

```java
import java.io.File;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface SmbFileSender {

    @Gateway(requestChannel = "sendSmbFiles")
    void upload(File localFile);
}
```

Kích hoạt scanning cho interface này, ví dụ đặt `@IntegrationComponentScan` trên một lớp `@Configuration` thích hợp. Service tạo tệp ACK hoàn chỉnh trước khi gọi:

```java
File ack = new File("./data/smb-outbox/partner-a/orders-20261123.ack");
if (!ack.isFile() || !ack.canRead()) {
    throw new IllegalStateException("File ACK local chưa sẵn sàng: " + ack);
}
smbFileSender.upload(ack);
```

Với cấu hình trên, đích remote dự kiến là:

```text
\\fs01.corp.example\exchange\outgoing\partner-a\orders-20261123.ack
```

Lệnh `upload(...)` không tự xác nhận đối tác đã xử lý ACK. Nó chỉ kích hoạt bước **ghi file lên share**; cần quy trình xác nhận nghiệp vụ riêng nếu muốn biết phía nhận đã đọc.

## 5. Hai mô hình truy cập: SMB client và OS-mounted share

Đây là nguồn nhầm lẫn thường gặp nhất trong dự án đa nền tảng.

### 5.1. Spring Integration SMB là SMB client

Khi dùng `SmbSessionFactory`, Java client mở phiên SMB qua mạng. Các bước quản lý host, share và đường dẫn remote nằm trong cấu hình Spring Integration, không đòi hỏi phải mount share thành ổ `Z:` trên máy chạy ứng dụng.

```text
Java process (Linux/Windows)
   -> SmbSessionFactory(host/share/credentials)
      -> SMB server (TCP 445)
         -> incoming/partner-a/orders.csv
```

Trên Linux, local directory có thể là `/var/lib/myapp/smb-inbox`, trong khi remote vẫn nằm trên Windows File Server. Trên Windows, local directory có thể là `C:/apps/myapp/data/smb-inbox`.

### 5.2. OS mount là một cách tiếp cận khác

Windows có thể map `\\fs01\exchange` thành `Z:`; Linux có thể mount SMB/CIFS vào `/mnt/exchange`. Nếu dùng cách này, chương trình đọc file qua **filesystem của hệ điều hành**, ví dụ Java NIO `Files.list(...)` trên đường dẫn mount.

Đó là một mô hình triển khai khác. Mount phải được quản lý ở cấp máy/container và phụ thuộc ngữ cảnh đăng nhập, quyền, khả năng duy trì mount. Spring Integration SMB adapter **không cần mount** và không nên cấu hình `remoteDirectory("Z:/incoming")` chỉ vì máy developer đã map ổ `Z:`.

| Tiêu chí | Client Spring Integration SMB | OS mount + Java filesystem |
|---|---|---|
| Địa chỉ server | Host/share qua `SmbSessionFactory` | Đường dẫn mount/ổ mạng do OS quản lý |
| Credential | Session/client config | OS/mount credentials và quyền tiến trình |
| Đường dẫn ứng dụng | Remote path tương đối với share; local path riêng | Path của filesystem đang được mount |
| Chạy trong container | Không cần map ổ Windows, nhưng phải kết nối SMB network | Cần mount được cấp cho container/máy chủ |
| Message flow | Inbound/outbound/gateway chuyên SMB | Thường dùng file adapter hoặc Java NIO |
| Vòng đời | Session/cache do ứng dụng quản lý | Mount/reconnect do OS hoặc nền tảng quản lý |

Một ổ mạng `Z:` được map trong phiên tương tác của nhân viên thường **không hiện diện trong phiên chạy Windows Service** hoặc container của ứng dụng. Không giải quyết lỗi bằng cách lấy đúng chữ cái ổ từ máy developer rồi đưa vào server production.

## 6. Mapping một thư mục remote sang một thư mục local

Với inbound adapter kiểu **đồng bộ về local**, kết quả là một tệp ở ổ đĩa ứng dụng. Payload của message tiếp theo thường là `java.io.File`.

```mermaid
sequenceDiagram
    participant S as SMB server
    participant P as Poller
    participant A as Inbound adapter
    participant L as Local disk
    participant H as Business handler
    P->>A: Poll mỗi 10 giây
    A->>S: Liệt kê incoming/partner-a/*.csv
    S-->>A: orders-20261123.csv
    A->>S: Đọc file
    A->>L: Ghi ./data/smb-inbox/partner-a/orders-20261123.csv
    A-->>H: Message<File> trỏ tới local file
    H->>L: Đọc và xử lý CSV
```

Những điều cần nhớ:

1. `remoteDirectory` quyết định **đọc ở đâu trên share**.
2. `localDirectory` quyết định **lưu ở đâu trên máy chạy ứng dụng**.
3. File name có thể giữ nguyên hoặc được đổi qua cấu hình local filename. Nếu đổi tên, cần giữ metadata nguồn để đối chiếu.
4. Handler nhận tệp local; đừng nhầm `File.getAbsolutePath()` là UNC path.
5. Tải xong chưa đồng nghĩa nghiệp vụ đã parse và commit dữ liệu.

### 6.1. Dùng tên file khác ở local

Spring Integration SMB inbound DSL có khả năng cấu hình chiến lược tên file local. Ví dụ ý tưởng:

```java
.localFilename(name -> "partner-a_" + name)
```

Với remote `orders-20261123.csv`, local có thể trở thành `partner-a_orders-20261123.csv`. Cần kiểm tra API cụ thể của dòng Spring Integration đang dùng và bộ lọc local: đổi tên không tự tạo khóa idempotency cho nội dung file.

Khi đổi tên, tránh dùng tên bắt nguồn trực tiếp từ dữ liệu không tin cậy có chứa dấu `/`, `\` hoặc `..`. Cần bảo đảm tên đích chỉ là **filename**, không thể trở thành đường dẫn đi ra ngoài vùng lưu trữ cho phép.

### 6.2. Nhiều remote directory có cùng filename

Giả sử:

```text
Remote A: incoming/partner-a/report.csv
Remote B: incoming/partner-b/report.csv
```

Nếu cả hai nguồn đồng bộ về cùng một local directory với tên `report.csv`, hai tệp có thể va chạm hoặc bị bộ lọc local xem như một. Có ba giải pháp dễ kiểm soát:

- Mỗi partner dùng thư mục local riêng: `./data/smb-inbox/partner-a` và `./data/smb-inbox/partner-b`.
- Dùng tên local có prefix partner và/hoặc batch ID đã được chuẩn hóa.
- Nếu cần bảo tồn cây thư mục con, cấu hình và kiểm chứng cơ chế đệ quy/ánh xạ local tương ứng; không giả định một inbound adapter đơn thư mục tự sao chép nguyên cây remote.

Trong bài này, lựa chọn **mỗi partner một thư mục** giúp truy vết và hạn chế lỗi tên trùng.

## 7. Đường dẫn trong SMB outbound gateway

SMB outbound gateway cho phép thực hiện các lệnh có reply: `ls`, `nlst`, `get`, `mget`, `rm`, `mv`, `put`, `mput`. Trường `expression` của gateway thường biểu diễn **đường dẫn tương đối remote**, không phải toàn bộ UNC.

Ví dụ Java DSL:

```java
@Bean
IntegrationFlow smbListIncomingFlow(SmbSessionFactory factory) {
    return IntegrationFlow.from("listSmbDirectory")
            .handle(Smb.outboundGateway(factory, "ls", "payload")
                    .options("-1"))
            .get();
}
```

Gửi message có payload `"incoming/partner-a"` vào `listSmbDirectory` thì gateway liệt kê tại:

```text
\\fs01.corp.example\exchange\incoming\partner-a
```

Reply của `ls -1` là một danh sách tên tệp `List<String>`. Dùng `ls` mặc định không có `-1`, payload là danh sách `FileInfo`; khi dùng `-R` tên trong reply có thể gồm đường dẫn tương đối dưới thư mục đã chọn.

| Lệnh | Đường dẫn request | Phạm vi thao tác |
|---|---|---|
| `ls` | `incoming/partner-a` | Liệt kê thư mục remote |
| `get` | `incoming/partner-a/report.csv` | Tải một tệp remote về local |
| `mget` | `incoming/partner-a/*` | Lấy nhiều file theo pattern |
| `put` | Payload là `File` local; thư mục đích cấu hình riêng | Gửi file lên remote directory |
| `mv` | Nguồn `incoming/partner-a/report.csv`, đích `archive/partner-a/report.csv` | Đổi tên/chuyển file trong phạm vi quyền |
| `rm` | `archive/partner-a/report.csv` | Xóa một tệp xác định |

**Đối với `put/mput`**, biểu thức `expression` dùng để xác định đường dẫn file request của các lệnh khác không quyết định nội dung payload gửi. Thư mục đích do `remoteDirectory`/`remoteDirectoryExpression`, còn file name do generator/expression đặt tên.

### 7.1. `get` và `mget`: ánh xạ local

Các lệnh `get`/`mget` cho phép khai báo `localDirectory`. Khi cần chuyển nhiều tệp từ các thư mục con, có thể dùng **local directory expression** để dựng đường dẫn theo biến `#remoteDirectory` và **local filename expression** theo biến `#remoteFileName`.

Ý tưởng ánh xạ:

```text
remote: incoming/partner-a/2026/11/report.csv
local:  /data/import/partner-a/2026/11/report.csv
```

Tuy nhiên, phải giới hạn và chuẩn hóa phần tương đối trước khi đưa vào đường dẫn local. Biến `#remoteDirectory` không nên được nối trực tiếp với một base directory khi phần đầu vào có thể chứa `..`, đường dẫn tuyệt đối hoặc thông tin ngoài phạm vi đối tác.

Tài liệu Spring Integration ghi nhận `local-directory-expression` **loại trừ lẫn nhau** với thuộc tính tĩnh `local-directory`. Chọn một cách xác định local directory cho mỗi gateway. Khi chưa cần bảo tồn cây thư mục, dùng local directory tĩnh và các tên file riêng có kiểm soát thường đơn giản hơn.

### 7.2. `mv`: đường dẫn nguồn và đích là hai giá trị

Với `mv`, biểu thức request xác định đường dẫn nguồn; `rename-expression` xác định đường dẫn đích. Ví dụ:

```java
@Bean
IntegrationFlow smbArchiveFlow(SmbSessionFactory factory) {
    return IntegrationFlow.from("archiveSmbFile")
            .handle(Smb.outboundGateway(factory, "mv", "payload")
                    .renameExpression("headers['file_renameTo']"))
            .get();
}
```

Request:

```text
payload:              incoming/partner-a/orders-20261123.csv
file_renameTo header: archive/partner-a/orders-20261123.csv
```

Đây là thao tác **trên server**, không di chuyển `./data/smb-inbox/...` ở local. Sau khi chuyển, path remote cũ có thể không còn. Nếu import đã commit nhưng `mv` thất bại, phải đối chiếu trạng thái trước khi retry để tránh nhập lại cùng dữ liệu.

## 8. Ánh xạ theo đối tác mà không mở quyền ghi sai thư mục

Một hệ thống có nhiều đối tác có thể dùng chung share:

```text
exchange/
  incoming/
    partner-a/
    partner-b/
  outgoing/
    partner-a/
    partner-b/
  archive/
    partner-a/
    partner-b/
```

Không nên lấy trực tiếp `partnerId` do bên ngoài truyền rồi ghép:

```java
// Không dùng dữ liệu chưa được kiểm tra để chọn remote directory.
String unsafe = "outgoing/" + request.getPartnerId();
```

Nếu `partnerId` có chứa `../` hoặc giá trị trái phép, đường dẫn remote có thể chỉ đến vị trí ngoài phạm vi nghiệp vụ mong muốn. Thay vào đó, ánh xạ từ **mã partner đã được xác thực** sang danh sách đường dẫn cho phép:

```java
import java.util.Map;

final class PartnerSmbPaths {

    private static final Map<String, String> OUTBOUND_DIRS = Map.of(
        "PARTNER_A", "outgoing/partner-a",
        "PARTNER_B", "outgoing/partner-b"
    );

    static String outboundDirFor(String authorizedPartnerCode) {
        String dir = OUTBOUND_DIRS.get(authorizedPartnerCode);
        if (dir == null) {
            throw new IllegalArgumentException(
                "Partner không được cấp đường dẫn SMB");
        }
        return dir;
    }
}
```

Khi cần nhiều thư mục đích, có thể chọn một trong hai thiết kế:

1. **Một outbound flow riêng cho mỗi partner/đích** với `remoteDirectory(...)` tĩnh. Phù hợp khi số đích ít, yêu cầu quyền và xử lý rõ ràng.
2. **Một flow dùng remote directory expression**, nhưng header chứa đường dẫn phải được ứng dụng tạo từ whitelist phía server (như `PartnerSmbPaths`), không nhận raw path từ request công khai. Cần kiểm tra chặt đường đi của message qua các handler/transformer để không bị một header khác ghi đè.

Các đối tác có quyền truy cập khác nhau nên dùng factory/credential riêng hoặc share/ACL được tách phù hợp. Một chuỗi path an toàn về cú pháp vẫn không thay thế kiểm soát quyền của server.

### 8.1. Ngăn path traversal và tên file không hợp lệ

Một chính sách hợp lý:

- Không chấp nhận đường dẫn tuyệt đối, UNC hoặc `smb://` từ bên ngoài tại điểm chỉ cho phép **relative path**.
- Từ chối đoạn `..` khi chuẩn hóa và mọi trường hợp đi ra ngoài prefix đã cấp.
- Chỉ chấp nhận tên file được sinh theo mã lô hoặc dữ liệu đã validate; không đưa dấu `/` hay `\` vào filename.
- Kiểm tra ký tự Windows không hợp lệ như `< > : " / \ | ? *`, tên reserved theo chính sách server và những ký tự/độ dài bị hạn chế.
- Nếu tạo file local, chuẩn hóa và kiểm tra đường dẫn đích nằm **bên dưới thư mục root đã cho phép**.
- Với file server có symbolic link, DFS hoặc tính năng redirect, phải xác minh thêm chính sách xử lý path ở phía server/client, không chỉ dựa vào kiểm tra chuỗi.

Ví dụ Java NIO để kiểm tra một **đường dẫn local** sau khi đã ánh xạ:

```java
import java.nio.file.Path;

Path localRoot = Path.of("./data/smb-inbox").toAbsolutePath().normalize();
String trustedRelativePath = "partner-a/orders-20261123.csv";
Path target = localRoot.resolve(trustedRelativePath).normalize();

if (!target.startsWith(localRoot)) {
    throw new IllegalArgumentException("Đường dẫn vượt local root");
}
```

Kiểm tra này chỉ xử lý đường dẫn theo cú pháp; nếu cần chống symlink hoặc thay đổi file đồng thời trên local filesystem, phải kết hợp kiểm soát quyền và thao tác file an toàn phù hợp. Không sao chép nguyên cách chuẩn hóa local path sang SMB remote path rồi giả định semantics giống nhau.

## 9. Lưu ý về tên, encoding, separator và tính tương thích

### 9.1. Tên trùng và chữ hoa/thường

Windows File Server thông thường truy cập không phân biệt hoa/thường nhưng giữ nguyên cách viết tên. Samba/NAS có thể cấu hình khác. Đừng giả định `Report.csv` và `report.csv` luôn là hai file độc lập hoặc luôn là một file trên mọi server.

Nếu dùng regex hoặc pattern:

```java
.regexFilter("(?i).*\\.csv$")
```

thì biểu thức `(?i)` giúp nhận cả `CSV` và `csv` khi lọc tên, nhưng **không thay đổi** quy tắc so sánh tên của file server. Nên thỏa thuận naming convention ổn định với đối tác.

### 9.2. Dấu cách, tiếng Việt và ký tự đặc biệt

Tên file có dấu cách hoặc Unicode có thể hợp lệ, nhưng các bước encode URL, export CSV, xử lý message header, lưu database và truyền qua nhiều hệ thống phải giữ nguyên một quy ước. Cần kiểm tra trường hợp:

```text
incoming/partner-a/Báo cáo tháng 11.csv
incoming/partner-a/report final.csv
```

Không tự nối credential và path thành `smb://user:password@host/share/...`; dấu `@`, `:` hay ký tự quốc tế có thể gây lỗi encode, đồng thời làm rò bí mật.

### 9.3. UNC dài và DFS

Một đường dẫn UNC có thể trỏ tới DFS namespace, ví dụ `\\corp.example\dfs\exchange\incoming`. Không mặc định client SMB, quyền và chính sách failover đối với DFS giống mọi file share trực tiếp; hãy kiểm tra với phiên bản thư viện SMB và hạ tầng thực tế. Nếu dùng tên DNS bí danh hoặc nhiều node file server, cần phối hợp quản trị viên để xác nhận target và quyền truy cập.

### 9.4. Đường dẫn local trong container

Trong container:

```text
Ứng dụng thấy:      /app/data/smb-inbox
Host container:     /srv/myapp-data/smb-inbox   (nếu bind mount)
Windows share:      \\fs01.corp.example\exchange\incoming
```

Ba path trên thuộc **ba lớp khác nhau**. `localDirectory(new File("/app/data/smb-inbox"))` phải tồn tại hoặc tạo được trong không gian filesystem của container. Nếu muốn dữ liệu tồn tại sau khi pod/container bị xóa, cần volume/persistent storage phù hợp; không thể dựa vào SMB session factory để bảo đảm tồn tại của file local.

## 10. Chẩn đoán lỗi ánh xạ đường dẫn

| Hiện tượng | Khả năng | Cách kiểm tra |
|---|---|---|
| Kết nối timeout ngay cả khi path đúng | DNS, TCP 445, mạng, SMB dialect | Kiểm tra từ máy/container chạy ứng dụng |
| Access denied với `incoming/partner-a` | Share permission hoặc ACL thư mục | Xác thực tài khoản, so quyền read/list trên path |
| Liệt kê được share nhưng không thấy file | Nhầm remote directory hoặc bộ lọc | Dùng `ls -1` ở một path xác định; so path trên UNC |
| File nằm trong `exchange/exchange/incoming` | Lặp tên share trong remote path | Kiểm tra `setShareAndDir` và `remoteDirectory` |
| File inbound được tải nhưng không thấy ở máy developer | Local directory nằm trong container/server | Kiểm tra đường dẫn local thật từ log an toàn và volume mount |
| Lỗi tạo thư mục remote | `autoCreateDirectory` không đủ quyền | Kiểm tra ACL; tạo sẵn remote dir hoặc cấp quyền cần thiết |
| Lỗi tạo thư mục local | Process không có quyền ghi hoặc ổ đĩa đầy | Kiểm tra OS permission, volume và dung lượng |
| Tệp A của partner A bị ghi đè bởi partner B | Chung tên và chung local directory | Tách local root hoặc tạo tên tệp riêng theo partner/batch |
| `get` thất bại khi local file đã có | `FileExistsMode.FAIL` | Chọn chính sách retry/tồn tại local rõ ràng |
| `put` thành công nhưng đối tác không thấy file | Gửi sai `remoteDirectory` hoặc còn file tạm | Kiểm tra share/dir thực, tên tạm, rename và quyền |
| `mv` báo không tìm thấy file | Ghép sai nguồn hoặc file đã được archive | Kiểm tra cả đường nguồn và đích trước khi retry |
| Chỉ lỗi khi chạy Windows Service | Dựa vào `Z:` map trong phiên user | Dùng SMB client trực tiếp hoặc mount theo identity service |
| File name thay đổi ký tự/không mở được | Encoding/URI/path conversion | Kiểm tra ký tự đặc biệt và cấu hình client/server |

Khi điều tra, ghi log các giá trị **đã làm sạch**: alias host, share, remote relative path, local absolute path (nếu chính sách cho phép), tên file, batch ID và loại lỗi. Không log URL SMB chứa password hoặc chia sẻ cả thư mục nhạy cảm cho người không có quyền.

### Quy trình tìm sai path nhanh

1. Lấy nguyên UNC mà người quản trị cung cấp (không gồm credential).
2. Tách host, share, thư mục tương đối và file name trên giấy hoặc bảng cấu hình.
3. Xác minh `SmbSessionFactory` đúng host/share; bảo đảm `remoteDirectory` **không chứa lại UNC/share**.
4. Thử `ls -1` trên thư mục thử nghiệm để xác nhận path; sau đó `get` một file nhỏ nếu được phép.
5. Kiểm tra `localDirectory` bằng chính đường dẫn tuyệt đối mà ứng dụng chạy trong container/VM nhìn thấy.
6. Với outbound, dùng file thử, xác minh vị trí trên share và cả rename tên tạm; chỉ sau đó mới chạy batch dữ liệu thực.

## 11. Thực hành với thư mục chia sẻ lab

Chuẩn bị một Windows File Server hoặc Samba/NAS share tên `exchange` có thư mục:

```text
exchange/
  incoming/
    partner-a/
    partner-b/
  outgoing/
    partner-a/
    partner-b/
  archive/
    partner-a/
```

Cấp quyền đọc cho `incoming` và quyền ghi/rename cần thiết trên `outgoing` **chỉ trong lab**. Cấu hình host, share, tài khoản và mật khẩu qua môi trường như phần 4.

### Lab A — Từ UNC đến các thuộc tính của adapter

Cho đường dẫn:

```text
\\fs01.corp.example\exchange\incoming\partner-a\orders-007.csv
```

Yêu cầu: viết ra `host`, `shareAndDir`, `remoteDirectory`, filename và local directory nếu muốn lưu tại `/app/data/inbound/partner-a`.

**Đáp án tham chiếu:** host `fs01.corp.example`, share `exchange`, `remoteDirectory = incoming/partner-a`, filename `orders-007.csv`, `localDirectory = /app/data/inbound/partner-a`. Tệp local dự kiến `/app/data/inbound/partner-a/orders-007.csv`.

### Lab B — Tải file và kiểm tra payload

1. Đặt file `orders-007.csv` trong `incoming/partner-a` có nội dung:

   ```csv
   order_id,amount,currency
   ORD-101,150000,VND
   ORD-102,85000,VND
   ```

2. Chạy inbound flow với `SMB_INBOUND_DIR=incoming/partner-a` và `SMB_LOCAL_INBOUND_DIR=./data/smb-inbox/partner-a`.
3. Chờ poll và quan sát đường dẫn `File` trong log mẫu.
4. Mở tệp local, xác minh đúng hai dòng dữ liệu và tổng tiền `235000` VND.

**Kết quả cần giải thích:** payload `File` trỏ tới bản local, không phải UNC hay URI `smb://`.

### Lab C — Phân biệt remote và local directory

1. Thay `SMB_LOCAL_INBOUND_DIR` sang thư mục local khác trong lab và khởi động lại ứng dụng.
2. Quan sát vị trí file được tải nhưng **không** thay đổi địa chỉ UNC nguồn.
3. Khôi phục và thay `SMB_INBOUND_DIR` từ `incoming/partner-a` thành `incoming/partner-b`.
4. Giải thích vì sao việc thay một giá trị dẫn tới thay **nơi lưu**, còn giá trị kia thay **nơi đọc trên server**.

**Kết quả:** phân biệt rõ trách nhiệm của `localDirectory` và `remoteDirectory`.

### Lab D — Gửi ACK lên đúng thư mục

1. Tạo `./data/smb-outbox/partner-a/orders-007.ack` sau khi xử lý file mẫu.
2. Gọi `SmbFileSender.upload(...)`; xác minh file xuất hiện trong `outgoing/partner-a`.
3. Kiểm tra tên tạm nếu có thể quan sát khi truyền, và chỉ đọc tên chính thức sau khi rename hoàn tất.
4. Thử cấu hình sai thư mục `outgoing/partner-b` **trong lab**, nhận diện sai lệch và sửa lại trước khi chạy dữ liệu thật.

**Kết quả:** ánh xạ nguồn local thành một đường dẫn đích remote theo đúng share và directory.

### Lab E — Hai partner gửi cùng filename

1. Tạo `incoming/partner-a/report.csv` và `incoming/partner-b/report.csv` với nội dung khác nhau.
2. Thử thiết kế cả hai vào cùng local directory trong môi trường lab, quan sát rủi ro collision/bộ lọc.
3. Đổi cấu hình để mỗi partner có local directory riêng.
4. Kiểm tra hai tệp không ghi đè lẫn nhau và giữ được metadata xác định nguồn.

**Kết quả:** thấy được giá trị của một bảng mapping cố định và khóa định danh theo partner/batch.

### Lab F — Thử lỗi đường dẫn và phân quyền

1. Dùng outbound gateway `ls -1` liệt kê một thư mục hợp lệ.
2. Thử một thư mục không tồn tại như `incoming/no-such-partner` và quan sát khác biệt với kết quả rỗng của thư mục hợp lệ.
3. Trên share lab, tạm đặt quyền đọc cho một thư mục nhưng không cấp quyền ghi, thử gửi file để thấy `Access Denied`.
4. So sánh ba nhóm lỗi: **path không tồn tại**, **không có quyền**, **không kết nối được**.
5. Khôi phục quyền, xóa file thử do chính lab tạo và ghi lại quy tắc cấu hình đúng.

**Kết quả:** biết sử dụng lệnh chỉ đọc để kiểm tra đường dẫn trước thao tác có thay đổi dữ liệu.

### Câu hỏi tự kiểm tra

1. Trong `\\srv\share\a\b.csv`, `a` là share hay remote directory?
2. Khi đã có `setShareAndDir("share")`, có nên cấu hình `remoteDirectory("share/a")` không? Vì sao?
3. Nếu ứng dụng chạy trên Linux, có cần mount `\\srv\share` thành ổ `Z:` để dùng SMB adapter không?
4. Khác biệt giữa `autoCreateLocalDirectory` và `autoCreateDirectory` là gì?
5. Vì sao hai file `partner-a/report.csv` và `partner-b/report.csv` có thể va chạm ở local?
6. `mv` qua outbound gateway chuyển tệp trên SMB hay chuyển `File` đã tải trên local?
7. Tại sao việc normalize một đường dẫn không thay thế whitelist và ACL?

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| UNC đầy đủ là giá trị của `remoteDirectory` | Factory cấu hình host/share, endpoint chỉ nhận remote path phù hợp với gốc đó |
| `setShareAndDir` chỉ nhận tên thư mục con | Nó đại diện share và có thể bao gồm base path; cần thiết kế điểm gốc nhất quán |
| `localDirectory` nằm trên SMB server | Đây là thư mục của ứng dụng khi inbound đồng bộ về local |
| SMB client cần có ổ đĩa `Z:` | Client Spring Integration SMB kết nối trực tiếp tới share, không cần mapped drive |
| Windows service nhìn thấy mọi drive map của user | Mapped drive phụ thuộc phiên đăng nhập/ngữ cảnh chạy |
| Dấu `\` luôn phù hợp trong mọi config | UNC dùng backslash, nhưng Java/YAML/remote path có quy tắc escaping khác |
| Inbound adapter tự giữ nguyên toàn bộ cây thư mục remote | Phải cấu hình và kiểm chứng cơ chế mapping/recursion; một local directory đơn có thể làm phẳng path |
| Gửi file lên share nghĩa là đã ghi vào localDirectory | Outbound ghi vào remote directory, nguồn `File` thường ở local |
| Cùng file name nghĩa là cùng file | Hai remote directory/partner có thể có tên trùng |
| `ls` trả rỗng chắc chắn là lỗi credential | Có thể thư mục hợp lệ nhưng không có file phù hợp |
| Check string path là đủ bảo vệ | Phải kết hợp whitelist/ủy quyền, canonical path, ACL, quản lý symlink |
| Tải file thành công nghĩa là đã nhập nghiệp vụ | Tải về và commit dữ liệu là hai mốc độc lập |

## 13. Tài liệu tham khảo

- [Spring Integration Reference 6.5 — SMB Support](https://docs.spring.io/spring-integration/reference/6.5/smb.html): cấu hình factory, inbound/outbound adapter, gateway và Java DSL.
- [Spring Integration 6.5 API — SmbConfig](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/smb/session/SmbConfig.html): `setHost`, `setShareAndDir`, cú pháp SMB URI và các thuộc tính cấu hình.
- [Spring Integration 6.5 API — SmbSessionFactory](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/smb/session/SmbSessionFactory.html): session factory gắn với SMB share.
- [Spring Integration Reference — Remote File Support](https://docs.spring.io/spring-integration/reference/ftp.html): mô hình chung cho remote file, đường dẫn và bộ lọc; cần đối chiếu khả năng cụ thể của SMB.

**Ghi nhớ:** một UNC path có cấu trúc **host → share → remote directory → filename**. Khi dùng Spring Integration SMB, hãy ánh xạ những phần đó vào `SmbSessionFactory` và các endpoint một cách nhất quán, đồng thời quản lý `localDirectory` như một vùng lưu trữ riêng của ứng dụng. Tính đúng đắn của đường dẫn, giới hạn quyền và cách bảo tồn metadata là nền tảng để xử lý file an toàn qua inbound/outbound adapter và gateway.

# Cấu hình TLS, chứng chỉ và xác minh máy chủ

## 1. Vai trò của TLS trong kết nối Spring Data Couchbase

Một ứng dụng có thể đã khai báo đúng connection string, username, password và bucket nhưng vẫn không kết nối được Couchbase khi chuyển từ môi trường local sang production. Trong nhiều trường hợp, nguyên nhân là **TLS, chuỗi chứng chỉ hoặc tên máy chủ không khớp** chứ không phải lỗi repository. Cần phân biệt rõ kết nối mạng thành công, kênh được mã hóa, máy chủ được xác minh và người dùng có đủ quyền truy cập dữ liệu.

Trong module **SPRING_DATA_COUCHBASE**, các thao tác document mapping, `CouchbaseRepository`, `CouchbaseTemplate` và truy vấn SQL++ sử dụng Couchbase Java SDK phía dưới. Nếu kênh TLS hoặc xác minh máy chủ sai, toàn bộ các API đó có thể thất bại, bất kể entity có annotation đúng hay index SQL++ đã được tạo đầy đủ.

Bài học thuộc chương **Cấu hình kết nối** và hướng đến các mục tiêu:

- Giải thích TLS giải quyết những rủi ro nào và vì sao **mã hóa** không đồng nghĩa **xác thực máy chủ**.
- Phân biệt **chứng chỉ server**, **CA/trust anchor**, **truststore**, **client certificate** và thông tin đăng nhập Couchbase.
- Sử dụng connection string `couchbases://` phù hợp và tổ chức cấu hình Spring Boot.
- Hiểu cách SDK dựa trên `ClusterEnvironment` cấu hình chính sách TLS và nguồn CA tin cậy.
- Xác minh hostname thông qua **Subject Alternative Name (SAN)**, tránh bỏ qua hostname verification.
- Chẩn đoán các lỗi PKIX, TLS handshake, DNS, topology và RBAC theo đúng tầng.
- Lập kế hoạch gia hạn/xoay chứng chỉ, secrets, rolling restart và kiểm tra KV/SQL++ sau thay đổi.

Các ví dụ tham chiếu kiến trúc **Spring Boot 3.x**, Spring Data Couchbase tương ứng và Couchbase Java SDK 3.x. API và property nâng cao có thể thay đổi giữa các bản minor; trước khi áp dụng vào production cần đối chiếu SDK/Boot đang dùng.

## 2. TLS giải quyết điều gì và không giải quyết điều gì?

TLS bảo vệ kênh trao đổi giữa client và endpoint của Couchbase bằng các cơ chế mã hóa, kiểm tra tính toàn vẹn và xác minh danh tính phía máy chủ khi cấu hình đúng. Nó giảm nguy cơ nghe lén hoặc can thiệp dữ liệu trên đường truyền.

Nhưng những việc sau **không tự động được giải quyết bằng TLS**:

- **RBAC**: một client đã kết nối an toàn vẫn có thể thiếu quyền đọc collection hoặc thực thi SQL++.
- **Tồn tại của tài nguyên**: TLS không tạo bucket/scope/collection hay secondary index.
- **Độ nhất quán**: CAS, `@Version`, transaction và scan consistency có quy tắc riêng.
- **Hiệu năng**: query thiếu index vẫn chậm khi được truyền trên kênh TLS.
- **Bảo vệ secrets**: TLS không thay thế việc lưu giữ password/private key đúng cách trong runtime.

~~~mermaid
flowchart LR
    A["Ứng dụng Java / Spring Data"] --> B["TLS handshake"]
    B --> C{"Chứng chỉ máy chủ tin cậy<br/>và hostname khớp?"}
    C -- "Không" --> D["Từ chối kết nối"]
    C -- "Có" --> E["Kênh TLS được thiết lập"]
    E --> F["Couchbase authentication"]
    F --> G{"RBAC trên tài nguyên?"}
    G -- "Không" --> H["Access denied"]
    G -- "Có" --> I["KV, SQL++, repository, template"]
~~~

**Nguyên tắc:** chỉ gửi credentials và thực hiện thao tác nghiệp vụ sau khi cơ chế TLS của SDK xác minh endpoint theo chính sách an toàn. Không dùng lựa chọn bỏ qua kiểm tra chứng chỉ để làm “giải pháp tạm” cho production.

## 3. Các thuật ngữ dễ nhầm

| Khái niệm | Ý nghĩa | Chú ý trong ứng dụng |
| --- | --- | --- |
| TLS server certificate | Chứng chỉ X.509 do endpoint Couchbase trình bày | Chứng minh danh tính server nếu chuỗi tin cậy và hostname hợp lệ |
| CA certificate | Chứng chỉ của tổ chức/cấp chứng thực đã ký hoặc làm gốc tin cậy | Client dùng làm trust anchor theo chính sách |
| Intermediate CA | CA trung gian trong chuỗi chứng thực | Cần có chuỗi hợp lệ tới một gốc tin cậy |
| Truststore | Tập chứng chỉ/CA được client tin cậy | Khác nơi lưu private key |
| Keystore | Kho key/certificate; có thể chứa private key của client | Không dùng như tên thay thế mặc định cho truststore |
| SAN (Subject Alternative Name) | Các DNS name/IP mà chứng chỉ xác nhận | Hostname kết nối phải khớp SAN phù hợp |
| Hostname verification | Đối chiếu tên endpoint với danh tính trong chứng chỉ | Không được bỏ qua |
| Client certificate / mTLS | Chứng chỉ client trình bày cho server khi được yêu cầu | Khác CA dùng để kiểm chứng server |
| Couchbase credentials | Username/password hoặc phương thức xác thực được hỗ trợ | Được server dùng cho authentication/RBAC, không phải CA |

Một chứng chỉ server được phát hành bởi CA tin cậy vẫn **không hợp lệ cho endpoint** nếu SAN không khớp tên host client đang kết nối. Ngược lại, SAN đúng chưa đủ khi chứng chỉ hết hạn hoặc chuỗi CA không đáng tin.

### 3.1. Luồng xác minh chứng chỉ

~~~mermaid
sequenceDiagram
    participant App as Spring Data / Couchbase SDK
    participant Server as Couchbase TLS Endpoint
    participant Trust as Nguồn CA tin cậy
    App->>Server: Thiết lập kết nối TLS / SNI
    Server-->>App: Chứng chỉ server + chuỗi liên quan
    App->>Trust: Kiểm tra đường dẫn chứng thực
    Trust-->>App: Gốc tin cậy?
    App->>App: Kiểm tra hạn, ràng buộc và SAN/hostname
    alt Chứng chỉ hoặc hostname không hợp lệ
      App-->>Server: Dừng handshake
    else Hợp lệ
      App->>Server: Hoàn tất handshake / tiếp tục xác thực
      Server-->>App: Kênh mã hóa hoạt động
    end
~~~

Sơ đồ mang tính khái niệm. Quy trình TLS thực tế do JDK và Couchbase Java SDK thực hiện; ứng dụng không nên tự viết một bộ xác minh chứng chỉ mới.

## 4. Chọn `couchbase://` hay `couchbases://`

Couchbase SDK sử dụng URI scheme trong connection string để diễn đạt chế độ kết nối:

~~~text
# Môi trường local tự quản lý khi cho phép không TLS
couchbase://127.0.0.1

# Kết nối TLS tới endpoint được cấp
couchbases://cb.example.internal
~~~

Với cluster cloud hoặc production bắt buộc TLS, sử dụng endpoint TLS được nhà vận hành cung cấp cùng `couchbases://`. Không lấy URI của cluster khác rồi thay riêng scheme mà không xác minh hệ thống server đã bật TLS, các cổng dịch vụ và chứng chỉ hợp lệ.

Connection string chứa **seed node**, không chứa bucket/scope/collection. Spring Data nhận bucket mặc định từ cấu hình riêng:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbases://cb.example.internal}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:inventory}"
~~~

Trong ví dụ:

- `spring.couchbase.connection-string` chỉ cluster/seed endpoints và dùng TLS.
- `spring.couchbase.username/password` là credentials ứng dụng, cần inject từ nguồn secret.
- `spring.data.couchbase.bucket-name` chọn bucket mặc định cho repository/template.
- Scope/collection được chọn bằng mapping entity hoặc API truy cập dữ liệu, không phải bằng scheme TLS.

**Giá trị `cb.example.internal` chỉ để minh họa.** Thay bằng DNS/endpoint hợp lệ do hệ thống thực tế cấp. Không sử dụng fallback endpoint không thuộc production trong cấu hình triển khai thật.

## 5. Nguồn tin cậy của client: CA và truststore

Khi server trình bày certificate chain, client phải có chính sách tin cậy phù hợp. Hai trường hợp điển hình:

1. **CA công khai đã được runtime/SDK tin cậy**: có thể không cần nạp một file CA riêng nếu đường dẫn chứng thực và hostname đã hợp lệ theo cấu hình SDK.
2. **Private CA hoặc CA riêng của doanh nghiệp**: cần cấp đúng chứng chỉ CA tin cậy cho môi trường SDK/truststore theo cơ chế được phiên bản SDK hỗ trợ.

Một số cluster được quản lý cung cấp certificate download hoặc tài liệu trust riêng. Không kết luận rằng môi trường cloud nào cũng dùng cùng CA hoặc bắt buộc phải tải một file PEM nếu chưa xem yêu cầu của cluster đó.

### 5.1. Phân biệt root CA và leaf certificate

Một file `ca.pem` thường chứa certificate PEM của CA, không phải private key. Để xác minh server, ưu tiên tin cậy **đúng CA**/trust anchor do đơn vị quản trị cung cấp thay vì chấp nhận vô điều kiện một leaf certificate chưa được kiểm tra.

Trust một leaf riêng có thể tạo phụ thuộc chặt khi server xoay certificate. Trust một CA quá rộng cũng làm tăng số endpoint có thể được chấp nhận nếu hostname không được ràng buộc. Vì vậy cần **cả chain validation và hostname verification**, không chọn một thay cho cái còn lại.

### 5.2. Không sửa JRE toàn cục khi không cần thiết

Tự import CA vào truststore chung `cacerts` của JDK có thể ảnh hưởng mọi ứng dụng Java sử dụng runtime đó. Trong container production, ưu tiên một cơ chế trust được quản lý theo ứng dụng hoặc image/base image, cùng quy trình phân phối CA rõ ràng.

Một truststore chỉ đọc được từ runtime và được mount theo môi trường dễ kiểm soát hơn việc để tài liệu chứng chỉ trong thư mục source rồi tự động đẩy đi mọi nơi. CA certificate không phải private key, nhưng **tính toàn vẹn** và nguồn gốc của nó vẫn rất quan trọng: nếu thay sai trust anchor, client có thể tin một máy chủ ngoài ý muốn.

## 6. Cấu hình TLS trong Spring Boot: bắt đầu từ cấu hình tiêu chuẩn

Trong ứng dụng Spring Boot thông thường, giữ cấu hình kết nối và danh tính ở property tiêu chuẩn:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:inventory}"
~~~

Ở production, biến `COUCHBASE_CONNECTION_STRING` phải nhận endpoint TLS thích hợp. Không ghi password thực vào `application.yml` hoặc vào code mẫu.

Spring Boot có thể cung cấp các thuộc tính bổ sung cho SSL/TLS hoặc SSL bundles tùy **phiên bản**. Không giả định tất cả các phiên bản Boot 3.x hỗ trợ cùng đường property, cùng cách nạp trust material hoặc cùng cơ chế auto-configuration.

**Quy trình quyết định:**

1. Kiểm tra dependency và Spring Boot version đang dùng.
2. Xác nhận connection string/endpoint của cluster yêu cầu TLS.
3. Xác nhận runtime có tin CA phù hợp hay không.
4. Nếu cần CA riêng, xem property/SSL bundle được phiên bản Boot hỗ trợ.
5. Nếu cần cấu hình builder đặc biệt, cân nhắc customizer của Boot hoặc SDK Java configuration một cách có chủ đích.
6. Chạy phép kiểm tra thật từ **chính runtime ứng dụng** và đọc log TLS nếu thất bại.

Không khai báo một tên property tự nghĩ ra rồi cho rằng Boot sẽ tự bind nó. Một YAML key không được bind có thể bị bỏ qua mà không đem lại tác dụng bảo mật nào.

## 7. Tùy chỉnh TLS bằng Java SDK `ClusterEnvironment`

Đối với một ứng dụng **SDK thuần** hoặc trường hợp kiểm soát trực tiếp builder, có thể cấp CA PEM qua security configuration của Couchbase Java SDK.

Ví dụ minh họa theo API SDK 3.x thông dụng:

~~~java
import java.nio.file.Path;
import com.couchbase.client.java.env.ClusterEnvironment;
import com.couchbase.client.java.env.SecurityConfig;

Path trustedCa = Path.of("/etc/couchbase/tls/ca.pem");

ClusterEnvironment environment = ClusterEnvironment.builder()
        .securityConfig(
                SecurityConfig.enableTls(true)
                        .trustCertificate(trustedCa)
        )
        .build();
~~~

Sau đó kết nối cluster bằng environment này:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;

String endpoint = "couchbases://cb.example.internal";
// username/password phải được lấy từ secrets runtime.

Cluster cluster = Cluster.connect(
        endpoint,
        ClusterOptions.clusterOptions(username, password)
                .environment(environment)
);
~~~

Điểm cần hiểu:

- `SecurityConfig.enableTls(true)` thể hiện chủ đích sử dụng TLS qua cấu hình SDK.
- `trustCertificate(...)` là một cách chỉ định vật liệu chứng thực tin cậy theo API phiên bản hỗ trợ; file PEM phải đến từ nguồn được kiểm soát.
- `couchbases://` và cấu hình TLS cần **nhất quán**; không dùng hai lựa chọn xung đột.
- Lựa chọn trust không bỏ qua kiểm tra hostname. SAN vẫn phải khớp endpoint mà SDK kết nối.
- Chương trình phải quản lý vòng đời `Cluster` và `ClusterEnvironment` do mình tạo.

Đừng để đường dẫn certificate là file build-time tuyệt đối chỉ tồn tại trên máy lập trình; khi chạy trong Docker/Kubernetes, file CA cần được mount đúng nơi runtime có thể đọc.

### 7.1. Đóng tài nguyên tự tạo đúng thứ tự

Trong chương trình SDK độc lập:

~~~java
Cluster cluster = null;
try {
    cluster = Cluster.connect(
            endpoint,
            ClusterOptions.clusterOptions(username, password)
                    .environment(environment)
    );

    // Thao tác qua cluster/bucket/collection.
} finally {
    try {
        if (cluster != null) {
            cluster.disconnect();
        }
    } finally {
        environment.shutdown();
    }
}
~~~

Cách này tránh rò rỉ environment khi cluster đang bootstrap và ném exception. Trong ứng dụng Spring Boot đã dùng auto-configuration, **không** tạo thêm client tùy ý rồi dùng lẫn với `CouchbaseClientFactory` hiện tại. Hãy để owner/container quản lý shutdown.

## 8. Dùng builder customizer khi Spring Boot sở hữu environment

Nếu Spring Boot đang tạo SDK environment, cách mở rộng có thể là một bean `ClusterEnvironmentBuilderCustomizer` (nếu phiên bản Boot đang dùng có hỗ trợ) thay vì tạo thủ công một `ClusterEnvironment` và `Cluster` thứ hai.

Ví dụ sử dụng **property tự định nghĩa của ứng dụng** cho đường dẫn CA:

~~~yaml
app:
  couchbase:
    trusted-ca-file: "${COUCHBASE_CA_FILE:/etc/couchbase/tls/ca.pem}"
~~~

Java configuration minh họa:

~~~java
package com.example.inventory.config;

import java.nio.file.Path;
import com.couchbase.client.java.env.SecurityConfig;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.couchbase.ClusterEnvironmentBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CouchbaseTlsConfig {

    @Bean
    ClusterEnvironmentBuilderCustomizer tlsCustomizer(
            @Value("${app.couchbase.trusted-ca-file}") String caPath) {
        return builder -> builder.securityConfig(
                SecurityConfig.enableTls(true)
                        .trustCertificate(Path.of(caPath))
        );
    }
}
~~~

**Lưu ý quan trọng:** `app.couchbase.trusted-ca-file` chỉ là một property do ví dụ đặt; Spring Boot không tự hiểu key này là cấu hình SDK. Bean customizer là phần kết nối property đó với builder.

Customizer hữu ích khi muốn giữ **Spring Boot làm owner** của môi trường SDK, đồng thời thiết lập trust material theo yêu cầu đặc biệt. Tuy nhiên:

- Nếu Boot phiên bản hiện tại đã hỗ trợ SSL bundles/property tương ứng, hãy ưu tiên cơ chế đó nếu đáp ứng yêu cầu.
- Nếu có customizer TLS khác hoặc YAML SSL config, phải xác định **giá trị hiệu lực cuối cùng** và thứ tự phối hợp.
- Cấu hình `securityConfig(...)` có thể ảnh hưởng các thiết lập security đã được áp dụng trước đó; đừng vô tình ghi đè chính sách khác.
- Nếu dự án tự khai báo `ClusterEnvironment` bean riêng, customizer của Boot có thể không tham gia tạo environment đó.
- API customizer và cách cấu hình trust cần được kiểm tra trên đúng dependency versions trước khi rollout.

Không tạo hai `Cluster` chỉ vì muốn đổi CA; điều đó có thể khiến repository sử dụng client khác với client bạn đã cấu hình TLS.

## 9. Hostname verification và SAN: nguyên nhân lỗi thường gặp

Một kết nối TLS an toàn phải xác minh rằng certificate được phát hành cho **tên máy chủ mà client thực sự kết nối**. Danh tính này thường được biểu diễn trong phần `subjectAltName` của chứng chỉ.

Giả sử leaf certificate chứa SAN:

~~~text
DNS:cb-a.example.internal
DNS:cb-b.example.internal
DNS:cb.example.internal
~~~

Kết nối qua `couchbases://cb.example.internal` có thể khớp tên này nếu chain và các điều kiện khác hợp lệ. Nhưng kết nối trực tiếp bằng `couchbases://10.10.1.20` không thể được xác minh chỉ dựa trên DNS SAN nói trên. Nếu dùng IP làm endpoint, chứng chỉ cần có IP SAN tương ứng theo quy tắc xác minh của TLS stack.

### 9.1. Common Name không phải cách “né” SAN

Nhiều hệ thống hiện đại ưu tiên SAN để xác minh hostname. Không nên dựa vào Common Name (CN) mà bỏ qua SAN, cũng không giả định có thể dùng một SAN wildcard để khớp mọi cấp subdomain. Quy tắc wildcard và tên endpoint cần được kiểm tra theo cơ chế xác thực hostname của client.

**Ví dụ lỗi tư duy:** “certificate đã do CA hợp lệ ký, nên bất kỳ host nào sử dụng nó đều đúng.” Kết luận này bỏ qua việc xác minh tên máy chủ và có thể làm mất mục tiêu chống giả mạo endpoint.

### 9.2. Couchbase có nhiều node, không chỉ một hostname

SDK thường bootstrap qua một seed node rồi khám phá topology của cluster. Một số thao tác tiếp theo có thể kết nối đến các node khác hoặc các endpoint dịch vụ được cluster quảng bá.

Do đó, không chỉ kiểm chứng SAN của seed node; cần bảo đảm **các hostname thực sự được SDK sử dụng** phù hợp với chứng chỉ ở những endpoint đó.

~~~mermaid
flowchart TD
    A["couchbases://seed.example.internal"] --> B["Bootstrap và nhận topology"]
    B --> C["Node A: cb-a.example.internal"]
    B --> D["Node B: cb-b.example.internal"]
    C --> E{"TLS certificate hợp lệ<br/>cho hostname A?"}
    D --> F{"TLS certificate hợp lệ<br/>cho hostname B?"}
    E -- "Không" --> G["Handshake failure"]
    F -- "Không" --> G
    E -- "Có" --> H["Có thể tiếp tục KV/Query"]
    F -- "Có" --> H
~~~

Điều này giải thích tình huống **bootstrap thành công nhưng KV hoặc Query đến một node khác lại lỗi TLS**. Kiểm tra topology, DNS/alternate address và chứng chỉ của các node, thay vì chỉ thử một seed rồi kết luận cluster đã sẵn sàng.

## 10. TLS khi chạy Docker, Kubernetes và cloud

Trong môi trường container, nguồn CA và hostname cần được thiết kế đồng bộ với cách mạng thực sự hoạt động.

### 10.1. Nguyên tắc triển khai

- Cấp file CA/truststore bằng cơ chế deploy được quản lý; mount vào path chỉ đọc mà ứng dụng có thể truy cập.
- Không cần đưa private key server vào container ứng dụng chỉ để xác minh server TLS.
- Cấu hình biến môi trường cho endpoint, username, password và (nếu cần) đường dẫn trust CA.
- Dùng hostname đúng với SAN được phát hành và với topology mà SDK nhận được.
- Kiểm tra DNS/route/port từ **bên trong pod hoặc container**, không chỉ từ laptop của developer.
- Xác minh chính sách NetworkPolicy, firewall, proxy/NAT và các địa chỉ node được quảng bá.
- Với các dịch vụ quản lý như Capella, tuân thủ connection string, network allowlist và hướng dẫn certificate của cluster cụ thể.

### 10.2. SNI và hostname

SNI (Server Name Indication) giúp client thông báo tên host mong muốn khi bắt tay TLS để server có thể chọn certificate phù hợp ở những topology hỗ trợ. Một kết nối qua IP literal hoặc alias khác tên chứng chỉ có thể gây lỗi hostname dù cổng vẫn mở.

Không sửa vấn đề này bằng việc tắt xác minh hostname. Hãy sửa tên endpoint/DNS, cấp certificate có SAN phù hợp, hoặc cấu hình cách công bố địa chỉ cluster theo quy trình quản trị.

### 10.3. Cổng TLS phải phù hợp dịch vụ

Couchbase có các dịch vụ KV, Query và quản trị; các endpoint/cổng TLS phụ thuộc topology và cấu hình triển khai. Ví dụ môi trường Couchbase tự quản lý có thể sử dụng **cổng TLS KV 11207**, nhưng không nên mặc định mọi cluster/cloud đều cho phép truy cập trực tiếp cổng đó hoặc dùng một cổng chung cho mọi dịch vụ.

Hãy lấy thông tin port/endpoint từ tài liệu hoặc cấu hình của cluster đang dùng. Chỉ kiểm tra đúng cổng và tên host mà SDK dự kiến sử dụng.

## 11. Phân biệt TLS server authentication, RBAC và mTLS

Một ứng dụng có thể kết nối TLS theo mô hình thông thường:

~~~text
Client xác minh certificate server
    ↓
Kênh TLS được thiết lập
    ↓
Client cung cấp Couchbase username/password
    ↓
Server kiểm tra RBAC
    ↓
Cho phép/không cho phép KV hoặc SQL++
~~~

**mTLS (mutual TLS)** bổ sung việc server yêu cầu và xác minh certificate của **client**. Nó không giống với việc client nạp file CA để tin cậy server.

| Nhu cầu | Tài liệu / dữ liệu liên quan |
| --- | --- |
| Client tin cậy server | Server certificate chain, CA/truststore, SAN |
| Server tin cậy client trong mTLS | Client certificate, client private key, CA/chính sách xác thực của server |
| Phân quyền tới collection | Couchbase user/identity, RBAC và chính sách cluster |
| Mã hóa trên đường truyền | Phiên TLS phù hợp và ciphers được hỗ trợ |

Nếu cluster yêu cầu client certificate authentication, cần xác minh phiên bản SDK, cách cung cấp client key/cert, yêu cầu CA và mapping danh tính của Couchbase Server. **Không** cố dùng một file `ca.pem` làm client private key, hoặc cho rằng `couchbases://` tự bật mTLS.

Private key là thông tin nhạy cảm: chỉ cấp vào môi trường thật sự cần, đặt quyền truy cập tối thiểu, tránh log/commit và lập quy trình xoay riêng. Tắt password authentication hoặc chuyển phương thức xác thực là thay đổi kiến trúc bảo mật, không phải một sửa lỗi handshake thông thường.

## 12. Xác minh chứng chỉ và endpoint bằng công cụ ngoài ứng dụng

Khi cần kiểm tra nguồn gốc certificate, có thể sử dụng công cụ hệ thống trên máy/container có kết nối mạng tới endpoint. Các lệnh dưới đây là **minh họa để kỹ sư thực thi trong môi trường được phép**, không dùng để thay thế kiểm tra thực tế qua SDK.

### 12.1. Kiểm tra nội dung chứng chỉ PEM

Ví dụ xem metadata của file CA/certificate:

~~~bash
openssl x509 -in /etc/couchbase/tls/ca.pem -noout -subject -issuer -dates -fingerprint -sha256
~~~

Lệnh giúp nhìn `subject`, `issuer`, thời hạn và fingerprint. Muốn biết SAN trên leaf certificate của server, cần kiểm tra **chính leaf** đó, không chỉ file root CA.

~~~bash
openssl x509 -in server-leaf.pem -noout -ext subjectAltName
~~~

Một file CA root thường không mang SAN cho hostname server; việc đọc SAN root rồi không thấy hostname là nhầm đối tượng.

### 12.2. Xem handshake tới endpoint phù hợp

Ví dụ với **self-managed** deployment có TLS KV trên cổng 11207:

~~~bash
openssl s_client \
  -connect cb.example.internal:11207 \
  -servername cb.example.internal \
  -showcerts \
  -verify_return_error
~~~

Có thể bổ sung nguồn CA phù hợp bằng tùy chọn như `-CAfile /path/to/ca.pem` theo phiên bản OpenSSL. Với các phiên bản hỗ trợ, `-verify_hostname cb.example.internal` giúp kiểm chứng hostname riêng; việc lệnh chỉ in certificate chain không tự chứng minh danh tính đã được xác minh đầy đủ.

**Lưu ý:** đây chỉ là một ví dụ cổng, không phải hướng dẫn áp dụng cho mọi Couchbase Capella/cluster. Nếu endpoint của bạn dùng cổng khác hoặc SDK khám phá nhiều node, kiểm tra từng host/cổng tương ứng.

### 12.3. Kiểm tra Java truststore khi thực sự dùng nó

Trong hệ thống sử dụng truststore PKCS#12 riêng:

~~~bash
keytool -list -v \
  -keystore /etc/app/truststore.p12 \
  -storetype PKCS12
~~~

Công cụ có thể yêu cầu password của truststore; không nhập password vào command line được lưu history nếu chính sách bảo mật không cho phép. Việc có CA trong một Java truststore **không bảo đảm** Couchbase SDK sẽ dùng truststore đó nếu SDK đã được cấu hình dùng nguồn trust khác. Phải kiểm tra cấu hình thực sự có hiệu lực.

### 12.4. Giới hạn của phép thử OpenSSL

OpenSSL và JVM/SDK có thể dùng các trust source, TLS policy và hostname khác nhau. Một phép thử `openssl s_client` thành công chứng minh đường kết nối/certificate ở mức nó thực sự kiểm tra, **không thay thế** thử `Cluster.connect(...)`, KV và SQL++ bằng chính ứng dụng.

## 13. Các lỗi TLS phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra trước |
| --- | --- | --- |
| `PKIX path building failed` | Client không xây được chain tới CA tin cậy | File CA, intermediate chain, trust source thực tế |
| `SSLHandshakeException` | TLS negotiation/certificate hoặc policy không phù hợp | Root cause, TLS endpoint và log handshake |
| `No subject alternative names matching ...` | Host/IP kết nối không khớp SAN | Endpoint, DNS, leaf SAN, topology |
| `certificate expired` | Leaf hoặc CA trong chain hết hạn | `notBefore/notAfter`, kế hoạch rotation |
| `certificate not yet valid` | Chứng chỉ chưa có hiệu lực hoặc đồng hồ hệ thống sai | Thời gian UTC, đồng bộ clock và certificate |
| Connection reset/refused | Endpoint/cổng/TLS listener sai hoặc mạng chặn | Scheme, firewall, network policy, port |
| Seed hoạt động nhưng KV tới node khác lỗi | Địa chỉ node hoặc certificate node khác không hợp lệ | Topology, SAN trên các endpoint liên quan |
| TLS thành công nhưng `AuthenticationFailure` | Credentials/phương thức auth sai | Secret runtime, user và cơ chế auth |
| TLS + auth thành công nhưng `AccessDenied` | Thiếu quyền RBAC trên keyspace hoặc dịch vụ | Role, bucket/scope/collection và Query |
| `findById` chạy, `findBySku` lỗi | Query/index/permission hoặc Query service | SQL++ index, Query endpoint; không quy hết cho TLS |
| Sau xoay CA một số pod lỗi | Pod còn trust material/client cũ | Deployment rollout, mount CA, hiệu lực config |

Một lỗi `TimeoutException` không đủ để kết luận là TLS. Phải xác định đang timeout ở **bootstrap**, thao tác **Key-Value** hay **Query**. Nếu TLS handshake thật sự thất bại, tăng timeout có thể chỉ làm hệ thống chờ lâu hơn.

### 13.1. Trình tự xử lý khi hostname mismatch

1. Ghi nhận endpoint mà ứng dụng dùng, không ghi secret.
2. Xác nhận DNS phân giải trong runtime thật.
3. Kiểm tra tên host SDK kết nối sau bootstrap, đặc biệt với cluster nhiều node.
4. Đọc SAN của leaf certificate ở endpoint tương ứng.
5. Yêu cầu cấp lại certificate hoặc sửa cấu hình endpoint/topology cho khớp.
6. Kiểm thử qua SDK với hostname verification **vẫn bật**.

Không đổi mọi kết nối thành IP literal khi certificate chỉ có DNS SAN. Không thêm host alias tùy tiện chỉ để né DNS nếu SAN không bao phủ tên đó.

### 13.2. Trình tự xử lý lỗi trust chain

1. Xác định issuer của leaf certificate.
2. Kiểm tra các intermediate và root CA được phát hành đúng.
3. Xác định chính xác nguồn trust SDK đang dùng.
4. Cập nhật trust anchor bằng kênh quản lý được phép.
5. Khởi tạo lại client/deployment theo cơ chế nạp cấu hình hiện hành.
6. Xác minh certificate chain và hostname từ ứng dụng.

Không mặc định rằng import mọi CA tìm được vào truststore sẽ an toàn: chỉ tin những CA đã được xác minh nguồn gốc.

## 14. Vòng đời certificate và quy trình rotation

Một chứng chỉ hợp lệ hôm nay có thể hết hạn, bị thu hồi theo chính sách hoặc được thay khi cluster thay node. Thiết kế production cần chuẩn bị từ trước.

~~~mermaid
flowchart LR
    A["Theo dõi hạn certificate"] --> B["Chuẩn bị cert/CA mới"]
    B --> C["Cấp trust material có kiểm soát"]
    C --> D["Kiểm tra ở staging"]
    D --> E["Rolling rollout"]
    E --> F["Kiểm tra KV + SQL++ + metrics"]
    F --> G["Loại bỏ trust cũ khi an toàn"]
~~~

### 14.1. Nếu server certificate đổi nhưng CA không đổi

Khi CA tin cậy vẫn ký certificate mới, client có thể tiếp tục hoạt động nếu chain và SAN mới hợp lệ, nhưng điều này còn tùy trust model của ứng dụng. Nếu đã chọn cách **pin leaf**, leaf mới sẽ yêu cầu cập nhật trust; vì thế pinning phải đi cùng kế hoạch rotation cụ thể.

### 14.2. Nếu CA/trust anchor đổi

Có thể cần giai đoạn chuyển tiếp tin cậy đồng thời CA cũ và mới khi chính sách cho phép, sau đó loại bỏ CA cũ sau khi cluster đã xoay và toàn bộ client được cập nhật. Việc tin CA song song cần giới hạn thời gian và kiểm tra kỹ, không kéo dài vô hạn.

### 14.3. Java process có tự nạp CA mới không?

Không nên giả định sửa file CA hoặc thay biến môi trường sẽ khiến một `ClusterEnvironment`/`Cluster` đang sống tự đổi trust configuration. Nhiều thiết lập được đọc khi tạo môi trường/client hoặc TLS context. Nếu không có cơ chế hot reload chính thức được kiểm chứng, áp dụng rolling restart để client khởi tạo với trust material mới.

Đừng shutdown client dùng chung từ một repository để ép nạp lại certificate. Dừng nhận request mới, để request đang xử lý hoàn tất theo chính sách rồi đóng ứng dụng ở ranh giới vòng đời.

## 15. TLS và hiệu năng, timeout, reactive

TLS có chi phí bắt tay và mã hóa nhưng đây không phải lý do để tắt xác minh máy chủ trong production. Couchbase Java SDK quản lý kết nối và tái sử dụng client; không tạo một `Cluster.connect(...)` cho mỗi request vì sẽ phải bootstrap/handshake lặp lại.

| Mối quan tâm | Điều cần nhớ |
| --- | --- |
| Connect timeout | TLS handshake có thể nằm trong quá trình kết nối; vẫn cần phân loại lỗi thực tế |
| KV timeout | Đọc/ghi trên Data service sau khi kết nối; không sửa bằng đổi CA khi TLS đã ổn |
| Query timeout | Truy vấn SQL++ yêu cầu Query service và index, dù kết nối được mã hóa |
| CAS/`@Version` | Kiểm soát cập nhật cạnh tranh, không xác minh hostname |
| TTL | Thời hạn của document, không phải thời hạn của certificate |
| Transaction | Có deadline/điều kiện riêng; kênh TLS chỉ bảo vệ đường truyền |
| Reactive | Vẫn dùng hạ tầng SDK TLS; `Mono`/`Flux` không bỏ qua certificate verification |

### 15.1. Reactive vẫn cần TLS hợp lệ

Với `ReactiveCouchbaseRepository` hoặc `ReactiveCouchbaseTemplate`, kết nối SDK phía dưới vẫn áp dụng chính sách TLS. Một `Mono` thất bại vì PKIX hoặc SAN mismatch không thể được “sửa” bằng `retryWhen` lặp vô hạn. Trước tiên sửa trust/hostname đúng tầng.

Một mutation reactive khi timeout có thể có kết quả mơ hồ; hủy subscription cũng không chứng minh lệnh ghi chưa được server áp dụng. Nếu thiết kế retry cho ghi, phải xét idempotency, CAS hoặc đối soát trạng thái.

## 16. Kiểm tra xuyên suốt từ TLS đến dữ liệu

Sau khi cấu hình TLS, cần kiểm chứng theo thứ tự để tránh nhầm lỗi bảo mật kết nối với lỗi mapping/index:

~~~mermaid
flowchart TD
    A["Kết nối TLS tới endpoint"] --> B{"Handshake + hostname hợp lệ?"}
    B -- "Không" --> C["CA/chain/SAN/DNS/port"]
    B -- "Có" --> D{"Couchbase authentication?"}
    D -- "Không" --> E["Credentials/certificate auth"]
    D -- "Có" --> F{"Bucket/collection KV truy cập được?"}
    F -- "Không" --> G["Bucket, scope, collection, RBAC, Data"]
    F -- "Có" --> H{"SQL++ hoạt động?"}
    H -- "Không" --> I["Query service, index, Query RBAC"]
    H -- "Có" --> J["Đo latency, error rate và readiness"]
~~~

### 16.1. Smoke test KV bằng Spring Data client factory

Ví dụ dưới đây chỉ dùng ở profile local/staging đã chuẩn bị quyền và keyspace:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;

@Configuration(proxyBeanMethods = false)
@Profile("local")
class CouchbaseTlsSmokeTestConfig {

    @Bean
    ApplicationRunner verifyConnectionAndKv(
            CouchbaseClientFactory factory) {

        return args -> {
            // ID không tồn tại vẫn có thể cho kết quả false hợp lệ.
            boolean exists = factory.getBucket()
                    .scope("catalog")
                    .collection("products")
                    .exists("probe::missing")
                    .exists();

            System.out.println("Couchbase KV probe completed: " + exists);
        };
    }
}
~~~

Kiểm tra này chỉ xác nhận đường **Key-Value** tới collection đang chọn; không chứng minh có index SQL++ hoặc quyền Query. Sau đó kiểm tra một repository query theo thuộc tính trên collection đã được tạo index phù hợp.

Với production, dùng readiness/health được thiết kế có timeout, rate limit và phạm vi kiểm chứng phù hợp, thay vì đặt một lệnh đồng bộ không kiểm soát vào mọi lần startup.

### 16.2. Index SQL++ là phần khác với TLS

Giả sử `ProductDocument` ánh xạ `inventory.catalog.products` và repository có phương thức `findBySku`, index ví dụ có thể là:

~~~sql
CREATE INDEX ix_products_sku
ON `inventory`.`catalog`.`products`(`sku`);
~~~

Index phải được provision và sẵn sàng trên server. TLS handshake thành công không tạo index; thiếu index không được sửa bằng cách giảm TLS security hoặc thay truststore.

## 17. Bài tập tình huống: từ local sang cluster TLS

Một dịch vụ catalog ban đầu chạy local với:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://127.0.0.1
  data:
    couchbase:
      bucket-name: inventory
~~~

Khi chuyển production, nhóm vận hành cấp endpoint `cb.example.internal`, một file CA PEM và user ứng dụng chỉ có quyền vào `inventory.catalog.products`. Sau rollout, xuất hiện ba báo cáo:

1. Một số pod lỗi `PKIX path building failed`.
2. Một số pod bootstrap được nhưng thao tác KV đến node khác lỗi hostname mismatch.
3. Sau khi sửa TLS, `findById` chạy được nhưng `findBySku` vẫn lỗi.

**Yêu cầu thực hành:**

1. Đổi connection string sang endpoint TLS và đưa credentials vào biến môi trường/secret.
2. Xác định SDK đang lấy trust từ đâu; cấp đúng CA cho runtime và kiểm tra chain.
3. Đối chiếu SAN với **tất cả hostname thực sự được SDK sử dụng**, kể cả node sau bootstrap.
4. Không dùng giải pháp tắt hostname verification hay chấp nhận mọi certificate.
5. Kiểm tra RBAC trên `inventory.catalog.products` và Query service/index cho `findBySku`.
6. Đưa certificate rotation vào runbook triển khai, gồm thử staging, rollout và quan sát.
7. Đề xuất cách chứng minh đã khắc phục: handshake, KV probe, SQL++ probe và latency/error metrics.

Một cấu hình khởi đầu an toàn về mặt tổ chức:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: inventory

app:
  couchbase:
    trusted-ca-file: "${COUCHBASE_CA_FILE:/etc/couchbase/tls/ca.pem}"
~~~

`app.couchbase.trusted-ca-file` là **property tự định nghĩa**; nếu chọn dùng nó phải có cấu hình Java/SSL support thực sự nạp CA. Chỉ khai báo YAML này sẽ **không** khiến Spring Boot tự tin cậy file `ca.pem`.

**Hướng trả lời:** lỗi thứ nhất nằm ở trust chain/nguồn CA; lỗi thứ hai nằm ở SAN/hostname của endpoint sau bootstrap; lỗi thứ ba nằm ở Query service, index hoặc quyền SQL++. Ba lỗi cần ba nhóm kiểm tra khác nhau. Tăng timeout hoặc bỏ xác minh chứng chỉ không phải giải pháp đúng.

## 18. Checklist trước triển khai

- [ ] Connection string dùng scheme TLS và endpoint đúng với topology thực tế khi môi trường yêu cầu.
- [ ] Certificate chain tới CA tin cậy; CA được phân phối từ nguồn đã xác minh.
- [ ] Certificate còn hiệu lực, các tên DNS/IP mà SDK dùng đều khớp SAN.
- [ ] Hostname verification luôn bật; không có cấu hình trust-all trong production.
- [ ] Credentials, private key (nếu mTLS) và secrets không bị commit/log.
- [ ] Container/pod đọc được file trust, DNS/port/node quảng bá đều reachable.
- [ ] Spring Boot/SDK sử dụng đúng **một cấu hình TLS có hiệu lực**, không có bean/client trùng.
- [ ] TLS handshake và xác thực thành công với tài khoản ứng dụng ít quyền nhất.
- [ ] KV probe đúng bucket/scope/collection hoạt động; SQL++ được kiểm chứng riêng.
- [ ] Có chính sách theo dõi hạn chứng chỉ, xoay CA và rolling restart khi cần.

## 19. Tổng kết

**TLS** bảo vệ đường truyền và xác minh danh tính server khi được cấu hình đúng. Với Spring Data Couchbase, kết nối `couchbases://`, chính sách trust trong `ClusterEnvironment`, certificate chain và **SAN/hostname verification** phải nhất quán với các endpoint mà Couchbase SDK thực sự kết nối.

Cần phân biệt server certificate với CA/truststore, client certificate trong mTLS và thông tin đăng nhập/RBAC. Việc vô hiệu hóa certificate validation không phải cách xử lý lỗi production. Hãy sửa đúng nguồn trust, tên endpoint hoặc certificate, rồi kiểm chứng KV và SQL++.

Trên nền kết nối được bảo mật, ứng dụng mới có thể triển khai an toàn document mapping, repository, `CouchbaseTemplate`, index SQL++, TTL, CAS, giao dịch và API reactive với những yêu cầu về hiệu năng, nhất quán và khả năng vận hành.


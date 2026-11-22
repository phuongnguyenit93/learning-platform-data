# Chẩn đoán lỗi xác thực, quyền truy cập và chứng thư

## 1. Tình huống mở đầu: “Không kết nối được database” là ba lỗi khác nhau

Một ứng dụng Java đọc thông tin đơn hàng từ MongoDB, Redis và DynamoDB. Sau khi đổi image triển khai, ba nhóm người dùng báo lỗi:

```text
Service A:
  javax.net.ssl.SSLHandshakeException:
  PKIX path building failed

Service B:
  MongoCommandException:
  Command failed with error ... Unauthorized

Service C:
  DynamoDbException:
  AccessDeniedException while calling GetItem
```

Nhóm trực vận hành định xử lý cả ba bằng cách “đổi password database”. Đây là phản ứng nguy hiểm vì các lỗi ở **những lớp khác nhau**:

- **Lỗi A:** Java không xác thực được chuỗi tin cậy của chứng thư server trong bắt tay TLS; thường chưa tới bước đăng nhập ứng dụng.
- **Lỗi B:** Có thể client đã được xác thực nhưng principal thiếu quyền với thao tác hoặc tài nguyên đích.
- **Lỗi C:** Một yêu cầu API AWS bị từ chối theo IAM hoặc chính sách liên quan; có thể danh tính có thật nhưng không được phép `GetItem` trên tài nguyên được chỉ định.

Nếu xử lý sai lớp, bạn có thể tạo thêm sự cố, làm lộ credential hoặc nới quyền quá mức mà lỗi vẫn tồn tại.

Bài học này thuộc **Database No SQL → Quan sát và chẩn đoán → Chẩn đoán lỗi xác thực, quyền truy cập và chứng thư**. Trọng tâm là một quy trình điều tra **có bằng chứng, không đoán lỗi từ một dòng thông báo, không tắt cơ chế bảo mật để làm cho kết nối “chạy được”**.

---

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt lỗi **mạng/định tuyến**, **TLS**, **xác thực (authentication)**, **phân quyền (authorization)** và lỗi **logic dữ liệu**.
2. Giải thích vai trò của CA, certificate chain, leaf certificate, SAN, hostname validation, SNI, truststore và keystore.
3. Chẩn đoán `PKIX path building failed`, `certificate expired`, `hostname mismatch`, lỗi mTLS và sai TLS protocol/cipher.
4. Hiểu sự khác nhau giữa **server certificate** và **client certificate**, cũng như identity mapping sau mTLS.
5. Kiểm tra cơ chế SCRAM, Redis ACL, Cassandra roles, IAM của DynamoDB và quyền trên search/graph/document databases.
6. Phân biệt “credential sai” với “credential đúng nhưng không đủ quyền”.
7. Quan sát tác động của rotation, token expiry, clock skew, connection pooling, failover và thay đổi endpoint.
8. Thu thập logs/traces/metrics chẩn đoán mà không lộ password, private key, access token hay dữ liệu nhạy cảm.
9. Xây các probe Java an toàn cho TLS, xác thực và một thao tác quyền tối thiểu.
10. Thiết kế runbook, kiểm thử lỗi có chủ đích, kế hoạch khôi phục và các guardrails để không nới quyền vô tội vạ.

## 3. Luồng xử lý một lời gọi NoSQL

```mermaid
flowchart TD
    A["Java service: gọi repository"] --> B["DNS / route / TCP hoặc HTTPS"]
    B --> C{"Thiết lập TLS nếu yêu cầu"}
    C -->|Lỗi| X1["TLS / certificate failure"]
    C -->|Thành công| D["Gửi credentials, proof hoặc signed request"]
    D --> E{"Authentication hợp lệ?"}
    E -->|Không| X2["Unauthenticated / invalid identity"]
    E -->|Có| F{"Principal có quyền?"}
    F -->|Không| X3["Forbidden / Unauthorized command"]
    F -->|Có| G["Thực thi query/command"]
    G --> H{"Operation và dữ liệu hợp lệ?"}
    H -->|Không| X4["Schema, conflict, capacity, consistency..."]
    H -->|Có| I["Response"]
```

Đây là **mô hình khái niệm**, không phải mọi dịch vụ thực thi đúng thứ tự từng bước.

- DynamoDB dùng HTTPS và request signing; danh tính/chính sách được đánh giá trong quá trình xử lý API.
- Redis có thể chạy không TLS nếu deployment cấu hình như vậy, nhưng kết nối production cần tuân yêu cầu bảo mật thực tế.
- Một proxy/gateway có thể chặn request **trước** khi đến database.
- mTLS có thể xác thực client certificate tại transport layer; database vẫn có thể áp RBAC sau đó.

**Nguyên tắc:** Hãy xác định lớp đầu tiên xảy ra lỗi. Đổi role không chữa được chứng thư CA sai; thêm CA không cấp quyền cho `GetItem`.

## 4. Authentication và authorization không phải một

**Authentication (AuthN)** trả lời: *Bên đang gọi là ai? Danh tính có được chứng minh hợp lệ không?*

Ví dụ:

```text
Username/password hợp lệ
SCRAM challenge response thành công
TLS client certificate được chấp nhận
AWS SDK ký request bằng credentials còn hiệu lực
Bearer token có chữ ký/audience hợp lệ
```

**Authorization (AuthZ)** trả lời: *Danh tính đã được nhận diện có quyền làm thao tác này trên tài nguyên này, trong ngữ cảnh này hay không?*

Ví dụ:

```text
Principal = catalog-reader
Operation = DELETE
Resource  = orders
Decision  = DENY
```

### 4.1. Hai kiểm tra liên tiếp

Một tài khoản `report-reader` đăng nhập MongoDB thành công nhưng gọi `dropDatabase` bị từ chối. Đó là behavior mong muốn của least privilege.

Ngược lại, một user có role `readWrite` ở database `shop` nhưng gửi sai mật khẩu sẽ không vượt qua AuthN.

### 4.2. HTTP 401 và 403 là gợi ý, không phải định luật NoSQL

Trong API HTTP:

- `401 Unauthorized` thường biểu thị cần xác thực/credential không hợp lệ.
- `403 Forbidden` thường biểu thị request bị từ chối dù đã biết danh tính hoặc do policy khác.

Nhưng một proxy, WAF, API gateway, managed service hoặc cơ chế che giấu tài nguyên có thể trả mã khác nhau. MongoDB, Cassandra, Redis, Neo4j có protocol errors riêng, **không phải mọi lỗi đều dùng HTTP status**.

## 5. Ma trận phân loại nhanh theo lớp lỗi

| Lớp | Triệu chứng thường gặp | Kiểm tra trước | Không nên làm |
| --- | --- | --- | --- |
| DNS | `UnknownHostException` | Hostname, resolver, network scope | Đổi mật khẩu |
| TCP/connect | `ConnectException`, timeout | Port, route, firewall, listener | Thêm quyền admin |
| TLS trust | `PKIX path building failed` | CA chain, truststore, endpoint | `trustAll` |
| TLS hostname | SAN/hostname mismatch | DNS/SNI và tên trong cert | Tắt hostname verification |
| TLS mTLS | `bad_certificate`, missing client cert | Keystore, clientAuth policy | Copy private key vào repo |
| AuthN | Invalid username/password/token | Mechanism, principal, secret version | Mở firewall toàn mạng |
| AuthZ | Permission denied/forbidden | Exact action, resource, role/policy | Cấp `*:*` |
| Data/query | Unknown table, invalid query | Schema, keyspace, query | Đổi chứng thư |
| Capacity | Throttling/too many requests | Limits, hot partitions, retry | Coi là AuthN |
| Consistency | Unavailable/quorum failure | Replica placement, CL | Tắt TLS |
| Business | Conditional write rejected | Preconditions/version | Retry vô hạn |

Triệu chứng gợi ý **giả thuyết**, không thay thế stack trace/cause chain và context từ service.

## 6. Ranh giới tin cậy: database, proxy, cloud API và ứng dụng

Một lời gọi có thể qua nhiều thành phần:

```text
Java API
  -> local service mesh sidecar
  -> API gateway / load balancer
  -> database proxy / cloud endpoint
  -> database service
  -> database authorization rules
```

Có thể có nhiều chứng thư và chính sách:

- Sidecar kiểm tra mTLS giữa services.
- Load balancer có server certificate khác database node.
- Proxy xác thực IAM hoặc OAuth, sau đó dùng service identity riêng đi tới DB.
- Database kiểm tra SCRAM/roles của chính nó.
- Business service kiểm tra tenant scope ngoài DB RBAC.

### 6.1. Lỗi ở proxy không phải lỗi engine

Một `403` từ WAF/proxy có thể xảy ra **trước** khi request đến DynamoDB/Search. Xem response headers, request ID được cấp, gateway access logs và trace routing để định vị.

### 6.2. Không nhầm tên endpoint với danh tính TLS

Kết nối qua alias DNS/proxy cần chứng thư hợp lệ cho **hostname client thực sự kiểm tra**. Nếu database chuyển từ `db.internal.example` sang `db-new.internal.example`, đổi DNS có thể làm lộ hostname mismatch dù tài khoản DB không đổi.

### 6.3. Xác định ai kết thúc TLS

Có trường hợp TLS kết thúc ở proxy và một phiên TLS khác dùng tới backend. Điều tra phải biết **bước handshake nào** thất bại; nhìn certificate backend khi client chỉ nhìn proxy cert sẽ sai hướng.

## 7. Thu thập bằng chứng trong 5 phút đầu

Trước khi chỉnh cấu hình, ghi nhận:

1. **Ứng dụng/endpoint:** service, build version, Java runtime, driver version, database product/mode.
2. **Thời điểm bắt đầu lỗi:** có trùng deploy, rotation, failover, thay image hoặc thay DNS không?
3. **Phạm vi:** tất cả requests hay một role, collection/table, region, pod, node?
4. **Exact exception class và cause chain:** từ lỗi ngoài cùng tới nguyên nhân sâu nhất.
5. **Operation:** login, `ping`, `find`, `insert`, `GetItem`, `Query`, index search, admin operation?
6. **Principal reference:** account/role/subject an toàn, không ghi credential.
7. **Credential source:** secret manager, environment, workload identity, file mount, token provider.
8. **TLS metadata:** host/SNI, issuer, SAN, notBefore/notAfter, truststore **path/type**.
9. **Request/trace ID:** để nối API, driver và provider logs.
10. **Các instance khỏe:** so configuration và đường mạng thay vì đoán.

### 7.1. Nhật ký ví dụ an toàn

```json
{
  "time": "2026-11-14T08:21:00Z",
  "service": "orders-api",
  "serviceVersion": "release-2026-11",
  "dbSystem": "mongodb",
  "dbOperation": "find",
  "endpointClass": "private-replica",
  "region": "ap-southeast-1",
  "credentialProvider": "secret-manager",
  "principalRef": "orders-reader",
  "tlsEnabled": true,
  "errorClass": "AUTHORIZATION_DENIED",
  "requestId": "REQ-3E9",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "retryCount": 0
}
```

`principalRef` và endpoint class chỉ được ghi nếu chính sách logging cho phép. Không xuất password, access key, token, private key, raw connection URI hoặc database document vào log.

## 8. Đọc exception chain thay vì chỉ đọc thông báo cuối

Một Java stack trace có thể có nhiều lớp:

```text
RepositoryAccessException
  caused by MongoSocketOpenException
    caused by SSLHandshakeException
      caused by ValidatorException
        caused by SunCertPathBuilderException
```

Lúc này truy vấn không thất bại vì field `_id` hay role thiếu: lỗi gốc là quá trình xây certificate trust path.

Ngược lại:

```text
RepositoryAccessException
  caused by MongoCommandException:
  not authorized to execute command
```

là tín hiệu phân quyền sau khi đi tới DB.

### 8.1. Lỗi bao ngoài có thể đặt tên chung

Framework có thể chuyển lỗi thành `DataAccessException`, `ServiceUnavailable` hoặc HTTP 500. Nếu chỉ xem lớp ngoài cùng, bạn sẽ đánh đồng certificate expiry với query conflict.

### 8.2. Không parse message thành policy duy nhất

Chuỗi lỗi thay đổi theo driver/server version, localization và proxy. Prefer:

- Exception type.
- Structured error code/status khi có.
- Driver-specific error categories.
- Cause chain.
- Operation/endpoint context.

Message vẫn hữu ích cho con người, nhưng không dùng substring `"authentication"` để tự cấp quyền hoặc rotate secrets.

## 9. Chẩn đoán TLS: TLS cung cấp điều gì?

TLS thường phục vụ:

1. **Confidentiality:** dữ liệu trên đường truyền được mã hóa.
2. **Integrity:** giảm nguy cơ thay đổi dữ liệu mà không bị phát hiện.
3. **Server authentication:** client kiểm tra endpoint đúng server/certificate đáng tin.
4. **Client authentication** trong mTLS, nếu cấu hình.

TLS thành công không có nghĩa:

- User được phép xem mọi table.
- Query nghiệp vụ hợp lệ.
- Replica đã nhất quán.
- Token không hết hạn trong tương lai.
- API được miễn kiểm tra tenant ownership.

**Mỗi lớp bảo vệ có một hợp đồng riêng.**

## 10. Chuỗi chứng thư: leaf, intermediate và root CA

Một server có thể gửi:

```text
Leaf certificate:
  Subject/SAN -> db.internal.example
  Issuer      -> Internal Intermediate CA

Intermediate CA:
  Issuer      -> Corporate Root CA

Root CA:
  Trust anchor trong JVM truststore
```

Client xây chuỗi tin cậy từ leaf qua intermediate tới trust anchor phù hợp.

### 10.1. `PKIX path building failed` có thể do đâu?

- JVM thiếu root CA được tin cậy.
- Server không gửi intermediate cần thiết.
- Truststore tùy chỉnh được khai báo nhưng chứa sai CA.
- Client đang kết nối một endpoint/proxy với certificate khác.
- Certificate bị thay trong rotation, CA không còn như trước.
- Certificate chain/constraints không hợp lệ.
- Java security policy không chấp nhận thuật toán chữ ký hoặc kích thước khóa.
- Runtime đang dùng truststore khác với bản dev.

**Không tự kết luận “chứng thư đã hết hạn” chỉ từ câu `PKIX path building failed`.** Đây là nhóm lỗi liên quan validation path, cần xem cause cụ thể.

### 10.2. Root CA không cần luôn được server gửi

Trong các triển khai TLS, trust anchor thường nằm ở client. Việc server không gửi root certificate không tự làm kết nối sai; vấn đề là liệu client có xây được một đường tin cậy hợp lệ hay không.

### 10.3. `-Djavax.net.ssl.trustStore` có hệ quả

Nếu cấu hình JVM dùng truststore riêng, một số ứng dụng có thể **không còn sử dụng danh sách CA mặc định** theo cách trước. Một truststore chỉ chứa CA nội bộ có thể khiến request HTTPS tới cloud API khác bị lỗi.

Phải hiểu phạm vi SSLContext/truststore, thay vì đặt property toàn JVM một cách vội vàng.

## 11. Hostname verification và SAN

Một certificate có SAN:

```text
DNS:db-a.internal.example
DNS:db-b.internal.example
```

Client kết nối `db.internal.example` có thể bị hostname mismatch nếu tên đó không nằm trong phạm vi certificate hợp lệ.

### 11.1. Các lỗi hay gặp

- Dùng IP `10.0.3.10` thay vì DNS name có trong SAN.
- Đổi Kubernetes Service name nhưng chưa cấp certificate mới.
- Trỏ tới endpoint managed khác region.
- Dùng CNAME/alias nhưng cert không bao gồm hostname client kiểm tra.
- Proxy TLS trả certificate mặc định do SNI không khớp.
- Gọi localhost qua port-forward nhưng TLS xác minh hostname production/localhost không tương ứng.

### 11.2. CN không phải thay thế đáng tin cho SAN

Các Java/TLS stacks hiện đại thường dựa vào SAN và hostname validation rules. Không thiết kế chứng thư mới chỉ dựa vào Common Name rồi hy vọng mọi client vẫn chấp nhận.

### 11.3. SNI là gì?

**Server Name Indication (SNI)** cho phép client báo hostname đang hướng tới trong TLS handshake để server/proxy chọn certificate tương ứng.

Một proxy phục vụ nhiều hostnames có thể trả sai cert nếu client không gửi SNI thích hợp. Nhưng **SNI không thay hostname verification**; client vẫn phải kiểm tra tên chứng thư của server phản hồi.

## 12. Kiểm tra thời hạn chứng thư và đồng hồ

Certificate có những mốc:

```text
Not Before: 2026-10-01T00:00:00Z
Not After:  2027-01-01T00:00:00Z
```

Nếu ngày giờ của client nằm ngoài khoảng hợp lệ, validation có thể thất bại.

### 12.1. Ba trường hợp riêng

- **Expired:** thời điểm hiện tại sau `Not After`.
- **Not yet valid:** trước `Not Before`.
- **Clock skew:** thời gian system/JVM/container lệch với nguồn đáng tin, tạo lỗi giả.

### 12.2. Clock ảnh hưởng cả cloud signature

Với AWS SigV4 và một số token có timestamp, thời gian client lệch lớn có thể gây signature/token rejection dù certificate server vẫn hợp lệ.

Đừng “sửa” bằng cách vô hiệu hóa certificate validation. Kiểm tra time synchronization, timezone configuration, thời gian thực tế UTC và token validity.

### 12.3. Chỉ gia hạn chứng thư có đủ chưa?

Chưa chắc. Sau rotation có thể thay:

- Intermediate/root CA.
- SAN.
- Key algorithm.
- Client identity mapping.
- PEM/PKCS12 path.
- Password bảo vệ private key.

Phải kiểm tra **toàn bộ handshake và access path** sau rotation, không chỉ so `Not After`.

## 13. Truststore và keystore trong Java

**Truststore** chứa các trust anchors/certificates mà client dùng để xác minh đối tác TLS.

**Keystore** trong ngữ cảnh mTLS có thể chứa client private key và certificate chain để chứng minh danh tính client.

Hai khái niệm có thể cùng sử dụng định dạng PKCS12/JKS; tên file `.jks` hay `.p12` chỉ là một dấu hiệu, **không chứng minh file chứa đúng loại entry hoặc hợp lệ**.

### 13.1. Các nguồn cấu hình thường gặp

```text
JDK default truststore
  $JAVA_HOME/lib/security/cacerts

JVM system properties
  javax.net.ssl.trustStore
  javax.net.ssl.trustStoreType
  javax.net.ssl.keyStore
  javax.net.ssl.keyStoreType

Application SDK/driver configuration
  SSLContext
  TrustManagerFactory
  KeyManagerFactory

Container/deployment
  Mounted Secret/ConfigMap
  Java runtime image
  Sidecar/proxy certificate injection
```

Không mặc định mọi driver dùng các Java properties toàn cục. Một SDK có thể có SSLContext hoặc HTTP transport riêng; một sidecar có thể kết thúc TLS trước khi request đến driver.

### 13.2. Đổi Java base image có thể đổi trust behavior

Hai containers đều chạy “Java 17” nhưng chứa bản `cacerts`, security policies hoặc OS CA bundles khác nhau. Điều tra nên ghi rõ runtime image digest/build chứ không chỉ số major JDK.

### 13.3. Không lưu private key trong Git

Private key và keystore passwords phải được quản lý bằng secret manager và access controls. Không paste nội dung `.p12`, `.key`, PEM private key vào issue hoặc log.

## 14. Ví dụ Java: tạo SSLContext từ truststore PKCS12

Đoạn mã minh họa tạo context dùng CA riêng, **không bỏ qua certificate validation**:

```java
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

public final class TlsContexts {
    private TlsContexts() {}

    public static SSLContext fromTrustStore(
            Path storePath,
            char[] storePassword
    ) throws Exception {

        KeyStore store = KeyStore.getInstance("PKCS12");

        try (InputStream in = Files.newInputStream(storePath)) {
            store.load(in, storePassword);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );

        tmf.init(store);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(),
            new SecureRandom());

        return context;
    }
}
```

### 14.1. Điều cần hiểu

- `TrustManagerFactory` kiểm tra certificate chain theo trust material.
- `SSLContext` này có thể được truyền cho driver/HTTP transport **nếu SDK hỗ trợ cách cấu hình đó**.
- Snippet không tự bật hostname verification cho mọi kiểu socket tùy ý; phải để transport/driver áp hostname verification theo API đúng.
- Dùng truststore riêng có thể thay danh sách CA tin cậy so với mặc định của ứng dụng.
- Mã ví dụ ném `Exception` để ngắn gọn; production nên phân loại lỗi đọc file, password, trust material và handshake.

### 14.2. Đường dẫn file không nên cố định

Trong container:

```text
/app/certs/db-trust.p12
```

có thể là mount path được điều phối từ secret manager. Đọc từ cấu hình, kiểm tra quyền file và xử lý rotation theo chiến lược SDK đang dùng.

## 15. Mutual TLS: khi server cũng yêu cầu client certificate

TLS một chiều:

```text
Java client -- verifies --> database server certificate
```

mTLS:

```text
Java client -- verifies --> server certificate
Database  -- verifies --> client certificate
```

Trong mTLS, client thường cần:

- Certificate có mục đích client authentication theo chính sách.
- Private key tương ứng certificate.
- Certificate chain phù hợp.
- Keystore chứa private-key entry đúng alias.
- Key manager được SSLContext/driver sử dụng.
- Server trust CA phát hành client cert.
- Identity mapping từ cert sang user/role khi database hỗ trợ.

### 15.1. TLS xác thực certificate không tự cấp DB roles

Một client cert hợp lệ có thể được server chấp nhận tại transport, nhưng principal trong DB chưa được map hoặc thiếu quyền. Khi đó handshake thành công nhưng command vẫn `Unauthorized`.

### 15.2. Certificate và private key phải là một cặp

Nếu triển khai certificate mới nhưng private key cũ, handshake có thể thất bại. Không tiết lộ private key để “so sánh nhanh”; dùng công cụ an toàn xác minh public-key correspondence theo quy trình quản lý chứng thư.

## 16. Ví dụ Java: cấu hình mTLS từ PKCS12

```java
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

public final class MutualTlsContext {
    private static KeyStore load(
            Path path,
            char[] password
    ) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, password);
        }
        return store;
    }

    public static SSLContext create(
            Path trustStorePath,
            char[] trustPassword,
            Path keyStorePath,
            char[] keyPassword
    ) throws Exception {

        KeyStore trust = load(trustStorePath, trustPassword);
        KeyStore identity = load(keyStorePath, keyPassword);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trust);

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm()
        );
        kmf.init(identity, keyPassword);

        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(kmf.getKeyManagers(), tmf.getTrustManagers(),
            new SecureRandom());

        return ctx;
    }
}
```

Đoạn mã chỉ cấu hình phần **TLS identity/trust**. Cách dùng SSLContext trong MongoDB, Cassandra, Redis, HTTP SDK khác nhau; ngoài ra hostname verification và authz vẫn phải được driver/transport áp dụng đúng.

### 16.1. Không dùng “trust-all” như giải pháp production

Một ví dụ thường thấy trên diễn đàn:

```java
// ANTI-PATTERN: tự cài TrustManager
// luôn chấp nhận mọi certificate của server.
```

Làm vậy phá kiểm tra danh tính máy chủ và mở nguy cơ man-in-the-middle. Giải pháp đúng là sửa CA chain, SAN, truststore, SNI hoặc certificate hợp lệ.

## 17. Các triệu chứng TLS thường gặp và hướng kiểm tra

| Triệu chứng | Có thể do | Kiểm tra |
| --- | --- | --- |
| `PKIX path building failed` | Không xây được trust chain | CA, intermediate, truststore thực dùng |
| `CertificateExpiredException` | Cert quá hạn | NotAfter, endpoint/proxy, rotation |
| `CertificateNotYetValidException` | NotBefore hoặc clock | UTC clock, certificate dates |
| `No subject alternative DNS name matching` | Hostname mismatch | SAN, DNS endpoint, SNI |
| `bad_certificate` alert | Client/server cert bị từ chối | mTLS, chain, usage, key |
| `certificate_required` | Thiếu client cert ở mTLS | Keystore/key manager |
| `handshake_failure` | Nhiều nguyên nhân | TLS versions, ciphers, cert, mTLS |
| `protocol_version` | Không thống nhất TLS protocol | JDK policy, server TLS versions |
| `no cipher suites in common` | Không có cipher overlap | JDK/server cipher settings |
| `UnrecoverableKeyException` | Không load private key | Keystore, alias, password |
| `InvalidAlgorithmParameterException` | Security config/trust anchors | Truststore, algorithm constraints |
| Kết nối timeout trước TLS | DNS/TCP/network | Không chẩn đoán vội thành CA |

Một TLS alert từ server có thể mơ hồ. Phải xem **cả phía client lẫn server/proxy**, với quyền phù hợp, thay vì suy nguyên nhân duy nhất từ tên alert.

## 18. Công cụ kiểm tra chứng thư mà không sửa quyền

Những lệnh dưới đây chỉ là **ví dụ thao tác chẩn đoán có chủ đích trên endpoint được phép**; không chạy chúng trên môi trường thật nếu chưa có quyền và quy trình phù hợp.

### 18.1. Xem metadata truststore

```bash
keytool -list \
  -keystore /path/to/db-trust.p12 \
  -storetype PKCS12
```

Lệnh có thể yêu cầu password theo cách an toàn. Không đặt password trên dòng lệnh vì có thể lộ qua terminal history, process list hoặc CI logs.

### 18.2. Kiểm tra TLS endpoint với OpenSSL

Ví dụ endpoint TLS:

```bash
openssl s_client \
  -connect db.internal.example:27017 \
  -servername db.internal.example \
  -verify_hostname db.internal.example \
  -verify_return_error \
  -CAfile /path/to/approved-ca.pem
```

Một kết nối thử thành công từ máy vận hành **không chứng minh** container Java production dùng cùng DNS, CA, mTLS, route hoặc JDK security policy. Kiểm tra cần thực hiện ở **network context tương đương ứng dụng**.

### 18.3. `openssl` và Java có thể cho kết quả khác

Khác nhau có thể đến từ:

- Truststore/CA bundle.
- TLS/cipher implementation.
- SNI.
- Certificate revocation configuration.
- Hostname validation.
- Java algorithm restrictions.
- Client certificate identity.

Khi OpenSSL kết nối thành công nhưng Java vẫn thất bại, hãy so **cùng endpoint, cùng host, cùng trust material và validation settings**, không dùng một công cụ thay chứng cứ của công cụ kia.

## 19. JVM TLS debug: hữu ích nhưng nhạy cảm

Có thể bật chẩn đoán JSSE trong môi trường thử nghiệm:

```text
-Djavax.net.debug=ssl,handshake
```

Đầu ra giúp xem quá trình chọn protocol, certificate chain và handshake events. Tuy nhiên:

- Log rất nhiều và làm tăng overhead.
- Có thể lộ metadata nội bộ về endpoint/identity.
- Một số cấu hình/phiên bản có thể phơi bày thông tin nhạy cảm hơn kỳ vọng.
- Không bật dài hạn ở production hoặc đẩy toàn bộ output vào kênh log công khai.
- Cần giới hạn thời gian, phân quyền truy cập và xóa file theo retention policy.

### 19.1. Đừng bật debug trên mọi pod ngay lập tức

Có thể chọn **một canary pod**, tăng mức logging trong một khoảng có kiểm soát, sau đó tắt và so với pod khỏe. Điều này làm giảm chi phí và khả năng vô tình ghi thông tin nhạy cảm.

### 19.2. DEBUG không tự chữa lỗi

Chứng thư hết hạn hoặc sai SAN không được giải quyết bằng việc tăng log level. Log giúp xác định **nguyên nhân cần sửa**.

## 20. TLS rotation và cache kết nối lâu sống

Một Java service thường tạo một database client/pool dài hạn. Sau khi chứng thư được rotate:

```text
Old TLS connections: vẫn còn hoạt động
New TLS connections: phải handshake lại
```

Vì vậy sự cố có thể xuất hiện **theo đợt**:

- Một số requests thành công qua connections cũ.
- Requests mở connection mới thất bại do CA/truststore sai.
- Sau restart, 100% requests thất bại.
- Mỗi region/pod có image hoặc secret version khác nên chỉ một phần lỗi.

### 20.1. Giữ trust overlap trong giai đoạn chuyển đổi

Khi đổi CA có kế hoạch, có thể cần một thời gian client tin cậy **cả CA cũ và CA mới** nếu chính sách cho phép, sau đó loại CA cũ đúng mốc. Không triển khai truststore mới sau khi server đã đổi nếu service không thể reconnect an toàn.

### 20.2. Kiểm tra client có reload cert không

Không mặc định thay file mount là một `SSLContext` đã tạo sẽ tự reload. Một số SDK đọc cert ở startup; muốn áp cert mới cần tạo client/connection phù hợp hoặc restart có kiểm soát.

### 20.3. Đừng gộp nhiều thay đổi

Đổi CA, password, network endpoint và driver version trong cùng một lần deploy làm khó phân biệt lỗi. Nếu có thể, triển khai migration theo từng pha và xác minh cả kết nối mới.

## 21. Revocation: chứng thư bị thu hồi khác chứng thư hết hạn

Một certificate có thể còn trong `NotAfter` nhưng đã bị revoke.

Cơ chế phổ biến gồm CRL hoặc OCSP; cách kiểm tra phụ thuộc JDK, proxy, SDK, policy và tính sẵn sàng của revocation endpoint.

### 21.1. Phải công bố fail-open/fail-closed policy

Nếu máy khách không truy cập được OCSP/CRL server:

- Hệ có thể fail closed theo bảo mật, nhưng gây outage nếu revocation service down.
- Hoặc có policy mềm hơn tùy hệ, nhưng cần đánh giá rủi ro.

Không thay đổi chính sách revocation trong lúc incident chỉ để tăng availability nếu chưa được phê duyệt.

### 21.2. Rotation của private keys

Khi key bị nghi lộ, không chỉ cấp thêm certificate rồi giữ key cũ. Cần quy trình thu hồi/đổi key, phân quyền và kiểm tra tác động tới sessions/connections.

## 22. Authentication bằng username/password: những lỗi không nằm ở mật khẩu

Một login có thể thất bại dù username và password do người vận hành nhập “đúng” trên máy cá nhân:

- Ứng dụng đọc một secret version cũ.
- Có khoảng trắng/newline ngoài ý muốn trong secret.
- Password chứa ký tự cần URL percent-encoding.
- User tồn tại ở auth database/keyspace khác.
- Driver chọn cơ chế AuthN không được server hỗ trợ.
- Tài khoản bị disabled/locked/expired.
- Kết nối qua endpoint khác môi trường.
- Secret mount không được cập nhật trong pod.
- Username phân biệt hoa/thường theo backend.
- Gateway/identity provider đã đổi role mapping.
- Driver đang dùng credential của default profile khác.

### 22.1. Lấy “đúng danh tính nào” trước

Nếu credentials nằm trong URI và cũng được set trong SDK builder, cần biết cấu hình nào được áp dụng. Tránh suy app đang dùng account A chỉ vì biến môi trường A có tồn tại.

### 22.2. Đừng log passwords để xác minh

Nếu cần chứng minh pod nhận secret mới, có thể dùng **secret version ID, revision metadata hoặc checksum có kiểm soát** theo quy trình, không log raw secret và không đưa hash thô của password vào telemetry chia sẻ.

## 23. MongoDB: phân biệt auth database, SCRAM và quyền

Một lỗi phổ biến: user được tạo trong database `admin`, còn connection URI trỏ tới `shop` mà `authSource` không đúng.

Ví dụ ý tưởng:

```text
mongodb://db-host:27017/shop
  ?authSource=admin
  &authMechanism=SCRAM-SHA-256
```

Ví dụ URI đã bỏ user/password; trong code, cần cấu hình credential an toàn và URI options đúng phiên bản. Không xây URI bằng cách nối raw username/password chưa percent-encode.

### 23.1. `authSource` là gì?

MongoDB có database dùng để xác thực user. Database thao tác mặc định trong path URI **không tự có nghĩa user được tạo ở đó**. Cần kiểm tra user tồn tại ở auth source nào và driver dùng mechanism nào.

### 23.2. AuthenticationFailed và Unauthorized

| Hiện tượng | Hướng điều tra |
| --- | --- |
| SCRAM authentication failed | Username, password, authSource, mechanism |
| Connect/TLS fails trước login | CA, SAN, network, SNI |
| `not authorized on shop to execute command` | Role/action/resource trong DB đích |
| `find` được, `insert` không được | Read vs write privileges |
| `listCollections` lỗi nhưng query theo tên cụ thể được | Quyền metadata riêng |
| Transaction command bị từ chối | Role, topology hoặc feature support |
| Change stream không được phép | Quyền và capability theo deployment |

Thông báo và mã lỗi có thể khác driver/server versions; không chỉ dựa một code số để kết luận.

### 23.3. Java driver: lấy URI từ cấu hình

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class MongoAccessProbe {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_URI not configured");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("shop");

            // Chỉ chạy lệnh được phép và không có side effect.
            Document response = db.runCommand(
                new Document("ping", 1));

            System.out.println("Ping completed: " +
                response.get("ok"));
        }
    }
}
```

**Cảnh báo:** `ping` thành công chỉ chứng minh một phần đường kết nối; một số deployment có thể cho phép ping mà chưa chứng minh đủ quyền `find/insert` trên collection mục tiêu.

### 23.4. Probe phân quyền đúng hơn

Trong một môi trường thử nghiệm có dữ liệu riêng, dùng **chính operation cần kiểm tra** với principal dự kiến:

```text
orders-reader -> find sample Order
orders-reader -> insert test Order => phải bị từ chối
orders-writer -> conditional update test Order => được phép
```

Không thử `dropDatabase` hoặc chỉnh role ở production chỉ để xác minh denied access.

## 24. MongoDB X.509: chứng thư còn là danh tính DB

Khi MongoDB được cấu hình `MONGODB-X509` theo deployment, client certificate có thể dùng để xác thực user thông qua subject/identity mapping.

Những yếu tố cần kiểm tra:

- TLS client cert và private key.
- Certificate chain được server tin cậy.
- Extended Key Usage và certificate policy phù hợp.
- MongoDB auth mechanism và external auth database theo cách triển khai.
- Identity/subject khớp database user.
- User có roles cho thao tác muốn thực hiện.
- Certificate rotation có đổi subject hoặc mapping không.

### 24.1. Hai lần xác thực khác nhau

1. TLS server chấp nhận client cert.
2. Database xác định user/roles dựa trên certificate và cơ chế xác thực.

Handshake thành công nhưng role lookup thất bại vẫn có thể làm query bị từ chối.

### 24.2. Không tự ý cấp role cho mọi certificate subject

Subject mapping phải theo thiết kế danh tính của tổ chức; broad wildcard hoặc role toàn quyền có thể biến lỗ hổng CA issuance thành quyền truy cập database.

## 25. Cassandra: authentication, authorization và TLS

Apache Cassandra thường có cấu hình authenticator/authorizer riêng; CQL Java Driver có thể truyền credentials và TLS settings theo version.

Các nhóm lỗi:

```text
AuthenticationException
UnauthorizedException
SSLHandshakeException
UnavailableException
ReadTimeoutException
```

Chúng không có cùng nguyên nhân.

### 25.1. Ví dụ CqlSession cơ bản

```java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class CassandraProbe {
    public static void main(String[] args) {
        String username = System.getenv("CASSANDRA_USER");
        String password = System.getenv("CASSANDRA_PASSWORD");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("db.internal.example", 9042))
                .withLocalDatacenter("dc1")
                .withAuthCredentials(username, password)
                // TLS phải cấu hình đúng theo deployment;
                // đừng coi ví dụ này là production-ready.
                .build()) {
            session.execute("SELECT release_version FROM system.local");
        }
    }
}
```

Đây là probe minh họa cho driver lineage sử dụng `CqlSession`. Cần kiểm tra phiên bản/driver, tên DC, supported security protocol, transport encryption và quyền SELECT trên system table theo deployment.

### 25.2. Quyền theo keyspace/table

Một role có thể `SELECT` trên `app.orders_by_id` nhưng không `MODIFY`. Không cấp `ALL PERMISSIONS` toàn keyspace khi service chỉ đọc một table.

### 25.3. Local DC khác quyền

Nếu driver chọn sai local DC hoặc node unavailable, error có thể giống “không truy cập được DB” nhưng không phải AuthN. Theo dõi connection errors và topology, không đổi role để chữa timeout.

### 25.4. Managed Cassandra-compatible API

Một managed service có thể dùng token, TLS đặc thù và subset CQL. Hãy kiểm tra endpoint/mode, auth method, driver capability và service-specific error mapping; không suy mọi CQL service dùng cùng password/roles như Cassandra tự quản.

## 26. Redis: NOAUTH, WRONGPASS và NOPERM

Redis có authentication/ACL theo cấu hình và phiên bản. Ba lỗi điển hình:

```text
NOAUTH Authentication required.
WRONGPASS invalid username-password pair or user is disabled.
NOPERM this user has no permissions to run the command.
```

### 26.1. Phân biệt hành động

- `NOAUTH`: command được gọi khi kết nối chưa chứng minh danh tính theo cấu hình.
- `WRONGPASS`: credential/user không được chấp nhận.
- `NOPERM`: user đã được xác định nhưng command/key/channel không nằm trong ACL cho phép.

Lưu ý error text có thể thay đổi theo Redis version và request context.

### 26.2. ACL có nhiều chiều

Quyền Redis có thể xét:

- Commands/categories được phép.
- Key patterns, ví dụ namespace `cache:catalog:*`.
- Pub/Sub channel patterns.
- User enabled/disabled.
- Passwords/tokens theo cấu hình.
- Redis Cluster node đang xử lý.

Một service có `+GET` chưa chắc được `SET`, `DEL`, `EVAL`, `SUBSCRIBE` hoặc đọc mọi key.

### 26.3. Key pattern phải khớp schema thực

Nếu app đổi từ:

```text
cache:catalog:P100
```

sang:

```text
cache:v2:catalog:P100
```

nhưng ACL vẫn chỉ cho `~cache:catalog:*`, GET/SET mới có thể bị từ chối. Đây là lỗi **phân quyền sau khi đổi namespace**, không phải Redis mất dữ liệu.

### 26.4. Chẩn đoán an toàn

Không dùng `AUTH password` bằng command-line arguments ở shared shell nếu có nguy cơ lộ process/history. Dùng cơ chế client/secret provider được phê duyệt và lệnh read-only như `ACL WHOAMI` khi account có quyền và môi trường cho phép.

Không bật ACL toàn quyền trong production để test “cho nhanh”.

## 27. Redis TLS: lỗi certificate khác ACL

Một Redis server có thể dùng TLS qua endpoint cấu hình riêng. Driver như Lettuce/Jedis phải:

- Dùng scheme/flag TLS phù hợp.
- Trust CA của endpoint.
- Xác minh hostname.
- Cung cấp client certificate nếu server yêu cầu mTLS.
- Sau khi TLS thành công, thực hiện Redis authentication/ACL.

### 27.1. Cùng biểu hiện “Redis unavailable”

- Redis connection timed out: mạng/firewall/endpoint.
- TLS handshake fail: trust/cert/protocol.
- WRONGPASS: credential.
- NOPERM: ACL.
- MOVED/ASK/topology problem: Cluster routing.
- READONLY/replica command rejection: node role/routing.

Phải phân loại thay vì gom vào `CacheUnavailableException` rồi gửi tất cả requests sang database nguồn, tạo stampede.

### 27.2. Redis failover và cached credentials

Sau failover, connections mới có thể đến node khác với cert chain hoặc ACL state không đồng bộ theo deployment. Test cả node hiện tại và đường reconnect sau failover/rotation.

## 28. DynamoDB: AWS IAM là hệ phân quyền theo hành động và tài nguyên

DynamoDB dùng AWS SDK với request signing/identity và IAM policies, không phải username/password MongoDB.

Một request thành công cần khớp nhiều điều kiện:

```text
AWS identity / assumed role
  -> Credentials còn hiệu lực
  -> Signed request đúng endpoint, region, time
  -> IAM & policy evaluation
  -> DynamoDB API action permitted
  -> Table/index/resource đúng
```

### 28.1. Các nguyên nhân AccessDenied

- Role không có `dynamodb:GetItem` hoặc `dynamodb:Query`.
- Policy resource ARN sai table/index/region/account.
- Permissions boundary hoặc service control policy giới hạn.
- Resource-based policy hoặc VPC endpoint policy từ chối.
- Một explicit deny ghi đè allow ở nơi áp dụng.
- KMS permissions thiếu khi luồng thực sự yêu cầu KMS API theo cơ chế/service.
- Application đang dùng role khác dự kiến.
- Session policy hoặc conditional IAM context không thỏa.

**Không mặc định cứ có một IAM Allow là đủ:** hệ thống đánh giá quyền có thể gồm nhiều policy layers.

### 28.2. ResourceNotFound chưa chắc do thiếu quyền

`ResourceNotFoundException` có thể xuất hiện khi:

- Table/index không tồn tại.
- Endpoint/region/account sai.
- Tên table không đúng.
- Resource chưa ở trạng thái sẵn sàng.

Đừng tự chẩn đoán mọi `ResourceNotFound` là AuthZ error; điều tra chính xác tài nguyên và Region.

### 28.3. Throttling không phải AccessDenied

`ProvisionedThroughputExceededException` hoặc các throttling errors biểu thị capacity/traffic constraints, không được giải quyết bằng cách thêm `dynamodb:*`.

## 29. AWS SDK v2: xác nhận identity chain an toàn

Ví dụ Java lấy identity thông qua STS trong môi trường được phép:

```java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;

public final class AwsIdentityProbe {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .credentialsProvider(
                    DefaultCredentialsProvider.create())
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            var identity = sts.getCallerIdentity();

            // In production, không log full identity nếu policy cấm.
            System.out.println("Identity was resolved successfully");
            System.out.println("Account reference available: " +
                (identity.account() != null));
        }
    }
}
```

Cần dependency `software.amazon.awssdk:sts` phù hợp với SDK BOM; ví dụ không cần in access key, secret key hay session token.

### 29.1. STS success không chứng minh DynamoDB access

`GetCallerIdentity` xác định identity đang dùng trong một context, nhưng **không chứng minh role được phép** `UpdateItem` trên table cụ thể.

Một probe quyền đúng cần chạy operation read-only đã được phép hoặc thao tác ghi trong fixture test có kiểm soát.

### 29.2. Credential provider chain

Một pod có thể lấy credentials từ:

```text
Environment variables
Shared config/profile
Web identity/workload identity
Container role
Instance role
Custom credential provider
```

Thứ tự và behavior cụ thể tùy SDK/version. Nếu local chạy được nhưng production `AccessDenied`, hãy xác minh **provider nào thực sự chọn** và role/session policy tương ứng, không copy long-lived access keys lên server.

## 30. AWS Signature và clock skew

Các lỗi như:

```text
SignatureDoesNotMatch
ExpiredToken
UnrecognizedClient
RequestExpired
```

có thể liên quan:

- Access key / secret key / session token không khớp.
- Token STS đã hết hạn.
- Region/service signing scope sai.
- HTTP request bị biến đổi sau khi ký.
- Endpoint/proxy can thiệp headers/body.
- Clock skew.
- Credential provider không refresh.
- Secret manager trả credential version cũ.

### 30.1. Đừng log canonical request chứa dữ liệu nhạy cảm

Khi debug SigV4, một số thông tin canonical headers/request path có thể hữu ích, nhưng **Authorization header, session token, raw query values và signed payload** phải được bảo vệ. Sử dụng SDK diagnostics có giới hạn và chính sách redaction.

### 30.2. Token rotation trên service chạy nhiều ngày

Lỗi chỉ xuất hiện sau nhiều giờ dù startup thành công có thể do token refresh bị ngừng. Theo dõi credential expiration/refresh events qua provider, không lưu raw token vào metrics.

### 30.3. Kết hợp với proxy/network

Signature mismatch do proxy chỉnh path/headers không được chữa bằng cách cấp IAM admin. Điều tra ở tầng HTTP signing/transport.

## 31. Elasticsearch/OpenSearch: ba tầng bảo mật

Search deployment có thể kiểm tra:

1. TLS/HTTP connection.
2. HTTP authentication (basic, API key, token, IAM-signed request ở một số managed modes).
3. Authorization tới index, alias, document hoặc cluster action.

### 31.1. 401 và 403

Một request:

```http
GET /orders/_search
```

có thể bị:

- 401 do chưa được xác thực.
- 403 do thiếu index privilege.
- 403 do WAF/proxy dù search engine chưa nhận.
- 404 do index không tồn tại hoặc tài nguyên bị che.
- 429 do threadpool/capacity, không phải permission.

### 31.2. Quyền index và cluster khác nhau

Một service được `read` index `orders-*` chưa chắc được:

```text
Create index
Delete index
Change index template
Manage cluster settings
Run snapshot/restore
```

**Không cấp cluster-admin** cho search API chỉ để nó gọi `_search`.

### 31.3. Managed OpenSearch với IAM

Nếu endpoint yêu cầu IAM SigV4, Basic Auth thông thường có thể không đúng cơ chế. Xác định **product, service mode và auth layer**, rồi chọn đúng Java client/signing transport và identity policy.

### 31.4. Alias migration

Khi ứng dụng đổi từ index `orders-v1` sang `orders-v2`, role chỉ cho `orders-v1` có thể khiến search trả 403. Đừng tự giả định lỗi do chứng thư sau deployment.

## 32. Neo4j, Couchbase và các hệ NoSQL khác

### 32.1. Neo4j

Neo4j Java Driver dùng Bolt. Cần xem:

- URI scheme và routing behavior (`bolt`, `neo4j` tùy deployment).
- TLS/trust policy.
- Credentials/token.
- User roles và database-level privileges.
- Cluster discovery.
- Driver/server version.

Một lỗi authentication token khác lỗi Cypher permission trên một database hoặc graph resource.

### 32.2. Couchbase

Couchbase có authentication và RBAC ở mức service/bucket/scope/collection. Một user có KV read trên collection A chưa chắc được SQL++ query hoặc index management.

Chẩn đoán cả:

- SDK TLS/certificate.
- Endpoint bootstrap/discovery.
- User/password hoặc identity mechanism.
- Bucket/scope/collection privileges.
- Query service RBAC.
- Index availability.

### 32.3. Cloud Firestore và Bigtable

Các dịch vụ Google Cloud thường dùng credential providers/workload identity và IAM. Không nhập MongoDB password vào Firestore client chỉ vì cả hai lưu document.

Cần kiểm tra project ID, resource identity, service account, scopes/permissions, API enablement và endpoint. `PERMISSION_DENIED` trong gRPC có thể xuất hiện do policy hoặc identity; `UNAVAILABLE` thường thuộc nhóm khác.

### 32.4. Cosmos DB API modes

Cosmos DB có nhiều API modes và mô hình identity/authorization khác nhau. Chọn SDK/auth protocol đúng endpoint; không tự coi native NoSQL API, MongoDB-compatible và Cassandra-compatible là cùng một đường xác thực.

## 33. Authentication thành công nhưng dữ liệu sai tenant

Một lỗi bảo mật đặc biệt nghiêm trọng là **database role hợp lệ nhưng application authorization sai**.

Ví dụ:

```text
DB user: orders-service
DB role: read orders collection

HTTP user: tenant T01
Request: GET /orders/O1002
Order O1002 belongs to tenant T02
```

Nếu repository query chỉ theo `_id` và bỏ `tenantId`, database sẽ trả record hợp lệ về mặt DB privilege nhưng **ứng dụng đã làm lộ dữ liệu xuyên tenant**.

### 33.1. DB AuthZ không thay business AuthZ

Cần kiểm tra ownership tại API/service, query scoped theo tenant và các security boundaries tương ứng.

Ví dụ:

```java
// Chỉ là minh họa truy vấn scoped, không phải toàn bộ security design.
Document filter = new Document("_id", orderId)
    .append("tenantId", authenticatedTenantId);
```

`authenticatedTenantId` phải đến từ identity đã xác minh, không chỉ tin field do client tự nhập.

### 33.2. Không dùng `tenantId` làm metric label tùy tiện

ID tenant có thể là thông tin nhạy cảm và high cardinality. Logs/traces cần quyền; metrics nên dùng tenant tier hoặc nhóm cardinality giới hạn.

### 33.3. Test negative access

Một security contract test nên xác nhận:

```text
Tenant T01 reads own order -> allowed
Tenant T01 reads T02 order -> denied/not found per policy
Service account read-only tries delete -> denied
```

Không chỉ thử happy path “user đúng đọc được”.

## 34. Quyền cần đủ cho thao tác cụ thể, không nhất thiết đủ cho metadata

Một tài khoản có thể đọc dữ liệu nhưng không có quyền:

- Liệt kê databases/collections.
- Chạy `explain` hoặc profiler.
- Xem user roles.
- Xem system tables.
- Liệt kê cloud resource metadata.
- Truy cập backup/snapshot management.

Điều này gây bẫy cho health checks và support probes.

### 34.1. Read probe an toàn

Nếu service chỉ cần đọc theo key, một probe dùng `listAllTables` có thể trả permission denied trong khi nghiệp vụ vẫn chạy tốt.

Nên chọn probe ít quyền nhất đủ để xác minh chức năng quan trọng, ví dụ đọc một fixture đã biết trong môi trường kiểm thử.

### 34.2. Health check không được tự ý đòi admin

Nếu liveness gọi `listUsers` và thất bại do đúng chính sách least privilege, Kubernetes có thể restart service liên tục. Thiết kế liveness/readiness theo khả năng thật và không yêu cầu quyền admin.

## 35. Least privilege: cách sửa một lỗi permission

Một dòng:

```text
Access denied for action UpdateItem on table Orders
```

không đồng nghĩa phải cấp:

```json
{
  "Action": "*",
  "Resource": "*"
}
```

Hãy xác định:

1. Principal nào được gọi.
2. API action nào.
3. Resource ARN / database.collection / keyspace.table nào.
4. Điều kiện context nào: region, tenant, tags, source VPC endpoint.
5. Policy nào đã deny.
6. Thao tác có thật sự cần thiết cho business flow không.

### 35.1. Mẫu quyết định

```text
Service: order-reader
Requirement: GetItem on Orders table
Not required: DeleteTable, UpdateTable, ScanAllTables
```

Grant đúng resource/action, kiểm tra các policy overlays. Với Redis, cấp command/key pattern cụ thể; với MongoDB, cấp role trên database/collection phù hợp.

### 35.2. Có nên cấp tạm admin để xác minh?

Trong môi trường production, **không** nên cấp quyền rộng cho tài khoản nghiệp vụ để thử nghiệm nếu thiếu phê duyệt, kiểm soát và rollback. Có thể dùng môi trường test, policy simulator hoặc principal thử nghiệm riêng theo quy trình.

### 35.3. Quyền sau migration

Khi schema chuyển từ collection `orders` sang `orders_v2`, role cũ có thể không bao gồm resource mới. Thử compatibility giữa bản app cũ/mới trước cutover.

## 36. Credential rotation: tại sao chỉ một số pod lỗi?

Một rotation có thể theo các pha:

```text
T0: Secret version A đang dùng
T1: Secret manager phát hành version B
T2: DB chấp nhận A và B trong overlap window
T3: Một số pods reload B, số khác vẫn giữ A
T4: DB thu hồi A
```

Nếu pods không reload secret, sau T4 chỉ những pods đó gặp AuthN failure.

### 36.1. Các nguyên nhân reload không thành công

- Mounted file update nhưng SDK giữ credential cũ trong memory.
- Environment variable chỉ được đọc lúc process start.
- HTTP client/DB pool giữ session cũ, lỗi xuất hiện khi reconnect.
- Secret manager access bị IAM deny.
- Rotation job đổi password trên DB nhưng không update secret.
- Clock/token refresh service không đồng bộ.
- Canary nhận secret version khác toàn cụm.

### 36.2. Nguyên tắc rotation an toàn

- Có overlap khi cơ chế bảo mật cho phép.
- Chuẩn bị rollback/alternate credential theo policy.
- Phân biệt rotation của password, access token, CA, server cert và client cert.
- Test **new connections** lẫn existing connections.
- Theo dõi AuthN errors, TLS handshake errors, reconnect rates và secret version references.
- Không log giá trị secret cũ/mới.

## 37. Container và Kubernetes: lỗi ở mount, quyền file và image

Một cấu hình local chạy tốt nhưng container lỗi có thể do:

```text
Truststore path khác
Secret chưa mount
Volume permission denied
Keystore file đọc được nhưng password sai
JDK cacerts thiếu CA
DNS/service mesh thay endpoint
ReadOnlyRootFilesystem khác behavior
Env var không cập nhật sau secret rotation
Pod đang chạy trên node có clock lệch
```

### 37.1. Phân biệt OS file permission và DB permission

```text
java.nio.file.AccessDeniedException:
  /app/certs/client.p12
```

là lỗi **đọc file trong container**, không phải database từ chối `SELECT` hay IAM thiếu `GetItem`.

Một tên exception giống nhau không thể dùng để suy lớp lỗi; phải xem package/class, file path và thời điểm xuất hiện.

### 37.2. Đừng copy truststore vào mỗi image vô tội vạ

Có thể quản lý bằng volume/secret mount theo policy, nhưng cần cập nhật CA, quyền file, ownership và reload strategy. Nhúng private key vào image làm tăng phạm vi lộ key và khó rotate.

### 37.3. Debug đúng pod

Probe từ laptop có CA và network khác production. Nếu lỗi chỉ xảy ra tại một pod, so image digest, mounted secret revision, `JAVA_HOME`, JDK config, DNS và service account identity của chính pod đó.

## 38. Network trước TLS: phân biệt để tránh chữa sai

Các bước kết nối:

```text
DNS resolution
  -> Route to endpoint
  -> TCP connect / HTTPS connection establishment
  -> TLS handshake
  -> Protocol authentication
  -> Authorization
  -> Query execution
```

Nếu:

```text
java.net.UnknownHostException
```

thì chưa thể bàn certificate chain của server.

Nếu:

```text
java.net.ConnectException: Connection refused
```

có thể endpoint không lắng nghe ở port, security group/proxy reject hoặc sai host; không phải bằng chứng password sai.

Nếu:

```text
java.net.SocketTimeoutException
```

phải xem xảy ra khi connect, TLS, auth, server selection hay request đang chạy.

### 38.1. Khi VPN hoặc private endpoint thay đổi

Một service có thể chuyển DNS tới public endpoint thay vì private, khiến cert/trust và firewall behavior khác. So DNS answer từ **runtime context**, không chỉ hostname string trong config.

## 39. Java: phân loại lỗi theo exception type

Ví dụ helper phân loại **lỗi transport/TLS nền tảng**, sau đó các SDK adapters ánh xạ lỗi xác thực/quyền riêng của từng database.

```java
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLPeerUnverifiedException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.nio.file.AccessDeniedException;

public final class ConnectionFailureClassifier {

    public enum FailureClass {
        DNS,
        CONNECT,
        TIMEOUT,
        TLS_HANDSHAKE,
        TLS_PEER_IDENTITY,
        LOCAL_FILE_PERMISSION,
        DATABASE_AUTHENTICATION,
        DATABASE_AUTHORIZATION,
        OTHER
    }

    public static FailureClass classify(Throwable error) {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof SSLPeerUnverifiedException) {
                return FailureClass.TLS_PEER_IDENTITY;
            }
            if (t instanceof SSLHandshakeException) {
                return FailureClass.TLS_HANDSHAKE;
            }
            if (t instanceof UnknownHostException) {
                return FailureClass.DNS;
            }
            if (t instanceof ConnectException) {
                return FailureClass.CONNECT;
            }
            if (t instanceof SocketTimeoutException) {
                return FailureClass.TIMEOUT;
            }
            if (t instanceof AccessDeniedException) {
                return FailureClass.LOCAL_FILE_PERMISSION;
            }
        }

        // Các case DATABASE_AUTHENTICATION/AUTHORIZATION
        // phải map bằng exception type, code và context
        // của chính SDK/driver đang dùng.
        return FailureClass.OTHER;
    }
}
```

### 39.1. Giới hạn của ví dụ

- Trong thực tế exception chain có thể bao lỗi lồng phức tạp; duyệt cause phải phòng tránh vòng tham chiếu bất thường nếu input không tin cậy.
- Thứ tự kiểm tra có thể cần ưu tiên root cause khi nhiều exceptions cùng hiện diện.
- Không phân loại IAM `AccessDeniedException` thành file access; class ở SDK khác `java.nio.file.AccessDeniedException`.
- Không nên auto-retry dựa duy nhất vào classifier đơn giản: write timeout có thể là unknown outcome.

## 40. Một bảng quyết định cho chẩn đoán

```mermaid
flowchart TD
    A["NoSQL request thất bại"] --> B{"DNS/TCP tới đúng endpoint?"}
    B -->|Không| N["Kiểm tra mạng, port, route, discovery"]
    B -->|Có| C{"TLS handshake / cert validation?"}
    C -->|Không| T["CA chain, SAN, time, SNI, mTLS, JDK"]
    C -->|Có| D{"Credentials được chấp nhận?"}
    D -->|Không| I["Auth mechanism, secret version, identity provider"]
    D -->|Có| E{"Action và resource được phép?"}
    E -->|Không| P["RBAC/IAM/ACL, policy overlays, resource scope"]
    E -->|Có| F{"Query và data contract hợp lệ?"}
    F -->|Không| Q["Schema, consistency, conflicts, throttling"]
    F -->|Có| R["Kiểm tra response, application handling"]
```

**Cách dùng:** Mỗi nhánh cần evidence. Không giả định TLS đã thành công chỉ vì bạn có một exception chứa chữ “auth”; cũng không tự gọi một lệnh admin để phân biệt hai nhánh.

## 41. Metric quan sát lỗi AuthN/AuthZ/TLS

Một bộ metric minh họa:

| Metric | Dùng để làm gì |
| --- | --- |
| `db_connect_attempts_total` | Tỷ lệ tạo kết nối |
| `db_connect_failures_total` | Connect failure theo class |
| `db_tls_handshake_failures_total` | TLS failures |
| `db_authentication_failures_total` | Credentials/identity failures |
| `db_authorization_denials_total` | Các thao tác bị từ chối quyền |
| `db_request_duration_seconds` | p50/p95/p99 theo operation/result |
| `db_connection_pool_pending` | Chờ connection |
| `db_connection_retries_total` | Reconnect/retry storm |
| `db_token_refresh_failures_total` | Token provider problems |
| `db_certificate_days_to_expiry` | Certificate expiration budget |
| `db_secret_rotation_version_info` | Metadata version có kiểm soát |
| `db_policy_denial_by_action_total` | Policy denials theo action hữu hạn |
| `db_tls_reload_failures_total` | Chứng thư mới không được áp |
| `db_unknown_outcomes_total` | Ambiguous write outcomes |

Các tên là **mô hình đề xuất**, không bảo đảm driver hoặc exporter có sẵn.

### 41.1. Tag cardinality

Nên dùng:

```text
db_system
operation_type
failure_class
service
region
environment
auth_mechanism_type
```

Tránh:

```text
raw_username
access_token
session_id
full_database_uri
private_key_fingerprint_for_every_request
user_email
tenant_id_millions
```

Nếu cần phân tích theo principal, sử dụng secure logs/audit với controlled identity references thay vì tags không giới hạn.

### 41.2. Cảnh báo certificate expiry

Đừng chỉ alert khi TLS handshake bắt đầu fail. Theo dõi thời hạn trên **đúng endpoint và đúng client/server certificate** từ trước, với lead time theo chính sách rotation. Alert cũng cần phát hiện **không đọc được metadata** hoặc monitor bị ngừng, không xem thiếu mẫu là “cert còn tốt”.

## 42. Structured logging: đủ chẩn đoán nhưng không rò bí mật

Ví dụ log lỗi:

```json
{
  "severity": "ERROR",
  "service": "catalog-api",
  "dbSystem": "redis",
  "dbOperation": "GET",
  "connectionEndpointRef": "cache-private-cluster",
  "requestId": "REQ-12A",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "failureLayer": "AUTHORIZATION",
  "resultClass": "COMMAND_NOT_PERMITTED",
  "principalRef": "catalog-reader",
  "credentialVersionRef": "secret-revision-8",
  "attempt": 1,
  "elapsedMs": 18,
  "message": "Read denied by cache ACL"
}
```

### 42.1. Không in chuỗi URI đầy đủ

Một URI:

```text
rediss://user:password@host:6379/0
```

có thể làm lộ credential nếu log ở mức DEBUG hoặc trong exception. Log **host ref** và connection type đã được chuẩn hóa, không log nguyên URI.

### 42.2. Không log token/cert private key

Cấm đưa những nội dung sau vào log chẩn đoán thông thường:

```text
Authorization: Bearer ...
X-Amz-Security-Token: ...
AWS_SECRET_ACCESS_KEY
Redis AUTH password
PEM private key block
PKCS12 password
Signed HTTP Authorization header
```

Có thể log **certificate issuer, expiration, normalized subject reference** khi policy cho phép, không log secret material.

### 42.3. Chú ý log injection

Header do client cung cấp có thể chứa newline hoặc dữ liệu giả. Validate IDs, dùng structured encoder có escaping, và đừng cho raw inbound header trở thành field metric/trace tag không hạn chế.

## 43. OpenTelemetry tracing qua các lỗi bảo mật

Một trace có thể có:

```text
HTTP GET /orders/{id}
  -> Auth middleware: OK
  -> OrderRepository.find: ERROR
      -> MongoDB server selection: OK
      -> TLS handshake: OK
      -> SCRAM authentication: OK
      -> MongoDB command: Unauthorized
```

Traces giúp thấy lỗi nằm ở command permission thay vì network.

### 43.1. Span attributes nên giữ dữ liệu nào?

Có thể giữ các trường hữu hạn:

```text
db.system
db.operation.name
server.address (theo policy)
error.type
app.failure.layer
app.auth.mechanism
```

Không gắn raw username, JWT, password, `Authorization` header hoặc query chứa PII.

### 43.2. Một lỗi AuthZ có thể đáng xem là hành vi đúng

Nếu user không có quyền đọc dữ liệu người khác, response 403 là **correct security outcome**; không nhất thiết phải page on-call như database outage.

Phân biệt:

- Expected business denials.
- Unexpected service-to-database permission regression.
- Suspicious increase in denied attempts.
- Actual credential compromise signals.

### 43.3. Sampling và security incidents

Traces có thể sampling và retention ngắn; không sử dụng chúng làm authoritative security audit trail nếu hệ có yêu cầu lưu giữ riêng.

## 44. Phát hiện lỗi theo thời gian và deployment version

Một dashboard nên hiển thị:

```text
AuthN errors by service/version/region
AuthZ denied by operation and policy layer
TLS handshake failures by endpoint class
Certificate expiry windows
Token refresh failures
New connection rate
Connection pool churn
Secrets rotation/deploy annotations
HTTP availability/p99
Database request success
```

### 44.1. Triệu chứng chỉ xảy ra khi scale-out

Một pod mới khởi tạo từ image khác có thể không có CA mới. Khi HPA scale, TLS failures tăng theo số pod mới. Điều tra image/secret revision và pool creation thay vì tự suy database đột nhiên “đổi mật khẩu”.

### 44.2. Triệu chứng theo thời điểm hết hạn

Nếu lỗi tăng đúng 00:00 UTC hoặc mốc TTL token, xem certificate/token expiry, lease renewal và clock. Không quên rằng log ingest có thể chậm; cần xem timestamp của event và token validity riêng.

### 44.3. Lỗi trên một node DB

Nếu một endpoint mới dùng cert sai SAN, chỉ requests route tới node ấy thất bại. Xem per-node connect failures; cluster average có thể che sự cố.

## 45. Case study A: PKIX lỗi sau khi đổi base image

**Quan sát:**

```text
Old image: Java application connects normally.
New image: SSLHandshakeException / PKIX path building failed.
Database certificates unchanged.
```

### 45.1. Giả thuyết

- JDK truststore trong image mới thiếu internal CA.
- Property `javax.net.ssl.trustStore` trỏ tới file không có CA phù hợp.
- Secret mount path/permission thay đổi.
- Runtime Java khác đã siết thuật toán.
- Proxy/DNS route thay vì DB đã đổi.

### 45.2. Quy trình

1. So image digest, JDK distribution và truststore path.
2. Xác minh endpoint/hostname thực tế.
3. Kiểm certificate chain từ context tương ứng.
4. So trust anchors giữa image cũ và mới dưới quyền được phép.
5. Bổ sung CA được phê duyệt hoặc sửa chain/server config.
6. Thử **new TLS connection** bằng canary.
7. Theo dõi handshake failure, API errors, p99 khi rollout.
8. Giữ rollback nếu image mới còn lỗi.

### 45.3. Không làm

Không thêm `TrustManager` chấp nhận mọi cert vào code để ép PASS. Điều đó đánh đổi tính xác thực server và có thể đưa rủi ro bảo mật vào mọi deployment.

## 46. Case study B: MongoDB login được nhưng insert bị từ chối

**Quan sát:**

```text
Connection success
ping success
find from shop.orders success
insert into shop.orders unauthorized
```

### 46.1. Kết luận từ evidence

Transport/TLS và AuthN có khả năng đã hoạt động; vấn đề hiện tại thuộc **write privilege** hoặc policy áp cho collection/command.

### 46.2. Những điểm cần xác minh

- Principal nào được driver sử dụng.
- Role có `insert` trên đúng database/collection không.
- Quyền chỉ read hay readWrite.
- Có dùng một client bean khác cho đường write không.
- Schema migration chuyển collection name không.
- Feature/mode hoặc proxy có giới hạn command không.

### 46.3. Cách sửa

Nếu business flow thật sự cần insert, cấp **quyền chính xác trên collection/operation**, kiểm thử bằng fixture riêng và theo dõi audit. Nếu service chỉ nên đọc, lỗi insert là expected protection — sửa code gọi sai chứ không tăng role.

## 47. Case study C: Redis NOPERM sau đổi key namespace

**Quan sát:**

```text
Before deploy:
  GET cache:product:P100 -> OK

After deploy:
  GET cache:v2:product:P100 -> NOPERM
```

### 47.1. Giả thuyết có căn cứ

ACL chỉ cho `~cache:product:*`, nhưng ứng dụng chuyển sang namespace v2.

### 47.2. Quy trình

1. Ghi principal/ACL user thực dùng.
2. Xác minh key pattern cũ/mới qua telemetry đã che dữ liệu.
3. Tại môi trường test, kiểm tra lệnh GET mới bị từ chối đúng policy.
4. Quyết định migration có cần grant thêm pattern v2 không.
5. Cấp pattern tối thiểu, triển khai trước code migration.
6. Canary, theo dõi NOPERM và cache MISS/source fallback.
7. Loại pattern cũ khi an toàn.

### 47.3. Bẫy vận hành

Nếu Redis NOPERM bị app coi là cache MISS và fallback ồ ạt vào MongoDB, sự cố AuthZ biến thành source overload. Phải phân loại cache error riêng và giới hạn fallback.

## 48. Case study D: DynamoDB AccessDenied chỉ ở production

**Quan sát:**

```text
Local developer profile: GetItem OK.
Production pod: AccessDeniedException.
Same table name appears in config.
```

### 48.1. Các câu hỏi

- Local và production đang dùng AWS account/role nào?
- Region có giống nhau không?
- Production role có `dynamodb:GetItem` đúng table ARN không?
- Có endpoint policy, SCP, permission boundary hay explicit deny không?
- Table là resource ở account khác?
- Service account/web identity mapping có đúng?
- Có credential provider override sai trong pod?

### 48.2. Đường xử lý

1. Xác minh caller identity được cho phép bằng SDK/provider diagnostics, không log keys.
2. Xác minh request Action/Resource/Region.
3. Xem policy evaluation và audit logs có quyền.
4. Sửa scope nhỏ nhất cần thiết.
5. Test `GetItem` fixture trong staging với chính role production-equivalent.
6. Theo dõi error rate/canary sau deploy.

### 48.3. Không làm

Không copy local developer access key vào production pod, và không cấp `AdministratorAccess` cho service role để né điều tra IAM.

## 49. Case study E: mTLS sau rotation chỉ lỗi trên một nửa pods

**Quan sát:**

```text
50% pods: healthy.
50% pods: TLS alert bad_certificate.
Old connections sometimes still work.
```

### 49.1. Những nguồn khác biệt

- Pods dùng client cert version khác.
- Private key và cert không khớp.
- Server trust CA chưa cập nhật ở mọi node.
- Keystore path/alias khác nhau.
- Certificate EKU hoặc subject thay đổi.
- Driver reload cert không đồng nhất.
- Route tới backend/proxy có trust config khác.

### 49.2. Kiểm chứng

So metadata certificate (issuer, expiry, fingerprint có quyền), secret version, keystore alias, image/config và target endpoint per pod. Thử kết nối mới vào backend được phép từ từng nhóm pods.

### 49.3. Khôi phục

Phục hồi về trạng thái có **trust overlap hợp lệ**, sửa mapping/chain/keystore, rollout có kiểm soát và xác minh reconnect. Không giải quyết bằng cách tắt yêu cầu client certificate.

## 50. Case study F: chứng thư đúng nhưng hostname sai sau failover

Một DB cluster có hai endpoints:

```text
db-a.internal.example -> certificate SAN: db-a.internal.example
db-b.internal.example -> certificate SAN: db-b.internal.example
```

Application cấu hình cố định `db-a.internal.example`, nhưng sau failover kết nối qua một IP/alias không được certificate tương ứng bao phủ.

### 50.1. Chẩn đoán

- Xác minh hostname mà driver gửi và xác minh.
- Kiểm tra DNS/SRV/cluster topology.
- Xem SNI và cert mà endpoint thực trả.
- So SAN theo tên kết nối.
- Kiểm tra vendor recommendation cho URI/routing.

### 50.2. Không cố dùng IP để bỏ qua validation

Kết nối trực tiếp bằng IP có thể phát sinh hostname mismatch; chọn endpoint và chứng thư đúng theo topology, không tắt certificate verification.

## 51. Kiểm thử phân quyền theo ma trận role × operation × resource

Ví dụ:

| Principal | `orders.read` | `orders.insert` | `orders.delete` | `admin.manageUsers` |
| --- | --- | --- | --- | --- |
| API reader | ALLOW | DENY | DENY | DENY |
| Order writer | ALLOW | ALLOW | Theo yêu cầu | DENY |
| Report exporter | ALLOW có scope | DENY | DENY | DENY |
| Admin break-glass | Theo quy trình | Theo quy trình | Theo quy trình | Chỉ khi phê duyệt |

### 51.1. Positive tests

- Reader đọc collection/table đúng.
- Writer update một test record được phép.
- Backup principal đọc metadata/snapshot đúng phạm vi được cấp.

### 51.2. Negative tests

- Reader ghi dữ liệu → denied.
- Service A truy cập data store của service B → denied.
- User tenant T01 đọc T02 → denied/not found theo policy.
- Principal lỗi/expired token → không được fallback sang admin.
- Revoked cert/token → bị từ chối theo revocation contract.

### 51.3. Test scope đúng môi trường

Không dùng tài khoản nghiệp vụ thật để thử thao tác phá hủy. Dùng resource fixtures, sandbox identities và cleanup có kiểm soát; các denial tests phải được thực hiện ở môi trường được phép.

## 52. Kiểm thử rotation và expiry theo dòng thời gian

Một kịch bản reproducible:

```text
T0: Client A sử dụng credential/cert version 1.
T1: Phát hành version 2; server chấp nhận overlap nếu hỗ trợ.
T2: Khởi tạo client mới với version 2.
T3: Giữ một số existing connections version 1.
T4: Thu hồi version 1 theo kế hoạch.
T5: Buộc reconnect hoặc renew token trong test.
T6: Quan sát AuthN/TLS failures và retry.
T7: Đối soát thành công/denials; cleanup.
```

Kỳ vọng:

- Client mới dùng version 2 thành công.
- Client chưa cập nhật version 1 bị từ chối sau thu hồi theo contract.
- Không có fallback sang credential cũ không kiểm soát.
- Không có request treo vô hạn khi cert/token không hợp lệ.
- Metrics phân biệt TLS/credential errors với permission errors.
- Không có secret values trong logs.
- Rollback chỉ theo policy được phê duyệt, không bật lại key đã bị lộ.

### 52.1. Test chứng thư sắp hết hạn

Có thể dùng certificates test với lifetime ngắn trong môi trường cô lập để kiểm tra cảnh báo và reload. Không tạo/sử dụng chứng thư hết hạn cho production.

### 52.2. Test token refresh

Giả lập provider trả credentials mới sau expiry; xác minh SDK không giữ token cũ mãi. Đo refresh failure/backoff và reconnection patterns.

## 53. Alerting: khi nào cần gọi on-call?

Không phải mọi `403` là incident.

| Sự kiện | Mức quan tâm |
| --- | --- |
| User không có quyền gọi DELETE | Có thể expected denial |
| Service read-only bỗng không đọc được source | Có thể incident về availability |
| Toàn bộ pods có TLS handshake failure sau CA rotation | Incident rõ |
| Một principal bị nhiều failed logins từ nguồn lạ | Security investigation |
| Cert còn 2 ngày trước expiry, chưa rotate | Urgent preventive action theo policy |
| Token refresh thất bại tăng sau deploy | Availability risk |
| Redis ACL denial kéo nguồn fallback quá tải | Incident kết hợp bảo mật/hiệu năng |
| Một tenant đọc được tenant khác | Security incident nghiêm trọng |

### 53.1. Alert theo symptoms và nguyên nhân

Ví dụ:

```text
AuthFailureSpike:
  service-auth-failure-ratio exceeds threshold
  AND valid traffic volume > minimum
  FOR defined duration
```

```text
CertificateExpiryRisk:
  known-certificate-expiry-within-rotation-budget
```

```text
UnexpectedAuthorizationRegression:
  read-operation-denials suddenly increase
  after a deployment
```

Pseudo-alerts cần mapping metric names/scope thực tế. Không phát nhiều paging alerts cho cùng một outage nếu có thể tổng hợp theo incident.

## 54. Runbook A — TLS và chứng thư thất bại

1. Xác định API/driver, host, endpoint, TLS termination point và region.
2. Thu exact exception/cause chain, thời gian bắt đầu, pod versions.
3. Phân biệt DNS/TCP lỗi trước handshake.
4. Xác định error: trust path, SAN, expired, mTLS, cipher/protocol.
5. Kiểm chứng server certificate chain/issuer/SAN/expiry.
6. Kiểm tra JVM truststore thật, security policy và trust anchors.
7. Nếu mTLS: kiểm client cert/key pair, EKU, alias, server CA trust.
8. So pods khỏe/lỗi, image, secret mount và connection age.
9. Kiểm tra CA/cert rotation timeline và overlap.
10. Sửa cấu hình/certificate đúng, không tắt validation.
11. Canary với kết nối TLS **mới** và một probe AuthN/AuthZ hợp lệ.
12. Theo dõi error, reconnect, p99 và rollback.
13. Lưu bằng chứng và bổ sung cảnh báo expiry/rotation.

**Điều không làm:** `trustAll`, tắt hostname verification, in private key, đổi password database khi lỗi mới dừng ở TLS.

## 55. Runbook B — Authentication failed

1. Xác định backend/protocol và AuthN mechanism.
2. Phân biệt TLS đã thành công chưa.
3. Xác định principal mong đợi và principal thực dùng.
4. Xác định credential provider/secret revision từ metadata.
5. Kiểm tra authSource/realm/database, endpoint và region.
6. Kiểm tra disabled/locked/expired identity, token refresh và clock.
7. Kiểm tra encoding của username/password/URI.
8. So pods/regions, thời điểm rotation và kết nối mới.
9. Test với identity thử nghiệm tương đương trong môi trường được phép.
10. Sửa source/config/identity mechanism, không log raw credentials.
11. Canary và xem AuthN errors/reconnect.
12. Theo dõi lại secret lifecycle sau sự cố.

**Điều không làm:** dùng credential của admin để “cho pass”, copy password qua chat/issue, hoặc thay mọi secret không liên quan.

## 56. Runbook C — Permission denied

1. Xác định operation cụ thể: `find`, `insert`, `GetItem`, `ACL GET`, `index search`, v.v.
2. Xác định resource exact: database.collection, keyspace.table, key pattern, table/index ARN.
3. Xác định principal thật và authorization layer đang deny.
4. Xem role/ACL/IAM policies, explicit denies và policy overlays.
5. Xác định hành vi denied có đúng least privilege không.
6. Kiểm tra deploy/migration đổi resource name, key prefix hoặc API operation.
7. Nếu business thật sự cần quyền, đề xuất grant nhỏ nhất.
8. Review, phê duyệt và thử ở staging/fixture.
9. Canary và xác minh cả ALLOW và expected DENY.
10. Theo dõi audit/denial metrics, không chỉ HTTP 200.
11. Ghi lại policy change, owner và rollback.

**Điều không làm:** cấp wildcard admin, tắt RBAC, dùng role của service khác hoặc xóa log dấu vết.

## 57. Runbook D — Chỉ lỗi sau vài giờ hoặc sau failover

1. Xem token/session/cert expiry timeline.
2. Xem SDK credential refresh và client pool behavior.
3. Kiểm tra node mới có certificate chain/SAN khác không.
4. So endpoint route, DNS/SRV và service discovery.
5. Xem secret rotation ở từng pod và node.
6. Xác minh mTLS identity mapping/ACL đồng bộ theo cluster policy.
7. Test **new connections** sau failover, không chỉ reused connections.
8. Theo dõi timeouts/retries và tránh retry storm.
9. Khôi phục qua rollback/trust overlap hợp lệ nếu có.
10. Bổ sung failover/rotation regression test và cảnh báo.

## 58. Những anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Hướng đúng |
| --- | --- | --- |
| Lỗi DB nào cũng đổi password | Sai lớp nguyên nhân | Phân tầng lỗi |
| `PKIX` thì tắt TLS | Bỏ xác thực server | Sửa CA chain/truststore |
| Bỏ hostname verification | Dễ MITM | Sửa SAN/SNI/endpoint |
| `trustAll` để chạy production | Bỏ ranh giới tin cậy | Dùng CA được phê duyệt |
| Dùng `curl -k` rồi kết luận TLS đúng | Chỉ bypass check | Test validation thực |
| Ghi password vào log | Rò bí mật | Log secret version ref |
| Gửi private key qua ticket | Lộ identity | Secure key management |
| Cấp role admin cho mọi service | Quyền quá rộng | Least privilege |
| 401/403 luôn do DB engine | Proxy/WAF cũng có thể trả | Xem request path |
| Redis `NOPERM` là Redis down | ACL denial, không phải network | Kiểm tra command/key patterns |
| IAM Allow nghĩa mọi request OK | Có SCP/boundary/explicit deny | Evaluate policies theo scope |
| STS identity success nghĩa GetItem success | AuthN khác AuthZ | Probe action/resource |
| `ping` success nghĩa CRUD có quyền | Ping không chứng minh privileges | Contract tests |
| Dùng wrong authSource với MongoDB | User không được tìm ở realm đúng | Xác minh auth DB |
| Tạo client mới mỗi request | TLS/AuthN handshake amplification | Reuse pool đúng |
| Secret file thay là client tự reload | SDK giữ state cũ | Rotation/reload strategy |
| Chỉ test kết nối đang mở | Cert mới có thể chỉ lỗi reconnect | Test new handshake |
| Một pod lỗi thì đổi cert toàn cluster | Có thể do mount/image riêng | So per-pod evidence |
| Tắt OCSP khi unavailable mà không review | Đổi security policy | Quy trình chấp thuận |
| Chạy probe `dropDatabase` | Gây nguy cơ mất dữ liệu | Test fixture/read-only |
| Test bằng account của người vận hành | Khác principal production | Production-equivalent role in staging |
| Đánh mọi denied request là incident | Expected denials là kiểm soát đúng | Phân loại intent |
| Retry permission denied vô hạn | Không tự hết, tạo tải | Fail fast, alert |
| Coi throttling là authorization | Sai hướng sửa | Capacity/retry budgets |
| Cho tenantId từ client quyết định quyền | Cross-tenant exposure | Verified identity context |
| Lấy ID/token làm metric label | High cardinality/PII | Bounded labels |
| Log full TLS handshake nhiều ngày | Tốn tài nguyên/metadata | Targeted diagnostics |
| Bỏ secret rotation vì sợ outage | Tích tụ security risk | Overlap/canary testing |
| Sửa lỗi bằng cách đổi nhiều thứ cùng lúc | Khó truy nguyên | Incremental change |
| Certificate chưa hết hạn nghĩa hợp lệ | SAN/CA/revocation khác | Kiểm đủ validation |
| Cert hợp lệ nghĩa user có quyền | AuthZ riêng | Roles/policies riêng |

## 59. Quy trình thiết kế observability cho lỗi bảo mật

### Bước 1 — Đặt taxonomy lỗi

Ít nhất:

```text
DNS_FAILURE
CONNECT_FAILURE
TLS_TRUST_FAILURE
TLS_HOSTNAME_FAILURE
TLS_MTLS_FAILURE
AUTHN_REJECTED
AUTHZ_DENIED
TOKEN_EXPIRED
TOKEN_REFRESH_FAILURE
THROTTLED
OTHER_DB_ERROR
```

Không gộp `AUTHZ_DENIED` với `DB_UNAVAILABLE`.

### Bước 2 — Tách theo operation và endpoint

Một user có thể `find` được nhưng `insert` lỗi. Metric nên có operation class hữu hạn; endpoint nên dùng normalized reference.

### Bước 3 — Truyền request/trace IDs

Cho phép nối HTTP request, SDK call, proxy log và provider request ID theo phạm vi; không coi ID là credential.

### Bước 4 — Gắn metadata có kiểm soát

Build version, secret revision reference, auth mechanism, TLS enabled, endpoint class, expiration window.

### Bước 5 — Giới hạn sensitive data

Redaction cho URI, headers, password, token, private keys và raw query fields.

### Bước 6 — Định nghĩa alert có hành động

AuthN spike, unexpected AuthZ regression, TLS handshake failures, certificate expiry, failed refresh, secret rotation drift.

### Bước 7 — Thu thập theo trust boundary

Tầng client, sidecar, gateway, engine; có thể log/metrics khác nhau và đồng hồ không đồng bộ hoàn toàn.

### Bước 8 — Luyện tập failure injection

CA không được tin, expired token, thiếu role và sai key pattern trong sandbox.

### Bước 9 — Kiểm tra confidentiality của telemetry

Người chỉ được xem dashboard vận hành không nên có quyền thấy raw credentials hoặc nhiều tenant-specific identifiers.

### Bước 10 — Lưu runbook và ownership

Ai quản lý CA, ai quản lý IAM, ai quản lý DB roles và ai chịu trách nhiệm rotation? Một lỗi không có owner dễ kéo dài hơn bản thân lỗi kỹ thuật.

## 60. Checklist triển khai Java NoSQL an toàn

- [ ] Xác định chính xác database product/API endpoint và cơ chế AuthN.
- [ ] Có sơ đồ network → TLS → AuthN → AuthZ → operation.
- [ ] Java runtime và SDK/driver nằm trong phạm vi hỗ trợ.
- [ ] Server certificate có CA chain, SAN và thời hạn phù hợp.
- [ ] Hostname verification được bật đúng.
- [ ] SNI/route/endpoint theo topology production.
- [ ] Truststore thực dùng được xác minh trên runtime image.
- [ ] Không có TrustManager chấp nhận mọi chứng thư.
- [ ] Client certificate/keystore đúng nếu dùng mTLS.
- [ ] Cert/key pair, EKU và identity mapping đúng.
- [ ] Rotation có overlap/reload/canary/rollback hợp lệ.
- [ ] Có cảnh báo trước certificate và token expiry.
- [ ] Secret không nằm trong code, Git, logs hoặc metrics.
- [ ] Credential provider chain và principal thật được kiểm chứng.
- [ ] MongoDB authSource/mechanism/role scope đúng nếu dùng.
- [ ] Cassandra roles/keyspace/table và local DC đúng nếu dùng.
- [ ] Redis ACL command/key/channel patterns đúng nếu dùng.
- [ ] AWS IAM Action/Resource/Condition/policy overlays đúng nếu dùng.
- [ ] Search/graph/document roles theo operation và resource cụ thể.
- [ ] Service không yêu cầu admin chỉ để health check.
- [ ] Business tenant authorization được kiểm tra độc lập DB RBAC.
- [ ] Error taxonomy phân biệt TLS, AuthN, AuthZ, network và throttle.
- [ ] Request/trace/provider IDs được lưu có kiểm soát.
- [ ] Log encoder scrub URI/password/token/private key.
- [ ] Metrics có cardinality hữu hạn.
- [ ] Retry không lặp vô hạn trên permission denied.
- [ ] Test đúng trong container/region/role production-like.
- [ ] Có positive và negative permission tests.
- [ ] Có tests cho new connections sau rotation/failover.
- [ ] Có runbook, audit trail, owner và rollback.
- [ ] Security incidents có escalation/containment theo policy.

## 61. Bài tập thực hành

### Bài 1 — Phân loại PKIX

Ứng dụng Java có `SSLHandshakeException: PKIX path building failed` sau khi nâng JDK image.

**Hỏi:** Bước đầu điều tra là gì?

**Gợi ý:** So truststore/runtime CA chain, endpoint và cấu hình TLS; không đổi DB role.

### Bài 2 — Hostname mismatch

Certificate SAN chỉ có `db.prod.example`, app kết nối `db-replica.prod.example`.

**Hỏi:** Vì sao thất bại dù root CA được tin cậy?

**Gợi ý:** Hostname verification độc lập trust anchor; tên phải thuộc SAN hợp lệ.

### Bài 3 — Cert hết hạn

Node có leaf certificate `NotAfter` hôm qua; JDK báo expired.

**Hỏi:** Có nên dùng trust-all để giữ uptime?

**Gợi ý:** Không. Rotate cert đúng, kiểm tra tất cả nodes/clients và quy trình rollback.

### Bài 4 — Clock skew

Container lệch thời gian 30 phút, token timestamp bị từ chối.

**Hỏi:** Lỗi có thể nằm ở đâu?

**Gợi ý:** Time sync/credential validity/SigV4; không tăng IAM permissions.

### Bài 5 — mTLS không có keystore

Server yêu cầu client cert nhưng SSLContext chỉ cấu hình trust managers.

**Hỏi:** Cần bổ sung gì?

**Gợi ý:** Client cert+private key và key managers theo deployment; không phải một CA trust nữa là đủ.

### Bài 6 — mTLS rồi Unauthorized

TLS handshake thành công nhưng MongoDB command bị denied.

**Hỏi:** Vì sao?

**Gợi ý:** Certificate authentication và DB role authorization là hai tầng.

### Bài 7 — Truststore thay thế mặc định

Sau khi thêm truststore nội bộ, DynamoDB HTTPS lại báo PKIX.

**Hỏi:** Nguyên nhân khả dĩ?

**Gợi ý:** JVM truststore mới không chứa các CA cần cho endpoint AWS.

### Bài 8 — OpenSSL success, Java failed

OpenSSL từ laptop kết nối được, Java pod không.

**Hỏi:** Điều gì cần so?

**Gợi ý:** DNS/network context, trust material, JVM SSL policy, SNI, mTLS và hostname validation.

### Bài 9 — MongoDB authSource

User được tạo ở `admin`, app xác thực vào `shop`.

**Hỏi:** Cần cấu hình gì?

**Gợi ý:** `authSource` đúng và mechanism/credentials phù hợp.

### Bài 10 — Mongo read-only

Tài khoản đọc được orders nhưng không insert được.

**Hỏi:** Có chắc credentials sai?

**Gợi ý:** Không. AuthN thành công; có thể thiếu write permission.

### Bài 11 — Cassandra role

`SELECT` được, `INSERT` nhận Unauthorized trên cùng table.

**Hỏi:** Tầng nào?

**Gợi ý:** AuthZ theo CQL role/permissions.

### Bài 12 — Cassandra timeout

`LOCAL_QUORUM` read timeout trong khi username đúng.

**Hỏi:** Có nên reset password?

**Gợi ý:** Không; xem replica availability/topology/consistency.

### Bài 13 — Redis NOAUTH

`GET` trả `NOAUTH Authentication required`.

**Hỏi:** Khác gì `NOPERM`?

**Gợi ý:** NOAUTH chưa xác thực; NOPERM là lệnh/key không được phép theo ACL.

### Bài 14 — Redis key pattern

ACL chỉ cho `cache:v1:*`, app chuyển `cache:v2:*`.

**Hỏi:** Điều gì có thể xảy ra?

**Gợi ý:** NOPERM; cần migration ACL theo namespace mới với least privilege.

### Bài 15 — Redis error fallback

Service coi NOPERM là MISS rồi gửi toàn bộ traffic tới MongoDB.

**Hỏi:** Rủi ro?

**Gợi ý:** Source overload; lỗi AuthZ phải được phân loại khác cache MISS.

### Bài 16 — IAM AccessDenied

AWS role có `dynamodb:Query` nhưng thiếu `dynamodb:GetItem`, code dùng GetItem.

**Hỏi:** Sửa như thế nào?

**Gợi ý:** Grant đúng Action/Resource nếu nghiệp vụ cần; không wildcard admin.

### Bài 17 — IAM explicit deny

Identity policy cho GetItem, nhưng SCP deny.

**Hỏi:** Vì sao vẫn bị từ chối?

**Gợi ý:** Policy evaluation nhiều lớp; explicit deny có ưu tiên.

### Bài 18 — STS identity

STS GetCallerIdentity thành công nhưng DynamoDB UpdateItem bị denied.

**Hỏi:** Có mâu thuẫn?

**Gợi ý:** Không, identity resolution khác resource authorization.

### Bài 19 — Token expiry

Ứng dụng chạy 12 giờ rồi mới bắt đầu UnrecognizedClient/expired token.

**Hỏi:** Điều tra gì?

**Gợi ý:** Temporary credential expiry và refresh provider.

### Bài 20 — Search 403

Elasticsearch `_search` trả 403 nhưng lệnh health check trả 200.

**Hỏi:** Có thể do đâu?

**Gợi ý:** Index-level privilege, WAF/proxy, hoặc action-specific policy.

### Bài 21 — Search index alias

Role chỉ đọc `orders-v1`, deploy chuyển sang `orders-v2`.

**Hỏi:** Test gì?

**Gợi ý:** Authorization scope và migration policy cho alias/index mới.

### Bài 22 — Multitenancy

DB service account có quyền đọc `orders`, nhưng user T01 yêu cầu order T02.

**Hỏi:** DB role có bảo vệ đủ không?

**Gợi ý:** Không. Cần business authorization và tenant-scoped query.

### Bài 23 — Health check

Read-only service bị restart vì readiness gọi `listUsers` thiếu quyền.

**Hỏi:** Sửa theo hướng nào?

**Gợi ý:** Thiết kế probe tối thiểu theo quyền cần thiết, không tăng role admin.

### Bài 24 — Secret file mount

Kubernetes pod báo `java.nio.file.AccessDeniedException` trên `/app/certs/client.p12`.

**Hỏi:** Đây là lỗi database RBAC hay gì?

**Gợi ý:** OS/container file permission.

### Bài 25 — Chỉ pod mới lỗi

Pod cũ TLS OK, pod mới lỗi sau scale-out.

**Hỏi:** So gì?

**Gợi ý:** Image, JDK truststore, mounted secret revision, DNS/network, new handshakes.

### Bài 26 — Rotation overlap

Server ngừng chấp nhận CA cũ trước khi toàn bộ clients nạp CA mới.

**Hỏi:** Rủi ro?

**Gợi ý:** Handshake failures; cần transition plan và canary.

### Bài 27 — Debug logging

Developer bật handshake debug trên 500 pods và gửi logs ra kênh công khai.

**Hỏi:** Vấn đề gì?

**Gợi ý:** Metadata exposure và resource overhead; targeted logging, phân quyền/retention.

### Bài 28 — Request ID

Client đưa `X-Request-ID` dài hàng nghìn ký tự chứa newline.

**Hỏi:** Có nên log nguyên?

**Gợi ý:** Không; validate/replace để tránh log injection/cardinality.

### Bài 29 — Rotation test

Cert mới được deploy, nhưng các existing TLS connections vẫn làm việc. Nhóm kết luận thành công.

**Hỏi:** Còn thiếu kiểm thử nào?

**Gợi ý:** Force new handshakes/reconnect và xác minh cert mới trên từng endpoint.

### Bài 30 — Thiết kế incident runbook tổng hợp

Một Java Order API dùng MongoDB qua TLS, Redis ACL làm cache và DynamoDB để lưu idempotency ledger. Sau deployment: 20% Mongo queries gặp PKIX, Redis `NOPERM` tăng và DynamoDB GetItem bị `AccessDenied`.

**Yêu cầu:** Lập timeline và phân loại ba lỗi, nguồn bằng chứng, cách xác định principal/endpoint, fix theo least privilege, canary, rollback, metric/alert, secret redaction và cách bảo vệ order correctness trong lúc lỗi.

**Gợi ý:** Mongo: CA/trust/SAN từng pod; Redis: command/key namespace ACL; DynamoDB: caller role/action/table ARN/policy overlays. Không dùng một giải pháp “đổi mật khẩu” chung, không tắt TLS và không cấp wildcard admin.

## 62. Tài liệu tham khảo để triển khai thực tế

Khi làm việc với hệ thống thật, phải xem tài liệu **đúng product, service mode và phiên bản**:

- Java JSSE Reference Guide: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- Java `keytool`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- OpenTelemetry Java: https://opentelemetry.io/docs/languages/java/
- Micrometer: https://docs.micrometer.io/micrometer/reference/
- MongoDB authentication: https://www.mongodb.com/docs/manual/core/authentication/
- MongoDB authorization: https://www.mongodb.com/docs/manual/core/authorization/
- MongoDB TLS/SSL: https://www.mongodb.com/docs/manual/tutorial/configure-ssl/
- Apache Cassandra security: https://cassandra.apache.org/doc/latest/
- Redis ACL: https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
- Redis TLS: https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/
- AWS IAM policy evaluation: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html
- DynamoDB security: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/security.html
- AWS SDK for Java v2 credentials: https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html
- Elasticsearch security: https://www.elastic.co/docs/
- OpenSearch security: https://docs.opensearch.org/
- Neo4j Java Driver security: https://neo4j.com/docs/java-manual/current/
- Couchbase security: https://docs.couchbase.com/

Các liên kết là hướng tham khảo; error messages, client configuration APIs và security defaults có thể thay đổi theo phiên bản hoặc cloud provider.

## 63. Kết luận

**Chẩn đoán lỗi xác thực, quyền truy cập và chứng thư phải đi từ đúng lớp thất bại, không bắt đầu bằng việc thay password hoặc mở rộng quyền.** DNS/TCP xác định client có tới endpoint được không; TLS xác minh certificate chain và danh tính bên kia; AuthN xác nhận principal; AuthZ quyết định principal được gọi action nào trên tài nguyên nào; application tiếp tục phải kiểm soát business permissions và tenant isolation.

Trong Java và NoSQL, những lỗi dễ bị trộn lẫn gồm **PKIX/truststore/SAN/mTLS, MongoDB SCRAM/authSource/roles, Redis NOAUTH/WRONGPASS/NOPERM, Cassandra role permissions, IAM của DynamoDB và index-level authorization của Elasticsearch/OpenSearch**. Rotation, token expiry, proxy, cloud region và các connection pools dài hạn có thể làm sự cố chỉ xuất hiện trên một số pods hoặc sau failover.

Quy trình vận hành đáng tin là **thu cause chain và telemetry có kiểm soát, định vị failure layer, xác minh danh tính/quyền/chứng thư từ nguồn đáng tin, sửa ở phạm vi nhỏ nhất, thử kết nối mới và quyền cụ thể trong canary, rồi theo dõi hồi phục**. Luôn giữ TLS verification, least privilege, secret redaction và kiểm tra đúng tenant. Một kết nối “hoạt động” chỉ có ý nghĩa khi nó **được xác thực đúng, được cấp đúng quyền và không làm suy yếu những ranh giới bảo mật mà hệ thống cần bảo vệ**.

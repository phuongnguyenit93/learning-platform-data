# Mã hóa kết nối, chứng chỉ TLS và kiểm tra danh tính máy chủ trong Neo4j

## 1. Bài toán bảo mật khi kết nối Neo4j

Ứng dụng dùng **Neo4j** để lưu dữ liệu dưới dạng **property graph**, từ node `Customer`, relationship `PURCHASED` đến các property về giao dịch hoặc cấu trúc phụ thuộc hệ thống. Các yêu cầu Cypher gửi qua mạng có thể chứa khóa định danh, dữ liệu nghiệp vụ và thông tin truy cập. Nếu đường truyền không được bảo vệ đúng cách, bên thứ ba có thể quan sát hoặc can thiệp vào phiên kết nối.

Trong chương **Bảo mật** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, bài học này tập trung vào **giao thức Bolt được Neo4j Java Driver, Spring Data Neo4j và các ứng dụng sử dụng để trao đổi với Neo4j**. Mục tiêu là bảo vệ **dữ liệu đang truyền** và xác định **máy chủ nào thực sự nhận truy vấn**, không chỉ bật một tùy chọn “mã hóa”.

Sau bài học, bạn có thể:

1. Phân biệt **mã hóa dữ liệu**, **kiểm tra tính toàn vẹn** và **xác thực danh tính máy chủ** trong TLS.
2. Chọn URI `neo4j+s://`, `bolt+s://` đúng ngữ cảnh, hiểu rủi ro của `+ssc` và URI không xác minh TLS.
3. Đọc các thành phần quan trọng của chứng chỉ máy chủ: CA, chuỗi tin cậy, SAN, tên DNS và thời hạn hiệu lực.
4. Cấu hình kết nối an toàn trong Java Driver và Spring Boot/Spring Data Neo4j mà không đưa mật khẩu vào mã nguồn.
5. Kiểm tra kết nối cụm/routing, proxy, quá trình gia hạn chứng chỉ và các lỗi TLS thường gặp.
6. Thiết kế kiểm thử để ứng dụng **từ chối kết nối không đáng tin** thay vì âm thầm hạ cấp bảo mật.

> **Phạm vi phiên bản:** Ví dụ hướng tới Neo4j 5.x, Neo4j Java Driver 5.x, Spring Boot 3.x và Spring Data Neo4j tương ứng. Tên một số thiết lập trên **máy chủ** và chi tiết trust strategy có thể thay đổi theo phiên bản/kiểu triển khai; luôn đối chiếu tài liệu của chính phiên bản đang chạy. Nội dung chỉ là hướng dẫn kỹ thuật, không thay thế chính sách bảo mật của tổ chức.

## 2. TLS bảo vệ điều gì?

**TLS (Transport Layer Security)** là cơ chế bảo vệ kênh giao tiếp giữa ứng dụng và máy chủ. Khi thiết lập đúng, TLS mang lại các thuộc tính liên quan nhưng khác nhau:

| Thuộc tính | Ý nghĩa đối với kết nối Neo4j | Hiểu nhầm cần tránh |
| --- | --- | --- |
| **Confidentiality** (bí mật) | Người quan sát mạng không đọc được nội dung Bolt/Cypher trên đường truyền | Không đồng nghĩa dữ liệu đã được mã hóa khi lưu trên disk |
| **Integrity** (toàn vẹn) | Dữ liệu trao đổi được bảo vệ trước sửa đổi không phát hiện trên đường truyền | Không chứng minh nội dung dữ liệu nghiệp vụ là đúng |
| **Server authentication** (xác thực máy chủ) | Client xác minh chứng chỉ và tên đích của máy chủ đang kết nối | Có một chứng chỉ bất kỳ **không** đủ chứng minh đúng máy chủ |

Hình dung:

```mermaid
sequenceDiagram
    participant A as Java / Spring Boot
    participant M as Mạng trung gian
    participant N as Neo4j Bolt
    A->>N: Yêu cầu thiết lập kết nối TLS
    N-->>A: Chứng chỉ và thông tin bắt tay TLS
    Note over A: Kiểm tra CA/chain, SAN/DNS, thời hạn và chính sách
    A->>N: Hoàn thành TLS nếu xác minh đạt
    A->>N: Thông điệp Bolt / xác thực / Cypher qua TLS
    N-->>A: Kết quả truy vấn qua TLS
```

Một kẻ tấn công có thể đứng giữa ứng dụng và địa chỉ đích, tự cung cấp chứng chỉ do mình tạo. **Nếu client chấp nhận mọi chứng chỉ**, kẻ đó có thể dựng một kết nối được mã hóa nhưng vẫn mạo danh máy chủ. Vì vậy phải kiểm tra **ai là đầu kia của kết nối**, không chỉ thấy biểu tượng khóa hoặc một port có hỗ trợ TLS.

Ba lớp bảo mật độc lập cần phối hợp:

1. **TLS:** bảo vệ đường truyền và danh tính endpoint.
2. **Authentication/authorization của Neo4j:** kiểm tra user/token, database, role và quyền `MATCH`, `CREATE`, `MERGE`, procedure.
3. **Kiểm soát ứng dụng:** kiểm tra tenant, tham số Cypher, phân quyền endpoint, log và chính sách xử lý dữ liệu.

TLS **không** thay thế phân quyền node/relationship, parameter hóa truy vấn hoặc cơ chế bảo vệ dữ liệu lúc lưu.

## 3. Chọn URI: Bolt trực tiếp, routing và chế độ TLS

Neo4j Java Driver nhận URI với scheme thể hiện cơ chế kết nối. Bảng sau mô tả cách dùng phổ biến:

| URI | Routing | Bảo mật TLS | Trường hợp sử dụng |
| --- | --- | --- | --- |
| `bolt://localhost:7687` | Kết nối trực tiếp | Không yêu cầu TLS qua scheme này | Chỉ dùng trong dev/test được cách ly và cho phép |
| `neo4j://db.example.com:7687` | Có cơ chế routing | Không tự đảm bảo TLS qua hậu tố `+s` | Không phù hợp khi chính sách bắt buộc TLS đã xác minh |
| `bolt+s://db.example.com:7687` | Kết nối trực tiếp | TLS, xác minh chứng chỉ đáng tin và tên máy chủ | Máy chủ đơn/địa chỉ trực tiếp có cấu hình TLS |
| `neo4j+s://db.example.com:7687` | Có cơ chế routing | TLS, xác minh chứng chỉ đáng tin và tên máy chủ | Cluster hoặc dịch vụ routing dùng TLS chuẩn |
| `bolt+ssc://db.example.com:7687` | Kết nối trực tiếp | TLS cho chứng chỉ tự ký theo chế độ tin cậy nới lỏng của driver | Chỉ cân nhắc môi trường thử nghiệm được kiểm soát |
| `neo4j+ssc://db.example.com:7687` | Có cơ chế routing | TLS với chế độ chấp nhận chứng chỉ tự ký/nới lỏng xác minh | Chỉ cân nhắc môi trường thử nghiệm |

Trong bảng, `db.example.com` là **tên miền minh họa**. Cổng Bolt mặc định phổ biến là `7687`, nhưng hạ tầng có thể công bố cổng khác.

### 3.1. Hai chiều quyết định tách biệt

**Chiều thứ nhất: topology.**

- `bolt...` thường chỉ định một endpoint trực tiếp.
- `neo4j...` cho phép driver làm việc với cơ chế routing, thích hợp khi server/cụm công bố địa chỉ cho các hoạt động đọc và ghi.

**Chiều thứ hai: kiểm tra TLS.**

- `+s` yêu cầu kênh TLS và việc xác thực danh tính máy chủ theo chứng chỉ tin cậy.
- `+ssc` được cung cấp để làm việc với chứng chỉ tự ký trong chế độ trust đặc biệt; **không có cùng mức bảo vệ danh tính như `+s` trên chuỗi tin cậy đã cấu hình đúng**.
- Không có `+s`/`+ssc` thì đừng tự giả định đường truyền đã được mã hóa an toàn; cấu hình cụ thể còn phụ thuộc phiên bản và server.

Đối với production, nguyên tắc thông thường là **`neo4j+s://` hoặc `bolt+s://` cùng trust anchor đã được quản lý**. Không đổi từ `+s` sang `+ssc` chỉ để ứng dụng hết báo lỗi chứng chỉ.

### 3.2. Tham số kết nối không được dùng để tắt xác minh

Một sai lầm phổ biến là đặt cấu hình “tin mọi certificate” trong Java hoặc dùng `+ssc` ở production vì đang gặp lỗi `PKIX path building failed`. Điều đó có thể bỏ qua mục tiêu **server authentication**.

Hướng xử lý đúng là xác định:

1. Ứng dụng đang kết nối đến **hostname** nào?
2. Máy chủ thực sự đưa ra **certificate chain** nào?
3. Certificate đó được cấp cho **hostname** nào?
4. CA gốc hoặc CA trung gian cần thiết có nằm trong **nguồn tin cậy của client** không?
5. Chứng chỉ có đang hiệu lực, chưa bị thay thế/thu hồi theo chính sách và được server cấu hình đúng không?

## 4. Chứng chỉ X.509 và quy trình xác minh máy chủ

Một chứng chỉ máy chủ thường chứa **public key**, thông tin tên máy chủ, thời hạn và chữ ký của tổ chức phát hành chứng chỉ (Certificate Authority — **CA**).

Để chấp nhận một endpoint theo chính sách TLS chuẩn, client cần kiểm tra nhiều điều kiện:

| Thành phần | Câu hỏi kiểm tra |
| --- | --- |
| **Certificate chain** | Chứng chỉ server có nối qua các CA trung gian đến trust anchor mà client tin cậy không? |
| **SAN (Subject Alternative Name)** | Tên DNS/IP mà ứng dụng kết nối có nằm trong SAN hợp lệ không? |
| **Thời hạn** | Có nằm giữa `Not Before` và `Not After` không? |
| **Chữ ký và thuật toán** | Chữ ký có hợp lệ, thuật toán/độ dài khóa có được chính sách cho phép không? |
| **Key usage/EKU** | Chứng chỉ có phù hợp mục đích xác thực máy chủ không? |
| **Khóa riêng phía server** | Server có chứng minh được quyền sử dụng private key tương ứng không? |
| **Chính sách thu hồi** | Cơ chế kiểm tra OCSP/CRL hoặc quản trị thu hồi có đáp ứng yêu cầu hệ thống không? |

Phần **Common Name (CN)** trong Subject không nên được coi là lựa chọn thay thế mặc định cho SAN khi xác minh hostname. Các client TLS hiện đại ưu tiên SAN; hãy phát hành chứng chỉ có SAN đúng DNS/IP sử dụng thực tế.

### 4.1. Ví dụ đúng và sai hostname

Giả sử ứng dụng cấu hình:

```text
NEO4J_URI=neo4j+s://graph.prod.example.com:7687
```

Chứng chỉ server có các DNS SAN:

```text
DNS:graph.prod.example.com
DNS:graph-router.prod.example.com
```

Trường hợp này có **tên tương ứng** với URI minh họa, nhưng vẫn cần kiểm tra chuỗi CA, hiệu lực và các điều kiện TLS khác.

Nếu ứng dụng đổi URI thành:

```text
NEO4J_URI=neo4j+s://10.0.4.23:7687
```

thì chứng chỉ chỉ có DNS SAN nói trên **không tự xác minh được địa chỉ IP**. Muốn kết nối qua IP, chứng chỉ phải có **IP SAN phù hợp** và client phải chấp nhận theo chính sách; phương án thường dễ vận hành hơn là dùng DNS đã cấp chứng chỉ.

Không sửa lỗi này bằng cách tùy tiện thêm tên vào file hosts hoặc tắt hostname verification trong production. Cần bảo đảm tên dùng trong URI, DNS/routing và chứng chỉ thống nhất.

### 4.2. CA công khai, CA nội bộ và chứng chỉ tự ký

Có ba trường hợp hay gặp:

1. **CA công khai được tin cậy:** phù hợp endpoint công bố theo chính sách tổ chức; client có thể đã có trust anchor qua môi trường Java/driver.
2. **CA nội bộ của tổ chức:** client phải được cấu hình tin cậy CA nội bộ bằng cơ chế được driver/JVM hỗ trợ, với phân phối CA an toàn và kiểm soát vòng đời.
3. **Chứng chỉ tự ký trên server:** không có chuỗi đến CA đã được tin cậy trừ khi chứng chỉ đó được cấp phép thành trust anchor theo một quy trình riêng. Dùng `+ssc` để chấp nhận rộng rãi là lựa chọn có rủi ro, không nên dùng thay quy trình trust CA của production.

**CA nội bộ không đồng nghĩa kết nối kém an toàn.** Nếu CA được quản trị chặt chẽ, certificate server có SAN đúng và client chỉ tin cậy CA cần thiết, kết nối `+s` vẫn có thể xác thực server theo chính sách.

### 4.3. Private key khác với chứng chỉ public

Chứng chỉ máy chủ chứa **public key**; nó không phải mật khẩu và thường có thể được gửi cho client trong quá trình TLS. **Private key** tương ứng phải được bảo vệ tại server/secret manager, giới hạn quyền file và không được đưa vào repository, image hoặc log.

Nếu private key bị lộ, phải thực hiện quy trình ứng phó: thay key, phát hành chứng chỉ mới, thu hồi chứng chỉ cũ khi áp dụng và kiểm tra ảnh hưởng. Việc đổi mật khẩu ứng dụng Neo4j **không tự thay thế** private key đã bị lộ.

## 5. Cấu hình phía Neo4j server và vai trò người quản trị

Để client dùng `+s`, phía endpoint phải **thực sự hỗ trợ TLS** và trình ra chứng chỉ hợp lệ. Với hệ thống tự quản lý, đội vận hành thường cần:

1. Cấp phát chứng chỉ máy chủ có SAN đúng với DNS mà client sẽ dùng.
2. Lưu certificate chain và private key vào vị trí an toàn, với quyền file tối thiểu.
3. Cấu hình **TLS policy cho Bolt** phù hợp phiên bản Neo4j.
4. Thiết lập Bolt chỉ chấp nhận kết nối TLS nếu chính sách yêu cầu bắt buộc.
5. Khởi động/áp dụng thay đổi theo quy trình triển khai rồi kiểm tra từ **mạng của client**, không chỉ từ chính server.

Ví dụ **minh họa các nhóm cấu hình**, không phải cấu hình hoàn chỉnh để sao chép nguyên xi:

```properties
# Các tên dưới đây thường gặp ở Neo4j 5 tự quản lý.
# Kiểm tra phiên bản, đường dẫn file và chính sách của cụm trước khi áp dụng.
server.bolt.enabled=true
server.bolt.tls_level=REQUIRED
dbms.ssl.policy.bolt.enabled=true
# Các đường dẫn public_certificate/private_key và trust settings
# phải được cấu hình theo cấu trúc mà bản Neo4j đang chạy hỗ trợ.
```

Đây là **quyết định cấu hình server**, không phải một đoạn code Java của ứng dụng. Việc bật policy TLS, đường dẫn certificate/key, client authentication tùy chọn, cách cấp quyền file và cách áp dụng cấu hình phải theo **Neo4j Operations Manual của phiên bản thực tế**.

### 5.1. Không nhầm Bolt TLS với HTTPS

Neo4j có thể phục vụ nhiều giao diện:

- **Bolt** dành cho Neo4j Java Driver/Cypher client, thường qua cổng `7687`.
- **HTTP/HTTPS** cho các endpoint HTTP được cấu hình riêng.
- **Kết nối nội bộ của cluster** có những yêu cầu bảo vệ riêng.

Có chứng chỉ hợp lệ cho website HTTPS hoặc reverse proxy **không chứng minh** kết nối Bolt tới database đã có TLS. Cần xác minh đúng **endpoint và giao thức** ứng dụng thực sự sử dụng.

### 5.2. Triển khai được quản lý

Trong dịch vụ Neo4j được quản lý, người dùng có thể không được trực tiếp sửa TLS policy hay private key trên server. Lúc này, tuân theo endpoint và URI TLS do nhà cung cấp công bố; không suy ra cách quản trị chứng chỉ từ ví dụ tự cài đặt.

## 6. Java Driver: cấu hình và kiểm chứng kết nối TLS

Neo4j Java Driver nhận URI và thông tin xác thực. Ví dụ Java 17+ sau yêu cầu scheme `+s` và chỉ thực thi truy vấn thử nhỏ:

```java
import java.net.URI;
import java.util.Set;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jTlsProbe {
    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Missing required configuration: " + name
            );
        }
        return value;
    }

    public static void main(String[] args) {
        String uriText = requiredEnv("NEO4J_URI");
        String username = requiredEnv("NEO4J_USERNAME");
        String password = requiredEnv("NEO4J_PASSWORD");
        String database = requiredEnv("NEO4J_DATABASE");

        URI uri = URI.create(uriText);
        if (!Set.of("neo4j+s", "bolt+s")
                .contains(uri.getScheme())) {
            throw new IllegalArgumentException(
                "A TLS-verified Neo4j URI is required"
            );
        }
        if (uri.getUserInfo() != null) {
            throw new IllegalArgumentException(
                "Credentials must not be embedded in URI"
            );
        }

        try (Driver driver = GraphDatabase.driver(
                 uriText, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();

            try (Session session =
                     driver.session(SessionConfig.forDatabase(database))) {
                int answer = session.executeRead(tx ->
                    tx.run("RETURN 1 AS ok")
                      .single().get("ok").asInt()
                );
                if (answer != 1) {
                    throw new IllegalStateException(
                        "Unexpected connectivity test result"
                    );
                }
            }
            System.out.println("Neo4j connectivity verified");
        }
    }
}
```

Những điểm cần hiểu:

- `Set.of("neo4j+s", "bolt+s")` là **chính sách ví dụ của ứng dụng**: không cho phép đổi sang URI chưa xác minh TLS qua cấu hình triển khai. Trong sản phẩm thực tế, có thể cho phép ngoại lệ dev/test **ở một cấu hình riêng** được kiểm soát.
- `verifyConnectivity()` kiểm tra khả năng kết nối với server và thực hiện các bước cần thiết của driver; nếu chain/hostname/TLS sai, quá trình kết nối có thể thất bại.
- `RETURN 1 AS ok` chỉ xác nhận một truy vấn nhỏ thành công; **không chứng minh** user có đủ quyền trên mọi label, relationship, index hoặc procedure.
- Mật khẩu được đọc từ môi trường thay vì hard-code. Biến môi trường **không phải kho bí mật tuyệt đối**: tiến trình có đặc quyền và hệ chẩn đoán có thể truy cập; dùng secret store/mount theo chính sách tổ chức.
- Trong ví dụ, không ghi mật khẩu, AuthToken, URI chứa userinfo hoặc stack trace có nội dung nhạy cảm ra API. Các lỗi cần được log có kiểm soát bằng correlation ID.

Không tạo một `Driver` mới cho **mỗi request** trong web service; driver quản lý connection pool và thường được dùng như một thành phần sống lâu, đóng khi ứng dụng ngừng.

### 6.1. Dùng CA nội bộ với Java

Nếu chứng chỉ được ký bởi **CA nội bộ**, ứng dụng phải tin cậy CA ấy bằng cơ chế phù hợp với Java Driver và phiên bản sử dụng. Có hai hướng triển khai cần đánh giá:

- **Trust store được quản trị cho JVM/ứng dụng**, nếu cấu hình và thư viện TLS thực tế của driver dùng nguồn tin cậy đó.
- **Custom trust strategy được Neo4j Java Driver hỗ trợ**, trỏ tới certificate CA đã được phân phối có xác minh.

Không giả định rằng chỉ chép file `company-ca.pem` vào container là driver tự đọc. Cần xác minh **đường dẫn cấu hình, kiểu chứng chỉ, chain, trust strategy và tên DNS** bằng integration test.

Không đưa private key máy chủ vào ứng dụng Java để “cho client tin server”. Client thường chỉ cần **trust anchor public**; private key của server phải ở phía endpoint phục vụ TLS.

## 7. Spring Boot và Spring Data Neo4j

Trong ứng dụng Spring Boot, starter `spring-boot-starter-data-neo4j` tích hợp SDN và Java Driver. Có thể cấu hình:

```yaml
spring:
  application:
    name: graph-service
  neo4j:
    uri: ${NEO4J_URI}
    authentication:
      username: ${NEO4J_USERNAME}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: ${NEO4J_DATABASE}
```

Ví dụ giá trị không bí mật trong môi trường production:

```text
NEO4J_URI=neo4j+s://graph.prod.example.com:7687
NEO4J_DATABASE=neo4j
```

`NEO4J_USERNAME` và `NEO4J_PASSWORD` phải được cấp phát từ hệ quản lý bí mật đã được tổ chức cho phép, không đưa giá trị thật vào YAML.

Phân biệt:

- `spring.neo4j.uri` quy định endpoint và scheme kết nối của **driver**.
- `spring.neo4j.authentication.*` cung cấp tài khoản đăng nhập Neo4j.
- `spring.data.neo4j.database` chọn **database đích** cho SDN.

Không ghi đè cấu hình bảo mật bằng một bean `Driver` tự tạo có chế độ trust nới lỏng mà quên kiểm soát bean do Spring Boot quản lý. Nếu thật sự cần tùy chỉnh driver, hãy theo cơ chế customize/configuration được phiên bản Boot/SDN hỗ trợ và kiểm tra kết quả trong runtime.

### 7.1. Test phân biệt lỗi TLS và lỗi phân quyền

Một service có thể:

1. Kết nối bằng TLS **đúng** và xác minh server thành công.
2. Xác thực username/password **đúng**.
3. Vẫn bị từ chối truy vấn `MATCH` hoặc `MERGE` vì **thiếu quyền**.

Đây là ba bước khác nhau. Không xử lý lỗi quyền bằng cách chuyển `neo4j+s://` sang `neo4j://` hoặc dùng tài khoản administrator.

Nếu một database nhiều tenant, TLS không tự bảo vệ ranh giới tenant: backend còn phải ràng buộc tenant từ danh tính người dùng, dùng parameter cho Cypher và đảm bảo role/quyền đáp ứng chính sách.

## 8. Routing, cluster, proxy và danh tính của endpoint

Ứng dụng dùng `neo4j+s://router.example.com:7687` có thể ban đầu kết nối đến một **seed/router**; driver sau đó nhận thông tin routing và kết nối đến các server khác. Đây là khác biệt quan trọng so với một URI `bolt+s://` trực tiếp.

Hình dung:

```mermaid
flowchart LR
    A["Java Driver"] -->|TLS + kiểm tra tên| R["router.example.com"]
    R -.->|routing table| A
    A -->|TLS + kiểm tra tên| S1["reader-1.example.com"]
    A -->|TLS + kiểm tra tên| S2["writer-1.example.com"]
```

Đối với routing:

- Không chỉ chứng chỉ của seed mới cần hợp lệ; **mọi endpoint mà driver thực sự kết nối tới** phải trình được chứng chỉ đúng hostname và được client tin cậy.
- Các địa chỉ **advertised** phải có DNS/cổng đi được từ mạng của ứng dụng. Địa chỉ nội bộ chưa thể truy cập từ Kubernetes/VM bên ngoài cụm sẽ gây lỗi routing dù seed URI đúng.
- Không giả định mọi server trong cluster dùng một certificate có SAN đúng cho tất cả tên; đội vận hành phải có chiến lược cấp chứng chỉ phù hợp.
- Với load balancer hay proxy, cần biết **TLS kết thúc ở đâu**. Nếu proxy giải mã TLS rồi kết nối không mã hóa tới Neo4j, đoạn sau proxy không được bảo vệ bởi cùng phiên TLS đó.

### 8.1. Tại sao proxy có chứng chỉ đúng vẫn có thể chưa đủ?

Giả sử:

```text
Ứng dụng -- TLS --> Proxy -- plaintext Bolt --> Neo4j
```

Ứng dụng đã xác minh danh tính **proxy**, không tự động xác minh máy chủ Neo4j ở phía sau. Cấu hình như vậy có thể được phép ở mạng cách ly theo chính sách, nhưng không được gọi là **end-to-end TLS tới database**.

Nếu yêu cầu mã hóa trên toàn đường đi, phải bảo vệ cả đoạn proxy–Neo4j hoặc dùng cách chuyển tiếp TLS phù hợp và xác minh điểm cuối đúng thiết kế.

### 8.2. DNS, SAN và IP trong cluster

Với `neo4j+s://`, cả hostname ban đầu lẫn hostname server được quảng bá đều phải khớp chứng chỉ mà endpoint tương ứng sử dụng. Nếu routing table chứa IP nhưng certificate chỉ có DNS SAN, có thể lỗi hostname verification. Cần sửa **advertised addresses/certificate**, không hạ cấp TLS.

## 9. Kiểm thử TLS và chẩn đoán lỗi

### 9.1. Kiểm tra với Java Driver trước

Trình tự phù hợp:

1. Dùng đúng URI `+s` và tài khoản ứng dụng trên môi trường thử nghiệm.
2. Chạy `driver.verifyConnectivity()`.
3. Chạy `RETURN 1 AS ok` trên **database đích**.
4. Thử một thao tác nghiệp vụ ít tác động để xác minh quyền.
5. Với routing, thử cả thao tác đọc và ghi tương ứng để kiểm tra các endpoint khác nhau.
6. Xác minh log không có token, password hay private key.

Nếu kết nối thất bại, phân loại theo **điểm xảy ra lỗi**, không thay đổi đồng thời nhiều thiết lập.

### 9.2. Kiểm tra certificate bằng công cụ mạng

Trong môi trường vận hành có phép dùng OpenSSL, có thể **quan sát certificate chain** tại endpoint Bolt:

```bash
openssl s_client \
  -connect graph.prod.example.com:7687 \
  -servername graph.prod.example.com \
  -showcerts \
  -verify_hostname graph.prod.example.com \
  -verify_return_error </dev/null
```

Đây là ví dụ cho shell POSIX có OpenSSL hỗ trợ tùy chọn nêu trên. Nó **không gửi username/password Neo4j**, nhưng chỉ kiểm tra một số khía cạnh TLS; việc kiểm tra có thể cần CA nội bộ do tổ chức cung cấp. Nếu dùng PowerShell hoặc công cụ khác, cú pháp dòng lệnh sẽ khác.

Lưu ý:

- `-servername` gửi thông tin SNI khi endpoint hỗ trợ; điều này quan trọng nếu proxy phục vụ nhiều tên miền.
- `-verify_hostname` yêu cầu đối chiếu hostname; không chỉ xem certificate hiển thị là đủ.
- Một kết quả kiểm tra OpenSSL thành công **không thay thế** kiểm thử bằng Java Driver, vì trust store và cách xử lý chứng chỉ có thể khác.
- Với routing, kiểm tra thêm các địa chỉ được driver dùng thực tế, không chỉ seed.
- Không đưa khóa bí mật hoặc mật khẩu vào tham số lệnh hay chụp màn hình gửi công khai.

### 9.3. Bảng lỗi thường gặp

| Triệu chứng | Lớp nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `PKIX path building failed` / certificate không được tin | Thiếu CA, thiếu intermediate, trust store sai | Bổ sung chain/trust anchor được phê duyệt; không bật trust-all |
| `No subject alternative names matching` / hostname mismatch | URI/advertised address khác SAN | Sửa DNS/SAN/certificate hoặc endpoint |
| `certificate has expired` / chưa hiệu lực | Chứng chỉ quá hạn hoặc đồng hồ sai | Gia hạn, kiểm tra đồng hồ và rollout |
| TLS handshake failure | Giao thức/cipher không tương thích, TLS policy hoặc cấu hình server sai | Đối chiếu cấu hình hai đầu, log máy chủ, phiên bản |
| `Connection refused` / timeout trước handshake | Mạng, DNS, firewall hoặc server chưa lắng nghe | Kiểm tra host/port và network policy |
| `Unable to retrieve routing information` | Không tới được endpoint được quảng bá, lỗi TLS của thành viên | Kiểm tra routing table, DNS và cert từng server |
| Neo4j authentication failure | Username/password/token sai hoặc hết hiệu lực | Kiểm tra secret store và tài khoản, **không** bỏ TLS |
| Query bị `Forbidden` | Tài khoản thiếu quyền trên database/graph | Sửa role theo quyền tối thiểu |
| Chỉ lỗi sau khi rotate cert | Pool/instance chưa làm mới, thiếu CA mới hoặc chain chưa đầy đủ | Kiểm tra giai đoạn rollout và trust overlap |
| Đổi thành `+ssc` thì kết nối thành công | Dấu hiệu xác minh danh tính ở `+s` đang không đạt | Tìm nguyên nhân chain/hostname; không coi `+ssc` là bản sửa production |

**Không ghi nguyên văn secret** vào ticket hỗ trợ. Có thể cung cấp scheme URI, hostname đã được phép công bố, phiên bản, mã lỗi và metadata certificate public sau khi loại bỏ thông tin nhạy cảm.

## 10. Gia hạn và xoay vòng chứng chỉ mà không gây mất kết nối

Certificate có thời hạn sử dụng. Nếu chỉ chờ đến ngày hết hạn rồi mới thay, ứng dụng có thể mất kết nối hàng loạt. Một quy trình vận hành:

1. **Kiểm kê:** endpoint Bolt, cluster member, proxy, certificate đang sử dụng, CN/SAN, CA phát hành, ngày hết hạn, nơi lưu private key.
2. **Chuẩn bị:** phát hành certificate mới có SAN đúng; kiểm tra mục đích sử dụng và độ dài khóa/thuật toán theo chính sách.
3. **Tin cậy trước:** nếu thay **CA**, phân phối CA mới cho những client cần thiết trong thời gian **overlap** có kiểm soát, khi CA cũ vẫn còn hợp lệ.
4. **Thay phía server:** triển khai certificate/key mới theo cách rolling hoặc cơ chế reload được phiên bản/hạ tầng hỗ trợ.
5. **Xác minh:** chạy `+s` từ mạng ứng dụng, kiểm tra cả seed và các địa chỉ routing, thao tác đọc/ghi và health.
6. **Thu hồi/tắt CA cũ:** chỉ sau khi xác nhận không còn client dùng trust anchor cũ, theo cửa sổ chuyển đổi và chính sách thu hồi.
7. **Theo dõi:** lỗi handshake, kết nối mới, tỷ lệ retry và cảnh báo ngày hết hạn.

### 10.1. Chứng chỉ đổi nhưng kết nối cũ có thể vẫn hoạt động

Các kết nối **đã thiết lập** có thể tiếp tục trong connection pool trong khi kết nối TLS **mới** bị lỗi xác minh. Vì vậy một hệ thống nhìn như vẫn hoạt động ngay sau rollout, rồi thất bại khi mở thêm connection, restart pod hoặc chuyển server.

Kiểm tra **tạo connection mới** sau rotation, không chỉ gửi truy vấn qua kết nối đã được giữ từ trước. Một số cấu hình cần restart/reload driver hoặc server để áp dụng certificate mới; không tự giả định file đã thay sẽ được nạp ngay.

### 10.2. Lộ private key cần quy trình khác với hết hạn

Nếu private key máy chủ bị lộ, không chỉ gia hạn cùng khóa. Cần sinh khóa mới, phát hành certificate mới, thu hồi hoặc chặn sử dụng certificate cũ khi chính sách cho phép, điều tra ảnh hưởng và bảo vệ các bản sao lưu có chứa khóa.

Việc thay `NEO4J_PASSWORD` của tài khoản database **không giải quyết** việc private key TLS đã bị lộ; đó là hai lớp bí mật khác nhau.

## 11. Kết nối an toàn còn phụ thuộc thông tin xác thực và quyền

Ngay cả khi TLS hoàn hảo, một ứng dụng dùng tài khoản `admin` cho mọi thao tác hoặc ghép chuỗi Cypher từ dữ liệu người dùng vẫn có rủi ro.

### 11.1. Không nhúng credential vào URI

Không viết:

```text
neo4j+s://user:password@graph.prod.example.com:7687
```

Đây là **ví dụ phản diện**, không phải một credential thật. URI chứa thông tin xác thực có thể bị ghi vào log HTTP, proxy, stack trace, monitoring hoặc công cụ chẩn đoán. Neo4j Java Driver nên nhận `AuthTokens.basic(...)` hoặc phương thức xác thực được hỗ trợ **tách khỏi URI**.

Với Spring Boot, dùng `spring.neo4j.authentication.*` từ secret manager, biến môi trường hoặc file mount an toàn. Không commit password vào `application-prod.yml` hoặc CI config.

### 11.2. Phân quyền tối thiểu

- Cấp tài khoản riêng cho service, môi trường và database khi phù hợp.
- Dùng quyền đọc cho chức năng chỉ đọc; không cấp quyền tạo/xóa index, node hoặc relationship nếu không cần.
- Kiểm soát quyền gọi procedure/APOC/GDS riêng khi ứng dụng có dùng.
- Giữ thao tác quản trị và thay đổi schema trong một quy trình migration/administration được cấp quyền.
- Với đa tenant, ràng buộc tenant từ danh tính đã xác thực và kiểm tra cả node lẫn relationship trong truy vấn.

TLS bảo vệ **trên dây**, nhưng tài khoản bị cấp quá nhiều quyền vẫn có thể truy vấn dữ liệu ngoài phạm vi nghiệp vụ sau khi đã kết nối thành công.

## 12. Kiểm thử an toàn và tiêu chí chấp nhận

Không dừng ở bài test “kết nối trả về UP”. Hãy kiểm tra cả **trường hợp đúng lẫn trường hợp phải thất bại**:

| Kịch bản test | Kết quả mong đợi |
| --- | --- |
| `neo4j+s://` với cert được CA tin và SAN đúng | Kết nối thành công khi account/database hợp lệ |
| Server có cert đúng nhưng client không tin CA | **Từ chối** TLS |
| CA được tin nhưng SAN không khớp hostname | **Từ chối** TLS |
| Cert hết hạn hoặc chưa có hiệu lực | **Từ chối** TLS |
| Secret username/password sai | TLS có thể thành công, **authentication bị từ chối** |
| Tài khoản có TLS và login đúng nhưng thiếu quyền ghi | **Từ chối query ghi**, không hạ cấp bảo mật |
| Router có cert đúng, một server được quảng bá cert sai | Truy vấn đến server sai **phải thất bại**, cần sửa endpoint |
| Proxy giải mã TLS, upstream không mã hóa | Không được ghi nhận “TLS end-to-end tới Neo4j” |
| Xoay certificate trong cluster | Client mới kết nối được ở mọi endpoint, không cần dùng `+ssc` |
| Bỏ biến secret trong môi trường production | Ứng dụng không tự dùng credential dự phòng mặc định |

### 12.1. Test với Spring Boot/Neo4j Java Driver

Một integration test có thể chạy trong môi trường Neo4j riêng biệt có cấu hình TLS, với certificate test do CA test cấp. Các kiểm tra tối thiểu:

1. Kết nối thành công bằng URI `+s` và trust anchor test hợp lệ.
2. Thay hostname bằng tên **không có trong SAN** mà vẫn dùng cùng CA; driver phải từ chối.
3. Loại bỏ CA test khỏi trust store; driver phải từ chối.
4. Kiểm tra khi certificate test hết hạn/không hợp lệ nếu môi trường test hỗ trợ.
5. Kiểm tra rằng response API/log chỉ có mã lỗi phù hợp và correlation ID, không có mật khẩu/token/private key.

Nếu local test chạy Neo4j không TLS bằng `bolt://localhost`, điều đó **chỉ kiểm chứng logic truy vấn cục bộ**, không chứng minh pipeline production đã thỏa mãn bảo mật TLS. Phải có một bài kiểm thử riêng cho cấu hình bảo mật thực tế.

### 12.2. Quan sát và chỉ số vận hành

Nên theo dõi ngày hết hạn certificate, số lỗi handshake, kết nối/reconnect, timeout, lỗi routing, số pod còn cấu hình cũ và trạng thái read/write của ứng dụng. Phân biệt:

- **Readiness:** ứng dụng có thể phục vụ yêu cầu cần Neo4j hay không.
- **Liveness:** tiến trình có còn hoạt động hay không; tránh vòng restart vô hạn khi database gặp sự cố ngắn.
- **Security check:** kết nối được thiết lập bằng scheme và trust policy đã được phê duyệt hay chưa.

Một health check `RETURN 1` **không** tự xác minh mọi điều kiện bảo mật và quyền. Kết quả test TLS phải được thiết kế từ đầu để kiểm chứng việc **từ chối endpoint không tin cậy**.

## 13. Bài tập có gợi ý đáp án

### Bài 1 — Chọn URI đúng nhu cầu

Ứng dụng A chạy cục bộ với Neo4j thử nghiệm được cách ly. Ứng dụng B kết nối cluster production qua routing, server có chứng chỉ từ CA tin cậy. Ứng dụng C kết nối một endpoint Bolt trực tiếp có cert đúng.

**Gợi ý:** A có thể dùng `bolt://localhost:7687` chỉ khi chính sách thử nghiệm cho phép; B thường là `neo4j+s://...`; C có thể dùng `bolt+s://...`. Không kết luận chỉ từ tên miền mà phải kiểm tra server thực sự hỗ trợ routing và TLS.

### Bài 2 — Hostname không khớp

URI là `neo4j+s://db.internal.example:7687`, certificate chỉ có `DNS:db-prod.example`. CA đúng và chứng chỉ chưa hết hạn. Vì sao phải từ chối?

**Đáp án:** danh tính được khai báo trong SAN không khớp **hostname mà ứng dụng yêu cầu**. Tin cậy CA không đủ; cần cấp certificate có SAN đúng hoặc dùng hostname được phép và khớp, đồng thời sửa cấu hình routing/DNS khi cần.

### Bài 3 — Chẩn đoán lỗi CA nội bộ

Trong staging, `neo4j+ssc://` kết nối được nhưng `neo4j+s://` báo `PKIX path building failed`. Đồng nghiệp muốn giữ `+ssc` cho production.

**Đáp án:** không nên. Hiện tượng gợi ý client chưa xây được trust chain hợp lệ. Cần kiểm tra chain, CA trung gian, trust store/driver trust strategy và SAN trước; triển khai CA nội bộ được quản trị để `+s` xác minh đúng endpoint.

### Bài 4 — Proxy có TLS

Một sơ đồ hạ tầng: client dùng TLS đến proxy, proxy mở Bolt không TLS tới Neo4j. Hệ thống ghi tài liệu “mã hóa đầu cuối tới database”. Nhận định đó đúng không?

**Đáp án:** không. TLS chỉ tới **proxy**; đoạn proxy–database không có TLS trong thiết kế được mô tả. Muốn claim end-to-end, cần đánh giá và bảo vệ đoạn sau proxy hoặc dùng mô hình TLS passthrough phù hợp.

### Bài 5 — Rotate certificate trong cluster

CA mới đã được đưa lên server nhưng một số pod Java vẫn chỉ tin CA cũ. Những pod có connection pool đang mở vẫn trả query được. Có thể coi rollout thành công không?

**Đáp án:** chưa. Cần thử **kết nối mới** tới tất cả server theo routing, kiểm tra trust anchor của từng client, thời gian chồng lấn CA và theo dõi lỗi handshake; chỉ sau đó mới loại CA cũ.

### Bài 6 — Phân biệt TLS, authentication và authorization

Ứng dụng kết nối `neo4j+s://` đúng và chạy `RETURN 1` thành công nhưng `MERGE (p:Product {...})` bị từ chối. Có nên đổi sang `neo4j://` để tránh lỗi?

**Đáp án:** không. Vấn đề nằm ở **quyền ghi**, không phải TLS. Giữ TLS, kiểm tra database/role của tài khoản ứng dụng và chỉ cấp quyền cần thiết.

## 14. Checklist vận hành

- [ ] URI Neo4j được cho phép theo môi trường, production ưu tiên `neo4j+s://` hoặc `bolt+s://`.
- [ ] Endpoint thực sự hỗ trợ TLS; policy Bolt trên server phù hợp yêu cầu.
- [ ] Certificate có SAN đúng DNS/IP mà driver dùng, kể cả địa chỉ do routing quảng bá.
- [ ] Chain tới CA tin cậy, chứng chỉ còn hạn và sử dụng thuật toán/khóa theo chính sách.
- [ ] Client không bật trust-all, không chuyển sang `+ssc` để che lỗi production.
- [ ] Đã xác định TLS kết thúc ở đâu; nếu qua proxy, đoạn tới Neo4j cũng được bảo vệ theo yêu cầu.
- [ ] Private key server được bảo vệ; CA/certificate public được phân phối có kiểm soát.
- [ ] Mật khẩu Neo4j tách khỏi URI, repository và log, lấy từ secret manager/mount phù hợp.
- [ ] Tài khoản ứng dụng có quyền tối thiểu; kiểm soát thêm quyền đọc/ghi/APOC/GDS.
- [ ] Có thử nghiệm kết nối **thành công và bị từ chối**: CA sai, hostname sai, cert hết hạn, secret sai.
- [ ] Có quy trình gia hạn certificate, thay CA với giai đoạn trust overlap và kiểm thử kết nối mới.
- [ ] Java Driver/Spring Data Neo4j được cấu hình nhất quán, không tạo pool/driver trust nới lỏng ngoài ý muốn.
- [ ] Health, log và cảnh báo TLS không tiết lộ secret; có giám sát lỗi handshake/routing và ngày hết hạn.

## Kết luận

Mã hóa Bolt bằng TLS là điều kiện quan trọng để bảo vệ truy vấn và dữ liệu khi Neo4j giao tiếp qua mạng, nhưng **mã hóa mà không xác minh máy chủ vẫn chưa đủ**. Cách tiếp cận bền vững là dùng URI `+s` với CA được quản trị, certificate có SAN đúng hostname, TLS policy phù hợp và kiểm chứng từng endpoint trong routing hoặc proxy. Sau khi kênh được xác thực, vẫn phải bảo vệ credential, cấp quyền tối thiểu, parameter hóa Cypher và giám sát vận hành. Việc gia hạn chứng chỉ và kiểm thử những kết nối **phải thất bại** quan trọng không kém kiểm thử kết nối thành công.

### Tài liệu tham khảo

- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Operations Manual — SSL framework](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/)
- [Neo4j Operations Manual — Security](https://neo4j.com/docs/operations-manual/current/security/)
- [Spring Boot Reference — Neo4j](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.neo4j)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)

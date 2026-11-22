# 11.3 Không đặt khóa bí mật trong mã nguồn, bản đóng gói hoặc nhật ký

**Khóa bí mật không được xuất hiện dưới dạng giá trị có thể sử dụng trực tiếp trong source code, mã đã biên dịch, gói triển khai hay log.** Đây là nguyên tắc căn bản của **vòng đời khóa**: khóa phải được tạo, cấp phát, sử dụng, xoay vòng và thu hồi qua một kênh kiểm soát riêng với mã ứng dụng.

Quy tắc này bao gồm khóa mã hóa đối xứng (AES, HMAC), private key của cặp khóa, khóa ký JWT, API token, mật khẩu database, credential của cloud, secret webhook, session key và các bí mật xác thực khác. Một giá trị có tên `password` hoặc `key` chưa chắc là bí mật; ngược lại, chuỗi vô danh có quyền truy cập production vẫn là secret dù được đặt tên `configValue`.

Bài này tập trung vào ba nơi rò rỉ thường bị đánh giá thấp:

1. **Mã nguồn và lịch sử kiểm soát phiên bản:** hard-code literal, config, fixture và commit.
2. **Bản đóng gói và đường ống build:** `.class`, JAR/WAR, resource, container image/layer, artifact CI/CD.
3. **Nhật ký và hệ thống quan sát:** log, trace, dump, request/response, exception, metrics và công cụ hỗ trợ.

Đích đến không chỉ là “xóa một dòng chứa khóa” mà là **thiết kế để cùng một artifact có thể triển khai vào nhiều môi trường mà không chứa secret của môi trường nào**, đồng thời có thể thu hồi/rotate khóa khi cần.

## 1. Khái niệm: secret khác key reference, public key và metadata

| Thành phần | Có thường là bí mật? | Xử lý khuyến nghị |
| --- | --- | --- |
| **AES key / HMAC key / JWT signing secret** | **Có.** | Giữ trong KMS/HSM hoặc secret manager phù hợp; giới hạn quyền sử dụng; không serialize ra log. |
| **Private key** | **Có.** | Ưu tiên private key không thể export nếu có HSM/KMS phù hợp; chỉ cấp quyền ký/giải mã cần thiết. |
| **API key / bearer token / DB password** | **Có.** | Cấp phát động hoặc lấy từ secret store; scope hẹp, thời hạn ngắn, theo dõi và thu hồi được. |
| **Password-hashing pepper** | **Có.** | Giữ ngoài database của password verifier, thường trong secret manager/HSM. |
| **Public key / chứng chỉ công khai** | Thường **không**. | Có thể được phân phối công khai nhưng phải kiểm tra nguồn tin cậy, tính đúng đắn và vòng đời. |
| **Salt của password hashing / AES-GCM IV** | Thường **không**. | Có thể lưu cùng dữ liệu tương ứng; vẫn phải tuân thủ quy tắc thuật toán (như nonce uniqueness). |
| **Key ID / version / alias** | Thường **không**, nhưng có thể là metadata nhạy cảm theo nghiệp vụ. | Chỉ ghi vào log nếu chính sách cho phép; không nhầm ID với secret thực. |
| **Đường dẫn đến secret đã mount** | Không phải nội dung secret, nhưng có thể tiết lộ cấu trúc hệ thống. | Giữ trong cấu hình triển khai, không đưa giá trị khóa vào đường dẫn hay tên file. |

**Encoding không làm secret an toàn.** Base64, hex, URL encoding, nối chuỗi, đảo thứ tự ký tự hoặc XOR một hằng số rồi giải mã lúc runtime chỉ làm khó đọc qua mắt người. Nếu artifact chứa toàn bộ vật liệu cần để khôi phục khóa, bên có artifact cũng có thể khôi phục.

**Hash của secret không tự động vô hại.** Với token ngẫu nhiên entropy cao, lưu digest có thể là một dạng verifier thích hợp. Với mật khẩu entropy thấp, hash nhanh không thay password KDF. Hash có thể làm lộ khả năng so sánh bản ghi, định danh hoặc hỗ trợ tấn công offline tùy ngữ cảnh. Không ghi hash/digest của bí mật vào log chỉ để “chứng minh đã che”.

## 2. Mô hình đe dọa: ba nơi secret có thể bị sao chép

~~~text
Developer / hệ thống quản lý secret
          |
          +-- SOURCE REPO ---------------------+
          |   Java literals, YAML, .properties, .env,
          |   test fixture, Git history, pull request,
          |   forks, clones, code review, cache
          |
          +-- BUILD / PACKAGE -----------------+
          |   .class, JAR/WAR, resources, fat JAR,
          |   Docker image/layers, build arguments,
          |   CI logs, artifacts, SBOM metadata
          |
          +-- RUNTIME / OBSERVABILITY ---------+
              System.out, SLF4J/JUL, HTTP debug,
              APM spans, crash/heap dumps, traces,
              exception messages, request snapshots

Các nơi sao chép có thể tồn tại rất lâu sau khi source đã được sửa.
~~~

Đừng chỉ kiểm tra file `src/main/java` rồi kết luận ứng dụng an toàn. Rủi ro nằm ở **mọi nơi secret đã đi qua**, không chỉ nơi developer đang nhìn thấy.

### 2.1. Vì sao repository riêng tư vẫn không phải secret vault?

Private repository giới hạn một số người truy cập, nhưng không thay thế quản lý secret vì:

- Nhiều developer, CI runner, bot, công cụ kiểm tra, fork và bản sao local có thể đọc lịch sử.
- Pull request, diff, notification hoặc review tool có thể lưu bản sao riêng.
- Người được quyền đọc code **không nhất thiết** được quyền dùng API key production.
- Khi secret bị commit, việc xóa nó ở commit mới **không xóa commit cũ**; lịch sử, tag, branch, clone và artifact có thể vẫn chứa nó.
- Trường hợp repository từng công khai hoặc token bị gửi qua kênh ngoài, phải giả định secret có thể đã bị khai thác.

Hãy coi việc secret thực xuất hiện trong Git là **sự cố lộ secret cần đánh giá và xoay vòng/thu hồi**, không chỉ là vấn đề style.

## 3. Không hard-code khóa vào mã nguồn Java

### 3.1. Anti-pattern: literal bí mật trong code

**Ví dụ sai — chỉ dùng chuỗi giả minh họa, không có credential thật:**

~~~java
// ANTI-PATTERN: không triển khai kiểu này.
private static final String DB_PASSWORD = "DEMO_NOT_A_REAL_PASSWORD";
private static final String API_TOKEN = "DEMO_NOT_A_REAL_TOKEN";

// Không an toàn hơn: bí mật được ghép lại khi runtime.
String token = "DEMO_" + "NOT_A_REAL_TOKEN";
~~~

Trong mã thực, một hằng như thế có thể tồn tại trong source, Git history và bytecode `.class`. Mức `private`, `static final` hoặc đóng gói vào thư viện nội bộ **không cung cấp bảo vệ mật mã**.

Những biến thể vẫn sai:
- Lưu bí mật trong source bằng Base64 rồi `decode` lúc startup.
- Chia secret thành nhiều fragment ở các lớp khác nhau rồi nối lại.
- “Mã hóa” secret trong resource nhưng để **khóa giải mã** cùng artifact.
- Giấu mật khẩu trong annotation, enum, unit test, test resource hoặc SQL migration.
- Để fallback production secret trong code khi không lấy được từ secret store.
- Commit một `application.properties` hoặc `application.yml` chứa khóa thật, kể cả file chỉ được dùng ở một môi trường.
- Dùng biến môi trường nhưng **gán giá trị thật ngay trong Dockerfile, startup script được commit hoặc pipeline YAML**.

Một repo có thể chứa **tên cấu hình, key reference, mô hình cấu trúc và ví dụ giá trị giả**. Nó không nên chứa secret có hiệu lực.

### 3.2. Phân biệt cấu hình tham chiếu và giá trị bí mật

**Ví dụ cấu hình chỉ có định danh, không chứa secret:**

~~~yaml
security:
  crypto-key-ref: payments/data-key/current
  token-secret-ref: payments/api-token/current
  key-policy: AES-GCM-128
~~~

`payments/data-key/current` là **alias/reference giả lập** phục vụ minh họa. Trong hệ thống thật, ứng dụng dùng identity được cấp để gọi KMS/secret manager tương ứng, lấy secret tạm thời hoặc yêu cầu dịch vụ thực hiện thao tác mật mã mà **không xuất key raw**.

Điểm khác biệt:

~~~text
Sai:
  application.yml chứa raw AES key hoặc API token
  code đọc YAML rồi dùng raw secret

Đúng hướng:
  application.yml chứa reference, algorithm policy, key version
  workload identity -> KMS/secret manager -> quyền sử dụng phù hợp
  app chỉ nhận secret khi thật sự cần, không ghi lại giá trị
~~~

Không đưa **credentials để truy cập secret manager** vào cùng source; nếu làm vậy chỉ chuyển hard-code sang một lớp khác. Dùng workload identity, managed identity, service account được cấp quyền theo môi trường hoặc cơ chế trust/bootstrap đã được kiểm chứng.

### 3.3. `.gitignore` không phải giải pháp cho secret đã commit

`.gitignore` chỉ giúp Git **không tự đưa các file chưa được track** vào danh sách theo pattern, chứ không làm một file đã track tự biến mất khỏi lịch sử. Nó cũng không kiểm soát file copy vào JAR, ZIP hoặc Docker image.

Một hướng dùng hợp lý:

~~~gitignore
# Ví dụ chính sách bỏ qua local config có secret
.env
.env.*
!.env.example
local-secrets/
*.local.properties
~~~

Nhưng vẫn phải **kiểm tra cấu hình build**: một file nằm ngoài Git vẫn có thể bị task `processResources`, Docker `COPY . .` hoặc bước gom artifact khác đưa vào bản đóng gói. `.env.example` nên chứa **tên biến và mô tả**, không có secret hoạt động. Không đưa dữ liệu production thật làm test fixture.

Các file cấu hình an toàn cần được code review/scan. Tránh dùng heuristic “nó nằm dưới `test/` nên không sao”; CI artifact và test report cũng có thể được tải xuống.

## 4. Bí mật có thể lộ trong `.class`, JAR/WAR và container image

### 4.1. Java đã biên dịch vẫn có thể bị quan sát

Khi code chứa một chuỗi literal, trình biên dịch có thể đưa chuỗi đó vào constant pool hoặc cấu trúc bytecode khác. Người có `.class`, JAR hoặc ứng dụng chạy được có thể dùng công cụ xem/decompile để khôi phục những giá trị không được bảo vệ.

- JAR/WAR là những định dạng đóng gói có thể mở và liệt kê resource.
- `application.properties` trong `src/main/resources` thường trở thành resource trong artifact nếu build không loại trừ.
- `static final` làm code bất biến ở mức Java, không phải trở thành nơi lưu bí mật chống phân tích.
- Obfuscation, minification, shading hoặc đóng gói “fat JAR” không thay cho quản lý key.
- Chữ ký JAR/code signing chứng minh tính toàn vẹn/nguồn phát hành theo cơ chế trust phù hợp, **không mã hóa** nội dung JAR.

Các lệnh kiểm tra artifact có thể dùng trên **bản build do đội sở hữu**:

~~~bash
jar tf application.jar
javap -verbose -classpath application.jar com.example.AppConfig
~~~

`jar tf` liệt kê entry của JAR; `javap -verbose` giúp quan sát bytecode/constant pool trong class phù hợp. Chúng không thể khẳng định mọi secret đã/không xuất hiện: secret có thể ở resource, native library, image layer, artifact khác hoặc được xây dựng động. Dùng thêm hệ thống secret scanning phù hợp thay vì chỉ tìm chuỗi bằng mắt.

### 4.2. Lớp Docker image, Dockerfile và biến build

**Anti-pattern:**

~~~dockerfile
# SAI: không thay phần này bằng credential thật.
ARG APP_SECRET=DEMO_NOT_A_REAL_SECRET
ENV APP_SECRET=DEMO_NOT_A_REAL_SECRET
COPY local-secrets/ /app/secrets/
~~~

Hệ quả: giá trị hoặc file có thể xuất hiện trong định nghĩa build, metadata/image configuration, filesystem layer hoặc cache. Xóa file ở một `RUN` hoặc layer sau **không đảm bảo** xóa bản cũ khỏi mọi layer, cache và registry.

Các biện pháp tốt hơn:
1. Image được build **không chứa khóa của môi trường**.
2. Chỉ mount/provision secret **ở runtime** qua platform secret store, volume bảo vệ hoặc SDK.
3. Nếu build thật sự cần secret, sử dụng **secret mount dành cho build** (ví dụ BuildKit secret mounts) và xác nhận command không copy/log secret vào output layer, cache hay build artifacts.
4. Không truyền secret qua Docker `ARG`/`ENV` trong image definition để tiện build.
5. Kiểm tra cả image layers, base image, bản artifact được đẩy lên registry và pipeline logs.
6. Giới hạn quyền đọc secret cho đúng workload; một secret mount vẫn có rủi ro nếu container/service bị chiếm quyền.

**Đưa bí mật vào image được mã hóa** chỉ có ý nghĩa khi cơ chế giải mã/quản lý khóa được thiết kế đúng và khóa giải mã **không nằm cùng image**. Trong phần lớn ứng dụng, không cần đưa secret vào artifact ngay từ đầu.

### 4.3. CI/CD và đường rò phụ

- Pipeline YAML, script triển khai, command line và lịch sử shell có thể lưu secret. Truyền credential qua command argument như `-Ddb.password=...` có thể lộ trong process list/diagnostics/log; tránh nếu có cơ chế cung cấp an toàn hơn.
- CI/CD logs có thể hiển thị output của `echo`, `set -x`, stack trace, thông báo lỗi của lệnh bên thứ ba hoặc dump môi trường.
- Masking secret trong CI là **lớp phòng vệ phụ**: các bản biến đổi/encode/chia nhỏ secret, định dạng đa dòng và lỗi cấu hình có thể vượt qua masking.
- Debug artifact, test report, screenshot, coverage upload, crash dump, build cache hay SBOM metadata đều có thể chứa thông tin không chủ định.
- Workflow chạy từ PR/fork chưa tin cậy không được trao secret production nếu không có policy cô lập và phê duyệt thích hợp.
- Không dùng cùng credential quyền cao cho mọi pipeline, môi trường dev/staging/prod hoặc tất cả microservice.

Các secret được tạo bởi pipeline nên có **scope nhỏ, TTL ngắn**, chỉ có mặt ở job cần thiết, audit được và có khả năng thu hồi. Với tích hợp cloud, ưu tiên **federated workload identity/short-lived credentials** thay vì long-lived token hard-code trong CI khi hệ thống hỗ trợ.

## 5. Không ghi khóa bí mật vào nhật ký hoặc hệ thống quan sát

Log được nhân bản rất rộng: stdout container, tập trung log, agent shipper, SIEM, APM, service tracing, alert, ticket đính kèm và backup. Người có quyền xem log **không nhất thiết** được quyền đọc private key hoặc token production.

### 5.1. Anti-pattern Java

~~~java
// SAI: các ví dụ minh họa, đừng đưa vào production.
logger.info("apiToken={}", apiToken);
logger.debug("AES key={}", Arrays.toString(keyBytes));
logger.info("Auth header={}", request.getHeader("Authorization"));
logger.error("Connection string: {}", connectionUrlWithPassword);
System.out.println(secretKey.getEncoded());
~~~

Có cả rủi ro **gián tiếp**:

- `logger.debug("request={}", request)` nếu `toString()` của object bao gồm Authorization header, password hoặc body.
- Ghi toàn bộ HTTP request/response trong filter/interceptor, reverse proxy, HTTP client wire debug.
- Serializing object cấu hình thành JSON đưa vào log, trace span attributes hoặc MDC/ThreadContext.
- Lấy `Throwable.getMessage()` hoặc stack trace của thư viện chứa URL có `user:password@host`, connection string hoặc giá trị token.
- Ghi lỗi OAuth callback, URL reset password hoặc query string chứa credential.
- `printStackTrace()`, crash dumps, heap dumps, profiler có thể chứa bản sao của secret trong bộ nhớ; giới hạn quyền truy cập, retention và nơi lưu.
- Ghi một digest/partial secret theo cách cho phép liên kết thông tin nhạy cảm hoặc giúp người ngoài nhận biết credential đang dùng.
- Ghi full HTTP body khi thấy validation error, kể cả request chứa password, OTP, bearer token.

Không in key raw cả khi “chỉ chạy local một lần”. Local console có thể được IDE, terminal logging, screen-sharing, CI và nhật ký hệ thống lưu lại.

### 5.2. Thay logging giá trị bằng logging sự kiện có danh sách cho phép

Một sự kiện hữu ích cho giám sát key lifecycle có thể chứa:

| Trường nên cân nhắc | Mục đích | Lưu ý |
| --- | --- | --- |
| `event=key_use` | Phân biệt truy cập secret, rotate, deny, revoke. | Không kèm key raw. |
| `request_id` / correlation ID | Ghép vết ở các service. | ID phải sinh độc lập, không chứa token. |
| `key_ref` hoặc key version được phê duyệt | Xác định alias/version có vấn đề. | Chỉ dùng nếu metadata này được policy cho phép. |
| `operation=encrypt/decrypt/sign` | Quan sát loại thao tác. | Không log plaintext hay nội dung cần ký. |
| `outcome=success/denied/error` | Phân tích lỗi và bất thường. | Không dựa trên việc in exception chứa secret. |
| `error_code` đã chuẩn hóa | Chẩn đoán mà không lộ nội bộ. | Tránh free-form message từ thư viện chưa kiểm soát. |

Nguyên tắc: **chỉ log những trường đã được xét duyệt (allowlist)**, thay vì serialize toàn bộ object rồi cố xóa một vài trường nhạy cảm (denylist). Các định danh cũng cần kiểm tra/normalize để tránh log injection và tránh nhúng dữ liệu từ attacker.

**Không coi redaction là tuyệt đối.** Các secret có thể xuất hiện trong chuỗi đã encode, nested JSON, multiline message hoặc trường chưa từng được định nghĩa. Logging tối thiểu ngay từ nguồn đáng tin cậy hơn mask sau khi đã phát tán log.

### 5.3. Java 17+: audit an toàn, không in secret

Tệp **`AllowlistAuditDemo.java`** sinh một mảng ngẫu nhiên **chỉ để minh họa secret trong bộ nhớ**. Chương trình xuất một event gồm các field được chọn, tuyệt đối không đưa mảng secret vào formatter. Đây không phải secret-manager SDK và không chứng minh quy trình authentication hoàn chỉnh.

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

public class AllowlistAuditDemo {
    static String safeEvent(
            String requestId, String keyReference, String outcome) {
        return "event=key_use request_id=" + requestId
                + " key_ref=" + keyReference + " outcome=" + outcome;
    }

    public static void main(String[] args) {
        byte[] demonstrationOnly = new byte[32];
        new SecureRandom().nextBytes(demonstrationOnly);
        try {
            if (demonstrationOnly.length != 32) {
                throw new IllegalStateException("Invalid demonstration material");
            }

            System.out.println(
                    safeEvent("req-001", "demo-key-v1", "success"));
        } finally {
            Arrays.fill(demonstrationOnly, (byte) 0);
            System.out.println("Buffer cleared: "
                    + Arrays.equals(demonstrationOnly, new byte[32]));
        }
    }
}
~~~

~~~bash
javac AllowlistAuditDemo.java
java AllowlistAuditDemo
~~~

Stdout chính xác:

~~~text
event=key_use request_id=req-001 key_ref=demo-key-v1 outcome=success
Buffer cleared: true
~~~

**Giải thích:** `demo-key-v1` chỉ là reference giả và các field đã được chọn. Chương trình không in nội dung 32 byte; `Arrays.fill` chủ động ghi đè **mảng byte do ứng dụng kiểm soát**, không có nghĩa đã xóa mọi bản sao bí mật trong JVM, native memory, swap hoặc thư viện khác. Không có cơ chế Java tổng quát bảo đảm mọi secret đã được xóa khỏi mọi nơi lưu.

Một hệ thống thật nên kiểm tra độ dài, cấu trúc và tính an toàn của `requestId`, `keyReference`, `outcome` trước khi ghi log, để attacker không chèn newline hay thông tin nhạy cảm trong những trường này.

## 6. Kiến trúc cấp secret đúng: tách bản đóng gói khỏi môi trường

Mô hình thực hành khuyến nghị:

~~~text
[Git repository]                  [CI/CD build]
  code, schema, key references ---> compile/test/package
  không có raw secret                 |
                                      v
                              [Image/JAR không chứa secret]
                                      |
                                      v
                      [Runtime: workload identity/service account]
                                      |
                                      v
                         [Secret Manager / KMS / HSM]
                          IAM, version, audit, TTL, rotate
                                      |
                         +------------+------------+
                         |                         |
           key handle / encrypt operation    runtime short-lived secret
             private key không export             cấp khi thật cần
                         |                         |
                         +------------+------------+
                                      |
                                [Ứng dụng]
                     chỉ thao tác được phép; không log secret
~~~

Hệ thống không nhất thiết phải **đưa raw AES/private key vào JVM**. Với HSM/KMS, ứng dụng có thể sử dụng API **sign/decrypt/encrypt/wrap** mà private key/master key không rời phần cứng hoặc dịch vụ. Nếu hệ thống cần data key trong bộ nhớ cho mã hóa local, phải quản lý thời hạn, quyền cấp, nonce, bộ nhớ, rotation và xóa bản sao có thể xóa theo policy.

### 6.1. Các phương án cấp bí mật

| Phương án | Ưu điểm | Giới hạn/rủi ro |
| --- | --- | --- |
| **KMS/HSM key handle** | Giới hạn việc export key, central audit và policy; ứng dụng dùng operation thay vì nhận raw key khi có hỗ trợ. | Phụ thuộc provider/latency/quota, cần IAM và quản lý key version/recovery. |
| **Secret manager qua SDK** | Cấp secret theo identity, version, TTL và audit; có thể rotate/revoke tập trung. | Raw secret vẫn có thể vào process memory; cần bảo vệ cache, log, retry và exception. |
| **Secret volume/file mount ở runtime** | Không cần đóng secret vào JAR/image; có thể dùng với nhiều framework. | Cần ACL, namespace, volume policy và xử lý rotation/mount updates. File vẫn có thể bị đọc nếu workload bị chiếm quyền. |
| **Environment variable do runtime inject** | Dễ cấu hình trong nhiều platform, giảm hard-code source. | Giá trị có thể hiện trong process environment, diagnostics, dump, subprocess và log; không phải kênh mặc định an toàn nhất cho mọi secret. |
| **External encrypted config** | Có thể hữu ích khi quản lý khóa giải mã và quyền tách biệt. | Nếu cùng artifact chứa ciphertext **và** khóa giải mã, bảo vệ gần như vô nghĩa. |
| **Khóa sinh lúc startup chỉ để dùng tạm** | Phù hợp với session/ephemeral key không cần persist, giảm lưu khóa dài hạn. | Không phù hợp dữ liệu cần giải mã sau restart nếu không có cơ chế lưu/truy xuất khóa đúng. |

Chọn theo mô hình đe dọa và yêu cầu tuân thủ. **Biến môi trường tốt hơn hard-code trong source** ở khía cạnh tách cấu hình, nhưng không tự động tương đương secret manager/HSM; cân nhắc SDK/identity hoặc secret mount được kiểm soát khi có thể.

### 6.2. Không hard-code thông tin đăng nhập để lấy secret

Sai lầm bootstrap phổ biến:

~~~text
Ứng dụng muốn lấy DB password từ secret manager
  -> hard-code SECRET_MANAGER_ADMIN_TOKEN trong source
  -> gọi secret manager bằng token đó

Kết quả: secret production vẫn bị nhúng, chỉ chuyển sang lớp khác.
~~~

Cách đúng hướng là dùng **định danh workload** do môi trường phát hành và được xác minh bởi nền tảng. Quyền phải hạn chế theo tên secret, version, operation, môi trường và tenant khi phù hợp. Không dùng cùng quyền quản trị kho secret để chạy mọi service.

### 6.3. Secret rotation không phải chỉ restart ứng dụng

- **Static secret** thường cần tạo version mới, cập nhật consumer và vô hiệu version cũ theo trình tự an toàn.
- **Dynamic credential** có thể hết hạn theo lease; cần làm mới đúng thời điểm và tự dừng truy cập khi lease bị revoke.
- Restart chỉ làm process lấy secret mới **nếu ứng dụng được thiết kế như vậy**; nó không vô hiệu khóa cũ đã lộ và không xóa mọi bản sao/cached artifact.
- Với encryption key, cần quản lý **key ID/version**, cho phép dữ liệu cũ được decrypt trong giai đoạn chuyển đổi thích hợp, cân nhắc re-encryption và thời hạn giữ khóa cũ. Không xóa key cũ khi còn dữ liệu cần phục hồi nếu chưa có kế hoạch migration.
- Với API token hoặc password đã lộ, thường phải **revoke/rotate càng sớm càng khả thi** và cập nhật hệ thống phụ thuộc theo quy trình sự cố.

## 7. Java 17: lấy secret từ runtime mà không đưa vào source

### 7.1. Không có API Java chung cho mọi secret manager

Java chuẩn cung cấp `KeyStore`, `KeyGenerator`, `Cipher`, `SecureRandom` và APIs liên quan, nhưng **không có một lệnh JDK duy nhất** để truy vấn mọi cloud secret manager. Ứng dụng dùng SDK/plugin của nhà cung cấp hoặc provider JCA/JCE/PKCS#11 đã cấu hình.

Tư duy tích hợp:

~~~text
Cấu hình non-secret: keyRef, algorithm, tenant, policy
      |
Workload identity (không embedded API key)
      |
Secret manager / KMS / HSM SDK hoặc JCA provider
      |
Secret lease / key handle / phép sign-encrypt được cho phép
      |
Use -> audit metadata -> release/expire
~~~

**Pseudocode mô tả kiến trúc**, không phải class SDK có thật:

~~~text
keyRef = config.getApprovedKeyReference()
identity = runtime.getWorkloadIdentity()
handle = keyService.openKey(identity, keyRef, allowedOperation="encrypt")
ciphertext = handle.encrypt(plaintext, authenticatedMetadata)
audit(event="key_use", keyRef=keyRef, outcome="success")
close handle/lease; không in raw key vào bất kỳ log nào
~~~

Nếu dùng provider HSM để tạo `SecretKey`/`PrivateKey`, đối tượng khóa có thể là **opaque handle** và `getEncoded()` có thể trả `null`. Không cố gọi `getEncoded()` để log/serialize/clone key; một số provider bảo vệ khóa bằng chính việc không cho export.

### 7.2. Khi bắt buộc nhận secret dưới dạng byte/char

- Tránh chuyển secret sang `String` nếu API cho phép dùng `byte[]` hoặc `char[]` trong vòng đời ngắn. `String` là immutable và việc GC giải phóng không bảo đảm xóa bản sao trên bộ nhớ ngay lập tức.
- Dùng `try/finally` hoặc `AutoCloseable` để có cơ hội xóa mảng tạm bằng `Arrays.fill` sau khi dùng; nhưng **không tuyên bố zeroization tuyệt đối** vì còn bản sao trong provider/native memory, dump và JVM.
- Không dùng `new String(secretBytes)` chỉ để ghi log hoặc debug.
- Không chuyển secret sang Base64 để lưu trong config hay stdout: Base64 là **encoding**, không phải encryption.
- Với secret file runtime, chỉ cho principal phù hợp đọc; bảo vệ file permission/volume, giới hạn kích thước input và xử lý thiếu file bằng **fail-closed**, không fallback sang giá trị nhúng.
- Không đính mật khẩu vào command-line parameter vì process list và shell history có thể lưu lại; tránh các bước truyền qua shell không an toàn.

Một phương pháp đọc file được cấp ở runtime có thể như sau; đây là **mảnh API tích hợp**, không phải chương trình độc lập và không thay authentication/authorization của secret manager:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

static void withMountedSecret(Path mountedFile) throws IOException {
    byte[] secret = Files.readAllBytes(mountedFile);
    try {
        if (secret.length == 0) {
            throw new IllegalStateException("Required secret is empty");
        }
        // Ứng dụng thực sử dụng secret trong SDK đã được cấu hình.
        // Không in secret hoặc chuyển nó thành biến cấu hình toàn cục.
    } finally {
        Arrays.fill(secret, (byte) 0);
    }
}
~~~

Mảnh này chỉ minh họa **điểm nhận secret và xóa buffer sau khi xử lý**; trước khi dùng production còn phải bổ sung giới hạn size, kiểm soát đường dẫn, ACL, kiểm tra định dạng và operation thật. Không tạo file chứa secret trong repo để “giả lập runtime mount”. Đường dẫn đến file nên được cấu hình riêng và không tự lấy từ input của user.

### 7.3. Environment variable: giới hạn thực tế

~~~java
String secret = System.getenv("SERVICE_API_TOKEN");
if (secret == null || secret.isBlank()) {
    throw new IllegalStateException("Service credential is not configured");
}
// Dùng qua client đã cấu hình, không log, không trả về trong lỗi.
~~~

Đây là **mảnh minh họa**, không chứa secret hay client implementation. `System.getenv` trả `String`, tức là không thể chủ động xóa giá trị này khỏi mọi nơi trong JVM. Giá trị environment còn có thể bị lộ qua cấu hình platform, crash dump, process debugging hoặc thao tác log sai.

Không cho phép:

~~~java
// SAI: secret dự phòng được hard-code (chuỗi bên dưới chỉ là ví dụ giả).
String token = System.getenv().getOrDefault(
        "SERVICE_API_TOKEN", "DEMO_NOT_A_REAL_TOKEN");
~~~

Nếu nguồn secret bắt buộc không sẵn có, **từ chối khởi tạo hoặc từ chối thao tác** theo thiết kế; không fallback sang credential tĩnh.

### 7.4. `KeyStore` có giải quyết toàn bộ không?

`KeyStore` giúp quản lý đối tượng khóa/chứng chỉ theo loại store và provider, nhưng **không tự biến một file chứa khóa và mật khẩu hard-code thành an toàn**. Nếu application JAR chứa cả keystore exportable và mật khẩu mở khóa, người sở hữu artifact vẫn có thể truy xuất bí mật.

Một HSM/PKCS#11 provider có thể đại diện khóa bằng handle không export; mức bảo vệ thực tế phụ thuộc cách key được tạo, key policy, PIN/session, hardware, provider và quyền của workload. Cần phân biệt `KeyStore` như API/abstraction với **hệ thống quản lý bí mật thực sự**.

## 8. Java 17+: tạo khóa dùng tạm, không nhúng hoặc log giá trị khóa

Ví dụ **`InMemoryKeyDemo.java`** minh họa một khóa AES được sinh ngẫu nhiên tại runtime chỉ để mã hóa/giải mã ngay trong tiến trình. Chương trình không dùng hard-coded key bytes, không gọi `key.getEncoded()` để in khóa, và chỉ in metadata không bí mật.

**Đây là khóa tạm thời để học.** Dữ liệu cần decrypt sau restart đòi hỏi kiến trúc quản lý/lưu key trong KMS/keystore hoặc key-wrapping thích hợp; không thay bằng cách hard-code key vào mã nguồn.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class InMemoryKeyDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, random);
        SecretKey ephemeralKey = generator.generateKey();

        byte[] iv = new byte[12];
        random.nextBytes(iv);

        byte[] message = "example".getBytes(StandardCharsets.UTF_8);
        Cipher enc = Cipher.getInstance("AES/GCM/NoPadding");
        enc.init(Cipher.ENCRYPT_MODE, ephemeralKey,
                 new GCMParameterSpec(128, iv));
        byte[] ciphertextAndTag = enc.doFinal(message);

        Cipher dec = Cipher.getInstance("AES/GCM/NoPadding");
        dec.init(Cipher.DECRYPT_MODE, ephemeralKey,
                 new GCMParameterSpec(128, iv));
        byte[] restored = dec.doFinal(ciphertextAndTag);

        System.out.println("Algorithm: "
                + ephemeralKey.getAlgorithm());
        System.out.println("IV bytes: " + iv.length);
        System.out.println("Ciphertext+tag bytes: "
                + ciphertextAndTag.length);
        System.out.println("Round-trip OK: "
                + Arrays.equals(message, restored));
    }
}
~~~

~~~bash
javac InMemoryKeyDemo.java
java InMemoryKeyDemo
~~~

Stdout kiểm chứng:

~~~text
Algorithm: AES
IV bytes: 12
Ciphertext+tag bytes: 23
Round-trip OK: true
~~~

Giải thích:
- `KeyGenerator.getInstance("AES")` tạo **key material mới từ CSPRNG**, không có literal AES key trong source.
- `generator.init(128, random)` xác định khóa AES 128 bit; đó **không phải** kích thước IV.
- `IV` có 12 byte và được sinh từ `SecureRandom`. Bài này chỉ thực hiện một lần encryption; trong hệ thống thực, AES-GCM **phải không lặp cặp (key, IV)** ở mọi lần encrypt với cùng khóa, kể cả giữa các node và restart.
- `doFinal(message)` tạo 7 byte ciphertext + 16 byte authentication tag (tLen=128 bit), nên tổng là 23 byte; không in plaintext hoặc key thực ngoài chuỗi demo không nhạy cảm.
- `key.getAlgorithm()` trả tên thuật toán (metadata); đây không phải phương pháp xác nhận quyền truy cập hay sự an toàn của kho khóa.
- Chương trình **không persist key**, nên không thể dùng để giữ ciphertext giải mã được sau khi tiến trình kết thúc. Với key dài hạn, cấu hình đúng KMS/HSM/keystore và quản lý version/rotation là bắt buộc.

### Tại sao không ghi `SecretKey.getEncoded()`?

Với key exportable, `getEncoded()` thường trả byte raw bí mật; `Base64.getEncoder().encodeToString(key.getEncoded())` rồi in ra console **tạo lộ khóa**. Với key không exportable, `getEncoded()` có thể trả `null`, nên ép lấy byte hoặc giả định khóa luôn exportable là sai. Không log `SecretKey` object tùy tiện vì provider có thể đưa metadata hoặc representation không mong muốn vào `toString()`.

## 9. Đọc, build, test, vận hành: kiểm soát nào ở mỗi giai đoạn?

| Giai đoạn | Nguy cơ | Kiểm soát thích hợp |
| --- | --- | --- |
| **Thiết kế** | Secret dùng chung rộng, tuổi thọ quá dài, không có owner | Inventory owner/purpose/scope, least privilege, rotation/revocation policy. |
| **Lập trình** | Hard-code credential trong Java/config/test/fixture | Secrets reference, dummy fixture vô hại, code review, linter + pre-commit scanning. |
| **Git push / pull request** | Secret vào history và snapshot/fork | Server-side push protection/secret scanning, branch policy, bot không lộ credential. |
| **CI build** | Pipeline in biến, artifact chứa secret, job có quyền cao | Identity ngắn hạn, cô lập runner, mask bổ sung, scan artifacts, tránh in command có secret. |
| **Package/JAR** | Secret lọt vào `.class`, resource, manifest, fat JAR | Kiểm tra dependencies/resources, build reproducible không cần production secret, scan package. |
| **Container image** | Dockerfile ENV/ARG, secret mount sai, layer/cache | Runtime injection, BuildKit secret mount nếu cần lúc build, kiểm tra layer/registry/cache. |
| **Runtime** | Secret trong dump, process env, file đọc được | Workload identity, KMS/HSM, runtime mounts có ACL, hạn chế dump/debug và quyền process. |
| **Observability** | In full request, Authorization header, SDK exception, traces | Allowlist logging, redaction, vô hiệu wire debug nhạy cảm, retention và ACL log. |
| **Rotation** | Key cũ vẫn có hiệu lực, rollback dùng version cũ | Versioned secrets, TTL, revoke, migration plan, đo lường consumer đã đổi. |
| **Incident** | Chỉ xóa secret khỏi code nhưng credential vẫn sống | Revoke/rotate, điều tra phạm vi, dọn bản sao/artefact có kiểm soát, audit & cảnh báo. |

### 9.1. Secret scanning có tác dụng và giới hạn nào?

Scanner có thể tìm pattern API key, private-key block, credential literal, entropy bất thường và tên file nhạy cảm. Dùng ở nhiều thời điểm: pre-commit, PR/CI, source history, artifact/image scanning và monitoring log khi chính sách cho phép.

Tuy nhiên:
- **False negative**: secret được mã hóa Base64/hex, chia đoạn, tạo động, mang format tùy chỉnh hoặc nằm ở bản sao ngoài tầm quét.
- **False positive**: chuỗi test/dummy hoặc dữ liệu entropy cao nhưng không phải secret.
- Scanner phát hiện secret không tự **revoke** secret. Khi có hit thật cần mở incident workflow.
- Đừng in nguyên secret phát hiện được vào **báo cáo của scanner** hoặc issue/ticket.
- Chỉ tính toán/hiển thị fingerprint đã được thiết kế an toàn khi cần deduplicate, không mặc định hash nào cũng vô hại.

Quy trình hay dùng là **chặn trước merge/commit nếu phát hiện secret**, thêm scan định kỳ artifact và thiết lập owner chịu trách nhiệm từng loại credential.

### 9.2. Phân quyền và đa môi trường

Không dùng một khóa production cho dev/staging, QA và CI. Một bản build trung lập có thể chạy ở mỗi môi trường nhờ được cấp **identity và secret reference riêng** ở runtime. Khi staging có lỗ hổng, sự cố không nên tự động cấp quyền tới production.

Sử dụng least privilege: service chỉ được `read` secret đúng scope hoặc `encrypt/sign` bằng key handle được cấp; không mặc định có quyền `list/all`, `delete`, `rotate` hoặc `export` mọi key. Runner build cũng không cần quyền decrypt dữ liệu sản xuất chỉ vì nó đóng gói code.

## 10. Nếu phát hiện khóa đã bị lộ: thứ tự xử lý

**Tình huống:** một developer từng commit một API token hoặc AES key, sau đó xóa dòng đó khỏi branch và tạo commit mới. Dòng đã xóa không bảo đảm secret chưa bị sao chép.

### Quy trình ứng cứu thực hành

1. **Phân loại và thông báo theo quy trình nội bộ.** Xác định secret gì, owner, phạm vi quyền, môi trường, ngày tạo, nơi có thể đã lộ (repo, artifact, log, CI cache, ticket, dump).
2. **Cô lập/thu hồi hoặc rotate càng sớm càng khả thi.** Với token/API key, revoke/replace để secret cũ không thể dùng nữa. Với private/signing/encryption key, lập kế hoạch thay khóa, điều chỉnh trust/certificate, re-sign/re-encrypt dữ liệu nếu cần; chú ý mất khả năng giải mã dữ liệu cũ.
3. **Kiểm tra access logs và usage history** để xác định có sử dụng trái phép không; không truy xuất/log lại secret gốc trong quá trình điều tra.
4. **Cập nhật consumer có kiểm soát**, xác nhận tất cả service dùng version mới và không còn phụ thuộc credential cũ; tránh fallback bí mật sang khóa đã lộ.
5. **Xử lý dấu vết rò rỉ** trên source history, PR, artifact, Docker registry/cache, logs, backup, các bản sao theo kế hoạch đã phê duyệt. Việc rewrite Git history có thể phá commit references và cần phối hợp với mọi clone; **không thay cho revoke**.
6. **Giám sát sau sự cố**: cảnh báo việc dùng credential cũ, thất bại bất thường, truy cập key version cũ, dấu hiệu abuse tài nguyên hoặc bypass quyền.
7. **Cải thiện cơ chế ngăn tái diễn**: bổ sung scanner/branch policy, bỏ secret khỏi build, audit logger, thu hẹp IAM, tăng TTL/rotation automation và tài liệu cho developer.

Không tự ý xóa log/audit trước khi đáp ứng yêu cầu điều tra hoặc pháp lý; cần phối hợp security/incident response để cách ly, hạn chế truy cập và loại bỏ bản sao nhạy cảm mà vẫn giữ bằng chứng cần thiết.

### Khi nào rotate khác revoke?

- **Rotate**: cấp secret mới, chuyển consumer sang bản mới, sau đó hủy/hạn chế bản cũ theo chính sách.
- **Revoke**: làm secret cũ mất quyền ngay hoặc theo thời gian kiểm soát của hệ thống. Trong tình huống lộ secret, revoke có thể cần được ưu tiên nếu có nguy cơ đang bị khai thác.
- **Expire**: giá trị tự hết hạn theo TTL/lease, không đồng nghĩa sự cố đã được xử lý nếu secret vẫn còn hiệu lực.
- **Re-encrypt/re-wrap**: khi key mã hóa bị lộ, chỉ thay API token không giải quyết dữ liệu đã được bảo vệ bằng key cũ; cần đánh giá phạm vi ảnh hưởng.

Đừng hứa “delete secret khỏi Git là an toàn 100%”: khi không thể kiểm soát mọi bản sao, **phải làm secret cũ không còn hữu dụng** và hạn chế rủi ro còn lại.

## 11. Bảng đối chiếu: cách sai và cách sửa

| Cách làm sai | Vấn đề bảo mật | Thay bằng |
| --- | --- | --- |
| `static final String AES_KEY = "...";` | Key được nhúng trong source/bytecode. | Cấp key qua KMS/HSM hoặc secret manager/runtime key handle. |
| Lưu secret Base64 trong properties | Ai có properties đều decode được. | Không để secret trong artifact; runtime injection có kiểm soát. |
| Đưa keystore + mật khẩu keystore vào cùng JAR | Artifact đủ vật liệu để giải mã khóa. | Keystore ngoài artifact, key-handle/HSM, mật khẩu/identity cấp riêng. |
| `.gitignore` được thêm sau khi commit | Không xóa secret khỏi history/clone. | Revoke/rotate và xử lý bản sao theo incident plan; bổ sung ignore/scanning. |
| Docker `ARG`/`ENV` chứa raw secret lúc build | Secret có thể nằm trong image metadata/layers/cache. | Build secrets chuyên dụng nếu buộc phải dùng và kiểm tra output; cấp tại runtime là ưu tiên. |
| `logger.debug("config={}", config)` | Có thể serialize toàn bộ mật khẩu và token. | Log event với trường allowlist, không log object nhạy cảm. |
| Bật HTTP wire logging trong production | Authorization header/body có thể bị phát tán. | Giữ logging tối thiểu, redaction và tắt log nhạy cảm. |
| Bắt lỗi rồi in `exception.getMessage()` thẳng | Error message của SDK có thể chứa request/URL/secret. | Mã lỗi chuẩn, log có kiểm soát, trace ID và bảo vệ log. |
| Đưa credential trong `-Dtoken=...` khi chạy JVM | Có thể lộ qua process list, shell history/diagnostics. | Cơ chế runtime injection an toàn hơn, file mount hoặc SDK. |
| Dùng cùng secret cho dev và prod | Sự cố môi trường thấp lan sang prod. | Tách identity, secret scope, rotation và quyền từng môi trường. |
| Khi KMS lỗi thì fallback về key nhúng | Fail-open, sử dụng key khó quản lý/lộ. | Fail-closed và cảnh báo; không có fallback secret trong code. |
| Chỉ xóa dòng hard-code sau phát hiện | Secret cũ còn dùng được, vẫn có thể ở history/artifact/log. | Revoke/rotate, kiểm tra toàn bộ nơi rò và giám sát hậu sự cố. |
| In một phần API key để debug | Có thể làm lộ thông tin hữu ích, tạo liên kết giữa log và secret. | Dùng key reference/version được policy cho phép hoặc correlation ID riêng. |
| KeyStore có mật khẩu = “đã an toàn” | Mật khẩu/key vẫn có thể cùng artifact, quyền đọc rộng hoặc backup lộ. | Xem xét toàn bộ nơi lưu và nơi nhận key; HSM/KMS/ACL phù hợp. |

## 12. Checklist PR/CI trước khi phát hành

### Kiểm tra cho lập trình viên

- [ ] Không có **secret có hiệu lực** trong Java source, Kotlin, properties, YAML, JSON, SQL migration, test fixtures hoặc README.
- [ ] `.env` hay local secret config không được track, nhưng hiểu rằng ignore **không sửa history**.
- [ ] Không có secret trong command line, Gradle/Maven task, Dockerfile `ARG`/`ENV` hoặc output của script.
- [ ] Mọi secret production được cấp qua identity/secret manager/runtime injection, **không có fallback hard-code**.
- [ ] Không có `println`/`logger`/`toString`/JSON serialization/exception message làm lộ key, password, Authorization header hoặc token.
- [ ] Không log raw object `SecretKey`, `PrivateKey` hoặc `getEncoded()`.
- [ ] Mọi test đều dùng **dummy credential vô hiệu**, dữ liệu test không được tái sử dụng ở production.
- [ ] Xác định key alias/version, rotation, quyền đọc/operation và trách nhiệm sở hữu.

### Kiểm tra cho build/security/ops

- [ ] Pre-commit/PR scanning và CI checks chặn credential lộ; những phát hiện được xử lý mà không tái phát tán nội dung secret.
- [ ] JAR/WAR/resources/image layers/artifacts được kiểm tra và không chứa secret môi trường.
- [ ] Pipeline có quyền tối thiểu; secret chỉ cấp cho job thực sự cần, không cấp cho PR/fork không tin cậy.
- [ ] Dev/staging/prod dùng secret và identity tách biệt; có key inventory, owner, expiry và runbook rotation.
- [ ] Audit của KMS/secret store bật đúng mức; log aggregation/tracing không giữ raw secret.
- [ ] Runtime secret file có ACL, owner, rotation và bảo vệ backup/mount.
- [ ] Có runbook khi lộ token/key, gồm revoke, chuyển consumer, kiểm tra history/artifact/log và điều tra.
- [ ] Đã kiểm tra đường lỗi như KMS outage, secret hết hạn hoặc permission denied: hệ thống **không fallback sang credential tĩnh**.

## 13. Bài tập tình huống (kèm đáp án)

**Câu 1.** Một class có `private static final String SERVICE_TOKEN = "..."`, code được đưa vào private repository. Có an toàn chưa?

**Đáp án:** Chưa. Token vẫn nằm trong source, history và có thể xuất hiện trong bytecode, artifact, clone. Không nên hard-code bất kể repo private hay public.

**Câu 2.** Developer chuyển giá trị secret từ Java literal vào `src/main/resources/application.properties` rồi build fat JAR. Đã giải quyết chưa?

**Đáp án:** Chưa. Resources thường được đưa vào JAR, vẫn có thể trích xuất được. Cần tách secret khỏi artifact, cấp ở runtime.

**Câu 3.** Đổi token thành Base64 và đặt hằng `BASE64_TOKEN` trong code có đủ bảo mật không?

**Đáp án:** Không. Base64 chỉ đổi biểu diễn; ai có binary và logic giải mã có thể khôi phục. Obfuscation không tạo bí mật thực.

**Câu 4.** Một Dockerfile dùng `ARG API_TOKEN`, rồi xóa file chứa token trong layer sau. Có chắc image sạch không?

**Đáp án:** Không. Token có thể còn ở build metadata, history, layers hoặc cache, và script đã sử dụng token có thể log giá trị. Không truyền raw secret qua ARG/ENV; dùng secret mount chuyên dụng khi cần lúc build và xác minh không persist vào output.

**Câu 5.** Mã Java gọi `logger.debug("headers={}", request.getHeaders())` nhưng log chỉ bật ở DEV. Có rủi ro không?

**Đáp án:** Có. Header có thể chứa Authorization/session token và log DEV/CI cũng có người đọc, backup, APM. Dùng allowlist field và chính sách log nhất quán giữa các môi trường.

**Câu 6.** `System.getenv("DB_PASSWORD")` có tốt hơn hard-code không? Có phải an toàn hoàn toàn không?

**Đáp án:** Tốt hơn về **tách cấu hình khỏi artifact** nếu giá trị được runtime inject, nhưng environment có thể lộ trong process metadata, dump, child process, platform UI hoặc log. Ưu tiên identity/secret manager hoặc runtime mount phù hợp, giảm scope/TTL.

**Câu 7.** Đã xóa secret khỏi nhánh hiện tại và thêm vào `.gitignore`. Có cần rotate không?

**Đáp án:** Nếu secret thật có thể đã bị lộ, **cần đánh giá và thường phải revoke/rotate**. Lịch sử và bản sao không tự biến mất; ignore không thu hồi credential.

**Câu 8.** Một key KMS không thể export, nhưng app log `keyId`. Có vi phạm cùng mức với log raw AES key không?

**Đáp án:** Không nhất thiết. `keyId` thường là metadata được phép audit, còn raw key là bí mật; tuy vậy keyId/alias vẫn phải được kiểm soát theo policy và không chứa thông tin nhạy cảm.

**Câu 9.** Khi secret manager lỗi, ứng dụng chuyển sang credential đã nhúng để luôn phục vụ request. Vì sao nguy hiểm?

**Đáp án:** Fallback làm secret khó quản lý tồn tại trong artifact, bypass quyền và rotation, có thể tiếp tục truy cập bằng khóa đã lộ. Cần fail-closed, alert và quy trình availability được thiết kế từ trước.

**Câu 10.** Ghi `key.getEncoded()` sang log rồi mã hóa tập log sau đó có an toàn tương đương không ghi không?

**Đáp án:** Không. Secret đã đi qua nhiều điểm thu gom/agent/buffer và có thể bị đọc trước khi mã hóa, sao chép sang nơi khác hoặc giữ trong backup. Tốt nhất **không log raw key từ đầu**.

**Câu 11.** Một AES key bị lộ nhưng chỉ dữ liệu mới dùng key mới, dữ liệu cũ vẫn được mã hóa bằng key cũ. Đã xử lý xong chưa?

**Đáp án:** Chưa chắc. Cần đánh giá nguy cơ đối với ciphertext cũ, key version còn dùng để decrypt, phương án re-encrypt/re-wrap, phạm vi và thời điểm thu hồi theo yêu cầu phục hồi dữ liệu. Rotation của khóa mã hóa có nhiều bước hơn thay một API token.

**Câu 12.** Scanner không báo gì trong code; có thể khẳng định image và log không có secret không?

**Đáp án:** Không. Scanner có false negative và chỉ nhìn phạm vi được cấu hình. Cần kiểm tra source history, package/resources, image layers, CI artifacts và logging path, đồng thời có giám sát runtime.

## 14. Tài liệu tham khảo

- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý tạo, phân quyền, lưu trữ, cấp phát, rotation, expiration, revocation và rủi ro của environment variables.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): các loại thông tin cần loại trừ khỏi log, including access tokens, authentication passwords, connection strings và encryption keys.
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html): không hard-code trong pipeline, nguy cơ artifacts/container image và least privilege.
- [MITRE CWE-798 — Use of Hard-coded Credentials](https://cwe.mitre.org/data/definitions/798): vấn đề credential được gắn cố định trong mã/đóng gói.
- [MITRE CWE-532 — Insertion of Sensitive Information into Log File](https://cwe.mitre.org/data/definitions/532.html): rò rỉ bí mật qua log và hệ quả confidentiality.
- [Java SE 17 — KeyGenerator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): sinh khóa đối xứng qua provider.
- [Java SE 17 — SecretKey API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKey.html): giao diện khóa bí mật.
- [Java SE 17 — Cipher API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): AES/GCM và cách làm việc với ciphertext/tag.
- [Java SE 17 — SecureRandom API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn ngẫu nhiên dùng trong ứng dụng bảo mật.
- [Java SE 17 — KeyStore API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): lưu trữ/đọc key và certificate theo keystore/provider.

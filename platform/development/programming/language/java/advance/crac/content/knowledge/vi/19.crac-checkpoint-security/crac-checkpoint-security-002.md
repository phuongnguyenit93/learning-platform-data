# Tạo checkpoint bằng dữ liệu giả và thông tin xác thực giới hạn

Checkpoint image của CRaC (Coordinated Restore at Checkpoint) lưu trạng thái của một tiến trình Java đang chạy. Image có thể chứa object trong heap, cache đã nạp, dữ liệu request, token đã giải mã, cấu hình runtime và vùng nhớ native mà checkpoint engine hỗ trợ. Vì vậy, tạo checkpoint cũng là tạo một bản sao của trạng thái dữ liệu và bảo mật bên trong ứng dụng tại thời điểm đó.

Nếu ứng dụng được warm-up bằng dữ liệu khách hàng thật hoặc sử dụng credential có quyền production, những dữ liệu và credential đó có thể nằm trong checkpoint image. Người có quyền đọc image có thể có được thông tin nhạy cảm hoặc trạng thái xác thực mà ứng dụng đã giữ trong bộ nhớ. Ngay cả khi JAR và container image không chứa secret, checkpoint image vẫn có thể chứa secret đã được nạp và giải mã trong lúc chạy.

Một cách giảm rủi ro là tạo checkpoint trong môi trường được cô lập, dùng **dữ liệu giả (synthetic data)** và **thông tin xác thực giới hạn (restricted credentials)**. Ứng dụng vẫn có thể khởi tạo, warm-up và kiểm tra đường đi xử lý, nhưng không cần tiếp xúc với dữ liệu production hoặc credential có quyền rộng.

Bài này trình bày cách thiết kế dữ liệu và identity cho quá trình tạo checkpoint, quản lý secret trước và sau checkpoint, bảo vệ artifact và kiểm chứng rằng image không mang theo quyền truy cập không cần thiết.

## 1. Vì sao dữ liệu và credential có thể nằm trong checkpoint?

JAR và container image chủ yếu đóng gói chương trình và môi trường chạy. Checkpoint image lại lưu trạng thái của tiến trình sau khi chương trình đã thực thi một phần.

Ví dụ, trước checkpoint, ứng dụng có thể đã:

- Đọc cấu hình từ secret manager.
- Tạo database connection pool với password đã giải mã.
- Nạp access token vào một client.
- Đọc hồ sơ khách hàng vào cache.
- Tạo session và giữ thông tin người dùng trong object.
- Nạp private key hoặc certificate vào TLS context.
- Đọc message chứa dữ liệu cá nhân.
- Tạo buffer native chứa payload đã giải mã.

Những giá trị này có thể còn được tham chiếu trong heap hoặc native memory tại thời điểm checkpoint. Image vì vậy có thể lưu lại các giá trị đó cùng trạng thái tiến trình.

Một ví dụ đơn giản:

~~~text
Application startup
  -> Read secret from secret manager
  -> Authenticate to production database
  -> Load customer records into cache
  -> Warm up services
  -> Create checkpoint
       |
       +-- Heap may contain secret, token and customer data
       +-- Native memory may contain decrypted buffers
       +-- Runtime may hold client and TLS state
~~~

Sau restore, các object có thể xuất hiện lại trong heap. Việc tiến trình được khôi phục không làm cho secret tự động hết hạn, dữ liệu tự động được ẩn danh hoặc quyền truy cập tự động bị thu hồi.

### 1.1 Checkpoint image là bản sao nhạy cảm của trạng thái runtime

Cần áp dụng mức bảo vệ cho checkpoint image dựa trên dữ liệu có thể nằm trong bộ nhớ, không chỉ dựa trên nội dung JAR hoặc container image.

Một image có thể chứa:

- PII hoặc dữ liệu nghiệp vụ được cache.
- Access token, refresh token hoặc session identifier.
- Password, API key hoặc secret đã giải mã.
- Private key hoặc material được TLS provider nạp.
- Cookie, authorization header hoặc request body.
- Dữ liệu tạm trong buffer và object chưa được thu hồi.
- Thông tin nội bộ như hostname, endpoint, tenant ID và topology.

Không nên cho rằng chỉ những object được ứng dụng chủ động serialize mới xuất hiện trong image. Checkpoint engine xử lý trạng thái tiến trình ở mức thấp hơn serialization của ứng dụng.

## 2. Xác định mục tiêu của checkpoint

Trước khi chuẩn bị dữ liệu và credential, hãy xác định image sẽ được dùng vào việc gì.

Các mục tiêu thường gặp:

- Kiểm tra ứng dụng có thể checkpoint và restore hay không.
- Tạo image đã warm-up để khởi chạy nhanh instance mới.
- Kiểm thử callback Resource và quy trình reconnect.
- Kiểm tra hiệu năng restore và thời gian readiness.
- Tạo artifact dùng trong CI hoặc staging.
- Chuẩn bị image cho production deployment.

Mỗi mục tiêu cần mức dữ liệu và quyền khác nhau. Một bài kiểm tra lifecycle thường chỉ cần dữ liệu giả và credential sandbox. Một image dùng để scale production có thể cần cấu hình production-compatible, nhưng vẫn nên lấy secret production sau restore bằng identity của instance thay vì đóng gói credential dài hạn vào image.

Hãy phân biệt:

| Mục tiêu | Dữ liệu phù hợp | Credential phù hợp |
|---|---|---|
| Kiểm tra API CRaC và callback | Fixture giả, dữ liệu nhỏ | Không cần credential hoặc credential sandbox |
| Kiểm tra tích hợp database | Database riêng với schema và dữ liệu giả | Database user chỉ có quyền trên database test |
| Kiểm tra OAuth/OIDC | Test tenant và test users | Client/identity sandbox, scope tối thiểu |
| Warm-up trước khi tạo image | Dữ liệu đại diện đã tổng hợp | Credential ngắn hạn, không có quyền production |
| Image được restore trong production | Cache không nhạy cảm hoặc cache có thể rebuild | Lấy credential runtime sau restore qua workload identity |
| Kiểm tra secret rotation | Secret giả có version và TTL kiểm soát | Credential test có thể revoke |

Không cần dùng dữ liệu production chỉ để tạo workload có kích thước giống production. Có thể tạo dữ liệu tổng hợp theo phân phối, cardinality và kích thước tương đương mà không sao chép thông tin nhận dạng thật.

## 3. Dùng synthetic data thay cho dữ liệu production

Synthetic data là dữ liệu được tạo ra có chủ đích để mô phỏng cấu trúc và đặc tính của dữ liệu thực. Nó không phải bản sao đã đổi tên của một tập dữ liệu khách hàng.

Ví dụ, thay vì sao chép hồ sơ khách hàng rồi thay tên và email, hãy sinh dữ liệu mới:

~~~json
{
  "customerId": "test-customer-000104",
  "name": "Nguyen Example",
  "email": "customer-104@example.invalid",
  "segment": "STANDARD",
  "createdAt": "2026-10-01T08:00:00Z"
}
~~~

Tên miền .invalid được dành riêng cho mục đích kiểm thử và không đại diện cho một địa chỉ email có thể nhận thư. Các giá trị ví dụ cần tuân theo quy ước riêng của hệ thống test.

### 3.1 Synthetic data khác masking và anonymization

| Phương pháp | Cách tạo | Rủi ro còn lại |
|---|---|---|
| Synthetic data | Tạo bản ghi mới theo schema và quy tắc mô phỏng | Thấp hơn nếu không sao chép giá trị hoặc bí mật từ nguồn thật |
| Masking | Thay một số trường như tên, email, số điện thoại | Có thể còn dữ liệu nhận dạng qua trường khác hoặc liên kết nhiều bảng |
| Pseudonymization | Thay định danh trực tiếp bằng mã giả | Có thể tái nhận dạng nếu còn bảng ánh xạ hoặc dữ liệu phụ |
| Anonymization | Xử lý dữ liệu nhằm giảm khả năng nhận dạng cá nhân | Chất lượng phụ thuộc kỹ thuật và khả năng kết hợp với dữ liệu ngoài |

Masking không tự động biến dữ liệu production thành dữ liệu vô hại. Một bộ dữ liệu đã thay tên nhưng vẫn giữ ngày sinh chính xác, địa chỉ, lịch sử giao dịch hiếm hoặc quan hệ giữa các bảng có thể vẫn nhận dạng được một người.

Nếu mục tiêu là tạo checkpoint test, ưu tiên sinh dữ liệu mới. Nếu buộc phải dùng dữ liệu dẫn xuất từ production, cần quy trình privacy review riêng, kiểm tra nguy cơ tái nhận dạng và giới hạn quyền truy cập. Không coi việc thay tên hoặc hash email là anonymization hoàn chỉnh.

### 3.2 Giữ cấu trúc và phân phối cần thiết

Dữ liệu giả vẫn cần đủ đại diện để warm-up có ý nghĩa. Hãy xác định những thuộc tính quan trọng đối với workload:

- Số lượng bản ghi và cardinality.
- Phân phối kích thước payload.
- Tỷ lệ trạng thái và loại nghiệp vụ.
- Quan hệ khóa ngoại.
- Dữ liệu thiếu hoặc null.
- Chuỗi dài, ký tự Unicode và dữ liệu biên.
- Ngày giờ trong quá khứ và tương lai.
- Bản ghi có trạng thái hoàn tất, lỗi hoặc đang chờ.
- Các trường hợp có thể kích hoạt nhánh xử lý khác nhau.

Không cần sao chép giá trị thực để giữ phân phối. Ví dụ, có thể tạo 100.000 khách hàng giả, với tỷ lệ segment tương tự dữ liệu tổng hợp đã được phê duyệt, nhưng dùng ID và thuộc tính hoàn toàn mới.

### 3.3 Dùng dữ liệu nhất quán giữa các bảng

Nếu ứng dụng cần customer, order và payment, hãy tạo fixture có quan hệ nhất quán:

~~~sql
INSERT INTO customer(customer_id, display_name)
VALUES
    ('test-customer-001', 'Customer Example 001'),
    ('test-customer-002', 'Customer Example 002');

INSERT INTO orders(order_id, customer_id, status)
VALUES
    ('test-order-001', 'test-customer-001', 'PENDING'),
    ('test-order-002', 'test-customer-002', 'PAID');
~~~

Đây chỉ là ví dụ minh họa. Hãy dùng namespace hoặc database riêng để fixture không thể ghi vào production.

Nếu dùng generator, nên tạo ID có prefix rõ ràng như test-, synthetic- hoặc fixture-. Tuy nhiên, prefix không thay thế việc cô lập database và network. Một cấu hình nhầm vẫn có thể gửi fixture tới hệ thống thật.

### 3.4 Synthetic data phải tránh side effect thật

Fixture không nên kích hoạt:

- Email tới khách hàng thật.
- SMS hoặc cuộc gọi thật.
- Payment hoặc refund thật.
- Webhook tới đối tác thật.
- Tạo tài khoản hoặc API key production.
- Message tới topic production.
- Giao dịch hoặc báo cáo được xem như số liệu kinh doanh thật.

Dùng fake SMTP, mock payment provider, sandbox endpoint, message broker riêng và network policy chặn egress tới production. Nếu cần kiểm tra giao thức, hãy dùng sandbox chính thức của nhà cung cấp.

## 4. Cô lập môi trường tạo checkpoint

Dữ liệu giả chỉ có ý nghĩa nếu ứng dụng không thể vô tình truy cập production. Môi trường tạo checkpoint nên có ranh giới rõ ràng về network, identity, storage và quyền.

### 4.1 Tách environment

Dùng một environment riêng cho quá trình tạo checkpoint, ví dụ:

~~~text
checkpoint-build
  |
  +-- synthetic database
  +-- test message broker
  +-- sandbox identity provider
  +-- fake email/payment endpoints
  +-- test object storage
  +-- restricted secret store
~~~

Không dùng chung database, broker hoặc bucket production rồi chỉ dựa vào tên schema hoặc prefix để phân biệt. Tách account, project, subscription hoặc network boundary khi nền tảng hỗ trợ.

### 4.2 Network egress policy

Container tạo checkpoint nên chỉ kết nối tới các dependency được liệt kê. Có thể dùng network policy, firewall hoặc egress gateway để:

- Chặn dải IP và endpoint production.
- Chỉ cho phép sandbox services.
- Chặn metadata endpoint không cần thiết.
- Chặn truy cập internet tùy mục tiêu test.
- Ghi log các kết nối bị từ chối.

Allowlist endpoint rõ ràng an toàn hơn việc chỉ hy vọng ứng dụng không gọi nhầm URL.

### 4.3 Tách storage

Dùng volume và bucket riêng cho:

- Dữ liệu fixture.
- Log của checkpoint job.
- File tạm và file mapping.
- Checkpoint artifact.
- Test report.

Không mount volume production vào container tạo checkpoint nếu không có yêu cầu đã được phê duyệt. Mount read-only cũng không làm dữ liệu production trở thành dữ liệu giả; nó vẫn có thể bị đưa vào heap hoặc checkpoint image nếu ứng dụng đọc nó.

### 4.4 Cấu hình môi trường rõ ràng

Đưa environment identity vào cấu hình và xác minh trước khi warm-up:

~~~yaml
environment:
  name: checkpoint-build
  dataMode: synthetic
  allowProductionEndpoints: false

dependencies:
  database: checkpoint-test-db
  identityProvider: sandbox
  messageBroker: checkpoint-test-broker

checkpoint:
  enabled: true
  artifactClass: restricted-test
~~~

Đây là cấu trúc cấu hình minh họa do ứng dụng tự định nghĩa. Cần validate cấu hình trước khi mở kết nối. Nếu environment không đúng hoặc endpoint không nằm trong allowlist, dừng quá trình tạo checkpoint.

Không đặt secret thật trong YAML, Dockerfile, build argument hoặc source repository.

## 5. Thiết kế credential với quyền tối thiểu

Credential dùng trong quá trình tạo checkpoint nên chỉ có quyền cần thiết cho các bước startup và warm-up.

Áp dụng nguyên tắc least privilege:

- Chỉ truy cập một database test hoặc schema test.
- Chỉ đọc các bảng cần warm-up nếu không cần ghi.
- Chỉ ghi vào namespace fixture.
- Chỉ publish vào topic test.
- Chỉ gọi sandbox API.
- Không có quyền quản trị account hoặc subscription.
- Không có quyền đọc secret production.
- Không có quyền tạo credential mới ngoài phạm vi test.
- Không dùng cùng một credential cho CI, checkpoint job và production runtime.

### 5.1 Tách identity theo vai trò

Nên phân biệt ít nhất ba identity:

| Identity | Nhiệm vụ | Quyền cần có |
|---|---|---|
| Build identity | Build JAR/container và publish artifact | Đọc dependency build, ghi artifact registry được chỉ định |
| Checkpoint identity | Khởi động ứng dụng, truy cập fixture và warm-up | Chỉ truy cập sandbox dependency và dữ liệu giả |
| Runtime identity | Phục vụ workload sau restore | Quyền nghiệp vụ cần thiết cho đúng service/tenant/instance |

Không dùng build identity làm runtime identity. Không đưa quyền production vào checkpoint identity chỉ để warm-up thành công.

Nếu checkpoint image được tạo trong môi trường test rồi restore ở production, ứng dụng cần lấy runtime identity mới theo workload identity của instance sau restore. Không kế thừa credential test trong image để gọi dịch vụ production.

### 5.2 Scope và audience

Với OAuth hoặc token-based authentication, giới hạn:

- Scope chỉ đủ cho API cần gọi.
- Audience đúng resource server.
- Tenant hoặc project chỉ thuộc sandbox.
- Thời hạn token ngắn.
- Quyền không bao gồm admin hoặc wildcard nếu không cần.
- Token không thể dùng ở production.

Một token có scope nhỏ nhưng audience production vẫn có thể tạo rủi ro. Cần kiểm tra cả issuer, audience, scope, tenant và resource server.

### 5.3 Credential ngắn hạn

Ưu tiên credential có TTL ngắn và có thể revoke. Không tạo password tĩnh dùng chung cho nhiều lần checkpoint.

Credential checkpoint nên có:

- Thời hạn phù hợp với thời gian tạo và test image.
- Quyền giới hạn theo resource.
- Chủ sở hữu rõ ràng.
- Quy trình revoke sau khi hoàn tất.
- Audit log về việc cấp và sử dụng.
- Không được tái sử dụng làm credential production.

TTL ngắn làm giảm cửa sổ rủi ro, nhưng không tự loại bỏ secret khỏi image. Nếu token còn nằm trong heap sau khi hết hạn, nó vẫn là dữ liệu nhạy cảm cần bảo vệ.

### 5.4 Không dùng credential production chỉ để warm-up

Warm-up thường cần thực hiện truy vấn, kết nối và thao tác đại diện. Những thao tác này có thể được thực hiện bằng sandbox credential và synthetic data.

Nếu cần đo latency gần production, hãy dùng môi trường staging có cấu hình tương đương, không dùng quyền production. Nếu có một bước chỉ production mới thực hiện được, hãy tách bước đó khỏi checkpoint creation và thực hiện sau restore bằng runtime identity.

## 6. Không đưa secret dài hạn vào checkpoint

Nguyên tắc tốt nhất là không nạp secret production dài hạn vào tiến trình trước khi checkpoint.

Thay vì:

~~~text
Start application
  -> Load production password
  -> Create production connection pool
  -> Warm up
  -> Checkpoint
~~~

Hãy tổ chức:

~~~text
Create checkpoint in isolated environment
  -> Use synthetic data
  -> Use sandbox credential with limited scope
  -> Warm up safe code paths
  -> Close sandbox clients
  -> Remove checkpoint-only credential references
  -> Create restricted checkpoint artifact

Restore in target environment
  -> Obtain instance-specific runtime identity
  -> Fetch current secrets
  -> Create production clients
  -> Reconcile external state
  -> Mark ready
~~~

Điều này giảm nguy cơ image chứa credential production và tránh dùng nhầm endpoint test sau restore.

### 6.1 Lấy secret sau restore

Nếu workload chạy trên nền tảng có workload identity, instance có thể xác thực với secret manager sau restore rồi lấy secret hiện tại.

Luồng tham khảo:

1. Container/instance được cấp identity riêng bởi platform.
2. Ứng dụng xác thực bằng workload identity.
3. Secret manager xác minh identity và policy.
4. Ứng dụng lấy secret đúng version hoặc version hiện hành.
5. Client được tạo lại bằng credential mới.
6. Readiness chỉ bật sau khi kiểm tra thành công.

Secret manager, workload identity và API cụ thể tùy cloud/platform. Không hard-code credential vào checkpoint để thay thế cơ chế identity của nền tảng.

### 6.2 Không lấy secret mới rồi ghi vào checkpoint cũ

Checkpoint image là artifact bất biến theo một lần tạo. Nếu restore rồi thay secret trong heap, thay đổi đó thuộc tiến trình đã restore; nó không tự cập nhật file image gốc.

Nếu tạo checkpoint mới từ tiến trình đã restore, hãy đánh giá lại toàn bộ dữ liệu và credential trong heap trước khi lưu image tiếp theo. Không biến một image ban đầu chỉ chứa credential test thành image mới có credential production mà không có quy trình bảo mật và phân loại artifact phù hợp.

## 7. Xử lý credential đã nằm trong bộ nhớ

Đôi khi ứng dụng phải xác thực với sandbox để warm-up. Khi đó, cần giảm tối đa dữ liệu credential còn tồn tại trong image.

### 7.1 Dừng refresh task và client

Trước checkpoint:

- Dừng background token refresh.
- Ngừng request mới.
- Drain request đang dùng credential.
- Đóng connection pool và client sandbox.
- Hủy scheduler hoặc callback có thể tiếp tục sử dụng token.
- Xóa cache credential nếu không cần cho restore.
- Xác minh không còn thread sử dụng secret.

Việc đóng client không đảm bảo mọi bản sao credential trong heap hoặc native memory đã bị xóa. Nó chỉ là một phần của lifecycle cleanup.

### 7.2 Mutable buffer và zeroization best effort

Nếu ứng dụng tự quản lý secret trong byte array, có thể ghi đè vùng nhớ trước khi bỏ tham chiếu:

~~~java
import java.util.Arrays;

public final class SecretBytes implements AutoCloseable {

    private byte[] value;

    public SecretBytes(byte[] value) {
        this.value = value.clone();
    }

    public synchronized byte[] copy() {
        if (value == null) {
            throw new IllegalStateException("Secret is closed");
        }
        return value.clone();
    }

    @Override
    public synchronized void close() {
        if (value != null) {
            Arrays.fill(value, (byte) 0);
            value = null;
        }
    }
}
~~~

Đây chỉ là best-effort zeroization cho buffer mà class sở hữu. Nó không xóa bản sao đã tạo trước đó, buffer của thư viện, native memory, CPU register, swap hoặc trang nhớ mà runtime/checkpoint engine đã sao chép. Không thể đưa ra bảo đảm xóa tuyệt đối chỉ bằng Arrays.fill().

### 7.3 String không thể xóa nội dung tại chỗ

Java String là immutable. Khi secret được chuyển thành String, ứng dụng không thể ghi đè nội dung của object String bằng API Java chuẩn.

Gán biến về null chỉ bỏ một reference. Garbage Collector có thể thu hồi object sau này, nhưng không đảm bảo thời điểm hoặc việc vùng nhớ cũ được ghi đè trước checkpoint.

Vì vậy:

- Tránh chuyển secret sang String nếu API cho phép dùng char[] hoặc byte[].
- Tránh tạo nhiều bản sao khi format hoặc nối chuỗi.
- Không log secret hoặc exception message chứa secret.
- Không giữ token trong static field lâu hơn cần thiết.
- Không dựa vào System.gc() để xóa secret.
- Tốt nhất là không nạp credential nhạy cảm trước checkpoint.

Ngay cả khi dùng mutable array, các thư viện có thể tạo bản sao nội bộ. Hãy xem zeroization là biện pháp giảm rủi ro, không phải lý do để đưa secret production vào image.

### 7.4 TLS context và private key

SSLContext, KeyManager, TrustManager hoặc provider có thể giữ key material trong object graph hoặc native memory. Đóng socket không nhất thiết xóa mọi key material đã được nạp.

Nếu checkpoint chỉ cần warm-up code path, hãy dùng certificate test. Tạo lại TLS context bằng certificate/secret hiện tại sau restore. Không đưa private key production vào image tạo trong CI hoặc staging.

## 8. Quản lý Resource callback cho checkpoint-only credential

Có thể dùng CRaC Resource để dừng và giải phóng tài nguyên chỉ dùng trong quá trình tạo checkpoint, sau đó tạo runtime client mới sau restore.

Ví dụ sau mô tả cấu trúc:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CheckpointClientResource implements Resource {

    private final CheckpointClientFactory checkpointFactory;
    private final RuntimeClientFactory runtimeFactory;

    private CheckpointClient checkpointClient;
    private RuntimeClient runtimeClient;

    public CheckpointClientResource(
            CheckpointClientFactory checkpointFactory,
            RuntimeClientFactory runtimeFactory) {
        this.checkpointFactory = checkpointFactory;
        this.runtimeFactory = runtimeFactory;

        this.checkpointClient = checkpointFactory.createSandboxClient();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (checkpointClient != null) {
            checkpointClient.stopAndDrain();
            checkpointClient.clearCredentialReferences();
            checkpointClient.close();
            checkpointClient = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        runtimeClient = runtimeFactory.createForCurrentInstance();
        runtimeClient.validateConnection();
    }
}
~~~

Các kiểu CheckpointClient, RuntimeClient và factory trong ví dụ là abstraction của ứng dụng, không phải API có sẵn của CRaC. Ví dụ minh họa việc tách client sandbox và client runtime.

Một số điểm cần lưu ý:

- Checkpoint client chỉ được phép truy cập sandbox.
- Runtime factory lấy identity của instance hiện tại sau restore.
- Không chuyển credential sandbox sang runtime client.
- Không mở readiness chỉ vì runtime client object đã được tạo.
- Nếu lấy credential hoặc validate thất bại, truyền lỗi ra ngoài hoặc giữ ứng dụng ở trạng thái chưa sẵn sàng theo lifecycle được thiết kế.
- Nếu beforeCheckpoint thất bại, CRaC có thể gọi restore notification để phục hồi resource trong tiến trình ban đầu; callback phải xử lý trạng thái đã đóng một phần.

Nếu callback afterRestore được gọi trong tiến trình mới, runtime factory cần lấy identity tương ứng với instance đó. Không dùng static token hoặc identity đã checkpoint từ instance nguồn.

### 8.1 Không gọi network vô hạn trong callback

Việc lấy secret hoặc xác thực sau restore có thể gặp timeout. Dùng connect timeout, request timeout và retry có giới hạn. Không giữ callback chờ vô hạn.

Nếu framework cho phép phục hồi dependency bất đồng bộ, hãy giữ readiness false cho tới khi runtime client hoạt động. Phải có trạng thái rõ ràng giữa RESTORING, RECONNECTING, RECONCILING và READY.

## 9. Kiểm tra không còn credential checkpoint trong image

Không có một công cụ chung có thể chứng minh mọi byte secret đã biến mất khỏi checkpoint image. Có thể kết hợp nhiều biện pháp kiểm soát:

- Thiết kế để secret production chưa từng được nạp trước checkpoint.
- Dùng credential sandbox ngắn hạn, có thể revoke.
- Dừng refresh task và đóng client.
- Xóa reference và zeroize mutable buffers do ứng dụng sở hữu.
- Không log token, password hoặc authorization header.
- Kiểm tra heap dump hoặc object inventory trong môi trường test nếu phù hợp.
- Kiểm tra file cấu hình, environment và metadata không chứa secret.
- Thử restore rồi xác minh credential sandbox đã hết hạn hoặc bị revoke.
- Xác minh runtime credential mới được cấp sau restore.
- Bảo vệ checkpoint artifact như dữ liệu nhạy cảm ngay cả khi đã scrub.

### 9.1 Secret scanning không đủ để chứng minh image sạch

Scanner có thể tìm chuỗi token hoặc pattern password trong file, nhưng checkpoint image có thể chứa memory pages nén, binary structures hoặc dữ liệu không có format văn bản dễ nhận diện.

Một kết quả scan không tìm thấy secret không chứng minh không có secret. Phòng ngừa bằng identity và data isolation quan trọng hơn việc chỉ scan artifact sau khi tạo.

### 9.2 Thử nghiệm token replay trong sandbox

Có thể tạo test token với scope nhỏ và TTL ngắn, rồi kiểm tra:

1. Token hoạt động trước checkpoint trong sandbox.
2. Token được revoke hoặc hết hạn theo test plan.
3. Image được restore.
4. Ứng dụng không tiếp tục dùng token cũ.
5. Runtime identity mới được cấp.
6. Request sandbox bằng credential mới hoạt động.
7. Không có request production nào phát sinh.

Không dùng token production để kiểm tra khả năng replay. Test nên ghi nhận token reference hoặc fingerprint, không log token nguyên bản.

## 10. Bảo vệ checkpoint artifact

Ngay cả khi dùng dữ liệu giả và credential giới hạn, checkpoint image vẫn cần được bảo vệ. Nó có thể chứa cấu trúc nội bộ, dữ liệu test, secret tạm thời và trạng thái runtime có thể bị lạm dụng.

### 10.1 Quyền truy cập tối thiểu

Giới hạn ai có thể:

- Tạo checkpoint.
- Đọc hoặc tải artifact.
- Sao chép image sang environment khác.
- Restore image.
- Xóa hoặc thay thế artifact.
- Đọc metadata và log đi kèm.

Tách quyền publish container image khỏi quyền tải checkpoint artifact nếu nền tảng cho phép. Người có quyền đọc checkpoint có thể có quyền quan sát nhiều trạng thái runtime hơn người chỉ có quyền pull JAR.

### 10.2 Mã hóa khi lưu và truyền

Dùng mã hóa storage và transport do nền tảng cung cấp. Quản lý encryption key tách biệt với artifact:

- Không lưu encryption key bên trong checkpoint.
- Giới hạn quyền decrypt cho workload hoặc pipeline được phép.
- Audit thao tác decrypt.
- Có quy trình rotate key.
- Xác minh backup và replica storage cũng được mã hóa.

Nếu image được chuyển giữa registry, object storage và node, bảo vệ mọi chặng truyền. Checksum xác minh tính toàn vẹn nhưng không thay thế encryption hoặc access control.

### 10.3 Integrity và provenance

Gắn checkpoint với metadata bất biến:

~~~yaml
artifact:
  checkpointId: orders-test-2026-11-13-001
  applicationBuild: 2.8.1
  containerDigest: sha256:example-container-digest
  createdFrom: checkpoint-build
  dataClassification: synthetic
  credentialClass: sandbox-short-lived
  createdAt: "2026-11-13T07:00:00Z"
  checksum: sha256:example-checkpoint-digest
~~~

Đây là manifest minh họa do pipeline định nghĩa. Không đưa secret value, token hoặc private key vào metadata.

Có thể ký manifest hoặc artifact bằng cơ chế signing của tổ chức để xác minh nguồn tạo và phát hiện thay đổi. Chỉ restore artifact có provenance được chấp nhận.

### 10.4 Retention và xóa

Đặt thời hạn lưu checkpoint theo mục đích:

- CI checkpoint có thể chỉ tồn tại trong thời gian ngắn.
- Staging checkpoint được giữ theo release window.
- Production checkpoint có retention theo rollback policy.
- Artifact chứa credential test phải bị thu hồi hoặc hết hạn theo lịch.

Khi xóa, cần xem xét bản sao trong backup, replica, cache registry và workspace CI. Xóa một object trong bucket chính không đảm bảo mọi bản sao đã biến mất.

### 10.5 Không publish nhầm vào registry công khai

Checkpoint image không nên được đẩy lên public registry chỉ vì container image tương ứng được public. Kiểm tra destination và ACL trong pipeline. Dùng registry hoặc bucket riêng cho checkpoint artifact.

## 11. Quy trình tạo checkpoint an toàn trong CI/CD

Một pipeline có thể tổ chức như sau:

~~~mermaid
flowchart TD
    A["Build JAR and container image"] --> B["Create isolated checkpoint environment"]
    B --> C["Provision synthetic fixtures"]
    C --> D["Issue sandbox-only credentials"]
    D --> E["Start application and warm up"]
    E --> F["Verify no production route or identity"]
    F --> G["Stop traffic and drain work"]
    G --> H["Close sandbox clients and scrub owned secrets"]
    H --> I["Create checkpoint"]
    I --> J["Store encrypted restricted artifact"]
    J --> K["Revoke checkpoint credentials"]
    K --> L["Restore in isolated target"]
    L --> M["Acquire new instance identity"]
    M --> N["Validate dependencies and readiness"]
    N --> O["Publish with provenance and retention"]
~~~

Trình tự cụ thể phụ thuộc ứng dụng và engine. Một số credential có thể cần còn hiệu lực cho bước test restore ngay sau checkpoint; hãy giữ chúng trong sandbox với quyền nhỏ, sau đó revoke theo test plan. Nếu image sẽ được giữ lâu hơn TTL của credential, không được dựa vào credential đó khi restore.

### 11.1 Provision fixture trước khi khởi động ứng dụng

Có thể tạo schema và dữ liệu giả bằng migration/fixture job riêng. Ứng dụng chỉ nhận quyền truy cập đúng database test.

Điều này giúp tránh việc ứng dụng tự phát hiện nhầm environment rồi tạo dữ liệu trên database ngoài ý muốn.

### 11.2 Warm-up chỉ dùng đường đi an toàn

Warm-up nên kiểm tra các đường code cần thiết nhưng không tạo side effect production. Dùng sandbox provider cho payment, email, object storage, message broker và identity.

Nếu có một đường xử lý không thể mô phỏng an toàn, có thể warm-up tới trước điểm gọi external side effect hoặc dùng mock có cùng interface.

### 11.3 Tạo image sau khi dừng công việc

Trước checkpoint:

- Ngừng nhận request.
- Drain request đang chạy.
- Dừng consumer và scheduler.
- Kết thúc transaction.
- Đóng client sandbox.
- Xóa dữ liệu tạm không cần giữ.
- Xác minh không còn tác vụ nền dùng credential.

Không tạo checkpoint giữa một thao tác có thể gây side effect không xác định ở hệ thống ngoài.

### 11.4 Restore test bằng identity mới

Trong bài test restore, cấp một runtime identity sandbox khác với identity tạo checkpoint. Nhờ đó, có thể chứng minh ứng dụng thực sự lấy credential mới sau restore thay vì dùng lại credential trong image.

Kiểm tra log của identity provider hoặc secret manager để xác nhận identity nào đã lấy secret và thời điểm nào. Không ghi giá trị secret vào log.

## 12. Dùng checkpoint cho production mà không mang credential production theo image

Một chiến lược thường dùng là tạo image từ môi trường tương thích nhưng không chứa credential production.

Trước checkpoint:

- Dùng synthetic data hoặc cache không nhạy cảm.
- Dùng sandbox identity để warm-up.
- Đóng client sandbox.
- Không nạp production secret.
- Gắn metadata về build và config compatibility.

Sau restore production:

- Platform cấp workload identity riêng cho instance.
- Ứng dụng lấy production secret từ secret manager.
- Tạo lại connection pool và network clients.
- Reconcile configuration và external state.
- Xác minh schema, endpoint và quyền.
- Chỉ sau đó mở readiness.

Nếu ứng dụng cần dữ liệu production để phục vụ ngay sau restore, hãy tải dữ liệu đó sau restore từ nguồn có thẩm quyền. Nếu cần cache trước, cân nhắc dữ liệu không nhạy cảm hoặc cache được mã hóa và có policy riêng; không mặc định đưa dữ liệu khách hàng vào image.

### 12.1 Tách warm-up khỏi việc nạp dữ liệu thật

Warm-up có thể dựa trên:

- Synthetic records.
- Request mẫu đã tạo mới.
- Cache key giả.
- Query có kết quả test.
- Model hoặc metadata không nhạy cảm.
- Code path được chạy với mock/sandbox dependency.

Mục tiêu warm-up là nạp class, JIT và khởi tạo cấu trúc cần thiết. Không phải mọi dữ liệu nghiệp vụ thật đều cần nằm trong heap để đạt mục tiêu đó.

### 12.2 Cache production cần policy riêng

Nếu một cache chứa dữ liệu production là thiết yếu để giảm latency, cần đánh giá:

- Dữ liệu có chứa PII hoặc secret không?
- Có thể rebuild sau restore không?
- Dữ liệu stale có gây sai nghiệp vụ không?
- Có TTL và version không?
- Ai có quyền đọc checkpoint artifact?
- Image có được restore ở environment khác không?
- Có thể mã hóa dữ liệu cache ở tầng ứng dụng không?
- Có thể tải cache sau restore theo tenant/instance identity không?

Chỉ giữ cache trong image khi lợi ích và rủi ro đã được xác định, và có cơ chế bảo vệ tương ứng.

## 13. Quản lý nhiều instance restore từ cùng một image

Nếu một checkpoint được dùng để tạo nhiều instance, mọi object trong image có thể được nhân bản cùng lúc. Điều này đặc biệt nguy hiểm với credential hoặc state có tính duy nhất.

Các rủi ro:

- Nhiều instance cùng dùng một refresh token.
- Nhiều instance cùng sử dụng một API key có giới hạn concurrency.
- Nhiều instance cùng mang một session hoặc identity nguồn.
- Nhiều instance cùng dùng một client certificate.
- Nhiều instance cùng sở hữu một lease hoặc scheduled job.
- Một instance revoke credential khiến các instance khác mất quyền.

### 13.1 Cấp identity theo từng instance

Sau restore, mỗi instance nên lấy identity riêng từ platform hoặc identity provider. Credential nên được gắn với workload, pod, VM hoặc service account cụ thể.

Không dùng UUID hoặc token được tạo trước checkpoint làm identity duy nhất của tất cả replica.

### 13.2 Không chia sẻ refresh token trong image

Refresh token rotation có thể khiến instance đầu tiên dùng token thành công và các instance sau bị từ chối. Nếu image được nhân bản, token state trong heap cũng bị nhân bản.

Dùng một trong các thiết kế:

- Mỗi instance nhận credential riêng sau restore.
- Một token broker duy nhất quản lý refresh token.
- Credential có thể được cấp lại độc lập cho từng workload.
- Dùng concurrency control và atomic token rotation nếu issuer hỗ trợ.

### 13.3 Tài nguyên dùng chung cần coordination bên ngoài

Checkpoint image không phải distributed lock. Dùng lease service, database lock, compare-and-set hoặc fencing token để quản lý quyền sở hữu. Không cho phép một boolean trong heap quyết định instance nào được quyền thực hiện side effect.

## 14. Kiểm thử dữ liệu giả và credential giới hạn

Một bài test an toàn cần chứng minh cả hai điều: dữ liệu được dùng là dữ liệu giả và credential có quyền đúng phạm vi.

### 14.1 Kiểm tra dữ liệu

- Fixture có source và generator được ghi nhận.
- Không có bản ghi khách hàng thật.
- Không có email hoặc số điện thoại có thể liên hệ người thật.
- Không có token hoặc secret được copy từ production.
- Quan hệ dữ liệu và phân phối đủ cho workload test.
- Log và report không chứa payload nhạy cảm.
- Dataset có thể tái tạo và xóa sau test.

Nếu dùng dữ liệu dẫn xuất từ production, cần có bằng chứng privacy review và quy trình anonymization được phê duyệt. Không chỉ dựa vào tên field hoặc prefix test.

### 14.2 Kiểm tra credential

- Issuer đúng là sandbox hoặc test identity provider.
- Audience đúng resource test.
- Scope nhỏ nhất cần thiết.
- Credential có TTL.
- Credential có thể revoke.
- Không có quyền production.
- Không có quyền admin không cần thiết.
- Identity được phân biệt giữa checkpoint build và restored instance.
- Secret không được in vào log hoặc metadata.
- Runtime identity được cấp lại sau restore.

### 14.3 Kiểm tra network và destination

- Production endpoint bị chặn từ checkpoint environment.
- Database hostname và account thuộc test.
- Broker/topic thuộc test.
- Email/payment provider là fake hoặc sandbox.
- Object storage bucket thuộc test.
- Restore target chỉ truy cập dependency theo allowlist.
- Kết quả network policy được lưu cùng test report.

### 14.4 Kiểm tra checkpoint artifact

- Checksum được xác minh.
- Artifact được lưu trong restricted storage.
- Encryption được bật.
- ACL được kiểm tra.
- Manifest không chứa secret.
- Retention có thời hạn.
- Artifact không được publish vào public registry.
- Restore test dùng identity mới và xác minh credential cũ không được dùng.

## 15. Các tình huống lỗi và cách xử lý

| Tình huống | Nguy cơ | Hành vi nên có |
|---|---|---|
| Ứng dụng trỏ nhầm production database | Dữ liệu thật lọt vào heap/image | Chặn kết nối bằng network policy và fail fast khi environment mismatch |
| Checkpoint credential có scope rộng | Image chứa quyền vượt nhu cầu | Revoke, hủy artifact và tạo lại với scope tối thiểu |
| Token còn sống sau restore | Credential test tiếp tục được dùng | Kiểm tra expiry/revocation và không cho phép dùng lại |
| Secret production đã được nạp trước checkpoint | Secret có thể nằm trong image | Không publish image; xử lý credential và tạo lại image an toàn |
| Secret String không thể zeroize | Bản sao có thể còn trong heap | Không dựa vào GC; tránh nạp secret trước checkpoint |
| Restore nhiều replica cùng token | Rotation/reuse hoặc xung đột | Cấp credential riêng theo instance |
| Secret manager không sẵn sàng sau restore | Không thể tạo client runtime | Giữ readiness false, retry có giới hạn và báo lỗi |
| Fixture gửi email thật | Side effect tới người dùng | Fake SMTP, chặn egress và dùng địa chỉ test |
| Artifact bị tải trái phép | Lộ heap data hoặc credential | Revoke credential, audit, xử lý incident và thu hồi artifact |
| Restore dùng cấu hình sandbox | Instance production gọi nhầm test service | Reconcile environment config trước readiness |

Nếu phát hiện checkpoint image chứa credential production hoặc dữ liệu không được phép, hãy xem đó là một sự cố bảo mật artifact. Chỉ xóa một reference trong ứng dụng không thu hồi các bản sao đã được lưu. Cần revoke credential, xác định phạm vi artifact và bản backup, hạn chế truy cập và tạo image mới từ môi trường sạch.

## 16. Quan sát và audit

Mỗi lần tạo checkpoint nên có log và metadata đủ để trả lời:

- Image được tạo từ environment nào?
- Dataset nào được dùng và generator version nào?
- Credential class nào được cấp?
- Credential thuộc issuer và audience nào?
- TTL và thời điểm revoke là gì?
- Container/JDK/engine build nào tạo image?
- Ai hoặc pipeline nào tạo và publish image?
- Artifact được lưu ở đâu và ai đã tải?
- Restore instance đã lấy identity mới hay chưa?
- Có request nào tới production endpoint trong checkpoint build không?

Không ghi secret value. Dùng ID, version hoặc fingerprint không nhạy cảm.

Metric hữu ích:

- Số lần checkpoint build bị từ chối do environment mismatch.
- Số request bị network policy chặn.
- Thời gian warm-up và checkpoint.
- Số lần cấp credential sandbox.
- Số credential bị revoke sau build.
- Số lần restore dùng identity mới thành công.
- Số lỗi reconnect hoặc secret retrieval.
- Thời gian từ restore tới readiness.

Audit log cần được bảo vệ khỏi sửa đổi và có retention phù hợp. Quyền xem audit log cũng cần được kiểm soát.

## 17. Checklist trước khi tạo checkpoint

Có thể dùng danh sách sau trong pipeline hoặc runbook:

### Dữ liệu

- [ ] Dataset được tạo mới bằng generator hoặc fixture đã phê duyệt.
- [ ] Không dùng bản sao raw của production database.
- [ ] Không chứa PII hoặc secret thật ngoài phạm vi đã phê duyệt.
- [ ] Fixture có quan hệ và phân phối đủ cho workload.
- [ ] Email, payment, webhook và message side effect được sandbox hóa.
- [ ] Log không chứa payload nhạy cảm.

### Credential và identity

- [ ] Checkpoint identity riêng biệt với build và runtime identity.
- [ ] Scope, audience, tenant và resource được giới hạn.
- [ ] Credential có TTL ngắn và khả năng revoke.
- [ ] Không có quyền production không cần thiết.
- [ ] Production secret chỉ được lấy sau restore nếu có thể.
- [ ] Refresh task và client được quản lý trong lifecycle.
- [ ] Không log token, password hoặc private key.

### Environment

- [ ] Database, broker, identity provider và storage thuộc sandbox.
- [ ] Network egress chặn production endpoint.
- [ ] Volume và mount không chứa dữ liệu production.
- [ ] Cấu hình environment được validate trước warm-up.
- [ ] CI runner không có quyền đọc secret production.

### Artifact

- [ ] Checkpoint image được phân loại và gắn metadata.
- [ ] Artifact được mã hóa và lưu trong restricted storage.
- [ ] Checksum hoặc signature được xác minh.
- [ ] Quyền đọc, restore và publish được phân tách.
- [ ] Retention và xóa artifact được định nghĩa.
- [ ] Restore test lấy runtime identity mới.

## 18. Quy trình triển khai đề xuất

Khi xây dựng checkpoint cho ứng dụng Java, có thể thực hiện theo trình tự sau:

**Bước 1 — Xác định mục tiêu và phạm vi.** Làm rõ image dùng cho CI, staging hay production deployment; xác định dữ liệu và dependency cần cho warm-up.

**Bước 2 — Tạo environment riêng.** Dùng database, broker, identity provider, storage và endpoint sandbox. Chặn network tới production.

**Bước 3 — Sinh synthetic data.** Tạo fixture mới có schema, quan hệ và phân phối đại diện. Tránh copy raw production data hoặc chỉ thay tên trên dữ liệu thật.

**Bước 4 — Cấp checkpoint credential.** Dùng identity riêng, scope nhỏ, audience đúng, TTL ngắn và quyền có thể revoke.

**Bước 5 — Khởi động và warm-up.** Chỉ chạy các đường xử lý an toàn với fixture và sandbox dependency. Theo dõi mọi network destination.

**Bước 6 — Chuẩn bị trước checkpoint.** Ngừng nhận công việc, drain thread, dừng refresh task, đóng client và xóa các secret buffer mà ứng dụng sở hữu.

**Bước 7 — Tạo và bảo vệ image.** Ghi metadata, checksum, mã hóa và lưu artifact vào restricted storage. Không publish vào registry công khai.

**Bước 8 — Revoke credential test.** Thu hồi hoặc để credential hết hạn theo chính sách; giữ audit evidence nhưng không ghi secret.

**Bước 9 — Restore bằng identity mới.** Cấp workload identity riêng cho instance, lấy secret hiện tại và tạo lại client. Xác minh không dùng credential checkpoint cũ.

**Bước 10 — Kiểm tra readiness và side effect.** Xác minh dependency, environment, dữ liệu và không có request production ngoài ý muốn.

**Bước 11 — Áp dụng retention.** Xóa fixture, log và checkpoint test khi hết hạn; kiểm tra cả bản sao và backup.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và trạng thái tiến trình được lưu.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): quản lý Resource qua beforeCheckpoint và afterRestore.
- [CRaC — Debugging](https://crac.org/reference/debugging/): điều tra trạng thái tài nguyên và lỗi checkpoint/restore.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): vòng đời, quyền truy cập và quản lý secret.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm khi lưu trữ.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): xác thực, session và credential.
- [OWASP Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html): phân quyền và bảo vệ database.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): xác thực và cấp quyền theo identity, resource và ngữ cảnh.
- [NIST SP 800-57 Part 1](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): quản lý vòng đời và bảo vệ key material.
- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): access token, scope và token response.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token và giảm rủi ro replay.


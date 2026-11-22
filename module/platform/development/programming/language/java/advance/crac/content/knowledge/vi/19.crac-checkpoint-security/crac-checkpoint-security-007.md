# Token, chứng chỉ, nonce và dữ liệu bảo mật không được dùng lại giữa các bản sao

CRaC có thể khôi phục cùng một checkpoint thành nhiều tiến trình hoặc nhiều replica. Mỗi replica bắt đầu từ một ảnh trạng thái bộ nhớ giống nhau, vì vậy các object đã được tạo trước checkpoint có thể xuất hiện với cùng giá trị ở nhiều bản sao. Điều này đặc biệt nhạy cảm với dữ liệu bảo mật: access token, refresh token, private key, session ID, nonce, bộ sinh số ngẫu nhiên, bộ đếm và trạng thái chống replay.

Nếu nhiều replica dùng lại cùng một token hoặc cùng trạng thái sinh nonce, hệ thống có thể mất khả năng phân biệt danh tính, gặp xung đột khi xoay vòng credential hoặc vi phạm yêu cầu mật mã. Một nonce bị dùng lại với cùng khóa mã hóa, chẳng hạn AES-GCM, có thể làm suy yếu nghiêm trọng tính bảo mật. Một refresh token dùng một lần có thể bị nhiều replica sử dụng đồng thời khiến một bản sao thành công còn các bản sao khác bị từ chối.

Vì vậy, checkpoint dùng để nhân bản cần được chuẩn bị như một trạng thái khởi tạo chung, còn danh tính và dữ liệu bảo mật riêng của từng replica phải được cấp mới hoặc xác minh sau restore. Mọi replica phải hoàn thành bước này trước khi nhận traffic hoặc thực hiện thao tác mật mã.

## 1. Vì sao restore nhiều replica tạo ra rủi ro bảo mật?

Giả sử ứng dụng khởi tạo một số object trước checkpoint:

~~~java
static final SecureRandom RANDOM = new SecureRandom();
static String accessToken;
static long nextRequestId = 1000;
static PrivateKey signingKey;
static byte[] lastNonce;
~~~

Nếu checkpoint được restore thành nhiều replica, trạng thái Java này có thể được sao chép cùng một giá trị:

~~~text
Checkpoint tại thời điểm T
   |
   +--------------------+--------------------+
   |                    |                    |
   v                    v                    v
Replica A            Replica B            Replica C
   |                    |                    |
   | accessToken=X      | accessToken=X      | accessToken=X
   | nextRequestId=1000 | nextRequestId=1000 | nextRequestId=1000
   | signingKey=K       | signingKey=K       | signingKey=K
   | RNG state=R        | RNG state=R        | RNG state=R
   |                    |                    |
   +--------------------+--------------------+
             Các giá trị có thể bị dùng lại
~~~

Đây là vấn đề khác với việc khởi động nhiều process độc lập. Khi mỗi process tự khởi động và lấy entropy hoặc credential mới, chúng có thể có trạng thái khác nhau. Khi nhiều process được tạo từ cùng một snapshot, không thể mặc định rằng mọi object trong heap sẽ tự trở nên độc lập.

Những nhóm dữ liệu cần xem xét:

- **Token và session:** access token, refresh token, session cookie, API token, OAuth state, CSRF token và thông tin xác thực ngắn hạn.
- **Danh tính mật mã:** private key, certificate identity, client certificate, signing key và key handle.
- **Nonce và trạng thái ngẫu nhiên:** nonce AEAD, IV, challenge, salt có yêu cầu riêng, trạng thái SecureRandom và PRNG tùy chỉnh.
- **Bộ đếm và ID:** sequence cục bộ, request ID, số thứ tự message, counter chống replay và generation number.
- **Trạng thái chống replay:** nonce đã sử dụng, cache token đã nhận, session ID và cửa sổ sequence.
- **Dữ liệu bảo mật đã cache:** credential, secret, key material, policy snapshot và quyền truy cập.

Không phải mọi giá trị đều bắt buộc phải khác nhau giữa các replica. Một truststore chứa public CA certificate có thể được chia sẻ. Một public key hoặc cấu hình không bí mật cũng có thể giống nhau. Điều cần phân biệt là dữ liệu dùng chung có chủ đích và dữ liệu đại diện cho danh tính, quyền sở hữu hoặc trạng thái mật mã riêng của từng replica.

## 2. Phân biệt dữ liệu có thể chia sẻ và dữ liệu phải cấp riêng

| Dữ liệu | Có thể chia sẻ giữa replica? | Chính sách phù hợp |
|---|---|---|
| Public CA certificate và trust bundle | Thường có | Chia sẻ theo chính sách trust; cập nhật khi CA thay đổi |
| Public key của issuer | Thường có | Chia sẻ để xác minh chữ ký, có version và rotation |
| Cấu hình không bí mật | Có thể | Dùng chung nếu cùng environment và cùng revision |
| Access token gắn với một workload/replica | Không nên dùng chung khi cần danh tính riêng | Cấp token mới sau restore cho từng replica |
| Refresh token có rotation hoặc single-use | Không | Không nhân bản token; dùng workload identity hoặc cơ chế phối hợp cấp token |
| Private key của từng replica | Không | Tạo hoặc lấy key riêng từ KMS/HSM/identity provider |
| Client certificate định danh replica | Nên riêng | Cấp certificate với subject/SAN hoặc workload identity riêng |
| Nonce dùng với cùng encryption key | Không được trùng theo yêu cầu của thuật toán | Cấp nonce độc lập hoặc bảo đảm bộ cấp phát không lặp |
| SecureRandom/PRNG state | Không nên tiếp tục dùng nguyên trạng giữa các bản sao | Tạo/reseed nguồn ngẫu nhiên riêng sau restore |
| Bộ đếm ID cục bộ | Không an toàn nếu clone cùng giá trị | Dùng sequence tập trung, range lease hoặc ID có node identity duy nhất |
| Secret cấu hình dùng chung có chủ đích | Có thể, nếu policy cho phép | Giới hạn quyền, bảo vệ checkpoint và rotation có kiểm soát |

Một chứng chỉ công khai và private key đi cùng nó có vai trò khác nhau. Public certificate thường được nhiều client dùng để xác minh một CA hoặc một service identity. Private key là bằng chứng sở hữu danh tính và phải được bảo vệ. Nếu mỗi replica cần được nhận diện độc lập, hãy cấp private key và certificate riêng cho từng replica.

Một số hệ thống cố ý dùng chung service identity cho toàn bộ replica. Cách đó có thể hợp lệ theo thiết kế, nhưng làm giảm khả năng quy trách nhiệm từng replica, tăng phạm vi ảnh hưởng khi key bị lộ và khiến rotation/revocation tác động tới tất cả bản sao. Không nên vô tình tạo ra service identity dùng chung chỉ vì private key đã nằm trong checkpoint.

## 3. Token: không nhân bản credential có vòng đời riêng

Token có thể mang quyền truy cập tới database, API, message broker hoặc dịch vụ nội bộ. Nếu token được lưu trong heap tại thời điểm checkpoint, nhiều replica có thể khôi phục cùng một chuỗi token.

Rủi ro phụ thuộc loại token:

- Access token có thể hợp lệ ở nhiều nơi cùng lúc, nhưng các replica sẽ dùng chung một danh tính và phạm vi quyền.
- Refresh token có thể được xoay vòng khi sử dụng; hai replica dùng cùng token có thể tạo race condition, làm token cũ bị vô hiệu hóa hoặc làm một replica mất khả năng refresh.
- Session token có thể bị ràng buộc với một kết nối, client hoặc session server-side đã hết hạn.
- Token có thời hạn có thể hết hạn trong lúc checkpoint; object String trong heap vẫn giữ giá trị nhưng server không còn chấp nhận.
- Token có thể chứa claim về audience, subject, scope hoặc instance ID không còn phù hợp với replica mới.

### Cấp token sau restore

Một mô hình thường dùng là mỗi replica xác thực bằng workload identity của môi trường triển khai, sau đó đổi danh tính đó lấy access token ngắn hạn:

~~~text
Restore checkpoint
       |
       v
Replica nhận workload identity riêng
       |
       v
Xác thực với identity provider
       |
       v
Đổi lấy access token mới
       |
       v
Tạo client bằng token mới
       |
       v
Health check và readiness
       |
       v
Nhận traffic
~~~

Workload identity có thể đến từ service account, cloud identity, SPIFFE/SPIRE hoặc cơ chế identity tương đương của nền tảng. Điểm quan trọng là mỗi replica được nhận diện theo một danh tính hoặc một phiên cấp phát riêng, không dựa vào token đã được lưu trong checkpoint.

Nếu hệ thống cần refresh token, hãy cấp token riêng cho replica hoặc sử dụng một dịch vụ token broker quản lý rotation. Không sao chép một refresh token có semantics single-use/rotation tới nhiều replica.

### Token phải có phạm vi và thời hạn phù hợp

Token mới sau restore vẫn cần tuân theo least privilege:

- Chỉ cấp audience cần thiết.
- Chỉ cấp scope và role mà replica cần.
- Dùng thời hạn ngắn phù hợp với khả năng refresh.
- Gắn subject hoặc workload identity có thể truy vết.
- Hỗ trợ revoke/rotation khi replica kết thúc hoặc bị nghi ngờ xâm nhập.
- Không ghi token vào log, metric label, exception hoặc manifest.

Không dùng một token có quyền quản trị rộng chỉ để đơn giản hóa bước restore. Nếu một chức năng cần quyền cao hơn, hãy dùng token riêng có phạm vi và thời gian tồn tại phù hợp.

## 4. Chứng chỉ, private key và danh tính TLS

TLS certificate bao gồm thông tin công khai về danh tính và chữ ký của CA. Private key tương ứng chứng minh bên trình bày certificate sở hữu danh tính đó.

Nếu checkpoint chứa private key của một replica rồi được restore thành nhiều bản sao, các replica có thể cùng dùng một private key. Khi kết nối mTLS hoặc ký dữ liệu, hệ thống bên ngoài không thể phân biệt các replica dựa trên key đó.

Các hệ quả có thể gồm:

- Không thể thu hồi quyền của một replica mà không ảnh hưởng các replica còn lại cùng dùng key.
- Log/audit ở hệ thống đích không xác định được bản sao nào thực hiện thao tác.
- Rotation có thể gây race giữa các replica đang dùng cùng certificate.
- Một replica bị xâm nhập có thể làm lộ danh tính chung của toàn bộ nhóm.
- Key có thể được dùng ở một host hoặc workload không còn được phép.

### Tạo danh tính TLS riêng sau restore

Với mô hình mỗi replica có identity riêng:

1. Replica nhận identity từ orchestrator hoặc workload identity provider.
2. Tạo key pair mới trong KMS/HSM hoặc trong phạm vi bảo vệ phù hợp.
3. Gửi CSR hoặc yêu cầu cấp identity theo giao thức của nhà cung cấp.
4. Nhận certificate có subject/SAN hoặc SPIFFE ID riêng.
5. Tạo TLS client/server context mới bằng key và certificate mới.
6. Chỉ mở kết nối sau khi kiểm tra chain, thời hạn và trust policy.
7. Khi replica kết thúc, thu hồi hoặc để certificate hết hạn theo chính sách.

Nếu dùng KMS/HSM, ưu tiên private key không exportable. Checkpoint có thể giữ handle hoặc object đại diện, nhưng handle đó vẫn cần được xác minh sau restore; có thể phải tạo lại session tới KMS/HSM. Không coi một Java object đại diện cho key là bằng chứng rằng quyền sử dụng key còn hiệu lực.

### Những thứ có thể chia sẻ

Public CA certificate, trust anchor và public key dùng để xác minh chữ ký thường có thể được chia sẻ giữa replica. Chúng không phải bí mật. Tuy nhiên, truststore vẫn cần versioning, integrity và rotation có kiểm soát.

Không chia sẻ CA signing key hoặc private key gốc trong checkpoint của ứng dụng. Những key này nên được giữ trong KMS/HSM hoặc hệ thống quản lý khóa chuyên dụng với quyền truy cập rất hạn chế.

## 5. Nonce và yêu cầu không lặp trong mật mã

Nonce là giá trị được dùng một lần hoặc cần duy nhất trong một phạm vi cụ thể của giao thức mật mã. Tùy thuật toán, nonce có thể không cần bí mật nhưng yêu cầu không lặp là bắt buộc.

Ví dụ, với AES-GCM, việc dùng lại cùng nonce với cùng key cho nhiều lần mã hóa có thể làm lộ thông tin và phá vỡ bảo đảm xác thực của chế độ mã hóa. Quy tắc an toàn cần được xác định theo thuật toán và thư viện, nhưng nguyên tắc cốt lõi là:

**Nếu thuật toán yêu cầu nonce duy nhất dưới cùng một key, tất cả replica cùng sử dụng key đó phải phối hợp để không phát sinh nonce trùng.**

Chỉ tạo một AtomicLong trong heap không đủ nếu tất cả replica được restore từ cùng một giá trị. Tương tự, lấy timestamp hoặc PID làm nonce không tạo ra bảo đảm duy nhất và khó kiểm soát khi replica khởi động đồng thời.

### Ba chiến lược phổ biến

**Dùng key riêng cho từng replica.** Mỗi replica nhận một encryption key riêng, do đó phạm vi nonce uniqueness được tách theo key. Vẫn cần nonce không lặp trong mỗi replica/key và không tái sử dụng key/nonce pair khi replica khởi tạo lại.

**Dùng bộ cấp phát nonce tập trung hoặc range lease.** Nếu nhiều replica buộc phải dùng chung key, cấp dải nonce không trùng từ một nguồn bền vững bên ngoài. Mỗi replica nhận một range hoặc prefix duy nhất sau restore. Bộ đếm và lease không được chỉ lưu trong heap của checkpoint.

**Dùng nonce ngẫu nhiên với CSPRNG và giới hạn khối lượng.** Một nguồn ngẫu nhiên mật mã có thể giảm xác suất trùng, nhưng cần đánh giá xác suất collision theo kích thước nonce và tổng số lần mã hóa dưới cùng key. Cách này không giải quyết được trạng thái PRNG bị clone nếu các replica tiếp tục cùng một trạng thái generator.

Nếu dùng AES-GCM, nhiều thư viện thường dùng nonce 96 bit. Kích thước này không có nghĩa có thể tùy ý tạo vô hạn nonce ngẫu nhiên dưới cùng một key. Cần theo giới hạn số lần mã hóa, xác suất va chạm và hướng dẫn của thư viện/chuẩn mật mã đang áp dụng.

### Không tự xây nonce từ thời gian

Những cách sau không đủ để bảo đảm duy nhất:

- System.currentTimeMillis() hoặc Instant.now().
- System.nanoTime().
- PID hoặc container hostname.
- AtomicLong được khôi phục cùng checkpoint.
- Một UUID được tạo trước checkpoint rồi sao chép sang mọi replica.
- Một PRNG tự viết hoặc seed bằng thời gian.

Có thể kết hợp nhiều thành phần trong một nonce format nếu giao thức quy định rõ, nhưng mỗi phần phải có tính duy nhất được chứng minh và được quản lý xuyên suốt vòng đời key.

## 6. SecureRandom và trạng thái PRNG sau restore

SecureRandom cung cấp số ngẫu nhiên mật mã theo provider được chọn. Nhưng object SecureRandom và trạng thái bên trong provider là trạng thái runtime. Nếu một instance được tạo trước checkpoint rồi được khôi phục thành nhiều replica, không nên giả định mỗi bản sao sẽ tự có một chuỗi số ngẫu nhiên độc lập.

Một mẫu dễ gây rủi ro:

~~~java
public final class NonceService {
    private static final SecureRandom RANDOM = new SecureRandom();

    public byte[] nextNonce() {
        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);
        return nonce;
    }
}
~~~

Static field này có thể được lưu trong trạng thái tiến trình. Sau restore nhiều lần, không nên dựa vào việc mỗi replica tự động có một trạng thái generator khác nhau.

### Tạo hoặc reseed nguồn ngẫu nhiên sau restore

Sau restore, tạo một SecureRandom instance mới từ provider/entropy source được tổ chức phê duyệt, hoặc gọi cơ chế reseed mà provider hỗ trợ theo tài liệu. Việc dùng **setSeed(System.nanoTime())** không phải cách reseed an toàn: timestamp không phải entropy mật mã và có thể giống nhau giữa các bản sao.

Ví dụ minh họa một Resource quản lý generator:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class NonceGenerator implements Resource {
    private volatile SecureRandom random = new SecureRandom();

    public NonceGenerator() {
        Core.getGlobalContext().register(this);
    }

    public byte[] nextGcmNonce() {
        SecureRandom source = random;
        if (source == null) {
            throw new IllegalStateException(
                    "Nonce generator is not ready");
        }

        byte[] nonce = new byte[12];
        source.nextBytes(nonce);
        return nonce;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Checkpoint coordinator phải drain mọi thao tác mã hóa trước
        // khi cho phép snapshot.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) {
        SecureRandom fresh = new SecureRandom();
        byte[] warmup = new byte[32];
        fresh.nextBytes(warmup);
        Arrays.fill(warmup, (byte) 0);
        random = fresh;
    }
}
~~~

Ví dụ thay thế generator trước khi ứng dụng được phép thực hiện mã hóa sau restore. Đoạn warmup chỉ khởi tạo hoạt động của provider; nó không phải một phép chứng minh độc lập rằng entropy đủ mạnh. Cần chọn provider và nguồn entropy được nền tảng phê duyệt, kiểm tra tài liệu provider về reseed và thử nghiệm trên đúng JDK/CRaC runtime.

Không cho phép request hoặc tác vụ mật mã chạy trước khi afterRestore hoàn tất. Nếu nhiều Resource độc lập có thể được gọi theo thứ tự không xác định, hãy dùng một readiness gate hoặc coordinator để đảm bảo NonceGenerator đã sẵn sàng trước khi mở các đường xử lý mật mã.

Nếu hệ thống dùng một bộ đếm nonce bền vững hoặc range lease, afterRestore phải xin range mới từ nguồn bên ngoài. Chỉ thay SecureRandom không thay thế được một cơ chế cấp phát nonce tập trung khi nhiều replica cùng dùng một key và giao thức yêu cầu uniqueness tuyệt đối.

## 7. Bộ đếm, request ID và trạng thái chống replay

Các giá trị như AtomicLong, sequence number, message offset hoặc replay cache cũng có thể bị nhân bản từ checkpoint.

Ví dụ, hai replica khôi phục cùng counter 5000 rồi cùng tạo ID tiếp theo. Nếu ID phải duy nhất toàn hệ thống, cả hai có thể phát ID 5001. Tình huống tương tự có thể làm sequence chống replay bị lùi hoặc khiến hai replica chấp nhận cùng một message.

Không dùng counter trong heap làm nguồn duy nhất cho ID toàn cục khi tiến trình có thể được clone.

Các lựa chọn thường dùng:

- Database sequence hoặc ID service có tính nguyên tử.
- Bộ cấp phát range bền vững, mỗi replica nhận một range mới sau restore.
- ID chứa node/replica identity duy nhất được cấp từ orchestrator hoặc coordinator.
- UUID/ULID hoặc định dạng ID ngẫu nhiên theo chuẩn đã đánh giá, với CSPRNG được khởi tạo đúng sau restore.
- Replay protection lưu ở kho chia sẻ bền vững hoặc dịch vụ xác thực trung tâm.

Đối với chống replay, không chỉ cần ID khác nhau. Server cần lưu hoặc kiểm tra nonce, timestamp, sequence hoặc token ID theo một chính sách có thời hạn và phạm vi rõ ràng. Nếu replay cache chỉ nằm trong heap rồi bị clone, nhiều replica có thể bắt đầu từ cùng một cửa sổ chống replay và đưa ra quyết định không nhất quán.

## 8. CRaC lifecycle cho dữ liệu bảo mật

Một Resource bảo mật có thể tham gia vào quy trình chuẩn bị và phục hồi:

~~~text
Trước checkpoint
    |
    v
Ngừng nhận request và drain tác vụ mật mã
    |
    v
Đóng client / giải phóng key handle
    |
    v
Loại bỏ token, nonce cache và identity tạm khỏi snapshot
    |
    v
Tạo checkpoint
    |
    v
Restore thành replica mới
    |
    v
Nhận identity riêng từ nền tảng
    |
    v
Cấp token / certificate / key handle mới
    |
    v
Khởi tạo SecureRandom hoặc nonce allocator mới
    |
    v
Kiểm tra quyền, thời hạn và dependency
    |
    v
Mở readiness
~~~

Không phải mọi secret đều cần xóa trước checkpoint. Một số secret cấu hình có thể được chia sẻ có chủ đích và cần thiết để khởi động. Nhưng token ngắn hạn, session, private key riêng của replica, nonce và trạng thái PRNG cần được đánh giá theo nguy cơ clone.

Nếu chọn xóa token hoặc key material trước checkpoint, phải có đường phục hồi cho trường hợp checkpoint bị hủy và tiến trình ban đầu tiếp tục chạy. Callback beforeCheckpoint không có nghĩa chắc chắn sẽ luôn được theo sau bởi afterRestore. Bộ điều phối checkpoint cần phát hiện checkpoint thất bại, yêu cầu cấp lại credential cho tiến trình hiện tại và chỉ mở admission khi phục hồi xong.

### Ví dụ Resource quản lý security context theo replica

Ví dụ dưới đây dùng các interface do ứng dụng định nghĩa. IdentityIssuer chịu trách nhiệm nhận identity riêng từ nền tảng, cấp token/key/certificate mới và tạo context bảo mật cho replica hiện tại.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ReplicaSecurityResource implements Resource {
    public interface WorkGate {
        void stopAdmissionAndDrain() throws Exception;
        void resumeAdmission() throws Exception;
    }

    public interface IdentityIssuer {
        ReplicaSecurityContext issueForCurrentReplica()
                throws Exception;
    }

    public interface ReplicaSecurityContext extends AutoCloseable {
        void verify() throws Exception;
        @Override
        void close() throws Exception;
    }

    private final WorkGate gate;
    private final IdentityIssuer issuer;
    private volatile ReplicaSecurityContext securityContext;

    public ReplicaSecurityResource(
            WorkGate gate,
            IdentityIssuer issuer) {
        this.gate = gate;
        this.issuer = issuer;
        Core.getGlobalContext().register(this);
    }

    public ReplicaSecurityContext current() {
        ReplicaSecurityContext current = securityContext;
        if (current == null) {
            throw new IllegalStateException(
                    "Replica security context is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        gate.stopAdmissionAndDrain();

        if (securityContext != null) {
            securityContext.close();
            securityContext = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        ReplicaSecurityContext fresh =
                issuer.issueForCurrentReplica();
        try {
            fresh.verify();
            securityContext = fresh;
            gate.resumeAdmission();
        } catch (Exception failure) {
            fresh.close();
            throw failure;
        }
    }

    // Được checkpoint coordinator gọi nếu checkpoint bị hủy và
    // tiến trình hiện tại tiếp tục chạy thay vì được restore.
    public synchronized void recoverAfterAbortedCheckpoint()
            throws Exception {
        if (securityContext == null) {
            ReplicaSecurityContext fresh =
                    issuer.issueForCurrentReplica();
            fresh.verify();
            securityContext = fresh;
        }
        gate.resumeAdmission();
    }
}
~~~

Đây là khung minh họa, không phải một IdentityIssuer có sẵn trong CRaC. Implementation thực tế cần:

- Lấy workload identity riêng của replica hiện tại.
- Xin token và certificate mới từ issuer.
- Tạo hoặc mở key handle riêng, ưu tiên KMS/HSM nếu phù hợp.
- Xác minh audience, scope, subject, thời hạn và trust chain.
- Đóng client và giải phóng handle cũ theo hợp đồng của thư viện.
- Không log giá trị secret hoặc private key.
- Chỉ mở admission sau khi toàn bộ security context đã sẵn sàng.

Nếu một bước phục hồi thất bại, không công bố context dở dang. Ứng dụng phải giữ readiness ở trạng thái false và retry hoặc chuyển sang cold start theo chính sách vận hành.

## 9. Cấp danh tính riêng cho replica

Danh tính replica cần đến từ nguồn có khả năng phân biệt từng instance. Có thể sử dụng:

- UID của Pod/container hoặc instance do orchestrator cấp.
- Workload identity của cloud provider.
- Service account có danh tính riêng theo workload.
- SPIFFE ID hoặc danh tính workload tương đương.
- Một identity broker cấp ID và credential khi replica đăng ký.

Không nên chỉ dùng hostname, PID hoặc timestamp để tạo identity. Những giá trị này có thể trùng, thay đổi hoặc bị tái sử dụng. Nếu dùng replica ID do orchestrator cấp, cần xác minh tính duy nhất trong phạm vi mà hệ thống bảo mật yêu cầu.

Một quy trình cấp danh tính có thể là:

1. Replica restore và vẫn ở trạng thái chưa ready.
2. Đọc workload identity từ môi trường được bảo vệ.
3. Xác thực với identity provider.
4. Nhận một identity/lease mới cho replica.
5. Cấp access token và certificate gắn với identity đó.
6. Tạo client mới và kiểm tra quyền.
7. Công bố replica identity cho telemetry/audit theo cách không chứa secret.

Nếu orchestrator có thể khởi tạo nhiều replica đồng thời từ cùng checkpoint, identity provider phải hỗ trợ cấp phát song song và phân biệt từng instance. Không dùng một file credential tĩnh được đóng gói trong image làm identity riêng cho mọi replica.

## 10. Xử lý token rotation và refresh đồng thời

Một lỗi thường gặp là nhiều replica cùng khôi phục một refresh token đã được cấp trước checkpoint. Nếu issuer dùng refresh token rotation, replica đầu tiên refresh có thể nhận token mới và làm token cũ mất hiệu lực. Replica thứ hai dùng token cũ có thể bị từ chối hoặc bị coi là hành vi bất thường.

Các giải pháp:

- Cấp refresh credential riêng cho từng replica.
- Dùng workload identity để mỗi replica tự đổi lấy access token mới.
- Dùng token broker quản lý refresh tập trung và cấp access token riêng.
- Dùng distributed lock/lease nếu bắt buộc phải chia sẻ một credential có rotation; tuy nhiên phải xử lý lease expiry và kết quả refresh không rõ.
- Không đưa token đã xoay vòng vào checkpoint artifact.

Không nên để tất cả replica đồng loạt refresh một token dùng chung mà không có coordination. Điều đó có thể tạo thundering herd, race condition và revoke cascade.

## 11. Bảo vệ checkpoint artifact chứa dữ liệu bảo mật

Ngay cả khi ứng dụng dự định thay token và key sau restore, checkpoint image có thể vẫn chứa bản sao dữ liệu trước checkpoint. Checkpoint có thể bao gồm heap, static field, buffer, object graph, credential cache và một số trạng thái runtime.

Hãy bảo vệ checkpoint như một artifact nhạy cảm:

- Mã hóa khi lưu trữ và truyền tải bằng cơ chế được tổ chức phê duyệt.
- Giới hạn quyền đọc, ghi, tải xuống và sao chép checkpoint.
- Chỉ cấp quyền restore cho workload và pipeline được xác thực.
- Lưu audit log cho việc tạo, tải, giải mã, restore và xóa artifact.
- Đặt thời hạn lưu trữ và quy trình xóa an toàn.
- Không ghi secret, token, private key hoặc nonce nhạy cảm vào manifest, log hay tên file.
- Không đưa checkpoint lên kho artifact công khai.

Mã hóa artifact không thay thế việc cấp lại identity sau restore. Nếu nhiều replica giải mã cùng checkpoint, chúng vẫn có thể nhận cùng token hoặc key cũ. Mã hóa chỉ bảo vệ dữ liệu khi lưu trữ và truyền tải; uniqueness và freshness cần được giải quyết ở lifecycle của ứng dụng.

## 12. Kiểm thử chống tái sử dụng giữa các replica

Kiểm thử cần tạo nhiều replica từ cùng một checkpoint, không chỉ restore một lần rồi kiểm tra ứng dụng hoạt động.

Các tình huống nên kiểm tra:

- Restore cùng checkpoint đồng thời thành nhiều replica và xác nhận mỗi replica nhận identity khác nhau.
- So sánh subject/SAN hoặc workload ID của certificate từng replica.
- Xác nhận private key handle hoặc key ID riêng nếu policy yêu cầu per-replica key.
- Xác nhận access token có subject, audience, scope và token ID phù hợp với từng replica.
- Xác nhận refresh token không bị chia sẻ hoặc không xảy ra race khi rotation.
- Sinh số lượng nonce đại diện trên từng replica và kiểm tra uniqueness trong phạm vi key dùng chung.
- Nếu dùng key riêng, xác nhận key ID khác nhau và nonce không lặp trong mỗi key.
- Restore nhiều lần từ cùng checkpoint để phát hiện PRNG sequence hoặc counter bị lặp.
- Kiểm tra replay cache và sequence chống replay không bị lùi hoặc nhân bản sai.
- Làm secret provider hoặc identity provider không sẵn sàng để xác nhận replica chưa mở readiness.
- Kiểm tra checkpoint image, log và manifest không làm lộ secret.
- Kiểm tra checkpoint bị hủy sau beforeCheckpoint và xác nhận tiến trình ban đầu có thể lấy lại credential trước khi nhận traffic.

Không nên in nonce, token hoặc key ra log để so sánh. Dùng fingerprint, key ID, token metadata không nhạy cảm hoặc kết quả kiểm tra phía issuer. Với nonce, có thể kiểm tra collision trong môi trường thử nghiệm và kiểm tra chính sách cấp phát; một bài test hữu hạn không chứng minh tuyệt đối uniqueness cho mọi lần chạy.

## 13. Những hiểu nhầm thường gặp

**“Mỗi container restore tự có SecureRandom state khác nhau.”**

Không nên giả định như vậy. Object và trạng thái generator có thể nằm trong checkpoint. Tạo/reseed nguồn ngẫu nhiên riêng sau restore và kiểm tra provider/runtime thực tế.

**“UUID hoặc timestamp luôn đủ để tạo nonce duy nhất.”**

Không phải mọi UUID hoặc timestamp đều đáp ứng yêu cầu của thuật toán. Dùng nonce format và nguồn cấp phát đã được thiết kế cho đúng giao thức mật mã.

**“Token vẫn còn hạn nên có thể dùng chung.”**

Token có thể hợp lệ về thời gian nhưng vẫn mang danh tính chung, bị ràng buộc với một session hoặc có semantics rotation. Cấp credential riêng nếu replica cần identity riêng.

**“Chỉ private key cần khác nhau; refresh token có thể dùng chung.”**

Refresh token có thể single-use hoặc rotation. Nhiều replica dùng cùng token có thể làm vô hiệu credential của nhau. Phải hiểu semantics của issuer.

**“Certificate là dữ liệu công khai nên có thể sao chép tất cả.”**

Certificate công khai có thể chia sẻ, nhưng private key tương ứng là bí mật. Nếu certificate định danh replica, nên cấp identity và key riêng cho mỗi replica.

**“Đổi token sau restore là đủ.”**

Nonce allocator, PRNG state, request counter, replay cache, key handle và certificate cũng có thể bị clone. Cần xem toàn bộ dữ liệu bảo mật và trạng thái chống replay.

**“Mã hóa checkpoint bảo đảm các replica độc lập.”**

Mã hóa bảo vệ artifact khi lưu trữ/truyền tải. Nó không làm các object trong heap tự khác nhau sau khi cùng được giải mã và restore.

**“Có thể xóa credential trong beforeCheckpoint mà không cần xử lý gì thêm.”**

Nếu checkpoint thất bại và tiến trình hiện tại tiếp tục, credential đã xóa có thể cần được cấp lại. Phải có đường phục hồi cho checkpoint abort.

## 14. Quy trình triển khai đề xuất

Một quy trình thực tế có thể thực hiện theo thứ tự:

1. Liệt kê toàn bộ token, secret, key, certificate, nonce generator, counter và replay state có thể nằm trong heap.
2. Phân loại dữ liệu nào được chia sẻ có chủ đích và dữ liệu nào phải riêng theo replica.
3. Thiết kế workload identity hoặc identity broker để cấp danh tính riêng sau restore.
4. Cấp token ngắn hạn và certificate/private key riêng theo policy; giữ key gốc trong KMS/HSM.
5. Dùng SecureRandom provider được phê duyệt và khởi tạo/reseed lại sau restore.
6. Nếu dùng chung encryption key, triển khai nonce allocator không bị clone, chẳng hạn range lease hoặc dịch vụ cấp phát bền vững.
7. Dừng admission và drain mọi thao tác mật mã trước checkpoint.
8. Loại bỏ hoặc đánh dấu không hợp lệ các credential và trạng thái riêng cần cấp lại trong snapshot.
9. Sau restore, tạo security context mới, kiểm tra key/token/certificate và khởi động lại client.
10. Chỉ mở readiness khi identity và tài nguyên bảo mật đã sẵn sàng.
11. Kiểm thử đồng thời nhiều replica từ cùng checkpoint và các tình huống rotation/failure.
12. Bảo vệ checkpoint artifact, manifest, log và quy trình restore.

## 15. Kết luận

Khi một checkpoint được nhân bản thành nhiều replica, mọi dữ liệu bảo mật nằm trong heap có nguy cơ bị sao chép cùng giá trị. Token, refresh token, private key, certificate identity, nonce generator, counter và replay state cần được đánh giá theo yêu cầu uniqueness, freshness và danh tính.

Hãy cấp identity và credential riêng sau restore, tạo hoặc mở key handle riêng, khởi tạo lại nguồn ngẫu nhiên từ entropy được phê duyệt và dùng nonce allocator có bảo đảm không lặp trong phạm vi key. Public trust material có thể được chia sẻ khi phù hợp, nhưng private key và credential riêng không nên được nhân bản ngoài chủ đích. Chỉ mở traffic sau khi từng replica đã hoàn tất phục hồi bảo mật; đồng thời bảo vệ checkpoint image vì nó có thể chứa bản sao secret trước khi được làm mới.

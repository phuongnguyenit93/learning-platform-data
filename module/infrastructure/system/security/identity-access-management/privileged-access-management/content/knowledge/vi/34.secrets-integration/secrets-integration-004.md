# Secret injection

## 1. Mục tiêu và phạm vi

Secret injection là cách đưa bí mật đến workload vào thời điểm chạy, để ứng dụng sử dụng được credential mà không phải chứa credential đó trong mã nguồn, image, manifest công khai hoặc tham số dòng lệnh.

Trong module Privileged Access Management (PAM), secret injection nối chính sách cấp quyền với hành vi sử dụng quyền. Vault có thể bảo vệ mật khẩu quản trị rất tốt, nhưng lợi ích đó giảm mạnh nếu pipeline sao chép mật khẩu vào log, container lưu nó vĩnh viễn hoặc ứng dụng tiếp tục dùng credential sau khi quyền đã bị thu hồi.

Sau bài này, bạn cần có thể:

- Phân biệt secret injection với lưu trữ secret, masking và mã hóa.
- Chọn cách cấp secret phù hợp cho ứng dụng Java, container và tác vụ tự động.
- Thiết kế luồng cấp secret dựa trên workload identity và quyền tối thiểu.
- Xử lý rotation, hết hạn, mất kết nối và thu hồi mà không tạo đường vòng đặc quyền.
- Kiểm tra việc cấp secret bằng bằng chứng truy cập, thay vì ghi giá trị bí mật vào log.

Ví dụ xuyên suốt là dịch vụ Java `checkout-api` cần kết nối cơ sở dữ liệu để xử lý đơn hàng. Dịch vụ chỉ cần quyền ứng dụng trên một tập bảng xác định, không cần tài khoản `root`, quyền quản trị database hay quyền đọc mọi secret trong vault.

## 2. Secret injection giải quyết vấn đề gì?

### 2.1. Secret cần đến đúng nơi, đúng lúc

Một workload muốn gọi hệ thống khác thường cần một trong các dạng thông tin sau:

- Mật khẩu của tài khoản dịch vụ.
- API token hoặc access token có thời hạn.
- Private key và chứng thư để xác thực máy.
- Cặp username/password được tạo động.
- Credential tạm thời để thực hiện một thao tác đặc quyền đã được phê duyệt.

Nếu đặt mật khẩu trong mã nguồn, người có quyền đọc repository có thể lấy được nó. Nếu đưa vào image, người kéo image hoặc đọc lớp image có thể khôi phục credential ngay cả khi một lớp sau đã xóa file. Nếu truyền qua tham số dòng lệnh, giá trị có thể xuất hiện trong danh sách tiến trình, lịch sử shell hoặc bản ghi tác vụ.

Secret injection chuyển việc cung cấp credential sang giai đoạn chạy. Một thành phần được tin cậy xác thực workload, kiểm tra quyền, lấy hoặc phát hành secret, rồi cấp secret qua một kênh giới hạn phạm vi.

Điểm quan trọng là giảm số bản sao và giảm thời gian tồn tại. Đưa secret vào runtime không làm nó biến mất: ứng dụng vẫn có thể phải giữ secret trong bộ nhớ và gửi credential đến hệ thống đích khi xác thực.

### 2.2. Những khái niệm dễ nhầm

| Khái niệm | Trả lời câu hỏi | Không tự bảo đảm |
|---|---|---|
| Secret storage | Secret được lưu và bảo vệ ở đâu? | Ứng dụng nhận secret bằng kênh nào |
| Secret injection | Secret đến workload như thế nào? | Secret có quyền tối thiểu hay không |
| Secret rotation | Khi nào và bằng cách nào thay credential? | Ứng dụng đã dùng phiên bản mới |
| Secret masking | Giá trị nào bị che trong đầu ra? | Giá trị chưa từng bị lộ qua kênh khác |
| Encryption | Dữ liệu được mã hóa trong trạng thái hoặc đường truyền nào? | Người được phép giải mã sử dụng đúng mục đích |
| Workload identity | Hệ thống nhận biết workload nào đang yêu cầu? | Workload được phép lấy mọi secret |

Một pipeline hiển thị `****` vẫn có thể truyền secret cho plugin không đáng tin. Một volume được mã hóa vẫn để tiến trình có quyền đọc volume nhìn thấy bản rõ. Cần đánh giá cả luồng sử dụng, không chỉ cơ chế lưu.

## 3. Luồng tin cậy từ identity đến hệ thống đích

Một thiết kế phổ biến có sáu thành phần:

1. Workload thực hiện nghiệp vụ.
2. Identity provider hoặc nền tảng thực thi cung cấp danh tính workload.
3. Secret broker, agent hoặc SDK xác thực với vault.
4. Policy xác định workload được đọc đường dẫn hoặc xin loại credential nào.
5. Kênh injection chuyển credential đến ứng dụng.
6. Hệ thống đích kiểm tra credential và quyền tương ứng.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng Java
    participant I as Injector hoặc agent
    participant V as Vault / secret service
    participant D as Database
    I->>V: Xác thực bằng workload identity
    V->>V: Kiểm tra policy và phạm vi môi trường
    V-->>I: Credential cùng version / lease / expiry
    I-->>A: Cấp qua file hoặc kênh runtime
    A->>D: Mở kết nối bằng credential được cấp
    D-->>A: Kết nối theo quyền của tài khoản
    Note over I,V: Renewal và rotation cần luồng riêng
    Note over A,D: Kết nối đã mở có thể sống lâu hơn credential
~~~

Mỗi mũi tên là một ranh giới tin cậy cần xem xét. TLS bảo vệ đường truyền đến vault, nhưng không kiểm soát được việc agent đặt file cho mọi tiến trình đọc. File permission đúng cũng không ngăn được ứng dụng đã bị chiếm quyền sử dụng credential mà chính nó được phép đọc.

### 3.1. Tránh vòng lặp “cần secret để lấy secret”

Một lỗi thiết kế thường gặp là loại mật khẩu database khỏi cấu hình, rồi thay bằng vault token cố định có quyền rộng. Khi đó chỉ chuyển vị trí của bí mật có rủi ro lớn nhất.

Ưu tiên xác thực dựa trên danh tính nền tảng:

- Service account hoặc danh tính được ràng buộc với workload.
- Danh tính máy được quản lý và có vòng đời rõ ràng.
- Chứng thư hoặc token ngắn hạn được phát hành theo cơ chế tin cậy đã thiết lập.
- Federation với điều kiện cụ thể về issuer, audience, môi trường và workload.

Không có cơ chế nào tạo ra niềm tin từ hư không. Cần biết ai phát hành danh tính, ai có quyền gán danh tính đó cho workload, token tồn tại bao lâu và thành phần nào có thể giả mạo hoặc đọc token.

### 3.2. Ánh xạ quyền theo workload

Đối với `checkout-api` chạy ở production, policy nên thể hiện được các giới hạn sau:

- Chỉ xin credential cho role database của `checkout-api`.
- Không đọc credential của `reporting-api` hoặc môi trường khác.
- Không quản trị policy vault, không liệt kê mọi đường dẫn nếu không cần.
- Không được cấp credential có TTL vượt giới hạn đã phê duyệt.
- Không dùng lại danh tính của pipeline deploy cho ứng dụng đang chạy.

Role được phép phát hành credential phải tương ứng với quyền thực tế tại database. Policy vault hẹp nhưng database account có quyền quản trị vẫn tạo ra đặc quyền quá mức.

## 4. Chọn kênh injection

Không có một cách cấp secret tối ưu cho mọi hệ thống. Hãy chọn theo khả năng reload của ứng dụng, thời hạn credential, ranh giới tiến trình và mô hình vận hành.

| Cách cấp | Thích hợp khi | Điểm cần kiểm soát |
|---|---|---|
| Biến môi trường | Ứng dụng cũ chỉ nhận cấu hình lúc khởi động | Có thể bị kế thừa bởi tiến trình con; thường cần restart để thay giá trị |
| File được mount hoặc render | Ứng dụng đọc được file và có thể reload | Quyền đọc, cập nhật nguyên tử, tránh bản sao và file tạm |
| SDK gọi secret service | Ứng dụng quản lý được xác thực, cache và refresh | Tăng trách nhiệm trong code; phải xử lý dependency và lỗi truy cập |
| Agent hoặc sidecar | Muốn tách phần tích hợp vault khỏi ứng dụng | Agent trở thành thành phần có quyền nhạy cảm; cần quản lý vòng đời |
| File descriptor hoặc kênh IPC | Workload và nền tảng có hỗ trợ chuyên biệt | Cần xác thực peer, framing, giới hạn truy cập và xử lý reconnect |
| Proxy thực hiện xác thực thay ứng dụng | Giao thức và sản phẩm hỗ trợ mô hình này | Proxy mang đặc quyền, phải ràng buộc identity và ngăn bypass |

Agent là một thành phần thực hiện injection, không phải một kênh độc lập hoàn toàn: agent thường ghi file, phục vụ socket hoặc cung cấp proxy. SDK cũng có thể dùng cache và giữ secret trong bộ nhớ.

### 4.1. Biến môi trường

Ưu điểm là dễ tích hợp với ứng dụng cũ. Tuy nhiên, biến môi trường có thể bị lộ qua:

- Chẩn đoán môi trường, crash report hoặc endpoint debug.
- Tiến trình con được tạo mà không lọc môi trường.
- Công cụ quản trị hoặc cơ chế kiểm tra tiến trình, tùy quyền hệ điều hành.
- Shell script dùng `set -x`, lệnh `env`, `printenv` hoặc in cấu hình.
- Hệ thống thu thập hỗ trợ kỹ thuật sao chép môi trường vào gói diagnostic.

Không phải mọi người dùng trên máy đều đọc được môi trường của mọi tiến trình. Khả năng này phụ thuộc hệ điều hành, quyền truy cập, namespace và cấu hình bảo vệ. Dù vậy, không nên xem biến môi trường là vùng lưu trữ bí mật chuyên dụng.

Biến môi trường của một tiến trình đang chạy không tự đổi khi nguồn secret đổi. Đối với mô hình này, rotation thường cần tạo tiến trình mới với giá trị mới và thay thế tiến trình cũ có kiểm soát.

### 4.2. File runtime

File phù hợp khi ứng dụng có thể đọc credential từ đường dẫn như `/run/secrets/db/password`. Thiết kế nên bảo đảm:

- Chỉ các UID/GID cần thiết có quyền đọc.
- Ứng dụng không có quyền sửa nguồn secret nếu không cần.
- Không đặt trong thư mục được phục vụ qua HTTP hoặc đồng bộ ra ngoài.
- Không sao chép vào cấu hình sinh sẵn, workspace, artifact hoặc image.
- Không để công cụ backup và log collector tự động thu thập.
- Không ghi credential vào tên file.

Nếu ghi đè trực tiếp một file, ứng dụng có thể đọc đúng lúc file mới chỉ được ghi một phần. Injector nên chuẩn bị phiên bản hoàn chỉnh rồi công bố nguyên tử bằng cơ chế phù hợp của nền tảng, chẳng hạn thay file bằng rename trên cùng filesystem.

Cần xác minh filesystem, volume driver và cơ chế mount thực tế có hỗ trợ tính chất mong muốn. Không suy ra rằng mọi cách ghi file đều nguyên tử.

File nằm trên bộ nhớ tạm có thể giảm việc ghi xuống đĩa, nhưng không bảo đảm dữ liệu chưa bao giờ xuất hiện ở swap, dump hoặc snapshot. Đánh giá cả nền tảng bên dưới.

### 4.3. SDK và cache trong ứng dụng

Ứng dụng gọi trực tiếp secret service có thể chủ động lấy credential mới, xử lý TTL và quan sát lỗi. Đổi lại, nó phải quản lý:

- Xác thực workload và refresh danh tính.
- Timeout, retry có giới hạn và backoff.
- Cache theo version hoặc lease, với thời hạn sử dụng rõ ràng.
- Tránh hàng trăm luồng đồng thời cùng gọi vault khi cache hết hạn.
- Không ghi payload request/response chứa secret.
- Thu hồi và hủy credential theo vòng đời được hỗ trợ.

Một cache không có thời hạn có thể biến credential ngắn hạn thành bí mật được sử dụng vô thời hạn trong ứng dụng, hoặc khiến ứng dụng liên tục dùng credential đã bị hệ thống đích từ chối.

### 4.4. Agent khởi tạo và agent chạy liên tục

Thành phần khởi tạo chỉ chuẩn bị secret trước khi ứng dụng chạy. Sau khi kết thúc, nó không còn thực hiện renewal hay cập nhật file.

Agent chạy liên tục có thể theo dõi lease và cập nhật secret, nhưng cần có cơ chế báo cho ứng dụng biết lúc nào dữ liệu mới sẵn sàng. Việc agent cập nhật file không tự động thay password đang nằm trong connection pool của ứng dụng.

Trong một số thiết kế, ứng dụng có thể mất readiness khi credential sắp hết hạn mà không có bản thay thế. Đó là quyết định vận hành cần chủ động thiết kế, không phải chức năng mặc định của mọi injector.

## 5. Ví dụ Java: đọc mật khẩu từ file được cấp lúc chạy

Giả sử ứng dụng nhận đường dẫn file qua biến `DB_PASSWORD_FILE`. Biến này chứa đường dẫn, không chứa mật khẩu. File được tạo hoặc mount bởi nền tảng trước khi ứng dụng khởi tạo database pool.

Ví dụ sau sử dụng Java 17 trở lên. Nó đọc tối đa 4.097 byte để từ chối file quá lớn, giải mã UTF-8 nghiêm ngặt và không tự ý loại bỏ khoảng trắng.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

final class InjectedPassword {
    private static final int MAX_BYTES = 4096;

    private InjectedPassword() {
    }

    static String read(Path path) throws IOException {
        byte[] bytes;
        try (InputStream input = Files.newInputStream(path)) {
            bytes = input.readNBytes(MAX_BYTES + 1);
        }

        try {
            if (bytes.length == 0 || bytes.length > MAX_BYTES) {
                throw new IOException("Invalid injected password length");
            }

            String value;
            try {
                value = StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(bytes))
                        .toString();
            } catch (CharacterCodingException ex) {
                throw new IOException("Injected password is not valid UTF-8");
            }

            // Hợp đồng của ví dụ: mật khẩu UTF-8, không CR/LF/NUL.
            if (value.indexOf('\r') >= 0
                    || value.indexOf('\n') >= 0
                    || value.indexOf('\0') >= 0) {
                throw new IOException("Invalid injected password format");
            }
            return value;
        } finally {
            Arrays.fill(bytes, (byte) 0);
        }
    }
}
~~~

Ứng dụng có thể gọi ở bước tạo pool:

~~~java
String passwordFile = System.getenv("DB_PASSWORD_FILE");
if (passwordFile == null || passwordFile.isBlank()) {
    throw new IllegalStateException("DB password file is not configured");
}

String dbPassword = InjectedPassword.read(Path.of(passwordFile));

// Truyền dbPassword vào API cấu hình DataSource/pool cụ thể.
// Không nối password vào JDBC URL, log hoặc thông báo lỗi.
~~~

### 5.1. Những giới hạn cần hiểu từ ví dụ

Đoạn code không phải một secret manager hoàn chỉnh. Nó chỉ minh họa ranh giới giữa dữ liệu được cấp và ứng dụng tiêu thụ.

- Giới hạn 4.096 byte là hợp đồng của ứng dụng mẫu, không phải chuẩn chung cho mọi loại secret.
- `trim()` hoặc `strip()` có thể làm thay đổi mật khẩu hợp lệ có khoảng trắng đầu/cuối.
- Nếu nền tảng cố ý thêm một newline, phải thống nhất hợp đồng và xử lý chính xác định dạng đó; không tùy tiện sửa mọi secret.
- Xóa mảng byte là biện pháp giảm bản sao còn tồn tại, không bảo đảm xóa toàn bộ dấu vết khỏi bộ nhớ.
- `String` là bất biến; không thể cam kết xóa bản rõ đã được tạo trong JVM. Driver, thư viện pool và JVM có thể tạo thêm bản sao.
- Đường dẫn phải đến từ cấu hình được tin cậy. Không nhận đường dẫn từ request của người dùng để đọc file tùy ý.
- Lỗi được báo không chứa giá trị secret; hệ thống log vẫn phải kiểm soát exception của driver và thư viện liên quan.

Một số API nhận `char[]` và cho phép giảm thời gian tồn tại của dữ liệu hơn so với `String`. Tuy nhiên, khả năng xóa bộ nhớ phụ thuộc toàn bộ chuỗi thư viện; không nên tuyên bố “zero secret in memory” chỉ vì một lớp dùng mảng ký tự.

### 5.2. Đọc một lần hay đọc lại?

Đọc lúc khởi động phù hợp với ứng dụng sử dụng credential tĩnh và triển khai rolling restart khi rotation. Với credential có TTL ngắn, cần thiết kế refresh chủ động.

Không nên đọc file ở mỗi SQL query. Cách này vừa tăng I/O vừa không thay được thông tin xác thực của kết nối đã mở.

Một mô hình thực tế là:

1. Bộ điều khiển credential phát hiện phiên bản mới.
2. Đọc trọn snapshot credential mới.
3. Tạo pool hoặc tập kết nối mới.
4. Kiểm tra kết nối thử bằng quyền ứng dụng tối thiểu.
5. Chuyển lưu lượng sang pool mới.
6. Drain pool cũ trong thời hạn giới hạn.
7. Đóng pool cũ và hoàn tất thu hồi theo chính sách.

Nếu username và password cùng thay đổi, cần coi chúng là một snapshot nhất quán. Đọc hai file vào hai thời điểm có thể ghép username của phiên bản cũ với password của phiên bản mới. Có thể dùng một tài liệu credential được công bố nguyên tử, hoặc cơ chế versioning bảo đảm đọc đúng cùng phiên bản.

## 6. Ví dụ Kubernetes: mount secret thành file

Ví dụ sau dùng đối tượng Kubernetes Secret đã được cấp sẵn để minh họa cách ứng dụng nhận file. Nó không minh họa tích hợp vault hoặc tự động phát hành dynamic credential.

Giả định Secret tên `checkout-db-runtime` có key `password`, và ứng dụng có quyền đọc bằng group đã cấu hình.

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: checkout-api
spec:
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: app
      image: registry.example/checkout-api:example
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      env:
        - name: DB_PASSWORD_FILE
          value: /run/secrets/db/password
      volumeMounts:
        - name: database-secret
          mountPath: /run/secrets/db
          readOnly: true
        - name: temp
          mountPath: /tmp
  volumes:
    - name: database-secret
      secret:
        secretName: checkout-db-runtime
        defaultMode: 0440
        items:
          - key: password
            path: password
    - name: temp
      emptyDir: {}
~~~

Image trong ví dụ là tên minh họa. Khi triển khai thực tế cần image đã kiểm soát nguồn gốc, phiên bản và quyền chạy. Xác minh quyền file trên container thực tế, kể cả ảnh hưởng của nền tảng bảo mật và loại volume.

### 6.1. Cơ chế này bảo đảm điều gì?

Ứng dụng đọc mật khẩu qua file chỉ đọc. Nó không cần tự gọi Kubernetes API để lấy Secret; vì vậy ví dụ tắt việc tự động mount token service account cho Pod. Kubelet và cơ chế cấp volume của nền tảng vẫn tham gia đưa Secret tới workload.

Đối với tích hợp dùng CSI driver, federation hoặc agent, yêu cầu identity và token có thể khác. Không sao chép tùy chọn tắt token sang mọi kiến trúc mà bỏ qua yêu cầu của provider.

`readOnly: true` hạn chế việc ứng dụng sửa volume qua mount đó. Nó không ngăn ứng dụng đọc file rồi gửi giá trị ra ngoài. Cần bổ sung kiểm soát mạng, quyền thực thi, giám sát và giới hạn quyền của credential.

### 6.2. Những điều không được suy diễn

- Giá trị base64 trong Kubernetes Secret không đồng nghĩa với mã hóa.
- Cần cấu hình và kiểm tra bảo vệ dữ liệu lưu trữ, quyền API và truy cập tới node.
- Quyền tạo Pod trong một namespace có thể cho phép một chủ thể tạo workload dùng Secret của namespace đó, tùy admission policy và các kiểm soát liên quan. Chỉ hạn chế quyền `get Secret` là chưa đủ.
- Secret mount được cập nhật theo cơ chế đồng bộ của nền tảng, không phải cam kết cập nhật tức thời.
- Mount bằng `subPath` không nhận cập nhật Secret theo cùng cơ chế như mount volume Secret thông thường.
- Khi đường dẫn được thay bằng phiên bản mới, ứng dụng giữ file descriptor cũ có thể vẫn đọc nội dung cũ. Cần mở lại đường dẫn để nhận bản mới.
- Một ứng dụng đã đọc password vào bộ nhớ hoặc pool không tự reload chỉ vì file đã thay đổi.
- Namespace giúp tổ chức và áp dụng policy, nhưng không thay thế đánh giá đầy đủ về ranh giới cách ly và quyền quản trị cluster.

Đừng kiểm tra cơ chế mount bằng cách chạy `cat` rồi chụp màn hình secret production. Có thể kiểm tra owner, mode, thời điểm thay đổi, version không nhạy cảm và một thao tác xác thực đã được giới hạn.

## 7. Injection phải đi cùng rotation và TTL

### 7.1. Phân biệt các mốc thời gian

Với dynamic credential, cần phân biệt ít nhất bốn mốc:

- Thời điểm phát hành credential.
- Thời điểm credential hoặc lease hết hạn.
- Thời điểm ứng dụng ngừng tạo kết nối mới bằng bản cũ.
- Thời điểm hệ thống đích ngừng chấp nhận hoặc kết thúc việc sử dụng bản cũ.

Bốn mốc này không nhất thiết trùng nhau. Một token hết hạn có thể khiến request mới bị từ chối, còn một kết nối database đã xác thực có thể tiếp tục hoạt động tùy hệ thống và cách thu hồi.

Renew lease cũng không luôn đồng nghĩa với cấp một password mới. Phải phân biệt gia hạn quyền dùng credential hiện tại với rotation thay giá trị credential.

### 7.2. Lập kế hoạch refresh trước hạn

Giả sử credential có TTL 30 phút. Một thiết kế có thể chủ động refresh khi còn 10 phút, thử lại có backoff và chuyển sang credential mới trước khi bản cũ hết hạn.

Các con số trên là ví dụ, không phải công thức bắt buộc. Khoảng đệm cần đủ cho:

- Sai lệch đồng hồ trong giới hạn cho phép.
- Timeout và retry.
- Thời gian cập nhật kênh injection.
- Thời gian tạo pool và kiểm tra kết nối.
- Rolling deployment hoặc drain kết nối cũ.
- Sự cố ngắn hạn của vault hoặc hệ thống đích.

Thêm jitter giúp tránh việc mọi replica cùng refresh tại một thời điểm. Vẫn cần giới hạn số lần retry và lưu lượng đến vault.

### 7.3. Rotation không đồng nghĩa với thu hồi hoàn chỉnh

Một chu trình rotation an toàn thường gồm:

1. Tạo hoặc nhận credential mới.
2. Cấp phiên bản mới đến đúng workload.
3. Xác minh workload đã tiêu thụ phiên bản mới.
4. Ngăn phát sinh sử dụng bản cũ.
5. Thu hồi credential cũ và xử lý phiên/kết nối còn tồn tại theo khả năng hệ thống.
6. Lưu bằng chứng chuyển đổi và kết quả thu hồi.

Nếu hệ thống đích chỉ hỗ trợ một password hoạt động tại một thời điểm, thay password có thể làm gián đoạn kết nối mới trong lúc consumer chưa nhận được bản mới. Cần chọn chiến lược phù hợp: hai tài khoản luân phiên, cơ chế chồng lấn có kiểm soát nếu sản phẩm hỗ trợ, hoặc cửa sổ bảo trì.

Không tự mặc định luôn có khoảng chồng lấn. Khả năng đó phụ thuộc loại credential và hệ thống đích.

## 8. Xử lý lỗi mà không tạo cửa hậu

### 8.1. Khởi động khi chưa có secret

Khi file chưa xuất hiện hoặc credential không hợp lệ:

- Chờ trong thời hạn giới hạn nếu injector có cơ chế chuẩn bị bất đồng bộ.
- Không cho workload nhận lưu lượng cần database khi chưa sẵn sàng.
- Trả lỗi có mã nguyên nhân, không in secret.
- Không fallback sang password mặc định, tài khoản quản trị hoặc secret được nhúng trong image.
- Phân biệt lỗi chưa sẵn sàng với lỗi cấu hình không thể tự khôi phục.

Readiness nên phản ánh khả năng phục vụ nghiệp vụ. Liveness không nên chỉ phản ánh việc vault tạm thời không truy cập được, vì restart đồng loạt có thể làm mất credential còn hợp lệ và khiến sự cố lan rộng.

### 8.2. Vault tạm thời mất kết nối

Có thể tiếp tục dùng credential đã cấp nếu nó còn hiệu lực và chính sách cho phép. Điều đó khác với kéo dài thời hạn một cách tùy tiện.

Ứng dụng hoặc agent phải biết:

- Bản credential hiện tại còn được phép dùng đến khi nào.
- Khi nào dừng mở kết nối mới.
- Khi nào mất readiness.
- Việc thu hồi từ xa có kênh thông báo nào, hoặc chỉ có thể phát hiện ở lần sử dụng tiếp theo.
- Có quy trình break-glass được kiểm soát riêng hay không.

Không lưu bản sao plaintext dài hạn làm “phương án dự phòng” ngoài sự quản lý của vault. Nếu có cơ chế khôi phục khẩn cấp, nó cần danh tính riêng, phê duyệt, thời hạn và audit phù hợp.

### 8.3. File mới không hợp lệ

Injector có thể gặp template lỗi, trường thiếu hoặc kết quả chưa đầy đủ. Consumer nên từ chối bản mới không hợp lệ, phát cảnh báo và chỉ tiếp tục dùng bản cũ trong phạm vi còn được phép.

Không chuyển pool sang một snapshot thiếu password rồi chờ lỗi nghiệp vụ phát hiện. Xác thực định dạng và kết nối thử trước khi thay consumer đang phục vụ.

### 8.4. Thu hồi khẩn cấp

Khi nghi ngờ lộ credential, chỉ xóa file injection là chưa đủ. Bản sao có thể vẫn nằm trong bộ nhớ hoặc kết nối đang mở.

Quy trình cần xét việc:

- Thu hồi hoặc vô hiệu hóa credential tại nguồn và hệ thống đích.
- Thu hồi identity hoặc policy của workload bị xâm phạm.
- Chặn hoặc cô lập workload để ngăn tiếp tục sử dụng.
- Đóng kết nối hoặc kết thúc session nếu nền tảng hỗ trợ.
- Cấp lại credential cho workload sạch và xác minh phục hồi.
- Giữ bằng chứng điều tra với quyền truy cập hạn chế.

Mức độ và thứ tự hành động phụ thuộc sự cố; không giả định restart ứng dụng luôn đủ để xử lý credential đã bị lộ ra ngoài.

## 9. Giảm các đường rò rỉ phổ biến

### 9.1. Log và observability

Không ghi password, token, private key hoặc toàn bộ payload từ secret service. Cũng cần xem xét các dữ liệu gián tiếp:

- JDBC URL có tham số mật khẩu.
- HTTP header xác thực.
- Đối tượng cấu hình được tự động chuyển thành chuỗi.
- Trace chứa body hoặc metadata nhạy cảm.
- Nội dung template sau khi render.
- Dump môi trường và gói hỗ trợ kỹ thuật.

Masking là lớp phòng vệ bổ sung. Nó có thể không nhận diện được giá trị đã encode, được chia nhỏ hoặc bị biến đổi. Đích đầu tiên là không thu thập dữ liệu bí mật vào hệ thống quan sát.

### 9.2. Tiến trình, shell và pipeline

Không truyền secret bằng cách nối nó vào chuỗi lệnh. Tránh bật shell tracing trong đoạn xử lý credential.

Credential phục vụ deploy nên tách khỏi credential runtime. Pipeline không cần đọc mật khẩu database của production nếu nền tảng runtime có thể tự cấp secret cho đúng workload.

Nếu ứng dụng sinh tiến trình con, chỉ truyền tập biến môi trường cần thiết. Không mặc định sao chép tất cả thông tin xác thực sang công cụ chuyển đổi file, script hỗ trợ hoặc lệnh chẩn đoán.

### 9.3. File tạm, quyền ghi và nhiều container

File tạm chứa secret cần quyền hạn chế ngay từ lúc tạo. Ghi file rồi mới `chmod` có thể tạo khoảng thời gian file có quyền rộng hơn mong muốn.

Trong Pod có nhiều container, chỉ mount secret vào container thật sự cần. Không mount cùng một volume secret vào sidecar thu log chỉ vì dùng chung một Pod.

Chia sẻ namespace tiến trình, quyền debug, quyền exec và quyền đọc filesystem trên node cũng có thể ảnh hưởng đến khả năng tiếp cận secret. Cần đánh giá các quyền này trong mô hình đe dọa thực tế.

### 9.4. Tránh biến đổi secret thành định dạng có thể thực thi

Render password vào shell script, YAML, JSON hoặc URI bằng nối chuỗi có thể làm hỏng cấu trúc nếu giá trị chứa ký tự đặc biệt.

Ưu tiên:

- API có tham số tách biệt.
- Serializer đúng định dạng.
- File giá trị thuần khi chỉ cần một secret.
- Hợp đồng encoding rõ ràng.
- Không chạy `eval` hoặc `source` trên file được tạo từ dữ liệu secret.

Secret là dữ liệu. Một injector có quyền cao không nên biến nó thành mã lệnh để thực thi.

## 10. Audit: chứng minh đã cấp đúng mà không ghi secret

Một bản ghi audit hữu ích có thể gồm:

| Trường | Mục đích |
|---|---|
| Workload identity | Ai thực sự yêu cầu credential |
| Môi trường và instance | Phân biệt production, staging và replica |
| Role hoặc tham chiếu secret được cho phép | Xác định phạm vi quyền |
| Version hoặc lease reference | Theo dõi vòng đời mà không ghi giá trị |
| Thời điểm cấp, refresh, hết hạn | Đối chiếu hành vi sử dụng |
| Kết quả và mã lỗi | Phát hiện từ chối hoặc lỗi hệ thống |
| Correlation ID | Nối sự kiện vault, injector, ứng dụng và hệ thống đích |
| Bằng chứng chuyển consumer | Xác nhận bản mới đã được dùng |

Tên đường dẫn, lease ID và metadata cũng có thể nhạy cảm. Chỉ thu thập mức cần thiết, hạn chế quyền đọc và không coi mọi metadata là công khai.

Không ghi hash của password yếu để thay cho password trong log. Hash đó vẫn có thể tạo điều kiện thử đoán ngoại tuyến. Ưu tiên version ID hoặc mã tham chiếu không chứa bí mật do hệ thống quản lý cung cấp.

Các tín hiệu vận hành đáng theo dõi gồm tỷ lệ injection thành công, thời gian chờ secret, số lần refresh thất bại, credential sắp hết hạn, độ trễ cập nhật và lỗi xác thực ở hệ thống đích. Tránh dùng secret value hoặc nhãn có số lượng không giới hạn làm metric label.

## 11. Kịch bản thiết kế cho checkout-api

Giả sử có ba replica `checkout-api`, mỗi replica dùng credential database có TTL 30 phút.

### 11.1. Thiết kế đề xuất

- Mỗi workload được xác thực bằng identity của môi trường production.
- Policy chỉ cho phép xin role database `checkout-runtime`.
- Role database có quyền nghiệp vụ tối thiểu và không có quyền quản trị.
- Injector công bố snapshot credential cùng metadata về version và expiry.
- Ứng dụng refresh trước hạn, tạo pool mới và kiểm tra kết nối.
- Pool cũ được drain với giới hạn thời gian.
- Audit ghi identity, tham chiếu credential và trạng thái chuyển đổi.
- Credential cũ được thu hồi theo chính sách sau khi consumer đã chuyển, hoặc ngay lập tức khi có sự cố cần cô lập.

Có thể chọn credential riêng theo replica để tăng khả năng quy trách nhiệm và giới hạn ảnh hưởng. Đổi lại, phải xét giới hạn tài khoản, kết nối, lưu lượng cấp credential và chi phí vận hành. Nếu dùng credential chung, cần chấp nhận khả năng khó phân biệt replica ở phía database và phạm vi thu hồi rộng hơn.

### 11.2. Tình huống lỗi

Tại phút thứ 20, vault không truy cập được. Credential hiện tại còn hiệu lực nhưng chưa có bản mới. Injector thử lại với backoff và phát cảnh báo.

Trước khi hết thời hạn an toàn, ứng dụng cần chuyển sang trạng thái đã định trước: tiếp tục phục vụ phần nghiệp vụ không cần database, mất readiness đối với phần phụ thuộc database, hoặc dừng nhận request mới theo kiến trúc cụ thể.

Không được đánh dấu refresh thành công chỉ vì file vẫn tồn tại. Cần kiểm tra version hoặc thời hạn bản hiện tại.

Sau khi vault phục hồi, injector lấy credential mới. Ứng dụng xác minh snapshot, tạo pool mới và chuyển lưu lượng. Việc đã phục hồi kết nối tới vault không tự chứng minh database đang chấp nhận credential mới; cần kiểm tra cả consumer và đích.

## 12. Bài thực hành

Thực hiện trên môi trường lab với credential giả hoặc tài khoản có quyền giới hạn.

### Bước 1: Định nghĩa hợp đồng injection

Ghi rõ:

- Workload nào cần secret và để làm việc gì.
- Định dạng, encoding, đường dẫn hoặc API cấp secret.
- Cách xác thực workload.
- Quyền tối thiểu tại vault và hệ thống đích.
- Secret tĩnh hay động, TTL và cách rotation.
- Khi nào ứng dụng được xem là sẵn sàng.
- Cách thu hồi và bằng chứng cần giữ.

### Bước 2: Kiểm tra luồng thành công

Cấp một secret thử nghiệm qua file runtime. Xác minh ứng dụng kết nối được, các file cấu hình thường không chứa password và log không có giá trị thử nghiệm.

Dùng một dấu hiệu kiểm thử chỉ dành cho lab để kiểm tra rò rỉ trong log/artifact. Không sao chép password production vào truy vấn tìm kiếm hoặc hệ thống kiểm tra bên ngoài.

### Bước 3: Kiểm tra quyền truy cập

Thử từ danh tính workload khác và xác nhận bị từ chối. Kiểm tra container không liên quan không được mount secret, file không được đọc bởi UID ngoài phạm vi thiết kế và ứng dụng không sửa được nguồn secret qua mount chỉ đọc.

### Bước 4: Kiểm tra rotation

Cấp bản mới, quan sát thời gian truyền tới ứng dụng và kiểm tra kết nối mới dùng credential mới. Xác nhận bản cũ bị từ chối theo chính sách tại hệ thống đích, đồng thời xử lý kết nối cũ theo hành vi đã xác định.

### Bước 5: Kiểm tra lỗi

Thử các trường hợp:

- Không có file khi khởi động.
- File rỗng, quá lớn hoặc sai encoding.
- File chứa newline ngoài hợp đồng.
- Injector không truy cập được vault.
- Credential mới không được hệ thống đích chấp nhận.
- Identity workload bị thu hồi.
- Credential hết hạn trong lúc còn kết nối đang mở.

Mỗi trường hợp cần có hành vi mong đợi và bằng chứng quan sát được. Một ứng dụng tiếp tục trả HTTP 200 trong khi mọi thao tác database đều lỗi không phải là dấu hiệu injection thành công.

## 13. Các lỗi thiết kế cần nhận ra

| Lỗi | Hệ quả | Hướng sửa |
|---|---|---|
| Nhúng vault token quản trị vào image | Image trở thành nguồn lấy đặc quyền rộng | Dùng workload identity và policy hẹp |
| Copy secret vào file cấu hình lâu dài | Tăng bản sao ngoài quản lý vòng đời | Đọc từ kênh runtime có kiểm soát |
| Dùng init container với credential TTL ngắn mà không refresh | Ứng dụng giữ bản hết hạn | Chọn refresh liên tục hoặc thay tiến trình trước hạn |
| Chỉ cập nhật file, không cập nhật pool | Rotation chưa đến consumer thực sự | Có giao thức reload và chuyển kết nối |
| In cấu hình để debug | Credential đi vào log và gói hỗ trợ | Chỉ log metadata cần thiết |
| Cho mọi workload dùng một admin account | Phạm vi ảnh hưởng lớn, khó quy trách nhiệm | Tách identity và quyền nghiệp vụ |
| Fallback sang password mặc định khi vault lỗi | Tạo đường vòng ngoài chính sách | Thiết kế trạng thái lỗi và phục hồi rõ ràng |
| Xóa file rồi coi như đã thu hồi | Credential còn dùng được ở nơi khác | Thu hồi tại nguồn/đích và xử lý session |
| Dùng `trim()` cho mọi password | Thay đổi giá trị hợp lệ | Thống nhất hợp đồng dữ liệu |
| Chỉ kiểm tra RBAC đọc Secret | Bỏ sót quyền tạo workload hoặc debug | Đánh giá toàn bộ đường truy cập đến runtime |

## 14. Câu hỏi tự kiểm tra

1. Vì sao chuyển password từ YAML sang biến môi trường chưa đủ để kết luận an toàn?
2. Workload dùng danh tính nào để lấy secret đầu tiên?
3. Ai có quyền gán danh tính đó cho một workload khác?
4. File secret đã đổi thì connection pool có tự dùng password mới không?
5. Username và password được đọc như thế nào để không ghép nhầm phiên bản?
6. TTL của credential khác gì thời gian tồn tại của kết nối đã xác thực?
7. Khi vault mất kết nối, ứng dụng được dùng bản cache đến thời điểm nào?
8. Quy trình thu hồi có xử lý bản sao trong bộ nhớ và session đang mở không?
9. Audit có chứng minh consumer đã chuyển sang version mới mà không ghi giá trị secret không?
10. Có quyền debug, exec, tạo Pod hoặc đọc node nào làm vượt qua giới hạn đã đặt cho secret không?

Secret injection hoàn chỉnh cần nối được identity, policy, kênh cấp, consumer, rotation và thu hồi. Đích cần đạt là workload nhận đúng credential với quyền và thời hạn cần thiết, còn việc sử dụng credential được kiểm chứng qua bằng chứng không chứa bí mật.

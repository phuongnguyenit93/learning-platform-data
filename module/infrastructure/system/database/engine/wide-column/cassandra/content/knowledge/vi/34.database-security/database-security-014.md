# Bảo vệ backup, cấu hình, log và dữ liệu thử nghiệm

> **Chương:** Bảo mật  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là hệ cơ sở dữ liệu phân tán theo mô hình wide-column. Việc bảo vệ dữ liệu cần theo toàn bộ vòng đời: thiết kế khóa phân vùng và bảng theo truy vấn, thực thi CQL, replication, consistency level, compaction/repair, backup/restore và truy cập từ ứng dụng Java.

## 1. Mục tiêu và tình huống mở đầu

Giả sử một cụm Cassandra phục vụ hệ thống đơn hàng đã được bật TLS, yêu cầu ứng dụng xác thực và phân quyền theo vai trò. Sau đó, một nhóm vận hành tạo snapshot, sao chép SSTable sang bucket backup, đưa bản ghi truy vấn vào hệ thống log và tải bản sao production về máy thử nghiệm để kiểm tra phục hồi. Mặc dù đường kết nối ứng dụng tới Cassandra được bảo vệ, dữ liệu khách hàng vẫn có thể bị lộ qua **bản backup, khóa giải mã, tệp cấu hình, log hoặc môi trường test**.

Bảo mật Cassandra cần bao phủ cả **đường dữ liệu trực tiếp** và **những bản sao dữ liệu phát sinh trong vận hành**. Bài này giúp bạn:

1. Nhận diện những tài sản và miền tin cậy liên quan tới snapshot, incremental backup, commitlog, cấu hình, log và dữ liệu test.
2. Thiết kế backup ngoài miền lỗi có **mã hóa, kiểm soát quyền, toàn vẹn, retention và khả năng restore**.
3. Giữ password/token/private key ra khỏi repository, script, tham số dòng lệnh, log và cấu hình phân phối rộng.
4. Giới hạn nội dung log, tracing, metrics và hồ sơ sự cố để vẫn quan sát được cluster mà không lộ dữ liệu nhạy cảm.
5. Chọn dữ liệu tổng hợp hoặc dữ liệu đã giảm nhận dạng cho môi trường kiểm thử, bảo toàn những đặc tính Cassandra cần đo.
6. Dùng checklist và bài tập để kiểm chứng biện pháp bảo vệ **mà không giả định “đã bật TLS là đủ”**.

**Phân biệt quan trọng:** cấu hình bảo mật là đầu vào; **khả năng đọc lại bản backup đúng quyền, kiểm tra được dữ liệu và khôi phục khi sự cố** mới là kết quả vận hành cần thử nghiệm.

## 2. Xác định tài sản, điểm vào và miền lỗi

### 2.1. Tài sản không chỉ là bảng đang chạy

| Tài sản | Có thể chứa gì? | Nguy cơ điển hình |
|---|---|---|
| SSTable trên node | Partition key, clustering key, cột dữ liệu, timestamp, tombstone và metadata | Đọc dữ liệu thô khi lấy được ổ đĩa hoặc tệp |
| Snapshot cục bộ | Các thành phần SSTable tại thời điểm snapshot; thường dùng hard link | Bản sao vẫn nằm trên volume của node, quyền file rộng hoặc bị quên dọn |
| Incremental backup, commitlog archive | SSTable bổ sung, các mutation để hỗ trợ khôi phục theo cơ chế phiên bản | Tập dữ liệu phụ không được mã hóa/kiểm soát như snapshot chính |
| Object storage backup | Nhiều phiên bản dữ liệu, schema, manifest, nhật ký khôi phục | Exfiltration, ghi đè hoặc xóa hàng loạt, thiếu khóa giải mã khi sự cố |
| Cấu hình node/ứng dụng | Credential, địa chỉ cluster, cấu hình TLS, chính sách quyền, đường dẫn cert/key | Lộ secret qua Git, máy developer, artifact build, log |
| Log, audit, tracing, crash dump | Client IP, role, CQL, lỗi, stack trace, giá trị bind nếu ứng dụng/công cụ ghi ra | Tập trung dữ liệu nhạy cảm ngoài chính sách retention của database |
| Bản test/khôi phục | Có thể chứa dữ liệu production gần như nguyên bản | Người có quyền test rộng hơn production có thể truy cập dữ liệu thật |

**Replica không phải backup.** Replication strategy và consistency level giúp duy trì phục vụ khi node hỏng; các replica vẫn nhận cùng lệnh DELETE/UPDATE và không tạo lịch sử độc lập để quay lại trước thao tác sai. **Repair** đồng bộ khác biệt replica chứ không phân biệt thao tác xóa đúng hay sai về nghiệp vụ.

### 2.2. Mô hình hóa kẻ tấn công và lỗi vô ý

Một thiết kế thực tế nên đặt các câu hỏi:

- Nếu token của ứng dụng bị lộ, kẻ tấn công có thể đọc **những keyspace nào**? Có thể đọc bucket backup không?
- Nếu tài khoản quản trị cluster bị chiếm quyền, tài khoản đó có thể **xóa cả mọi phiên bản backup** và tắt cơ chế khóa retention không?
- Nếu toàn bộ region chính không hoạt động, **khóa giải mã backup** nằm ở đâu và ai có quyền dùng?
- Nếu nhân viên đính kèm log vào ticket hỗ trợ, log có chứa password, payload JSON, tenant ID hay query values không?
- Nếu nhà phát triển tải bản sao về laptop, dữ liệu có còn được bảo vệ như trên production không?
- Nếu ứng dụng xóa dữ liệu theo yêu cầu hợp pháp, bản sao trong backup và test có tuân thủ chính sách lưu/xóa không?

Biện pháp được chọn phải gắn với **nguy cơ và miền lỗi cụ thể**. Lưu backup ở region khác có thể chống mất region nhưng chưa chống được xóa sai nếu cùng một quyền quản trị có thể xóa cả hai nơi.

## 3. Backup Cassandra chứa những gì và vì sao phải bảo vệ riêng?

Cassandra ghi dữ liệu vào **memtable** rồi flush thành **SSTable**. Snapshot thường giữ hard link tới các tệp SSTable trên node. Điều này giúp tạo snapshot nhanh, nhưng snapshot **không mặc nhiên rời node và không tự được mã hóa chỉ vì đường kết nối CQL có TLS**.

~~~mermaid
flowchart LR
    A["CQL write / Java driver"] --> B["Coordinator và replica"]
    B --> C["Commitlog + memtable"]
    C --> D["Flush → SSTable"]
    D --> E["Snapshot trên từng node"]
    E --> F["Đóng gói + manifest + checksum"]
    F --> G["Mã hóa và chuyển bằng kênh tin cậy"]
    G --> H["Kho backup độc lập"]
    H --> I["Restore trong môi trường cô lập"]
~~~

Một bộ backup có thể cần nhiều loại tệp:

- **Snapshot SSTable** của đủ phạm vi token và table.
- **Incremental SSTable** nếu dùng chuỗi backup gia tăng theo phiên bản.
- **Commitlog archive** nếu thiết kế có point-in-time recovery (PITR); cần ranh giới replay phù hợp để không phát lại thao tác xóa lỗi.
- **Schema CQL**, UDT, thông tin version/table ID, replication/DC/rack, partitioner, cấu hình cần thiết và bản ghi cutoff.
- **Manifest** mô tả backup ID, node, token coverage, tên tệp, byte size, digest, mốc tạo, trạng thái upload và dữ liệu cần giải mã.

**Không tự kết luận rằng snapshot ở một node chứa toàn bộ dữ liệu.** Cassandra phân vùng theo token; với RF lớn hơn một, mỗi node vẫn chỉ giữ các phần dữ liệu mà nó là replica. Khi tạo backup toàn cluster, phải điều phối phạm vi node/token và xác minh đầy đủ.

### 3.1. Những điểm dễ hiểu nhầm

| Giả định sai | Thực tế cần kiểm tra |
|---|---|
| “TLS của Cassandra mã hóa snapshot trên đĩa.” | TLS bảo vệ đường truyền được cấu hình; bảo vệ tệp backup tại nơi lưu cần cơ chế riêng |
| “RF = 3 nghĩa là ba bản backup độc lập.” | Ba replica nhận cùng biến đổi logic; mất/xóa dữ liệu hợp lệ có thể lan tới cả ba |
| “nodetool snapshot đã upload backup.” | Snapshot là thao tác cục bộ trên node được gọi; upload/kiểm chứng do pipeline khác thực hiện |
| “Bucket đã mã hóa nên ai cũng có thể tải bản sao.” | Mã hóa không thay thế phân quyền, audit và giới hạn sử dụng dữ liệu |
| “Có SHA-256 nghĩa là chống sửa tệp hoàn toàn.” | Digest phát hiện thay đổi khi giá trị kỳ vọng được bảo vệ; kẻ có thể sửa cả tệp lẫn manifest vẫn qua được kiểm tra nếu không có lớp xác thực |
| “Backup đã tải xong nghĩa là restore được.” | Cần schema, khóa, phiên bản tương thích và diễn tập khôi phục có kết quả |

## 4. Bảo vệ backup: bí mật, toàn vẹn, khả dụng

### 4.1. Bí mật: mã hóa khi truyền và khi lưu

Một pipeline backup nên dùng:

1. **Kênh mã hóa được xác thực** giữa node/agent và kho lưu trữ; chỉ cho phép endpoint hợp lệ.
2. **Mã hóa ở nơi lưu** bằng cơ chế được chấp thuận cho object/volume; cân nhắc mã hóa phía client nếu cần tách quyền giữa bên lưu trữ và bên giữ khóa.
3. **Quản lý khóa tập trung** qua KMS/HSM hoặc hệ thống quản lý secret phù hợp, với chính sách rotation, kiểm soát phiên giải mã và ghi nhận audit.
4. **Thiết kế phục hồi khóa:** nếu miền lỗi chính bị mất, role phục hồi còn truy cập được khóa và metadata giải mã không?

Mã hóa phía server và mã hóa phía client có mô hình tin cậy khác nhau. Nếu mã hóa phía client, phải lưu đủ thông tin thuật toán, key ID, nonce/IV hoặc metadata envelope cần thiết để giải mã, **không được lưu khóa bí mật thô trong manifest**.

Cơ chế mã hóa phải cung cấp bảo vệ toàn vẹn/xác thực phù hợp, chẳng hạn authenticated encryption ở tầng tệp; một checksum đơn thuần chủ yếu giúp phát hiện thay đổi vô ý khi giá trị chuẩn được bảo vệ.

### 4.2. Toàn vẹn: manifest, digest và provenance

Ví dụ logic của manifest do đội backup tự định nghĩa:

~~~json
{
  "backup_id": "cassandra-example-20261121T0200Z",
  "status": "COMPLETE",
  "cluster": "example-cluster",
  "scope": ["shop"],
  "data_cutoff_utc": "<verified-or-unknown>",
  "cassandra_version": "<actual-version>",
  "schema_object": "<protected-object-key>",
  "files": [
    {
      "node_id": "<node-identifier>",
      "token_scope": "<recorded-coverage>",
      "path": "<relative-path>",
      "bytes": 204800,
      "sha256": "<trusted-digest>"
    }
  ],
  "encryption_key_reference": "<key-id-not-secret>",
  "manifest_signature_reference": "<optional-signature-object>"
}
~~~

Đây là **mẫu metadata minh họa**, không phải định dạng mặc định của Cassandra. Một hệ thống đáng tin cậy cần xác minh:

- Số node, bảng, SSTable components và token ranges có đủ theo chiến lược backup.
- Kích thước và digest của tệp; manifest/digest phải được **xác thực hoặc lưu trong miền quyền tách biệt** để tránh sửa cả dữ liệu lẫn checksum.
- Trạng thái backup chỉ chuyển sang **COMPLETE** khi upload, kiểm tra digest, kiểm tra khóa và metadata bắt buộc đều đạt.
- Nguồn tệp, backup ID, phiên bản Cassandra/JDK và thời gian cutoff phải truy xuất được khi điều tra sự cố.

Có thể dùng lệnh tại một **máy kiểm thử riêng** để tạo/kiểm tra checksum của tệp đã được phép đọc:

~~~bash
sha256sum snapshot-file.db

# Chỉ tin cậy kết quả khi tệp checksum chuẩn được lấy
# từ nguồn độc lập hoặc đã được xác thực.
sha256sum -c backup.sha256
~~~

Đừng đưa tên tệp chứa thông tin khách hàng hoặc bucket URI có token truy cập vào log công khai. Digest phát hiện thay đổi không tự chứng minh tệp gốc là dữ liệu đúng; cần kiểm tra **provenance** và khả năng restore.

### 4.3. Khả dụng: giữ bản sao khi miền lỗi chính bị phá hủy

Một backup phải sống sót sau sự cố mà nó được thiết kế để chống lại:

- **Tách vị trí:** lưu ngoài volume/node và ngoài AZ/region nếu kịch bản yêu cầu.
- **Tách quyền:** tài khoản dịch vụ ghi backup không nhất thiết có quyền xóa mọi phiên bản; role Cassandra admin không mặc nhiên có quyền quản trị bucket.
- **Giới hạn xóa:** retention, versioning, WORM/object lock/immutability theo khả năng của nền tảng và yêu cầu nghiệp vụ.
- **Tách khóa phù hợp:** không để một sự cố IAM/KMS/region duy nhất làm mọi bản backup không giải mã được.
- **Bản sạch trước thao tác lỗi:** việc backup liên tục một trạng thái đã bị xóa nhầm không thay thế retention của các điểm khôi phục cũ.
- **Tải thử:** đo bandwidth, thời gian giải mã và đọc được dữ liệu trong môi trường miền lỗi chính giả định không còn.

**Immutability không phải bất tử:** cần quản lý thời hạn giữ, quyền quản trị cấp cao, lifecycle và khả năng phục hồi khóa. Đồng thời phải đáp ứng quy định xóa dữ liệu phù hợp; bản backup bất biến có thể tạo căng thẳng với chính sách loại bỏ dữ liệu cá nhân, nên cần lịch lưu/xóa được thiết kế từ trước.

## 5. Phân quyền backup theo vai trò và nguyên tắc ít đặc quyền

Nên tách các vai trò:

| Vai trò | Quyền thường cần | Quyền nên hạn chế |
|---|---|---|
| Agent tạo snapshot trên node | Thao tác snapshot cho phạm vi được giao; đọc tệp cần upload | Đổi role toàn cluster, xóa keyspace, chỉnh cấu hình unrelated |
| Uploader | Ghi object vào prefix/bucket mục tiêu, đọc metadata cần xác minh | Xóa tất cả phiên bản backup, truy cập bucket môi trường khác |
| Verifier | Đọc manifest, tệp mẫu, kiểm tra digest và trạng thái | Ghi đè snapshot hoặc thay đổi retention |
| Restore operator | Đọc bản backup đã chọn, dùng khóa giải mã theo quy trình, dựng cluster đích | Truy cập mọi kho dữ liệu hoặc tự động ghi lên production |
| Backup administrator | Quản lý lịch, retention và policy theo quy trình phê duyệt | Dùng chung credential với ứng dụng business hoặc node database |
| Auditor | Đọc evidence, policy và sự kiện thao tác | Đọc toàn bộ payload khách hàng nếu không cần thiết |

Các quyền cụ thể của object storage/IAM/KMS khác nhau theo nhà cung cấp. Bảng trên nêu **ranh giới trách nhiệm**, không phải bộ policy copy nguyên xi.

### 5.1. Lưu ý về quyền Cassandra

Cassandra có cơ chế **authentication**, **authorization** và **roles** tùy cấu hình/phiên bản. Nếu một service chỉ cần đọc một bảng, không nên cấp quyền quản trị rộng cho nó. Trong một môi trường đã bật authorization có thể kiểm tra quyền theo cú pháp được phiên bản hỗ trợ:

~~~sql
-- Chỉ dùng khi người vận hành có quyền kiểm tra và được phê duyệt.
LIST ROLES;
LIST ALL PERMISSIONS;
~~~

Lệnh có thể hiển thị thông tin nhạy cảm về vai trò/quyền; lưu kết quả trong kho evidence có phân quyền. **CQL role permissions không tự quản lý quyền của bucket backup, KMS, filesystem, Kubernetes Secret hoặc CI/CD.** Phải kiểm soát từng tầng.

Không đặt mật khẩu thật trong ví dụ **CREATE ROLE ... WITH PASSWORD = '...'** được commit vào repository hay chia sẻ qua chat/ticket. Dùng quy trình cấp secret có quản lý và tách quyền triển khai.

## 6. Secret và tệp cấu hình: phân biệt cấu hình được phép chia sẻ và dữ liệu bí mật

### 6.1. Những nơi secret thường bị rò rỉ

- Tệp cấu hình Cassandra/driver/app, biến môi trường, command-line arguments hoặc các file service manager.
- **CI logs**, output của shell ở chế độ verbose/debug hoặc artifact build.
- File truststore/keystore và mật khẩu của chúng; private key TLS; credential object storage, KMS, monitoring/JMX.
- File backup cấu hình, archive của thư mục dự án và snapshot VM.
- Stack trace, exception message, log request/response hoặc ticket đính kèm bản cấu hình đầy đủ.

**Không phải mọi trường cấu hình đều là secret.** Tên datacenter, contact point, port hoặc replication settings thường là thông tin vận hành cần kiểm soát phạm vi chia sẻ; password, API token, private key và session credential là bí mật cần xử lý nghiêm ngặt hơn.

### 6.2. Mẫu cấu hình ứng dụng an toàn hơn

Phân chia trách nhiệm:

1. **Repository:** chỉ giữ template không chứa secret; cấu hình không bí mật có thể được review.
2. **Secret store:** giữ credential, private key hoặc tham chiếu định danh đến key; có phân quyền/rotation.
3. **Runtime:** ứng dụng nhận secret qua phương pháp được nền tảng quản lý, không in giá trị ra log. Biến môi trường tiện lợi nhưng không an toàn tuyệt đối: có thể lộ qua crash dump, process inspection, debug hoặc cấu hình runtime.
4. **Triển khai:** quyền file/volume và quyền truy cập secret phải khớp với service account; tránh sao chép nguyên thư mục cấu hình vào artifact công khai.
5. **Rotation:** tài khoản/khóa có chủ sở hữu, vòng đời, quy trình thay thế và kiểm thử kết nối sau rotation.

Mẫu cấu hình không có giá trị nhạy cảm:

~~~yaml
# application.yml minh họa, không chứa password thực
cassandra:
  localDatacenter: dc1
  contactPoints:
    - cassandra-internal.example:9042
  auth:
    usernameSecretRef: "secret-store://orders/cassandra/username"
    passwordSecretRef: "secret-store://orders/cassandra/password"
  tls:
    trustBundleRef: "config-store://cassandra/cluster-ca"
~~~

Đây là **định dạng do ứng dụng giả định định nghĩa**, không phải config chuẩn được Cassandra hoặc Java driver tự động hiểu. **Secret reference** chỉ có ý nghĩa khi chương trình triển khai đã tích hợp resolver và xử lý lỗi quyền/rotation.

### 6.3. Cấu hình node: xác minh giá trị hiệu lực

Với Cassandra, các cơ chế có thể liên quan gồm:

- **client-to-node encryption** cho kết nối CQL/native protocol.
- **server-to-server encryption** cho traffic giữa các node.
- **authenticator** và **authorizer**, role/permission.
- Kiểm soát kết nối quản trị/JMX và tài khoản hệ điều hành chạy Cassandra.
- Tùy phiên bản/phân phối: audit logging, mã hóa dữ liệu khi lưu hoặc tích hợp KMS khác nhau.

**Tên tham số và khả năng hỗ trợ thay đổi theo phiên bản**, vì vậy cần dựa trên tài liệu của Cassandra/JDK đang chạy. Không nên tự tuyên bố “bật TLS thì mọi file trên disk được mã hóa”, cũng không vô hiệu hóa xác minh certificate chỉ để tránh lỗi kết nối.

Với truststore, certificate/CA có thể không phải secret, nhưng **private key và mật khẩu keystore** phải được bảo vệ. Xác minh hostname, certificate chain, hạn sử dụng và quyền truy cập là một phần kiểm thử triển khai và khôi phục.

## 7. Java driver: kết nối và logging không làm lộ thông tin

Ứng dụng Java có thể dùng **prepared statement** và **bind** để truyền giá trị kiểu dữ liệu phù hợp, tránh ghép dữ liệu vào chuỗi CQL. Nhưng prepared statement không tự bảo đảm an toàn nếu ứng dụng sau đó log mọi **BoundStatement** hoặc giá trị từng cột.

Ví dụ phần thiết lập session với secret/TLS được cấp phát qua thành phần quản lý của ứng dụng:

~~~java
import java.net.InetSocketAddress;
import java.util.UUID;
import javax.net.ssl.SSLContext;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class OrderReader {
    public interface Credentials {
        String username();
        String password();
    }

    // SSLContext phải được cấu hình xác minh CA/server phù hợp.
    public static void readOrder(
            Credentials credentials,
            SSLContext trustedTlsContext,
            UUID customerId,
            String orderMonth) {

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                        "cassandra-internal.example", 9042))
                .withLocalDatacenter("dc1")
                .withAuthCredentials(
                        credentials.username(), credentials.password())
                .withSslContext(trustedTlsContext)
                .build()) {

            PreparedStatement statement = session.prepare(
                "SELECT created_at, order_id, status " +
                "FROM shop.orders_by_customer_month " +
                "WHERE customer_id = ? AND order_month = ? LIMIT ?");

            var result = session.execute(
                    statement.bind(customerId, orderMonth, 20));

            int rows = 0;
            for (var row : result) {
                // Không in customer ID, payload hoặc credential.
                rows++;
            }
            System.out.println("Query completed; rowCount=" + rows);
        }
    }
}
~~~

**Đặc điểm của ví dụ:**

- Dùng **Java driver 4.x** với package **com.datastax.oss.driver.api**, chỉ minh họa cách dùng API; môi trường cần dependency tương ứng, keyspace/table và TLS server đã cấu hình.
- **Credentials** và **SSLContext** phải đến từ resolver/tài nguyên đã được xác minh; ví dụ không cài sẵn secret, không chỉ ra cách lấy khóa từ secret store cụ thể.
- Trong ứng dụng thật, **CqlSession** và **PreparedStatement** thường được tái sử dụng lâu dài, thay vì tạo mới mỗi lần đọc; session được mở trong hàm chỉ để ví dụ có phạm vi tự chứa.
- **SSLContext** cần kiểm tra CA và danh tính máy chủ theo chính sách kết nối của driver/version; không dùng trust-all context.
- **rowCount** là chỉ số thấp độ nhạy trong ví dụ, nhưng ngay cả row count cũng có thể nhạy cảm trong một số nghiệp vụ. Hệ thống thật phải phân loại trường log trước khi thu thập.
- Để tránh Java 10+ nếu dự án dùng phiên bản cũ, thay **var** bằng kiểu **ResultSet**/**Row** tương ứng.

**Tuyệt đối tránh** ghi password, session token, private key, toàn bộ kết quả SELECT hoặc nguyên **BoundStatement** chứa giá trị khách hàng vào log. Khi cần định danh truy vấn để tối ưu, dùng mã **query shape** hoặc tên operation, không tự động in tất cả bind values.

## 8. Bảo vệ log, audit, tracing và dữ liệu chẩn đoán

### 8.1. Phân loại trường và giảm dữ liệu

| Nguồn | Nên giữ để vận hành | Cần tránh hoặc bảo vệ đặc biệt |
|---|---|---|
| App/Java driver | Tên operation, duration, status/error code, correlation ID, số retry, node/DC ở phạm vi được phép | Password, token, bind values, payload, PII, full customer query |
| Cassandra server | Node health, GC, compaction, repair, read/write timeout, lỗi auth tổng hợp | Data payload, đường dẫn có secret, stack trace có thông tin nhạy cảm |
| Audit log | Ai làm gì, vào lúc nào, từ nơi nào, kết quả cho phép/từ chối | Mật khẩu, private key, dữ liệu trả về không cần thiết |
| Query tracing | Đường đi coordinator/replica và thời gian xử lý khi chẩn đoán | Query text/bind values nếu công cụ/ứng dụng thu thập, thông tin topology nhạy cảm |
| Backup pipeline | Backup ID, file count, digest/trạng thái, thời lượng, mã lỗi | Signed URL, credential kho, raw manifest nhạy cảm, secret KMS |
| Support ticket | Mô tả lỗi đã giảm nhận dạng, thời điểm, trace ID, ảnh chụp metrics đã kiểm tra | Dump nguyên log, bản sao bảng, unredacted customer ID |

**Lưu ý:** một số hệ thống telemetry hoặc proxy có thể thu thập CQL với bind values tùy cấu hình. Không được đoán rằng driver/server luôn bỏ giá trị nhạy cảm; cần **kiểm chứng đường đi log thực tế**, bao gồm error message, tracing, APM và exception handler.

### 8.2. Quy tắc ghi log ứng dụng an toàn

Thay vì:

~~~text
WARN failed query="INSERT INTO orders ...", password="...", payload={...}
~~~

Nên ưu tiên một bản ghi có cấu trúc:

~~~json
{
  "event": "cassandra_request_failed",
  "operation": "orders_by_customer_month.insert",
  "request_id": "req-8f2c",
  "consistency_level": "LOCAL_QUORUM",
  "error_class": "WriteTimeout",
  "duration_ms": 1200,
  "retry_attempt": 0
}
~~~

Đoạn JSON là ví dụ log có chủ ý giảm dữ liệu, không phải trường tự phát sinh từ driver. **request_id** phải không tiết lộ PII và không thay thế xác thực; không nên dùng partition key thô làm correlation ID nếu khóa đó chứa dữ liệu khách hàng.

Khi cần nghiên cứu truy vấn chậm, có thể lưu **query shape** (“SELECT... WHERE tenant_id = ? AND day = ?”), kích thước trang, số replica liên hệ, CL, p95/p99 và trace ID được tạo có kiểm soát. Với **Cassandra query tracing**, bật chỉ cho request/môi trường cần chẩn đoán và tắt khi hoàn tất; tracing có overhead và dữ liệu quan sát cần retention/quyền riêng.

### 8.3. Che dữ liệu khác với xóa nguyên nhân

**Redaction** phải diễn ra càng sớm càng tốt, trước khi payload vượt khỏi trust boundary. Chỉ che dữ liệu khi xem dashboard vẫn có thể để bản gốc nằm trong log pipeline/bucket không được bảo vệ.

Đồng thời cần:

- Đặt retention riêng cho **operational log, audit log, security log, trace** và evidence.
- Hạn chế quyền truy cập log theo nhóm nhiệm vụ; audit truy cập và xuất dữ liệu.
- Mã hóa storage/log transit và kiểm soát đường đẩy log ra dịch vụ bên thứ ba.
- Bảo vệ **core dump, heap dump, thread dump, JVM diagnostic bundles** vì chúng có thể chứa dữ liệu hoặc credential.
- Có quy trình xử lý khi secret hoặc PII bị log: ngăn tiếp tục lộ, thu hồi/rotation secret, hạn chế truy cập, dọn bản sao theo quy trình và đánh giá tác động.

## 9. Dữ liệu thử nghiệm và diễn tập restore: chọn đúng mức nhạy cảm

### 9.1. Ưu tiên synthetic data

**Synthetic data** là dữ liệu được tạo cho kiểm thử từ quy tắc và phân phối giả lập, không sao chép trực tiếp bản ghi khách hàng thật. Nó thường là lựa chọn mặc định cho CI, bài học, thử nghiệm hiệu năng quy mô nhỏ và kiểm thử logic CRUD.

Ví dụ schema CQL để tạo dữ liệu giả lập:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_shop
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS lab_shop.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);

INSERT INTO lab_shop.orders_by_customer_month
    (customer_id, order_month, created_at, order_id, status, amount)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11',
     '2026-11-21T04:00:00Z',
     22222222-2222-4222-8222-222222222222,
     'CREATED', 125.00);
~~~

Các UUID chỉ là **fixture giả lập**. Khi chạy trên cluster một node, phải điều chỉnh RF cho phù hợp với môi trường, không giả định keyspace RF = 3 và consistency LOCAL_QUORUM hoạt động như production chỉ với một node.

### 9.2. Khi cần dữ liệu tương tự production

Đôi khi cần mô phỏng hotspot, kích thước partition, tombstone, TTL, compaction hoặc các mẫu truy vấn hiếm. Khi không thể tạo synthetic data đủ đại diện, có thể cân nhắc **dữ liệu đã xử lý theo chính sách cho phép** trong môi trường cô lập.

| Cách xử lý | Lợi ích | Giới hạn cần biết |
|---|---|---|
| Synthetic data | Ít nguy cơ lộ dữ liệu khách hàng thực | Phải thiết kế phân phối dữ liệu đủ đại diện |
| Pseudonymization | Có thể giữ ánh xạ ổn định để join/đối chiếu nghiệp vụ | Vẫn có thể tái nhận dạng; bảng ánh xạ và khóa phải được bảo vệ |
| Masking/tokenization | Ẩn trường nhạy cảm theo chính sách | Dễ phá mẫu phân phối dữ liệu hoặc làm lộ metadata |
| Aggregation | Giảm nhu cầu dùng từng bản ghi | Không thích hợp cho mọi kiểm thử consistency/restore |
| Copy production có kiểm soát | Đại diện nhất với dữ liệu thực | Rủi ro cao; yêu cầu phê duyệt, cách ly, quyền hạn, retention và quy trình xóa |

**Hash thuần túy không bảo đảm ẩn danh**, đặc biệt với miền giá trị nhỏ (email, phone, mã vùng, ngày sinh). Với partition key, thay giá trị còn thay token phân phối; thiết kế test phải kiểm tra xem hotspot, phân phối partition, row size và clustering order còn đủ đại diện hay không. Nếu yêu cầu đo tải rất giống production, có thể tạo synthetic theo **thống kê phân phối** thay vì sao chép identity thật.

### 9.3. Checklist trước khi mang dữ liệu vào test

1. Xác định mục đích, phạm vi cột, thời hạn và người chịu trách nhiệm xử lý dữ liệu.
2. Ưu tiên dữ liệu tổng hợp; nếu cần dữ liệu thật, có phê duyệt và căn cứ xử lý phù hợp.
3. Chọn trường cần loại bỏ/biến đổi: tên, email, số điện thoại, địa chỉ, token, payload, tài liệu, định danh thiết bị, thông tin thanh toán.
4. Bảo vệ mapping/seed/key của phép biến đổi, không đặt trong cùng kho dữ liệu test dễ truy cập.
5. Tách tài khoản, mạng, secret, bucket, KMS và log khỏi production; chặn truy cập nhầm production từ test.
6. Kiểm tra ứng dụng test không gửi email, SMS, webhook, sự kiện thanh toán hoặc tác vụ ngoài ý muốn tới người thật.
7. Đặt TTL/retention cho bản sao dữ liệu, snapshot test và cả log sinh ra trong quá trình thử nghiệm.
8. Chạy kiểm tra dữ liệu nhạy cảm sau biến đổi và trước khi mở quyền truy cập cho nhóm test.
9. Ghi nhận version dataset, cách tạo, chủ sở hữu, quyền sử dụng và ngày cần xóa; thu hồi toàn bộ tệp phụ sau thử nghiệm.

**Phục hồi snapshot production vào test** phải được xem là một luồng xử lý dữ liệu có độ nhạy tương đương production cho đến khi kiểm chứng việc giảm nhận dạng hoàn tất. Không gắn nhãn “test” rồi mặc nhiên hạ mức kiểm soát.

## 10. Xây pipeline backup và restore có lớp bảo vệ rõ ràng

~~~mermaid
flowchart TD
    A["Cassandra nodes / SSTable snapshot"] --> B["Backup agent với quyền giới hạn"]
    B --> C["Manifest: độ phủ + mốc + checksum"]
    C --> D["Mã hóa / xác thực dữ liệu"]
    D --> E["Upload TLS vào kho độc lập"]
    E --> F["Xác minh digest, quyền và khả năng giải mã"]
    F --> G{"Backup đủ và đọc được?"}
    G -->|Không| H["Không đánh dấu COMPLETE; cảnh báo"]
    G -->|Có| I["COMPLETE + retention/immutability"]
    I --> J["Restore có phê duyệt vào cluster cô lập"]
    J --> K["Kiểm chứng CQL/Java và đối soát nghiệp vụ"]
    K --> L["Ghi RPO/RTO và nhật ký audit"]
~~~

Từng bước có trách nhiệm riêng:

**Trên node:** dùng user/service có quyền cần thiết, bảo vệ thư mục snapshot và kiểm soát disk space. Snapshot local có thể giữ SSTable cũ sau compaction và làm đầy ổ nếu không dọn theo retention.

**Khi truyền:** dùng TLS với xác minh endpoint; tránh link có credential tồn tại lâu, cấm đưa token vào command history/log.

**Khi lưu:** áp encryption-at-rest, IAM policy theo prefix, tách vai trò xóa/quản trị, retention và kiểm tra khóa.

**Khi xác minh:** tính/so checksum, kiểm tra chữ ký hoặc nguồn manifest đáng tin cậy, kiểm tra metadata, phát hiện thiếu node/table/SSTable component. Chỉ đánh dấu COMPLETE sau khi tất cả phần bắt buộc đạt.

**Khi restore:** chọn mốc sạch, dùng role phục hồi và cluster tách biệt, giới hạn truy cập backup, đo RPO/RTO và thử query/Java theo partition key. Không trộn bừa SSTable cũ với cluster production đang ghi vì có thể gặp lỗi schema/TTL/tombstone và dữ liệu xóa bị hồi sinh.

**Khi dọn:** bản local chỉ nên dọn theo chính sách sau khi backup độc lập đã được kiểm chứng; bản backup giữ theo retention và quy trình loại bỏ phù hợp yêu cầu pháp lý/nghiệp vụ. Việc dọn phải có audit trail và bảo vệ khỏi thao tác hàng loạt ngoài ý muốn.

## 11. Kiểm chứng cấu hình, log và backup mà không lộ bí mật

Một buổi kiểm tra có thể dùng các bước sau, với quyền phù hợp và dữ liệu **thử nghiệm**:

### 11.1. Kiểm tra trạng thái Cassandra

~~~bash
# Quan sát trạng thái node và datacenter.
nodetool status

# Snapshot được liệt kê trên node đang kết nối.
nodetool listsnapshots

# Kiểm tra các bảng/độ trễ theo phạm vi được phép.
nodetool tablestats lab_shop.orders_by_customer_month
~~~

Các lệnh trên **không phải công cụ kiểm toán toàn bộ bảo mật**. Node có thể UP/NORMAL mà backup vẫn thiếu, KMS không giải mã được hoặc app log vẫn lộ payload. Tên metric và cú pháp còn tùy phiên bản Cassandra.

### 11.2. Kiểm tra rủi ro qua danh mục, không xuất bí mật

- **Backup:** có bản COMPLETE mới nhất? Có đủ manifest, schema, tệp và checksum? Có bản ở miền lỗi khác? Role restore có giải mã được file mẫu không?
- **Config:** secret có đến từ store được cấp quyền? Có private key/credential trong repository hoặc artifact build không? TLS/auth có hiệu lực theo phiên bản và đúng node/driver không?
- **Log:** có CQL bind values, session token, signed URL, dữ liệu khách hàng hoặc đường dẫn chứa secret trong app/Cassandra/APM/backup job không?
- **Test:** dữ liệu có synthetic hoặc đã xử lý phù hợp? Có thể gửi dữ liệu sang dịch vụ production không? Có snapshot/log test bị bỏ quên không?
- **Audit:** ai truy cập bản backup, ai thay đổi policy/retention/key, ai thao tác restore và khi nào?

Nếu phát hiện secret thật, **không copy giá trị đó vào báo cáo**. Ghi tên hệ thống, loại tài sản, bằng chứng đã giảm nhận dạng và một ID ticket; phối hợp rotation/thu hồi theo quy trình ứng cứu.

### 11.3. Kiểm thử khôi phục độc lập

Chọn một bộ backup đã đánh dấu COMPLETE, tạo cluster cô lập, giải mã và nạp dữ liệu theo runbook tương thích với phiên bản Cassandra. Kiểm tra nhiều partition key, clustering order, row đã UPDATE/DELETE và trường TTL. Với các bảng thiết kế theo truy vấn, kiểm tra nhất quán nghiệp vụ giữa các bảng denormalized.

Kết quả thử nên có:

~~~yaml
drill_id: "cassandra-security-restore-example"
backup_id: "<verified-backup-id>"
backup_integrity: "PASS"
encryption_key_available_in_target_domain: true
manifest_and_schema: "PASS"
restore_environment: "isolated"
data_validation: "PASS_FOR_DECLARED_FIXTURES"
sensitive_data_in_logs: "NOT_OBSERVED_IN_TEST_SCOPE"
rpo_estimate_minutes: "<measured-or-unknown>"
rto_drill_minutes: "<measured-or-unknown>"
unverified_dependencies:
  - "<if-any>"
result: "PASS_WITH_DEFINED_SCOPE"
~~~

Đây là **mẫu báo cáo tự định nghĩa**, không phải cấu hình Cassandra. Nếu chưa thử mất region, chưa kiểm tra toàn bộ log pipeline hoặc chưa thử dữ liệu đủ quy mô, ghi rõ **scope chưa kiểm chứng**. Không tự đánh dấu PASS cho hệ thống production chỉ vì một tập fixture nhỏ khôi phục được.

## 12. Kịch bản xử lý sự cố rò rỉ và sai cấu hình

### 12.1. Credential backup bị lộ trong CI log

**Tín hiệu:** job backup in signed URL hoặc access token ra log build, log được nhiều người truy cập.

1. Hạn chế ngay đường phát tán: quyền xem log, job đang chạy, artifact/cache liên quan.
2. Thu hồi hoặc rotation credential và xác minh không còn quyền sử dụng token cũ, phù hợp khả năng token/session đang dùng.
3. Kiểm tra audit trail để đánh giá những object có thể bị đọc, sửa hoặc xóa.
4. Sửa pipeline để không log tham số/URL nhạy cảm, không bật shell verbose và dùng scoped identity thay cho credential lâu dài khi có thể.
5. Xác thực backup vẫn đầy đủ, nguyên vẹn và có bản sạch không bị quyền vừa lộ xóa.
6. Ghi sự kiện bằng chứng giảm nhận dạng, owner và kiểm thử tránh tái diễn.

### 12.2. Bucket backup bị mở quyền quá rộng

**Tín hiệu:** bucket/prefix hoặc policy cho phép đọc ngoài phạm vi tổ chức dự kiến.

- Khóa quyền đọc ngoài phạm vi và kiểm tra những đường chia sẻ/public URL trước đây.
- Đối chiếu access logs, inventory, retention và checksum/signature; kiểm tra xem dữ liệu đã bị tải hoặc thay đổi hay chưa.
- Nếu backup được mã hóa bằng khóa mà bên ngoài không có quyền giải mã, rủi ro giảm nhưng không bằng không: metadata, đường dẫn, key policy và lỗi triển khai vẫn cần đánh giá.
- Kiểm thử restore sau khi siết policy, tránh khóa luôn vai trò DR hợp lệ.
- Xác định có cần thay khóa, thông báo, điều tra hoặc các bước pháp lý theo quy trình đơn vị hay không.

### 12.3. Log test vô tình chứa PII

**Tín hiệu:** khi phục hồi dữ liệu production vào test, ứng dụng ghi nguyên customer payload vào APM.

- Tạm dừng pipeline phát tán, hạn chế truy cập và thời gian lưu log liên quan.
- Dùng dữ liệu synthetic hoặc dataset đã giảm nhận dạng, kiểm tra tất cả sink như APM, alert, ticket và archive.
- Thêm bộ lọc/redaction tại nguồn, test không hồi quy bằng payload đánh dấu.
- Xóa/giảm quyền với bản log nhạy cảm theo chính sách; kiểm chứng retention và backup log cũng được xử lý.
- Chỉ mở lại diễn tập sau khi chứng minh dữ liệu test không vượt khỏi miền tin cậy đã xác định.

## 13. Các quyết định thiết kế cần cân bằng

### 13.1. Bảo mật và RTO

Mã hóa, tách quyền và cấp quyền khôi phục có thể làm quy trình restore thêm bước, nhưng bỏ qua chúng sẽ khiến backup bị lộ hoặc không tồn tại khi cần. Cách cải thiện RTO đúng là **tự động hóa bước kiểm tra quyền được phép**, thử KMS trong miền đích, lưu runbook/version và diễn tập định kỳ; không lưu private key trong script để “khỏi chờ phê duyệt”.

### 13.2. Retention và yêu cầu xóa dữ liệu

Backup dài hạn giúp quay về mốc sạch, nhưng có thể giữ dữ liệu đã bị xóa khỏi bảng live vì TTL hoặc yêu cầu pháp lý. Đội vận hành cần biết:

- Dữ liệu live hết TTL không có nghĩa mọi snapshot/backup chứa phiên bản cũ cũng tự biến mất.
- **gc_grace_seconds** liên quan tombstone/repair, không phải chính sách lưu backup.
- Thời hạn giữ, phạm vi đối tượng và quy trình xóa/ngoại lệ phải thống nhất giữa backup, test data, log và hồ sơ sự cố.
- Trong kịch bản restore từ bản cũ, phải xử lý các yêu cầu xóa hợp lệ phát sinh sau cutoff trước khi mở lại dữ liệu cho người dùng.

### 13.3. Observability và tối thiểu hóa dữ liệu

Để phân tích phân vùng nóng, người vận hành cần số row, kích thước partition, token/routing và latency; thông thường không cần log tên khách hàng hoặc payload giao dịch. Cassandra hỗ trợ **thiết kế bảng theo truy vấn**: khi đã biết truy vấn cần gì, có thể thiết kế metric theo **query shape**, DC, CL, partition-size bucket và dấu hiệu timeout thay vì dump giá trị CQL.

Một hệ thống có quan sát tốt nên giúp trả lời “bảng nào đang có compaction backlog, replica nào chậm, truy vấn nào timeout?” mà không cần người xem thấy nội dung đơn hàng.

## 14. Bài tập thực hành

### Bài 1 — Snapshot được copy trong cùng region

Cluster dùng RF = 3, snapshot các node được copy vào bucket cùng region và cùng tài khoản admin quản lý cluster. Một người vô tình xóa bảng rồi xóa luôn bucket.

**Câu hỏi:** Tại sao replica không giúp? Những thay đổi nào cần để có bản backup độc lập hơn?

**Gợi ý:** thao tác xóa logic được replicate, còn bucket và cluster cùng quyền/miền lỗi. Cần bản trước lỗi được giữ ở miền độc lập thích hợp, quyền xóa tách biệt, retention/versioning/immutability, khóa giải mã và diễn tập restore.

### Bài 2 — Tìm vấn đề trong thông báo lỗi

Ứng dụng Java log:

~~~text
WARN Cassandra login failed for user=orders_app
password=swordfish123 customer_id=... payload={...}
~~~

**Câu hỏi:** Có những loại dữ liệu nào không nên nằm trong log? Cần xử lý sự cố đang xảy ra thế nào?

**Gợi ý:** password, định danh khách hàng/payload và thông tin xác thực có thể bị lộ. Chặn phát tán, thu hồi/rotation secret, giảm quyền log, điều tra scope, sửa template log và kiểm tra sink khác.

### Bài 3 — Checksum có đủ chống sửa backup?

Một uploader có quyền sửa cả tệp SSTable trong bucket và manifest chứa SHA-256. Uploader thay SSTable rồi tính lại digest.

**Câu hỏi:** Bước verify checksum hiện tại phát hiện được không? Có thể bổ sung lớp nào?

**Gợi ý:** kiểm tra digest với manifest vừa bị sửa có thể vẫn PASS. Cần nguồn manifest được bảo vệ độc lập, chữ ký/xác thực, hạn chế quyền ghi đè và retention/immutability.

### Bài 4 — Dữ liệu test thay đổi partition key

Một team hash toàn bộ customer_id trước khi đưa production snapshot vào test. Sau đó họ khẳng định benchmark giữ nguyên phân phối token và hotspot.

**Câu hỏi:** Tại sao kết luận chưa chắc đúng? Có cách nào kiểm chứng?

**Gợi ý:** token được tính trên khóa phân vùng đã mã hóa; đổi giá trị làm đổi token và có thể đổi phân bố replica/hotspot. Kiểm tra cardinality, skew, kích thước partition, throughput, latency; ưu tiên synthetic data theo phân phối và workload đã đo.

### Bài 5 — Thiết kế bảng theo truy vấn và log an toàn

Cho mẫu CQL:

~~~sql
SELECT order_id, status, amount
FROM lab_shop.orders_by_customer_month
WHERE customer_id = ? AND order_month = ?
LIMIT ?;
~~~

**Yêu cầu:** đề xuất một log entry hỗ trợ điều tra **read timeout** mà không lộ customer_id hoặc amount.

**Gợi ý:** ghi operation name, query-shape ID, keyspace/table, CL, dc, latency, timeout class, retry count, tracing ID có kiểm soát, request ID không chứa PII. Không log BoundStatement hoặc row payload.

### Bài 6 — Phục hồi đúng dữ liệu nhưng mất khóa KMS

Bản backup ngoài region được mã hóa, checksum hợp lệ, nhưng chỉ khóa KMS ở region chính mới giải mã được. Region chính mất hoàn toàn.

**Câu hỏi:** Bản backup có đạt mục tiêu DR không? Cần bổ sung gì vào runbook?

**Gợi ý:** chưa đáp ứng nếu miền đích không có quyền/khả năng giải mã. Cần kiến trúc khóa/ủy quyền phù hợp khi region chính mất, kiểm thử từ miền đích và đo thời gian cấp quyền trong RTO.

## 15. Checklist tự đánh giá bảo mật vận hành Cassandra

- [ ] Xác định được dữ liệu nhạy cảm trong **SSTable, snapshot, incremental backup, commitlog, manifest, config, log, test dataset**.
- [ ] Có backup **độc lập với miền lỗi mục tiêu** và được kiểm chứng đầy đủ về node/token coverage.
- [ ] Dữ liệu được mã hóa khi truyền và ở nơi lưu; khóa giải mã có quyền/retention/khả năng DR phù hợp.
- [ ] IAM, CQL roles, quyền hệ điều hành, JMX, KMS và quyền bucket được xét **từng tầng**, theo ít đặc quyền.
- [ ] Không có password/token/private key trong Git, script dùng chung, command history, artifact hoặc log.
- [ ] Có kiểm tra **TLS/auth/authorization** thực tế theo phiên bản Cassandra và driver Java.
- [ ] Log, audit, tracing và APM không phát tán credential, bind values hoặc payload; có redaction tại nguồn.
- [ ] Core dump/heap dump, support bundle và ticket có kiểm soát quyền/retention.
- [ ] Môi trường test tách cluster, secret, network, bucket và external integrations khỏi production.
- [ ] Dataset test ưu tiên synthetic; dữ liệu lấy từ production chỉ dùng theo chính sách và được kiểm chứng xử lý thích hợp.
- [ ] Retention và quy trình xóa áp dụng nhất quán cho bảng live, backup, log, test và bản trích xuất.
- [ ] Có backup manifest/checksum và nguồn xác thực để phát hiện sửa đổi; chỉ gắn COMPLETE khi kiểm tra xong.
- [ ] Đã diễn tập restore vào môi trường cô lập, kiểm tra nhiều partition, TTL/DELETE, schema và ứng dụng Java.
- [ ] Đã đo RPO/RTO, kiểm chứng khả năng giải mã khi miền chính mất và cập nhật runbook từ phát hiện thực tế.

## 16. Tổng kết

Bảo vệ Cassandra không dừng ở cấu hình xác thực và mã hóa kết nối. **Replica** phục vụ tính sẵn sàng, **snapshot** giữ dữ liệu theo mốc và **backup ngoài miền lỗi** tạo cơ hội khôi phục khi hạ tầng hoặc dữ liệu live bị phá hủy. Mỗi bản sao ấy, cùng cấu hình, log và dữ liệu test, đều có thể trở thành một đường lộ dữ liệu nếu thiếu phân quyền, mã hóa, kiểm chứng toàn vẹn và vòng đời lưu/xóa phù hợp.

Thiết kế bền vững là **giới hạn quyền theo vai trò, bảo vệ secret, tối thiểu hóa dữ liệu quan sát, dùng dữ liệu thử nghiệm an toàn và kiểm thử restore thực tế**. Kết hợp với mô hình wide-column, partition key, consistency level, compaction, repair và ứng dụng Java, các biện pháp này giúp Cassandra vừa có thể phục hồi sau sự cố, vừa giảm nguy cơ lộ dữ liệu trong chính quá trình vận hành.

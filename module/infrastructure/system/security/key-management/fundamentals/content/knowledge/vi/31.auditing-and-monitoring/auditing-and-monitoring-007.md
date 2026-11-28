# Key destroyed event: Ghi nhận và giám sát sự kiện hủy khóa

**Key destroyed event** là sự kiện kiểm toán ghi nhận một khóa mật mã đã đi qua quy trình hủy và đạt trạng thái mà hệ thống quản lý khóa xác nhận là không còn có thể sử dụng theo cơ chế của nền tảng. Sự kiện này có ý nghĩa đặc biệt vì hủy khóa có thể làm dữ liệu được bảo vệ trở nên không thể giải mã, chữ ký mới không thể tạo ra, hoặc một danh tính mật mã không thể tiếp tục hoạt động.

Trong quản lý khóa, yêu cầu hủy, phê duyệt hủy, đưa khóa vào trạng thái chờ hủy và xác nhận hủy hoàn tất là những mốc khác nhau. Một log ghi nhận yêu cầu destroy không chứng minh key material đã bị xóa. Hệ thống audit cần phân biệt ý định, tiến trình, kết quả và bằng chứng xác minh; hệ thống monitoring cần phát hiện thao tác bất thường, hủy nhầm khóa và khoảng trống kiểm toán.

Sự kiện hủy khóa cũng cần được đặt trong ngữ cảnh vòng đời dữ liệu. Hủy một KEK có thể khiến các DEK được wrap bằng KEK đó không thể mở gói; hủy một DEK có thể khiến bản mã tương ứng không thể giải mã. Tuy nhiên, nếu dữ liệu rõ, khóa đã xuất, bản sao hoặc một đường phục hồi khác vẫn tồn tại, việc hủy một đối tượng khóa chưa chắc đã xóa mọi khả năng truy cập dữ liệu.

## 1. Key destroyed event là gì?

Key destroyed event là bản ghi có cấu trúc mô tả việc hủy khóa hoặc một phiên bản khóa đã hoàn tất theo semantics của KMS, HSM, thiết bị mật mã hoặc hệ thống quản lý khóa. Sự kiện thường chứa định danh khóa, phiên bản, danh tính thực hiện, thời điểm, lý do, kết quả và tham chiếu bằng chứng.

Sự kiện này có thể được phát ra bởi:

- KMS khi một key version hoặc key resource được hủy.
- HSM khi key object bị xóa hoặc key material được zeroize theo quy trình của thiết bị.
- Hệ thống quản lý khóa khi hoàn tất cryptographic erasure hoặc thao tác hủy theo workflow.
- PKI/CA khi khóa riêng hoặc tài sản khóa được hủy trong quy trình kết thúc vòng đời chứng thư.
- Ứng dụng hoặc orchestration service khi điều phối thao tác hủy và ghi nhận kết quả từ backend.

Nguồn phát phải được xác định rõ. Một sự kiện do ứng dụng tự ghi “destroy success” có độ tin cậy khác với audit event được phát trực tiếp từ KMS/HSM. Nên ưu tiên sự kiện từ hệ thống thực thi thao tác, sau đó đối chiếu với bản ghi điều phối và bằng chứng độc lập.

### Vì sao phải giám sát sự kiện hủy?

- Hủy nhầm khóa có thể làm mất khả năng truy cập dữ liệu hoặc gián đoạn dịch vụ.
- Hủy trái phép có thể là hành vi phá hoại, che giấu dấu vết hoặc gây gián đoạn có chủ đích.
- Khóa đã đến cuối vòng đời nhưng chưa hủy có thể tiếp tục tạo rủi ro nếu vẫn được phép sử dụng.
- Hủy không đầy đủ có thể để lại bản sao, replica, key backup hoặc key material đã xuất.
- Thiếu audit event khiến tổ chức không thể chứng minh ai đã hủy khóa, khi nào và theo phê duyệt nào.
- Event pipeline bị gián đoạn có thể làm mất khả năng phát hiện hành động quan trọng.

## 2. Phân biệt destroy request, pending và destroyed

Không nên gộp mọi trạng thái liên quan đến hủy thành một sự kiện duy nhất. Tên trạng thái và semantics phụ thuộc nền tảng, nhưng quy trình thường có các mốc logic sau:

| Mốc | Ý nghĩa | Bằng chứng cần có |
|---|---|---|
| Destroy requested | Có người hoặc workload yêu cầu hủy khóa. | Request ID, principal, key ID, lý do và thời điểm. |
| Approval granted | Yêu cầu đã được phê duyệt theo quy trình. | Approval ID, người phê duyệt, phạm vi và thời điểm. |
| Destruction scheduled | Hệ thống đã lên lịch hủy hoặc bắt đầu thời gian chờ. | Trạng thái backend, thời điểm dự kiến và điều kiện hủy. |
| Pending destruction | Khóa đang chờ đến thời điểm hủy hoặc chờ hoàn tất tác vụ. | Trạng thái hiện tại, thời hạn còn lại và khả năng hủy lịch. |
| Destruction completed | Backend xác nhận thao tác hủy đã hoàn tất theo semantics của nó. | Event từ nguồn thực thi, trạng thái sau hủy và mã tham chiếu. |
| Destruction failed | Backend không thể hoàn tất thao tác. | Mã lỗi, nguyên nhân, trạng thái thực tế và kế hoạch xử lý. |
| Destruction cancelled | Lịch hủy được hủy trước khi thao tác hoàn tất. | Principal, lý do, approval và trạng thái khóa sau hủy lịch. |

Một số nền tảng dùng thuật ngữ pending deletion, scheduled deletion, destroyed, deleted hoặc disabled. Không được suy ra rằng các từ này có cùng ý nghĩa trên mọi nhà cung cấp.

**Disable không phải destroy.** Disable thường ngăn thao tác mới nhưng key material vẫn còn để có thể kích hoạt lại hoặc phục hồi theo policy. **Revoke** có thể thu hồi chứng thư, quyền hoặc khả năng sử dụng theo semantics của hệ thống. **Delete metadata** có thể chỉ xóa bản ghi quản lý, trong khi key material hoặc bản sao vẫn còn. Chỉ đánh dấu destroyed khi có bằng chứng rằng thao tác hủy thực sự đã hoàn tất theo quy trình được định nghĩa.

### Thời gian chờ trước khi hủy

Một số KMS cung cấp khoảng thời gian chờ hoặc recovery window trước khi hủy vĩnh viễn. Trong khoảng này, khóa có thể ở trạng thái pending deletion và có thể khôi phục hoặc hủy lịch. Đây là biện pháp giảm rủi ro thao tác nhầm, nhưng cũng có nghĩa khóa chưa bị hủy hoàn toàn.

Monitoring cần phân biệt:

- Yêu cầu hủy đã được tạo.
- Thời điểm hủy dự kiến.
- Khóa còn khả năng phục hồi hay không.
- Thời điểm backend xác nhận hủy vĩnh viễn.

Không gửi cảnh báo “key material đã bị xóa” chỉ vì nhận được event scheduled deletion. Nếu cần thông báo sớm, hãy dùng tên cảnh báo như “destruction scheduled” hoặc “pending deletion”.

## 3. Quy trình hủy khóa có kiểm soát

Một quy trình an toàn thường bao gồm các bước:

1. **Xác định khóa:** tìm đúng key ID, phiên bản, môi trường, owner, purpose và các hệ thống phụ thuộc.
2. **Đánh giá tác động:** xác định dữ liệu, chứng thư, ứng dụng, DEK, bản sao và backup có phụ thuộc vào khóa.
3. **Ngừng cấp phát mới:** chuyển khóa sang trạng thái không dùng cho thao tác mới nếu quy trình yêu cầu.
4. **Phê duyệt:** xác minh người yêu cầu, người sở hữu và người phê duyệt độc lập; yêu cầu dual control với khóa quan trọng.
5. **Lên lịch hủy:** tạo request và ghi nhận thời hạn chờ nếu backend hỗ trợ.
6. **Kiểm tra trước thời điểm hủy:** xác nhận không còn phụ thuộc hợp lệ hoặc đã có kế hoạch di trú/phục hồi.
7. **Thực thi hủy:** gọi KMS/HSM hoặc quy trình zeroization được phê duyệt.
8. **Xác minh kết quả:** đọc trạng thái từ backend, nhận audit event và đối chiếu bằng chứng.
9. **Đóng quy trình:** lưu event, approval, bằng chứng, phạm vi bản sao và kết quả rà soát.

Đối với khóa được dùng trong production, không nên cho một cá nhân vừa yêu cầu vừa phê duyệt và thực hiện hủy mà không có kiểm soát độc lập. Quy trình cần xác định ai có quyền hủy, ai có quyền dừng lịch hủy và ai xác minh kết quả.

## 4. Hủy khóa và cryptographic erasure

**Cryptographic erasure** là phương pháp làm dữ liệu không thể giải mã bằng cách hủy hoặc làm mất vĩnh viễn khóa cần thiết để giải mã dữ liệu đó. Phương pháp này thường hữu ích khi dữ liệu được mã hóa trước khi lưu trữ và key material được quản lý tách biệt.

Ví dụ với envelope encryption:

~~~text
Plaintext
   |
   v
DEK mã hóa dữ liệu
   |
   +----> Ciphertext lưu trong storage
   |
   v
DEK được wrap bằng KEK
   |
   v
Wrapped DEK lưu cùng metadata

Hủy KEK hoặc mọi bản sao có thể mở gói DEK
   |
   v
Không thể lấy DEK để giải mã ciphertext
~~~

Hủy KEK có thể làm cho các DEK được wrap không còn khả năng mở gói, nhưng kết luận này chỉ đúng nếu không còn bản sao KEK, bản sao DEK dạng rõ, recovery key hoặc bản backup có thể phục hồi. Nếu ứng dụng từng nhận DEK dạng rõ và lưu trong cache, heap dump, file tạm hoặc log, việc hủy KEK không xóa các bản sao đó.

Cryptographic erasure cần đánh giá:

- Key material có tồn tại trong KMS/HSM, replica, backup hoặc thiết bị khác không?
- Khóa có từng được export hoặc wrap bằng một KEK khác không?
- DEK có được cache trong ứng dụng hoặc lưu trong snapshot không?
- Có bản backup dữ liệu và khóa phục hồi còn mở được bản backup đó không?
- Có dữ liệu plaintext hoặc bản sao không mã hóa ở hệ thống phụ trợ không?
- Hệ thống có bằng chứng kiểm tra toàn bộ bản sao và phiên bản khóa liên quan không?

Hủy một key object trong KMS không tự động chứng minh toàn bộ dữ liệu trên mọi hệ thống đã được xóa. Báo cáo cryptographic erasure cần nêu rõ phạm vi, giả định, bản sao được kiểm soát và giới hạn xác minh.

## 5. Zeroization trong HSM và hệ thống quản lý khóa

**Zeroization** là quá trình xóa hoặc làm mất key material trong vùng lưu trữ theo cơ chế của thiết bị hoặc hệ thống. Trong HSM, thao tác này có thể được thực hiện trong ranh giới phần cứng bảo vệ và có thể tạo audit record hoặc bằng chứng trạng thái.

Không nên khẳng định zeroization thành công chỉ dựa trên việc:

- Xóa alias trong ứng dụng.
- Xóa file chứa metadata.
- Gọi một hàm delete nhưng không kiểm tra kết quả.
- Xóa một bản sao mà không rà soát replica và backup.
- Nhận HTTP 200 từ một lớp wrapper nhưng chưa xác minh backend.

Bằng chứng đáng tin cậy có thể gồm event từ HSM/KMS, trạng thái object sau hủy, log kiểm toán thiết bị, chứng từ vận hành hoặc báo cáo của nhà cung cấp theo mức đảm bảo phù hợp. Cần lưu ý rằng mức chứng minh vật lý phụ thuộc kiến trúc và chứng nhận của thiết bị; ứng dụng thường chỉ xác minh được kết quả theo giao diện quản lý và bằng chứng mà nền tảng cung cấp.

Nếu khóa được backup theo cơ chế HSM, phải hiểu cách hủy tác động đến backup, security domain, cluster member và thiết bị phục hồi. Một key object có thể bị xóa khỏi thiết bị chính nhưng vẫn có thể được phục hồi từ bản backup nếu quy trình chưa hủy bản sao tương ứng.

## 6. Những nguồn phát Key destroyed event

Một hệ thống có thể nhận sự kiện từ nhiều nguồn:

| Nguồn | Sự kiện có thể phát | Cần đối chiếu |
|---|---|---|
| KMS control plane | Yêu cầu destroy, lên lịch, hủy hoàn tất hoặc thất bại. | Trạng thái key resource và key version qua API quản trị. |
| HSM audit subsystem | Xóa key object, zeroization, thao tác quản trị hoặc lỗi thiết bị. | Thiết bị/cluster, operator, security domain và log phần cứng. |
| Orchestration service | Workflow bắt đầu, approval, retry và kết thúc. | Event thực tế từ backend; không chỉ dựa vào trạng thái workflow. |
| PKI/CA | Hủy khóa liên quan đến chứng thư hoặc tài khoản CA. | Trạng thái chứng thư, CRL/OCSP và việc xử lý private key. |
| Backup/recovery system | Xóa bản backup hoặc key replica. | Xác nhận bản sao không còn khả năng phục hồi theo policy. |
| Application audit | Ứng dụng ngừng tham chiếu hoặc hoàn tất di trú khóa. | Dữ liệu và backend; event ứng dụng không chứng minh zeroization. |

Khi tổng hợp sự kiện, cần lưu nguồn phát và mức tin cậy của nguồn. Một event từ orchestration service có thể chứng minh workflow đã chạy đến bước cuối, nhưng chỉ backend hoặc bằng chứng được công nhận mới xác nhận trạng thái hủy khóa.

## 7. Cấu trúc một audit event về hủy khóa

Audit event nên có schema ổn định, phiên bản hóa và không chứa key material. Một cấu trúc logic có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| event_id | Định danh duy nhất của event để chống xử lý trùng. |
| event_type | Ví dụ key.destroy.requested, key.destroy.scheduled, key.destroy.completed, key.destroy.failed. |
| event_version | Phiên bản schema. |
| occurred_at | Thời điểm sự kiện xảy ra theo UTC. |
| received_at | Thời điểm pipeline nhận được event. |
| source | KMS, HSM, orchestration service hoặc nguồn khác. |
| actor | Principal hoặc workload identity thực hiện thao tác. |
| key_id | Định danh khóa, không phải key material. |
| key_version | Phiên bản khóa bị tác động nếu nền tảng hỗ trợ version. |
| purpose/environment | Mục đích và môi trường của khóa. |
| action/result | Thao tác, trạng thái và kết quả. |
| request_id/correlation_id | Liên kết các bước của cùng workflow. |
| approval_id | Tham chiếu phê duyệt, nếu có. |
| reason | Lý do hủy đã được ghi nhận. |
| effective_at | Thời điểm hủy có hiệu lực hoặc dự kiến. |
| evidence_ref | Tham chiếu đến bằng chứng từ backend/HSM. |
| error_code | Mã lỗi nếu thao tác thất bại. |

Ví dụ event đã được giản lược:

~~~json
{
  "event_id": "evt-8f21c4",
  "event_type": "key.destroy.completed",
  "event_version": 1,
  "occurred_at": "2026-11-28T04:15:30Z",
  "received_at": "2026-11-28T04:15:31Z",
  "source": "kms-audit",
  "actor": "service:key-lifecycle-controller",
  "key_id": "key-prod-archive-042",
  "key_version": "v3",
  "purpose": "archive-encryption",
  "environment": "production",
  "action": "destroy",
  "result": "completed",
  "request_id": "req-7a91",
  "approval_id": "chg-2026-1182",
  "reason": "retention-period-expired",
  "effective_at": "2026-11-28T04:15:30Z",
  "evidence_ref": "kms-audit-record-59108"
}
~~~

Đây là schema minh họa, không phải định dạng chuẩn của một nhà cung cấp. Không đưa password, token, private key, DEK, KEK hoặc nội dung dữ liệu vào event. Nếu cần lưu lý do chi tiết, tránh đưa dữ liệu cá nhân hoặc thông tin nhạy cảm vào trường reason; dùng mã lý do và tham chiếu hồ sơ thay đổi.

## 8. Bảo vệ tính toàn vẹn và độ tin cậy của audit event

Audit event về hủy khóa phải được bảo vệ vì đây là bằng chứng cho một hành động có tác động lớn. Các kiểm soát cần cân nhắc:

- Gửi event từ nguồn thực thi đến hệ thống log độc lập với quyền ghi bị giới hạn.
- Bảo vệ log khỏi sửa đổi hoặc xóa trái phép; dùng storage bất biến hoặc cơ chế chống sửa đổi phù hợp.
- Đồng bộ thời gian và lưu timestamp UTC; theo dõi độ lệch đồng hồ giữa KMS, HSM và collector.
- Dùng event ID, request ID và correlation ID để nối các bước.
- Lưu source, schema version và metadata xác thực của nguồn phát.
- Mã hóa dữ liệu audit khi truyền và khi lưu; giới hạn quyền đọc.
- Giám sát event pipeline, subscription, queue, collector và dead-letter queue.
- Lưu bằng chứng approval độc lập với hệ thống thực thi hủy.

Một số event stream có thể giao nhận ít nhất một lần, dẫn đến event trùng; event cũng có thể đến trễ hoặc sai thứ tự. Consumer cần xử lý idempotent bằng event ID và không suy luận thứ tự chỉ từ thời điểm nhận. Nếu có sequence number hoặc trạng thái backend, hãy dùng chúng để đối chiếu tiến trình.

Không nên chỉ dựa vào event do chính ứng dụng yêu cầu hủy phát ra. Để có bằng chứng độc lập, cần đối chiếu event với trạng thái KMS/HSM hoặc audit record của backend. Nếu event pipeline mất kết nối, phải có khả năng truy vấn lại lịch sử hoặc đối chiếu trạng thái để phát hiện khoảng trống.

## 9. Monitoring và cảnh báo

Monitoring nên phát hiện cả hành động hợp lệ nhưng có rủi ro cao lẫn hành động sai policy. Một số cảnh báo quan trọng:

| Điều kiện | Mức độ gợi ý | Hành động |
|---|---|---|
| Khóa production bị destroy ngoài change window. | Critical | Xác minh ngay actor, approval và trạng thái backend. |
| Destroy không có approval ID hoặc người phê duyệt độc lập. | High/Critical | Tạm dừng workflow nếu còn có thể; điều tra quyền và quy trình. |
| Một principal hủy nhiều khóa trong thời gian ngắn. | Critical | Kiểm tra hành vi hàng loạt, credential compromise và blast radius. |
| Khóa đang được ứng dụng tham chiếu bị lên lịch hủy. | High | Xác minh dependency, migration và owner. |
| Pending destruction vượt quá thời hạn dự kiến. | Medium/High | Kiểm tra workflow, backend và khả năng phục hồi. |
| Destroy thất bại liên tiếp. | High | Điều tra quyền, trạng thái thiết bị, quota hoặc backend outage. |
| Event completed nhưng API backend vẫn báo khóa active. | Critical | Xem đây là mâu thuẫn trạng thái; không đóng ticket. |
| Không nhận được audit event sau thao tác hủy. | High | Kiểm tra pipeline và truy vấn audit backend trực tiếp. |
| Hủy khóa backup/replica không có lịch hoặc phê duyệt. | High/Critical | Kiểm tra khả năng phục hồi và bản sao còn lại. |

Mức độ cảnh báo cần dựa trên phân loại khóa. Hủy khóa thử nghiệm có thể có mức rủi ro thấp hơn hủy khóa gốc CA, khóa ký phát hành, KEK production hoặc khóa bảo vệ backup. Tuy nhiên, khóa môi trường thấp vẫn cần audit để phát hiện quyền và quy trình bị lạm dụng.

### Theo dõi chỉ số

- Số lượng destroy request theo principal, key class và môi trường.
- Tỷ lệ request được phê duyệt, bị từ chối, thất bại và hoàn tất.
- Thời gian trung bình từ request đến scheduled và completed.
- Số khóa đang pending destruction.
- Số event bị trễ, trùng, sai thứ tự hoặc đưa vào dead-letter queue.
- Số lần backend báo trạng thái khác với event consumer.
- Số replica, backup hoặc key version chưa được xác nhận xử lý.

Đặt baseline theo loại khóa và lịch thay đổi. Cảnh báo dựa trên tốc độ hủy bất thường có thể phát hiện hành vi phá hoại sớm hơn chỉ kiểm tra một event riêng lẻ.

## 10. Xử lý event trong hệ thống giám sát

Một pipeline điển hình:

~~~text
KMS / HSM / Key lifecycle service
              |
              v
       Audit event source
              |
              v
    Secure event transport
              |
              v
       Event collector
              |
       +------+------+
       |             |
       v             v
  Immutable audit   Event processor
       |             |
       |             v
       |       Validate schema/source
       |             |
       |             v
       |       Deduplicate + correlate
       |             |
       |             v
       |       Query backend state
       |             |
       +-------> SIEM / alert / case
~~~

Consumer nên:

1. Xác minh nguồn, schema version và các trường bắt buộc.
2. Từ chối hoặc cách ly event thiếu key ID, event ID, source hoặc trạng thái.
3. Chống xử lý trùng bằng event ID.
4. Liên kết request, approval, scheduled event và completed event bằng correlation ID.
5. Kiểm tra trạng thái hiện tại từ backend khi event có tác động lớn.
6. Phát cảnh báo nếu không có approval, actor không hợp lệ hoặc trạng thái mâu thuẫn.
7. Lưu event gốc và kết quả xử lý để phục vụ điều tra.

Không tự động đánh dấu một key là destroyed chỉ vì consumer nhận event có chuỗi completed. Cần xác minh nguồn phát, trạng thái backend và mức bằng chứng mà chính sách yêu cầu. Với event từ nguồn chưa được xác thực, có thể lưu ở trạng thái unverified và tạo cảnh báo thay vì thay đổi trạng thái tài sản.

## 11. Ví dụ xử lý event bằng Java

Đoạn mã dưới đây minh họa cách kiểm tra các trường cơ bản và chống xử lý event trùng. Nó không phải một consumer hoàn chỉnh và không thay thế xác minh chữ ký, quyền truy cập, schema validation hoặc truy vấn KMS/HSM.

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class KeyDestroyEventHandler {
    private final Set<String> processedEventIds =
            ConcurrentHashMap.newKeySet();

    public void handle(KeyDestroyEvent event) {
        validate(event);

        if (!processedEventIds.add(event.eventId())) {
            return; // Event đã được xử lý trước đó.
        }

        try {
            if (!"key.destroy.completed".equals(event.eventType())) {
                recordLifecycleEvent(event);
                return;
            }

            recordCompletionCandidate(event);
            requestBackendStateVerification(
                    event.keyId(),
                    event.keyVersion(),
                    event.correlationId());
        } catch (Exception e) {
            // Cho phép retry nếu ghi nhận hoặc xác minh chưa hoàn tất.
            processedEventIds.remove(event.eventId());
            throw new IllegalStateException(
                    "Không xử lý được key destroy event", e);
        }
    }

    private void validate(KeyDestroyEvent event) {
        Objects.requireNonNull(event, "event");
        requireText(event.eventId(), "eventId");
        requireText(event.eventType(), "eventType");
        requireText(event.source(), "source");
        requireText(event.keyId(), "keyId");
        Objects.requireNonNull(event.occurredAt(), "occurredAt");
    }

    private void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu trường bắt buộc: " + field);
        }
    }

    private void recordLifecycleEvent(KeyDestroyEvent event)
            throws Exception {
        // Ghi event gốc vào audit store độc lập.
    }

    private void recordCompletionCandidate(KeyDestroyEvent event)
            throws Exception {
        // Ghi nhận ứng viên hoàn tất, chưa tự kết luận zeroization.
    }

    private void requestBackendStateVerification(
            String keyId,
            String keyVersion,
            String correlationId) throws Exception {
        // Truy vấn KMS/HSM và đối chiếu bằng chứng hủy.
    }

    public record KeyDestroyEvent(
            String eventId,
            String eventType,
            String source,
            String keyId,
            String keyVersion,
            String actor,
            Instant occurredAt,
            String correlationId) {
    }
}
~~~

Ví dụ dùng record nên yêu cầu JDK 16 trở lên. Tập event ID chỉ tồn tại trong bộ nhớ của một tiến trình, không đủ cho hệ thống phân tán hoặc khởi động lại. Production cần kho idempotency bền vững, cơ chế claim/lease nguyên tử khi có nhiều consumer, transaction hoặc quy trình tương đương, xác thực nguồn event và chính sách retry. Các thao tác ghi audit phải idempotent theo event ID vì có thể được gọi lại sau lỗi. Nếu bước truy vấn backend thất bại, phải giữ trạng thái chờ xác minh và retry; không được đánh dấu hoàn tất chỉ vì event đã được ghi nhận.

## 12. Điều tra khi phát hiện hủy khóa bất thường

Khi nhận cảnh báo, người trực vận hành cần xác định nhanh phạm vi và trạng thái:

1. Xác định key ID, phiên bản, owner, purpose, môi trường và mức phân loại.
2. Kiểm tra actor, workload identity, nguồn gọi, request ID và quyền tại thời điểm thao tác.
3. Đối chiếu approval/change ticket, lịch bảo trì và người phê duyệt.
4. Truy vấn trạng thái trực tiếp từ KMS/HSM; xác định khóa active, disabled, pending hay destroyed.
5. Kiểm tra event trước/sau, event trùng, event trễ và audit pipeline có bị gián đoạn không.
6. Xác định ứng dụng, dữ liệu, chứng thư, DEK, KEK, replica và backup phụ thuộc.
7. Nếu khóa chưa bị hủy hoàn toàn, dừng hoặc hủy lịch theo quyền khẩn cấp và quy trình được phê duyệt.
8. Nếu đã hủy, xác định khả năng phục hồi hợp lệ; không tự tạo khóa mới rồi giả định dữ liệu cũ có thể giải mã.
9. Thu thập log bất biến, bằng chứng backend, approval và timeline để điều tra.
10. Cập nhật policy, quyền hoặc cảnh báo sau khi xác định nguyên nhân gốc.

Nếu nghi ngờ tài khoản quản trị bị chiếm quyền, cần thu hồi phiên/token và chặn principal ở lớp IAM/KMS theo quy trình sự cố. Việc này không thay thế đánh giá trạng thái khóa đã bị tác động.

### Hủy nhầm khóa production

Nếu khóa vẫn trong recovery window, ưu tiên kiểm tra khả năng cancel scheduled deletion hoặc restore theo quy trình nền tảng. Sau khi khôi phục, xác minh lại quyền, trạng thái, phiên bản và khả năng thao tác trước khi mở lại dịch vụ.

Nếu key material đã bị hủy không thể phục hồi, cần xác định có bản backup hợp lệ và còn được phép sử dụng hay không. Với dữ liệu đã mã hóa, khả năng phục hồi phụ thuộc vào việc còn DEK hoặc KEK tương ứng trong bản backup. Nếu không còn khóa có thể mở gói, dữ liệu có thể mất khả năng giải mã vĩnh viễn. Ghi nhận rõ giới hạn thay vì khẳng định có thể khôi phục.

## 13. Retention và bằng chứng kiểm toán

Audit record về hủy khóa cần được lưu theo yêu cầu pháp lý, hợp đồng, phân loại dữ liệu và chính sách nội bộ. Bản ghi nên tồn tại độc lập với key resource vì metadata khóa có thể bị xóa sau khi hủy.

Một hồ sơ hoàn tất nên liên kết:

- Key ID, phiên bản, owner, purpose và phân loại.
- Yêu cầu hủy, lý do, người yêu cầu và thời điểm.
- Phê duyệt, người phê duyệt và điều kiện dual control.
- Event scheduled, completed, failed hoặc cancelled.
- Nguồn event, request/correlation ID và trạng thái backend.
- Bằng chứng zeroization hoặc cryptographic erasure theo mức nền tảng hỗ trợ.
- Danh sách replica, backup và bản sao đã được xử lý hoặc ngoại lệ còn tồn tại.
- Người xác minh và kết luận cuối cùng.

Không lưu key material trong hồ sơ audit. Bằng chứng có thể là audit record có chữ ký, reference ID, báo cáo thiết bị hoặc bản xác nhận của hệ thống quản lý khóa. Bảo vệ tính toàn vẹn, quyền truy cập và khả năng truy xuất của hồ sơ theo thời hạn lưu trữ.

## 14. Những sai lầm thường gặp

**Coi destroy request là destroy completed.** Yêu cầu chỉ thể hiện ý định. Phải theo dõi trạng thái backend và event hoàn tất.

**Coi disable là destroy.** Disable thường có thể đảo ngược và key material vẫn tồn tại. Phân biệt trạng thái trong event và dashboard.

**Coi xóa metadata là zeroization.** Xóa alias hoặc record không chứng minh key material đã bị xóa khỏi HSM, replica hay backup.

**Không theo dõi thời gian chờ.** Khóa có thể vẫn đang pending deletion và còn khả năng phục hồi. Phải có cảnh báo trước thời điểm hủy vĩnh viễn.

**Không kiểm tra dependency.** Hủy KEK có thể làm mất khả năng mở nhiều DEK; hủy CA key có thể ảnh hưởng chuỗi chứng thư hoặc khả năng ký.

**Bỏ qua bản sao và backup.** Bản backup còn phục hồi được có thể giữ lại key material hoặc khả năng giải mã sau khi khóa chính bị hủy.

**Tin event do ứng dụng tự phát.** Event ứng dụng không đủ làm bằng chứng zeroization. Đối chiếu nguồn KMS/HSM và trạng thái backend.

**Không chống event trùng hoặc sai thứ tự.** Consumer có thể xử lý lặp hoặc đánh dấu sai trạng thái. Dùng event ID, correlation và xác minh trạng thái.

**Không giám sát khoảng trống audit.** Không nhận event có thể là lỗi pipeline hoặc hành vi vô hiệu hóa logging. Theo dõi heartbeat, sequence và truy vấn đối chiếu.

**Không lưu hồ sơ độc lập.** Nếu audit log bị xóa cùng key metadata, tổ chức mất bằng chứng về ai đã hủy và hủy theo quy trình nào.

## 15. Checklist giám sát Key destroyed event

- [ ] Có định nghĩa riêng cho requested, approved, scheduled, pending, completed, failed và cancelled.
- [ ] Chỉ nguồn thực thi đáng tin cậy được dùng để xác nhận destroy completed.
- [ ] Event có event ID, source, actor, key ID/version, timestamp, result và correlation ID.
- [ ] Event không chứa password, token hoặc key material.
- [ ] Có phê duyệt độc lập cho khóa quan trọng và thao tác rủi ro cao.
- [ ] Có kiểm tra dependency trước khi hủy và kiểm tra backend sau khi hủy.
- [ ] Có rà soát replica, backup, snapshot, bản export và key version liên quan.
- [ ] Consumer xử lý event trùng, trễ, sai thứ tự và lỗi schema.
- [ ] Event pipeline có giám sát độ trễ, dead-letter queue và khoảng trống dữ liệu.
- [ ] Có cảnh báo cho hủy ngoài lịch, thiếu approval, hủy hàng loạt và pending quá hạn.
- [ ] Audit log bất biến hoặc có cơ chế phát hiện sửa đổi, được lưu độc lập.
- [ ] Có runbook cho hủy nhầm, destroy thất bại và nghi ngờ quyền quản trị bị xâm phạm.

Key destroyed event là bằng chứng quan trọng trong vòng đời khóa, nhưng chỉ có ý nghĩa khi trạng thái và nguồn phát được hiểu đúng. Phân biệt yêu cầu hủy với hủy hoàn tất, xác minh kết quả từ KMS/HSM, rà soát bản sao và bảo vệ audit log giúp tổ chức chứng minh việc hủy được thực hiện có kiểm soát. Monitoring tốt còn phát hiện sớm hành vi bất thường và giảm nguy cơ mất dữ liệu do hủy nhầm hoặc phá hoại.

# Key rotation

## 1. Audit phải trả lời được khóa đã đổi đến đâu

Một dịch vụ tạo phiên bản khóa mới, nhận phản hồi thành công từ hệ thống quản lý khóa rồi ghi “rotation completed”. Tuy nhiên, hai worker vẫn dùng phiên bản cũ để tạo dữ liệu mới, bản backup còn cần khóa cũ để giải mã và không ai biết tài khoản nào đã yêu cầu thay đổi. Dòng log có tồn tại nhưng chưa đủ để chứng minh vòng chuyển đổi đã hoàn tất.

**Key rotation** là quá trình thay đổi khóa hoặc phiên bản khóa được sử dụng theo một phạm vi và chính sách xác định. Trong chương Logging và audit, trọng tâm là tạo bằng chứng về quyết định, hành động, kết quả và các điều kiện chuyển tiếp của quá trình đó.

Không cần đưa key material vào audit để chứng minh đã rotation. Thông tin cần thiết thường là định danh khóa, phiên bản, mục đích sử dụng, chủ thể thực hiện, trạng thái và tham chiếu tới bằng chứng được phép lưu.

Trong module yêu cầu bảo mật, mục tiêu là chuyển rủi ro của việc quản lý khóa thành yêu cầu đo được, liên kết với phân quyền, bảo vệ dữ liệu, logging và phục hồi. Sau bài này, người học có thể:

- Phân biệt tạo phiên bản mới, chuyển sử dụng mới và ngừng sử dụng phiên bản cũ.
- Đặc tả sự kiện audit cho từng mốc có ý nghĩa.
- Thiết kế schema không mang key material hoặc credential quản trị.
- Xác định bằng chứng để tuyên bố rotation hoàn tất trong phạm vi cụ thể.
- Kiểm thử retry, thất bại từng phần, phục hồi và tính kiểm chứng của lịch sử.

## 2. Khóa logic, phiên bản và mục đích sử dụng

### 2.1. Một tên khóa có thể đại diện cho nhiều phiên bản

Cần tách các khái niệm sau:

| Khái niệm | Ý nghĩa | Ví dụ không chứa secret |
|---|---|---|
| Khóa logic | Đối tượng quản lý phục vụ một mục đích | `payment-record-encryption` |
| Phiên bản khóa | Một phiên bản cụ thể trong vòng đời đối tượng | Tham chiếu phiên bản do registry quản lý |
| Alias hoặc active reference | Tên hoặc con trỏ được dùng để chọn phiên bản | `current-encryption-version` |
| Key material | Dữ liệu mật mã thực tế | Không ghi vào audit thông thường |
| Mục đích sử dụng | Phép toán và phạm vi khóa được phép phục vụ | Encrypt, decrypt, sign, verify |

Một thay đổi alias chưa chứng minh mọi consumer đã dùng phiên bản mới. Consumer có thể giữ cache, cấu hình cố định hoặc một bản sao credential không còn đồng bộ.

Tên và ID của khóa cũng là metadata nội bộ cần quyền truy cập phù hợp. Việc chúng không phải key material không có nghĩa có thể công khai toàn bộ danh mục khóa và quan hệ hệ thống.

### 2.2. Rotation không phải một thao tác duy nhất cho mọi loại khóa

| Tình huống | Cần phân biệt trong audit |
|---|---|
| Khóa mã hóa dữ liệu | Phiên bản dùng mã hóa mới và phiên bản còn cần để giải mã dữ liệu cũ |
| Khóa ký | Phiên bản tạo chữ ký mới và thông tin cần để xác minh chữ ký lịch sử |
| Envelope encryption | Khóa mã hóa dữ liệu và khóa bảo vệ khóa; rewrap khác với mã hóa lại toàn bộ dữ liệu |
| Khóa bảo vệ audit | Khả năng kiểm chứng lịch sử khi bản thân khóa ký hoặc mã hóa audit được thay đổi |
| Credential ứng dụng | Chuyển credential ở bên cấp và bên dùng, cùng việc thu hồi giá trị cũ |

Không suy ra rằng gia hạn chứng thư luôn tạo key material mới. Cũng không gọi một thay đổi metadata là thay khóa nếu hệ thống chưa có bằng chứng cho điều đó.

Nếu module của dự án dùng thuật ngữ rotation cho API credential, cần ghi rõ phạm vi. Tránh gộp credential, khóa mã hóa và khóa ký vào một loại sự kiện không thể giải thích hành vi.

## 3. Trạng thái phải gắn với phép sử dụng

### 3.1. “Khóa cũ đã tắt” là một mô tả thiếu

Một phiên bản có thể không còn được phép mã hóa dữ liệu mới nhưng vẫn cần để giải mã dữ liệu đã tồn tại. Với khóa ký bất đối xứng, phần khóa bí mật không còn được dùng ký mới trong khi thông tin khóa công khai vẫn có thể cần cho việc xác minh lịch sử.

Vì vậy, schema nên ghi cả chuyển trạng thái và mục đích:

```text
v1: được dùng cho dữ liệu mới
  -> v2 được chuẩn bị
  -> v2 được chọn cho thao tác mới
  -> xác nhận consumer chuyển sang v2
  -> v1 bị chặn cho thao tác mới
  -> v1 chỉ còn phục vụ các nhu cầu lịch sử được cho phép
  -> ngừng các nhu cầu còn lại khi đủ điều kiện
  -> lên lịch hủy hoặc hủy theo vòng đời đã chốt
```

Đây là luồng minh họa, không phải state machine bắt buộc của mọi nhà cung cấp. Tên trạng thái thực tế phải được ánh xạ sang ý nghĩa kiểm chứng được.

### 3.2. Tách điều khiển, quan sát và kết luận

Ba phát biểu sau không đồng nhất:

1. Orchestrator đã gửi lệnh chuyển active version.
2. Hệ thống quản lý khóa xác nhận thay đổi có hiệu lực tại ranh giới của nó.
3. Tất cả consumer trong phạm vi đã ngừng dùng phiên bản cũ cho thao tác mới.

Mỗi phát biểu cần sự kiện và bằng chứng khác nhau. Một HTTP response thành công có thể chỉ xác nhận tiếp nhận lệnh, tùy hợp đồng API. Không dùng nó để thay thế việc xác nhận tác động.

Tương tự, “đã lên lịch hủy” không có nghĩa “đã hủy”. Audit phải giữ sự khác biệt và nêu mức bằng chứng mà hệ thống thực sự có, chẳng hạn xác nhận từ dịch vụ quản lý khóa. Không tự tuyên bố đã kiểm chứng thao tác vật lý ở một hạ tầng không quan sát được.

## 4. Rủi ro dẫn tới yêu cầu audit

| ID | Điều kiện và hành vi | Hậu quả có thể xảy ra |
|---|---|---|
| R-KR-01 | Chỉ ghi hoàn tất khi tạo được phiên bản mới | Consumer tiếp tục dùng phiên bản cũ nhưng hồ sơ thể hiện đã chuyển xong |
| R-KR-02 | Không ghi người yêu cầu, người thực thi hoặc policy | Không phân biệt thay đổi hợp lệ với thao tác trái phép |
| R-KR-03 | Ghi response quản trị hoặc object khóa thô | Key material, credential hoặc dữ liệu nhạy cảm đi vào kho audit |
| R-KR-04 | Mất sự kiện giữa thay đổi ở nhà cung cấp và ghi nhận tại ứng dụng | Trạng thái khóa thực tế khác lịch sử có thể truy vết |
| R-KR-05 | Hủy khóa cũ mà chưa kiểm tra dữ liệu, backup và nhu cầu lịch sử | Mất khả năng giải mã hoặc kiểm chứng cần thiết |
| R-KR-06 | Retry hoặc rotation đồng thời bị gộp sai | Không biết phiên bản nào thực sự có hiệu lực và thao tác nào thất bại |
| R-KR-07 | Thay khóa bảo vệ audit mà bỏ thông tin kiểm chứng cũ | Không kiểm chứng được lịch sử hoặc diễn giải sai tính toàn vẹn |
| R-KR-08 | Rollback tự bật lại khóa đã bị nghi xâm phạm | Khôi phục khả năng sử dụng một căn cứ tin cậy không còn phù hợp |

Ví dụ kịch bản có quan hệ nhân quả:

> Khi lệnh tạo phiên bản mới thành công, orchestrator ghi `KEY_ROTATION_COMPLETED` mà không xác nhận các worker đã chuyển phiên bản. Người vận hành dựa vào sự kiện đó để vô hiệu hóa phiên bản cũ, khiến một phần luồng ghi ngừng hoạt động hoặc một bản backup không còn được giải mã theo nhu cầu phục hồi đã chốt.

Biện pháp không chỉ là “ghi thêm log”. Cần sửa định nghĩa hoàn tất, danh mục consumer, điều kiện vô hiệu hóa và loại bằng chứng phải thu.

## 5. Danh mục sự kiện theo vòng đời

Các tên dưới đây là ví dụ thiết kế, không đại diện cho event chuẩn của một nhà cung cấp cụ thể.

| Sự kiện | Sự thật cần thể hiện | Điều chưa được suy ra |
|---|---|---|
| `KEY_ROTATION_REQUESTED` | Một yêu cầu có nguồn và phạm vi đã được tiếp nhận | Thay đổi đã xảy ra |
| `KEY_ROTATION_AUTHORIZED` | Yêu cầu đạt điều kiện phân quyền và phê duyệt áp dụng | Khóa mới đã được tạo |
| `KEY_VERSION_CREATED` | Nguồn có thẩm quyền xác nhận phiên bản mới được tạo | Consumer đã sử dụng phiên bản đó |
| `KEY_NEW_USE_ACTIVATION_CONFIRMED` | Phiên bản được chọn cho phép sử dụng mới tại ranh giới đã nêu | Mọi cache và consumer đã chuyển |
| `KEY_CONSUMER_ADOPTION_CONFIRMED` | Consumer thuộc phạm vi có bằng chứng chuyển sử dụng | Consumer khác hoặc dữ liệu lịch sử đã được xử lý |
| `KEY_DATA_TRANSITION_PROGRESS` | Một phạm vi rewrap hoặc migration có kết quả đối soát | Toàn bộ dữ liệu đã hoàn tất |
| `KEY_OLD_USE_RESTRICTED` | Phiên bản cũ bị hạn chế với những phép sử dụng cụ thể | Key material đã bị hủy |
| `KEY_DESTRUCTION_SCHEDULED` | Một yêu cầu hủy theo lịch đã được chấp nhận | Thao tác hủy cuối cùng đã hoàn tất |
| `KEY_DESTRUCTION_CANCELLED` | Việc hủy theo lịch được hủy theo thẩm quyền | Khóa tự động trở lại mọi quyền sử dụng cũ |
| `KEY_DESTRUCTION_CONFIRMED` | Có xác nhận hủy theo mức bằng chứng của nguồn | Đã quan sát mọi bản sao ngoài phạm vi nguồn |
| `KEY_ROTATION_FAILED` | Một bước xác định thất bại | Các bước trước chắc chắn đã rollback |
| `KEY_ROTATION_COMPLETED` | Các tiêu chí hoàn tất cho phạm vi đã được xác minh | Mọi khóa cũ ở mọi hệ thống đều đã bị hủy |

Không nhất thiết mọi dự án đều cần đủ các loại trên. Cần chọn theo kiến trúc và mô hình rủi ro, đồng thời bảo đảm trạng thái thất bại, bị hủy và chưa xác định không bị biến thành thành công.

Rotation tự động cũng cần nguồn gốc: service thực thi, policy hoặc lịch áp dụng, thay đổi cấu hình lịch và phiên bản liên quan. Không gán một tên người dùng giả cho thao tác do hệ thống thực hiện.

## 6. Schema: ai, khóa nào, làm gì, bằng chứng ở đâu?

### 6.1. Những field có mục đích rõ

| Nhóm | Field minh họa | Nguồn cần tin cậy |
|---|---|---|
| Hợp đồng | `schemaVersion`, `eventType` | Registry schema và producer được quản lý |
| Liên kết | `eventId`, `rotationId`, `operationId` | Trạng thái orchestration hoặc hệ thống nguồn |
| Chủ thể | `initiatorRef`, `executorRef`, `actorType` | Ngữ cảnh xác thực và ủy quyền đã xác minh |
| Thẩm quyền | `policyRevision`, `approvalRef`, `reasonCode` | Kết quả đánh giá và hồ sơ được tham chiếu |
| Đối tượng | `keyRef`, `previousVersionRef`, `targetVersionRef` | Registry hoặc metadata nguồn có thẩm quyền |
| Phạm vi | Tenant, môi trường, mục đích, nhóm consumer | Context được xác nhận, không chỉ header client |
| Chuyển trạng thái | Trạng thái trước, sau và phép sử dụng | Kết quả quan sát đúng ranh giới |
| Kết quả | `SUCCEEDED`, `FAILED`, `UNKNOWN` và mã nguyên nhân | Mapping an toàn từ kết quả thực tế |
| Thời gian | Thời điểm xảy ra, thời điểm quan sát hoặc ingest | Nguồn thời gian và ý nghĩa riêng của từng field |
| Bằng chứng | ID sự kiện nhà cung cấp, batch hoặc bản đối soát | Nơi lưu có quyền truy cập và nội dung phù hợp |

Initiator là chủ thể khởi tạo; executor là principal thực hiện lời gọi. Một nhân sự yêu cầu rotation qua worker không nên bị ghi thành chính worker là người duy nhất có liên quan, hoặc ngược lại giả rằng nhân sự trực tiếp thực hiện mọi API call.

Phê duyệt bổ sung hoặc phân tách nhiệm vụ phụ thuộc chính sách của hành động. Nếu có, audit cần liên kết được bằng chứng áp dụng; không tự bịa approval khi luồng đó không có bước phê duyệt.

### 6.2. Ví dụ xác nhận chuyển phiên bản cho thao tác mới

```json
{
  "schemaVersion": 1,
  "eventType": "KEY_NEW_USE_ACTIVATION_CONFIRMED",
  "eventId": "3fad334a-2e1b-4104-bd9a-7385d8672f33",
  "rotationId": "72e5221d-14f4-4aa9-9993-6c95a11e0e0d",
  "operationId": "activate-new-encryption-version",
  "initiatorRef": "usr-operations-17",
  "executorRef": "svc-key-rotation",
  "keyRef": "payment-record-encryption",
  "previousVersionRef": "version-004",
  "targetVersionRef": "version-005",
  "purpose": "ENCRYPT_NEW_DATA",
  "observationBoundary": "key-management-control-plane",
  "outcome": "SUCCEEDED",
  "reasonCode": "SCHEDULED_ROTATION",
  "policyRevision": "key-policy-r9",
  "occurredAt": "2026-11-27T04:20:00Z",
  "evidenceRef": "provider-event-fixture-81"
}
```

Mọi giá trị là dữ liệu tổng hợp. Event chỉ xác nhận mốc ở control plane đã nêu. Các consumer chưa được xác nhận chuyển sử dụng cần có trạng thái riêng; không đổi tên event thành “hoàn tất toàn hệ thống”.

`evidenceRef` phải trỏ tới bằng chứng được kiểm soát. Không nhúng URL có token truy cập hoặc toàn bộ response quản trị vào field này.

### 6.3. Dữ liệu bị cấm trong audit thông thường

- Key material dạng bản rõ, private key, khóa đối xứng hoặc seed.
- Credential gọi dịch vụ quản lý khóa, access token, cookie và header xác thực.
- Secret được bọc trong object cấu hình, exception, request dump hoặc connection string.
- Dữ liệu bản rõ cần mã hóa, payload ký hoặc dữ liệu nghiệp vụ không cần cho mục đích audit.
- Blob khóa đã wrap hoặc bản export khóa nếu chưa có mục đích và chính sách xử lý riêng phù hợp.

Một blob đã mã hóa không tự trở thành dữ liệu nên đưa vào log rộng quyền. Tránh sao chép vật liệu hoặc artifact khóa khi chỉ cần tham chiếu phiên bản.

Không tự băm khóa bí mật để tạo fingerprint cho audit. Nếu cần fingerprint của thông tin khóa công khai, hãy định nghĩa rõ nguồn và mục đích theo định dạng mà dự án sử dụng. Metadata lấy từ registry thường phù hợp hơn việc để logger tiếp xúc key material.

## 7. Ví dụ Java: DTO xác nhận activation chỉ chứa metadata

Ví dụ dùng Java 17 trở lên và tham chiếu UUID nội bộ của registry. Nó minh họa một sự kiện hẹp: nguồn có thẩm quyền đã xác nhận activation cho thao tác mới. Nó không thực hiện phép toán mật mã hay rotation thật.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class KeyRotationAudit {
    private KeyRotationAudit() {}

    public enum Purpose {
        ENCRYPT_NEW_DATA,
        CREATE_NEW_SIGNATURE
    }

    public enum EventType {
        KEY_NEW_USE_ACTIVATION_CONFIRMED
    }

    public record VersionRef(UUID keyRef, UUID versionRef) {
        public VersionRef {
            Objects.requireNonNull(keyRef);
            Objects.requireNonNull(versionRef);
        }
    }

    public record ConfirmedActivation(
        UUID rotationId,
        UUID initiatorRef,
        UUID executorRef,
        VersionRef previousVersion,
        VersionRef targetVersion,
        Purpose purpose,
        UUID evidenceRef,
        Instant occurredAt
    ) {
        public ConfirmedActivation {
            Objects.requireNonNull(rotationId);
            Objects.requireNonNull(initiatorRef);
            Objects.requireNonNull(executorRef);
            Objects.requireNonNull(previousVersion);
            Objects.requireNonNull(targetVersion);
            Objects.requireNonNull(purpose);
            Objects.requireNonNull(evidenceRef);
            Objects.requireNonNull(occurredAt);

            if (!previousVersion.keyRef().equals(targetVersion.keyRef())) {
                throw new IllegalArgumentException("KEY_SCOPE_MISMATCH");
            }
            if (previousVersion.versionRef().equals(targetVersion.versionRef())) {
                throw new IllegalArgumentException("VERSION_NOT_CHANGED");
            }
        }
    }

    public record ActivationEvent(
        int schemaVersion,
        EventType eventType,
        UUID eventId,
        ConfirmedActivation activation
    ) {}

    public static ActivationEvent create(
        UUID eventId,
        ConfirmedActivation activation
    ) {
        return new ActivationEvent(
            1,
            EventType.KEY_NEW_USE_ACTIVATION_CONFIRMED,
            Objects.requireNonNull(eventId),
            Objects.requireNonNull(activation)
        );
    }
}
```

Các lựa chọn có ý nghĩa bảo mật:

- Schema không nhận key object, byte của khóa, credential hoặc Throwable.
- Định danh phiên bản và bằng chứng là tham chiếu nội bộ, không phải dữ liệu cấp quyền.
- Factory không tạo event ID hoặc thời điểm mới mỗi lần exporter retry.
- Mục đích bị giới hạn vào phép sử dụng mới, tránh diễn giải rằng khóa cũ đã bị hủy.
- Hai phiên bản phải thuộc cùng khóa logic trong mô hình minh họa này.

Tên `ConfirmedActivation` không tự chứng minh thao tác đã xảy ra. Record phải được dựng từ bằng chứng đã xác minh nguồn và ràng buộc với đúng operation. Không deserialize JSON do người dùng gửi rồi coi nó là xác nhận của hệ thống quản lý khóa.

Schema thực tế có thể bổ sung outcome, revision policy, môi trường và observation boundary theo allowlist. Nếu sự kiện mô tả di chuyển giữa hai khóa logic khác nhau, cần hợp đồng riêng thay vì bỏ kiểm tra phạm vi để dùng lại mẫu một cách tùy tiện.

## 8. Khi nào được ghi rotation completed?

### 8.1. Chốt điều kiện theo phạm vi

Một định nghĩa minh họa cho khóa mã hóa:

```text
Rotation được coi là hoàn tất cho phạm vi đã khai báo khi:
  phiên bản mới được tạo và xác minh phù hợp policy;
  lựa chọn phiên bản cho thao tác mới đã có hiệu lực;
  mọi consumer bắt buộc trong danh mục có bằng chứng chuyển sử dụng;
  phiên bản cũ bị chặn cho thao tác mới theo policy;
  nhu cầu giải mã, migration và phục hồi lịch sử có trạng thái rõ;
  các mốc bắt buộc có bằng chứng audit có thể đối soát;
  ngoại lệ còn lại được ghi đúng thẩm quyền và không bị tính là đã đạt.
```

Nếu định nghĩa hoàn tất không yêu cầu hủy phiên bản cũ ngay, event phải ghi được sự khác biệt đó. Không dùng một cờ `completed = true` để khiến người đọc suy ra cả việc hủy.

“Mọi consumer” phải là một tập cụ thể theo revision danh mục. Nếu bỏ sót job chạy cuối tháng hoặc môi trường restore, kết luận toàn bộ có thể sai dù những consumer đang online đều đạt.

### 8.2. Chuyển dữ liệu và khóa là hai công việc liên quan nhưng khác nhau

Đổi phiên bản dùng mã hóa mới không tự làm ciphertext cũ chuyển sang phiên bản mới. Tùy kiến trúc, dữ liệu cũ có thể tiếp tục cần phiên bản cũ, được mã hóa lại hoặc có phần khóa dữ liệu được rewrap.

Trong envelope encryption, rewrap một data key dưới khóa bảo vệ mới không đồng nghĩa đã mã hóa lại toàn bộ dữ liệu bằng data key khác. Audit cần ghi đúng thao tác, batch, phạm vi và bằng chứng đối soát.

Không đếm số lệnh API thành số bản ghi đã chuyển thành công nếu lệnh có thể được retry hoặc một batch chỉ hoàn tất một phần. Phải đối chiếu trạng thái dữ liệu theo mô hình của migration.

### 8.3. Bằng chứng consumer đã chuyển

Bằng chứng có thể gồm cấu hình hiệu lực, phiên bản được chọn trong thao tác tổng hợp, trạng thái rollout và số liệu sử dụng theo phiên bản trong phạm vi quyền quan sát.

Một lần kiểm tra cấu hình chưa chắc chứng minh runtime đã xóa cache cũ. Ngược lại, không thấy sử dụng phiên bản cũ trong một khoảng ngắn chưa chứng minh một job hiếm chạy đã chuyển. Cần kết hợp bằng chứng theo inventory và chu kỳ hoạt động liên quan.

Không ghi mọi payload mã hóa hoặc ký chỉ để chứng minh có sử dụng phiên bản mới. Tham chiếu thao tác và metadata đã giảm dữ liệu thường phù hợp hơn.

## 9. Độ tin cậy của sự kiện và khoảng trống giữa các hệ thống

### 9.1. Chỉ định nguồn có thẩm quyền

Orchestrator có thẩm quyền về yêu cầu, tiến độ và quyết định điều phối. Hệ thống quản lý khóa có thẩm quyền về những thay đổi trong ranh giới của nó. Consumer có bằng chứng về cấu hình hoặc việc sử dụng tại runtime của chính nó.

Một event tổng hợp cần chỉ rõ đang dựa vào nguồn nào. Không thay sự kiện nhà cung cấp bằng một dòng “đã gửi lệnh”, hoặc nâng tự khai báo của consumer thành bằng chứng vượt quá điều đã quan sát.

Collector phải xác thực producer và giới hạn loại sự kiện được phát hành. Người có quyền đọc audit không được tự tạo xác nhận hủy hoặc activation như thể đến từ nguồn quản lý khóa.

### 9.2. Outbox không tạo transaction xuyên mọi nhà cung cấp

Một transaction cục bộ có thể gắn trạng thái orchestration với outbox. Tuy nhiên, thao tác ở dịch vụ quản lý khóa từ xa thường nằm ngoài transaction đó.

```text
Ghi ý định và operation ID
  -> gọi nguồn quản lý khóa theo hợp đồng
  -> nhận hoặc truy vấn kết quả có thể đối chiếu
  -> lưu trạng thái quan sát và outbox
  -> giao sự kiện tới kho audit
  -> đối soát trạng thái nguồn, orchestration và audit
```

Nếu tiến trình ngừng sau khi nguồn đã thay đổi nhưng trước khi lưu kết quả, hệ thống cần cơ chế truy vấn hoặc đối soát. Không tự ghi FAILED rồi giả định khóa chưa thay đổi.

Nếu không xác minh được kết quả, trạng thái UNKNOWN có ý nghĩa hơn thành công hoặc thất bại giả. Việc phục hồi phải ràng buộc với operation gốc, tránh tạo thêm phiên bản hoặc chuyển ngược trạng thái một cách không kiểm soát.

### 9.3. Retry và thay đổi đồng thời

Giữ nguyên event ID cho các lần giao nhận lại cùng sự kiện logic. Một lần thử operation mới có thể có attempt ID riêng nhưng vẫn liên kết với rotation ID và bước tương ứng.

Cần phân biệt giao lại event với thực hiện lại lệnh. Dedup ở kho audit không tự ngăn việc lệnh rotation đã được gọi hai lần.

Với rotation đồng thời, nên có điều kiện trạng thái hoặc version kỳ vọng theo thiết kế. Một yêu cầu chuẩn bị từ v4 không được âm thầm ghi đè activation sang v6 sau khi một yêu cầu khác đã chuyển từ v4 sang v5 mà không xử lý xung đột.

Nếu dùng sequence hoặc revision, phải xác định nguồn cấp và phạm vi của nó. Timestamp một mình không bảo đảm thứ tự nhân quả giữa nhiều producer.

### 9.4. Audit không khả dụng

Nếu policy yêu cầu ghi ý định bền vững trước một thao tác quản trị, không thực hiện thao tác khi điều kiện đó chưa đáp ứng. Nếu một outbox bền vững được chấp nhận, collector ngừng hoạt động có thể dẫn tới chờ gửi trong giới hạn đã chốt.

Với rotation tự động do nhà cung cấp thực hiện, ứng dụng có thể không điều khiển được thời điểm thao tác. Khi đó, yêu cầu cần tập trung vào thu nhận nguồn, phát hiện khoảng trống và đối soát theo khả năng thực tế. Không tuyên bố có thể chặn thao tác ở một ranh giới mình không kiểm soát.

## 10. Bảo vệ kho audit và dữ liệu lịch sử

### 10.1. Phân quyền trên lịch sử quản trị khóa

Tách quyền yêu cầu rotation, thực thi, đọc audit, export và quản lý thời hạn lưu theo nhu cầu của tổ chức. Producer thường chỉ cần ghi trong phạm vi của nó, không cần quyền sửa lịch sử.

Quản trị một tenant không tự có quyền xem tên khóa, consumer hoặc incident của tenant khác. API tìm kiếm audit phải kiểm soát phạm vi, không chỉ kiểm tra người dùng đã đăng nhập.

Append-only, lưu trữ chống sửa đổi hoặc cơ chế kiểm chứng toàn vẹn có thể hỗ trợ yêu cầu cụ thể. Chúng không chứng minh nội dung do một producer bị xâm phạm ghi ra là sự thật. Mô hình đe dọa phải nêu rõ ai có thể tạo, sửa, xóa hoặc giữ lại sự kiện.

### 10.2. Thay khóa bảo vệ chính audit

Nếu audit được ký, bản ghi cần liên kết với thông tin đủ để xác minh đúng phiên bản khóa và thuật toán theo hợp đồng. Thay khóa ký mới không tự xác minh lại lịch sử; thông tin kiểm chứng cũ phải được quản lý theo nhu cầu lưu giữ.

Với chữ ký bất đối xứng, lưu thông tin khóa công khai phù hợp có thể phục vụ xác minh lịch sử mà không cần tiếp tục dùng private key cũ để ký mới. Không suy rộng cách làm đó sang mọi cơ chế MAC hoặc khóa đối xứng, nơi mô hình quản lý bí mật khác.

Nếu audit được mã hóa, việc bỏ khóa giải mã cũ có thể làm mất khả năng đọc lịch sử còn cần giữ. Cần đối chiếu thời hạn dữ liệu, phương án chuyển đổi và phục hồi trước khi hủy.

### 10.3. Khóa bị xâm phạm làm thay đổi cách tin bằng chứng

Một chữ ký kiểm tra được về mặt mật mã không tự chứng minh nó được tạo trước thời điểm khóa bị lộ. Nếu người khác có khả năng ký, họ có thể tạo thêm dữ liệu có chữ ký phù hợp với khóa đó.

Do đó, khi đánh giá lịch sử sau sự cố, cần chính sách về thời điểm, nguồn lưu độc lập, bằng chứng đã tồn tại và giới hạn tin cậy. Chỉ giữ public key cũ không giải quyết toàn bộ câu hỏi về nguồn gốc và thời điểm của bản ghi.

Audit cho rotation khẩn cấp nên liên kết incident, mốc thay đổi mức tin cậy và quyết định xử lý lịch sử. Không sửa âm thầm các event cũ để chúng trông như được tạo bằng khóa mới.

## 11. Rotation khẩn cấp, rollback và phục hồi

### 11.1. Trường hợp khẩn cấp khác với bảo trì định kỳ

Rotation do nghi ngờ xâm phạm có thể không cho phép giữ cửa sổ sử dụng khóa cũ như kế hoạch định kỳ. Cần đặc tả mục tiêu bảo vệ, tác động tới consumer và thẩm quyền quyết định.

Không dùng một khoảng overlap cố định cho mọi loại khóa. Với dữ liệu hoặc chữ ký cũ, điều kiện giữ khả năng giải mã hoặc xác minh còn phụ thuộc mục đích và mô hình rủi ro. Với credential dùng truy cập, yêu cầu thu hồi lại có ý nghĩa khác.

Reason code nên phân biệt bảo trì, thay đổi policy, sự cố và thao tác thủ công. Chi tiết nhạy cảm của incident có thể nằm ở hồ sơ hạn chế quyền, còn audit giữ reference phù hợp.

### 11.2. Rollback phải tạo lịch sử mới

Nếu chuyển phiên bản thất bại, ghi trạng thái thực tế của từng bước và hành động khắc phục. Không xóa các event activation trước đó để khiến lịch sử trông như chưa có thay đổi.

Không rollback sang một phiên bản đã bị đánh dấu không còn đáng tin cậy chỉ để khôi phục dịch vụ nhanh. Phương án phục hồi phải đáp ứng điều kiện bảo mật đang có hiệu lực.

Sau khi key material đã bị hủy theo mô hình nguồn, khả năng quay lại có thể không còn. Một câu “rollback nếu cần” không thay thế việc kiểm tra trước các hậu quả không thể đảo ngược.

### 11.3. Backup và môi trường khôi phục

Inventory cần xem xét dữ liệu cũ, backup, bản sao, batch chưa chuyển và các khóa liên quan tới việc đọc chúng. Restore có thể đưa cấu hình hoặc ciphertext dùng phiên bản cũ trở lại.

Diễn tập phục hồi phải xác minh điều kiện sử dụng khóa, policy hiện tại và khả năng giải mã hoặc kiểm chứng theo nhu cầu đã chốt. Không tự bật lại quyền dùng khóa cũ chỉ vì restore gặp lỗi.

Rotation không tự xóa dữ liệu, và hủy một khóa không mặc nhiên chứng minh mọi bản sao dữ liệu đã không thể đọc. Còn phải xét các phiên bản, bản sao khóa, đường wrap khác và dữ liệu đã giải mã ngoài phạm vi. Mọi tuyên bố cần bám theo ranh giới có bằng chứng.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

Các mã sau là mẫu đặc tả, không phải chứng nhận rằng một sản phẩm đã đáp ứng.

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| KR-AUD-01 | Mỗi loại rotation có phạm vi, mục đích, phiên bản và tiêu chí hoàn tất rõ | Hợp đồng lifecycle cùng inventory revision |
| KR-AUD-02 | Yêu cầu, tác động được xác nhận, consumer adoption và hủy được phân biệt bằng ngữ nghĩa sự kiện | Schema và state machine |
| KR-AUD-03 | Audit liên kết initiator, executor, policy và bằng chứng thẩm quyền áp dụng | Context tin cậy và hồ sơ ủy quyền |
| KR-AUD-04 | Event không chứa key material, credential, payload thô hoặc exception chưa được kiểm soát | Canary và kiểm tra mọi sink trong phạm vi |
| KR-AUD-05 | Event ID ổn định khi giao nhận lại; operation và rotation có liên kết riêng | Thử retry, dedup và đối soát |
| KR-AUD-06 | Khoảng trống giữa nguồn quản lý khóa, orchestration và audit có cơ chế phát hiện cùng xử lý UNKNOWN | Diễn tập dừng tiến trình tại các mốc |
| KR-AUD-07 | Chỉ producer có quyền phù hợp phát hành sự kiện có thẩm quyền; đọc và export đúng tenant hoặc phạm vi | Kiểm thử nguồn giả và ma trận quyền |
| KR-AUD-08 | Hoàn tất yêu cầu đủ bằng chứng cho mọi consumer bắt buộc; phần chưa kiểm chứng không tính là đạt | Đối soát inventory, rollout và quan sát runtime |
| KR-AUD-09 | Hạn chế hoặc hủy phiên bản cũ có bằng chứng điều kiện dữ liệu, lịch sử và phục hồi theo policy | Kết quả migration, backup và diễn tập restore |
| KR-AUD-10 | Thất bại, rollback và rotation khẩn cấp giữ lịch sử cùng nguyên nhân an toàn | Ca lỗi từng phần và hồ sơ incident tổng hợp |
| KR-AUD-11 | Thay khóa bảo vệ audit không làm mất ngữ nghĩa, định danh và khả năng kiểm chứng cần thiết | Thử đọc hoặc xác minh bản ghi trước và sau rotation |
| KR-AUD-12 | Nguồn thời gian, retention, bản sao và replay được đặc tả; độ trễ cùng backlog có tín hiệu quan sát | Cấu hình hiệu lực và hồ sơ đối soát |

### 12.1. Đặc tả chi tiết cho tiêu chí hoàn tất

```text
Phạm vi:
  Khóa mã hóa bản ghi và tập consumer theo inventory revision đã chốt.

Sự kiện hoàn tất:
  Chỉ phát sinh sau khi các mốc bắt buộc có bằng chứng.

Các mốc:
  Phiên bản đích được xác nhận ở nguồn quản lý khóa.
  Consumer bắt buộc dùng phiên bản đích cho thao tác mới.
  Phiên bản trước bị hạn chế đúng phép sử dụng theo policy.
  Trạng thái dữ liệu cũ, migration và backup được đối soát.
  Audit các bước có thể truy vết bằng rotation và operation ID.

Không được suy ra:
  Tạo phiên bản mới không đồng nghĩa toàn bộ rotation hoàn tất.
  Hoàn tất rotation không đồng nghĩa phiên bản cũ đã bị hủy.

Giới hạn:
  Ghi riêng consumer chưa quan sát được và nguồn chưa có bằng chứng.
```

Nếu chỉ rotation cho một nhóm consumer, tên phạm vi và kết luận phải thể hiện nhóm đó. Không dùng kết quả cục bộ làm tuyên bố toàn hệ thống.

## 13. Kiểm thử bằng fixture và fault injection

### 13.1. Dùng dữ liệu tổng hợp

Fixture có thể dùng key reference, version reference và operation ID tổng hợp. Khi cần kiểm tra chống lộ, đặt canary không có quyền truy cập thật vào những vị trí có khả năng mang secret trong request, response hoặc exception thử.

Không ghi key material thật vào môi trường log chỉ để xem cơ chế lọc có hoạt động. Việc kiểm thử vòng đời có sử dụng khóa thử phải theo môi trường và ranh giới của dự án; bài học không yêu cầu tác động tới khóa production.

### 13.2. Ma trận kiểm thử minh họa

| Ca | Điều kiện kích hoạt | Điều kiện đạt |
|---|---|---|
| TC-KR-01 | Rotation bình thường trong phạm vi fixture | Các mốc đúng ngữ nghĩa, actor, version và evidence liên kết được |
| TC-KR-02 | Tạo phiên bản thành công nhưng chưa activation | Không phát sinh completed chỉ vì version mới tồn tại |
| TC-KR-03 | Activation được xác nhận nhưng một consumer chưa chuyển | Trạng thái chưa hoàn tất hoặc ngoại lệ thể hiện đúng policy |
| TC-KR-04 | Nguồn đổi trạng thái rồi tiến trình ngừng trước khi lưu kết quả | Đối soát phục hồi đúng, không giả rằng thao tác chưa xảy ra |
| TC-KR-05 | Timeout làm kết quả chưa xác định | Có UNKNOWN và cơ chế xác minh, không retry lệnh mù |
| TC-KR-06 | Giao lại cùng event hoặc thực hiện lại attempt | Dedup event không nhầm với trạng thái operation |
| TC-KR-07 | Hai rotation cùng kỳ vọng một active version | Xung đột được xử lý, audit không che mất thay đổi cạnh tranh |
| TC-KR-08 | Collector ngừng hoạt động hoặc backlog đầy | Hành vi theo mức bền vững đã chốt, có tín hiệu mất hoặc chờ dữ liệu |
| TC-KR-09 | Canary nằm trong object khóa, credential hoặc cause của exception | Không phát hành canary ở những sink bị cấm |
| TC-KR-10 | Người dùng hoặc producer không có quyền tạo event xác nhận | Không được giả mạo sự kiện có thẩm quyền |
| TC-KR-11 | Tenant hoặc vai trò khác tìm kiếm và export | Không đọc metadata hoặc bằng chứng ngoài phạm vi |
| TC-KR-12 | Lên lịch hủy, hủy lịch rồi xác nhận hủy | Các trạng thái phân biệt, không gọi lịch hủy là đã hủy |
| TC-KR-13 | Backup hoặc dữ liệu cũ còn cần phiên bản trước | Không bỏ qua điều kiện lịch sử khi hạn chế hoặc hủy |
| TC-KR-14 | Rotation khẩn cấp và đề xuất rollback về bản không đáng tin | Không tự khôi phục quyền dùng bản đó; quyết định có truy vết |
| TC-KR-15 | Khóa bảo vệ audit thay đổi | Đọc hoặc kiểm chứng lịch sử đạt hợp đồng, không đổi ID và thời điểm gốc |
| TC-KR-16 | Replay hoặc restore event cùng metadata cũ | Không coi là rotation mới, giữ thứ tự và giới hạn suy luận phù hợp |

### 13.3. Oracle cần xác nhận cả sự kiện và trạng thái

Không chỉ tìm một dòng `KEY_ROTATION_COMPLETED`. Cần đối chiếu trạng thái nguồn, orchestration, consumer và bằng chứng lịch sử theo điều kiện của ca.

Với ca timeout sau thay đổi, phải chứng minh nguồn đã thay đổi trước khi làm mất response. Nếu lệnh chưa tới nguồn, đó là lỗi trước tác động, không xác minh được nhánh UNKNOWN sau tác động.

Với ca chống lộ, cần biết exporter đã hoạt động, kiểm tra cả exception formatter và các sink phụ trong danh mục. Chưa thấy canary ngay trong kho trung tâm không đủ nếu pipeline còn trễ hoặc sampling làm bỏ sự kiện.

Các ca có kết luận hủy hoặc khả năng phục hồi phải nêu mức bằng chứng thực tế. Xác nhận của nguồn quản lý khóa và kiểm thử đọc dữ liệu là những loại bằng chứng khác nhau; không thay thế nhau bằng một status chung.

## 14. Vận hành và đối soát vòng đời

Các tín hiệu có ích có thể gồm rotation đang chờ quá giới hạn của policy, consumer chưa xác nhận, thao tác mới vẫn dùng phiên bản cũ, sự kiện nguồn chưa khớp audit, UNKNOWN chưa xử lý và backlog export.

Đặt ngưỡng theo nhu cầu dự án. Không dùng một lịch rotation hoặc khoảng overlap tùy ý làm quy tắc chung cho mọi loại khóa và mọi môi trường.

Metric nên dùng nhóm sự kiện, loại bước hoặc trạng thái có tập giá trị được kiểm soát. Rotation ID và thông tin chi tiết của key reference thường phù hợp hơn trong log có quyền tìm kiếm riêng, thay vì trở thành nhãn tăng không giới hạn của metric.

Đối soát phải biết nguồn gốc của số liệu. “Không thấy sử dụng khóa cũ” có thể là không có workload, thiếu collector hoặc một consumer chưa được quan sát; không phải lúc nào cũng là đã chuyển xong.

Khi nhà cung cấp hoặc policy tự rotation, kiểm tra cả thay đổi lịch, cấu hình tự động và sự kiện kết quả. Một lịch còn tồn tại không chứng minh lần chạy dự kiến đã thành công.

## 15. Truy vết từ rủi ro tới tiêu chí nghiệm thu

Một chuỗi minh họa:

```text
R-KR-01: tạo version mới bị ghi nhầm là rotation hoàn tất
  -> KR-AUD-01, KR-AUD-02, KR-AUD-08
  -> state machine tách creation, activation và adoption
  -> inventory consumer cùng tiêu chí completed
  -> TC-KR-01, TC-KR-02, TC-KR-03
  -> metadata nguồn, kết quả rollout và quan sát runtime
  -> kết luận trong phạm vi build, policy và inventory đã chốt
```

Hồ sơ nghiệm thu cần có build, phiên bản schema, policy, inventory consumer, cấu hình thu sự kiện, các ca đã chạy và giới hạn quan sát. Tham chiếu bằng chứng không được trở thành đường tải secret cho người đọc audit.

Một tiêu chí đo được có thể là:

> Với tập khóa, mục đích và consumer trong phạm vi nghiệm thu, mọi chuyển trạng thái bắt buộc có sự kiện logic đúng schema và nguồn; các ca thất bại từng phần không tạo kết luận hoàn tất giả; không có canary secret ở sink bị cấm; trạng thái nguồn và hồ sơ audit được đối soát trong cửa sổ đã chốt. Phần chưa có bằng chứng được ghi riêng, không tính là PASS.

Đây là kết luận theo phạm vi bằng chứng. Nó không khẳng định mọi bản sao khóa, mọi consumer chưa được liệt kê hoặc mọi thao tác vật lý bên ngoài ranh giới đều đã được kiểm chứng.

## 16. Thực hành đặc tả cho hệ thống thanh toán

Một hệ thống dùng khóa bảo vệ data key của bản ghi thanh toán và một khóa khác để ký audit. Job rotation tạo phiên bản mới, đổi alias và ghi một dòng “done”. Một worker giữ cache phiên bản cũ, bản backup chưa được diễn tập phục hồi và exporter có thể giao event lặp. Đội hỗ trợ có quyền đọc log rộng nhưng không có quyền quản trị khóa.

Hãy xây dựng một đặc tả gồm:

1. Phân biệt hai loại khóa, khóa logic, phiên bản và phép sử dụng được bảo vệ.
2. State machine và điều kiện hoàn tất cho từng phạm vi rotation.
3. Danh mục sự kiện tách yêu cầu, activation, adoption, rewrap và hủy.
4. Schema có initiator, executor, version, policy, outcome và bằng chứng không mang secret.
5. Cơ chế xử lý khi nguồn đã thay đổi nhưng ứng dụng chưa ghi kết quả.
6. Quy tắc retry, event ID, operation ID và xung đột rotation đồng thời.
7. Điều kiện hạn chế khóa cũ, nhu cầu backup và khả năng kiểm chứng audit lịch sử.
8. Phân quyền đọc, ghi, export và tham chiếu bằng chứng cho đội hỗ trợ.
9. Ma trận kiểm thử với consumer chưa chuyển, timeout, canary secret và replay.
10. Hồ sơ đối soát nêu rõ điều đã xác minh, điều còn UNKNOWN và người chịu trách nhiệm xử lý.

Kết quả cần cho người khác dựng lại được ai đã thay đổi điều gì, tại ranh giới nào, bằng chứng nào xác nhận tác động và vì sao một vòng rotation được coi là hoàn tất, trong khi dữ liệu khóa thực tế vẫn ở ngoài luồng audit thông thường.

# Export retention — Quản lý thời hạn lưu giữ bản xuất dữ liệu

## 1. Export là một bản sao cần có vòng đời riêng

Trong chương **Export Security** của Business Logic Security, export retention là tập quy tắc xác định bản xuất dữ liệu được lưu ở đâu, tồn tại bao lâu, khi nào không còn được truy cập và làm thế nào xác minh việc dọn bỏ những bản sao thuộc phạm vi quản lý.

Một file CSV, XLSX hoặc PDF xuất từ hệ thống thường tập hợp nhiều đối tượng và field trong một nơi. Quyền xem dữ liệu nguồn có thể thay đổi sau khi file được tạo, trong khi file vẫn còn ở object storage, thư mục tạm hoặc một URL tải đã phát hành. Vì vậy, xóa một dòng job trong database hoặc ẩn nút Download chưa đủ thực hiện retention.

Trong phạm vi module này, retention phải giữ các invariant nghiệp vụ:

- Người dùng chỉ được tải export còn trong thời hạn và đúng phạm vi quyền.
- Retry, tải lại hoặc thăm trang trạng thái không tự gia hạn bản xuất.
- Worker không được công bố lại export đã hết hạn, bị thu hồi hoặc đã hủy.
- Quá trình xóa đúng artifact của đúng tenant/job, không tác động dữ liệu nguồn hoặc file của job khác.
- Hệ thống không báo “đã xóa toàn bộ” khi vẫn còn những bản sao trong phạm vi cần xử lý.

Mục tiêu là thiết kế vòng đời có thể thực thi và kiểm chứng, thay vì chỉ gắn một field `expiresAt` lên response.

## 2. Phân biệt các mốc thời gian và phạm vi lưu giữ

### 2.1. Hết quyền tải khác với đã xóa payload

| Khái niệm | Ý nghĩa | Bằng chứng cần có |
| --- | --- | --- |
| Thời hạn truy cập | Đến thời điểm nào hệ thống còn chấp nhận yêu cầu tải mới | Gate kiểm tra thời gian và quyền ở đường tải |
| Hạn dọn payload đang hoạt động | Khi nào phải loại bỏ file ở kho phục vụ và nơi tạm liên quan | Kết quả xóa/đối soát artifact theo phạm vi |
| Thời hạn backup/bản sao khác | Bao lâu bản sao còn nằm trong hệ thống dự phòng hoặc lưu trữ riêng | Policy và cơ chế hết hạn/khôi phục tương ứng |
| Thời hạn metadata/audit | Giữ thông tin nào về job và quá trình xóa, trong bao lâu | Dữ liệu tối thiểu, quyền truy cập và lịch dọn riêng |

Một export hết quyền tải có thể đang chờ dọn. Một object không còn xuất hiện ở URL thông thường có thể vẫn có version cũ. Một metadata job còn tồn tại không có nghĩa phải giữ nguyên payload.

Không dùng cùng một nhãn mơ hồ `DELETED` để che tất cả những trạng thái này. Nếu chỉ xác minh đã dọn active storage, ghi rõ phạm vi đó.

### 2.2. Policy do server xác định

Thời hạn có thể phụ thuộc loại export, độ nhạy cảm, mục đích sử dụng và chính sách tổ chức. Client có thể chọn một loại báo cáo được cấp quyền nhưng không tự quyết định giữ dữ liệu vô hạn bằng `retentionDays`, `expiresAt` hoặc tag object tự khai.

Các con số trong bài chỉ phục vụ thiết kế kỹ thuật minh họa, không phải thời hạn áp dụng chung cho dữ liệu thật. Bản xuất tiện dụng và hồ sơ nghiệp vụ gốc có thể có vòng đời khác nhau; xóa export không đồng nghĩa xóa chứng từ hay dữ liệu nguồn.

### 2.3. Lập danh mục mọi bản sao được tạo

Một job có thể tạo nhiều artifact:

```text
file cuối dùng để tải
file staging trước khi publish
file tạm và dữ liệu spill trên worker
các chunk trung gian hoặc file nén
multipart upload chưa hoàn tất
version cũ và replica ở object storage
cache phân phối nếu có
bản sao trong backup hoặc snapshot hạ tầng
metadata, log và thông tin chẩn đoán liên quan
```

Nếu không biết mình đã tạo những bản sao nào, hệ thống khó chứng minh retention được thực hiện. Danh mục này cũng giúp tránh việc giữ lại một file tạm chứa đầy đủ dữ liệu sau khi file cuối đã được xóa.

## 3. Chọn deadline cố định, không trượt theo hoạt động

### 3.1. Định nghĩa rõ mốc bắt đầu

Một policy minh họa cho bản xuất nội bộ:

```text
requestedAt: lúc server chấp nhận job
firstReadyAt: lần đầu job được publish thành công
availability: 24 giờ tính từ firstReadyAt
maximumJobLifetime: 48 giờ tính từ requestedAt

accessExpiresAt = min(
  firstReadyAt + availability,
  requestedAt + maximumJobLifetime
)
```

Mốc giới hạn toàn job ngăn một job chậm hoặc bị retry liên tục tồn tại không giới hạn trước khi publish. Nếu worker hoàn thành sau giới hạn đó, không công bố file như một export mới còn đầy đủ thời gian tải; xử lý nó theo nhánh hết hạn và dọn staging.

### 3.2. Không lấy `updatedAt` làm thời điểm gia hạn ngầm

Các thao tác sau không được làm deadline tự chạy xa hơn trong hợp đồng này:

- Người dùng mở trang tiến độ.
- Gửi lại request cùng idempotency key.
- Worker báo heartbeat hoặc nhận lại message.
- Tải lại file hoặc xin lại URL tải.
- Cleanup retry sau lỗi lưu trữ.

`firstReadyAt` và deadline được ghi nhận theo một chuyển trạng thái có kiểm soát. Không gán lại chúng bằng thời điểm hiện tại mỗi lần consumer xử lý message READY.

Nếu sản phẩm cho phép gia hạn, đó là một operation riêng: cần quyền, lý do, giới hạn mới, kiểm tra trạng thái và audit. Không cho sửa trực tiếp `expiresAt` qua DTO cập nhật job thông thường.

### 3.3. Thời gian phải đến từ nguồn tin cậy

Lưu deadline dưới dạng thời điểm tuyệt đối, thống nhất cách dùng UTC/Instant. Trình duyệt có thể hiển thị theo múi giờ người dùng nhưng không quyết định thời hạn bằng đồng hồ của nó.

Định nghĩa biên rõ ràng: trong bài, request tải mới chỉ hợp lệ khi `now < accessExpiresAt`. Tại đúng thời điểm bằng deadline, export đã hết quyền tải. Các service tham gia cần có cơ chế đồng hồ và độ chính xác phù hợp với cam kết đó.

## 4. Mô hình dữ liệu và trạng thái không được mập mờ

### 4.1. Metadata tối thiểu cho vòng đời

```text
ExportJob
  jobId, tenantId, requestedBy
  exportKind, normalizedRequestFingerprint, policyVersion
  requestedAt, firstReadyAt, accessExpiresAt
  availabilityState
  artifactManifestId, generation
  revocationReason, cancellationState nếu có

ArtifactManifest
  jobId, generation, manifestVersion
  danh sách artifactRef do server quản lý
  loại bản sao, vị trí, version/generation lưu trữ
  kích thước/checksum cần thiết để nhận diện và đối soát

PurgeTask
  jobId, generation, manifestVersion
  purgeScope, state, attempt, lease/fencing data
  deleteDueAt, lastErrorCode, verifiedAt
```

Không dùng filename hiển thị hoặc object key client gửi làm định danh duy nhất để xóa. Artifact reference cần trỏ tới đối tượng cụ thể trong kho do hệ thống quản lý.

### 4.2. Tách khả năng phục vụ khỏi tiến độ dọn bỏ

Một mô hình minh họa:

```text
availabilityState:
  REQUESTED → RUNNING → READY
                        → EXPIRED
                        → REVOKED
  REQUESTED/RUNNING → FAILED hoặc CANCELLED

purgeState:
  PENDING → IN_PROGRESS → VERIFIED
                       → RETRYABLE_FAILURE
                       → BLOCKED
```

Export có thể đã EXPIRED nhưng purge vẫn PENDING. Nó phải bị chặn tải ngay, không chờ trạng thái purge đổi thành VERIFIED.

READY trong database cũng chưa đủ cho phép tải: nếu đồng hồ đã qua deadline nhưng sweeper chưa cập nhật EXPIRED, gate vẫn phải từ chối. Cách kiểm tra theo thời gian giúp tính đúng không phụ thuộc lịch chạy cleanup.

### 4.3. Không xóa metadata quá sớm

Nếu xóa job trước khi dọn object, worker có thể mất danh sách những gì phải xóa. Nếu xóa dấu vết hết hạn trước khi những message cũ hoặc backup cũ không còn khả năng quay lại, export có thể bị công bố lại ngoài ý muốn.

Giữ metadata/tombstone tối thiểu đủ để điều phối và chứng minh trong thời hạn đã chọn. Tombstone vẫn có thể chứa thông tin định danh, nên nó cũng cần quyền truy cập và retention riêng; không mặc nhiên giữ mọi chi tiết vĩnh viễn.

## 5. Chặn truy cập độc lập với tác vụ xóa

### 5.1. Đường tải phải xét quyền và deadline

Một request tải mới cần thỏa các điều kiện phù hợp:

```text
actor đã được xác thực
AND đúng tenant/job hoặc có quyền chia sẻ được cấp rõ
AND còn quyền tải loại dữ liệu của export theo policy
AND job đang có artifact READY hợp lệ
AND không bị thu hồi/hủy theo trạng thái áp dụng
AND thời điểm quyết định < accessExpiresAt
```

Quyền submit job không tự là quyền tải file mãi mãi. Khi phạm vi quyền đối tượng hoặc field đã đổi, hệ thống cần áp dụng chính sách đã công bố: xét quyền hiện hành, thu hồi export hoặc quyền đọc snapshot lịch sử riêng. Một bản sao chứa dữ liệu cũ không tự mang theo quyền đọc vĩnh viễn.

Kiểm tra cả các đường download, preview, HEAD, Range/resume và tải lại theo thiết kế thực tế. Ẩn nút trên UI không chặn được URL đã biết.

### 5.2. Chọn rõ cách xử lý stream đang chạy

Trong hợp đồng minh họa, hệ thống xét điều kiện ngay trước khi chấp nhận một lần tải; stream đã được chấp nhận trước deadline có thể hoàn tất. Một request resume mới sau deadline phải được xét lại và bị từ chối.

Nếu sản phẩm yêu cầu ngắt stream tại deadline hoặc khi thu hồi, cần một cơ chế truyền tải thực sự hỗ trợ và test riêng. Không suy ra khả năng đó từ việc xóa metadata hoặc hết hạn URL. Dữ liệu người dùng đã tải hợp lệ về thiết bị của họ không thể bị thu hồi từ xa chỉ bằng xóa file trên server.

### 5.3. Presigned URL có vòng đời riêng

Với đường tải trực tiếp qua URL ký, deadline của khả năng tải phải được giới hạn bởi các mốc liên quan:

```text
URL expiry <= min(
  accessExpiresAt,
  now + giới hạn thời gian link của server,
  thời hạn credential/khả năng ký tương ứng
)
```

Cần tính đúng độ chính xác mà provider hỗ trợ; không làm tròn lên khiến link vượt deadline. Không phát hành link có thời gian sử dụng không còn dương.

Amazon S3 mô tả presigned URL là bearer capability, chịu giới hạn của credential; S3 kiểm tra hết hạn khi nhận request và một download bắt đầu trước lúc hết hạn có thể tiếp tục sau đó. Xem [Amazon S3 — Using presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).

Khi đã phát URL trực tiếp, việc thay quyền trong ứng dụng không tự làm mọi request storage quay qua policy của ứng dụng. Nếu cần xét quyền hiện hành ở từng request, cân nhắc gateway tải có xác thực hoặc cơ chế thu hồi được thiết kế phù hợp. Đừng hứa thu hồi tức thời chỉ vì link có TTL ngắn.

Không ghi URL ký đầy đủ vào log hoặc công bố lại qua metadata công khai. Cache phân phối cũng cần giữ đúng giới hạn truy cập, thay vì phục vụ bản sao đã cache sau khi ứng dụng từ chối tải mới.

## 6. Minh họa Java: deadline cố định và gate tải

### 6.1. Tính deadline từ policy phía server

Ví dụ dùng `Instant` và `Duration`; các giá trị policy được quản lý bởi ứng dụng:

```java
public record ExportRetentionPolicy(
        Duration availability,
        Duration maximumJobLifetime) {
    public ExportRetentionPolicy {
        Objects.requireNonNull(availability);
        Objects.requireNonNull(maximumJobLifetime);
        if (availability.isNegative() || availability.isZero()
                || maximumJobLifetime.isNegative()
                || maximumJobLifetime.isZero()) {
            throw new IllegalArgumentException("Invalid retention policy");
        }
    }
}

public Instant accessDeadline(
        Instant requestedAt,
        Instant firstReadyAt,
        ExportRetentionPolicy policy) {
    if (firstReadyAt.isBefore(requestedAt)) {
        throw new IllegalArgumentException("Invalid export timestamps");
    }
    Instant fromReady = firstReadyAt.plus(policy.availability());
    Instant absoluteLimit = requestedAt.plus(policy.maximumJobLifetime());
    return fromReady.isBefore(absoluteLimit) ? fromReady : absoluteLimit;
}
```

Luồng publish chỉ tiếp tục nếu thời điểm publish vẫn nằm trước deadline tính được và chuyển trạng thái/generation còn hợp lệ. Deadline đã commit không bị tính lại từ một `firstReadyAt` mới khi retry.

### 6.2. Gate tải không phụ thuộc sweeper

```java
@Transactional(readOnly = true)
public AuthorizedArtifact authorizeDownload(UUID jobId) {
    Actor actor = currentActor.requireActiveTenantActor();
    ExportJob job = jobs.findInTenant(actor.tenantId(), jobId)
        .orElseThrow(ExportUnavailableException::new);

    authorization.requireCanDownload(actor, job);
    Instant decisionAt = clock.instant();
    if (job.availabilityState() != AvailabilityState.READY
            || job.accessExpiresAt() == null
            || !decisionAt.isBefore(job.accessExpiresAt())
            || job.artifactRef() == null) {
        throw new ExportUnavailableException();
    }

    return new AuthorizedArtifact(
        job.artifactRef(), job.generation(), job.accessExpiresAt(), decisionAt);
}
```

`Actor`, repository, policy và các kiểu domain là thành phần cần tự hiện thực. `AuthorizedArtifact` là descriptor nội bộ cho đường tải, không phải một token công khai được phép dùng lại bất kỳ lúc nào.

Điều kiện áp dụng:

- Actor/tenant lấy từ context tin cậy, không lấy từ query parameter `ownerId` hoặc body của client.
- Policy xét trạng thái thu hồi/hủy và quyền đọc nội dung phù hợp. Ví dụ không giả định quyền sở hữu job luôn đủ cho mọi loại export.
- Thời điểm quyết định và việc bắt đầu phục vụ phải theo ranh giới tải đã định nghĩa. Không xếp descriptor vào queue nhiều giờ rồi dùng nó mà không kiểm tra lại.
- Artifact reference cố định tới đúng generation/version, không mở một key chung mà worker khác có thể ghi đè nội dung.
- Response lỗi không cần tiết lộ job của tenant khác tồn tại hay không. Mã HTTP cụ thể tùy hợp đồng API.
- Transaction kiểm tra không nên bị giữ mở trong toàn bộ quá trình stream file lớn chỉ vì method có annotation; tách vòng đời truyền tải theo thiết kế phù hợp.

Mã này bảo vệ khả năng bắt đầu tải qua ứng dụng. Nó không thực hiện xóa payload, không tự thu hồi link trực tiếp đã phát và không thay thế cơ chế kiểm soát cache.

## 7. Dọn bỏ là một workflow có retry và bằng chứng

### 7.1. Luồng cleanup có thể thực hiện lại an toàn

Một quy trình minh họa:

```text
1. Chọn job/artifact tới hạn từ metadata tin cậy.
2. Claim purge task theo generation và manifest version.
3. Ghi nhận trạng thái không còn được phục vụ khi phù hợp; commit.
4. Xóa các artifact chính xác trong manifest, ngoài transaction DB kéo dài.
5. Đối soát kết quả theo phạm vi active storage đã chọn.
6. Ghi VERIFIED bằng cập nhật có điều kiện trên đúng claim/generation.
7. Nếu lỗi: ghi trạng thái có thể retry hoặc BLOCKED, không báo đã xóa.
```

Việc không còn object đúng phiên bản có thể được coi là kết quả idempotent thành công khi đã kiểm chứng bằng quyền/nguồn quan sát phù hợp. Lỗi permission, timeout hoặc mất kết nối không được tự quy thành “chắc là đã xóa”.

Một worker chết sau khi xóa object nhưng trước cập nhật metadata cần có thể nhận lại task và đối soát, thay vì tạo lại file để hoàn tất job.

### 7.2. Không xóa theo đường dẫn do client điều khiển

Cleanup chỉ làm việc trong namespace/kho được quản lý, dựa trên artifact ID và mapping phía server. Với file local, cần xác minh đường dẫn thực nằm trong vùng export được chỉ định và xử lý an toàn quan hệ đường dẫn theo hệ thống đang dùng.

Không dùng filename người dùng chọn, đường dẫn tương đối chưa kiểm chứng hoặc một prefix quá rộng làm mục tiêu xóa. Một job tenant A không được khiến cleanup xóa file của tenant B hoặc dữ liệu nguồn.

### 7.3. Chống worker cũ và file xuất hiện lại

Các race cần xử lý:

- Cleanup chọn generation G1 nhưng worker mới đã tạo G2.
- Worker G1 upload xong sau khi job bị hủy hoặc hết hạn.
- Một message READY cũ chạy sau khi purge đã được xác minh.
- Upload thành công nhưng worker chết trước khi đăng ký artifact vào metadata.

Dùng key/namespace riêng theo job và generation, chuyển trạng thái có điều kiện, lease/fencing phù hợp và tombstone để ngăn publish muộn. Chỉ một fencing token nằm trong log không ngăn được ghi file ngoài database; tài nguyên/đường publish cần thực thi kiểm tra tương ứng.

Manifest và cơ chế phát hiện orphan phải bao phủ khoảng trống giữa ghi object và cập nhật metadata. Có thể đăng ký ý định tạo artifact trước, dùng metadata/tag do server kiểm soát và inventory đối soát những artifact không được job hợp lệ tham chiếu.

Không coi một lần kiểm tra “không còn file” là bảo đảm vĩnh viễn nếu worker cũ vẫn có thể tái tạo cùng vị trí. Cần đóng đường ghi/publish muộn hoặc tiếp tục dọn orphan theo cam kết.

## 8. Object storage: lifecycle, version và multipart

### 8.1. Lifecycle là lớp hỗ trợ, không phải đồng hồ authorization

Object storage có thể hỗ trợ tự động hết hạn. Tuy nhiên, deadline truy cập của ứng dụng không nên phụ thuộc việc tác vụ storage đã thực sự chạy hay chưa.

AWS mô tả S3 Lifecycle xử lý expiration bất đồng bộ và không bảo đảm thời điểm hoàn tất chính xác. Xem [Amazon S3 — Lifecycle configuration considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/how-to-set-lifecycle-configuration-intro.html).

Do đó, có thể phối hợp lifecycle với worker dọn chủ động và đối soát. Nếu có yêu cầu dọn trước một deadline cụ thể, cần thiết kế khả năng đáp ứng/quan sát riêng, không chỉ trỏ vào rule cấu hình.

### 8.2. Delete marker không phải mọi byte đã biến mất

Trong bucket có versioning, expiration hoặc một thao tác xóa thông thường có thể tạo delete marker, còn phiên bản dữ liệu cũ trở thành noncurrent. AWS mô tả riêng việc xóa current và noncurrent version tại [Deleting object versions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html).

Manifest/purge policy cần biết có versioning không, version nào đã được tạo, replica nào thuộc phạm vi và cách xử lý noncurrent version. Kiểm tra GET không chỉ định version trả không thấy file chưa chứng minh một version cụ thể không còn đọc được.

Không chỉ kiểm tra `HEAD key` hiện hành nếu hệ thống từng phát URL trỏ version cũ. Cần bằng chứng phù hợp cho từng version/đích nằm trong phạm vi dọn, với quyền kiểm tra đáng tin cậy.

### 8.3. Multipart và file tạm có vòng đời riêng

Một multipart upload chưa hoàn tất không phải object cuối đã publish. S3 có hành động `AbortIncompleteMultipartUpload` để dọn các phần upload chưa hoàn tất; nó không xóa các object đã hoàn tất. Xem [Amazon S3 — Deleting incomplete multipart uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html).

Tương tự, worker có thể để lại chunk local, file nén tạm hoặc spill khi crash. Đặt thời hạn và cơ chế dọn phù hợp cho từng loại, gắn chúng với job/attempt khi có thể. Không chờ job READY mới bắt đầu theo dõi những bản sao này.

### 8.4. Khi storage khóa giữ lại dữ liệu

Một artifact có thể bị cơ chế retention lock hoặc hold ngăn xóa. Chẳng hạn S3 Object Lock bảo vệ object version khỏi bị xóa/ghi đè theo chế độ được cấu hình; xem [Amazon S3 — Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html).

Ứng dụng cần thể hiện BLOCKED và lý do phù hợp, tiếp tục chặn tải theo policy và chuyển việc xử lý tới vai trò quản trị có thẩm quyền. Không báo purge VERIFIED, không tự gỡ khóa và không âm thầm kéo dài quyền download vì payload chưa thể xóa.

## 9. Backup, replica và phục hồi không được làm sống lại export

### 9.1. Xác định retention theo từng bản sao

Backup có thể giữ dữ liệu lâu hơn kho phục vụ. Nếu điều đó thuộc thiết kế được chấp thuận, phải ghi rõ phạm vi, quyền đọc/khôi phục, thời điểm hết hạn và trạng thái dọn. Không dùng câu “đã xóa toàn bộ” để mô tả việc chỉ xóa bản đang phục vụ.

Mã hóa giúp bảo vệ dữ liệu lưu trữ nhưng không tự thực hiện deadline truy cập hoặc chứng minh mọi bản sao đã bị xóa. Checksum giúp nhận diện/đối soát artifact, không phải bằng chứng xóa.

### 9.2. Tombstone và policy hiện hành phải sống qua restore

Một backup cũ có thể chứa job READY và deadline chưa được cập nhật trạng thái EXPIRED. Khi restore:

- Gate tải vẫn kiểm tra thời gian hiện tại, không chỉ nhìn trạng thái trong backup.
- Áp dụng lại những tombstone/thu hồi có thẩm quyền mà bản restore chưa chứa.
- Không khôi phục đường public hoặc cache như một khả năng tải mới không kiểm tra quyền.
- Worker nhận message cũ vẫn bị kiểm tra generation, trạng thái và deadline.
- Dữ liệu phục hồi dùng để đối soát không tự được công bố thành export cho người dùng.

Cần giữ dấu vết vô hiệu hóa đủ lâu so với cửa sổ có thể phục hồi và tuổi message/job liên quan, hoặc có cơ chế tái dựng tương đương. Nếu dấu vết đó bị mất khi restore cùng một backup cũ, việc “có tombstone trong database” chưa giải quyết được vấn đề.

### 9.3. Tạo lại file là một yêu cầu mới có kiểm soát

Người dùng muốn dữ liệu mới sau khi export hết hạn có thể tạo job mới nếu được cấp quyền, còn quota và nguồn dữ liệu cho phép. Job mới có policy và deadline riêng; không sửa một job EXPIRED thành READY chỉ để tái sử dụng URL cũ.

Với cùng idempotency key của một yêu cầu đã hết hạn, trả trạng thái/kết quả theo hợp đồng đã định, không tự sinh payload mới và khởi động lại TTL. Nếu cho phép yêu cầu mới, định danh ý định mới phải rõ ràng và vẫn đi qua kiểm tra quyền hiện hành.

## 10. Metadata, log và audit cũng có retention

Một job đã xóa payload có thể vẫn cần bằng chứng tối thiểu như job ID, policy version, phạm vi purge, thời điểm hoàn tất và mã lỗi. Không nhất thiết giữ nguyên filter chứa danh sách khách hàng, nội dung báo cáo hoặc URL ký để chứng minh điều đó.

OWASP nhấn mạnh việc quản lý thời hạn của log cùng các bản sao/backup liên quan trong [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html). Với export, hãy áp dụng một policy rõ cho metadata và dữ liệu chẩn đoán, thay vì coi log là nơi lưu miễn trừ mọi giới hạn.

Audit hữu ích có thể ghi:

```text
jobId, tenant tham chiếu, chủ thể thao tác theo policy
exportKind, policyVersion, generation, manifestVersion
accessExpiresAt, thời điểm quyết định tải hoặc từ chối
purgeScope, số artifact dự kiến/đã đối soát
mã lỗi, attempt, verifiedAt, correlationId
```

Giới hạn quyền đọc audit và tránh ghi nội dung nhạy cảm của export. Một hash hoặc ID liên kết vẫn có thể là thông tin cần bảo vệ theo ngữ cảnh; không tự coi chúng là dữ liệu vô danh.

Thông tin người dùng nhìn thấy nên phân biệt “đã hết hạn tải”, “đang dọn dữ liệu” và trạng thái khác cần công bố. Không trình bày thất bại storage như thể file còn được gia hạn sử dụng.

## 11. Kiểm thử deadline, retry và tác động thực tế

### 11.1. Dùng clock điều khiển được

Không chờ 24 giờ hoặc dùng sleep để kiểm tra hết hạn. Inject `Clock` và dùng clock cố định hoặc `MutableClock` do test harness hiện thực.

Ba mốc quan trọng:

```text
T = accessExpiresAt
T - epsilon: cho tải nếu các điều kiện khác hợp lệ
T: từ chối request tải mới
T + epsilon: tiếp tục từ chối, dù cleanup chưa chạy
```

Epsilon phải phù hợp độ chính xác của tầng đang test. Với signed URL hoặc database cắt độ chính xác tới giây, test cả quá trình chuyển đổi để không làm tròn theo hướng kéo dài thời hạn.

Một ca quan trọng:

```java
@Test
void expiredPayloadIsDeniedEvenBeforeCleanupRuns() {
    Fixture f = fixtures.readyExportWithPayloadPresent();
    clock.setInstant(f.accessExpiresAt());

    assertThatThrownBy(() -> downloadService.authorizeDownload(f.jobId()))
        .isInstanceOf(ExportUnavailableException.class);

    assertThat(storageProbe.exists(f.artifactRef())).isTrue();
}
```

`clock`, fixture và probe ở đây là thành phần test. Ca này chứng minh gate không phụ thuộc việc file đã bị xóa; cần actor/context hợp lệ và positive control trước deadline để tránh ca âm giả.

### 11.2. Ma trận tình huống tấn công logic

| Tình huống | Cách kích hoạt | Oracle |
| --- | --- | --- |
| Sliding TTL | Mở tiến độ, tải lại, retry cùng yêu cầu | Deadline đã ghi không thay đổi |
| Client tự gia hạn | Gửi retention/expiresAt ngoài hợp đồng | Không làm rộng thời hạn hoặc quyền |
| READY quá muộn | Worker hoàn tất sau maximumJobLifetime | Không publish khả năng tải mới |
| Sweeper trễ | Giữ payload tồn tại sau accessExpiresAt | Request mới vẫn bị chặn |
| Link cũ | Dùng URL đã phát qua deadline/thu hồi theo mô hình | Không vượt cam kết truy cập đã chọn |
| Resume | Bắt đầu lại sau deadline | Được xét như request mới theo hợp đồng |
| Khác tenant | Dùng jobId hoặc artifactRef tenant khác | Không tải, không xóa nhầm |
| Retry cleanup | Xóa thành công rồi mất phản hồi/worker chết | Đối soát an toàn, không tạo lại payload |
| Version cũ | Tạo delete marker nhưng giữ noncurrent version | Không báo đã dọn toàn phạm vi khi version còn |
| Upload dở | Worker chết trong multipart/staging | Các phần dở được theo dõi và dọn |
| Publish muộn | Worker cũ hoàn thành sau cancel/expire | Bị chặn publish, artifact orphan được xử lý |
| Generation thay đổi | Cleanup G1 chạy khi G2 tồn tại | Không xóa nhầm G2; metadata cập nhật có điều kiện |
| Storage từ chối xóa | Permission lỗi hoặc retention lock | RETRY/BLOCKED đúng loại, không VERIFIED giả |
| Restore backup | Khôi phục job READY cũ sau khi đã hết hạn | Không sống lại quyền tải hoặc republish |
| Metadata cleanup | Dọn job trước khi purge payload xong | Test phát hiện mất khả năng truy vết/dọn artifact |

### 11.3. Tách test ứng dụng khỏi bằng chứng storage

Test policy/clock xác minh điều kiện truy cập và deadline. Test cleanup với fake storage giúp điều khiển lỗi, crash và idempotency. Test tích hợp storage trong môi trường riêng cần kiểm tra những tính chất provider mà fake không mô phỏng đầy đủ, như versioning, multipart hoặc lock.

Không coi một mock `delete()` được gọi là bằng chứng mọi byte/bản sao đã bị dọn. Cũng không coi `403` khi đọc object là bằng chứng object không còn tồn tại. Nguồn quan sát phải có quyền và phạm vi đủ để kết luận tương ứng.

Với race, điều phối bằng barrier/latch hoặc fault injection ở ranh giới commit/upload/publish. Sau request, đọc metadata đã commit qua transaction mới và đối soát artifact độc lập. Log truy cập hoặc audit từ chối có thể phát sinh; dữ liệu đơn hàng, giá, phê duyệt và reservation nguồn không được đổi chỉ vì export hết hạn.

## 12. Quan sát vận hành và xử lý tồn đọng

Các số đo hữu ích gồm:

- Payload active đã quá hạn nhưng chưa dọn và tuổi tồn đọng lớn nhất.
- Số purge task retry/BLOCKED theo lý do.
- Artifact orphan, staging và multipart quá tuổi.
- Số lần từ chối tải sau hết hạn hoặc sau thu hồi.
- Job hoàn tất muộn bị chặn publish và attempt cũ bị loại.
- Mức khớp giữa manifest, inventory lưu trữ và kết quả dọn theo scope.

Một queue cleanup trống không chứng minh retention đúng nếu hệ thống chưa tạo task cho orphan hoặc version cũ. Cần đối soát từ cả metadata job và inventory kho theo namespace được quản lý.

Ví dụ báo cáo trung thực:

```text
Export: E-17, generation G3
Access: hết hạn, gate đang từ chối request mới
Purge scope: active storage và staging đã đăng ký
Expected artifacts: 4
Verified absent/deleted: 3
Remaining: 1 noncurrent version bị storage lock
Purge state: BLOCKED
Backups: theo policy riêng, chưa tuyên bố đã dọn toàn bộ
```

Thông tin vận hành chi tiết chỉ dành cho vai trò phù hợp. Phía người dùng có thể chỉ cần biết bản xuất không còn khả dụng; việc payload đang chờ xử lý không cấp lại quyền tải.

Khi phát hiện backlog, sửa nguồn gây bỏ sót hoặc lỗi retry cùng với xử lý artifact. Không chỉ chỉnh trạng thái database thành VERIFIED để làm sạch dashboard.

## 13. Bài tập thực hành

Một hệ thống đang triển khai:

```text
- expiresAt được tính bằng updatedAt + 30 ngày.
- Mỗi lần lấy tiến độ đều cập nhật updatedAt.
- Chỉ cron ban đêm kiểm tra file quá hạn.
- Download chỉ kiểm tra job.status == READY.
- Signed URL được cấp lại với TTL cố định dù job sắp hết hạn.
- Cleanup chỉ xóa key hiện hành trong bucket versioned rồi xóa dòng job.
- Worker retry có thể đặt lại READY và firstReadyAt.
- Restore backup khôi phục toàn bộ job cũ mà không đối soát tombstone.
```

Hãy thiết kế lại:

1. Chọn mốc bắt đầu, giới hạn tuyệt đối và công thức deadline không trượt.
2. Phân biệt hết quyền tải, tiến độ purge active storage và retention của backup/metadata.
3. Thiết kế gate tải cùng cách giới hạn link và xử lý resume theo cam kết rõ ràng.
4. Xây manifest đủ nhận diện file cuối, staging, version cũ và upload chưa hoàn tất.
5. Ngăn worker cũ republish hoặc cleanup xóa nhầm generation mới.
6. Định nghĩa bằng chứng trước khi ghi purge VERIFIED và cách xử lý BLOCKED.
7. Viết test clock/race/restore để chứng minh export hết hạn không sống lại và không tác động dữ liệu nguồn.

Export retention được thực hiện đúng khi thời hạn truy cập luôn được cưỡng chế, các bản sao được xử lý theo phạm vi và deadline đã xác định, còn retry, phục hồi hay lỗi dọn dẹp không tạo ra một vòng đời mới ngoài quyền được cấp.

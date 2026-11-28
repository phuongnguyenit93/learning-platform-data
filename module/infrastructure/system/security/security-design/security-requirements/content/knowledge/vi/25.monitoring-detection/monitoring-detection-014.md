# Incident evidence

## 1. Incident evidence là gì và yêu cầu bảo mật cần bảo đảm điều gì?

**Incident evidence** là dữ liệu, vật phẩm và hồ sơ có nguồn gốc được xác định, được dùng để kiểm tra những câu hỏi liên quan đến một sự cố: chuyện gì đã xảy ra, phạm vi ảnh hưởng, những hành động nào đã được thực hiện và kết luận nào có thể được hỗ trợ.

Ví dụ, sau một cảnh báo đăng nhập bất thường rồi xuất dữ liệu, đội xử lý cần nối log xác thực, thay đổi credential, truy cập dữ liệu, trạng thái export và hoạt động phản ứng. Một ảnh chụp dashboard hoặc một nhãn “tài khoản bị chiếm” chưa đủ thay cho các nguồn đó.

Trong chương Monitoring và detection của module yêu cầu bảo mật, mục tiêu là đặc tả **khả năng tạo, thu nhận, bảo toàn, truy xuất và sử dụng bằng chứng**. Yêu cầu phải có phạm vi, thẩm quyền, trách nhiệm, hành vi khi lỗi và tiêu chí kiểm chứng.

[NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) gắn phát hiện, phản ứng và phục hồi với quản lý rủi ro. [NIST SP 800-86](https://csrc.nist.gov/pubs/sp/800/86/final) trình bày việc tích hợp kỹ thuật forensic từ góc nhìn công nghệ thông tin vào xử lý sự cố. Bài học dùng các mục tiêu đó để xây dựng contract cho một hệ thống, không mặc định mọi incident cần cùng một mức thu thập.

Mọi ID, cửa sổ thời gian, deadline và ví dụ metadata dưới đây thuộc hệ thống giả định. Điều kiện về thẩm quyền, chia sẻ và thời hạn lưu cần được xác định theo profile áp dụng cho tổ chức và vụ việc.

## 2. Chất lượng bằng chứng có nhiều trục khác nhau

| Thuộc tính | Câu hỏi cần trả lời | Điều không được tự suy ra |
|---|---|---|
| Liên quan | Vật phẩm giúp kiểm tra giả thuyết/câu hỏi nào? | Dữ liệu nhiều tự động có giá trị điều tra cao |
| Nguồn gốc | Đến từ hệ thống, asset, người hoặc phép thu nào? | Một tên file tự khai chứng minh nguồn |
| Toàn vẹn | Bytes hoặc metadata có đổi so với mốc đã bảo toàn không? | Hash khớp chứng minh nội dung nguồn luôn đúng |
| Phạm vi/độ đầy đủ | Đã thu phần nào, thiếu phần nào, vì sao? | Export có dữ liệu nghĩa là đã có toàn bộ lịch sử |
| Thời gian | Mốc nào, đồng hồ nào, mức sai lệch ra sao? | UTC tự bảo đảm mọi nguồn đồng bộ |
| Khả năng truy vết | Ai thu, nhận, truy cập, sao chép hoặc xử lý vật phẩm? | Một account dùng chung giúp quy đúng người |
| Khả năng tái kiểm | Có thể đọc, xác minh và lặp lại bước phân tích thích hợp không? | Chỉ giữ một biểu đồ tổng hợp là đủ |
| Tính bí mật và quyền | Ai được thu, xem, biến đổi hoặc chia sẻ? | Incident cho phép mọi người đọc mọi dữ liệu |

Một vật phẩm có thể toàn vẹn sau thu nhận nhưng nguồn đã bị can thiệp trước đó. Một export có nguồn xác thực vẫn có thể chỉ chứa một phần thời gian hoặc thiếu trang dữ liệu. Cần biểu diễn những giới hạn này thay vì gắn một nhãn “evidence verified” cho tất cả các trục.

### 2.1. Phân biệt quan sát, suy luận và kết luận

- **Quan sát:** nguồn A ghi một request thành công; nguồn B ghi một gói export được tạo.
- **Suy luận:** hai event có thể thuộc cùng workflow dựa trên các liên kết và thời gian.
- **Kết luận:** nhận định đã được đánh giá với evidence, giới hạn và mức tin cậy phù hợp.

Một HTTP 200 không tự chứng minh người nhận đã đọc toàn bộ dữ liệu. Event tạo export không phải event tải export. Việc không thấy log truy cập không tự chứng minh không có truy cập nếu nguồn hoặc cửa sổ lưu chưa đầy đủ.

## 3. Tình huống minh họa và mô hình đe dọa

Một nền tảng học tập phát hiện tài khoản có đăng nhập bất thường, sau đó thay MFA và tạo export hồ sơ. Đội xử lý muốn xác định diễn biến, dữ liệu có thể bị công bố và hiệu lực của các biện pháp đã áp dụng.

| Nguồn | Câu hỏi điều tra minh họa |
|---|---|
| Identity provider và hệ thống phiên | Những lần xác thực nào được ghi, kết quả và mức tin cậy? |
| Audit credential/configuration | Thay đổi nào đã commit, ai/luồng nào thực hiện, policy nào được dùng? |
| API/gateway và dịch vụ dữ liệu | Request nào vào scope, kết quả và lượng dữ liệu đã phục vụ ở mức quan sát được? |
| Kho export/object storage | Artifact/version nào được tạo, quyền chia sẻ và hoạt động tải nào có evidence? |
| Hạ tầng/workload | Instance nào phục vụ, cấu hình hiệu lực và vòng đời liên quan? |
| Công cụ phản ứng | Yêu cầu thu hồi/cách ly được gửi và hiệu lực nào đã được xác nhận? |
| Ghi chép của người xử lý | Quyết định, thao tác, người chịu trách nhiệm và tác động tới hiện trường? |

Các rủi ro cần chuyển thành yêu cầu:

| Mã | Tình huống | Hậu quả |
|---|---|---|
| R1 | Log hết hạn, instance biến mất hoặc dữ liệu volatile mất | Không còn dữ liệu cần thiết để kiểm tra giả thuyết |
| R2 | Thu sai asset/version/tenant hoặc thiếu cửa sổ/trang dữ liệu | Kết luận dựa trên phạm vi không đúng |
| R3 | Vật phẩm hoặc manifest bị sửa mà không biết | Không xác định được dữ liệu nào đã được phân tích |
| R4 | Không có provenance/custody hoặc dùng nguồn không đáng tin | Không giải thích được lịch sử và mức tin cậy |
| R5 | Chuẩn hóa sai thời gian hoặc ghép sai định danh | Timeline và quan hệ nhân quả sai |
| R6 | Evidence chứa secret, PII hoặc vật phẩm nghi độc bị chia sẻ quá rộng | Tạo sự cố dữ liệu hoặc nguy cơ mới trong điều tra |
| R7 | Thu thập/phân tích làm thay đổi nguồn hoặc phá dữ liệu dễ mất | Mất khả năng kiểm tra diễn biến gốc |
| R8 | Có file lưu nhưng không đọc/giải mã/tái kiểm được | Không dùng được bằng chứng khi cần |

## 4. Đặc tả phạm vi trước khi tự động thu thập

### 4.1. Câu hỏi điều tra dẫn tới collection plan

Collection plan nên liên kết incident/case với giả thuyết, nguồn, asset, loại dữ liệu, khoảng thời gian, mức ưu tiên, người chịu trách nhiệm và điều kiện được phép.

Không bắt đầu bằng yêu cầu “thu mọi dữ liệu từ mọi máy”. Với ví dụ trên, có thể ưu tiên dữ liệu của tài khoản và workflow export trong cửa sổ đã xác định, đồng thời ghi rõ nguồn cần mở rộng nếu phát hiện asset hoặc thời điểm khác.

Mỗi nguồn cần có cách thu, quyền cần thiết, thời gian dữ liệu còn tồn tại, giới hạn API/format và nơi lưu được phép. Nguồn do nhà cung cấp quản lý cần owner phối hợp và mốc phản hồi phù hợp; không coi gửi ticket là đã có dữ liệu.

### 4.2. Biểu diễn trạng thái theo từng nguồn

| Trạng thái minh họa | Ý nghĩa |
|---|---|
| `PLANNED` | Đã xác định cần thu nhưng chưa bắt đầu |
| `COLLECTING` | Đang thực hiện phép thu theo scope |
| `COLLECTED_WITHIN_SCOPE` | Đã thu theo phạm vi và điều kiện được mô tả |
| `PARTIAL` | Chỉ có một phần, với giới hạn cụ thể |
| `UNAVAILABLE` | Dữ liệu không còn/không thể lấy theo điều kiện hiện tại |
| `FAILED_RETRYABLE` | Chưa có kết quả vì lỗi có thể thử lại |
| `REVIEW_REQUIRED` | Có mâu thuẫn, chưa rõ scope hoặc cần quyết định |

`UNAVAILABLE`, timeout và kết quả tìm không có bản ghi là những điều khác nhau. Không chuyển lỗi collector thành “không có hoạt động bất thường”.

“Đã thu trong scope” chỉ nói về scope được khai báo, không khẳng định toàn bộ sự cố hoặc toàn hệ thống đã được bao phủ. Một nguồn mới xuất hiện có thể cần mở rộng collection plan.

### 4.3. Scope và quyền không được tự khai bởi người gọi

Một collector workload phải được cấp phạm vi case, nguồn và thao tác thích hợp. Không dùng credential quản trị toàn tổ chức cho mọi phép thu nếu không cần.

Asset reference cần gắn với instance/version có ý nghĩa. Hostname, PID hoặc tên workload có thể được tái sử dụng; tenant hoặc account ID tự nhập không tự chứng minh quyền thu dữ liệu của đối tượng đó.

## 5. Thứ tự thu, dữ liệu dễ mất và tác động tới hệ thống

### 5.1. Đánh giá độ dễ mất theo từng nguồn

Memory, tiến trình, kết nối đang mở hoặc dữ liệu trong buffer có thể mất khi process/host thay đổi. Log có retention ngắn, queue hoặc workload tạm thời cũng có thể biến mất trước dữ liệu lưu trữ dài hạn.

[RFC 3227](https://www.rfc-editor.org/rfc/rfc3227.html) đề cập ưu tiên dữ liệu volatile và ghi chép phương pháp/thời gian thu thập. Khi áp dụng vào kiến trúc cụ thể, cần xác định thứ tự và nguồn theo hiện trạng, không dùng một danh sách cố định như công thức cho mọi môi trường.

Cần chủ động nhận diện những hành động có thể làm mất dữ liệu: reboot, terminate/reimage, autoscaling, dọn queue, xóa file, đổi retention hoặc thu hồi một tài khoản có quyền truy xuất nguồn. Collection plan phải phối hợp với người xử lý, không chỉ chạy sau khi mọi thao tác phục hồi đã xong.

### 5.2. Không để bảo toàn evidence làm bỏ ngỏ tác động đang gây hại

Ngăn hại và bảo toàn dữ liệu cần được quyết định cùng nhau. Không đặt quy tắc máy móc luôn chờ một bản thu đầy đủ trước khi containment, cũng không mặc định luôn xóa hoặc khởi động lại ngay.

Yêu cầu nên có thẩm quyền quyết định, phương án đã chuẩn bị, bằng chứng tối thiểu ưu tiên và record về điều đã làm. Nếu containment đã làm mất một loại dữ liệu, cần ghi nhận giới hạn đó để analyst không suy ngược từ sự vắng mặt của nó.

### 5.3. Phép thu có thể làm thay đổi hiện trường

Đọc hoặc chạy công cụ trên hệ thống đang sống có thể tạo tiến trình, cập nhật metadata, thêm log hoặc ảnh hưởng tải. Yêu cầu cần giảm thay đổi phù hợp và ghi rõ method/tool/version, thời điểm, phạm vi cùng tác động đã biết.

Công cụ từ một nguồn có thể đã bị chiếm cần được đánh giá mức tin cậy. Nếu thu qua agent/provider, phải giữ nguồn gốc, identity và giới hạn quan sát thay vì tự coi mọi output là ảnh chụp hoàn hảo.

Vùng nhận dữ liệu thu phải được xác định trước. Không ghi kết quả trở lại vật phẩm/phương tiện cần bảo toàn ngoài thiết kế được cho phép, làm lẫn dữ liệu sự cố với dữ liệu do chính quá trình điều tra tạo ra.

## 6. Evidence manifest: nhận diện vật phẩm và phạm vi thu

### 6.1. Metadata phải đi cùng artifact

| Nhóm | Field hoặc thông tin minh họa |
|---|---|
| Case | Evidence ID, incident/case reference, owner |
| Nguồn | Service/provider, environment, tenant, asset instance, object/version |
| Phạm vi | Loại dữ liệu, khoảng thời gian, điều kiện tìm/thu, phần thiếu |
| Thu nhận | Collector identity, quyền/phê duyệt reference, method/tool/version |
| Thời gian | Bắt đầu/kết thúc thu, thời điểm nhận, timezone/clock quality |
| Vật phẩm | Artifact reference, version, định dạng, kích thước và số phần nếu có |
| Toàn vẹn | Thuật toán, digest/reference được bảo vệ, mốc tính và kết quả xác minh |
| Bảo vệ | Classification, access profile, retention/hold reference khi áp dụng |
| Liên kết | Source event/export job, custody record và artifact cha/con |

Query hoặc selector cần đủ để tái kiểm trong phạm vi phù hợp, nhưng không tự ghi token, connection string hoặc SQL chứa dữ liệu nhạy cảm vào manifest ít được bảo vệ hơn. Có thể dùng tham chiếu tới query/method được lưu riêng có quyền.

### 6.2. Ví dụ một record đã thu

```json
{
  "evidenceId": "evidence-demo-731",
  "incidentRef": "incident-demo-42",
  "kind": "SOURCE_EVENT_EXPORT",
  "sourceRef": "identity-audit-demo",
  "tenantRef": "tenant-demo-a",
  "sourceScopeRef": "collection-scope-demo-8",
  "sourceTimeRange": {
    "startInclusive": "2026-01-12T08:00:00Z",
    "endExclusive": "2026-01-12T10:00:00Z"
  },
  "collectorRef": "collector-workload-demo",
  "collectionMethodRef": "audit-export-method-demo-v3",
  "collectionStartedAt": "2026-01-12T10:05:00Z",
  "collectionCompletedAt": "2026-01-12T10:06:30Z",
  "artifactRef": "evidence-object-demo-731",
  "artifactVersion": "version-demo-1",
  "format": "JSONL",
  "byteCount": 245760,
  "fixity": {
    "algorithm": "SHA-256",
    "recordRef": "fixity-record-demo-731",
    "verificationStatus": "VERIFIED"
  },
  "collectionOutcome": "COLLECTED_WITHIN_SCOPE",
  "limitationsRef": "collection-notes-demo-731",
  "classification": "RESTRICTED_INCIDENT_DATA"
}
```

Tất cả giá trị là minh họa. `fixity.recordRef` dẫn tới digest thật và metadata được bảo vệ phù hợp; nó không phải chuỗi giả được dùng thay digest. `VERIFIED` chỉ nói phép kiểm toàn vẹn được định nghĩa, không khẳng định mọi nội dung nguồn là đúng.

`collectionOutcome` phải dựa vào contract của phép thu, gồm các trang/part và giới hạn nguồn liên quan. Job export được chấp nhận chưa phải artifact đã sẵn sàng hoặc tải hoàn tất.

### 6.3. Bản nguồn động, bản bảo toàn và bản làm việc

Một export từ hệ thống đang thay đổi là vật phẩm được tạo qua một phép thu với scope và mốc cụ thể. Không gọi nó là bản gốc đầy đủ của toàn hệ thống nếu nguồn không cung cấp bảo đảm đó.

Bản được bảo toàn đầu tiên cần identity và kiểm soát thích hợp. Bản sao dùng để phân tích là vật phẩm riêng có lineage. Dữ liệu đã normalize, redaction, giải nén hoặc tổng hợp cũng là artifact dẫn xuất, không âm thầm thay bản đã thu.

## 7. Tính toàn vẹn: hash có ích nhưng không đủ

### 7.1. Gắn digest với đúng bytes và mốc

Profile có thể dùng SHA-256 cho ví dụ kiểm fixity, cùng việc ghi kích thước, artifact/version và mốc tính. Cần nói rõ digest của nội dung thu, container nén hay container mã hóa.

Một gói nén hoặc mã hóa có bytes khác vật phẩm bên trong; không so hai digest thuộc hai representation rồi tự kết luận dữ liệu đã bị sửa trái phép. Nếu giữ cả hai lớp, manifest phải chỉ quan hệ và phạm vi từng digest.

Normalize newline, chuyển encoding, đổi định dạng hoặc redaction có thể thay bytes. Kết quả đó cần artifact mới với digest và method riêng, còn bản thu được giữ theo chính sách.

### 7.2. Bảo vệ cả vật phẩm và record kiểm tra

[NIST IR 8387](https://nvlpubs.nist.gov/nistpubs/ir/2022/NIST.IR.8387.pdf) phân tích các vấn đề bảo toàn dữ liệu số, bao gồm việc bảo vệ hash/chữ ký để tránh sửa vật phẩm rồi thay cả giá trị đối chiếu. Thiết kế cần xác định quyền và nguồn kiểm chứng độc lập phù hợp, không chỉ đặt một file hash cạnh file dữ liệu rồi coi là đủ.

Có thể phối hợp storage versioning/immutability, quyền hạn chế, manifest được bảo vệ, chữ ký hoặc checkpoint theo profile. Mỗi biện pháp phải có owner, quản lý khóa/quyền và giới hạn được công bố.

Hash khớp giúp kiểm sự không thay đổi so với mốc đã ghi. Nó không chứng minh sự kiện chưa bị làm giả trước lúc thu, không chứng minh completeness và không tự xác nhận actor là con người cụ thể.

### 7.3. Khi xác minh không khớp

Không tự tính lại digest mới rồi ghi đè expected digest để bỏ cảnh báo. Cần giữ record mâu thuẫn, dừng sử dụng kết luận phụ thuộc vào tính toàn vẹn chưa được xác lập và chuyển owner xem xét.

Phải phân biệt hỏng dữ liệu, sai representation, lỗi quy trình, thay đổi có chủ đích được ghi nhận và can thiệp trái phép. Nếu phục hồi từ bản sao đã được xác minh, cần lineage và bằng chứng phục hồi, không xóa lịch sử vấn đề.

## 8. Chain of custody: ai đã quản lý và xử lý vật phẩm?

### 8.1. Ghi lịch sử thao tác theo identity và artifact cụ thể

**Chain of custody** là hồ sơ về nguồn phát hiện, thu nhận, người/đơn vị quản lý, xử lý và những lần chuyển giao vật phẩm. [RFC 3227, mục 4.1](https://www.rfc-editor.org/rfc/rfc3227.html#section-4.1) nêu những nhóm thông tin cần giải thích trong lịch sử này.

Trong hệ thống số, cần định nghĩa các hành động như nhận, sao chép, chuyển quyền quản lý, truy cập, biến đổi, xuất, lưu trữ và hủy. Không phải mỗi lần đọc đều là chuyển custodian, nhưng những lần đọc/xử lý liên quan vẫn cần audit theo policy.

Một record bàn giao minh họa:

```yaml
custodyEventId: custody-demo-301
evidenceId: evidence-demo-731
artifactVersion: version-demo-1
action: TRANSFER_CUSTODY
fromCustodianRef: collection-team-demo
toCustodianRef: investigation-team-demo
requestedByRef: operator-demo-4
authorizedByRef: approval-demo-19
transferMethodRef: protected-evidence-transfer-v2
sentAt: "2026-01-12T10:20:00Z"
receivedAt: "2026-01-12T10:21:30Z"
receiptRef: receipt-demo-731
integrityCheckRef: fixity-check-demo-9
outcome: CONFIRMED
```

Dữ liệu trên là ví dụ. `CONFIRMED` cần có bằng chứng nhận và kiểm tương ứng, không được suy chỉ từ thao tác enqueue hoặc API gửi thành công. Receipt chứng minh một mốc theo contract, không tự chứng minh người nhận đã hiểu hoặc phân tích nội dung.

### 8.2. Tách quyền quản lý, đọc và sửa hồ sơ

Một analyst được đọc bản làm việc không mặc nhiên được sửa/xóa vật phẩm bảo toàn hoặc expected digest. Người quản trị storage cũng không mặc nhiên có quyền thay kết luận điều tra hay tự mở rộng người nhận.

Quyền cập nhật custody/manifest cần được xác thực, phân quyền và lưu lịch sử. Không sửa đè record quá khứ để làm mất một lần bàn giao bị lỗi hoặc một khoảng chưa xác định.

Nếu một bước bàn giao không có bằng chứng đủ, phải ghi gap và quyết định xử lý. Không lấp gap bằng một tên người hoặc thời điểm được đoán sau sự cố.

### 8.3. Bản sao và quan hệ cha/con

Một bản sao nguyên bytes có thể giữ cùng content digest nhưng vẫn có artifact/storage reference và lịch sử xử lý riêng. Bản redaction hoặc kết quả phân tích có bytes khác cần lineage tới input.

Không dedup mất toàn bộ provenance chỉ vì hai vật phẩm cùng digest. Chúng có thể được thu từ hai nơi hoặc hai thời điểm khác nhau, và chính nguồn/vị trí là thông tin quan trọng cho phạm vi sự cố.

## 9. Dòng thời gian và độ tin cậy của nguồn

### 9.1. Giữ nhiều mốc có ý nghĩa

| Mốc | Ý nghĩa |
|---|---|
| Event time | Thời điểm nguồn nói sự kiện xảy ra |
| Observed/ingest time | Thời điểm một thành phần thu nhận thấy record |
| Acquisition interval | Khoảng thời gian thực hiện phép thu artifact |
| Analysis time | Thời điểm thực hiện phép biến đổi hoặc phân tích |
| Custody/action time | Thời điểm quản lý, chia sẻ hoặc xử lý evidence |

Timezone, clock offset và mức bất định cần được giữ. Việc normalize sang UTC tạo một cách biểu diễn thống nhất, không tự sửa đồng hồ nguồn.

Ví dụ, hai event chỉ cách nhau một giây nhưng một nguồn có sai lệch chưa được biết trong khoảng lớn hơn đó thì không đủ cơ sở khẳng định thứ tự chắc chắn chỉ từ timestamp. Có thể cần liên kết workflow, revision, sequence trong phạm vi phù hợp hoặc nguồn khác.

Một phép thu trên hệ thống đang chạy cũng có khoảng bắt đầu/kết thúc. Không mô tả memory hoặc export nhiều nguồn như một snapshot nguyên tử toàn hệ thống nếu không có cơ chế cung cấp bảo đảm đó.

### 9.2. Giữ nguyên dữ liệu nguồn khi bổ sung cách hiểu

Có thể tạo field thời gian chuẩn hóa, ước lượng offset hoặc annotation trong bản dẫn xuất. Phải giữ giá trị nguồn và phương pháp ánh xạ, không âm thầm sửa các event gốc để chúng khớp một giả thuyết.

Ghi cả hành động của người thu và công cụ phản ứng có thể tạo dấu vết trên nguồn. Nhờ đó, analyst phân biệt được hoạt động điều tra/containment với hoạt động đang bị xem xét.

### 9.3. Nguồn bị chiếm hoặc nhiều bản sao của cùng một nguồn

Một log từ host nghi bị chiếm cần được đánh giá cùng nguồn gốc và điều kiện thu. Hash sau thu không làm những khẳng định bên trong nó tự trở thành sự thật.

Log do agent gửi sang hai kho khác nhau có thể vẫn là cùng một quan sát ban đầu. Không cộng chúng thành hai xác nhận độc lập nếu lineage cho thấy cùng nguồn.

Nguồn khác như control-plane audit, identity provider hoặc dữ liệu gateway có thể bổ sung bối cảnh nếu đúng scope và quyền. Những mâu thuẫn giữa nguồn cần được ghi nhận và phân tích, không tự chọn nguồn khớp giả thuyết rồi bỏ phần còn lại.

## 10. Pipeline thu nhận phải chịu được lỗi và dữ liệu không đầy đủ

### 10.1. Lifecycle của một collection job

```mermaid
flowchart LR
    P[Plan và quyền thu] --> J[Collection job]
    J --> S[Vùng nhận được bảo vệ]
    S --> V[Kiểm kích thước, phạm vi và fixity]
    V --> R[Đăng ký artifact và manifest]
    R --> W[Bản làm việc và phân tích]
    W --> C[Kết luận có evidence và giới hạn]
```

Các mốc cần có trạng thái thật và khả năng tiếp tục/đối soát. Không đánh dấu job hoàn tất chỉ vì đã nhận được tên một export hoặc một object rỗng.

Phải phân biệt hoàn tất truyền, hoàn tất số part, hoàn tất export theo scope và toàn vẹn bytes. Hash hợp lệ của một file bị cắt ngắn không biến nó thành một export đầy đủ.

### 10.2. Pagination, quyền và nguồn động

Một API có thể giới hạn trang, thời gian, số dòng hoặc quyền theo tài nguyên. Collector cần lưu điều kiện truy vấn, tiến trình trang/part, lỗi và giới hạn nguồn thích hợp. Không coi trang đầu có dữ liệu là toàn bộ kết quả.

Nếu nguồn không có snapshot nhất quán, collection plan và manifest phải công bố điều đó. Retry hoặc pagination trên dữ liệu đang thay đổi có thể tạo record thiếu/trùng; cần cơ chế nguồn hỗ trợ hoặc phương pháp đối soát đã được xác định.

Kết quả rỗng có thể do không có dữ liệu trong scope, sai selector, quyền bị giới hạn hoặc nguồn lỗi. Contract cần giúp phân biệt các tình huống này trước khi kết luận.

### 10.3. Retry và partial result

Mỗi collection job cần operation reference, scope và chính sách retry. Không trộn các phần thuộc hai phép thu có cửa sổ hoặc snapshot khác nhau mà không ghi rõ.

Nếu chỉ thu được một phần, có thể bảo toàn phần đó với trạng thái `PARTIAL` và giới hạn cụ thể. Không cần vứt mọi dữ liệu hữu ích, nhưng không gắn nó là đã đủ.

Lỗi một nguồn cần được cảnh báo và chuyển owner; các nguồn còn được phép và có thể thu không nên bị bỏ qua chỉ vì workflow chưa có kết quả toàn bộ. Tiêu chí đóng collection plan cần liệt kê phần đầy đủ, phần thiếu và quyết định chấp nhận giới hạn.

### 10.4. Khi kho evidence hoặc manifest không hoạt động

Profile cần hành vi cho thiếu dung lượng, hết quyền ghi, lỗi key, mất kết nối hoặc không đăng ký được manifest. Nếu có vùng nhận/journal dự phòng, nó vẫn cần identity, bảo vệ dữ liệu, giới hạn dung lượng và khả năng đối soát.

Không đưa raw evidence vào log lỗi, email hoặc kho public để vượt sự cố storage. Không khẳng định đã bảo toàn nếu dữ liệu chỉ nằm trong bộ nhớ hoặc vùng tạm có thể bị dọn ngoài contract.

## 11. Phân tích, artifact dẫn xuất và báo cáo

### 11.1. Phân tích trên bản làm việc có lineage

Một phép phân tích nên chỉ ra input Evidence ID/version, tool/parser version, query hoặc method reference, tham số có ý nghĩa, thời gian chạy và output artifact. Người có quyền cần có khả năng tái kiểm cách tạo kết quả trong điều kiện phù hợp.

Không phải mọi phép phân tích đều tái tạo bit-for-bit do nguồn hoặc công cụ có yếu tố không xác định. Những điều kiện đó cần được ghi; không hứa tính tái lập tuyệt đối khi thiết kế không cung cấp.

Normalization, giải nén, redaction và extraction tạo vật phẩm dẫn xuất. Giữ quan hệ input/output và digest tương ứng, không ghi đè bản bảo toàn đầu tiên.

### 11.2. Screenshot và bản tổng hợp có vai trò riêng

Screenshot hữu ích để trình bày trạng thái giao diện, bộ lọc hoặc bối cảnh người vận hành thấy. Tuy nhiên, nó có thể thiếu timezone, phân trang, record bị ẩn hoặc chi tiết nguồn. Cần lưu context và nguồn có cấu trúc khi mục tiêu yêu cầu tái kiểm những dữ liệu đó.

Biểu đồ tổng hợp hoặc nhãn verdict là kết quả phân tích, không tự thay thế input. Kết luận nên trỏ tới Evidence ID, phần dữ liệu liên quan và method, kèm giới hạn.

Nếu parser hoặc mapping bị sai, cần tạo kết quả sửa có version/lineage. Không thay một con số trong báo cáo mà không để lại căn cứ và lịch sử cập nhật phù hợp.

### 11.3. Báo cáo phải phân biệt sự thật quan sát với điều chưa biết

Một finding có thể ghi:

```yaml
findingId: finding-demo-18
statement: Export creation was confirmed for the scoped workflow
supportedBy:
  - evidenceId: evidence-demo-731
    locatorRef: event-locator-demo-81
  - evidenceId: evidence-demo-732
    locatorRef: object-version-locator-demo-22
limitations:
  - Complete recipient-side download was not established
  - One relevant source had a documented collection gap
analysisMethodRef: export-timeline-analysis-demo-v2
reviewState: REVIEWED
```

Ví dụ không khẳng định người ngoài đã đọc toàn bộ dữ liệu chỉ vì hệ thống tạo một export. Locator cần đủ để tìm phần liên quan theo quyền, không chứa secret hoặc URL truy cập evidence không kiểm soát.

Khi không tìm thấy dấu vết, nên mô tả “không tìm thấy trong các nguồn/cửa sổ đã thu” và coverage tương ứng. Điều đó khác với kết luận phổ quát “không xảy ra”.

## 12. Quyền truy cập, chia sẻ, retention và khả năng đọc lâu dài

### 12.1. Evidence có thể nhạy cảm hơn log thường

Memory, forensic artifact hoặc export sự cố có thể chứa credential, dữ liệu cá nhân và nội dung ngoài phần tóm tắt. Khi thật sự cần thu chúng theo scope và thẩm quyền, phải có mức bảo vệ tương ứng; không tự xóa dữ liệu gốc cần thiết chỉ để mọi bản đều phù hợp một dashboard ít quyền.

Bản làm việc hoặc bản chia sẻ có thể được redaction/giảm dữ liệu theo mục đích, giữ lineage và quyền riêng. Secret không được lặp lại trong log pipeline, ticket hoặc báo cáo thông thường.

Mẫu nghi độc cần vùng xử lý phù hợp. Không tự render, thực thi, trích xuất hoặc gửi tới dịch vụ phân tích ngoài bằng công cụ/quyền production chỉ vì nó được gọi là evidence.

### 12.2. Tách quyền theo nhiệm vụ và case

Có thể tách collector, custodian, analyst, reviewer và người được phép chia sẻ/hủy. Quyền trên case không mặc định cho phép đọc mọi tenant hoặc mọi loại dữ liệu nằm trong một artifact lớn.

Các đường UI, API, object storage, archive, export và bản sao đều cần kiểm quyền phù hợp. Biết Evidence ID hoặc một đường dẫn không tạo quyền truy cập; link có khả năng dùng như bearer credential phải có kiểm soát tương ứng.

Lưu và truyền dữ liệu cần biện pháp bảo vệ phù hợp, cùng việc quản lý khóa và quyền giải mã. Mã hóa không thay thế kiểm scope và audit truy cập.

### 12.3. Chia sẻ cần một gói và receipt có kiểm soát

Mỗi lần chia sẻ cần mục đích, người/bên nhận, thẩm quyền, danh mục vật phẩm/version, mức redaction, cách truyền và bằng chứng nhận theo contract. Không chỉ gửi một link rồi coi chuỗi trách nhiệm đã hoàn tất.

Nếu có dữ liệu bên thứ ba hoặc dịch vụ ngoài, profile phải xác định điều kiện được phép và mức dữ liệu tối thiểu. Việc đã chia sẻ có thể ảnh hưởng khả năng xóa/thu hồi bản sao, nên cần theo dõi phạm vi thay vì hứa có thể thu hồi mọi kiến thức đã được người nhận tiếp cận.

### 12.4. Retention và archive phải giữ được khả năng sử dụng

Thời gian giữ theo case, mục tiêu và nghĩa vụ áp dụng. Đóng incident để khôi phục dịch vụ không tự có nghĩa mọi bằng chứng được phép hủy. Ngược lại, một nhãn incident cũng không cho phép giữ mọi dữ liệu vô hạn.

Nếu có quyết định bảo toàn, cần scope, người quyết định, thời điểm rà soát và điều kiện kết thúc. Hết retention hoặc giải phóng hold cần xử lý bản online, archive, export và backup theo phạm vi đã công bố, có record thích hợp.

[NIST IR 8387](https://nvlpubs.nist.gov/nistpubs/ir/2022/NIST.IR.8387.pdf) lưu ý các vấn đề bảo toàn dài hạn như dữ liệu, lưu trữ và khả năng truy xuất khóa khi mã hóa. Profile nên kiểm restore, định dạng/schema cũ, key version và việc chuyển nơi lưu, thay vì chỉ xác nhận file vẫn tồn tại.

Khi migrate hoặc tạo container mã hóa mới, cần xác minh các lớp artifact theo manifest và lưu lịch sử. Không kết luận mất toàn vẹn chỉ vì digest của container mới khác container cũ nếu sự chuyển đổi đã được định nghĩa và bytes bên trong được kiểm chứng.

## 13. Bộ yêu cầu bảo mật mẫu có thể nghiệm thu

| ID | Yêu cầu | Rủi ro và bằng chứng |
|---|---|---|
| EVID-01 | Mỗi incident profile có collection plan theo câu hỏi, nguồn, asset, scope, quyền và owner | R1, R2; threat/incident-to-source map và phê duyệt phạm vi |
| EVID-02 | Ưu tiên nguồn dễ mất và phối hợp containment/restore; ghi tác động của thao tác thu | R1, R7; diễn tập vòng đời workload, outage và nhật ký thao tác |
| EVID-03 | Collector dùng nguồn identity/scope tin cậy; không thu nhầm tenant, instance hoặc version | R2, R4; giả metadata, object đổi version và asset name/PID tái sử dụng |
| EVID-04 | Artifact có manifest về provenance, method, interval, format, size, limitations và kết quả từng nguồn | R2, R4; schema, pagination, partial export và đối soát |
| EVID-05 | Fixity gắn đúng representation/mốc; digest và manifest được bảo vệ, mismatch không bị tự ghi đè | R3; tamper, sai container layer, copy và verification failure |
| EVID-06 | Custody và các thao tác liên quan có identity, thời gian, mục đích, artifact/version và receipt phù hợp | R4; bàn giao, đọc/xử lý, retry và thiếu acknowledgment |
| EVID-07 | Thời gian nguồn/thu/nhận và bất định được giữ; timeline không giả định thứ tự toàn cục khi thiếu bằng chứng | R5; clock skew, trễ và event mâu thuẫn |
| EVID-08 | Bản phân tích/redaction có lineage, tool/query version và output reference; không ghi đè bản bảo toàn | R3, R7; biến đổi, parser sửa và tái kiểm kết quả |
| EVID-09 | Evidence, sample, key và dữ liệu nhạy cảm có phân quyền/cách xử lý theo case, tenant và nhiệm vụ | R6; IAM, UI/API/storage trực tiếp và các bản sao |
| EVID-10 | Chia sẻ/export có scope, thẩm quyền, danh mục, cách truyền và record nhận; report chỉ chứa dữ liệu được phép | R4, R6; redaction, recipient scope và package verification |
| EVID-11 | Retention/hold, archive, migration và hủy được quản lý; dữ liệu giữ lại phải đọc/giải mã/tái kiểm được | R1, R8; restore, key/schema cũ và hết retention |
| EVID-12 | Lỗi thu nhận/kho/manifest tạo trạng thái thật và escalation; không biến thiếu dữ liệu thành kết luận an toàn | R1, R2, R8; lỗi phụ thuộc, file cắt ngắn và diễn tập end-to-end |

Ví dụ đặc tả cho một export evidence:

```yaml
id: EVID-04
asset: incident-source-export
trigger: A scoped source export is collected
requiredBehavior:
  - Bind the artifact to the case, source, scope and collection method
  - Track every expected page or part under the source contract
  - Preserve collection interval, limitations and source outcome
  - Verify size and fixity against the defined representation
forbiddenBehavior:
  - Claim complete collection from job acceptance alone
  - Convert timeout or truncated output into no-activity evidence
measurement:
  registeredArtifactsMissingRequiredManifestFields: 0
  completeClaimsWithUnresolvedRequiredParts: 0
evidence:
  - Pagination and interrupted-transfer test
  - Manifest and artifact verification report
owner: incident-response-platform
```

Các thước đo chỉ có ý nghĩa khi xác định source contract, những phần được kỳ vọng và điểm kiểm tra. Có một digest khớp không thay thế kiểm completeness; có đầy field không tự chứng minh method hoặc context đã đúng.

## 14. Ma trận kiểm thử và diễn tập bằng chứng

Đây là tiêu chí thiết kế kiểm thử, chưa phải kết quả QA của một triển khai cụ thể. Dùng sự kiện, artifact và tài khoản tổng hợp trong môi trường có thẩm quyền.

| Tình huống | Kết quả mong đợi |
|---|---|
| Incident cần nhiều nguồn có quyền thu khác nhau | Collection plan đúng scope, trạng thái và owner từng nguồn |
| Source gần hết retention hoặc workload sắp kết thúc | Ưu tiên/phối hợp bảo toàn hoạt động theo profile, có phần thiếu nếu không thu được |
| Client/operator tự khai tenant/asset ngoài quyền | Không thu hoặc đọc dữ liệu vượt scope |
| Hostname, PID hoặc object name được tái sử dụng | Binding tới đúng instance/version, không ghép nhầm |
| Export job accepted nhưng artifact chưa có | Chưa ghi collected/complete |
| Nguồn có nhiều trang, giới hạn dòng hoặc part thất bại | Không bỏ sót âm thầm hoặc gắn đầy đủ sai |
| File truyền bị cắt ngắn nhưng vẫn tính hash được | Kiểm completeness phát hiện, không dùng hash hợp lệ làm bằng chứng đủ |
| Nguồn lỗi, quyền bị giới hạn hoặc query trả rỗng | Phân biệt trạng thái, không kết luận không có sự kiện từ lỗi |
| Artifact bị đổi bytes hoặc manifest/digest bị thử sửa | Kiểm soát ngăn/phát hiện theo mô hình quyền, không tự cập nhật expected value |
| Nén/mã hóa/chuyển encoding tạo representation mới | Giữ layer/lineage và digest đúng representation |
| Retry collection hoặc mất receipt khi bàn giao | Không trộn scope/part tùy ý; custody giữ trạng thái thật |
| Hai vật phẩm cùng bytes nhưng nguồn khác nhau | Giữ provenance của từng phép thu thay vì dedup mất phạm vi |
| Clock skew, timezone khác hoặc ingest trễ | Giữ giá trị nguồn và bất định, timeline không khẳng định thứ tự sai |
| Một nguồn bị nghi can thiệp hoặc mâu thuẫn nguồn khác | Ghi giới hạn, xem xét đối chiếu, không tự bỏ evidence bất tiện |
| Collector hoặc containment tạo dấu vết mới trên nguồn | Ghi hành động để phân biệt với dữ liệu sự cố |
| Normalize, redaction hoặc parser thay đổi | Tạo bản dẫn xuất có input/output/tool version, không sửa bản bảo toàn |
| Reviewer muốn tái kiểm một finding | Tìm được evidence locator, method và giới hạn phù hợp |
| Evidence có canary secret/PII hoặc mẫu nghi độc | Không phát tán qua log/ticket/preview hoặc kênh không được cấp |
| Người ngoài case/tenant gọi UI, API hoặc object link | Không vượt phân quyền bằng ID hoặc đường trực tiếp |
| Export chia sẻ bị thiếu file, sai version hoặc chưa có receipt | Không báo bàn giao hoàn tất ngoài contract |
| Archive restore hoặc key/schema cũ cần dùng lại | Đọc, giải mã và xác minh được theo profile |
| Retention hết, hold còn hoặc incident đã đóng | Xử lý theo quyết định/phạm vi thật, không xóa/giữ vô hạn máy móc |
| Kho evidence, manifest store hoặc collector lỗi | Có trạng thái, vùng dự phòng/escalation theo profile, không đổ raw data ra log |

Bằng chứng nghiệm thu cần gồm artifact, manifest, expected digest được bảo vệ, custody/access record, kết quả phân tích và hành vi ở nguồn. Không chỉ kiểm một màn hình có nhãn `VERIFIED`.

Diễn tập nên chọn một câu hỏi thực tế, tạo dữ liệu có ground truth, thu qua các chặng và yêu cầu người khác tái kiểm kết luận. Nó giúp phát hiện thiếu quyền, thiếu metadata, sai parser hoặc archive không dùng được trước khi xảy ra sự cố thật.

Nếu đặt mục tiêu thời gian, cần nêu mốc bắt đầu, điều kiện và loại nguồn. Ví dụ thu một export log đã được chuẩn bị trong vài phút không chứng minh có thể thu mọi dữ liệu volatile trong cùng khoảng thời gian.

## 15. Quản trị evidence trong vòng đời phát triển và sự cố

Evidence readiness cần được thiết kế trước: schema log/audit, inventory nguồn, quyền collector, retention, export API, kho lưu, key và công cụ tái kiểm. Một hệ thống không tạo record cần thiết từ đầu có thể không khôi phục được nó chỉ bằng cách mở một case sau sự cố.

Thay schema, provider, timezone, query interface hoặc vòng đời workload phải đánh giá tác động tới collection profile và phân tích. Method và parser có phiên bản giúp giải thích vì sao cùng nguồn tạo kết quả khác khi công cụ thay đổi.

Đóng điều tra cần tổng hợp nguồn đã có, phần thiếu, finding, evidence hỗ trợ, mức tin cậy, những quyết định phản ứng và công việc còn lại. Việc dịch vụ đã chạy lại không tự xác lập nguyên nhân hoặc tính đầy đủ của bằng chứng.

Những lỗi đặc tả thường gặp:

- **“Có nhiều log là có evidence đầy đủ.”** Chưa chứng minh phạm vi, nguồn, metadata và khả năng truy xuất.
- **“Hash khớp nghĩa là nội dung luôn thật.”** Nhầm toàn vẹn sau mốc thu với tính đúng và đầy đủ của nguồn.
- **“Export job thành công là đã thu xong.”** Bỏ qua part, pagination, truyền và kiểm artifact.
- **“Sắp theo UTC là biết thứ tự.”** Bỏ qua clock skew, khoảng thu và quan hệ giữa các nguồn.
- **“Chỉ cần giữ một screenshot hoặc báo cáo.”** Thiếu input và method để tái kiểm những khẳng định quan trọng.
- **“Cùng hash thì chỉ cần một record.”** Làm mất provenance của các nơi và lần thu khác nhau.
- **“Trong incident ai cũng được xem mọi thứ.”** Mở rộng dữ liệu và secret ngoài scope điều tra.
- **“Đóng case là xóa evidence hoặc giữ mãi.”** Không có retention/hold và quyết định vòng đời phù hợp.

Một yêu cầu incident evidence tốt nối được câu hỏi điều tra với nguồn, phép thu, artifact, lịch sử xử lý và kết luận có giới hạn rõ ràng. Bằng chứng cần được bảo vệ và dùng lại được, còn điều chưa biết phải được giữ đúng trạng thái để người xử lý không nhầm thiếu dữ liệu với sự chắc chắn.

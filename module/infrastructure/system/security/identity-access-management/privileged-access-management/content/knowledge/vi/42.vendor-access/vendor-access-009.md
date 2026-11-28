# Third-party evidence: bằng chứng truy cập đặc quyền của bên thứ ba

## 1. Bằng chứng cần trả lời điều gì?

Một kỹ sư của nhà cung cấp truy cập máy chủ để xử lý sự cố. Ticket đã được duyệt, phiên đi qua PAM và nhóm vận hành thấy dịch vụ hoạt động trở lại. Những thông tin đó chưa đủ để trả lời: người nào thực sự truy cập, họ nhận quyền gì, thao tác trên tài nguyên nào, quyền đã kết thúc chưa và dữ liệu nào chứng minh các kết luận này.

**Third-party evidence** trong PAM là tập bằng chứng có nguồn gốc và mối liên hệ rõ ràng về toàn bộ vòng đời truy cập đặc quyền của bên thứ ba. Bằng chứng bao gồm hồ sơ nhà cung cấp, danh tính cá nhân, căn cứ phê duyệt, quyền được cấp, credential hoặc lease được sử dụng, phiên truy cập, hoạt động tại hệ thống đích và kết quả thu hồi. Mục tiêu là tái dựng được một lần truy cập mà không phải dựa hoàn toàn vào lời kể của người tham gia.

Bên thứ ba có thể là hãng bảo trì, đối tác triển khai, chuyên gia tư vấn hoặc nhà thầu phụ. Một tài khoản thuộc doanh nghiệp không tự động trở thành tài khoản nội bộ về mặt trách nhiệm: tài khoản đó vẫn phải gắn với đơn vị cung cấp và người bảo trợ trong doanh nghiệp.

Có hai nhóm bằng chứng cần phân biệt:

| Nhóm | Ví dụ | Trả lời được | Không tự chứng minh được |
|---|---|---|---|
| Bảo đảm về nhà cung cấp | Hồ sơ đánh giá, cam kết kiểm soát, báo cáo đánh giá độc lập | Nhà cung cấp được xem xét và chấp thuận theo quy trình nào | Một kỹ sư cụ thể đã làm gì trong phiên cụ thể |
| Bằng chứng giao dịch truy cập | Sự kiện xác thực, phê duyệt JIT, phiên PAM, audit tại target, kết quả thu hồi | Diễn biến và phạm vi của lần truy cập | Toàn bộ kiểm soát của nhà cung cấp luôn hiệu quả |

Một báo cáo đánh giá tốt không thay thế nhật ký phiên. Ngược lại, có video một phiên cũng không chứng minh doanh nghiệp đã đánh giá nhà cung cấp, cấp đúng phạm vi hoặc thu hồi tất cả quyền còn tồn tại.

Sau bài học này, người học cần có khả năng thiết kế một gói bằng chứng cho vendor access, tìm mắt xích còn thiếu, đánh giá giới hạn của từng nguồn và kiểm chứng việc kết thúc truy cập mà không đưa secret vào hồ sơ.

## 2. Đơn vị quản lý là một lần truy cập có trách nhiệm

Nếu chỉ gom log theo tên nhà cung cấp, doanh nghiệp sẽ khó phân biệt các kỹ sư, các hợp đồng và các môi trường. Nếu chỉ gom theo tài khoản target, doanh nghiệp có thể mất danh tính con người khi PAM dùng một tài khoản dịch vụ được chia sẻ ở phía hệ thống đích.

Một hồ sơ bằng chứng cần nối được ít nhất các định danh sau:

- **Vendor ID:** định danh ổn định của đơn vị cung cấp; nhà thầu phụ phải được nhận diện riêng khi có liên quan.
- **External subject ID:** định danh bất biến của cá nhân hoặc workload; email là thuộc tính hiển thị, không nên là khóa liên kết duy nhất.
- **Sponsor và resource owner:** người bảo trợ việc sử dụng bên thứ ba và chủ thể chịu trách nhiệm về tài nguyên.
- **Request ID và approval ID:** yêu cầu công việc, quyết định phê duyệt và phiên bản phạm vi đã được duyệt.
- **Grant ID hoặc lease ID:** lần cấp quyền hoặc cấp credential cụ thể, gồm thời điểm bắt đầu và kết thúc.
- **Session ID:** phiên do PAM/broker quản lý; một yêu cầu có thể phát sinh nhiều phiên.
- **Target identity:** tài nguyên và tài khoản/quyền hiệu lực ở phía đích.
- **Event ID và artifact ID:** sự kiện và tệp bằng chứng được dùng để tái dựng diễn biến.

Không dùng IP làm bằng chứng duy nhất của danh tính. IP có thể thuộc NAT, proxy hoặc thiết bị trung gian. Tên tài khoản cũng có thể được tái sử dụng sau khi nhân sự rời nhà cung cấp. Khóa bất biến và lịch sử ánh xạ theo thời gian giúp tránh gán nhầm hoạt động.

Mối liên hệ điển hình:

~~~mermaid
flowchart LR
    V[Nhà cung cấp và cá nhân] --> R[Yêu cầu có phạm vi]
    R --> A[Phê duyệt]
    A --> G[Grant hoặc credential lease]
    G --> S[Phiên PAM]
    S --> T[Audit ở hệ thống đích]
    G --> C[Thu hồi và kiểm chứng]
    S --> E[Gói bằng chứng có manifest]
    T --> E
    C --> E
~~~

Sơ đồ không có nghĩa mọi hệ thống đã dùng chung một ID. Khi phải nối dữ liệu từ nhiều sản phẩm, cần ghi rõ quy tắc liên kết, mức tin cậy và trường hợp chưa liên kết được. Một phép ghép dựa trên tài khoản, target và khoảng thời gian chỉ là suy luận; không nên trình bày nó như một liên kết trực tiếp bằng session ID.

## 3. Lập ma trận bằng chứng trước khi mở quyền

Bằng chứng hiệu quả phải được thiết kế cùng quy trình cấp quyền. Sau khi phiên đã kết thúc, không thể tạo lại bản ghi hình hay nhật ký chưa từng được thu thập.

Ma trận dưới đây là một mẫu triển khai, không phải yêu cầu cứng cho mọi sản phẩm:

| Giai đoạn | Bằng chứng cần có | Nguồn ưu tiên | Người chịu trách nhiệm |
|---|---|---|---|
| Chấp thuận vendor | Đơn vị, công việc, sponsor, điều kiện được phép truy cập | Hồ sơ quản lý nhà cung cấp và hệ thống yêu cầu | Chủ hợp đồng/sponsor |
| Đăng ký danh tính | Cá nhân, vendor, định danh ngoài, thời hạn được tham gia | Nguồn danh tính và hồ sơ onboarding | Nhóm IAM |
| Yêu cầu công việc | Mục đích, target, quyền, thời gian, phương thức truy cập | Ticket hoặc cổng yêu cầu | Người yêu cầu |
| Phê duyệt | Người duyệt, quyết định, phạm vi đã duyệt, thời điểm | Workflow có audit | Resource owner |
| Cấp quyền | Grant/lease, quyền hiệu lực, TTL, policy version | PAM/vault và hệ thống cấp quyền | Nhóm PAM |
| Thiết lập phiên | Danh tính, kết quả xác thực, thiết bị theo chính sách, đường truy cập | IdP và broker | Nhóm IAM/PAM |
| Thực hiện công việc | Phiên, lệnh nếu có, truyền tệp, thay đổi tại target | Broker và audit target | Vận hành/SOC |
| Kết thúc | Đóng phiên, thu hồi grant, vô hiệu hóa credential/token, kiểm chứng | PAM và cơ chế kiểm tra độc lập | Nhóm PAM/target owner |
| Đóng hồ sơ | Manifest, thiếu hụt, người kiểm tra, giới hạn kết luận | Kho bằng chứng | Evidence owner |

Với mỗi loại bằng chứng, bổ sung các thuộc tính: có bắt buộc không, phải có trước hay sau truy cập, thời gian trễ chấp nhận được, nơi lưu, người được xem, thời hạn lưu theo chính sách và cách xử lý nếu thiếu.

Ví dụ, môi trường thử nghiệm có thể dùng audit lệnh thay cho quay màn hình nếu chính sách cho phép. Môi trường nhạy cảm có thể yêu cầu cả broker audit và target audit. Quyết định cần xuất phát từ tác động và khả năng quan sát thực tế, không phải từ mong muốn thu thập càng nhiều càng tốt.

Trước khi mở đường truy cập, kiểm tra một luồng mẫu để biết broker có ghi đúng target, event có mang correlation ID và bản ghi có thể phát lại hay không. Đèn báo “recording enabled” là cấu hình; khả năng đọc được tệp của phiên thực tế mới là bằng chứng vận hành.

## 4. Phạm vi được duyệt phải là dữ liệu có thể đối chiếu

Ticket ghi “hỗ trợ hệ thống” quá rộng để đánh giá một phiên đặc quyền. Phạm vi nên chỉ rõ môi trường, target hoặc nhóm target, thao tác được phép, khoảng thời gian, tài khoản/quyền và giới hạn truyền dữ liệu.

Các thay đổi trong phạm vi cần có lịch sử. Nếu bổ sung máy chủ giữa phiên, bằng chứng phải cho biết ai duyệt phần bổ sung, thời điểm nào và nó áp dụng cho grant nào. Không sửa nội dung ticket hiện tại rồi dùng bản mới để giải thích ngược một hành động đã xảy ra trước khi được duyệt.

Ví dụ yêu cầu giả lập:

~~~yaml
accessRequest:
  id: REQ-VND-204
  vendorId: VND-017
  externalSubjectId: ext-subject-083
  sponsorId: employee-214
  purpose: Phân tích lỗi kết nối của dịch vụ thanh toán trong lab
  environment: lab
  targets:
    - assetId: app-lab-02
      allowedRole: support-diagnostics
  permittedActions:
    - Đọc trạng thái dịch vụ và log đã che dữ liệu nhạy cảm
    - Thu thập bộ chẩn đoán vào kho nội bộ được chỉ định
  prohibitedActions:
    - Tạo tài khoản hoặc khóa truy cập lâu dài
    - Sao chép dữ liệu khách hàng ra ngoài
  validFrom: "2026-11-27T02:00:00Z"
  validUntil: "2026-11-27T03:00:00Z"
  approvalId: APR-601
  scopeVersion: 3
~~~

Đây là biểu diễn minh họa, không phải schema của một sản phẩm PAM. Không đưa mật khẩu, private key, OTP hay token còn hiệu lực vào yêu cầu. Nếu cần liên kết credential, sử dụng ID đối tượng trong vault hoặc lease ID, không dùng chính giá trị credential.

Quyết định phê duyệt phải được gắn với scope version. Chỉ lưu approval ID mà không biết approval đó duyệt nội dung nào sẽ làm mất khả năng đối chiếu quyền thực tế với quyền đã được phép.

## 5. Bằng chứng trong phiên: phối hợp broker và hệ thống đích

PAM broker quan sát đường truy cập đi qua nó. Hệ thống đích quan sát hoạt động mà nó có khả năng audit. Hai góc nhìn bổ sung cho nhau.

| Nguồn | Điểm mạnh | Giới hạn cần ghi nhận |
|---|---|---|
| IdP/xác thực | Xác định lần xác thực, subject và các điều kiện đã được đánh giá | Xác thực thành công không chứng minh target đã cấp đúng quyền |
| PAM broker | Nối danh tính yêu cầu với phiên, đường truy cập, sự kiện điều khiển | Có thể không nhìn thấy đường truy cập đi vòng hoặc hành động nằm ngoài giao thức được hỗ trợ |
| Vault/credential service | Ghi nhận cấp secret, lease, luân chuyển, thu hồi | Secret đã được lấy ra có thể được sử dụng ngoài broker nếu kiến trúc cho phép |
| Audit của target | Ghi thao tác, quyền hiệu lực, thay đổi tài nguyên | Có thể thiếu danh tính con người nếu chỉ ghi tài khoản dùng chung |
| Truyền tệp | Ghi nhận hướng truyền, đích, kích thước hoặc digest khi có | Không tự chứng minh mọi dữ liệu đã rời hệ thống qua mọi kênh |
| Recording | Tái hiện một phần tương tác của người thao tác | Không bảo đảm bao phủ API, tiến trình nền hoặc mọi chi tiết của hành động |
| Network telemetry | Cho thấy kết nối, đường đi và target được liên hệ | Không thay thế audit thao tác hay ánh xạ danh tính |

### 5.1. Tài khoản dùng chung ở target

Nếu target chỉ hỗ trợ tài khoản quản trị chung, PAM có thể vẫn quy trách nhiệm cho từng người bằng cách giữ chuỗi liên kết giữa external subject, grant và phiên. Tuy nhiên, mức độ quy trách nhiệm còn phụ thuộc việc chặn đường đi vòng, cách kiểm soát credential và khả năng gắn hoạt động đích với phiên.

Hai phiên cùng dùng một tài khoản trong cùng khoảng thời gian có thể tạo mơ hồ nếu target không có session ID hoặc dấu hiệu tách biệt. Phải đánh dấu phần mơ hồ đó, hoặc cải thiện thiết kế bằng tài khoản tạm riêng, định danh phiên được hỗ trợ hay giới hạn đồng thời. Không chọn ngẫu nhiên một kỹ sư để gán mọi sự kiện của tài khoản chung.

### 5.2. Lệnh và thay đổi thực tế

Một lệnh xuất hiện trong nhật ký broker có thể chỉ chứng minh lệnh đã được nhập/gửi. Muốn kết luận thay đổi thành công, cần thêm kết quả thực thi hoặc audit/trạng thái ở target.

Ví dụ, “đã gọi lệnh khởi động lại dịch vụ” khác với “dịch vụ đã khởi động lại và healthy”. Hồ sơ nên tách:

1. Hành động được yêu cầu hoặc phát lệnh.
2. Kết quả được thành phần thực thi báo về.
3. Trạng thái được quan sát ở target.
4. Kết luận của người rà soát dựa trên các dữ liệu đó.

Không phải phiên nào cũng cần quay toàn bộ màn hình. Nhưng nếu chính sách yêu cầu recording, một log “session started” không thể thay cho tệp recording đọc được.

### 5.3. Workload và hỗ trợ tự động

Vendor có thể gọi API bằng workload thay vì đăng nhập tương tác. Khi đó, bằng chứng cần liên kết workload identity, đơn vị sở hữu, phiên bản tích hợp nếu phù hợp, grant/token identifier an toàn để lưu, request ID và audit của API.

Không ép mọi hoạt động tự động thành “session video”. Hãy chọn dấu vết phù hợp giao thức, đồng thời chứng minh workload không nhận quyền rộng hoặc tồn tại lâu hơn công việc đã được duyệt.

## 6. Chuẩn hóa sự kiện để liên kết mà không làm mất nguồn

Một bản ghi chuẩn hóa nên giữ được ID của sự kiện gốc, nguồn, thời gian sự kiện, thời gian tiếp nhận và các trường tương quan. Không chỉ lưu câu mô tả đọc được như “vendor đã truy cập”.

Ví dụ sự kiện giả lập sau khi broker chấp nhận mở phiên:

~~~json
{
  "schemaVersion": "1",
  "eventId": "evt-broker-00821",
  "eventType": "pam.session.started",
  "eventTime": "2026-11-27T02:12:41Z",
  "observedTime": "2026-11-27T02:12:43Z",
  "source": {
    "systemId": "pam-broker-lab-01",
    "nativeEventId": "native-58210"
  },
  "actor": {
    "vendorId": "VND-017",
    "externalSubjectId": "ext-subject-083",
    "identityProviderId": "external-idp-lab"
  },
  "authorization": {
    "requestId": "REQ-VND-204",
    "approvalId": "APR-601",
    "scopeVersion": 3,
    "grantId": "grant-098",
    "policyVersion": "vendor-support-v7"
  },
  "session": {
    "sessionId": "session-782",
    "protocol": "SSH",
    "targetAssetId": "app-lab-02",
    "targetAccountId": "support-diagnostics"
  },
  "result": {
    "outcome": "success",
    "meaning": "Broker đã chấp nhận và thiết lập phiên"
  },
  "rawEvidenceRef": "evidence://CASE-VND-204/broker/events-02"
}
~~~

Trường meaning chỉ rõ kết quả thuộc bước nào; success của việc mở phiên không có nghĩa công việc đã hoàn thành.

Các điểm cần giữ khi chuẩn hóa:

- Phân biệt external subject với target account; không ghi đè trường này bằng trường kia.
- Bảo toàn event ID gốc để đối chiếu với hệ thống nguồn.
- Ghi rõ bản ghi được tạo lại, chuyển đổi hoặc che dữ liệu theo phiên bản xử lý nào.
- Phân biệt kết quả thành công, thất bại, đang xử lý và chưa biết.
- Giữ bản gốc theo chính sách, còn bản chuẩn hóa phục vụ tìm kiếm và đối chiếu.
- Ghi nhận sự kiện đến trễ; không bỏ qua chỉ vì hồ sơ đã qua một lần rà soát.

Tên trường ở ví dụ chỉ là thiết kế minh họa. Không giả định mọi sản phẩm đã xuất đủ các trường này. Những trường không thu được phải được biểu diễn là thiếu/không áp dụng kèm lý do, thay vì điền giá trị phỏng đoán để hoàn thiện schema.

## 7. Thời gian, thứ tự sự kiện và khả năng phát hiện thiếu hụt

Một timeline có giá trị khi biết thời gian đó đến từ đâu và chính xác đến mức nào. Nên dùng định dạng có múi giờ rõ ràng, giữ thời gian gốc, chuẩn hóa để truy vấn và theo dõi độ lệch đồng hồ của các nguồn.

Cần phân biệt ba thời điểm:

| Thời điểm | Ý nghĩa | Ví dụ vấn đề |
|---|---|---|
| Event time | Nguồn cho rằng hành động xảy ra lúc nào | Đồng hồ target bị chậm |
| Ingestion/observed time | Hệ thống thu thập nhận hoặc quan sát bản ghi lúc nào | Queue chuyển log bị nghẽn |
| Review time | Người hoặc quy trình đánh giá dữ liệu lúc nào | Hồ sơ được xem trước khi log đến đủ |

Không sắp xếp mù mọi nguồn theo một cột rồi kết luận thứ tự tuyệt đối. Nếu độ lệch có thể lớn hơn khoảng cách hai sự kiện, chỉ nên kết luận chúng xảy ra trong một khoảng không chắc chắn hoặc dựa thêm quan hệ nhân quả như grant ID.

Ví dụ timeline mong đợi cho yêu cầu trên:

| Mốc | Dấu vết | Điều cần đối chiếu |
|---|---|---|
| 02:05 | Approval APR-601 duyệt scope version 3 | Người duyệt có thẩm quyền, phạm vi chưa thay |
| 02:11 | Grant grant-098 được kích hoạt | Target/quyền và TTL nằm trong yêu cầu |
| 02:12 | Session session-782 bắt đầu | Người dùng và đường truy cập khớp grant |
| 02:20 | Thu thập chẩn đoán tại app-lab-02 | Thao tác nằm trong phạm vi |
| 02:36 | Session kết thúc | Có kết quả đóng phiên |
| 02:37 | Thu hồi grant và lease liên quan | Có kết quả, không chỉ có yêu cầu thu hồi |
| 02:39 | Kiểm tra không còn phiên/quyền được theo dõi | Biết phạm vi và cách kiểm tra |
| Sau khoảng trễ thu thập đã định | Đóng hồ sơ bằng chứng | Không còn nguồn bắt buộc đang chờ |

Các giờ trên là ví dụ thiết kế. Không mặc định mọi hệ thống phải đáp ứng một ngưỡng phút cụ thể.

Khả năng phát hiện thiếu log cần dựa thêm heartbeat, health của collector, sequence number nếu nguồn hỗ trợ và đối soát số lượng phiên. “Không tìm thấy hoạt động bất thường” chỉ có ý nghĩa trong phạm vi nguồn đang hoạt động và khoảng thời gian có dữ liệu.

## 8. Kết thúc phiên chưa phải là kết thúc quyền

Đây là điểm dễ tạo hồ sơ trông đầy đủ nhưng kết luận sai. Một vendor có thể đóng phiên broker trong khi:

- Quyền nhóm vẫn còn ở target.
- Token API chưa hết hiệu lực.
- Credential đã được lấy ra nhưng chưa được luân chuyển/vô hiệu hóa.
- Phiên phía target hoặc tiến trình nền vẫn tồn tại.
- Kỹ sư đã tạo khóa, tài khoản hay đường truy cập thứ cấp ngoài phạm vi.
- Truy cập qua tích hợp hoặc target khác của cùng công việc chưa được đóng.

Tập bằng chứng kết thúc cần bao phủ các đường quyền thuộc phạm vi công việc, không chỉ một session ID.

~~~text
Session ended
    ↓
Yêu cầu thu hồi các grant/lease liên quan
    ↓
Ghi nhận kết quả từ từng thành phần thực thi
    ↓
Kiểm tra quyền và phiên tồn tại ở phạm vi target đã xác định
    ↓
Ghi kết luận, ngoại lệ và phần chưa kiểm chứng
~~~

Sự kiện “revoke requested” chứng minh hệ thống đã nhận yêu cầu; chưa chứng minh quyền bị thu hồi. Trường hợp broker mất kết nối với target phải được ghi là đang chờ hoặc chưa xác minh, không chuyển thành thành công chỉ vì ticket đã đóng.

Bằng chứng kiểm chứng có thể bao gồm kết quả truy vấn membership/quyền hiệu lực, danh sách phiên còn hoạt động, trạng thái lease, xác nhận credential đã luân chuyển và một phép thử truy cập bị từ chối trong môi trường, tài khoản và phương pháp đã được cho phép.

Không lặp lại credential còn hiệu lực trong phép thử hoặc xuất chúng vào log. Không thực hiện phép thử gây khóa tài khoản, ảnh hưởng dịch vụ hay vượt phạm vi được duyệt. Khi chỉ kiểm tra một phần đường truy cập, kết luận phải nói rõ phần đó; không suy rộng thành “mọi khả năng truy cập đã bị xóa”.

Nếu phát hiện tài khoản hoặc khóa ngoài phạm vi, chuyển sang quy trình xử lý sự cố/ngoại lệ được doanh nghiệp quy định. Ghi lại việc phát hiện và trách nhiệm xử lý, không sửa hồ sơ để che khoảng trống.

## 9. Bảo vệ tính toàn vẹn và nguồn gốc của bằng chứng

Tính toàn vẹn và tính đúng đắn là hai thuộc tính khác nhau. Digest khớp giúp phát hiện tệp đã đổi so với giá trị tham chiếu. Nó không tự chứng minh nội dung ban đầu đúng, người xuất tệp trung thực hay nguồn đã ghi đầy đủ sự kiện.

Một thiết kế bằng chứng cần phối hợp:

1. **Thu thập từ nguồn được kiểm soát:** danh tính collector, quyền đọc, kết nối, cấu hình nguồn và thời điểm lấy.
2. **Bảo toàn bản gốc:** lưu theo chính sách và giới hạn quyền sửa/xóa, tách khỏi quyền quản trị thường ngày khi phù hợp.
3. **Manifest và digest:** liên kết artifact ID, đường dẫn, kích thước, thuật toán/digest, nguồn và thời gian xuất.
4. **Audit việc truy cập kho:** ai xem, xuất, tạo bản dẫn xuất hay thay đổi cấu hình lưu trữ.
5. **Lưu dấu xử lý:** chuyển định dạng, che dữ liệu hoặc trích xuất đều có nguồn cha và phương pháp.
6. **Kiểm tra khả năng đọc:** artifact phải mở được bằng công cụ và quyền được quản lý, kể cả khi đã mã hóa.

Nếu kẻ sửa tệp cũng thay được manifest và digest mà không để lại dấu vết, digest riêng lẻ không cung cấp bảo đảm mạnh. Có thể bảo vệ manifest bằng cơ chế ký hoặc kho có kiểm soát tính bất biến, tùy thiết kế. Chữ ký xác nhận quan hệ với khóa và dữ liệu được ký; vẫn phải quản lý khóa, xác định bên ký và đánh giá độ tin cậy của nguồn.

Mã hóa bảo vệ tính bí mật, nhưng không thay thế chính sách truy cập và lưu vết. Bản ghi được mã hóa mà không còn khóa giải mã hoặc công cụ đọc cũng có thể không phục vụ được điều tra.

### 9.1. Chuỗi quản lý bằng chứng

Chuỗi quản lý bằng chứng mô tả ai thu thập, ai bàn giao, ai truy cập và xử lý gì trên artifact. Mỗi lần chuyển giao nên ghi:

- Artifact ID và digest tham chiếu.
- Người/hệ thống giao, người/hệ thống nhận.
- Thời gian và mục đích chuyển.
- Vị trí nguồn, vị trí đích được kiểm soát.
- Kết quả kiểm tra và bản dẫn xuất nếu có.

Không cần tạo thủ tục nặng cho mọi log vận hành. Nhưng với gói dùng cho điều tra hoặc đánh giá quan trọng, thiếu lịch sử chuyển giao sẽ làm giảm khả năng giải thích vì sao bản đang xem là bản thu được từ nguồn.

### 9.2. Ví dụ kiểm tra digest trong PowerShell

Đoạn dưới chỉ minh họa cách đối chiếu một tệp đã xuất với digest đáng tin cậy trong manifest. Đường dẫn và tên tệp là dữ liệu lab.

~~~powershell
$evidenceFile = 'C:\PamLab\Evidence\CASE-VND-204\broker-events.jsonl'
$expectedDigest = '<SHA256_TU_MANIFEST_DA_DUOC_KIEM_TRA>'

if ($expectedDigest -notmatch '^[0-9A-Fa-f]{64}$') {
    throw 'Digest tham chiếu không hợp lệ.'
}

$actualDigest = (Get-FileHash -LiteralPath $evidenceFile -Algorithm SHA256).Hash

if ($actualDigest -ine $expectedDigest) {
    throw 'Digest không khớp; cần điều tra trước khi sử dụng artifact.'
}

'Artifact khớp digest tham chiếu.'
~~~

Kết quả khớp chỉ có giá trị trong giới hạn đã nêu. Không dùng thông báo này để kết luận tệp “không thể bị giả mạo” hoặc “chứng minh đầy đủ mọi thao tác”.

## 10. Nhận bằng chứng do nhà cung cấp cung cấp

Trong một số mô hình, doanh nghiệp không kiểm soát toàn bộ nguồn log. Nhà cung cấp có thể gửi báo cáo công việc, log công cụ hỗ trợ hoặc bản trích xuất từ hệ thống của họ.

Cần phân biệt rõ:

| Loại | Cách ghi trong hồ sơ | Cách sử dụng |
|---|---|---|
| Thu trực tiếp từ nguồn doanh nghiệp kiểm soát | Nguồn, collector, artifact gốc | Làm nguồn đối chiếu hoạt động tại hệ thống doanh nghiệp |
| Nhà cung cấp xuất từ hệ thống của họ | Người xuất, nguồn tự khai, cách xuất, thời gian, digest | Đánh giá nguồn gốc và đối chiếu với dấu vết độc lập |
| Nhà cung cấp viết báo cáo tường thuật | Người viết, phạm vi, thời điểm, các tham chiếu | Dùng giải thích công việc; không coi là thay thế log máy |
| Ảnh chụp màn hình | Người tạo, thời gian, bối cảnh được biết | Là chứng cứ bổ sung, khó bảo đảm đầy đủ diễn biến |
| Tệp đã che dữ liệu/chuyển đổi | Nguồn cha, phương pháp xử lý, phần bị bỏ | Dùng đúng giới hạn của bản dẫn xuất |

Ví dụ, vendor nói “chỉ tải log ứng dụng”. Broker có sự kiện tải tệp, target có đường dẫn gói chẩn đoán và kho nội bộ nhận đúng digest. Ba nguồn này hỗ trợ kết luận tốt hơn một email xác nhận.

Ngược lại, nếu vendor gửi tệp log không có event ID, không rõ múi giờ và không mô tả bộ lọc khi xuất, cần ghi thiếu hụt đó. Không tự thêm timestamp hoặc nhận xét như thể chúng có trong bản gốc.

Kênh tiếp nhận artifact nên được kiểm soát quyền, có quét/kiểm tra tệp phù hợp và hạn chế việc mở nội dung chủ động trên máy phân tích. Tệp do vendor gửi có thể chứa secret hoặc dữ liệu nhạy cảm ngoài dự kiến. Nếu phát hiện, cô lập theo quy trình xử lý hiện hành, hạn chế phân phối và ghi lại bản dẫn xuất đã che; không chép dữ liệu đó vào ticket rộng người xem.

Thỏa thuận vận hành nên xác định từ đầu những sự kiện vendor phải cung cấp, thời gian cung cấp, đầu mối giải trình, quyền truy cập bản gốc và cách kết thúc khi vendor không còn khả năng cung cấp dữ liệu. Những nội dung này cần được doanh nghiệp xác lập theo chính sách và các bên phụ trách; một mẫu kỹ thuật không thay thế quyết định đó.

## 11. Thiết kế gói bằng chứng có thể kiểm tra lại

Một gói bằng chứng nên có cấu trúc ổn định, không chỉ là tệp ZIP chứa nhiều log khó tìm.

Ví dụ tổ chức logic:

~~~text
CASE-VND-204/
├── manifest.yml
├── request/
│   └── approved-scope-v3.json
├── identity/
│   └── external-subject-mapping.json
├── grants/
│   └── grant-098-events.jsonl
├── broker/
│   ├── session-782-events.jsonl
│   └── recording-reference.json
├── target/
│   └── app-lab-02-audit.jsonl
├── closure/
│   └── revocation-verification.json
└── review/
    └── findings.yml
~~~

Đây là mô hình tổ chức, không yêu cầu sao chép mọi recording vào cùng thư mục. Recording lớn có thể được giữ trong kho riêng, với tham chiếu ổn định, quyền truy cập phù hợp và bằng chứng kiểm tra khả năng đọc. Một URL tạm sắp hết hạn không phải tham chiếu lưu trữ bền vững.

Manifest minh họa:

~~~yaml
evidencePackage:
  id: CASE-VND-204
  requestId: REQ-VND-204
  vendorId: VND-017
  scopeVersion: 3
  ownerId: pam-evidence-owner
  collectionWindow:
    from: "2026-11-27T02:00:00Z"
    to: "2026-11-27T03:15:00Z"
  completeness: PARTIAL
  artifacts:
    - id: ART-001
      sourceSystem: ticketing-lab
      sourceNativeId: REQ-VND-204-v3
      path: request/approved-scope-v3.json
      digestAlgorithm: SHA-256
      digest: "<DIGEST_THUC_TE_DUOC_TINH_KHI_XUAT>"
      classification: internal-restricted
    - id: ART-002
      sourceSystem: pam-broker-lab-01
      sourceNativeId: session-782
      path: broker/session-782-events.jsonl
      digestAlgorithm: SHA-256
      digest: "<DIGEST_THUC_TE_DUOC_TINH_KHI_XUAT>"
      classification: internal-restricted
  knownGaps:
    - id: GAP-01
      description: Chưa nhận audit target cho khoảng 02:18 đến 02:24 UTC
      ownerId: target-operations
      impact: Chưa xác nhận được đầy đủ hoạt động tại target trong khoảng này
      state: OPEN
  review:
    outcome: NEEDS_FOLLOW_UP
    reviewedBy: reviewer-031
~~~

Các digest trong ví dụ là placeholder, không phải giá trị kiểm tra hợp lệ. Khi triển khai, chỉ dùng kết quả tính từ tệp thật và quy trình xác minh nguồn tham chiếu.

Hồ sơ đang PARTIAL không được gắn nhãn hoàn tất chỉ vì tất cả đường dẫn trong manifest đều tồn tại. Cần biết danh mục bằng chứng bắt buộc nào còn thiếu và hệ quả đối với kết luận.

Nếu bổ sung artifact sau rà soát, tạo lịch sử phiên bản hoặc bản bổ sung có liên kết rõ ràng. Không âm thầm sửa kết luận đã phát hành. Bản cũ và bản mới cần giải thích được quan hệ theo chính sách lưu trữ của tổ chức.

## 12. Tính đầy đủ: bắt đầu từ tập truy cập phải có bằng chứng

Một lỗi phổ biến là bắt đầu từ kho recording rồi thấy mọi recording đều có ticket, từ đó kết luận mọi vendor access đều được ghi nhận. Cách này bỏ sót chính những phiên không có recording.

Để kiểm tra tính đầy đủ, phải bắt đầu từ một tập đối chiếu có phạm vi rõ ràng, chẳng hạn mọi grant vendor được kích hoạt trong khoảng thời gian. Sau đó kiểm tra các bằng chứng mong đợi cho từng grant. Bổ sung đối soát từ phía target và network để tìm đường truy cập ngoài tập grant được quản lý.

Mẫu truy vấn khái niệm:

~~~sql
-- Pseudocode: tên bảng và cột cần ánh xạ theo hệ thống thực tế.
-- Tập gốc gồm mọi grant vendor đã kích hoạt trong phạm vi rà soát.
SELECT
    g.grant_id,
    g.request_id,
    g.external_subject_id,
    CASE WHEN a.approval_id IS NULL
         THEN 'MISSING' ELSE 'PRESENT' END AS approval_evidence,
    CASE WHEN s.session_id IS NULL
         THEN 'NO_SESSION_EVIDENCE' ELSE 'PRESENT' END AS session_evidence,
    CASE WHEN r.verification_id IS NULL
         THEN 'UNVERIFIED' ELSE r.verification_outcome END AS revocation_evidence
FROM vendor_grants g
LEFT JOIN approvals a
    ON a.approval_id = g.approval_id
   AND a.scope_version = g.approved_scope_version
LEFT JOIN pam_sessions s
    ON s.grant_id = g.grant_id
LEFT JOIN revocation_verifications r
    ON r.grant_id = g.grant_id
WHERE g.activated_at >= :window_start
  AND g.activated_at < :window_end;
~~~

Truy vấn này là điểm xuất phát, chưa phải quy tắc kết luận hoàn chỉnh:

- Một grant có thể không được sử dụng; cần lý do và bằng chứng kết thúc grant, không bịa phiên.
- Grant cho API/workload có thể cần audit request thay vì pam_sessions.
- Một grant có nhiều phiên sẽ tạo nhiều hàng; phải tổng hợp theo đúng quan hệ một-nhiều.
- Grant chưa đến hạn không nên bị kết luận thu hồi thất bại; vẫn cần biết nó còn hiệu lực.
- PRESENT không có nghĩa dữ liệu đúng phạm vi, đọc được hoặc đầy đủ.
- Bản ghi thu hồi có kết quả thất bại vẫn là bằng chứng hiện diện, nhưng kiểm soát chưa đạt.
- Bảng grant không bao phủ tài khoản/đường đi vòng chưa được đưa vào PAM.

Sau bước tìm thiếu hụt, cần đối chiếu quyền hiệu lực, target, thời gian và chủ thể. Những chỗ ghép nhờ khoảng thời gian hoặc tên tài khoản phải có nhãn về phương pháp và mức chắc chắn.

## 13. Giảm dữ liệu nhạy cảm mà vẫn giữ khả năng giải trình

Bằng chứng PAM có thể chứa thông tin định danh, đường dẫn nội bộ, cấu hình, dữ liệu ứng dụng và giá trị nhạy cảm vô tình xuất hiện trên màn hình. Thu thập toàn bộ không đồng nghĩa ai cũng được xem toàn bộ.

Một mô hình phân quyền có thể tách:

| Vai trò | Quyền phù hợp theo nhiệm vụ |
|---|---|
| Sponsor/resource owner | Xem tình trạng và kết luận về yêu cầu thuộc phạm vi mình phụ trách |
| Người rà soát bằng chứng | Đọc các artifact cần thiết để đối chiếu |
| Người điều tra được cấp quyền | Đọc bản gốc nhạy cảm khi có căn cứ và phạm vi được duyệt |
| Người quản trị kho | Vận hành lưu trữ; quyền đọc nội dung cần được xem xét riêng |
| Vendor | Xem hoặc nhận phần bằng chứng của mình theo thỏa thuận, sau kiểm tra dữ liệu |

Thực hiện che hoặc loại bỏ secret tại nguồn nếu có thể, nhưng phải hiểu cơ chế đó có làm mất dấu vết hành động cần thiết hay không. Bản che dữ liệu nên có liên kết với bản gốc được bảo vệ và ghi rõ những lớp dữ liệu đã bị loại, trong phạm vi chính sách cho phép.

Không đưa full recording hoặc log chứa secret vào email, ticket công khai hay báo cáo tổng hợp. Báo cáo thường chỉ cần artifact ID, kết luận và đoạn trích đã được kiểm tra. Quyền xuất dữ liệu phải có audit vì xuất ra ngoài kho sẽ tạo thêm một bản sao cần quản lý.

Thời hạn lưu phải được xác định theo chính sách, mục đích, cam kết và yêu cầu áp dụng của doanh nghiệp. Không lấy thời hạn mặc định của một sản phẩm làm câu trả lời chung. Nếu một vụ việc có yêu cầu giữ bằng chứng, quy trình xử lý phải ngăn xóa theo lịch trong đúng phạm vi và ghi nhận việc giữ đó.

Việc hết hợp đồng với vendor không tự động có nghĩa phải xóa ngay mọi bằng chứng, cũng không cho phép giữ vô thời hạn. Quy trình kết thúc phải tách thu hồi quyền truy cập khỏi quyết định lưu/xóa hồ sơ theo chính sách.

## 14. Tình huống thực hành: hồ sơ “đủ tệp” nhưng chưa đủ kết luận

Giả sử vendor xử lý lỗi ở app-lab-02. Hồ sơ có ticket, approval, recording và email xác nhận hoàn tất. Khi đối chiếu, nhóm PAM thấy:

1. Recording mang session-782 và target đúng.
2. Ticket hiện tại hiển thị scope version 4, nhưng approval APR-601 duyệt version 3.
3. Target audit có một lần đăng nhập bằng tài khoản hỗ trợ sau khi phiên broker kết thúc.
4. Vault ghi revoke requested, chưa có kết quả luân chuyển credential.
5. Log target được chuyển đến trễ; collector có khoảng gián đoạn.

### 14.1. Những điều có thể kết luận ngay

Có bằng chứng về một phiên broker cụ thể và phạm vi target của phiên đó. Có yêu cầu thu hồi được phát ra. Có dấu vết ở target cần tiếp tục liên kết.

Chưa thể kết luận mọi thao tác đều được phê duyệt theo version 4, quyền đã kết thúc hay lần đăng nhập sau phiên chắc chắn thuộc kỹ sư vendor.

### 14.2. Hướng xử lý hồ sơ

Giữ approval gốc và lấy lại phạm vi version 3 từ lịch sử. Xác định nội dung version 4 được sửa lúc nào, có cần phê duyệt mới hay không. Đối chiếu lần đăng nhập sau phiên bằng dữ liệu mạng, tài khoản, session và lịch sử cấp credential; ghi rõ nếu chưa đủ cơ sở quy trách nhiệm.

Kiểm tra trạng thái thu hồi thực tế, khả năng credential vẫn dùng được và những phiên/quyền còn lại trong phạm vi đã xác định. Đánh dấu việc gián đoạn collector và chờ dữ liệu đến theo quy trình thu thập, không coi dữ liệu chưa đến là “không có hoạt động”.

Nếu phát hiện hành vi ngoài phạm vi hoặc quyền còn mở, chuyển xử lý theo quy trình vận hành/sự cố. Hồ sơ bằng chứng ghi nhận việc đó và người nhận trách nhiệm, thay vì chỉ đổi ticket thành Done.

### 14.3. Kết luận có giới hạn

Một kết luận phù hợp có thể là:

> Đã xác nhận phiên broker session-782 truy cập app-lab-02 bằng grant-098. Phạm vi đã được duyệt là version 3. Chưa xác nhận được việc thu hồi credential và chưa liên kết chắc chắn lần đăng nhập tại target sau khi phiên kết thúc. Hồ sơ đang chờ xử lý GAP-01 và GAP-02.

Cách viết này tách sự kiện đã xác minh, giới hạn quan sát và phần cần theo dõi. Nó hữu ích hơn một câu “vendor compliant” không chỉ rõ căn cứ.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng email làm khóa duy nhất | Nhầm người khi email đổi hoặc được tái sử dụng | Dùng subject ID ổn định và lịch sử thuộc vendor |
| Chỉ lưu trạng thái ticket hiện tại | Mất phạm vi thực sự được duyệt | Giữ scope version và audit thay đổi |
| Chỉ ghi tài khoản target | Không xác định người ngoài đã dùng tài khoản chung | Nối subject, grant, broker session và target event |
| Chỉ giữ screenshot/recording | Bỏ sót API, tiến trình nền và thay đổi tại target | Bổ sung nguồn audit phù hợp giao thức |
| Xem revoke requested là hoàn tất | Quyền hoặc credential có thể còn hiệu lực | Lưu kết quả thực thi và kiểm chứng |
| Đánh đồng digest với sự thật | Bỏ qua nguồn log sai hoặc thiếu ngay từ đầu | Bảo vệ nguồn thu, manifest và lịch sử xử lý |
| Ghép log theo timestamp tuyệt đối | Gán nhầm sự kiện do lệch đồng hồ | Theo dõi sai số và dùng ID liên kết |
| Đếm artifact để đo tính đầy đủ | Không phát hiện phiên chưa được thu thập | Đối chiếu từ tập grant/phiên/target cần có |
| Cho vendor tự sửa bằng chứng chính | Khó phân biệt bản gốc và bản đã thay | Kiểm soát tiếp nhận, quyền lưu và phiên bản |
| Đưa raw log vào báo cáo rộng người xem | Mở rộng rò rỉ dữ liệu hoặc secret | Dùng tham chiếu và trích xuất được kiểm soát |
| Chỉ quan sát đường broker | Không phát hiện đường truy cập đi vòng | Đối soát target, network và cấu hình đường truy cập |

Các lỗi này có thể tồn tại đồng thời. Một recording có digest tốt vẫn có thể thuộc sai phiên; một grant có thời hạn đúng vẫn có thể để lại token; một hồ sơ có đủ số tệp vẫn có thể thiếu audit trong chính khoảng thời gian quan trọng.

## 16. Tự kiểm tra thiết kế bằng chứng

Với một lần truy cập cụ thể, thử trả lời bằng artifact tham chiếu được, thay vì câu trả lời dựa vào trí nhớ:

1. Danh tính nào của vendor đã được doanh nghiệp chấp thuận, và người đó thuộc đơn vị nào ở thời điểm truy cập?
2. Ai chịu trách nhiệm bảo trợ và ai duyệt quyền cho tài nguyên?
3. Phê duyệt áp dụng cho phạm vi và phiên bản nào?
4. Grant/lease nào đã đưa quyền đó vào hiệu lực, trong khoảng thời gian nào?
5. Những phiên, request API hoặc hành động nào đã thực sự dùng quyền?
6. Hành động tại target có được liên kết trực tiếp hay chỉ suy luận?
7. Nguồn nào bị gián đoạn, đến trễ hoặc không có khả năng quan sát?
8. Quyền, credential và phiên còn lại đã được kiểm chứng kết thúc đến mức nào?
9. Artifact có nguồn gốc, digest tham chiếu, quyền đọc và lịch sử xử lý rõ ràng không?
10. Kết luận có phân biệt dữ liệu hiện diện, kiểm soát đạt và phần chưa biết không?

Một thiết kế tốt giúp người không tham gia phiên có thể tái dựng các mắt xích này. Khi chưa trả lời được, việc cần làm là ghi rõ khoảng trống, người chịu trách nhiệm và giới hạn kết luận. Bằng chứng bên thứ ba có giá trị khi nó làm rõ trách nhiệm và diễn biến của quyền đặc biệt, kể cả khi kết quả cho thấy kiểm soát chưa hoàn tất.

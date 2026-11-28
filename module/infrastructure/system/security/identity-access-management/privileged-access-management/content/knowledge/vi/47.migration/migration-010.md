# Decommission credential cũ

## 1. Mục tiêu của bước kết thúc migration

Một hệ thống đã sử dụng PAM để lấy credential mới chưa chắc đã loại bỏ được đường truy cập đặc quyền cũ. Mật khẩu vẫn có thể hoạt động trực tiếp trên máy chủ, khóa SSH còn nằm trên một node dự phòng, API key vẫn được chấp nhận ở một vùng khác hoặc phiên đăng nhập trước cutover tiếp tục tồn tại.

**Decommission credential cũ** là quá trình đưa một credential đã được thay thế ra khỏi khả năng sử dụng, loại bỏ các đường phụ thuộc còn lại và lưu đủ bằng chứng cho quyết định kết thúc. Trong migration PAM, bước này biến việc “đã có đường mới” thành “chỉ còn các đường được quản lý và phê duyệt”.

Sau bài học, người học cần có khả năng:

- Phân biệt credential, tài khoản, quyền và phiên để thu hồi đúng đối tượng.
- Lập danh sách credential cũ cùng nơi xác thực và các hệ thống tiêu thụ.
- Thiết kế trình tự ngừng phát hành, chuyển phụ thuộc, vô hiệu hóa và xử lý bản sao.
- Xác minh cả đường truy cập mới hoạt động lẫn đường cũ bị từ chối.
- Xử lý ngoại lệ, khôi phục có kiểm soát và nguy cơ credential sống lại sau restore.
- Lập hồ sơ kết thúc mà không lưu giá trị bí mật trong ticket hoặc log.

Phạm vi của bài là giai đoạn cuối migration quyền truy cập đặc quyền cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Các bước thực thi phải được cụ thể hóa theo cơ chế xác thực thực tế của từng hệ thống; ví dụ và cấu hình dưới đây là mô hình học tập.

## 2. Xác định chính xác thứ cần ngừng sử dụng

### 2.1. Credential không đồng nhất với tài khoản

Credential là thông tin hoặc vật chứng được dùng để chứng minh một danh tính: mật khẩu, private key, API secret, refresh token hoặc khóa của chứng thư. Tài khoản là danh tính được hệ thống nhận biết. Quyền mô tả những hành động danh tính được thực hiện. Phiên là trạng thái truy cập đã hình thành sau một lần xác thực.

| Đối tượng | Ví dụ trong migration PAM | Việc cần xác minh riêng |
|---|---|---|
| Credential cũ | Mật khẩu trước khi đưa tài khoản vào vault | Hệ thống đích còn chấp nhận mật khẩu này không |
| Danh tính | Tài khoản dịch vụ chạy tác vụ đối soát | Có tiếp tục dùng danh tính này với credential mới không |
| Quyền | Quyền quản trị cơ sở dữ liệu | Quyền có được giảm về đúng nhu cầu không |
| Phiên hoặc kết nối | Phiên SSH hoặc connection pool đã mở | Sau thu hồi credential, phiên có còn thực thi được không |
| Nguồn phát hành | Pipeline tạo API key cũ | Nguồn này còn cấp lại credential ngoài PAM không |
| Bản sao | File cấu hình trên image triển khai | Bản sao có thể bị nạp lại trong lần khởi động sau không |

Đổi mật khẩu thường không đồng nghĩa kết thúc mọi phiên đã mở. Xóa secret khỏi vault cũng không đồng nghĩa hệ thống đích từ chối secret đó. Xóa một tài khoản dịch vụ để loại bỏ một mật khẩu có thể làm mất ownership hoặc gây gián đoạn vượt phạm vi migration.

Trước khi thao tác, xác định rõ một trong hai tình huống:

1. Giữ danh tính, thay cơ chế hoặc phiên bản credential: thu hồi credential cũ, giữ quyền cần thiết cho đường mới.
2. Thay cả danh tính: chuyển workload và ownership, thu hồi quyền của danh tính cũ, sau đó xử lý tài khoản theo chính sách vòng đời.

### 2.2. Xác thực mới và quyền truy cập hiệu lực là hai lớp

Một phép thử đăng nhập cũ bị từ chối chỉ chứng minh lần xác thực đó thất bại trong điều kiện đã thử. Nó chưa chứng minh mọi đường truy cập phát sinh từ credential đều đã mất hiệu lực.

Ví dụ, một API key có thể được dùng để lấy token tạm thời. Sau khi API key bị thu hồi, token đã phát hành có thể còn hiệu lực theo cơ chế của hệ thống. Một certificate ngừng được gia hạn vẫn có thể được verifier chấp nhận đến khi hết hạn nếu không có cơ chế thu hồi được thực thi phù hợp.

Vì vậy, hồ sơ cần tách:

- Trạng thái credential gốc.
- Trạng thái credential hoặc token phái sinh.
- Trạng thái phiên và kết nối.
- Trạng thái quyền của danh tính.
- Khả năng phát hành lại.

Một đối tượng chỉ được kết luận đã decommission khi các lớp áp dụng với nó đều có kết quả phù hợp, hoặc có ngoại lệ được chấp thuận với thời hạn và chủ sở hữu rõ ràng.

## 3. Hoàn tất là một tập điều kiện có thể kiểm chứng

Có thể dùng các điều kiện sau làm tiêu chí đóng một đơn vị decommission:

1. Đường truy cập mới qua PAM hoạt động với quyền và phạm vi đúng.
2. Các consumer đã biết đã chuyển sang đường mới hoặc đã ngừng hoạt động.
3. Credential cũ bị vô hiệu hóa tại các nơi có thể chấp nhận nó trong phạm vi.
4. Phiên, token phái sinh và cache liên quan được xử lý hoặc có giới hạn tồn tại đã xác minh.
5. Không còn nguồn tự động cấp lại credential theo cơ chế cũ.
6. Các bản sao có thể xóa đã được xử lý; bản sao phải giữ có biện pháp kiểm soát.
7. Kiểm thử âm có khả năng kết luận và được đối chiếu với log tại nơi xác thực.
8. Tác vụ hiếm, đường dự phòng và kịch bản restore đã có cách xử lý.
9. Chủ hệ thống xác nhận vận hành, người xác minh xác nhận bằng chứng.
10. Ngoại lệ còn mở không bị ghi nhận nhầm là hoàn tất.

Từ “trong phạm vi” phải được viết cụ thể: hệ thống, môi trường, vùng, tenant, node, loại đăng nhập và phiên bản credential. Một phép thử trên node chính không tự bao phủ replica, máy offline hoặc vùng dự phòng.

Nếu còn một đường hợp lệ chưa được xử lý, trạng thái phù hợp là đang xử lý hoặc có ngoại lệ; không đổi tên trạng thái để làm đẹp tỷ lệ migration.

## 4. Kiểm kê theo quan hệ phụ thuộc

### 4.1. Bốn điểm cần truy vết

Với mỗi credential cũ, trả lời bốn câu hỏi:

- **Ai phát hành?** Con người, vault cũ, pipeline, script hoặc dịch vụ quản lý khóa.
- **Ai tiêu thụ?** Người quản trị, ứng dụng, batch job, agent backup, monitoring, nhà cung cấp.
- **Ai xác thực?** Máy chủ, cơ sở dữ liệu, API gateway, directory, cloud control plane.
- **Ở đâu còn bản sao?** Cấu hình, biến môi trường, secret store, image, artifact, tài liệu, cache hoặc backup.

Mỗi quan hệ phải có một người hoặc nhóm chịu trách nhiệm xác nhận. “Không rõ consumer” là một khoản việc cần điều tra, không phải bằng chứng không có consumer.

### 4.2. Bản ghi tối thiểu

Không đưa giá trị mật khẩu, private key, token đầy đủ hoặc secret vào bảng kiểm kê. Dùng ID phiên bản, key ID công khai, fingerprint public key, serial certificate hoặc tham chiếu nội bộ phù hợp.

~~~yaml
decommissionUnit:
  id: MIG-PAM-DC-017
  environment: training
  identityRef: reconciliation-service
  credentialRef: legacy-secret-version-04
  credentialKind: PASSWORD
  replacementRef: pam-managed-version-05
  identityAction: RETAIN
  authorities:
    - id: database-cluster-training
      coverage: primary-and-standby
      owner: database-team
  consumers:
    - id: daily-reconciliation
      owner: finance-platform
      schedule: daily
    - id: month-end-reconciliation
      owner: finance-platform
      schedule: month-end
  issuanceSource:
    id: legacy-deployment-template
    retirementOwner: delivery-team
  sessionHandling:
    method: drain-and-reconnect
    owner: application-team
  recovery:
    method: issue-new-controlled-credential
    owner: incident-coordinator
  state: DEPENDENCIES_DISCOVERED
~~~

Đây là ví dụ hồ sơ quy trình, không phải cấu hình của một sản phẩm PAM. Tham chiếu replacement cần dẫn đến đối tượng được kiểm soát truy cập; không nhúng secret vào hồ sơ.

### 4.3. Tìm phụ thuộc không xuất hiện trong luồng thường ngày

Các nguồn phát hiện có thể gồm lịch scheduler, manifest triển khai, cấu hình dịch vụ, metadata của secret store, log xác thực, mapping service account và xác nhận của chủ hệ thống. Khi công cụ hỗ trợ, đối chiếu lần sử dụng theo đúng phiên bản credential hoặc key ID; log chỉ có username thường không đủ phân biệt cũ với mới.

Đặc biệt kiểm tra:

- Tác vụ cuối tháng, cuối quý hoặc được kích hoạt thủ công.
- Node standby, cụm DR, agent chỉ chạy lúc backup hoặc restore.
- Máy scale-to-zero và image khởi động lại từ phiên bản cũ.
- Pipeline rollback còn tham chiếu biến môi trường cũ.
- Thiết bị tạm mất kết nối và tài khoản local dự phòng.
- Nhà cung cấp chỉ truy cập khi có sự cố.
- Workload hàng đợi chỉ lấy credential khi reconnect.

Không có log sử dụng trong bảy ngày không loại trừ phụ thuộc chỉ chạy mỗi tháng. Độ dài thời gian quan sát phải gắn với lịch và đặc điểm consumer, thay vì chọn một con số chung cho mọi credential.

## 5. Trình tự decommission có điểm kiểm soát

~~~mermaid
flowchart TD
    A["Kiểm kê credential và phụ thuộc"] --> B["Xác minh đường mới qua PAM"]
    B --> C["Chuyển consumer và chặn cấp mới theo đường cũ"]
    C --> D["Phê duyệt cửa sổ vô hiệu hóa"]
    D --> E["Thu hồi tại nơi xác thực"]
    E --> F["Xử lý phiên, token phái sinh và cache"]
    F --> G["Kiểm thử dương và âm, theo dõi nghiệp vụ"]
    G --> H{"Bằng chứng đủ và không còn phụ thuộc?"}
    H -->|Có| I["Dọn bản sao được phép, lưu hồ sơ, đóng"]
    H -->|Chưa| J["Xử lý phụ thuộc hoặc mở ngoại lệ có hạn"]
    J --> G
~~~

Sơ đồ diễn tả các mốc logic. Một số hệ thống yêu cầu xử lý phiên đồng thời với thu hồi, hoặc thu hồi khẩn cấp trước khi hoàn tất điều tra phụ thuộc. Runbook phải mô tả trình tự tương thích với hệ thống cụ thể.

### 5.1. Chuẩn bị đường mới

Trước khi bỏ đường cũ, thử đường PAM mới từ đúng ngữ cảnh sử dụng:

- Đúng workload, tài khoản chạy dịch vụ và môi trường.
- Đúng giao thức, endpoint và phạm vi quyền.
- Đúng cơ chế lấy secret, thời hạn lease hoặc quy trình JIT/JEA.
- Có log quy về danh tính và yêu cầu truy cập.
- Có khả năng reconnect khi credential mới được luân chuyển.
- Có đường phục hồi được phê duyệt và đã kiểm chứng phù hợp.

Việc người quản trị đọc được secret mới trong giao diện vault không chứng minh ứng dụng có thể lấy và sử dụng nó.

### 5.2. Ngừng tạo thêm nợ migration

Chặn nguồn cấp lại cơ chế cũ: template triển khai, pipeline, công cụ sinh khóa, hướng dẫn tạo tài khoản, auto-provisioning hoặc quy trình cấp quyền thủ công.

Nếu chưa thể chặn ngay, phải có kiểm soát phát hiện đối tượng mới và ngày kết thúc cụ thể. Một bộ credential đã thu hồi vẫn có thể bị thay bằng credential cũ kiểu khác nếu pipeline tiếp tục tạo tài khoản ngoài PAM.

### 5.3. Chuyển consumer

Mỗi consumer cần có bằng chứng đã dùng đường mới. Có thể là một lần lấy secret thành công kết hợp xác thực tại đích và kết quả nghiệp vụ, hoặc một lần chạy đại diện trong môi trường kiểm soát.

Đối với ứng dụng giữ kết nối lâu, chủ ứng dụng cần xác định lúc nào credential được đọc lại. Có ứng dụng đọc mỗi lần mở kết nối; có ứng dụng chỉ đọc lúc khởi động. Chuyển secret reference mà chưa reload hoặc reconnect có thể chỉ thay cấu hình trên giấy.

### 5.4. Phê duyệt cửa sổ vô hiệu hóa

Quyết định cần nêu phạm vi, thời điểm, người thực hiện, người theo dõi nghiệp vụ, điều kiện dừng và cách phục hồi. Với credential chia sẻ nhiều consumer, tránh thu hồi theo thông báo chung mà không có xác nhận của từng owner.

Nếu đang xử lý nghi ngờ lộ credential, mức ưu tiên thay đổi: thu hồi để hạn chế truy cập trái phép có thể phải diễn ra trước khi bảo đảm mọi consumer hoạt động. Khi đó dùng luồng ứng phó sự cố, ghi nhận tác động và điều phối phục hồi; không coi credential đã lộ là phương án rollback bình thường.

### 5.5. Thu hồi tại nơi xác thực

Thao tác quyết định phải tác động đến nơi thực sự chấp nhận credential: thay mật khẩu ở target, xóa đúng public key được ủy quyền, vô hiệu hóa đúng API key, thu hồi quyền phát hành hoặc cập nhật chính sách chấp nhận.

Đối chiếu định danh trước khi thao tác. Tên tài khoản có thể giống nhau giữa các môi trường; nhãn secret có thể trỏ tới phiên bản khác. Cần kết hợp ít nhất các thông tin có khả năng phân biệt: môi trường, authority, identity và credential version hoặc key identifier.

Không đưa lệnh thu hồi tổng quát vào pipeline khi chưa biết tính chất target. Trong bài thực hành, dùng môi trường sandbox và credential giả lập.

## 6. Hai khoảng thời gian thường bị đánh đồng

### 6.1. Khoảng cùng tồn tại

Một số hệ thống hỗ trợ hai khóa hoặc hai credential song song để chuyển consumer. Nếu sử dụng cơ chế này, khoảng cùng tồn tại phải có:

- Thời điểm bắt đầu và thời hạn kết thúc.
- Danh sách consumer còn dùng credential cũ.
- Hạn chế phạm vi và khả năng sử dụng của đường cũ nếu hệ thống hỗ trợ.
- Cảnh báo khi credential cũ được sử dụng ngoài dự kiến.
- Người có quyền phê duyệt gia hạn.
- Hành động thu hồi xác định được.

Không phải hệ thống nào cũng hỗ trợ hai mật khẩu cho cùng tài khoản. Không mô tả việc “giữ cả hai” như một tính năng mặc định.

### 6.2. Khoảng quan sát sau thu hồi

Sau khi credential cũ bị vô hiệu hóa, nhóm vận hành cần quan sát lỗi xác thực, sức khỏe dịch vụ và tác vụ theo lịch. Đây không phải lý do tiếp tục để credential cũ có hiệu lực.

Cần phân biệt hai kết quả:

- Không có truy cập cũ thành công: bằng chứng cần thiết nhưng phụ thuộc chất lượng quan sát.
- Không có tác động nghiệp vụ chưa xử lý: xác nhận hệ thống đã chuyển thành công.

Nếu tác vụ hiếm chưa tới lịch, có thể chủ động chạy thử có kiểm soát hoặc ghi ngoại lệ chờ lịch thực tế. Việc lựa chọn phải dựa trên mức độ đại diện của phép thử, không chỉ sự thuận tiện.

## 7. Cách xử lý theo từng loại credential

### 7.1. Mật khẩu tài khoản quản trị hoặc dịch vụ

Nếu giữ tài khoản, thay mật khẩu tại authority và kiểm tra trạng thái đồng bộ với PAM. Bản secret cũ trong một kho khác không còn giá trị xác thực khi target đã đổi đúng, nhưng vẫn cần xử lý như dữ liệu nhạy cảm.

Xác định rõ authority của mật khẩu: directory tập trung, tài khoản local hoặc kho người dùng riêng của ứng dụng. Thay mật khẩu directory không tự thay mật khẩu của một tài khoản local trùng tên.

Các điểm dễ bỏ sót:

- Node cục bộ có cơ sở người dùng riêng.
- Dịch vụ dùng credential được lưu trong cấu hình scheduler.
- Cơ chế reconcile có thể đặt lại mật khẩu theo bản cũ.
- Connection pool hoặc phiên quản trị đã xác thực.
- Trạng thái account lockout ảnh hưởng đến phép thử âm.

Nếu mục tiêu là loại bỏ tài khoản chia sẻ, thay mật khẩu chỉ là một phần. Còn phải chuyển trách nhiệm vận hành sang danh tính cá nhân hoặc workload identity phù hợp và thu hồi quyền của tài khoản cũ theo kế hoạch.

### 7.2. Khóa SSH

Không chỉ xóa private key khỏi máy người vận hành. Public key có thể vẫn được chấp nhận ở tài khoản đích, hệ thống quản lý cấu hình, image hoặc nguồn cấp quyền tập trung.

Dùng fingerprint của public key để kiểm kê và đối chiếu. Không sao chép private key vào ticket để “chứng minh đúng khóa”. Nếu cùng key được dùng trên nhiều hệ thống, phạm vi decommission phải bao phủ từng nơi chấp nhận.

Loại bỏ public key khỏi nguồn cấu hình chuẩn và các target áp dụng. Nếu chỉ sửa trực tiếp target nhưng không cập nhật cấu hình quản lý, lần đồng bộ tiếp theo có thể cấp lại quyền.

Với SSH certificate, xử lý theo trust model của hệ thống: certificate, principal, CA trust và cơ chế revocation có thể là các đối tượng khác nhau. Không gỡ một CA dùng chung chỉ để thu hồi một credential nếu điều đó làm gián đoạn các danh tính không thuộc phạm vi.

Các phiên SSH đã mở cần được đánh giá riêng; bỏ key không bảo đảm phiên đó kết thúc.

### 7.3. API key, access key và token

Xác minh chính xác key ID ở tenant, project, tài khoản hoặc vùng liên quan. Nếu nền tảng hỗ trợ disable trước delete, có thể dùng trạng thái vô hiệu hóa để xác minh và quan sát trước khi xóa đối tượng; việc chọn cách làm phụ thuộc cơ chế của nền tảng.

Tách refresh token, access token và phiên đăng nhập. Thu hồi refresh token có thể ngừng cấp token mới nhưng không mặc nhiên làm mọi access token đã phát hành mất hiệu lực ngay.

Nếu credential tĩnh được thay bằng workload identity hoặc token ngắn hạn, kiểm tra:

- Workload mới có đúng trust policy và audience hay không.
- Nguồn cấp token cũ có còn hoạt động không.
- Token đã phát hành có thời hạn hiệu lực tối đa nào.
- Có thể thu hồi phiên hay thay đổi quyền để giảm hiệu lực còn lại không.
- Log có thể phân biệt issuer, key ID hoặc token context tới mức nào.

Không giả định TTL ngắn thay thế hoàn toàn cho kế hoạch thu hồi; TTL chỉ có tác dụng theo cách target thực sự xác minh token.

### 7.4. Certificate và private key

Cần phân biệt hủy private key đang giữ, thu hồi certificate và ngừng tin cậy certificate tại verifier. Hủy một bản private key không chứng minh không còn bản sao.

Nếu sử dụng cơ chế kiểm tra thu hồi, phải xác minh các verifier liên quan thực sự kiểm tra và áp dụng kết quả đó. Nếu dựa vào hết hạn, hồ sơ cần chỉ rõ thời hạn, cách đồng bộ thời gian và khoảng rủi ro còn lại.

Không xóa CA trust dùng chung khi phạm vi chỉ là một certificate của một workload. Với mTLS, kiểm tra cả client certificate, server trust, mapping danh tính và các kết nối đang giữ.

### 7.5. Credential động và lease

Chặn consumer lấy credential cũ chưa đủ nếu lease đang tồn tại ở hệ thống đích. Xác minh cơ chế revoke lease có thực sự vô hiệu hóa tài khoản hoặc quyền tại target, hay chỉ xóa thông tin quản lý trong kho.

Credential động cũng có thể để lại orphan account nếu lần thu hồi trước thất bại. Đối chiếu lease inventory với danh tính còn tồn tại ở target khi có khả năng đó.

## 8. Phiên, cache và token phái sinh

Hãy lập một bảng riêng cho trạng thái truy cập còn sống:

| Loại trạng thái | Rủi ro khi chỉ thu hồi credential gốc | Cách xử lý cần quyết định |
|---|---|---|
| Phiên tương tác | Người đã đăng nhập vẫn thực thi lệnh | Kết thúc phiên hoặc áp dụng thời hạn theo chính sách |
| Connection pool | Ứng dụng tiếp tục chạy trên kết nối cũ | Drain, reconnect và kiểm thử nghiệp vụ |
| Token tạm thời | Token còn được verifier chấp nhận | Thu hồi nếu hỗ trợ, hạn chế quyền hoặc chờ hết hạn có kiểm soát |
| Cache credential | Workload dùng lại secret trong lần reconnect | Làm mới cache theo cơ chế ứng dụng |
| Agent offline | Khi kết nối lại vẫn mang cấu hình cũ | Cách ly hoặc bắt buộc cập nhật trước khi phục vụ |
| Session recording | Bằng chứng bị mất khi dọn hạ tầng | Bảo toàn dữ liệu theo chính sách lưu giữ |

Thời hạn xử lý cần dựa trên khả năng thực tế. Không hứa “revoke ngay mọi token” nếu hệ thống không cung cấp cơ chế đó. Có thể ghi trạng thái đã thu hồi nguồn cấp nhưng còn chờ hết hạn token, cùng phạm vi và biện pháp giám sát tương ứng.

Đừng dùng việc kết nối cũ vẫn chạy để kết luận credential mới đã tốt. Thử đường mới phải bao gồm một lần xác thực mới, còn kiểm tra đường cũ phải tách khỏi những phiên đã được chấp nhận trước đó.

## 9. Kiểm thử dương và âm

### 9.1. Kiểm thử dương chứng minh đường thay thế dùng được

Từ consumer đại diện, lấy credential hoặc quyền qua PAM, mở kết nối mới và thực hiện thao tác nghiệp vụ được phép. Đối chiếu log PAM và target theo thời gian, identity, request hoặc session reference.

Một phép thử đủ giá trị cần tránh kết nối cũ và cache không rõ trạng thái. Khi cần, tạo một kết nối mới theo quy trình vận hành đã được duyệt.

Ngoài thành công, thử giới hạn quyền: workload không được hưởng thêm quyền quản trị chỉ vì đổi cơ chế lấy credential. JIT/JEA hoặc least privilege phải được giữ trong đường truy cập mới.

### 9.2. Kiểm thử âm cần cho ra kết luận đúng

Kiểm thử âm là thử sử dụng credential cũ trong điều kiện cho phép xác định target còn chấp nhận nó hay không. Chỉ thực hiện trong phạm vi đã phê duyệt; cân nhắc lockout, rate limit, cảnh báo và nguy cơ ghi bí mật ra log.

Không đặt secret trên command line, URL, log debug hoặc nội dung ticket. Dùng công cụ lấy bí mật theo tham chiếu, bảo vệ đầu vào và chỉ xuất kết quả đã lược bỏ dữ liệu nhạy cảm.

Nếu không còn giữ giá trị credential cũ, không tạo thêm bản sao chỉ để tiện kiểm thử. Có thể dùng bằng chứng quản trị trạng thái cùng log và phép thử phù hợp khác; hồ sơ phải nói rõ giới hạn thay vì tuyên bố đã thử điều chưa thực hiện.

| Kết quả quan sát | Có đủ để chứng minh credential cũ bị thu hồi không? | Bước tiếp theo |
|---|---|---|
| Target xác nhận key bị vô hiệu hóa, lần thử bị từ chối đúng lý do | Có giá trị trong phạm vi và thời điểm được kiểm tra | Kết hợp bằng chứng quản trị, coverage và log |
| Timeout hoặc DNS lỗi | Không | Khôi phục điều kiện kiểm thử hoặc ghi chưa thể kết luận |
| Bị firewall chặn trước tầng xác thực | Không chứng minh credential đã mất hiệu lực | Kiểm tra tại authority bằng phương pháp phù hợp |
| Báo account locked | Không đủ để phân biệt credential đúng hay sai | Xác minh trạng thái credential độc lập |
| Xác thực được nhưng bị từ chối một thao tác | Chứng minh giới hạn thao tác, không chứng minh credential đã vô hiệu | Phân tích lớp xác thực và lớp phân quyền |
| Log không có sự kiện | Không tự đủ | Kiểm tra đường log, phạm vi quan sát và kết quả tại target |

### 9.3. Ma trận kiểm thử theo coverage

Một credential dùng trên nhiều target cần các hàng kiểm thử tương ứng. Nếu chia sẻ authority tập trung, có thể sử dụng bằng chứng tập trung kết hợp kiểm tra đại diện tại các lớp thực thi; phải giải thích vì sao cách lấy mẫu bao phủ được phạm vi.

~~~text
Đơn vị: MIG-PAM-DC-017

Target A:
  Đường PAM mới: kết nối mới + nghiệp vụ thành công
  Credential cũ: target từ chối; có audit reference
  Phiên cũ: đã drain và không còn phiên thuộc phiên bản cũ

Target B dự phòng:
  Đường PAM mới: diễn tập kết nối thành công
  Credential cũ: bị từ chối sau khi cấu hình đồng bộ
  Failover: dùng nguồn secret mới

Job cuối tháng:
  Chạy đại diện: thành công sau khi loại bỏ cache cũ
  Lần chạy theo lịch: tiếp tục theo dõi theo kế hoạch đóng
~~~

Không coi một ô “PASS” không có điều kiện và bằng chứng là hồ sơ xác minh đầy đủ.

## 10. Xử lý bản sao và ngăn credential sống lại

### 10.1. Bản sao đang hoạt động

Sau khi target đã thu hồi đúng, dọn các nơi còn phân phối hoặc nạp secret cũ: biến CI/CD, file cấu hình, secret store phụ, môi trường container, scheduler, image và runbook.

Với secret trong repository hoặc artifact, chỉ xóa ở phiên bản hiện tại không làm mất mọi bản lịch sử. Thu hồi tại target là hành động làm giảm giá trị xác thực của những bản sao đó; xử lý lịch sử và phân phối artifact theo chính sách riêng, tránh thao tác xóa lịch sử vượt phạm vi.

Nếu phát hiện secret có thể đã bị truy cập ngoài phạm vi được phép, chuyển đánh giá theo quy trình sự cố. Không ghi secret vào báo cáo điều tra để minh họa phát hiện.

### 10.2. Backup và bản sao phải giữ

Không cần và thường không phù hợp để sửa trực tiếp mọi backup bất biến chỉ nhằm xóa một credential đã bị thu hồi. Thay vào đó, quản lý quyền đọc, mã hóa, thời hạn giữ và quy trình restore theo chính sách của tổ chức.

Một backup có thể phục hồi đồng thời cấu hình, tài khoản và password hash cũ của hệ thống đích. Khi đó credential tưởng đã thu hồi có thể được chấp nhận lại. Vì vậy cần một danh mục thu hồi hoặc biện pháp tương đương được bảo toàn ngoài phạm vi rollback của ứng dụng.

Danh mục đó có thể chứa identity reference, key fingerprint, credential version, thời điểm thu hồi, ticket và hành động cần áp lại; không chứa secret.

### 10.3. Cổng kiểm tra sau restore

Runbook restore nên quy định trước khi hệ thống quay lại phục vụ:

1. Cách ly phạm vi vừa phục hồi khỏi truy cập bình thường.
2. Đối chiếu tài khoản, key và cấu hình với danh mục đã thu hồi.
3. Áp lại trạng thái revoke, rotate hoặc chính sách thay thế cần thiết.
4. Làm mới nguồn secret và chặn template cũ tạo lại credential.
5. Kiểm tra đường PAM mới và các đường cũ bị từ chối.
6. Ghi bằng chứng rồi mới gỡ điều kiện cách ly theo phê duyệt.

Một snapshot đã được tạo trước migration không thể tự mang trạng thái thu hồi xuất hiện sau đó. Cổng restore là nơi xử lý chênh lệch này.

## 11. Phục hồi vận hành mà không làm mất kiểm soát

### 11.1. Xác định trước điểm không thể quay lại

Trước khi revoke hoặc delete, cần biết hệ thống có hỗ trợ re-enable hay không và việc khôi phục đó có được phép trong tình huống hiện tại hay không. Credential đã lộ hoặc đã mất khả năng kiểm soát bản sao không nên được tái sử dụng làm đường cứu hộ.

Trong nhiều trường hợp, phục hồi tiến về phía trước phù hợp hơn: cấp credential mới có thời hạn, sửa consumer, xác minh lại và thu hồi credential tạm khi xong.

Phương án phục hồi có thể gồm:

- Cấp một credential thay thế mới qua quy trình PAM được kiểm soát.
- Mở quyền JIT giới hạn để sửa workload.
- Dùng tài khoản break-glass riêng đã được chuẩn bị.
- Quay lại phiên bản ứng dụng tương thích với nguồn secret mới.
- Chuyển workload sang tuyến dự phòng đã được kiểm chứng.

Khôi phục phiên bản ứng dụng không đồng nghĩa phải khôi phục secret cũ. Hai quyết định này cần tách riêng trong runbook.

### 11.2. Ngoại lệ khôi phục credential cũ

Nếu tổ chức cho phép tái kích hoạt một credential chưa bị nghi lộ, quyết định phải có lý do cụ thể, người phê duyệt, thời hạn, phạm vi hạn chế và kế hoạch thu hồi tiếp. Không tự động re-enable chỉ vì một health check báo lỗi.

Sau khi tái kích hoạt, kết luận decommission trước đó không còn đúng trong phạm vi bị mở lại. Hồ sơ cần quay về trạng thái phù hợp và tiếp tục quan sát, thay vì giữ “đã hoàn tất” rồi ghi chú ở nơi khác.

### 11.3. Break-glass là một hệ thống riêng

Không giữ tài khoản admin cũ ngoài PAM vô thời hạn với nhãn “dự phòng”. Một đường break-glass hợp lệ cần mục đích, người chịu trách nhiệm, cách bảo vệ, điều kiện kích hoạt, giám sát và kiểm tra định kỳ.

Nếu break-glass nằm trong chính hạ tầng đang migration, cần đánh giá sự phụ thuộc để tránh mất cả đường thường lẫn đường khẩn cấp trong cùng một sự cố.

## 12. Tình huống thực hành: dịch vụ đối soát

### 12.1. Bối cảnh

Một dịch vụ đối soát dùng tài khoản cơ sở dữ liệu có quyền cao hơn nhu cầu. Mật khẩu được lưu trong biến pipeline cũ và một file cấu hình trên máy DR. Nhóm chuyển workload sang secret được PAM quản lý và giảm quyền về các bảng, thủ tục cần thiết.

Có ba consumer:

- Batch hàng ngày.
- Batch cuối tháng.
- Workload ở vùng DR chỉ hoạt động khi failover.

Ứng dụng dùng connection pool. Cấu hình mới đã triển khai nhưng một số kết nối mở từ trước vẫn còn sống.

### 12.2. Sai lầm có thể xảy ra

Nhóm thấy batch hàng ngày thành công và xóa secret khỏi pipeline. Tuy nhiên:

- Password trên target chưa thay nên file DR vẫn dùng được.
- Batch cuối tháng lấy secret từ một biến khác.
- Connection pool khiến kết quả thành công không chứng minh credential mới được dùng.
- Template DR cũ có thể khôi phục cả cấu hình lẫn nguồn credential.

Kết luận “đã chuyển sang PAM” lúc này chỉ phản ánh một phần đường truy cập.

### 12.3. Cách thực hiện có kiểm soát

**Chuẩn bị:** ghi đơn vị decommission, identity, phiên bản secret cũ và mới, authority của cụm cơ sở dữ liệu, các consumer và nguồn cấu hình. Chủ ứng dụng xác nhận cơ chế reload, pool và lịch cuối tháng.

**Xác minh đường mới:** chạy batch đại diện trên kết nối mới, đối chiếu log lấy secret PAM, audit tại cơ sở dữ liệu và kết quả đối soát. Kiểm tra workload không thể dùng quyền quản trị ngoài nhu cầu.

**Chuyển phụ thuộc:** cập nhật cả biến pipeline còn sót, cấu hình DR và template triển khai. Chạy thử batch cuối tháng bằng dữ liệu thực hành phù hợp, không giả định batch hàng ngày bao phủ nó.

**Thu hồi:** thực hiện thay mật khẩu tại authority theo cửa sổ đã duyệt, kiểm tra PAM giữ đúng phiên bản mới. Với thiết kế giữ cùng tài khoản, không xóa tài khoản đang phục vụ workload mới.

**Xử lý trạng thái sống:** drain pool theo khả năng ứng dụng, mở lại kết nối bằng đường mới; đánh giá các phiên quản trị và kết nối từ vùng DR.

**Kiểm thử:** đường mới thành công, mật khẩu cũ bị target từ chối trong điều kiện mạng bình thường, quyền mới giới hạn đúng. Xác minh cả đường DR và quá trình failover đại diện.

**Dọn bản sao:** gỡ tham chiếu cũ khỏi các nguồn cấu hình đang hoạt động, cập nhật hướng dẫn vận hành, ghi cổng restore áp lại trạng thái thu hồi.

**Đóng:** chủ ứng dụng, chủ cơ sở dữ liệu và người xác minh xác nhận bằng chứng trong phạm vi của họ. Nếu chưa đủ điều kiện xác nhận batch theo lịch, giữ mục theo dõi hoặc ngoại lệ có thời hạn được phê duyệt.

### 12.4. Khi phát hiện batch hỏng sau thu hồi

Một batch cuối tháng báo xác thực thất bại không có nghĩa cần đưa mật khẩu cũ trở lại. Trước hết xác nhận batch nào đang chạy, lấy credential từ đâu và có đang dùng cấu hình cũ hay không.

Nếu đúng phụ thuộc còn sót, cập nhật nguồn secret mới và chạy lại theo cơ chế an toàn của nghiệp vụ. Với batch không idempotent, chủ nghiệp vụ phải xác định phần đã chạy và cách tránh ghi trùng. Nhóm PAM không nên tự chạy lại chỉ vì lỗi xuất hiện ở tầng xác thực.

Nếu cần quyền cứu hộ, cấp đường truy cập tạm có kiểm soát, ghi lại ai thực hiện và thu hồi sau khi hoàn tất.

## 13. Hồ sơ bằng chứng phục vụ đóng migration

Một hồ sơ tốt cho phép người khác hiểu được điều gì đã bị thu hồi, ai quyết định và kết quả nào hỗ trợ kết luận. Không cần thu thập dữ liệu bí mật để làm hồ sơ trông đầy đủ hơn.

~~~yaml
decommissionEvidence:
  unitId: MIG-PAM-DC-017
  credentialRef: legacy-secret-version-04
  targetScope:
    - database-primary-training
    - database-standby-training
  authorityAction:
    result: REVOKED
    evidenceRef: restricted-audit-event-821
  replacementTest:
    result: PASS
    evidenceRef: controlled-test-run-155
    usedFreshConnection: true
  oldCredentialTest:
    result: REJECTED_BY_AUTHORITY
    evidenceRef: restricted-auth-event-822
    networkReachable: true
  remainingAccess:
    sessions: HANDLED
    derivedTokens: NOT_APPLICABLE
    caches: REFRESHED
  consumerCoverage:
    dailyBatch: VERIFIED
    monthEndBatch: REPRESENTATIVE_TEST_PASSED
    drWorkload: VERIFIED
  restoreControl:
    evidenceRef: recovery-runbook-revision-12
  exceptions: []
  approvals:
    systemOwner: approval-reference-41
    verifier: approval-reference-42
  outcome: READY_FOR_CLOSURE
~~~

Các trạng thái trong ví dụ cần được định nghĩa trong quy trình sử dụng chúng. NOT_APPLICABLE phải có căn cứ, không dùng để bỏ qua mục chưa điều tra. REPRESENTATIVE_TEST_PASSED cần ghi giới hạn nếu khác với lần chạy theo lịch thật.

Bằng chứng nên chứa thời điểm có timezone, người thực hiện, phạm vi, phương pháp, kết quả và tham chiếu log. Quyền đọc log và thời hạn lưu giữ phải phù hợp với dữ liệu chứa trong đó.

Giữ các ID và audit trail cần cho kiểm toán; việc xóa credential sử dụng được không đồng nghĩa xóa lịch sử về đối tượng đó.

## 14. Trách nhiệm và bàn giao

| Vai trò | Trách nhiệm chính |
|---|---|
| Chủ hệ thống | Xác nhận phụ thuộc, tác động và điều kiện đóng |
| Nhóm PAM | Cung cấp đường thay thế, quản lý credential và bằng chứng cấp quyền |
| Quản trị target hoặc IAM | Thực hiện và xác minh revoke tại authority |
| Chủ ứng dụng hoặc workload | Chuyển consumer, xử lý cache, pool và kiểm tra nghiệp vụ |
| Nhóm vận hành hoặc SOC | Theo dõi truy cập cũ, lỗi và dấu hiệu bất thường |
| Chủ backup hoặc DR | Ngăn restore đưa credential và cấu hình cũ trở lại |
| Người phê duyệt thay đổi | Phê duyệt cửa sổ, ngoại lệ và phương án phục hồi |
| Người xác minh | Đối chiếu coverage và bằng chứng trước khi đóng |

Trong tổ chức nhỏ, một người có thể đảm nhiệm nhiều vai trò theo chính sách. Dù vậy, trách nhiệm cho từng quyết định phải rõ; “nhóm migration đã làm” không đủ để biết ai xử lý một consumer chưa chuyển.

Bàn giao cho vận hành cần chỉ ra nơi lấy quyền mới, cách nhận cảnh báo truy cập cũ, quy trình khôi phục, danh mục thu hồi và người liên hệ khi phát hiện phụ thuộc muộn.

## 15. Chỉ số đo đúng kết quả

Đếm số secret đã xóa khỏi vault không phản ánh đầy đủ credential cũ còn được target chấp nhận. Nên theo dõi các chiều riêng:

- Số đơn vị decommission đã đóng trên tổng số đơn vị trong phạm vi.
- Số nơi chấp nhận credential cũ đã xác minh trên tổng số nơi đã biết.
- Số consumer đã chuyển và xác minh trên tổng số consumer đã kiểm kê.
- Số phiên, token hoặc lease chưa xử lý.
- Số ngoại lệ quá hạn và thời gian tồn tại của chúng.
- Số truy cập thành công bằng credential đã được đánh dấu thu hồi.
- Số trường hợp phát hiện credential sống lại sau triển khai hoặc restore.

Ví dụ:

~~~text
Đơn vị credential trong phạm vi: 40
Đã đóng đủ điều kiện: 34
Đang xử lý: 4
Ngoại lệ có hạn: 2

Tỷ lệ đóng = 34 / 40 = 85%
Không cộng 2 ngoại lệ vào số đã đóng.

Consumer đã biết: 96
Đã xác minh dùng đường mới: 91
Coverage consumer = 91 / 96, theo inventory hiện tại.
~~~

Khi phát hiện thêm consumer hoặc authority, cập nhật mẫu số và ghi nguyên nhân thay đổi. Coverage 100% chỉ có ý nghĩa đối với inventory và phương pháp phát hiện đã mô tả, không phải lời bảo đảm không còn hệ thống chưa biết.

Một truy cập cũ thành công sau thời điểm revoke là tín hiệu cần điều tra ngay: revoke chưa áp dụng đủ, định danh credential bị nhầm, propagation chưa xong, phiên cũ còn sống hoặc credential được cấp lại. Phân loại theo bằng chứng trước khi sửa trạng thái.

## 16. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao kết luận không đúng | Cách sửa |
|---|---|---|
| Xóa secret khỏi kho là xong | Target có thể vẫn chấp nhận giá trị cũ | Thu hồi và xác minh tại authority |
| Đổi mật khẩu là kết thúc mọi truy cập | Phiên và token có vòng đời riêng | Kiểm kê và xử lý trạng thái sống |
| Một lần đăng nhập mới thành công chứng minh migration hoàn tất | Consumer khác có thể chưa chuyển | Kiểm tra theo inventory và lịch sử dụng |
| Timeout được ghi là credential cũ bị từ chối | Chưa tới lớp xác thực | Phân loại kết quả chưa kết luận |
| Giữ khóa cũ đề phòng vô thời hạn | Tạo đường đặc quyền ngoài kiểm soát | Chuẩn bị phục hồi và break-glass có quản trị |
| Chỉ sửa target, bỏ qua template | Automation có thể cấp lại quyền | Sửa nguồn cấu hình và kiểm tra lần deploy sau |
| Xóa tài khoản để thu hồi một secret | Có thể ảnh hưởng ownership và đường mới | Tách vòng đời credential với danh tính |
| Backup được bỏ qua vì không online | Restore có thể phục hồi trạng thái cũ | Áp cổng kiểm tra sau restore |
| Chụp hoặc ghi secret làm bằng chứng | Tạo thêm bản sao nhạy cảm | Dùng ID, fingerprint và audit reference |
| Ngoại lệ được tính là hoàn tất | Che giấu đường truy cập còn hiệu lực | Theo dõi ngoại lệ và tỷ lệ đóng riêng |

## 17. Bài tập tự kiểm tra

Trong môi trường thực hành, một tài khoản dịch vụ đã chuyển sang PAM. Bạn có các thông tin:

- Ứng dụng chính chạy thành công nhưng chưa tạo kết nối mới.
- API key cũ đã được đánh dấu disabled ở một vùng.
- Một token cấp trước lúc disable còn 20 phút hiệu lực.
- Job DR chưa từng được chạy trong đợt migration.
- Một phép thử credential cũ trả về timeout.
- Pipeline rollback vẫn trỏ tới tên secret cũ.

Hãy xác định liệu có thể đóng decommission hay chưa và lập các hành động tiếp theo theo thứ tự ưu tiên.

Một câu trả lời hợp lý phải nêu được:

1. Chưa đủ điều kiện đóng; thành công của ứng dụng có thể đến từ kết nối cũ.
2. Cần kiểm tra phạm vi của key, các nơi chấp nhận và hiệu lực token phái sinh.
3. Timeout không chứng minh key bị từ chối; cần phép thử có khả năng kết luận.
4. Cần chạy hoặc xác minh đường DR theo phương án được phê duyệt.
5. Cần sửa nguồn rollback để không phát hành hoặc nạp lại đường cũ.
6. Cần xử lý thời gian token còn hiệu lực và ghi bằng chứng sau khi điều kiện kết thúc đạt được.
7. Sau đó xác minh đường mới, tác động nghiệp vụ, dọn bản sao và hoàn tất hồ sơ.

Câu hỏi cuối cùng trước khi ký đóng không chỉ là “credential cũ đã bị xóa chưa”, mà là: **còn nơi nào chấp nhận, phát hành lại hoặc phục hồi được đường truy cập đặc quyền cũ trong phạm vi cần kiểm soát hay không?** Kết luận phải dựa trên inventory, hành động tại authority và bằng chứng vận hành tương ứng.

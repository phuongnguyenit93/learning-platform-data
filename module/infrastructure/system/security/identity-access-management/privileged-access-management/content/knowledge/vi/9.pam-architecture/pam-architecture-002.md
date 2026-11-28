# Credential broker trong kiến trúc PAM

## 1. Credential broker giải quyết vấn đề gì?

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), **credential broker** là thành phần trung gian tiếp nhận một yêu cầu sử dụng credential, xác minh danh tính bên yêu cầu, đánh giá chính sách và cung cấp hoặc sử dụng credential trong phạm vi được phép.

Credential có thể là mật khẩu, khóa, chứng thư hoặc token dùng để chứng minh danh tính với hệ thống đích. Không phải mọi credential đều mang đặc quyền quản trị; mức độ nhạy cảm còn phụ thuộc quyền thực tế của danh tính mà credential đại diện.

Bài học này tập trung vào broker phục vụ tài khoản quản trị, tài khoản dịch vụ và truy cập hạ tầng nhạy cảm. Mục tiêu là giảm việc phân phối credential dài hạn, thu hẹp quyền theo nhu cầu, quản lý vòng đời và tạo bằng chứng có thể liên kết với hoạt động tại đích.

Ví dụ, một tác vụ đối soát cần đọc dữ liệu thanh toán trong thời gian chạy. Nếu tác vụ giữ sẵn mật khẩu quản trị cơ sở dữ liệu trong cấu hình, mọi lần triển khai đều mang theo một quyền rộng và lâu dài. Với broker, tác vụ có thể chứng minh danh tính workload rồi nhận credential chỉ dành cho vai trò đọc dữ liệu đã được xác định. Khả năng cấp credential tạm thời phụ thuộc cơ chế mà hệ thống đích và connector hỗ trợ.

Broker giúp trả lời bốn câu hỏi:

1. Ai hoặc workload nào đang yêu cầu?
2. Yêu cầu truy cập tài nguyên và vai trò nào?
3. Điều kiện nào cho phép cấp hoặc sử dụng credential?
4. Credential, quyền liên quan và bằng chứng được quản lý đến khi nào?

Một endpoint trả secret sau khi kiểm tra một API key chung vẫn có thể làm trung gian về kỹ thuật, nhưng chưa tạo ra mô hình PAM có danh tính rõ, least privilege và thu hồi đáng tin cậy.

## 2. Phân biệt broker với các thành phần liên quan

| Thành phần | Trách nhiệm chính | Điều không thể tự suy ra |
|---|---|---|
| Identity provider hoặc nguồn danh tính workload | Cung cấp bằng chứng danh tính và thuộc tính theo mô hình tin cậy | Danh tính hợp lệ không đồng nghĩa được truy cập mọi secret |
| Vault hoặc kho bí mật | Bảo vệ, quản lý phiên bản và kiểm soát truy cập secret | Có vault không chứng minh secret chưa từng bị sao chép |
| Credential broker | Gắn danh tính, chính sách và việc cung cấp hoặc sử dụng credential | Có broker không bảo đảm credential ngắn hạn hoặc quyền hẹp |
| Credential issuer hoặc hệ thống đích | Tạo token, chứng thư, tài khoản hoặc credential theo khả năng hỗ trợ | Lease tại broker không tự trở thành thời hạn tại đích |
| Session proxy hoặc gateway | Trung gian đường kết nối và có thể giữ credential khỏi người dùng | Broker trả secret không tự ghi hình hay kiểm soát nội dung phiên |
| Rotation engine | Thay credential và phối hợp cập nhật nơi sử dụng | Rotation không mặc nhiên kết thúc mọi phiên đã xác thực |
| Hệ thống audit và giám sát | Lưu sự kiện, liên kết hoạt động, phát hiện bất thường | Có log cấp credential không chứng minh đầy đủ thao tác tại đích |

Một sản phẩm có thể tích hợp nhiều vai trò trong cùng nền tảng. Khi thiết kế, vẫn cần xác định ranh giới trách nhiệm: thành phần nào quyết định, thành phần nào thực thi, thành phần nào là nguồn trạng thái có thẩm quyền.

Credential broker cũng không phải secret scanner. Việc tìm credential bị nhúng trong mã nguồn, cấu hình cũ hoặc log là công việc bổ sung để loại bỏ những đường sử dụng nằm ngoài broker.

## 3. Ba mô hình cung cấp credential

### 3.1. Trả credential có sẵn

Broker đọc một credential được quản lý trong vault rồi chuyển cho bên được phép.

~~~text
Workload → Broker → Vault
Workload ← credential được phép ← Broker
Workload → Hệ thống đích
~~~

Mô hình này có thể phù hợp với ứng dụng cũ chưa hỗ trợ danh tính liên kết hoặc credential động. Nó tập trung điểm phân phối và tạo log truy xuất, nhưng credential vẫn đi vào không gian thực thi của workload.

Những điểm cần thiết kế:

- Danh tính nào được đọc credential nào.
- Quyền của tài khoản tại đích có đúng nhu cầu không.
- Credential có được chia sẻ giữa nhiều workload hay không.
- Việc thay credential có cập nhật được tất cả consumer không.
- Bản sao còn tồn tại ở bộ nhớ, tệp, bản sao lưu hoặc hệ thống triển khai nào.

Một lần cấp credential không đồng nghĩa một lần sử dụng. Với credential dùng chung, log tại đích thường cần thêm dữ liệu tương quan mới có thể quy trách nhiệm cho từng workload.

### 3.2. Cấp credential động hoặc tạm thời

Sau khi cho phép yêu cầu, broker phối hợp với issuer hoặc đích để tạo credential có phạm vi và thời gian phù hợp.

~~~text
Workload → Broker: bằng chứng danh tính + target_id + role_id
Broker → Issuer/đích: cấp credential theo vai trò đã cho phép
Broker ← credential + thông tin vòng đời
Workload ← credential + thời hạn được công bố
Workload → Đích: xác thực và thực hiện công việc
~~~

Đây có thể là token tạm thời, chứng thư có thời hạn hoặc tài khoản cơ sở dữ liệu được tạo cho một lease. Các cơ chế không tương đương nhau: có cơ chế được đích kiểm tra thời hạn trực tiếp, có cơ chế cần broker chạy tác vụ thu hồi.

Cần xác định:

- Thời hạn nằm trong credential hay chỉ nằm trong sổ lease.
- Ai thực thi hết hạn.
- Có thể thu hồi trước hạn bằng cách nào.
- Quyền được ánh xạ sang đối tượng nào tại đích.
- Phiên hoặc kết nối đã mở sẽ được xử lý ra sao.

### 3.3. Sử dụng credential thay cho người yêu cầu

Broker hoặc một gateway liên quan dùng credential để thiết lập kết nối, còn người dùng hay workload tương tác qua đường trung gian.

Ưu điểm có thể là không tiết lộ secret cho bên yêu cầu trong luồng đó. Đổi lại, thành phần trung gian nằm trên đường dữ liệu và cần được thiết kế về hiệu năng, tính sẵn sàng, bảo vệ phiên và giám sát.

Việc ghi nhận lệnh, truy vấn hoặc hình ảnh phiên phụ thuộc giao thức và khả năng gateway. Không suy ra chức năng ghi hình chỉ từ tên gọi credential broker.

| Mô hình | Credential đến bên yêu cầu? | Trọng tâm kiểm soát |
|---|---|---|
| Trả secret có sẵn | Có | Phân phối, bảo vệ bản sao, rotation và quyền tại đích |
| Cấp credential động | Thường có, tùy thiết kế | Định danh từng lần cấp, phạm vi, hết hạn và thu hồi |
| Trung gian kết nối | Có thể được giữ tại gateway | Đường truy cập, phiên, tính sẵn sàng và bằng chứng thao tác |

Các mô hình có thể phối hợp. Ví dụ, broker cấp credential động cho gateway, rồi gateway dùng credential đó mở phiên mà không chuyển secret cho quản trị viên.

## 4. Kiến trúc tham chiếu và ranh giới tin cậy

~~~mermaid
flowchart LR
    W["Người dùng hoặc workload"] -->|Bằng chứng danh tính và yêu cầu| B["Credential broker"]
    I["Nguồn danh tính tin cậy"] -.->|Thông tin xác minh danh tính| B
    P["Chính sách và kiểm kê tài nguyên"] -->|Vai trò, phạm vi, điều kiện| B
    B -->|Đọc credential được phép| V["Vault"]
    B -->|Yêu cầu cấp hoặc thu hồi| T["Issuer hoặc hệ thống đích"]
    B -->|Credential hoặc tham chiếu phiên| W
    W -->|Truy cập được phép| T
    B -->|Sự kiện quyết định và vòng đời| A["Audit và giám sát"]
    T -->|Sự kiện xác thực và hoạt động| A
~~~

Sơ đồ là mô hình logic, không yêu cầu mỗi khối là một máy chủ riêng. Broker có thể xác minh bằng chứng bằng khóa và dữ liệu tin cậy được quản lý cục bộ; không phải mọi lần cấp đều cần gọi trực tiếp identity provider.

Cần xác định ít nhất các ranh giới sau:

1. Giữa client và broker: client có thể bị giả mạo hoặc gửi yêu cầu ngoài quyền.
2. Giữa broker và vault/issuer: broker có khả năng tiếp cận credential hoặc tạo quyền tại đích.
3. Giữa môi trường phát triển và production: danh tính ở môi trường này không được tự chuyển thành quyền ở môi trường khác.
4. Giữa quản trị broker và sử dụng broker: người sửa chính sách có thể tác động tới tập credential được cấp.
5. Giữa dữ liệu audit và người vận hành: bằng chứng không nên bị sửa dễ dàng bởi chính chủ thể bị giám sát.

Broker là điểm tập trung quyền lực. Nếu một connector dùng tài khoản quản trị rộng để tạo credential cho nhiều hệ thống, việc xâm phạm connector có thể vượt xa phạm vi một workload. Phân vùng theo mức nhạy cảm, môi trường và nhóm tài nguyên giúp giới hạn ảnh hưởng.

## 5. Chuẩn bị kiểm kê trước khi đưa workload qua broker

Không thể xây chính sách hẹp nếu chưa biết đối tượng và quyền thực tế.

| Dữ liệu cần có | Mục đích |
|---|---|
| Định danh workload hoặc người dùng | Xác định chủ thể xin credential |
| Owner và đơn vị chịu trách nhiệm | Phê duyệt nhu cầu, xử lý sự cố và thay đổi |
| Target ID cùng môi trường | Ngăn ánh xạ nhầm sang tài nguyên khác |
| Tài khoản, vai trò và quyền tại đích | Kiểm tra least privilege thực tế |
| Loại credential và khả năng của đích | Chọn trả secret, cấp tạm thời hoặc đi qua gateway |
| Consumer và vòng đời kết nối | Thiết kế refresh, rotation và thu hồi |
| Đường truy cập ngoài broker | Xác định phần kiểm soát có thể bị đi vòng |
| Yêu cầu bằng chứng | Chọn sự kiện cần lưu và cách liên kết |

Tên hiển thị như “payment-db” có thể không đủ nếu tồn tại ở nhiều môi trường. Nên dùng định danh có nguồn quản lý rõ và ánh xạ được kiểm tra.

Một workload có thể gọi broker đúng quy trình nhưng vẫn giữ credential cũ trong cấu hình dự phòng. Nếu đường dự phòng tiếp tục hoạt động mà không được kiểm soát, phạm vi bảo vệ của broker chỉ bao phủ một phần đường truy cập.

## 6. Xác thực người yêu cầu và bài toán bootstrap

### 6.1. Workload lấy gì để chứng minh danh tính?

Nếu ứng dụng phải giữ một secret dài hạn có quyền đọc tất cả secret khác để gọi broker, rủi ro chỉ được chuyển sang một vị trí mới.

Tùy hạ tầng, bằng chứng danh tính có thể dựa trên:

- Danh tính workload do nền tảng chạy ứng dụng cung cấp.
- Token liên kết từ nguồn phát hành được tin cậy.
- Chứng thư client trong mô hình mTLS có quản lý vòng đời.
- Agent cục bộ đại diện workload theo cơ chế ràng buộc được thiết kế.
- Một bootstrap credential có phạm vi và vòng đời được quản trị khi chưa có phương án tốt hơn.

Không có cơ chế nào tự an toàn chỉ nhờ tên gọi. Cần hiểu ai có thể lấy bằng chứng, bằng chứng được chuyển cho ai và bên khác có thể sử dụng lại hay không.

### 6.2. Xác minh bằng chứng đầy đủ

Với token có chữ ký, broker cần kiểm tra những yếu tố phù hợp với loại token và mô hình tin cậy: chữ ký, nguồn phát hành, đối tượng nhận, thời gian hiệu lực và các thuộc tính dùng để ánh xạ chủ thể.

Không chấp nhận một chuỗi token chỉ vì đọc được trường tên workload. Không lấy địa chỉ kho khóa do client tùy ý chỉ định làm nguồn tin cậy để xác minh chính client đó.

Với mTLS, cần xác minh chuỗi chứng thư và ràng buộc danh tính trong chứng thư với workload được cho phép. Việc kết nối được qua TLS không tự chứng minh client là workload mong muốn.

Các thuộc tính như địa chỉ IP, namespace hoặc nhãn môi trường có thể hỗ trợ quyết định, nhưng cần biết nguồn cung cấp và khả năng bị sửa. Một trường do client tự gửi không có giá trị tương đương thuộc tính đã được xác minh.

### 6.3. Danh tính người dùng và danh tính workload có trách nhiệm khác nhau

Đối với quản trị viên, chính sách có thể yêu cầu xác thực mạnh, phê duyệt, lý do công việc và liên kết yêu cầu thay đổi.

Đối với workload không tương tác, kiểm soát thường dựa vào danh tính máy, môi trường triển khai, vai trò ứng dụng và điều kiện chạy. Không thay trách nhiệm đó bằng một tài khoản dùng chung mang tên đội vận hành.

Nếu người dùng ủy quyền một tác vụ cho workload, nên giữ được cả chủ thể khởi tạo và chủ thể thực thi. Chỉ lưu tên dịch vụ sẽ làm mất bối cảnh cần thiết khi điều tra.

## 7. Chính sách cấp credential và least privilege

Xác thực trả lời “đây là ai”; ủy quyền trả lời “chủ thể này được phép làm gì”. Hai bước cần được thực hiện riêng.

Một chính sách đủ rõ nên mô tả:

~~~text
Chủ thể đã xác minh
  → môi trường và điều kiện được phép
  → target_id được quản lý
  → role_id được quản lý
  → phương thức cấp credential
  → giới hạn thời gian
  → điều kiện phê duyệt hoặc kiểm soát bổ sung
  → sự kiện phải ghi nhận.
~~~

### 7.1. Không để client tự quyết định quyền tại đích

Client có thể yêu cầu một role ID, nhưng broker phải ánh xạ role ID đó sang định nghĩa đã được quản trị. Không nhận một chuỗi lệnh tạo user hoặc một policy tùy ý từ client rồi thực thi bằng quyền connector.

Cũng cần kiểm soát địa chỉ đích. Nếu client được gửi tùy ý endpoint, broker có thể bị lợi dụng kết nối tới dịch vụ không thuộc phạm vi hoặc tiết lộ credential sang một đích do kẻ tấn công kiểm soát.

### 7.2. Quyền hẹp phải tồn tại tại hệ thống đích

Một nhãn “read-only” trong broker không đủ nếu tài khoản tại đích vẫn có quyền quản trị.

Ví dụ, vai trò đối soát có thể được phép đọc những bảng hoặc view đã chỉ định. Cần kiểm tra cả quyền kế thừa, quyền qua nhóm, quyền sở hữu đối tượng và khả năng gọi chức năng dẫn tới hành động rộng hơn.

Broker nên cấp theo vai trò do tổ chức quản lý; việc xác minh quyền hiệu lực tại đích là phần không thể bỏ qua khi triển khai PAM.

### 7.3. JIT và JEA cần được thể hiện bằng cơ chế thực thi

**Just-in-Time (JIT)** giới hạn thời gian quyền hoặc credential được cung cấp theo nhu cầu. Chỉ trả một mật khẩu của tài khoản luôn có quyền quản trị chưa chứng minh quyền nền đã trở thành JIT.

**Just Enough Administration (JEA)** thu hẹp năng lực thực hiện công việc quản trị. Một credential có tuổi thọ ngắn nhưng toàn quyền vẫn có thể gây thiệt hại lớn trong thời gian ngắn.

Broker có thể hỗ trợ JIT/JEA khi phối hợp với vai trò tại đích, cấp quyền có thời hạn hoặc gateway giới hạn tác vụ. Cần chỉ rõ lớp nào thực thi từng giới hạn.

## 8. Ví dụ chính sách và yêu cầu cấp credential

Các cấu trúc dưới đây là giả mã minh họa, không phải cú pháp của một sản phẩm cụ thể. Các định danh, thời hạn và tài nguyên là dữ liệu giả định cho tình huống.

~~~yaml
policy_id: reconciliation-read-prod
subject:
  trusted_issuer: platform-identity
  workload_id: settlement-reconciler
  environment: production
target:
  target_id: payment-ledger-prod
  role_id: ledger-reconciliation-reader
issuance:
  mode: dynamic
  requested_ttl_upper_bound: 10m
  absolute_lifetime_upper_bound: 30m
conditions:
  deployment_identity_must_match: true
  role_mapping_must_be_current: true
audit:
  record_decision: true
  record_credential_lifecycle: true
~~~

Giới hạn 10 phút và 30 phút chỉ minh họa. Thời hạn thực tế cần dựa trên thời gian công việc, khả năng thu hồi của đích, hành vi kết nối và mức ảnh hưởng.

Yêu cầu logic:

~~~json
{
  "request_id": "req-reconcile-042",
  "target_id": "payment-ledger-prod",
  "role_id": "ledger-reconciliation-reader",
  "requested_ttl_seconds": 600,
  "purpose": "scheduled-reconciliation"
}
~~~

Bằng chứng danh tính được truyền bằng cơ chế xác thực đã thiết kế cho API; không đặt credential thật trong ví dụ, log hoặc thông báo lỗi.

Broker xác định thời hạn được cấp từ giới hạn chính sách, bằng chứng danh tính, khả năng issuer và điều kiện hiện tại. Giá trị client yêu cầu không phải cam kết broker phải đáp ứng.

Một phản hồi có thể gồm credential cùng metadata như lease ID, thời điểm hết hạn và cách renew. Metadata chỉ giúp client xử lý vòng đời; hiệu lực thật của credential vẫn phụ thuộc cơ chế tại đích.

## 9. Luồng xử lý một lần cấp

Một trình tự tham chiếu:

1. Client thiết lập kênh bảo mật và xác minh broker.
2. Broker xác minh bằng chứng danh tính theo nguồn tin cậy.
3. Broker chuẩn hóa yêu cầu và phân giải target/role từ danh mục được quản lý.
4. Broker đánh giá quyền, điều kiện, thời hạn và phê duyệt nếu có.
5. Broker đọc credential hoặc yêu cầu issuer tạo credential.
6. Broker ghi trạng thái vòng đời đủ để quản lý lần cấp.
7. Broker ghi sự kiện quyết định và kết quả, không ghi giá trị secret.
8. Broker trả kết quả qua kênh đã bảo vệ.
9. Client dùng credential để kết nối tới đúng đích.
10. Các thành phần liên quan theo dõi renew, hết hạn, thu hồi và hoạt động tại đích.

Giả mã:

~~~text
issue(request, identity_proof):
    identity = verify_against_configured_trust(identity_proof)
    target, role = resolve_managed_target_and_role(request)
    decision = authorize(identity, target, role, current_conditions)

    if decision is not PERMIT:
        record_denied_request_without_secrets()
        return DENIED

    issuance_plan = constrain_by_policy_and_target_capabilities(decision)
    result = obtain_or_create_credential(issuance_plan)

    if result is ambiguous:
        record_pending_reconciliation()
        return RETRY_WITH_TRACKING_REFERENCE

    persist_lifecycle_and_audit_metadata(result)
    return confidential_response(result)
~~~

Giả mã không mô tả một giao dịch nguyên tử xuyên broker, vault và đích. Đặc biệt, lỗi có thể xảy ra sau khi tài khoản đã được tạo nhưng trước khi broker trả kết quả.

### 9.1. Timeout không chứng minh chưa cấp credential

Nếu issuer đã tạo credential rồi kết nối bị đứt, việc client gọi lại có thể tạo nhiều tài khoản mồ côi.

Nên có cơ chế nhận diện yêu cầu lặp lại và đối soát, phù hợp với khả năng issuer. Request ID phải được ràng buộc với danh tính và nội dung yêu cầu; không dùng một mã do client gửi như quyền đọc lại kết quả của người khác.

Không phải hệ thống nào cũng hỗ trợ trả lại cùng credential sau retry. Một thiết kế có thể cần thu hồi lần cấp chưa bàn giao rồi cấp mới. Điều quan trọng là không để kết quả không xác định bị coi như chắc chắn chưa xảy ra.

### 9.2. Khi không lưu được bằng chứng

Chính sách phải xác định yêu cầu audit là điều kiện gì của việc cấp. Có thể cần ghi bền vững tại chỗ trước khi chuyển tiếp, hoặc từ chối cấp mới khi không thể bảo đảm bằng chứng theo yêu cầu.

Nếu credential đã được tạo trước khi lỗi audit xảy ra, cần theo dõi và thu hồi hoặc đối soát. Chỉ trả lỗi cho client chưa giải quyết đối tượng đã tồn tại tại đích.

## 10. Bảo vệ credential sau khi cấp

Khi mô hình trả credential cho workload được sử dụng, workload trở thành một phần của ranh giới bảo vệ secret.

Các nguyên tắc thực hành:

- Hạn chế thời gian và số nơi lưu credential.
- Không ghi credential vào log, trace, crash report hoặc tham số dòng lệnh có thể bị quan sát.
- Không dùng credential làm nhãn metric hay khóa cache có thể được xuất.
- Giới hạn quyền truy cập tệp, socket hoặc vùng lưu tạm nếu cần dùng.
- Xem xét bản sao lưu, dump bộ nhớ và công cụ chẩn đoán.
- Chỉ gửi credential tới đích phù hợp và xác minh danh tính máy chủ.

Biến môi trường, tệp được mount, agent và truyền qua bộ nhớ có các đặc điểm khác nhau; không có lựa chọn nào mặc nhiên loại bỏ rủi ro. Ví dụ, tệp có thể bị sao lưu ngoài ý muốn; biến môi trường có thể lọt vào dữ liệu chẩn đoán; bộ nhớ có thể bị đọc nếu tiến trình hoặc máy chủ bị xâm phạm.

Xóa một tham chiếu trong ứng dụng không bảo đảm mọi bản sao secret đã được xóa vật lý, nhất là trong môi trường có runtime quản lý bộ nhớ. Thiết kế nên dựa vào giảm phơi lộ, quyền truy cập hẹp, thời hạn và khả năng thu hồi thay vì một cam kết xóa bộ nhớ không được kiểm chứng.

## 11. Lease, TTL, renew và hiệu lực tại đích

### 11.1. Tách các mốc thời gian

| Mốc | Ý nghĩa |
|---|---|
| Thời hạn bằng chứng danh tính | Khoảng bằng chứng được chấp nhận để xác minh người yêu cầu |
| Thời hạn credential | Khoảng credential được đích chấp nhận theo cơ chế tương ứng |
| Lease tại broker | Bản ghi vòng đời mà broker dùng để theo dõi hoặc lên lịch xử lý |
| Thời hạn grant hoặc role assignment | Khoảng quyền được gán cho chủ thể tại đích |
| Thời gian tồn tại phiên | Khoảng phiên hoặc kết nối đang hoạt động tiếp tục tồn tại |
| Thời hạn cache | Khoảng một bản sao dữ liệu được giữ và sử dụng theo chính sách |

Các mốc này có thể liên quan nhưng không tự bằng nhau. Lease hết hạn trong broker không tự chứng minh mật khẩu đã mất hiệu lực tại cơ sở dữ liệu.

Token có thời hạn được đích kiểm tra cũng không nhất thiết làm một phiên đã thiết lập kết thúc đúng thời điểm token hết hạn. Cần xác minh hành vi của giao thức và hệ thống đích.

### 11.2. Renew cần đánh giá lại điều kiện phù hợp

Renew không nên trở thành cách duy trì quyền vô hạn sau một lần xác thực ban đầu.

Thiết kế cần quy định:

- Khi nào client cần lấy lại bằng chứng danh tính.
- Có kiểm tra lại policy và trạng thái chủ thể không.
- Giới hạn thời gian tồn tại tuyệt đối.
- Điều kiện từ chối renew.
- Cách workload xử lý khi renew thất bại.

Client có thể chuẩn bị refresh trước hạn với độ lệch thời gian và cơ chế giảm đồng loạt yêu cầu. Không tự kéo dài credential đã hết hạn bằng một giá trị trong cache.

### 11.3. Kết nối dài hạn cần cơ chế riêng

Một connection pool có thể giữ phiên lâu hơn thời gian cấp credential. Khi credential đổi, kết nối mới có thể dùng phiên bản mới trong khi kết nối cũ tiếp tục chạy.

Cần quyết định cách tái xác thực, thay kết nối và giới hạn tuổi phiên. Nếu cần kết thúc phiên vì sự cố, phải có cơ chế thực thi tương ứng tại đích hoặc gateway.

## 12. Rotation và đồng bộ consumer

### 12.1. Rotation của secret có sẵn

Một luồng có thể gồm:

~~~text
Xác định consumer
  → chuẩn bị thay đổi
  → đổi credential tại đích
  → cập nhật phiên bản trong kho
  → cập nhật hoặc refresh consumer
  → kiểm tra xác thực mới
  → xử lý credential và cấu hình cũ.
~~~

Trình tự cụ thể phụ thuộc đích. Có hệ thống hỗ trợ hai credential đồng thời để chuyển đổi; có hệ thống chỉ có một mật khẩu và cần cửa sổ phối hợp. Không giả định luôn có khoảng chồng lấn an toàn.

Broker phải biết nguồn nào là trạng thái có thẩm quyền và cách xử lý khi vault, đích và consumer lệch phiên bản.

### 12.2. Credential động không loại bỏ mọi rotation

Credential ngắn hạn có thể được thay bằng cách cấp mới thay vì cập nhật cùng một mật khẩu. Tuy nhiên, credential quản trị của connector, khóa ký hoặc trust anchor phía dưới vẫn có vòng đời riêng.

Nếu broker dùng một tài khoản quản trị dài hạn để tạo tài khoản tạm thời, tài khoản đó vẫn phải được kiểm kê, giới hạn quyền và bảo vệ.

### 12.3. Không xử lý sự cố bằng rollback thiếu đánh giá

Nếu thay đổi thất bại do lỗi phối hợp, cần có phương án phục hồi theo trạng thái thực tế. Nếu credential cũ bị nghi lộ, đưa credential đó trở lại chỉ để khôi phục dịch vụ có thể tái tạo đường xâm nhập.

Phương án phục hồi nên có credential thay thế, phạm vi sử dụng và người chịu trách nhiệm. Bằng chứng cần cho biết credential nào được đích và consumer sử dụng sau xử lý.

## 13. Thu hồi và ứng phó sự cố

Khi một workload bị xâm phạm, chỉ chặn workload xin credential mới thường chưa đủ.

| Lớp cần xử lý | Ví dụ hành động | Giới hạn cần kiểm tra |
|---|---|---|
| Danh tính nguồn | Vô hiệu hóa chủ thể, chứng thư hoặc quyền lấy token | Bằng chứng đã phát hành có thể vẫn còn hiệu lực |
| Chính sách broker | Chặn cấp mới và renew | Credential đã được trả có thể tiếp tục dùng |
| Credential tại đích | Vô hiệu hóa tài khoản, đổi secret hoặc thu hồi token khi được hỗ trợ | Có cơ chế chỉ hết hiệu lực khi tới hạn |
| Grant và quyền | Gỡ quyền tạm hoặc role assignment | Quyền gián tiếp và bản sao gán quyền cần được xem xét |
| Phiên đang mở | Kết thúc phiên hoặc kết nối liên quan | Đòi hỏi khả năng thực thi tại đích/gateway |
| Dấu vết duy trì truy cập | Kiểm tra khóa mới, user mới, job hoặc policy bị sửa | Thu hồi credential ban đầu không tự xóa mọi thay đổi |

Khả năng thu hồi token phụ thuộc thiết kế. Với credential được kiểm tra độc lập tại đích mà không tra cứu trạng thái thu hồi, việc đánh dấu revoked trong broker có thể chưa làm credential mất hiệu lực ngay.

Quy trình ứng phó cần chỉ ra độ trễ dự kiến, bằng chứng xác nhận và biện pháp giảm ảnh hưởng trong khoảng chờ.

Sự kiện cần liên kết gồm chủ thể yêu cầu, lần cấp, tài khoản tại đích, tài nguyên, thời điểm và các phiên liên quan. Nếu không có ánh xạ này, đội ứng phó có thể không biết phải thu hồi đối tượng nào.

## 14. Tính sẵn sàng và hành vi khi lỗi

Broker có thể nằm trên đường khởi động workload và refresh credential. Vì vậy, thiết kế lỗi ảnh hưởng trực tiếp tới dịch vụ.

### 14.1. Các phụ thuộc phải được nhìn thấy

Ngoài broker, cần xét vault, issuer, nguồn danh tính, dữ liệu chính sách, lưu trữ lease, thời gian hệ thống, phân giải tên và đường mạng.

Nhiều instance broker chưa đủ nếu tất cả cùng phụ thuộc một thành phần không có phương án phục hồi. Trạng thái lease cũng phải được quản lý để tránh mất tác vụ thu hồi khi một instance dừng.

### 14.2. Phân biệt cấp mới với tiếp tục sử dụng

Khi broker không hoạt động:

- Workload có credential còn hiệu lực có thể tiếp tục trong phạm vi mà đích cho phép.
- Workload cần credential mới có thể không khởi động hoặc không mở được kết nối mới.
- Tác vụ thu hồi phụ thuộc broker có thể bị chậm nếu chưa có thành phần thực thi khác.
- Gateway nằm trên đường phiên có thể ảnh hưởng cả kết nối đang hoạt động.

Không mô tả chung “broker down thì mọi truy cập dừng” hoặc “không ảnh hưởng gì”. Kết quả phụ thuộc mô hình cung cấp và vòng đời credential.

### 14.3. Cache cần giới hạn rõ

Nếu dùng cache, phải nêu cache dữ liệu gì, ai được đọc, thời hạn và điều kiện làm mất hiệu lực.

Cache credential làm tăng nơi chứa secret. Cache chính sách có thể làm chậm thu hồi quyền. Cache khóa xác minh có yêu cầu về nguồn tin cậy và xử lý vòng đời khóa.

Không dùng việc broker mất kết nối làm lý do tự động trả credential quản trị dự phòng cho mọi yêu cầu. Đường khẩn cấp cần được thiết kế, giới hạn và kiểm toán riêng.

### 14.4. Không xác minh được điều kiện thì không mặc định đạt

Nếu broker không xác minh được danh tính hoặc quyền cho một lần cấp mới, không nên chuyển kết quả unknown thành permit.

Đối với công việc đang chạy, cần có phương án theo mức rủi ro và khả năng vận hành, như dừng nhận việc mới, chuyển kết nối có kiểm soát hoặc kích hoạt quy trình khẩn cấp đã được quản trị.

Các lựa chọn phải được quyết định trước và kiểm tra trong diễn tập, thay vì được ứng biến bằng một cờ bỏ kiểm soát thường trực.

## 15. Bảo vệ chính broker và quyền quản trị

Broker có thể tiếp cận nhiều hệ thống nhạy cảm nên cần được bảo vệ như một thành phần đặc quyền.

Các điểm thiết kế:

1. Tách quyền sửa policy, quản lý connector, đọc secret và vận hành hạ tầng khi phù hợp.
2. Giới hạn credential của connector tới đúng tài nguyên và hành động cần thiết.
3. Hạn chế đường mạng ra tới vault, issuer và các đích đã quản lý.
4. Bảo vệ cấu hình tin cậy, khóa và dữ liệu trạng thái.
5. Kiểm soát thay đổi policy, lưu phiên bản và chủ thể phê duyệt.
6. Giới hạn tốc độ, phát hiện yêu cầu bất thường và cô lập workload gây quá tải.
7. Quản trị vòng đời tài khoản dùng để quản trị broker.

Thay đổi ánh xạ danh tính hoặc vai trò có thể cấp quyền gián tiếp dù không ai đọc secret. Vì vậy, audit chỉ ghi hoạt động lấy credential sẽ bỏ sót một nhóm hành động quản trị quan trọng.

Quyền tạo tài khoản tạm thời tại đích cũng cần được xem xét như quyền đặc quyền. Không gọi đó là “tài khoản kỹ thuật nội bộ” rồi bỏ khỏi phạm vi PAM.

## 16. Audit, giám sát và bằng chứng kiểm toán

### 16.1. Ghi sự kiện đủ để liên kết

Một sự kiện cấp có thể chứa:

~~~json
{
  "event_type": "credential_issued",
  "request_id": "req-reconcile-042",
  "subject_id": "settlement-reconciler",
  "target_id": "payment-ledger-prod",
  "role_id": "ledger-reconciliation-reader",
  "policy_version": "policy-v17",
  "issuance_id": "issue-081",
  "lease_id": "lease-081",
  "target_principal_id": "principal-081",
  "outcome": "success",
  "credential_expires_at": "2026-11-26T03:10:00Z"
}
~~~

Đây là metadata giả định. Sự kiện thực tế cần thêm thời điểm ghi nhận và các trường phù hợp với mô hình. Không chứa password, private key, access token hoặc toàn bộ header xác thực.

Không dùng giá trị secret làm khóa tương quan. Dùng định danh lần cấp, phiên bản hoặc tham chiếu do hệ thống quản lý.

### 16.2. Chuỗi bằng chứng cần nhiều nguồn

~~~text
Danh tính đã xác minh
  → chính sách có hiệu lực
  → quyết định cấp
  → credential/tài khoản đã tạo hoặc được lấy
  → xác thực tại đích
  → hành động hoặc phiên tại đích
  → renew, hết hạn hoặc thu hồi
  → xác nhận trạng thái cuối.
~~~

Log broker chứng minh quyết định và hành động của broker trong phạm vi nó quan sát. Log đích hoặc gateway bổ sung bằng chứng sử dụng. Hai nguồn cần được liên kết theo thời gian và định danh, với giới hạn độ chính xác được hiểu rõ.

Không gọi credential broker là công cụ giám sát toàn bộ phiên nếu nó chỉ tham gia lúc cấp secret.

### 16.3. Chỉ số có giá trị vận hành

| Chỉ số | Câu hỏi hỗ trợ |
|---|---|
| Tỷ lệ cấp thành công và độ trễ theo loại đích | Broker hoặc phụ thuộc có đang gây nghẽn? |
| Yêu cầu bị từ chối theo lý do | Có cấu hình sai, quyền thừa hoặc hành vi bất thường? |
| Lease quá hạn nhưng chưa xác nhận thu hồi | Vòng đời tại đích có lệch sổ quản lý? |
| Tài khoản động không có bản ghi cấp tương ứng | Có đối tượng mồ côi hoặc đường tạo ngoài broker? |
| Độ trễ thu hồi tới hiệu lực tại đích | Phản ứng sự cố nhanh đến mức nào? |
| Lỗi refresh và xác thực sau rotation | Consumer có đang sử dụng credential cũ? |
| Thay đổi policy hoặc trust configuration | Có thay đổi làm mở rộng quyền truy cập? |

Cần giới hạn dữ liệu nhạy cảm trong nhãn metric và dữ liệu xuất. Một dashboard hữu ích không cần hiển thị giá trị credential.

## 17. Tình huống xuyên suốt: tác vụ đối soát thanh toán

### 17.1. Hiện trạng

Tác vụ đối soát chạy ở production, dùng một tài khoản chia sẻ với công cụ vận hành và có quyền ghi dữ liệu. Mật khẩu được đưa vào cấu hình triển khai; việc đổi mật khẩu phụ thuộc nhiều consumer.

Mục tiêu của thiết kế mới:

- Định danh riêng workload đối soát.
- Chỉ cấp quyền đọc dữ liệu cần thiết.
- Giảm thời gian credential có thể được sử dụng.
- Có ánh xạ giữa lần chạy, lần cấp và tài khoản tại đích.
- Có phương án thu hồi khi workload bị xâm phạm.

### 17.2. Thiết kế đề xuất

Trong tình huống giả định, cơ sở dữ liệu hỗ trợ tạo tài khoản tạm và quản lý quyền theo vai trò. Broker dùng một connector có quyền tạo, gán đúng vai trò được phép và xử lý vòng đời các tài khoản thuộc phạm vi quản lý.

Workload trình bằng chứng từ nguồn danh tính production. Broker ánh xạ sang role đọc đối soát và cấp credential theo giới hạn thời gian của chính sách.

Credential được giữ trong môi trường chạy theo cơ chế đã chọn; không đưa lại vào tệp cấu hình triển khai. Các lần chạy cần thời gian dài hơn phải tuân thủ cơ chế renew hoặc lấy credential mới đã thiết kế.

### 17.3. Những điều vẫn cần xác minh

- Quyền reader có bao gồm quyền ghi qua chức năng hoặc đối tượng kế thừa không?
- Connector có thể tạo tài khoản ngoài phạm vi dự kiến không?
- Tài khoản tạm hết hạn tại đích bằng cơ chế nào?
- Nếu broker dừng, ai tiếp tục thực hiện tác vụ thu hồi?
- Phiên trong connection pool tồn tại bao lâu?
- Đường truy cập bằng tài khoản chia sẻ cũ đã được xử lý chưa?
- Một lần chạy có ánh xạ được tới sự kiện truy vấn ở đích không?

Nếu cơ sở dữ liệu không hỗ trợ cấp động phù hợp, có thể chọn broker trả secret được quản lý cùng rotation có phối hợp. Khi đó phải giữ rõ giới hạn: credential có thể dài hạn hơn, việc quy trách nhiệm và thu hồi phụ thuộc mô hình khác.

### 17.4. Diễn biến sự cố

Giả sử phát hiện workload đối soát bị chiếm quyền sau một lần cấp.

Đội ứng phó cần cô lập workload, ngừng cấp mới/renew, tra các lần cấp liên quan, vô hiệu hóa credential hoặc principal tại đích theo khả năng, xử lý phiên còn mở và kiểm tra hành động đã thực hiện.

Nếu chỉ tắt quyền gọi broker, credential đã cấp có thể vẫn hoạt động. Nếu chỉ đổi một mật khẩu, các thay đổi mà kẻ tấn công đã tạo tại đích có thể vẫn tồn tại.

Bằng chứng đóng sự cố phải thể hiện trạng thái thực tế của credential, quyền và phiên trong phạm vi xử lý, cùng những giới hạn chưa khắc phục.

## 18. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| Mọi workload dùng một API key đọc nhiều secret | Khó quy trách nhiệm, phạm vi ảnh hưởng lớn | Danh tính riêng và policy theo workload |
| Token đọc được là được tin cậy | Có thể chấp nhận bằng chứng giả hoặc sai đối tượng nhận | Xác minh theo cấu hình tin cậy |
| Role do client gửi được thực thi nguyên dạng | Client có thể mở rộng quyền | Ánh xạ sang role đã quản trị |
| Tài khoản tại đích vẫn toàn quyền | Credential ngắn hạn vẫn có ảnh hưởng lớn | Giảm quyền hiệu lực tại đích |
| Lease hết hạn được hiểu là tài khoản đã vô hiệu | Sai lệch giữa sổ quản lý và thực tế | Đối soát và xác minh thu hồi |
| Đổi credential được hiểu là đóng mọi phiên | Phiên cũ tiếp tục hoạt động | Thiết kế quản lý phiên riêng |
| Cache secret không có thời hạn rõ | Tăng bản sao và kéo dài phơi lộ | Giới hạn cache và xử lý mất hiệu lực |
| Retry sau timeout luôn tạo mới | Tài khoản mồ côi, khó kiểm kê | Nhận diện yêu cầu lặp và đối soát |
| Broker lỗi thì cấp secret quản trị dự phòng | Đường lỗi trở thành đường bỏ kiểm soát | Quy trình khẩn cấp có giới hạn |
| Log toàn bộ request/response để dễ debug | Credential bị lộ qua quan sát vận hành | Lọc dữ liệu và ghi metadata |
| Có broker nên bỏ log ở đích | Không thấy hành động sau xác thực | Liên kết audit broker và đích |
| Bỏ qua credential của connector | Hình thành đặc quyền nền không được quản trị | Kiểm kê và quản lý vòng đời connector |

## 19. Bài tập thiết kế

Một đội có ba workload đọc cùng một cơ sở dữ liệu. Cả ba dùng một secret trong vault, lấy qua broker bằng API key chung. Broker đặt lease 15 phút nhưng cơ sở dữ liệu không có thời hạn tương ứng. Connection pool có thể giữ kết nối nhiều giờ.

Hãy trả lời:

1. Những phần nào đã được cải thiện so với nhúng mật khẩu trực tiếp?
2. Những phần nào chưa tạo được danh tính và least privilege theo workload?
3. Sau 15 phút, điều gì thực sự mất hiệu lực?
4. Khi một workload bị xâm phạm, cần thu hồi những lớp nào?
5. Cần thêm bằng chứng gì để biết workload nào đã thực hiện truy vấn?
6. Có thể chọn thiết kế nào nếu đích hỗ trợ hoặc không hỗ trợ credential động?

Gợi ý phân tích:

- Broker tập trung đường lấy secret và có thể tạo sự kiện truy xuất, nhưng API key chung làm suy yếu khả năng xác định chủ thể.
- Nếu tài khoản dùng chung có quyền rộng, nhãn role ở broker chưa giảm quyền tại cơ sở dữ liệu.
- Lease 15 phút chỉ có hiệu lực theo cơ chế đã triển khai; nó không tự thay mật khẩu hoặc đóng kết nối.
- Cần xem xét danh tính gọi broker, secret tại đích, quyền, phiên và đường truy cập ngoài broker.
- Danh tính riêng cùng định danh lần cấp giúp liên kết; log đích và hành vi tài khoản chia sẻ quyết định giới hạn quy trách nhiệm.
- Nếu không cấp động được, vẫn có thể phân tách tài khoản, thu hẹp quyền, quản lý rotation và đánh giá phương án gateway. Cần ghi rõ giới hạn của lựa chọn đó.

## 20. Các điểm cần nắm

Credential broker nối danh tính đã xác minh với chính sách cấp và sử dụng credential. Giá trị của nó nằm ở phạm vi quyền, quản lý vòng đời và bằng chứng, không chỉ ở việc chuyển secret qua một endpoint.

Một kiến trúc PAM có broker cần làm rõ credential nằm ở đâu, ai có thể sử dụng, thành phần nào thực thi hết hạn và thu hồi, cùng cách liên kết hoạt động tại đích. Credential ngắn hạn, lease, quyền tạm và phiên là những đối tượng liên quan nhưng cần được quản lý bằng cơ chế cụ thể.

Khi đánh giá một thiết kế, hãy lần theo một yêu cầu từ danh tính ban đầu đến trạng thái cuối của tài khoản, credential, grant và phiên. Mỗi bước phải có chủ thể chịu trách nhiệm và bằng chứng phù hợp với điều hệ thống thực sự quan sát.

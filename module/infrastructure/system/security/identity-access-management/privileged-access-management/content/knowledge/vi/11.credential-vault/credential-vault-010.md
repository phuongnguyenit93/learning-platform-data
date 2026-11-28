# Vault audit trail

## Mục tiêu bài học

Trong chương **Vault**, audit trail là chuỗi bản ghi giúp giải thích ai đã yêu cầu, được cho phép, sử dụng hoặc thay đổi khả năng truy cập credential đặc quyền; hành động liên quan đến đối tượng nào, ở thời điểm nào và có kết quả gì.

Trong **Privileged Access Management (PAM)**, vault lưu giữ credential cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Audit trail hỗ trợ kiểm kê quyền, least privilege, JIT/JEA, luân chuyển credential, giám sát phiên và lưu bằng chứng phục vụ kiểm toán, ứng phó sự cố.

**Có log không tự chứng minh đã có một audit trail đầy đủ và đáng tin cậy.** Cần xác định sự kiện nào được ghi, ý nghĩa của kết quả, cách bảo vệ bản ghi, độ đầy đủ của đường thu thập và khả năng liên kết với hoạt động ở hệ thống đích.

Sau bài học, bạn có thể:

- Phân biệt audit trail với log chẩn đoán và số liệu vận hành.
- Xác định các nhóm sự kiện cần ghi trong vòng đời credential.
- Thiết kế bản ghi có danh tính, tài nguyên, quyết định và kết quả đủ rõ.
- Tránh đưa bí mật vào audit và bảo vệ metadata nhạy cảm.
- Đánh giá tính toàn vẹn, độ đầy đủ và độ trễ của đường thu thập.
- Sử dụng audit để kiểm tra chính sách, điều tra bất thường và ghi nhận giới hạn kết luận.

## 1. Audit trail cần trả lời những câu hỏi nào?

Một chuỗi bằng chứng có ích cần trả lời được:

1. Ai hoặc workload nào khởi tạo yêu cầu?
2. Thành phần nào thực sự gọi vault?
3. Yêu cầu nhằm vào credential, tài khoản hoặc cấu hình nào?
4. Chính sách và điều kiện nào được áp dụng?
5. Quyết định là cho phép hay từ chối?
6. Hành động có thực thi không và thành công ở lớp nào?
7. Credential hoặc phiên bản liên quan được sử dụng tiếp ở đâu?
8. Có thay đổi quyền, cấu hình hoặc cơ chế audit nào trước và sau sự kiện?
9. Có khoảng trống dữ liệu khiến chưa thể kết luận không?

Ví dụ, một sự kiện “cho phép đọc” và một sự kiện “đã gửi phản hồi” mang ý nghĩa khác nhau. Cả hai vẫn chưa tự chứng minh người nhận đã đăng nhập vào hệ thống đích.

Audit trail phải giữ được những khác biệt này để tránh suy luận quá mức.

### Phân biệt các loại dữ liệu

| Loại dữ liệu | Mục đích chính | Ví dụ |
| --- | --- | --- |
| Audit trail | Truy trách nhiệm, kiểm tra quyết định và thay đổi | Ai sửa policy, ai truy xuất credential |
| Log chẩn đoán | Tìm nguyên nhân lỗi kỹ thuật | Lỗi connector hoặc lỗi phân tích yêu cầu |
| Số liệu vận hành | Theo dõi tải và sức khỏe dịch vụ | Số yêu cầu, độ trễ, dung lượng hàng đợi |
| Bản ghi phiên | Quan sát một phiên theo khả năng giải pháp | Metadata phiên, hình ảnh hoặc nội dung được ghi |
| Audit tại đích | Ghi nhận hành động trên tài nguyên đích | Xác thực, thay quyền, thao tác quản trị |

Các loại dữ liệu bổ sung cho nhau. Một biểu đồ số lần đọc không thay thế bản ghi về từng danh tính và tài nguyên. Một bản ghi vault cũng không thay thế toàn bộ audit của hệ thống đích.

## 2. Phạm vi sự kiện cần bao phủ

Không nên chỉ ghi những lần đọc bí mật thành công.

| Nhóm | Ví dụ sự kiện cần xem xét | Giá trị điều tra |
| --- | --- | --- |
| Xác thực | Thành công, thất bại, nhận danh tính liên kết | Xác định danh tính và điều kiện tiếp cận |
| Quyết định truy cập | Cho phép, từ chối, thiếu điều kiện phê duyệt | Giải thích vì sao hành động được thực hiện hoặc bị chặn |
| Credential | Tạo, nhập, đọc, dùng qua broker, đổi phiên bản, thu hồi, xóa | Theo dõi vòng đời và phạm vi phân phối |
| Lease hoặc checkout | Cấp, gia hạn, hết hạn, trả lại, kết quả xử lý | Phân biệt trạng thái quản lý với hiệu lực ở đích |
| Chính sách | Tạo, sửa, gán quyền, thay điều kiện hoặc người phê duyệt | Phát hiện mở rộng đường quyền |
| Quản trị vault | Đổi cấu hình, connector, endpoint, cơ chế xác thực | Xác định thay đổi có thể ảnh hưởng toàn kho |
| Khóa và khôi phục | Hoạt động quản lý khóa, backup, restore theo khả năng hệ thống | Theo dõi các đường tiếp cận hoặc làm mất dữ liệu |
| Audit | Đổi nơi nhận, bộ lọc, thời hạn, quyền xem hoặc xuất | Phát hiện thay đổi khả năng quan sát |
| Sử dụng khẩn cấp | Kích hoạt break-glass, lý do, phạm vi và kết thúc | Kiểm tra truy cập ngoài luồng thông thường |

Với mỗi nhóm, cần xác định nguồn nào tạo bằng chứng. Một số sự kiện nằm tại vault, một số nằm ở nguồn danh tính, bộ quản lý khóa, broker hoặc nơi lưu audit.

Không thể yêu cầu vault tự chứng minh mọi hoạt động xảy ra ngoài tầm quan sát của nó.

## 3. Ngữ nghĩa sự kiện: ghi đúng điều đã xảy ra

Một hành động thường đi qua nhiều trạng thái:

~~~text
Yêu cầu được tiếp nhận
         |
         v
Danh tính được xác thực
         |
         v
Chính sách đưa ra quyết định
         |
         v
Hành động được thực thi
         |
         v
Phản hồi hoặc trạng thái được phát hành
         |
         v
Bên nhận sử dụng tại hệ thống đích
~~~

Các trạng thái không tự suy ra nhau.

### Những kết luận cần tránh

| Bản ghi quan sát được | Chưa đủ để kết luận |
| --- | --- |
| Policy cho phép đọc bí mật | Giá trị bí mật đã được gửi |
| Vault ghi phản hồi đã gửi | Người dùng đã nhìn thấy hoặc đã sử dụng bí mật |
| Broker lấy credential | Phiên tại đích đã thiết lập thành công |
| Vault cập nhật phiên bản | Credential mới đã có hiệu lực tại đích |
| Lease hết hạn | Credential và mọi phiên ở đích đã bị thu hồi |
| Yêu cầu thu hồi đã gửi | Đích đã hoàn tất việc thu hồi |
| Không có sự kiện truy xuất | Không có đường sử dụng nào khác hoặc không có khoảng trống log |

Cần thống nhất ý nghĩa các trường kết quả. Chẳng hạn “success” phải cho biết thành công của xác thực, quyết định policy, thao tác vault hay xác minh ở đích.

Nếu không biết kết quả cuối, hãy ghi trạng thái chưa xác định và liên kết công việc đối soát. Không biến timeout thành bằng chứng chắc chắn thao tác chưa xảy ra.

## 4. Mô hình bản ghi audit

Một bản ghi nên đủ cấu trúc để tìm kiếm và liên kết, đồng thời giữ được ngữ nghĩa nguồn.

| Nhóm trường | Nội dung điển hình |
| --- | --- |
| Định danh sự kiện | ID sự kiện, phiên bản schema, loại sự kiện |
| Nguồn | Thành phần, node, phạm vi quản lý, thế hệ tiến trình khi cần |
| Thời gian | Thời điểm sự kiện, thời điểm tiếp nhận, độ tin cậy thời gian |
| Danh tính | Principal gọi trực tiếp, loại danh tính, bên khởi tạo được xác minh nếu có |
| Yêu cầu | ID do hệ thống kiểm soát, mã liên kết, mục đích hoặc hồ sơ được tham chiếu |
| Tài nguyên | ID bản ghi credential, tài khoản đích, môi trường hoặc phạm vi |
| Phân quyền | Quyết định, policy và phiên bản, điều kiện hoặc phê duyệt liên quan |
| Thực thi | Hành động, trạng thái, kết quả, mã lỗi đã làm sạch |
| Liên kết | Phiên, thao tác rotation, phiên bản credential, thay đổi cấu hình |
| Chất lượng | Trường thiếu, giới hạn thu thập hoặc thông tin chuẩn hóa |

Không phải sự kiện nào cũng có mọi trường. Cần phân biệt trường không áp dụng với trường bị thiếu do lỗi.

### Danh tính gọi trực tiếp và người khởi tạo

Một broker có thể gọi vault bằng danh tính dịch vụ thay mặt người vận hành. Nếu chỉ ghi broker, khó phân biệt người yêu cầu; nếu chỉ ghi tên người dùng do client gửi lên, có thể quy kết sai.

Cần giữ cả principal thực thi và bên khởi tạo khi bên khởi tạo đã được xác minh qua cơ chế tin cậy. Nguồn của thông tin đại diện phải rõ ràng.

Trường “người yêu cầu”, “owner” hoặc “ticket” do client tự cung cấp chỉ là dữ liệu khai báo nếu chưa được đối chiếu. Nó không tự trở thành bằng chứng thẩm quyền.

### Định danh phải tồn tại qua thay đổi tên

Tên hiển thị có thể đổi hoặc trùng giữa các môi trường. Nên dùng ID ổn định trong phạm vi nguồn, kèm ngữ cảnh tenant, hệ thống và tài nguyên.

Khi cần giải thích lịch sử, phải biết ánh xạ danh tính và policy tại thời điểm sự kiện. Tra danh tính theo trạng thái hiện tại có thể dẫn đến quy kết sai cho một bản ghi cũ.

## 5. Ví dụ một sự kiện truy xuất

Ví dụ sau là **dữ liệu minh họa, không phải schema bắt buộc của một sản phẩm**. Các định danh đều mang tính minh họa và không chứa credential.

~~~json
{
  "schema_version": "example-1",
  "event_id": "event-example-1042",
  "event_time_utc": "2026-01-15T08:02:10Z",
  "ingested_time_utc": "2026-01-15T08:02:12Z",
  "source": {
    "component": "vault-api",
    "node_ref": "vault-node-a",
    "generation_ref": "generation-example-7",
    "sequence": 1042
  },
  "actor": {
    "principal_type": "workload",
    "principal_ref": "release-pipeline-a",
    "authentication_context_ref": "auth-context-example"
  },
  "request_ref": "request-example-88",
  "action": "secret.read",
  "resource": {
    "managed_account_ref": "production-service-a-release",
    "credential_version_ref": "version-example-9"
  },
  "authorization": {
    "decision": "allow",
    "policy_ref": "service-a-release-access",
    "policy_version_ref": "policy-version-example-17"
  },
  "execution": {
    "outcome": "response-sent"
  }
}
~~~

Trong ví dụ, “response-sent” chỉ có nghĩa theo định nghĩa của nguồn rằng phản hồi đã được gửi ra khỏi thành phần xử lý. Nó không tự chứng minh bên nhận đã lưu, đọc hoặc dùng credential để đăng nhập.

Thời điểm tiếp nhận do đường thu thập gắn vào phải được phân biệt với thời điểm nguồn phát sự kiện. Trường sequence cũng chỉ có ý nghĩa theo phạm vi và thế hệ nguồn đã định nghĩa, không phải thứ tự toàn cục của mọi node.

## 6. Không để audit trở thành một kho bí mật thứ hai

Audit thường có nhiều người dùng, nhiều bản sao và vòng đời riêng. Đưa credential vào đó làm tăng đáng kể phạm vi cần bảo vệ.

### Những dữ liệu cần loại khỏi bản ghi

- Mật khẩu và giá trị bí mật.
- Token truy cập, refresh token hoặc session token có thể sử dụng.
- Khóa riêng và vật liệu khôi phục nhạy cảm.
- Header xác thực.
- Payload phản hồi chứa bí mật.
- Tham số URL hoặc thông báo lỗi có chèn credential.
- Nội dung cấu hình chứa bí mật không cần thiết.

Cần kiểm tra cả đường thành công lẫn đường lỗi. Exception, stack trace hoặc log debug có thể vô tình ghi payload dù sự kiện audit chính đã được làm sạch.

### Dùng tham chiếu thay giá trị

Nên ghi ID credential, phiên bản, loại credential và kết quả sử dụng. Những thông tin này thường đủ để liên kết vòng đời mà không ghi giá trị.

Ngay cả metadata như đường dẫn bí mật, tên tài khoản, địa chỉ đích và owner cũng có thể nhạy cảm. Quyền đọc audit phải gắn với nhiệm vụ.

### Hash hoặc mã hóa trường không tự giải quyết mọi rủi ro

Một số thiết kế che hoặc biến đổi trường nhạy cảm. Cần hiểu cơ chế và khả năng liên kết của nó.

Hash đơn giản trên dữ liệu dễ đoán có thể bị suy đoán bằng tập giá trị ứng viên. Cơ chế có khóa cũng phải bảo vệ khóa và kiểm soát bên có thể yêu cầu tính giá trị tương ứng.

Không cần lưu hash của mật khẩu chỉ để chứng minh đã truy xuất đúng. Dùng định danh phiên bản do hệ thống quản lý thường phù hợp hơn cho mục đích đó.

## 7. Kiến trúc thu thập và lưu giữ

~~~mermaid
flowchart LR
    Vault[Vault và API] --> Buffer[Bộ đệm được bảo vệ]
    Broker[Broker và bộ rotation] --> Buffer
    Buffer --> Transport[Kênh truyền xác thực]
    Transport --> Store[Kho audit được bảo vệ]
    Store --> Normalize[Chuẩn hóa và liên kết]
    Normalize --> Detect[Phát hiện và xử lý]
    Store --> Review[Tra cứu và xuất bằng chứng]
    Health[Theo dõi sức khỏe đường thu thập] --> Detect
~~~

Đây là mô hình logic. Không bắt buộc các nguồn dùng chung một bộ đệm hoặc tất cả chức năng nằm trên một nền tảng.

### 7.1. Tại nguồn

Nguồn cần tạo bản ghi có ý nghĩa, loại dữ liệu bí mật và giữ ID liên kết. Nếu sự kiện không được tạo đúng tại nguồn, việc lưu trữ tốt ở phía sau không khôi phục được thông tin chưa từng có.

### 7.2. Bộ đệm và truyền tải

Cần xác định dữ liệu được giữ khi nơi nhận không sẵn sàng, giới hạn dung lượng, cách bảo vệ và thời điểm nguồn coi bản ghi đã được tiếp nhận.

Một xác nhận ở đầu vào bộ thu không nhất thiết có nghĩa dữ liệu đã được lưu bền vững tại nơi cuối cùng. Ngữ nghĩa xác nhận cần được thiết kế và kiểm tra.

### 7.3. Kho lưu và lớp phân tích

Kho lưu bảo vệ dữ liệu theo chính sách; lớp phân tích tạo chỉ số, liên kết và cảnh báo. Nếu lớp phân tích lỗi, cần có cách xác định dữ liệu gốc còn ở đâu và khả năng xử lý lại.

“Bản gốc” ở đây là sự kiện nguồn đã được thiết kế để không chứa bí mật, không phải sao chép nguyên payload xác thực hoặc phản hồi chứa credential.

## 8. Độ đầy đủ: phát hiện mất, lặp và sai thứ tự

Một audit trail có thể bị thiếu dù không có lỗi hiển thị trên giao diện.

### 8.1. Mất dữ liệu

Các nguyên nhân có thể gồm:

- Nguồn không ghi một loại hành động.
- Bộ lọc loại nhầm sự kiện.
- Bộ đệm đầy hoặc ổ đĩa không còn dung lượng.
- Lỗi truyền tải hoặc hết thời gian giữ.
- Parser không tương thích schema mới.
- Một node chưa được cấu hình gửi audit.
- Chuyển vai trò hoặc khôi phục làm lệch trạng thái thu thập.

Không có sự kiện có thể nghĩa là không có hoạt động, nhưng cũng có thể nghĩa là mất khả năng quan sát. Cần tín hiệu sức khỏe độc lập để phân biệt.

### 8.2. Sự kiện lặp

Cơ chế gửi lại có thể tạo bản ghi lặp. Cần chống đếm trùng bằng khóa có phạm vi đủ rõ, chẳng hạn nguồn, thế hệ và ID sự kiện.

Nếu cùng một ID xuất hiện với nội dung khác nhau, không nên im lặng loại bỏ một bản. Đây có thể là lỗi hoặc dấu hiệu toàn vẹn cần xem xét.

Không nên khẳng định “chỉ có đúng một bản ghi” nếu thiết kế thực tế cho phép gửi lại và chưa có cơ chế xử lý lặp được xác minh.

### 8.3. Sai thứ tự

Sự kiện có thể đến muộn hoặc qua các đường khác nhau. Thời gian tiếp nhận không tự biểu diễn thứ tự thực thi.

Sequence giúp phân tích trong phạm vi nguồn nếu nguồn hỗ trợ, nhưng cần hiểu khi nào nó bắt đầu lại, có được cấp cho mọi loại sự kiện không và bộ lọc có tạo khoảng số hợp lệ không.

Một khoảng sequence là tín hiệu cần giải thích, không tự động là bằng chứng tấn công.

### 8.4. Thời gian

Cần đồng bộ và theo dõi sai lệch thời gian của các nguồn. Thời gian nguồn, thời gian tiếp nhận và thời gian xử lý phải được phân biệt.

Chênh lệch giữa thời gian sự kiện và thời gian tiếp nhận có thể bao gồm cả độ trễ truyền lẫn sai lệch đồng hồ. Không coi đó là phép đo chính xác duy nhất của độ trễ đường truyền khi chưa biết chất lượng thời gian.

## 9. Tính toàn vẹn và phân tách quyền

Bảo vệ audit cần xét cả người vận hành vault, người quản trị kho log, người quản lý khóa và người có thể sửa pipeline.

### Những quyền nên được xem xét riêng

| Khả năng | Rủi ro |
| --- | --- |
| Đọc audit | Lộ cấu trúc quyền và dữ liệu hoạt động |
| Sửa hoặc xóa bản ghi | Làm sai bằng chứng |
| Đổi bộ lọc hoặc nơi nhận | Tạo điểm mù cho hoạt động sau đó |
| Đổi policy lưu giữ | Làm mất dữ liệu sớm hơn dự kiến |
| Xuất bằng chứng | Tạo bản sao ngoài phạm vi kiểm soát |
| Quản lý khóa bảo vệ | Có thể ảnh hưởng đọc dữ liệu hoặc xác minh |
| Sửa mã nguồn tạo sự kiện | Có thể thay đổi nội dung trước khi ghi |

Không nên để người sử dụng một credential có thể tự xóa mọi dấu vết sử dụng đó.

### Append-only và khả năng phát hiện sửa đổi

Cơ chế chỉ ghi thêm hoặc lưu giữ có bảo vệ có thể giảm nguy cơ sửa, xóa theo thiết kế. Tuy nhiên, phải xét quyền quản trị, cấu hình, khóa và đường khôi phục thực tế.

Hash chain hoặc chữ ký có thể giúp phát hiện một số thay đổi nếu khóa, điểm neo và quy trình xác minh được bảo vệ. Chúng không tự bảo đảm:

- Sự kiện đúng đã được tạo ngay từ đầu.
- Không có sự kiện bị bỏ trước khi ký.
- Không có phần cuối chuỗi bị loại bỏ khi thiếu điểm kiểm chứng độc lập.
- Thành phần cầm khóa ký chưa bị kiểm soát.
- Nội dung đã ghi phản ánh toàn bộ hoạt động.

Chữ ký chứng minh quan hệ với khóa theo cơ chế xác minh, không tự chứng minh mọi hành động được ghi là hợp lệ.

### Audit cho chính việc quản lý audit

Cần ghi nhận truy vấn hoặc xuất dữ liệu nhạy cảm, thay quyền, thay nơi nhận và thay cấu hình quan trọng.

Mục tiêu là truy được hoạt động quản trị và tiếp cận bằng chứng. Không cần tạo một vòng lặp vô hạn bằng cách ghi lại mỗi lần một sự kiện nội bộ khác được ghi.

## 10. Khi đường audit không sẵn sàng

Tổ chức cần quyết định hành vi cho từng lớp thao tác, thay vì chỉ dựa vào mặc định của sản phẩm.

Những câu hỏi cần giải quyết:

- Thao tác nào bắt buộc có bản ghi bền vững trước khi thực hiện?
- Có được tiếp tục bằng bộ đệm được bảo vệ không?
- Bộ đệm đầy thì dừng thao tác nào?
- Quy trình khẩn cấp nào được phép hoạt động trong điều kiện suy giảm?
- Ai có quyền quyết định và bằng chứng thay thế là gì?
- Sau phục hồi, làm thế nào gửi lại, đối soát và công bố khoảng trống?

### Ghi ý định và ghi kết quả

Một thiết kế có thể ghi ý định trước khi thực thi thao tác quan trọng, rồi ghi kết quả sau đó.

Cách này giúp nhận biết công việc chưa có kết quả cuối, nhưng bản ghi ý định không được coi là bằng chứng thao tác đã hoàn thành. Nếu mất kết nối giữa hai thời điểm, cần đối soát với trạng thái vault hoặc đích.

### Dừng hay tiếp tục phải có ngữ nghĩa rõ

Với một số thao tác nhạy cảm, không ghi được bằng chứng bắt buộc có thể là điều kiện dừng. Với một số tình huống phục hồi, quy trình có thể cho phép tiếp tục có điều kiện.

Không nên âm thầm bỏ log để duy trì giao diện hoạt động. Cũng không nên đặt yêu cầu dừng chung mà chưa xét đường khẩn cấp và khả năng phục hồi của hạ tầng PAM.

## 11. Liên kết với rotation, JIT và giám sát phiên

### 11.1. Rotation

Cần liên kết được:

1. Ai hoặc thành phần nào khởi tạo thay đổi.
2. Tài khoản và phiên bản liên quan.
3. Thao tác tại nơi có thẩm quyền đổi credential.
4. Trạng thái vault ghi nhận.
5. Kết quả xác minh ở đích.
6. Bên phụ thuộc đã chuyển đổi trong phạm vi.
7. Lỗi hoặc trạng thái chưa xác định.

Không ghi giá trị credential cũ hoặc mới vào sự kiện để hỗ trợ đối soát.

### 11.2. JIT và checkout

Cần phân biệt yêu cầu, quyết định, kích hoạt, gia hạn, hết hạn và xác minh thu hồi.

Một sự kiện “hết hạn” trong PAM không tự chứng minh role, credential hoặc phiên ở đích đã hết tác dụng. Bằng chứng thu hồi phải chỉ rõ đối tượng và kết quả thực tế theo khả năng nền tảng.

### 11.3. Broker và phiên

Vault có thể chứng minh broker đã được cấp credential. Để biết người nào mở phiên, vào đích nào và đã làm gì, cần liên kết thêm bằng chứng của broker và đích.

Không mặc định mọi giao thức đều ghi được mọi thao tác. Bản ghi hình, metadata kết nối và audit câu lệnh có phạm vi khác nhau.

Nếu người dùng có thể truy cập trực tiếp ngoài broker, audit của vault chưa bao phủ đường đó. Đây là một giới hạn cần xử lý hoặc công bố, không nên che bằng nhãn “mọi phiên đã được giám sát”.

## 12. Từ audit đến phát hiện bất thường

Một số tình huống đáng xem xét:

| Tín hiệu | Câu hỏi cần điều tra |
| --- | --- |
| Nhiều credential được truy xuất trong thời gian ngắn | Có tác vụ được chấp nhận hay hoạt động thu thập bất thường? |
| Workload đọc bí mật ngoài phạm vi thông thường | Policy, owner hoặc cách dùng có thay đổi không? |
| Policy mở rộng ngay trước lần truy xuất | Thay đổi có thẩm quyền và đúng nhu cầu không? |
| Dùng break-glass | Có điều kiện kích hoạt, người chịu trách nhiệm và review không? |
| Nhiều yêu cầu bị từ chối | Lỗi triển khai, credential hết hạn hay hoạt động thăm dò? |
| Đổi cấu hình audit gần sự kiện nhạy cảm | Có tạo khoảng trống bằng chứng không? |
| Rotation chưa có xác minh cuối | Có nguy cơ lệch trạng thái hoặc credential cũ còn hiệu lực? |
| Một node ngừng gửi sự kiện | Không có hoạt động hay đường thu thập bị lỗi? |

Một tín hiệu bất thường chưa phải kết luận tài khoản bị chiếm quyền. Cần đối chiếu lịch thay đổi, owner, công việc hợp lệ và giới hạn dữ liệu.

### Luật phát hiện cần gắn với ngữ cảnh

Ngưỡng truy xuất phù hợp với một tài khoản người dùng có thể không phù hợp với một job được phép đọc nhiều credential. Không dùng một con số chung cho mọi chủ thể.

Cần xác định tập bí mật được phép, giờ hoặc sự kiện công việc, vai trò principal và nguồn dữ liệu đủ bao phủ. Những điều này phải được cập nhật khi dịch vụ thay đổi.

### Kết quả phát hiện phải dẫn đến công việc

Cảnh báo cần có người tiếp nhận, bằng chứng được tham chiếu, phạm vi tài nguyên và hành động xử lý theo thẩm quyền.

Không gửi giá trị bí mật cùng thông báo. Người xử lý cần truy cập bằng chứng qua kênh được bảo vệ.

## 13. Ví dụ điều tra: pipeline đọc credential ngoài phạm vi

Một pipeline A thường chỉ nhận credential triển khai của dịch vụ A. Audit ghi nhận chuỗi sự kiện minh họa:

| Thời điểm minh họa | Quan sát |
| --- | --- |
| 08:00 | Một thay đổi policy mở rộng phạm vi đọc của pipeline A |
| 08:02 | Pipeline A được cho phép đọc credential của dịch vụ B, phản hồi được ghi là đã gửi |
| 08:03 | Hệ thống phát hiện khác biệt với phạm vi được kỳ vọng |
| 08:04 | Người có thẩm quyền hạn chế đường cấp mới theo quy trình |
| 08:05 | Khởi tạo xử lý credential B và đối soát hoạt động tại đích |

### 13.1. Những điều có thể kết luận ban đầu

Nếu đường audit có đủ bằng chứng, có thể xác định thay đổi policy, danh tính thực hiện, policy áp dụng và việc cấp credential theo ngữ nghĩa nguồn.

Chưa thể chỉ từ đó khẳng định:

- Người tấn công đã thực hiện thay đổi.
- Pipeline đã sử dụng credential ở đích.
- Credential chỉ được cấp một lần.
- Mọi bản sao credential đã bị thu hồi.
- Không còn phiên nào đang hoạt động.

### 13.2. Những bằng chứng cần bổ sung

Cần kiểm tra nguồn thẩm quyền của thay đổi, hồ sơ công việc, danh tính pipeline, log tại đích, các lần cấp liên quan và sức khỏe đường thu thập.

Nếu cần rotation, phải theo dõi đến xác minh ở đích. Nếu có phiên đang chạy, xem cơ chế xử lý phiên theo mục tiêu containment.

Hạn chế policy chỉ cắt một đường cấp mới. Credential đã được gửi ra ngoài vault có vòng đời riêng.

### 13.3. Bảo toàn và ghi giới hạn

Cần giữ các sự kiện liên quan cùng schema, nguồn, phiên bản policy và quy tắc liên kết. Ghi rõ cửa sổ thời gian, nguồn đã xem và khoảng trống.

Một timeline nên phân biệt thời điểm nguồn, thời điểm tiếp nhận và thứ tự đã xác minh. Không sắp theo một trường thời gian duy nhất rồi coi đó là quan hệ nhân quả chắc chắn.

## 14. Tra cứu và xuất bằng chứng

Truy vấn nên bắt đầu từ một câu hỏi cụ thể, chẳng hạn:

- Ai được cấp credential X trong một cửa sổ thời gian?
- Policy nào có hiệu lực cho lần truy xuất?
- Có thay đổi thẩm quyền trước sự kiện không?
- Rotation nào chưa có kết quả xác minh?
- Những nguồn nào không gửi dữ liệu trong cùng giai đoạn?

Có thể kết hợp mã yêu cầu, tài khoản đích, phiên bản credential, principal và ID phiên. Không nên chỉ tìm theo tên hiển thị hoặc vài từ trong thông báo tự do.

### Hồ sơ xuất bằng chứng

Khi cần xuất, nên ghi:

- Mục đích, người thực hiện và người được phép nhận.
- Phạm vi truy vấn, cửa sổ thời gian và bộ lọc.
- Nguồn, phiên bản schema và bước chuẩn hóa liên quan.
- Thời điểm xuất và định danh bộ bằng chứng.
- Cơ chế kiểm tra toàn vẹn phù hợp.
- Giới hạn dữ liệu và thông tin đã che.
- Nơi lưu, quyền truy cập và vòng đời của bản xuất.

Nếu dùng hash để kiểm tra toàn vẹn bản xuất, cần bảo vệ giá trị tham chiếu hoặc kênh xác minh. Lưu file và hash ở cùng một nơi mà cùng người có thể sửa cả hai không tạo được mọi bảo đảm mong muốn.

Xuất dữ liệu không nên trở thành đường đưa toàn bộ audit nhạy cảm vào tài liệu công khai hoặc công cụ không thuộc phạm vi được chấp nhận.

## 15. Lưu giữ, khôi phục và vòng đời bằng chứng

Thời hạn lưu giữ cần dựa trên mục tiêu vận hành, kiểm tra, điều tra và yêu cầu thực tế áp dụng. Không có một thời hạn chung thích hợp cho mọi tổ chức.

Cần xác định:

- Những loại sự kiện và bản ghi phiên cần giữ.
- Khoảng thời gian tìm kiếm trực tiếp và cách truy xuất dữ liệu lưu trữ.
- Quyền đọc, xuất, thay policy và xóa.
- Cơ chế bảo vệ khóa cùng dữ liệu sao lưu.
- Cách thực hiện xóa theo chính sách và ghi nhận hành động đó.
- Cách xử lý bằng chứng đang phục vụ một cuộc điều tra.

### Xóa tài khoản không đồng nghĩa xóa lịch sử

Audit có thể cần tiếp tục giải thích hoạt động của tài khoản đã bị xóa. Cần giữ định danh và ngữ cảnh phù hợp mà không biến kho audit thành nơi lưu bí mật đã thu hồi.

### Khôi phục audit khác khôi phục credential

Kho audit và vault có thể có cơ chế khôi phục khác nhau. Khi khôi phục, cần kiểm tra dữ liệu, khóa, schema, quyền và liên kết thời gian.

Bản audit cũ có thể giải thích một trạng thái credential trước đây; nó không thay thế kiểm tra credential hiện tại ở đích và không nên chứa giá trị để khôi phục mật khẩu.

Nếu khôi phục làm thay đổi ID nguồn hoặc sequence, cần giữ ngữ cảnh thế hệ để tránh gộp nhầm hoặc loại nhầm sự kiện.

## 16. Xác minh chất lượng audit trail

Cần kiểm tra bằng những sự kiện được kiểm soát trong phạm vi phù hợp:

1. Một yêu cầu được phép.
2. Một yêu cầu bị từ chối đúng policy.
3. Một thay đổi policy hoặc cấu hình được chấp nhận.
4. Một thao tác vòng đời credential thuộc phạm vi.
5. Một phiên hoặc tác vụ cần liên kết với đích.
6. Một tình huống suy giảm đường thu thập nếu kế hoạch cho phép.

Mục tiêu là xác nhận loại sự kiện, danh tính, tài nguyên, quyết định, kết quả, liên kết và việc không ghi bí mật.

### Kiểm tra độ đầy đủ có mẫu số rõ

Nếu một kịch bản thử đã tạo 100 sự kiện kỳ vọng và nơi nhận có 99 sự kiện hợp lệ sau xử lý lặp, có một phần cần đối soát.

Kết quả đó chỉ nói về tập sự kiện kiểm tra đã biết. Không thể suy ra “bao phủ 99% mọi hoạt động thực tế” khi chưa biết toàn bộ sự kiện đáng lẽ phải được tạo.

### Những chỉ số hữu ích

| Chỉ số | Ý nghĩa và giới hạn |
| --- | --- |
| Độ phủ loại sự kiện | Loại hành động nào trong phạm vi có bằng chứng |
| Nguồn đang gửi dữ liệu | Phát hiện node hoặc thành phần bị mất quan sát |
| Tuổi dữ liệu gần nhất | Cần kết hợp nhịp hoạt động và tín hiệu sức khỏe |
| Độ trễ tiếp nhận | Cần hiểu sai lệch đồng hồ và cách đo |
| Lỗi schema hoặc parser | Sự kiện có thể tồn tại nhưng không tra cứu đúng |
| Tỷ lệ liên kết yêu cầu với phiên | Phản ánh phần có đủ khóa liên kết theo phạm vi |
| Khoảng trống và sự kiện xung đột ID | Cần điều tra nguyên nhân trước khi kết luận |
| Sự kiện nhạy cảm chưa được xử lý | Khoảng cách giữa quan sát và hành động |

Một dashboard có màu xanh không thay thế việc kiểm tra rằng dữ liệu đúng và có ý nghĩa.

## 17. Phân công trách nhiệm

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| Chủ sở hữu chương trình PAM | Xác định phạm vi và mục tiêu bằng chứng |
| Đội vận hành PAM | Cấu hình nguồn, kiểm tra sự kiện và xử lý lỗi tại thành phần được giao |
| Đội quản lý đường thu thập | Vận hành truyền, lưu, quyền truy cập và trạng thái pipeline |
| Đội bảo mật hoặc ứng phó | Phát hiện, phân tích, điều phối xử lý theo thẩm quyền |
| Chủ sở hữu dịch vụ | Giải thích nhu cầu, phụ thuộc và tác động tại đích |
| Người xem xét độc lập | Đánh giá bằng chứng với mức độc lập phù hợp |

Có log không có nghĩa đã có người theo dõi. Có cảnh báo không có nghĩa đã có người chịu trách nhiệm xử lý.

Cũng cần xác định ai có thể đổi policy audit, ai duyệt thay đổi quan trọng và ai xác nhận sau thay đổi rằng khả năng quan sát vẫn đáp ứng mục tiêu.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ ghi truy xuất thành công | Thiếu bằng chứng từ chối và thay đổi đường quyền | Bao phủ vòng đời và hoạt động quản trị |
| Dùng một trường “success” chung | Dễ nhầm cho phép với sử dụng thành công | Ghi giai đoạn và kết quả có ngữ nghĩa |
| Chỉ ghi tài khoản broker | Khó quy trách nhiệm cho người khởi tạo | Liên kết danh tính được xác minh |
| Tin tên người dùng do client gửi | Có thể quy kết sai | Giữ nguồn tin cậy và principal gọi thực tế |
| Ghi payload chứa bí mật | Tạo thêm kho credential | Loại dữ liệu bí mật ngay trong thiết kế sự kiện |
| Cho người dùng vault xóa log liên quan | Có thể mất dấu vết | Phân tách quyền và bảo vệ kho audit |
| Không theo dõi sức khỏe pipeline | Nhầm mất log với không có hoạt động | Có tín hiệu nguồn, lỗi và độ đầy đủ |
| Gộp theo tên hoặc ID thiếu scope | Liên kết sai hoặc loại nhầm sự kiện | Dùng định danh có ngữ cảnh nguồn |
| Xem hash chain là bảo đảm tuyệt đối | Bỏ qua nguồn, khóa và phần chưa ghi | Xác định đúng giả định và giới hạn |
| Chặn policy rồi coi đã containment xong | Credential hoặc phiên cũ vẫn có thể dùng | Xét đích, phiên và quyền phát sinh |

## 19. Bài tập tự đánh giá

Một vault ghi tất cả lần đọc thành công nhưng không ghi thay đổi policy. Log được lưu trên cùng máy mà quản trị viên vault có thể xóa. Các node gửi dữ liệu về nơi tập trung, nhưng không có cảnh báo khi một node ngừng gửi. Nhóm điều tra không thấy truy xuất credential trong một khoảng thời gian rồi kết luận không có ai sử dụng tài khoản đích.

Hãy xác định:

1. Những khoảng trống nào làm kết luận chưa đủ cơ sở?
2. Vì sao không có log truy xuất chưa chứng minh không có sử dụng?
3. Cần bổ sung gì để truy vết việc mở rộng quyền?
4. Làm thế nào giảm nguy cơ xóa hoặc sửa bằng chứng?
5. Những dữ liệu nào cần liên kết để điều tra tại đích?

### Gợi ý phân tích

**Khoảng trống:** thiếu sự kiện policy, thiếu độc lập trong bảo vệ log và thiếu tín hiệu mất nguồn. Không biết tập dữ liệu có đầy đủ hay không.

**Sử dụng:** credential có thể đã được lấy trước đó, còn bản sao hoặc phiên đang hoạt động, hoặc tồn tại đường truy cập ngoài vault.

**Thay quyền:** cần ghi danh tính, quyết định, nội dung thay đổi thích hợp hoặc tham chiếu phiên bản trước/sau, nguồn thẩm quyền và kết quả.

**Bảo vệ:** xem quyền xóa, nơi lưu, pipeline, khóa, cơ chế toàn vẹn và đường quản trị, không chỉ bật một tùy chọn trên giao diện.

**Liên kết:** cần danh tính ban đầu, lần cấp credential, phiên bản, phiên broker nếu có, tài khoản đích và audit hoạt động ở đích, kèm chất lượng thời gian và giới hạn dữ liệu.

## 20. Những điểm cần ghi nhớ

- Vault audit trail phải giải thích danh tính, tài nguyên, quyết định, hành động và kết quả trong vòng đời credential.
- Cho phép, gửi credential, đăng nhập và thực hiện tác vụ là những sự kiện khác nhau.
- Không ghi giá trị bí mật; metadata và bản ghi phiên cũng cần được bảo vệ.
- Tính toàn vẹn cần đi cùng độ đầy đủ, nguồn tin cậy, thời gian và khả năng liên kết.
- Không có sự kiện chưa đủ chứng minh không có hoạt động khi chưa xác nhận sức khỏe và phạm vi thu thập.
- Hết hạn hoặc thu hồi trong vault cần được liên kết với hiệu lực credential và phiên tại đích.
- Bằng chứng có ích phải dẫn đến người chịu trách nhiệm, quyết định xử lý và kết luận đúng trong giới hạn dữ liệu.

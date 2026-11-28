# Privilege elevation count: đếm và diễn giải các lượt nâng quyền trong IAM

## 1. Chỉ số này trả lời câu hỏi nào?

Privilege elevation count là số lượt nâng quyền được ghi nhận trong một phạm vi và khoảng thời gian xác định. Trong IAM, chỉ số này giúp nhóm vận hành biết quyền nhạy cảm đang được kích hoạt với tần suất nào, qua cơ chế nào và trong hoàn cảnh nào.

Ví dụ, kỹ sư thường chỉ được xem trạng thái cơ sở dữ liệu. Khi xử lý sự cố, người đó yêu cầu quyền quản trị trong 30 phút. Nếu hệ thống thực sự cấp quyền theo yêu cầu, đây có thể là một lượt nâng quyền thành công theo định nghĩa của tổ chức.

Tên chỉ số chưa đủ để hiểu con số. “Có 20 lượt nâng quyền” cần đi kèm các câu trả lời:

- Đếm yêu cầu gửi lên, phê duyệt hay quyền đã được cấp?
- Đếm người dùng, phiên, lần kích hoạt vai trò hay từng tài nguyên?
- Đang quan sát môi trường production hay môi trường thử nghiệm?
- Có bao gồm workload, quyền khẩn cấp và gia hạn không?
- Khoảng thời gian dựa trên lúc yêu cầu hay lúc cấp quyền?

Bài học dùng tình huống công ty An Bình vận hành hệ thống hợp đồng. Kỹ sư trực có thể xin quyền xử lý sự cố; workload triển khai có thể nhận vai trò mạnh hơn trong một tác vụ được kiểm soát. Nhóm IAM muốn theo dõi hoạt động này mà vẫn giữ nguyên nguyên tắc ít quyền nhất.

## 2. Xác định thế nào là một lượt nâng quyền

Nâng quyền xảy ra khi một chủ thể nhận thêm khả năng truy cập so với trạng thái hoặc ngữ cảnh ban đầu. Phần tăng thêm có thể nằm ở loại hành động, phạm vi tài nguyên, mức nhạy cảm hoặc điều kiện sử dụng.

Một số tình huống thường gặp:

| Tình huống | Thay đổi cần quan sát |
| --- | --- |
| Kích hoạt vai trò quản trị tạm thời | Từ đủ điều kiện nhận vai trò sang có quyền hoạt động |
| Cấp phiên đặc quyền qua hệ thống quản lý truy cập | Tạo một phiên có khả năng thực hiện thao tác nhạy cảm |
| Nhận vai trò cho workload triển khai | Workload nhận khả năng vượt quyền vận hành thông thường |
| Sử dụng cơ chế truy cập khẩn cấp | Kích hoạt quyền theo quy trình đặc biệt khi cần xử lý sự cố |
| Mở rộng phạm vi từ một tài nguyên sang nhiều tài nguyên | Tăng phạm vi tác động dù tên vai trò có thể không đổi |
| Gán quyền đặc quyền lâu dài | Tăng quyền bền vững, cần được nhận diện riêng với kích hoạt tạm thời |

Không phải mọi lần đổi vai trò hoặc nhận token đều là nâng quyền. Một vai trò mới có thể tương đương, hẹp hơn hoặc phục vụ phạm vi độc lập. Cần xét quyền thực tế và mục đích của luồng, thay vì chỉ kiểm tra tên có chứa “admin” hay không.

Việc gia hạn quyền hiện có cũng cần quy ước riêng. Gia hạn không nhất thiết tạo một lần chuyển từ không có quyền sang có quyền, nhưng làm thời gian tiếp xúc với đặc quyền dài hơn. Vì vậy, nên quan sát gia hạn như một loại sự kiện riêng hoặc công bố rõ nếu nó được gộp vào số lượt nâng quyền.

Những quyền được cấp sẵn và sử dụng thường xuyên có thể không phát sinh sự kiện nâng quyền mới. Privilege elevation count không thay thế việc kiểm kê tài khoản và quyền đặc quyền thường trực.

## 3. Tách yêu cầu, phê duyệt, kích hoạt và kết thúc

Một lượt yêu cầu có thể đi qua nhiều trạng thái:

~~~mermaid
flowchart TD
    A[Yêu cầu nâng quyền] --> B{Quyết định chính sách và phê duyệt}
    B -->|Không chấp nhận| C[Từ chối yêu cầu]
    B -->|Chấp nhận| D[Thực hiện cấp hoặc kích hoạt quyền]
    D -->|Không thành công| E[Lỗi cấp quyền]
    D -->|Đã xác nhận cấp quyền| F[Quyền đang hoạt động]
    F --> G[Hết hạn hoặc thu hồi]
~~~

Sơ đồ minh họa một luồng; hệ thống thực tế có thể thêm các trạng thái chờ, hủy hoặc hết hạn yêu cầu.

Những con số sau có ý nghĩa khác nhau:

| Chỉ số | Mốc ghi nhận | Câu hỏi được trả lời |
| --- | --- | --- |
| Số yêu cầu nâng quyền | Tiếp nhận yêu cầu hợp lệ theo định nghĩa | Nhu cầu nâng quyền là bao nhiêu? |
| Số yêu cầu được phê duyệt | Quyết định chấp nhận được ghi nhận | Bao nhiêu yêu cầu được phép tiếp tục? |
| Số lần kích hoạt thành công | Thành phần có thẩm quyền xác nhận quyền đã được cấp | Bao nhiêu lượt thực sự nhận đặc quyền tại mốc này? |
| Số lần cấp quyền thất bại | Thao tác cấp quyền kết thúc bằng lỗi | Luồng cấp quyền gặp vấn đề ở đâu? |
| Số lần kết thúc hoặc thu hồi | Có bằng chứng quyền kết thúc theo mốc đã định | Vòng đời quyền đã kết thúc như thế nào? |

Một yêu cầu được phê duyệt nhưng bộ kết nối không cấp được quyền không phải là một lần kích hoạt thành công.

Tương tự, đăng nhập thành công hoặc hoàn tất MFA chỉ chứng minh một mốc xác thực. Nó chưa chứng minh quyền đặc quyền đã được cấp, và cũng chưa chứng minh một thao tác trên tài nguyên đã được cho phép.

Nếu quyền đã được ghi vào hệ thống nguồn nhưng chưa truyền tới tài nguyên đích, cần đặt tên chỉ số theo đúng điểm quan sát. Có thể đo riêng “đã cấp tại hệ thống nguồn” và “đã xác nhận có hiệu lực tại đích”. Không tuyên bố thành công đầu cuối từ một sự kiện trung gian.

## 4. Viết hợp đồng đếm trước khi dựng dashboard

Một định nghĩa minh họa cho An Bình:

> Một lượt nâng quyền thành công được tính khi dịch vụ cấp quyền xác nhận một lần kích hoạt đặc quyền mới đã hoàn tất cho một chủ thể, một phạm vi và một khoảng hiệu lực xác định. Retry không tạo thêm lần kích hoạt thì không làm tăng số lượt.

Định nghĩa này cần được cụ thể hóa bằng các lựa chọn:

| Thành phần | Ví dụ quy ước |
| --- | --- |
| Chủ thể nhận quyền | Người dùng hoặc workload, tách nhóm khi báo cáo |
| Đơn vị đếm | Một lần kích hoạt có định danh nội bộ ổn định |
| Điểm ghi nhận | Dịch vụ có thẩm quyền xác nhận cấp quyền |
| Mốc thời gian | Thời điểm xác nhận kích hoạt |
| Phạm vi | Production, nhóm tài nguyên và cơ chế cấp quyền |
| Kết quả | Thành công, bị từ chối hoặc lỗi kỹ thuật được tách riêng |
| Gia hạn | Có counter riêng, không mặc định cộng vào kích hoạt mới |
| Retry | Cùng lần kích hoạt chỉ tính một lần |
| Quyền khẩn cấp | Được phân loại để xem riêng |
| Nguồn sự kiện | Xác định rõ hệ thống nào phát sự kiện chính thức |

Nếu một lần kích hoạt mở quyền trên năm tài nguyên, tổ chức có thể đếm một lượt kích hoạt và đo thêm số tài nguyên được tác động. Nếu thiết kế lại đếm từng lần cấp trên từng tài nguyên, kết quả sẽ khác. Cả hai cách đều có thể phục vụ nhu cầu cụ thể, nhưng không được cộng lẫn như một đại lượng.

Khi thay đổi hợp đồng đếm, cần ghi nhận thời điểm và phiên bản định nghĩa. Một đỉnh trên biểu đồ do đổi cách đo không nên bị hiểu thành thay đổi hành vi sử dụng quyền.

## 5. Công thức count, rate và tỷ lệ kết quả

Với các sự kiện kích hoạt thành công đã được loại trùng:

~~~text
Privilege elevation count trong [t0, t1)
    = số lượt kích hoạt thành công
      có thời điểm ghi nhận >= t0 và < t1
      thỏa các bộ lọc phạm vi
~~~

Cửa sổ nửa mở giúp xác định rõ sự kiện ở ranh giới thuộc cửa sổ nào.

Nếu trong 15 phút có 41 lần kích hoạt thành công:

~~~text
Count = 41 lượt

Rate trung bình = 41 / 15
                ≈ 2,73 lượt/phút
~~~

Count và rate không phải phần trăm. Muốn tính tỷ lệ thành công, phải xác định mẫu số:

~~~text
Tỷ lệ cấp quyền thành công
    = số thao tác cấp quyền thành công
      / số thao tác cấp quyền đã kết thúc với kết quả xác định
~~~

Mẫu số này khác tổng số yêu cầu gửi lên. Yêu cầu có thể đang chờ phê duyệt, bị hủy trước bước cấp quyền hoặc bị từ chối bởi chính sách.

Nếu muốn tính “bao nhiêu yêu cầu cuối cùng dẫn đến cấp quyền”, cần liên kết các yêu cầu trong cùng một nhóm theo thời điểm bắt đầu và theo dõi chúng đến kết quả phù hợp. Không lấy số kích hoạt trong một giờ chia tùy tiện cho số yêu cầu đến trong cùng giờ, vì các lượt đó có thể thuộc những nhóm yêu cầu khác nhau.

Khi không có lượt nào đủ điều kiện làm mẫu số, tỷ lệ là không xác định theo phép tính thông thường. Dashboard cần hiển thị trạng thái không có mẫu hoặc không áp dụng, thay vì tự biến thành 100% thành công.

Với counter tích lũy, lấy số tăng trong cửa sổ và xử lý việc tiến trình khởi động lại. Không lấy tổng counter từ lúc khởi động rồi gọi đó là số lượt của 15 phút gần nhất.

## 6. Những trường hợp dễ đếm sai

### Retry và sự kiện được gửi lại

Client có thể gửi lại yêu cầu vì mất phản hồi. Hệ thống thu thập cũng có thể nhận cùng một sự kiện nhiều lần.

Nếu quyền chỉ được cấp một lần, không nên tính thành nhiều lượt chỉ vì có nhiều bản tin. Cần phân biệt định danh bản tin với định danh lần kích hoạt. Hai bản tin khác nhau vẫn có thể mô tả cùng một lần cấp quyền.

### Một luồng đi qua nhiều hệ thống

Ví dụ, một lần kích hoạt vai trò tại nhà cung cấp danh tính dẫn đến việc phát thông tin xác thực tạm thời và mở phiên quản trị tại tài nguyên.

Đây có thể là ba mốc quan sát của cùng một hành trình. Cộng toàn bộ chúng thành ba lượt nâng quyền đầu cuối sẽ làm sai ý nghĩa nếu đơn vị mong muốn là một hành trình kích hoạt.

Có thể giữ counter cho từng thành phần, nhưng cần định danh mốc và quy tắc liên kết. Dashboard tổng không cộng các mốc khác loại.

### Quyền được cấp cho nhóm

Một thay đổi membership có thể ảnh hưởng đến nhiều người. “Một thay đổi cấp quyền” và “số chủ thể nhận thêm quyền” là hai đại lượng khác nhau.

Không coi một sự kiện thay đổi nhóm là đủ để kết luận chỉ một người được tăng quyền. Cần theo dõi thêm phạm vi ảnh hưởng và quá trình truyền thay đổi.

### Gia hạn hoặc tái kích hoạt

Gia hạn thời gian, thay đổi phạm vi của một lần đang hoạt động và kích hoạt lại sau khi hết hạn cần được phân loại rõ.

Việc mở rộng phạm vi có thể làm tăng rủi ro dù số phiên không đổi. Nếu chỉ đếm phiên mới, dashboard có thể bỏ sót thay đổi này.

### Truy cập đặc quyền ngoài luồng quản lý

Một tài khoản quản trị thường trực hoặc một đường cấp quyền trực tiếp có thể hoạt động mà không tạo sự kiện tại cổng xin quyền.

Counter ở cổng chỉ phản ánh các luồng đi qua cổng đó. Nó không chứng minh toàn bộ hoạt động đặc quyền của tổ chức đã được quan sát.

## 7. Chọn chiều phân tích có giá trị

Tổng số lượt toàn hệ thống hữu ích để nhìn xu hướng, nhưng thường chưa đủ để tìm nguyên nhân.

Các chiều phân tích thường có ích gồm:

- Môi trường: production, staging hoặc development.
- Loại chủ thể: người dùng và workload.
- Nhóm đặc quyền hoặc mức nhạy cảm được chuẩn hóa.
- Cơ chế cấp quyền: tạm thời, lâu dài hoặc khẩn cấp.
- Giai đoạn và kết quả của luồng.
- Hệ thống cấp quyền hoặc nhóm tài nguyên đích.
- Nhóm lý do theo danh mục kiểm soát.

Nên bắt đầu từ số chiều nhỏ, ổn định và phù hợp với câu hỏi vận hành. Mỗi tổ hợp giá trị nhãn có thể tạo một chuỗi metrics riêng; tổ hợp quá nhiều chiều sẽ làm hệ thống thu thập và truy vấn khó vận hành.

Không đưa email, tên người dùng, mã yêu cầu, session ID, ticket ID hoặc chuỗi lý do tự do vào nhãn metrics. Những giá trị này thường có số lượng lớn, có thể chứa dữ liệu cá nhân và khó kiểm soát vòng đời.

Dữ liệu nhận diện cần thiết cho điều tra nên nằm trong audit log được kiểm soát truy cập, với quy tắc bảo vệ và lưu giữ phù hợp. Metrics giúp nhận ra hiện tượng; audit log giúp đối chiếu từng lượt.

Một nhãn “ngoài giờ” cũng cần định nghĩa theo ca trực, múi giờ và quy trình công việc. Truy cập ban đêm của đội trực không có cùng ý nghĩa với truy cập không có nhiệm vụ hỗ trợ.

## 8. Thiết kế sự kiện có thể đối chiếu

Một bản ghi minh họa cho lần kích hoạt thành công:

~~~json
{
  "event_type": "privilege_elevation.activated",
  "event_id": "evt-example-104",
  "elevation_id": "elv-example-27",
  "occurred_at": "2026-01-15T03:20:00Z",
  "actor_ref": "actor-example-9",
  "subject_ref": "subject-example-12",
  "subject_type": "human",
  "environment": "production",
  "privilege_class": "database_maintenance",
  "mechanism": "temporary",
  "outcome": "succeeded",
  "reason_code": "incident_response",
  "expires_at": "2026-01-15T03:50:00Z",
  "source": "privilege_broker"
}
~~~

Đây là schema minh họa, không phải yêu cầu của một sản phẩm cụ thể. Các mã tham chiếu trong ví dụ là dữ liệu giả và không có khả năng cấp quyền.

Một số điểm cần chú ý:

| Trường hoặc khái niệm | Mục đích |
| --- | --- |
| Định danh sự kiện | Hỗ trợ nhận biết một bản tin bị gửi lại |
| Định danh lần kích hoạt | Liên kết yêu cầu, cấp quyền và kết thúc |
| Actor | Bên khởi tạo hành động tại mốc đang ghi nhận |
| Subject | Chủ thể thực sự nhận quyền |
| Thời điểm xảy ra | Xác định thời gian nghiệp vụ của sự kiện |
| Thời điểm tiếp nhận | Đo độ trễ thu thập và hỗ trợ xử lý sự kiện đến muộn |
| Phạm vi và loại quyền | Hiểu quyền đã tăng ở đâu và mạnh đến mức nào |
| Hạn hiệu lực | Đối chiếu quyền tạm thời và lịch kết thúc |

Actor và subject có thể khác nhau: một dịch vụ điều phối có thể thực hiện cấp quyền cho người dùng đã được phê duyệt. Nếu cần biết ai phê duyệt, ghi nhận liên kết tới sự kiện phê duyệt hoặc trường phù hợp; không đồng nhất dịch vụ thực thi với người ra quyết định.

Thời điểm hết hạn dự kiến không phải bằng chứng việc thu hồi đã có hiệu lực ở mọi nơi. Cần quan sát trạng thái thực tế tại các điểm cần thiết.

Không ghi mật khẩu, mã MFA, access token, refresh token, private key hoặc credential đặc quyền vào sự kiện. Một mã liên kết phục vụ quan sát cũng không được là bí mật có thể dùng để chiếm phiên.

## 9. Instrumentation và chất lượng dữ liệu

Có thể đo trực tiếp tại thành phần cấp quyền hoặc dựng metrics từ luồng sự kiện. Mỗi cách cần có quy tắc bảo đảm độ tin cậy.

Nếu tăng counter trước khi biết kết quả cấp quyền, thao tác thất bại có thể bị tính là thành công. Nếu cấp quyền xong nhưng tiến trình chết trước lúc tăng counter, chỉ số có thể bị thiếu.

Một thiết kế ghi nhận kết quả bền vững cùng thay đổi trạng thái, rồi chuyển sự kiện tới hệ thống quan sát, có thể giúp giảm khoảng trống này. Tuy nhiên, vẫn cần xử lý sự kiện trùng, đến muộn, mất kết nối và việc phát lại dữ liệu.

Không đồng thời cộng counter trực tiếp tại nguồn và counter dựng từ cùng các audit event vào một tổng, nếu cả hai cùng đại diện cho một lượt kích hoạt.

Ví dụ tên metrics minh họa:

~~~text
iam_privilege_elevation_events_total{
    stage="activation",
    outcome="succeeded",
    environment="production",
    subject_type="human",
    mechanism="temporary"
}
~~~

Tên và nhãn cần có tài liệu định nghĩa. Nhãn stage giúp phân biệt cấp quyền với phê duyệt; nhãn outcome giúp phân biệt kết quả, nhưng bản thân việc đặt nhãn không bảo đảm logic tăng counter đúng.

Khi metrics được suy ra từ sự kiện, cần quyết định dùng thời điểm xảy ra hay thời điểm tiếp nhận cho cửa sổ báo cáo. Một bản tin đến muộn có thể làm báo cáo lịch sử được cập nhật hoặc xuất hiện trong cửa sổ tiếp nhận hiện tại. Người đọc phải biết cách hệ thống xử lý.

Các tín hiệu chất lượng dữ liệu nên đi kèm:

- Nguồn nào đang gửi hoặc ngừng gửi dữ liệu.
- Độ trễ sự kiện và độ trễ xử lý hàng đợi.
- Số bản tin lỗi schema, bị loại trùng hoặc không xử lý được.
- Thời điểm cập nhật gần nhất.
- Phạm vi luồng cấp quyền đã được tích hợp.

Không lấy “không có dữ liệu” làm bằng chứng “không có nâng quyền”.

## 10. Đọc xu hướng mà không suy diễn quá mức

| Quan sát | Khả năng cần kiểm tra |
| --- | --- |
| Lượt nâng quyền tăng vào lịch bảo trì | Nhu cầu hợp lệ tăng hoặc quy trình thay đổi |
| Yêu cầu tăng nhưng kích hoạt không tăng | Chờ phê duyệt, bị từ chối hoặc lỗi cấp quyền |
| Kích hoạt tăng mạnh ở một workload | Tăng số job, retry tạo phiên mới hoặc thay đổi vai trò |
| Quyền khẩn cấp xuất hiện ngoài đợt diễn tập | Sự cố thực tế hoặc sử dụng không đúng quy trình |
| Count ổn định nhưng thời lượng tăng | Quyền tồn tại lâu hơn hoặc quy trình kết thúc gặp vấn đề |
| Count giảm sau triển khai | Ít nhu cầu, thay đổi cơ chế cấp quyền hoặc lỗi telemetry |
| Một chủ thể có nhiều lần kích hoạt ngắn | Quy trình khó dùng, phiên hết hạn sớm hoặc hành vi cần điều tra |
| Kích hoạt hợp lệ nhưng thao tác tài nguyên bị từ chối | Quyền chưa có hiệu lực tại đích hoặc phạm vi không phù hợp |

Count cao không tự chứng minh có tấn công. Một tổ chức chuyển từ quyền quản trị thường trực sang quyền theo nhu cầu có thể ghi nhận nhiều lượt kích hoạt hơn, đồng thời giảm thời gian tồn tại của đặc quyền.

Count thấp cũng không tự chứng minh an toàn. Tài khoản đặc quyền lâu dài có thể thực hiện nhiều thao tác nhạy cảm mà không cần nâng quyền mới.

Lượt nâng quyền hợp lệ theo quy trình vẫn có thể được sử dụng sai mục đích. Cần đối chiếu với hành động trên tài nguyên, phê duyệt, thời gian, phạm vi và ngữ cảnh sự cố.

## 11. Kết hợp với thời lượng, phạm vi và thu hồi

Để hiểu mức tiếp xúc với đặc quyền, nên xem thêm:

| Tín hiệu bổ sung | Điều mà count chưa thể hiện |
| --- | --- |
| Số lần kích hoạt đang hoạt động | Có bao nhiêu lượt quyền chưa kết thúc |
| Thời lượng của một lần nâng quyền | Quyền tồn tại lâu đến đâu |
| Phạm vi tài nguyên và nhóm quyền | Quyền có thể tác động tới đâu |
| Số lần gia hạn hoặc mở rộng phạm vi | Quyền đang kéo dài hoặc trở nên mạnh hơn thế nào |
| Độ trễ thu hồi | Khoảng cách từ yêu cầu thu hồi tới mốc xác nhận có hiệu lực |
| Quyền đặc quyền thường trực | Phần đặc quyền không đi qua cơ chế kích hoạt |
| Thao tác nhạy cảm trong phiên | Quyền đã được sử dụng để làm gì |

“Số lần đang hoạt động” là một giá trị trạng thái, khác counter tích lũy. Một chủ thể cũng có thể có nhiều lần kích hoạt đồng thời, nên số lần đang hoạt động không nhất thiết bằng số người đang có quyền.

Có thể ước lượng tổng thời gian đặc quyền bằng cách cộng phần thời gian mỗi lượt có hiệu lực nằm trong cửa sổ quan sát. Kết quả này có đơn vị như lượt-phút, không phải số phút theo đồng hồ của hệ thống. Hai lượt cùng tồn tại trong 10 phút đóng góp 20 lượt-phút.

Phép cộng đó vẫn không đánh giá đầy đủ rủi ro: quyền xem log và quyền thay đổi chính sách bảo mật có mức tác động khác nhau. Không gán trọng số tùy ý rồi coi kết quả là xác suất xảy ra sự cố.

Việc quyền hết hạn tại hệ thống nguồn cũng cần được phân biệt với thời điểm các phiên, cache hoặc thông tin xác thực liên quan không còn được chấp nhận tại đích. Chọn mốc đo phù hợp với cơ chế thực tế.

## 12. Ví dụ vận hành tại An Bình

Trong một đợt bảo trì 15 phút, nhóm IAM ghi nhận một tập 60 yêu cầu đã được theo dõi đến kết quả cuối của bước cấp quyền:

| Kết quả | Số lượt |
| --- | ---: |
| Yêu cầu được tiếp nhận | 60 |
| Yêu cầu bị từ chối | 15 |
| Yêu cầu được chấp nhận để cấp quyền | 45 |
| Cấp quyền thành công | 41 |
| Cấp quyền kết thúc bằng lỗi | 4 |

Trong ví dụ này, mỗi yêu cầu được chấp nhận dẫn đến đúng một thao tác cấp quyền và cả 45 thao tác đã kết thúc. Vì vậy:

~~~text
Privilege elevation count = 41

Tỷ lệ thành công của bước cấp quyền = 41 / 45
                                  ≈ 91,1%

Tỷ lệ yêu cầu dẫn đến cấp quyền thành công = 41 / 60
                                         ≈ 68,3%
~~~

Hai tỷ lệ dùng mẫu số khác nhau và trả lời hai câu hỏi khác nhau. Không gọi 15 yêu cầu bị từ chối bởi chính sách là lỗi hạ tầng.

Trong 41 lượt thành công, 37 lượt thuộc người dùng và 4 lượt thuộc workload. Hai lượt của người dùng dùng cơ chế khẩn cấp. Nhóm không cộng thêm hai lượt khẩn cấp vào tổng 41 vì chúng là một tập con, không phải hoạt động độc lập.

Khi count tăng gấp đôi so với ngày thường, nhóm đối chiếu lịch bảo trì và thấy phần lớn tăng trưởng đến từ công việc đã lên kế hoạch. Tuy nhiên, hai lượt khẩn cấp vẫn được xem riêng để xác nhận lý do, người chịu trách nhiệm và thời điểm kết thúc.

Ở một đợt khác, count không tăng nhưng các lần nâng quyền tồn tại lâu hơn dự kiến. Nhóm kiểm tra luồng thu hồi thay vì kết luận mọi thứ ổn từ biểu đồ số lượt.

## 13. Cảnh báo cần gắn với hành động

Không có một ngưỡng số lượt phù hợp cho mọi tổ chức. Ngưỡng cần xét quy mô, cơ chế cấp quyền, lịch bảo trì, workload và mức nhạy cảm.

Một cảnh báo hữu ích nên nêu rõ chỉ số, phạm vi, cửa sổ thời gian, chất lượng dữ liệu, lý do cần chú ý và nơi đối chiếu các lượt liên quan.

Các hướng cảnh báo minh họa:

- Kích hoạt quyền rất nhạy cảm hoặc quyền khẩn cấp trong phạm vi cần theo dõi sát.
- Số lượt tăng bất thường so với nền cùng loại công việc.
- Lỗi cấp quyền tăng sau một thay đổi triển khai.
- Quyền còn hoạt động vượt mốc dự kiến.
- Có cấp quyền tại tài nguyên nhưng không tìm thấy luồng quản lý tương ứng.
- Nguồn audit quan trọng ngừng gửi hoặc gửi dữ liệu quá trễ.

Một đợt tăng yêu cầu bị từ chối có thể cần điều tra khác với một đợt tăng kích hoạt thành công. Cảnh báo cần giữ sự khác biệt này.

Không tự động khóa hàng loạt tài khoản chỉ từ một con số tổng. Tương tự, không nới điều kiện phê duyệt hoặc kéo dài quyền chỉ để giảm số cảnh báo. Phản ứng cần dựa trên bằng chứng và quy trình tương ứng với loại sự kiện.

## 14. Những tình huống cần kiểm tra khi triển khai phép đo

| Tình huống | Kết quả quan sát mong muốn |
| --- | --- |
| Phê duyệt thành công nhưng cấp quyền lỗi | Không tăng count kích hoạt thành công |
| Cùng một lần cấp quyền bị retry | Count phù hợp với số lần kích hoạt thực tế |
| Một audit event được gửi lại | Không làm tăng số lượt nghiệp vụ |
| Một luồng qua nhiều thành phần | Không cộng trùng các mốc vào tổng đầu cuối |
| Gia hạn quyền hiện có | Được phân loại theo hợp đồng đếm |
| Quyền tạm thời hết hạn | Quan sát được kết thúc theo mốc đã chọn |
| Chủ thể có hai kích hoạt đồng thời | Không nhầm số lượt với số chủ thể |
| Một lần cấp ảnh hưởng nhiều tài nguyên | Giữ rõ đơn vị kích hoạt và phạm vi ảnh hưởng |
| Counter reset sau khởi động lại | Không tạo mức tăng giả hoặc số âm |
| Sự kiện đến muộn hoặc được phát lại | Cửa sổ báo cáo xử lý theo quy ước công bố |
| Không có lượt mới | Phân biệt được 0 với mất dữ liệu |
| Có thay đổi quyền ngoài cổng quản lý | Thấy giới hạn bao phủ hoặc có nguồn đối chiếu |
| Kiểm tra metrics và audit log | Không xuất hiện credential hoặc bí mật phiên |

Privilege elevation count có giá trị khi được gắn với một mốc cấp quyền rõ ràng, đơn vị đếm ổn định và khả năng đối chiếu từng sự kiện. Kết hợp nó với thời lượng, phạm vi, thu hồi và việc sử dụng quyền giúp nhóm IAM hiểu được cả nhu cầu vận hành lẫn những dấu hiệu cần điều tra.

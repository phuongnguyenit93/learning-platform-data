# Đã kiểm thử failover

Một cụm PAM có hai node, một địa chỉ truy cập dự phòng và dashboard báo “healthy” chưa đủ để xác nhận sẵn sàng production. Câu hỏi nghiệm thu là: **khi một thành phần gặp lỗi, người đúng quyền còn làm được công việc cần thiết, người không đủ quyền vẫn bị chặn, và tổ chức vẫn giải thích được toàn bộ diễn biến hay không?**

Với Privileged Access Management, failover tác động đồng thời tới tính sẵn sàng và ranh giới đặc quyền. Một lần chuyển đổi có thể làm endpoint phục vụ trở lại nhưng để lại credential không đồng bộ, phiên quản trị mất ghi hình hoặc quyết định cấp quyền dựa trên dữ liệu cũ. Vì vậy, mục “Đã kiểm thử failover” phải được xác nhận bằng kết quả kiểm thử đầu cuối và bằng chứng có thể đối chiếu, không chỉ bằng trạng thái của cụm.

## 1. Mục tiêu và phạm vi của mục checklist

Sau bài học này, người triển khai cần biết cách:

- Xác định những luồng truy cập đặc quyền phải tiếp tục hoạt động hoặc phải dừng an toàn khi xảy ra lỗi.
- Chọn tình huống failover phù hợp với kiến trúc và phạm vi production thực tế.
- Đặt tiêu chí đạt cho thời gian khôi phục, dữ liệu, quyền truy cập, credential, phiên và audit.
- Thu thập bằng chứng để đưa ra quyết định go/no-go.
- Kiểm tra failback và giới hạn hiệu lực của kết quả sau thay đổi.

Trong bài này, PAM bao gồm các năng lực như quản lý secret trong vault, cấp quyền JIT/JEA, phê duyệt truy cập, trung chuyển phiên, rotation credential và lưu bằng chứng. Không phải sản phẩm nào cũng có cùng thành phần hoặc cơ chế HA. Nhóm triển khai phải ánh xạ những yêu cầu bên dưới vào kiến trúc đã được phê duyệt của mình.

Đối tượng kiểm thử là **dịch vụ truy cập đặc quyền hoàn chỉnh**. Một bài test chỉ chứng minh load balancer chuyển traffic chưa thể đại diện cho việc kiểm thử vault, bộ ghi phiên hoặc rotation.

## 2. Phân biệt failover, backup, DR và failback

| Khái niệm | Điều cần chứng minh | Điều không tự suy ra |
|---|---|---|
| High availability | Kiến trúc có khả năng duy trì dịch vụ trong những lỗi đã thiết kế để chịu được | Mọi cơ chế chuyển đổi đều đã được kiểm thử |
| Failover | Dịch vụ chuyển sang thành phần hoặc đường phục vụ khác khi có lỗi hay khi được chủ động chuyển đổi | Dữ liệu, quyền và audit đều còn đúng nếu chưa kiểm tra |
| Backup/restore | Dữ liệu có thể phục hồi từ bản sao với quy trình xác định | Dịch vụ tự chuyển đổi trong thời gian ngắn |
| Disaster recovery | Khôi phục dịch vụ trong phạm vi thảm họa được chọn, có thể gồm cả site và phụ thuộc | Bài test mất một node đã bao phủ mất cả site |
| Failback | Trở về trạng thái phục vụ mong muốn sau failover, có kiểm soát đồng bộ và quyền ghi | Chỉ cần bật lại node cũ là an toàn |

Một lần switchover có kế hoạch giúp xác minh đường chuyển đổi và runbook. Tuy nhiên, nó không thay thế hoàn toàn bài test lỗi bất ngờ: thành phần đang phục vụ có thể không kịp bàn giao trạng thái khi mất điện hoặc mất mạng.

Tương tự, restart thành công một node chỉ chứng minh được tình huống đã thực hiện. Biên bản phải ghi rõ điều kiện lỗi, cách tạo lỗi, loại chuyển đổi tự động hay thủ công và các giới hạn của kết quả.

## 3. Xác định luồng nghiệp vụ cần được bảo vệ

Bắt đầu từ luồng người dùng hoặc workload, sau đó mới ánh xạ xuống thành phần hạ tầng.

Ví dụ một luồng quản trị qua PAM:

~~~text
Người quản trị / workload
        |
        v
Xác thực + chính sách + phê duyệt
        |
        v
Vault / cấp quyền tạm thời
        |
        v
Broker / connector --------------> Hệ thống đích
        |
        v
Ghi phiên / audit / chuyển sự kiện
~~~

Luồng này có thể phụ thuộc vào DNS, load balancer, IdP, MFA, dịch vụ thời gian, cơ sở dữ liệu, dịch vụ khóa, storage, mạng và hệ thống nhận log. Việc một phụ thuộc nằm ngoài sản phẩm PAM không làm nó biến mất khỏi rủi ro vận hành.

Lập danh mục tối thiểu:

| Luồng | Câu hỏi nghiệm thu |
|---|---|
| Đăng nhập quản trị | Người có quyền đăng nhập được qua endpoint thực tế và MFA vẫn được áp dụng? |
| Yêu cầu JIT/JEA | Quyền được cấp đúng phạm vi, đúng thời hạn, với phê duyệt hợp lệ? |
| Truy cập secret | Chỉ chủ thể được phép mới lấy hoặc sử dụng được đúng phiên bản secret? |
| Phiên SSH/RDP hoặc tương đương | Phiên mới và phiên đang mở có hành vi đúng như thiết kế? |
| Rotation | Secret trong vault và credential ở hệ thống đích có trạng thái nhất quán hoặc được đưa vào quy trình đối soát an toàn? |
| Thu hồi | Quyết định revoke được áp dụng trên đường phục vụ sau chuyển đổi? |
| Ghi phiên và audit | Bằng chứng còn đủ, liên kết được với yêu cầu, danh tính và kết quả? |
| Truy cập khẩn cấp | Người được ủy quyền có thực hiện được quy trình đã phê duyệt khi PAM chính không sẵn sàng? |

Không nhất thiết mọi luồng phải có cùng mục tiêu khôi phục. Chẳng hạn, tổ chức có thể chấp nhận báo cáo quản trị khôi phục chậm hơn truy cập ứng cứu production. Sự khác biệt phải được ghi trước bài test.

## 4. Đặt tiêu chí đạt trước khi tạo lỗi

Nếu chỉ đặt mục tiêu “dịch vụ hoạt động trở lại”, nhóm kiểm thử sẽ khó phân biệt một lần khôi phục an toàn với một lần mở rộng quyền ngoài ý muốn.

Tiêu chí cần gồm hai nhóm:

1. **Mục tiêu vận hành:** thời gian phục hồi, tỷ lệ giao dịch thành công, độ trễ, công suất và khả năng thực hiện runbook.
2. **Điều kiện an toàn:** không cấp quyền sai, không dùng credential chưa xác định trạng thái, không tạo hai chủ thể ghi không hợp lệ và không mất dấu truy cập ngoài chính sách.

Một số ví dụ để cụ thể hóa yêu cầu:

| Hạng mục | Ví dụ tiêu chí phải được nhóm triển khai định lượng |
|---|---|
| Truy cập mới | Khôi phục luồng quản trị ưu tiên trong RTO đã duyệt |
| JIT/JEA | Không cấp quyền rộng hơn hoặc thời hạn dài hơn chính sách |
| Thu hồi | Quyết định revoke có hiệu lực trong giới hạn đã duyệt, kể cả sau failover |
| Credential | Không cho phép thao tác dựa trên trạng thái không xác định; có đối soát khi giao dịch dở dang |
| Quyền ghi | Chỉ thành phần được kiến trúc cho phép có quyền ghi tại từng thời điểm |
| Phiên | Tiếp tục hoặc ngắt theo hợp đồng đã duyệt; khi ngắt phải có nhận diện và hướng dẫn kết nối lại |
| Audit | Đủ sự kiện theo phạm vi cam kết; phát hiện được khoảng trống và đối chiếu được sự kiện trùng |
| Công suất | Đường dự phòng xử lý được mức tải tối thiểu cần thiết |
| Khẩn cấp | Thực hiện được bởi đúng người, có ghi nhận và xử lý hậu kiểm |

Các con số trong kế hoạch phải xuất phát từ nhu cầu của hệ thống đích, rủi ro và khả năng kiến trúc. Không dùng một RTO hay TTL mẫu làm chuẩn chung cho mọi môi trường.

### Không dùng một RPO chung cho mọi dữ liệu

RPO thường mô tả mức mất dữ liệu chấp nhận được khi phục hồi. Nhưng dữ liệu PAM gồm nhiều loại có hậu quả khác nhau:

- Mất một bản ghi báo cáo có thể ảnh hưởng phân tích.
- Mất sự kiện audit có thể làm đứt khả năng quy trách nhiệm.
- Mất một cập nhật revoke có thể làm quyền đáng lẽ hết hiệu lực tiếp tục được sử dụng.
- Mất cập nhật secret có thể khiến vault không còn khớp với hệ thống đích.

Vì vậy, cần xác định hành vi phục hồi theo từng loại dữ liệu. Một kết quả replication đáp ứng RPO cơ sở dữ liệu chưa đủ để chứng minh yêu cầu thu hồi quyền và nhất quán credential.

## 5. Chốt hành vi khi hệ thống suy giảm

Trước bài test, ghi rõ các trường hợp dịch vụ phải từ chối, được tiếp tục hoặc được chuyển sang quy trình thay thế.

Ví dụ:

- Không xác minh được MFA: luồng đặc quyền thông thường phải xử lý theo chính sách xác thực đã duyệt.
- Không xác định được phê duyệt còn hiệu lực: không tự coi yêu cầu là đã được chấp thuận.
- Mất liên lạc với vault: không tự đưa mật khẩu dự phòng vào script hoặc cho phép người dùng đọc secret từ nơi khác.
- Không ghi phiên được: chặn phiên mới, ngắt phiên hay dùng bộ đệm được bảo vệ phải theo thiết kế và phạm vi chấp thuận.
- Mất SIEM nhưng audit local vẫn hoạt động: có thể tiếp tục trong giới hạn bộ đệm nếu chính sách cho phép và việc gửi bù được xác minh.

“Fail closed” không có nghĩa mọi lỗi đều phải ngắt mọi phiên theo cùng một cách. Điều quan trọng là hành vi được quyết định trước, phù hợp với rủi ro và không vô tình tạo đường vượt kiểm soát.

“Fail open” cũng không thể được xem là đạt chỉ vì giúp kết nối thành công. Nếu chính sách cho phép một chế độ suy giảm, phải có phạm vi, điều kiện kích hoạt, thời hạn, người chịu trách nhiệm, cảnh báo và bằng chứng. Nếu thiết kế yêu cầu chặn khi mất kiểm soát mà bài test cho thấy vẫn truy cập được, đó là lỗi nghiệm thu.

## 6. Lập ma trận lỗi theo phạm vi kiến trúc

Không có một danh sách lỗi duy nhất phù hợp cho mọi hệ thống. Ma trận sau là điểm bắt đầu để chọn các tình huống liên quan.

| Tình huống | Điều cần quan sát | Rủi ro PAM cần bắt được |
|---|---|---|
| Dừng node ứng dụng đang phục vụ | Đường chuyển traffic, thời gian lỗi, đăng nhập lại | Session hoặc policy cache không nhất quán |
| Mất broker/connector | Phiên đang chạy, phiên mới, đường tới hệ thống đích | Kết nối lại qua đường không được quản lý |
| Chuyển vai trò vault/database | Quyền đọc/ghi và trạng thái đồng bộ | Secret cũ, ghi trùng, cập nhật thất lạc |
| Mất một vùng lỗi đã thiết kế dự phòng | Dịch vụ và phụ thuộc thực sự còn hoạt động ở vùng còn lại | Nhiều node cùng phụ thuộc một storage hoặc đường mạng |
| Mất kết nối giữa các thành phần | Cách xác định bên được quyền phục vụ | Split brain hoặc sử dụng dữ liệu đã lỗi thời |
| IdP/MFA không sẵn sàng | Quyết định xác thực và quy trình khẩn cấp | Tắt MFA để làm cho bài test “đạt” |
| Dịch vụ khóa không truy cập được | Hành vi giải mã/cấp secret và khôi phục | Có node nhưng không thể sử dụng vault |
| Storage ghi phiên đầy hoặc không truy cập được | Cảnh báo, bộ đệm, chính sách phiên | Phiên chạy nhưng bằng chứng mất |
| SIEM không nhận sự kiện | Lưu tạm, gửi lại và đối chiếu | Mất log âm thầm hoặc tràn bộ đệm |
| Đường dự phòng chịu tải cao | Độ trễ, lỗi, tài nguyên và tác vụ nền | Phục hồi khi ít tải nhưng sụp khi có nhiều phiên |
| Thành phần cũ quay lại | Đồng bộ, quyền ghi, rotation và failback | Node cũ tự phục vụ dữ liệu không còn hợp lệ |

### Lỗi từng phần đáng được kiểm thử riêng

Một thành phần có thể vẫn trả health check nhưng không hoàn thành giao dịch nghiệp vụ. Ví dụ broker nhận kết nối nhưng không mở được phiên tới hệ thống đích, hoặc vault trả lời đọc nhưng không hoàn tất được rotation.

Nếu chỉ tắt cả node, bài test có thể bỏ qua loại lỗi này. Cần có probe nghiệp vụ để phát hiện đường phục vụ bị kẹt và xác minh cơ chế xử lý đúng thiết kế.

Mỗi bài test chỉ tạo lỗi trong phạm vi đã phê duyệt. Không mở rộng một tình huống mất node thành mất nhiều vùng hoặc mất đồng thời nhiều phụ thuộc chỉ để kiểm tra giới hạn.

## 7. Chuẩn bị an toàn và tính đại diện của môi trường

Môi trường thử nghiệm cần đại diện cho cấu hình production liên quan: topology, phiên bản, endpoint, cơ chế xác thực, đường mạng, policy, recording và trạng thái đồng bộ.

Tải nhỏ hơn production có thể được chấp nhận cho một số tình huống chức năng, nhưng kết quả đó không chứng minh công suất của đường dự phòng. Ghi rõ giới hạn thay vì dùng chung một nhãn “PASS”.

Trước khi bắt đầu:

- Chỉ định người điều phối, người tạo lỗi, người theo dõi PAM, người phụ trách hệ thống đích và người có quyền quyết định dừng.
- Chốt cửa sổ, phạm vi ảnh hưởng, điều kiện dừng và đường liên lạc.
- Chuẩn bị account, secret và hệ thống đích dành cho thử nghiệm với quyền tối thiểu.
- Kiểm tra trạng thái replication, sức khỏe hiện tại, dung lượng và điều kiện an toàn để chuyển đổi.
- Xác nhận có phương án phục hồi phù hợp; việc có backup không thay thế yêu cầu đồng bộ hay quy trình failover.
- Xác nhận quy trình khẩn cấp có thể sử dụng trong tình huống đã chọn.
- Chuẩn bị nơi lưu bằng chứng có kiểm soát truy cập.
- Dừng hoặc điều phối các thay đổi có thể làm nhiễu bài test.

Nếu kiểm thử trên production, phải dùng phạm vi và biện pháp kiểm soát được tổ chức phê duyệt. Không cần gây ảnh hưởng toàn bộ người dùng để chứng minh một tình huống có thể kiểm thử bằng phạm vi cô lập phù hợp.

Bằng chứng không được chứa mật khẩu, private key, token hoặc video hiển thị secret chưa được xử lý. Mã định danh secret và version đủ để đối chiếu trong nhiều trường hợp; không cần chụp giá trị secret.

## 8. Thiết kế giao dịch kiểm thử dương và âm

Một bài test tốt có cả giao dịch được phép và giao dịch phải bị từ chối.

### Giao dịch dương

Ví dụ một người vận hành thử nghiệm:

1. Đăng nhập qua endpoint được sử dụng trong vận hành thực tế.
2. Hoàn tất bước xác thực và phê duyệt cần thiết.
3. Nhận quyền có giới hạn thời gian cho đúng hệ thống đích.
4. Mở phiên qua đường PAM được quản lý.
5. Thực hiện thao tác vô hại, đã cho phép.
6. Đóng phiên và đối chiếu audit/recording.
7. Kiểm tra quyền kết thúc theo chính sách.

Với workload, thay bước tương tác bằng cơ chế xác thực máy tương ứng. Không đưa secret thực vào báo cáo hoặc probe.

### Giao dịch âm

Chọn các trường hợp liên quan, chẳng hạn:

- Account thử nghiệm không có quyền vào hệ thống đích.
- Yêu cầu JIT hết hạn hoặc chưa được phê duyệt.
- Danh tính đã bị thu hồi.
- Yêu cầu vượt phạm vi vai trò.
- Credential hoặc token cũ được thử trong phạm vi kiểm soát.
- Kết nối trực tiếp ngoài đường PAM nếu thiết kế yêu cầu ngăn đường này.

Chạy các kiểm tra phù hợp trước, trong và sau failover. Không để việc kết nối thành công che khuất một lần truy cập trái phép.

Một lỗi từ chối chung do toàn hệ thống chưa phục hồi cũng chưa chứng minh policy hoạt động đúng. Sau khi luồng hợp lệ phục vụ trở lại, vẫn phải kiểm tra luồng không hợp lệ tiếp tục bị chặn.

## 9. Kiểm tra riêng credential, rotation và quyền tạm thời

Đây là phần dễ bị bỏ qua nếu bài test chỉ tập trung vào giao diện.

### 9.1. Rotation đang thực hiện khi xảy ra lỗi

Xem xét tình huống credential ở hệ thống đích đã đổi nhưng vault chưa ghi nhận xong, hoặc ngược lại. Sau chuyển đổi, cần xác định:

- Hệ thống nhận biết thao tác đang dở như thế nào.
- Có retry hay không và retry có an toàn theo cơ chế của sản phẩm không.
- Có nguy cơ hai thành phần cùng rotation một account không.
- Cách đối soát để xác định trạng thái thật ở hệ thống đích.
- Khi nào account được phép phục vụ trở lại.
- Ai chịu trách nhiệm xử lý trạng thái không xác định.

Không giả định mọi thao tác rotation đều có tính idempotent. Một lần chạy lại có thể tạo thêm thay đổi hoặc làm account bị khóa. Dùng đúng cơ chế đối soát và phục hồi được hỗ trợ.

Tiêu chí đạt không nhất thiết là “mọi rotation đều thành công ngay lập tức”. Có thể một thao tác được đưa vào trạng thái lỗi có kiểm soát, bị khóa sử dụng và được phục hồi bằng runbook. Điều đó chỉ đạt nếu đúng hợp đồng vận hành đã duyệt và có bằng chứng.

### 9.2. TTL, JIT và revoke

Failover không được tự đặt lại thời điểm bắt đầu hay kéo dài thời hạn cấp quyền ngoài chính sách.

Ví dụ quyền có hiệu lực từ 10:00 đến 10:15. Nếu failover xảy ra lúc 10:10, đường phục vụ mới phải xử lý theo thời hạn đã được cấp; không tự tạo một khoảng 15 phút mới chỉ vì node vừa tiếp nhận.

Kiểm tra riêng:

- Thời hạn được cấp có được bảo toàn.
- Revoke trước hạn có đến được điểm thực thi.
- Cache quyền cũ được vô hiệu hóa hoặc giới hạn theo thiết kế.
- Phiên đã mở chịu chính sách thu hồi nào.
- Hệ thống đích có tiếp tục chấp nhận credential/token đã cấp hay không.

Xóa một record ở PAM không tự chứng minh hệ thống đích đã thu hồi quyền. Một credential từng được phát ra có thể còn hiệu lực ngoài PAM cho tới khi được đổi hoặc vô hiệu hóa theo cơ chế tương ứng. Bài test phải xác minh tại điểm thực thi liên quan.

### 9.3. Ngăn hai bên cùng có quyền ghi không hợp lệ

Khi có phân vùng mạng hoặc node cũ quay lại, cần chứng minh cơ chế quyết định quyền ghi hoạt động như thiết kế. Quorum, fencing hoặc cơ chế tương đương phụ thuộc kiến trúc cụ thể.

Không tự bật đồng thời hai bên để “giữ dịch vụ chạy” khi chưa xác định bên nào có quyền cập nhật secret. Khả năng đọc được từ cả hai nơi không chứng minh an toàn cho việc ghi và rotation.

## 10. Kiểm tra phiên đang mở và bằng chứng truy cập

Không phải kiến trúc nào cũng có thể chuyển một phiên tương tác đang mở sang broker khác. Hành vi chấp nhận được cần được quy định trước.

| Trạng thái | Nội dung cần nghiệm thu |
|---|---|
| Phiên mới | Được định tuyến đúng, xác thực và phê duyệt đúng, ghi nhận đầy đủ |
| Phiên đang mở được duy trì | Kiểm soát quyền còn hiệu lực; recording và audit tiếp tục đáp ứng cam kết |
| Phiên bị ngắt | Người dùng nhận biết, có sự kiện và có cách kết nối lại theo chính sách |
| Phiên kết nối lại | Không bỏ qua xác thực/phê duyệt; có liên kết hoặc dấu vết để đối chiếu |
| Phiên bị revoke | Hành vi kết thúc hoặc giới hạn tiếp tục đúng chính sách đã duyệt |
| Kết thúc bài test | Không còn phiên mồ côi, quyền tạm thời hoặc credential thử nghiệm chưa xử lý |

Một video phát được sau bài test chưa đủ để xác nhận audit đầy đủ. Cần đối chiếu thời điểm, đoạn ghi còn thiếu, danh tính, yêu cầu truy cập, hệ thống đích và sự kiện ngắt/kết nối lại.

Nếu sản phẩm lưu cục bộ rồi chuyển sau, kiểm tra cả giới hạn dung lượng, thời gian giữ, bảo vệ dữ liệu và gửi bù. Bộ đệm hoạt động trong một thử nghiệm ngắn không chứng minh có thể chịu mất kết nối vô thời hạn.

Khi sự kiện có thể gửi lại, cần phát hiện và xử lý trùng để không nhầm số lượng log với số lượng hành động thực tế.

## 11. Quy trình thực hiện một bài test failover

### Bước 1: Ghi baseline

Ghi cấu hình và trạng thái liên quan trước lỗi:

- Thành phần đang phục vụ và thành phần dự phòng.
- Tình trạng đồng bộ, độ trễ replication và tác vụ nền.
- Endpoint, đường truy cập và phụ thuộc được sử dụng.
- Số phiên, mức tải và nhóm account thử nghiệm.
- Policy, TTL, trạng thái phê duyệt và revoke cần kiểm tra.

Chạy giao dịch dương và âm để xác nhận môi trường đang hoạt động đúng trước khi tạo lỗi. Nếu baseline đã sai, chưa thể quy lỗi cho failover.

### Bước 2: Bắt đầu quan sát

Đặt mã bài test và mốc thời gian chung. Thu thập health, giao dịch nghiệp vụ, trạng thái đồng bộ, cảnh báo, phiên, rotation và audit.

Đồng bộ thời gian giữa các nguồn theo yêu cầu vận hành. Đo khoảng thời gian bằng đồng hồ đơn điệu của công cụ đo khi có thể; dùng timestamp có múi giờ để đối chiếu các hệ thống. Không ghép các log có sai lệch thời gian chưa biết rồi kết luận chính xác tới từng giây.

### Bước 3: Tạo đúng lỗi đã phê duyệt

Dùng phương pháp được hỗ trợ và có thể phục hồi trong môi trường cụ thể. Ghi thời điểm thao tác và thời điểm lỗi thực sự ảnh hưởng tới luồng.

Không đưa một lệnh tắt mạng hay xóa dữ liệu chung vào runbook khi chưa xác định chính xác đối tượng và đường phục hồi.

### Bước 4: Theo dõi chuyển đổi

Quan sát:

- Lỗi được phát hiện khi nào.
- Cơ chế chuyển đổi bắt đầu và hoàn tất khi nào.
- Thành phần nào đang có quyền phục vụ và quyền ghi.
- Giao dịch dương thất bại hay thành công.
- Giao dịch âm có bị chặn.
- Phiên, rotation, revoke và recording thay đổi ra sao.
- Người vận hành có nhận được cảnh báo đủ để hành động.

Nếu cần can thiệp thủ công, ghi rõ thao tác, người thực hiện và thời gian. Một failover có hỗ trợ thủ công không được báo cáo thành failover tự động.

### Bước 5: Xác nhận khôi phục đầu cuối

Thực hiện lại các luồng trong phạm vi. Đừng chỉ kiểm tra màn hình đăng nhập hoặc health check.

Theo dõi trong khoảng ổn định đã chọn để phát hiện dao động, lỗi từng lúc, backlog tăng và tài nguyên cạn dần. Một giao dịch thành công đơn lẻ không đủ để xác nhận phục hồi bền vững.

### Bước 6: Phục hồi cấu hình và kiểm tra failback

Theo runbook đã duyệt, xác định trạng thái nguồn dữ liệu, đồng bộ node cũ, điều kiện chuyển lại và quyền ghi. Sau đó kiểm tra lại giao dịch và bằng chứng.

### Bước 7: Đối soát và kết luận

Đối chiếu kết quả với tiêu chí đã ghi trước bài test. Mở vấn đề cho mọi sai lệch, gắn bằng chứng và chỉ rõ nội dung phải kiểm thử lại.

Không đánh dấu “Đã kiểm thử failover” chỉ vì bài test đã chạy xong. Trạng thái hoàn thành cần phản ánh kết quả đạt trong phạm vi được nghiệm thu.

## 12. Đo thời gian khôi phục đúng cách

Chọn mốc đo trước để tránh báo cáo thuận lợi bằng cách đổi định nghĩa sau sự cố.

Ví dụ:

~~~text
T0: lỗi bắt đầu ảnh hưởng tới luồng trong phạm vi
T1: hệ thống phát hiện lỗi
T2: thành phần dự phòng bắt đầu phục vụ
T3: giao dịch nghiệp vụ đầu cuối đầu tiên thành công
T4: kết thúc khoảng quan sát ổn định đạt tiêu chí
~~~

Có thể báo cáo:

- Thời gian phát hiện: T1 − T0.
- Thời gian tới giao dịch đầu cuối đầu tiên thành công: T3 − T0.
- Mốc xác nhận ổn định: T4, kèm độ dài khoảng quan sát và tiêu chí.
- Khoảng gián đoạn, số giao dịch lỗi và độ trễ trong từng giai đoạn.

Kế hoạch phải nói rõ RTO được đánh giá tại mốc nào. Nếu yêu cầu “khôi phục ổn định”, thời điểm một giao dịch may mắn thành công không được dùng thay cho tiêu chí ổn định.

### Ví dụ minh họa

Một kế hoạch giả định đặt mục tiêu luồng quản trị ưu tiên có giao dịch đầu cuối thành công lại trong 180 giây, sau đó đạt khoảng quan sát ổn định 5 phút. Đây là con số minh họa, không phải chuẩn khuyến nghị.

~~~text
10:00:00  T0 — luồng bắt đầu chịu ảnh hưởng
10:00:12  T1 — phát hiện lỗi
10:00:34  T2 — đường dự phòng nhận traffic
10:01:08  T3 — đăng nhập, phê duyệt và mở phiên thành công
10:06:08  T4 — hoàn tất 5 phút quan sát đạt tiêu chí
~~~

Kết quả đầu tiên cho thấy T3 − T0 = 68 giây, nằm trong mục tiêu 180 giây của kế hoạch này. Xác nhận ổn định được hoàn thành ở T4, không phải ở giây 68.

Tuy nhiên, nếu một account đã revoke vẫn mở được phiên lúc 10:02, bài test **không đạt điều kiện an toàn**, dù mục tiêu thời gian đã đạt.

Không dùng tỷ lệ thành công trung bình của cả ngày để che khuất khoảng failover thất bại. Báo cáo riêng cửa sổ lỗi/chuyển đổi và dùng cách tính độ trễ, timeout, số mẫu nhất quán.

## 13. Thu thập bằng chứng đủ để tái kiểm tra

Mỗi kết quả nên liên kết được với một test case, một tiêu chí và một cấu hình.

Bộ bằng chứng có thể gồm:

| Nhóm | Ví dụ bằng chứng |
|---|---|
| Nhận diện | Test ID, phạm vi, môi trường, người thực hiện và cửa sổ |
| Cấu hình | Phiên bản, topology, cấu hình HA/policy liên quan và thời điểm snapshot |
| Lỗi | Cách tạo lỗi, đối tượng, thời điểm, cách xác nhận lỗi thực sự có hiệu lực |
| Chuyển đổi | Log phát hiện/chuyển vai trò, quyền ghi và trạng thái đồng bộ |
| Nghiệp vụ | Kết quả đăng nhập, JIT/JEA, mở phiên, revoke và truy cập secret |
| Credential | Rotation job ID, version/metadata, kết quả đối soát với hệ thống đích |
| Phiên và audit | Session ID, request/correlation ID, bản ghi và kiểm tra khoảng trống |
| Hiệu năng | Tải, số mẫu, khoảng lỗi, độ trễ, tài nguyên và backlog |
| Phục hồi | Failback, kiểm tra sau khôi phục và xử lý account/phiên thử nghiệm |
| Quyết định | Kết quả từng tiêu chí, vấn đề, người nghiệm thu và phạm vi hiệu lực |

Ảnh dashboard chỉ là một phần bằng chứng. Nó thường không thể chứng minh policy ở hệ thống đích hay tính đầy đủ của recording.

Lưu bằng chứng theo chính sách truy cập và lưu giữ của tổ chức. Nếu dùng checksum để kiểm tra toàn vẹn file, phải nhớ rằng checksum chỉ giúp phát hiện thay đổi so với giá trị đã tin cậy; nó không tự chứng minh nguồn gốc hoặc tính đúng đắn của nội dung.

### Mẫu biên bản minh họa

Mẫu dưới đây chỉ mô tả cách tổ chức thông tin, không phải cấu hình sản phẩm hay file bắt buộc:

~~~yaml
testId: PAM-FO-EXAMPLE-01
scenario: Mat mot broker dang phuc vu
environment: Pre-production dai dien production
scope:
  - Dang nhap va mo phien moi qua endpoint chinh
  - Hanh vi phien dang mo
  - Revoke va ghi nhan audit
acceptance:
  recoveryDefinition: Giao dich dau cuoi thanh cong lai
  recoveryTargetSeconds: 180
  stableObservationSeconds: 300
  unauthorizedAccessAllowed: false
result:
  recoverySeconds: 68
  stableObservation: PASS
  validAccess: PASS
  revokedIdentityDenied: PASS
  sessionBehavior: DISCONNECT_AS_APPROVED
  recordingReconciliation: PASS
  failback: PASS
limitations:
  - Chua bao phu mat toan bo site
decision: PASS_WITHIN_DECLARED_SCOPE
~~~

Một biên bản thật cần dẫn tới bằng chứng và người phê duyệt cụ thể. Không điền PASS theo mẫu khi chưa thực hiện và đối chiếu.

## 14. Failback và phục hồi sau bài test

Khôi phục node cũ thường tạo thêm rủi ro nếu node mang trạng thái cũ nhưng được cho nhận traffic hoặc ghi dữ liệu ngay.

Trình tự cụ thể phụ thuộc sản phẩm, nhưng phải giải quyết được các câu hỏi:

1. Thành phần nào giữ trạng thái có thẩm quyền sau failover?
2. Node cũ đã được ngăn nhận traffic hoặc ghi ngoài ý muốn chưa?
3. Có giao dịch dở dang hay rotation cần đối soát không?
4. Đồng bộ về node cũ đã hoàn thành theo cơ chế được hỗ trợ chưa?
5. Điều kiện chuyển lại có được kiểm tra trước không?
6. Sau chuyển lại, quyền, credential, phiên và audit còn đúng không?
7. Cảnh báo, tác vụ nền và công suất đã trở về trạng thái mong muốn chưa?

Không dùng rollback cơ sở dữ liệu cũ như thao tác phục hồi chung cho PAM. Làm như vậy có thể khôi phục policy đã lỗi thời, làm mất revoke hoặc đưa vault về version không khớp credential ở đích.

Nếu cần phục hồi dữ liệu, phải theo quy trình phù hợp và đối soát các trạng thái bảo mật bị ảnh hưởng. Chỉ việc giao diện hoạt động lại không đủ để kết thúc sự cố.

Sau bài test, xử lý account thử nghiệm, quyền tạm thời, credential đã phát, phiên còn mở và mọi cấu hình lỗi đã chủ động tạo. Hoàn tất runbook và lưu kết quả trước khi đóng cửa sổ kiểm thử.

## 15. Quy trình khẩn cấp phải được kiểm thử cùng giả định

Failover có thể thất bại hoặc mất nhiều thời gian hơn dự kiến. Tổ chức cần biết quy trình break-glass có thực hiện được trong tình huống tương ứng hay không.

Kiểm tra tính độc lập của những thành phần thiết yếu. Ví dụ tài liệu khẩn cấp chỉ nằm trên hệ thống đang mất truy cập, hoặc credential khẩn cấp chỉ mở được bằng chính vault đang lỗi, sẽ làm quy trình không thực thi được.

Tuy vậy, đường khẩn cấp không được trở thành đường quản trị thường xuyên:

- Chỉ đúng người được ủy quyền có thể kích hoạt.
- Phạm vi và thời gian sử dụng được giới hạn theo chính sách.
- Việc sử dụng được ghi nhận bằng cơ chế phù hợp với tình huống.
- Có hậu kiểm, thu hồi và rotation khi cần.
- Khả năng truy cập hệ thống đích được xác minh bằng thao tác thử được kiểm soát.

Thành công của break-glass chứng minh một năng lực ứng cứu, không thay thế bằng chứng failover đạt. Nếu luồng thông thường chỉ phục hồi nhờ mọi người dùng tài khoản khẩn cấp, báo cáo phải thể hiện đúng sự khác biệt đó.

## 16. Quyết định go/no-go

Có thể đánh dấu mục checklist đạt khi những điều kiện trong phạm vi production đã chọn được kiểm thử, thỏa tiêu chí và được người có trách nhiệm nghiệm thu.

Những tình huống sau cần chặn kết luận đạt cho phạm vi tương ứng:

- Đường dự phòng phục vụ nhưng cấp quyền ngoài chính sách.
- Revoke hoặc thời hạn quyền không được thực thi đúng.
- Không xác định được trạng thái credential sau rotation dở dang.
- Có nguy cơ hai bên cùng ghi không hợp lệ chưa được xử lý.
- Mất bằng chứng vượt mức cho phép hoặc không phát hiện được khoảng trống.
- Không đạt mục tiêu khôi phục hoặc công suất đã chốt.
- Không thể phục hồi trạng thái an toàn sau failover/failback.
- Bằng chứng không khớp cấu hình định đưa vào production.

Một sai lệch có thể được tổ chức đánh giá và chấp thuận rủi ro theo thẩm quyền. Nhưng sự chấp thuận đó không biến một test case thất bại thành thành công. Biên bản phải phân biệt kết quả kỹ thuật, quyết định chấp thuận và công việc còn lại.

Với các mục chưa kiểm thử, dùng trạng thái rõ như “chưa kiểm thử”, “không thuộc phạm vi đã duyệt” hoặc “không đạt”. Không để ô đánh dấu trống gây hiểu nhầm là đã đạt.

## 17. Checklist nghiệm thu thực hành

Dùng checklist này để tổng hợp kết quả, kèm tham chiếu tới test case và bằng chứng tương ứng.

### Phạm vi và điều kiện

- [ ] Đã xác định endpoint, luồng đặc quyền, phụ thuộc và vùng lỗi trong phạm vi.
- [ ] Môi trường kiểm thử đại diện cho cấu hình cần nghiệm thu; giới hạn đã được ghi.
- [ ] Tiêu chí khôi phục, công suất, quyền, credential, phiên và audit đã được chốt trước.
- [ ] Có người điều phối, điều kiện dừng và phương án phục hồi.
- [ ] Baseline giao dịch dương/âm và trạng thái đồng bộ đều hợp lệ.

### Kết quả khi tạo lỗi

- [ ] Đã tạo đúng tình huống và xác nhận lỗi thực sự ảnh hưởng tới đường phục vụ.
- [ ] Chuyển đổi tự động/thủ công diễn ra đúng hợp đồng.
- [ ] Giao dịch hợp lệ khôi phục trong mục tiêu được duyệt.
- [ ] Giao dịch không hợp lệ vẫn bị từ chối sau khi dịch vụ phục hồi.
- [ ] JIT/JEA, TTL, phê duyệt và revoke còn đúng ở điểm thực thi.
- [ ] Credential và rotation được đối soát; không còn trạng thái không xác định ngoài quy trình xử lý được duyệt.
- [ ] Quyền ghi và việc node cũ quay lại được kiểm soát.
- [ ] Phiên đang mở, phiên mới và kết nối lại có hành vi đúng.
- [ ] Audit/recording đầy đủ theo cam kết; backlog, mất đoạn và sự kiện trùng đã được đối chiếu.
- [ ] Đường dự phòng đáp ứng mức tải đã nghiệm thu.

### Kết thúc và hiệu lực

- [ ] Failback hoặc trạng thái phục vụ sau cùng đã được kiểm tra an toàn.
- [ ] Đã xử lý quyền, account, phiên và thay đổi thử nghiệm.
- [ ] Đã ghi hạn chế, vấn đề và nội dung cần kiểm thử lại.
- [ ] Bằng chứng có mã nhận diện, thời gian, cấu hình và người chịu trách nhiệm.
- [ ] Kết luận đạt chỉ áp dụng cho phạm vi thực sự đã kiểm thử.
- [ ] Runbook và danh sách liên hệ đã được cập nhật theo kết quả thực tế.

Các mục “không áp dụng” cần lý do và người xác nhận. Không dùng “không áp dụng” để bỏ qua một thành phần đang tồn tại trong luồng production.

## 18. Những kết luận sai thường gặp

| Kết luận sai | Vì sao chưa đủ | Cách xác nhận phù hợp |
|---|---|---|
| Có hai node nên failover đã đạt | Có thể cùng phụ thuộc một điểm lỗi | Kiểm thử vùng lỗi và phụ thuộc thực tế |
| Health check xanh nên người dùng vào được | Probe có thể không đi hết luồng | Chạy giao dịch nghiệp vụ qua endpoint thật |
| Đăng nhập được nên PAM đã phục hồi | Vault, broker, quyền hoặc recording có thể còn lỗi | Kiểm tra toàn bộ luồng trong phạm vi |
| Có log nên không mất audit | Có thể thiếu đoạn hoặc gửi trùng | Đối chiếu request/session/action theo thời gian |
| Có backup nên có thể quay lại bất cứ lúc nào | Dữ liệu cũ có thể không khớp quyền và secret hiện tại | Phục hồi theo runbook và đối soát trạng thái bảo mật |
| Bài test năm trước đã PASS nên vẫn còn hiệu lực | Kiến trúc hoặc policy có thể đã thay đổi | Đánh giá tác động và kiểm thử lại phần liên quan |
| Tắt MFA để qua bài test là cách ứng cứu | Kết quả không còn chứng minh luồng đã phê duyệt | Kiểm thử hành vi suy giảm và đường khẩn cấp đã duyệt |

## 19. Khi nào phải kiểm thử lại?

Kết quả failover gắn với cấu hình và giả định tại thời điểm thử. Đánh giá nhu cầu kiểm thử lại khi thay đổi:

- Phiên bản PAM, vault, broker, database hoặc cơ chế HA.
- Topology, vùng triển khai, endpoint, DNS, load balancer hay đường mạng.
- IdP/MFA, dịch vụ khóa, storage ghi phiên hoặc luồng audit.
- Chính sách JIT/JEA, TTL, revoke, phê duyệt hoặc break-glass.
- Cơ chế rotation hoặc nhóm hệ thống đích quan trọng.
- Mức tải, số phiên hoặc yêu cầu khôi phục.
- Runbook, tổ chức trực vận hành hoặc sự cố cho thấy giả định cũ không đúng.

Không phải mọi thay đổi nhỏ đều cần lặp toàn bộ ma trận. Phải xác định phạm vi ảnh hưởng và lựa chọn kiểm thử tương xứng; lý do giữ nguyên bằng chứng cũ cũng cần được ghi nhận.

Ngoài kiểm thử kỹ thuật, diễn tập vận hành giúp xác nhận người trực biết nhận diện lỗi, đọc cảnh báo và thực hiện đúng runbook. Diễn tập bàn giấy không thay thế các tình huống cần kiểm chứng hành vi thật của hệ thống.

## 20. Bài tập áp dụng

Giả sử một cụm PAM đã chuyển sang broker dự phòng trong 70 giây. Người có quyền mở được phiên mới, nhưng có ba phát hiện:

1. Một phiên đang mở bị ngắt và có đủ sự kiện kết thúc; chính sách đã cho phép hành vi này.
2. Một account bị revoke trước failover vẫn vào được hệ thống đích qua đường phục vụ mới.
3. Recording được gửi bù sau khi kết nối storage phục hồi và đã đối chiếu đầy đủ.

Hãy xác định mục “Đã kiểm thử failover” có đạt hay không, và cần xử lý gì.

**Gợi ý phân tích:** Thời gian 70 giây chỉ đánh giá được sau khi so với mục tiêu và cách đo đã duyệt. Việc ngắt phiên có thể đạt nếu đúng hợp đồng. Gửi bù recording có thể đạt nếu nằm trong giới hạn được phép, dữ liệu được bảo vệ và đã đối chiếu. Tuy nhiên, account đã revoke vẫn truy cập được là sai lệch về ranh giới đặc quyền; bài test không đạt điều kiện an toàn tương ứng.

Cần xác định điểm thực thi nào còn chấp nhận quyền cũ, khắc phục và kiểm thử lại revoke qua failover, đồng thời đánh giá các luồng có thể bị cùng nguyên nhân. Không giải quyết bằng cách bỏ kiểm tra âm hoặc chỉ tăng tốc chuyển đổi.

**Bằng chứng cốt lõi của mục checklist này là khả năng phục hồi truy cập đặc quyền đúng chính sách, trong giới hạn đã duyệt, với trạng thái credential và bằng chứng đủ để đối chiếu.** Khi chưa chứng minh được những điều đó, trạng thái “cụm đã chuyển đổi” chưa đủ để xác nhận sẵn sàng production.

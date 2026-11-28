# Workload decommissioning: thu hồi danh tính khi ngừng vận hành workload

## 1. Ngừng chạy chưa có nghĩa là hết quyền truy cập

Một dịch vụ Java được thay thế, một batch job kết thúc dự án hoặc một pipeline triển khai bị loại bỏ đều để lại nhiều thứ hơn tiến trình đang chạy. Service account, quyền trên cơ sở dữ liệu, khóa API, chứng thư, cấu hình liên kết danh tính và token đã cấp có thể tiếp tục tồn tại sau khi workload biến mất khỏi màn hình giám sát.

**Workload decommissioning** là quá trình kết thúc có kiểm soát vòng đời của một workload, bao gồm việc ngừng thực thi, chấm dứt khả năng nhận credential mới, loại bỏ quyền truy cập còn lại và lưu bằng chứng phục vụ kiểm toán. Trong IAM, mục tiêu không chỉ là “xóa tài khoản” mà là bảo đảm danh tính cũ không còn tạo ra truy cập ngoài ý muốn.

Workload ở đây có thể là dịch vụ backend, máy ảo, container, tác vụ định kỳ, hàm xử lý sự kiện, agent tự động hóa hoặc pipeline CI/CD. Đối tượng được thu hồi là **danh tính máy và quyền của nó**, không phải tài khoản của lập trình viên đã tạo workload.

Ví dụ, `invoice-exporter` là batch job dùng một principal riêng để đọc hóa đơn và ghi báo cáo vào kho đối tượng. Khi chuyển sang hệ thống báo cáo mới, chỉ xóa lịch chạy chưa giải quyết được các vấn đề sau:

- Một bản sao job vẫn đang chạy ở môi trường dự phòng.
- Khóa truy cập đã được sao chép vào cấu hình cũ vẫn dùng được.
- Token được cấp trước thời điểm ngừng vận hành vẫn còn hiệu lực.
- Chính sách tin cậy cho phép một pipeline cũ tiếp tục đổi assertion lấy token mới.
- Hệ thống quản lý cấu hình có thể tạo lại principal và quyền vào lần đồng bộ tiếp theo.

Decommissioning hoàn chỉnh phải xử lý được từng đường truy cập đó.

## 2. Phân biệt kết thúc một instance với kết thúc một danh tính

Trong hệ thống tự động mở rộng, hàng trăm instance có thể dùng chung một danh tính logic. Kết thúc một container không đồng nghĩa nên xóa service account mà các replica khác còn sử dụng. Ngược lại, khi toàn bộ dịch vụ bị loại bỏ, dừng một instance không đủ để kết thúc danh tính logic.

| Tình huống | Phạm vi kết thúc | Xử lý IAM cần chú ý |
|---|---|---|
| Thay một replica lỗi | Một instance | Hủy credential hoặc phiên gắn riêng với instance nếu có; giữ danh tính chung cho các replica hợp lệ |
| Kết thúc một lần chạy batch | Một execution | Hết hạn hoặc thu hồi credential của execution; lịch chạy và danh tính cho lần sau có thể vẫn cần |
| Tạm dừng dịch vụ | Hoạt động vận hành | Giảm quyền hoặc khóa khả năng truy cập theo kế hoạch; giữ cấu hình cần thiết để khôi phục có kiểm soát |
| Thay danh tính dùng chung bằng các danh tính riêng | Danh tính cũ sau khi chuyển đổi | Xác minh từng consumer đã chuyển xong rồi thu hồi danh tính dùng chung |
| Loại bỏ vĩnh viễn một dịch vụ | Toàn bộ workload logic | Kết thúc các instance, nguồn cấp credential, quyền, trust và cấu hình có thể tái tạo workload |

Trước khi thu hồi, phải trả lời rõ: **đang kết thúc một lần thực thi, một môi trường hay toàn bộ workload?** Câu trả lời xác định những principal và consumer nào nằm trong phạm vi.

Nếu danh tính đang được dùng chung, không thể mặc định mọi truy cập mang danh tính đó đều đến từ workload cần loại bỏ. Cần kiểm kê và chuyển các consumer còn hợp lệ sang danh tính khác trước khi xóa hoặc vô hiệu hóa danh tính chung. Không nên gán lại nguyên danh tính cũ cho một ứng dụng mới chỉ để tránh cấu hình quyền.

## 3. Kiểm kê tất cả đường tạo và sử dụng quyền

Một bản kiểm kê hữu ích nối được ba câu hỏi: ai chứng minh workload là ai, ai cấp credential cho nó và hệ thống nào chấp nhận credential đó?

| Thành phần | Ví dụ | Câu hỏi phải giải quyết |
|---|---|---|
| Định danh chuẩn | Principal ID, service account ID, workload subject | Danh tính nào thực sự bị kết thúc, ở môi trường nào? |
| Nguồn thực thi | Deployment, scheduler, pipeline, trigger, hệ thống DR | Còn nơi nào có thể chạy hoặc khởi động lại workload? |
| Cơ chế chứng thực ban đầu | Assertion liên kết, định danh máy, bootstrap credential | Workload còn có thể chứng minh danh tính với bên cấp token không? |
| Credential đã cấp | Access token, refresh token, khóa API, chứng thư | Credential nào còn sống, tồn tại ở đâu và bị thu hồi thế nào? |
| Quyền và quan hệ thành viên | Role binding, group, ACL, database grant | Quyền trực tiếp và quyền gián tiếp nào vẫn cấp truy cập? |
| Chính sách tin cậy | Quy tắc đổi token, ánh xạ subject, trust giữa môi trường | Nguồn bên ngoài nào còn được phép đóng vai danh tính này? |
| Truy cập trung gian | Phiên database, lease secret, phiên quản trị | Kênh đã mở có tiếp tục hoạt động sau khi bỏ quyền không? |
| Nguồn cấu hình | IaC, GitOps, job template, bản sao cấu hình | Lần reconcile hoặc restore sau có tạo lại quyền cũ không? |
| Bằng chứng | Audit log, quyết định phê duyệt, kết quả kiểm tra | Có giải thích được việc thu hồi đã diễn ra với đối tượng nào không? |

Không chỉ tìm tên hiển thị. Tên `invoice-exporter` có thể xuất hiện ở nhiều môi trường hoặc được tái sử dụng. Hồ sơ thu hồi nên ghi định danh bất biến của principal khi nền tảng cung cấp, môi trường, chủ sở hữu, tài nguyên đích và mã thay đổi liên quan.

“Không thấy log truy cập trong bảy ngày” chỉ là một tín hiệu. Job chạy cuối tháng hoặc hệ thống dự phòng có thể im lặng lâu hơn. Cần kết hợp log với cấu hình triển khai, lịch chạy, owner và danh sách dependency. Khoảng quan sát phải phù hợp chu kỳ hoạt động thực tế của workload.

## 4. Ba việc khác nhau: dừng cấp mới, chặn quyền và xử lý credential đã cấp

Một kế hoạch thường thất bại vì xem mọi thao tác thu hồi là tương đương. Thực tế có ba lớp cần giải quyết riêng.

### 4.1. Chấm dứt khả năng nhận credential mới

Đây là việc ngăn workload tiếp tục lấy khóa, token, chứng thư hoặc lease mới. Biện pháp có thể là vô hiệu hóa principal, gỡ quyền đổi token, bỏ ánh xạ federation dành riêng cho workload hoặc thu hồi bootstrap credential.

Với workload federation, chỉ xóa một secret cục bộ có thể không có tác dụng: workload vẫn có thể lấy assertion mới từ nguồn được tin cậy rồi đổi lấy token đích. Phải xử lý đúng quy tắc trust hoặc quyền trao đổi token gắn với workload bị loại bỏ.

Không gỡ cả identity provider dùng chung chỉ vì một workload ngừng hoạt động. Thu hồi cần chính xác đến subject, quan hệ tin cậy hoặc binding thuộc phạm vi; các consumer khác của nhà cung cấp đó có thể vẫn hợp lệ.

### 4.2. Loại bỏ quyền truy cập tại nơi thực thi quyết định

Một token hợp lệ về mật mã không tự bảo đảm còn được phép đọc dữ liệu. Tài nguyên có thể kiểm tra quyền hiện hành, chính sách cục bộ hoặc dữ liệu quyền đã nhúng trong token, tùy kiến trúc.

Vì vậy, cần kiểm kê và gỡ quyền trên từng hệ thống đích: kho đối tượng, database, message broker, API nội bộ, kho secret và các dịch vụ quản lý. Bỏ một role ở hệ thống IAM trung tâm có thể chưa xóa database user hoặc ACL được tạo riêng trước đó.

Quyền gián tiếp cũng quan trọng: principal có thể vẫn là thành viên của một group, có thể đóng vai role khác hoặc có thể gọi một dịch vụ trung gian thực hiện thao tác thay mình. Thu hồi một grant dễ nhìn thấy chưa chắc đã cắt hết đường truy cập.

### 4.3. Xử lý credential và phiên đã tồn tại

Credential đã cấp có vòng đời riêng. Một số hệ thống hỗ trợ thu hồi ngay; một số khác chỉ kiểm tra chữ ký và thời hạn, nên credential có thể tiếp tục được chấp nhận đến khi hết hạn nếu không có cơ chế chặn bổ sung.

| Loại credential hoặc phiên | Điều cần xác minh khi decommission |
|---|---|
| Khóa API hoặc secret tĩnh | Đã vô hiệu hóa hoặc xóa giá trị ở bên xác thực; xóa bản sao trong cấu hình không đủ để vô hiệu hóa bản đã lộ |
| Refresh token | Đã thu hồi khả năng dùng nó để lấy access token mới; đồng thời xử lý access token đã được cấp |
| Access token dạng tự chứa | Bên nhận có kiểm tra thu hồi hoặc quyền hiện hành không; nếu không, cần biện pháp chặn phù hợp hoặc chờ hết thời hạn thực tế |
| Token được kiểm tra trực tuyến | Trạng thái không còn hoạt động đã được bên nhận áp dụng chưa, có cache làm chậm không? |
| Chứng thư mTLS | Còn được chấp nhận ở đâu; cơ chế thu hồi, kiểm tra trạng thái hoặc danh sách danh tính được phép có được thực thi không? |
| Credential động hoặc lease | Có thể thu hồi lease không; tài khoản hoặc phiên ở backend đã được xử lý chưa? |
| Phiên database hoặc kết nối dài hạn | Bỏ quyền hoặc khóa tài khoản có chấm dứt phiên đang mở không, hay phải đóng phiên riêng? |

Không xoay khóa ký dùng chung cho toàn tổ chức chỉ để kết thúc một workload nếu có cách thu hồi hẹp hơn. Thao tác đó có thể làm gián đoạn nhiều hệ thống không thuộc phạm vi. Tương tự, xóa trust anchor dùng chung để chặn một chứng thư là thay đổi rộng hơn việc thu hồi danh tính của một workload.

Nguyên tắc cần nhớ là: **dừng cấp mới không tự hủy credential cũ; xóa credential cục bộ không tự xóa quyền; xóa principal không bảo đảm mọi phiên đã mở lập tức kết thúc**.

## 5. Quy trình decommission có kiểm soát

Quy trình dưới đây dành cho trường hợp ngừng vận hành có kế hoạch. Nếu có dấu hiệu bị chiếm quyền, thứ tự ưu tiên phải thay đổi để chặn truy cập nguy hiểm ngay.

### Bước 1: Xác nhận phạm vi, owner và điều kiện kết thúc

Ghi lại workload nào sẽ ngừng, môi trường nào liên quan, danh tính nào thuộc phạm vi, thời điểm cắt chuyển và người chịu trách nhiệm. Xác định consumer dùng chung, lịch chạy thưa, hệ thống dự phòng và bên tiếp nhận dữ liệu hoặc công việc còn lại.

Điều kiện kết thúc cần mô tả hành vi có thể kiểm chứng, chẳng hạn “principal cũ không thể lấy credential mới hoặc đọc kho hóa đơn”, thay vì chỉ “ticket xóa service account đã hoàn thành”.

### Bước 2: Chuyển dependency và làm cạn công việc

Chuyển traffic, scheduler hoặc producer sang workload thay thế. Cho những tác vụ hợp lệ đang chạy hoàn tất hoặc hủy chúng theo kế hoạch. Với consumer hàng đợi, xác định rõ cách xử lý message đang giữ và retry để tránh mất hoặc xử lý trùng nghiệp vụ.

Workload thay thế nên có danh tính và quyền riêng được kiểm tra trước cắt chuyển. Việc sao chép nguyên credential của workload cũ khiến quá trình thu hồi sau đó không còn tách biệt được hai hệ thống.

Không giữ quyền rộng vô thời hạn chỉ vì “có thể cần rollback”. Nếu cần cửa sổ khôi phục, phải xác định thời hạn, owner và quy trình cấp lại quyền tối thiểu.

### Bước 3: Dừng nguồn thực thi và nguồn tái tạo

Dừng deployment, lịch chạy, trigger và pipeline thuộc phạm vi. Kiểm tra cả autoscaling, cơ chế retry, lịch chạy ở môi trường DR và quy trình phục hồi từ bản sao lưu.

Cập nhật nguồn cấu hình mà hệ thống tự động coi là trạng thái mong muốn. Nếu chỉ xóa tài nguyên trực tiếp trong khi IaC hoặc GitOps vẫn khai báo nó, tài nguyên và quyền có thể quay lại ở lần đồng bộ sau.

Thứ tự giữa cập nhật nguồn cấu hình và thay đổi trực tiếp phải phù hợp với cơ chế triển khai. Mục tiêu là không có khoảng mà tự động hóa vô tình khôi phục trạng thái cũ trong khi đang thu hồi.

### Bước 4: Chặn cấp credential mới và thu hồi quyền

Đóng các đường cấp mới đã kiểm kê: principal, federation binding, quyền impersonation, bootstrap credential hoặc quyền đọc secret. Sau đó xử lý các grant tại tài nguyên đích theo kế hoạch thu hồi.

Trong cửa sổ chuyển đổi có kiểm soát, những bước này có thể cần phối hợp để công việc còn lại hoàn tất. Nhưng thời điểm “không cấp mới” phải rõ ràng; từ thời điểm đó không được gia hạn credential cho workload chỉ vì một tiến trình cũ vẫn thử gọi.

Thu hồi quyền tại tài nguyên và chặn cấp mới là hai việc bổ sung nhau. Nếu hệ thống đích vẫn chấp nhận quyền nhúng trong credential cũ, cần thêm cách xử lý ở bước kế tiếp.

### Bước 5: Thu hồi credential đã cấp và kết thúc phiên

Vô hiệu hóa khóa tĩnh, thu hồi refresh token và lease, xử lý chứng thư và đóng các phiên cần chấm dứt. Với token không thể thu hồi riêng lẻ, đánh giá đường chặn tại bên nhận và thời điểm hết hiệu lực muộn nhất.

Không suy ra thời điểm an toàn chỉ từ TTL cấu hình hiện tại. Token đã cấp trước một lần thay đổi cấu hình có thể dùng thời hạn khác. Cần xét credential thực tế còn tồn tại, cache, thời gian lan truyền chính sách và sai lệch đồng hồ mà cơ chế xác thực cho phép.

Nếu không biết chắc credential nào còn sống, không được ghi nhận rằng việc chặn đã tức thời có hiệu lực. Phải giữ ràng buộc tại hệ thống đích hoặc một biện pháp chặn phù hợp cho đến khi có bằng chứng đủ tin cậy.

### Bước 6: Kiểm chứng trước khi xóa phần định danh còn lại

Kiểm tra cả việc lấy credential mới và sử dụng credential đã cấp. Thử nghiệm âm tính phải được thực hiện trong phạm vi cho phép, ở tài nguyên kiểm thử hoặc theo cách không tạo tác động nghiệp vụ. Không đưa giá trị secret hoặc token thật vào ticket làm bằng chứng.

Xác minh rằng workload thay thế và consumer hợp lệ vẫn hoạt động. Thu hồi đúng đối tượng là một phần của hoàn thành; gây lỗi cho danh tính dùng chung chưa được chuyển đổi là dấu hiệu phạm vi chưa được giải quyết.

Chỉ sau khi đạt điều kiện đã đặt ra mới xóa principal, mapping hoặc tài nguyên IAM còn lại nếu nền tảng và chính sách lưu giữ cho phép. Một số hệ thống cần giữ principal ở trạng thái vô hiệu hóa một thời gian để bảo toàn liên kết log hoặc xử lý tham chiếu cũ. Đây phải là trạng thái có owner và hạn xử lý, không phải tài khoản bỏ quên.

### Bước 7: Dọn bản sao credential và lưu bằng chứng

Xóa các bản sao credential thuộc phạm vi trong secret store, cấu hình triển khai, biến môi trường pipeline và nơi lưu trữ vận hành phù hợp. Việc này giảm nguy cơ tái sử dụng hoặc rò rỉ trong tương lai, nhưng chỉ thực hiện sau hoặc cùng với vô hiệu hóa ở bên cấp; không nhầm việc dọn bản sao với thu hồi credential.

Lưu định danh principal, thời điểm chặn cấp mới, thời điểm bỏ quyền, kết quả kiểm chứng và tham chiếu audit log. Không cần giữ secret để chứng minh đã thu hồi secret. Bằng chứng có thể dùng mã credential, fingerprint chứng thư hoặc ID sự kiện thay cho giá trị bí mật.

## 6. Ví dụ: loại bỏ batch job xuất hóa đơn

Giả sử `invoice-exporter` chạy hằng đêm trong production. Nó đọc database hóa đơn, lấy credential động từ kho secret và ghi file vào một bucket báo cáo. Hệ thống mới `reporting-events` đã tiếp nhận chức năng này với danh tính riêng.

Qua kiểm kê, nhóm vận hành phát hiện bốn đường truy cập của danh tính cũ:

1. Một scheduler chính và một scheduler dự phòng có thể khởi động job.
2. Một binding federation cho phép job đổi assertion thành token truy cập kho secret.
3. Database có tài khoản động được cấp theo lease và vẫn còn phiên mở.
4. Bucket có một grant cho principal cũ, cùng một khóa tĩnh nằm trong pipeline bảo trì đã lâu không chạy.

Nếu nhóm chỉ xóa service account ở hệ thống chạy job, khóa tĩnh hoặc phiên database có thể vẫn là đường truy cập độc lập. Quy trình xử lý cần bám vào từng đường đã tìm được.

| Mốc | Thay đổi | Bằng chứng mong đợi |
|---|---|---|
| Trước cắt chuyển | Chuyển công việc sang `reporting-events`, kiểm tra dữ liệu đầu ra | Hệ thống mới xử lý đủ phạm vi; owner xác nhận job cũ không còn nhiệm vụ |
| Dừng thực thi | Tắt cả hai scheduler, kết thúc execution và cập nhật cấu hình triển khai | Không còn execution cũ; reconcile không tạo lại lịch |
| Chặn cấp mới | Bỏ binding riêng của job cũ và quyền lấy credential động | Yêu cầu lấy credential mới của danh tính cũ bị từ chối vì chính sách |
| Thu hồi hiện hữu | Thu hồi lease, xử lý phiên database, vô hiệu hóa khóa tĩnh và bỏ grant bucket | Credential hoặc phiên cũ không còn tạo truy cập trái phép |
| Quan sát và xác nhận | Theo dõi các lần thử lại, kiểm tra hệ thống thay thế | Không có truy cập thành công ngoài ý muốn; lỗi retry cũ được truy nguồn |
| Kết thúc | Dọn cấu hình và principal theo chính sách lưu giữ | Không còn nguồn tái tạo; hồ sơ chứa đủ ID, thời điểm và kết quả |

Các tên và mốc trong ví dụ là mô hình minh họa. Không có một khoảng chờ cố định phù hợp cho mọi hệ thống: thời gian xác nhận phụ thuộc vòng đời credential, đặc điểm phiên, chu kỳ job và độ trễ của bằng chứng.

## 7. Kiểm chứng bằng kết quả quan sát được

Một kiểm tra “kết nối thất bại” chưa đủ để chứng minh IAM đã thu hồi đúng. Lỗi có thể đến từ DNS, đường mạng hoặc một dịch vụ tạm ngừng. Khi kiểm chứng, cần phân biệt lỗi hạ tầng với quyết định từ chối xác thực hoặc phân quyền.

Một tập kiểm chứng thường gồm các nhóm sau:

- **Cấp mới:** principal cũ không thể lấy token, gia hạn credential hoặc đổi assertion theo đường từng được cho phép.
- **Quyền tài nguyên:** các thao tác đại diện cho quyền cũ bị từ chối tại tài nguyên tương ứng; không chỉ thử đăng nhập vào hệ thống IAM.
- **Credential và phiên cũ:** khóa đã cấp bị vô hiệu hóa; token, chứng thư, lease và kết nối dài hạn được xử lý theo cơ chế thực tế của từng hệ thống.
- **Tái tạo:** scheduler, pipeline, restore hoặc reconcile thông thường không phục hồi workload cùng quyền cũ.
- **Đối tượng còn hợp lệ:** workload thay thế và consumer ngoài phạm vi vẫn thực hiện được nghiệp vụ cần thiết.
- **Audit:** các quyết định thu hồi và lần kiểm chứng có dấu thời gian, principal ID và kết quả có thể đối chiếu.

Audit log cần được xem cùng độ trễ đưa log vào hệ thống và phạm vi tài nguyên đã bật ghi nhận. Không có log thành công chỉ có ý nghĩa khi biết nguồn log đủ bao phủ, thời gian quan sát phù hợp và các thử nghiệm thực sự đi qua đường truy cập cần kiểm tra.

Có thể biểu diễn điều kiện đóng việc bằng giả mã sau; đây không phải API của một nền tảng cụ thể:

```text
close_decommission_request khi:
    không còn nguồn thực thi ngoài ý muốn trong phạm vi
    VÀ không còn đường cấp credential mới cho workload cũ
    VÀ quyền cũ đã được loại bỏ hoặc chặn tại hệ thống đích
    VÀ credential/phiên đã cấp đã bị thu hồi hoặc hết hiệu lực có xác minh
    VÀ tự động hóa không tái tạo danh tính và quyền đã loại bỏ
    VÀ dependency hợp lệ đã được chuyển hoặc xác nhận không còn dùng
    VÀ bằng chứng kiểm chứng đã được lưu
```

Nếu một điều kiện chưa đạt, ghi rõ phần còn lại, biện pháp đang duy trì và người chịu trách nhiệm. Không đóng việc chỉ vì đối tượng đã biến mất khỏi một giao diện quản trị.

## 8. Trường hợp sự cố: chặn truy cập trước, hoàn tất thu hồi sau

Khi nghi ngờ workload hoặc credential đã bị chiếm quyền, không chờ drain nghiệp vụ như một lần ngừng vận hành bình thường. Ưu tiên chặn truy cập, dừng cấp credential mới, vô hiệu hóa credential bị ảnh hưởng và xử lý phiên còn hoạt động theo phạm vi sự cố.

Việc thu thập bằng chứng và cô lập cần được phối hợp để không kéo dài truy cập nguy hiểm. Không xóa ngay mọi log hoặc dấu vết triển khai, vì chúng giúp xác định credential nào bị sử dụng, tài nguyên nào bị truy cập và đường nào cần thu hồi thêm.

Sau khi đã chặn, vẫn phải hoàn tất các phần thường bị bỏ sót: quyền gián tiếp, tài khoản ở hệ thống đích, nguồn tự động tái tạo và cấu hình dự phòng. Một khóa bị lộ đã vô hiệu hóa không bảo đảm kẻ tấn công chưa tạo credential hoặc quyền khác trước đó; điều tra sự cố quyết định phạm vi kiểm tra bổ sung.

Nếu cần khôi phục nghiệp vụ, nên dùng deployment và credential được xác minh sạch với quyền tối thiểu. Không khôi phục nguyên credential nghi bị lộ từ backup để làm hệ thống hoạt động trở lại.

## 9. Những sai lầm thường gặp

### Xóa workload nhưng giữ principal “phòng khi cần”

Principal bỏ quên tích lũy quyền và không có owner vận hành thực tế. Nếu cần thời gian chờ, chuyển sang trạng thái bị chặn với hạn xử lý rõ ràng. Ngoại lệ giữ quyền phải có lý do cụ thể và thời điểm kết thúc.

### Chỉ xóa secret khỏi secret store

Một bản sao của secret có thể còn trên máy chạy, trong pipeline hoặc đã nằm ngoài hệ thống. Bản sao chỉ hết khả năng truy cập khi bên xác thực không còn chấp nhận nó. Thu hồi ở bên xác thực và dọn bản sao là hai công việc khác nhau.

### Tin rằng mọi access token đều bị hủy khi xóa tài khoản

Điều này phụ thuộc cách tài nguyên xác minh token và chính sách. Với token được chấp nhận độc lập dựa trên chữ ký và thời hạn, phải xác minh cơ chế chặn hoặc chờ hết hiệu lực thay vì suy luận từ trạng thái tài khoản.

### Bỏ sót identity federation và quyền impersonation

Thu hồi credential hiện có nhưng giữ đường cấp mới cho phép workload quay lại với credential khác. Cần chặn cả trust, ánh xạ và quyền đóng vai thuộc phạm vi.

### Xóa danh tính dùng chung trước khi tách consumer

Hành động này gây gián đoạn cho workload khác và khiến nhóm vận hành phải khôi phục quyền vội vàng. Kiểm kê và chuyển consumer hợp lệ trước giúp thu hồi chính xác, đồng thời giảm lý do phải duy trì danh tính dùng chung.

### Để tự động hóa khôi phục quyền cũ

Thay đổi thủ công có thể bị IaC, GitOps hoặc một pipeline bảo trì ghi đè. Hoàn thành decommissioning bao gồm sửa trạng thái mong muốn và kiểm tra chu kỳ tự động hóa liên quan.

### Tái sử dụng tên rồi cho rằng mọi quyền cũ đã mất

Cách nền tảng gắn quyền với ID hoặc tên khác nhau. Một binding tham chiếu tên hay subject có thể tiếp tục khớp đối tượng mới. Trước khi tái sử dụng tên, kiểm tra chính sách còn tham chiếu và tách rõ định danh lịch sử với định danh mới.

### Xóa bằng chứng cùng với tài khoản

Xóa principal không thay thế chính sách lưu giữ audit. Cần lưu đủ định danh và thời điểm để các log cũ vẫn giải thích được sau khi đối tượng không còn tồn tại.

## 10. Đưa decommissioning thành phần cuối của vòng đời workload

Decommissioning dễ thực hiện hơn khi danh tính được thiết kế có owner, môi trường, mục đích và thời hạn ngay từ lúc cấp phát. Credential ngắn hạn, quyền ít nhất, danh tính tách theo workload và audit tập trung đều giảm số đường phải xử lý khi kết thúc.

Tuy nhiên, credential ngắn hạn không loại bỏ nhu cầu thu hồi. Nếu nguồn cấp mới vẫn mở, workload có thể lấy credential mới liên tục. Nếu quyền nằm ở một hệ thống khác hoặc phiên đã mở sống lâu hơn token, vẫn cần xử lý ở nơi đó.

Một workload chỉ hoàn tất vòng đời IAM khi nó không còn thực thi ngoài ý muốn, không nhận được credential mới, không sử dụng được quyền cũ và không bị tự động tái tạo cùng quyền truy cập. Bằng chứng về các điều kiện đó là cơ sở để kết thúc công việc, thay cho việc chỉ xác nhận đã xóa một tài khoản.

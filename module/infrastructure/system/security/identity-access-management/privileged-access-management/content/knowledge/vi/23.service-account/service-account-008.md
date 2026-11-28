# Service account permission

## Mục tiêu bài học

Một service account có thể xác thực thành công nhưng vẫn không nên được phép thực hiện mọi hành động trên hệ thống. Credential trả lời “định danh nào đang gửi yêu cầu”; permission quyết định “định danh đó được làm gì, với tài nguyên nào và trong điều kiện nào”.

Trong chương Service account của module Privileged Access Management (PAM), bài học này tập trung vào thiết kế, cấp, kiểm tra và thu hồi quyền cho định danh phi con người. Mục tiêu là giữ workload hoạt động đúng chức năng đồng thời giới hạn khả năng lạm dụng khi ứng dụng, pipeline hoặc credential gặp sự cố.

Sau bài học, bạn có thể:

- Chuyển nhu cầu của workload thành tập quyền có phạm vi cụ thể.
- Phân biệt quyền được gán trực tiếp với quyền hiệu lực và đường tăng quyền gián tiếp.
- Tách quyền runtime, triển khai, migration và vận hành khẩn cấp.
- Kiểm chứng quyền bằng cả tình huống được phép và bị từ chối.
- Rà soát, xử lý ngoại lệ, phát hiện drift và thu hồi quyền có bằng chứng.

Các mô hình và policy trong bài là ví dụ minh họa độc lập với sản phẩm. Khi triển khai, phải ánh xạ sang cơ chế phân quyền thực tế của hệ thống đích; không coi cú pháp minh họa là cấu hình có thể áp dụng trực tiếp.

## 1. Service account permission là gì?

Service account là định danh dành cho workload như ứng dụng, job, pipeline hoặc tác vụ tự động. Permission là quyền thực hiện hành động cụ thể trên một phạm vi tài nguyên.

Một yêu cầu truy cập có thể được mô tả bằng bốn thành phần:

> Chủ thể → hành động → tài nguyên → điều kiện thực hiện.

Ví dụ:

- Chủ thể: định danh của job xuất báo cáo production.
- Hành động: đọc tập dữ liệu đã được duyệt.
- Tài nguyên: một view báo cáo cụ thể.
- Điều kiện: sử dụng qua đường kết nối được chấp thuận và trong môi trường phù hợp.

Một mô tả khác:

- Chủ thể: định danh của dịch vụ xuất báo cáo.
- Hành động: ghi đối tượng kết quả.
- Tài nguyên: vùng lưu trữ báo cáo thuộc đúng dịch vụ.
- Điều kiện: chỉ tạo nội dung trong phạm vi được duyệt, theo các khả năng kiểm soát mà nền tảng hỗ trợ.

“Cho phép truy cập database” hoặc “có quyền storage” là mô tả quá rộng. Nó chưa cho biết có được đọc, sửa, xóa, liệt kê, thay policy hoặc cấp quyền cho người khác hay không.

### 1.1. Authentication không thay thế authorization

Authentication xác minh chủ thể; authorization đánh giá yêu cầu truy cập của chủ thể đó.

Đưa mật khẩu vào vault, dùng chứng thư hoặc lấy credential ngắn hạn giúp quản lý cách workload chứng minh định danh. Những biện pháp này không tự làm giảm permission.

Nếu một credential được bảo vệ tốt nhưng gắn với quyền quản trị toàn hệ thống, một workload bị chiếm quyền vẫn có thể hành động trong phạm vi quản trị đó. PAM cần kiểm soát cả credential lẫn quyền được sử dụng sau khi xác thực.

### 1.2. Có hai mặt quyền cần xem xét

Khi nói “quyền của service account”, cần phân biệt:

1. **Quyền mà service account có trên tài nguyên:** đọc dữ liệu, ghi kết quả, gọi API, triển khai hoặc quản lý cấu hình.
2. **Quyền của chủ thể khác đối với service account:** đọc credential, dùng định danh, gắn định danh vào workload, sửa cấu hình hoặc thay đổi quyền của nó.

Một tài khoản có quyền runtime hẹp vẫn có thể trở thành mục tiêu nếu nhiều người hoặc pipeline được phép sử dụng định danh của nó. Ngược lại, người không có quyền đọc secret vẫn có thể hành động dưới định danh đó nếu nền tảng cho phép giả mạo hoặc ủy quyền theo một cơ chế khác.

Vì vậy, kiểm kê permission phải nhìn cả **tài khoản được làm gì** và **ai có thể điều khiển việc sử dụng tài khoản**.

## 2. Từ nhu cầu workload đến quyền tối thiểu

Least privilege không có nghĩa là cấp ít quyền đến mức workload liên tục lỗi. Nó có nghĩa là chỉ cấp các hành động cần thiết, trên phạm vi cần thiết, trong thời gian và điều kiện phù hợp với nhiệm vụ.

Một cách làm thực tế là bắt đầu từ từng tác vụ thay vì từ tên role có sẵn.

Giả sử job **report-export-prod** thực hiện:

1. Đọc dữ liệu từ một view báo cáo đã được phê duyệt.
2. Tạo file kết quả trong vùng lưu trữ của dịch vụ.
3. Ghi log và trạng thái xử lý.
4. Kết thúc phiên chạy.

Từ đó lập bảng quyền:

| Tác vụ | Quyền cần xem xét | Phạm vi dự kiến | Không mặc định cấp |
|---|---|---|---|
| Đọc dữ liệu báo cáo | Đọc view được duyệt | Đúng đối tượng dữ liệu | Đọc toàn bộ cơ sở dữ liệu |
| Xuất kết quả | Tạo hoặc ghi kết quả theo thiết kế | Vùng kết quả của dịch vụ | Xóa dữ liệu của dịch vụ khác |
| Ghi log | Gửi log hoặc sự kiện theo cơ chế triển khai | Đích log được chỉ định | Xóa hoặc sửa lịch sử log |
| Đọc cấu hình cần thiết | Đọc các mục cấu hình được phép | Đúng namespace hoặc đối tượng | Đọc mọi secret trong môi trường |

Không thêm quyền quản trị chỉ để tránh phải phân tích lỗi permission. Nếu chưa biết quyền nào cần thiết, phải điều tra yêu cầu cụ thể trong môi trường kiểm thử và hoàn thiện mô hình.

### 2.1. Ba câu hỏi cho từng quyền

Với mỗi quyền đề xuất, hãy hỏi:

- **Vì sao cần?** Liên kết được với tác vụ nào?
- **Cần ở đâu?** Có giới hạn được tài nguyên, môi trường hoặc tenant không?
- **Cần trong bao lâu?** Thường trực cho runtime hay chỉ trong một lần thay đổi?

Nếu không gắn được một quyền với nhu cầu đã được chấp thuận, quyền đó là ứng viên cần loại bỏ hoặc làm rõ.

### 2.2. Xem xét dữ liệu, không chỉ thao tác kỹ thuật

Quyền đọc không phải lúc nào cũng rủi ro thấp. Một service account chỉ có quyền đọc nhưng đọc được toàn bộ dữ liệu nhạy cảm vẫn có phạm vi ảnh hưởng lớn.

Tương tự, quyền ghi vào một vùng kết quả có thể ảnh hưởng hệ thống phía sau nếu consumer tin tưởng nội dung được ghi. Cần xem tài nguyên nằm ở đâu trong luồng xử lý và ai sử dụng kết quả.

Khi nền tảng hỗ trợ, có thể giới hạn theo đối tượng dữ liệu, view, namespace hoặc ranh giới nghiệp vụ. Cần kiểm chứng hiệu lực bảo vệ thực tế và các quyền liên quan; không giả định rằng chỉ đặt tên một view hay prefix là đã ngăn mọi đường truy cập khác.

## 3. Quyền được gán và quyền hiệu lực

Danh sách role trực tiếp là đầu vào, chưa phải kết luận về khả năng truy cập thực tế.

Quyền hiệu lực có thể bị ảnh hưởng bởi:

- Policy gán trực tiếp cho định danh.
- Thành viên nhóm hoặc role.
- Quyền kế thừa từ phạm vi cha.
- Policy gắn với tài nguyên.
- Quyền được ủy quyền qua định danh khác.
- Các giới hạn, điều kiện hoặc quy tắc từ chối.
- Trạng thái phiên, credential và cơ chế cache.
- Kiểm soát tại chính hệ thống đích.

Cách kết hợp các lớp này phụ thuộc vào nền tảng. Không có một công thức cộng quyền hoặc ưu tiên từ chối duy nhất áp dụng cho mọi hệ thống.

### 3.1. Ví dụ quyền trực tiếp trông hẹp nhưng quyền hiệu lực rộng

Một service account chỉ được gán role đọc trên một tài nguyên. Tuy nhiên, nó còn thuộc nhóm được cấp quyền quản trị ở phạm vi cha.

Nếu cơ chế phân quyền của nền tảng cho phép kế thừa đó, khả năng truy cập thực tế có thể lớn hơn role đọc trực tiếp. Việc chỉ xuất danh sách quyền gán tại tài nguyên sẽ bỏ sót đường cấp quyền này.

Một ví dụ khác: tài khoản được phép lấy credential của một định danh đặc quyền hơn. Quyền hiện tại không trực tiếp ghi “quản trị hệ thống”, nhưng đường truy cập gián tiếp có thể dẫn tới hành động quản trị.

### 3.2. Cần xác minh đường cấp quyền

Khi rà soát một quyền nhạy cảm, cần ghi nhận:

- Quyền đến từ đâu.
- Áp dụng trên phạm vi nào.
- Điều kiện nào thực sự được đánh giá.
- Có định danh trung gian hay quan hệ tin cậy nào không.
- Bằng chứng kiểm tra ở hệ thống đích là gì.

Kết luận “không còn role admin trực tiếp” không đủ nếu vẫn còn một đường khác đạt khả năng tương đương.

### 3.3. Mạng và permission là các lớp bổ sung

Giới hạn nguồn kết nối có thể giảm khả năng tiếp cận nhưng không thay thế phân quyền.

Một workload nằm trong mạng được phép vẫn phải có permission phù hợp. Nếu workload đó bị chiếm quyền, kẻ tấn công có thể sử dụng vị trí mạng của nó để gửi yêu cầu dưới định danh đang được gán.

Ngược lại, một yêu cầu bị chặn ở mạng chưa chứng minh policy authorization tại đích đã giới hạn đúng. Kiểm thử cần phân biệt lớp nào gây ra kết quả từ chối.

## 4. Tách quyền theo tác vụ và môi trường

Một lỗi thiết kế phổ biến là dùng một service account cho cả triển khai, migration và runtime.

| Giai đoạn | Nhu cầu điển hình | Rủi ro nếu dùng chung với runtime |
|---|---|---|
| Build | Đọc mã, lấy dependency, tạo artifact | Ứng dụng có thể tiếp cận tài nguyên build không cần thiết |
| Publish | Ghi artifact vào kho được duyệt | Workload runtime có thể thay nội dung sẽ được triển khai |
| Deploy | Cập nhật workload và cấu hình triển khai | Lỗi ứng dụng có thể trở thành thay đổi hạ tầng |
| Migration | Thay đổi cấu trúc dữ liệu theo kế hoạch | Runtime có thể phá hỏng cấu trúc ngoài nhu cầu xử lý |
| Runtime | Thực hiện chức năng nghiệp vụ | Thường cần quyền hẹp và ổn định hơn |
| Emergency maintenance | Thao tác được ủy quyền trong tình huống đặc biệt | Quyền khẩn cấp trở thành quyền thường trực |

Tách định danh giúp gắn từng tập quyền với nhiệm vụ, owner, thời gian hoạt động và bằng chứng riêng. Định danh triển khai cũng cần được bảo vệ vì nó có thể ảnh hưởng tới workload và định danh runtime.

### 4.1. Tách production khỏi môi trường khác

Định danh dùng trong development không nên mặc nhiên truy cập production. Việc có cùng tên dịch vụ không có nghĩa các môi trường có cùng mức tin cậy.

Một mô hình có thể sử dụng:

- Định danh runtime riêng cho production.
- Định danh riêng cho kiểm thử.
- Định danh triển khai production được kiểm soát qua workflow.
- Quyền migration chỉ khả dụng khi thực hiện thay đổi được duyệt.

Mức tách cụ thể phụ thuộc kiến trúc, nhưng ranh giới cần rõ và có thể kiểm chứng. Không sao chép credential production vào môi trường thấp hơn để làm kiểm thử thuận tiện.

### 4.2. Giới hạn thời gian khi phù hợp

Tác vụ thường trực cần quyền đủ để vận hành bình thường. Tác vụ hiếm gặp hoặc có đặc quyền cao nên được đánh giá khả năng cấp quyền theo thời gian hoặc theo yêu cầu, nếu nền tảng hỗ trợ.

JIT có thể giảm thời gian tồn tại đặc quyền, nhưng không thay thế việc giới hạn hành động và tài nguyên. Một quyền quản trị toàn hệ thống được cấp ngắn hạn vẫn có thể gây tác động lớn trong khoảng thời gian đó.

Cần xác định điều gì hết hạn: quyền gán, khả năng lấy credential hay chính credential. Chúng không luôn có cùng vòng đời.

### 4.3. Không tự động áp dụng JEA bằng một script chạy toàn quyền

Ý tưởng chỉ cho phép một tập thao tác quản trị giới hạn có thể hữu ích cho tác vụ tự động. Tuy nhiên, một script chỉ cung cấp vài tham số nhưng có thể bị sửa hoặc chèn lệnh vẫn có thể mở đường tới quyền của tiến trình thực thi.

Muốn giới hạn thao tác có hiệu lực, cần kiểm soát cả đầu vào, mã thực thi, người được sửa mã và quyền của thành phần chạy tác vụ. Tên gọi “limited automation” không tự tạo ra ranh giới bảo mật.

## 5. Nhận diện quyền quản trị và đường tăng quyền gián tiếp

Quyền nhạy cảm không chỉ gồm đọc, ghi hoặc xóa dữ liệu. Các khả năng điều khiển định danh, cấu hình hoặc mã thực thi có thể tạo ảnh hưởng tương đương.

| Khả năng | Vì sao cần xem xét đặc biệt |
|---|---|
| Cấp role hoặc thay policy | Có thể mở rộng quyền của chính mình hoặc chủ thể khác |
| Đọc hoặc xuất credential | Có thể sử dụng định danh khác |
| Sử dụng hoặc giả mạo một định danh khác | Có thể nhận quyền của định danh được ủy quyền |
| Gắn định danh đặc quyền vào workload | Có thể đưa quyền vào môi trường do người khác điều khiển |
| Sửa mã, script hoặc artifact được chạy dưới quyền cao | Có thể tác động hành vi của tiến trình đặc quyền |
| Sửa cấu hình triển khai hoặc tham số tác vụ | Có thể thay luồng thực thi hoặc đích dữ liệu |
| Quản lý khóa dùng bảo vệ dữ liệu | Có thể ảnh hưởng quyền tiếp cận hoặc tính sẵn sàng của dữ liệu |
| Xóa hoặc tắt cơ chế audit | Có thể làm giảm khả năng phát hiện và điều tra |

Các đường trên chỉ dẫn tới tăng quyền khi các điều kiện cần thiết tồn tại. Phải kiểm tra mô hình tin cậy, quyền liên quan và cơ chế thực thi; không suy ra khả năng khai thác chỉ từ một tên permission.

### 5.1. Ví dụ về chuỗi ảnh hưởng

Giả sử một định danh triển khai được phép cập nhật cấu hình của workload đang chạy dưới một service account đặc quyền. Nếu nó có thể đưa mã tùy ý vào workload và không có kiểm soát bổ sung ngăn chặn, nó có thể tác động tới những hành động thực hiện dưới định danh runtime.

Khi đó, chỉ rà soát quyền trên dữ liệu của tài khoản triển khai sẽ thiếu. Cần xem cả quyền sửa workload và mức quyền của định danh gắn với workload đó.

~~~mermaid
flowchart LR
    A[Định danh triển khai] -->|Có thể sửa triển khai| B[Workload]
    B -->|Dùng định danh được gán| C[Service account runtime]
    C -->|Có quyền đã cấp| D[Tài nguyên nhạy cảm]
~~~

Sơ đồ biểu diễn một quan hệ cần phân tích, không khẳng định mọi quyền triển khai đều cho phép khai thác mọi quyền runtime.

### 5.2. Owner không được mặc nhiên tự duyệt tăng quyền

Owner chịu trách nhiệm về nhu cầu sử dụng tài khoản, nhưng việc cấp thêm quyền cần đúng thẩm quyền của tài nguyên và chính sách phân tách nhiệm vụ.

Tách rõ:

- Bên yêu cầu giải thích nhu cầu.
- Owner xác nhận sự phù hợp với dịch vụ.
- Bên có thẩm quyền phê duyệt phạm vi truy cập.
- Custodian hoặc quản trị viên thực hiện.
- Bên kiểm tra xác nhận kết quả theo yêu cầu rủi ro.

Không phải mọi thay đổi đều cần cùng số bước thủ công. Có thể tự động hóa những quy tắc đã được phê duyệt, nhưng phải giữ được điều kiện áp dụng và bằng chứng quyết định.

## 6. Mô hình policy minh họa

Dưới đây là ví dụ dữ liệu mô tả ý định cấp quyền. **Đây không phải cú pháp của cloud IAM, database hay một sản phẩm PAM cụ thể. Không áp dụng trực tiếp lên hệ thống.**

~~~yaml
permission_intent:
  subject: svc-report-export-prod
  environment: production
  purpose: Xuat bao cao da duoc phe duyet
  allowed_operations:
    - action: read
      resource: reporting.approved_export_view
    - action: create_report
      resource: report-output/reporting-export/
    - action: append_event
      resource: telemetry/report-export
  operations_not_justified:
    - manage_identity
    - grant_permissions
    - modify_database_schema
    - read_unrelated_secrets
    - delete_other_service_outputs
  decision_references:
    request: request-demo-072
    owner_acceptance: acceptance-demo-018
    resource_approval: approval-demo-033
  review:
    trigger: Service or permission change
    next_due: Theo chinh sach noi bo
~~~

Danh sách **operations_not_justified** là tài liệu hóa các hành động không có nhu cầu. Nó **không phải một tập lệnh từ chối được thực thi**.

Để biến ý định thành kiểm soát thực tế, phải:

1. Ánh xạ từng hành động sang permission hoặc role thật của nền tảng.
2. Xác định tài nguyên và ranh giới mà nền tảng thực sự hỗ trợ.
3. Kiểm tra quyền kế thừa, policy tài nguyên và đường ủy quyền.
4. Áp dụng thay đổi theo quy trình.
5. Kiểm chứng kết quả authorization tại hệ thống đích.
6. Lưu phiên bản cấu hình và bằng chứng kiểm tra.

### 6.1. Role có sẵn hay role tùy chỉnh?

Role có sẵn giúp giảm chi phí quản lý nhưng có thể rộng hơn nhu cầu. Role tùy chỉnh có thể hẹp hơn nhưng làm tăng trách nhiệm duy trì, kiểm tra và theo dõi thay đổi.

Quyết định nên dựa trên:

- Các hành động thực sự cần.
- Khả năng giới hạn phạm vi tài nguyên.
- Những quyền thừa trong role.
- Tính ổn định và khả năng kiểm tra.
- Cơ chế quản trị khi quyền hoặc dịch vụ thay đổi.

Không chọn role chỉ dựa vào tên như “viewer”, “operator” hoặc “service user”. Phải xem nội dung và cách role áp dụng trong hệ thống cụ thể.

### 6.2. Điều kiện chỉ có giá trị khi được thực thi

Một điều kiện như “chỉ production” hoặc “chỉ workload đã đăng ký” cần được nền tảng đánh giá bằng thuộc tính đáng tin cậy.

Nếu chính chủ thể có thể tự sửa nhãn hoặc thuộc tính đang được dùng để cấp quyền, phải xem xét khả năng vượt ranh giới. Tương tự, ghi điều kiện trong ticket không có nghĩa hệ thống đã thực thi điều kiện đó.

Khi nền tảng không hỗ trợ một ranh giới cần thiết, có thể phải đổi cấu trúc tài nguyên, tách định danh, thêm điểm kiểm soát hoặc ghi nhận ngoại lệ có thời hạn. Không nên tuyên bố đã giới hạn trong khi cơ chế thực tế chưa làm được.

## 7. Quy trình cấp và thay đổi permission

### Bước 1 — Xác nhận định danh và owner

Xác định ID tài khoản, workload, môi trường, owner và custodian. Không dựa duy nhất vào tên hiển thị vì có thể tồn tại tài khoản trùng tên ở các hệ thống khác nhau.

### Bước 2 — Liệt kê tác vụ và tài nguyên

Mỗi quyền phải gắn với một tác vụ cụ thể. Phân biệt quyền runtime với quyền tạo tài nguyên, triển khai hoặc xử lý khẩn cấp.

### Bước 3 — Đánh giá phạm vi và đường ảnh hưởng

Xem quyền trực tiếp, kế thừa, quan hệ tin cậy, khả năng quản lý định danh khác và việc tác động tới workload có đặc quyền cao hơn.

### Bước 4 — Phê duyệt đúng thẩm quyền

Lưu bên yêu cầu, lý do, phạm vi, thời hạn và người phê duyệt. Với quyền vượt chuẩn, ghi ngoại lệ và kế hoạch giảm quyền.

### Bước 5 — Triển khai có thể truy nguyên

Áp dụng cấu hình bằng quy trình kiểm soát thay đổi. Nếu dùng cấu hình khai báo, cần biết phiên bản nào đã được triển khai, không chỉ phiên bản đang nằm trong kho mã.

### Bước 6 — Kiểm chứng bằng định danh thực tế

Kiểm tra chức năng cần thiết và các ranh giới phải từ chối. Phải biết bài kiểm tra thực sự chạy dưới service account nào.

### Bước 7 — Theo dõi và rà soát

Ghi nhận quyền hiệu lực, bằng chứng kiểm tra và thời điểm cần đánh giá lại. Thay đổi consumer hoặc môi trường phải kích hoạt rà soát khi phù hợp.

## 8. Kiểm chứng permission

Một workload chạy thành công chỉ chứng minh nó có đủ quyền cho những đường xử lý đã được thực hiện. Điều đó chưa chứng minh tập quyền là tối thiểu.

Cần kết hợp **kiểm tra cho phép** và **kiểm tra từ chối**.

### 8.1. Ma trận kiểm tra cho job xuất báo cáo

| Tình huống | Kết quả mong đợi | Điều cần xác minh |
|---|---|---|
| Đọc view báo cáo được duyệt | Cho phép | Đúng tài khoản, đúng đối tượng |
| Tạo báo cáo trong vùng được duyệt | Cho phép | Đúng ranh giới tài nguyên |
| Đọc dữ liệu ngoài phạm vi | Từ chối | Từ chối do authorization phù hợp |
| Ghi vào vùng của dịch vụ khác | Từ chối | Không có quyền kế thừa ngoài ý muốn |
| Thay đổi cấu trúc dữ liệu | Từ chối | Không dùng nhầm định danh migration |
| Thêm quyền cho chính mình | Từ chối | Không có đường quản lý policy ngoài nhu cầu |
| Đọc secret không thuộc dịch vụ | Từ chối | Không có quyền đọc rộng hoặc qua trung gian |
| Dùng định danh production từ workload không được duyệt | Từ chối theo thiết kế | Kiểm tra quan hệ tin cậy và đường cấp credential |

Không thực hiện thao tác phá hủy trên production chỉ để chứng minh một quyền bị từ chối. Dùng môi trường thử, tài nguyên giả lập hoặc cơ chế đánh giá policy phù hợp với nền tảng.

### 8.2. Phân biệt kết quả thực thi và mô phỏng

Một công cụ mô phỏng có thể giúp phân tích policy nhưng không nhất thiết bao phủ mọi kiểm soát thực tế: mạng, hệ thống đích, trạng thái phiên hoặc điều kiện môi trường.

Ngược lại, một yêu cầu thực tế có thể thất bại vì tài nguyên không tồn tại hoặc tham số sai, chứ không phải vì permission đã được chặn.

Khi ghi bằng chứng, cần nêu:

- Công cụ hoặc phương thức kiểm tra.
- Chủ thể được sử dụng.
- Hành động và tài nguyên.
- Lớp kiểm soát đã được đánh giá.
- Kết quả và giới hạn của kết luận.

“Request failed” là bằng chứng quá yếu nếu không biết nguyên nhân thất bại.

### 8.3. Mã giả cho kiểm tra quyền

Ví dụ dưới đây là mã giả mô tả ý tưởng trong môi trường kiểm thử; không phải lệnh gọi một API có thật:

~~~text
subject = test_identity("svc-report-export-prod")

assert_allowed(
    subject,
    action = "read",
    resource = "reporting.approved_export_view"
)

assert_allowed(
    subject,
    action = "create_report",
    resource = "test-report-output/reporting-export/sample"
)

assert_authorization_denied(
    subject,
    action = "read",
    resource = "unrelated_dataset"
)

assert_authorization_denied(
    subject,
    action = "grant_permissions",
    resource = "test_identity_scope"
)
~~~

Hàm kiểm tra từ chối phải phân biệt lỗi authorization với lỗi kết nối, lỗi đầu vào hoặc tài nguyên không tồn tại. Nếu dùng credential của người quản trị thay cho service account, toàn bộ kết luận về tài khoản đang xét có thể sai.

### 8.4. Bằng chứng không được chứa secret

Có thể lưu tham chiếu tài khoản, policy, tài nguyên thử, kết quả và thời điểm. Không đưa mật khẩu, bearer token, private key hoặc chuỗi kết nối chứa secret vào log kiểm thử.

Nếu cần điều tra lỗi cấp credential, ưu tiên metadata và mã sự kiện đã được xử lý phù hợp. Không bật debug làm lộ credential chỉ để dễ chứng minh danh tính.

## 9. Rà soát quyền và phát hiện permission drift

Permission drift xảy ra khi trạng thái quyền thực tế lệch khỏi trạng thái đã được chấp thuận hoặc kỳ vọng.

Ví dụ:

- Một quản trị viên cấp role rộng trong lúc xử lý lỗi và quên thu hồi.
- Tài khoản được thêm vào nhóm có quyền kế thừa.
- Tài nguyên chuyển sang phạm vi có policy khác.
- Một role thay đổi nội dung.
- Pipeline mới sử dụng tài khoản ngoài consumer đã đăng ký.
- Quyền khẩn cấp tồn tại lâu hơn thời hạn được duyệt.

Rà soát không nên chỉ hỏi owner “còn dùng tài khoản không”. Cần xem **những quyền nào còn cần thiết** và **chúng được cấp qua những đường nào**.

### 9.1. Kết hợp trạng thái mong muốn, trạng thái thực tế và hoạt động quan sát được

Ba nguồn này trả lời các câu hỏi khác nhau:

| Nguồn | Trả lời | Giới hạn |
|---|---|---|
| Hồ sơ phê duyệt hoặc cấu hình mong muốn | Quyền nào đã được chấp thuận? | Có thể chưa phản ánh triển khai thực tế |
| Cấu hình và quyền hiệu lực thực tế | Tài khoản hiện có thể làm gì? | Cần phân tích đầy đủ các đường cấp quyền |
| Telemetry sử dụng | Những hành động nào đã được quan sát? | Không chứng minh mọi quyền chưa thấy dùng đều dư |

Đối chiếu ba nguồn giúp phát hiện cả quyền thiếu, quyền dư và sai lệch quy trình.

### 9.2. Không xóa quyền chỉ vì chưa thấy sử dụng trong một khoảng ngắn

Một tác vụ có thể chỉ chạy theo quý, theo sự kiện hoặc trong phục hồi. Log có thể thiếu, thời gian lưu ngắn hoặc không bao phủ mọi hành động.

Quyền chưa quan sát thấy sử dụng là một tín hiệu để điều tra. Trước khi thu hồi, cần xác nhận với owner, xem consumer, lịch hoạt động và tác động. Với quyền rủi ro cao, có thể ưu tiên chuyển sang cấp theo yêu cầu thay vì giữ thường trực.

### 9.3. Ngoại lệ cần có giới hạn

Nếu hệ thống cũ chưa hỗ trợ phân quyền đủ hẹp, hồ sơ ngoại lệ nên chỉ rõ:

- Quyền nào đang rộng hơn nhu cầu.
- Vì sao chưa thu hẹp được.
- Owner và người có thẩm quyền chấp nhận ngoại lệ.
- Thời hạn và mốc rà soát.
- Kiểm soát bổ sung có thể thực thi.
- Kế hoạch xử lý nguyên nhân.

Giám sát tăng cường có thể giúp phát hiện lạm dụng nhưng không làm quyền rộng trở thành quyền tối thiểu. Cần mô tả đúng rủi ro còn lại.

## 10. Thu hồi permission và rotation credential

Thu hồi quyền và rotation giải quyết những vấn đề khác nhau.

- Rotation thay đổi hoặc cấp lại phương tiện xác thực.
- Thu hồi permission thay đổi khả năng được phép thực hiện hành động.
- Vô hiệu hóa tài khoản hoặc chấm dứt quan hệ tin cậy tác động tới khả năng sử dụng định danh.
- Kết thúc phiên hoặc credential đã cấp có thể cần cơ chế riêng.

Đổi secret không tự sửa một policy quá rộng. Xóa một role cũng không bảo đảm mọi phiên hoặc credential đã phát hành đều hết hiệu lực ngay.

### 10.1. Quy trình thu hồi quyền có kiểm chứng

1. Xác định đúng quyền, đường cấp và tài nguyên.
2. Xác nhận nhu cầu đã kết thúc hoặc có quyết định xử lý.
3. Đánh giá tác động tới các consumer.
4. Thu hồi tại nguồn cấp quyền phù hợp.
5. Xem các phiên, token hoặc credential liên quan theo cơ chế nền tảng.
6. Kiểm tra lại những hành động trước đó được phép.
7. Xác nhận chức năng còn cần thiết vẫn hoạt động.
8. Lưu thay đổi, kết quả và vấn đề còn lại.

Thời gian lan truyền policy, cơ chế cache và vòng đời token phụ thuộc hệ thống. Phải kiểm tra thực tế và dùng tài liệu nền tảng khi triển khai; không giả định một khoảng thời gian cố định áp dụng chung.

### 10.2. Khi credential nghi bị lộ

Cần đồng thời xem phạm vi quyền, khả năng tiếp tục lấy credential, phiên đang tồn tại và những hành động đã xảy ra.

Nếu chỉ đổi mật khẩu nhưng nguồn bị chiếm quyền vẫn lấy được credential mới, khả năng lạm dụng có thể tiếp tục. Nếu chỉ thu hẹp một role nhưng còn đường ủy quyền khác, rủi ro cũng chưa được xử lý đầy đủ.

Containment cần theo thẩm quyền ứng phó sự cố, phối hợp owner và custodian để hiểu tác động. Trong trường hợp khẩn cấp, đường escalation không nên khiến mọi hành động phải chờ một cá nhân duy nhất.

## 11. Tình huống thực tế: tài khoản runtime có quyền migration

### Bối cảnh

Ứng dụng báo cáo dùng một service account để đọc dữ liệu và tạo kết quả. Khi triển khai phiên bản đầu tiên, nhóm kỹ thuật dùng cùng tài khoản để tạo cấu trúc dữ liệu.

Sau khi triển khai, quyền thay đổi cấu trúc vẫn được giữ lại vì “có thể cần ở lần nâng cấp sau”. Credential đã nằm trong vault và rotation theo quy trình, nên nhóm cho rằng rủi ro đã được kiểm soát.

### Phân tích

Vault và rotation cải thiện quản lý credential nhưng không thay đổi permission. Nếu ứng dụng bị chiếm quyền, người tấn công có thể có khả năng sử dụng các quyền migration mà runtime không cần.

Cần xác định quyền thực tế, vì tên role hoặc mô tả ban đầu có thể không đầy đủ. Đồng thời kiểm tra ai có quyền lấy credential, thay pipeline và sửa cấu hình ứng dụng.

### Phương án điều chỉnh

**Tách nhiệm vụ.** Định danh runtime chỉ giữ quyền cần cho chức năng báo cáo. Migration sử dụng định danh riêng qua workflow thay đổi được kiểm soát.

**Thu hẹp phạm vi.** Runtime chỉ đọc dữ liệu đã được duyệt và ghi kết quả vào vùng của dịch vụ. Không cấp quyền quản lý policy hoặc định danh khác nếu không có nhu cầu.

**Giới hạn migration.** Đánh giá phạm vi tài nguyên và thời gian cấp quyền phù hợp với nền tảng. Không để quyền phục vụ thay đổi trở thành quyền thường trực của ứng dụng.

**Kiểm chứng.** Trong môi trường thử, xác nhận runtime vẫn xuất báo cáo và bị từ chối với thao tác thay đổi cấu trúc. Kiểm tra bằng đúng định danh, không bằng tài khoản của người triển khai.

**Triển khai và theo dõi.** Thực hiện thay đổi có kế hoạch, kiểm tra consumer, quan sát lỗi và xác nhận quyền dư đã được thu hồi ở các đường cấp liên quan.

### Bằng chứng cần có

- Nhu cầu quyền runtime đã được owner xác nhận.
- Phê duyệt phạm vi tài nguyên.
- Cấu hình trước và sau hoặc tham chiếu thay đổi.
- Kết quả kiểm tra cho phép và từ chối.
- Danh tính thực tế dùng trong kiểm tra.
- Kết quả xác nhận sau triển khai.
- Ngoại lệ còn tồn tại và thời hạn xử lý, nếu có.

## 12. Sai lầm thường gặp

### Cấp admin để giải quyết mọi lỗi permission

Cách này có thể làm lỗi biến mất nhưng che giấu quyền thực sự cần thiết. Cần điều tra hành động bị từ chối, ánh xạ nhu cầu và kiểm tra phạm vi thay vì giữ role rộng.

### Chỉ xem quyền gán trực tiếp

Nhóm, role kế thừa, policy tài nguyên và quan hệ ủy quyền có thể tạo quyền khác. Rà soát phải tìm được đường cấp quyền hiệu lực.

### Dùng cùng tài khoản cho nhiều workload không liên quan

Khó xác định quyền thuộc nhu cầu nào, khó thu hồi và khó phân biệt hành vi khi điều tra. Cần đánh giá tách theo ranh giới nhiệm vụ, môi trường và owner.

### Coi quyền đọc luôn an toàn

Quyền đọc dữ liệu nhạy cảm hoặc credential có thể gây hậu quả lớn. Phải xem nội dung và phạm vi tài nguyên, không chỉ tên hành động.

### Tài liệu ghi cấm nhưng hệ thống chưa chặn

Policy ý định không phải policy thực thi. Cần ánh xạ cấu hình, kiểm tra quyền hiệu lực và xác minh tại hệ thống đích.

### Thử thành công bằng credential người quản trị

Kết quả đó không chứng minh service account có đúng quyền. Mỗi kiểm tra cần xác nhận danh tính và đường lấy credential.

### Chỉ kiểm thử các đường được phép

Workload chạy được chưa chứng minh không có quyền dư. Cần kiểm tra các ranh giới từ chối quan trọng bằng phương thức phù hợp.

### Tin rằng token ngắn hạn đồng nghĩa quyền hẹp

Token có thời hạn ngắn vẫn có thể mang quyền rộng. Cần quản lý riêng thời gian và phạm vi.

### Xóa quyền nhưng không kiểm tra phiên và đường cấp khác

Có thể còn phiên hiệu lực, policy kế thừa hoặc quan hệ ủy quyền. Thu hồi phải bao phủ các cơ chế liên quan và có readback ở hệ thống đích.

## 13. Bài tập thực hành

Một dịch vụ đồng bộ danh mục có ba tác vụ:

- Đọc một tập dữ liệu nguồn đã được duyệt.
- Cập nhật danh mục của chính dịch vụ.
- Gửi trạng thái vào hệ thống giám sát.

Service account hiện có quyền quản trị trên nguồn dữ liệu, được ghi vào mọi vùng lưu trữ của nhóm và có thể đọc toàn bộ secret của môi trường.

Hãy làm trên dữ liệu và tài nguyên mô phỏng:

1. Lập ma trận chủ thể, hành động, tài nguyên và điều kiện cho từng tác vụ.
2. Xác định những quyền chưa có lý do nghiệp vụ.
3. Tách quyền runtime khỏi quyền cần cho triển khai hoặc bảo trì.
4. Nêu các đường cấp quyền gián tiếp cần kiểm tra.
5. Thiết kế ít nhất hai kiểm tra cho phép và ba kiểm tra từ chối.
6. Xác định bằng chứng cần lưu sau khi thay đổi.
7. Nêu cách xử lý nếu một ranh giới cần thiết chưa được nền tảng hỗ trợ.

### Gợi ý đánh giá

Một phương án tốt không chỉ thay role “admin” bằng role tên có vẻ nhỏ hơn. Nó phải chỉ rõ những hành động được giữ, phạm vi tài nguyên và đường cấp quyền đã được kiểm tra.

Quyền đọc secret cần được thu hẹp tới những mục thực sự cần cho workload hoặc thay đổi cơ chế cấp phát nếu phù hợp. Nếu không cần secret cho một tác vụ, không nên giữ quyền chỉ để dự phòng.

Các phép kiểm tra từ chối có thể gồm truy cập dữ liệu ngoài phạm vi, ghi sang vùng của dịch vụ khác và thay đổi quyền của chính tài khoản. Phải phân biệt kết quả từ chối authorization với lỗi do tài nguyên thử không tồn tại.

Nếu nền tảng chưa hỗ trợ giới hạn cần thiết, cần thiết kế lại ranh giới hoặc ghi ngoại lệ có trách nhiệm và thời hạn. Không tuyên bố đã đạt least privilege khi một quyền rộng vẫn còn tồn tại ngoài nhu cầu.

## 14. Câu hỏi tự kiểm tra

**1. Lưu credential trong vault có làm service account ít quyền hơn không?**

Không. Vault kiểm soát việc lưu và cấp credential. Permission tại hệ thống đích vẫn cần được thiết kế và quản lý riêng.

**2. Vì sao phải xem quyền hiệu lực thay vì chỉ xem role trực tiếp?**

Vì quyền có thể đến từ nhiều nguồn như nhóm, kế thừa, policy tài nguyên và quan hệ ủy quyền. Một đường cấp khác có thể làm phạm vi thực tế rộng hơn dự kiến.

**3. Vì sao định danh runtime không nên mặc nhiên giữ quyền migration?**

Runtime thường không cần thay đổi cấu trúc hoặc quản trị hệ thống. Dùng chung làm tăng tác động khi ứng dụng bị chiếm quyền và làm mờ trách nhiệm từng giai đoạn.

**4. Một tác vụ chạy thành công có chứng minh least privilege không?**

Không. Nó chỉ chứng minh đủ quyền cho những hành động đã được thực hiện. Cần kiểm tra cả những hành động phải bị từ chối và các đường cấp quyền khác.

**5. Có thể tự xóa mọi quyền chưa xuất hiện trong log gần đây không?**

Không nên. Cần xem mức bao phủ log, chu kỳ workload, hoạt động phục hồi và xác nhận của owner trước khi quyết định.

**6. Xóa role có bảo đảm mọi token đang tồn tại hết hiệu lực ngay không?**

Không thể giả định chung. Hiệu lực thu hồi phụ thuộc cơ chế policy, phiên và token của hệ thống; cần kiểm chứng theo nền tảng.

**7. Owner có được tự phê duyệt mọi quyền cho tài khoản của mình không?**

Không. Owner xác nhận nhu cầu của dịch vụ; việc chấp thuận quyền phải tuân theo thẩm quyền tài nguyên và yêu cầu phân tách nhiệm vụ.

**8. Vì sao cần xem ai có thể sử dụng hoặc điều khiển service account?**

Vì quyền lấy credential, dùng định danh, sửa workload hoặc thay quan hệ tin cậy có thể mở đường sử dụng các quyền của tài khoản dù chủ thể không có những quyền đó trực tiếp.

## 15. Điểm cần ghi nhớ

Permission của service account phải được giải thích bằng tác vụ, tài nguyên, điều kiện và vòng đời thực tế. Credential được quản lý tốt là một phần của PAM; phạm vi quyền hiệu lực và các đường điều khiển định danh cũng quan trọng như vậy.

Một mô hình kiểm soát có thể kiểm chứng cần biết quyền đến từ đâu, ai phê duyệt, workload nào sử dụng và làm thế nào xác nhận quyền đã bị thu hồi. Least privilege phải thể hiện trong khả năng thực tế của hệ thống, không chỉ trong tên role hoặc mô tả của ticket.

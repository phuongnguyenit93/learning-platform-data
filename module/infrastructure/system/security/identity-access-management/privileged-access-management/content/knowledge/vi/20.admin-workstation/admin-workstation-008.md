# Screen capture control trên máy trạm quản trị đặc quyền

## 1. Screen capture control là gì?

**Screen capture control** là tập biện pháp quản lý việc nội dung hiển thị bị chuyển thành ảnh, video hoặc luồng chia sẻ màn hình. Trong môi trường PAM, nội dung đó có thể xuất hiện trong SSH client, desktop quản trị, trình duyệt, công cụ database hoặc ứng dụng quản trị cục bộ trên PAW.

Mục tiêu có thể gồm:

- Giảm khả năng người dùng tạo bản sao ngoài luồng của dữ liệu nhạy cảm.
- Hạn chế công cụ hoặc tiến trình không được phép ghi lại màn hình.
- Kiểm soát việc chia sẻ nội dung phiên cho bên khác.
- Tạo dấu nhận diện phù hợp khi nội dung được hiển thị hoặc xuất có phép.
- Giữ recording kiểm toán trong một kho được quản lý.
- Cung cấp đường lấy bằng chứng chẩn đoán mà không phát tán dữ liệu thừa.

Một chức năng chặn screenshot không tự ngăn mọi cách ghi lại thông tin. Nội dung mà con người có thể nhìn thấy vẫn có thể bị chụp bằng thiết bị bên ngoài hoặc được ghi nhớ, chép lại.

Do đó, cần thiết kế theo phạm vi có thể thực thi và kiểm chứng, không dùng một nhãn “anti-screenshot” để khẳng định dữ liệu không thể rời môi trường quản trị.

## 2. Những hình thức ghi lại màn hình cần phân biệt

| Hình thức | Nguồn tạo bản sao | Điều cần quản lý |
|---|---|---|
| Ảnh chụp một cửa sổ | Ứng dụng hoặc chức năng OS | Nội dung, nơi lưu và quyền sử dụng |
| Ảnh toàn màn hình | Chức năng hệ thống hoặc công cụ khác | Nhiều cửa sổ, nhiều màn hình và dữ liệu ngoài phiên |
| Video màn hình | Công cụ ghi hình | Luồng dữ liệu liên tục và storage |
| Chia sẻ trong cuộc họp | Ứng dụng hội nghị | Người xem, khả năng ghi lại và phạm vi chia sẻ |
| Hỗ trợ từ xa | Công cụ điều khiển endpoint | Quyền xem, thao tác và lưu bản ghi |
| Capture tại host hoặc nền tảng ảo hóa | Thành phần ngoài guest | Ranh giới mà guest không tự kiểm soát được |
| Ảnh hoặc video bằng camera ngoài | Thiết bị độc lập | Ngoài phạm vi của kiểm soát screenshot trên OS |
| Recording PAM | Gateway, proxy hoặc thành phần ghi nhận được thiết kế | Mục đích bằng chứng, quyền xem và vòng đời dữ liệu |

Ngoài ảnh chính, nội dung có thể xuất hiện trong preview, thumbnail, màn hình chuyển ứng dụng hoặc dữ liệu hỗ trợ. Khả năng kiểm soát những bề mặt đó phụ thuộc ứng dụng, OS và display stack.

Trước khi đặt policy, phải biết mình đang kiểm soát hình thức nào và ở đâu.

## 3. Phân biệt chặn capture với recording kiểm toán

### 3.1. Hai mục đích khác nhau

Chặn capture thường nhằm giảm bản sao do người dùng hoặc công cụ ngoài luồng tạo ra. Recording PAM nhằm tạo bằng chứng hoạt động qua một cơ chế đã được quản lý.

Một thiết kế có thể đồng thời yêu cầu:

~~~text
Không cho công cụ thông thường chụp nội dung phiên.
Vẫn ghi nhận phiên qua đường kiểm toán được phép.
Chỉ cho người có thẩm quyền truy xuất recording.
~~~

Ba yêu cầu này phải được kiểm chứng riêng.

### 3.2. Vị trí ghi nhận có ý nghĩa

Recording có thể lấy dữ liệu tại gateway, phía server, endpoint hoặc một thành phần khác. Một cơ chế bảo vệ capture có thể làm đường ghi nhận cùng dùng bề mặt đó nhận nội dung trống, trong khi đường khác vẫn nhìn thấy.

Ngược lại, watermark phủ ở client có thể xuất hiện trong screenshot tại client nhưng không nằm trong recording lấy trước điểm phủ đó.

Không mặc định recording luôn được miễn trừ, luôn đầy đủ hoặc luôn có watermark. Phải xác định vị trí tạo dữ liệu và kiểm tra kết quả thật.

### 3.3. Recording cũng chứa dữ liệu nhạy cảm

Nếu màn hình có secret hoặc thông tin khách hàng, recording có thể lưu lại chúng. Việc dữ liệu nằm trong kho kiểm toán không làm mất nhu cầu giới hạn người xem, tải xuống và lưu giữ.

Cần quản lý quyền đối với bản ghi, nguồn phát hành liên kết, bản sao hỗ trợ và bản đã được che dữ liệu. Đường kiểm toán không nên trở thành một kênh lấy secret dễ dàng hơn đường phiên.

## 4. Mô hình đe dọa và ranh giới thực thi

Các tình huống có thể cần giải quyết gồm:

- Người dùng vô tình đính kèm screenshot chứa dữ liệu thật vào ticket.
- Người dùng chia sẻ toàn bộ màn hình trong một cuộc họp không phù hợp.
- Một tiến trình trên endpoint ghi lại nội dung phiên.
- Một bên hỗ trợ có quyền xem hoặc điều khiển PAW quá rộng.
- Dữ liệu chẩn đoán được lưu ở thư mục tự đồng bộ.
- Nội dung được capture ở host của VM hoặc ở client của remote desktop.
- Một người dùng có chủ đích tạo bản sao ngoài quy trình.

Mức kiểm soát phụ thuộc thành phần có thẩm quyền với bề mặt hiển thị. Ví dụ:

- Ứng dụng có thể đánh dấu nội dung theo khả năng nền tảng.
- OS hoặc agent có thể áp dụng policy cho một số đường capture.
- Gateway có thể kiểm soát nội dung và chức năng trong phiên được môi giới.
- Tổ chức có thể quản lý công cụ hội nghị hoặc hỗ trợ từ xa.
- Guest không tự bảo vệ được mọi hoạt động của host đang điều khiển nó.
- Website không tự kiểm soát được mọi công cụ của OS chỉ bằng JavaScript.

Người dùng có quyền quản trị cao trên endpoint hoặc thành phần bị kiểm soát có thể làm suy giảm một số cơ chế. Vì vậy, least privilege trên PAW và bảo vệ chuỗi quản lý vẫn cần thiết.

## 5. Các lớp kiểm soát bổ sung cho nhau

### 5.1. Giảm nội dung nhạy cảm trước khi hiển thị

Dữ liệu chưa được đưa tới màn hình sẽ ít phụ thuộc hơn vào việc chặn capture.

Các lựa chọn theo nhu cầu và khả năng gồm:

- Không hiển thị secret nếu gateway có thể sử dụng thay người dùng.
- Chỉ cấp role và tập dữ liệu cần cho tác vụ.
- Dùng dữ liệu chẩn đoán đã được giảm thiểu.
- Che trường nhạy cảm ở nguồn trước khi render.
- Không đưa token hoặc mật khẩu vào command output không cần thiết.
- Hạn chế khả năng mở tùy ý dữ liệu nhạy cảm ngoài công việc.

Che một trường trong giao diện không tự chặn quyền đọc dữ liệu qua API hoặc công cụ khác. Cần đánh giá quyền thực tế và các đường xuất.

### 5.2. Hạn chế capture tại ứng dụng hoặc OS

Một số nền tảng có cơ chế để ứng dụng hoặc hệ thống yêu cầu bảo vệ bề mặt hiển thị. Hiệu lực phụ thuộc tổ hợp ứng dụng, phiên bản, compositor, công cụ capture và cách triển khai.

Cần kiểm tra từng trường hợp hỗ trợ. Không suy từ một screenshot bị đen rằng mọi công cụ video, remote support, preview và đường host capture đều đã bị chặn.

Một trang web vô hiệu menu chuột phải, chọn văn bản hoặc một phím tắt không tự tạo kiểm soát screenshot trên toàn thiết bị.

### 5.3. Giới hạn công cụ và quyền trên PAW

Giới hạn phần mềm, extension và quyền quản trị cục bộ có thể giảm khả năng chạy công cụ ghi hình ngoài policy.

Tuy nhiên, chỉ cấm một tên ứng dụng không đủ nếu người dùng có thể chạy chương trình tương đương hoặc thay policy. Cần quản lý nguồn phần mềm, danh tính tiến trình theo khả năng nền tảng và quyền can thiệp vào agent.

Các công cụ được phép như hội nghị hoặc hỗ trợ từ xa cũng cần được xem xét; chúng có thể có khả năng chia sẻ hoặc ghi màn hình phục vụ công việc hợp lệ.

### 5.4. Kiểm soát nơi nhận và vòng đời dữ liệu

Dù một bản capture được phép, vẫn cần quyết định:

- Được lưu ở đâu?
- Ai được xem và tải?
- Có được gửi ra ngoài không?
- Có tự đồng bộ tới dịch vụ khác không?
- Giữ bao lâu theo mục đích đã xác định?
- Xử lý bản sao và sự cố chia sẻ nhầm ra sao?

Chặn một phím chụp màn hình không giải quyết các bản đã tồn tại từ trước hoặc được tạo qua luồng được phép.

## 6. Watermark: nhận diện và răn đe có giới hạn

### 6.1. Watermark có thể chứa gì?

Theo nhu cầu và policy, watermark có thể sử dụng:

- Định danh người dùng ở mức phù hợp.
- Mã phiên ngắn có thể đối chiếu.
- Target hoặc nhãn phân loại.
- Thời điểm cùng múi giờ hoặc quy ước hiển thị.
- Nhãn môi trường như production.

Không đưa credential, token hoặc dữ liệu cá nhân không cần thiết vào watermark. Watermark có thể bị chụp lại và phát tán cùng ảnh.

Cần chọn vị trí, độ tương phản và tần suất hiển thị phù hợp để vừa nhận diện được vừa không che mất thông tin vận hành quan trọng.

### 6.2. Watermark không tự ngăn capture

Watermark có thể hỗ trợ xác định ngữ cảnh của một ảnh, nhưng người dùng vẫn có thể tạo bản sao. Một ảnh có thể bị cắt, chỉnh sửa hoặc sao chép từ nguồn khác.

Do đó, watermark không phải bằng chứng mật mã rằng một cá nhân cụ thể đã chụp hoặc phát tán ảnh. Cần đối chiếu session, quyền truy cập, nguồn ảnh và các bằng chứng khác.

### 6.3. Vị trí phủ ảnh hưởng phạm vi

Watermark phía client, gateway và ứng dụng đích có thể xuất hiện trong những bản capture khác nhau.

Cần xác minh:

- Có nằm trong ảnh toàn màn hình và ảnh cửa sổ không?
- Có xuất hiện khi thay kích thước hoặc chuyển màn hình không?
- Có nằm trong recording ở điểm thu thập đang dùng không?
- Có làm lộ thông tin nhận diện quá mức cho người xem hỗ trợ không?
- Có cản trở thao tác hoặc khả năng tiếp cận giao diện không?

Không dùng một lần thử trên một màn hình làm bằng chứng cho mọi topology.

## 7. Kiến trúc tham chiếu với PAM và PAW

~~~mermaid
flowchart LR
    U["Quản trị viên"] --> W["PAW được quản lý"]
    W --> P["PAM: danh tính và policy phiên"]
    P --> G["Gateway hoặc proxy"]
    G --> T["Target và quyền hiệu lực"]
    M["Nguồn quản lý endpoint"] --> W
    C["Policy capture theo khả năng"] --> W
    G --> R["Recording được quản lý"]
    W --> E["Sự kiện endpoint"]
    P --> E
    R --> A["Truy xuất bằng chứng theo thẩm quyền"]
    X["Luồng xuất dữ liệu được duyệt"] --> A
~~~

Sơ đồ thể hiện các vai trò logic. Không phải mọi sản phẩm đều có đủ khả năng hoặc kiểm soát ở cùng vị trí.

Các câu hỏi cần trả lời:

1. Thành phần nào áp dụng capture control?
2. Nó nhận policy từ nguồn nào?
3. PAM có biết policy đã áp dụng đúng không?
4. Nếu không xác minh được, có mở phiên mới không?
5. Recording lấy dữ liệu ở đâu và có bị ảnh hưởng không?
6. Ngoại lệ được thực thi cho đúng phiên hay mở rộng toàn thiết bị?
7. Quyền sửa policy và quyền lấy recording được quản lý ra sao?

Một trường trạng thái do client tự gửi không đủ chứng minh control đang hoạt động. Cần dùng dữ liệu có nguồn, độ mới và mức tin cậy phù hợp với nền tảng.

## 8. Thiết kế policy theo nội dung và công việc

Không phải mọi nội dung quản trị cần cùng một mức hạn chế. Có thể phân biệt:

| Phạm vi | Ý định policy minh họa |
|---|---|
| Màn hình có secret hoặc dữ liệu nhạy cảm | Ưu tiên giảm hiển thị, hạn chế capture trong phạm vi hỗ trợ |
| Phiên chẩn đoán không có dữ liệu thật | Có thể cho luồng xuất bằng chứng được quản lý |
| Hỗ trợ vendor | Giới hạn người xem, kênh chia sẻ và tập nội dung |
| Recording kiểm toán | Thu thập theo phạm vi cần thiết, truy xuất có thẩm quyền |
| Tác vụ khẩn cấp | Ngoại lệ rõ chủ thể, phiên, mục đích và thời hạn |

Nguồn phân loại target hoặc nội dung cần được quản lý. Không cho người dùng tự đổi nhãn từ “nhạy cảm” sang “thông thường” rồi bỏ điều kiện.

Policy cũng cần có hành vi khi thiếu khả năng hỗ trợ. Nếu một phiên bắt buộc có capture control nhưng client không đáp ứng, cần chọn luồng khác phù hợp hoặc xử lý ngoại lệ đúng thẩm quyền.

Không ghi “đã áp dụng” chỉ vì đã gửi một cấu hình tới agent mà chưa biết kết quả.

## 9. Policy minh họa

~~~yaml
# Mã giả thể hiện ý định; không phải cấu hình sản phẩm.
policy:
  id: privileged-screen-content-example
  applies_to:
    source: approved_admin_workstations
    target_group: sensitive_production_targets
    session_type: supported_interactive_session

  content:
    avoid_secret_display: true
    use_task_scoped_role: true

  endpoint_capture:
    require_verified_supported_control: true
    evaluate_control_freshness: true
    reject_client_self_asserted_compliance: true
    action_if_unverified: do_not_open_under_normal_policy

  watermark:
    enabled: true
    fields:
      - approved_subject_label
      - short_session_reference
      - environment_label

  audit_recording:
    required_when_applicable: true
    verify_recording_path_independently: true
    access: authorized_reviewers_only

  export:
    route: approved_evidence_workflow
    require_data_minimization: true

  exception:
    scope: approved_subject_and_session
    require_authority_and_expiry: true
~~~

Mỗi trường cần được ánh xạ thành khả năng cụ thể. Nếu control chỉ hỗ trợ một ứng dụng hoặc một đường capture, phạm vi policy phải phản ánh đúng giới hạn.

Một watermark bật không thay capture control bắt buộc. Một bản ghi kiểm toán tạo thành công cũng không chứng minh người dùng không có bản capture khác.

Khi trạng thái chuyển sang không xác minh được trong phiên, cần áp dụng hành vi đã thiết kế cho cấp mới, resume và phiên hiện hữu. Không mặc định một kiểm tra ban đầu vẫn có hiệu lực vô hạn.

## 10. Luồng xuất ảnh chẩn đoán được phép

Người vận hành đôi khi cần gửi ảnh lỗi cho nhóm hỗ trợ. Nếu chỉ cấm mọi ảnh mà không có đường phù hợp, họ có thể tìm cách chuyển thông tin ngoài quy trình.

Một luồng có thể gồm:

1. Xác định vấn đề cần minh họa và nơi nhận.
2. Chọn nội dung tối thiểu, tránh chụp toàn bộ desktop.
3. Dùng dữ liệu giả hoặc một màn hình chẩn đoán đã giảm thiểu nếu có.
4. Tạo bằng chứng qua cơ chế được phép.
5. Loại bỏ dữ liệu nhạy cảm trước khi xuất tới nơi nhận.
6. Kiểm tra bản xuất cuối cùng.
7. Lưu ảnh ở kho có quyền truy cập và vòng đời phù hợp.
8. Ghi tham chiếu tới yêu cầu hoặc sự cố.

### 10.1. Che dữ liệu phải xét bản gốc

Nếu một screenshot chứa secret đã được lưu vào thư mục đồng bộ, việc che ở một bản đính kèm sau đó không tự xóa bản gốc hoặc bản đã đồng bộ.

Cần biết quá trình capture tạo những tệp tạm, clipboard, bản xem trước hay backup nào. Nếu có thể, giảm dữ liệu trước khi tạo ảnh sẽ giảm các bản nhạy cảm phát sinh.

### 10.2. Kiểm tra bản đã che

Một lớp phủ trong tài liệu hoặc annotation có thể không đồng nghĩa dữ liệu bên dưới đã bị loại khỏi artifact cuối cùng. Cần kiểm tra định dạng xuất, lớp nội dung, metadata và những phần còn đọc được theo công cụ thực tế.

Không chỉ dựa vào việc “nhìn thấy một hình chữ nhật che trên màn hình soạn thảo”. Bản được gửi đi phải được xác minh riêng.

### 10.3. Ưu tiên bằng chứng đúng mục đích

Một mã lỗi hoặc đoạn log đã được giảm thiểu có thể đủ cho chẩn đoán mà không cần screenshot chứa nhiều dữ liệu xung quanh.

Log cũng có thể chứa secret, nên vẫn cần kiểm tra. Mục tiêu là cung cấp đúng thông tin cần thiết, không đơn thuần thay ảnh bằng một tệp khác có cùng mức lộ dữ liệu.

## 11. Chia sẻ màn hình và hỗ trợ từ xa

### 11.1. Người xem là một phần của phạm vi

Một phiên PAM chỉ cấp quyền cho kỹ sư đang thao tác không tự cho mọi người trong cuộc họp quyền xem nội dung target.

Cần xác định ai được tham gia, nội dung nào được chia sẻ và khả năng ghi lại của nền tảng hỗ trợ. Một cuộc họp có thể được ghi hoặc có người dùng tạo bản sao ngoài môi trường của tổ chức.

Chia sẻ một cửa sổ thay vì toàn màn hình có thể giảm dữ liệu ngoài công việc, nhưng hiệu lực và nội dung hiển thị thực tế vẫn cần kiểm tra.

### 11.2. Công cụ hỗ trợ có quyền cao

Remote support có thể xem màn hình, điều khiển input, truyền tệp hoặc ghi hình. Quyền quản trị công cụ đó có thể ảnh hưởng trực tiếp PAW và phiên đặc quyền.

Cần kiểm soát chủ thể, thời gian, tác vụ và bằng chứng của đường hỗ trợ. Không tạo một ngoại lệ toàn bộ cho mọi công cụ mang nhãn “support”.

### 11.3. Khả năng tiếp cận và công việc hợp lệ

Một số người dùng cần công cụ hỗ trợ tiếp cận giao diện. Một số công cụ có thể đọc dữ liệu theo cơ chế khác với capture pixel.

Không tự vô hiệu tất cả công cụ hỗ trợ chỉ để đạt một nhãn kiểm soát. Cần hiểu nhu cầu, quyền, luồng dữ liệu và cách áp dụng policy phù hợp.

Hạn chế screenshot không tự hạn chế mọi đường đọc text hoặc dữ liệu ứng dụng. Phạm vi kiểm soát phải được mô tả đúng.

## 12. Ví dụ xuyên suốt: chẩn đoán qua phiên database

### 12.1. Bối cảnh

Linh cần chẩn đoán lỗi kết nối trên một database production. Role được cấp chỉ cho tác vụ chẩn đoán đã kiểm chứng. Một số màn hình có thể hiển thị định danh người dùng và thông tin cấu hình nhạy cảm.

Policy của tình huống yêu cầu:

- Mở từ PAW được quản lý.
- Dùng PAM và MFA theo điều kiện của công việc.
- Không xuất credential.
- Hạn chế capture bằng khả năng được hỗ trợ và kiểm chứng.
- Watermark gắn với phiên.
- Recording kiểm toán ở đường đã được quản lý.
- Bằng chứng gửi hỗ trợ đi qua luồng giảm thiểu dữ liệu.

### 12.2. Trước khi mở

PAM đánh giá danh tính, entitlement, phê duyệt và nguồn thiết bị. Thành phần có thẩm quyền kiểm tra trạng thái capture control trong phạm vi hỗ trợ.

Nếu chưa xác minh được control mà policy bắt buộc, không coi watermark là vật thay thế. Công việc cần một đường đáp ứng hoặc một ngoại lệ đã được quyết định đúng thẩm quyền.

### 12.3. Trong phiên

Linh chỉ mở màn hình cần cho chẩn đoán. Credential được gateway sử dụng mà không đưa lên màn hình.

Nếu một công cụ tại target tự hiển thị token trong output, đó là một vấn đề cần xử lý dù screenshot bị hạn chế. Token có thể đã đi vào recording hoặc các nguồn log khác.

Recording được kiểm tra ở đường của nó; không suy rằng các hạn chế endpoint không ảnh hưởng chỉ vì vị trí ghi nhận khác nhau trên sơ đồ.

### 12.4. Nhu cầu gửi ảnh

Nhóm hỗ trợ yêu cầu hình minh họa lỗi. Linh tạo bằng chứng qua luồng được phép, chỉ lấy phần thông tin cần thiết và kiểm tra bản xuất đã giảm thiểu.

Không mở rộng policy cho phép capture mọi cửa sổ trong cả ngày chỉ để đáp ứng một yêu cầu ảnh. Nếu có ngoại lệ kỹ thuật, nó phải giới hạn đúng người, phiên, nội dung và thời gian theo khả năng.

### 12.5. Kết thúc

Phiên được đóng theo vòng đời PAM. Ngoại lệ được thu hồi, ảnh chẩn đoán nằm ở kho đã định và quyền xem recording được giới hạn.

Đóng phiên không tự xóa những ảnh hoặc bản ghi đã được tạo trước đó. Các artifact đó có vòng đời riêng.

## 13. Ngoại lệ và tình huống không hỗ trợ

Một ngoại lệ capture cần có:

- Nhu cầu và lý do không dùng được luồng thông thường.
- Danh tính, thiết bị, target và phiên.
- Loại nội dung được phép tạo bản sao.
- Công cụ và nơi nhận.
- Thời hạn và điều kiện kết thúc.
- Người có thẩm quyền.
- Bằng chứng về bật, dùng và thu hồi ngoại lệ.

Không chỉ ghi “cho phép chụp màn hình” mà không nêu phạm vi.

Nếu nền tảng chỉ có khả năng bật/tắt ở cấp thiết bị, phải đánh giá đúng phạm vi mở rộng đó. Không tuyên bố đã giới hạn theo phiên nếu sản phẩm không thực thi được.

Sự cố agent, cập nhật OS, thay client hoặc failover có thể làm thay đổi hỗ trợ. Cần có hành vi khi control mất hiệu lực và kiểm chứng sau thay đổi.

Ngoại lệ hết hạn không nên phụ thuộc duy nhất vào một người nhớ tắt lại. Cần cơ chế vòng đời và đối chiếu kết quả phù hợp.

## 14. Kiểm chứng trên cấu hình thực tế

Kiểm chứng nên dùng dữ liệu giả, marker nhận diện và môi trường trong phạm vi được phép. Không hiển thị secret production chỉ để thử tính năng capture.

| Tình huống | Nội dung cần kiểm chứng |
|---|---|
| Chụp cửa sổ bằng chức năng OS được hỗ trợ | Nội dung được hạn chế đúng như policy |
| Chụp toàn màn hình | Không suy kết quả từ thử nghiệm cửa sổ |
| Công cụ ghi video được cho phép trong môi trường | Hành vi khớp phạm vi kiểm soát thực tế |
| Chia sẻ cửa sổ hoặc màn hình trong công cụ họp | Nội dung người xem nhận được đã được kiểm tra |
| Nhiều màn hình, thay kích thước, chuyển cửa sổ | Control và watermark không mất ngoài ý định |
| Preview hoặc thumbnail có liên quan | Giới hạn và phần còn hiển thị được biết rõ |
| Phiên remote desktop hoặc ứng dụng từ xa | Kiểm tra ở cả điểm tạo nội dung và client liên quan |
| Host của VM có khả năng capture | Giới hạn ranh giới guest được ghi đúng |
| Recording PAM | Đủ nội dung cần thiết, không bị trống ngoài ý định |
| Watermark ở recording và ảnh được phép | Có ở đúng điểm thu thập, đọc được và không che tác vụ |
| Resume từ client khác | Điều kiện nguồn và capture control được đánh giá lại |
| Agent mất trạng thái hoặc bị sửa trái phép | Có khả năng phát hiện và hành vi theo policy |
| Ngoại lệ hết hạn | Không còn quyền mở rộng ngoài thời hạn |
| Xuất ảnh đã che | Không còn nội dung cần loại khỏi bản cuối theo kiểm tra |
| Công cụ hỗ trợ tiếp cận | Công việc cần thiết vẫn thực hiện theo thiết kế phù hợp |

Một lần capture không thành công có thể do quyền công cụ, lỗi phần mềm hoặc control đang hoạt động. Cần đối chiếu nguồn và kết quả, không chỉ dựa vào một thông báo lỗi.

Không có event capture cũng không chứng minh không ai đã chụp. Một số đường có thể không được instrumentation quan sát, và camera ngoài không tạo sự kiện screenshot của OS.

## 15. Bằng chứng và ứng phó khi có bản sao ngoài luồng

### 15.1. Bằng chứng vận hành

Các dữ kiện có thể cần liên kết gồm:

~~~text
Người dùng và thiết bị.
Request, grant và session.
Target, phân loại và policy áp dụng.
Phiên bản và trạng thái control trong phạm vi hỗ trợ.
Thời điểm đánh giá, áp dụng và thay đổi.
Watermark hoặc tham chiếu phiên.
Sự kiện capture được quan sát nếu nền tảng có dữ liệu.
Ngoại lệ và kết quả thu hồi.
Recording và artifact xuất qua luồng được phép.
Giới hạn quan sát.
~~~

Log cần tránh lưu chính nội dung nhạy cảm không cần thiết. Không chụp thêm ảnh chứa secret vào ticket chỉ để chứng minh một ảnh trước đó đã bị lộ.

### 15.2. Khi phát hiện chia sẻ nhầm hoặc capture trái policy

Cần xác định nội dung, người có thể tiếp cận, nơi lưu, thời điểm và phạm vi bản sao theo bằng chứng hiện có.

Các hành động trong thẩm quyền có thể gồm hạn chế liên kết chia sẻ, xử lý quyền truy cập kho, bảo toàn dữ liệu điều tra và đánh giá credential hoặc dữ liệu có thể đã lộ.

Thu hồi một liên kết không tự chứng minh mọi người nhận đã mất các bản tải về. Nếu secret đã xuất hiện, xóa ảnh không làm secret tự trở lại bí mật; cần xử lý vòng đời credential theo tình huống.

Không kết luận một người phát tán ảnh chỉ từ watermark mang tên họ. Cần đối chiếu các khả năng truy cập và nguồn bằng chứng.

### 15.3. Quản lý bản ghi và bản dẫn xuất

Recording gốc, bản che dữ liệu và ảnh trích xuất có thể có quyền và mục đích khác nhau. Cần giữ liên kết nhưng không tự cấp người xem bản che quyền lấy bản gốc.

Quyền xem, xuất và xử lý vòng đời artifact cần được ghi nhận theo thiết kế. Mọi người có quyền vận hành phiên không mặc nhiên có quyền tải toàn bộ recording.

## 16. Chỉ số và sai lầm thường gặp

Các chỉ số có thể hỗ trợ đánh giá gồm:

- Phiên thuộc diện yêu cầu có control đã được xác minh trong phạm vi hỗ trợ.
- Client, ứng dụng hoặc topology chưa được kiểm chứng.
- Ngoại lệ quá hạn hoặc có phạm vi rộng.
- Trường hợp dữ liệu nhạy cảm bị hiển thị không cần thiết.
- Artifact hỗ trợ không đi qua kho được quản lý.
- Recording bị thiếu, trống hoặc chứa dữ liệu thừa.
- Quyền tải recording quá rộng.
- Sự kiện capture được quan sát và kết quả xử lý liên quan.

Mẫu số phải rõ. Tỷ lệ control bật trên một nhóm PAW không đại diện cho vendor dùng client khác, máy host ngoài phạm vi hoặc mọi đường quản trị.

| Sai lầm | Hệ quả | Hướng xử lý |
|---|---|---|
| Chặn phím screenshot là coi đã chặn capture | Bỏ sót công cụ và đường khác | Kiểm chứng theo từng bề mặt được hỗ trợ |
| Website chặn chuột phải được coi là bảo vệ OS | Ranh giới thực thi bị hiểu sai | Xác định quyền kiểm soát của ứng dụng và thiết bị |
| Watermark được coi là ngăn rò rỉ | Bản sao vẫn có thể được tạo | Dùng như một lớp nhận diện có giới hạn |
| Capture control được coi là không ảnh hưởng recording | Có thể mất bằng chứng cần thiết | Kiểm tra đường ghi nhận độc lập |
| Có recording là coi không cần bảo vệ màn hình | Dữ liệu vẫn có thể được lấy ngoài luồng | Kết hợp giảm hiển thị và kiểm soát capture |
| Che ảnh sau khi bản gốc đã đồng bộ | Bản nhạy cảm có thể còn ở nơi khác | Quản lý toàn bộ luồng tạo và lưu artifact |
| Mọi công cụ hỗ trợ đều được miễn trừ | Mở đường ghi hình rộng | Ngoại lệ theo chủ thể, mục đích và phạm vi |
| Guest được coi là kiểm soát host capture | Bỏ qua thành phần có quyền cao hơn | Đánh giá chuỗi tin cậy |
| Không có event là coi không có capture | Vượt quá khả năng quan sát | Ghi đúng giới hạn và đối chiếu nguồn khác |
| Watermark là bằng chứng duy nhất quy trách nhiệm | Có thể kết luận sai | Liên kết session, quyền và nguồn artifact |

## 17. Bài tập áp dụng

Một đội dùng PAW để mở phiên production. Họ chặn một phím screenshot nhưng vẫn cho phần mềm họp chia sẻ toàn màn hình. Watermark chỉ xuất hiện ở một góc client, còn recording được lấy ở gateway trước điểm phủ. Khi cần hỗ trợ, người dùng chụp ảnh chứa dữ liệu thật rồi che bằng annotation trong một tài liệu, sau đó gửi cho vendor. Bản gốc đã nằm trong thư mục đồng bộ.

Hãy phân tích:

1. Những đường capture và người xem nào cần được kiểm kê?
2. Vì sao chặn một phím không chứng minh mọi bản sao đều bị ngăn?
3. Watermark nằm ở đâu và xuất hiện trong artifact nào?
4. Recording cần được kiểm tra và bảo vệ ra sao?
5. Quy trình xuất ảnh có những bản tạm hoặc bản gốc nào?
6. Làm thế nào xác minh bản che cuối cùng trước khi gửi?
7. Ngoại lệ hỗ trợ cần giới hạn theo các chiều nào?
8. Nếu credential xuất hiện trong ảnh, xóa ảnh đã và chưa giải quyết điều gì?

Một thiết kế đạt mục tiêu cần nêu rõ nội dung nào được hiển thị, lớp nào kiểm soát capture, bản ghi nào được phép tồn tại và cách xác minh kết quả. Giá trị của screen capture control nằm ở phạm vi thực thi có bằng chứng, kết hợp với quyền hẹp và quản lý dữ liệu trong toàn bộ vòng đời phiên.

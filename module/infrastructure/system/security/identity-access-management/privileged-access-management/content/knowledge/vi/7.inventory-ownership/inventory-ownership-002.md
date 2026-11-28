# Business purpose

## Mục tiêu bài học

Trong chương **Inventory và ownership** của quản lý truy cập đặc quyền (**Privileged Access Management — PAM**), **business purpose** là mục đích công việc giải thích vì sao một danh tính, tài khoản hoặc đường truy cập đặc quyền cần tồn tại và được sử dụng.

Một danh mục chỉ có tên tài khoản, role và người quản lý chưa đủ để quyết định quyền nào cần giữ. Cần biết tài khoản phục vụ kết quả gì, thực hiện nhiệm vụ nào, trên tài nguyên nào và trong điều kiện nào. Thông tin này là cơ sở để áp dụng least privilege, JIT/JEA, quản lý credential và giám sát truy cập.

Bài học tập trung vào tài khoản quản trị, tài khoản dịch vụ và truy cập tới hạ tầng nhạy cảm. Sau bài học, bạn có thể:

- Viết mô tả business purpose cụ thể và kiểm chứng được.
- Phân biệt mục đích công việc với mô tả kỹ thuật, ownership và quyết định cấp quyền.
- Liên kết mục đích với danh tính, nhiệm vụ, tài nguyên và khả năng cần thiết.
- Xác nhận mục đích bằng chủ sở hữu và bằng chứng phù hợp.
- Xử lý mục đích chưa rõ, đã thay đổi hoặc hết hiệu lực mà vẫn xét phụ thuộc vận hành.

## 1. Business purpose trả lời câu hỏi nào?

Business purpose trả lời câu hỏi:

> Tổ chức cần giữ hoặc sử dụng khả năng truy cập này để hoàn thành công việc gì?

Ví dụ, “tài khoản quản trị cơ sở dữ liệu” mô tả loại tài khoản hoặc sức mạnh kỹ thuật. Nó chưa giải thích công việc nào cần khả năng đó.

Một mô tả có ích hơn là:

> Tài khoản phục vụ tác vụ sao lưu dữ liệu đơn hàng production và kiểm tra kết quả theo lịch vận hành đã được chấp nhận. Tác vụ cần truy cập đúng nguồn dữ liệu và kho sao lưu được giao; các thay đổi phân quyền không thuộc nhiệm vụ sao lưu thông thường.

Mô tả này tạo đầu vào cho phân tích quyền. Nó chưa khẳng định role hiện tại đã phù hợp, cũng chưa thay thế việc đánh giá cơ chế sao lưu cụ thể.

### Mục đích hợp lệ không làm mọi quyền trở nên hợp lệ

Một tài khoản có nhu cầu công việc thực sự vẫn có thể được cấp quá nhiều quyền. Cần tách hai kết luận:

1. Công việc có cần tồn tại và có cần một danh tính thực hiện không?
2. Tập quyền, phạm vi, thời gian và điều kiện hiện tại có cần cho công việc đó không?

Nếu câu trả lời thứ nhất là có, câu trả lời thứ hai vẫn có thể là không. Business purpose giúp đánh giá quyền; nó không phải giấy phép giữ mọi đặc quyền đã cấp.

## 2. Phân biệt những thông tin thường bị trộn lẫn

| Thông tin | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Business purpose | Công việc hoặc kết quả nào cần khả năng truy cập? | Duy trì khả năng khôi phục dữ liệu của dịch vụ đơn hàng |
| Nhiệm vụ vận hành | Cần thực hiện những hoạt động gì? | Tạo bản sao lưu, kiểm tra kết quả, thực hiện diễn tập phục hồi đã lên kế hoạch |
| Mô tả kỹ thuật | Thành phần hoạt động bằng cơ chế nào? | Job chạy trên máy chủ sao lưu và dùng danh tính dịch vụ |
| Quyền cần thiết | Hành động nào trên tài nguyên nào là cần thiết? | Đọc nguồn đã giao và ghi bản sao lưu vào đích tương ứng |
| Ownership | Ai chịu trách nhiệm xác nhận và duy trì thông tin? | Đội sở hữu dịch vụ phối hợp với đội nền tảng dữ liệu |
| Quyết định cấp quyền | Quyền nào được chấp nhận, với giới hạn nào? | Role giới hạn cho tác vụ, có scope và điều kiện cụ thể |
| Ngoại lệ | Vì sao chưa đạt kiểm soát mục tiêu và khi nào xử lý? | Chưa tách được một chức năng; có người chịu trách nhiệm và thời hạn |

Một ghi chú “đã được trưởng nhóm đồng ý” không thay thế business purpose. Người đồng ý, phạm vi quyết định và bằng chứng nhu cầu đều cần rõ.

Tương tự, “dùng cho ứng dụng A” mới chỉ chỉ ra một bên sử dụng. Cần bổ sung ứng dụng thực hiện nhiệm vụ gì và vì sao nhiệm vụ cần truy cập vào tài nguyên đang xét.

## 3. Liên kết từ mục đích tới khả năng truy cập

Có thể tổ chức thông tin theo chuỗi:

```text
Kết quả hoặc nhu cầu công việc
              |
              v
Dịch vụ / quy trình được hỗ trợ
              |
              v
Nhiệm vụ cụ thể
              |
              v
Danh tính thực hiện
              |
              v
Hành động + tài nguyên + điều kiện
              |
              v
Quyền và cơ chế PAM cần đánh giá
```

Ví dụ:

```text
Duy trì hoạt động của dịch vụ đơn hàng
    -> Phát hành bản sửa lỗi đã được chấp nhận
    -> Pipeline phát hành ứng dụng đơn hàng
    -> Danh tính workload của pipeline
    -> Cập nhật đúng ứng dụng trên production trong luồng phát hành
    -> Đánh giá role, scope, điều kiện nhận danh tính và audit
```

Chuỗi liên kết cần đủ cụ thể để phân biệt nhiệm vụ với quyền ngoài nhiệm vụ. Nếu lý do chỉ là “vận hành hệ thống”, gần như mọi đặc quyền đều có thể được gắn vào mà không giải thích được sự cần thiết.

### Một mục đích có thể dùng nhiều danh tính

Tài khoản người vận hành, danh tính pipeline và tài khoản dịch vụ có thể cùng phục vụ một kết quả nhưng thực hiện nhiệm vụ khác nhau. Mỗi danh tính cần có liên kết tới phần việc của mình.

### Một danh tính có thể có nhiều mục đích

Nếu một tài khoản phục vụ nhiều nhiệm vụ hợp lệ, hãy liệt kê riêng từng nhiệm vụ, phạm vi và chủ sở hữu liên quan. Không gộp thành “tài khoản dùng chung cho mọi việc”.

Tập quyền đáp ứng nhiều mục đích cũng cần được đánh giá về khả năng kết hợp và phạm vi tác động. Tách danh tính có thể phù hợp khi các workload, môi trường hoặc trách nhiệm khác nhau, nhưng quyết định cần dựa trên nhu cầu và mô hình nền tảng.

## 4. Thông tin cần có trong một mô tả mục đích

Không nhất thiết đưa mọi chi tiết vào một câu dài. Có thể dùng một mô tả ngắn và các trường có cấu trúc.

| Thành phần | Nội dung cần rõ | Câu hỏi kiểm tra |
| --- | --- | --- |
| Kết quả cần hỗ trợ | Dịch vụ hoặc công việc được duy trì | Nếu không có khả năng này, công việc nào bị ảnh hưởng? |
| Nhiệm vụ | Hoạt động cụ thể của chủ thể | Chủ thể thực sự cần làm gì? |
| Danh tính | Tài khoản hoặc workload liên quan | Đúng principal nào thực hiện nhiệm vụ? |
| Tài nguyên và môi trường | Đích truy cập trong phạm vi | Có cần production, mọi ứng dụng hoặc toàn tổ chức không? |
| Khả năng cần thiết | Các hành động ở mức có thể đối chiếu | Vì sao cần đọc, ghi, quản trị hoặc cấp quyền? |
| Thời điểm và điều kiện | Chu kỳ, thời hạn, sự kiện hoặc điều kiện kích hoạt | Cần thường trực hay chỉ khi có nhiệm vụ? |
| Chủ thể xác nhận | Bên hiểu nhu cầu và bên hiểu tài nguyên | Ai có thể giải thích và xác nhận thông tin? |
| Bằng chứng | Tham chiếu công việc, cấu hình hoặc quyết định | Người review có thể đối chiếu ở đâu? |
| Điều kiện kết thúc | Sự kiện khiến nhu cầu hết hiệu lực | Dự án, hợp đồng, migration hoặc workload kết thúc khi nào? |

Không ép mọi công việc có cùng tần suất hoặc cùng ngày hết hạn. Một tài khoản dịch vụ dài hạn có thể có nhu cầu liên tục; một tài khoản migration có thể chỉ cần trong một giai đoạn. Cả hai đều cần cơ chế xem xét khi bối cảnh thay đổi.

### Mẫu câu thực hành

> [Danh tính hoặc nhóm thực hiện] cần [nhiệm vụ] để hỗ trợ [dịch vụ/kết quả], trên [tài nguyên và môi trường], trong [thời điểm hoặc điều kiện]. [Chủ sở hữu] xác nhận nhu cầu; [tham chiếu] cung cấp bằng chứng.

Đây là mẫu gợi ý, không phải yêu cầu sao chép nguyên xi. Nếu mô tả chỉ đọc lên được mà không giúp phân biệt quyền cần và quyền dư, cần bổ sung nội dung cụ thể.

## 5. Nhận diện mô tả quá chung hoặc sai trọng tâm

| Mô tả ban đầu | Vấn đề | Cách làm rõ |
| --- | --- | --- |
| “Cần admin để làm việc” | Dùng quyền hiện tại để giải thích chính quyền đó | Nêu nhiệm vụ, tài nguyên và hành động cần thiết |
| “Đã có từ lâu” | Lịch sử tồn tại không chứng minh nhu cầu hiện tại | Xác nhận workload, chủ sở hữu và phần việc còn hoạt động |
| “Dùng cho production” | Mới chỉ có môi trường | Nêu dịch vụ và công việc trên production |
| “Để xử lý mọi sự cố” | Không có ranh giới hoặc điều kiện sử dụng | Nêu loại nhiệm vụ khẩn cấp, cơ chế kích hoạt và trách nhiệm |
| “Ứng dụng yêu cầu full access” | Chưa chỉ ra căn cứ kỹ thuật | Phân tích thao tác thực tế và giới hạn có thể áp dụng |
| “Theo yêu cầu kiểm toán” | Không rõ yêu cầu và hành động được hỗ trợ | Liên kết yêu cầu áp dụng với nhiệm vụ và bằng chứng cụ thể |
| “Tài khoản của đội nền tảng” | Ownership bị dùng thay cho mục đích | Xác định nhiệm vụ mà đội dùng tài khoản để thực hiện |

Không cần biến mô tả thành một bản thiết kế đầy đủ. Tuy nhiên, mô tả phải đủ để đặt câu hỏi có ý nghĩa như “vì sao một job phát hành lại cần sửa IAM?” hoặc “vì sao tác vụ ứng dụng A cần credential của ứng dụng B?”.

## 6. Ai xác nhận business purpose?

Một người biết cách đăng nhập chưa chắc có đủ thẩm quyền hoặc ngữ cảnh để xác nhận toàn bộ nhu cầu. Có thể phân công theo trách nhiệm sau:

| Vai trò | Phần cần xác nhận |
| --- | --- |
| Chủ sở hữu dịch vụ hoặc quy trình | Công việc có cần thiết và còn hiệu lực không |
| Chủ sở hữu tài nguyên hoặc nền tảng | Phạm vi tài nguyên và cơ chế quyền có phù hợp không |
| Nhóm vận hành hoặc phát triển | Tác vụ thực tế, lịch chạy và phụ thuộc |
| Nhóm IAM/PAM | Danh tính, đường nhận quyền, credential và các kiểm soát truy cập |
| Người có thẩm quyền chấp nhận ngoại lệ | Quyết định đối với rủi ro còn lại trong phạm vi được giao |

Quy mô tổ chức có thể khiến một đội đảm nhiệm nhiều vai trò. Với quyền nhạy cảm, cần mức xem xét độc lập phù hợp, đặc biệt khi người đề xuất cũng là người sẽ sử dụng quyền.

Đội IAM/PAM có thể hỗ trợ chuẩn hóa hồ sơ, nhưng không nên tự bịa mục đích thay cho đội sở hữu công việc. Người quản lý vault cũng không mặc nhiên biết mọi workload đang sử dụng credential.

### Trách nhiệm cần có khả năng duy trì

Nên liên kết tới đội hoặc chức năng chịu trách nhiệm và thông tin liên hệ còn hoạt động. Nếu dùng tên cá nhân, cần có quy trình cập nhật khi người đó chuyển vai trò hoặc rời tổ chức.

Không tự động gán người tạo tài khoản làm chủ sở hữu hiện tại. Họ có thể chỉ thực hiện yêu cầu kỹ thuật trong quá khứ.

## 7. Quy trình xây dựng và xác nhận mục đích

### Bước 1: Xác định đúng đối tượng

Ghi ID của danh tính, hệ thống nguồn, loại tài khoản và môi trường. Với tài khoản cục bộ hoặc tài khoản tại đích, cần đủ ngữ cảnh để tránh gộp những tài khoản cùng tên.

Xác định hồ sơ đang mô tả mục đích của tài khoản, của một binding quyền hay của một đường truy cập. Các mức này liên quan nhưng không đồng nhất.

### Bước 2: Thu thập mô tả hiện có

Có thể đối chiếu yêu cầu tạo tài khoản, hồ sơ dịch vụ, cấu hình workload, tài liệu vận hành và lịch công việc. Đây là nguồn bằng chứng, chưa phải kết luận cuối cùng về nhu cầu hiện tại.

Nếu mô tả từ yêu cầu cũ không còn đúng với workload hiện tại, ghi rõ sự khác biệt thay vì sao chép lại để điền đủ trường.

### Bước 3: Trao đổi theo nhiệm vụ

Những câu hỏi hữu ích gồm:

- Tài khoản đang phục vụ dịch vụ hoặc quy trình nào?
- Tác vụ nào cần quyền nhạy cảm và tác vụ nào chỉ cần quyền hẹp?
- Tài nguyên nguồn, đích và môi trường nào nằm trong nhiệm vụ?
- Lịch chạy hoặc điều kiện kích hoạt là gì?
- Nếu không cấp quyền này, công việc nào không thực hiện được?
- Có thể dùng danh tính, scope hoặc công cụ tác vụ hẹp hơn không?
- Khi nào nhiệm vụ hoặc nhu cầu truy cập kết thúc?

Không dùng câu hỏi “còn cần admin không?” làm toàn bộ quá trình xác nhận.

### Bước 4: Đối chiếu với cấu hình và sử dụng

So sánh mô tả với quyền hiệu lực, workload sử dụng và audit trong khoảng có dữ liệu. Cần đánh dấu những hành động chưa giải thích được, tài nguyên ngoài phạm vi và khoảng trống quan sát.

Không có log không chứng minh không có mục đích. Một job theo chu kỳ dài hoặc nhiệm vụ phục hồi có thể chưa xuất hiện trong khoảng quan sát. Ngược lại, hành động từng được thực hiện không tự chứng minh nó thuộc nhu cầu hợp lệ.

### Bước 5: Ghi kết quả xác nhận

Lưu mô tả, phạm vi, bên xác nhận, thời điểm và tham chiếu bằng chứng. Tách các trạng thái chưa rõ hoặc có tranh chấp khỏi mục đích đã được xác nhận.

### Bước 6: Bàn giao phần chênh lệch

Nếu nhu cầu hợp lệ nhưng quyền quá rộng, tạo đầu việc giảm quyền. Nếu mục đích đã hết, xác định phụ thuộc và kế hoạch kết thúc truy cập. Nếu chưa đủ dữ liệu, giao bên chịu trách nhiệm xác minh thay vì đánh dấu hoàn tất.

## 8. Áp dụng cho các loại tài khoản và truy cập

| Đối tượng | Mục đích cần làm rõ | Giới hạn cần đánh giá |
| --- | --- | --- |
| Tài khoản quản trị cá nhân | Nhiệm vụ vận hành mà người đó được giao | Dịch vụ, môi trường, hành động và thời gian cần quyền |
| Tài khoản dịch vụ | Nhiệm vụ tự động và workload sử dụng | Danh tính thực thi, tài nguyên, credential và bên được điều khiển workload |
| Tài khoản bên thứ ba | Công việc hỗ trợ hoặc bảo trì cụ thể | Hệ thống đích, thời gian, người bảo trợ và điều kiện giám sát |
| Tài khoản migration | Chuyển đổi dữ liệu hoặc cấu hình trong một giai đoạn | Phạm vi nguồn/đích và điều kiện kết thúc |
| Tài khoản khẩn cấp | Khôi phục khả năng vận hành trong tình huống xác định | Điều kiện sử dụng, trách nhiệm, bằng chứng và xử lý sau sử dụng |
| Công cụ thực thi tác vụ đặc quyền | Một tập công việc được ủy quyền | Lệnh, tham số, đích và khả năng sửa chính công cụ |

### Tài khoản quản trị của con người

“Nhân viên thuộc đội vận hành” chưa đủ để giữ toàn bộ quyền production. Cần xác định họ phụ trách hệ thống nào và loại tác vụ nào. Nếu chỉ cần thao tác nhạy cảm theo vụ việc, mục đích là đầu vào để xem xét cấp quyền tạm thời hoặc giao diện tác vụ hẹp.

### Tài khoản dịch vụ

Mục đích cần gắn với workload thực tế. Nếu một principal dùng chung cho nhiều ứng dụng, liệt kê từng bên sử dụng và phần việc tương ứng. Không để mô tả “cho hệ thống tự động” che khuất tổng quyền của nhiều nhiệm vụ.

Với danh tính workload hoặc cơ chế do nền tảng quản lý, không cần giả định luôn có mật khẩu. Vẫn phải mô tả mục đích, quyền và điều kiện nhận danh tính.

### Truy cập bên thứ ba

Cần có người bảo trợ và công việc cụ thể. Việc nhà cung cấp đã từng hỗ trợ hệ thống không tạo nhu cầu truy cập vô thời hạn. Thời hạn, phạm vi và điều kiện sử dụng phải gắn với công việc còn hiệu lực.

### Truy cập khẩn cấp

Mục đích có thể hợp lệ dù chưa được dùng gần đây. Cần mô tả loại tình huống phục hồi và cơ chế chịu trách nhiệm, thay vì đo nhu cầu chỉ bằng số lần đăng nhập.

Đường khẩn cấp cũng phải khả dụng trong tình huống được thiết kế phục vụ. Một quy trình phụ thuộc hoàn toàn vào thành phần có thể đang hỏng cần được xem xét trong thiết kế phục hồi.

## 9. Ví dụ xuyên suốt: tác vụ sao lưu dữ liệu đơn hàng

Một danh mục PAM có hồ sơ sau:

```text
Tài khoản: svc-order-backup
Business purpose: Vận hành hệ thống
Owner: Đội nền tảng
Quyền hiện tại: Quản trị rộng trên nhiều cơ sở dữ liệu
Credential: Được phân phối qua vault
```

Hồ sơ có thông tin kỹ thuật nhưng chưa giải thích quyền quản trị rộng phục vụ công việc gì.

### Làm rõ nhiệm vụ

Đội sở hữu dịch vụ xác nhận tài khoản dùng để chạy tác vụ sao lưu cơ sở dữ liệu đơn hàng production, ghi bản sao tới kho đã giao và ghi nhận kết quả. Thao tác phục hồi dữ liệu có quy trình riêng.

Đội nền tảng xác nhận workload đang chạy, các tài nguyên phụ thuộc và cơ chế quyền của công cụ sao lưu. Audit trong khoảng quan sát phù hợp với tác vụ đã mô tả, nhưng chưa bao phủ mọi tình huống phục hồi.

### Mô tả mục đích sau khi xác nhận

> `svc-order-backup` phục vụ tác vụ sao lưu cơ sở dữ liệu đơn hàng production để duy trì khả năng khôi phục dịch vụ. Workload sao lưu cần truy cập nguồn dữ liệu đã chỉ định, ghi bản sao tới kho được giao và báo cáo kết quả theo lịch vận hành. Đội sở hữu dịch vụ xác nhận nhu cầu; đội nền tảng dữ liệu chịu trách nhiệm cơ chế thực thi. Phục hồi và thay đổi phân quyền được đánh giá qua nhiệm vụ riêng.

Mô tả mới không đưa ra một role kỹ thuật cố định cho mọi sản phẩm. Công cụ sao lưu cụ thể có thể cần các khả năng riêng; đội kỹ thuật phải đối chiếu với cơ chế thực tế.

### Đối chiếu quyền

| Khả năng hiện tại | Liên hệ với mục đích | Bước tiếp theo |
| --- | --- | --- |
| Truy cập nguồn dữ liệu đơn hàng | Có liên hệ trực tiếp | Xác định hành động tối thiểu mà công cụ sao lưu cần |
| Ghi bản sao vào kho được giao | Có liên hệ trực tiếp | Xác nhận scope, đường ghi và kiểm tra kết quả |
| Quản trị cơ sở dữ liệu ứng dụng khác | Chưa có nhu cầu được xác nhận | Tìm phụ thuộc; nếu không có, lập thay đổi loại bỏ |
| Sửa IAM | Chưa thuộc nhiệm vụ sao lưu thông thường đã mô tả | Làm rõ nhu cầu riêng hoặc chuyển sang danh tính/quy trình phù hợp |
| Xóa bản sao lưu | Không thể kết luận chỉ từ tên tác vụ | Xác định chính sách vòng đời, nhiệm vụ dọn dẹp và phân tách trách nhiệm cần thiết |

Đây là lúc business purpose phát huy giá trị: nó tạo căn cứ để đặt câu hỏi cụ thể về từng khả năng. Nó không thay việc xác minh phụ thuộc, quyền hiệu lực hoặc khả năng tác vụ tiếp tục hoạt động sau thay đổi.

### Phát hiện mục đích cũ không còn đúng

Nếu sau này dịch vụ chuyển sang cơ chế sao lưu do nền tảng quản lý, tài khoản cũ cần được đánh giá lại. Không giữ mục đích “sao lưu đơn hàng” chỉ vì tài khoản vẫn tồn tại.

Trước khi kết thúc, xác nhận workload đã chuyển, các job phụ đã dừng, credential cũ được xử lý và không còn đường truy cập cần thiết bị bỏ sót.

## 10. Mẫu hồ sơ có cấu trúc

Ví dụ dưới đây là **mô hình hồ sơ minh họa**, không phải cấu hình cho một công cụ hay bộ field bắt buộc của mọi tổ chức:

```yaml
purpose_record:
  id: purpose-example-002
  identity_ref: production-data/svc-order-backup
  service_ref: order-service
  business_outcome: maintain-service-recoverability
  task: scheduled-order-database-backup
  target_scope:
    source: production/order-database
    destination: backup/order-service
  required_capabilities:
    - access-approved-backup-source
    - write-backup-to-assigned-destination
    - report-backup-result
  operating_conditions:
    trigger: approved-backup-schedule
    consumer: order-backup-workload
  ownership:
    service_owner: order-service-operations
    technical_owner: data-platform
  evidence:
    need_ref: protected-records/order-backup-requirement
    workload_ref: protected-records/order-backup-configuration
    permission_review_ref: protected-records/order-backup-access-review
  validation:
    state: confirmed
    confirmed_by: service-owner-reference
    confirmed_at: example-confirmation-time
  review_triggers:
    - workload-replacement
    - target-scope-change
    - service-retirement
  open_items:
    - verify-and-reduce-unrelated-database-administration
```

`validation.state: confirmed` trong ví dụ chỉ nói mục đích đã được xác nhận. Mục `open_items` cho thấy quyền thực tế vẫn cần xử lý. Không gộp “mục đích hợp lệ”, “quyền phù hợp” và “kiểm soát đã áp dụng” thành một trạng thái duy nhất.

Các định danh và tham chiếu cần trỏ tới dữ liệu được quản lý. Không đưa mật khẩu, token, private key hoặc dữ liệu sản xuất không cần thiết vào trường mô tả mục đích.

## 11. Dùng business purpose để lựa chọn kiểm soát PAM

| Nội dung mục đích cho biết | Quyết định có thể hỗ trợ | Câu hỏi xác nhận |
| --- | --- | --- |
| Một tập thao tác giới hạn | Least privilege hoặc JEA | Role, công cụ và tham số có thực sự chỉ cho phép tập thao tác đó không? |
| Nhiệm vụ chỉ cần theo đợt | JIT hoặc quyền có thời hạn | Điều kiện kích hoạt, hết hạn và phiên còn hiệu lực được xử lý thế nào? |
| Workload tự động ổn định | Danh tính riêng và cơ chế cấp credential phù hợp | Workload nào được nhận danh tính và trên scope nào? |
| Nhiều mục đích khác nhau dùng chung danh tính | Xem xét tách danh tính | Có thể tách theo workload, môi trường hoặc trách nhiệm không? |
| Công việc cần credential đặc quyền | Vault và quản lý vòng đời credential | Ai nhận được credential, có bản sao ngoài quản lý và bên phụ thuộc nào? |
| Nhiệm vụ nhạy cảm cần truy vết | Audit, ghi phiên hoặc tương quan lần chạy | Có thể liên kết người/workload với hành động tại đích không? |
| Nhu cầu phục hồi hoặc ngoại lệ | Cơ chế khẩn cấp và kiểm soát bù đắp | Khi nào dùng, ai chịu trách nhiệm và bằng chứng được lưu ở đâu? |

Không chọn JIT chỉ vì mô tả có từ “tạm thời”. Cần xem cả quyền đủ điều kiện kích hoạt, khả năng sửa chính điều kiện và trạng thái quyền sau khi phiên kết thúc.

Không chọn JEA chỉ bằng cách đặt một script trước tài khoản quản trị. Nếu người dùng sửa được mã, tham số hoặc đích tùy ý, khả năng thực tế vẫn có thể vượt mục đích.

Với workload, không mặc định mọi lần chạy đều cần một người phê duyệt tương tác. Điều kiện cấp quyền có thể dựa trên danh tính, môi trường và tác vụ đã được chấp nhận, miễn là những điều kiện đó được bảo vệ và đối chiếu với mục đích.

### Giám sát theo mục đích có thể phát hiện sai lệch

Nếu tài khoản sao lưu bắt đầu sửa IAM hoặc truy cập một cơ sở dữ liệu không thuộc scope, đây là dấu hiệu cần xác minh. Có thể đã phát sinh nhiệm vụ hợp lệ chưa được cập nhật; cũng có thể là cấu hình sai hoặc hành vi ngoài nhu cầu.

Không tự coi mọi sai lệch là sự cố đã được chứng minh. Cần xem bối cảnh, bằng chứng và quy trình ứng phó phù hợp.

## 12. Quản lý mục đích trong vòng đời

Mục đích không phải trường điền một lần khi tạo tài khoản. Nó có thể thay đổi khi dịch vụ, nhân sự, kiến trúc hoặc bên sử dụng thay đổi.

Các sự kiện cần xem xét gồm:

- Tạo tài khoản hoặc yêu cầu cấp thêm quyền nhạy cảm.
- Workload đổi chức năng, môi trường hoặc tài nguyên đích.
- Người dùng chuyển vai trò hoặc dịch vụ đổi chủ sở hữu.
- Dự án, migration hoặc công việc bên thứ ba kết thúc.
- Tài khoản được thêm bên sử dụng hoặc chuyển sang dùng chung.
- Phát hiện hành động ngoài phạm vi mục đích.
- Quy trình phục hồi hoặc cơ chế cấp credential thay đổi.

### Trạng thái cần phản ánh sự thật

Có thể quản lý các trạng thái nội bộ như **chờ xác nhận**, **đã xác nhận**, **cần cập nhật**, **có tranh chấp** và **đã hết nhu cầu**. Tên trạng thái tùy hệ thống, nhưng phải phân biệt rõ các tình huống.

Một ngày xác nhận mới không chứng minh nội dung đã được xem lại. Cần lưu ai xác nhận, họ dựa vào đâu và phần nào đã thay đổi.

### Khi chưa tìm được mục đích

Không bịa mô tả từ tên tài khoản hoặc role. Ghi rõ chưa xác định, tìm workload và chủ sở hữu, rồi giao trách nhiệm xác minh với mức ưu tiên phù hợp.

Không rõ mục đích là một khoảng trống quản trị cần xử lý. Nó chưa tự chứng minh tài khoản không được dùng. Thu hồi ngay mà chưa xem phụ thuộc có thể làm gián đoạn dịch vụ.

### Khi mục đích đã hết

Cần xác nhận công việc thực sự kết thúc, lập kế hoạch thu hồi quyền và xử lý credential, token hoặc phiên liên quan theo cơ chế nền tảng. Nếu tài khoản phục vụ nhiều mục đích, chỉ kết thúc một mục đích chưa đủ để xóa toàn bộ tài khoản.

Thu hồi một binding cũng chưa bảo đảm khả năng đã mất nếu còn đường nhận quyền khác. Bằng chứng đóng việc phải phù hợp với mục tiêu thay đổi.

### Khi các bên không thống nhất

Nếu chủ sở hữu dịch vụ và chủ sở hữu tài nguyên có nhận định khác nhau, ghi nội dung bất đồng và chuyển tới bên có thẩm quyền quyết định. Không biến tình trạng chưa quyết định thành một mục đích đã được xác nhận.

Nếu cần giữ quyền tạm thời, dùng hồ sơ ngoại lệ với lý do, scope, trách nhiệm, biện pháp bù đắp và thời hạn phù hợp.

## 13. Bằng chứng, chất lượng dữ liệu và chỉ số

Bằng chứng có thể gồm yêu cầu công việc, xác nhận của chủ sở hữu, tham chiếu cấu hình workload, kết quả review quyền và audit liên quan. Mỗi nguồn giải thích một phần; không có một nguồn duy nhất luôn thay thế mọi nguồn khác.

Nên lưu cả lịch sử thay đổi mục đích, người xác nhận và mốc thời gian. Dữ liệu này giúp kiểm toán hoặc điều tra vì sao một tài khoản có quyền tại thời điểm nhất định.

Mô tả có thể tiết lộ kiến trúc, tài nguyên nhạy cảm và quy trình phục hồi. Giới hạn quyền xem theo nhu cầu và chỉ lưu nội dung cần thiết. Không sao chép dữ liệu khách hàng, credential hoặc chi tiết nhạy cảm không phục vụ quyết định.

### Đo chất lượng thay vì chỉ đo trường có chữ

Các chỉ số có thể gồm:

- Tỷ lệ tài khoản trong phạm vi có mục đích đã được xác nhận và có chủ sở hữu.
- Số mục đích cần cập nhật sau sự kiện thay đổi.
- Số quyền nhạy cảm chưa liên kết được với nhiệm vụ hợp lệ.
- Số mục đích đã hết nhưng quyền hoặc credential chưa được xử lý xong.
- Số trường hợp chưa xác định được chủ sở hữu hoặc đang có tranh chấp.

Ví dụ minh họa, trong **40 tài khoản thuộc phạm vi review**:

| Trạng thái mục đích | Số tài khoản |
| --- | --- |
| Đã xác nhận, còn hiệu lực | 30 |
| Đang chờ xác nhận | 5 |
| Cần cập nhật | 3 |
| Có tranh chấp | 2 |

Tỷ lệ có mục đích đã xác nhận, còn hiệu lực trong tập này là **30/40 = 75%**. Tỷ lệ trường đã điền có thể cao hơn nhưng không phản ánh cùng chất lượng.

Tỷ lệ trên không chứng minh 75% quyền đã đúng hoặc 75% hạ tầng đã được kiểm kê. Cần ghi rõ mẫu số, đơn vị đo và phạm vi thu thập.

## 14. Tình huống tự đánh giá

Một tài khoản `svc-data-move` có mục đích được ghi là “migration dữ liệu ứng dụng A”. Dự án migration đã kết thúc, nhưng audit vẫn cho thấy tài khoản chạy một job hàng tháng. Tài khoản còn quyền quản trị cả nguồn lẫn đích.

### Cần hỏi gì?

1. Job hàng tháng phục vụ công việc nào và ai chịu trách nhiệm?
2. Đây là phần còn lại của migration, một nhiệm vụ mới hay cấu hình không còn cần thiết?
3. Job đang dùng đúng tài khoản này hay một principal khác có tên gần giống?
4. Hành động nào và tài nguyên nào thực sự cần cho job?
5. Có credential được phân phối cho bên sử dụng khác không?
6. Cần thay đổi mục đích, tách danh tính, giảm quyền hay kết thúc truy cập?

### Phân tích mẫu

Mục đích migration cũ không còn đủ để giải thích trạng thái hiện tại. Tuy nhiên, dữ liệu sử dụng cho thấy cần điều tra phụ thuộc trước khi thu hồi toàn bộ.

Nếu job hàng tháng phục vụ nhu cầu mới hợp lệ, chủ sở hữu phải xác nhận mục đích mới. Cần đánh giá lại quyền thay vì chuyển nguyên role quản trị của migration sang công việc mới.

Nếu job không còn cần thiết, lập kế hoạch dừng và thu hồi, bao gồm đường cấp credential và trạng thái truy cập ở đích. Nếu chưa xác định được công việc, ghi trạng thái chờ xác minh và bên chịu trách nhiệm.

Không chọn giữa hai cực “còn log nên giữ mọi quyền” và “dự án hết nên xóa ngay”. Quyết định cần dựa trên mục đích hiện tại, bằng chứng và phụ thuộc đã xác nhận.

## 15. Checklist cho một business purpose có thể sử dụng

- Nêu được công việc hoặc kết quả cần hỗ trợ.
- Xác định nhiệm vụ và đúng danh tính thực hiện.
- Có tài nguyên, môi trường và điều kiện đủ cụ thể.
- Giải thích được nhu cầu, không lấy role hiện tại làm lý do.
- Có chủ sở hữu và bên xác nhận phù hợp.
- Có tham chiếu bằng chứng và thời điểm xác nhận.
- Phân biệt mục đích hợp lệ với kết luận quyền đã phù hợp.
- Có điều kiện xem xét lại hoặc kết thúc nhu cầu.
- Đánh dấu phần chưa rõ và giao bước xác minh tiếp theo.
- Không chứa credential hoặc dữ liệu nhạy cảm không cần thiết.

Business purpose giúp biến danh mục PAM thành cơ sở ra quyết định: **giữ khả năng nào, cho ai, để làm việc gì, trên phạm vi nào và trong điều kiện nào**. Khi mục đích được xác nhận và cập nhật theo vòng đời, việc giảm quyền, quản lý credential và lưu bằng chứng có cơ sở rõ ràng hơn.

# Security policy là gì?

## 1. Khái niệm và vai trò trong security assurance

**Security policy (chính sách bảo mật)** là tập hợp những nguyên tắc, yêu cầu và quy tắc **được tổ chức phê duyệt chính thức**, quy định cách bảo vệ tài sản thông tin, hệ thống, dữ liệu và hoạt động kinh doanh. Chính sách xác định **điều gì phải được bảo vệ, ai chịu trách nhiệm, hành vi nào được phép hoặc không được phép, và mức yêu cầu tối thiểu cần tuân thủ** trong phạm vi áp dụng.

Một chính sách thường dùng ngôn ngữ bắt buộc như **“phải”**, **“không được”**, **“chỉ được phép khi”**. Ví dụ:

> “Mọi yêu cầu truy cập dữ liệu khách hàng phải được kiểm tra quyền theo danh tính và phạm vi tài nguyên. Việc chỉ xác thực đăng nhập không đủ để cấp quyền truy cập mọi bản ghi.”

Quy định trên **chưa chỉ định** phải dùng Java, Spring Security hay một thư viện cụ thể. Những cách triển khai thuộc tiêu chuẩn, thiết kế control và quy trình kỹ thuật; chúng có thể thay đổi mà vẫn phục vụ cùng mục tiêu chính sách.

Trong module **SECURITY_SECURITY_ASSURANCE**, security policy là một mắt xích quan trọng của quá trình **chứng minh bằng bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật**. Chính sách tạo nền tảng để hình thành yêu cầu kiểm chứng được, lựa chọn security controls, thiết kế kiểm thử, tiến hành audit và tổ chức khắc phục sai lệch. Một chuỗi truy vết hữu ích là:

**Mục tiêu và rủi ro kinh doanh → chính sách → yêu cầu/tiêu chuẩn → security controls → bằng chứng thực thi → kết luận assurance → phát hiện và khắc phục.**

Có văn bản chính sách **không đồng nghĩa** hệ thống đang bảo mật tốt. Giá trị của chính sách chỉ được hiện thực hóa khi các quy tắc được giao trách nhiệm, triển khai thành control, kiểm chứng trong thực tế và điều chỉnh theo thay đổi của hệ thống.

### 1.1. Chính sách bảo vệ những mục tiêu nào?

Những mục tiêu thường gặp gồm:

- **Confidentiality – tính bí mật:** dữ liệu chỉ được truy cập, truyền và sử dụng bởi các đối tượng có quyền.
- **Integrity – tính toàn vẹn:** dữ liệu, cấu hình và thao tác nghiệp vụ được bảo vệ khỏi sửa đổi trái phép hoặc sai lệch.
- **Availability – tính sẵn sàng:** hệ thống và dữ liệu quan trọng có khả năng phục vụ và khôi phục theo yêu cầu đã thống nhất.
- **Accountability – trách nhiệm giải trình:** thao tác quan trọng có người chịu trách nhiệm và có thể truy vết khi cần điều tra.
- **Privacy – quyền riêng tư:** dữ liệu cá nhân được xử lý theo mục đích, phạm vi và nghĩa vụ thực tế có áp dụng.

Một chính sách cụ thể không nhất thiết bao phủ toàn bộ mục tiêu trên. Ví dụ, *Access Control Policy* tập trung vào cấp và thu hồi quyền, còn *Backup and Recovery Policy* tập trung vào khôi phục và tính sẵn sàng. Các chính sách cần nhất quán với chính sách bảo mật cấp tổ chức.

## 2. Vì sao tổ chức cần security policy?

Nếu mỗi đội tự quyết định thế nào là “an toàn”, nhiều hệ thống sẽ dùng mức bảo vệ khác nhau mà không có lý do quản trị rõ ràng. Chính sách cung cấp **cơ sở thống nhất để đưa ra quyết định**, đặc biệt khi sản phẩm, kỹ thuật, vận hành và kiểm toán có mục tiêu riêng.

| Lợi ích | Cơ chế tạo ra giá trị | Dấu hiệu kiểm chứng |
| --- | --- | --- |
| **Thống nhất kỳ vọng** | Quy định cùng một mức bảo vệ cho các tài sản và hoạt động trong phạm vi | Hệ thống áp dụng yêu cầu bảo mật theo cùng tiêu chí |
| **Làm rõ trách nhiệm** | Giao chủ sở hữu chính sách, control owner, risk owner và người phê duyệt | Có ma trận trách nhiệm và đường chuyển cấp |
| **Ưu tiên theo rủi ro** | Quy định mức kiểm soát tương xứng với giá trị tài sản và hậu quả có thể xảy ra | Control quan trọng có tiêu chí và mức ưu tiên rõ |
| **Hỗ trợ phát triển an toàn** | Chuyển yêu cầu thành chuẩn kỹ thuật, kiểm thử và điều kiện phát hành | Pull request, pipeline, test và quyết định phát hành có bằng chứng |
| **Hỗ trợ audit và tuân thủ** | Nêu rõ yêu cầu phải kiểm tra, phạm vi và cách ghi nhận sai lệch | Hồ sơ đánh giá, phát hiện, ngoại lệ và kế hoạch sửa |
| **Cải tiến liên tục** | Có cơ chế cập nhật khi rủi ro, kiến trúc và vận hành thay đổi | Phiên bản chính sách, lịch review, các thay đổi được phê duyệt |

Ví dụ, chính sách có thể quy định rằng **mọi tài khoản quản trị tương tác phải dùng xác thực đa yếu tố (MFA)**. Bộ phận quản lý danh tính triển khai các phương thức MFA phù hợp; nhóm assurance kiểm tra cấu hình, danh sách tài khoản và các trường hợp miễn trừ. Nếu phát hiện một tài khoản chưa đáp ứng, phải có người xử lý và theo dõi kết quả. Khi đó chính sách hỗ trợ quyết định quản trị bằng bằng chứng thực tế.

## 3. Phân biệt policy, standard, baseline, procedure, guideline và control

Các khái niệm sau có liên hệ nhưng không nên dùng thay thế cho nhau.

| Khái niệm | Câu hỏi được trả lời | Mức độ quy định | Ví dụ liên quan đến tài khoản quản trị |
| --- | --- | --- | --- |
| **Policy – Chính sách** | Tổ chức **yêu cầu điều gì, vì sao, ai chịu trách nhiệm**? | Bắt buộc trong phạm vi được phê duyệt | “Tài khoản quản trị tương tác phải dùng MFA.” |
| **Standard – Tiêu chuẩn** | Phải đáp ứng **tiêu chí kỹ thuật hoặc nghiệp vụ tối thiểu** nào? | Thường bắt buộc nếu chính sách viện dẫn hoặc cơ chế quản trị quy định | “Các phương thức MFA được chấp nhận phải nằm trong danh mục được phê duyệt.” |
| **Baseline – Cấu hình chuẩn tối thiểu** | Một loại hệ thống phải được cấu hình tối thiểu ra sao? | Bắt buộc cho đối tượng áp dụng | “Tắt đăng nhập quản trị bằng tài khoản mặc định, bật chính sách MFA của IdP.” |
| **Procedure – Quy trình** | **Ai thực hiện các bước gì, vào lúc nào** để đáp ứng yêu cầu? | Thường bắt buộc đối với vai trò được giao | “Quy trình đăng ký, xác minh và thu hồi thiết bị MFA.” |
| **Guideline – Hướng dẫn** | Có **cách thực hiện khuyến nghị** nào giúp đạt mục tiêu? | Khuyến nghị, trừ khi được quy định bắt buộc | “Ưu tiên phương thức xác thực chống phishing khi khả thi.” |
| **Control – Biện pháp kiểm soát** | Biện pháp nào **ngăn ngừa, phát hiện hoặc giảm tác động** của rủi ro? | Là cơ chế được triển khai/vận hành | IdP yêu cầu MFA khi đăng nhập quản trị |
| **Evidence – Bằng chứng** | Dựa vào đâu biết control **đang đáp ứng** yêu cầu? | Phải đủ tin cậy cho kết luận tương ứng | Cấu hình IdP, kết quả thử tài khoản, danh sách ngoại lệ có kiểm tra |

Một chính sách có thể viện dẫn nhiều tiêu chuẩn và quy trình. Ngược lại, một control có thể đáp ứng nhiều yêu cầu của các chính sách khác nhau.

**Ví dụ đối chiếu:** “Tất cả dữ liệu phải an toàn” là một khẩu hiệu khó đánh giá. “Dữ liệu nhạy cảm chỉ được truy cập bởi chủ thể được cấp quyền theo nhiệm vụ” là yêu cầu chính sách; “dịch vụ phải kiểm tra quyền ở mỗi lần đọc tài nguyên” là yêu cầu kiểm chứng; “truy vấn bản ghi theo ID và danh tính tin cậy” là một cách triển khai control; “test A không thể đọc bản ghi của B” là một phần bằng chứng.

### 3.1. Chính sách có luôn là một tài liệu duy nhất?

Không nhất thiết. Tổ chức có thể có **Information Security Policy** cấp cao và các chính sách chuyên đề về quản lý truy cập, dữ liệu, bảo mật ứng dụng, quản lý lỗ hổng, sử dụng thiết bị, ứng cứu sự cố hoặc bảo mật nhà cung cấp.

Trong đơn vị nhỏ, một tài liệu có nhiều mục có thể phù hợp. Trong tổ chức lớn, nhiều chính sách có owner riêng giúp việc cập nhật và phê duyệt nhanh hơn. Dù cấu trúc nào, cần tránh **mâu thuẫn, trùng quyền phê duyệt và khoảng trống trách nhiệm**.

## 4. Một security policy tốt thường có những thành phần nào?

Cấu trúc có thể khác theo loại chính sách, nhưng nên đủ thông tin để người áp dụng hiểu **nghĩa vụ, phạm vi, quyền hạn và cách kiểm chứng**.

| Thành phần | Nội dung cần làm rõ | Câu hỏi tự kiểm tra |
| --- | --- | --- |
| **Tên, ID, phiên bản, trạng thái** | Mã định danh, phiên bản, ngày hiệu lực, người phê duyệt | Người dùng có biết đang áp dụng bản nào? |
| **Mục đích** | Rủi ro hoặc mục tiêu kinh doanh mà chính sách bảo vệ | Vì sao cần quy định này? |
| **Phạm vi** | Đơn vị, hệ thống, dữ liệu, môi trường, nhân sự, đối tác | Trường hợp nào áp dụng và trường hợp nào không? |
| **Định nghĩa** | Thuật ngữ dễ gây hiểu nhầm như dữ liệu nhạy cảm, tài khoản đặc quyền | Người đọc có hiểu cùng một cách? |
| **Yêu cầu bắt buộc** | Các phát biểu rõ, có thể kiểm chứng | Có thể viết test hoặc tiêu chí đánh giá cho mỗi yêu cầu? |
| **Vai trò và trách nhiệm** | Policy owner, control owner, risk owner, operator, reviewer | Ai triển khai, ai đánh giá, ai quyết định? |
| **Ngoại lệ và xử lý sai lệch** | Điều kiện, người phê duyệt, biện pháp bù trừ, hạn và chuyển cấp | Có thể hợp thức hóa ngoại lệ vượt quyền không? |
| **Giám sát và bằng chứng** | Đo hiệu quả, nguồn bằng chứng, lịch kiểm tra và bảo vệ hồ sơ | Dựa vào đâu kết luận yêu cầu đang được đáp ứng? |
| **Thực thi và xử lý vi phạm** | Quy trình phản hồi, khắc phục và các hành động theo quy chế | Khi không tuân thủ thì ai làm gì? |
| **Review và quản lý thay đổi** | Khi nào cập nhật, ai đánh giá lại và thông báo | Điều gì xảy ra nếu kiến trúc hoặc luật thay đổi? |

Không nên nhồi các cấu hình kỹ thuật dễ thay đổi vào văn bản chính sách cấp cao nếu có thể quản lý bằng standard/baseline riêng. Ví dụ, chính sách yêu cầu bảo vệ dữ liệu khi truyền; tiêu chuẩn mật mã quy định phiên bản giao thức và cấu hình được phép theo từng thời điểm.

### 4.1. Viết yêu cầu chính sách sao cho kiểm chứng được

So sánh ba cách viết:

| Cách viết | Vấn đề hoặc ưu điểm |
| --- | --- |
| “Hệ thống nên bảo mật dữ liệu.” | Mơ hồ: không rõ dữ liệu nào, ai chịu trách nhiệm, thế nào là đạt |
| “Các dịch vụ cần cân nhắc phân quyền phù hợp.” | Khó kiểm chứng: “cân nhắc” không tạo một điều kiện bảo vệ |
| “Mỗi yêu cầu đọc dữ liệu khách hàng phải kiểm tra quyền của chủ thể trên tài nguyên; yêu cầu không được phép phải bị từ chối và không trả nội dung tài nguyên.” | Chỉ rõ phạm vi, yêu cầu và điều kiện kiểm thử |

Để làm sắc nét một câu chính sách, hãy hỏi:

1. **Đối tượng nào:** hệ thống, loại dữ liệu, tài khoản hay quy trình?
2. **Phải làm gì hoặc không được làm gì:** quy tắc bắt buộc và ngoại lệ định nghĩa ở đâu?
3. **Áp dụng khi nào:** với mọi request, khi triển khai hay theo kỳ?
4. **Ai chịu trách nhiệm:** chủ sở hữu kiểm soát và người thực hiện là ai?
5. **Chứng minh thế nào:** kiểm thử, cấu hình, log, biên bản review hoặc quan sát nào là bằng chứng phù hợp?

Không phải mọi câu trong chính sách đều cần nêu trực tiếp cách test, nhưng **phải có thể truy vết đến yêu cầu và tiêu chí đo** ở tài liệu hoặc hệ thống liên quan.

## 5. Chính sách bắt nguồn từ rủi ro và mục tiêu bảo mật

Một chính sách hợp lý phải giải thích được **tại sao quy định đó cần thiết**. Nguồn đầu vào có thể gồm:

- Bối cảnh kinh doanh và những tài sản quan trọng.
- Kết quả đánh giá rủi ro và threat modeling.
- Phát hiện kiểm thử, audit, sự cố và bài học khắc phục.
- Nghĩa vụ pháp lý, hợp đồng và cam kết với khách hàng thực sự áp dụng.
- Kiến trúc hiện tại, nhà cung cấp và mô hình vận hành.
- Mức chấp nhận rủi ro đã được cấp có thẩm quyền phê duyệt.

Ví dụ, mối đe dọa **người dùng A truy cập đơn hàng của B** cho thấy cần chính sách bảo vệ dữ liệu theo quyền truy cập. Từ chính sách có thể dẫn đến yêu cầu kiểm tra quyền theo đối tượng và bằng chứng test từ chối truy cập chéo tài khoản.

| Rủi ro/điều cần bảo vệ | Yêu cầu chính sách | Control cần có | Bằng chứng assurance |
| --- | --- | --- | --- |
| Lộ dữ liệu do truy cập sai đối tượng | Chỉ chủ thể được ủy quyền mới đọc dữ liệu khách hàng | Authorization tại tầng dữ liệu/nghiệp vụ | Test quyền A/B, review xử lý quyền, giám sát vi phạm |
| Tài khoản quản trị bị chiếm quyền | Truy cập quản trị tương tác phải có xác thực mạnh theo tiêu chuẩn | MFA, kiểm soát vòng đời tài khoản, quản lý đặc quyền | Cấu hình IdP, test đăng nhập, báo cáo tài khoản và ngoại lệ |
| Bí mật ứng dụng xuất hiện trong mã nguồn | Bí mật phải được lưu và truy cập qua cơ chế bảo vệ được phê duyệt | Secrets manager, secret scanning, rotation | Scan kết quả, cấu hình truy cập, lịch sử thu hồi |
| Thay đổi trái phép bản triển khai | Chỉ thay đổi được ủy quyền mới đến production | Phân quyền CI/CD, bảo vệ artifact, review thay đổi | Log build/deploy, quyền pipeline, truy vết artifact |
| Không thể phục hồi dữ liệu sau sự cố | Hệ thống trọng yếu phải đáp ứng mục tiêu khôi phục | Backup, replication, diễn tập khôi phục | Kết quả restore/failover theo phạm vi, mốc và dữ liệu kiểm chứng |
| Sự kiện quan trọng không thể điều tra | Hành động trọng yếu phải có dấu vết có thể truy vết | Audit logging, bảo vệ log, đồng bộ thời gian | Test sinh log, giám sát truy cập, kiểm tra retention |

**Lưu ý:** các control và bằng chứng trong bảng là ví dụ. Hiệu lực bảo vệ phụ thuộc phạm vi, cấu hình, môi trường và yêu cầu đã phê duyệt. Không suy rằng cứ “có công cụ” thì chính sách đã được thực thi đầy đủ.

## 6. Vòng đời xây dựng và quản lý security policy

Một chính sách có giá trị khi được duy trì như một **chu trình quản trị liên tục**.

### Bước 1. Xác định nhu cầu và người sở hữu

Từ rủi ro, mục tiêu bảo mật hoặc nghĩa vụ áp dụng, xác định **policy owner** chịu trách nhiệm nội dung và vòng đời. Ví dụ CISO có thể sở hữu chính sách bảo mật cấp tổ chức; chính sách khôi phục cần phối hợp với chủ sở hữu hạ tầng, dịch vụ và liên tục kinh doanh.

Ngay ở bước này cần nêu rõ **cấp nào có quyền phê duyệt**, phạm vi ảnh hưởng và tiêu chí thành công.

### Bước 2. Soạn dự thảo theo ngôn ngữ có thể áp dụng

Dự thảo nêu mục đích, phạm vi, quy tắc bắt buộc, trách nhiệm, ngoại lệ và các tài liệu bổ trợ. Các yêu cầu cần kiểm chứng được nhưng không khóa tổ chức vào một công nghệ khi điều đó không cần thiết.

Ví dụ, dùng “mọi truy cập dữ liệu nhạy cảm phải được phân quyền” thay vì “bắt buộc dùng chính xác phương thức của một phiên bản framework”, trừ khi tiêu chuẩn kỹ thuật thực sự cần ràng buộc đó.

### Bước 3. Tham vấn các bên chịu ảnh hưởng

Để kiểm tra tính đúng và khả thi, mời các đại diện có liên quan:

- **Kinh doanh/data owner:** xác định tài sản, hậu quả và nhu cầu sử dụng.
- **Security và quản trị rủi ro:** kiểm tra sự tương xứng với các mối đe dọa và khẩu vị rủi ro.
- **Developer/architect:** nhận diện tác động kiến trúc và kiểm thử.
- **Vận hành/SRE:** kiểm tra khả năng triển khai, giám sát, sao lưu và ứng cứu.
- **Pháp chế/compliance:** xác nhận những nghĩa vụ thực sự áp dụng.
- **Assurance/audit** khi phù hợp: góp ý về tính kiểm chứng và khả năng lưu bằng chứng, đồng thời bảo vệ tính độc lập của đánh giá sau này.

Ghi nhận bất đồng có tác động đáng kể; không đánh đồng sự đồng ý trong cuộc họp với quyết định phê duyệt theo đúng thẩm quyền.

### Bước 4. Phê duyệt, phiên bản hóa và công bố

Người được ủy quyền phê duyệt chính sách; tổ chức lưu **ID, phiên bản, ngày hiệu lực, trạng thái và lịch sử thay đổi**. Khi công bố phải có một **nguồn chính thức** để người thực hiện lấy đúng bản đang hiệu lực.

Một chính sách chưa được phê duyệt hoặc bản nháp không nên được trình bày như nghĩa vụ đã có hiệu lực. Khi có bản mới, cần xác định thời hạn chuyển đổi và những bản/biểu mẫu nào hết hiệu lực.

### Bước 5. Chuyển chính sách thành yêu cầu và control

Đây là bước quan trọng để tránh “chính sách nằm trên giấy”:

1. **Phân rã quy định** thành các yêu cầu hoặc security claims có thể kiểm tra.
2. **Chọn security controls** phù hợp rủi ro và kiến trúc.
3. **Giao control owner** và người thực hiện cho từng phạm vi.
4. **Thiết kế tiêu chuẩn/quy trình/baseline** kỹ thuật khi cần.
5. **Tạo bằng chứng từ đầu**: test case, cấu hình, nhật ký, kết quả quét, review, diễn tập.
6. **Đưa hoạt động kiểm tra vào quy trình** phát triển, phát hành và vận hành.

Nếu một chính sách áp dụng cho nhiều dịch vụ, cần làm rõ **control tập trung** và **trách nhiệm tích hợp ở từng ứng dụng**. Ví dụ IdP chịu trách nhiệm phần MFA tập trung; mỗi ứng dụng vẫn phải tích hợp và không vô tình bỏ qua đường đăng nhập riêng.

### Bước 6. Kiểm chứng tuân thủ và hiệu quả

Cần kiểm tra cả hai góc độ:

- **Compliance/conformance – mức tuân thủ:** hệ thống và con người có thực hiện các yêu cầu đã quy định không?
- **Effectiveness – mức hiệu quả:** các control có giúp đạt mục tiêu bảo mật trong các tình huống thực tế không?

Ví dụ, ứng dụng có middleware kiểm tra token nghĩa là đã có một thành phần xác thực, nhưng **chưa chứng minh** người dùng không thể đọc dữ liệu của người khác. Kết luận về phân quyền cần kiểm thử cấp đối tượng và rà soát những đường truy cập khác.

Khi có phát hiện, cần chỉ định người xử lý, mức ưu tiên theo rủi ro, hạn, **bằng chứng xác minh bản sửa** và đường chuyển cấp.

### Bước 7. Rà soát và cập nhật theo thay đổi

Chính sách nên có chu kỳ review theo rủi ro và **trigger** xem xét sớm khi:

- Có luật, hợp đồng hoặc nghĩa vụ mới thực sự áp dụng.
- Kiến trúc, công nghệ hoặc nhà cung cấp thay đổi đáng kể.
- Xuất hiện threat mới hoặc kết quả kiểm thử cho thấy control trước đây không đủ.
- Xảy ra sự cố hoặc phát hiện audit lặp lại.
- Tổ chức thay đổi cơ cấu, phân quyền hoặc mức chấp nhận rủi ro.
- Một quy định không còn khả thi hoặc có các ngoại lệ kéo dài bất thường.

Việc cập nhật cần có đánh giá tác động, phê duyệt phù hợp, công bố phiên bản mới và **tái kiểm chứng control** bị ảnh hưởng.

## 7. Ví dụ: Security policy dẫn đến phân quyền API Java/Spring Boot

Giả sử một nền tảng thương mại điện tử có dịch vụ **Orders API** viết bằng **Java/Spring Boot**. Dịch vụ xử lý thông tin đơn hàng, người nhận và địa chỉ giao hàng. API nhận request:

~~~http
GET /api/orders/841
Authorization: Bearer <token-cua-khach-hang-A>
~~~

Đơn hàng 841 thuộc khách hàng B. Nếu server chỉ xác thực token A hợp lệ rồi trả đơn hàng theo ID, A có thể đọc dữ liệu không thuộc quyền. Kịch bản này thường liên quan đến **broken object-level authorization** khi được xác minh.

### 7.1. Viết yêu cầu ở ba mức

**Chính sách cấp tổ chức:**

> “Dữ liệu khách hàng chỉ được truy cập bởi chủ thể đã được xác thực và được cấp quyền. Mọi dịch vụ xử lý dữ liệu khách hàng phải thực thi phân quyền phù hợp với tài nguyên và mục đích truy cập.”

**Tiêu chuẩn/yêu cầu cho Orders API:**

> “Mỗi request đọc đơn hàng phải xác minh quyền của danh tính hiện tại trên đúng đơn hàng được yêu cầu. Nếu không đủ quyền, API không được trả bất kỳ nội dung nhạy cảm nào của đơn hàng. Những vai trò được ủy quyền phải tuân theo chính sách quyền riêng.”

**Security claim để assurance kiểm tra:**

> “User A không thể đọc hoặc xuất đơn hàng của user B nếu không có quyền được ủy quyền hợp lệ.”

Ba mức này tương ứng với **định hướng bắt buộc → tiêu chí cụ thể → khẳng định có thể kiểm chứng**.

### 7.2. Control ở tầng ứng dụng

Một cách triển khai minh họa là ràng buộc truy vấn đơn hàng với customer ID **lấy từ ngữ cảnh xác thực tin cậy**, thay vì từ dữ liệu do client tự khai:

~~~java
@Service
public class OrderReadService {
    private final OrderRepository orders;
    private final CurrentCustomer currentCustomer;

    public OrderReadService(OrderRepository orders,
                            CurrentCustomer currentCustomer) {
        this.orders = orders;
        this.currentCustomer = currentCustomer;
    }

    @Transactional(readOnly = true)
    public OrderView findOrder(long orderId) {
        long customerId = currentCustomer.customerId();

        return orders.findByIdAndCustomerId(orderId, customerId)
                .map(OrderView::from)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Đây là **trích đoạn mô hình**, không phải chương trình hoàn chỉnh. Các kiểu **OrderRepository**, **OrderView** và **CurrentCustomer** cần có triển khai thực tế. **CurrentCustomer** phải ánh xạ từ identity đã xác minh; không lấy trực tiếp customer ID từ request tùy ý. Những chính sách cho vai trò đặc quyền hoặc ủy quyền hợp lệ phải được thiết kế và kiểm thử riêng. Sử dụng 403 hay 404 tùy chính sách công bố dữ liệu của API; trong mọi trường hợp **không trả nội dung trái quyền**.

Kiểm tra quyền tại một endpoint không tự bảo vệ các đường truy cập khác như list, export, batch hoặc service-to-service. Control owner cần làm rõ phạm vi bao phủ.

### 7.3. Thiết kế bằng chứng

| Trường hợp cần kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| User A đọc đơn của A | Test được phép, xác nhận trả đúng dữ liệu |
| User A đọc đơn của B | Test bị từ chối, không có nội dung dữ liệu B |
| Request thiếu token hoặc token không hợp lệ | Kết quả test xác thực và cấu hình security liên quan |
| User có quyền ủy quyền hợp lệ | Test quyền theo phạm vi được ủy quyền |
| User bị thu hồi quyền | Test sau cập nhật quyền, kiểm tra thời gian hiệu lực theo chính sách |
| Endpoint export/list cũng dùng dữ liệu đơn | Test và review các đường truy cập tương ứng |
| Bản phát hành hiện tại | Kết quả test gắn build/commit, môi trường, thời điểm, reviewer |
| Phát hiện từng tồn tại | Ticket, bản sửa và kết quả kiểm thử lại |

Một báo cáo CI ghi “tất cả test đều PASS” có thể **không đủ bằng chứng** nếu suite chưa có kiểm thử truy cập chéo khách hàng. Bằng chứng chỉ hỗ trợ kết luận **trong phạm vi và phiên bản đã được kiểm tra**.

### 7.4. Nếu có phát hiện vi phạm chính sách

Giả sử kiểm thử phát hiện A đọc được đơn B. Khi đó:

1. **Ghi nhận phát hiện** và bằng chứng của phiên bản bị ảnh hưởng, tránh đưa dữ liệu thật không cần thiết vào ticket.
2. **Phân loại tác động/rủi ro** cùng risk owner và bộ phận bảo mật.
3. **Giao action owner** sửa control, rà soát các đường truy cập tương tự.
4. **Áp dụng giảm thiểu tạm thời** khi cần: hạn chế tính năng, chặn đường truy cập hoặc hoãn phạm vi phát hành theo cơ chế được phép.
5. **Kiểm thử lại** trên bản sửa với các ca được phép/bị từ chối, cập nhật test hồi quy.
6. **Đánh giá residual risk** dựa trên bằng chứng mới; người có thẩm quyền quyết định phương án tiếp theo.
7. **Cập nhật hồ sơ** chính sách–requirement–control–test–finding và xem có cần sửa tiêu chuẩn/đào tạo hay không.

Chính sách giúp xác định **vi phạm điều gì**, còn assurance giúp xác minh **đã sửa đến mức nào**.

## 8. Ví dụ một bản policy register

Tổ chức cần lưu bản chính sách chính thức, quyền phê duyệt và những liên kết tới yêu cầu/kiểm soát. Mẫu YAML sau **chỉ minh họa cấu trúc**, không phải một chính sách đã được phê duyệt:

~~~yaml
policy_id: "SEC-POL-DEMO-001"
title: "Chinh sach kiem soat truy cap du lieu khach hang"
document_status: "DRAFT"
version: "0.1"
effective_date: null
policy_owner: "Bo phan an ninh thong tin"
approval_authority: "Cap co tham quyen theo dieu le"
approved_by: null
scope:
  data: "Du lieu khach hang"
  systems: "Cac ung dung va API xu ly du lieu khach hang"
objectives:
  - "Ngan truy cap du lieu trai quyen"
  - "Co the kiem chung va truy vet truy cap quan trong"
requirements:
  - id: "POL-AUTHZ-001"
    statement: "Moi request doc tai nguyen phai kiem tra quyen"
    control_ref: "CTRL-OBJECT-AUTHZ"
    evidence_plan:
      - "Review luong phan quyen"
      - "Integration test truy cap cheo tai khoan"
      - "Kiem tra tren phien ban trien khai"
    status: "CHUA_XAC_MINH"
exception_process:
  approver: "Risk owner hoac cap duoc uy quyen"
  conditions:
    - "Co ly do va danh gia rui ro"
    - "Co bien phap bu tru khi phu hop"
    - "Co thoi han va ngay xem lai"
review_triggers:
  - "Thay doi he thong xac thuc hoac phan quyen"
  - "Phat hien nghiem trong hoac su co"
  - "Thay doi nghia vu bao ve du lieu"
~~~

Trong môi trường thật, nên dùng ngày hiệu lực và ngày review cụ thể, người phê duyệt được xác thực, tham chiếu chính sách gốc, văn bản phê duyệt, đường dẫn bằng chứng có kiểm soát truy cập và lịch sử thay đổi. Trạng thái **DRAFT** và **CHUA_XAC_MINH** trong ví dụ là cố ý: không được xem chúng là bằng chứng chính sách đã có hiệu lực hoặc control đã được chứng minh.

### 8.1. Chính sách có cần chứa mã nguồn?

Thông thường, **không cần**. Chính sách cần bền vững qua các lần thay đổi công nghệ. Mã nguồn, baseline, kiến trúc và test có thể được dẫn chiếu ở tài liệu kỹ thuật để dễ cập nhật. Điều thiết yếu là duy trì **liên kết truy vết được** giữa quy định và các artifact thực thi.

## 9. Ai chịu trách nhiệm với security policy?

Chính sách liên quan đến nhiều vai trò. Không nên mặc định CISO tự chịu mọi trách nhiệm hay auditor là người phải vận hành control.

| Vai trò | Trách nhiệm phù hợp | Giới hạn cần nhớ |
| --- | --- | --- |
| **Policy owner** | Soạn, duy trì, phối hợp review, truyền đạt và đề xuất sửa đổi chính sách | Không tự phê duyệt nếu điều lệ giao quyền cho cấp khác |
| **Approval authority** | Phê duyệt nội dung, phạm vi, hiệu lực và thay đổi theo thẩm quyền | Không dùng phê duyệt để bỏ qua nghĩa vụ bắt buộc |
| **Risk owner** | Đánh giá tác động nghiệp vụ và quyết định xử lý residual risk trong quyền được giao | Không tự tuyên bố control đã hiệu quả nếu chưa kiểm chứng |
| **Control owner** | Tổ chức triển khai, duy trì control, bằng chứng và khắc phục | Không mặc định có quyền chấp nhận mọi ngoại lệ/rủi ro |
| **Developer / operator / SRE** | Thực hiện control, kiểm thử, giám sát và sửa lỗi | Chỉ đóng kết quả theo tiêu chí và bằng chứng phù hợp |
| **Security team** | Hướng dẫn kỹ thuật, threat modeling, review và giám sát phù hợp | Cần công bố rõ khi đánh giá chính công việc của mình |
| **Assurance reviewer/auditor** | Đánh giá bằng chứng và báo cáo kết luận/phát hiện trong phạm vi | Không thay thế owner trong việc triển khai hoặc chấp nhận rủi ro |
| **Người dùng/nhân viên/đối tác** | Tuân thủ quy định áp dụng trong công việc | Cần được thông báo rõ các yêu cầu liên quan |

### 9.1. RACI tham khảo cho vòng đời chính sách

**R – Responsible**: trực tiếp làm; **A – Accountable**: chịu trách nhiệm cuối cùng; **C – Consulted**: được tham vấn; **I – Informed**: được thông báo.

| Hoạt động | Cấp phê duyệt | Policy owner | Control owner / kỹ thuật | Risk owner | Reviewer/audit |
| --- | --- | --- | --- | --- | --- |
| Soạn và cập nhật dự thảo | C | A/R | C | C | C |
| Phê duyệt chính sách | A | R | C | C | I |
| Chuyển yêu cầu thành control | I | C | A/R | C | C |
| Thực thi và tạo bằng chứng | I | C | A/R | I | C |
| Đánh giá độc lập việc tuân thủ | I | C | C | I | A/R |
| Quyết định chấp nhận rủi ro theo quyền của risk owner | I | C | C | A/R | I |
| Theo dõi thay đổi của văn bản chính sách | I | A/R | C | C | C |

Ma trận này **chỉ là ví dụ** và không thay thế điều lệ phân quyền của từng tổ chức. Mỗi hoạt động nên có một chủ thể chịu trách nhiệm cuối cùng rõ ràng; nhiều người có thể cùng thực hiện.

## 10. Xử lý ngoại lệ chính sách và rủi ro còn lại

Không phải hệ thống nào cũng đáp ứng ngay mọi yêu cầu. Chẳng hạn, một ứng dụng cũ có thể chưa hỗ trợ phương thức MFA được tiêu chuẩn mới chấp nhận. Việc không đáp ứng cần được quản lý bằng **quy trình ngoại lệ có kiểm soát**, không chỉ ghi một chú thích rồi bỏ qua.

Một hồ sơ ngoại lệ nên có:

1. **Yêu cầu bị lệch:** policy ID, điều khoản, hệ thống và phạm vi cụ thể.
2. **Lý do và bối cảnh:** vì sao chưa đáp ứng, ảnh hưởng đến hoạt động nào.
3. **Rủi ro và tác động:** threat scenario, hậu quả, likelihood và độ tin cậy của đánh giá.
4. **Control bù trừ:** biện pháp hạn chế rủi ro tạm thời, cùng bằng chứng hiệu quả nếu có.
5. **Kế hoạch khắc phục:** action owner, mốc công việc và điều kiện đóng.
6. **Thời hạn ngoại lệ và ngày tái đánh giá:** tránh biến ngoại lệ ngắn hạn thành trạng thái vô thời hạn.
7. **Người có thẩm quyền:** ai được phê duyệt, giới hạn thẩm quyền và điều kiện chuyển cấp.
8. **Điều kiện thu hồi ngoại lệ:** khi rủi ro, công nghệ hoặc nghĩa vụ thay đổi.

**Chấp nhận ngoại lệ không có nghĩa đã loại bỏ rủi ro**. Một ngoại lệ có thể hết hạn, bị thu hồi hoặc buộc phải chuyển cấp nếu điều kiện không còn phù hợp. Không được dùng ngoại lệ nội bộ để hợp thức hóa việc vi phạm nghĩa vụ pháp luật bắt buộc.

Nếu ngoại lệ lặp lại ở nhiều dịch vụ, policy owner cần hỏi: do control chưa được triển khai tốt, tiêu chuẩn thiếu khả thi hay chính sách cần thay đổi? Câu trả lời phải dựa vào rủi ro và bằng chứng, không chỉ vào mong muốn giảm số lượng phát hiện.

## 11. Security policy và audit, compliance, security assurance

Một đánh giá không chỉ hỏi **“có chính sách không?”** mà còn có thể hỏi:

1. Chính sách có được phê duyệt đúng thẩm quyền, còn hiệu lực và có phạm vi rõ không?
2. Yêu cầu trong chính sách có được phân rã thành các control có chủ sở hữu không?
3. Control có được thiết kế để giảm đúng kịch bản rủi ro không?
4. Control có **thực sự hoạt động** trên phiên bản/môi trường đang đánh giá không?
5. Các ngoại lệ, phát hiện và rủi ro còn lại có được phê duyệt/xử lý đúng quyền không?
6. Có hồ sơ kết quả kiểm thử lại và cải tiến sau những sai lệch không?

Có thể phân biệt ba mức kiểm chứng:

| Mức | Câu hỏi | Bằng chứng có thể xem |
| --- | --- | --- |
| **Chính sách (governance/design)** | Tổ chức có yêu cầu, trách nhiệm và thẩm quyền rõ không? | Policy đã phê duyệt, điều lệ, danh sách vai trò, lịch sử sửa đổi |
| **Triển khai (implementation)** | Control đã được đưa vào nơi cần thiết chưa? | Thiết kế, cấu hình, pull request, phiên bản build, baseline |
| **Vận hành (operating effectiveness)** | Control hoạt động như yêu cầu trong thực tế không? | Integration/security test, log phù hợp, audit, diễn tập khôi phục, retest |

Mỗi bằng chứng cần xem **độ liên quan, độ bao phủ, nguồn gốc, thời điểm, phiên bản, môi trường và độ tin cậy**. Ví dụ, cấu hình MFA trên môi trường thử nghiệm không chứng minh production đã bật; chứng chỉ đã có từ kỳ trước không bao phủ mọi thay đổi ở kỳ hiện tại.

### 11.1. Liên hệ với các framework

Những khung quản trị và kiểm soát như **ISO/IEC 27001**, **NIST Cybersecurity Framework** hoặc tiêu chí kiểm toán **SOC 2** có thể giúp tổ chức xác định các chủ đề cần chính sách, control và đánh giá, tùy yêu cầu cụ thể.

Tuy vậy, **có tài liệu security policy không tự động tạo sự tuân thủ hoặc chứng nhận**. Việc đánh giá luôn phụ thuộc phạm vi, phiên bản tiêu chí, bằng chứng và quy trình đánh giá áp dụng. Chính sách phải phản ánh nghĩa vụ thật sự của tổ chức thay vì sao chép nguyên mẫu một bộ tiêu chí mà không xem bối cảnh.

## 12. Đo hiệu quả chính sách như thế nào?

Chỉ số tốt cần giúp tổ chức phát hiện khoảng trống và **quyết định hành động**, không chỉ chứng minh “đã ban hành văn bản”.

| Chỉ số tham khảo | Cách sử dụng | Điều cần tránh |
| --- | --- | --- |
| Tỷ lệ yêu cầu trọng yếu có control owner và scope | Đo độ rõ trách nhiệm và phạm vi áp dụng | Ghi owner trên giấy nhưng không có quyền thực thi |
| Tỷ lệ control trọng yếu có bằng chứng còn hiệu lực | Đo mức độ có thể đưa kết luận assurance | Tính cả bằng chứng sai phiên bản hoặc không đúng claim |
| Tỷ lệ control được kiểm tra đúng lịch và có reviewer | Theo dõi việc duy trì đánh giá | Chỉ đếm số lượt chạy tool mà không kiểm tra kết quả |
| Tỷ lệ phát hiện đã khắc phục **và kiểm thử lại đạt** | Đo hiệu quả hành động khắc phục | Đếm ticket “Done” chưa retest |
| Tuổi của các phát hiện quan trọng chưa đóng | Cho thấy rủi ro tồn đọng và vướng nguồn lực | Xem mọi phát hiện như có tác động như nhau |
| Tỷ lệ ngoại lệ hết hạn chưa tái đánh giá | Kiểm tra kỷ luật xử lý ngoại lệ | Coi yêu cầu gia hạn là phê duyệt gia hạn |
| Tỷ lệ thay đổi hệ thống quan trọng được đánh giá tác động chính sách | Kiểm tra assurance theo kịp thay đổi | Tính review hình thức không có đánh giá risk/control |
| Tỷ lệ phát hiện tái diễn sau khi đóng | Đánh giá chất lượng sửa nguyên nhân gốc và hồi quy | Bỏ qua các lỗ hổng giống nhau ở hệ thống khác |

Ví dụ giả định: chính sách phân quyền có **20 yêu cầu trọng yếu** trong phạm vi và **16 yêu cầu** có bằng chứng hợp lệ, còn hiệu lực. Tỷ lệ bao phủ bằng chứng là **16/20 = 80%**. Điều đó **không có nghĩa hệ thống an toàn 80%**: bốn yêu cầu chưa có bằng chứng có thể bao gồm rủi ro nghiêm trọng hơn nhiều so với những yêu cầu đã được kiểm tra.

Nên xem các chỉ số cùng với **mức độ rủi ro, chất lượng bằng chứng, xu hướng và các trường hợp ngoại lệ**.

## 13. Những sai lầm phổ biến

### 13.1. Viết quy định quá chung

“Đảm bảo an toàn tuyệt đối”, “bảo vệ dữ liệu phù hợp” hoặc “sử dụng mã hóa tốt nhất” đều khó kiểm chứng nếu không gắn tiêu chí. **Khắc phục:** xác định tài sản, hành vi bắt buộc, chuẩn áp dụng và bằng chứng cần có.

### 13.2. Sao chép chính sách từ mẫu mà không xét hệ thống thực

Bản mẫu có thể chứa các yêu cầu không tương ứng kiến trúc, dữ liệu hoặc nguồn lực. **Khắc phục:** bắt đầu từ risk assessment, quy định áp dụng và trách nhiệm hiện hữu; điều chỉnh mẫu theo thực tế.

### 13.3. Gộp mục tiêu quản trị và chỉ dẫn cấu hình vào một nơi

Việc sửa một phiên bản giao thức hoặc công cụ có thể khiến văn bản phải phê duyệt lại không cần thiết. **Khắc phục:** giữ chính sách đủ ổn định, tách standard, baseline và procedure với cơ chế tham chiếu rõ ràng.

### 13.4. Chỉ đo sự tồn tại của chính sách

Một policy đã được ký không chứng minh control hoạt động. **Khắc phục:** kiểm tra cả thiết kế, triển khai và vận hành bằng bằng chứng đúng phiên bản/môi trường.

### 13.5. Không giao chủ sở hữu

Nhóm security viết chính sách nhưng không ai chịu trách nhiệm cho việc tích hợp ở sản phẩm. **Khắc phục:** gắn từng yêu cầu trọng yếu với control owner, operator, risk owner và đường chuyển cấp.

### 13.6. Ngoại lệ không có hạn hoặc sai thẩm quyền

Một ticket “đã chấp nhận” có thể tồn tại mãi mà không đánh giá lại. **Khắc phục:** phê duyệt đúng quyền, nêu điều kiện, biện pháp bù trừ và mốc xem xét lại.

### 13.7. Đào tạo và truyền thông không đúng đối tượng

Nhân viên không biết chính sách nào áp dụng cho công việc; developer không biết cách kiểm chứng yêu cầu. **Khắc phục:** cung cấp thông tin theo vai trò, các tiêu chuẩn triển khai, tình huống thực tế và kênh hỗ trợ.

### 13.8. Không đánh giá lại khi có thay đổi

Chính sách hoặc control có thể lạc hậu trước dịch vụ cloud, mô hình truy cập, kiến trúc hoặc rủi ro mới. **Khắc phục:** đặt lịch review và trigger cập nhật gắn với quản lý thay đổi, sự cố và phát hiện audit.

## 14. Sơ đồ tổng thể từ security policy đến bằng chứng

~~~mermaid
flowchart TD
    A["Mục tiêu kinh doanh, tài sản và rủi ro"] --> B["Security policy được phê duyệt"]
    B --> C["Yêu cầu, tiêu chuẩn và baseline"]
    C --> D["Security control có owner và scope"]
    D --> E["Triển khai trong phát triển và vận hành"]
    E --> F["Review, test, audit, monitoring"]
    F --> G{"Bằng chứng có chứng minh yêu cầu?"}
    G -- "Thiếu" --> H["Bổ sung evidence và làm rõ phạm vi"]
    H --> F
    G -- "Không đạt" --> I["Phát hiện, xử lý và kiểm thử lại"]
    I --> D
    G -- "Đạt trong phạm vi" --> J["Kết luận assurance và residual risk"]
    J --> K["Theo dõi thay đổi, ngoại lệ và đánh giá lại"]
    K --> A
~~~

Sơ đồ thể hiện việc assurance **liên tục quay lại xem yêu cầu và rủi ro**, vì hệ thống và bối cảnh bảo mật không đứng yên. Nhánh “đạt” là kết luận có giới hạn, không phải tuyên bố không còn khả năng bị tấn công.

## 15. Checklist xây dựng và áp dụng security policy

- [ ] Mục đích của chính sách liên kết với tài sản, yêu cầu và rủi ro cụ thể.
- [ ] Phạm vi, đối tượng chịu tác động, định nghĩa và điều kiện áp dụng rõ ràng.
- [ ] Các quy định bắt buộc dùng ngôn ngữ thống nhất, có thể chuyển thành tiêu chí kiểm chứng.
- [ ] Có policy owner, người có quyền phê duyệt và ngày hiệu lực.
- [ ] Có bản chính thức, phiên bản, lịch sử thay đổi, nơi công bố và cách truyền đạt.
- [ ] Các yêu cầu trọng yếu liên kết đến tiêu chuẩn, baseline hoặc quy trình phù hợp.
- [ ] Mỗi control có owner, operator, scope và cơ chế chuyển cấp.
- [ ] Đã xác định cách thu thập evidence từ thiết kế, code, cấu hình, kiểm thử và vận hành.
- [ ] Có kế hoạch kiểm tra tính tuân thủ và hiệu quả của control theo mức rủi ro.
- [ ] Các phát hiện có action owner, thời hạn và tiêu chí retest trước khi đóng.
- [ ] Ngoại lệ có thẩm quyền, biện pháp bù trừ, thời hạn và lịch tái đánh giá.
- [ ] Đã xác định trigger xem lại chính sách khi có thay đổi quan trọng hoặc sự cố.
- [ ] Các quyết định về residual risk được đúng người có quyền phê duyệt.
- [ ] Bằng chứng và biên bản được quản lý quyền truy cập và thời hạn lưu phù hợp.

Checklist hỗ trợ chuẩn hóa hoạt động; tự nó **không phải** bằng chứng tổ chức đã tuân thủ toàn bộ yêu cầu bảo mật.

## 16. Câu hỏi tự kiểm tra

1. Security policy khác security control như thế nào? Hãy nêu ví dụ chính sách, control và bằng chứng tương ứng.
2. Vì sao không nên đưa mọi tham số cấu hình cụ thể của Spring Boot vào chính sách cấp tổ chức?
3. Từ yêu cầu “chỉ người có quyền được xem dữ liệu khách hàng”, hãy viết một security claim và hai ca kiểm thử.
4. Một hệ thống đã bật JWT authentication. Điều đó có chứng minh chính sách phân quyền theo tài nguyên được đáp ứng chưa? Vì sao?
5. Policy owner, control owner và risk owner có trách nhiệm khác nhau thế nào khi phát hiện API có lỗi phân quyền?
6. Tại sao ngoại lệ chính sách cần có người phê duyệt, thời hạn, biện pháp bù trừ và lịch tái đánh giá?
7. Bằng chứng test trên phiên bản cũ có thể dùng để kết luận phiên bản production mới không? Cần kiểm tra điều gì?
8. Tổ chức có chứng nhận/audit đạt trong phạm vi A. Có thể suy toàn bộ các hệ thống B và C an toàn không?
9. Khi liên tiếp xuất hiện ngoại lệ đối với cùng một yêu cầu, cần xem xét những nguyên nhân và quyết định nào?
10. Chỉ số “80% yêu cầu có bằng chứng” nói lên điều gì và **không** nói lên điều gì?

## 17. Ghi nhớ

**Security policy** là cam kết và quy định **bắt buộc, được phê duyệt** về cách tổ chức bảo vệ thông tin, tài sản và hệ thống. Chính sách tốt chỉ ra **mục tiêu, phạm vi, trách nhiệm, yêu cầu rõ ràng và cách quản lý ngoại lệ**, đồng thời được cụ thể hóa bằng tiêu chuẩn, quy trình và security controls. Trong **SECURITY_SECURITY_ASSURANCE**, giá trị thực của chính sách nằm ở khả năng **kết nối rủi ro với yêu cầu kiểm chứng được, thu thập bằng chứng về hiệu quả control, đánh giá sai lệch, khắc phục và duy trì assurance sau thay đổi**. Chỉ ban hành chính sách chưa phải là đạt bảo mật; phải chứng minh việc thực thi với bằng chứng phù hợp và kết luận có giới hạn rõ ràng.

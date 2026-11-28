# Data protection requirement

## 1. Yêu cầu bảo vệ dữ liệu phải cụ thể hơn “dữ liệu phải an toàn”

Một hệ thống có thể mã hóa database nhưng vẫn trả thông tin của học viên khác qua API. Nó có thể phân quyền đúng ở màn hình chính nhưng để file export công khai. Nó cũng có thể xóa một bản ghi trong database trong khi bản sao còn nằm trong search index, log và báo cáo đã tạo.

**Data protection requirement** là yêu cầu xác định dữ liệu nào phải được bảo vệ, trước rủi ro nào, trong hoạt động và trạng thái nào, bằng hành vi có thể kiểm chứng của hệ thống cùng quy trình vận hành liên quan.

Trong module yêu cầu bảo mật, mục tiêu là chuyển một mong muốn chung thành những điều đủ rõ để thiết kế, triển khai và nghiệm thu:

```text
Dữ liệu và mục đích sử dụng
    → rủi ro đối với dữ liệu và chủ thể liên quan
    → yêu cầu bảo vệ cụ thể
    → điểm thực thi cùng chủ sở hữu
    → bằng chứng nghiệm thu và duy trì
```

Ví dụ yếu:

> Hệ thống phải bảo vệ thông tin học viên.

Ví dụ có thể triển khai và kiểm chứng:

> Khi học viên đọc tiến độ học tập, server chỉ trả các bản ghi thuộc tenant và tài khoản mà học viên được phép truy cập; những trường phản hồi nằm trong schema đã duyệt. Kiểm tra này áp dụng cho API chi tiết, danh sách và đường export tương ứng, không phụ thuộc việc giao diện có hiển thị dữ liệu hay không.

Ví dụ thứ hai nêu được chủ thể, nhóm dữ liệu, hành vi bắt buộc và các đường cần kiểm tra. Các ngưỡng vận hành cùng ngoại lệ, nếu có, vẫn cần được bổ sung theo chức năng cụ thể.

## 2. Mục tiêu bảo vệ không chỉ là giữ bí mật

Data protection cần xem xét nhiều thuộc tính của dữ liệu:

| Thuộc tính | Câu hỏi | Ví dụ trên nền tảng học tập |
| --- | --- | --- |
| Bí mật | Ai được biết dữ liệu hoặc một phần của dữ liệu? | Học viên không đọc được bài làm riêng của người khác |
| Toàn vẹn | Ai được sửa, sửa qua luồng nào và sai lệch được phát hiện thế nào? | Client không tự đặt điểm số đã chấm |
| Khả dụng | Dữ liệu cần dùng có thể được truy cập và khôi phục đúng lúc không? | Tiến độ không mất ngoài mục tiêu phục hồi đã chọn |
| Đúng mục đích và giảm thiểu | Có cần thu thập, dùng hoặc chia sẻ phần dữ liệu này cho chức năng đó không? | Báo cáo tiến độ không cần chứa token đăng nhập hoặc địa chỉ nhà |
| Khả năng đối chiếu | Có thể xác định những hoạt động quan trọng mà không làm lộ thêm dữ liệu không? | Biết ai tạo export và trong phạm vi khóa học nào |
| Vòng đời có kiểm soát | Dữ liệu được giữ, chuyển, xóa và phục hồi theo quy tắc nào? | File export hết hạn không tiếp tục được tải qua URL cũ |

Dữ liệu công khai vẫn có yêu cầu toàn vẹn và khả dụng. Một mô tả khóa học không cần bí mật nhưng bị sửa sai có thể ảnh hưởng người học. Ngược lại, một dữ liệu riêng tư có thể vẫn gây rủi ro nếu được sử dụng quá mục đích dù không có truy cập trái phép.

[NIST Privacy Framework](https://www.nist.gov/privacy-framework) tiếp cận quyền riêng tư qua quản lý rủi ro đối với cá nhân. Trong thiết kế dự án, điều này gợi mở một câu hỏi riêng bên cạnh chống rò rỉ: hoạt động xử lý đã được cho phép có tạo tác động không mong muốn cho người mà dữ liệu mô tả hay không?

Không nên gom mọi mục tiêu vào một checkbox “encrypted”. Mã hóa, quyền truy cập, tính đúng của nghiệp vụ và vòng đời dữ liệu có những tiêu chí hoàn thành khác nhau.

## 3. Xác định dữ liệu, owner và mục đích trước khi chọn công cụ

Giả sử một nền tảng học tập nhiều tenant xử lý các nhóm sau:

| Nhóm dữ liệu | Mục đích minh họa | Chủ sở hữu nghiệp vụ cần xác định |
| --- | --- | --- |
| Hồ sơ tài khoản | Nhận diện người học và liên hệ cho chức năng được chọn | Đơn vị quản lý tài khoản |
| Tiến độ học | Hiển thị quá trình hoàn thành bài học | Chủ sở hữu sản phẩm học tập |
| Bài làm và điểm | Chấm, phản hồi và theo dõi kết quả theo phạm vi khóa học | Chủ sở hữu chức năng đánh giá |
| Danh mục khóa học công khai | Giới thiệu nội dung được phát hành | Đơn vị quản lý nội dung |
| Log và sự kiện an toàn | Chẩn đoán, đối chiếu và phát hiện lạm dụng | Đơn vị vận hành/an toàn theo policy |
| File export | Phục vụ một báo cáo có người yêu cầu và người nhận cụ thể | Chủ sở hữu báo cáo |

Các nhóm chỉ là ví dụ. Dự án phải xác nhận chủ thể quyết định mục đích, phân loại, quyền sử dụng và thời gian giữ. Người vận hành database không tự mặc định là người có quyền quyết định công khai mọi dữ liệu trong database.

### Câu hỏi cần trả lời cho từng trường hoặc nhóm trường

1. Vì sao chức năng cần dữ liệu này?
2. Nguồn nào cung cấp, và nguồn nào được xem là có thẩm quyền?
3. Dữ liệu có mô tả một cá nhân, một tổ chức hay một bí mật hệ thống không?
4. Ai được đọc, tạo, sửa, xuất hoặc yêu cầu xóa?
5. Những bản dẫn xuất nào có thể giữ cùng thông tin?
6. Sự kiện nào bắt đầu hoặc kết thúc thời gian giữ?
7. Điều gì xảy ra nếu dữ liệu lộ, sai hoặc không dùng được?

Không thu thập một trường chỉ vì có thể hữu ích trong tương lai mà chưa có quyết định mục đích và trách nhiệm. Một trường bổ sung cũng làm tăng những đường phải bảo vệ, kiểm tra, lưu giữ và xử lý khi sự cố xảy ra.

## 4. Phân loại theo tác động và ngữ cảnh

Các nhãn như công khai, nội bộ, nhạy cảm hoặc hạn chế có thể giúp ánh xạ policy, nhưng nhãn phải có định nghĩa và chủ sở hữu. Không nên tự suy mức bảo vệ chỉ từ tên cột.

Một ma trận tác động minh họa:

| Dữ liệu | Nếu lộ | Nếu bị sửa sai | Nếu không truy cập được |
| --- | --- | --- | --- |
| Danh mục khóa học công khai | Có thể ít ảnh hưởng về bí mật | Có thể phát hành nội dung hoặc thông tin sai | Người học không tìm được khóa học |
| Email tài khoản | Có thể hỗ trợ liên kết danh tính hoặc lừa đảo | Có thể gửi thông báo sai người | Một số luồng liên hệ không hoạt động |
| Tiến độ và bài làm riêng | Lộ hoạt động hoặc nội dung cá nhân | Ghi nhận sai kết quả và trải nghiệm | Không tiếp tục hoặc đối chiếu được quá trình học |
| Điểm đánh giá | Lộ kết quả ngoài phạm vi được phép | Có thể làm sai kết luận học tập | Không cung cấp được báo cáo cần thiết |
| Token hoặc khóa hệ thống | Có thể cấp khả năng truy cập trái phép | Có thể làm hỏng cơ chế xác thực/mật mã | Dịch vụ phụ thuộc không hoạt động |

Phân loại cần xét dữ liệu kết hợp. Một mã học viên không chứa tên nhưng có thể được liên kết với danh sách khác. Một thống kê của nhóm rất nhỏ có thể cho phép suy đoán thông tin từng người.

Không tự xem dữ liệu đã băm, che một phần hoặc đổi sang mã giả là dữ liệu vô danh. Yêu cầu phải mô tả phép biến đổi và rủi ro liên kết/suy luận còn lại trong ngữ cảnh sử dụng.

### Phân loại và quyền không phải cùng một bảng

Nhãn “nhạy cảm” cho biết một thuộc tính của dữ liệu theo policy. Nó chưa nói học viên nào, giảng viên nào hoặc workload nào được phép thao tác với từng tài nguyên.

Hệ thống vẫn cần quan hệ với tenant, khóa học, học viên và tác vụ. Một giảng viên được đọc kết quả của lớp mình không mặc nhiên được đọc mọi dữ liệu cùng nhãn trên toàn nền tảng.

## 5. Theo dõi dữ liệu qua toàn bộ vòng đời

Một luồng tiến độ học có thể tạo nhiều bản lưu:

```text
Ứng dụng người học
    → API xử lý tiến độ
        ├── Database chính
        ├── Cache hoặc search index
        ├── Sự kiện/hàng đợi xử lý
        ├── Báo cáo và file export
        └── Log/trace có chọn lọc

Các nơi lưu bền vững
    → Replica / snapshot / backup
    → Môi trường phục hồi theo quyền được cấp
```

Vì một nguồn tạo ra nhiều nhánh, yêu cầu bảo vệ không thể dừng ở database chính. Mỗi bản sao có người được đọc, thời gian giữ và khả năng công khai riêng.

Một inventory có thể có các trường:

```yaml
dataGroup: learner-progress
purpose: show-and-report-authorized-learning-progress
owner: learning-product-team
authoritativeSource: progress-service
scopeDimensions:
  - tenant
  - learner
  - course
copies:
  - primary-store
  - progress-cache
  - reporting-export
  - protected-backup
policyProfile: learner-progress-profile-v1
```

Đây là ví dụ mô tả yêu cầu, không phải schema hệ thống hoặc file cần tạo trong dự án. Các tên logic cần được ánh xạ sang thành phần thật trước khi dùng để nghiệm thu.

### Dữ liệu dẫn xuất vẫn có owner

Một chỉ mục tìm kiếm chứa email, một file CSV có điểm hoặc payload trong dead-letter queue đều có thể giữ thông tin cần bảo vệ. Không coi chúng là “dữ liệu kỹ thuật” rồi loại khỏi policy của chức năng.

Các bước cần kiểm kê gồm thu thập, kiểm tra, sử dụng, lưu, sao chép, chia sẻ, tổng hợp, xuất, lưu giữ, xóa và phục hồi. Những nơi không có trong kiến trúc nên được ghi nhận là không áp dụng với bằng chứng phù hợp, thay vì âm thầm bỏ trống.

## 6. Chuyển rủi ro thành yêu cầu kiểm chứng được

Một yêu cầu nên có những thành phần sau:

| Thành phần | Nội dung cần nêu |
| --- | --- |
| ID và mục tiêu | Yêu cầu bảo vệ điều gì và liên quan rủi ro nào |
| Phạm vi dữ liệu | Nhóm dữ liệu, trường, tài nguyên và bản sao |
| Chủ thể/ngữ cảnh | Ai thao tác, tenant/quan hệ nào, mục đích nào |
| Hành vi bắt buộc | Hệ thống phải cho phép, từ chối hoặc biến đổi ra sao |
| Điểm thực thi | Thành phần có thẩm quyền giữ điều kiện đó |
| Tham số | Thời hạn, giới hạn, profile hoặc ngưỡng đã quyết định |
| Hành vi lỗi | Điều xảy ra khi không xác định được policy hoặc dependency không khả dụng |
| Owner và bằng chứng | Ai thực hiện, kiểm chứng bằng cách nào |
| Ngoại lệ | Phạm vi, lý do, thời hạn và cách quản lý nếu policy cho phép |

Ví dụ từ một rủi ro:

```text
Rủi ro:
  Giảng viên tải báo cáo có dữ liệu của lớp ngoài phạm vi được giao.

Yêu cầu:
  Dịch vụ báo cáo phải xác định phạm vi từ danh tính và phân công có thẩm quyền.
  Chỉ tạo và cung cấp file với các dòng, trường thuộc biểu diễn được phép.
  Kiểm tra quyền tại các thời điểm được hợp đồng job/download quy định.

Bằng chứng:
  Thử hai giảng viên ở hai khóa học, một người đã bị thu hồi phân công,
  một request tự sửa courseId/tenantId và một file được tạo trước thay đổi quyền.
```

Không biến yêu cầu thành câu mô tả công cụ như “dùng một thư viện mã hóa”. Công cụ phải được gắn với điều kiện an toàn cần giữ. Nếu có thay công cụ, mục tiêu bảo vệ vẫn phải giữ nguyên hoặc được thay đổi theo quy trình của dự án.

## 7. Thu thập và xử lý đúng phạm vi

Giảm thiểu dữ liệu bắt đầu trước khi lưu. Nếu một chức năng chỉ cần mã học viên và trạng thái hoàn thành, không nên gửi thêm toàn bộ hồ sơ cho mọi worker hoặc dịch vụ phân tích.

Một yêu cầu thu thập có thể xác định:

- Tập trường được nhận và mục đích sử dụng của từng nhóm.
- Giới hạn kích thước và loại nội dung.
- Cách xử lý trường không hỗ trợ.
- Những giá trị server phải tự tính hoặc lấy từ nguồn có thẩm quyền.
- Những nơi không được sao chép raw payload.

Ví dụ, API nộp bài có thể nhận câu trả lời nhưng không nhận `finalScore` như một giá trị có thẩm quyền từ client. Một trường nhìn thấy được ở response không đồng nghĩa client có quyền ghi lại trường ấy.

Validation giúp giữ cấu trúc và ràng buộc dữ liệu, nhưng không thay quyền truy cập hoặc policy mục đích. Một email đúng định dạng vẫn có thể không cần thiết cho một báo cáo tiến độ.

### Không tự diễn giải lại mục đích từ một tham số request

Client có thể gửi `purpose=analytics` hoặc `role=teacher`, nhưng giá trị đó không tự cấp quyền xử lý tương ứng. Mục đích được phép phải gắn với chức năng và chủ thể đã được kiểm tra, không phải một nhãn tùy ý trong body.

Khi mở một tính năng phân tích mới, cần đánh giá lại trường dữ liệu, người nhận và khả năng suy luận, thay vì mặc định mọi dữ liệu đã có trong hệ thống đều sẵn sàng dùng cho chức năng mới.

## 8. Quyền trên đối tượng, thuộc tính và tenant

Data protection cần kết nối với authorization. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) đề cập quyền tối thiểu, mặc định từ chối và kiểm tra quyền trên từng request. Các nguyên tắc này phải được ánh xạ tới tài nguyên và quan hệ của ứng dụng.

Ví dụ ma trận đọc dữ liệu:

| Chủ thể | Phạm vi tài nguyên | Biểu diễn có thể được cấp |
| --- | --- | --- |
| Học viên | Tiến độ của chính mình theo tenant/khóa học hợp lệ | Trường tiến độ và kết quả đã được công bố theo chức năng |
| Giảng viên | Lớp/khóa học được phân công | Báo cáo theo nhiệm vụ, không tự kèm bí mật tài khoản |
| Hỗ trợ | Vụ việc và phạm vi được giao | Thông tin tối thiểu cho tác vụ hỗ trợ |
| Workload chấm bài | Bài làm thuộc công việc đã cấp | Dữ liệu cần để chấm, không phải mọi hồ sơ cá nhân |
| Người dùng công khai | Nội dung đã phát hành công khai | Danh mục và nội dung công khai theo schema |

Bảng chỉ minh họa một mô hình quyền. Dự án cần xác nhận các điều kiện như trạng thái phân công, thời điểm phát hành kết quả và quan hệ tenant cụ thể.

### Kiểm tra tài nguyên chưa đủ cho mọi trường

[OWASP API Security về quyền ở mức thuộc tính](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/) nhấn mạnh việc chỉ công khai và cho sửa những thuộc tính được phép. Vì vậy, một học viên có quyền đọc hồ sơ của mình vẫn không có lý do nhận password hash, reset token hoặc ghi chú xử lý nội bộ.

Ứng dụng nên định nghĩa biểu diễn đầu ra bằng danh sách cho phép. Không serialize toàn bộ entity rồi trông chờ frontend ẩn trường. Các object con, array, metadata và header cũng thuộc đầu ra cần kiểm tra.

### Cache và đường dẫn tải phải giữ cùng ranh giới

Nếu cùng URL trả biểu diễn khác nhau theo danh tính, cache dùng chung không được phát lại biểu diễn rộng quyền cho một người khác. Một URL tải file khó đoán cũng không thay được chính sách về người nhận, thời hạn và quyền đọc.

Yêu cầu phải bao phủ cả đường truy cập trực tiếp tới file/object nếu đường đó tồn tại. Bảo vệ API tạo link nhưng để file công khai vẫn là một khoảng trống trong luồng dữ liệu.

## 9. Bí mật, toàn vẹn và khả dụng cần các kiểm soát phù hợp

### Bảo vệ khi truyền và lưu

Cần xác định những chặng truyền và nơi lưu thuộc phạm vi, danh tính hai đầu, profile mã hóa và quyền dùng khóa. [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) lưu ý chọn lớp mã hóa theo threat model và giảm dữ liệu nhạy cảm cần giữ.

Mã hóa volume/database có thể bảo vệ một bản lưu trước một số cách lấy dữ liệu, nhưng không tự ngăn tài khoản có quyền truy vấn hợp lệ đọc dữ liệu rõ. Mã hóa ở ứng dụng cũng không thay kiểm tra quyền trước khi giải mã và công khai kết quả.

Yêu cầu phải bao gồm phụ thuộc khóa, backup và hành vi khi không thể mã hóa/giải mã. Không cho phép lưu rõ như fallback ngoài policy chỉ để tác vụ không báo lỗi.

### Toàn vẹn dữ liệu nghiệp vụ

Với điểm số, yêu cầu có thể gồm:

- Nguồn có thẩm quyền cho phép tính và thay đổi kết quả.
- Quyền hiệu chỉnh cùng lý do/sự kiện đối chiếu phù hợp.
- Kiểm tra phiên bản để tránh ghi đè thay đổi đồng thời ngoài quy tắc.
- Tính nhất quán giữa bài làm, kết quả và trạng thái công bố.
- Cách phát hiện và xử lý dữ liệu bị sửa hoặc payload không hợp lệ.

Một phép mã hóa hoặc checksum không tự chứng minh giá trị điểm là đúng nghiệp vụ. Nếu client tự gửi điểm và server tin nó, dữ liệu vẫn có thể được mã hóa hoàn toàn đúng nhưng sai ý nghĩa.

### Khả dụng và phục hồi có giới hạn

Mục tiêu phục hồi cần nêu tập dữ liệu, mức mất dữ liệu chấp nhận được, thời gian cần sử dụng lại và những phụ thuộc như khóa, policy hoặc phiên bản định dạng.

Một backup hoàn tất về kỹ thuật không đủ nếu môi trường đích thiếu khóa hoặc restore làm công khai kết quả chưa được phép. Bằng chứng cần kiểm tra cả đọc hợp lệ và từ chối truy cập không hợp lệ sau phục hồi.

## 10. Retention và xóa phải có mốc cùng phạm vi

“Giữ dữ liệu khi còn cần” hoặc “xóa sau một thời gian” không đủ để hiện thực. Yêu cầu phải nêu:

1. Sự kiện bắt đầu tính thời gian.
2. Giá trị thời hạn do policy quyết định.
3. Bản dữ liệu và bản sao nào thuộc phạm vi.
4. Hạn chót thực hiện và cách đo độ trễ.
5. Ngoại lệ có điều kiện nào được cho phép.
6. Bằng chứng kết thúc và cách xử lý job thất bại.

### Phân biệt hết quyền truy cập với xóa vật lý

Trong một chính sách export giả định:

```text
File export chỉ được tải trong tối đa 24 giờ kể từ lúc tạo thành công.
Sau mốc đó, mọi đường tải thuộc hợp đồng phải từ chối.
Artifact ở kho hoạt động được dọn trong vòng 1 giờ tiếp theo.
Các bản backup tuân theo retention riêng đã được xác định.
```

Các con số chỉ là ví dụ thiết kế, không phải thời hạn dùng chung cho mọi dữ liệu học tập. Dự án cần quyết định chúng theo chức năng, rủi ro và những nghĩa vụ thực sự áp dụng.

Một URL hết hạn không chứng minh file đã bị xóa. Một file đã bị xóa ở kho chính cũng không chứng minh mọi cache hoặc bản export khác đã được xử lý.

### Xóa là một workflow qua các bản sao

Luồng xóa dữ liệu có thể cần cập nhật database, cache, search index, file export và các bản gửi sang hệ thống khác. Nếu không thể thực hiện đồng thời, cần trạng thái tiến trình, retry có kiểm soát và đối chiếu phần tồn đọng.

Không đánh dấu hoàn tất chỉ vì một row chính đã bị xóa. Ngược lại, không hứa xóa tức thì mọi byte trong một kiến trúc có backup lịch sử mà không có cơ chế đáp ứng.

### Restore không làm sống lại dữ liệu ngoài policy hiện hành

Backup có thể phản ánh một thời điểm trước quyết định xóa hoặc thu hồi quyền. Runbook cần đối chiếu những quyết định hiện hành trước khi đưa dữ liệu được restore trở lại phục vụ.

Nguồn ghi nhận việc xóa/thu hồi cũng cần được bảo vệ và có thể dùng trong kịch bản phục hồi. Nếu nguồn duy nhất nằm trong chính snapshot cũ, hệ thống có thể mất thông tin cần để áp dụng policy mới.

## 11. Dữ liệu ngoài production và bên nhận bên ngoài

### Môi trường phát triển và kiểm thử

Sao chép database production sang môi trường thử không tự trở nên an toàn vì môi trường ấy được gọi là staging. Tập người có quyền, công cụ debug, backup và khả năng gửi dữ liệu có thể khác hẳn.

Một yêu cầu của dự án có thể chọn dữ liệu tổng hợp làm mặc định cho phát triển. Nếu phải sử dụng dữ liệu có nguồn từ môi trường thật, cần quyết định rõ tập trường, phép biến đổi, quyền, nơi giữ, thời hạn và kiểm tra rủi ro tái liên kết.

Che tên nhưng giữ email, định danh ổn định, bài làm tự do và lịch sử chi tiết có thể vẫn cho phép nhận diện. Không coi một lần chạy script masking là bằng chứng đủ cho mọi mục đích chia sẻ dữ liệu.

### Dịch vụ phân tích hoặc tích hợp đối tác

Mỗi luồng gửi dữ liệu ra ngoài cần có:

- Người nhận và endpoint được phép.
- Tập trường cùng mục đích gửi.
- Cơ chế xác thực, bảo vệ truyền tải và kiểm soát quyền.
- Policy lưu giữ, xử lý lỗi và kết thúc chia sẻ theo hợp đồng được chọn.
- Khả năng nhận biết hoặc đối chiếu dữ liệu đã gửi.

Không gửi nguyên entity chỉ vì API đối tác chấp nhận JSON linh hoạt. Khi một chức năng phân tích chỉ cần số lượng hoàn thành, hồ sơ liên hệ của từng học viên không tự trở thành cần thiết.

Payload webhook, sự kiện hàng đợi và attachment hỗ trợ cũng là đường xuất dữ liệu. Chúng cần cùng cách kiểm kê và quyết định phạm vi, thay vì được xem là phần kỹ thuật nằm ngoài data protection.

## 12. Logging và audit không tạo thêm một kho dữ liệu nhạy cảm

Hệ thống cần khả năng đối chiếu hoạt động nhưng không cần ghi mọi giá trị. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) nêu các nhóm cần loại bỏ hoặc bảo vệ khi ghi log như token, mật khẩu, khóa và dữ liệu nhạy cảm; đồng thời lưu ý bảo vệ quyền truy cập và tính toàn vẹn của log.

Với nền tảng minh họa, một sự kiện export có thể cần mã tác vụ, chủ thể đã xác minh, phạm vi khóa học, số bản ghi và kết quả. Nó thường không cần toàn bộ CSV, raw request hoặc token dùng để tải file.

Một hợp đồng quan sát nên xác định:

- Sự kiện bắt buộc và những dữ liệu được phép ghi.
- Định danh nào hỗ trợ liên hệ mà không trở thành credential.
- Quyền đọc, thời hạn giữ và nơi gửi log/trace.
- Giới hạn kích thước, kiểu và xử lý dữ liệu không tin cậy.
- Hành vi khi hệ thống quan sát lỗi.
- Những operation cần bằng chứng đối chiếu bền vững theo policy riêng.

Không mặc định một lỗi nghiệp vụ là quyền ghi toàn bộ nội dung người dùng để debug. Không đưa email, raw URL chứa dữ liệu hoặc định danh không giới hạn thành nhãn metric chỉ vì công cụ cho phép.

### Audit cũng cần giảm dữ liệu

Một audit log có quyền đọc quá rộng có thể trở thành đường xem tiến độ hoặc điểm ngoài chức năng chính. Policy dữ liệu cần theo được thông tin sang kho audit, bao gồm các bản export từ công cụ audit.

Nếu nghiệp vụ cần giữ bằng chứng sau khi dữ liệu gốc được xóa, phải xác định tập thông tin tối thiểu còn cần và thời gian giữ của chính bằng chứng đó. Không giữ toàn bộ nội dung dưới nhãn “audit” vô thời hạn mà chưa có quyết định mục đích.

## 13. Hành vi lỗi là một phần của yêu cầu bảo vệ

Những tình huống cần được đặc tả gồm:

- Không tải được policy hoặc không xác định được tenant có thẩm quyền.
- Không thể mã hóa dữ liệu cần bảo vệ hoặc không thể dùng khóa.
- Không tạo được bằng chứng bắt buộc của một operation nhạy cảm.
- Job xóa, export hoặc migration chỉ hoàn tất một phần.
- Một dịch vụ bên nhận không xác nhận kết quả.
- Cache chứa dữ liệu hoặc policy cũ ngoài giới hạn được chọn.

Hệ thống không được tự gán một tenant chung, mở toàn bộ trường hoặc ghi rõ ra một đường tạm ngoài policy để vượt qua lỗi. Thay vào đó, hành vi từ chối, chờ, retry hoặc phục hồi phải được xác định cho từng operation.

Không phải mọi lỗi log đều buộc mọi chức năng ngừng hoạt động. Nhưng nếu một yêu cầu của dự án quy định export nhạy cảm chỉ được chạy sau khi có bằng chứng bền vững, đường lỗi của chính operation ấy phải giữ điều kiện đó.

Response lỗi cần đủ thông tin để client xử lý theo hợp đồng, không chứa dữ liệu của người khác, credential, raw entity hoặc chi tiết hạ tầng không thuộc phạm vi công khai.

## 14. Ví dụ từ policy tới điểm thực thi

Giả sử endpoint đọc tiến độ có luồng logic sau:

```text
readLearnerProgress(request):
    principal = establishVerifiedIdentity(request)
    resource = resolveResourceWithinAuthorizedScope(principal, request.resourceRef)
    policy = resolveApplicableDataPolicy(principal, resource, "read-progress")

    if policy cannot be established or does not allow the action:
        return controlledDenialWithoutProtectedData()

    data = loadOnlyDataRequiredByPolicy(resource, policy)
    responseView = buildAllowlistedResponse(data, policy.allowedFields)

    recordApprovedAuditMetadata(principal, resource, policy)
    return encodeAccordingToResponseContract(responseView)
```

Đây là mã giả về trách nhiệm, không phải implementation framework hay lời khuyên rằng một chuỗi `purpose` bất kỳ do client gửi được tin cậy.

Các điểm cần chú ý:

- Danh tính đã được xác minh trước khi dùng làm nguồn quyết định.
- Tham chiếu tài nguyên phải được giải quyết trong phạm vi quyền, không chỉ lookup theo ID.
- Policy quyết định trường phản hồi ở server.
- Dữ liệu quan sát là metadata đã được cho phép, không phải toàn bộ nội dung.
- Những đường khác như export hoặc search cần điểm thực thi tương ứng.

Một helper dùng chung có thể giảm bỏ sót, nhưng vẫn phải kiểm tra mọi đường đi thực tế. Việc có một hàm tên `protectData()` không chứng minh các controller, job nền và đường tải file đều dùng nó đúng.

## 15. Mẫu yêu cầu cho chức năng tiến độ và export

### DP-LRN-01 — Phạm vi đọc tiến độ

> Server chỉ trả tiến độ thuộc quan hệ học viên–tenant–khóa học được phép. Tenant và danh tính dùng cho quyết định không chỉ lấy từ giá trị tự khai trong request. Endpoint danh sách, chi tiết và dữ liệu lồng nhau cùng tuân theo chính sách.

Bằng chứng gồm học viên A/B, tenant khác, ID đoán được, tài khoản đã bị thu hồi quyền và những đường endpoint tương đương.

### DP-LRN-02 — Tập trường phản hồi

> Response tiến độ chỉ có những thuộc tính trong biểu diễn đã duyệt. Việc entity được bổ sung trường nội bộ không tự làm thay đổi đầu ra API.

Bằng chứng gồm kiểm tra tập trường ở mọi mức, một trường nội bộ mới trong dữ liệu thử và response lỗi có liên quan.

### DP-LRN-03 — Toàn vẹn điểm

> Chỉ thành phần được cấp nhiệm vụ chấm hoặc hiệu chỉnh mới tạo được giá trị điểm có thẩm quyền. Thuộc tính điểm do client không được cấp quyền gửi không được tự bind vào trạng thái kết quả.

Bằng chứng gồm request gửi thêm trường, principal không có quyền, thay đổi đồng thời và dấu vết hiệu chỉnh theo policy.

### DP-LRN-04 — Export có thời hạn

> File export chỉ chứa dòng/trường trong phạm vi nhiệm vụ và có thời hạn truy cập đã công bố. Quyền tại lúc tạo, chạy job và tải file được xử lý theo hợp đồng; thay đổi quyền trong thời gian đó có hành vi xác định.

Bằng chứng gồm job tạo trước khi thu hồi phân công, tải trực tiếp object, URL hết hạn và cache được làm nóng bằng chủ thể có quyền rộng hơn.

### DP-LRN-05 — Vòng đời bản sao

> Quyết định kết thúc retention áp dụng qua inventory bản sao và dữ liệu dẫn xuất. Workflow phải ghi nhận phần tồn đọng, retry và kết quả đối chiếu; restore lịch sử không tự tái công khai dữ liệu ngoài policy hiện hành.

Bằng chứng gồm database, cache, index, export và tình huống restore từ bản trước quyết định xóa.

Các yêu cầu trên là ví dụ thiết kế, chưa thay cho policy chính thức của một nền tảng giáo dục cụ thể.

## 16. Danh mục yêu cầu nền tảng có thể nghiệm thu

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| DP-01 | Có inventory nhóm dữ liệu, mục đích, owner, nguồn có thẩm quyền và bản sao | Đối chiếu luồng chức năng với nơi lưu, export và tích hợp |
| DP-02 | Phân loại phản ánh tác động bí mật, toàn vẹn, khả dụng và ngữ cảnh kết hợp | Ma trận tác động được ánh xạ tới policy cụ thể |
| DP-03 | Chỉ thu thập và truyền những trường cần cho mục đích được cho phép | Kiểm tra schema đầu vào, job payload và luồng sang dịch vụ khác |
| DP-04 | Quyền trên tài nguyên, thuộc tính và tenant được thực thi ở nơi có thẩm quyền | Thử chủ thể hợp lệ/không hợp lệ cùng request tự sửa phạm vi |
| DP-05 | Biểu diễn đầu ra dùng tập trường được phép ở mọi mức | Kiểm tra cấu trúc response, lỗi, metadata và dữ liệu lồng nhau |
| DP-06 | Các chặng truyền và nơi lưu cần bảo vệ có profile cùng phụ thuộc khóa xác định | Cấu hình, hành vi và thử quyền phù hợp threat model |
| DP-07 | Các giá trị nghiệp vụ có thẩm quyền không bị ghi đè ngoài quy tắc | Thử input thừa, quyền ghi, version và tính nhất quán |
| DP-08 | Cache, link tải và object storage giữ ranh giới người nhận/thời hạn | Làm nóng cache bằng nhiều chủ thể, thử đường tải trực tiếp và hết hạn |
| DP-09 | Retention có trigger, phạm vi, hạn thực thi và cơ chế đối chiếu | Đo workflow trên dữ liệu thử sát và vượt mốc |
| DP-10 | Xóa bao phủ các bản sao đã xác định và trạng thái từng phần | Đối chiếu database, index, cache, export và bên nhận liên quan |
| DP-11 | Backup/restore giữ tính đọc đúng cùng quyền và quyết định vòng đời hiện hành | Diễn tập phục hồi với dữ liệu cũ, quyền đã thu hồi và khóa cần thiết |
| DP-12 | Dữ liệu ngoài production và gửi bên ngoài có profile riêng | Kiểm tra tập trường, người nhận, biến đổi, quyền và thời gian giữ |
| DP-13 | Log/trace/audit có danh mục dữ liệu được phép và quyền đọc | Dùng dấu hiệu thử tổng hợp để kiểm tra luồng thành công và lỗi |
| DP-14 | Lỗi policy/khóa/job không mở quyền hoặc tạo plaintext fallback ngoài chính sách | Gây lỗi có kiểm soát và quan sát trạng thái dữ liệu thật của phép thử |
| DP-15 | Ngoại lệ và thay đổi chức năng có owner, phạm vi cùng thời hạn xem xét | Đối chiếu policy, kiểm thử hồi quy và thay đổi inventory |

Tên ID có thể thay theo dự án, nhưng mỗi yêu cầu phải truy được về rủi ro, điểm thực thi và bằng chứng. “Đã dùng công cụ bảo mật” không phải một trạng thái nghiệm thu đủ rõ.

## 17. Kịch bản chấp nhận minh họa

### 17.1. Học viên không nhận tiến độ ngoài phạm vi

```text
Given:
  Học viên A có quyền với tiến độ của A trong tenant đã xác định.
  Có dữ liệu thử của học viên B và một tenant khác.

When:
  A sửa tham chiếu tài nguyên hoặc tenant trong request đọc.

Then:
  Server không trả dữ liệu ngoài phạm vi.
  Không có trường lồng, tổng số hoặc metadata trái chính sách tiết lộ.
  Đường đọc hợp lệ của A vẫn trả đúng biểu diễn được phép.
```

### 17.2. Entity có thêm trường nội bộ

```text
Given:
  Profile phản hồi tiến độ đã được duyệt.
  Nguồn dữ liệu thử có thêm internalReviewNote.

When:
  API tạo response chi tiết, danh sách và export tương ứng.

Then:
  Trường mới không tự xuất hiện ngoài hợp đồng.
  Không chỉ kiểm tra giao diện đã ẩn trường đó.
```

### 17.3. Thu hồi phân công khi export chưa được tải

```text
Given:
  Giảng viên G đã tạo một export trong phạm vi được cấp.
  Phân công liên quan sau đó bị thu hồi.
  Hợp đồng download yêu cầu kiểm tra quyền hiện hành.

When:
  G yêu cầu tải file.

Then:
  Quyền được đánh giá theo hợp đồng đã chọn.
  Không có đường object trực tiếp hoặc cache làm bỏ qua quyết định.
  Audit ghi kết quả mà không ghi nguyên nội dung file hay credential.
```

### 17.4. Xóa một nhóm dữ liệu có bản dẫn xuất

```text
Given:
  Có quyết định xóa theo policy và không có ngoại lệ đang áp dụng cho tập dữ liệu thử.
  Inventory có database, cache, search index và file export.

When:
  Workflow xóa chạy tới hạn hoàn tất đã công bố.

Then:
  Các đường phục vụ dữ liệu phản ánh đúng trạng thái policy.
  Kết quả của từng bản sao được đối chiếu.
  Một job lỗi không bị che bằng trạng thái hoàn tất chung.
```

### 17.5. Restore từ bản trước quyết định vòng đời

```text
Given:
  Backup thử được tạo trước một quyết định xóa hoặc thu hồi quyền.
  Quy trình phục hồi có nguồn trạng thái hiện hành cần thiết.

When:
  Restore được thực hiện trong môi trường kiểm chứng.

Then:
  Dữ liệu được đọc đúng trong phạm vi được phép.
  Quyền cũ hoặc dữ liệu ngoài policy không tự được đưa lại vào phục vụ.
  Kết quả thể hiện cả khả năng phục hồi và ranh giới dữ liệu.
```

## 18. Bằng chứng và giới hạn của kết luận

Một bộ bằng chứng nên kết hợp:

| Mức kiểm tra | Điều cần quan sát |
| --- | --- |
| Hợp đồng dữ liệu | Trường, kiểu, chủ thể, mục đích và thời hạn được định nghĩa rõ |
| Đường gọi thực tế | API, job, file, search, error response và tích hợp có cùng policy tương ứng |
| Chủ thể/tenant | Không chỉ principal hợp lệ mà cả các trường hợp ngoài phạm vi |
| Trạng thái vòng đời | Trước/sau hết hạn, thu hồi, xóa và phục hồi |
| Lưu trữ và khóa | Cơ chế có hiệu lực và quyền đọc/giải mã đúng ranh giới |
| Kênh quan sát | Không phát tán dữ liệu qua log, trace, báo cáo hoặc công cụ hỗ trợ |
| Vận hành | Owner, tiến trình tồn đọng, cảnh báo và khả năng khắc phục có thực tế |

Nên dùng dữ liệu tổng hợp có dấu hiệu dễ nhận diện để kiểm tra nơi thông tin đi tới. Không đưa thông tin thật hoặc credential vào báo cáo nhằm chứng minh đã phát hiện được chúng.

Một ảnh giao diện ít trường không chứng minh API không trả dư. Một backup restore thành công không chứng minh quyền đã đúng. Một phép tìm không thấy chuỗi rõ không phải bằng chứng mật mã đầy đủ. Từng kết luận phải đi kèm ranh giới của phép thử và các phụ thuộc đã được kiểm tra.

Nếu một yêu cầu chưa thể đo hoặc không rõ ai chịu trách nhiệm, nó chưa đủ chín để đánh dấu hoàn tất chỉ bằng một nhận xét chung “đã an toàn”.

## 19. Duy trì yêu cầu khi chức năng và dữ liệu thay đổi

Khi thêm một trường, bản export, index hoặc đối tác, nhóm cần xem lại mục đích, phân loại và các đường sao chép. Khi thay quyền giảng viên, cơ chế cache hoặc quy trình phục hồi, cần kiểm tra những trạng thái lịch sử mà người dùng và hệ thống còn giữ.

Ngoại lệ nên có phạm vi, owner, lý do và thời hạn xem xét theo policy. Không để một cách xử lý tạm như log đầy đủ payload hoặc giữ export vô thời hạn trở thành cấu hình lâu dài mà không có quyết định rõ.

Thiết kế data protection đạt mục tiêu khi dữ liệu được thu thập và dùng đúng phạm vi, giữ được bí mật/toàn vẹn/khả dụng cần thiết và kết thúc vòng đời theo quy tắc có thể đối chiếu. Các yêu cầu phải theo dữ liệu qua mọi bản sao và đường xử lý; một điểm kiểm soát tốt ở database hoặc màn hình chính không thay thế được toàn bộ hành vi của hệ thống.

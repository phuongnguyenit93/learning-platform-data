# Incident response requirement: đặc tả yêu cầu ứng phó sự cố bảo mật

## 1. Vì sao ứng phó sự cố phải trở thành yêu cầu từ khi thiết kế?

Một hệ thống có thể chặn được nhiều hành vi nguy hiểm nhưng vẫn khó ứng phó khi có tài khoản bị chiếm đoạt, quyền bị lạm dụng hoặc dữ liệu bị phá hoại. Nếu không biết ai đang truy cập, không thể thu hồi quyền trên mọi đường cấp dữ liệu hoặc không phục hồi được khóa và cấu hình, nhóm vận hành sẽ phải xử lý sự cố bằng các thao tác thủ công thiếu chắc chắn.

**Incident response requirement** là yêu cầu xác định khả năng mà hệ thống, con người và quy trình phải có để tiếp nhận, đánh giá, giới hạn thiệt hại, xử lý và phục hồi sau sự cố bảo mật. Yêu cầu cần làm rõ hành vi bắt buộc, phạm vi, người chịu trách nhiệm, giới hạn thời gian và bằng chứng xác minh.

Trong thiết kế yêu cầu bảo mật, ứng phó sự cố không chỉ là viết một tài liệu trực. Nó tác động tới kiến trúc danh tính, phân quyền, audit, quản lý dữ liệu, khóa, hàng đợi, kênh quản trị và phục hồi. Những khả năng này cần được thiết kế, triển khai và diễn tập trước khi có sự cố thật.

Sau bài học, người học có thể:

- Chuyển kịch bản rủi ro thành các yêu cầu ứng phó có thể kiểm chứng.
- Phân biệt yêu cầu với kế hoạch, playbook và hướng dẫn thao tác.
- Đặt mốc đo rõ cho tiếp nhận, xác nhận trách nhiệm, cô lập và phục hồi.
- Đặc tả quyền ứng cứu, bảo vệ bằng chứng và điều kiện mở lại dịch vụ.
- Liên kết yêu cầu với kiến trúc, kiểm thử, diễn tập và việc cải tiến sau sự cố.

Các mức ưu tiên, thời gian và định danh trong bài là giả định minh họa. Chúng cần được quyết định theo tác động nghiệp vụ, khả năng vận hành và các nghĩa vụ áp dụng đã được xác nhận; không phải thời hạn chung cho mọi tổ chức.

## 2. Thống nhất sự kiện, cảnh báo và sự cố

### 2.1. Không phải mọi tín hiệu đều có cùng mức kết luận

| Khái niệm | Cách hiểu trong bài | Ví dụ |
| --- | --- | --- |
| Sự kiện bảo mật | Một quan sát liên quan tới an toàn của hệ thống | Một yêu cầu xuất báo cáo, một lần đổi quyền |
| Cảnh báo | Tín hiệu được quy tắc hoặc người tạo ra để yêu cầu xem xét | Nhiều lần tải dữ liệu khác thường từ một phiên |
| Sự cố nghi ngờ | Có dấu hiệu cần xử lý nhưng chưa đủ kết luận | Tài khoản hỗ trợ truy cập ngoài phạm vi công việc |
| Sự cố được xác nhận | Đã có căn cứ cho việc thuộc tính bảo vệ bị vi phạm theo tiêu chí tổ chức | Tài khoản không có quyền đã tải được dữ liệu |
| Vấn đề vận hành | Suy giảm dịch vụ có thể có hoặc không có nguyên nhân bảo mật | Kho log ngừng nhận dữ liệu hoặc worker bị dừng |

Một vấn đề vận hành có thể làm suy yếu khả năng ứng phó; một sự cố nghi ngờ có thể cần hành động ngay vì tác động tiềm tàng lớn. Không yêu cầu phải xác nhận đầy đủ mọi chi tiết mới được chuyển cấp hoặc thực hiện biện pháp đã được ủy quyền.

### 2.2. Mức tác động và độ chắc chắn là hai trục riêng

Phân loại nên xét dữ liệu, phạm vi khách hàng, đặc quyền, khả năng tiếp diễn và ảnh hưởng tới nghiệp vụ. Đồng thời ghi riêng mức chắc chắn của thông tin.

Ví dụ, tín hiệu nghi ngờ lộ dữ liệu nhiều tổ chức có thể cần xử lý ở mức ưu tiên cao dù phạm vi chính xác chưa rõ. Nhãn “chưa xác nhận” không tự có nghĩa ưu tiên thấp. Khi thông tin mới xuất hiện, mức ưu tiên có thể được nâng hoặc hạ với lý do và lịch sử rõ ràng.

Không được xóa mốc tiếp nhận ban đầu khi đổi phân loại để làm thời gian xử lý trông ngắn hơn. Những quy tắc tính lại mục tiêu khi nâng mức phải được đặc tả trước.

### 2.3. Xác định phạm vi ứng phó

Phạm vi cần bao gồm các môi trường, dữ liệu, người dùng, danh tính kỹ thuật và bên cung cấp có liên quan. Luồng chính, đường quản trị, API, worker và đường tải trực tiếp đều có thể cần biện pháp ứng cứu khác nhau.

Nếu dùng dịch vụ bên ngoài để phát hiện hoặc xử lý, cần ghi rõ ai tiếp nhận tín hiệu, ai có quyền hành động trên hệ thống và ai chịu trách nhiệm cuối cùng về dữ liệu hoặc hoạt động nghiệp vụ. Hợp đồng dịch vụ không tự làm các trách nhiệm tích hợp biến mất.

## 3. Từ mục tiêu và mô hình đe dọa tới khả năng cần có

### 3.1. Chuẩn bị đầu vào đúng phạm vi

Những đầu vào hữu ích gồm tài sản và phân loại dữ liệu, luồng nghiệp vụ quan trọng, mô hình đe dọa, kiến trúc, mục tiêu phục hồi, mô hình quyền và các giới hạn vận hành. Cần biết dịch vụ nào phụ thuộc vào danh tính, khóa, mạng, log và kênh liên lạc nào.

Nếu chưa biết người có thẩm quyền tắt một chức năng hoặc chưa biết cách thu hồi danh tính của worker, ghi thành khoảng trống cần hoàn thiện. Không coi đó là chi tiết có thể để tới lúc xảy ra sự cố.

### 3.2. Ánh xạ kịch bản thành yêu cầu

| Kịch bản rủi ro | Khả năng cần có | Hướng đặc tả và xác minh |
| --- | --- | --- |
| Tài khoản có quyền bị chiếm đoạt | Tìm phiên liên quan, giới hạn quyền và chặn truy cập mới | Đo hiệu lực thu hồi trên các điểm cấp dữ liệu |
| Người của A đọc dữ liệu B | Xác định chủ thể, tổ chức và tài nguyên đã truy cập | Truy vấn được chuỗi sự kiện và chặn đường vi phạm |
| Danh tính worker bị lạm dụng | Ngừng tác vụ, thu hồi quyền kỹ thuật, thay thông tin xác thực | Kiểm tra tác vụ đang chờ, đang chạy và cơ chế thử lại |
| Dữ liệu bị mã hóa hoặc xóa trái phép | Cô lập tác nhân, giữ bản sao có thể phục hồi | Diễn tập với dữ liệu, khóa, cấu hình và quyền |
| Audit bị gián đoạn hoặc sửa | Phát hiện mất quan sát và bảo vệ bằng chứng | Thử lỗi kênh ghi, quyền sửa và kênh báo độc lập |
| Dịch vụ danh tính không dùng được | Có đường ứng cứu được kiểm soát | Diễn tập quyền khẩn cấp, hạn dùng và ghi nhận thao tác |

Mỗi khả năng cần liên kết tới yêu cầu rõ ràng, không dừng ở một dòng “có quy trình ứng phó”. Cũng không cần tạo một cơ chế toàn cục quá mạnh nếu chỉ cần cô lập một tổ chức hoặc một danh tính.

## 4. Phân biệt yêu cầu, kế hoạch và playbook

| Loại nội dung | Vai trò | Ví dụ |
| --- | --- | --- |
| Yêu cầu | Cam kết bắt buộc cần đáp ứng và xác minh | Thu hồi quyền phải có hiệu lực ở mọi đường tải trong giới hạn đã chốt |
| Kế hoạch ứng phó | Tổ chức trách nhiệm, thẩm quyền và phối hợp | Ai chỉ huy, ai đánh giá tác động, ai quyết định mở lại |
| Playbook | Chuỗi quyết định cho một loại tình huống | Xử lý nghi ngờ tài khoản quản trị bị chiếm đoạt |
| Runbook | Hướng dẫn thao tác trên hệ thống cụ thể | Cách vô hiệu hóa danh tính, kiểm tra trạng thái và khôi phục |
| Bằng chứng diễn tập | Ghi nhận khả năng thực tế theo phiên bản | Mốc thời gian và kết quả thu hồi qua API, worker, điểm tải |

Yêu cầu không nên chỉ chứa tên công cụ hoặc thao tác bấm nút. Nếu đổi công cụ, mục tiêu bảo vệ vẫn cần giữ được. Ngược lại, runbook cần đủ cụ thể để người trực thực hiện đúng trong điều kiện đã định.

Một mẫu diễn đạt yêu cầu:

> Khi [điều kiện kích hoạt], [hệ thống hoặc vai trò] phải thực hiện [hành vi] đối với [phạm vi], trong [giới hạn tính từ mốc xác định], với [điều kiện quyền và xử lý lỗi]. Xác minh bằng [phương pháp và bằng chứng].

Ví dụ, “khi lệnh thu hồi được ghi nhận thành công tại nguồn quyền, mọi điểm cấp nội dung phải từ chối yêu cầu tải mới của danh tính đó trong tối đa 60 giây” rõ hơn “khóa tài khoản ngay khi có sự cố”. Việc ai được ra lệnh và điều kiện ra lệnh cần yêu cầu hoặc quyết định trách nhiệm riêng.

## 5. Đặt mốc thời gian có thể đo và không gây hiểu nhầm

### 5.1. Một bảng mục tiêu minh họa

Giả sử tổ chức chọn các mục tiêu sau cho phạm vi bài học:

| Hoạt động | Mốc bắt đầu | Điều kiện hoàn tất | Giới hạn minh họa |
| --- | --- | --- | --- |
| Đưa sự kiện vào kho tra cứu | Sự kiện được xác nhận ghi bền vững tại nguồn | Sự kiện có thể được người có quyền tra cứu | 120 giây |
| Chuyển cấp khi chưa có người nhận | Cảnh báo ưu tiên cao được hệ thống tiếp nhận ứng phó ghi nhận | Kênh dự phòng nhận được thông báo có thể hành động | 5 phút |
| Xác nhận trách nhiệm xử lý | Mốc tiếp nhận trên | Một người có trách nhiệm nhận xử lý và được ghi nhận | 10 phút |
| Ghi quyết định cô lập ban đầu | Mốc tiếp nhận cảnh báo ưu tiên cao | Có quyết định thực hiện hoặc chưa thực hiện biện pháp, kèm lý do và người chịu trách nhiệm | 20 phút |
| Hiệu lực thu hồi quyền | Lệnh thay đổi được ghi nhận thành công tại nguồn quyền | Mọi yêu cầu tải mới trong phạm vi phản ánh việc mất quyền | 60 giây |
| Phục hồi chức năng thiết yếu | Thời điểm có thẩm quyền công bố bắt đầu phục hồi | Chức năng đã được kiểm tra và đủ điều kiện mở lại | 2 giờ |

Đây là các cam kết khác nhau. Ra quyết định cô lập không đồng nghĩa đã cô lập xong. Nhận thông báo không đồng nghĩa đã có người chịu trách nhiệm. Một bot gửi phản hồi không nên được tính là xác nhận của người xử lý nếu yêu cầu đòi hỏi trách nhiệm con người.

### 5.2. Không dùng một mốc để che một đoạn chưa được đo

Thời gian sự cố bắt đầu, thời gian phát hiện, thời gian cảnh báo được tiếp nhận và thời gian người trực nhận việc thường khác nhau. Có thể chưa biết chính xác thời điểm xâm nhập; cần ghi phần chưa biết thay vì tự coi thời điểm cảnh báo là thời điểm sự cố bắt đầu.

Mục tiêu 120 giây đưa log vào kho tra cứu không đo độ trễ phát hiện một hành vi. Mục tiêu phục hồi tính từ quyết định bắt đầu phục hồi cũng không bao gồm toàn bộ thời gian phát hiện, đánh giá và chờ phê duyệt trước đó.

Nên lưu các mốc riêng: thời điểm sự kiện theo nguồn, thời điểm thu nhận, thời điểm tiếp nhận ứng phó, xác nhận trách nhiệm, quyết định, hành động, xác minh hiệu lực và mở lại. Nguồn thời gian và độ lệch có liên quan phải đủ rõ để so sánh.

### 5.3. Phân biệt giới hạn bắt buộc với chỉ số tổng hợp

Trung bình thời gian xử lý có thể hỗ trợ quản lý, nhưng không chứng minh mọi sự cố ưu tiên cao đều được nhận trong 10 phút. Nếu mục tiêu dùng phân vị hoặc một tỷ lệ đáp ứng, cần đặc tả rõ tập sự kiện, khoảng thời gian và cách xử lý phần không đạt.

Không đổi mức ưu tiên, bỏ sự cố kéo dài hoặc chỉ tính những trường hợp đã đóng để làm chỉ số đẹp hơn. Bằng chứng nên cho thấy các trường hợp chưa hoàn tất, bị chặn và vượt mục tiêu.

## 6. Yêu cầu tiếp nhận, phát hiện và phân loại

### 6.1. SR-IR-01 — Tiếp nhận và tạo hồ sơ

Mọi kênh được chỉ định để tiếp nhận sự cố phải có cách ghi nhận một hồ sơ định danh duy nhất, mốc tiếp nhận, nguồn, mô tả, phạm vi biết được và người hoặc hàng đợi chịu trách nhiệm. Các thông tin chưa biết phải được thể hiện rõ, không để trống theo cách dễ hiểu là không có ảnh hưởng.

Hồ sơ cần giữ lịch sử đổi trạng thái và phân loại. Khi gộp cảnh báo trùng, vẫn giữ được nguồn và mốc liên quan để không mất bối cảnh hoặc làm mất một tổ chức bị ảnh hưởng.

Bằng chứng có thể gồm tình huống tiếp nhận từ cảnh báo tự động, báo cáo của người dùng và kênh dự phòng, cùng việc người trực tra cứu được hồ sơ.

### 6.2. SR-IR-02 — Quan sát đủ để điều tra phạm vi

Các thao tác nhạy cảm trong phạm vi phải phát sinh sự kiện có chủ thể thực hiện, danh tính kỹ thuật nếu khác, tổ chức đích, tài nguyên, hành động, kết quả, thời điểm và định danh tương quan phù hợp.

Với tác vụ bất đồng bộ, cần liên hệ được người yêu cầu, tác vụ, worker và điểm cấp nội dung. Chỉ ghi danh tính dịch vụ chung sẽ khó xác định ai đã kích hoạt hành vi và dữ liệu của ai liên quan.

Không ghi mật khẩu, token, khóa hoặc toàn bộ dữ liệu nhạy cảm vào log để tiện điều tra. Dữ liệu bằng chứng chi tiết, nếu cần, phải được thu thập và lưu ở nơi có mục đích, thẩm quyền và quyền truy cập phù hợp.

### 6.3. SR-IR-03 — Phát hiện mất khả năng quan sát

Hệ thống phải phát hiện hoặc báo hiệu những lỗi làm mất sự kiện thuộc phạm vi cam kết: nguồn không gửi, hàng đợi tắc, kho không nhận hoặc truy vấn không hoạt động. Đường báo lỗi phải được thiết kế để không hoàn toàn phụ thuộc vào chính thành phần vừa hỏng.

Tín hiệu sống của một tiến trình chưa chứng minh luồng sự kiện đầu cuối còn hoạt động. Có thể dùng sự kiện kiểm tra được kiểm soát và đối chiếu qua các điểm thu nhận để xác minh đúng khả năng cần có.

### 6.4. SR-IR-04 — Phân loại và chuyển cấp

Tiêu chí phân loại phải nêu loại dữ liệu, phạm vi khách hàng, đặc quyền, khả năng tiếp diễn và tác động nghiệp vụ. Cảnh báo thỏa tiêu chí ưu tiên cao phải đi vào luồng xử lý tương ứng ngay cả khi một số thông tin còn chưa được xác nhận.

Nếu chưa có người nhận trong giới hạn chuyển cấp đã chọn, hệ thống hoặc quy trình phải chuyển tới người dự phòng có thẩm quyền. Danh sách trực và cách tiếp cận người dự phòng cần được duy trì và kiểm tra, không chỉ ghi một tên vai trò trong tài liệu.

## 7. Yêu cầu quyền ứng cứu và cô lập

### 7.1. SR-IR-05 — Thao tác cô lập có phạm vi rõ

Hệ thống phải hỗ trợ các biện pháp đã được lựa chọn từ mô hình đe dọa, chẳng hạn vô hiệu hóa một danh tính, thu hồi phiên, dừng quyền xuất, tạm ngừng tác vụ hoặc chặn một đường cấp nội dung. Mỗi thao tác cần chỉ ra phạm vi, quyền thực hiện, hiệu lực, tác dụng phụ và cách xác minh.

Ưu tiên khả năng cô lập đúng đối tượng khi đáp ứng được mục tiêu. Tắt toàn bộ nền tảng có thể gây tác động lớn hơn cần thiết và phải có điều kiện, thẩm quyền tương ứng. Một công tắc toàn cục không thay thế cho thiết kế phân tách theo tài khoản, tổ chức hoặc chức năng.

### 7.2. SR-IR-06 — Thu hồi trên mọi đường liên quan

Lệnh thu hồi phải có hiệu lực trong giới hạn được đặc tả tại API, điểm tải, phiên, thông tin truy cập đã cấp và thành phần liên quan trong phạm vi. Cần xác định riêng hành vi đối với tác vụ đang chờ, đang chạy và luồng truyền đã mở.

Với các yêu cầu tải mới, nếu không xác minh được quyền còn hiệu lực thì xử lý theo chính sách từ chối đã chốt. Không chỉ đổi quyền trên giao diện trong khi URL trực tiếp hoặc cache vẫn cấp dữ liệu.

Thử lại hoặc phục hồi trạng thái cũ không được tự làm sống lại quyền đã thu hồi. Các trường hợp này cần thiết kế và kiểm thử riêng.

### 7.3. SR-IR-07 — Quyền khẩn cấp có kiểm soát

Nếu cần quyền ứng cứu khi đường danh tính thông thường không khả dụng, phải đặc tả cách kích hoạt, xác minh người thực hiện, phạm vi thao tác, thời hạn, ghi nhận và kết thúc quyền. Không biến đường khẩn cấp thành tài khoản dùng chung lâu dài không thể quy trách nhiệm.

Thao tác có tác động lớn có thể cần phê duyệt độc lập hoặc điều kiện ủy quyền trước. Các điều kiện đó phải đủ thực tế để người trực hành động trong thời gian yêu cầu, kể cả khi một kênh liên lạc chính bị gián đoạn.

### 7.4. SR-IR-08 — Tự động hóa có giới hạn và xác minh hiệu lực

Nếu tự động khóa hoặc cô lập, cần nêu điều kiện kích hoạt, phạm vi tối đa, cách tránh lặp ngoài ý muốn, hành vi khi dữ liệu đầu vào sai và người có thể can thiệp. Một cảnh báo nhầm không nên mặc nhiên có quyền gây dừng toàn hệ thống nếu chưa được thiết kế và phê duyệt cho mục đích đó.

Hành động được gửi đi chưa chứng minh đã có hiệu lực. Cần đọc trạng thái hoặc thử hành vi tại điểm thực thi để xác nhận. Khi một phần thành công và một phần thất bại, hồ sơ phải thể hiện trạng thái chưa hoàn tất thay vì báo đã cô lập toàn bộ.

## 8. Yêu cầu xử lý nguyên nhân và phục hồi an toàn

### 8.1. Không mở lại chỉ vì dịch vụ đã trả phản hồi

Điều kiện mở lại cần dựa trên chức năng nghiệp vụ và thuộc tính bảo vệ, không chỉ là tiến trình đã chạy. Có thể cần môi trường sạch, đường lạm dụng đã bị chặn, danh tính và bí mật bị ảnh hưởng đã xử lý, dữ liệu được kiểm tra và quan sát đã hoạt động.

Nếu chưa xác định đầy đủ mọi nguyên nhân nhưng cần phục hồi trong phạm vi hạn chế, phải ghi rõ điều đã biết, biện pháp giới hạn, phần rủi ro còn lại và quyết định đúng thẩm quyền. Không giả định phục hồi là bằng chứng sự cố không thể tái diễn.

### 8.2. SR-IR-09 — Phục hồi đúng dữ liệu và phụ thuộc

Kế hoạch và thiết kế phục hồi phải bao gồm dữ liệu, metadata, khóa, danh tính dịch vụ, cấu hình và kết nối cần thiết. Các bản sao cần được bảo vệ trước đường phá hoại đang được xem xét; một tài khoản ứng dụng có thể xóa cả dữ liệu chính lẫn mọi bản sao là một phụ thuộc cần xử lý.

Nếu có mục tiêu điểm phục hồi, ví dụ không mất quá 15 phút dữ liệu trong một kịch bản đã chọn, phải xác định điểm dữ liệu và thời điểm gián đoạn làm cơ sở. Bản sao mới nhất không tự là bản sao an toàn nếu đã chứa thay đổi độc hại.

Khi điểm sạch đã xác nhận cũ hơn mục tiêu, phải ghi rõ khoảng trống và tác động. Không dùng bản sao mới nhưng không đáng tin chỉ để báo cáo đạt mục tiêu.

### 8.3. SR-IR-10 — Quyền hiện hành sau phục hồi

Trước khi mở lại cấp dữ liệu, phải đối chiếu quyền, phiên và đường truy cập với nguồn quyết định hiện hành được thiết kế cho tình huống phục hồi. Quyền cũ trong bản sao không được mặc nhiên xem là quyền còn hiệu lực.

Các đường không xác minh được điều kiện cho phép phải bị vô hiệu hóa hoặc từ chối theo đặc tả. Bài diễn tập nên có quyền bị thu hồi sau thời điểm tạo bản sao để kiểm tra khả năng này.

### 8.4. Mở lại và theo dõi tăng cường

Điều kiện mở lại cần có người xác nhận kỹ thuật và người có thẩm quyền quyết định theo quy trình. Nếu mở theo từng tổ chức hoặc chức năng, ghi chính xác phạm vi đang hoạt động và phạm vi còn bị giới hạn.

Khoảng theo dõi sau phục hồi cần mục tiêu, tín hiệu và người xử lý rõ. Một yêu cầu “theo dõi kỹ” không đủ để xác minh; cần biết đang tìm dấu hiệu gì và khi nào phải dừng hoặc chuyển cấp lại.

## 9. Trách nhiệm, phối hợp và thông tin liên lạc

### 9.1. Phân định người thực hiện và người quyết định

| Vai trò | Trách nhiệm cần được xác định |
| --- | --- |
| Người tiếp nhận hoặc trực | Ghi nhận, xác nhận trách nhiệm và chuyển cấp |
| Người chỉ huy xử lý | Điều phối ưu tiên, phạm vi hành động và trạng thái chung |
| Nhóm kỹ thuật | Cô lập, sửa, xác minh hiệu lực và phục hồi phần được giao |
| Người phụ trách điều tra | Thu thập, đánh giá bằng chứng và các giả thuyết |
| Chủ nghiệp vụ hoặc dữ liệu | Làm rõ tác động và điều kiện hoạt động chấp nhận được |
| Người phụ trách truyền thông và nghĩa vụ | Xác nhận nội dung, đối tượng, thời điểm và thẩm quyền thông báo |
| Người quyết định mở lại | Chấp thuận theo điều kiện, bằng chứng và rủi ro còn lại |

Một người có thể đảm nhận nhiều vai trò trong tổ chức nhỏ, nhưng các quyền và trách nhiệm vẫn phải rõ. Không mặc định người có quyền thao tác kỹ thuật cũng có quyền quyết định mọi tổn thất nghiệp vụ hoặc mọi thông báo bên ngoài.

### 9.2. Kênh chính, kênh dự phòng và bảo mật nội dung

Nếu nghi ngờ tài khoản hoặc kênh liên lạc bị kiểm soát, cần cách phối hợp dự phòng phù hợp. Danh sách liên hệ, cách xác minh người nhận và quyền đọc hồ sơ phải được quản lý, nhất là khi có bên cung cấp tham gia.

Thông tin chia sẻ nên tách sự thật đã xác nhận, giả thuyết, phần chưa biết và hành động đang làm. Không phát tán khóa, token, toàn bộ dữ liệu khách hàng hoặc chi tiết nhạy cảm qua một kênh rộng chỉ để cập nhật nhanh.

### 9.3. Thông báo và nghĩa vụ áp dụng

Yêu cầu cần chỉ ra ai xác định nghĩa vụ, ai duyệt nội dung, ai gửi và bằng chứng nào ghi nhận việc hoàn tất. Các mốc bên ngoài phải lấy từ nghĩa vụ đã được người có trách nhiệm xác nhận, với đúng sự kiện bắt đầu tính thời hạn.

Không dùng thời hạn nội bộ trong bảng mục tiêu để thay cho thời hạn thông báo bên ngoài. Cũng không tự đưa một thời hạn pháp lý hoặc hợp đồng chung vào mọi tình huống khi chưa xác nhận phạm vi áp dụng.

## 10. Bảo toàn bằng chứng và bảo vệ dữ liệu điều tra

### 10.1. Thu thập có mục đích và thẩm quyền

Yêu cầu nên xác định loại dữ liệu cần giữ, nguồn, người được thu thập, cách truy cập và điều kiện bảo quản. Một số dữ liệu dễ mất có thể cần ưu tiên, nhưng hành động thu thập không nên trì hoãn vô điều kiện biện pháp cần thiết để ngừng thiệt hại đang tiếp diễn.

Mọi lựa chọn ảnh hưởng bằng chứng cần ghi lại: đã cô lập gì, đã đổi trạng thái nào, dữ liệu nào không thể thu và vì sao. Không yêu cầu người trực luôn chụp đầy đủ mọi thứ trước khi hành động trong mọi loại sự cố.

### 10.2. Nguồn gốc, tính toàn vẹn và lịch sử xử lý

Hồ sơ bằng chứng nên có định danh, nguồn, thời điểm, người thu, phương pháp, phạm vi, vị trí lưu và lịch sử truy cập hoặc chuyển giao. Có thể dùng digest để hỗ trợ phát hiện thay đổi của bản đã thu, nhưng digest đứng riêng không chứng minh nguồn ban đầu đáng tin hoặc người thu đã được phép.

Giữ bản gốc và bản làm việc theo quy tắc được chọn, tránh chỉnh trực tiếp dữ liệu nguồn rồi mất khả năng giải thích. Kết luận điều tra phải liên hệ được với dữ liệu hỗ trợ và ghi rõ những giới hạn về độ đầy đủ, đồng hồ hoặc nguồn bị ảnh hưởng.

### 10.3. Quyền đọc, thời hạn giữ và xóa

Bằng chứng có thể chứa dữ liệu nhạy cảm hơn log vận hành thông thường. Cần giới hạn người đọc, thao tác xuất, thời hạn giữ và điều kiện xóa theo mục đích cùng nghĩa vụ đã xác nhận.

Nếu cần tạm dừng việc xóa theo vòng đời thông thường để giữ bằng chứng, phải có phạm vi, thẩm quyền và điều kiện kết thúc. Không chuyển mọi dữ liệu vào kho giữ vô hạn chỉ vì có một sự cố.

## 11. Ví dụ: tài khoản hỗ trợ bị lạm dụng để xuất dữ liệu

### 11.1. Bối cảnh

Nền tảng học tập cho phép nhân viên hỗ trợ truy cập theo phê duyệt của từng tổ chức. Một tín hiệu ưu tiên cao cho thấy tài khoản hỗ trợ đang tạo và tải báo cáo ngoài phạm vi công việc. Chưa xác nhận đầy đủ mọi tổ chức bị ảnh hưởng, nhưng hành vi có thể tiếp tục tiết lộ dữ liệu.

Các yêu cầu liên quan gồm ghi nhận người thực hiện và tổ chức đích, tiếp nhận ưu tiên cao, chuyển cấp, thu hồi quyền trên mọi đường tải, bảo vệ bằng chứng và mở lại có điều kiện.

### 11.2. Dòng thời gian minh họa

| Mốc | Điều xảy ra | Cách đánh giá |
| --- | --- | --- |
| 09:00 | Hệ thống tiếp nhận ứng phó ghi nhận cảnh báo ưu tiên cao | Bắt đầu các mục tiêu tính từ tiếp nhận; chưa coi đây là lúc xâm nhập bắt đầu |
| 09:05 | Chưa có người nhận nên kênh dự phòng được thông báo | Đáp ứng mốc chuyển cấp 5 phút nếu việc nhận tại kênh được xác minh |
| 09:06 | Người trực dự phòng nhận trách nhiệm | Đáp ứng mục tiêu 10 phút; không tính phản hồi tự động trước đó |
| 09:14 | Có quyết định cô lập tài khoản và tạm dừng tác vụ liên quan | Đáp ứng mốc quyết định 20 phút; chưa khẳng định cô lập hoàn tất |
| 09:15:00 | Lệnh thu hồi được ghi nhận tại nguồn quyền | Bắt đầu giới hạn hiệu lực thu hồi 60 giây |
| 09:15:38 | Xác minh các điểm tải thuộc phạm vi từ chối yêu cầu mới | Có bằng chứng hiệu lực trong 38 giây cho đường đã kiểm tra, kết hợp kiểm tra cấu hình và cơ chế lan truyền |
| 09:20 | Có quyết định bắt đầu phục hồi chức năng hỗ trợ trong môi trường đã xử lý | Bắt đầu mục tiêu phục hồi theo mốc đã chọn |
| 10:30 | Hoàn tất kiểm tra và được phép mở lại phạm vi xác định | Thời gian tính từ 09:20 là 70 phút; không gọi đó là toàn bộ thời gian ảnh hưởng |

Trong ví dụ này chưa có nhu cầu khôi phục cơ sở dữ liệu từ bản sao, nên không tự báo đạt mục tiêu điểm phục hồi. Nếu có dữ liệu bị sửa hoặc xóa, cần kịch bản và bằng chứng phục hồi dữ liệu riêng.

### 11.3. Điều cần chứng minh ngoài các con số

Nhóm cần xác định tác vụ nào do tài khoản tạo, tài nguyên nào đã được cấp nội dung, các URL cũ còn hoạt động không và dữ liệu đã có thể rời hệ thống tới đâu. Việc chặn tải mới không lấy lại dữ liệu đã được tải trước đó.

Nếu chỉ kiểm tra API nhưng bỏ đường tải trực tiếp, không được kết luận SR-IR-06 đạt. Nếu không tra được tổ chức đích do thiếu sự kiện, phải ghi khoảng trống điều tra và cập nhật yêu cầu quan sát, không khẳng định không có khách hàng khác bị ảnh hưởng.

Sau sự cố, kết quả phải quay lại yêu cầu và thiết kế: thu hẹp quyền hỗ trợ, cải thiện hiệu lực thu hồi, hoàn thiện dấu vết hoặc sửa điều kiện tự động hóa. Tạo ticket là bước giao việc; chỉ đóng khi có bằng chứng phù hợp cho phần khắc phục.

## 12. Xác minh bằng kiểm thử và diễn tập

### 12.1. Chọn phương pháp theo bản chất cam kết

| Yêu cầu hoặc khả năng | Phương pháp phù hợp | Bằng chứng mong đợi |
| --- | --- | --- |
| Tiếp nhận và chuyển cấp | Mô phỏng cảnh báo, người chính không phản hồi | Hồ sơ, mốc tiếp nhận, chuyển kênh và người nhận trách nhiệm |
| Tra cứu phạm vi | Tạo chuỗi sự kiện thử qua API, worker và điểm tải | Tìm được chủ thể, tổ chức, tài nguyên và định danh tương quan |
| Thu hồi quyền | Kiểm thử tích hợp trên các đường truy cập | Mốc thay đổi tại nguồn và kết quả tại điểm cấp nội dung |
| Quyền khẩn cấp | Diễn tập đường danh tính chính không khả dụng | Kích hoạt đúng người, phạm vi, hạn dùng và audit |
| Kênh audit lỗi | Gây lỗi có kiểm soát trong môi trường thử | Tín hiệu qua đường dự phòng và hành vi nghiệp vụ đúng đặc tả |
| Phục hồi | Khôi phục thực tế và kiểm tra nghiệp vụ | Dữ liệu, khóa, danh tính, quyền, thời gian và điều kiện mở lại |
| Thẩm quyền, phối hợp | Diễn tập bàn với tình huống chưa đủ thông tin | Người quyết định, tiêu chí, câu hỏi mở và việc cần hoàn thiện |

Diễn tập bàn giúp phát hiện khoảng trống trách nhiệm và quyết định, nhưng không chứng minh lệnh thu hồi thực sự có hiệu lực trên kho tệp. Ngược lại, kiểm thử một API không chứng minh có người trực và kênh dự phòng hoạt động.

### 12.2. Điều kiện khó cần được đưa vào diễn tập

Nên chọn các biến thể có cơ sở rủi ro: sự cố ngoài giờ làm việc, người chính không phản hồi, dịch vụ danh tính lỗi, nguồn log bị gián đoạn, tác vụ đang chạy, URL đã cấp, bản sao chứa quyền cũ hoặc một phần thao tác cô lập thất bại.

Mọi thao tác diễn tập phải có phạm vi được phép, dữ liệu thử và điều kiện dừng phù hợp. Nội dung bài học không yêu cầu thực hiện thao tác ứng cứu trên hệ thống thật; việc xác minh thực tế cần được tổ chức theo quyền đã có.

### 12.3. Truy vết và giới hạn kết luận

```text
Rủi ro tiếp tục xuất dữ liệu sau khi tài khoản bị chiếm
  -> SR-IR-05, SR-IR-06: cô lập và thu hồi có hiệu lực
  -> Kiến trúc danh tính, hàng đợi, cache và điểm tải
  -> Ca phiên cũ, tác vụ cũ, URL cũ và lỗi nguồn quyền
  -> Bằng chứng theo bản dựng, cấu hình và môi trường
  -> Đánh giá khoảng trống, rủi ro tồn dư và điều kiện phát hành
```

Lưu phiên bản yêu cầu, playbook, cấu hình và kết quả diễn tập. Không dùng đường dẫn tới lần chạy mới nhất thay cho kết quả cụ thể đã làm cơ sở phê duyệt.

Một lần diễn tập tốt không chứng minh mọi loại sự cố đều được xử lý đúng. Khi kiến trúc, danh tính, nhà cung cấp hoặc mô hình trực thay đổi, cần đánh giá lại bằng chứng bị ảnh hưởng.

## 13. Những lỗi đặc tả thường gặp

| Cách viết hoặc kết luận | Vấn đề | Cách sửa |
| --- | --- | --- |
| Có kế hoạch ứng phó nên đã đáp ứng | Chưa chứng minh khả năng kỹ thuật và phối hợp | Liên kết yêu cầu với kiểm thử và diễn tập tương ứng |
| Phải phản hồi ngay | Không có mốc và điều kiện hoàn tất | Ghi thời điểm bắt đầu, hành vi và giới hạn đo |
| Bot đã trả lời nên coi là có người nhận | Nhầm thông báo với trách nhiệm xử lý | Ghi người nhận trách nhiệm và cơ chế dự phòng |
| Chờ xác nhận hết phạm vi rồi mới chuyển cấp | Có thể để thiệt hại tiếp tục trong lúc điều tra | Phân biệt ưu tiên và mức chắc chắn, cho phép xử lý nghi ngờ theo tiêu chí |
| Khóa tài khoản là đủ | Có thể còn URL, cache, tác vụ hoặc danh tính kỹ thuật | Liệt kê các đường và xác minh hiệu lực |
| Gửi lệnh cô lập là báo hoàn tất | Không biết thành phần nào thực thi thành công | Đọc trạng thái hoặc kiểm tra hành vi tại điểm thực thi |
| Thu mọi bằng chứng trước mọi hành động | Có thể trì hoãn việc ngừng thiệt hại | Đặt ưu tiên theo tình huống, ghi hành động và ảnh hưởng bằng chứng |
| Sao lưu mới nhất chắc chắn an toàn | Có thể đã chứa thay đổi độc hại | Xác định điểm tin cậy và kiểm tra sau phục hồi |
| Dịch vụ trả phản hồi nên mở lại | Chưa kiểm tra quyền, khóa và đường lạm dụng | Đặt tiêu chí an toàn và nghiệp vụ trước khi mở |
| Một thời hạn thông báo dùng cho mọi trường hợp | Thiếu căn cứ về nghĩa vụ và mốc tính | Để người có trách nhiệm xác nhận điều kiện áp dụng |
| Lưu mọi thứ vào log để điều tra | Tạo thêm nơi lộ dữ liệu và bí mật | Tách sự kiện tối thiểu với kho bằng chứng có kiểm soát |
| Sau sự cố chỉ tạo ticket | Chưa xác minh cải tiến có hiệu lực | Gắn yêu cầu, người phụ trách và điều kiện đóng bằng chứng |

## 14. Thực hành và điều kiện bàn giao

### 14.1. Bài tập đặc tả

Một ứng dụng nhiều tổ chức có tài khoản quản trị, worker xử lý nền, kho tệp và dịch vụ danh tính dùng chung. Người dùng báo rằng tài khoản đã bị khóa nhưng đường tải báo cáo vẫn hoạt động. Cùng lúc, kho audit chính chậm nhận sự kiện và người trực chính chưa phản hồi.

Hãy thực hiện:

1. Viết phạm vi, tài sản và những kịch bản gây hại cần xử lý.
2. Tách sự thật đã xác nhận, giả thuyết và câu hỏi cần điều tra.
3. Đặc tả tiếp nhận, ưu tiên, chuyển cấp và xác nhận trách nhiệm với mốc đo rõ.
4. Viết yêu cầu cô lập danh tính, URL, tác vụ đang chờ và tác vụ đang chạy; không tự gộp mọi đối tượng thành một thao tác.
5. Nêu dữ liệu cần để xác định tổ chức, tài nguyên và người thực hiện mà không ghi bí mật vào log.
6. Thiết kế hành vi khi nguồn quyền hoặc kho audit không khả dụng.
7. Ghi điều kiện phục hồi và mở lại, bao gồm quyền hiện hành sau khôi phục trạng thái cũ.
8. Xác định người có thẩm quyền với hành động tác động lớn và thông báo bên ngoài.
9. Chọn kiểm thử hoặc diễn tập cho từng yêu cầu, cùng bằng chứng và giới hạn kết luận.

Không đủ cơ sở để kết luận sự cố đã kết thúc chỉ vì tài khoản được đánh dấu khóa. Cần kiểm tra hiệu lực trên mọi đường có thể tiếp tục gây hậu quả trong phạm vi đã chọn.

### 14.2. Điểm kiểm tra khi bàn giao bộ yêu cầu

- Phạm vi, tài sản, môi trường và phụ thuộc đã rõ.
- Phân loại dựa trên tác động, với độ chắc chắn được ghi riêng.
- Mỗi mục tiêu thời gian có mốc bắt đầu và điều kiện hoàn tất có thể kiểm chứng.
- Có người chính, người dự phòng, thẩm quyền và kênh phối hợp khả dụng.
- Sự kiện đủ để liên hệ chủ thể, tổ chức, tài nguyên và chuỗi xử lý.
- Hành động cô lập có phạm vi, quyền, tác dụng phụ và cách xác minh hiệu lực.
- Phiên, cache, URL, worker, thử lại và phục hồi được xét khi liên quan.
- Bằng chứng điều tra có nguồn gốc, quyền truy cập, lịch sử xử lý và vòng đời.
- Phục hồi bao gồm dữ liệu, khóa, danh tính, cấu hình và điều kiện mở lại an toàn.
- Nghĩa vụ thông báo có người xác nhận và không bị thay bằng thời hạn nội bộ tùy ý.
- Có truy vết tới rủi ro, kiến trúc, kiểm thử, diễn tập và công việc cải tiến.

Một bộ yêu cầu ứng phó sự cố có thể sử dụng được khi người trực biết mình được làm gì, hệ thống thực thi được hành động đó và người đánh giá có thể xác minh hiệu lực. Mục tiêu là giữ khả năng quyết định và bảo vệ trong điều kiện bất lợi, đồng thời công khai những phần chưa biết và rủi ro còn lại.

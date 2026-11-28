# Containment — Yêu cầu khoanh vùng và hạn chế thiệt hại sự cố

## 1. Containment cần đạt điều gì?

**Containment** là hoạt động hạn chế sự mở rộng của một sự cố, ngăn thiệt hại tiếp diễn và tạo điều kiện để đội ứng phó xử lý phần còn lại trong phạm vi kiểm soát được.

Ví dụ, một thông tin xác thực của dịch vụ xuất dữ liệu bị lộ. Chỉ đổi mật khẩu trên một màn hình chưa chắc đã ngăn được hành vi gây hại: token đã cấp, tác vụ đang chờ, worker hoặc liên kết tải đã tạo có thể vẫn tiếp tục cho phép lấy dữ liệu.

Trong [NIST SP 800-61 Rev. 3, phần RS.MI-01](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf), containment gắn với việc ngăn sự cố mở rộng và hạn chế thiệt hại bổ sung. NIST CSF 2.0 cũng phân biệt kết quả khoanh vùng tại RS.MI-01 với loại bỏ sự cố tại RS.MI-02.

Đối với thiết kế yêu cầu bảo mật, bài toán không dừng ở câu “đội vận hành phải cô lập khi có sự cố”. Hệ thống cần có khả năng:

- Xác định và tác động đúng tài khoản, tenant, workload hoặc luồng dữ liệu.
- Thực hiện hành động bởi người hoặc cơ chế đủ thẩm quyền.
- Có giới hạn thời gian và bằng chứng về hiệu lực.
- Giữ các đường quan sát, dữ liệu và chức năng thiết yếu theo quyết định ứng phó.
- Duy trì hạn chế trong thời gian cần thiết.
- Mở lại theo điều kiện đã được xác nhận.

Chuỗi lập luận của bài học là:

**Kịch bản sự cố → thiệt hại cần ngăn → phạm vi khoanh vùng → khả năng kỹ thuật → điều kiện vận hành → bằng chứng kiểm chứng.**

Sau bài học, người học cần có thể đặc tả và đánh giá yêu cầu containment liên quan đến xác thực, phân quyền, dữ liệu, logging và phục hồi trong vòng đời phát triển.

## 2. Phân biệt containment, eradication và recovery

| Hoạt động | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Phân tích sự cố | Điều gì đang xảy ra và phạm vi đã biết là gì? | Xác định danh tính dịch vụ bị dùng để xuất dữ liệu |
| Containment | Làm thế nào ngăn thiệt hại lan rộng hoặc tiếp diễn? | Chặn xuất và bàn giao tệp trong phạm vi bị ảnh hưởng |
| Eradication | Cần loại bỏ nguyên nhân, điểm vào hoặc khả năng duy trì nào? | Xử lý lỗ hổng, quyền trái phép hoặc cơ chế tồn tại đã phát hiện |
| Recovery | Khi nào và bằng cách nào đưa hoạt động trở lại trạng thái được chấp nhận? | Khôi phục dịch vụ với danh tính và cấu hình đã xác minh |
| Cải tiến sau sự cố | Điều gì cần thay đổi để giảm tái diễn? | Bổ sung yêu cầu kiểm soát tác vụ đang chạy và kiểm thử hồi quy |

Các hoạt động có thể giao nhau và phải được điều chỉnh theo thông tin mới. Không cần đợi biết toàn bộ nguyên nhân mới thực hiện biện pháp khẩn cấp đã được cho phép để ngăn thiệt hại đang diễn ra.

Ngược lại, một hành động containment thành công không chứng minh hệ thống đã sạch hoặc đã sẵn sàng mở lại. Tài khoản khác, quyền được tạo thêm hoặc thành phần bị thay đổi có thể chưa được phát hiện.

[NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) đặt ứng phó sự cố trong quản lý rủi ro theo CSF 2.0. Trong bài này, các tên hoạt động giúp phân biệt mục tiêu và bằng chứng, không mô tả một quy trình cứng mà mọi sự cố phải đi qua đúng một lần.

### Ngắn hạn và duy trì trong chuyển tiếp

Containment có thể là một hành động khẩn cấp hoặc một chế độ hạn chế kéo dài trong khi xử lý nguyên nhân:

- Cô lập một workload.
- Tạm dừng xuất dữ liệu của một tenant.
- Thu hồi một danh tính hoặc nhóm thông tin xác thực.
- Chuyển chức năng sang chế độ chỉ đọc.
- Dùng tuyến phục vụ thay thế có giới hạn.
- Giới hạn kết nối hoặc quyền đối với một nhóm tài nguyên.

Biện pháp tạm thời cần có người sở hữu, lịch xem xét và điều kiện kết thúc. Không để nó tồn tại không ai quản lý; cũng không tự gỡ chỉ vì đến một ngày dự kiến khi nguy cơ vẫn còn.

## 3. Xác định phạm vi và đánh đổi

### 3.1. Đơn vị khoanh vùng

| Đơn vị | Cách giới hạn có thể có | Phần cần kiểm tra thêm |
| --- | --- | --- |
| Tài khoản hoặc danh tính dịch vụ | Vô hiệu hóa, thu hồi quyền, giới hạn hành động | Phiên, token và quyền đã ủy nhiệm |
| Phiên hoặc thông tin xác thực | Thu hồi phạm vi cụ thể | Bản sao, token phát sinh và cách hệ thống kiểm tra hiệu lực |
| Tenant | Dừng một chức năng trong tenant | Worker, hàng đợi, đường tải và tài nguyên dùng chung |
| Workload hoặc endpoint | Cô lập khỏi các đường gây hại | Kênh quản trị, logging và các phiên đang tồn tại |
| Dịch vụ | Tạm dừng hoặc giảm chức năng | Phụ thuộc của dịch vụ khác và quy trình thay thế |
| Dữ liệu hoặc nhóm tệp | Chặn bàn giao, giới hạn truy cập | Bản xuất, cache, liên kết tải và bản sao ngoài hệ thống |
| Kết nối | Hạn chế ingress, egress hoặc kết nối nội bộ | Lưu lượng hợp lệ, kênh điều tra và khả năng phản ứng |

Chọn phạm vi hẹp có thể giảm gián đoạn, nhưng chỉ có ý nghĩa nếu đủ ngăn đường gây hại đã biết. Nếu danh tính bị lộ có quyền nhiều tenant, khoanh vùng một tenant có thể không đủ.

Phạm vi cần được cập nhật khi phát hiện hoạt động, tài khoản hoặc tài sản liên quan mới. Không coi giả định ban đầu là ranh giới cố định của sự cố.

### 3.2. Các yếu tố ra quyết định

Cần cân nhắc:

- Thiệt hại đang xảy ra và khả năng tiếp diễn.
- Mức tin cậy của tín hiệu và độ bất định về phạm vi.
- Tác động đến hoạt động thiết yếu.
- Khả năng giữ bằng chứng và quan sát sau khi áp dụng.
- Thời gian để biện pháp thực sự có hiệu lực.
- Phụ thuộc hoặc quyền dùng chung.
- Khả năng đảo ngược và nguy cơ mở lại đường gây hại.
- Năng lực thực hiện của đội ứng phó và nhà cung cấp.

Không có một lựa chọn mặc định như “tắt toàn bộ” hoặc “chỉ chặn IP” phù hợp mọi sự cố. Chặn một chỉ báo cụ thể có thể hữu ích nhưng chưa xử lý danh tính bị lộ hoặc đường truy cập khác.

### 3.3. Chặn giao diện chưa chắc chặn hoạt động

Một chức năng có thể đi qua nhiều lớp:

~~~mermaid
flowchart LR
    C[Client hoặc tích hợp] --> API[API]
    API --> Q[Hàng đợi]
    Q --> W[Worker]
    W --> D[(Nguồn dữ liệu)]
    W --> F[(Tệp xuất)]
    F --> DL[Đường tải hoặc bàn giao]
    API --> L[Logging]
    W --> L
    DL --> L
~~~

Tắt nút xuất trên UI không ngăn client gọi API. Chặn API không tự hủy tác vụ đã xếp hàng. Dừng worker chưa chắc vô hiệu hóa tệp và liên kết tải đã tạo.

Yêu cầu containment cần đi theo các đường tiếp tục tạo thiệt hại, thay vì chỉ theo nơi đầu tiên phát hiện sự cố.

## 4. Thiết kế khả năng containment trước khi có sự cố

### 4.1. Kiểm kê và khả năng nhận diện đối tượng

Hệ thống cần cho phép đội ứng phó xác định đúng:

- Danh tính và thông tin xác thực liên quan.
- Tenant, nhóm tài nguyên và quyền hiện hành.
- Workload, phiên bản và nơi triển khai.
- Tác vụ đang chờ, đang chạy và kết quả đã tạo.
- Các đường bàn giao dữ liệu.
- Nơi có log và bằng chứng.
- Chủ hệ thống, chủ dữ liệu và nhà cung cấp cần phối hợp.

Nếu không nối được một hành động xuất dữ liệu với danh tính, tenant và tác vụ, việc khoanh vùng sẽ chậm và dễ gây gián đoạn rộng hơn cần thiết.

### 4.2. Năng lực điều khiển có phạm vi

Một ứng dụng có thể cần các khả năng như:

- Dừng một nhóm hành động mà không dừng mọi chức năng.
- Chặn một danh tính hoặc thông tin xác thực.
- Áp dụng chế độ hạn chế theo tenant.
- Tạm dừng hoặc giữ kết quả tác vụ nền.
- Ngăn bàn giao tệp đã tạo.
- Duy trì chức năng đọc hoặc quy trình thay thế theo quyết định.
- Xem trạng thái áp dụng tại các thành phần liên quan.

Các khả năng này phải được bảo vệ như chức năng đặc quyền. Một kill switch không được phân quyền đúng có thể trở thành đường gây từ chối dịch vụ.

### 4.3. Đường điều khiển và quan sát đáng tin cậy

Cần làm rõ đội ứng phó điều khiển hệ thống bằng cách nào khi một tài khoản, máy trạm hoặc kênh liên lạc bị nghi ngờ.

Tùy kiến trúc, có thể cần kênh quản trị tách biệt, tài khoản khẩn cấp được kiểm soát hoặc phương án phối hợp với nhà cung cấp. Yêu cầu phải xác định điều kiện dùng, người có quyền và cách ghi nhận.

Cô lập tài nguyên không nên vô tình cắt mọi đường logging và quản trị cần thiết mà kế hoạch đang dựa vào. Nếu phải hy sinh một khả năng quan sát để ngăn thiệt hại lớn hơn, ghi rõ quyết định và giới hạn bằng chứng.

### 4.4. Không phụ thuộc vào sự khỏe mạnh của chính thành phần bị nghi ngờ

Nếu workload có thể đã bị kiểm soát, xác nhận “đã tự cô lập” từ workload đó chưa chắc đủ. Có thể cần bằng chứng từ lớp nền tảng, kết nối hoặc hệ thống độc lập phù hợp.

Tương tự, một lệnh thu hồi được IdP chấp nhận không chứng minh mọi ứng dụng đang xác minh token đã cập nhật trạng thái. Phải xác định nơi thực thi và cách kiểm tra hiệu lực thật.

## 5. Thẩm quyền và kiểm soát hành động ứng phó

### 5.1. Quyền phải rõ trước tình huống khẩn cấp

Kế hoạch cần xác định:

- Ai được tuyên bố và điều phối sự cố.
- Ai được khoanh vùng một tài khoản, tenant hoặc dịch vụ.
- Hành động nào đã được cho phép trước theo điều kiện cụ thể.
- Hành động nào cần quyết định bổ sung do tác động lớn.
- Cơ chế liên hệ và thay thế người phụ trách.
- Ai được sửa phạm vi hoặc gỡ biện pháp.

Không cần buộc mọi hành động phải đợi cùng một chuỗi phê duyệt nếu kế hoạch đã cho phép tự động hóa hoặc hành động khẩn cấp. Thẩm quyền và phạm vi đó phải được xác định trước, có bằng chứng sử dụng.

### 5.2. Hồ sơ hành động

Một hành động nên có:

| Thông tin | Mục đích |
| --- | --- |
| Mã sự cố và mã thao tác | Liên kết quyết định, triển khai và bằng chứng |
| Chủ thể thực hiện | Biết ai hoặc cơ chế nào sử dụng quyền |
| Lý do và tín hiệu liên quan | Giải thích cơ sở hành động |
| Đối tượng và phạm vi | Tránh áp dụng nhầm tài nguyên hoặc tenant |
| Biện pháp và trạng thái mong muốn | Biết điều gì cần có hiệu lực |
| Thời điểm và thời hạn xem xét | Đo thời gian và quản lý biện pháp tạm |
| Người quyết định hoặc chính sách cho phép | Xác nhận thẩm quyền |
| Kết quả theo thành phần | Phân biệt thành công, thất bại và chưa rõ |
| Điều kiện gỡ bỏ | Tránh mở lại tùy ý |

Không ghi khóa, token hoặc bí mật vào bản ghi chỉ để mô tả đối tượng. Dùng định danh và tham chiếu an toàn theo chính sách.

### 5.3. Tự động hóa phải có giới hạn

Tự động hóa có thể giảm thời gian phản ứng, nhưng cần biết tín hiệu nào đủ để kích hoạt, phạm vi tối đa và khi nào phải chuyển người xử lý.

Cần đánh giá tình huống tín hiệu sai khiến hệ thống tự khóa người dùng hoặc dịch vụ hợp lệ. Những hành động rộng hoặc khó đảo ngược cần mức kiểm soát tương ứng với hậu quả.

Hệ thống cũng cần cách thực hiện thủ công phù hợp khi tự động hóa không đủ hoặc không hoạt động, nhất quán với [NIST SP 800-61 Rev. 3, RS.MI-01](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf).

## 6. Viết yêu cầu containment đo được và kiểm chứng được

Câu “hệ thống hỗ trợ containment nhanh” chưa cho biết đối tượng, thời gian hoặc cách xác nhận.

Có thể dùng mẫu:

**Khi [lệnh hoặc điều kiện đã được cho phép] có hiệu lực, hệ thống phải [giới hạn hành vi] trong [phạm vi], không muộn hơn [giới hạn], đồng thời duy trì [điều kiện cần thiết] và tạo [bằng chứng].**

Các mã và ngưỡng dưới đây là giả định của bài học, không phải ngưỡng mặc định do NIST áp đặt.

| Mã | Yêu cầu minh họa | Bằng chứng dự kiến |
| --- | --- | --- |
| CT-AUTH-01 | Chỉ chủ thể đáp ứng chính sách ứng phó đã xác định được tạo, sửa hoặc gỡ lệnh containment trong phạm vi được cấp | Ca đúng quyền, sai quyền và audit quyết định |
| CT-IDENT-02 | Trong tối đa 120 giây từ khi lệnh hợp lệ được lưu bền vững, yêu cầu mới dùng thông tin xác thực đã chỉ định không được tiếp tục thực hiện hành động bị chặn tại các điểm thuộc phạm vi | Mốc lệnh, kiểm tra các loại phiên/token và điểm thực thi |
| CT-EXPORT-03 | Khi chế độ giữ xuất dữ liệu có hiệu lực với tenant, không nhận tác vụ xuất mới và không bàn giao kết quả thuộc phạm vi đang bị giữ | API, hàng đợi, worker và đường tải |
| CT-SCOPE-04 | Biện pháp theo tenant không tự mở rộng sang chức năng hoặc tenant ngoài phạm vi đã quyết định | Kiểm tra đối chứng và dữ liệu phạm vi |
| CT-AUDIT-05 | Mỗi thay đổi containment có sự kiện chứa chủ thể, mã sự cố, phạm vi, hành động, thời điểm, kết quả và phiên bản trạng thái | Đối chiếu lệnh, trạng thái và audit |
| CT-DUR-06 | Biện pháp đã áp dụng được duy trì qua restart hoặc mở rộng hệ thống cho đến khi có quyết định thay đổi hợp lệ | Thử restart, thêm nút và lỗi đồng bộ |
| CT-OBS-07 | Hệ thống phân biệt lệnh được nhận, đã thực thi, đã kiểm chứng, áp dụng một phần và chưa rõ hiệu lực | Trạng thái theo đối tượng và tình huống mất kết nối |
| CT-REC-08 | Gỡ containment chỉ được thực hiện theo thẩm quyền và điều kiện phục hồi đã xác định | Ca gỡ hợp lệ, gỡ trái quyền và khôi phục từ backup |

Các tham chiếu như “chính sách ứng phó” hoặc “các điểm thuộc phạm vi” phải có nội dung cụ thể và phiên bản. Nếu không xác định được người nào đủ quyền hoặc gateway nào chịu tác động, yêu cầu vẫn chưa đủ để nghiệm thu.

### 6.1. Nêu rõ thời điểm và đường thực thi

Đối với CT-IDENT-02:

- Mốc bắt đầu là lệnh hợp lệ đã được lưu bền vững, không phải lúc người vận hành mở giao diện.
- Giới hạn bao gồm thời gian phân phối lệnh và cập nhật điểm thực thi.
- Phải xác định các loại phiên hoặc token có liên quan.
- Phải bao phủ các nút và đường xử lý thuộc phạm vi.
- Cần quản lý sai lệch đồng hồ và độ chính xác của phép đo.
- Request mới sau giới hạn vẫn thực hiện được hành động bị chặn là không đạt.

Đây chưa phải yêu cầu về toàn bộ thời gian từ phát hiện đến khoanh vùng. Khoảng đó còn gồm phân tích, quyết định và thao tác trước khi lệnh được lưu; cần đo riêng nếu tổ chức có mục tiêu tương ứng.

### 6.2. Xử lý yêu cầu và tác vụ đang chạy

Cần xác định hành vi với:

- Request đã bắt đầu trước lệnh.
- Phiên tải dữ liệu hoặc stream đang mở.
- Tác vụ đã được xếp hàng nhưng chưa chạy.
- Tác vụ đang tạo kết quả.
- Tệp đã tạo nhưng chưa bàn giao.
- Liên kết tải đã cấp.

Một hợp đồng có thể quy định chặn bàn giao kết quả tại điểm cuối dù tác vụ đã được nhận trước đó. Với stream đang chạy, cần định nghĩa khả năng dừng và giới hạn hiệu lực của phía cung cấp dữ liệu.

Dữ liệu đã được gửi hoặc đã được đối phương lưu không thể được containment bảo đảm thu hồi. Cần phân biệt ngăn bàn giao tiếp với xử lý hậu quả của dữ liệu có thể đã rời hệ thống.

Nếu nền tảng không hỗ trợ vô hiệu hóa một đường tải trong giới hạn yêu cầu, nhóm phải thiết kế biện pháp bổ sung hoặc ghi nhận khoảng trống. Không đánh dấu hoàn tất chỉ vì phần API đã bị chặn.

## 7. Thu hồi danh tính và hạn chế dữ liệu phải phối hợp

### 7.1. Đổi bí mật không tự chứng minh mọi quyền đã mất

Cần kiểm tra quan hệ giữa:

- Thông tin xác thực gốc.
- Phiên hoặc token đã cấp.
- Quyền ủy nhiệm và danh tính mà worker sử dụng.
- Cache quyền hoặc trạng thái tài khoản.
- Liên kết tải hoặc kết quả được cấp trước đó.

Một token có thể được kiểm tra theo cơ chế khác với bí mật dùng để phát hành nó. Một worker cũng có thể tiếp tục bằng danh tính kỹ thuật của mình sau khi danh tính người yêu cầu bị khóa.

Vì vậy, cần xác minh tại nơi hành động có thể tiếp tục tạo thiệt hại, thay vì chỉ nhìn trạng thái khóa tài khoản.

### 7.2. MFA và quyền ứng phó có vai trò khác nhau

MFA có thể bảo vệ quyền điều khiển của người ứng phó. Nó không tự giải quyết token đã bị lấy cắp, quyền cấp thêm hoặc tác vụ đã được chấp nhận.

Các yêu cầu xác thực và phân quyền containment cần có ca kiểm thử:

- Người có vai trò phù hợp và phiên đáp ứng chính sách thao tác được đúng phạm vi.
- Người thiếu vai trò hoặc thiếu điều kiện phiên không thay đổi trạng thái.
- Người chỉ được xử lý tenant A không áp dụng hoặc gỡ biện pháp cho tenant B.
- Một lần gỡ bị từ chối không làm cấu hình thực tế trở lại bình thường.

### 7.3. Hạn chế đường dữ liệu

Nếu mục tiêu là ngăn tiếp tục xuất dữ liệu, chỉ thu hồi quyền tạo tác vụ mới có thể chưa đủ. Cần đánh giá dữ liệu ở hàng đợi, worker, storage, cache và điểm tải.

Ngược lại, chặn bàn giao tệp mà để kẻ tấn công tiếp tục thay đổi quyền hoặc tạo danh tính mới có thể không kiểm soát được sự cố. Phạm vi cần phản ánh các khả năng gây hại đã biết, không chỉ triệu chứng đầu tiên.

## 8. Bảo toàn bằng chứng trong khi hạn chế thiệt hại

### 8.1. Dữ liệu nào cần giữ?

Tùy sự cố, có thể cần:

- Log xác thực, phân quyền, thao tác API và hành động quản trị.
- Sự kiện tạo, chạy và tải kết quả của tác vụ.
- Cấu hình, phiên bản triển khai và trạng thái quyền.
- Thông tin kết nối hoặc trạng thái hệ thống có thời gian tồn ngắn.
- Mốc quyết định, hành động và kết quả khoanh vùng.
- Dữ liệu cần xác định phạm vi và hậu quả.

Chỉ thu thập phần cần thiết theo mục tiêu, phạm vi và thẩm quyền. Hiện vật điều tra có thể chứa dữ liệu nhạy cảm hoặc bí mật nên cần được bảo vệ, giới hạn người tiếp cận và quản lý thời hạn lưu.

### 8.2. Ghi lại nguồn và quá trình xử lý

Một hiện vật nên có định danh, nguồn, thời điểm thu thập, người hoặc cơ chế thu thập, phương thức và lịch sử chuyển giao phù hợp.

Giá trị băm hỗ trợ kiểm tra tính toàn vẹn của một bản đã thu thập. Nó không tự chứng minh dữ liệu nguồn chưa từng bị thay đổi hoặc người thu thập đã có thẩm quyền.

[NIST CSF 2.0, nhóm RS.AN](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf) đề cập ghi nhận hành động điều tra và bảo toàn tính toàn vẹn, nguồn gốc của dữ liệu sự cố. Điều này cần được thể hiện trong yêu cầu logging và quản lý hiện vật.

### 8.3. Không biến một thứ tự thao tác thành quy tắc tuyệt đối

Một số thao tác có thể làm mất dữ liệu tạm thời; tiếp tục chờ thu thập mọi hiện vật có thể cho thiệt hại tiếp diễn. Kế hoạch cần nêu cách quyết định khi các mục tiêu này xung đột.

Không mặc định luôn tắt nguồn, luôn khởi động lại hoặc luôn chờ thu thập xong. Chọn theo kịch bản và thẩm quyền, đồng thời ghi rõ phần bằng chứng có thể bị mất và lý do hành động.

Việc xóa dấu vết, reset trạng thái hoặc ghi đè backup trước khi có căn cứ phù hợp có thể làm khó xác định phạm vi. Các bước xử lý nguyên nhân và phục hồi cần phối hợp với việc giữ bằng chứng.

## 9. Xác minh containment đã có hiệu lực

### 9.1. Phân biệt các mức trạng thái

| Trạng thái minh họa | Ý nghĩa |
| --- | --- |
| Đã nhận lệnh | Hệ thống điều khiển ghi nhận yêu cầu |
| Đang áp dụng | Các thành phần đang được cập nhật |
| Đã thực thi | Có xác nhận biện pháp được áp dụng ở những điểm đã biết |
| Đã kiểm chứng theo phạm vi | Có bằng chứng hành vi bị chặn tại các điểm được xác định |
| Áp dụng một phần | Một số mục tiêu chưa đạt |
| Chưa rõ | Không đủ thông tin đáng tin cậy để xác nhận |
| Thất bại | Có bằng chứng hành động không thực hiện được hoặc mục tiêu vẫn vi phạm |

Đây là cách thiết kế trạng thái của bài học, không phải nhãn bắt buộc của một tiêu chuẩn.

Một nút không trả lời không được tự động xem là đã an toàn. Cần biện pháp hoặc kênh xác minh khác, hoặc tiếp tục ghi rõ chưa kiểm soát được phạm vi đó.

### 9.2. Bằng chứng từ hành vi

Có thể cần kiểm tra:

- Request mới bằng danh tính bị chặn không thực hiện được hành động.
- Tác vụ chờ không được khởi chạy hoặc bàn giao ngoài chính sách.
- Tệp và đường tải đã cấp không còn cung cấp dữ liệu thuộc phạm vi bị giữ.
- Workload bị cô lập không còn các kết nối bị cấm.
- Hành động hợp lệ ngoài phạm vi vẫn đáp ứng điều kiện đã thống nhất.
- Audit và trạng thái điều khiển khớp với thay đổi thực tế.

Chỉ log “command succeeded” không chứng minh quyền hoặc kết nối ở phía sau đã bị chặn. Cũng không đủ chỉ quan sát không có cảnh báo mới nếu chính kênh giám sát đã bị gián đoạn.

### 9.3. Xác nhận có giới hạn

Kết luận nên nêu:

- Phạm vi được kiểm soát.
- Thời điểm và cơ sở kiểm chứng.
- Các đường gây hại đã được chặn.
- Các đường, hệ thống hoặc bên thứ ba chưa xác minh.
- Giả định đang dùng.
- Điều kiện phải mở rộng hành động.

“Đã kiểm chứng containment cho luồng xuất của tenant A” khác với “sự cố đã được xử lý hoàn toàn”. Nếu phát hiện danh tính liên quan có quyền ở nơi khác, cần phân tích và điều chỉnh phạm vi.

## 10. Duy trì biện pháp trong hệ thống phân tán

### 10.1. Trạng thái mong muốn phải được giữ

Feature flag chỉ tồn tại trong bộ nhớ có thể mất khi restart. Nút mới được thêm có thể chưa nhận lệnh, và bản phục hồi cũ có thể làm chế độ hạn chế biến mất.

Cần đặc tả:

- Nguồn trạng thái có thẩm quyền.
- Cách nút mới hoặc nút khởi động lại nhận trạng thái.
- Hành vi khi không đọc được trạng thái.
- Cách báo chậm đồng bộ hoặc không áp dụng được.
- Điều kiện cho phép thành phần bắt đầu xử lý lại.

Không bắt buộc mọi chức năng phải có cùng hành vi khi mất hệ thống điều khiển. Chọn hành vi theo rủi ro của chức năng và yêu cầu duy trì hoạt động.

### 10.2. Lệnh lặp lại và lệnh đến sai thứ tự

Một thao tác được gửi lại không nên vô tình gỡ biện pháp hoặc tạo tác động khác với ý định. Cần có định danh thao tác và cách xử lý lặp phù hợp.

Lệnh “mở lại” cũ đến sau lệnh “giữ” mới cũng không được tự thắng chỉ vì đến muộn. Có thể dùng phiên bản trạng thái hoặc cơ chế điều phối thích hợp để bảo đảm quyết định hiện hành được thực thi.

Yêu cầu nên mô tả kết quả cần giữ; lựa chọn kỹ thuật cụ thể thuộc thiết kế và cần được kiểm chứng.

### 10.3. Thời hạn xem xét không phải tự mở lại

Một biện pháp tạm cần được xem xét đúng hạn. Nếu chưa có quyết định thay đổi, hệ thống không nên tự coi mối đe dọa đã hết chỉ vì thời gian dự kiến đã qua.

Nếu một loại biện pháp buộc phải có hạn tự động vì lý do nghiệp vụ, điều đó phải được quyết định rõ cùng hành vi khi hết hạn, cảnh báo và phương án xử lý. Không để hạn tự động trở thành giả định ngầm của cơ chế ứng phó.

## 11. Ví dụ: khoanh vùng danh tính xuất dữ liệu bị lộ

### 11.1. Bối cảnh giả định

Một nền tảng tài liệu nhiều tenant có danh tính tích hợp svc-export-A phục vụ tenant A. Đội giám sát phát hiện hoạt động xuất bất thường liên quan một thông tin xác thực của danh tính này.

Phân tích ban đầu cho thấy:

- Thông tin xác thực có thể tạo tác vụ xuất của tenant A.
- Có tác vụ đang chờ, một số đang chạy và tệp đã tạo.
- Một số đường tải được cấp trước thời điểm phát hiện.
- Chưa có bằng chứng đủ để kết luận các danh tính khác bị ảnh hưởng.
- Cần tiếp tục kiểm tra phạm vi quyền và hoạt động liên quan.

Tổ chức quyết định áp dụng gói biện pháp trong phạm vi đã biết:

1. Chặn thông tin xác thực liên quan.
2. Giữ toàn bộ luồng xuất và bàn giao kết quả của tenant A.
3. Xử lý tác vụ đang chờ hoặc đang chạy theo chính sách giữ.
4. Hạn chế các đường tải kết quả đã tạo thuộc phạm vi.
5. Duy trì logging và chức năng ngoài phạm vi theo quyết định.
6. Tiếp tục điều tra danh tính, quyền và dữ liệu có thể đã bị truy cập.

Việc giữ toàn bộ xuất của tenant A cũng ảnh hưởng người dùng hợp lệ trong tenant đó. Đây là tác động đã được cân nhắc, không phải dấu hiệu biện pháp chỉ tác động kẻ tấn công.

### 11.2. Phân biệt danh tính bị chặn và phạm vi chức năng bị giữ

Thu hồi một thông tin xác thực ngăn chủ thể tiếp tục dùng nó trên các đường có thực thi thu hồi. Chế độ giữ xuất của tenant A còn phải chặn bàn giao bằng các đường khác trong phạm vi, kể cả một token mới hợp lệ.

Do đó, cấp lại bí mật cho dịch vụ không được tự làm chế độ giữ biến mất. Khôi phục danh tính và mở lại chức năng là hai quyết định liên quan nhưng khác nhau.

Nếu điều tra phát hiện danh tính này có quyền rộng hơn tenant A, kế hoạch phải được điều chỉnh. Không dùng giới hạn giả định của ví dụ để bỏ qua bằng chứng mới.

### 11.3. Dòng thời gian minh họa

Trong bài, giới hạn thu hồi và giới hạn hiệu lực của gói chặn bàn giao được giả định là 120 giây từ khi lệnh hợp lệ được lưu bền vững. Các giá trị chỉ phục vụ cách đo.

| Thời điểm | Quan sát | Kết luận phù hợp |
| --- | --- | --- |
| 09:00:00 | Có tín hiệu bất thường | Cần phân loại và xác định hành động phù hợp |
| 09:03:00 | Quyết định phạm vi ban đầu | Biện pháp được cho phép nhưng chưa chứng minh có hiệu lực |
| 09:04:00 | Lệnh hợp lệ được lưu bền vững | Bắt đầu mốc đo kỹ thuật của ví dụ |
| 09:04:30 | API chặn thông tin xác thực; một worker chưa xác nhận | Chưa thể báo hoàn tất gói biện pháp |
| 09:05:00 | Tác vụ bị giữ, nhưng một đường tải cũ vẫn cung cấp dữ liệu | Containment mới áp dụng một phần |
| 09:05:40 | Các đường thuộc phạm vi đã được kiểm chứng chặn đúng; đối chứng ngoài phạm vi đạt | Có cơ sở xác nhận hiệu lực trong phạm vi đã nêu |
| Sau đó | Tiếp tục theo dõi, điều tra và xử lý nguyên nhân | Chưa đồng nghĩa sự cố đã được loại bỏ hoàn toàn |

Trong ví dụ, mốc lệnh đến xác nhận hiệu lực là 100 giây. Nhưng thời gian từ tín hiệu đầu đến mốc đó là 5 phút 40 giây. Hai đại lượng trả lời hai câu hỏi khác nhau.

Không chuyển mốc bắt đầu sang lúc worker cuối cùng nhận lệnh để làm số liệu đẹp hơn.

### 11.4. Những gì phải kiểm chứng

- Thông tin xác thực cũ không thực hiện được hành động bị chặn.
- Không tạo được tác vụ xuất mới trong tenant A.
- Tác vụ tồn không bàn giao kết quả ngoài chính sách.
- Đường tải cũ thuộc phạm vi không tiếp tục cung cấp dữ liệu bị giữ.
- Các nút mới hoặc khởi động lại giữ đúng trạng thái.
- Tenant B không bị chặn bởi một lỗi gán phạm vi.
- Các thao tác ứng phó có audit và không làm lộ bí mật.
- Còn dữ liệu nào đã được gửi trước biện pháp được ghi riêng để điều tra hậu quả.

Không thể chỉ dựa vào log “đã khóa khóa API” để kết luận đủ các mục trên.

## 12. Thiết kế kiểm thử và diễn tập containment

### 12.1. Tách kiểm tra khả năng kỹ thuật khỏi diễn tập phối hợp

| Mức đánh giá | Điều có thể chứng minh |
| --- | --- |
| Kiểm tra thành phần | Quyết định quyền, chuyển trạng thái và xử lý lệnh lặp |
| Kiểm thử tích hợp | API, danh tính, hàng đợi và worker cùng thực thi phạm vi |
| Kiểm tra cấu hình triển khai | Nút, tuyến kết nối và kho dữ liệu thực sự chịu tác động |
| Diễn tập kỹ thuật | Đo thời gian và hành vi trong kịch bản có kiểm soát |
| Tabletop | Vai trò, quyết định, phối hợp và thông tin cần để hành động |

Một tabletop có thể phát hiện không ai có quyền gỡ biện pháp, nhưng không tự chứng minh token cũ bị từ chối trong 120 giây. Ngược lại, API thử đạt không chứng minh đội trực có thể tìm đúng phạm vi và phối hợp nhà cung cấp.

### 12.2. Ma trận tình huống kiểm chứng

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Người ứng phó đúng quyền tạo lệnh | Lệnh được ghi đúng phạm vi và có audit |
| Người thiếu quyền tạo hoặc gỡ lệnh | Không đổi trạng thái containment |
| Lệnh được gửi lặp | Không làm trạng thái bị đảo hoặc mở rộng ngoài ý định |
| Lệnh gỡ cũ đến sau lệnh giữ mới | Quyết định hiện hành vẫn được tôn trọng |
| Token cũ gọi API sau giới hạn thu hồi | Không thực hiện được hành động bị chặn |
| Tác vụ đã xếp hàng trước lệnh | Được giữ hoặc xử lý đúng chính sách, không bàn giao trái phép |
| Tệp hoặc liên kết tải đã tạo | Không cung cấp dữ liệu thuộc phạm vi bị giữ theo giới hạn đã định |
| Một nút không phản hồi | Báo chưa rõ hoặc áp dụng một phần; không tự báo toàn bộ thành công |
| Restart hoặc thêm nút mới | Trạng thái hạn chế được duy trì |
| Tenant ngoài phạm vi thực hiện chức năng đối chứng | Không bị chặn ngoài quyết định đã nêu |
| Đến hạn xem xét nhưng chưa có quyết định gỡ | Không tự coi biện pháp đã hết cần thiết |
| Gỡ hợp lệ sau khi đạt điều kiện | Mở đúng phạm vi, có kiểm chứng và audit |
| Khôi phục từ bản sao cũ | Không làm mất trạng thái hoặc mở lại ngoài quy trình |

Điều kiện thử phải phản ánh đúng hợp đồng. Nếu hệ thống không có loại liên kết tải được cấp trước, ghi rõ mục đó không áp dụng thay vì tạo một tuyên bố chung không được kiểm chứng.

### 12.3. Kịch bản kiểm tra minh họa

~~~text
Mục tiêu:
Xác minh chế độ giữ xuất tenant A không chỉ chặn tác vụ mới.

Chuẩn bị:
- Có tác vụ đang chờ, tác vụ đang chạy và tệp đã tạo của tenant A.
- Có tài khoản, dữ liệu và tác vụ đối chứng của tenant B.
- Các điểm quan sát và mốc thời gian được xác định.
- Người thực hiện có đúng quyền containment trong môi trường thử.

Thực hiện:
1. Tạo lệnh giữ xuất tenant A.
2. Ghi mốc lệnh được lưu bền vững.
3. Thử tạo tác vụ mới và tải kết quả thuộc phạm vi.
4. Quan sát tác vụ đã tồn tại và đường tải được cấp trước đó.
5. Thêm hoặc khởi động lại một thành phần trong kịch bản thử.
6. Kiểm tra trạng thái, audit và hoạt động đối chứng của tenant B.

Đạt khi:
- Đáp ứng giới hạn hiệu lực và các hành vi đã đặc tả.
- Không có bàn giao dữ liệu ngoài chính sách giữ.
- Trạng thái qua restart phù hợp.
- Phạm vi tác động và bằng chứng được ghi rõ.

Không đạt hoặc chưa đủ bằng chứng khi:
Một đường vẫn bàn giao trái chính sách, một nút chưa rõ trạng thái,
hoặc không thể đối chiếu thời điểm và kết quả cần thiết.
~~~

Mẫu chỉ mô tả ý định kiểm thử; việc triển khai phụ thuộc kiến trúc và phạm vi được cho phép.

### 12.4. Quan sát lỗi và kịch bản giảm khả năng

Cần thử những lỗi làm biện pháp chỉ áp dụng một phần: mất kết nối đến điểm thực thi, lỗi hệ thống policy, hàng đợi chậm, giới hạn API của nhà cung cấp hoặc kênh logging gián đoạn.

Kết quả mong đợi phải được đặc tả: duy trì hạn chế, chuyển phương án khác, báo cấp xử lý cao hơn hoặc giới hạn chức năng. Không mặc định timeout nghĩa là thành công.

## 13. Đo lường và báo cáo hiệu lực

### 13.1. Định nghĩa các mốc trước khi tính thời gian

Có thể ghi:

- Tín hiệu đầu được nhận.
- Sự cố được phân loại hoặc xác nhận theo quy trình.
- Quyết định biện pháp được đưa ra.
- Lệnh được ghi nhận bền vững.
- Từng điểm thực thi áp dụng.
- Hiệu lực được kiểm chứng theo phạm vi.
- Biện pháp được điều chỉnh hoặc gỡ.

Khi dùng chỉ số như time to containment, phải nêu rõ mốc bắt đầu, mốc kết thúc và điều kiện kết luận. Không dùng cùng một tên cho các phép đo khác nghĩa.

### 13.2. Không chỉ báo thời gian trung bình

Một số sự cố nhanh có thể che những trường hợp chậm hoặc chưa hoàn tất. Báo cáo có thể cần:

- Thời gian theo từng sự cố và mức ưu tiên.
- Tỷ lệ đối tượng đã áp dụng hoặc kiểm chứng.
- Số đối tượng thất bại hoặc chưa rõ.
- Những đường gây hại còn mở.
- Gián đoạn ngoài phạm vi dự kiến.
- Những lần biện pháp bị mất sau restart hoặc khôi phục.
- Phần bằng chứng và phụ thuộc nhà cung cấp còn thiếu.

Trường hợp chưa hoàn tất không được loại khỏi báo cáo chỉ vì chưa có mốc kết thúc để tính thời gian.

### 13.3. Bản ghi trạng thái mẫu

~~~text
Sự cố: INC-EXPORT-A
Mục tiêu: Ngăn tiếp tục xuất và bàn giao dữ liệu trong phạm vi đã xác định
Phạm vi: Danh tính liên quan và luồng xuất tenant A
Lệnh: Tham chiếu bản ghi có thẩm quyền và phiên bản trạng thái
Thời điểm: Tín hiệu, quyết định, lưu lệnh, áp dụng và kiểm chứng
Kết quả: Theo từng API, worker và đường tải
Giới hạn: Hệ thống hoặc dữ liệu chưa được xác minh
Tác động nghiệp vụ: Chức năng bị giữ và đối chứng ngoài phạm vi
Bằng chứng: Tham chiếu hiện vật đã được bảo vệ
Bước tiếp theo: Điều tra, mở rộng phạm vi hoặc chuẩn bị phục hồi
Người phụ trách: Vai trò điều phối và chủ hệ thống
~~~

Các nội dung trong mẫu phải được điền cụ thể khi sử dụng cho sự cố thật. Không dùng một trạng thái tổng hợp để che những phần chưa rõ.

## 14. Gỡ containment và chuyển sang phục hồi

### 14.1. Điều kiện mở lại

Tùy sự cố, có thể cần xác nhận:

- Phạm vi ảnh hưởng đã được đánh giá đến mức đủ để ra quyết định.
- Đường xâm nhập hoặc khả năng gây hại liên quan đã được xử lý.
- Danh tính, quyền và cấu hình đích đã được xác minh.
- Dữ liệu và hiện vật cần giữ đã được quản lý.
- Các tác vụ tồn và tệp tạm được xử lý đúng.
- Logging và khả năng phát hiện sẵn sàng.
- Người có thẩm quyền chấp thuận phạm vi mở lại.
- Có cách theo dõi và tái áp dụng hạn chế khi phát hiện dấu hiệu mới.

Không mở lại chỉ vì không còn cảnh báo hoặc vì đã cấp một khóa mới. Hệ thống có thể còn quyền trái phép, tác vụ hoặc đường tải không phụ thuộc khóa đó.

### 14.2. Mở theo từng phần khi phù hợp

Có thể khôi phục một phần chức năng hoặc phạm vi đã được xác nhận trước, trong khi giữ hạn chế ở phần chưa đủ cơ sở.

Mỗi lần mở cần giữ cùng tính rõ ràng: ai quyết định, phạm vi nào, phiên bản cấu hình nào, điều kiện kiểm chứng và cách xử lý nếu sai.

Đảo ngược thao tác kỹ thuật không phải lúc nào cũng là phục hồi an toàn. Một rule bị gỡ có thể khôi phục cả đường dữ liệu chưa được làm sạch hoặc chưa được đánh giá.

### 14.3. Biến bài học thành yêu cầu trong SDLC

Sau sự cố hoặc diễn tập:

1. Xác định khả năng nào thiếu hoặc không đạt.
2. Viết yêu cầu đo được với chủ thể, phạm vi và giới hạn.
3. Liên kết với rủi ro và thiết kế cần thay đổi.
4. Bổ sung kiểm thử và dữ liệu thử.
5. Lưu bằng chứng của phiên bản mới.
6. Cập nhật runbook và trách nhiệm vận hành.
7. Duy trì ca hồi quy cho lỗi đã được xử lý.

Ví dụ, phát hiện “khóa API nhưng bản xuất cũ vẫn tải được” cần dẫn đến yêu cầu và thiết kế cho đường bàn giao dữ liệu. Chỉ bổ sung một dòng vào checklist vận hành có thể chưa đủ nếu nền tảng thiếu khả năng kỹ thuật.

## 15. Sai sót thường gặp

| Sai sót | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Đồng nhất nhận lệnh với có hiệu lực | Báo thành công khi điểm thực thi chưa cập nhật | Tách trạng thái và có kiểm chứng hành vi |
| Chỉ khóa tài khoản | Token, tác vụ hoặc đường tải tiếp tục gây hại | Phân tích toàn bộ chuỗi danh tính và dữ liệu |
| Chỉ chặn tại UI hoặc một gateway | Còn đường gọi trực tiếp hoặc phía sau | Kiểm kê giao diện và điểm thực thi |
| Cố định phạm vi theo giả định đầu | Bỏ hoạt động liên quan mới | Cập nhật phạm vi theo bằng chứng |
| Biện pháp mất sau restart | Hệ thống tự mở lại ngoài quyết định | Duy trì trạng thái và kiểm tra nút mới |
| Gỡ tự động theo ngày dự kiến | Nguy cơ còn tồn tại nhưng hạn chế biến mất | Phân biệt hạn xem xét và điều kiện kết thúc |
| Cắt mọi telemetry ngoài kế hoạch | Không đánh giá được phạm vi và hiệu lực | Bảo vệ đường quan sát cần thiết hoặc ghi rõ giới hạn |
| Thu thập mọi dữ liệu không phân biệt | Tạo thêm bản sao và người tiếp cận thông tin nhạy cảm | Giới hạn hiện vật theo mục tiêu và thẩm quyền |
| Xóa hoặc khởi động lại theo thói quen | Mất bằng chứng hoặc tăng gián đoạn | Quyết định theo kịch bản và ghi hành động |
| Không có quyền gỡ hoặc người thay thế | Dịch vụ bị giữ không ai quản lý | Thiết kế trách nhiệm và quyền từ trước |
| Không kiểm tra ngoài phạm vi | Biện pháp ảnh hưởng tenant hoặc chức năng khác | Có đối chứng phù hợp trong kiểm thử |
| Gọi containment là xử lý xong | Bỏ nguyên nhân, hậu quả hoặc điều kiện phục hồi | Giữ riêng mục tiêu và bằng chứng của từng hoạt động |

## 16. Tiêu chí sẵn sàng của yêu cầu containment

Đây là kiểm tra về khả năng đặc tả và kiểm chứng, không phải kết luận mọi sự cố đều có thể được khoanh vùng hoàn toàn.

- [ ] Có kịch bản sự cố và thiệt hại cần ngăn cụ thể.
- [ ] Đơn vị khoanh vùng và phạm vi kỹ thuật được xác định.
- [ ] Có người hoặc cơ chế đủ thẩm quyền thực hiện và gỡ biện pháp.
- [ ] Các điều kiện kích hoạt, hành động và giới hạn tự động hóa rõ.
- [ ] Xác thực và phân quyền của đường điều khiển được kiểm thử.
- [ ] Token, phiên, quyền ủy nhiệm và cache đã được xem xét.
- [ ] Tác vụ chờ, tác vụ đang chạy, tệp và đường tải cũ đã được xem xét.
- [ ] Có mốc thời gian, giới hạn hiệu lực và cách đo.
- [ ] Phân biệt nhận lệnh, thực thi, kiểm chứng và áp dụng một phần.
- [ ] Có hành vi khi một điểm thực thi không phản hồi.
- [ ] Trạng thái được duy trì qua restart, mở rộng và khôi phục.
- [ ] Logging và bằng chứng được bảo vệ, có nguồn và lịch sử phù hợp.
- [ ] Tác động nghiệp vụ và chức năng ngoài phạm vi được xác định.
- [ ] Có tiêu chí gỡ containment và điều kiện phục hồi.
- [ ] Biện pháp tạm có người sở hữu và lịch xem xét.
- [ ] Kiểm thử kỹ thuật và diễn tập phối hợp tạo được bằng chứng tương ứng.
- [ ] Các khoảng trống phát hiện được đưa trở lại vòng đời yêu cầu.

## 17. Tài liệu tham khảo

- [NIST SP 800-61 Rev. 3 — trang công bố chính thức](https://csrc.nist.gov/pubs/sp/800/61/r3/final): ứng phó sự cố trong quản lý rủi ro theo CSF 2.0.
- [NIST SP 800-61 Rev. 3 — toàn văn](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf): RS.MI-01 về containment, RS.MI-02 về eradication và các kết quả phục hồi liên quan.
- [NIST Cybersecurity Framework 2.0](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf): các nhóm kết quả Respond, Incident Analysis, Incident Mitigation và Recover.

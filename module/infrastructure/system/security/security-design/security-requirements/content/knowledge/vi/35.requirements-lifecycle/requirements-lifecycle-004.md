# Ưu tiên requirement trong vòng đời yêu cầu bảo mật

## 1. Mục tiêu bài học

Một danh sách yêu cầu bảo mật chỉ trở thành kế hoạch thực hiện khi nhóm biết yêu cầu nào cần làm trước, yêu cầu nào phải đạt trước khi mở một chức năng và yêu cầu nào có thể xử lý sau trong một khoảng thời gian được chấp thuận.

**Ưu tiên requirement** là quá trình lựa chọn thứ tự và mốc đáp ứng yêu cầu dựa trên rủi ro, phạm vi phát hành, nghĩa vụ áp dụng, phụ thuộc kỹ thuật và năng lực thực hiện. Kết quả phải có lý do, người chịu trách nhiệm và điều kiện xem xét lại.

Trong module Security Requirements, việc ưu tiên nối các mục tiêu an toàn và mô hình đe dọa với yêu cầu cụ thể về xác thực, phân quyền, dữ liệu, logging và phục hồi. Nó không chỉ là sắp xếp các công việc có nhãn “security”.

Học xong bài này, bạn có thể:

- Phân biệt mức ưu tiên, mức nghiêm trọng của rủi ro, điều kiện chấp nhận phát hành và trạng thái triển khai.
- Chọn yêu cầu cần xử lý trước theo kịch bản đe dọa và mức rủi ro còn lại.
- Xử lý nghĩa vụ, phụ thuộc và bất định trước khi dùng điểm số để sắp thứ tự.
- Lập kế hoạch có đủ triển khai, kiểm thử và bằng chứng cho yêu cầu được chọn.
- Ghi lại quyết định hoãn, ngoại lệ và các sự kiện làm thay đổi ưu tiên.

Mã yêu cầu, nhãn ưu tiên, ngân sách công sức và ngưỡng số trong bài là ví dụ nội bộ để học cách ra quyết định. Chúng không phải mức bắt buộc chung cho mọi tổ chức.

## 2. Ưu tiên yêu cầu trả lời những câu hỏi nào?

Một quyết định ưu tiên tốt trả lời được:

1. Tài sản và luồng nghiệp vụ nào đang có rủi ro?
2. Yêu cầu này giảm rủi ro nào và giảm ở đâu trong kiến trúc?
3. Khi nào yêu cầu phải được đáp ứng để phạm vi dự kiến được phép hoạt động?
4. Có phụ thuộc nào phải hoàn thành trước?
5. Cần bao nhiêu công sức cho cả triển khai lẫn xác minh?
6. Nếu chưa làm, ai chịu trách nhiệm cho quyết định và khi nào phải xem xét lại?

Ví dụ, “thêm MFA cho tài khoản quản trị” chưa đủ để quyết định thứ tự. Cần biết giao diện quản trị đã mở ra bên ngoài hay chưa, có đường đăng nhập dự phòng nào, tài khoản có thể thực hiện thao tác gì và có kiểm soát hiện hữu nào đã được xác minh.

Một chức năng chưa được mở có thể cho phép nhóm loại nó khỏi bản phát hành để giảm phạm vi rủi ro. Với một đường quản trị đang bị khai thác, hành động cần thiết có thể là cô lập hoặc khóa truy cập ngay, rồi mới hoàn thiện yêu cầu dài hạn.

### 2.1. Bốn thuộc tính cần tách riêng

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| Mức nghiêm trọng của rủi ro | Hậu quả và khả năng xảy ra trong một kịch bản xác định | Người dùng có thể xuất dữ liệu tenant khác qua API công khai. |
| Mức ưu tiên | Thứ tự và thời điểm cần xử lý trong bối cảnh hiện tại | Đưa yêu cầu cách ly tenant vào nhóm cần làm ngay trước khi mở API. |
| Điều kiện phát hành | Tiêu chí cần đạt để một phạm vi được phép triển khai hoặc kích hoạt | Không bật chức năng xuất dữ liệu khi kiểm tra quyền chưa được xác minh. |
| Trạng thái thực hiện | Yêu cầu đang ở đâu trong quá trình làm việc | Đã viết đặc tả, đang triển khai, chờ kiểm thử hoặc đã xác minh đạt. |

Một yêu cầu ưu tiên cao vẫn có thể chưa triển khai. Một yêu cầu đã triển khai vẫn có thể chưa đạt tiêu chí kiểm thử. Không nên dùng một cột “High/Medium/Low” để thay cho cả bốn thuộc tính.

Mức ưu tiên có thể thay đổi khi phạm vi hoặc rủi ro thay đổi. Điều đó không tự động làm yếu đi nghĩa vụ bảo vệ đã áp dụng.

## 3. Đầu vào tối thiểu trước khi xếp ưu tiên

### 3.1. Yêu cầu phải đủ rõ để so sánh

Hai câu “cải thiện logging” và “bảo mật API” không phải hai đơn vị công việc có thể ước lượng hoặc so sánh đáng tin cậy.

Cần diễn đạt thành hành vi cụ thể:

> Các API hồ sơ phải kiểm tra quyền theo chủ thể, hành động, tenant và tài nguyên đích. Yêu cầu truy cập chéo tenant bị từ chối không được trả dữ liệu hoặc gây thay đổi trạng thái.

Hoặc:

> Sự kiện audit cho thao tác xuất dữ liệu phải ghi chủ thể, tenant, phạm vi xuất, kết quả và mã tương quan; không ghi token truy cập hoặc toàn bộ nội dung hồ sơ.

Nếu yêu cầu còn quá rộng, tách thành các phần có kết quả kiểm chứng được. Việc tách phải giữ đủ các thành phần cần thiết để đạt mục tiêu bảo vệ.

### 3.2. Dữ liệu cần có cho từng yêu cầu

| Nhóm thông tin | Nội dung cần ghi |
|---|---|
| Phạm vi | Dịch vụ, endpoint, tác vụ nền, loại dữ liệu và môi trường liên quan. |
| Căn cứ | Mục tiêu an toàn, kịch bản đe dọa, kiểm soát nền hoặc nghĩa vụ đã xác định. |
| Rủi ro | Tài sản bị ảnh hưởng, tác nhân, đường tấn công, điều kiện và hậu quả. |
| Trạng thái hiện tại | Kiểm soát đang tồn tại, bằng chứng hiệu quả và khoảng thiếu hụt. |
| Mốc cần đạt | Trước khi phát hành, trước khi mở thêm dữ liệu hoặc trước hạn đã được xác nhận. |
| Phụ thuộc | Yêu cầu, thành phần nền tảng, quyết định kiến trúc và nhà cung cấp liên quan. |
| Ước lượng | Công sức triển khai, tích hợp, kiểm thử, thu thập bằng chứng và thời gian chờ. |
| Bất định | Điều chưa biết, mức tin cậy và hoạt động cần làm để xác minh. |
| Trách nhiệm | Chủ yêu cầu, nhóm thực hiện và người quyết định phần rủi ro còn lại. |

Không cần chờ có mọi chi tiết mới bắt đầu. Tuy nhiên, cần hiển thị phần chưa biết, thay vì mặc định nó không ảnh hưởng tới ưu tiên.

## 4. Xét điều kiện bắt buộc trước khi chấm điểm

Một bảng điểm có thể hỗ trợ so sánh, nhưng không nên cho phép lợi ích ở mục khác bù trừ một điều kiện phát hành chưa đạt.

Nên thực hiện theo hai lớp:

1. **Xác định ràng buộc và điều kiện cần đạt:** yêu cầu nào bắt buộc cho đúng phạm vi, mốc thời gian và quyết định rủi ro hiện tại.
2. **Sắp thứ tự phần việc có thể lựa chọn:** so sánh mức giảm rủi ro, phụ thuộc, công sức và cơ hội thực hiện trong tập còn lại.

### 4.1. Những điều kiện có thể khiến yêu cầu phải làm trước

- Có dấu hiệu khai thác thực tế hoặc đường tấn công đã được xác nhận trên tài sản đang hoạt động.
- Rủi ro vượt ngưỡng được tổ chức chấp nhận cho phạm vi sắp phát hành.
- Yêu cầu là điều kiện cho một chức năng mới có dữ liệu hoặc đặc quyền nhạy cảm.
- Có thời hạn áp dụng từ nguồn nghĩa vụ đã được người phụ trách xác nhận.
- Một yêu cầu là tiền đề cần thiết để kiểm soát quan trọng khác có hiệu lực.
- Trì hoãn quyết định sẽ khóa hệ thống vào thiết kế khó sửa, chẳng hạn mô hình dữ liệu thiếu ranh giới tenant.

Không kết luận có nghĩa vụ chỉ từ một nhãn “compliance”. Hồ sơ phải chỉ rõ nguồn, phạm vi, thời điểm áp dụng và người xác nhận cách diễn giải.

### 4.2. Nếu không đủ năng lực thực hiện

Cần thay đổi kế hoạch một cách rõ ràng:

- Giảm hoặc loại phạm vi chức năng chưa được bảo vệ.
- Hoãn mốc phát hành hoặc bổ sung năng lực.
- Triển khai biện pháp tạm thời được đánh giá hiệu quả và giới hạn.
- Xin ngoại lệ có thời hạn nếu chính sách và nguồn nghĩa vụ cho phép.

Không phải ràng buộc nào cũng có thể được miễn trừ nội bộ. Người chấp nhận rủi ro phải có thẩm quyền phù hợp; việc gắn nhãn ưu tiên thấp không tạo ra quyền bỏ qua một nghĩa vụ đang áp dụng.

## 5. Đánh giá rủi ro để biết yêu cầu nào tạo giá trị bảo vệ

### 5.1. Viết kịch bản thay vì chỉ gắn tên mối đe dọa

“Rò rỉ dữ liệu” quá rộng để so sánh. Một kịch bản tốt hơn:

> Người dùng hợp lệ của tenant A thay mã hồ sơ trong API đọc dữ liệu để truy cập hồ sơ của tenant B, do dịch vụ chỉ kiểm tra đăng nhập mà không kiểm tra quyền trên tài nguyên.

Từ đó xác định:

- **Tài sản:** hồ sơ riêng của khách hàng.
- **Tác nhân và khả năng tiếp cận:** người dùng có tài khoản và truy cập được API.
- **Điểm yếu:** thiếu kiểm tra quyền tại nơi truy cập tài nguyên.
- **Hậu quả:** lộ dữ liệu giữa các tenant.
- **Yêu cầu cần ưu tiên:** kiểm tra quyền trên toàn bộ đường đọc, sửa, xóa và xuất thuộc phạm vi.
- **Bằng chứng cần có:** kiểm thử chéo tenant cùng rà soát các đường truy cập và tác vụ nền.

Yêu cầu “thêm cảnh báo đăng nhập thất bại” có thể hữu ích, nhưng không trực tiếp khắc phục kịch bản này vì tác nhân đã đăng nhập hợp lệ.

### 5.2. Xét rủi ro còn lại dựa trên kiểm soát hiện hữu

Khi so sánh, cần phân biệt:

- Rủi ro khi không xét kiểm soát.
- Rủi ro hiện tại sau các kiểm soát đang hoạt động và có bằng chứng phù hợp.
- Rủi ro dự kiến sau khi yêu cầu được triển khai và xác minh.

Không coi một kế hoạch “sẽ bật MFA” là kiểm soát hiện hữu. Không coi việc có backup là bằng chứng rằng có thể khôi phục đúng mục tiêu.

Một yêu cầu có thể được làm sau nếu kiểm soát hiện hữu đã làm giảm rủi ro tới mức được chấp nhận trong phạm vi và thời hạn xác định. Quyết định này phải dựa trên bằng chứng, không chỉ dựa trên tên công nghệ.

### 5.3. Các khía cạnh nên xem xét cùng nhau

| Khía cạnh | Câu hỏi thực tế |
|---|---|
| Tác động | Mất bí mật, toàn vẹn hoặc sẵn sàng sẽ ảnh hưởng tới ai và tới mức nào? |
| Khả năng xảy ra | Tác nhân có tiếp cận được không, cần điều kiện gì và đường khai thác đã được chứng minh tới đâu? |
| Mức phơi lộ | Luồng đang công khai, chỉ nội bộ có kiểm soát hay chưa được kích hoạt? |
| Phạm vi ảnh hưởng | Một tài nguyên, một tenant hay nhiều dịch vụ và khách hàng? |
| Thời gian có thể bị ảnh hưởng | Khoảng thời gian nào xuất hiện khi quyết định trì hoãn? |
| Mức giảm rủi ro | Yêu cầu ngăn, phát hiện hoặc hỗ trợ phục hồi cho kịch bản nào? |
| Mức tin cậy | Kết luận dựa trên kiểm thử, quan sát vận hành hay một giả định chưa kiểm tra? |

Không cần nhân các nhãn “Cao = 3” và “Trung bình = 2” rồi xem kết quả là xác suất hoặc thiệt hại chính xác. Các mức định tính giúp thống nhất cách so sánh; chúng vẫn cần được giải thích bằng kịch bản và bằng chứng.

### 5.4. Xử lý bất định có tác động lớn

Giả sử chưa biết worker xuất dữ liệu có kiểm tra lại quyền hay không. Chưa có bằng chứng không đồng nghĩa với rủi ro thấp.

Có thể ưu tiên một hoạt động khảo sát ngắn: rà soát đường đi của tác vụ và thử trường hợp quyền bị thu hồi trước khi worker thực thi. Kết quả giúp xác định phạm vi sửa và quyết định có được mở chức năng hay không.

Hoạt động khảo sát hoàn thành chỉ có nghĩa là đã giảm phần chưa biết. Nếu phát hiện thiếu kiểm soát, yêu cầu bảo vệ vẫn chưa được đáp ứng.

## 6. Phụ thuộc và kiến trúc ảnh hưởng tới thứ tự

Một yêu cầu giảm rủi ro lớn có thể phụ thuộc vào những công việc nền ít dễ nhìn thấy.

Ví dụ:

```text
Định danh tenant từ ngữ cảnh đã xác minh
                  |
                  v
Chính sách quyền cho chủ thể - hành động - tài nguyên
                  |
           +------+------+
           |             |
           v             v
     API trực tiếp   Worker tác vụ nền
           |             |
           +------+------+
                  |
                  v
   Kiểm thử chéo tenant và thay đổi quyền
```

Nếu nhóm chỉ ưu tiên endpoint dễ sửa mà chưa thống nhất nguồn tenant đáng tin cậy, các thành phần có thể diễn giải khác nhau và để lại đường đi vòng.

Cần tách hai loại quyết định:

- **Mức quan trọng của kết quả bảo vệ:** vì sao yêu cầu cần đạt.
- **Thứ tự thực hiện:** phần nào phải làm trước để kết quả đó có thể đạt.

Một công việc nền được thực hiện sớm vì phụ thuộc không có nghĩa là bản thân nó có cùng mức rủi ro với mọi yêu cầu phía sau. Hồ sơ cần ghi quan hệ phụ thuộc thay vì nâng nhãn ưu tiên của toàn bộ backlog.

### 6.1. Tách việc thành phần có thể xác minh độc lập

Có thể tách một yêu cầu rộng theo luồng hoặc tài sản, với điều kiện phần đưa vào sử dụng đã được bảo vệ đầy đủ.

Ví dụ, trước tiên mở chức năng đọc hồ sơ với kiểm tra quyền đã được xác minh, còn chức năng xuất dữ liệu chưa mở. Đây là giảm phạm vi có kiểm soát.

Ngược lại, chỉ kiểm tra quyền ở giao diện nhưng vẫn mở API không được bảo vệ không tạo thành một phần hoàn thành độc lập. Người gọi có thể bỏ qua giao diện.

### 6.2. Ưu tiên quyết định khó thay đổi

Một số quyết định nên được giải quyết sớm ngay cả khi chức năng chưa hoàn thiện:

- Ranh giới tenant trong mô hình dữ liệu.
- Nguồn danh tính và cách ánh xạ sang quyền nghiệp vụ.
- Phạm vi tin cậy giữa các dịch vụ.
- Vị trí thực thi chính sách.
- Cơ chế bảo vệ khóa và bản sao lưu.
- Cách ghi nhận sự kiện để điều tra được thao tác qua nhiều thành phần.

Nếu để tới cuối, nhóm có thể phải sửa nhiều thành phần cùng lúc. Tuy nhiên, “ảnh hưởng kiến trúc” cũng cần được chứng minh bằng phụ thuộc và tác động cụ thể, không dùng làm lý do chung để mọi công việc đều khẩn cấp.

## 7. Phương pháp xếp ưu tiên và giới hạn sử dụng

### 7.1. MoSCoW cho một mốc hoặc phạm vi cụ thể

MoSCoW có thể giúp trao đổi về cam kết của một bản phát hành:

| Nhóm | Cách hiểu trong ví dụ bảo mật |
|---|---|
| Must have | Không thể chấp thuận phạm vi phát hành đã định nếu thiếu yêu cầu này. |
| Should have | Có giá trị lớn, nhưng có thể xử lý sau nếu rủi ro còn lại được quyết định rõ ràng. |
| Could have | Có ích khi còn năng lực và không làm trễ phần cần đạt. |
| Won't have this time | Chủ động không đưa vào mốc hiện tại; cần ghi phạm vi, lý do và thời điểm xem xét lại. |

Từ “Must” chỉ có ý nghĩa khi kèm phạm vi và mốc. “Mọi yêu cầu bảo mật đều là Must” không giúp lập kế hoạch; “chỉ những việc dễ làm mới là Must” lại bỏ qua rủi ro.

Một yêu cầu có thể không thuộc bản phát hành hiện tại vì chức năng liên quan đã được loại khỏi phạm vi. Điều đó không đồng nghĩa yêu cầu bị xóa vĩnh viễn hoặc được phép bỏ qua khi chức năng được mở lại.

### 7.2. Ma trận quyết định có tiêu chí rõ ràng

Với các yêu cầu không bị ràng buộc phải đạt ngay, có thể so sánh các tiêu chí:

- Mức giảm rủi ro đối với kịch bản đã nêu.
- Mức nhạy cảm với thời gian hoặc thay đổi phạm vi.
- Khả năng mở đường cho yêu cầu khác.
- Chi phí và công sức để đạt kết quả được xác minh.
- Độ chắc chắn của đánh giá.

Nếu dùng trọng số hoặc điểm tổng, phải thống nhất trước ý nghĩa từng mức, ghi lý do chấm và kiểm tra xem đổi giả định có làm đảo thứ tự hay không.

Một điểm tổng cao không cho phép đưa một yêu cầu qua điều kiện phát hành mà nó chưa đáp ứng. Điểm số cũng không phải phép đo khách quan về “phần trăm an toàn” của hệ thống.

### 7.3. Ưu tiên giá trị giảm rủi ro theo công sức

Tỷ lệ lợi ích so với công sức hữu ích khi chọn giữa các phương án cùng đáp ứng ràng buộc. Ví dụ, cấu hình sẵn có có thể xử lý một đường truy cập nguy hiểm nhanh hơn việc xây một cơ chế mới.

Tuy nhiên, cách so sánh này có thể thiên về việc nhỏ, dễ ghi điểm và bỏ đói thay đổi nền tảng. Không dùng tỷ lệ để cho một chuỗi cải tiến nhỏ vượt qua một kiểm soát bắt buộc có công sức lớn.

Công sức phải gồm thiết kế, triển khai, tích hợp, kiểm thử âm tính, xử lý lỗi và bằng chứng. “Một dòng cấu hình” không đồng nghĩa với “không cần xác minh”.


## 8. Quy trình ưu tiên yêu cầu trong một vòng lập kế hoạch

### Bước 1: Chốt phạm vi và mốc ra quyết định

Ghi rõ đang ưu tiên cho bản phát hành nào, nhóm người dùng nào và loại dữ liệu nào. Phân biệt triển khai mã với kích hoạt chức năng: mã đã lên môi trường nhưng chức năng chưa mở vẫn cần có cơ chế ngăn truy cập được xác minh.

### Bước 2: Chuẩn hóa yêu cầu và tiêu chí chấp nhận

Mỗi yêu cầu cần có định danh, hành vi cần đạt, phạm vi và cách xác minh. Nếu yêu cầu quá rộng hoặc chỉ nêu giải pháp mơ hồ, làm rõ trước khi ước lượng.

Ví dụ, thay “thêm log tốt hơn” bằng “ghi sự kiện cho thao tác thay đổi quyền, gồm chủ thể, tài nguyên, kết quả và mã tương quan; không chứa bí mật xác thực”.

### Bước 3: Xác định rủi ro và điều kiện phải đạt

Liên kết từng yêu cầu với kịch bản đe dọa, kiểm soát nền hoặc nghĩa vụ đã xác nhận. Ghi yêu cầu nào là điều kiện cho phạm vi dự kiến, không để điểm tổng làm mờ ràng buộc này.

### Bước 4: Rà soát phụ thuộc và phương án xử lý

Nhận diện thành phần dùng chung, nhà cung cấp, thay đổi dữ liệu và việc cần làm trước. Với yêu cầu công sức lớn, xem xét giảm phạm vi hoặc một thiết kế khác có thể đạt cùng mục tiêu bảo vệ.

### Bước 5: Ước lượng cả hoàn thành lẫn xác minh

Làm rõ công sức của từng nhóm và thời gian chờ. Một ngày công không đồng nghĩa với một ngày lịch: có thể phải chờ môi trường, phê duyệt hoặc thay đổi ở dịch vụ khác.

Ghi độ tin cậy của ước lượng. Nếu còn bất định lớn, thực hiện khảo sát có thời hạn thay vì cam kết một con số chính xác giả tạo.

### Bước 6: Xếp thứ tự và kiểm tra khả thi

Đưa hành động khẩn cấp và điều kiện cần đạt vào kế hoạch trước. Sắp các mục còn lại theo tiêu chí đã thống nhất. Kiểm tra tổng năng lực và đường phụ thuộc để biết mốc dự kiến có thực tế hay không.

### Bước 7: Ghi quyết định và phần chưa làm

Với mỗi mục được hoãn, ghi lý do, rủi ro còn lại, kiểm soát hiện hữu, mốc xem xét lại và người quyết định. Nếu cần ngoại lệ, dùng quy trình ngoại lệ phù hợp thay vì chỉ để một ghi chú trong backlog.

### Bước 8: Theo dõi bằng kết quả kiểm chứng

Khi triển khai xong, xác minh theo tiêu chí chấp nhận. Nếu kiểm thử thất bại hoặc xuất hiện đường truy cập mới, cập nhật kế hoạch và quyết định phát hành. Không coi trạng thái “đã merge” là bằng chứng yêu cầu đã đạt.

## 9. Ví dụ: ngân sách 10 ngày công cho một bản phát hành

### 9.1. Bối cảnh và giả định

Một dịch vụ nhiều tenant chuẩn bị mở cho khách hàng. Phạm vi dự kiến gồm API hồ sơ, công cụ quản trị và chức năng xuất dữ liệu chạy qua worker.

Các giả định đã được nhóm xác nhận trong tình huống minh họa:

- Xác thực cơ bản đã tồn tại, nhưng kiểm tra quyền theo tenant chưa bao phủ đủ các đường truy cập.
- Chức năng xuất dữ liệu là chức năng mới, chưa được cung cấp cho người dùng.
- Đã có hạ tầng sao lưu, nhưng chưa có bằng chứng diễn tập khôi phục của dịch vụ.
- Rà soát quyền định kỳ đang được làm thủ công theo quy trình đã xác minh; tự động hóa là cải tiến.
- Chính sách phát hành nội bộ xác định REQ-01 tới REQ-05 là điều kiện cần đạt cho các phạm vi tương ứng.
- Nhóm có 10 ngày công khả dụng trong kỳ; không mặc định ngày công bằng thời gian lịch.

### 9.2. Backlog và quyết định ban đầu

| Mã | Yêu cầu bảo mật | Căn cứ chính | Công sức minh họa | Quyết định cho phạm vi dự kiến |
|---|---|---|---|---|
| REQ-01 | API hồ sơ kiểm tra quyền theo chủ thể, hành động, tenant và tài nguyên | Ngăn truy cập chéo tenant | 3 ngày công | Phải đạt trước khi mở API. |
| REQ-02 | Worker và đường tải tệp xuất kiểm tra quyền theo chính sách hiện hành | Ngăn xuất hoặc tải dữ liệu trái phép | 3 ngày công | Phải đạt trước khi mở chức năng xuất; phụ thuộc cơ chế quyền của REQ-01. |
| REQ-03 | Không ghi token hoặc bí mật xác thực trong các đường logging đã xác định | Tránh lộ thông tin xác thực qua log | 1 ngày công | Phải đạt trước khi mở dịch vụ. |
| REQ-04 | Đường quản trị yêu cầu MFA, gồm đường dự phòng nằm trong phạm vi | Hạn chế chiếm dụng đặc quyền quản trị | 2 ngày công | Phải đạt trước khi cho phép truy cập quản trị. |
| REQ-05 | Khôi phục được dịch vụ theo RPO, RTO đã thống nhất và có bằng chứng | Giới hạn mất dữ liệu và gián đoạn | 2 ngày công | Phải đạt trước khi nhận dữ liệu khách hàng. |
| REQ-06 | Phát hiện và cảnh báo mẫu đăng nhập thất bại theo quy tắc được duyệt | Tăng khả năng phát hiện tấn công xác thực | 2 ngày công | Lập kế hoạch sau khi đáp ứng điều kiện hiện tại; xem lại nếu mức đe dọa đổi. |
| REQ-07 | Tự động hóa một phần rà soát quyền định kỳ | Giảm chậm trễ và sai sót của thao tác thủ công | 3 ngày công | Có thể hoãn khi quy trình hiện hữu vẫn đáp ứng và có bằng chứng. |
| REQ-08 | Bổ sung màn hình tổng hợp sự kiện audit | Hỗ trợ tra cứu và điều tra nhanh hơn | 2 ngày công | Có thể hoãn nếu vẫn truy xuất được bằng chứng theo yêu cầu hiện hành. |

Ước lượng từng mục đã bao gồm triển khai và kiểm thử riêng. Các mục này chưa bao gồm phần xác minh tích hợp chung của bản phát hành.

Tổng REQ-01 tới REQ-05 là:

```text
3 + 3 + 1 + 2 + 2 = 11 ngày công
```

Nhóm không thể cam kết đủ phạm vi chỉ với 10 ngày công, ngay cả trước khi tính phần xác minh chung. Việc chọn bốn mục rẻ nhất không giải quyết vấn đề nếu API và chức năng còn thiếu kiểm soát vẫn được mở.

### 9.3. Phương án giảm phạm vi có thể xem xét

Nhóm quyết định chưa phát hành chức năng xuất dữ liệu trong kỳ này:

- Giữ REQ-01, REQ-03, REQ-04 và REQ-05: tổng 8 ngày công.
- Dành 2 ngày công còn lại cho xác minh tích hợp chung, kiểm tra việc loại chức năng xuất và xử lý vấn đề phát sinh trong phạm vi khả dụng.
- Giữ REQ-02 trong backlog, gắn điều kiện phải đạt trước khi chức năng xuất được kích hoạt.
- Lên mốc xem xét REQ-06 tới REQ-08 dựa trên rủi ro và năng lực kỳ sau.

Việc loại chức năng xuất phải được thực thi ở phía máy chủ và các đường chạy liên quan. Cần xác minh không thể tạo tác vụ qua API trực tiếp, không có lịch chạy worker tạo tệp và không có đường tải tệp còn được mở trái với phạm vi đã chọn.

Chỉ ẩn nút trên giao diện không đủ. Nếu không chứng minh được chức năng đã được loại khỏi phạm vi hoạt động, REQ-02 vẫn là điều kiện chưa đạt cho bản phát hành đó.

REQ-02 chưa được “hoàn thành” và không bị xóa. Mốc áp dụng của nó được gắn với việc mở chức năng; mọi thay đổi phạm vi phải kích hoạt đánh giá lại trước khi cho người dùng truy cập.

### 9.4. Phần việc thực hiện trước và sau

Một thứ tự có thể là:

1. Làm REQ-01 sớm vì nó xác lập cơ chế quyền và ảnh hưởng nhiều đường truy cập.
2. Thực hiện REQ-03 và REQ-04 song song nếu nhân lực, thành phần và môi trường cho phép.
3. Chuẩn bị và diễn tập REQ-05; nếu kết quả không đạt, tính lại kế hoạch khắc phục.
4. Xác minh tích hợp, kiểm tra giới hạn phạm vi và rà soát bằng chứng trước quyết định phát hành.

Đây là thứ tự dựa trên các giả định đã nêu, không phải lịch mẫu dùng cho mọi dự án. Nếu đang có tài khoản quản trị bị khai thác, hành động ngăn chặn sẽ cần được ưu tiên ngay thay vì chờ thứ tự trên.

Nếu diễn tập phục hồi thất bại và ước lượng sửa vượt ngân sách, nhóm phải cập nhật phạm vi hoặc mốc phát hành. Không được giữ cam kết cũ bằng cách đổi REQ-05 thành ưu tiên thấp hơn.

## 10. Biến yêu cầu được ưu tiên thành công việc có thể nghiệm thu

Ưu tiên chỉ có giá trị nếu mục được chọn đi tới kết quả bảo vệ. Một hồ sơ cho REQ-01 có thể viết như sau:

```yaml
requirement_id: REQ-01
title: Cách ly quyền truy cập hồ sơ theo tenant
release_scope: API hồ sơ khách hàng
risk_refs:
  - RISK-TENANT-01
priority: P1
blocks_release: true
priority_reason: Ngăn người dùng đọc hoặc sửa hồ sơ tenant khác
owner: Nhóm dịch vụ hồ sơ
dependencies:
  - Nguồn danh tính và tenant đã xác minh
acceptance_criteria:
  - Chỉ cho phép thao tác khi chủ thể có quyền với hành động và tài nguyên
  - Từ chối khi không có đủ dữ kiện để quyết định quyền
  - Không trả dữ liệu hoặc gây thay đổi trái phép khi bị từ chối
verification:
  - Kiểm thử người dùng đúng tenant và có quyền
  - Kiểm thử chéo tenant
  - Kiểm thử cùng tenant nhưng thiếu quyền hành động
  - Rà soát toàn bộ đường truy cập API thuộc phạm vi
estimate:
  effort: 3 ngày công
  includes: Triển khai và kiểm thử riêng của yêu cầu
  confidence: Trung bình
review_trigger:
  - Thêm endpoint hoặc thay đổi mô hình quyền
  - Phát hiện đường truy cập chưa được bao phủ
```

Trong ví dụ này, P1 là nhãn nội bộ của nhóm cho yêu cầu cần đạt trước mốc phát hành liên quan. Tổ chức có thể dùng hệ nhãn khác, nhưng phải định nghĩa rõ và không để cùng một nhãn mang nghĩa khác nhau giữa các nhóm.

### 10.1. Tiêu chí chấp nhận cần bao phủ tình huống bất lợi

Với các nhóm yêu cầu thường gặp:

| Nhóm yêu cầu | Bằng chứng chấp nhận điển hình |
|---|---|
| Xác thực | Danh tính hợp lệ được xử lý đúng; token bị sửa, hết hạn hoặc không dành cho dịch vụ bị từ chối theo thiết kế. |
| Phân quyền | Chủ thể được phép có thể thực hiện hành động; truy cập chéo tenant, thiếu quyền hoặc đi đường thay thế bị chặn. |
| Bảo vệ dữ liệu | Các chặng truyền và bản lưu thuộc phạm vi có cấu hình đúng; thử truy cập trái phép không đọc được dữ liệu cần bảo vệ. |
| Logging | Sự kiện cần thiết được tạo và truy xuất được; không chứa bí mật; quyền đọc, sửa và xóa log được kiểm soát. |
| Phục hồi | Diễn tập khôi phục đạt trạng thái nghiệp vụ và mục tiêu đã thống nhất; bằng chứng thể hiện dữ liệu và thời gian thực tế. |

Các ví dụ trên phải được cụ thể hóa theo kiến trúc. Không lấy một ca kiểm thử thành công để kết luận tất cả đường truy cập đều đã được bảo vệ.

### 10.2. Điều kiện hoàn thành của yêu cầu

Nhóm cần thống nhất ít nhất:

- Đặc tả và tiêu chí chấp nhận đủ rõ.
- Triển khai bao phủ phạm vi đã cam kết.
- Kiểm thử và rà soát liên quan đạt.
- Bằng chứng gắn với phiên bản và môi trường phù hợp.
- Phần thiếu hoặc giới hạn còn lại có quyết định xử lý rõ ràng.

Nếu công việc chỉ hoàn thành khảo sát hoặc tạo cấu hình thử nghiệm, ghi đúng kết quả đó. Không đóng yêu cầu bảo vệ chỉ vì một công việc con đã xong.

## 11. Ghi nhận trì hoãn và chấp nhận rủi ro

Ưu tiên không thể loại bỏ sự đánh đổi. Nó cần làm cho đánh đổi trở nên minh bạch và có người chịu trách nhiệm.

### 11.1. Phân biệt ba cách xử lý

| Cách xử lý | Ý nghĩa | Điều kiện cần ghi |
|---|---|---|
| Lập kế hoạch ở mốc sau | Yêu cầu chưa cần đạt ở mốc hiện tại theo phạm vi và rủi ro đã đánh giá | Rủi ro hiện tại, kiểm soát hiện hữu, mốc và sự kiện xem xét lại. |
| Loại chức năng khỏi phạm vi | Chưa cho phép luồng tạo rủi ro hoạt động | Bằng chứng giới hạn phạm vi và điều kiện phải đạt trước khi mở lại. |
| Ngoại lệ có thời hạn | Vẫn hoạt động trong khi yêu cầu đang áp dụng chưa được đáp ứng đầy đủ | Căn cứ cho phép ngoại lệ, rủi ro còn lại, biện pháp tạm, thẩm quyền và hạn kết thúc. |

Ba cách này không thay thế cho nhau. Đặc biệt, yêu cầu đang áp dụng nhưng bị thiếu không thể được đổi thành “không áp dụng” chỉ vì chưa có năng lực triển khai.

### 11.2. Mẫu nhật ký quyết định

```text
Quyết định: DEC-PRIO-07
Phạm vi: Bản phát hành đầu của dịch vụ hồ sơ
Yêu cầu: REQ-02
Xử lý: Chưa mở chức năng xuất dữ liệu
Lý do: Năng lực hiện tại không đủ để đạt và xác minh toàn bộ phạm vi
Rủi ro được tránh: Worker hoặc đường tải tệp bỏ qua kiểm tra quyền
Điều kiện: API tạo tác vụ, worker và đường tải không được cung cấp
Bằng chứng: Kết quả kiểm tra giới hạn phạm vi trên bản phát hành
Chủ yêu cầu: Nhóm dịch vụ hồ sơ
Người phê duyệt phạm vi: Vai trò có thẩm quyền theo quy trình nội bộ
Xem xét lại: Tại lần lập kế hoạch kế tiếp và trước mọi lần mở chức năng
```

Với một ngoại lệ, cần thêm ngày hết hạn cụ thể, phương án xử lý khi hết hạn, biện pháp giảm rủi ro tạm thời và người chấp nhận rủi ro. Không tự động gia hạn vì công việc chưa xong.

Nếu không có thẩm quyền hoặc căn cứ cho phép ngoại lệ, nhóm phải chọn phương án khác như ngừng luồng bị ảnh hưởng, giảm phạm vi hoặc hoãn phát hành.

## 12. Vai trò và cách giải quyết bất đồng

Ưu tiên yêu cầu bảo mật là quyết định chung có trách nhiệm rõ ràng:

| Vai trò | Đóng góp chính |
|---|---|
| Chủ sản phẩm hoặc đại diện nghiệp vụ | Làm rõ giá trị, phạm vi, tác động kinh doanh và khả năng thay đổi mốc. |
| Nhóm bảo mật | Phân tích kịch bản đe dọa, hiệu quả kiểm soát và rủi ro còn lại. |
| Kiến trúc và phát triển | Xác định điểm thực thi, phụ thuộc, phương án thiết kế và công sức. |
| Kiểm thử | Làm rõ khả năng kiểm chứng, phạm vi kiểm tra và bằng chứng cần có. |
| Vận hành | Cung cấp hiện trạng, khả năng giám sát, phục hồi và các giới hạn thực tế. |
| Người có thẩm quyền quyết định rủi ro | Chấp thuận hoặc từ chối phần rủi ro còn lại trong phạm vi được giao. |

Nhóm bảo mật không nên tự quyết định mọi đánh đổi nghiệp vụ. Nhóm sản phẩm cũng không thể bỏ qua điều kiện bảo vệ chỉ bằng một thứ tự backlog mới.

Khi bất đồng, cần quay lại cùng một hồ sơ:

1. Hai bên có đang xét cùng phạm vi và cùng thời điểm không?
2. Kịch bản rủi ro có bằng chứng gì, giả định nào chưa được xác minh?
3. Kiểm soát hiện hữu thực sự bao phủ phần nào?
4. Có phương án giảm phạm vi hoặc thay thiết kế đáp ứng mục tiêu không?
5. Ai có thẩm quyền quyết định nếu vẫn còn rủi ro chưa được xử lý?

Nếu bất đồng do thiếu dữ kiện, ưu tiên thu thập đúng dữ kiện. Nếu bất đồng là về mức rủi ro được chấp nhận, chuyển tới đúng cấp có thẩm quyền thay vì điều chỉnh điểm số để che khuất khác biệt.

## 13. Khi nào phải đánh giá lại ưu tiên?

Danh sách ưu tiên cần được xem lại theo lịch lập kế hoạch và khi có sự kiện quan trọng:

- Xuất hiện bằng chứng khai thác hoặc sự cố liên quan.
- API nội bộ được mở ra bên ngoài.
- Chức năng bắt đầu xử lý dữ liệu nhạy cảm hơn hoặc nhiều tenant hơn.
- Tài khoản hay thành phần được cấp đặc quyền mới.
- Kiểm soát dùng chung thay đổi hoặc không còn bảo đảm phạm vi đã cam kết.
- Kiểm thử cho thấy cơ chế bảo vệ không có hiệu lực.
- Phụ thuộc hoàn thành sớm, bị trễ hoặc thay đổi thiết kế.
- Nguồn nghĩa vụ, thời hạn hoặc cách diễn giải được cập nhật bởi người phụ trách.
- Ngoại lệ sắp hết hạn hoặc biện pháp tạm thời không còn hiệu quả.

Mỗi lần đổi ưu tiên nên lưu lý do và giả định mới. Không cần ghi nhật ký dài cho mọi thay đổi nhỏ, nhưng phải giải thích được vì sao một yêu cầu quan trọng bị chuyển mốc.

Ví dụ, REQ-06 về cảnh báo đăng nhập thất bại có thể được đưa lên làm sớm nếu hệ thống bắt đầu chịu tấn công tự động và thiếu khả năng phát hiện phù hợp. Cần đánh giá lại toàn bộ kế hoạch liên quan, không chỉ thêm một nhãn “khẩn cấp” rồi giữ nguyên mọi cam kết cũ.

## 14. Theo dõi hiệu quả ưu tiên

Không đánh giá chất lượng ưu tiên chỉ bằng số lượng yêu cầu đã đóng. Mười yêu cầu nhỏ đã hoàn thành có thể không xử lý được một đường truy cập chéo tenant.

Các chỉ dấu hữu ích gồm:

- Yêu cầu gắn với rủi ro cao còn chưa đạt và khoảng thời gian tồn đọng.
- Điều kiện phát hành chưa có bằng chứng xác minh phù hợp.
- Số lần phải sửa lại kế hoạch vì phụ thuộc bị bỏ sót.
- Yêu cầu triển khai xong nhưng đang chờ xác minh.
- Ngoại lệ sắp hết hạn, hết hạn hoặc phải gia hạn nhiều lần.
- Yêu cầu bị hoãn nhiều kỳ mà không có đánh giá lại.
- Đường truy cập hoặc thành phần mới chưa được gắn với yêu cầu bảo vệ.

Đọc các chỉ dấu cùng phạm vi, phiên bản và mức độ rủi ro. Không suy ra phần trăm an toàn từ tỷ lệ yêu cầu đã hoàn thành.

Cũng cần xem lại cách ước lượng: nhóm có thường bỏ sót kiểm thử, tích hợp hoặc thời gian chờ hay không. Mục đích là làm quyết định sau thực tế hơn, không phải tạo động lực để viết yêu cầu nhỏ nhằm tăng số mục được đóng.

## 15. Lỗi thường gặp và cách điều chỉnh

| Lỗi | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Mọi yêu cầu đều có ưu tiên cao nhất | Không phân biệt được thứ tự và điều kiện phải đạt | Chốt phạm vi, mốc, kịch bản và tiêu chí ưu tiên. |
| Dùng điểm số làm quyết định duy nhất | Ràng buộc quan trọng có thể bị các tiêu chí khác bù trừ | Xét điều kiện bắt buộc trước khi sắp điểm phần có thể lựa chọn. |
| Chỉ chọn việc dễ làm | Thay đổi nền tảng hoặc rủi ro lớn bị trì hoãn liên tục | Theo dõi phụ thuộc, tuổi thiếu hụt và mức giảm rủi ro thực tế. |
| Chỉ dùng mức nghiêm trọng kỹ thuật | Bỏ qua mức phơi lộ, dữ liệu, kiểm soát hiện hữu và thời điểm | Viết kịch bản theo bối cảnh hệ thống. |
| Ước lượng chỉ phần code | Kế hoạch không có đủ thời gian xác minh | Tính cả tích hợp, kiểm thử bất lợi và bằng chứng. |
| Hoãn mà không có chủ sở hữu | Thiếu hụt trở thành tồn đọng vô thời hạn | Ghi quyết định, người chịu trách nhiệm và mốc đánh giá lại. |
| Hạ ưu tiên để kịp ngày phát hành | Rủi ro không giảm nhưng bị che trong báo cáo | Đổi phạm vi, năng lực, mốc hoặc xử lý ngoại lệ đúng thẩm quyền. |
| Đóng yêu cầu ngay khi merge | Chưa biết cơ chế có hiệu lực trên môi trường đích | Chỉ xác nhận đạt khi có bằng chứng phù hợp. |
| Giữ nguyên ưu tiên sau thay đổi lớn | Quyết định dựa trên giả định đã hết đúng | Dùng sự kiện kích hoạt đánh giá lại. |

## 16. Bài tập thực hành

Bạn có 6 ngày công cho một kỳ phát triển. Hệ thống đang hoạt động có API nhiều tenant, giao diện quản trị và sao lưu tự động.

Backlog gồm:

| Mục | Thông tin hiện có | Công sức tạm tính |
|---|---|---|
| A | Có báo cáo tái hiện được việc đọc hồ sơ tenant khác qua một endpoint | 3 ngày công |
| B | Muốn thêm màn hình tổng hợp audit; hiện vẫn truy vấn được sự kiện cần thiết | 2 ngày công |
| C | Chưa biết bản sao lưu có khôi phục đủ dữ liệu và cấu hình hay không | Khảo sát và diễn tập 1 ngày công, chưa biết công sức sửa |
| D | Muốn tự động hóa rà soát quyền; quy trình thủ công hiện tại có bằng chứng đáp ứng | 3 ngày công |
| E | Đường quản trị dự phòng mới được phát hiện chưa đi qua cơ chế MFA đã yêu cầu | 2 ngày công |

Hãy thực hiện:

1. Viết kịch bản rủi ro cho A, C và E; xác định phần nào là thông tin chắc chắn, phần nào là giả định.
2. Nêu hành động ngăn chặn hoặc giới hạn truy cập cần xem xét trước khi chờ sửa hoàn chỉnh.
3. Phân biệt ưu tiên khắc phục với thứ tự thực hiện và các phụ thuộc cần xác minh.
4. Lập kế hoạch trong 6 ngày công, nêu rõ công sức nào đã gồm kiểm thử và phần dự phòng còn thiếu.
5. Ghi quyết định cho các mục chưa được chọn, cùng mốc và điều kiện đánh giá lại.
6. Giả sử diễn tập ở C thất bại: cập nhật kế hoạch và xác định người cần tham gia quyết định.

### Gợi ý tự đánh giá

- A có bằng chứng truy cập trái phép trên hệ thống đang hoạt động, nên cần xem xét hành động ngăn chặn và xử lý theo quy trình sự cố phù hợp, không chỉ đưa vào lịch phát triển thông thường.
- E cần kiểm tra phạm vi, mức phơi lộ và khả năng tạm khóa đường dự phòng. Việc có đường quản trị chính dùng MFA không chứng minh đường dự phòng được bảo vệ.
- C là bất định quan trọng về khả năng phục hồi. Một ngày khảo sát không được tính là đã đáp ứng yêu cầu phục hồi; kết quả có thể tạo thêm công việc bắt buộc.
- B và D có thể được xem xét làm sau theo giả định hiện tại, nhưng cần lưu bằng chứng về cơ chế đang đáp ứng và sự kiện khiến phải đánh giá lại.
- Tổng 3 + 1 + 2 bằng 6 chỉ cho thấy đủ công sức tạm tính cho A, khảo sát C và E. Nó chưa bảo đảm đủ thời gian tích hợp, khắc phục phát sinh hoặc đạt mọi yêu cầu.
- Nếu năng lực không đủ cho mức rủi ro thực tế, cần giảm phạm vi hoạt động, bổ sung nguồn lực hoặc chuyển quyết định tới đúng người có thẩm quyền.

## 17. Câu hỏi tự kiểm tra

1. Vì sao một yêu cầu có rủi ro nghiêm trọng cao chưa đủ thông tin để quyết định chính xác thứ tự triển khai?
2. Mức ưu tiên khác trạng thái đáp ứng và điều kiện phát hành ở điểm nào?
3. Khi nào nên dùng điểm số, khi nào phải xét ràng buộc trước?
4. Vì sao kiểm soát dự kiến trong roadmap chưa thể dùng để giảm đánh giá rủi ro hiện tại?
5. Cần điều kiện gì để loại một chức năng khỏi phạm vi thay cho việc hoàn thành yêu cầu ngay?
6. Khi nào một hoạt động khảo sát nên được làm sớm, và vì sao nó không thay thế yêu cầu bảo vệ?
7. Một yêu cầu phụ thuộc được làm trước có nhất thiết mang cùng mức rủi ro với yêu cầu phía sau không?
8. Hồ sơ hoãn yêu cầu và hồ sơ ngoại lệ cần phân biệt như thế nào?
9. Những thay đổi nào phải kích hoạt đánh giá lại ưu tiên?
10. Bằng chứng nào cần có trước khi kết luận một yêu cầu được ưu tiên đã đạt?


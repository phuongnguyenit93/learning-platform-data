# Nhận diện rủi ro chưa được một tầng nào chịu trách nhiệm

Một rủi ro chất lượng có thể bị bỏ sót dù nhóm có nhiều kiểm thử và nhiều tầng kiểm thử. Điều này thường xảy ra khi mọi người cho rằng một nhóm hoặc một tầng khác đang kiểm tra vấn đề đó, trong khi không ai thực sự thiết kế phép kiểm chứng, duy trì dữ liệu, theo dõi kết quả và xử lý khi kiểm thử thất bại.

Rủi ro chưa được một tầng nào chịu trách nhiệm là rủi ro chưa có cách kiểm chứng rõ ràng và chưa có người hoặc nhóm chịu trách nhiệm bảo đảm việc kiểm chứng đó tồn tại, được thực hiện và còn đáng tin cậy. Đây là một khoảng trống trong phân bổ kiểm thử. Khoảng trống có thể nằm giữa các thành phần, giữa các tầng kiểm thử, giữa trách nhiệm của các nhóm hoặc giữa hoạt động trước phát hành và vận hành sau triển khai.

Mục tiêu của việc nhận diện không phải là buộc mọi rủi ro phải có kiểm thử ở tất cả các tầng. Mục tiêu là bảo đảm mỗi rủi ro quan trọng có một cách kiểm chứng phù hợp, có chủ sở hữu rõ ràng và có bằng chứng đủ để hỗ trợ quyết định chất lượng. Một tầng có thể chịu trách nhiệm chính, các tầng khác cung cấp bằng chứng bổ trợ. Với rủi ro xuyên suốt nhiều thành phần, trách nhiệm có thể được chia theo từng phần nhưng vẫn cần một đầu mối điều phối.

## 1. Hiểu thế nào là rủi ro không có chủ sở hữu kiểm thử?

Một rủi ro được xem là chưa được phân bổ đầy đủ khi nhóm không thể trả lời rõ những câu hỏi sau:

- Rủi ro cụ thể là gì và hậu quả nếu xảy ra?
- Phép kiểm chứng nào có thể phát hiện hoặc giảm rủi ro?
- Tầng kiểm thử nào là nơi phù hợp nhất để thực hiện phép kiểm chứng chính?
- Ai chịu trách nhiệm thiết kế, duy trì và thực hiện kiểm thử?
- Kết quả được lưu ở đâu và ai theo dõi khi kiểm thử thất bại?
- Nếu rủi ro không thể kiểm tra tự động hoặc trước phát hành, biện pháp kiểm soát thay thế là gì?
- Ai có quyền chấp nhận rủi ro còn lại và khi nào cần xem xét lại?

Không có câu trả lời rõ ràng không nhất thiết có nghĩa là hệ thống chắc chắn có lỗi. Nó có nghĩa là nhóm chưa có đủ bằng chứng để khẳng định rủi ro đang được kiểm soát.

### Phân biệt ba tình trạng thường bị nhầm lẫn

**Có kiểm thử nhưng không có chủ sở hữu.** Một kịch bản từng được tạo ra hoặc chạy thủ công, nhưng không ai chịu trách nhiệm cập nhật khi yêu cầu thay đổi, chuẩn bị dữ liệu hoặc xử lý khi kết quả thất bại.

**Có chủ sở hữu nhưng không có phép kiểm chứng phù hợp.** Một nhóm được giao phụ trách chức năng, nhưng chưa xác định được cách kiểm tra rủi ro. Ví dụ, nhóm sở hữu dịch vụ thanh toán nhưng chưa có cách xác minh thông điệp lặp hoặc đến sai thứ tự.

**Có kiểm thử ở một tầng nhưng rủi ro nằm ở ranh giới khác.** Kiểm thử đơn vị xác nhận logic tính tiền, nhưng không kiểm tra số tiền thực sự được gửi sang cổng thanh toán. Mỗi thành phần có thể đúng riêng lẻ trong khi hợp đồng giữa chúng không tương thích.

Những tình trạng này cần cách xử lý khác nhau. Thiếu người sở hữu cần phân công trách nhiệm; thiếu phép kiểm chứng cần thiết kế kiểm thử hoặc biện pháp kiểm soát; thiếu kiểm tra ở ranh giới cần chọn tầng phù hợp và xác định rõ thành phần tham gia.

## 2. Vì sao rủi ro thường bị bỏ trống giữa các tầng?

Các tầng kiểm thử được xây dựng để kiểm tra những phạm vi khác nhau. Nếu chỉ nhìn vào tên tầng hoặc số lượng kiểm thử, nhóm có thể tưởng rằng toàn bộ sản phẩm đã được bao phủ.

Ví dụ, một nhóm có nhiều kiểm thử đơn vị, một số kiểm thử tích hợp và một bộ kiểm thử đầu cuối. Tuy nhiên, vẫn có thể chưa ai kiểm tra:

- Quyền truy cập khi một người dùng thay đổi mã định danh tài nguyên trong API.
- Thông điệp sự kiện được gửi lặp sau khi dịch vụ nhận đã xử lý thành công.
- Dữ liệu cũ được chuyển đổi đúng khi triển khai phiên bản mới.
- Một giao dịch được hoàn tất ở dịch vụ này nhưng thất bại ở dịch vụ khác.
- Hệ thống phục hồi sau khi mất kết nối giữa thời điểm ghi dữ liệu và thời điểm nhận phản hồi.
- Cấu hình môi trường sản xuất khác với cấu hình đã kiểm tra.

Một số nguyên nhân phổ biến gồm:

### Ranh giới trách nhiệm không rõ

Nhóm phát triển một dịch vụ nghĩ rằng nhóm tích hợp sẽ kiểm tra giao tiếp. Nhóm tích hợp lại cho rằng mỗi nhóm dịch vụ đã kiểm tra hợp đồng của mình. Kết quả là không bên nào xác minh hành vi thực tế giữa hai dịch vụ.

### Tối ưu từng tầng nhưng không xem toàn bộ rủi ro

Nhóm có thể tập trung tăng độ bao phủ mã nguồn hoặc số lượng kiểm thử đơn vị vì những chỉ số này dễ đo. Trong khi đó, rủi ro về dữ liệu, quyền truy cập, tính nhất quán hoặc phục hồi thường xuất hiện ở nhiều thành phần và khó quy về một chỉ số đơn lẻ.

### Giả định rằng kiểm thử đầu cuối bao phủ tất cả

Một kiểm thử đầu cuối thường xác minh một hành trình đại diện. Nó không nhất thiết kiểm tra mọi nhánh lỗi, trạng thái trung gian, tổ hợp quyền, thứ tự thông điệp hoặc điều kiện tải. Bộ kiểm thử đầu cuối cũng có thể không cung cấp đủ thông tin để khoanh vùng nguyên nhân.

### Thiếu thông tin về rủi ro

Nếu yêu cầu chỉ mô tả hành vi thành công, nhóm có thể không nhận diện được các hậu quả khi lỗi xảy ra. Không có mô tả rủi ro thì khó xác định tầng kiểm thử nào cần chịu trách nhiệm.

### Công việc kiểm thử bị tách khỏi công việc phát triển

Kiểm thử có thể được giao cho một giai đoạn hoặc một nhóm riêng sau khi tính năng hoàn tất. Khi đó, các ranh giới kỹ thuật và quyết định thiết kế đã hình thành nhưng chưa có người chịu trách nhiệm kiểm chứng chúng.

### Kiểm thử tồn tại nhưng đã mất giá trị

Một kiểm thử có thể bị bỏ qua, bị tắt, không còn chạy trong pipeline, dùng dữ liệu lỗi thời hoặc không có assertion đủ mạnh. Danh sách kiểm thử vẫn có tên nhưng rủi ro thực tế không được kiểm tra.

## 3. Nhìn các tầng kiểm thử như những vị trí kiểm chứng khác nhau

Mỗi tầng có khả năng phát hiện một số loại lỗi tốt hơn những tầng khác. Việc phân bổ cần căn cứ vào nơi có thể quan sát rủi ro rõ nhất, chi phí kiểm tra và khả năng tái tạo.

| Tầng kiểm thử | Phạm vi thường phù hợp | Ví dụ rủi ro có thể kiểm chứng |
|---|---|---|
| Đơn vị | Hàm, lớp hoặc quy tắc logic nhỏ | Tính sai phí, làm tròn sai, điều kiện phân quyền bị đảo |
| Thành phần | Một thành phần cùng các phụ thuộc được kiểm soát | Thành phần không xử lý đúng trạng thái lỗi hoặc dữ liệu bất thường |
| Hợp đồng | Giao tiếp giữa các thành phần hoặc dịch vụ | Tên trường, kiểu dữ liệu, quy tắc tương thích hoặc ý nghĩa mã trạng thái không khớp |
| Tích hợp | Nhiều thành phần thật phối hợp với nhau | Ghi dữ liệu không nhất quán, sự kiện bị mất, xử lý retry sai |
| Hệ thống hoặc đầu cuối | Hành vi của sản phẩm qua hành trình hoàn chỉnh | Người dùng không hoàn thành được quy trình hoặc trạng thái cuối không đúng |
| Chấp nhận | Nhu cầu người dùng và quy tắc nghiệp vụ | Quy trình không đáp ứng chính sách hoặc tiêu chí chấp nhận |
| Kiểm thử phi chức năng chuyên biệt | Thuộc tính như hiệu năng, bảo mật, phục hồi, khả năng tiếp cận | Hệ thống quá tải, truy cập trái phép, không phục hồi được hoặc không sử dụng được bằng bàn phím |

Bảng này là định hướng, không phải phân công cứng. Một rủi ro có thể cần bằng chứng ở nhiều tầng. Ví dụ, quyền truy cập cần được kiểm tra ở đơn vị hoặc thành phần để xác minh logic chính sách, ở API để xác minh kiểm soát thực tế và ở hành trình đầu cuối để bảo đảm trải nghiệm phù hợp.

### Chọn tầng chính và tầng bổ trợ

Với mỗi rủi ro, nên xác định:

- **Tầng chính:** nơi thực hiện phép kiểm chứng quan trọng nhất và có thể phát hiện lỗi với độ tin cậy, tốc độ và chi phí phù hợp.
- **Tầng bổ trợ:** nơi xác minh thêm các giả định, ranh giới hoặc tác động liên quan.
- **Biện pháp vận hành:** giám sát, cảnh báo, đối soát, quy trình xử lý hoặc khả năng quay lui khi không thể kiểm chứng đầy đủ trước phát hành.

Không nên cố gắng đưa mọi rủi ro lên tầng đầu cuối. Rủi ro về một quy tắc tính toán thường được kiểm tra nhanh và rõ ở tầng đơn vị. Ngược lại, rủi ro về phối hợp giữa dịch vụ thanh toán và dịch vụ đơn hàng cần kiểm thử tích hợp hoặc hợp đồng. Hành trình người dùng vẫn cần một số kiểm thử đầu cuối đại diện để xác nhận các thành phần phối hợp đúng trong bối cảnh thực tế.

## 4. Lập bản đồ rủi ro từ yêu cầu đến tầng kiểm thử

Để tìm rủi ro bị bỏ trống, hãy bắt đầu từ các mục tiêu chất lượng và hậu quả có thể xảy ra, sau đó liên kết từng rủi ro với phép kiểm chứng và tầng chịu trách nhiệm.

### Bước 1: Liệt kê mục tiêu và rủi ro

Thu thập các luồng nghiệp vụ quan trọng, yêu cầu chất lượng, thay đổi gần đây, sự cố đã biết và phụ thuộc kỹ thuật. Với mỗi mục, mô tả tình huống lỗi và hậu quả.

Tránh ghi rủi ro quá chung như “hệ thống có thể không ổn định”. Hãy viết thành tình huống có thể kiểm tra, chẳng hạn: “Khi dịch vụ thanh toán đã ghi nhận giao dịch nhưng phản hồi bị mất, dịch vụ đơn hàng có thể giữ trạng thái chờ thanh toán và người dùng gửi lại yêu cầu.”

### Bước 2: Xác định điều kiện làm rủi ro xuất hiện

Làm rõ điều kiện, dữ liệu, trạng thái, vai trò và thành phần liên quan. Điều này giúp chọn đúng tầng kiểm thử.

Ví dụ, rủi ro gửi sự kiện trùng chỉ xuất hiện khi hệ thống nhận lại cùng một thông điệp. Kiểm thử đơn vị có thể xác minh logic xử lý idempotency, nhưng kiểm thử tích hợp cần xác minh hành vi khi broker thực sự giao lại thông điệp.

### Bước 3: Tìm bằng chứng hiện có

Tìm các trường hợp kiểm thử, mã tự động hóa, hợp đồng, pipeline, báo cáo chạy, checklist thủ công và bằng chứng vận hành. Không chỉ kiểm tra tên hoặc số lượng test; cần xem assertion, dữ liệu, điều kiện chạy và kết quả có thực sự xác minh rủi ro hay không.

### Bước 4: Xác định tầng chính và tầng bổ trợ

Chọn tầng có thể quan sát điều kiện gây lỗi và kết quả sai một cách rõ ràng. Nếu cần nhiều tầng, mô tả vai trò của từng tầng để tránh trùng lặp hoặc bỏ sót.

### Bước 5: Gán người hoặc nhóm chịu trách nhiệm

Chỉ định chủ sở hữu cho việc thiết kế, duy trì, chạy và xử lý kết quả. Trách nhiệm có thể thuộc nhóm sở hữu dịch vụ, nhóm nền tảng, nhóm bảo mật, nhóm kiểm thử hoặc nhóm vận hành tùy theo kiến trúc và năng lực.

### Bước 6: Đánh giá khoảng trống và quyết định xử lý

Đánh dấu rủi ro đã có bằng chứng đầy đủ, mới có bằng chứng một phần, chưa có phép kiểm chứng, chưa có chủ sở hữu hoặc được chấp nhận có chủ đích. Mọi ngoại lệ cần có lý do, người chấp nhận và thời điểm xem xét lại.

## 5. Ma trận phát hiện rủi ro chưa được phân bổ

Ma trận giúp nhóm nhìn thấy rủi ro nào chưa có tầng kiểm thử hoặc người chịu trách nhiệm. Một cấu trúc hữu ích gồm các cột:

| Trường | Ý nghĩa |
|---|---|
| Mã rủi ro | Định danh để truy vết |
| Tình huống và hậu quả | Điều có thể sai và ảnh hưởng nếu xảy ra |
| Mức ưu tiên | Mức độ quan trọng dựa trên tác động và khả năng xảy ra |
| Tầng chính | Tầng chịu trách nhiệm kiểm chứng chính |
| Tầng bổ trợ | Các tầng cung cấp bằng chứng bổ sung |
| Phép kiểm chứng | Trường hợp, kịch bản hoặc cơ chế kiểm soát cụ thể |
| Chủ sở hữu | Nhóm hoặc vai trò chịu trách nhiệm |
| Bằng chứng | Vị trí lưu kết quả và cách xác minh |
| Trạng thái | Đã bao phủ, một phần, chưa phân bổ hoặc chấp nhận rủi ro |
| Hành động tiếp theo | Việc cần làm và thời điểm xem xét |

Ví dụ với luồng đặt hàng:

| Rủi ro | Tầng chính | Tầng bổ trợ | Chủ sở hữu minh họa | Trạng thái |
|---|---|---|---|---|
| Quy tắc tính tổng tiền làm tròn sai | Đơn vị | Tích hợp | Nhóm đơn hàng | Đã có kiểm thử quy tắc |
| Dịch vụ thanh toán và đơn hàng hiểu khác trạng thái giao dịch | Hợp đồng | Tích hợp, đầu cuối | Nhóm sở hữu hai dịch vụ phối hợp | Chưa có kiểm thử hợp đồng |
| Thông điệp thanh toán được giao lại tạo giao dịch trùng | Tích hợp | Đơn vị, hệ thống | Nhóm thanh toán và nhóm đơn hàng | Chưa rõ chủ sở hữu |
| Người dùng xem được đơn của tài khoản khác | API hoặc thành phần bảo mật | Đầu cuối | Nhóm sở hữu dịch vụ đơn hàng | Mới kiểm tra ở giao diện |
| Luồng đặt hàng không hoàn tất khi dịch vụ thông báo gián đoạn | Tích hợp | Hệ thống, vận hành | Nhóm đơn hàng và vận hành | Có kiểm thử nhưng thiếu giám sát sau triển khai |

Các hàng trong bảng là ví dụ về cách ghi nhận. Khi áp dụng thực tế, nhóm cần thay tên vai trò, trạng thái và tầng theo kiến trúc thật. Không nên kết luận “đã bao phủ” chỉ vì có một kiểm thử liên quan; phải xác minh rằng kiểm thử đó tạo được điều kiện rủi ro và kiểm tra đúng hậu quả.

### Cách nhận diện hàng bị bỏ trống

Một rủi ro có dấu hiệu chưa được phân bổ khi:

- Cột tầng chính không có giá trị hoặc chỉ ghi “tất cả các tầng”.
- Không có phép kiểm chứng cụ thể.
- Không có nhóm hoặc vai trò chịu trách nhiệm.
- Có người sở hữu nhưng không có bằng chứng thực thi.
- Có kiểm thử nhưng không biết nó chạy ở đâu hoặc ai xử lý khi thất bại.
- Chỉ có kiểm thử ở một tầng không thể tạo ra điều kiện lỗi.
- Rủi ro được đánh dấu đã bao phủ nhưng kiểm thử không có assertion liên quan.
- Rủi ro chỉ được kiểm tra thủ công nhưng không có lịch, người thực hiện hoặc hồ sơ kết quả.
- Biện pháp kiểm soát phụ thuộc vào một cá nhân hoặc môi trường không ổn định.

Một hàng có đủ trường cũng chưa chắc đã được kiểm soát. Cần kiểm tra chất lượng của mối liên kết giữa rủi ro, phép kiểm chứng, tầng, chủ sở hữu và bằng chứng.

## 6. Tìm khoảng trống tại các ranh giới giữa thành phần

Nhiều rủi ro khó phát hiện nhất không nằm bên trong một thành phần mà xuất hiện khi các thành phần phối hợp. Đây là nơi cần xem xét kỹ khi phân bổ trách nhiệm.

### Hợp đồng và giao tiếp dịch vụ

Hai dịch vụ có thể cùng vượt qua kiểm thử đơn vị nhưng vẫn không tương thích vì khác tên trường, kiểu dữ liệu, quy tắc bắt buộc hoặc ý nghĩa trạng thái. Rủi ro này cần chủ sở hữu cho hợp đồng và kiểm thử tại ranh giới giao tiếp.

### Giao dịch và tính nhất quán dữ liệu

Một quy trình có thể cập nhật thành công một cơ sở dữ liệu nhưng thất bại khi ghi sang hệ thống khác. Nhóm cần xác định ai kiểm tra trạng thái một phần, đối soát, retry, bù trừ và phục hồi.

### Thông điệp bất đồng bộ

Thông điệp có thể bị lặp, đến sai thứ tự, đến muộn hoặc không đến. Kiểm thử logic xử lý riêng lẻ chưa đủ nếu chưa có phép kiểm chứng ở tầng tích hợp với cơ chế truyền nhận thực tế hoặc mô phỏng có kiểm soát.

### Xác thực và phân quyền

Giao diện ẩn nút thao tác không chứng minh API từ chối truy cập trái phép. Cần có trách nhiệm rõ ràng cho chính sách quyền, kiểm tra tại điểm thực thi và xác minh các trường hợp truy cập chéo người dùng hoặc tổ chức.

### Cấu hình và triển khai

Mã nguồn có thể vượt qua kiểm thử nhưng hệ thống thất bại do biến môi trường, quyền dịch vụ, cấu hình mạng, thứ tự triển khai hoặc khác biệt phiên bản. Cần xác định ai kiểm tra cấu hình, migration, smoke test và khả năng quay lui.

### Hiệu năng và giới hạn tài nguyên

Một thành phần có thể đạt kiểm thử đơn vị nhưng toàn hệ thống chậm khi tải tăng do truy vấn, khóa, kết nối hoặc giao tiếp giữa dịch vụ. Cần có chủ sở hữu cho mô hình tải, ngưỡng chấp nhận và cách theo dõi sau triển khai.

## 7. Phân công trách nhiệm rõ ràng

Gán tên một tầng kiểm thử không đồng nghĩa đã có người chịu trách nhiệm. Một phép kiểm thử cần người hoặc nhóm chịu trách nhiệm trong suốt vòng đời của nó.

Có thể phân chia trách nhiệm như sau:

- **Nhóm sở hữu thành phần:** hiểu hành vi, xác định rủi ro bên trong thành phần, xây dựng kiểm thử đơn vị và thành phần, duy trì hợp đồng do mình cung cấp.
- **Nhóm tích hợp hoặc nhóm sở hữu luồng:** xác minh phối hợp giữa các dịch vụ, dữ liệu và trạng thái xuyên suốt.
- **Nhóm kiểm thử hoặc chất lượng:** hỗ trợ phân tích rủi ro, thiết kế phạm vi, đánh giá bằng chứng và phát hiện khoảng trống giữa các nhóm.
- **Nhóm nền tảng hoặc CI/CD:** duy trì môi trường, pipeline, dữ liệu và khả năng thực thi kiểm thử đáng tin cậy.
- **Nhóm bảo mật hoặc chuyên gia chất lượng:** hỗ trợ rủi ro chuyên biệt và phương pháp kiểm chứng phù hợp.
- **Nhóm vận hành:** duy trì giám sát, cảnh báo, đối soát và quy trình phản ứng sau triển khai.
- **Chủ sản phẩm hoặc người có thẩm quyền:** xác nhận mức độ chấp nhận được của rủi ro nghiệp vụ còn lại.

Một người hoặc nhóm có thể đảm nhận nhiều vai trò. Điều quan trọng là mỗi rủi ro quan trọng có một đầu mối chịu trách nhiệm cuối cùng về việc bảo đảm phép kiểm chứng được duy trì. Với rủi ro xuyên nhóm, cần chỉ định một nhóm điều phối và xác định phần việc của từng nhóm tham gia.

### Phân biệt người thực hiện và người chịu trách nhiệm

Người viết kiểm thử có thể khác người duy trì pipeline. Người chạy kiểm thử có thể khác người xử lý lỗi. Một nhóm có thể cung cấp môi trường nhưng không sở hữu quy tắc nghiệp vụ. Vì vậy, bản phân công nên làm rõ:

- Ai định nghĩa rủi ro và tiêu chí đạt?
- Ai thiết kế và viết kiểm thử?
- Ai duy trì dữ liệu, môi trường và công cụ?
- Ai bảo đảm kiểm thử chạy đúng thời điểm?
- Ai xem xét kết quả và xử lý khi thất bại?
- Ai chấp nhận rủi ro còn lại?

Nếu chỉ ghi một tên người cho tất cả các hoạt động mà không có sự thống nhất, trách nhiệm có thể vẫn mơ hồ. Cần xác nhận sự phân công với những nhóm liên quan.

## 8. Phân bổ kiểm thử mà không tạo trùng lặp hoặc khoảng trống mới

Mục tiêu là có bằng chứng phù hợp ở đúng tầng, không phải nhân bản mọi trường hợp ở mọi nơi.

### Kiểm tra quy tắc ở tầng thấp, kiểm tra ranh giới ở tầng phù hợp

Một quy tắc tính thuế có thể có nhiều kiểm thử đơn vị cho giá trị biên. Hợp đồng giữa dịch vụ đơn hàng và dịch vụ thuế xác minh cách trao đổi dữ liệu. Một số kiểm thử tích hợp xác minh kết quả được ghi nhận đúng. Một hành trình đầu cuối xác nhận người dùng nhìn thấy tổng tiền phù hợp.

Mỗi tầng trả lời một câu hỏi khác nhau. Khi các tầng cùng kiểm tra một rủi ro, hãy nêu rõ bằng chứng bổ sung mà mỗi tầng cung cấp.

### Tránh dùng kiểm thử đầu cuối để thay mọi kiểm thử khác

Kiểm thử đầu cuối có giá trị xác nhận hành trình, nhưng thường chậm, phụ thuộc môi trường và khó cô lập nguyên nhân. Nếu một quy tắc có thể được kiểm tra đáng tin cậy ở tầng thấp hơn, hãy đặt phần kiểm tra chi tiết ở đó và giữ kiểm thử đầu cuối cho các hành trình đại diện.

### Tránh coi kiểm thử đơn vị là bằng chứng cho tích hợp

Kiểm thử đơn vị thường thay thế hoặc giả lập phụ thuộc. Nó có thể xác minh logic nhưng không chứng minh hai dịch vụ thật sự tương thích, cấu hình đúng hoặc dữ liệu được đồng bộ. Các rủi ro ở ranh giới cần bằng chứng ở hợp đồng hoặc tích hợp.

### Không nhân bản cùng một assertion mà không có lý do

Nếu nhiều tầng kiểm tra cùng một kết quả, hãy xác định mục đích riêng. Có thể tầng thấp kiểm tra nhiều trường hợp biên, còn tầng cao kiểm tra một hành trình đại diện. Nếu các kiểm thử không bổ sung bằng chứng, chúng chỉ làm tăng thời gian chạy và chi phí bảo trì.

## 9. Đánh giá mức độ bao phủ thực chất

Để biết rủi ro có thực sự được kiểm soát hay không, hãy đánh giá chất lượng bằng chứng thay vì chỉ đếm số lượng kiểm thử.

Một phép kiểm chứng có giá trị cần:

- Tạo được điều kiện liên quan đến rủi ro.
- Kiểm tra đúng hành vi hoặc bất biến cần bảo vệ.
- Có kết quả mong đợi rõ ràng.
- Chạy trong môi trường và dữ liệu phù hợp.
- Có thể tái hiện hoặc giải thích khi thất bại.
- Có người duy trì và xem xét kết quả.
- Được thực hiện ở thời điểm đủ sớm để hành động.

Có thể dùng các trạng thái sau trong ma trận:

| Trạng thái | Ý nghĩa |
|---|---|
| Đã phân bổ và có bằng chứng | Có tầng chính, chủ sở hữu, phép kiểm chứng và kết quả đáng tin cậy |
| Bao phủ một phần | Có kiểm thử nhưng chưa tạo đủ điều kiện rủi ro hoặc thiếu một phần bằng chứng |
| Chưa có phép kiểm chứng | Đã nhận diện rủi ro nhưng chưa có cách kiểm tra phù hợp |
| Chưa có chủ sở hữu | Có thể có ý tưởng hoặc kiểm thử nhưng chưa có người duy trì và theo dõi |
| Chấp nhận có chủ đích | Rủi ro được ghi nhận, có người có thẩm quyền chấp nhận và thời điểm xem xét lại |

Không nên dùng một tỷ lệ tổng thể để che khuất rủi ro nghiêm trọng. Nếu 95% rủi ro đã có kiểm thử nhưng 5% còn lại liên quan đến mất dữ liệu hoặc truy cập trái phép, nhóm vẫn cần xử lý hoặc ghi nhận quyết định chấp nhận rủi ro một cách minh bạch.

## 10. Ví dụ chi tiết: phát hiện rủi ro không ai sở hữu trong thanh toán

Giả sử ứng dụng thương mại điện tử gồm ba dịch vụ: đơn hàng, thanh toán và kho. Mỗi nhóm đều có kiểm thử đơn vị và pipeline riêng. Bộ kiểm thử đầu cuối xác nhận một đơn hàng có thể thanh toán thành công.

Trong một buổi rà soát, nhóm phát hiện tình huống sau:

1. Dịch vụ thanh toán gửi yêu cầu đến nhà cung cấp.
2. Nhà cung cấp đã trừ tiền và gửi thông báo thành công.
3. Dịch vụ đơn hàng cập nhật trạng thái thành đã thanh toán.
4. Broker giao lại cùng thông báo vì lần xác nhận xử lý trước đó bị timeout.
5. Dịch vụ nhận thông báo xử lý lại và có thể tạo thêm một bản ghi hoặc phát sự kiện tiếp theo.

Các nhóm có thể nghĩ rằng:

- Nhóm thanh toán chịu trách nhiệm giao dịch với nhà cung cấp.
- Nhóm đơn hàng chịu trách nhiệm trạng thái đơn.
- Nhóm nền tảng chịu trách nhiệm broker.
- Nhóm kiểm thử chịu trách nhiệm chạy kiểm thử đầu cuối.

Tuy nhiên, nếu không ai xác minh thông báo lặp được xử lý idempotent xuyên suốt, rủi ro vẫn chưa có chủ sở hữu.

### Phân bổ lại rủi ro

| Thành phần kiểm chứng | Tầng | Trách nhiệm | Bằng chứng |
|---|---|---|---|
| Hàm xử lý thông báo bỏ qua sự kiện đã xử lý | Đơn vị | Nhóm đơn hàng | Kiểm thử cùng mã sự kiện được xử lý nhiều lần |
| Hợp đồng thông báo và mã định danh giao dịch | Hợp đồng | Nhóm thanh toán và đơn hàng | Kiểm thử schema, trường định danh và tương thích |
| Broker giao lại thông điệp sau timeout | Tích hợp | Nhóm nền tảng cùng nhóm dịch vụ | Kiểm thử giao nhận lặp và xác nhận thông điệp |
| Trạng thái đơn và giao dịch không bị nhân đôi | Tích hợp | Nhóm đơn hàng và thanh toán phối hợp | Kiểm tra dữ liệu sau nhiều lần nhận cùng sự kiện |
| Hành trình người dùng chỉ ghi nhận một giao dịch | Đầu cuối | Nhóm sở hữu luồng mua hàng | Kiểm thử một số tình huống thanh toán đại diện |
| Cảnh báo khi số giao dịch và trạng thái đơn lệch nhau | Vận hành | Nhóm vận hành | Metric, cảnh báo và quy trình đối soát |

Trong ví dụ này, không một tầng đơn lẻ nào đủ để kiểm chứng mọi khía cạnh. Mỗi nhóm sở hữu một phần bằng chứng, còn nhóm điều phối luồng thanh toán bảo đảm các phần liên kết với nhau và có người theo dõi kết quả tổng thể.

## 11. Quy trình rà soát định kỳ các rủi ro bị bỏ trống

Khoảng trống có thể xuất hiện khi kiến trúc, nhóm hoặc sản phẩm thay đổi. Vì vậy, việc rà soát cần được thực hiện định kỳ và khi có sự kiện quan trọng.

Có thể dùng quy trình sau:

1. **Chọn phạm vi rà soát:** một hành trình nghiệp vụ, dịch vụ, bản phát hành hoặc thuộc tính chất lượng.
2. **Thu thập rủi ro:** xem yêu cầu, thay đổi, sự cố, lỗi lọt ra sản xuất và phụ thuộc.
3. **Lập bản đồ tầng:** xác định nơi đang có kiểm thử và nơi cần bằng chứng.
4. **Kiểm tra thực tế:** xem assertion, dữ liệu, pipeline, kết quả chạy và người xử lý.
5. **Tìm hàng mồ côi:** đánh dấu rủi ro thiếu tầng chính, phép kiểm chứng, chủ sở hữu hoặc bằng chứng.
6. **Ưu tiên khoảng trống:** dựa trên hậu quả, khả năng xảy ra, mức phơi nhiễm và chi phí xử lý.
7. **Giao hành động:** chỉ định người chịu trách nhiệm, kết quả mong đợi và thời hạn.
8. **Xác minh đóng khoảng trống:** chạy kiểm thử, xem bằng chứng và cập nhật ma trận.
9. **Xem xét lại:** rà soát sau phát hành, sự cố hoặc thay đổi kiến trúc.

Những thời điểm nên kích hoạt rà soát gồm:

- Thêm dịch vụ hoặc thay đổi ranh giới giữa các dịch vụ.
- Thay đổi schema, API, sự kiện hoặc quy trình dữ liệu.
- Thêm vai trò, quyền hoặc loại người dùng mới.
- Thay đổi cơ chế retry, timeout, cache hoặc xử lý đồng thời.
- Di chuyển dữ liệu hoặc nâng cấp nền tảng.
- Sự cố cho thấy kiểm thử hiện tại không phát hiện được vấn đề.
- Thay đổi người sở hữu hoặc cấu trúc nhóm.
- Tắt, bỏ qua hoặc di chuyển một bộ kiểm thử quan trọng.

## 12. Theo dõi việc đóng khoảng trống và rủi ro còn lại

Một khoảng trống chỉ nên được đánh dấu đã đóng khi có bằng chứng cho thấy phép kiểm chứng đã được triển khai, được thực hiện và có người chịu trách nhiệm duy trì.

Kết quả cần ghi nhận:

- Rủi ro ban đầu và mức ưu tiên.
- Tầng chính và tầng bổ trợ đã thống nhất.
- Kiểm thử hoặc biện pháp kiểm soát được bổ sung.
- Người hoặc nhóm chịu trách nhiệm.
- Vị trí lưu kết quả và lịch thực hiện.
- Kết quả chạy và giới hạn còn lại.
- Quyết định về rủi ro còn lại.
- Ngày hoặc điều kiện cần xem xét lại.

Một số rủi ro không thể được kiểm chứng hoàn toàn bằng kiểm thử trước phát hành. Ví dụ, khả năng phục hồi khi hạ tầng gặp sự cố hiếm có thể cần diễn tập, giám sát và phương án khôi phục. Trong trường hợp đó, cần ghi rõ kiểm thử nào đã thực hiện, biện pháp vận hành nào bổ sung và rủi ro nào vẫn còn.

Nếu rủi ro được chấp nhận, quyết định phải có người có thẩm quyền, lý do, giới hạn áp dụng và thời điểm xem xét lại. “Chưa có thời gian làm” không phải bằng chứng rằng rủi ro đã được kiểm soát.

## 13. Những sai lầm cần tránh

- **Cho rằng mỗi tầng đều đã kiểm tra phần của mình nên toàn hệ thống đã an toàn:** các lỗi tại ranh giới vẫn có thể bị bỏ sót.
- **Giao trách nhiệm chung chung cho nhóm kiểm thử:** nhóm sở hữu sản phẩm và thành phần cần tham gia chịu trách nhiệm về chất lượng.
- **Chỉ ghi tên tầng mà không mô tả phép kiểm chứng:** không thể biết rủi ro được kiểm tra như thế nào.
- **Dùng một bộ kiểm thử đầu cuối để đại diện cho mọi rủi ro:** một hành trình thành công không chứng minh mọi nhánh lỗi và thuộc tính chất lượng đều đạt.
- **Coi tên kiểm thử là bằng chứng:** cần xem dữ liệu, điều kiện, assertion và kết quả thực tế.
- **Không phân biệt tầng chính và tầng bổ trợ:** có thể tạo trùng lặp mà vẫn thiếu người điều phối.
- **Bỏ qua kiểm thử thủ công và vận hành:** những rủi ro không tự động hóa được vẫn cần lịch, bằng chứng và chủ sở hữu.
- **Đánh dấu khoảng trống đã đóng khi mới tạo test:** cần xác nhận test chạy được, phát hiện đúng vấn đề và được duy trì.
- **Không xem xét lại sau thay đổi:** phép kiểm chứng cũ có thể không còn bảo vệ rủi ro hiện tại.
- **Để rủi ro được chấp nhận vô thời hạn:** quyết định chấp nhận cần có thời hạn hoặc điều kiện xem xét lại.

## 14. Mẫu rà soát rủi ro chưa được phân bổ

Nhóm có thể dùng mẫu sau trong buổi rà soát chiến lược hoặc trước phát hành:

~~~text
RỦI RO:
Mô tả tình huống và hậu quả:

ĐIỀU KIỆN XUẤT HIỆN:
Dữ liệu, trạng thái, vai trò, thành phần và điều kiện môi trường:

TẦNG KIỂM THỬ CHÍNH:
Phép kiểm chứng:

TẦNG BỔ TRỢ:
Bằng chứng bổ sung:

CHỦ SỞ HỮU:
Nhóm chịu trách nhiệm cuối cùng:
Người/nhóm thực hiện:
Người xem xét kết quả:

BẰNG CHỨNG:
Vị trí lưu:
Thời điểm chạy:
Kết quả gần nhất:

TRẠNG THÁI:
Đã phân bổ / Bao phủ một phần / Chưa có phép kiểm chứng /
Chưa có chủ sở hữu / Chấp nhận có chủ đích

HÀNH ĐỘNG TIẾP THEO:
Người phụ trách:
Thời hạn:
Điều kiện xác nhận hoàn tất:
Ngày xem xét lại:
~~~

Mẫu này giúp buổi rà soát tập trung vào quyết định cụ thể. Với mỗi rủi ro quan trọng, nhóm cần rời buổi họp với một chủ sở hữu, một hành động hoặc một quyết định chấp nhận có căn cứ.

## Kết luận

Nhận diện rủi ro chưa được một tầng nào chịu trách nhiệm là việc kiểm tra mối liên kết giữa rủi ro, phép kiểm chứng, tầng kiểm thử, chủ sở hữu và bằng chứng. Khoảng trống thường xuất hiện ở ranh giới giữa dịch vụ, giữa các tầng hoặc giữa trách nhiệm của các nhóm. Chúng có thể tồn tại ngay cả khi sản phẩm đã có nhiều kiểm thử.

Khi lập bản đồ rủi ro, chọn tầng chính và tầng bổ trợ, phân công trách nhiệm rõ ràng và rà soát bằng chứng thực tế, nhóm có thể phát hiện những điểm chưa được bảo vệ trước khi chúng trở thành sự cố. Mỗi rủi ro quan trọng cần có cách kiểm chứng phù hợp hoặc một quyết định chấp nhận rủi ro được ghi nhận, có người chịu trách nhiệm và được xem xét lại khi bối cảnh thay đổi.

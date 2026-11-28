# Tách quyền quản trị và audit

## 1. Mục tiêu và bối cảnh

Trong chương **Least privilege**, tách quyền quản trị và audit là cách giới hạn khả năng một chủ thể vừa thực hiện thay đổi đặc quyền, vừa tự kiểm soát toàn bộ bằng chứng và việc đánh giá thay đổi đó.

Trong PAM, nguyên tắc này áp dụng cho tài khoản quản trị, tài khoản dịch vụ, vault, cổng truy cập, hệ thống đích và nơi lưu bằng chứng. Nếu cùng một chủ thể có thể tự cấp quyền, dùng quyền, xóa log rồi xác nhận không có vấn đề, sự tồn tại của nhật ký chưa tạo ra khả năng kiểm toán đáng tin cậy.

Sau bài học, bạn có thể:

- Phân biệt quyền vận hành, thu thập log, quản lý bằng chứng và thực hiện audit.
- Lập ma trận quyền theo nhiệm vụ thay vì chỉ tạo hai nhóm mang tên khác nhau.
- Nhận diện đường gián tiếp làm mất tính độc lập, gồm quản lý vai trò, hạ tầng, khóa mã hóa và chính sách lưu giữ.
- Kết hợp tách trách nhiệm với JIT/JEA, vault, luân chuyển credential và giám sát phiên.
- Thiết kế chuỗi bằng chứng đủ để đối chiếu một lần sử dụng đặc quyền từ yêu cầu đến thu hồi.

## 2. Hiểu đúng hai phía của việc tách quyền

### 2.1. Quyền quản trị bao gồm những gì?

**Quyền quản trị** là khả năng tạo hoặc thay đổi trạng thái của hệ thống trong phạm vi được giao. Ví dụ: thay cấu hình dịch vụ, cấp vai trò, sửa chính sách truy cập vault, quản lý credential hoặc thực hiện tác vụ vận hành nhạy cảm.

Quản trị cũng có thể tác động đến cơ chế quan sát: thay mức ghi log, dừng agent thu thập, đổi nơi gửi sự kiện hoặc sửa cấu hình cảnh báo. Những khả năng này cần được kiểm kê riêng vì ảnh hưởng đến chất lượng bằng chứng.

### 2.2. Audit không đồng nghĩa với mọi công việc liên quan đến log

**Audit** trong bài là hoạt động kiểm tra và đánh giá: quyền có được cấp đúng không, sử dụng có phù hợp mục đích không, thay đổi có được phê duyệt không và bằng chứng có đủ để đưa ra kết luận không.

Có ít nhất bốn nhóm công việc liên quan nhưng khác nhau:

| Nhóm công việc | Mục tiêu | Quyền điển hình cần xem xét |
| --- | --- | --- |
| Quản trị vận hành | Thực hiện thay đổi hoặc tác vụ được giao | Sửa cấu hình, dùng đặc quyền, quản lý tài nguyên |
| Thu thập và chuyển tiếp | Đưa sự kiện từ nguồn đến nơi nhận | Đọc nguồn được giao, gửi sự kiện, quản lý trạng thái gửi cần thiết |
| Quản lý kho bằng chứng | Duy trì nơi lưu, tính sẵn có và vòng đời dữ liệu | Cấu hình lưu trữ, bảo vệ dữ liệu, thực thi lưu giữ theo chính sách |
| Audit hoặc rà soát | Đối chiếu bằng chứng với yêu cầu kiểm soát | Đọc, truy vấn, lập báo cáo và ghi nhận phát hiện |

Người quản trị kho log không tự động là kiểm toán viên. Người xem log cũng không nên mặc nhiên được thay chính sách lưu giữ hoặc sửa bản ghi nguồn.

### 2.3. Tách quyền không có nghĩa cấm người vận hành đọc mọi log

Người vận hành có thể cần log chẩn đoán để khôi phục dịch vụ. Nhu cầu đó nên được giới hạn theo tài nguyên, loại dữ liệu và mục đích, thay vì buộc phải cấp quyền đọc toàn bộ bằng chứng của tổ chức.

Điểm cần bảo vệ là khả năng thay đổi hoặc loại bỏ bằng chứng và khả năng tự đưa ra xác nhận độc lập về chính hoạt động của mình. Cấp quyền đọc phục vụ xử lý sự cố không đồng nghĩa trao quyền audit hoặc quyền quản lý kho lưu trữ.

## 3. Least privilege và separation of duties hỗ trợ nhau

**Least privilege** yêu cầu chỉ cấp khả năng cần cho nhiệm vụ. **Separation of duties**, hay tách trách nhiệm, xem xét những khả năng nào không nên do cùng một chủ thể kiểm soát trọn vẹn trong một quy trình.

Ví dụ, người vận hành cần khởi động lại dịch vụ A. Nhiệm vụ này không tự kéo theo nhu cầu xóa bằng chứng, sửa thời hạn lưu giữ hay tự duyệt quyền quản trị cho chính mình.

### 3.1. Hai tài khoản chưa chắc tạo thành hai phía độc lập

Nếu một người có tài khoản quản trị và tài khoản audit, nhưng vẫn toàn quyền điều khiển cả hai, việc tách tài khoản có thể làm rõ ngữ cảnh sử dụng nhưng chưa tạo ra kiểm tra độc lập giữa hai người chịu trách nhiệm.

Tương tự, hai nhóm khác tên vẫn không độc lập nếu:

- Cùng một chủ thể có thể tùy ý thêm mình vào cả hai nhóm.
- Một nhóm có thể đặt lại phương thức xác thực hoặc sử dụng credential của nhóm kia.
- Một danh tính dịch vụ dùng chung nắm cả hai tập quyền.
- Quyền kế thừa hoặc quyền tại lớp hạ tầng cho phép vượt qua ranh giới đã vẽ.

Cần đánh giá theo người hoặc workload thực sự kiểm soát quyền, không chỉ theo số lượng tài khoản và tên nhóm.

### 3.2. Tách ở mức cấp quyền và ở mức giao dịch

Có thể giới hạn một chủ thể không đồng thời giữ những vai trò xung đột. Cũng có thể cho phép một người đủ điều kiện làm nhiều nhiệm vụ nhưng không được vừa yêu cầu vừa phê duyệt cùng một giao dịch.

Hai cách này giải quyết những vấn đề khác nhau. Việc không cho kích hoạt đồng thời hai vai trò chưa chắc đủ nếu chủ thể có thể thực hiện thao tác quản trị trước, rồi chuyển vai trò để sửa bằng chứng sau. Cần xem cả khả năng nối tiếp theo thời gian và phạm vi của từng quyền.

Không phải mọi hoạt động đều cần hai người. Mức độ tách phải phù hợp với tác động, quy mô tổ chức và khả năng kiểm soát thực tế. Những ngoại lệ cần có căn cứ, người chịu trách nhiệm và cơ chế rà soát phù hợp.

## 4. Các ranh giới cần bảo vệ trong một hệ thống PAM

### 4.1. Cấp quyền và sử dụng quyền

Người dùng đặc quyền không nên mặc nhiên được tự mở rộng vai trò, sửa điều kiện kích hoạt hoặc tự duyệt mọi yêu cầu của chính mình.

Nếu một quản trị viên IAM có khả năng thay thành viên nhóm audit, quyền đó phải được nhận diện như một khả năng ảnh hưởng đến tính độc lập. Chỉ giới hạn nhóm vận hành ở tài nguyên đích nhưng bỏ qua quyền quản lý thành viên nhóm sẽ để lại đường gián tiếp.

### 4.2. Hoạt động tại đích và bản sao bằng chứng

Một quản trị viên có thể cần quyền cao tại máy chủ, nhưng không nên vì thế tự động có quyền xóa bản sao log ở kho bằng chứng độc lập.

Tuy nhiên, nguồn phát vẫn có thể chịu tác động. Người có quyền cao trên máy chủ có thể thay cấu hình hoặc ngừng việc phát sự kiện tùy nền tảng. Bản sao từ xa giúp bảo vệ dữ liệu đã nhận; nó không tự bảo đảm mọi sự kiện đáng lẽ phát sinh đều được ghi đầy đủ.

Cần kết hợp nguồn đối chiếu, theo dõi tình trạng thu thập và kiểm soát thay đổi cấu hình. Khoảng trống log phải được đánh giá trong kết luận audit.

### 4.3. Quản lý kho bằng chứng và đánh giá nội dung

Người quản lý kho cần duy trì dịch vụ lưu trữ, nhưng không nhất thiết cần đọc mọi dữ liệu nhạy cảm hoặc tự thay thời hạn lưu giữ không qua kiểm soát.

Kiểm toán viên cần truy vấn và xuất phần bằng chứng được giao, nhưng không cần sửa bản ghi nguồn, thay cấu hình ingestion hoặc quản lý credential của người vận hành. Họ có thể ghi nhận phát hiện trong báo cáo hoặc hệ thống đánh giá riêng mà không thay nội dung gốc.

### 4.4. Kho bằng chứng và hạ tầng bên dưới

Phải xem cả quyền quản trị máy chủ lưu log, bản sao lưu, khóa mã hóa, tài khoản dịch vụ và chính sách truy cập của nơi lưu. Chặn nút xóa trong giao diện chưa đủ nếu cùng chủ thể có thể xóa dữ liệu qua lớp lưu trữ hoặc làm mất khả năng giải mã bằng cách xử lý khóa không phù hợp.

Mức độc lập đạt được phụ thuộc vào kiến trúc và nền tảng. Cần xác định những chủ thể quyền cao vẫn có khả năng tác động, thay vì khẳng định bằng chứng không thể bị sửa chỉ từ một tên vai trò.

## 5. Một ma trận quyền minh họa

Ma trận sau mô tả trách nhiệm mong muốn cho một môi trường giả định. Khi triển khai phải ánh xạ sang quyền thực tế và giới hạn của sản phẩm.

| Khả năng | Người vận hành | Người phê duyệt | Danh tính thu thập | Người quản lý kho | Người audit |
| --- | --- | --- | --- | --- | --- |
| Yêu cầu dùng đặc quyền | Theo nhiệm vụ | Không mặc nhiên cần | Không | Theo nhiệm vụ quản lý kho | Không mặc nhiên cần |
| Duyệt yêu cầu của người vận hành | Không tự duyệt cùng giao dịch | Trong phạm vi được giao | Không | Không mặc nhiên cần | Không mặc nhiên cần |
| Thực hiện thay đổi ở đích | Theo quyền đã kích hoạt | Không mặc nhiên cần | Không | Không, trừ đích thuộc nhiệm vụ quản lý kho riêng | Không |
| Đọc log chẩn đoán | Phạm vi cần thiết | Khi cần cho quyết định | Đọc nguồn được giao để chuyển tiếp | Theo nhu cầu vận hành có kiểm soát | Theo phạm vi audit |
| Gửi sự kiện vào kho | Qua cơ chế được xác thực | Không | Có, trong phạm vi nguồn | Không mặc nhiên thay danh tính nguồn | Không |
| Sửa hoặc xóa bản ghi bằng chứng đã nhận | Không | Không | Không | Chỉ theo cơ chế vòng đời đã phê duyệt và được nền tảng cho phép | Không |
| Thay chính sách lưu giữ | Không | Duyệt nếu được giao thẩm quyền | Không | Thực hiện thay đổi đã được kiểm soát | Chỉ đề xuất hoặc đánh giá |
| Thay quyền truy cập kho | Không | Duyệt trong thẩm quyền | Không | Thực hiện theo quy trình và phạm vi được giao | Không tự mở rộng quyền |
| Truy vấn, lập báo cáo audit | Không thay thế đánh giá độc lập | Khi cần cho nhiệm vụ | Không | Không mặc nhiên cần toàn bộ nội dung | Có, giới hạn theo phạm vi |
| Sửa báo cáo hoặc ghi chú đánh giá | Theo vai trò phản hồi riêng nếu được cấp | Theo nhiệm vụ | Không | Không mặc nhiên cần | Có, không làm thay đổi bản ghi nguồn |

Những ô “không mặc nhiên cần” nhấn mạnh rằng một nhiệm vụ không tự kéo theo nhiệm vụ khác. Nếu có nhu cầu kiêm nhiệm, phải cấp bổ sung có căn cứ và đánh giá xung đột.

Cũng cần phân biệt **xóa theo vòng đời đã được duyệt** với **xóa tùy ý để làm mất bằng chứng**. Chính sách lưu giữ phải có người chịu trách nhiệm, thời hạn phù hợp với nhu cầu và cơ chế kiểm soát thay đổi. Không cần giữ mọi dữ liệu mãi mãi để đạt mục tiêu tách quyền.

## 6. Thiết kế luồng bằng chứng từ nguồn đến người đánh giá

### 6.1. Liên kết nhiều lớp quan sát

Một lần dùng đặc quyền có thể tạo sự kiện ở nhiều nơi:

```text
Yêu cầu và phê duyệt
    -> PAM kích hoạt quyền hoặc mở phiên
    -> vault cấp hoặc sử dụng credential
    -> hệ thống đích thực hiện hành động
    -> các nguồn gửi sự kiện vào kho bằng chứng
    -> người audit đối chiếu nhu cầu, hành động và thu hồi
```

Mỗi nguồn trả lời một phần khác nhau. PAM biết ai xin quyền; vault biết credential nào được truy xuất; hệ thống đích biết hành động được xử lý thế nào. Một nguồn riêng lẻ có thể chưa đủ kết luận toàn bộ chuỗi.

### 6.2. Ràng buộc nguồn và chống gán nhầm

Danh tính gửi log nên được ràng buộc với những nguồn được phép. Nếu một tác vụ có thể tự khai tùy ý rằng mình là bất kỳ máy chủ nào, việc gắn nhãn nguồn có thể không đáng tin.

Cần có mã liên kết yêu cầu, phiên, lần cấp quyền hoặc lần chạy khi phù hợp. Dấu thời gian cần đủ nhất quán để đối chiếu, và các giới hạn về chênh lệch đồng hồ phải được hiểu rõ.

### 6.3. Theo dõi việc chuyển và nhận

“Đã gửi” chưa chắc tương đương “đã được lưu”. Hệ thống phải hiểu xác nhận của nơi nhận có nghĩa gì: đã nhận qua mạng, đã ghi vào bộ đệm hay đã lưu theo cam kết của kho.

Theo dõi hàng đợi, lỗi chuyển tiếp, tình trạng agent và khoảng gián đoạn giúp nhận diện dữ liệu có thể thiếu. Heartbeat cho thấy một thành phần vẫn liên lạc được, nhưng riêng nó không chứng minh mọi hành động đã được ghi đầy đủ.

Nếu mất log trong một khoảng thời gian, cần giữ sự kiện mất quan sát và đối chiếu nguồn khác. Không nên biến “không có dữ liệu” thành kết luận “không có hoạt động”.

## 7. Bảo vệ tính toàn vẹn, tính đầy đủ và tính sẵn có

Ba thuộc tính này cần được xem riêng:

| Thuộc tính | Câu hỏi | Ví dụ biện pháp cần đánh giá |
| --- | --- | --- |
| Toàn vẹn | Dữ liệu đã nhận có bị sửa hoặc thay thế không? | Quyền ghi hạn chế, cơ chế chỉ ghi thêm, bảo vệ thay đổi cấu hình |
| Đầy đủ | Những sự kiện cần có đã được ghi và chuyển đủ chưa? | Theo dõi thu thập, đối chiếu nguồn, quản lý khoảng trống |
| Sẵn có | Người được phép có đọc và phục hồi được bằng chứng khi cần không? | Dự phòng, kiểm tra khôi phục, bảo vệ khóa và quyền truy cập |

### 7.1. Không nhầm mã hóa với chống sửa

Mã hóa giúp bảo vệ dữ liệu khỏi việc đọc không được phép. Nó không tự ngăn người có quyền hợp lệ xóa dữ liệu hoặc thay chính sách lưu giữ.

Tương tự, hàm băm hoặc chữ ký có thể hỗ trợ phát hiện thay đổi hay xác minh nguồn theo thiết kế, nhưng không tự chứng minh mọi sự kiện đáng lẽ có đều đã được phát sinh. Một nguồn bị kiểm soát vẫn có thể không gửi một sự kiện.

### 7.2. Kiểm soát vòng đời của kho và khóa

Nếu nền tảng hỗ trợ khóa chính sách lưu giữ hoặc cơ chế ghi không sửa trong một khoảng thời gian, cần hiểu phạm vi bảo vệ và quyền ngoại lệ. Cũng cần kiểm soát ai có thể thay cấu hình, quản lý bản sao hoặc tác động đến khóa cần để đọc dữ liệu.

Bản sao lưu không tự thay thế tính toàn vẹn. Nếu cùng một chủ thể có thể xóa cả dữ liệu chính lẫn mọi bản sao, hoặc không ai kiểm tra việc khôi phục, khả năng lưu bằng chứng vẫn có điểm yếu.

### 7.3. Bảo vệ nội dung nhạy cảm

Người audit thường cần dữ liệu để đánh giá, nhưng không cần nhận mọi bí mật của hệ thống. Log, bản ghi phiên và kết quả lệnh có thể chứa thông tin cá nhân, dữ liệu nghiệp vụ hoặc credential nếu thu thập thiếu kiểm soát.

Cần giảm việc ghi bí mật từ nguồn, giới hạn nội dung được xem và quản lý việc xuất dữ liệu. Có thể cung cấp bản nhìn đã giới hạn theo phạm vi đánh giá, đồng thời giữ quan hệ rõ với bằng chứng được bảo quản. Không được làm mất ý nghĩa hoặc che giấu khoảng trống bằng cách chỉnh sửa dữ liệu rồi coi đó là bản ghi gốc đầy đủ.

## 8. Phối hợp với các cơ chế PAM khác

### 8.1. JIT cho quyền quản trị và quyền đọc bằng chứng

Quyền vận hành có thể được kích hoạt theo nhiệm vụ. Quyền đọc một tập bằng chứng nhạy cảm cũng có thể được cấp có thời hạn theo phạm vi audit.

Điểm khác nhau là quyền đọc bằng chứng không nên kéo theo quyền thay cấu hình thu thập hay xóa dữ liệu. Việc hết hạn cũng phải được xét theo cơ chế token, phiên và kết nối thực tế, không chỉ theo trạng thái trên cổng.

### 8.2. JEA giới hạn thao tác

Một người chỉ cần khởi động lại dịch vụ không nên mặc nhiên có shell quản trị tùy ý nếu nền tảng có thể ủy quyền chức năng hẹp hơn. Giới hạn thao tác cũng giúp giảm khả năng người vận hành thay cơ chế ghi log tại nguồn.

Tuy nhiên, nếu vẫn cần quyền quản trị toàn máy, phải thừa nhận khả năng tác động tại nguồn và bổ sung lớp đối chiếu phù hợp. Không thể dùng một sơ đồ JEA để che đi quyền rộng còn tồn tại qua đường khác.

### 8.3. Vault và credential

Credential của người vận hành, agent thu thập và người quản lý kho cần được quản lý riêng theo nhiệm vụ. Không dùng chung một bí mật cho các vai trò cần độc lập.

Quyền đọc bằng chứng không nên mặc nhiên cho phép lấy credential để đăng nhập hệ thống đích. Người quản trị vault cũng không nên tự động nhận quyền đọc mọi bí mật nếu nhu cầu chỉ là quản lý chính sách và sản phẩm có khả năng tách.

Luân chuyển credential cần được phối hợp để không làm ngừng chuyển log ngoài dự kiến. Lỗi cập nhật giữa kho credential và đích phải được phát hiện, có người xử lý và có bằng chứng về khoảng gián đoạn nếu xảy ra.

### 8.4. Giám sát phiên và API

Bản ghi phiên giúp hiểu hoạt động tương tác, nhưng một số thay đổi đi qua API, pipeline hoặc tác vụ nền. Cần kết hợp dữ liệu phiên với log hành động, danh tính workload và kết quả tại đích.

Nếu người vận hành có thể xóa bản ghi phiên ở cùng nơi họ quản lý, cần xem xét lại ranh giới bảo quản. Việc bật ghi hình riêng lẻ chưa tạo ra tính độc lập.

## 9. Ví dụ xuyên suốt: khởi động lại dịch vụ qua PAM

### 9.1. Thiết kế ban đầu

Một tài khoản dùng chung có thể mở phiên quản trị máy chủ, quản lý PAM và xóa log trong kho trung tâm. Nhóm kiểm tra dùng chính credential đó để lấy báo cáo. Mỗi lần thay đổi chỉ được ghi nhận là do tài khoản dùng chung thực hiện.

Ba vấn đề xuất hiện cùng lúc: khó xác định cá nhân, người thực hiện có thể tác động đến bằng chứng và người đánh giá dùng cùng quyền với người được đánh giá.

### 9.2. Thiết kế sau khi phân tách

Nhiệm vụ hợp lệ là khởi động lại dịch vụ A. Một phương án phân tách gồm:

1. Kỹ sư yêu cầu bằng danh tính cá nhân, gắn với mã sự cố.
2. Người hoặc chính sách có thẩm quyền cho phép đúng chức năng trên dịch vụ A.
3. PAM mở quyền sử dụng có thời hạn; cơ chế thực thi chỉ chấp nhận thao tác được giao.
4. Danh tính tác vụ và hệ thống đích ghi hành động, kết quả cùng mã liên kết.
5. Dữ liệu được chuyển sang kho mà kỹ sư không có quyền xóa hoặc thay chính sách lưu giữ.
6. Người audit dùng quyền đọc riêng để đối chiếu quyết định, hành động và kết quả thu hồi.
7. Người quản lý kho thực hiện nhiệm vụ lưu trữ bằng quyền riêng, có kiểm soát thay đổi cấu hình.

Các nhóm quyền ở đây phục vụ những việc khác nhau. Người phê duyệt không tự động được sửa máy chủ; người audit không được đọc giá trị credential trong vault; danh tính tác vụ không được quản lý kho bằng chứng.

### 9.3. Ràng buộc chính sách ở mức khái niệm

Mã giả dưới đây minh họa các ranh giới, không phải cấu hình chạy trực tiếp:

```text
Người vận hành:
  được yêu_cầu và thực_hiện chức_năng trong phạm_vi đã_duyệt
  được đọc log_chẩn_đoán cần_thiết cho nhiệm_vụ
  không được tự_duyệt cùng yêu_cầu
  không được sửa hoặc xóa bằng_chứng đã_bảo_quản

Danh tính thu thập:
  được đọc nguồn được_giao và gửi sự_kiện theo nguồn đã_xác_thực
  không được sửa hoặc xóa sự_kiện đã_nhận tại kho
  không được tự_mở_rộng nguồn hoặc quyền_truy_cập

Người quản lý kho:
  được vận_hành nơi_lưu theo phạm_vi được_giao
  thay_đổi quyền và lưu_giữ theo quy_trình có_kiểm_soát
  không mặc_nhiên được thực_hiện tác_vụ trên hệ_thống_đích

Người audit:
  được truy_vấn và xuất phần_bằng_chứng thuộc phạm_vi
  được ghi nhận_xét trong hồ_sơ_đánh_giá riêng
  không được thay bản_ghi_nguồn, chính_sách_lưu_giữ hoặc credential_đích
```

Chính sách mong muốn phải được kiểm tra qua quyền hiệu lực và các đường truy cập thực tế. Nếu cùng một người có thể sửa thành viên tất cả nhóm trên, ranh giới vẫn chưa có mức độc lập như dự kiến.

### 9.4. Nếu log tại đích bị gián đoạn

Giả sử PAM ghi có một phiên mở thành công nhưng log hành động tại đích thiếu trong một khoảng thời gian. Người audit cần ghi nhận thiếu bằng chứng và đối chiếu nguồn khác như dữ liệu phiên hoặc log dịch vụ phù hợp.

Không nên kết luận tác vụ đã đúng chỉ vì có phê duyệt, cũng không nên kết luận có hành vi sai chỉ từ khoảng trống. Cần đánh giá những gì quan sát được, những gì chưa xác minh và nguyên nhân của gián đoạn.

## 10. Triển khai phân tách trong môi trường đang dùng chung quyền

### 10.1. Kiểm kê quyền và đường truy cập

Lập danh sách người, workload và credential có thể quản trị đích, thay cấu hình thu thập, truy cập kho hoặc quản lý thành viên nhóm. Bao gồm quyền trực tiếp, kế thừa, khả năng đặt lại xác thực và quyền tại lớp hạ tầng.

Đừng chỉ kiểm tra giao diện sử dụng hằng ngày. API, tác vụ tự động, tài khoản dự phòng và cơ chế phục hồi có thể mang cùng quyền rộng.

### 10.2. Xác định nhiệm vụ và ma trận mong muốn

Chủ sở hữu hệ thống, kho bằng chứng và hoạt động đánh giá cần xác nhận nhu cầu. Xác định nhóm nào cần thực hiện, nhóm nào cần xem, nhóm nào được thay chính sách và điểm nào cần phê duyệt độc lập.

Nếu công cụ không tách được một tập quyền, ghi nhận giới hạn thực tế và chọn kiểm soát bổ sung phù hợp, chẳng hạn quy trình thay đổi chặt hơn, giới hạn thời gian và nguồn đối chiếu riêng.

### 10.3. Chuyển credential và tích hợp

Tách danh tính của agent, pipeline, người quản trị và người đánh giá. Cập nhật nơi cấp credential, chính sách truy cập và các tích hợp liên quan.

Cần kiểm tra luồng thu thập, công việc vận hành và khả năng đọc bằng chứng trước khi kết thúc đường cũ. Việc chuyển đổi không nên vô tình tạo một khoảng mất log mà không được nhận biết.

### 10.4. Xác nhận bằng các thao tác có ý nghĩa

Kiểm tra cả việc được phép và việc phải bị từ chối trong phạm vi kiểm soát: người vận hành hoàn thành nhiệm vụ nhưng không xóa được bản sao bằng chứng; người audit đọc đúng tập dữ liệu nhưng không sửa cấu hình; danh tính thu thập gửi được sự kiện nhưng không quản lý quyền của kho.

Kiểm tra quyền gián tiếp và quyền sau khi hết hạn. Chỉ quan sát nút bị ẩn trên giao diện chưa chứng minh API hoặc đường khác đã bị giới hạn.

### 10.5. Thu hồi quyền cũ và rà soát tồn dư

Sau khi xác nhận đường mới, xử lý credential dùng chung, quyền kế thừa và phiên cũ theo cơ chế nền tảng. Giữ bằng chứng chuyển đổi và xác nhận những ngoại lệ còn tồn tại.

Rà soát lại khi thay tổ chức nhóm, đổi công cụ, thay kho log hoặc thay cơ chế cấp quyền. Tính độc lập có thể suy giảm dần nếu các quyền mới được cấp mà không đánh giá cùng quyền đã có.

## 11. Nhóm nhỏ, ngoại lệ và truy cập khẩn cấp

Một nhóm nhỏ có thể không đủ người tách hoàn toàn mọi vai trò. Vẫn có thể giảm tập quyền thường trực, tách credential, dùng phê duyệt phù hợp và bố trí rà soát bởi một chủ thể khác cho những thao tác tác động lớn.

Cần mô tả chính xác mức độc lập đạt được. Hai tài khoản do một người nắm giữ có thể hữu ích cho phân tách mục đích nhưng không tương đương kiểm tra độc lập của hai người.

Trong sự cố, có thể cần truy cập khẩn cấp để khôi phục cơ chế thu thập hoặc kho bằng chứng. Đường này phải có mục tiêu, thẩm quyền, cách ghi nhận thay thế và xử lý sau sử dụng. Không nên dùng nhãn khẩn cấp để bỏ qua việc rà soát những thay đổi đã thực hiện.

Nếu hệ thống giám sát chính không hoạt động, cần lưu các nguồn bằng chứng còn có thể thu thập và đối chiếu sau khôi phục. Khoảng thời gian không quan sát được phải được ghi rõ, cùng biện pháp khắc phục và giới hạn của kết luận.

## 12. Các sai lầm thường gặp

| Nhầm lẫn | Cách hiểu cần dùng |
| --- | --- |
| Có nhóm Admin và Audit là đã tách | Cần kiểm tra quyền hiệu lực, người kiểm soát và đường gán quyền |
| Hai tài khoản của cùng một người là hai phía độc lập | Chỉ tách ngữ cảnh; chưa tự tạo kiểm tra độc lập |
| Người audit phải được xem mọi dữ liệu | Cấp theo phạm vi đánh giá và bảo vệ nội dung nhạy cảm |
| Người quản lý kho log đương nhiên là kiểm toán viên | Quản lý dịch vụ lưu trữ và đánh giá bằng chứng là nhiệm vụ khác nhau |
| Mã hóa log là đủ chống xóa | Mã hóa bảo vệ việc đọc; quyền xóa và quản lý khóa cần kiểm soát riêng |
| Có chữ ký thì log chắc chắn đầy đủ | Xác minh nguồn hoặc thay đổi không tự chứng minh không thiếu sự kiện |
| Log đã ở kho từ xa thì nguồn không thể che giấu gì | Kho bảo vệ phần đã nhận; nguồn vẫn có thể ngừng hoặc làm sai việc phát log |
| Cấp toàn quyền vài phút sẽ không ảnh hưởng audit | Trong khoảng đó vẫn có thể thay bảo vệ hoặc bằng chứng nếu được phép |
| Không có log nghĩa là không có hoạt động | Cần kiểm tra tình trạng quan sát và nguồn đối chiếu |
| Đã ghi hình phiên thì không cần log API | Các đường truy cập khác cần bằng chứng tương ứng |

## 13. Bài tập vận dụng

Một nền tảng PAM có ba nhóm: người vận hành, người quản lý log và người audit. Trưởng nhóm vận hành có quyền sửa thành viên cả ba nhóm. Agent gửi log dùng cùng credential với tác vụ dọn dữ liệu. Người audit có thể xuất toàn bộ bản ghi phiên và thay chính sách lưu giữ. Kho log được mã hóa, nhưng cùng một tài khoản có thể xóa dữ liệu và xử lý khóa mã hóa.

Hãy phân tích:

1. Những ranh giới nào mới chỉ tồn tại ở tên nhóm?
2. Quyền nào vượt nhu cầu của agent và người audit?
3. Vì sao mã hóa chưa giải quyết được tính toàn vẹn và sẵn có của bằng chứng?
4. Cần kiểm soát quyền quản lý thành viên nhóm như thế nào?
5. Những thao tác xác nhận nào chứng minh mô hình mới vẫn vận hành và giới hạn quyền đúng?

**Định hướng trả lời:** đánh giá quyền quản lý nhóm như một khả năng vượt ranh giới; tách credential thu thập khỏi quyền dọn dữ liệu; giới hạn người audit vào tập bằng chứng được giao và hồ sơ đánh giá riêng. Bảo vệ dữ liệu, cấu hình lưu giữ, bản sao và khóa theo ranh giới trách nhiệm phù hợp. Xác nhận cả luồng công việc hợp lệ lẫn các thao tác phải bị từ chối, đồng thời đối chiếu quyền tại lớp hạ tầng.

## 14. Ghi nhớ

Tách quyền quản trị và audit giúp tránh việc một chủ thể kiểm soát toàn bộ hành động, bằng chứng và kết luận về chính hành động đó. Muốn đạt mục tiêu, phải tách theo nhiệm vụ và quyền hiệu lực, bao gồm cả những đường gián tiếp qua IAM, credential, hạ tầng và khóa.

Trong PAM, hãy nối yêu cầu, phê duyệt, sử dụng đặc quyền và thu hồi với nguồn bằng chứng được bảo vệ phù hợp. Least privilege, JIT/JEA, quản lý credential và giám sát chỉ phát huy đầy đủ khi người đánh giá hiểu được chất lượng, tính độc lập và khoảng trống của chuỗi bằng chứng.
# Điều chỉnh chiến lược theo nhịp phát hành và thay đổi của sản phẩm

## Mục tiêu bài học

Trong chiến lược VALIDATION_TESTING_STRATEGY, cách kiểm thử phù hợp ở giai đoạn đầu của sản phẩm có thể không còn phù hợp khi sản phẩm đã vận hành ổn định, mở rộng quy mô hoặc chuyển sang nhịp phát hành nhanh hơn. Tương tự, một bản sửa nhỏ, một thay đổi kiến trúc, một lần di trú dữ liệu và một tính năng mới có thể cần phạm vi kiểm thử rất khác nhau dù cùng nằm trong một phiên bản.

Chiến lược kiểm thử vì vậy cần được điều chỉnh theo hai tín hiệu quan trọng: **nhịp phát hành** và **mức độ, bản chất của thay đổi sản phẩm**. Nhịp phát hành quyết định thời điểm và tần suất nhóm cần có bằng chứng. Loại thay đổi quyết định rủi ro nào cần được kiểm tra, ở phạm vi nào và bằng phương pháp nào. Vòng đời sản phẩm cung cấp bối cảnh để hiểu những tín hiệu đó thay đổi ra sao theo thời gian.

Sau bài học, người học có thể:

- Phân biệt nhịp tích hợp, triển khai và phát hành.
- Giải thích cách nhịp phát hành ảnh hưởng đến thời điểm, độ sâu và cách tổ chức kiểm thử.
- Phân loại thay đổi theo phạm vi, độ bất định và rủi ro.
- Điều chỉnh bộ kiểm thử, cổng chất lượng và hoạt động xác nhận theo từng kiểu phát hành.
- Nhận biết khi nào cần tăng, giảm hoặc thiết kế lại phạm vi kiểm thử.
- Dùng dữ liệu vận hành và chất lượng để cải tiến chiến lược theo vòng đời sản phẩm.

## 1. Vì sao chiến lược kiểm thử cần được điều chỉnh?

Chiến lược kiểm thử mô tả cách nhóm thu thập bằng chứng để đánh giá chất lượng và rủi ro. Nó thường xác định phạm vi, loại kiểm thử, môi trường, dữ liệu, mức tự động hóa, trách nhiệm, tiêu chí đạt và điều kiện phát hành. Những quyết định này không tồn tại độc lập với cách sản phẩm được phát triển và đưa đến người dùng.

Nếu sản phẩm phát hành mỗi quý, nhóm có thể có một khoảng thời gian tích hợp và xác nhận phiên bản tương đối dài. Nếu sản phẩm triển khai nhiều lần mỗi ngày, kiểm tra phải trả kết quả nhanh và đáng tin cậy để hỗ trợ từng thay đổi. Nếu sản phẩm đang tái cấu trúc lớn, kiểm thử hồi quy và kiểm tra tương thích cần được chú ý hơn. Nếu sản phẩm gần kết thúc vòng đời, nhóm vẫn cần xác minh các thay đổi bảo trì, bảo mật và di trú dữ liệu, dù chức năng mới ít được bổ sung.

Một chiến lược cố định dễ tạo ra các vấn đề:

- Bộ kiểm thử quá nặng so với nhịp phát hành, làm phản hồi chậm và gây tắc nghẽn.
- Bộ kiểm thử quá nhẹ so với mức độ thay đổi, khiến lỗi lọt đến người dùng.
- Cổng chất lượng không còn phù hợp với kiến trúc hoặc cách triển khai mới.
- Kiểm thử lặp lại những khu vực ổn định trong khi bỏ sót ranh giới vừa thay đổi.
- Nhóm không thu thập đủ bằng chứng sau phát hành để phát hiện rủi ro trong vận hành.
- Tài liệu và dữ liệu kiểm thử không còn đại diện cho phiên bản sản phẩm hiện tại.

Điều chỉnh chiến lược không có nghĩa là thay toàn bộ quy trình sau mỗi lần phát hành. Nhóm cần giữ một nền tảng kiểm soát ổn định, đồng thời thay đổi phạm vi và cường độ kiểm thử khi rủi ro, nhịp làm việc hoặc khả năng phản hồi thay đổi.

## 2. Phân biệt nhịp tích hợp, triển khai và phát hành

Ba khái niệm thường bị dùng thay thế nhau nhưng có ý nghĩa khác nhau:

- **Tích hợp (integration):** đưa thay đổi vào nhánh hoặc phiên bản chung để kiểm tra chúng hoạt động cùng nhau.
- **Triển khai (deployment):** đưa một bản dựng đến môi trường đích, có thể là môi trường kiểm thử, staging hoặc production.
- **Phát hành (release):** làm cho chức năng hoặc phiên bản sẵn sàng sử dụng đối với một nhóm người dùng.

Một nhóm có thể tích hợp mã nhiều lần mỗi ngày, triển khai đến production mỗi ngày nhưng chỉ bật tính năng cho khách hàng theo lịch. Feature flag, cấu hình hoặc cơ chế phân phối theo nhóm người dùng cho phép tách thời điểm triển khai khỏi thời điểm công bố chức năng.

Cần phân biệt thêm:

- **Phân phối liên tục (Continuous Delivery):** duy trì khả năng tạo bản dựng đã qua các cổng chất lượng và có thể phát hành bất cứ lúc nào; việc phát hành có thể vẫn cần quyết định của con người.
- **Triển khai liên tục (Continuous Deployment):** tự động đưa thay đổi đáp ứng điều kiện vào production mà không cần một thao tác phát hành thủ công cho từng thay đổi.

Sự phân biệt này ảnh hưởng trực tiếp đến chiến lược kiểm thử. Khi tích hợp thường xuyên, nhóm cần phản hồi nhanh ở cấp thay đổi. Khi triển khai tự động, cổng chất lượng và khả năng phục hồi phải đủ tin cậy để giảm nguy cơ đưa lỗi ra production. Khi phát hành theo lịch, nhóm cần quản lý phạm vi phiên bản và kiểm tra toàn bộ tập thay đổi được chọn.

## 3. Những yếu tố quyết định cách điều chỉnh

### 3.1. Nhịp phát hành

Nhịp phát hành có thể theo yêu cầu, theo lịch cố định, theo release train, theo sự kiện nghiệp vụ hoặc theo từng nhóm người dùng. Tần suất cao thường đòi hỏi kiểm thử tự động ổn định, phản hồi nhanh và thay đổi nhỏ. Tần suất thấp có thể cho phép một đợt xác nhận rộng hơn, nhưng không nên dồn toàn bộ kiểm thử vào cuối chu kỳ.

### 3.2. Kích thước và phạm vi thay đổi

Một thay đổi nhỏ trong một thành phần cô lập có thể chỉ cần kiểm tra tại thành phần và các luồng liên quan. Một thay đổi ảnh hưởng đến hợp đồng API, schema dữ liệu hoặc dịch vụ dùng chung cần đánh giá phạm vi rộng hơn. Số dòng mã không phải thước đo đủ tốt: một thay đổi một dòng trong điều kiện phân quyền có thể có rủi ro lớn hơn một lần cập nhật giao diện nhiều dòng.

### 3.3. Độ bất định

Yêu cầu chưa rõ, công nghệ mới, kiến trúc mới, dữ liệu chưa đại diện hoặc phụ thuộc chưa được hiểu đầy đủ làm tăng độ bất định. Trong trường hợp này, nhóm cần dành nguồn lực cho kiểm thử khám phá, nguyên mẫu, thử nghiệm kỹ thuật, rà soát chuyên môn và xác nhận sớm với người dùng hoặc bên liên quan.

### 3.4. Mức độ quan trọng và hậu quả lỗi

Các luồng liên quan đến bảo mật, quyền riêng tư, thanh toán, dữ liệu cốt lõi, an toàn hoặc tuân thủ cần mức bằng chứng tương xứng với hậu quả lỗi. Nhịp phát hành nhanh không làm giảm trách nhiệm kiểm soát các rủi ro này.

### 3.5. Năng lực tự động hóa và vận hành

Pipeline nhanh nhưng không ổn định có thể tạo ra quyết định sai. Phát hành thường xuyên cần môi trường tái lập, dữ liệu kiểm thử được quản lý, giám sát, cảnh báo, rollback hoặc roll-forward và người chịu trách nhiệm xử lý sự cố.

### 3.6. Lịch sử chất lượng

Tỷ lệ lỗi lọt qua, lỗi tái diễn, rollback, thời gian phục hồi và các kiểm thử không ổn định cho biết chiến lược hiện tại có hiệu quả hay không. Một vùng có lịch sử lỗi nghiêm trọng cần tăng kiểm soát ngay cả khi nhịp phát hành không thay đổi.

## 4. Điều chỉnh theo kiểu nhịp phát hành

| Kiểu phát hành | Đặc điểm | Trọng tâm chiến lược kiểm thử |
|---|---|---|
| Theo yêu cầu (on-demand) | Phát hành khi thay đổi đã sẵn sàng và đáp ứng điều kiện. | Kiểm tra tự động theo từng thay đổi, cổng chất lượng nhanh, bản dựng có thể tái lập và giám sát sau phát hành. |
| Theo lịch cố định | Phát hành theo ngày hoặc chu kỳ đã công bố. | Quản lý phạm vi phiên bản, kiểm thử tích hợp/hồi quy theo tập thay đổi và xác nhận trước ngày phát hành. |
| Release train | Thay đổi sẵn sàng lên chuyến phát hành kế tiếp; thay đổi chưa đạt chờ chuyến sau. | Quy tắc đưa vào/rút khỏi phiên bản, tương thích giữa nhóm và kiểm tra tích hợp tại mốc chung. |
| Theo sự kiện nghiệp vụ | Phát hành gắn với chiến dịch, mùa bán hàng, kỳ học hoặc thời điểm quan trọng. | Diễn tập, kiểm thử tải, phương án dự phòng, xác nhận dữ liệu và người có quyền dừng phát hành. |
| Theo nhóm người dùng | Bật tính năng theo từng nhóm hoặc tỷ lệ người dùng. | Kiểm thử điều kiện bật/tắt, phân đoạn người dùng, chỉ số mở rộng/dừng và theo dõi từng đợt. |

### 4.1. Phát hành thường xuyên

Với nhịp phát hành cao, chiến lược cần tối ưu tốc độ phản hồi và tính lặp lại:

- Chạy format, lint, phân tích tĩnh và unit test khi tạo pull request.
- Chạy kiểm thử thành phần, API, hợp đồng và tích hợp sau khi hợp nhất hoặc theo thay đổi.
- Tạo bản dựng có định danh rõ ràng và có thể truy vết về mã nguồn, cấu hình và phụ thuộc.
- Tự động hóa smoke test và health check sau triển khai.
- Dùng feature flag hoặc progressive delivery để giới hạn phạm vi tiếp cận khi phù hợp.
- Theo dõi lỗi, độ trễ, tỷ lệ giao dịch thành công và cảnh báo sau phát hành.
- Đặt ngưỡng dừng, rollback hoặc roll-forward và xác định người trực xử lý.

Bộ kiểm thử cần được chia lớp. Các kiểm tra nhanh nên chạy thường xuyên; kiểm tra nặng hơn có thể chạy theo mốc, lịch hoặc khi thay đổi chạm đến vùng liên quan. Việc phân lớp không được làm mất các kiểm tra bắt buộc đối với rủi ro nghiêm trọng.

### 4.2. Phát hành theo lịch

Với phiên bản phát hành hàng tuần, hàng tháng hoặc theo quý, nhóm cần kiểm soát tập thay đổi:

- Chốt phạm vi phiên bản và xác định điều kiện nhận thêm thay đổi.
- Theo dõi trạng thái kiểm thử của từng hạng mục.
- Chạy hồi quy dựa trên rủi ro và phạm vi tác động.
- Kiểm tra tương thích giữa các thành phần, cấu hình và dữ liệu.
- Xác nhận tiêu chí nghiệm thu, tài liệu vận hành và hướng dẫn hỗ trợ.
- Có cơ chế rút một thay đổi chưa sẵn sàng mà không làm chặn toàn bộ phiên bản.
- Lưu hồ sơ lỗi còn mở, ngoại lệ và rủi ro được chấp nhận.

Lịch cố định không có nghĩa là chỉ kiểm thử trước ngày phát hành. Các thay đổi nên được kiểm tra ngay khi được tích hợp để tránh tích tụ lỗi và xung đột đến cuối chu kỳ.

### 4.3. Phát hành theo từng nhóm người dùng

Progressive delivery, canary release và các hình thức triển khai theo giai đoạn cho phép giới hạn phạm vi ảnh hưởng và thu thập dữ liệu thực tế. Chiến lược kiểm thử cần xác định:

- Nhóm nội bộ hoặc nhóm thử nghiệm nào được tiếp cận trước.
- Điều kiện bật, tắt và mở rộng tính năng.
- Chỉ số chất lượng và nghiệp vụ cần theo dõi.
- Ngưỡng lỗi, độ trễ hoặc tỷ lệ thành công khiến phải dừng mở rộng.
- Cách xử lý dữ liệu được tạo bởi phiên bản mới.
- Khả năng tắt tính năng hoặc chuyển về phiên bản ổn định.

Triển khai theo giai đoạn không thay thế kiểm thử trước phát hành. Nó là một lớp kiểm soát bổ sung để giảm phạm vi ảnh hưởng và xác nhận hành vi dưới điều kiện thực tế.

## 5. Điều chỉnh theo loại thay đổi của sản phẩm

| Loại thay đổi | Rủi ro thường gặp | Bằng chứng nên ưu tiên |
|---|---|---|
| Sửa lỗi cục bộ | Bản sửa không xử lý nguyên nhân hoặc gây hồi quy lân cận. | Tái hiện lỗi, kiểm thử lại, unit/component test bảo vệ và hồi quy theo tác động. |
| Tính năng mới | Yêu cầu chưa rõ, luồng mới tương tác sai với chức năng hiện có. | Rà soát tiêu chí chấp nhận, kiểm thử chức năng, tích hợp, khả năng sử dụng và hồi quy. |
| Tái cấu trúc | Hành vi thay đổi ngoài ý muốn dù mục tiêu là giữ nguyên hành vi. | Bộ kiểm thử đặc tính (characterization), unit/component, contract và hồi quy cho các luồng phụ thuộc. |
| Thay đổi kiến trúc hoặc nền tảng | Phụ thuộc, cấu hình, hiệu năng, khả năng tương thích hoặc phục hồi thay đổi. | Thử nghiệm kỹ thuật, kiểm thử tích hợp, tải, độ bền, bảo mật, di trú và diễn tập vận hành. |
| Thay đổi schema hoặc di trú dữ liệu | Mất, sai, trùng hoặc không tương thích dữ liệu giữa các phiên bản. | Kiểm tra dữ liệu trước/sau, tính toàn vẹn, migration trên bản sao đại diện, tương thích ngược và kế hoạch phục hồi. |
| Nâng cấp thư viện hoặc dịch vụ bên ngoài | Thay đổi hành vi, lỗ hổng, API hoặc điều kiện lỗi. | Kiểm tra tương thích, contract, bảo mật phụ thuộc, timeout/retry và kiểm thử lỗi dịch vụ. |
| Thay đổi cấu hình hoặc hạ tầng | Sai môi trường, quyền, mạng, tài nguyên hoặc cấu hình production. | Kiểm tra cấu hình, smoke test, health check, tải và xác nhận quyền truy cập. |
| Thay đổi nội dung hoặc giao diện | Sai hiển thị, khả năng truy cập, điều hướng hoặc thông điệp. | Kiểm tra giao diện trên thiết bị đại diện, accessibility, liên kết và một số luồng người dùng chính. |

### 5.1. Sửa lỗi

Mỗi lỗi cần có bước tái hiện rõ, kết quả mong đợi và bằng chứng về phiên bản bị ảnh hưởng. Sau khi sửa, kiểm thử lại trường hợp thất bại ban đầu. Sau đó chọn hồi quy theo nguyên nhân và phạm vi tác động, thay vì chạy toàn bộ bộ kiểm thử một cách máy móc hoặc chỉ kiểm tra lại đúng một bước.

Nếu lỗi có hậu quả lớn hoặc tái diễn nhiều lần, cần phân tích nguyên nhân gốc, xem lại thiết kế, dữ liệu và quy trình phát triển. Bổ sung kiểm thử tự động tại tầng có thể phát hiện nguyên nhân sớm nhất.

### 5.2. Tính năng mới

Tính năng mới cần xác nhận cả yêu cầu và tác động đến trải nghiệm hiện tại. Nhóm nên làm rõ tiêu chí chấp nhận, luồng chính, trường hợp biên, quyền truy cập, dữ liệu, khả năng tương thích và cách tắt hoặc giới hạn tính năng nếu cần.

Với yêu cầu còn bất định, có thể kiểm thử nguyên mẫu hoặc phát hành cho nhóm nhỏ để thu thập phản hồi. Cần phân biệt bằng chứng xác minh kỹ thuật với bằng chứng rằng tính năng thực sự giải quyết nhu cầu người dùng.

### 5.3. Tái cấu trúc

Tái cấu trúc hướng đến cải thiện cấu trúc nội bộ trong khi giữ nguyên hành vi quan sát được. Nếu thiếu bộ kiểm thử đặc tính, nhóm nên ghi nhận hành vi hiện tại của các luồng quan trọng trước khi thay đổi. Sau đó dùng unit test, component test và contract test để phát hiện sai lệch.

Tái cấu trúc lớn có thể cần chia thành nhiều bước nhỏ, mỗi bước có kiểm tra hồi quy và khả năng hoàn nguyên. Không nên dựa vào việc mã nguồn biên dịch thành công để kết luận thay đổi an toàn.

### 5.4. Di trú dữ liệu và thay đổi không dễ đảo ngược

Di trú dữ liệu cần kế hoạch riêng vì rollback ứng dụng không tự động khôi phục dữ liệu đã biến đổi. Nhóm cần kiểm tra:

- Bản sao dữ liệu đại diện và các trường hợp dữ liệu bất thường.
- Số lượng bản ghi, ràng buộc, quan hệ và tính toàn vẹn trước/sau.
- Khả năng chạy song song phiên bản cũ và mới nếu triển khai theo giai đoạn.
- Tính idempotent của tác vụ di trú và khả năng tiếp tục sau gián đoạn.
- Backup, restore, đối soát và phương án roll-forward.
- Quyền truy cập và bảo vệ dữ liệu trong môi trường kiểm thử.

## 6. Điều chỉnh theo vòng đời sản phẩm

Chiến lược kiểm thử cần phản ánh sản phẩm đang ở giai đoạn nào. Các giai đoạn không nhất thiết diễn ra tuyến tính; sản phẩm trưởng thành vẫn có thể có một tính năng mới ở giai đoạn khám phá hoặc một thành phần cũ đang được thay thế.

### 6.1. Khám phá và xác định nhu cầu

Ở giai đoạn đầu, yêu cầu và giả định có thể thay đổi nhanh. Nhóm nên dành nguồn lực cho:

- Làm rõ nhu cầu và tiêu chí thành công với người dùng.
- Kiểm thử nguyên mẫu, thử nghiệm khả năng sử dụng và đánh giá tính khả thi.
- Xác định rủi ro kiến trúc, bảo mật và dữ liệu từ sớm.
- Xây dựng chiến lược kiểm thử ban đầu và xác định các luồng cốt lõi.
- Tránh đầu tư quá sớm vào bộ E2E lớn cho giao diện và quy trình còn biến động.

Mục tiêu là giảm bất định trước khi mở rộng phạm vi triển khai.

### 6.2. Xây dựng và tích hợp

Khi sản phẩm được phát triển, nhóm cần hình thành nền tảng phản hồi tự động:

- Unit test cho quy tắc và logic trọng yếu.
- Component, API, contract và integration test cho ranh giới.
- Quy tắc review và kiểm tra bắt buộc trên pull request.
- Dữ liệu và môi trường kiểm thử tái lập.
- Truy vết yêu cầu, thay đổi và kết quả kiểm thử.
- Một số E2E bảo vệ hành trình cốt lõi khi luồng đã đủ ổn định.

Tần suất tích hợp nên đủ thường xuyên để giảm xung đột và phát hiện lỗi sớm.

### 6.3. Phát hành ban đầu và mở rộng người dùng

Trước khi đưa sản phẩm đến người dùng rộng hơn, nhóm cần xác nhận chức năng, bảo mật, hiệu năng, khả năng phục hồi, hỗ trợ vận hành và tài liệu cần thiết. Với phát hành theo giai đoạn, cần xác định nhóm tiếp cận trước, ngưỡng mở rộng và cách dừng.

Sau phát hành, nhóm theo dõi chỉ số thực tế và phản hồi để điều chỉnh bộ kiểm thử. Những vấn đề chỉ xuất hiện trong môi trường thật cần được chuyển thành kiểm tra hồi quy hoặc cải thiện giám sát khi phù hợp.

### 6.4. Vận hành và cải tiến liên tục

Ở giai đoạn vận hành, thay đổi có thể nhỏ nhưng diễn ra thường xuyên. Chiến lược nên tập trung vào:

- Pipeline nhanh và ổn định.
- Kiểm thử hồi quy theo tác động thay đổi.
- Kiểm tra bảo mật và cập nhật phụ thuộc.
- Giám sát, cảnh báo, xử lý sự cố và phân tích nguyên nhân.
- Đánh giá lỗi lọt qua và bổ sung kiểm tra phòng ngừa.
- Định kỳ rà soát các test không còn giá trị hoặc gây tắc nghẽn.

### 6.5. Bảo trì, thay thế và kết thúc vòng đời

Khi sản phẩm bước vào giai đoạn bảo trì hoặc chuẩn bị ngừng hoạt động, nhóm vẫn cần kiểm thử bản vá bảo mật, tương thích, sao lưu, xuất dữ liệu, di trú và quy trình ngừng dịch vụ. Mức đầu tư cho tính năng mới có thể giảm, nhưng các cam kết hỗ trợ, bảo vệ dữ liệu và an toàn vẫn cần được thực hiện.

Nếu thay thế một hệ thống cũ, cần kiểm thử đối chiếu giữa hệ thống cũ và mới, xác nhận dữ liệu di trú, xử lý sai lệch và kiểm tra phương án chuyển đổi hoặc quay lại.

## 7. Ma trận điều chỉnh chiến lược

Ma trận dưới đây kết hợp nhịp phát hành và độ lớn/rủi ro thay đổi để gợi ý mức kiểm soát. Nó không thay thế đánh giá riêng của từng sản phẩm.

| Nhịp phát hành | Thay đổi nhỏ, rủi ro thấp | Thay đổi lớn hoặc rủi ro cao |
|---|---|---|
| Liên tục hoặc nhiều lần mỗi ngày | Kiểm tra nhanh trên pull request, unit và kiểm tra thành phần liên quan, smoke test sau triển khai, giám sát. | Chia nhỏ thay đổi nếu có thể; review chuyên môn, contract/integration, kiểm thử hồi quy theo tác động, bảo mật/hiệu năng phù hợp, triển khai có kiểm soát và theo dõi sát. |
| Hàng tuần hoặc theo sprint | Kiểm thử thay đổi, hồi quy lân cận, kiểm tra tích hợp trong chu kỳ. | Phân tích tác động, kiểm thử sâu theo rủi ro, xác nhận phiên bản, diễn tập và phê duyệt nếu cần. |
| Hàng tháng hoặc theo release train | Kiểm tra theo hạng mục, kiểm tra tương thích và hồi quy tập hợp trước mốc phát hành. | Tách giai đoạn tích hợp, thử nghiệm sớm, kiểm thử hệ thống, tải, dữ liệu và vận hành; có điều kiện rút thay đổi chưa sẵn sàng. |
| Theo sự kiện hoặc cửa sổ hiếm | Xác minh cấu hình và luồng sử dụng trước thời điểm sự kiện. | Diễn tập đầy đủ, kiểm thử tải cực đại, phục hồi, dữ liệu, người trực và phương án dự phòng. |

Một thay đổi nhỏ ở thành phần có hậu quả rất nghiêm trọng vẫn có thể cần kiểm soát cao. Ma trận chỉ là bước đầu; rủi ro sản phẩm, lịch sử lỗi và độ bất định có thể làm thay đổi mức ưu tiên.

## 8. Cổng chất lượng cần thích ứng nhưng nhất quán

Cổng chất lượng là điều kiện cần đạt trước khi một thay đổi được hợp nhất, triển khai hoặc phát hành. Cổng có thể khác nhau theo loại thay đổi, nhưng phải có tiêu chí rõ, người chịu trách nhiệm và bằng chứng truy vết.

Ví dụ:

- **Cổng pull request:** lint, phân tích tĩnh, unit test, review bắt buộc và kiểm tra bảo mật tự động phù hợp.
- **Cổng sau hợp nhất:** build, contract, integration, kiểm tra migration và xác minh hiện vật phát hành.
- **Cổng trước phát hành:** hồi quy theo rủi ro, E2E luồng chính, kiểm thử hiệu năng/bảo mật cần thiết, nghiệm thu và rà soát lỗi còn mở.
- **Cổng triển khai:** xác nhận cấu hình, quyền, backup, kế hoạch phục hồi và smoke test.
- **Cổng mở rộng người dùng:** chỉ số ổn định trong ngưỡng, không có lỗi nghiêm trọng và có người quyết định mở rộng.

Không nên thay đổi tiêu chí đạt chỉ để đáp ứng lịch phát hành. Nếu phải có ngoại lệ, cần ghi lý do, phạm vi ảnh hưởng, rủi ro còn lại, người phê duyệt và thời hạn xử lý. Với rủi ro nghiêm trọng, nhóm cần có điều kiện dừng rõ ràng.

## 9. Ví dụ xuyên suốt: sản phẩm SaaS chuyển sang phát hành thường xuyên

Một nền tảng SaaS ban đầu phát hành theo quý. Nhóm có một đợt kiểm thử hồi quy thủ công dài trước mỗi phiên bản. Khi số khách hàng và số nhóm phát triển tăng, nhóm chuyển sang phát hành hàng tuần rồi nhiều lần mỗi ngày.

**Giai đoạn đầu — phát hành theo quý:** nhóm cần xác nhận tập chức năng lớn, kiểm thử tích hợp liên hệ thống, kiểm thử tải và nghiệm thu nghiệp vụ. Tuy nhiên, nếu chỉ chạy kiểm thử vào cuối chu kỳ, lỗi tích hợp có thể tích tụ và khó tìm nguyên nhân.

**Giai đoạn chuyển tiếp — phát hành hàng tuần:** nhóm bắt đầu tích hợp thường xuyên, thêm unit test cho logic cốt lõi, API/contract test cho dịch vụ dùng chung và kiểm thử hồi quy theo từng hạng mục. Bộ E2E được rút gọn thành các hành trình quan trọng. Nhóm chốt phạm vi phiên bản và có thể rút thay đổi chưa sẵn sàng.

**Giai đoạn phát hành thường xuyên:** pipeline chạy lint, phân tích tĩnh và unit test trên pull request; component, contract và integration test sau hợp nhất; một số E2E cốt lõi trước triển khai hoặc theo lịch. Bản dựng được định danh, triển khai có kiểm soát, feature flag cho tính năng mới và theo dõi chỉ số sau phát hành.

Một thay đổi lớn trong dịch vụ phân quyền vẫn phải đi qua review chuyên môn, kiểm thử bảo mật và hồi quy mở rộng dù pipeline thường ngày rất nhanh. Một sửa lỗi giao diện cô lập có thể dùng phạm vi kiểm thử nhỏ hơn. Khi một lỗi nghiêm trọng lọt qua, nhóm bổ sung kiểm tra ở tầng phù hợp và xem lại nguyên nhân trong quy trình, thay vì chỉ thêm một E2E dài cho mọi trường hợp.

Sự chuyển đổi không chỉ là tăng tần suất phát hành. Nhóm đã thay đổi cách thu thập bằng chứng, cách chia nhỏ thay đổi, cách quản lý rủi ro và cách phản hồi sau triển khai.

## 10. Đo lường để biết khi nào cần điều chỉnh

Các chỉ số giúp nhóm nhận ra chiến lược hiện tại đang hỗ trợ hay cản trở nhịp phát hành:

| Nhóm | Chỉ số tham khảo | Câu hỏi cần đặt ra |
|---|---|---|
| Tốc độ phản hồi | Thời gian chạy pipeline, thời gian chờ kết quả kiểm thử, thời gian từ commit đến phản hồi. | Kiểm tra nào gây tắc nghẽn? Có thể chuyển hoặc tối ưu mà vẫn giữ bằng chứng cần thiết không? |
| Chất lượng thay đổi | Change failure rate, lỗi lọt qua, lỗi tái diễn, rollback và hotfix. | Nhịp phát hành mới có làm tăng rủi ro? Loại thay đổi nào gây sự cố? |
| Độ ổn định kiểm thử | Flaky test, tỷ lệ chạy lại, thời gian chẩn đoán và tỷ lệ kiểm thử bị vô hiệu hóa. | Kết quả pipeline có đáng tin cậy để ra quyết định không? |
| Khả năng phục hồi | Time to restore service, tỷ lệ rollback thành công, kết quả diễn tập. | Khi lỗi xảy ra, nhóm có giới hạn được tác động không? |
| Giá trị sản phẩm | Tỷ lệ hoàn thành tác vụ, sử dụng tính năng, phản hồi người dùng và chỉ số nghiệp vụ. | Thay đổi có tạo giá trị thực tế và có tác dụng phụ không? |
| Độ bao phủ rủi ro | Rủi ro quan trọng có kiểm tra, giám sát hoặc biện pháp kiểm soát tương ứng. | Có vùng quan trọng nào chưa có bằng chứng phù hợp không? |

Không nên tối ưu một chỉ số riêng lẻ. Tăng deployment frequency nhưng change failure rate và thời gian phục hồi cũng tăng có thể là dấu hiệu nhóm phát hành nhanh hơn khả năng kiểm soát. Pipeline rất nhanh nhưng thiếu kiểm thử hợp đồng có thể làm lỗi giao tiếp lọt qua. Tỷ lệ pass cao nhưng không bao phủ luồng quan trọng không chứng minh sản phẩm an toàn.

Cần phân tích theo loại thay đổi, thành phần và phiên bản. Dữ liệu tổng hợp toàn sản phẩm có thể che giấu một dịch vụ có lỗi tăng mạnh hoặc một nhóm đang bị tắc nghẽn.

## 11. Quy trình rà soát và điều chỉnh chiến lược

Có thể thực hiện rà soát theo chu kỳ hoặc khi xuất hiện tín hiệu thay đổi đáng kể:

1. **Xác định tín hiệu:** nhịp phát hành tăng/giảm, kiến trúc thay đổi, lỗi nghiêm trọng, mở rộng người dùng, phụ thuộc mới hoặc yêu cầu tuân thủ mới.
2. **Đánh giá tác động:** xác định thành phần, luồng, dữ liệu và nhóm người dùng bị ảnh hưởng.
3. **Cập nhật rủi ro:** đánh giá khả năng xảy ra, hậu quả, độ bất định và khả năng phục hồi.
4. **Rà soát bằng chứng hiện có:** xem bộ kiểm thử nào còn phù hợp, kiểm tra nào chậm, thiếu ổn định hoặc trùng lặp.
5. **Chọn điều chỉnh:** bổ sung kiểm tra, thay đổi tầng kiểm thử, tự động hóa, thay đổi lịch chạy hoặc tăng giám sát.
6. **Cập nhật cổng chất lượng:** nêu rõ điều kiện đạt, điều kiện dừng và trách nhiệm phê duyệt.
7. **Thử nghiệm điều chỉnh:** áp dụng trên một thành phần hoặc một chu kỳ, đo kết quả và xem tác dụng phụ.
8. **Chuẩn hóa và truyền đạt:** cập nhật tài liệu, pipeline, hướng dẫn vận hành và trách nhiệm của nhóm.

Mọi điều chỉnh cần có lý do và bằng chứng. Không nên tăng số lượng test chỉ vì một phiên bản có nhiều lỗi, cũng không nên xóa kiểm tra chỉ vì pipeline đang chậm mà chưa hiểu rủi ro mà kiểm tra đó bảo vệ.

## 12. Những sai lầm thường gặp

- **Dùng một chiến lược cho mọi nhịp phát hành:** kiểm thử phù hợp với release train hàng quý có thể quá chậm cho triển khai liên tục.
- **Đồng nhất triển khai với phát hành:** có thể cần kiểm thử và điều khiển riêng thời điểm bật tính năng.
- **Dồn kiểm thử về cuối chu kỳ:** lỗi tích hợp và yêu cầu được phát hiện muộn, khó xác định nguyên nhân.
- **Giảm kiểm thử khi tăng tốc:** tốc độ phát hành cao cần tự động hóa và khả năng phục hồi tốt hơn, không phải bỏ cổng chất lượng.
- **Chỉ tăng E2E khi có lỗi:** có thể tạo bộ kiểm thử chậm và khó bảo trì; cần tìm tầng phù hợp để bảo vệ nguyên nhân.
- **Bỏ qua loại thay đổi:** di trú dữ liệu, tái cấu trúc và nâng cấp phụ thuộc cần bằng chứng khác nhau.
- **Không cập nhật dữ liệu và môi trường:** kết quả kiểm thử không còn đại diện cho điều kiện vận hành.
- **Không theo dõi sau phát hành:** một số lỗi chỉ xuất hiện dưới tải, dữ liệu hoặc hành vi người dùng thực tế.
- **Không có cơ chế ngoại lệ:** việc bỏ qua cổng kiểm thử không có người phê duyệt và thời hạn tạo rủi ro không kiểm soát.
- **Chỉ đo số lượng test và tỷ lệ pass:** các số liệu này không phản ánh đầy đủ độ bao phủ rủi ro hoặc giá trị của chiến lược.

## 13. Checklist trước khi thay đổi chiến lược kiểm thử

- [ ] Nhịp tích hợp, triển khai và phát hành đã được mô tả riêng.
- [ ] Loại, kích thước và phạm vi thay đổi đã được xác định.
- [ ] Rủi ro nghiệp vụ, dữ liệu, bảo mật, vận hành và tuân thủ đã được đánh giá.
- [ ] Bộ kiểm thử hiện tại được rà soát về phạm vi, độ ổn định, tốc độ và khả năng chẩn đoán.
- [ ] Kiểm tra nhanh được đặt ở vị trí phù hợp trong pipeline.
- [ ] Các ranh giới dịch vụ, hợp đồng và dữ liệu có bằng chứng kiểm thử tương ứng.
- [ ] Các luồng đầu cuối quan trọng được duy trì với phạm vi hợp lý.
- [ ] Cổng chất lượng có điều kiện đạt, điều kiện dừng và người phê duyệt.
- [ ] Có giám sát sau phát hành và phương án phục hồi phù hợp.
- [ ] Chỉ số được theo dõi theo thành phần, loại thay đổi và phiên bản.
- [ ] Điều chỉnh được thử nghiệm và đánh giá trước khi áp dụng rộng.

## Kết luận

Chiến lược kiểm thử cần thay đổi cùng nhịp phát hành, loại thay đổi và giai đoạn vòng đời sản phẩm. Phát hành thường xuyên đòi hỏi phản hồi nhanh, tự động hóa ổn định và giám sát tốt; phát hành theo lịch đòi hỏi quản lý phạm vi phiên bản và xác nhận tích hợp; thay đổi lớn hoặc rủi ro cao cần phân tích tác động và bằng chứng sâu hơn. Nhóm nên điều chỉnh dựa trên rủi ro và dữ liệu thực tế, giữ rõ tiêu chí chất lượng và trách nhiệm quyết định ở mọi nhịp phát hành.

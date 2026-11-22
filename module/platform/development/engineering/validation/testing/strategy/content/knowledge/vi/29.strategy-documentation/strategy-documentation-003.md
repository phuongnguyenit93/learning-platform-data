# Ghi danh mục rủi ro và lý do chọn cách tiếp cận

Một chiến lược kiểm thử cần giải thích sản phẩm có thể thất bại ở đâu, hậu quả của những thất bại đó là gì và nhóm sẽ dùng cách nào để thu thập bằng chứng phù hợp. Nếu chỉ liệt kê các hoạt động như unit test, integration test hay kiểm thử thủ công mà không liên kết chúng với rủi ro, kế hoạch dễ trở thành danh sách công việc rời rạc. Nhóm có thể dành nhiều thời gian cho các trường hợp ít ảnh hưởng trong khi bỏ sót những luồng có hậu quả nghiêm trọng.

**Danh mục rủi ro (risk register)** là bản ghi có cấu trúc về các rủi ro đã nhận diện, đánh giá, ưu tiên và theo dõi. Trong chiến lược kiểm thử xác thực, danh mục này giúp liên kết rủi ro sản phẩm với mục tiêu kiểm thử, cách tiếp cận, phạm vi, nguồn lực, bằng chứng và quyết định chấp nhận rủi ro còn lại.

Lý do chọn cách tiếp cận cần trả lời được: vì sao nhóm chọn loại kiểm thử này, kiểm tra ở cấp độ nào, dùng dữ liệu và môi trường nào, ưu tiên trường hợp nào, và giới hạn nào vẫn còn. Một quyết định tốt dựa trên mức độ tác động, khả năng xảy ra, độ khó phát hiện, yêu cầu tuân thủ, kiến trúc, lịch sử lỗi và chi phí kiểm thử. Danh mục rủi ro không phải tài liệu làm một lần rồi cất đi; nó cần được cập nhật khi sản phẩm, yêu cầu, kiến trúc hoặc bối cảnh sử dụng thay đổi.

## 1. Vai trò của danh mục rủi ro trong chiến lược kiểm thử

Rủi ro sản phẩm mô tả khả năng sản phẩm có hành vi sai hoặc không đáp ứng yêu cầu trong một điều kiện nhất định, cùng hậu quả có thể xảy ra. Ví dụ, dịch vụ thanh toán có thể ghi nhận một giao dịch hai lần khi client retry sau timeout; hậu quả là khách hàng bị trừ tiền nhiều lần và nhóm vận hành phải xử lý hoàn tiền.

Danh mục rủi ro giúp nhóm:

- Tập trung kiểm thử vào hành vi có hậu quả lớn đối với người dùng, tổ chức hoặc hệ thống.
- Giải thích vì sao một số chức năng cần kiểm thử sâu, nhiều cấp độ hoặc đánh giá độc lập.
- Chọn kỹ thuật kiểm thử và mức bao phủ dựa trên loại rủi ro.
- Phân bổ thời gian, nhân lực, môi trường và công cụ theo mức ưu tiên.
- Xác định rủi ro chưa được kiểm tra hoặc chỉ được kiểm tra một phần.
- Theo dõi biện pháp giảm thiểu và rủi ro còn lại sau kiểm thử.
- Cung cấp căn cứ cho quyết định tiếp tục, trì hoãn, phát hành hoặc chấp nhận ngoại lệ.
- Giữ được lý do của các quyết định khi thành viên hoặc ưu tiên dự án thay đổi.

Danh mục rủi ro không thay thế backlog, danh sách lỗi hay ma trận truy vết yêu cầu. Backlog mô tả công việc; defect log ghi nhận lỗi đã quan sát; traceability matrix liên kết yêu cầu với thiết kế và kiểm thử. Risk register tập trung vào những điều có thể xảy ra và tác động của chúng, kể cả khi chưa có lỗi thực tế.

## 2. Phân biệt rủi ro sản phẩm và rủi ro dự án

Trong lập kế hoạch, cần phân biệt hai nhóm rủi ro để chọn phản ứng phù hợp.

| Nhóm | Mô tả | Ví dụ | Cách xử lý thường gặp |
|---|---|---|---|
| Rủi ro sản phẩm (product risk) | Khả năng sản phẩm có lỗi hoặc không đáp ứng nhu cầu, gây hậu quả khi sử dụng | Tính sai thuế, lộ dữ liệu, mất message, không khôi phục được bản sao lưu | Thiết kế kiểm thử, giảm thiểu trong sản phẩm, giám sát và kế hoạch khôi phục |
| Rủi ro dự án (project risk) | Khả năng ảnh hưởng đến tiến độ, chi phí, nguồn lực hoặc khả năng hoàn thành dự án | Thiếu môi trường test, chuyên gia nghỉ, nhà cung cấp giao sandbox trễ | Điều phối, bổ sung nguồn lực, thay đổi lịch, quản lý phụ thuộc và kế hoạch dự phòng |

Hai nhóm có thể liên quan. Ví dụ, môi trường kiểm thử chậm bàn giao là rủi ro dự án; nếu vì thế nhóm không kiểm tra được luồng khôi phục dữ liệu trước phát hành, phạm vi bằng chứng về rủi ro sản phẩm bị giảm. Cần ghi nhận cả nguyên nhân dự án lẫn tác động đến khả năng kiểm soát rủi ro sản phẩm.

Trong bài học này, danh mục tập trung chủ yếu vào rủi ro sản phẩm và cách chúng định hướng kiểm thử. Rủi ro dự án vẫn cần được ghi nhận khi ảnh hưởng đến độ bao phủ, thời điểm hoặc tính hợp lệ của kết quả.

## 3. Viết mô tả rủi ro rõ ràng

Một mô tả rủi ro tốt cho biết điều kiện, sự kiện có thể xảy ra và hậu quả. Cách viết phổ biến là:

> Do [điều kiện hoặc nguyên nhân], [sự kiện không mong muốn] có thể xảy ra, dẫn đến [hậu quả].

Ví dụ:

- Do API thanh toán có thể nhận lại request sau timeout, một yêu cầu bị xử lý lặp có thể tạo hai giao dịch, dẫn đến khách hàng bị trừ tiền hai lần.
- Do kiểm tra quyền chỉ dựa trên vai trò mà không xét tenant, người dùng có thể đọc dữ liệu của tổ chức khác, dẫn đến vi phạm quyền riêng tư.
- Do message được xử lý bất đồng bộ và cơ chế retry chưa idempotent, một sự kiện có thể cập nhật tồn kho nhiều lần, dẫn đến số lượng hàng sai.
- Do dữ liệu migration có định dạng cũ chưa được bao phủ, một phần bản ghi có thể bị chuyển đổi sai hoặc mất, dẫn đến báo cáo không khớp.

Tránh mô tả quá chung như “hệ thống có thể lỗi”, “API không ổn định” hoặc “cần kiểm thử bảo mật”. Những câu này không cho biết sự kiện, điều kiện và tác động nên khó chuyển thành mục tiêu kiểm thử.

Mỗi rủi ro nên tập trung vào một sự kiện và một nhóm hậu quả chính. Nếu một mô tả chứa nhiều sự kiện độc lập, hãy tách thành các rủi ro riêng để có thể đánh giá và chọn biện pháp khác nhau.

## 4. Nguồn nhận diện rủi ro

Rủi ro có thể được phát hiện từ nhiều nguồn. Không nên chỉ dựa vào kinh nghiệm cá nhân hoặc danh sách lỗi của phiên bản trước.

Các nguồn thường dùng:

- **Yêu cầu và tiêu chí chấp nhận:** Quy tắc nghiệp vụ, giới hạn, ngoại lệ và hành vi bắt buộc.
- **Kiến trúc và thiết kế:** Ranh giới dịch vụ, luồng dữ liệu, tích hợp, điểm lỗi đơn và phụ thuộc.
- **Luồng người dùng:** Hành trình phổ biến, hành động nhạy cảm và các bước có thể gây tác dụng phụ.
- **Dữ liệu và quyền:** Dữ liệu cá nhân, dữ liệu tài chính, phân loại dữ liệu, tenant và quyền truy cập.
- **Lịch sử lỗi và sự cố:** Defect, incident, support ticket, nguyên nhân gốc và lỗi tái diễn.
- **Thay đổi hiện tại:** Mã mới, migration, thư viện nâng cấp, cấu hình, feature flag hoặc thay đổi nền tảng.
- **Đánh giá bảo mật và mối đe dọa:** Threat modeling, lạm dụng chức năng, xác thực và phân quyền.
- **Vận hành và giám sát:** Tải thực tế, giới hạn tài nguyên, khả năng phục hồi, backup và alert.
- **Chuyên gia và người dùng:** Kinh nghiệm nghiệp vụ, phản hồi người dùng, yêu cầu hỗ trợ và bối cảnh sử dụng.
- **Bên thứ ba và tuân thủ:** SLA, hợp đồng, tiêu chuẩn, nghĩa vụ pháp lý và thay đổi từ nhà cung cấp.

Một phiên nhận diện hiệu quả nên có đại diện từ phát triển, QA, vận hành, bảo mật và nghiệp vụ khi các vai trò đó liên quan. Góc nhìn khác nhau giúp tìm ra giả định mà một nhóm riêng lẻ có thể bỏ qua.

## 5. Các bước xây dựng danh mục rủi ro

Có thể xây dựng risk register theo quy trình sau:

1. **Xác định phạm vi:** Chọn sản phẩm, phiên bản, tính năng, hành trình hoặc thay đổi cần đánh giá.
2. **Thu thập bối cảnh:** Đọc yêu cầu, sơ đồ kiến trúc, hợp đồng API, dữ liệu, lịch sử sự cố và kế hoạch phát hành.
3. **Nhận diện sự kiện:** Mô tả điều kiện, sự kiện có thể xảy ra và hậu quả.
4. **Xác định nguyên nhân và điểm dễ tổn thương:** Nêu yếu tố có thể làm sự kiện xảy ra, chẳng hạn retry, race condition, dữ liệu biên hoặc cấu hình sai.
5. **Đánh giá rủi ro:** Ước lượng khả năng xảy ra, tác động và các yếu tố bổ sung theo quy ước của tổ chức.
6. **Xếp ưu tiên:** Xác định rủi ro cần xử lý trước, căn cứ vào mức độ và khả năng giảm thiểu.
7. **Chọn phản ứng và cách tiếp cận kiểm thử:** Xác định biện pháp phòng ngừa, ca kiểm thử, cấp độ, dữ liệu, môi trường và bằng chứng.
8. **Phân công chủ sở hữu:** Chỉ định người theo dõi rủi ro, người thực hiện biện pháp và người có quyền chấp nhận rủi ro còn lại.
9. **Theo dõi trạng thái:** Cập nhật khi kiểm thử, sửa lỗi, thay đổi thiết kế hoặc có thông tin mới.
10. **Rà soát và lưu quyết định:** Ghi lại lý do thay đổi mức ưu tiên, phạm vi kiểm thử hoặc cách xử lý.

Risk register có thể bắt đầu ở mức đơn giản rồi được bổ sung dần. Không cần chờ mọi rủi ro được định lượng chính xác mới bắt đầu sử dụng; cần nêu rõ giả định và mức độ chắc chắn của đánh giá.

## 6. Cấu trúc đề xuất cho một risk register

Các trường nên đủ để hiểu rủi ro, ưu tiên, biện pháp và quyết định. Tùy quy mô, có thể dùng bảng tính, công cụ quản lý rủi ro hoặc hệ thống quản lý yêu cầu.

| Trường | Nội dung | Mục đích |
|---|---|---|
| Risk ID | Mã duy nhất, ví dụ `RISK-PAY-01` | Truy vết và tham chiếu giữa tài liệu |
| Tên rủi ro | Tiêu đề ngắn, mô tả sự kiện chính | Nhận diện nhanh |
| Mô tả | Điều kiện/nguyên nhân, sự kiện và hậu quả | Làm rõ điều có thể xảy ra |
| Thành phần/phạm vi | Service, API, dữ liệu, hành trình hoặc môi trường liên quan | Xác định phạm vi ảnh hưởng |
| Nguyên nhân/điểm dễ tổn thương | Yếu tố có thể kích hoạt rủi ro | Hỗ trợ chọn biện pháp |
| Khả năng xảy ra | Mức hoặc ước lượng theo thang đã thống nhất | Đánh giá xác suất tương đối |
| Tác động | Mức hậu quả đối với người dùng, tài chính, an toàn, dữ liệu hoặc vận hành | Đánh giá mức nghiêm trọng |
| Mức ưu tiên | Kết quả đánh giá hoặc thứ tự xử lý | Hướng dẫn phân bổ nguồn lực |
| Bằng chứng hiện có | Lịch sử lỗi, phân tích, log, review hoặc giả định | Giải thích cơ sở đánh giá |
| Biện pháp phòng ngừa | Thay đổi thiết kế, kiểm soát hoặc vận hành để giảm khả năng | Giảm xác suất xảy ra |
| Cách tiếp cận kiểm thử | Mục tiêu, cấp độ, kỹ thuật và phạm vi kiểm tra | Xác minh kiểm soát và phát hiện lỗi |
| Liên kết kiểm thử | Test ID, suite, requirement ID hoặc báo cáo | Truy vết bằng chứng |
| Chủ sở hữu | Người theo dõi rủi ro và người thực hiện hành động | Làm rõ trách nhiệm |
| Rủi ro còn lại | Mức sau khi áp dụng biện pháp | Hỗ trợ quyết định chấp nhận |
| Trạng thái/ngày rà soát | Mới, đang xử lý, đã giảm thiểu, chấp nhận, đóng; ngày cập nhật | Quản lý vòng đời |

Không phải trường nào cũng cần điền bằng con số. Với đánh giá định tính, có thể dùng thấp/trung bình/cao và giải thích căn cứ. Tránh ghi một điểm số không có định nghĩa hoặc không thể giải thích.

## 7. Đánh giá khả năng xảy ra và tác động

Một phương pháp phổ biến là đánh giá hai chiều: khả năng xảy ra (likelihood) và mức độ tác động (impact). Nhóm có thể dùng thang ba hoặc năm mức. Điều quan trọng là định nghĩa từng mức bằng ngôn ngữ nhất quán.

Ví dụ thang định tính:

| Mức | Khả năng xảy ra | Tác động |
|---|---|---|
| 1 – Thấp | Hiếm, cần nhiều điều kiện đồng thời | Bất tiện nhỏ, dễ khôi phục, ảnh hưởng hẹp |
| 2 – Trung bình | Có thể xảy ra trong một số điều kiện thường gặp | Ảnh hưởng đáng kể đến một nhóm người dùng hoặc quy trình |
| 3 – Cao | Dễ xảy ra hoặc đã có dấu hiệu/lịch sử tương tự | Ảnh hưởng lớn, mất dữ liệu, gián đoạn hoặc thiệt hại tài chính đáng kể |

Với thang năm mức, tổ chức có thể phân biệt rõ hơn các mức rất thấp, thấp, trung bình, cao và rất cao. Cần có ví dụ và tiêu chí để hai người đánh giá không gán mức khác nhau chỉ vì cách hiểu chủ quan.

### 7.1. Ma trận khả năng và tác động

Ma trận đơn giản có thể hỗ trợ sắp xếp thảo luận:

| Khả năng \ Tác động | Thấp | Trung bình | Cao |
|---|---|---|---|
| Cao | Trung bình | Cao | Rất cao |
| Trung bình | Thấp | Trung bình | Cao |
| Thấp | Thấp | Thấp | Trung bình |

Ma trận này là ví dụ định tính. Một số tổ chức dùng tích số `likelihood × impact`, nhưng kết quả số học không tự động có nghĩa là xác suất hay tổn thất kỳ vọng chính xác. Chỉ dùng phép nhân khi thang đo và cách diễn giải đã được định nghĩa. Không để một điểm tổng thấp che khuất một tác động hiếm nhưng thảm khốc, chẳng hạn nguy cơ mất an toàn hoặc vi phạm dữ liệu nghiêm trọng.

### 7.2. Xem xét độ khó phát hiện và khả năng khôi phục

Ngoài khả năng và tác động, nhóm có thể xem xét:

- **Khả năng phát hiện:** Lỗi có được phát hiện trước khi người dùng bị ảnh hưởng hay chỉ lộ ra trong vận hành?
- **Khả năng khôi phục:** Có rollback, backup, bù trừ hoặc phục hồi trạng thái đáng tin cậy không?
- **Phạm vi lan truyền:** Một lỗi có thể lan sang nhiều dịch vụ, tenant hoặc giao dịch không?
- **Tốc độ tăng tác động:** Hậu quả có tăng nhanh theo thời gian trước khi được phát hiện không?

Đây là các yếu tố bổ sung để tinh chỉnh ưu tiên, không nhất thiết phải gộp vào một công thức duy nhất. Hãy ghi rõ khi một rủi ro được nâng ưu tiên vì khó phát hiện hoặc khó khôi phục.

## 8. Phân biệt rủi ro vốn có và rủi ro còn lại

**Rủi ro vốn có (inherent risk)** là mức rủi ro trước khi tính đến các biện pháp kiểm soát. **Rủi ro còn lại (residual risk)** là phần rủi ro vẫn tồn tại sau khi áp dụng biện pháp phòng ngừa, kiểm thử, giám sát hoặc khôi phục.

Ví dụ, trước khi có idempotency key, API thanh toán có rủi ro xử lý request retry thành giao dịch trùng. Sau khi triển khai idempotency, kiểm thử các tình huống timeout/retry và đối soát, khả năng xảy ra có thể giảm. Tuy nhiên, rủi ro còn lại vẫn có thể tồn tại do lỗi tích hợp, cấu hình key hoặc giới hạn của nhà cung cấp.

Danh mục nên ghi riêng:

- Rủi ro ban đầu và căn cứ đánh giá.
- Biện pháp đã triển khai hoặc đang dự kiến.
- Bằng chứng cho thấy biện pháp hoạt động.
- Mức rủi ro còn lại và giả định.
- Người có thẩm quyền chấp nhận rủi ro còn lại nếu cần.

Không giảm mức rủi ro chỉ vì đã viết test case. Cần có bằng chứng test đã thực thi, kết quả được đánh giá và biện pháp kiểm soát liên quan thực sự hoạt động. Một ca kiểm thử được thiết kế nhưng chưa chạy không làm giảm rủi ro hiện tại.

## 9. Chuyển rủi ro thành mục tiêu và cách tiếp cận kiểm thử

Mỗi rủi ro ưu tiên cần được chuyển thành câu hỏi kiểm thử có thể trả lời. Cách tiếp cận cần nêu mục tiêu, loại kiểm thử, cấp độ, dữ liệu, điều kiện, oracle và bằng chứng.

Quy trình chuyển đổi:

1. Xác định hành vi hoặc điều kiện gây ra rủi ro.
2. Nêu điều gì cần chứng minh để biết biện pháp kiểm soát có hoạt động.
3. Chọn cấp độ kiểm thử gần nơi lỗi có thể xuất hiện nhất, đồng thời bổ sung cấp cao hơn khi cần xác nhận tích hợp hoặc hành trình.
4. Chọn kỹ thuật phù hợp: phân vùng tương đương, giá trị biên, decision table, state transition, property-based, negative testing, fault injection hoặc kỹ thuật khác.
5. Xác định dữ liệu và trạng thái ban đầu có thể tái tạo.
6. Chọn test oracle và tiêu chí đạt/không đạt.
7. Xác định môi trường, phụ thuộc và quyền cần thiết.
8. Ghi nhận giới hạn, trường hợp chưa kiểm tra và rủi ro còn lại.

Không phải rủi ro nào cũng cần một test case riêng. Một bất biến hoặc bộ kiểm thử có thể bao phủ nhiều rủi ro liên quan. Ngược lại, một rủi ro nghiêm trọng có thể cần nhiều lớp bằng chứng: unit test cho logic, contract test cho giao tiếp, integration test cho giao dịch và kiểm tra vận hành cho khả năng phát hiện sự cố.

## 10. Ánh xạ loại rủi ro sang kỹ thuật kiểm thử

Loại rủi ro gợi ý kỹ thuật phù hợp, nhưng cần chọn theo cơ chế gây lỗi cụ thể.

| Loại rủi ro | Kỹ thuật kiểm thử có thể phù hợp | Bằng chứng cần tìm |
|---|---|---|
| Sai quy tắc nghiệp vụ | Decision table, equivalence partitioning, boundary value analysis | Kết quả đúng ở các nhánh, giới hạn và ngoại lệ |
| Chuyển trạng thái sai | State transition testing, model-based testing | Chỉ cho phép chuyển trạng thái hợp lệ; từ chối chuyển sai |
| Truy cập trái phép | Negative authorization test, role/tenant matrix, security testing | Request ngoài quyền bị từ chối và không tạo tác dụng phụ |
| Giao dịch trùng | Retry testing, idempotency testing, concurrency testing | Một tác dụng nghiệp vụ duy nhất sau retry hoặc request đồng thời |
| Mất hoặc sai dữ liệu | Migration testing, reconciliation, invariant checking, backup/restore test | Bản ghi được bảo toàn hoặc sai khác được giải thích |
| Tích hợp không tương thích | Contract testing, schema validation, integration testing | Provider/consumer tuân thủ hợp đồng và xử lý lỗi đúng |
| Suy giảm hiệu năng | Load, stress, spike, endurance testing | Độ trễ, throughput, error rate và tài nguyên trong ngưỡng |
| Khó phục hồi | Failover, recovery, chaos/fault injection có kiểm soát | Hệ thống phục hồi theo mục tiêu và không mất dữ liệu ngoài giới hạn |
| Không tương thích nền tảng | Compatibility matrix, cross-browser/device testing | Hành vi đúng trên tổ hợp nền tảng ưu tiên |
| Dữ liệu đầu vào bất thường | Fuzzing, property-based, negative testing | Hệ thống xử lý an toàn và giữ bất biến |

Kỹ thuật phải gắn với mục tiêu. Chẳng hạn, load test không tự chứng minh hệ thống chống mất dữ liệu; security scan không thay thế kiểm thử phân quyền theo vai trò; contract test không chứng minh toàn bộ hành trình nghiệp vụ đúng.

## 11. Ghi rõ lý do chọn cách tiếp cận

Phần rationale nên trả lời vì sao cách tiếp cận đã chọn phù hợp hơn các lựa chọn khả thi khác. Một mô tả ngắn nhưng có căn cứ có thể gồm:

- Rủi ro hoặc yêu cầu cần xử lý.
- Cơ chế lỗi hoặc hậu quả đang quan tâm.
- Cấp độ và kỹ thuật kiểm thử được chọn.
- Dữ liệu, môi trường, oracle và mức độc lập cần thiết.
- Lý do lựa chọn, chẳng hạn khả năng phát hiện, độ tái hiện, tốc độ phản hồi hoặc yêu cầu tuân thủ.
- Những phương án không chọn và lý do loại trừ nếu điều đó quan trọng.
- Giới hạn bằng chứng và rủi ro còn lại.

Ví dụ rationale:

> Rủi ro `RISK-PAY-01` liên quan đến việc một request retry có thể tạo giao dịch thanh toán trùng. Nhóm chọn unit test cho quy tắc idempotency, integration test với payment sandbox cho timeout/retry và kiểm tra đồng thời hai request có cùng idempotency key. Cách tiếp cận này xác minh cả logic nội bộ lẫn hành vi qua ranh giới nhà cung cấp. Dữ liệu giao dịch được tạo riêng theo test run; oracle là số giao dịch đã ghi nhận và trạng thái đơn hàng. Kiểm thử thủ công đơn lẻ không đủ để tái hiện ổn định tình huống cạnh tranh. Rủi ro còn lại gồm sự cố ngoài sandbox và hành vi nhà cung cấp ở môi trường thật.

Tránh các lý do chung như “đây là best practice”, “QA yêu cầu” hoặc “cần test đầy đủ”. Lý do phải giải thích mối quan hệ giữa rủi ro và bằng chứng cần thu thập.

## 12. Ví dụ risk register cho nền tảng đặt hàng

Giả sử hệ thống gồm web app, order service, payment service, inventory service, message broker và báo cáo. Một phần danh mục minh họa:

| ID | Mô tả rủi ro | Khả năng | Tác động | Ưu tiên | Cách tiếp cận và lý do |
|---|---|---|---|---|---|
| R-01 | Request thanh toán retry sau timeout có thể tạo giao dịch trùng, gây trừ tiền hai lần | Trung bình | Cao | Rất cao | Unit test idempotency, integration test với sandbox, retry/concurrency test và đối soát; cần xác minh cả logic lẫn ranh giới dịch vụ |
| R-02 | Kiểm tra tenant không đầy đủ có thể cho phép đọc đơn hàng của tổ chức khác | Thấp đến trung bình | Rất cao | Rất cao | Role/tenant matrix, negative API test và đánh giá bảo mật độc lập theo phạm vi; hậu quả quyền riêng tư nghiêm trọng |
| R-03 | Message giao hàng được xử lý lặp có thể trừ tồn kho nhiều lần | Trung bình | Cao | Cao | Contract/integration test, duplicate delivery và property kiểm tra tồn kho; lỗi xảy ra tại ranh giới bất đồng bộ |
| R-04 | Migration không xử lý trường cũ có thể làm sai tổng tiền trong báo cáo | Thấp đến trung bình | Cao | Cao | Migration test trên snapshot đã ẩn danh, reconciliation và kiểm tra invariant; cần xác minh dữ liệu trước/sau |
| R-05 | Trang danh mục có thể tải chậm khi số lượng sản phẩm tăng | Trung bình | Trung bình | Trung bình | Load test theo workload đại diện và theo dõi P95; cần đo ở quy mô dữ liệu dự kiến |
| R-06 | Một số trình duyệt cũ có thể hiển thị sai biểu mẫu đặt hàng | Trung bình | Trung bình | Trung bình | Compatibility test trên tổ hợp trình duyệt ưu tiên; chọn theo dữ liệu sử dụng và phạm vi hỗ trợ |

Các mức trong bảng chỉ minh họa. Dự án thực tế cần xác định thang đo, dữ liệu lịch sử và tiêu chí ưu tiên riêng. Không nên dùng bảng này như đánh giá chính thức cho một sản phẩm khác.

### 12.1. Từ một dòng rủi ro đến kế hoạch kiểm thử

Với `R-01`, nhóm có thể phân rã cách tiếp cận:

| Thành phần | Quyết định |
|---|---|
| Mục tiêu | Một yêu cầu thanh toán lặp không tạo thêm giao dịch hoặc tác dụng phụ |
| Cấp độ | Unit, API/integration và một số luồng đầu cuối |
| Kỹ thuật | Retry, boundary, concurrency và negative testing |
| Dữ liệu | Đơn hàng và idempotency key riêng cho từng test run |
| Oracle | Số giao dịch, trạng thái đơn hàng và bản ghi đối soát |
| Môi trường | Sandbox thanh toán, queue test và database namespace riêng |
| Bằng chứng | Request ID, correlation ID, payment reference và trạng thái cuối |
| Chủ sở hữu | Payment team theo dõi biện pháp; QA sở hữu bằng chứng kiểm thử |
| Giới hạn | Sandbox không chứng minh mọi tình huống vận hành của nhà cung cấp thật |

Việc phân rã này biến một câu mô tả rủi ro thành kế hoạch có thể thực hiện và đánh giá.

## 13. Liên kết rủi ro với yêu cầu, test case và lỗi

Danh mục rủi ro phát huy giá trị khi có liên kết truy vết hai chiều. Một rủi ro có thể liên quan đến nhiều yêu cầu và nhiều ca kiểm thử; một ca kiểm thử có thể cung cấp bằng chứng cho nhiều rủi ro.

Các liên kết hữu ích:

- Risk ID ↔ requirement hoặc business rule.
- Risk ID ↔ component, API, data flow hoặc user journey.
- Risk ID ↔ test objective và test case ID.
- Test case ↔ test run, build và kết quả.
- Risk ID ↔ defect/incident đã phát hiện.
- Risk ID ↔ biện pháp giảm thiểu, quyết định và người chấp nhận.

Ví dụ:

```text
R-01: Giao dịch thanh toán trùng
  -> REQ-PAY-12: Xử lý request thanh toán lặp
  -> API-PAY-07: Idempotency key
  -> TC-PAY-031: Retry sau timeout
  -> TC-PAY-032: Hai request đồng thời cùng key
  -> RUN-2026-041: Kết quả integration test
  -> DEF-882: Giao dịch trùng khi worker retry
```

Mã định danh cần ổn định và được dùng nhất quán trong công cụ quản lý. Nếu đổi ID, cần giữ alias hoặc lịch sử để báo cáo cũ vẫn truy vết được.

## 14. Xếp ưu tiên và phân bổ nguồn lực

Khi thời gian hoặc nguồn lực hạn chế, nhóm cần ưu tiên kiểm thử theo rủi ro thay vì chia đều số ca cho mọi tính năng.

Một cách thực hiện:

1. Sắp xếp rủi ro theo mức ưu tiên và hậu quả.
2. Xác định những rủi ro cần bằng chứng trước mốc hiện tại.
3. Ưu tiên kỹ thuật có khả năng phát hiện sớm và phản hồi nhanh cho lỗi phổ biến.
4. Dành thời gian cho rủi ro hiếm nhưng có hậu quả nghiêm trọng bằng phân tích, mô phỏng hoặc đánh giá chuyên sâu.
5. Xác định rủi ro nào chưa thể kiểm tra và ai có quyền chấp nhận.
6. Rà soát lại ưu tiên khi có lỗi mới, thay đổi thiết kế hoặc thông tin vận hành.

Không nên chỉ dùng điểm số để quyết định. Một rủi ro tác động rất cao nhưng khả năng thấp vẫn có thể cần kiểm thử riêng vì hậu quả không thể chấp nhận. Các yêu cầu pháp lý, an toàn hoặc hợp đồng có thể đặt ra kiểm soát bắt buộc dù điểm tổng không cao.

Nguồn lực cũng cần phù hợp với loại kiểm thử. Kiểm thử hiệu năng cần người hiểu workload và phân tích số liệu; kiểm thử bảo mật cần chuyên môn phù hợp; kiểm thử nghiệp vụ cần người hiểu quy tắc. Giao một rủi ro quan trọng cho người không có năng lực hoặc môi trường không phù hợp không tạo ra bằng chứng đáng tin cậy.

## 15. Theo dõi trạng thái rủi ro và hiệu quả biện pháp

Trạng thái trong risk register cần phản ánh tình hình thực tế. Có thể dùng các trạng thái:

- **Mới nhận diện:** Đã ghi nhận nhưng chưa đánh giá đầy đủ.
- **Đang đánh giá:** Đang thu thập thông tin hoặc xác minh mức độ.
- **Đã lập kế hoạch:** Có biện pháp và chủ sở hữu nhưng chưa hoàn thành.
- **Đang giảm thiểu:** Biện pháp đang được triển khai hoặc kiểm thử.
- **Đã giảm thiểu:** Có bằng chứng cho thấy mức rủi ro giảm; vẫn cần theo dõi rủi ro còn lại.
- **Chấp nhận:** Người có thẩm quyền đã chấp nhận rủi ro còn lại trong phạm vi và thời hạn xác định.
- **Đóng:** Rủi ro không còn áp dụng hoặc đã được loại bỏ với căn cứ rõ.

Không nên chuyển sang “đã giảm thiểu” chỉ vì đã hoàn thành một task. Cần kiểm tra biện pháp hoạt động và có bằng chứng tương ứng. Một test pass không chứng minh toàn bộ rủi ro đã biến mất; nó chỉ cung cấp bằng chứng trong phạm vi, dữ liệu và môi trường đã chạy.

Khi chấp nhận rủi ro, ghi rõ:

- Mức rủi ro còn lại và hậu quả có thể xảy ra.
- Lý do chưa xử lý hoặc không xử lý thêm.
- Biện pháp giám sát, phát hiện và khôi phục.
- Người có quyền quyết định và thời điểm phê duyệt.
- Thời hạn hoặc sự kiện kích hoạt rà soát lại.

## 16. Rà soát và cập nhật danh mục

Risk register cần được xem xét ở các thời điểm có thể làm thay đổi rủi ro:

- Khi bắt đầu dự án hoặc một giai đoạn xác thực mới.
- Khi yêu cầu, kiến trúc, API hoặc luồng dữ liệu thay đổi.
- Khi có dependency, nhà cung cấp hoặc nền tảng mới.
- Khi xuất hiện defect nghiêm trọng hoặc incident thực tế.
- Khi kiểm thử phát hiện một giả định ban đầu không đúng.
- Trước các quyết định phát hành hoặc nghiệm thu quan trọng.
- Khi biện pháp giảm thiểu được triển khai hoặc ngừng sử dụng.
- Theo chu kỳ đã thống nhất đối với sản phẩm đang vận hành.

Trong buổi rà soát, hãy hỏi:

1. Có rủi ro mới nào từ thay đổi gần đây không?
2. Mức khả năng hoặc tác động có thay đổi theo bằng chứng mới không?
3. Các biện pháp đã thực sự hoạt động chưa?
4. Ca kiểm thử có còn phù hợp với yêu cầu và kiến trúc hiện tại không?
5. Có rủi ro nào chưa có test, test chưa chạy hoặc kết quả không đáng tin cậy không?
6. Rủi ro còn lại có được người có thẩm quyền chấp nhận không?
7. Có thể đóng rủi ro nào và căn cứ đóng là gì?

Mọi thay đổi quan trọng cần lưu người cập nhật, ngày, lý do và bằng chứng. Lịch sử giúp giải thích vì sao mức ưu tiên hoặc chiến lược kiểm thử thay đổi.

## 17. Vai trò và trách nhiệm trong quản lý rủi ro

Quản lý rủi ro là trách nhiệm phối hợp. Không nên để QA tự quyết định toàn bộ mức chấp nhận rủi ro sản phẩm.

| Vai trò | Trách nhiệm thường gặp |
|---|---|
| Chủ sở hữu sản phẩm/nghiệp vụ | Giải thích hậu quả, ưu tiên nghiệp vụ và chấp nhận rủi ro trong thẩm quyền |
| Kiến trúc sư/kỹ sư | Nhận diện điểm lỗi kỹ thuật, phụ thuộc và biện pháp thiết kế |
| QA/test lead | Điều phối nhận diện rủi ro, đề xuất cách tiếp cận và đánh giá bằng chứng kiểm thử |
| Nhóm phát triển | Triển khai biện pháp, unit test, sửa lỗi và cung cấp thông tin thay đổi |
| Vận hành/SRE | Đánh giá khả năng phục hồi, giám sát, năng lực và tác động vận hành |
| Bảo mật/quyền riêng tư | Đánh giá mối đe dọa, quyền truy cập và xử lý dữ liệu nhạy cảm |
| Quản lý phát hành | Tổng hợp bằng chứng, rủi ro còn lại và điều kiện phát hành |

Một người có thể đảm nhiệm nhiều vai trò ở nhóm nhỏ, nhưng cần phân biệt ai đề xuất, ai thực hiện, ai xác minh và ai chấp nhận rủi ro. Với rủi ro cao, quyết định chấp nhận nên được chuyển đến người có thẩm quyền và không chỉ dựa trên ý kiến của người trực tiếp tạo ra thành phần.

## 18. Mẫu ghi một rủi ro và rationale

Có thể dùng mẫu sau trong tài liệu chiến lược hoặc công cụ quản lý:

```text
Risk ID:
Tên rủi ro:
Phạm vi/thành phần:

Mô tả:
  Do [điều kiện/nguyên nhân], [sự kiện] có thể xảy ra,
  dẫn đến [hậu quả].

Nguyên nhân và bằng chứng:
Khả năng xảy ra:
Mức tác động:
Yếu tố bổ sung (khả năng phát hiện/khôi phục):
Mức ưu tiên:

Biện pháp phòng ngừa/giảm thiểu:
Mục tiêu kiểm thử:
Cách tiếp cận và lý do lựa chọn:
  - Cấp độ kiểm thử:
  - Kỹ thuật:
  - Dữ liệu và môi trường:
  - Test oracle/bằng chứng:
  - Mức độc lập cần thiết:

Test ID/liên kết yêu cầu:
Chủ sở hữu rủi ro:
Người thực hiện biện pháp:
Rủi ro còn lại:
Quyết định chấp nhận (nếu có):
Trạng thái/ngày rà soát tiếp theo:
```

Mẫu cần được điều chỉnh theo quy trình của tổ chức. Với rủi ro thấp, có thể rút gọn; với rủi ro an toàn, tài chính hoặc bảo mật nghiêm trọng, cần bổ sung căn cứ, người phê duyệt và bằng chứng chi tiết.

## 19. Những sai lầm thường gặp

- **Ghi rủi ro quá chung:** Không thể xác định ca kiểm thử hoặc biện pháp phù hợp.
- **Chỉ ghi lỗi đã xảy ra:** Bỏ qua các sự kiện có thể xảy ra nhưng chưa từng xuất hiện.
- **Đánh giá theo cảm giác:** Không có định nghĩa thang đo hoặc bằng chứng hỗ trợ.
- **Chỉ dùng phép nhân điểm số:** Che khuất tác động rất cao hoặc nghĩa vụ bắt buộc.
- **Nhầm rủi ro dự án với rủi ro sản phẩm:** Không thấy việc thiếu nguồn lực đang làm giảm bằng chứng về chất lượng.
- **Gắn test case nhưng không nêu mục tiêu:** Không biết ca đang giảm hoặc phát hiện rủi ro nào.
- **Coi test pass là rủi ro bằng không:** Bỏ qua giới hạn môi trường, dữ liệu và phạm vi.
- **Không ghi rủi ro còn lại:** Người ra quyết định không biết điều gì vẫn có thể xảy ra.
- **Không có chủ sở hữu:** Rủi ro tồn tại trong tài liệu nhưng không ai theo dõi.
- **Không cập nhật sau thay đổi:** Danh mục trở nên lỗi thời và dẫn đến lựa chọn kiểm thử sai.
- **Chọn kỹ thuật theo thói quen:** Dùng một loại test cho mọi rủi ro mà không xét cơ chế lỗi.
- **Chấp nhận rủi ro không đúng thẩm quyền:** Người thực hiện kiểm thử tự quyết định thay cho chủ sở hữu chịu tác động.
- **Không giữ lịch sử quyết định:** Không giải thích được vì sao phạm vi hoặc ưu tiên thay đổi.

## 20. Checklist xây dựng và duy trì risk register

Trước khi phê duyệt danh mục rủi ro trong chiến lược kiểm thử, nhóm có thể rà soát:

- [ ] Phạm vi sản phẩm, phiên bản và bối cảnh sử dụng đã rõ.
- [ ] Rủi ro được mô tả theo điều kiện/nguyên nhân, sự kiện và hậu quả.
- [ ] Rủi ro sản phẩm được phân biệt với rủi ro dự án.
- [ ] Nguồn nhận diện gồm yêu cầu, kiến trúc, dữ liệu, lịch sử lỗi, vận hành và chuyên gia liên quan.
- [ ] Mỗi rủi ro có ID duy nhất, thành phần và chủ sở hữu.
- [ ] Khả năng xảy ra, tác động và thang đánh giá có định nghĩa rõ.
- [ ] Các rủi ro có tác động nghiêm trọng được xem xét riêng, không bị che bởi điểm tổng.
- [ ] Mức ưu tiên có căn cứ và được rà soát khi có thông tin mới.
- [ ] Biện pháp giảm thiểu được phân biệt với hoạt động kiểm thử xác minh.
- [ ] Cách tiếp cận nêu mục tiêu, cấp độ, kỹ thuật, dữ liệu, oracle và bằng chứng.
- [ ] Lý do chọn cách tiếp cận giải thích mối liên hệ với cơ chế rủi ro.
- [ ] Risk ID được liên kết với yêu cầu, test case, kết quả và defect liên quan.
- [ ] Rủi ro còn lại và giới hạn kiểm thử được ghi rõ.
- [ ] Quyết định chấp nhận rủi ro do đúng người có thẩm quyền thực hiện.
- [ ] Danh mục có trạng thái, lịch sử thay đổi và thời điểm rà soát tiếp theo.
- [ ] Rủi ro chưa được kiểm tra hoặc chưa có bằng chứng được báo cáo minh bạch.

Ghi danh mục rủi ro và lý do chọn cách tiếp cận giúp chiến lược kiểm thử có căn cứ, ưu tiên đúng vấn đề và giải thích được giới hạn của bằng chứng. Khi rủi ro được mô tả rõ, đánh giá nhất quán, liên kết với kiểm thử và cập nhật theo thay đổi, nhóm có thể tập trung nguồn lực vào những hậu quả cần ngăn ngừa hoặc phát hiện sớm nhất, đồng thời cung cấp cơ sở minh bạch cho quyết định chất lượng.

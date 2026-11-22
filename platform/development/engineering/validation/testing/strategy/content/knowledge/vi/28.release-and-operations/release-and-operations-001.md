# Tổng hợp bằng chứng kiểm thử cho bản phát hành cụ thể

Một bản phát hành chỉ có thể được đánh giá đáng tin cậy khi nhóm phát triển trả lời được ba câu hỏi: chính xác phần mềm nào sẽ được phát hành, những kiểm thử nào đã được thực hiện trên phần mềm đó, và kết quả nào chứng minh bản phát hành đáp ứng tiêu chí chấp nhận. Bằng chứng kiểm thử tập hợp câu trả lời thành một hồ sơ có thể truy vết, kiểm tra lại và dùng làm căn cứ cho quyết định phát hành.

Trong chiến lược validation và testing, hồ sơ bằng chứng không đơn thuần là thư mục chứa ảnh chụp màn hình hoặc báo cáo CI. Nó liên kết yêu cầu, thay đổi, rủi ro, trường hợp kiểm thử, lần thực thi, kết quả, lỗi còn tồn tại và quyết định cuối cùng. Mỗi kết luận quan trọng phải dẫn tới bằng chứng cụ thể gắn với đúng ứng viên phát hành.

## 1. Mục tiêu và phạm vi của hồ sơ bằng chứng

Hồ sơ bằng chứng kiểm thử cho một bản phát hành cụ thể là tập hợp thông tin và hiện vật được thu thập trong suốt quá trình xác minh một phiên bản phần mềm. Hồ sơ cần giúp người đọc độc lập xác định:

- Bản phát hành nào đã được kiểm thử, được tạo từ mã nguồn và cấu hình nào.
- Những yêu cầu, luồng nghiệp vụ và thành phần nào nằm trong phạm vi.
- Những cấp độ kiểm thử nào đã chạy, chạy ở môi trường nào và vào thời điểm nào.
- Kết quả đạt, không đạt, bị chặn, chưa chạy hoặc được miễn trừ.
- Các lỗi và rủi ro còn lại ảnh hưởng thế nào tới người dùng hoặc vận hành.
- Ai đánh giá kết quả và ai có thẩm quyền chấp nhận rủi ro để phát hành.

Hồ sơ phục vụ nhiều đối tượng. Kỹ sư cần dùng nó để truy nguyên lỗi; người phụ trách kiểm thử cần đánh giá độ bao phủ và chất lượng xác minh; chủ sản phẩm cần hiểu tác động tới yêu cầu; nhóm vận hành cần biết điều kiện triển khai, giám sát và khôi phục; người phê duyệt cần có căn cứ rõ ràng để quyết định go/no-go.

Phạm vi của hồ sơ phải được giới hạn vào một ứng viên phát hành xác định. Nếu kiểm thử lại sau khi thay đổi mã nguồn, cấu hình, dữ liệu hoặc phụ thuộc, lần xác minh mới phải được nhận diện riêng. Không gộp kết quả của nhiều build thành một kết luận duy nhất nếu không thể chứng minh chúng tương đương.

## 2. Định danh chính xác ứng viên phát hành

Định danh bản phát hành là bước đầu tiên vì mọi bằng chứng phía sau đều phải gắn với cùng một đối tượng. Tên phiên bản như 2.4.0 hoặc release-candidate-2 thường chưa đủ: hai artifact có cùng nhãn vẫn có thể khác nội dung.

Thông tin nhận diện nên bao gồm:

| Trường | Nội dung cần ghi | Vì sao cần |
|---|---|---|
| Sản phẩm hoặc dịch vụ | Tên thành phần được phát hành | Xác định phạm vi hệ thống |
| Phiên bản phát hành | Version hoặc mã release candidate | Phân biệt các đợt phát hành |
| Mã nguồn | Commit, tag và nhánh nguồn | Truy ngược thay đổi |
| Build | Số build và định danh pipeline | Xác định lần tạo artifact |
| Artifact | Tên, vị trí lưu và checksum hoặc digest | Chứng minh chính xác gói đã kiểm thử |
| Cấu hình | Phiên bản cấu hình, feature flag và tham số liên quan | Giải thích khác biệt giữa các lần chạy |
| Môi trường | Hệ điều hành, runtime, dịch vụ phụ thuộc và topology quan trọng | Đặt kết quả trong đúng điều kiện |
| Dữ liệu kiểm thử | Bộ dữ liệu hoặc phiên bản fixture | Có thể tái tạo kịch bản |
| Thời gian | Thời điểm build và thời điểm kiểm thử, kèm múi giờ | Xác định thứ tự và tính hiệu lực |
| Người hoặc hệ thống thực thi | Tài khoản CI, nhóm hoặc người kiểm thử | Truy nguyên nguồn tạo bằng chứng |

Checksum hoặc digest của artifact đặc biệt hữu ích. Khi nhóm kiểm thử và nhóm triển khai cùng tham chiếu một digest, họ có cơ sở xác nhận gói đã được kiểm thử chính là gói được đưa lên môi trường đích. Nếu artifact được đóng gói lại, ký lại hoặc biến đổi trong quá trình phát hành, cần ghi nhận bước biến đổi và cách xác minh tính tương đương.

Thông tin môi trường phải đủ cụ thể để giải thích các điều kiện có thể làm thay đổi kết quả, chẳng hạn phiên bản cơ sở dữ liệu, cấu hình mạng, phiên bản dịch vụ phụ thuộc, loại thiết bị hoặc trình duyệt. Không cần liệt kê mọi chi tiết hạ tầng không liên quan; hãy ghi những yếu tố có ảnh hưởng tới hành vi đang được xác minh.

## 3. Xác định phạm vi kiểm thử và tiêu chí chấp nhận

Trước khi tổng hợp kết quả, cần xác định bản phát hành thay đổi điều gì và thay đổi đó tạo ra rủi ro nào. Nguồn đầu vào thường gồm yêu cầu, user story, tiêu chí chấp nhận, danh sách commit, pull request, lỗi đã sửa, thay đổi cấu hình, thay đổi schema dữ liệu và các phụ thuộc được nâng cấp.

Với mỗi thay đổi, nhóm nên xác định:

1. Thành phần hoặc luồng nghiệp vụ bị tác động trực tiếp.
2. Thành phần liên quan có thể bị ảnh hưởng gián tiếp.
3. Rủi ro nếu chức năng sai, chậm, mất dữ liệu hoặc không tương thích.
4. Kiểm thử cần chạy để phát hiện từng loại rủi ro.
5. Tiêu chí cụ thể để kết luận kiểm thử đạt.

Tiêu chí chấp nhận phải quan sát và đánh giá được. Ví dụ, “chức năng hoạt động tốt” không đủ rõ. Một tiêu chí tốt mô tả điều kiện đầu vào, hành vi mong đợi và kết quả có thể kiểm tra. Với yêu cầu phi chức năng, cần nêu ngưỡng, tải, thời lượng, môi trường và cách đo.

Ma trận truy vết giúp nối các thành phần của hồ sơ:

| Liên kết | Câu hỏi cần trả lời |
|---|---|
| Yêu cầu → rủi ro | Nếu yêu cầu không đạt thì tác động là gì? |
| Rủi ro → kiểm thử | Kịch bản nào có khả năng phát hiện rủi ro? |
| Kiểm thử → lần chạy | Kịch bản đã chạy trên build và môi trường nào? |
| Lần chạy → bằng chứng | Log, báo cáo hoặc hiện vật nào chứng minh kết quả? |
| Kết quả → lỗi | Nếu không đạt, lỗi nào được tạo và theo dõi? |
| Lỗi và rủi ro → quyết định | Điều gì còn tồn tại và ai chấp nhận? |

Không phải mọi yêu cầu đều cần cùng một số lượng kiểm thử. Hãy ưu tiên theo xác suất xảy ra lỗi, mức độ tác động, độ phức tạp thay đổi, lịch sử sự cố và khả năng phát hiện sau triển khai. Những luồng liên quan tới dữ liệu quan trọng, quyền truy cập, giao dịch hoặc khả năng khôi phục thường cần bằng chứng sâu hơn.

Nếu một hạng mục bị loại khỏi phạm vi, hồ sơ phải nêu rõ lý do, tác động và người chấp nhận việc loại trừ. Không được xem hạng mục chưa kiểm thử là đã đạt chỉ vì không có lỗi được báo cáo.

## 4. Các nhóm bằng chứng thường gặp

Một bản phát hành có thể cần nhiều loại kiểm thử. Chọn nhóm phù hợp với kiến trúc, thay đổi và rủi ro; không dùng số lượng báo cáo làm thước đo thay cho chất lượng xác minh.

| Nhóm kiểm thử | Nội dung xác minh | Bằng chứng nên lưu |
|---|---|---|
| Phân tích tĩnh và chất lượng mã | Quy tắc mã, lỗi tiềm ẩn, cảnh báo và tiêu chuẩn dự án | Báo cáo công cụ, phiên bản rule set, danh sách ngoại lệ |
| Unit test | Hành vi của đơn vị nhỏ trong điều kiện cô lập | Kết quả từng test, log, báo cáo coverage và cấu hình chạy |
| Integration test | Tương tác giữa module, cơ sở dữ liệu hoặc dịch vụ | Log tích hợp, kết quả truy vấn kiểm chứng, cấu hình phụ thuộc |
| API và contract test | Cấu trúc request/response, mã lỗi và tương thích hợp đồng | Báo cáo contract, request/response đã loại bỏ dữ liệu nhạy cảm |
| End-to-end và regression | Luồng nghiệp vụ từ đầu đến cuối và hành vi cũ cần bảo toàn | Kịch bản, kết quả, ảnh hoặc video khi có ích, log trình duyệt |
| Hiệu năng và tải | Thời gian phản hồi, thông lượng, độ ổn định và mức sử dụng tài nguyên | Kịch bản tải, cấu hình tải, biểu đồ và dữ liệu đo |
| Bảo mật | Lỗ hổng, quyền truy cập, xác thực, phân quyền và cấu hình an toàn | Báo cáo scan, kết quả kiểm tra thủ công, ngoại lệ được duyệt |
| Tương thích | Hành vi trên runtime, hệ điều hành, trình duyệt hoặc thiết bị hỗ trợ | Ma trận môi trường và kết quả theo từng tổ hợp |
| Migration và dữ liệu | Nâng cấp schema, chuyển đổi dữ liệu và tính toàn vẹn | Log migration, kiểm tra trước/sau, đối soát dữ liệu |
| Rollback và khôi phục | Khả năng quay lui, backup và phục hồi khi triển khai lỗi | Kết quả diễn tập, thời gian khôi phục, log và điều kiện thực hiện |
| Kiểm thử khám phá hoặc thủ công | Rủi ro khó mô hình hóa bằng kịch bản tự động | Mục tiêu phiên kiểm thử, ghi chú, phát hiện và người thực hiện |

Mỗi báo cáo cần cho biết công cụ và phiên bản công cụ, cấu hình quan trọng, phạm vi dữ liệu và thời điểm thực thi. Với kiểm thử thủ công, ghi rõ người thực hiện, các bước chính, kết quả quan sát và liên kết tới lỗi nếu có. Một ảnh chụp màn hình riêng lẻ thường không đủ để chứng minh toàn bộ kịch bản đã đạt.

Coverage của mã nguồn là một chỉ số hỗ trợ, không phải bằng chứng đầy đủ về chất lượng. Coverage cao không đảm bảo assertion đúng hoặc yêu cầu đã được kiểm tra. Ngược lại, tỷ lệ coverage thấp cần được diễn giải theo mức độ rủi ro và phần mã chưa được kiểm tra.

## 5. Thiết kế ma trận bằng chứng

Ma trận bằng chứng là bảng trung tâm để người đọc chuyển từ một yêu cầu sang kết quả thực thi và hiện vật gốc. Mỗi dòng nên đại diện cho một liên kết có thể kiểm tra, không chỉ là một dòng tổng hợp số liệu.

Các cột khuyến nghị:

| Cột | Cách ghi |
|---|---|
| Requirement ID | Mã yêu cầu hoặc tiêu chí chấp nhận |
| Change hoặc component | Thay đổi hay thành phần chịu tác động |
| Risk | Rủi ro đang được kiểm soát |
| Test ID | Mã kịch bản kiểm thử |
| Test level | Unit, integration, API, end-to-end, security... |
| Build identity | Version, commit và artifact digest |
| Environment | Môi trường cùng cấu hình liên quan |
| Executed at | Thời điểm chạy và múi giờ |
| Result | PASS, FAIL, BLOCKED, NOT RUN hoặc WAIVED |
| Evidence reference | Liên kết tới log, báo cáo hoặc artifact |
| Defect reference | Mã lỗi liên quan, nếu có |
| Owner | Người hoặc nhóm chịu trách nhiệm |
| Notes | Giới hạn, điều kiện hoặc giải thích cần thiết |

Một yêu cầu có thể được kiểm tra bằng nhiều kịch bản ở nhiều cấp độ. Một kịch bản cũng có thể hỗ trợ nhiều yêu cầu, nhưng cần thể hiện rõ các liên kết đó. Nếu báo cáo được lưu ở hệ thống CI, hãy dùng liên kết ổn định tới đúng lần chạy và artifact, thay vì liên kết tới trang tổng quan luôn hiển thị lần chạy mới nhất.

Ví dụ minh họa cách đọc một dòng:

| Requirement ID | Test ID | Build | Environment | Result | Evidence |
|---|---|---|---|---|---|
| REQ-ORDER-07 | API-ORDER-014 | release-x.y.z-rc.n / digest đã ghi nhận | staging, cấu hình đã chốt | PASS | Liên kết tới báo cáo lần chạy cụ thể |

Các mã trong ví dụ chỉ minh họa cấu trúc. Khi lập hồ sơ thật, phải thay bằng mã và liên kết thực tế của dự án. Không điền PASS hoặc đường dẫn giả để hoàn thiện hình thức của bảng.

## 6. Chuẩn hóa trạng thái và cách tổng hợp kết quả

Trạng thái kiểm thử phải có ý nghĩa nhất quán trong toàn bộ hồ sơ:

| Trạng thái | Ý nghĩa | Cách xử lý khi đánh giá phát hành |
|---|---|---|
| PASS | Kịch bản chạy và đáp ứng tiêu chí đã định | Có thể dùng làm bằng chứng đạt trong đúng phạm vi |
| FAIL | Kết quả thực tế không đáp ứng tiêu chí | Tạo hoặc liên kết defect, đánh giá tác động |
| BLOCKED | Không thể hoàn tất do điều kiện hoặc phụ thuộc bị cản trở | Nêu nguyên nhân, ảnh hưởng và kế hoạch xử lý |
| NOT RUN | Chưa thực thi | Nêu lý do và đánh giá rủi ro của khoảng trống |
| WAIVED | Được miễn thực hiện hoặc chấp nhận ngoại lệ theo phê duyệt | Lưu người phê duyệt, lý do, phạm vi và thời hạn |

Không gộp BLOCKED, NOT RUN và WAIVED thành PASS. Một ngoại lệ được chấp nhận là quyết định quản trị rủi ro, không phải bằng chứng rằng hành vi đã được kiểm thử thành công. Nếu dùng thêm trạng thái như SKIPPED hoặc FLAKY, cần định nghĩa rõ và nêu cách chúng ảnh hưởng tới kết luận chung.

Khi báo cáo số liệu, ghi cả tử số và mẫu số. Chẳng hạn, “96/100 kịch bản đã chạy đạt” có ý nghĩa hơn “96% đạt” nếu người đọc không biết mẫu số. Tách riêng số PASS, FAIL, BLOCKED, NOT RUN và WAIVED; nói rõ các kịch bản bị loại khỏi mẫu số cùng lý do. Nếu có test chạy lại, ghi nhận từng lần chạy và quy tắc chọn kết quả cuối.

Với kiểm thử không ổn định, không chọn lần chạy đạt để che khuất lần chạy lỗi. Hãy ghi tần suất thất bại, điều kiện tái hiện, ảnh hưởng và quyết định xử lý. Một test flaky vẫn là tín hiệu rủi ro về độ tin cậy của pipeline hoặc sản phẩm.

## 7. Ghi nhận lỗi và rủi ro còn tồn tại

Kết quả FAIL cần được liên kết với defect có thể truy vết. Một defect hữu ích cho quyết định phát hành nên có:

- Mã lỗi, mô tả ngắn và phiên bản phát hiện.
- Các bước tái hiện, điều kiện môi trường và dữ liệu liên quan.
- Kết quả mong đợi và kết quả thực tế.
- Mức độ nghiêm trọng, phạm vi ảnh hưởng và khả năng xảy ra.
- Trạng thái xử lý, người phụ trách và bản sửa dự kiến hoặc đã có.
- Bằng chứng xác nhận lỗi đã được sửa, nếu đã đóng.

Không nên chỉ đếm số lỗi đang mở. Một lỗi nghiêm trọng trong luồng thanh toán, phân quyền hoặc mất dữ liệu có thể quan trọng hơn nhiều lỗi giao diện nhỏ. Đánh giá phải kết hợp mức độ tác động, khả năng khai thác hoặc xảy ra, phạm vi người dùng, khả năng phát hiện và biện pháp giảm thiểu.

Với từng rủi ro chưa được loại bỏ, ghi rõ: điều gì có thể xảy ra, ai hoặc hệ thống nào bị ảnh hưởng, dấu hiệu giám sát nào giúp phát hiện, biện pháp giảm thiểu, phương án khôi phục và người có thẩm quyền chấp nhận rủi ro. Nếu một lỗi được chấp nhận tạm thời, phải ghi điều kiện chấp nhận và thời hạn xem xét lại.

## 8. Bảo đảm chất lượng và tính toàn vẹn của bằng chứng

Bằng chứng chỉ có giá trị khi người đọc tin được nguồn gốc, tính toàn vẹn và mối liên hệ của nó với bản phát hành. Khi thu thập và lưu trữ, cần áp dụng các nguyên tắc sau:

**Nguồn gốc rõ ràng:** Mỗi hiện vật có nguồn tạo, thời điểm, lần chạy, build và người hoặc hệ thống chịu trách nhiệm. Không dùng ảnh hoặc log không rõ xuất xứ để chứng minh tiêu chí quan trọng.

**Liên kết đúng đối tượng:** Báo cáo phải chỉ tới đúng artifact, commit, cấu hình và môi trường. Khi một lần chạy dùng build khác, cần phân biệt kết quả đó thay vì gộp vào hồ sơ.

**Không bị thay đổi âm thầm:** Ưu tiên kho lưu trữ có lịch sử, quyền truy cập và khả năng giữ nguyên artifact. Với hiện vật quan trọng, lưu checksum hoặc digest để phát hiện thay đổi sau khi tạo.

**Đủ ngữ cảnh để diễn giải:** Lưu phiên bản công cụ, tham số chạy, dữ liệu đầu vào, điều kiện môi trường và thời gian. Một con số không có ngữ cảnh thường không thể dùng để tái tạo hoặc so sánh.

**Bảo vệ dữ liệu:** Loại bỏ token, mật khẩu, khóa bí mật, dữ liệu cá nhân và thông tin khách hàng khỏi log, ảnh chụp và request/response. Nếu cần giữ dữ liệu nhạy cảm để điều tra, dùng kho được kiểm soát quyền truy cập và chính sách lưu trữ phù hợp; không đính kèm trực tiếp vào báo cáo phát hành phổ thông.

**Có thể truy cập và lưu giữ:** Liên kết phải được cấp quyền cho người đánh giá. Quy định thời gian lưu theo chính sách dự án và yêu cầu kiểm toán. Tránh phụ thuộc vào máy cá nhân hoặc liên kết tạm thời sẽ hết hạn trước khi hồ sơ được xem xét.

**Có thể tái lập khi cần:** Lưu kịch bản, cấu hình, dữ liệu mẫu và hướng dẫn đủ để chạy lại các kiểm thử trọng yếu. Không phải mọi môi trường đều có thể tái tạo hoàn toàn, nhưng giới hạn đó cần được nêu rõ.

## 9. Quy trình tổng hợp hồ sơ cho một bản phát hành

Một quy trình thực tế có thể triển khai theo các bước sau:

1. **Chốt ứng viên phát hành.** Ghi version, commit, build, artifact digest và cấu hình. Nếu có thay đổi sau thời điểm chốt, xác định lại ứng viên và đánh giá phần kiểm thử cần chạy lại.
2. **Thu thập phạm vi thay đổi.** Đối chiếu yêu cầu, pull request, commit, lỗi đã sửa, thay đổi schema, cấu hình và phụ thuộc.
3. **Lập bản đồ rủi ro và tiêu chí.** Xác định luồng quan trọng, tác động tiềm ẩn, tiêu chí chấp nhận và các hạng mục được loại trừ có lý do.
4. **Chọn bộ kiểm thử.** Phân bổ kiểm thử theo rủi ro ở các cấp độ phù hợp; xác định môi trường và dữ liệu cần thiết.
5. **Thực thi và lưu bằng chứng.** Đảm bảo mỗi lần chạy gắn với build cụ thể; lưu log, báo cáo, artifact và thông tin ngữ cảnh.
6. **Xử lý kết quả bất thường.** Tạo defect, điều tra test flaky, ghi nhận blocked hoặc not run, và xin phê duyệt rõ ràng cho mọi waiver.
7. **Đối chiếu ma trận truy vết.** Kiểm tra các yêu cầu và rủi ro quan trọng đều có kết quả hoặc có ngoại lệ được giải thích; kiểm tra liên kết bằng chứng có thể mở và đúng lần chạy.
8. **Đánh giá rủi ro tồn dư.** Tóm tắt lỗi mở, khoảng trống kiểm thử, giới hạn môi trường và biện pháp giảm thiểu.
9. **Lập báo cáo sẵn sàng phát hành.** Đưa ra kết luận dựa trên tiêu chí đã thống nhất, ghi người đánh giá và người phê duyệt.
10. **Lưu hồ sơ cuối cùng.** Đóng băng phiên bản báo cáo và các liên kết bằng chứng được dùng cho quyết định; cập nhật hồ sơ nếu quyết định thay đổi.

Nếu bước 1 thay đổi sau khi các bước sau đã hoàn thành, cần đánh giá tác động. Thay đổi chỉ ở tài liệu có thể không yêu cầu chạy lại toàn bộ kiểm thử; thay đổi mã nguồn, artifact, cấu hình hoặc dependency có thể làm mất hiệu lực một phần hoặc toàn bộ kết quả trước đó. Quyết định chạy lại phải dựa trên phạm vi ảnh hưởng và rủi ro, đồng thời được ghi nhận.

## 10. Đánh giá sẵn sàng phát hành

Hồ sơ bằng chứng hỗ trợ quyết định go/no-go; nó không tự động thay thế thẩm quyền phê duyệt. Nhóm nên đánh giá tối thiểu các điều kiện sau:

| Điều kiện | Câu hỏi đánh giá |
|---|---|
| Định danh | Artifact dự kiến phát hành có khớp artifact đã kiểm thử không? |
| Phạm vi | Các thay đổi và luồng rủi ro cao đã được xác minh chưa? |
| Tiêu chí | Các tiêu chí bắt buộc có kết quả đạt hoặc ngoại lệ hợp lệ không? |
| Lỗi | Có lỗi nghiêm trọng hoặc lỗi không có biện pháp giảm thiểu chấp nhận được không? |
| Khoảng trống | BLOCKED, NOT RUN và WAIVED có được giải thích và đánh giá tác động không? |
| Vận hành | Có bằng chứng triển khai, giám sát, backup và rollback phù hợp không? |
| Tính toàn vẹn | Các báo cáo và artifact có nguồn gốc, quyền truy cập và liên kết rõ ràng không? |
| Phê duyệt | Người có thẩm quyền đã xem xét rủi ro tồn dư và ghi nhận quyết định chưa? |

**GO** có nghĩa là các tiêu chí phát hành đã thống nhất được đáp ứng và rủi ro tồn dư nằm trong mức được chấp nhận bởi người có thẩm quyền. **NO-GO** có nghĩa là còn điều kiện bắt buộc chưa đạt, bằng chứng không đủ tin cậy hoặc rủi ro vượt ngưỡng chấp nhận. Một quyết định **GO WITH CONDITIONS** chỉ phù hợp khi quy trình của tổ chức cho phép, điều kiện có người phụ trách, thời hạn và cách xác minh rõ ràng.

Không nên đưa ra GO chỉ dựa trên tỷ lệ test pass tổng thể. Một tỷ lệ cao vẫn có thể che giấu một kịch bản trọng yếu chưa chạy hoặc một lỗi nghiêm trọng. Ngược lại, một lỗi nhỏ đã được đánh giá, giới hạn ảnh hưởng và chấp nhận đúng thẩm quyền không nhất thiết làm mọi bản phát hành phải dừng. Điều quyết định là tiêu chí, tác động và sự chấp thuận có thể kiểm chứng.

## 11. Ví dụ minh họa: tổng hợp bằng chứng cho một release candidate

Giả sử nhóm chuẩn bị một release candidate có nhãn release-x.y.z-rc.n. Các giá trị dưới đây là chỗ giữ chỗ minh họa cấu trúc hồ sơ, không phải kết quả kiểm thử của một sản phẩm thật.

**Định danh ứng viên**

| Thuộc tính | Giá trị cần điền |
|---|---|
| Release candidate | release-x.y.z-rc.n |
| Commit | commit-id |
| Build và pipeline | build-number / pipeline-run-id |
| Artifact digest | sha256:digest-value |
| Môi trường xác minh | staging-environment-id |
| Cấu hình | config-version |
| Thời điểm | timestamp kèm múi giờ |

**Kết quả kiểm thử minh họa**

| Nhóm | Kết quả | Bằng chứng cần đính kèm | Nhận định |
|---|---|---|---|
| Unit | PASS | Báo cáo test và coverage | Xác nhận hành vi đơn vị trong phạm vi chạy |
| Integration | PASS | Log tích hợp và phiên bản dependency | Xác nhận tương tác giữa các thành phần đã chọn |
| API regression | FAIL | Báo cáo lần chạy và defect reference | Cần đánh giá mức độ ảnh hưởng trước quyết định |
| Performance | NOT RUN | Lý do chưa chạy và đánh giá rủi ro | Không được xem là đạt |
| Rollback rehearsal | PASS | Log diễn tập và thời gian khôi phục | Có bằng chứng cho kịch bản khôi phục đã thực hiện |

Trong ví dụ này, không thể kết luận GO chỉ từ hai dòng PASS. API regression còn FAIL và performance chưa chạy. Nhóm phải xem defect ảnh hưởng tới luồng nào, có cách sửa hoặc giảm thiểu hay không, tiêu chí hiệu năng có bắt buộc cho đợt phát hành này không, và ai có quyền chấp nhận ngoại lệ. Nếu API regression liên quan tới tiêu chí bắt buộc hoặc hiệu năng là cổng phát hành không thể miễn, quyết định phải là NO-GO cho tới khi điều kiện được đáp ứng. Nếu quy trình cho phép ngoại lệ, hồ sơ cần lưu phê duyệt và rủi ro tồn dư cụ thể trước khi xem xét GO WITH CONDITIONS.

Điểm quan trọng của ví dụ là mọi kết luận đều quay lại đúng release candidate, lần chạy và bằng chứng. Không được lấy kết quả PASS của một build trước đó để bù cho FAIL của build hiện tại nếu chưa có xác minh rằng thay đổi không ảnh hưởng tới kiểm thử đó.

## 12. Mẫu cấu trúc báo cáo sẵn sàng phát hành

Một báo cáo ngắn gọn nhưng có thể kiểm tra lại thường có các phần:

1. **Thông tin phát hành:** sản phẩm, version, commit, build, artifact digest, môi trường và cấu hình.
2. **Tóm tắt thay đổi:** các yêu cầu, thành phần và luồng nghiệp vụ chịu tác động.
3. **Tiêu chí và phạm vi:** điều kiện chấp nhận, nhóm kiểm thử, phạm vi loại trừ và lý do.
4. **Kết quả:** số lượng PASS, FAIL, BLOCKED, NOT RUN, WAIVED; liên kết ma trận bằng chứng.
5. **Lỗi và rủi ro:** defect đang mở, mức độ ảnh hưởng, biện pháp giảm thiểu và rủi ro tồn dư.
6. **Sẵn sàng vận hành:** triển khai, giám sát, backup, rollback và người trực hỗ trợ nếu có liên quan.
7. **Ngoại lệ:** nội dung được miễn, lý do, người phê duyệt, thời hạn và điều kiện.
8. **Quyết định:** GO, NO-GO hoặc GO WITH CONDITIONS theo quy trình; người đánh giá, người phê duyệt và thời điểm.
9. **Phụ lục bằng chứng:** liên kết ổn định tới pipeline, log, báo cáo, artifact và defect.

Phần tóm tắt nên nêu kết luận và những yếu tố có thể làm thay đổi kết luận. Người đọc có thể xem phần tóm tắt để hiểu tình hình, sau đó mở ma trận hoặc phụ lục để kiểm chứng. Không yêu cầu người phê duyệt tự tìm kiếm qua nhiều hệ thống mà không có liên kết và chỉ dẫn.

## 13. Sai sót thường gặp khi tổng hợp bằng chứng

**Gắn kết quả với tên phiên bản nhưng không với artifact.** Điều này có thể khiến nhóm dùng nhầm kết quả của một build khác. Cần ghi commit, build và digest.

**Chỉ báo cáo tỷ lệ pass.** Tỷ lệ tổng hợp có thể che giấu kiểm thử trọng yếu chưa chạy. Cần phân tách trạng thái và liên kết tới từng kết quả.

**Dùng ảnh chụp thay cho dữ liệu gốc.** Ảnh có thể thiếu ngữ cảnh, thời gian hoặc chi tiết lỗi. Hãy lưu log và báo cáo nguồn; dùng ảnh như bằng chứng bổ trợ.

**Không ghi môi trường và cấu hình.** Kết quả khó tái lập và khó giải thích khi khác biệt giữa staging và production. Hãy ghi các yếu tố ảnh hưởng tới hành vi.

**Xem waiver là PASS.** Việc miễn kiểm thử không chứng minh chức năng hoạt động. Hãy giữ trạng thái WAIVED và ghi phê duyệt.

**Gộp kết quả của nhiều build.** Điều này phá vỡ tính truy vết. Mỗi ứng viên cần một hồ sơ riêng hoặc một cấu trúc phân biệt rõ từng build.

**Không quản lý thông tin nhạy cảm.** Log có thể chứa token hoặc dữ liệu cá nhân. Cần làm sạch trước khi chia sẻ và kiểm soát quyền truy cập vào bản gốc.

**Thiếu người chịu trách nhiệm cho rủi ro tồn dư.** Rủi ro không có chủ sở hữu thường bị bỏ quên sau phát hành. Mỗi ngoại lệ cần người phụ trách và thời hạn xem xét.

## 14. Tiêu chí hoàn thành hồ sơ

Trước khi gửi hồ sơ để phê duyệt, người tổng hợp nên tự kiểm tra:

- [ ] Có thể xác định duy nhất artifact được đánh giá bằng version, commit, build và digest.
- [ ] Phạm vi thay đổi, yêu cầu và rủi ro đã được ghi nhận.
- [ ] Các tiêu chí chấp nhận quan trọng được nối với test và kết quả cụ thể.
- [ ] Mỗi kết quả có lần chạy, môi trường, thời gian và liên kết bằng chứng.
- [ ] PASS, FAIL, BLOCKED, NOT RUN và WAIVED được phân biệt rõ.
- [ ] Lỗi mở, ngoại lệ và rủi ro tồn dư có đánh giá tác động, chủ sở hữu và hướng xử lý.
- [ ] Bằng chứng có thể truy cập, có nguồn gốc và không làm lộ dữ liệu nhạy cảm.
- [ ] Có đánh giá triển khai, giám sát và khôi phục phù hợp với rủi ro của bản phát hành.
- [ ] Quyết định phát hành, điều kiện kèm theo và người phê duyệt được ghi lại.

Khi các mục bắt buộc chưa đạt, hồ sơ phải thể hiện rõ khoảng trống và tác động của nó. Mục tiêu của việc tổng hợp bằng chứng là giúp quyết định phát hành dựa trên dữ liệu có thể kiểm chứng, đồng thời giữ lại dấu vết đủ tốt để điều tra sự cố, đánh giá sau phát hành và cải thiện chiến lược kiểm thử ở các phiên bản tiếp theo.

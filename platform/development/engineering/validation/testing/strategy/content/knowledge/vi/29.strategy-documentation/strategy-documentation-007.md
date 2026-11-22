# Liên kết chiến lược với kế hoạch và bằng chứng thực thi

## 1. Vì sao cần liên kết xuyên suốt

Chiến lược kiểm thử chỉ có giá trị khi định hướng của nó được chuyển thành công việc cụ thể và có bằng chứng cho thấy công việc đó đã được thực hiện. Một tài liệu chiến lược có thể nêu mục tiêu giảm rủi ro, ưu tiên luồng nghiệp vụ quan trọng và tự động hóa kiểm thử hồi quy. Nếu kế hoạch phát hành không dành thời gian cho các hoạt động ấy, hoặc báo cáo chỉ ghi “đã kiểm thử” mà không chỉ ra kết quả, chiến lược sẽ không dẫn dắt được quyết định thực tế.

Liên kết xuyên suốt (traceability) tạo ra mối quan hệ có thể kiểm tra giữa:

- Mục tiêu sản phẩm, yêu cầu và rủi ro cần kiểm soát.
- Chiến lược kiểm thử và cách tiếp cận được lựa chọn.
- Kế hoạch, nguồn lực, lịch và môi trường thực hiện.
- Phạm vi kiểm thử, test case, dữ liệu và lần chạy.
- Bằng chứng, phát hiện, xử lý lỗi và quyết định phát hành.

Mối liên kết này giúp trả lời các câu hỏi quan trọng: Vì sao một kiểm thử được thực hiện? Nó kiểm soát rủi ro nào? Ai chịu trách nhiệm? Kết quả nằm ở đâu? Còn rủi ro nào chưa được kiểm soát? Khi phạm vi thay đổi, nhóm có thể xác định những kế hoạch và bằng chứng nào cần cập nhật.

Liên kết tốt không có nghĩa là tạo thật nhiều tài liệu hoặc bắt mọi hạng mục phải có một dòng liên kết riêng. Mục tiêu là giữ đủ thông tin để người khác lần theo quyết định và xác minh kết quả mà không phải phỏng đoán.

## 2. Mô hình liên kết từ chiến lược tới bằng chứng

Một mô hình đơn giản có thể biểu diễn như sau:

~~~mermaid
flowchart TD
    A["Mục tiêu và bối cảnh sản phẩm"] --> B["Yêu cầu và rủi ro"]
    B --> C["Chiến lược và phạm vi kiểm thử"]
    C --> D["Kế hoạch, nguồn lực, lịch và môi trường"]
    D --> E["Test suite, test case và dữ liệu"]
    E --> F["Lần chạy và kết quả"]
    F --> G["Bằng chứng và phát hiện"]
    G --> H["Đánh giá rủi ro và quyết định"]
    H --> I["Hành động tiếp theo và cập nhật chiến lược"]
    I --> B
~~~

Mỗi bước cần có đầu ra đủ rõ để bước tiếp theo sử dụng được:

| Tầng | Câu hỏi cần trả lời | Ví dụ đầu ra |
|---|---|---|
| Mục tiêu và bối cảnh | Sản phẩm cần đạt điều gì, trong điều kiện nào? | Mục tiêu chất lượng, SLO, phạm vi phát hành |
| Yêu cầu và rủi ro | Hành vi nào phải đúng, điều gì có thể gây thiệt hại? | Yêu cầu có mã định danh, risk register |
| Chiến lược | Kiểm thử ở đâu, mức nào, ưu tiên ra sao? | Test approach, mức độ bao phủ, tiêu chí vào/ra |
| Kế hoạch | Ai làm, khi nào, cần gì và phụ thuộc điều gì? | Test plan, lịch, phân công, môi trường |
| Thiết kế kiểm thử | Cần chạy những trường hợp nào với dữ liệu nào? | Test suite, test case, dữ liệu kiểm thử |
| Thực thi | Điều gì đã được chạy trên phiên bản nào? | Run ID, trạng thái, thời gian, người chạy |
| Bằng chứng | Kết quả nào chứng minh trạng thái đã ghi nhận? | Log, báo cáo tự động, ảnh chụp, trace, kết quả truy vấn |
| Quyết định | Có thể tiếp tục, cần sửa hay phải chấp nhận rủi ro? | Báo cáo đánh giá, defect, release decision |

Không phải mọi nhóm cần một công cụ riêng cho từng tầng. Một hệ thống quản lý công việc, kho mã nguồn và nền tảng CI có thể cung cấp phần lớn thông tin. Điều quan trọng là định danh và liên kết giữa chúng phải ổn định, có thể truy cập và được duy trì.

## 3. Chuyển chiến lược thành kế hoạch có thể thực hiện

Chiến lược mô tả cách tiếp cận ở cấp định hướng; kế hoạch biến định hướng đó thành hoạt động có chủ sở hữu, thời điểm và điều kiện thực hiện. Khi lập kế hoạch, hãy chuyển từng quyết định chiến lược thành câu hỏi vận hành.

Ví dụ:

- Nếu chiến lược ưu tiên rủi ro thanh toán, kế hoạch phải chỉ ra thời gian kiểm thử luồng thanh toán, môi trường phù hợp, dữ liệu mô phỏng và người xác nhận kết quả.
- Nếu chiến lược yêu cầu kiểm thử hồi quy tự động ở mỗi pull request, kế hoạch cần xác định pipeline, bộ test bắt buộc, ngưỡng thời gian và người xử lý khi pipeline thất bại.
- Nếu chiến lược yêu cầu kiểm tra khả năng khôi phục, kế hoạch cần bố trí một hoạt động diễn tập, người quan sát, tiêu chí thành công và cách lưu bằng chứng.
- Nếu chiến lược dựa trên kiểm thử thăm dò cho khu vực mới, kế hoạch cần xác định charter, giới hạn thời gian, phạm vi và cách ghi lại phát hiện.

Một kế hoạch kiểm thử có thể bao gồm:

| Thành phần | Nội dung cần ghi |
|---|---|
| Mục tiêu và phạm vi | Mục tiêu chất lượng, chức năng trong phạm vi và phần loại trừ |
| Căn cứ | Yêu cầu, rủi ro, thay đổi hoặc quyết định chiến lược liên quan |
| Cách tiếp cận | Mức kiểm thử, loại test, kỹ thuật và thứ tự ưu tiên |
| Lịch và mốc | Thời điểm chuẩn bị, thực thi, sửa lỗi, kiểm thử lại và đánh giá |
| Vai trò | Người phụ trách, người thực hiện, người xem xét và người ra quyết định |
| Môi trường và dữ liệu | Phiên bản, cấu hình, phụ thuộc, tài khoản và quy tắc làm sạch dữ liệu |
| Tiêu chí | Điều kiện bắt đầu, điều kiện hoàn tất, ngưỡng đạt và cách xử lý ngoại lệ |
| Phụ thuộc và rủi ro | Hệ thống ngoài, dữ liệu chờ, giới hạn môi trường và phương án dự phòng |
| Bằng chứng | Nơi lưu kết quả, quy tắc đặt tên và quyền truy cập |

Kế hoạch không nên sao chép nguyên văn toàn bộ chiến lược. Hãy tham chiếu tới phiên bản chiến lược và ghi rõ những quyết định được áp dụng cho lần phát hành hoặc phạm vi cụ thể. Khi một kế hoạch phải điều chỉnh, người xem có thể phân biệt đâu là nguyên tắc chung và đâu là lựa chọn riêng của lần thực hiện đó.

## 4. Thiết kế định danh và ma trận truy vết

Định danh ổn định giúp liên kết tài liệu, test và bằng chứng qua nhiều lần thay đổi. Có thể dùng mã ngắn theo loại đối tượng, chẳng hạn:

- `OBJ-12`: mục tiêu chất lượng.
- `REQ-34`: yêu cầu.
- `RISK-08`: rủi ro.
- `STRAT-02`: quyết định chiến lược.
- `PLAN-05`: kế hoạch kiểm thử.
- `TC-104`: test case.
- `RUN-2026-041`: lần chạy.
- `BUG-77`: lỗi hoặc phát hiện.
- `EVD-2026-041-03`: bằng chứng.

Quy tắc đặt mã cần đơn giản, duy nhất trong phạm vi đã thống nhất và không phụ thuộc vào vị trí hiện tại của tệp. Nếu một đối tượng bị đổi tên hoặc di chuyển, mã định danh vẫn giữ nguyên. Không tái sử dụng mã đã xóa cho đối tượng mới vì liên kết lịch sử có thể trỏ nhầm.

Ma trận truy vết (traceability matrix) là một cách trình bày các quan hệ này. Ví dụ dưới đây minh họa một phần luồng thanh toán:

| Yêu cầu/rủi ro | Quyết định chiến lược | Kế hoạch | Test case | Lần chạy và bằng chứng |
|---|---|---|---|---|
| REQ-34: tổng tiền phải chính xác | STRAT-02: ưu tiên kiểm thử nghiệp vụ theo rủi ro | PLAN-05: kiểm thử thanh toán trước phát hành | TC-104: tính tổng tiền với giảm giá và thuế | RUN-2026-041, EVD-2026-041-03 |
| RISK-08: giao dịch có thể bị ghi nhận hai lần | STRAT-02: kiểm thử tính lặp an toàn và xử lý retry | PLAN-05: kiểm tra retry và đối soát | TC-108: gửi lại cùng mã yêu cầu | RUN-2026-041, EVD-2026-041-07 |

Một ma trận có thể có nhiều-nhiều quan hệ: một rủi ro được kiểm soát bởi nhiều test, và một test có thể cung cấp bằng chứng cho nhiều yêu cầu. Hãy thể hiện quan hệ đúng với thực tế thay vì cố ép mỗi yêu cầu chỉ có một test hoặc mỗi test chỉ thuộc một yêu cầu.

Ma trận nên giúp phát hiện cả hai chiều:

- **Truy vết xuôi:** từ mục tiêu hoặc rủi ro, xác định chiến lược, kế hoạch, test và bằng chứng tương ứng.
- **Truy vết ngược:** từ một test hoặc bằng chứng, xác định lý do tồn tại và rủi ro mà nó hỗ trợ kiểm soát.

Truy vết xuôi giúp tìm phạm vi chưa được kiểm tra. Truy vết ngược giúp phát hiện test dư thừa, test không còn liên quan hoặc bằng chứng không phục vụ quyết định nào. Việc một test không liên kết trực tiếp với yêu cầu không tự động có nghĩa là test vô ích; test thăm dò, kiểm thử khả năng phục hồi và kiểm tra tuân thủ có thể gắn với rủi ro hoặc mục tiêu cấp cao hơn.

## 5. Liên kết bằng chứng với lần thực thi

Kết quả “Pass” hoặc “Fail” chỉ có ý nghĩa khi người xem biết chính xác điều gì đã được chạy và trong điều kiện nào. Một bản ghi thực thi có thể cần các thông tin:

- Mã test case và phiên bản nội dung test tại thời điểm chạy.
- Mã build, commit, artifact hoặc phiên bản ứng dụng.
- Môi trường, cấu hình liên quan và trạng thái phụ thuộc quan trọng.
- Dữ liệu kiểm thử hoặc mã định danh dữ liệu; tránh ghi dữ liệu bí mật.
- Người hoặc pipeline kích hoạt, thời điểm bắt đầu và kết thúc.
- Kết quả, bước thất bại, giá trị mong đợi và giá trị thực tế.
- Liên kết tới log, báo cáo, ảnh chụp, trace hoặc tệp kết quả.
- Mã lỗi liên quan và trạng thái kiểm thử lại nếu có.

Ví dụ, một báo cáo pipeline ghi `TC-104: PASS` chưa đủ để tái hiện. Báo cáo nên cho biết test chạy trên build nào, ở môi trường nào, dùng bộ dữ liệu nào và liên kết tới kết quả chi tiết. Nếu test tự động, lưu báo cáo máy đọc được cùng log cần thiết. Nếu kiểm thử thủ công, ghi bước thực hiện, kết quả quan sát và bằng chứng phù hợp.

### 5.1. Chọn bằng chứng phù hợp

Không phải mọi loại test đều cần cùng một loại bằng chứng:

| Hoạt động | Bằng chứng có ích |
|---|---|
| Kiểm thử API | Request/response đã loại bỏ thông tin nhạy cảm, mã trạng thái, assertion và log |
| Kiểm thử giao diện | Ảnh chụp hoặc video ngắn, console log, kết quả tự động hóa |
| Kiểm thử hiệu năng | Cấu hình tải, thời lượng, phân bố độ trễ, thông lượng, tỷ lệ lỗi và biểu đồ |
| Kiểm thử bảo mật | Báo cáo công cụ, phiên bản rule, phát hiện đã phân loại và trạng thái xử lý |
| Kiểm thử migration | Phiên bản schema trước/sau, kết quả kiểm tra dữ liệu và log migration |
| Kiểm thử khôi phục | Mốc thời gian, trạng thái dịch vụ, dữ liệu đối chiếu và thời gian phục hồi |
| Kiểm thử thăm dò | Charter, phạm vi đã khám phá, ghi chú quan sát và lỗi được phát hiện |

Bằng chứng phải đủ để hỗ trợ kết luận, nhưng cần tránh thu thập quá mức. Không đính kèm token, mật khẩu, khóa truy cập, dữ liệu cá nhân hoặc thông tin khách hàng thật vào báo cáo. Với ảnh chụp và log, che hoặc loại bỏ dữ liệu nhạy cảm trước khi chia sẻ. Quyền truy cập và thời hạn lưu giữ phải tuân theo chính sách của tổ chức.

## 6. Đánh giá độ bao phủ và khoảng trống

Ma trận truy vết không chỉ để lưu tài liệu; nó là công cụ phân tích phạm vi. Một số câu hỏi có thể dùng khi rà soát:

- Mỗi mục tiêu hoặc rủi ro quan trọng đã có cách kiểm soát và người chịu trách nhiệm chưa?
- Những test bắt buộc đã có kế hoạch thực thi trong môi trường phù hợp chưa?
- Test đã chạy trên đúng phiên bản và có bằng chứng truy cập được chưa?
- Có yêu cầu nào chỉ có test thiết kế nhưng chưa có kết quả thực thi?
- Có test thất bại hoặc bị bỏ qua mà chưa có đánh giá tác động không?
- Có bằng chứng nào không gắn với mục tiêu, yêu cầu hoặc rủi ro đã xác định?
- Các phát hiện mức nghiêm trọng đã được sửa, kiểm thử lại hoặc chấp nhận rủi ro theo đúng thẩm quyền chưa?

Có thể phân loại trạng thái liên kết theo từng đối tượng:

| Trạng thái | Ý nghĩa |
|---|---|
| Chưa liên kết | Chưa xác định được test hoặc bằng chứng phù hợp |
| Đã thiết kế | Có test hoặc hoạt động dự kiến, chưa có kết quả chạy |
| Đã thực thi | Có lần chạy và kết quả, cần đánh giá kết luận |
| Đạt | Bằng chứng đáp ứng tiêu chí đã định |
| Không đạt | Kết quả vi phạm tiêu chí hoặc phát hiện rủi ro |
| Được miễn có lý do | Không thực hiện, có lý do, người chấp thuận và đánh giá tác động |
| Chờ xác minh | Thiếu bằng chứng hoặc cần kiểm tra lại kết quả |

Trạng thái phải phản ánh đúng thực tế. Không đánh dấu “đạt” chỉ vì test đã chạy; không đánh dấu “đã bao phủ” khi chỉ mới có test case nhưng chưa thực thi. Nếu một hoạt động được miễn, cần ghi lý do, người có thẩm quyền chấp thuận, rủi ro còn lại và điều kiện xem xét lại.

Độ bao phủ nên được phân tích theo rủi ro và mức độ quan trọng, không chỉ bằng tỷ lệ số lượng. Có 95% yêu cầu được liên kết vẫn có thể là kết quả kém nếu 5% còn thiếu bao gồm chức năng thanh toán hoặc khôi phục dữ liệu. Một báo cáo tốt cần nêu rõ các khoảng trống có tác động lớn và cách xử lý chúng.

## 7. Quản lý thay đổi và giữ liên kết luôn đúng

Yêu cầu, kiến trúc và kế hoạch có thể thay đổi trong suốt vòng đời phát triển. Mỗi thay đổi đáng kể cần được đánh giá tác động tới các liên kết liên quan.

Ví dụ, khi yêu cầu tính phí thay đổi:

1. Cập nhật yêu cầu và ghi nhận phiên bản hoặc lịch sử thay đổi.
2. Đánh giá lại rủi ro, giả định và quyết định chiến lược liên quan.
3. Xác định kế hoạch, test case, dữ liệu và môi trường cần sửa.
4. Đánh dấu kết quả cũ là bằng chứng của phiên bản trước; không trình bày nó như bằng chứng cho yêu cầu mới.
5. Chạy lại các kiểm thử bị ảnh hưởng và lưu bằng chứng mới.
6. Cập nhật báo cáo độ bao phủ và đánh giá phát hành.

Khi test case thay đổi, cần giữ lịch sử phiên bản hoặc lưu bản chụp nội dung đã dùng trong lần chạy. Nếu chỉ sửa nội dung test tại chỗ, nhóm có thể không biết kết quả cũ được tạo ra theo bước nào. Khi một yêu cầu bị loại bỏ, không xóa ngay các liên kết lịch sử; hãy đánh dấu trạng thái đã ngừng áp dụng và giữ quan hệ để phục vụ kiểm toán hoặc điều tra.

Một quy trình thay đổi có thể dùng các bước rà soát đơn giản:

- Người đề xuất mô tả thay đổi và lý do.
- Người phụ trách kiểm thử đánh giá ảnh hưởng tới phạm vi, mức rủi ro, lịch và bằng chứng.
- Chủ sở hữu yêu cầu hoặc sản phẩm xác nhận cách hiểu và ưu tiên.
- Kế hoạch và test được cập nhật trước khi thực thi phần thay đổi.
- Kết quả mới được liên kết với phiên bản thay đổi và quyết định tương ứng.

Tần suất rà soát có thể theo mốc phát hành, sprint hoặc khi có thay đổi lớn. Không nên chờ tới cuối dự án mới tạo liên kết, vì khi đó ngữ cảnh và người chịu trách nhiệm có thể đã thay đổi.

## 8. Sử dụng liên kết trong báo cáo và quyết định phát hành

Báo cáo kiểm thử cần chuyển dữ liệu thực thi thành thông tin hỗ trợ quyết định. Một báo cáo hữu ích thường trình bày:

1. Phạm vi và phiên bản được đánh giá.
2. Mục tiêu chất lượng và rủi ro quan trọng.
3. Kế hoạch đã thực hiện so với kế hoạch dự kiến.
4. Kết quả theo loại test, mức độ quan trọng và trạng thái.
5. Bằng chứng cho các kết luận chính.
6. Lỗi còn mở, ảnh hưởng, biện pháp giảm thiểu và chủ sở hữu.
7. Phạm vi chưa kiểm tra, test bị bỏ qua và lý do.
8. Rủi ro còn lại, người chấp nhận rủi ro và khuyến nghị.

Ví dụ, thay vì báo cáo “đạt 92% test”, hãy nêu: “Các luồng đăng nhập và thanh toán bắt buộc đã đạt trên build X; kiểm thử retry phát hiện một lỗi mức cao đang mở; kiểm thử tải chưa thực hiện do môi trường chưa sẵn sàng; chủ sở hữu phát hành cần quyết định có tiếp tục canary hay tạm dừng.” Cách diễn đạt này cho biết kết quả, giới hạn và hành động cần thiết.

Quyết định phát hành phải dựa trên tiêu chí đã thống nhất và mức độ rủi ro còn lại. Bằng chứng kiểm thử cung cấp căn cứ; người có thẩm quyền chịu trách nhiệm quyết định chấp nhận hoặc từ chối rủi ro. Không nên để một tỷ lệ tổng hợp che khuất lỗi nghiêm trọng hoặc thiếu bằng chứng ở phạm vi trọng yếu.

Sau phát hành, các sự cố thực tế cũng cần được liên kết ngược về rủi ro, yêu cầu và kiểm thử liên quan. Nếu lỗi lọt qua, hãy xác định vì sao: rủi ro chưa được nhận diện, test thiếu, test không được chạy, môi trường không đại diện, tiêu chí chưa phù hợp hay bằng chứng bị diễn giải sai. Kết quả phân tích này giúp điều chỉnh chiến lược và kế hoạch cho chu kỳ sau.

## 9. Tự động hóa liên kết và quản trị dữ liệu

Khi số lượng yêu cầu và lần chạy tăng lên, có thể tự động hóa một phần việc duy trì liên kết:

- Pipeline gắn build ID, commit SHA, môi trường và Run ID vào báo cáo test.
- Hệ thống quản lý công việc liên kết yêu cầu, rủi ro, lỗi và test case bằng mã định danh.
- Báo cáo tổng hợp phát hiện test chưa chạy, liên kết bị hỏng hoặc bằng chứng thiếu.
- Khi yêu cầu thay đổi, quy trình quản lý thay đổi thông báo tới người phụ trách test liên quan.
- Dashboard hiển thị độ bao phủ theo rủi ro, trạng thái test và lỗi còn mở.

Tự động hóa chỉ có ích khi dữ liệu nguồn đáng tin cậy. Một liên kết sai được đồng bộ tự động vẫn là liên kết sai. Cần quy định ai được tạo hoặc thay đổi định danh, cách xử lý đối tượng trùng lặp, cách lưu lịch sử và cách kiểm tra liên kết định kỳ.

Không nên dùng tên hiển thị làm khóa liên kết nếu tên có thể thay đổi. Hạn chế sao chép thủ công cùng một kết quả vào nhiều báo cáo; hãy tham chiếu tới nguồn kết quả gốc. Nếu cần xuất báo cáo tĩnh, ghi thời điểm tạo và phiên bản dữ liệu để người đọc hiểu đó là ảnh chụp tại một thời điểm.

## 10. Ví dụ tổng hợp: thay đổi quy tắc tính phí

Giả sử sản phẩm thay đổi quy tắc tính phí giao hàng theo khu vực và giá trị đơn hàng. Nhóm có thể xây dựng liên kết như sau:

**Mục tiêu và rủi ro:** Mục tiêu `OBJ-12` là tính đúng phí trước khi khách xác nhận đơn. Rủi ro `RISK-08` là tính sai phí khiến khách bị thu thừa hoặc thiếu.

**Chiến lược:** Quyết định `STRAT-02` ưu tiên kiểm thử theo bảng quyết định cho các ngưỡng giá trị và khu vực; kiểm tra hồi quy các luồng tạo đơn; đồng thời kiểm tra quyền và tính nhất quán dữ liệu.

**Kế hoạch:** `PLAN-05` dành môi trường tích hợp, dữ liệu tổng hợp cho từng khu vực, người phụ trách nghiệp vụ và thời gian kiểm thử trước khi phát hành.

**Thiết kế:** `TC-104` kiểm tra đơn dưới ngưỡng miễn phí; `TC-105` kiểm tra đúng ngưỡng; `TC-106` kiểm tra khu vực không hỗ trợ; `TC-107` kiểm tra tổng phí được lưu cùng đơn.

**Thực thi:** Pipeline tạo `RUN-2026-041` trên build đã xác định. Kết quả của từng test được lưu cùng môi trường, dữ liệu và thời điểm.

**Bằng chứng và phát hiện:** `EVD-2026-041-03` liên kết tới báo cáo kết quả tính phí; `EVD-2026-041-04` liên kết tới truy vấn xác minh dữ liệu. Nếu một trường hợp sai, tạo lỗi, ghi mức độ ảnh hưởng và liên kết ngược tới `RISK-08`.

**Quyết định:** Người phụ trách đánh giá các test bắt buộc, lỗi còn mở và phần chưa kiểm tra. Quyết định tiếp tục, tạm dừng hoặc chấp nhận rủi ro được ghi lại cùng căn cứ và người chịu trách nhiệm.

Khi quy tắc tính phí thay đổi lần tiếp theo, nhóm có thể dùng các mã định danh để tìm nhanh những test, kế hoạch và bằng chứng bị ảnh hưởng. Kết quả cũ vẫn hữu ích cho lịch sử nhưng không được coi là bằng chứng cho phiên bản quy tắc mới nếu chưa đánh giá hoặc chạy lại.

## 11. Những lỗi thường gặp khi duy trì truy vết

- **Liên kết chỉ để hoàn thành biểu mẫu:** mã được điền nhưng không phản ánh quan hệ thực. Hãy kiểm tra bằng truy vết xuôi và ngược.
- **Chỉ liên kết yêu cầu với test:** bỏ qua rủi ro, kế hoạch, lần chạy và bằng chứng. Mở rộng liên kết tới quyết định và kết quả thực tế.
- **Dùng mã không ổn định:** đổi tên hoặc di chuyển tệp làm mất tham chiếu. Dùng định danh duy nhất tồn tại độc lập với tên hiển thị.
- **Đánh đồng test được thiết kế với test đã chạy:** báo cáo độ bao phủ cao hơn thực tế. Tách trạng thái thiết kế, thực thi và đạt.
- **Bằng chứng thiếu ngữ cảnh:** không biết build, môi trường hoặc dữ liệu nào tạo ra kết quả. Gắn bằng chứng với Run ID và phiên bản cụ thể.
- **Không cập nhật sau thay đổi:** liên kết trỏ tới yêu cầu hoặc test cũ. Đưa đánh giá tác động vào quy trình quản lý thay đổi.
- **Thu thập quá nhiều dữ liệu:** làm tăng chi phí lưu trữ và nguy cơ lộ thông tin. Chỉ giữ bằng chứng cần thiết, kiểm soát quyền và thời hạn lưu.
- **Dùng tỷ lệ tổng hợp làm quyết định duy nhất:** che khuất rủi ro trọng yếu. Phân tích theo mức độ quan trọng và nêu rõ khoảng trống.

## 12. Checklist rà soát trước khi chốt kết quả kiểm thử

- Mục tiêu, yêu cầu và rủi ro trọng yếu có định danh và chủ sở hữu rõ ràng.
- Mỗi rủi ro trọng yếu có cách kiểm soát hoặc quyết định chấp nhận rủi ro được ghi nhận.
- Các quyết định chiến lược liên quan đã được chuyển thành hoạt động trong kế hoạch.
- Test case có liên kết tới mục tiêu, yêu cầu hoặc rủi ro phù hợp.
- Lần chạy xác định được build, môi trường, dữ liệu, người hoặc pipeline thực hiện.
- Bằng chứng đủ để xác minh kết quả và không chứa thông tin nhạy cảm không cần thiết.
- Test chưa chạy, thất bại, bị bỏ qua hoặc được miễn đều có lý do và đánh giá tác động.
- Các thay đổi gần nhất đã được đánh giá ảnh hưởng tới kế hoạch, test và bằng chứng.
- Báo cáo nêu rõ rủi ro còn lại, giới hạn kiểm thử và người chịu trách nhiệm quyết định.

Khi các liên kết được duy trì từ lúc lập kế hoạch đến khi ra quyết định, chiến lược kiểm thử trở thành một phần của hoạt động phát triển và phát hành hằng ngày. Nhóm có thể giải thích vì sao đã chọn một kiểm thử, chứng minh nó đã được thực hiện trong điều kiện nào, và xác định chính xác điều gì còn chưa được bảo đảm.

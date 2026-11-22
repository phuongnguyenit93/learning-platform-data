# Điều chỉnh phạm vi theo nguồn lực và công khai rủi ro phát sinh

Trong một dự án kiểm thử, thời gian, nhân lực, môi trường, dữ liệu và ngân sách luôn có giới hạn. Một kế hoạch có thể yêu cầu kiểm tra hàng trăm luồng nghiệp vụ, nhiều nền tảng, nhiều phiên bản dịch vụ và các thuộc tính phi chức năng, trong khi nhóm chỉ có một số ngày trước mốc phát hành. Khi nguồn lực thay đổi, nhóm phải điều chỉnh phạm vi kiểm thử để tập trung vào những bằng chứng quan trọng nhất và công khai phần rủi ro còn lại.

Điều chỉnh phạm vi là quyết định quản lý rủi ro. Nó xác định những gì sẽ được kiểm tra, kiểm tra ở mức nào, dùng phương pháp nào, thời điểm nào và điều gì chưa thể xác minh. Quyết định tốt cần dựa trên mức độ quan trọng của hành vi, khả năng xảy ra lỗi, hậu quả, thay đổi trong phiên bản, bằng chứng đã có và chi phí để thu thập thêm bằng chứng. Quyết định cũng cần được truyền đạt cho người có thẩm quyền chấp nhận rủi ro.

Trong chiến lược kiểm thử, thiếu nguồn lực không làm rủi ro biến mất. Nếu một kịch bản không được chạy, một môi trường không được kiểm tra hoặc một thuộc tính chưa được đo, tổ chức cần biết khoảng trống đó và tác động có thể xảy ra. Việc ghi nhận rõ giúp đội ngũ lựa chọn có trách nhiệm, tránh tạo ấn tượng rằng toàn bộ phạm vi đã được xác minh.

## 1. Hiểu đúng phạm vi kiểm thử và nguồn lực

Phạm vi kiểm thử (test scope) mô tả những sản phẩm, thành phần, hành vi, yêu cầu, rủi ro, nền tảng và thuộc tính chất lượng sẽ được kiểm tra trong một giai đoạn cụ thể. Phạm vi thường được xác định trong kế hoạch kiểm thử và có thể thay đổi khi sản phẩm, rủi ro hoặc nguồn lực thay đổi.

Nguồn lực kiểm thử không chỉ là số người trong nhóm. Cần xem xét nhiều loại nguồn lực:

- **Thời gian:** thời gian phát triển, thời gian kiểm thử, cửa sổ triển khai, thời gian chờ môi trường và hạn chót phát hành.
- **Nhân lực và kỹ năng:** số người có thể tham gia, kiến thức nghiệp vụ, kỹ năng tự động hóa, bảo mật, hiệu năng và khả năng vận hành.
- **Môi trường:** môi trường tích hợp, staging, thiết bị, trình duyệt, sandbox, tài khoản và dịch vụ phụ thuộc.
- **Dữ liệu:** dữ liệu đại diện, dữ liệu biên, dữ liệu nhạy cảm đã được xử lý phù hợp và khả năng tạo/reset dữ liệu.
- **Công cụ và hạ tầng:** runner CI, thiết bị kiểm thử, license, hệ thống quan sát, lưu trữ artifact và năng lực tính toán.
- **Ngân sách:** chi phí cloud, thiết bị, dịch vụ bên thứ ba, chuyên gia và thời gian của các nhóm liên quan.
- **Quyền truy cập và phối hợp:** quyền triển khai, quyền truy cập hệ thống, lịch làm việc của nhóm phụ thuộc và thời gian phê duyệt.

Một kế hoạch chỉ ghi “có ba tester” chưa đủ để đánh giá năng lực. Ba người có thể cùng thiếu quyền truy cập môi trường hoặc không có chuyên môn kiểm thử bảo mật cần thiết. Ngược lại, một nhóm nhỏ có thể kiểm tra được phạm vi lớn nếu có test tự động ổn định, dữ liệu độc lập và pipeline đáng tin cậy.

### Phân biệt năng lực, công suất và nguồn lực sẵn có

- **Năng lực (capability):** nhóm có kỹ năng, công cụ và quyền cần thiết để thực hiện loại kiểm thử nào.
- **Công suất (capacity):** lượng công việc nhóm có thể hoàn thành trong một khoảng thời gian, sau khi tính thời gian họp, hỗ trợ, xử lý sự cố và công việc vận hành.
- **Nguồn lực sẵn có (availability):** thời gian hoặc tài nguyên thực sự có thể dành cho nhiệm vụ trong giai đoạn đó.

Ví dụ, một kỹ sư kiểm thử có thể có kỹ năng viết automation nhưng chỉ dành 30% thời gian cho dự án vì còn trực vận hành. Năng lực tồn tại nhưng công suất của dự án thấp hơn một người làm toàn thời gian.

## 2. Xác định phạm vi ban đầu trước khi điều chỉnh

Không thể đánh giá phần nào nên cắt nếu phạm vi ban đầu chưa rõ. Trước khi điều chỉnh, hãy tạo một danh sách các mục cần kiểm chứng và gắn chúng với yêu cầu hoặc rủi ro.

Một mục phạm vi có thể là:

- Một luồng nghiệp vụ, chẳng hạn tạo đơn, hoàn tiền hoặc phê duyệt.
- Một quy tắc hoặc nhóm điều kiện đầu vào.
- Một API hoặc hợp đồng tích hợp.
- Một nền tảng, phiên bản runtime, trình duyệt hoặc thiết bị.
- Một thuộc tính phi chức năng như hiệu năng, bảo mật, khả năng phục hồi hoặc khả năng truy cập.
- Một hoạt động như kiểm thử migration, backup/restore hoặc kiểm tra vận hành.

Với mỗi mục, ghi nhận:

1. Mục tiêu và hành vi cần xác minh.
2. Yêu cầu, người dùng hoặc quy trình chịu ảnh hưởng.
3. Rủi ro nếu hành vi sai.
4. Mức độ thay đổi trong phiên bản.
5. Test hoặc bằng chứng hiện có.
6. Phương pháp và môi trường cần thiết.
7. Ước lượng thời gian và nguồn lực.
8. Phụ thuộc và điều kiện tiên quyết.
9. Người chịu trách nhiệm.
10. Tiêu chí hoàn tất hoặc bằng chứng chấp nhận.

### Phân biệt phạm vi sản phẩm và phạm vi kiểm thử

Phạm vi sản phẩm là những chức năng hoặc thay đổi được đưa vào phiên bản. Phạm vi kiểm thử là phần bằng chứng nhóm sẽ thu thập cho phiên bản đó. Khi nguồn lực giảm, không tự động đồng nghĩa phải giảm chức năng sản phẩm. Có thể giảm mức kiểm tra, thay đổi phương pháp, hoãn một tính năng, chia đợt phát hành hoặc trì hoãn mốc phát hành. Mỗi lựa chọn có tác động khác nhau và cần được quyết định bởi người có thẩm quyền.

## 3. Lập danh mục công việc và ước lượng nguồn lực

Một danh sách test case riêng lẻ thường khó dùng để điều chỉnh phạm vi. Hãy nhóm công việc theo luồng, rủi ro hoặc mục tiêu chất lượng để có thể so sánh và ra quyết định.

Ví dụ:

| Nhóm công việc | Hoạt động | Nguồn lực chính |
|---|---|---|
| Nghiệp vụ thanh toán | Kiểm tra tính tiền, thanh toán, retry, hoàn tiền | Tester nghiệp vụ, API, sandbox, dữ liệu |
| Phân quyền | Kiểm tra vai trò, tenant và truy cập trái phép | Chuyên gia bảo mật, tài khoản và dữ liệu |
| Tích hợp | Kiểm tra API, message, database và webhook | Môi trường tích hợp, dịch vụ phụ thuộc |
| Hiệu năng | Load, stress, soak và phân tích bottleneck | Môi trường đại diện, công cụ tải, metric |
| Trình duyệt | Smoke và hồi quy giao diện | Browser runner, thiết bị, automation |
| Phát hành | Smoke, migration, rollback và xác nhận vận hành | Staging, DevOps, chủ sở hữu dịch vụ |

Ước lượng không nên chỉ dựa vào thời gian thực thi test. Tổng chi phí thường gồm chuẩn bị, thiết lập môi trường, tạo dữ liệu, thực hiện, điều tra lỗi, sửa test, chạy lại và lưu bằng chứng.

Có thể dùng mô hình đơn giản:

\[
T_{total}=T_{setup}+T_{execution}+T_{analysis}+T_{rerun}+T_{report}
\]

Đối với công việc cần nhiều vai trò, hãy ghi rõ phần thời gian của từng vai trò và thời điểm họ cần tham gia. Một kiểm thử bảo mật có thể chỉ chạy vài giờ nhưng cần nhiều ngày để sắp lịch chuyên gia, cấp quyền và khắc phục phát hiện.

### Ước lượng theo khoảng

Khi độ bất định cao, nên dùng khoảng thay vì một con số có vẻ chính xác. Ví dụ:

- Ước lượng thấp: 4 giờ nếu môi trường và dữ liệu sẵn sàng.
- Ước lượng thường gặp: 1 ngày nếu cần chuẩn bị và điều tra.
- Ước lượng cao: 2 ngày nếu dịch vụ phụ thuộc hoặc dữ liệu gặp sự cố.

Khoảng ước lượng giúp người quyết định hiểu rằng kế hoạch có thể thay đổi. Hãy ghi giả định đi kèm, chẳng hạn môi trường đã được provision, build đã ổn định và tài khoản kiểm thử được cấp trước.

## 4. Đánh giá ưu tiên dựa trên rủi ro

Khi không thể kiểm tra mọi thứ, hãy ưu tiên những mục có rủi ro cao và hậu quả đáng kể. Một cách phổ biến là đánh giá:

- **Khả năng xảy ra (likelihood):** lỗi có thể xuất hiện đến mức nào, xét thay đổi, độ phức tạp, lịch sử defect và độ mới của thành phần.
- **Tác động (impact):** hậu quả đối với người dùng, dữ liệu, tài chính, vận hành, bảo mật, pháp lý và uy tín.
- **Khả năng phát hiện (detectability):** lỗi có dễ được phát hiện trước khi gây ảnh hưởng không, qua monitoring, kiểm soát khác hoặc người dùng.
- **Mức độ bất định:** bằng chứng hiện có có đáng tin và có phù hợp với phiên bản này không.

Có thể dùng ma trận định tính để phân loại:

| Khả năng xảy ra | Tác động thấp | Tác động vừa | Tác động cao |
|---|---|---|---|
| Thấp | Thấp | Thấp/Vừa | Vừa |
| Vừa | Thấp/Vừa | Vừa | Cao |
| Cao | Vừa | Cao | Rất cao |

Đây là công cụ thảo luận, không phải phép đo xác suất chính xác. Nhóm cần định nghĩa tiêu chí cho từng mức và không nên để một điểm số tổng hợp che mất hậu quả đặc biệt nghiêm trọng. Ví dụ, một lỗi hiếm nhưng có thể làm lộ dữ liệu của tenant khác vẫn có thể cần ưu tiên cao.

### Các tín hiệu làm tăng ưu tiên

- Thay đổi mới hoặc tái cấu trúc lớn.
- Thành phần có nhiều defect trong quá khứ.
- Luồng ảnh hưởng đến thanh toán, dữ liệu, phân quyền hoặc thao tác không thể hoàn tác.
- Tích hợp với hệ thống ngoài hoặc giao thức không ổn định.
- Migration hoặc thay đổi schema.
- Logic đồng thời, retry, timeout và xử lý sự kiện.
- Tính năng được nhiều người dùng hoặc khách hàng quan trọng sử dụng.
- Thiếu monitoring hoặc khó khôi phục khi có lỗi.
- Yêu cầu pháp lý, hợp đồng hoặc chính sách nội bộ.

### Xác định phần có thể giảm mức kiểm tra

Các mục có thể được xem xét giảm mức kiểm tra khi:

- Hành vi ít thay đổi và có bằng chứng hồi quy đáng tin cậy.
- Tác động lỗi thấp và có cách phát hiện nhanh.
- Được bảo vệ bởi test ở tầng khác hoặc kiểm soát độc lập.
- Có thể khôi phục dễ dàng và không gây mất dữ liệu.
- Mức sử dụng thấp nhưng vẫn nằm trong phạm vi hỗ trợ.
- Chi phí kiểm thử cao hơn giá trị bằng chứng trong giai đoạn hiện tại.

“Có thể giảm” không có nghĩa là tự động bỏ. Cần ghi lý do, bằng chứng thay thế và điều kiện để kiểm tra lại.

## 5. Phân biệt giảm phạm vi, giảm chiều sâu và thay đổi phương pháp

Khi nguồn lực thiếu, có nhiều cách điều chỉnh. Mỗi cách làm giảm một loại bằng chứng khác nhau.

### Giảm phạm vi (scope reduction)

Không kiểm tra một số hành vi, nền tảng hoặc thuộc tính trong đợt hiện tại. Ví dụ, hoãn kiểm thử một báo cáo ít sử dụng hoặc một trình duyệt cũ vẫn nằm trong lịch hỗ trợ theo quý.

Đây là lựa chọn tạo ra khoảng trống rõ nhất. Cần ghi cụ thể mục nào không được kiểm tra và rủi ro phát sinh.

### Giảm chiều sâu (depth reduction)

Vẫn kiểm tra hành vi nhưng dùng ít kịch bản hơn, ít dữ liệu hơn hoặc giảm số vòng lặp. Ví dụ, chạy smoke test trên một tập luồng chính thay vì hồi quy toàn bộ.

Giảm chiều sâu có thể bỏ qua trường hợp biên hoặc tương tác hiếm. Hãy nêu rõ các lớp dữ liệu và nhánh chưa được kiểm tra.

### Thay đổi phương pháp (method substitution)

Thay phương pháp tốn kém bằng phương pháp rẻ hơn nhưng vẫn tạo được một phần bằng chứng. Ví dụ:

- Chạy API test thay cho một số kịch bản E2E khi mục tiêu là kiểm tra quy tắc nghiệp vụ.
- Dùng contract test để xác nhận schema trước khi có môi trường tích hợp đầy đủ.
- Dùng phân tích tĩnh để phát hiện một số lỗi trước khi chạy kiểm thử động.
- Dùng dữ liệu mô phỏng cho kiểm tra logic, sau đó giữ một số test với phụ thuộc thật ở ranh giới quan trọng.
- Dùng smoke test tự động trên thiết bị đại diện và thực hiện kiểm tra thủ công có mục tiêu trên thiết bị đặc biệt.

Phương pháp thay thế không tương đương hoàn toàn. Ví dụ, API test không chứng minh người dùng có thể hoàn thành luồng qua giao diện; contract test không chứng minh mạng, cấu hình và giao dịch thật hoạt động. Báo cáo cần nêu phần bằng chứng được thay thế và phần còn thiếu.

### Chia phạm vi theo đợt

Một số kiểm tra có thể chuyển sang đợt tiếp theo hoặc lịch chạy sau phát hành nếu rủi ro và chính sách cho phép. Cần phân biệt rõ:

- Chưa kiểm tra trước phát hành.
- Sẽ kiểm tra sau triển khai.
- Được theo dõi bằng monitoring hoặc kiểm soát khác.
- Được chấp nhận tạm thời bởi người có thẩm quyền.
- Không còn nằm trong phạm vi hỗ trợ.

Không gọi một test là “đã hoàn thành” nếu nó chỉ được lên lịch cho tương lai.

## 6. Bảo vệ các kiểm tra không nên cắt

Một số kiểm tra cần được giữ ngay cả khi nguồn lực bị giới hạn, vì hậu quả nếu bỏ qua có thể quá lớn. Tùy sản phẩm, nhóm nên xem xét các nhóm sau:

- Luồng đăng nhập, xác thực và phân quyền cốt lõi.
- Cách ly dữ liệu giữa người dùng, tenant hoặc tổ chức.
- Thanh toán, hoàn tiền, tính tiền và đối soát.
- Tạo, cập nhật, xóa và khôi phục dữ liệu quan trọng.
- Migration, backup/restore và khả năng tương thích dữ liệu.
- Xử lý retry, idempotency, timeout và sự kiện trùng.
- Các yêu cầu bảo mật hoặc pháp lý bắt buộc.
- Luồng nghiệp vụ quan trọng nhất của người dùng.
- Smoke test và khả năng rollback của bản phát hành.

Danh sách này không phải quy tắc cứng cho mọi hệ thống. Nhóm phải xác định kiểm tra trọng yếu dựa trên kiến trúc và tác động thực tế. Một sản phẩm y tế, tài chính, thương mại điện tử hoặc công cụ nội bộ có các rủi ro khác nhau.

### Dùng tầng kiểm thử để giữ bằng chứng với chi phí phù hợp

Nếu không đủ thời gian chạy nhiều E2E, có thể giữ:

- Unit test cho các quy tắc và trường hợp biên.
- API/contract test cho hợp đồng và quyền truy cập.
- Integration test cho giao dịch và phụ thuộc quan trọng.
- Một số E2E cho hành trình người dùng trọng yếu.
- Kiểm tra thủ công có mục tiêu cho những điều khó tự động hóa.

Mục tiêu là giữ bằng chứng cho các ranh giới rủi ro chính. Không nên chỉ cắt tầng cao mà không xác nhận các tầng thấp có thực sự bao phủ rủi ro liên quan.

## 7. Tối ưu kế hoạch theo thời gian và công suất

Một kế hoạch có thể được chia thành các nhóm ưu tiên để đội ngũ biết việc nào cần hoàn thành trước khi đưa ra quyết định phát hành.

### Phân nhóm ưu tiên

| Nhóm | Mô tả | Cách xử lý |
|---|---|---|
| P0 - Bắt buộc | Rủi ro nghiêm trọng, yêu cầu bắt buộc hoặc điều kiện phát hành | Phải có bằng chứng đạt hoặc quyết định dừng/hoãn |
| P1 - Cao | Luồng quan trọng, thay đổi lớn, tác động đáng kể | Hoàn thành trước release candidate nếu có thể |
| P2 - Trung bình | Rủi ro vừa, có biện pháp phát hiện/khôi phục | Chạy theo thời gian còn lại hoặc theo lịch |
| P3 - Thấp | Tác động thấp, ít sử dụng, ít thay đổi | Có thể giảm tần suất hoặc đưa vào lịch định kỳ |

Mức ưu tiên cần có tiêu chí cụ thể. Không nên dùng P0/P1 chỉ theo ý kiến cá nhân mà không liên hệ với hậu quả và cam kết.

### Lập lịch ngược từ mốc quyết định

Bắt đầu từ thời điểm cần quyết định phát hành, sau đó phân bổ thời gian cho:

1. Chuẩn bị build và môi trường.
2. Chạy kiểm thử bắt buộc.
3. Điều tra và phân loại lỗi.
4. Sửa lỗi và chạy lại.
5. Kiểm thử hồi quy sau sửa.
6. Đánh giá rủi ro còn lại và phê duyệt.

Nếu kế hoạch không dành thời gian cho điều tra và chạy lại, một lỗi phát hiện vào cuối kỳ có thể không được xử lý kịp. Hãy giữ buffer cho sự cố môi trường và thay đổi bất ngờ.

### Tính công suất thực tế

Ví dụ, nhóm có 3 người trong 5 ngày làm việc. Mỗi người dành trung bình 6 giờ/ngày cho nhiệm vụ kiểm thử sau khi trừ họp, hỗ trợ và công việc khác:

\[
Capacity = 3 \times 5 \times 6 = 90\text{ giờ}
\]

Nếu danh mục kiểm thử ước lượng 110 giờ, thiếu 20 giờ. Nhóm không nên giả định làm thêm giờ sẽ tự động bù đủ. Cần xác định phần nào có thể rút ngắn, chuyển phương pháp, bổ sung người có kỹ năng phù hợp hoặc điều chỉnh thời hạn/phạm vi.

### Theo dõi công việc đang bị chặn

Công suất có thể bị tiêu hao bởi các việc chờ:

- Chưa có build ổn định.
- Thiếu dữ liệu hoặc tài khoản.
- Môi trường chưa sẵn sàng.
- Chờ nhóm khác triển khai hoặc sửa lỗi.
- Chờ quyền truy cập hoặc phê duyệt.
- Runner CI hoặc sandbox bị giới hạn.

Ghi thời gian chờ và nguyên nhân giúp phân biệt thiếu nhân lực với nút thắt phụ thuộc. Nếu môi trường thường xuyên sẵn sàng muộn, thêm tester có thể không cải thiện thời gian hoàn thành.

## 8. Đánh giá các phương án điều chỉnh

Không nên đưa ra một quyết định cắt phạm vi duy nhất khi có nhiều lựa chọn. Hãy so sánh các phương án theo chi phí, bằng chứng, rủi ro còn lại và tác động đến mốc phát hành.

Ví dụ:

| Phương án | Nguồn lực/chi phí | Bằng chứng thu được | Rủi ro còn lại |
|---|---|---|---|
| Chạy full regression | Cao | Rộng trên các luồng và môi trường đã chọn | Có thể vẫn thiếu tổ hợp ngoài ma trận |
| Chạy smoke + test rủi ro cao | Thấp hơn | Tập trung vào hành vi trọng yếu | Ít bằng chứng cho nhánh ít dùng và trường hợp biên |
| Chuyển một phần E2E thành API/integration | Trung bình | Tốt cho hợp đồng và logic ở ranh giới dịch vụ | Ít bằng chứng về trải nghiệm UI xuyên suốt |
| Thuê chuyên gia kiểm thử bảo mật ngắn hạn | Tăng chi phí tiền mặt, giảm thời gian thiếu kỹ năng | Bằng chứng chuyên sâu cho phạm vi được giao | Không bao phủ toàn bộ sản phẩm nếu phạm vi giới hạn |
| Hoãn phát hành để hoàn tất test | Tăng thời gian phát hành | Có thêm thời gian cho kiểm tra và sửa lỗi | Tác động lịch kinh doanh và phụ thuộc |
| Phát hành theo nhóm người dùng nhỏ | Cần năng lực rollout/monitoring | Bằng chứng production trong phạm vi giới hạn | Rủi ro vẫn tồn tại và cần khả năng rollback |

Bảng là ví dụ định hướng. Phương án tốt nhất phụ thuộc vào hậu quả lỗi, chi phí trì hoãn, khả năng giám sát và năng lực khôi phục.

### Tìm phương án giảm chi phí nhưng giữ bằng chứng

Trước khi bỏ một kiểm tra, hãy xem có thể:

- Tự động hóa bước lặp lại đang làm thủ công.
- Chạy song song khi dữ liệu và môi trường được cô lập.
- Dùng test ở tầng thấp hơn cho các quy tắc phù hợp.
- Tái sử dụng fixture và môi trường đã chuẩn hóa.
- Chỉ chạy nhóm test bị ảnh hưởng bởi thay đổi.
- Dùng smoke test để sàng lọc trước bộ hồi quy dài.
- Tách nhóm test độc lập để chạy theo lịch.
- Bổ sung log và trace để giảm thời gian điều tra.
- Dùng kiểm thử theo phiên hoặc thăm dò có mục tiêu cho vùng bất định.

Không nên tối ưu thời gian bằng cách chạy song song trên dữ liệu dùng chung hoặc bỏ qua bước chuẩn bị. Điều đó có thể làm kết quả không đáng tin và tạo thêm thời gian điều tra.

## 9. Công khai rủi ro phát sinh khi điều chỉnh

Mỗi thay đổi phạm vi đều có thể tạo ra hoặc làm tăng rủi ro còn lại. Rủi ro phải được mô tả cụ thể, tránh các câu chung chung như “có thể còn lỗi”.

Một bản ghi rủi ro nên gồm:

- **ID và tên:** định danh duy nhất, dễ tham chiếu.
- **Mô tả:** điều gì có thể xảy ra, trong điều kiện nào.
- **Nguyên nhân:** vì sao rủi ro tồn tại, ví dụ một kịch bản chưa được chạy.
- **Hậu quả:** ảnh hưởng đến người dùng, dữ liệu, tài chính, bảo mật hoặc vận hành.
- **Khả năng và mức độ:** đánh giá theo tiêu chí thống nhất.
- **Bằng chứng hiện có:** test đã chạy, monitoring, lịch sử lỗi hoặc kiểm soát khác.
- **Khoảng trống:** điều gì chưa được xác minh.
- **Biện pháp giảm thiểu:** kiểm soát có thể áp dụng trước hoặc sau phát hành.
- **Chủ sở hữu:** người theo dõi và xử lý.
- **Người chấp nhận:** vai trò có thẩm quyền chấp nhận rủi ro.
- **Thời hạn xem xét:** khi nào cần kiểm tra lại.
- **Trạng thái:** mở, đang giảm thiểu, được chấp nhận tạm thời, đã đóng hoặc đã xảy ra.

### Mô tả rủi ro theo điều kiện và hậu quả

Cấu trúc hữu ích:

> Do [nguyên nhân hoặc khoảng trống], trong [điều kiện], có thể xảy ra [sự kiện], dẫn đến [hậu quả].

Ví dụ:

> Do chưa chạy hồi quy trên PostgreSQL 14 sau thay đổi migration, khi khách hàng nâng cấp từ schema cũ, migration có thể thất bại hoặc chuyển đổi dữ liệu không đầy đủ, dẫn đến gián đoạn nâng cấp và cần khôi phục thủ công.

Mô tả này hữu ích hơn “rủi ro database” vì nó cho biết điều gì chưa được kiểm tra, tình huống nào có thể kích hoạt và hậu quả có thể xảy ra.

### Không che giấu bằng cách đổi tên trạng thái

Một test bị bỏ qua vì thiếu thời gian vẫn là chưa chạy. Không đổi trạng thái thành pass, không tính nó vào coverage như đã đạt và không ghi “đã xác minh” nếu chỉ có kế hoạch thực hiện. Báo cáo cần phân biệt:

- Passed: đã chạy và đạt tiêu chí.
- Failed: đã chạy và không đạt.
- Blocked: không thể chạy vì điều kiện phụ thuộc.
- Not run: chưa thực hiện.
- Skipped: được bỏ qua có chủ đích theo quyết định.
- Not applicable: không áp dụng theo phạm vi được xác định.

Nếu một test được thay bằng phương pháp khác, ghi cả test gốc chưa chạy và bằng chứng thay thế, kèm giới hạn của phương pháp thay thế.

## 10. Truyền đạt rủi ro cho đúng người

Rủi ro không chỉ là vấn đề của nhóm kiểm thử. Người quản lý sản phẩm, chủ sở hữu nghiệp vụ, kỹ thuật, vận hành, bảo mật và người có quyền phát hành có thể cần thông tin khác nhau.

### Người ra quyết định cần biết gì?

Một báo cáo ngắn cho người quyết định nên trả lời:

1. Phạm vi ban đầu là gì?
2. Nguồn lực thực tế còn bao nhiêu và thiếu ở đâu?
3. Những mục nào đã hoàn thành, chưa chạy hoặc bị chặn?
4. Phương án điều chỉnh nào được đề xuất và vì sao?
5. Rủi ro mới hoặc rủi ro tăng thêm là gì?
6. Có biện pháp giảm thiểu hoặc rollback nào?
7. Ai có thẩm quyền chấp nhận rủi ro?
8. Quyết định cần được đưa ra trước thời điểm nào?

Không gửi một danh sách test case dài mà thiếu tác động. Hãy chuyển thông tin kỹ thuật thành hậu quả có thể hiểu: ví dụ “chưa xác minh luồng hoàn tiền khi webhook đến trễ; có thể ghi nhận sai trạng thái giao dịch và cần đối soát thủ công”.

### Công khai sớm và cập nhật khi có thay đổi

Không chờ đến cuộc họp phát hành mới báo rằng thiếu nguồn lực. Khi thấy một mốc có nguy cơ không đạt, thông báo sớm với dữ liệu hiện có, giả định và lựa chọn. Cập nhật khi:

- Ước lượng thay đổi đáng kể.
- Một phụ thuộc bị chậm.
- Một test trọng yếu thất bại.
- Có thêm nguồn lực hoặc môi trường.
- Rủi ro được giảm thiểu hoặc xuất hiện mới.
- Phương án phát hành thay đổi.

Thông tin cần có thời điểm cập nhật để người đọc biết báo cáo còn mới hay không.

## 11. Quy trình phê duyệt và chấp nhận rủi ro

Nhóm kiểm thử có trách nhiệm đưa ra bằng chứng và khuyến nghị, nhưng không phải lúc nào cũng có thẩm quyền chấp nhận mọi rủi ro kinh doanh. Cần xác định người có quyền quyết định theo chính sách tổ chức.

Một quy trình điển hình:

1. Tester hoặc test lead phát hiện nguồn lực thiếu hoặc một phạm vi không thể hoàn thành.
2. Nhóm phân tích các lựa chọn: bổ sung nguồn lực, thay phương pháp, giảm phạm vi, chia đợt hoặc hoãn mốc.
3. Test lead cập nhật kế hoạch và danh sách rủi ro, ghi rõ phần bằng chứng còn thiếu.
4. Chủ sở hữu kỹ thuật và nghiệp vụ đánh giá hậu quả, biện pháp giảm thiểu.
5. Người có thẩm quyền quyết định chấp nhận, yêu cầu giảm thiểu thêm, hoãn hoặc không phát hành.
6. Quyết định được ghi nhận cùng người phê duyệt, ngày, điều kiện và thời hạn.
7. Nhóm triển khai biện pháp đã thống nhất và theo dõi rủi ro.
8. Khi có bằng chứng mới, xem xét lại quyết định.

### Chấp nhận rủi ro không có nghĩa là xóa rủi ro

Một rủi ro được chấp nhận vẫn có thể xảy ra. Bản ghi cần giữ:

- Lý do chấp nhận.
- Người có thẩm quyền và phạm vi quyết định.
- Phiên bản hoặc khoảng thời gian áp dụng.
- Biện pháp giám sát và ứng phó.
- Điều kiện làm quyết định hết hiệu lực.
- Thời điểm bắt buộc đánh giá lại.

Không dùng một phê duyệt chung cho mọi phiên bản tương lai nếu rủi ro, kiến trúc hoặc phạm vi thay đổi.

### Những điều kiện không nên được bỏ qua

Một số tổ chức có yêu cầu pháp lý, hợp đồng, bảo mật hoặc an toàn bắt buộc. Không thể tự ý giảm các kiểm tra này chỉ bằng một quyết định của test lead. Khi thiếu năng lực thực hiện, cần báo đúng chủ sở hữu và tuân theo cơ chế ngoại lệ được phê duyệt. Nếu không có cơ chế hợp lệ, lựa chọn có thể là hoãn phát hành hoặc thay đổi phạm vi sản phẩm.

## 12. Thiết kế biện pháp giảm thiểu cho phần chưa kiểm tra

Khi một mục chưa thể được kiểm tra đầy đủ, có thể dùng các biện pháp khác để giảm khả năng hoặc hậu quả của lỗi. Biện pháp cần phù hợp với rủi ro và có người chịu trách nhiệm.

Ví dụ:

| Khoảng trống kiểm thử | Biện pháp giảm thiểu có thể cân nhắc |
|---|---|
| Chưa kiểm tra hết tổ hợp trình duyệt | Giới hạn rollout, theo dõi lỗi client và giữ smoke test trên browser đại diện |
| Chưa chạy kiểm thử tải đầy đủ | Giới hạn traffic ban đầu, theo dõi latency/error rate, chuẩn bị capacity rollback |
| Chưa xác minh toàn bộ migration | Backup, rehearsal trên bản sao dữ liệu đại diện, kiểm tra restore và có kế hoạch rollback |
| Chưa kiểm tra mọi tình huống webhook | Idempotency, reconciliation job, log giao dịch và cảnh báo sự kiện tồn đọng |
| Chưa kiểm thử hết quyền theo vai trò | Giữ kiểm soát authorization ở server, rà soát policy và monitoring truy cập bất thường |
| Chưa chạy toàn bộ E2E | Giữ API/integration cho ranh giới trọng yếu, smoke trên hành trình chính và kiểm tra thủ công có mục tiêu |

Biện pháp giảm thiểu không tự động tương đương với kiểm thử. Ví dụ monitoring có thể phát hiện lỗi sau phát hành nhưng không ngăn lỗi xảy ra. Backup giúp khôi phục dữ liệu nhưng không chứng minh migration không gây gián đoạn. Cần nêu rõ biện pháp giảm xác suất, giảm tác động hay chỉ cải thiện khả năng phát hiện.

### Chuẩn bị kế hoạch ứng phó

Với rủi ro có hậu quả lớn, hãy xác định trước:

- Tín hiệu nào kích hoạt cảnh báo hoặc dừng rollout.
- Ai nhận cảnh báo và ai có quyền hành động.
- Cách giới hạn ảnh hưởng hoặc tắt tính năng.
- Cách rollback hoặc khôi phục.
- Cách xác minh sau khôi phục.
- Cách thông báo cho người dùng hoặc nhóm liên quan.

Một kế hoạch ứng phó chỉ hữu ích nếu đã được kiểm tra ở mức phù hợp và có thể thực hiện trong điều kiện thực tế.

## 13. Sử dụng rollout có kiểm soát để bổ sung bằng chứng

Khi sản phẩm hỗ trợ triển khai từng phần, có thể dùng canary, feature flag hoặc progressive delivery để giới hạn số người dùng chịu ảnh hưởng ban đầu. Đây là một biện pháp giảm thiểu sau khi kiểm thử, không thay thế việc xác minh trước phát hành.

Một quy trình rollout có thể gồm:

1. Triển khai cho môi trường nội bộ hoặc nhóm người dùng thử nghiệm.
2. Xác nhận smoke và các chỉ số vận hành.
3. Mở rộng cho một tỷ lệ nhỏ người dùng.
4. Theo dõi lỗi, latency, tỷ lệ giao dịch thất bại và các chỉ số nghiệp vụ.
5. Mở rộng từng bước khi đạt ngưỡng.
6. Dừng hoặc rollback nếu tín hiệu vượt ngưỡng.
7. Hoàn tất mở rộng và tiếp tục giám sát.

Cần xác định ngưỡng trước khi rollout. Ví dụ: tỷ lệ lỗi 5xx, độ trễ p95, tỷ lệ thanh toán thất bại hoặc số sự kiện tồn đọng. Ngưỡng cần dựa trên baseline và mức chịu đựng của sản phẩm, không chọn tùy tiện.

Nếu không có telemetry đáng tin cậy, rollback nhanh hoặc người trực theo dõi, rollout nhỏ có thể chỉ chuyển rủi ro sang production mà không kiểm soát được nó.

## 14. Theo dõi tiến độ và rủi ro trong suốt giai đoạn

Kế hoạch điều chỉnh cần được theo dõi như một phần của công việc phát hành. Một bảng theo dõi tối thiểu có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| Work item | Hành vi, test suite hoặc môi trường |
| Priority | Mức ưu tiên theo rủi ro |
| Planned scope | Phạm vi dự kiến ban đầu |
| Current scope | Phạm vi sau điều chỉnh |
| Status | Passed, failed, blocked, not run, skipped hoặc N/A |
| Evidence | Link report, log, trace hoặc artifact |
| Effort remaining | Công sức còn lại |
| Dependency | Điều kiện hoặc nhóm đang chờ |
| Risk ID | Rủi ro liên quan |
| Owner | Người thực hiện hoặc theo dõi |
| Decision | Quyết định và người phê duyệt |

### Chỉ số giúp nhận biết kế hoạch đang lệch

- Tỷ lệ test trọng yếu đã hoàn thành.
- Số mục bị block và thời gian bị block.
- Công suất còn lại so với công việc chưa hoàn thành.
- Thời gian điều tra và sửa lỗi.
- Tỷ lệ test flaky hoặc phải chạy lại.
- Số rủi ro mở theo mức độ.
- Số ngoại lệ đang chờ quyết định.
- Số mục chưa kiểm tra trước mốc phát hành.

Không nên chỉ dùng tổng số test pass làm chỉ số thành công. Một nhóm có thể đạt tỷ lệ pass cao vì đã bỏ nhiều test khó chạy. Cần đọc tỷ lệ đó cùng mẫu số, trạng thái skip, phạm vi và rủi ro chưa được kiểm tra.

## 15. Ví dụ thực hành: thiếu nguồn lực trước đợt phát hành thanh toán

Giả sử một phiên bản thương mại điện tử có thay đổi ở tính tiền, tích hợp cổng thanh toán và giao diện checkout. Kế hoạch ban đầu cần 120 giờ kiểm thử trong tuần cuối, nhưng nhóm chỉ còn 80 giờ do một thành viên nghỉ và sandbox thanh toán bị gián đoạn.

### Phạm vi ban đầu

| Nhóm | Ước lượng | Rủi ro |
|---|---:|---|
| Unit test tính tiền, thuế và chiết khấu | 16 giờ | Cao |
| API và integration thanh toán | 24 giờ | Rất cao |
| E2E checkout và xác nhận đơn | 20 giờ | Cao |
| Hồi quy trình duyệt | 16 giờ | Vừa |
| Kiểm tra retry, webhook và hoàn tiền | 20 giờ | Rất cao |
| Kiểm tra hiệu năng checkout | 12 giờ | Cao |
| Kiểm tra smoke và rollback | 12 giờ | Cao |
| **Tổng** | **120 giờ** | |

Nguồn lực sẵn có là 80 giờ. Chênh lệch 40 giờ cần được giải quyết rõ ràng.

### Phân tích lựa chọn

Nhóm không cắt đều từng mục 1/3 vì các mục có rủi ro khác nhau. Một phương án đề xuất:

- Giữ unit test tính tiền và các trường hợp biên.
- Ưu tiên API/integration cho idempotency, trạng thái giao dịch và quyền truy cập.
- Giữ một E2E cho hành trình checkout chính.
- Giảm hồi quy trình duyệt xuống smoke trên browser chuẩn, đưa phần còn lại vào nightly.
- Giữ một số kiểm tra webhook trùng, đến trễ và retry với môi trường mô phỏng; ghi rõ sandbox chưa xác minh được phần nào.
- Chạy kiểm tra hiệu năng mục tiêu trên checkout với tải đại diện thấp hơn, ghi rõ giới hạn của phép đo.
- Giữ smoke, backup/rollback và xác nhận vận hành.

Phương án này có thể phân bổ 80 giờ như sau:

| Nhóm | Giờ sau điều chỉnh | Quyết định |
|---|---:|---|
| Unit test tính tiền | 14 | Giảm nhẹ nhưng giữ trường hợp biên |
| API/integration thanh toán | 20 | Ưu tiên hành vi giao dịch và quyền |
| E2E checkout | 10 | Giữ hành trình chính |
| Hồi quy trình duyệt | 5 | Smoke trên browser chuẩn |
| Retry, webhook, hoàn tiền | 15 | Giữ kịch bản rủi ro cao; một số xác minh sandbox bị chặn |
| Hiệu năng checkout | 7 | Kiểm tra mục tiêu, phạm vi tải hạn chế |
| Smoke và rollback | 9 | Giữ điều kiện phát hành |
| **Tổng** | **80** | |

Các con số chỉ minh họa cách lập phương án; nhóm cần ước lượng lại dựa trên năng lực thực tế và điều kiện môi trường.

### Ghi nhận rủi ro còn lại

| Rủi ro | Khoảng trống | Giảm thiểu | Quyết định cần có |
|---|---|---|---|
| R-01: Tương thích browser | Chưa hồi quy đầy đủ trên mọi browser hỗ trợ | Smoke trên browser chuẩn, theo dõi lỗi client, nightly khi browser runner sẵn sàng | Chủ sản phẩm chấp nhận phạm vi kiểm tra giảm cho đợt này |
| R-02: Webhook thật | Sandbox không ổn định, chưa xác minh đầy đủ callback bên ngoài | Test logic với mô phỏng, giữ idempotency, reconciliation và cảnh báo | Chủ dịch vụ thanh toán đánh giá khả năng phát hành hoặc yêu cầu hoãn |
| R-03: Hiệu năng đỉnh | Không đủ thời gian chạy tải cực đại và soak dài | Giới hạn rollout, theo dõi latency/error rate, chuẩn bị scale/rollback | Chủ kỹ thuật xác nhận ngưỡng vận hành |
| R-04: Hoàn tiền | Chỉ chạy một phần biến thể | Giữ kiểm tra API trọng yếu, đối soát giao dịch và theo dõi sau phát hành | Chủ nghiệp vụ xác nhận rủi ro còn lại |

### Quyết định phát hành

Test lead cung cấp báo cáo về 80 giờ công suất, các kiểm tra đã đạt, phần chưa chạy và các rủi ro. Chủ sở hữu thanh toán, sản phẩm và kỹ thuật đánh giá. Nếu webhook thật là điều kiện bắt buộc theo hợp đồng hoặc chính sách, không thể dùng một phê duyệt chung để bỏ qua; cần chờ sandbox hoặc thay đổi kế hoạch phát hành theo quy trình ngoại lệ hợp lệ.

Nếu được phép rollout giới hạn, nhóm phải xác định tỷ lệ mở ban đầu, chỉ số theo dõi, người trực, ngưỡng dừng và phương án rollback trước khi mở traffic. Sau khi sandbox phục hồi, các kiểm tra bị chặn cần được chạy và kết quả cập nhật vào hồ sơ phiên bản.

## 16. Những sai lầm thường gặp khi điều chỉnh phạm vi

- **Cắt đều mọi nhóm test:** bỏ qua sự khác biệt về tác động và xác suất lỗi.
- **Chỉ nhìn số lượng test:** không phản ánh độ sâu, chất lượng dữ liệu hoặc mức rủi ro được bao phủ.
- **Giảm kiểm thử bảo mật hoặc dữ liệu mà không đánh giá thẩm quyền:** có thể vi phạm yêu cầu bắt buộc.
- **Gọi test bị bỏ qua là pass:** làm sai lệch báo cáo và quyết định phát hành.
- **Dùng monitoring thay cho kiểm thử:** monitoring thường phát hiện sau khi lỗi đã ảnh hưởng người dùng.
- **Dùng mock thay cho mọi kiểm tra thật:** có thể bỏ sót sai lệch giao tiếp, cấu hình và giao dịch.
- **Không tính thời gian điều tra và chạy lại:** kế hoạch không có buffer cho lỗi phát hiện muộn.
- **Giả định làm thêm giờ giải quyết mọi thiếu hụt:** bỏ qua mệt mỏi, chất lượng và kỹ năng cần thiết.
- **Không công khai rủi ro cho người quyết định:** người phê duyệt không hiểu phần bằng chứng còn thiếu.
- **Chấp nhận rủi ro không có thời hạn:** ngoại lệ tạm thời trở thành vĩnh viễn.
- **Không gắn rủi ro với owner:** không ai chịu trách nhiệm theo dõi và đóng rủi ro.
- **Không cập nhật sau khi điều kiện thay đổi:** báo cáo nhanh chóng lỗi thời.

## 17. Mẫu ghi nhận điều chỉnh phạm vi và rủi ro

Có thể dùng mẫu sau trong test plan, release note nội bộ hoặc báo cáo readiness:

~~~text
Mã quyết định:
Phiên bản / mốc phát hành:
Ngày cập nhật:
Người đề xuất:
Người phê duyệt:

1. Lý do điều chỉnh
- Nguồn lực thiếu:
- Phụ thuộc hoặc môi trường bị chặn:
- Thay đổi lịch hoặc phạm vi sản phẩm:

2. Phạm vi ban đầu
- Các nhóm kiểm thử dự kiến:
- Tiêu chí hoàn tất:

3. Phạm vi sau điều chỉnh
- Giữ nguyên:
- Giảm chiều sâu:
- Chuyển phương pháp:
- Hoãn hoặc bỏ khỏi đợt hiện tại:

4. Bằng chứng
- Passed:
- Failed:
- Blocked:
- Not run / Skipped:
- Phương pháp thay thế và giới hạn:

5. Rủi ro còn lại
- ID:
- Điều kiện kích hoạt:
- Hậu quả:
- Mức độ:
- Biện pháp giảm thiểu:
- Owner:
- Người chấp nhận:
- Hạn xem xét:

6. Điều kiện phát hành
- Điều kiện bắt buộc:
- Ngưỡng theo dõi:
- Điều kiện dừng rollout:
- Kế hoạch rollback:
- Mốc chạy bù:

7. Quyết định
- Chấp nhận / yêu cầu giảm thiểu / hoãn / không phát hành:
- Người quyết định:
- Thời điểm:
- Phạm vi hiệu lực:
~~~

Mẫu cần được điều chỉnh theo quy trình quản trị của tổ chức. Không lưu thông tin nhạy cảm hoặc dữ liệu người dùng trong tài liệu rủi ro nếu không cần thiết.

## 18. Danh sách kiểm tra trước khi chốt phạm vi

**Nguồn lực và ước lượng**

- Đã xác định thời gian, công suất, kỹ năng, môi trường, dữ liệu và quyền truy cập chưa?
- Ước lượng đã tính setup, thực thi, điều tra, sửa lỗi, chạy lại và báo cáo chưa?
- Các giả định và phụ thuộc có được ghi rõ không?
- Có buffer cho sự cố và thay đổi bất ngờ không?

**Ưu tiên và phương án**

- Mỗi mục phạm vi có liên kết với yêu cầu hoặc rủi ro không?
- Các luồng dữ liệu, phân quyền, thanh toán và điều kiện bắt buộc đã được đánh giá chưa?
- Đã so sánh giảm phạm vi, giảm chiều sâu, thay phương pháp và chia đợt chưa?
- Phương án thay thế có nêu rõ giới hạn bằng chứng không?
- Các mục bị hoãn có thời điểm hoặc điều kiện chạy lại không?

**Rủi ro và quyết định**

- Mỗi khoảng trống có mô tả điều kiện và hậu quả cụ thể không?
- Có bằng chứng hiện có và biện pháp giảm thiểu không?
- Owner và người có thẩm quyền chấp nhận đã rõ chưa?
- Ngoại lệ có thời hạn và điều kiện xem xét lại không?
- Yêu cầu pháp lý, hợp đồng và bảo mật có được xử lý đúng quy trình không?

**Truyền đạt và theo dõi**

- Người ra quyết định đã nhận báo cáo trước thời điểm cần quyết định chưa?
- Passed, failed, blocked, not run, skipped và N/A có được phân biệt không?
- Báo cáo có ghi phiên bản, thời điểm và nguồn bằng chứng không?
- Có chỉ số theo dõi sau phát hành và điều kiện dừng/rollback không?
- Kế hoạch được cập nhật khi nguồn lực hoặc môi trường thay đổi không?

## Kết luận

Điều chỉnh phạm vi theo nguồn lực là một quyết định dựa trên rủi ro, bằng chứng và công suất thực tế. Nhóm cần hiểu rõ phạm vi ban đầu, xác định nguồn lực và phụ thuộc, ưu tiên các hành vi có hậu quả lớn, rồi so sánh việc giảm phạm vi, giảm chiều sâu, thay phương pháp hoặc chia đợt. Mọi khoảng trống phải được ghi nhận trung thực, gắn với hậu quả, biện pháp giảm thiểu, owner và người có thẩm quyền chấp nhận. Khi thông tin được công khai sớm và cập nhật theo bằng chứng, tổ chức có thể đưa ra quyết định phát hành có hiểu biết, theo dõi rủi ro còn lại và bổ sung kiểm thử đúng thời điểm.

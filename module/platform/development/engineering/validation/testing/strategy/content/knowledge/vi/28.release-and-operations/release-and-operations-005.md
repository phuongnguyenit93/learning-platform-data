# Lựa chọn smoke sau triển khai và kiểm tra mức sẵn sàng vận hành

## 1. Mục tiêu và khái niệm

Sau khi một phiên bản được triển khai, nhóm phát triển cần xác nhận nhanh rằng dịch vụ đã khởi động, có thể nhận lưu lượng và những luồng quan trọng nhất vẫn hoạt động. Smoke test sau triển khai (post-deployment smoke test) là tập hợp nhỏ các phép kiểm tra đại diện, chạy ngay sau khi phát hành để phát hiện lỗi nghiêm trọng như ứng dụng không khởi động, cấu hình sai, không kết nối được cơ sở dữ liệu hoặc người dùng không thể hoàn thành tác vụ cốt lõi.

Smoke test trả lời câu hỏi: **phiên bản vừa triển khai có hoạt động đủ tốt để tiếp tục phục vụ và chuyển sang giai đoạn theo dõi hay không?** Nó không chứng minh toàn bộ chức năng đều đúng và không thay thế kiểm thử hồi quy, kiểm thử hiệu năng, kiểm thử bảo mật hoặc kiểm thử chấp nhận.

Kiểm tra mức sẵn sàng vận hành (operational readiness check) có phạm vi rộng hơn một phép thử chức năng. Nó xác nhận dịch vụ có đủ điều kiện để được vận hành an toàn: cấu hình và phụ thuộc đúng, khả năng quan sát hoạt động, cảnh báo, quy trình ứng phó sự cố, sao lưu và phương án khôi phục đã sẵn sàng. Hai hoạt động bổ trợ cho nhau:

- Smoke test xác nhận những hành vi quan trọng có thể thực hiện được trên phiên bản vừa phát hành.
- Readiness check xác nhận đội vận hành có thể quan sát, hỗ trợ và khôi phục dịch vụ khi có sự cố.

Một endpoint `/health` trả về HTTP 200 chỉ cho biết một phần trạng thái kỹ thuật. Nó không chứng minh người dùng đăng nhập được, dữ liệu được ghi đúng hoặc dịch vụ phụ thuộc đang xử lý yêu cầu. Vì vậy, cần kết hợp kiểm tra hạ tầng với một số luồng thực tế có giá trị cao.

## 2. Chọn smoke test dựa trên tác động của thay đổi

Không nên chạy cùng một tập smoke test cho mọi lần phát hành. Tập kiểm tra cần phản ánh phần hệ thống bị tác động, mức độ quan trọng của chức năng và hậu quả nếu lỗi lọt tới người dùng.

Trước khi chọn phép thử, hãy đọc phạm vi thay đổi trong bản phát hành và xác định:

1. Thành phần nào thay đổi: mã ứng dụng, thư viện, cấu hình, biến môi trường, feature flag, lược đồ dữ liệu, hạ tầng hay kết nối bên ngoài.
2. Thành phần nào phụ thuộc vào phần vừa thay đổi: API, cơ sở dữ liệu, hàng đợi, bộ nhớ đệm, dịch vụ xác thực hoặc nhà cung cấp bên thứ ba.
3. Luồng nghiệp vụ nào có thể bị ảnh hưởng và luồng nào có hậu quả nghiêm trọng nếu ngừng hoạt động.
4. Dấu hiệu nào đủ tin cậy để phát hiện lỗi: mã phản hồi, dữ liệu được tạo, trạng thái xử lý, log, metric hoặc trace.

Ví dụ, thay đổi cấu hình kết nối cơ sở dữ liệu cần kiểm tra khả năng khởi động, truy vấn đọc và một thao tác ghi an toàn. Thay đổi quy tắc tính phí cần kiểm tra luồng tính giá và kết quả được lưu. Thay đổi giao diện ít ảnh hưởng tới backend có thể cần smoke test tải trang, đăng nhập và thao tác chính trên trình duyệt.

Có thể lập bảng tác động trước khi chọn test:

| Thay đổi | Rủi ro cần xác minh | Smoke test phù hợp |
|---|---|---|
| Cấu hình hoặc secret | Dịch vụ không khởi động hoặc không truy cập được phụ thuộc | Kiểm tra trạng thái tiến trình, readiness, kết nối tới phụ thuộc |
| API hoặc logic nghiệp vụ | Hợp đồng API thay đổi hoặc luồng chính trả kết quả sai | Gọi API đại diện và xác minh mã phản hồi, cấu trúc, kết quả |
| Lược đồ hoặc migration dữ liệu | Đọc/ghi lỗi, dữ liệu cũ không tương thích | Kiểm tra truy vấn đọc và thao tác ghi có thể hoàn tác |
| Hàng đợi hoặc xử lý nền | Sự kiện không được nhận hoặc không được xử lý | Gửi một sự kiện kiểm thử an toàn và xác minh trạng thái hoàn tất |
| Giao diện người dùng | Trang lỗi hoặc thao tác chính không dùng được | Mở trang, đăng nhập bằng tài khoản kiểm thử và thực hiện luồng cốt lõi |
| Hạ tầng hoặc định tuyến | Không truy cập được dịch vụ hoặc lưu lượng đi sai đích | Kiểm tra DNS/route, TLS, endpoint qua đường truy cập thực tế |

## 3. Nguyên tắc chọn tập kiểm tra nhỏ nhưng có giá trị

Một smoke test hữu ích nên đáp ứng các nguyên tắc sau:

- **Ưu tiên theo rủi ro:** chọn luồng có mức độ quan trọng cao và khả năng bị ảnh hưởng bởi thay đổi. Không chọn test chỉ vì nó dễ chạy.
- **Đại diện cho hành vi thật:** kiểm tra qua cùng API, giao diện hoặc đường đi mà người dùng hay hệ thống tích hợp sử dụng.
- **Nhanh và ổn định:** thời gian chạy ngắn, kết quả có thể lặp lại và ít phụ thuộc vào dữ liệu ngẫu nhiên.
- **An toàn với môi trường:** không tạo giao dịch thật, gửi thông báo thật, xóa dữ liệu dùng chung hoặc gây tải lớn khi chưa có cơ chế kiểm soát.
- **Có thể chẩn đoán:** khi thất bại phải biết bước nào lỗi, mong đợi điều gì và tìm log/metric ở đâu.
- **Độc lập hợp lý:** một phép thử lỗi không nên làm hỏng dữ liệu khiến các phép thử sau thất bại dây chuyền.

Không cần đưa toàn bộ bộ kiểm thử hồi quy vào smoke suite. Hãy chọn số lượng nhỏ nhất vẫn bao phủ được các rủi ro nghiêm trọng của lần phát hành. Nếu smoke suite quá dài, tín hiệu quan trọng sẽ bị chậm và nhóm có thể bỏ qua kết quả.

### 3.1. Các lớp kiểm tra nên cân nhắc

**Lớp triển khai và tiến trình**

- Bản phát hành đúng phiên bản hoặc image dự kiến.
- Các instance/pod đã khởi động và đạt trạng thái sẵn sàng.
- Không có vòng lặp khởi động lại, lỗi cấu hình hoặc thiếu secret.
- Endpoint readiness phản ánh đúng khả năng nhận yêu cầu.

**Lớp truy cập và giao tiếp**

- Tên miền, định tuyến, TLS và cổng truy cập hoạt động.
- Người dùng hoặc client hợp lệ có thể xác thực.
- API quan trọng trả đúng mã trạng thái và cấu trúc dữ liệu theo hợp đồng.
- Kiểm tra quyền truy cập cơ bản để tránh trường hợp triển khai khiến tài nguyên bị mở sai phạm vi.

**Lớp nghiệp vụ cốt lõi**

- Thực hiện một hành trình đại diện từ đầu đến cuối, chẳng hạn tạo và tra cứu một bản ghi kiểm thử.
- Xác minh kết quả nghiệp vụ, không chỉ xác minh HTTP 200.
- Nếu có bước xử lý bất đồng bộ, kiểm tra trạng thái cuối cùng hoặc xác nhận sự kiện đã được tiêu thụ.

**Lớp dữ liệu và tích hợp**

- Đọc được dữ liệu cần thiết và ghi được dữ liệu kiểm thử trong phạm vi an toàn.
- Kết nối tới hàng đợi, bộ nhớ đệm hoặc dịch vụ phụ thuộc quan trọng.
- Kiểm tra tương thích giữa phiên bản ứng dụng và cấu trúc dữ liệu sau migration.
- Xác minh lỗi từ phụ thuộc được ghi nhận và xử lý theo thiết kế.

Không phải dịch vụ nào cũng cần tất cả các lớp trên trong mỗi lần phát hành. Chọn lớp phù hợp với kiến trúc và thay đổi thực tế.

## 4. Phân biệt health, readiness và smoke test

Ba loại kiểm tra thường xuất hiện cùng nhau nhưng phục vụ các mục đích khác nhau:

| Kiểm tra | Câu hỏi chính | Ví dụ |
|---|---|---|
| Liveness/health | Tiến trình còn sống và không bị treo không? | Endpoint liveness phản hồi; tiến trình không ở trạng thái deadlock |
| Readiness | Instance đã đủ điều kiện nhận lưu lượng chưa? | Cấu hình đã nạp, kết nối thiết yếu sẵn sàng, instance được phép vào load balancer |
| Smoke test | Hành vi quan trọng của dịch vụ có hoạt động sau triển khai không? | Đăng nhập, gọi API chính, tạo rồi đọc lại bản ghi kiểm thử |
| Operational readiness | Đội vận hành có thể theo dõi và xử lý sự cố không? | Dashboard, cảnh báo, runbook, quyền truy cập và rollback đã sẵn sàng |

Không nên biến liveness thành phép kiểm tra sâu tới mọi dịch vụ bên ngoài. Một phụ thuộc tạm thời chậm có thể khiến mọi instance bị khởi động lại liên tục. Thay vào đó, xác định rõ điều kiện sống của tiến trình và điều kiện sẵn sàng nhận lưu lượng; dùng smoke test để kiểm tra luồng người dùng ở mức phù hợp.

## 5. Kiểm tra mức sẵn sàng vận hành

Readiness check nên được chuẩn bị trước thời điểm phát hành và đánh giá lại khi có thay đổi đáng kể về kiến trúc, dữ liệu hoặc cách vận hành. Các câu hỏi dưới đây giúp nhóm xác định liệu có thể phát hành và hỗ trợ phiên bản mới hay chưa.

| Hạng mục | Tiêu chí cần xác nhận | Bằng chứng phù hợp |
|---|---|---|
| Artifact và cấu hình | Đúng phiên bản, đúng môi trường, cấu hình/secret được nạp | Mã phiên bản, manifest triển khai, kết quả kiểm tra cấu hình |
| Phụ thuộc | Các dịch vụ thiết yếu có thể truy cập và có timeout/retry phù hợp | Readiness, log kết nối, kiểm tra tích hợp an toàn |
| Dữ liệu | Migration đã hoàn tất; tương thích đọc/ghi và có kế hoạch khôi phục | Trạng thái migration, kiểm tra truy vấn, bản sao lưu theo chính sách |
| Quan sát | Có metric, log và trace đủ để nhận biết lỗi | Dashboard, truy vấn log mẫu, trace của luồng quan trọng |
| Cảnh báo | Cảnh báo có ngưỡng, người nhận và hướng dẫn xử lý | Cấu hình alert, kênh trực, kết quả kiểm tra cảnh báo |
| Ứng phó sự cố | Có người chịu trách nhiệm và runbook cập nhật | Lịch trực, runbook, đầu mối liên hệ |
| Khôi phục | Có thể rollback hoặc áp dụng biện pháp giảm thiểu đã được kiểm chứng | Phiên bản trước còn khả dụng, quy trình rollback, kế hoạch dữ liệu |
| An toàn vận hành | Smoke test dùng dữ liệu và tài khoản an toàn | Tài khoản kiểm thử, dữ liệu tổng hợp, cơ chế dọn dữ liệu |
| Năng lực phục vụ | Tài nguyên và giới hạn phù hợp với lưu lượng dự kiến | Metric CPU, bộ nhớ, kết nối, hàng đợi và giới hạn dịch vụ |

Một mục chưa sẵn sàng cần có người phụ trách, mức độ ảnh hưởng và quyết định rõ ràng. Các thiếu sót có thể chấp nhận phải được ghi nhận cùng biện pháp giảm thiểu và thời hạn xử lý. Những điều kiện thiết yếu như không có phương án khôi phục cho migration không tương thích hoặc không thể quan sát lỗi nghiêm trọng thường phải chặn phát hành theo chính sách của tổ chức.

## 6. Quy trình thực hiện sau triển khai

Một trình tự thực tế có thể gồm các bước sau:

1. **Ghi nhận trạng thái trước phát hành.** Lưu mã phiên bản, thời điểm, cấu hình thay đổi, số instance và các chỉ số nền như tỷ lệ lỗi, độ trễ, lưu lượng, độ sâu hàng đợi.
2. **Triển khai theo chiến lược đã chọn.** Có thể dùng rolling, canary hoặc blue-green. Xác minh bộ điều phối đã triển khai đúng artifact và instance mới đạt trạng thái cần thiết.
3. **Kiểm tra nền tảng.** Kiểm tra liveness, readiness, định tuyến, TLS, cấu hình và kết nối thiết yếu.
4. **Chạy smoke suite.** Chạy các phép thử đã chọn theo phạm vi thay đổi, dùng tài khoản và dữ liệu kiểm thử an toàn. Ghi lại thời gian, đầu vào định danh và kết quả từng bước.
5. **Đối chiếu tín hiệu vận hành.** Kiểm tra tỷ lệ lỗi, độ trễ, log lỗi, trace, CPU/bộ nhớ và hàng đợi. So sánh với trạng thái nền và ngưỡng đã định nghĩa.
6. **Ra quyết định.** Tiếp tục rollout, tạm dừng, giảm lưu lượng hoặc rollback dựa trên tiêu chí phát hành.
7. **Theo dõi sau quyết định.** Duy trì quan sát trong khoảng thời gian phù hợp với mức rủi ro và đặc tính lưu lượng; xác nhận không có lỗi tăng dần sau khi smoke test kết thúc.

Smoke test nên chạy qua đường truy cập tương tự người dùng hoặc hệ thống tích hợp. Nếu chỉ gọi trực tiếp một instance nội bộ, phép thử có thể bỏ sót lỗi ở DNS, gateway, load balancer, chứng chỉ hoặc định tuyến.

### 6.1. Ví dụ về trình tự kiểm tra

Giả sử một dịch vụ quản lý đơn hàng vừa thay đổi cách tính tổng tiền. Một tập smoke test có thể thực hiện như sau:

1. Xác nhận phiên bản mới đã được triển khai và instance đạt readiness.
2. Xác thực bằng tài khoản kiểm thử có quyền phù hợp.
3. Gửi yêu cầu xem trước đơn hàng với dữ liệu tổng hợp đã biết trước.
4. So sánh tổng tiền, thuế và phí với kết quả mong đợi theo bộ dữ liệu kiểm thử.
5. Nếu môi trường hỗ trợ, tạo một đơn hàng thử nghiệm không phát sinh thanh toán hoặc tác động bên ngoài; đọc lại đơn hàng để xác minh dữ liệu được lưu.
6. Kiểm tra log và metric của yêu cầu, xác nhận không có lỗi bất thường hoặc độ trễ vượt ngưỡng.

Nếu không thể tạo giao dịch thử nghiệm an toàn trong production, hãy dùng phép kiểm tra chỉ đọc hoặc cơ chế thử nghiệm đã được phê duyệt. Không dùng thẻ thật, gửi hàng thật hoặc kích hoạt thông báo tới khách hàng chỉ để chứng minh smoke test thành công.

## 7. Tiêu chí đạt, không đạt và quyết định phát hành

Tiêu chí phải được thống nhất trước khi chạy. Không nên tự đặt một ngưỡng chung cho mọi hệ thống; hãy dùng SLO, hợp đồng dịch vụ, mức nền và chính sách phát hành của sản phẩm.

Một bộ tiêu chí thường bao gồm:

- Tất cả kiểm tra bắt buộc của luồng nghiệp vụ quan trọng đều đạt.
- Tỷ lệ lỗi và độ trễ không vượt ngưỡng đã xác định trong cửa sổ quan sát.
- Không xuất hiện lỗi nghiêm trọng mới trong log hoặc trace.
- Các phụ thuộc thiết yếu và hàng đợi hoạt động trong giới hạn cho phép.
- Không có dấu hiệu mất dữ liệu, ghi sai dữ liệu hoặc vi phạm quyền truy cập.
- Dashboard và cảnh báo vẫn nhận dữ liệu sau khi phát hành.

Có thể phân loại kết quả:

| Kết quả | Điều kiện | Hành động |
|---|---|---|
| Đạt | Tất cả gate bắt buộc đạt; tín hiệu vận hành trong ngưỡng | Tiếp tục rollout hoặc chuyển sang theo dõi sau phát hành |
| Đạt có điều kiện | Chỉ còn vấn đề nhỏ đã biết, có biện pháp giảm thiểu và người chịu trách nhiệm | Chỉ tiếp tục khi chính sách cho phép và quyết định được ghi nhận |
| Không đạt | Smoke test quan trọng thất bại, lỗi tăng bất thường hoặc có nguy cơ dữ liệu/an toàn | Dừng rollout, giảm lưu lượng hoặc rollback theo runbook |
| Chưa đủ bằng chứng | Không chạy được phép thử, thiếu metric/log hoặc kết quả không xác định | Giữ trạng thái phát hành ở mức tạm dừng cho tới khi có bằng chứng |

Một phép thử thất bại không phải lúc nào cũng đồng nghĩa phải rollback ngay. Trước tiên, xác định lỗi thuộc ứng dụng mới, môi trường kiểm thử, dữ liệu thử hay phụ thuộc bên ngoài. Tuy nhiên, nếu có nguy cơ ảnh hưởng người dùng hoặc dữ liệu, cần kích hoạt cơ chế dừng/khôi phục đã thống nhất thay vì tiếp tục rollout trong khi điều tra.

Với canary, so sánh nhóm instance mới với nhóm ổn định và chỉ tăng tỷ lệ lưu lượng khi các gate đạt. Với blue-green, kiểm tra môi trường xanh trước khi chuyển lưu lượng chính. Với rolling deployment, xác minh từng đợt instance và theo dõi khả năng tương thích giữa các phiên bản cùng tồn tại.

## 8. Tự động hóa và lưu bằng chứng

Đưa các smoke test ổn định vào pipeline phát hành để giảm thao tác thủ công và bảo đảm lần nào cũng dùng cùng tiêu chí. Pipeline có thể mô tả ở mức khái quát:

~~~text
deploy(version)
wait_until_ready(timeout)
assert_deployed_version(version)
run_required_smoke_tests()
collect_metrics_and_logs(observation_window)
if required_checks_pass and operational_signals_are_healthy:
    continue_rollout()
else:
    pause_rollout()
    notify_on_call_with_failure_evidence()
    follow_rollback_or_mitigation_runbook()
~~~

Mỗi lần chạy nên lưu tối thiểu:

- Mã phiên bản, môi trường, thời điểm và người hoặc pipeline kích hoạt.
- Danh sách test, kết quả từng test, thời lượng và thông tin lỗi đã được làm sạch dữ liệu nhạy cảm.
- Các chỉ số liên quan trước và sau triển khai.
- Quyết định tiếp tục, tạm dừng hoặc rollback cùng người phê duyệt nếu có.

Không ghi token, mật khẩu, secret, dữ liệu cá nhân hoặc nội dung nhạy cảm vào log smoke test. Dùng định danh kiểm thử có thể truy vết nhưng không tiết lộ thông tin thật. Dữ liệu được tạo phải có quy tắc dọn dẹp và không ảnh hưởng tới báo cáo nghiệp vụ.

Tự động hóa cần có timeout và giới hạn retry. Retry vô hạn có thể che giấu lỗi thực hoặc kéo dài thời gian phát hiện sự cố. Khi một phép thử thất bại, báo rõ bước lỗi, kết quả mong đợi, kết quả thực tế và liên kết tới log/trace tương ứng.

## 9. Những sai lầm thường gặp

- **Chỉ kiểm tra endpoint health:** tiến trình sống nhưng luồng nghiệp vụ có thể hỏng. Bổ sung ít nhất một kiểm tra đại diện cho hành vi quan trọng.
- **Chạy quá nhiều test:** smoke suite biến thành regression suite và làm chậm quyết định phát hành. Giữ lại các test có giá trị phát hiện rủi ro cao.
- **Chỉ kiểm tra nội bộ:** bỏ sót lỗi gateway, DNS, TLS hoặc định tuyến. Kiểm tra qua đường truy cập thực tế khi phù hợp.
- **Dùng dữ liệu không ổn định:** test phụ thuộc dữ liệu dùng chung hoặc thời điểm chạy dễ cho kết quả chập chờn. Chuẩn bị dữ liệu tổng hợp và cách dọn dẹp rõ ràng.
- **Tạo tác động thật trong production:** có thể phát sinh thanh toán, email, đơn hàng hoặc thay đổi không thể hoàn tác. Dùng thao tác chỉ đọc, chế độ dry-run hoặc tài khoản thử nghiệm được kiểm soát.
- **Không đặt tiêu chí trước:** nhóm diễn giải kết quả theo cảm tính và quyết định thiếu nhất quán. Xác định gate, ngưỡng và người quyết định trước phát hành.
- **Không theo dõi sau smoke test:** lỗi có thể chỉ xuất hiện khi lưu lượng tăng hoặc tác vụ nền bắt đầu chạy. Tiếp tục theo dõi theo cửa sổ quan sát đã chọn.
- **Không lưu bằng chứng:** khó phân biệt lỗi do phiên bản, môi trường hay dữ liệu. Lưu kết quả có thể truy vết và liên kết tới log, metric, trace.

## 10. Checklist áp dụng cho một lần phát hành

Trước khi triển khai, xác định thay đổi, rủi ro, test bắt buộc, dữ liệu thử, ngưỡng đạt, người chịu trách nhiệm và phương án rollback. Sau triển khai, xác minh đúng phiên bản, readiness, đường truy cập, các luồng cốt lõi và tín hiệu vận hành. Chỉ tiếp tục rollout khi các gate bắt buộc đạt hoặc có quyết định chấp nhận rủi ro theo chính sách. Cuối cùng, lưu bằng chứng và tiếp tục theo dõi để phát hiện vấn đề xuất hiện muộn.

Chất lượng của smoke test được đo bằng khả năng phát hiện nhanh những lỗi có ảnh hưởng lớn với chi phí và tác động kiểm tra thấp. Một tập test ngắn, gắn với thay đổi và có tiêu chí rõ ràng giúp nhóm đưa ra quyết định phát hành nhất quán, đồng thời giúp đội vận hành biết dịch vụ đã sẵn sàng và cần quan sát điều gì.

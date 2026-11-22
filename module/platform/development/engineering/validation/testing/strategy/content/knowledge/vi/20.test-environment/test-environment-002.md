# Chọn môi trường riêng, dùng chung hoặc tạm theo lần chạy

## 1. Vì sao cần lựa chọn mô hình môi trường kiểm thử?

Môi trường kiểm thử ảnh hưởng trực tiếp đến độ tin cậy, tốc độ phản hồi và chi phí của hoạt động xác nhận. Cùng một bộ kiểm thử có thể cho kết quả khác nhau nếu chạy trên cấu hình, phiên bản dịch vụ, dữ liệu, mạng hoặc tài nguyên khác nhau. Môi trường thiếu cô lập có thể khiến hai lần chạy tác động lẫn nhau; môi trường quá ổn định nhưng khác xa sản xuất có thể che giấu lỗi tích hợp; môi trường được tạo mới cho mọi lần chạy có thể tốn tài nguyên hoặc mất quá nhiều thời gian khởi tạo.

Ba mô hình thường được cân nhắc là:

- **Môi trường riêng (dedicated environment):** tài nguyên hoặc một phần hệ thống được dành riêng cho một nhóm, một sản phẩm, một mục đích kiểm thử hoặc một khoảng thời gian xác định.
- **Môi trường dùng chung (shared environment):** nhiều người, nhóm hoặc pipeline cùng sử dụng một tập dịch vụ và tài nguyên kiểm thử.
- **Môi trường tạm theo lần chạy (ephemeral/per-run environment):** môi trường được tạo cho một test run, pull request, nhánh hoặc phiên kiểm thử rồi được thu hồi sau khi hoàn tất.

Không có mô hình nào phù hợp với mọi loại kiểm thử. Môi trường riêng giúp kiểm soát thay đổi và tài nguyên nhưng có thể tốn chi phí. Môi trường dùng chung thuận tiện cho kiểm thử xuyên dịch vụ và sử dụng tài nguyên hiệu quả nhưng cần quản lý xung đột. Môi trường tạm hỗ trợ cô lập và tái lập nhưng đòi hỏi tự động hóa cấp phát, cấu hình, dữ liệu và dọn dẹp.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, lựa chọn môi trường cần xuất phát từ mục tiêu kiểm thử, mức rủi ro, độ trung thực cần thiết, thời gian phản hồi, khả năng cô lập, nhu cầu phối hợp, chi phí và năng lực vận hành. Có thể kết hợp cả ba mô hình trong cùng một chiến lược: kiểm thử nhanh trên môi trường tạm, kiểm thử tích hợp xuyên nhóm trên môi trường dùng chung và kiểm thử hiệu năng hoặc phần cứng trên môi trường riêng.

## 2. Hiểu ba mô hình môi trường

### 2.1. Môi trường riêng

Môi trường riêng là môi trường có tài nguyên, cấu hình hoặc quyền sử dụng được dành cho một đối tượng cụ thể. Đối tượng đó có thể là một nhóm, một dịch vụ, một chương trình kiểm thử hoặc một hoạt động có thời gian dài.

Ví dụ:

- Một nhóm sở hữu một môi trường staging riêng để xác nhận các thay đổi trước phát hành.
- Một cụm máy chủ được dành riêng cho kiểm thử hiệu năng để tránh tải từ nhóm khác làm sai kết quả.
- Một thiết bị phần cứng hoặc thiết bị di động vật lý được dành cho nhóm kiểm thử tương thích.
- Một môi trường tích hợp dành riêng cho một dự án có nhiều phụ thuộc phức tạp.

**Ưu điểm**

- Dễ kiểm soát thời điểm triển khai, cấu hình, phiên bản và dữ liệu.
- Giảm xung đột do nhóm khác thay đổi môi trường trong lúc kiểm thử.
- Có thể dành đủ tài nguyên cho các phép đo hiệu năng hoặc kiểm thử kéo dài.
- Dễ tái hiện lỗi khi trạng thái môi trường được giữ ổn định.
- Phù hợp với thiết bị, phần mềm có giấy phép, mạng hoặc phụ thuộc chuyên biệt.

**Hạn chế**

- Chi phí hạ tầng, giấy phép, bảo trì và giám sát có thể cao.
- Tài nguyên có thể nhàn rỗi khi nhóm không sử dụng.
- Cấu hình riêng có thể dần lệch khỏi cấu hình chuẩn hoặc sản xuất.
- Nhóm sở hữu phải duy trì cập nhật, backup, dữ liệu và xử lý sự cố.
- Nếu môi trường được tùy chỉnh quá nhiều, kết quả khó so sánh với môi trường khác.

Môi trường riêng không có nghĩa là một máy chủ duy nhất hoặc không dùng chung bất kỳ thành phần nào. Có thể chỉ dành riêng namespace, database, cluster node, thiết bị hoặc khoảng thời gian sử dụng. Cần mô tả rõ phạm vi nào thực sự được cô lập.

### 2.2. Môi trường dùng chung

Môi trường dùng chung là môi trường được nhiều người hoặc nhóm sử dụng theo quy tắc phối hợp. Ví dụ thường gặp là integration, QA hoặc staging environment của một sản phẩm có nhiều dịch vụ.

**Ưu điểm**

- Nhiều nhóm có thể xác nhận tích hợp trên cùng một cấu hình.
- Giảm chi phí so với việc duy trì một bản sao đầy đủ cho từng nhóm.
- Phù hợp với kiểm thử xuyên dịch vụ, luồng nghiệp vụ liên nhóm và xác nhận cấu hình chung.
- Giúp phát hiện vấn đề tương tác giữa các phiên bản dịch vụ được triển khai cùng nhau.
- Có thể tập trung quản lý dữ liệu, quyền truy cập, giám sát và hỗ trợ.

**Hạn chế**

- Nhóm này có thể làm thay đổi dữ liệu hoặc cấu hình mà nhóm khác đang dùng.
- Triển khai không đồng bộ có thể tạo tổ hợp phiên bản không được hỗ trợ.
- Tài nguyên, tài khoản, cổng mạng hoặc dữ liệu có thể bị tranh chấp.
- Lỗi môi trường khó tái hiện nếu trạng thái thay đổi liên tục.
- Lịch bảo trì hoặc sự cố của một thành phần có thể chặn nhiều nhóm.

Môi trường dùng chung cần có chủ sở hữu, lịch sử dụng hoặc quy tắc điều phối, catalog phiên bản, quy trình thay đổi, cơ chế phân vùng dữ liệu và kênh thông báo. Nếu không có những điều kiện này, môi trường dễ trở thành nguồn gây nhiễu cho kiểm thử.

### 2.3. Môi trường tạm theo lần chạy

Môi trường tạm được tạo tự động cho một đơn vị công việc cụ thể như pull request, commit, test run hoặc phiên kiểm thử. Khi hoàn thành hoặc hết thời hạn, môi trường được thu hồi.

Môi trường tạm có thể là:

- Một stack dịch vụ chạy trong container hoặc máy ảo.
- Một namespace riêng trong Kubernetes hoặc nền tảng tương tự.
- Một database/schema riêng trong cụm database dùng chung.
- Một preview deployment cho một pull request.
- Một tenant hoặc bộ dữ liệu riêng trên nền tảng tích hợp.

**Ưu điểm**

- Mỗi lần chạy có trạng thái và dữ liệu riêng, giảm ảnh hưởng chéo.
- Có thể tạo lại từ mã nguồn và cấu hình đã phiên bản hóa.
- Hỗ trợ chạy song song nhiều nhánh hoặc nhiều test run.
- Dễ gắn môi trường với commit, test report và artifact.
- Giảm tình trạng môi trường tồn tại lâu nhưng không rõ ai sở hữu.

**Hạn chế**

- Thời gian khởi tạo và dọn dẹp có thể làm tăng thời gian pipeline.
- Cần tự động hóa provisioning, cấu hình, seed dữ liệu, readiness và cleanup.
- Một số phụ thuộc không thể tạo mới cho mỗi lần chạy, như hệ thống đối tác, phần cứng hoặc dịch vụ có chi phí cao.
- Nếu giới hạn tài nguyên không tốt, nhiều môi trường đồng thời có thể gây quá tải cụm.
- Dữ liệu hoặc artifact có thể bị mất khi môi trường bị thu hồi nếu không lưu đúng cách.

Môi trường tạm không nhất thiết là bản sao đầy đủ của sản xuất. Có thể tạo một lát cắt tối thiểu gồm các dịch vụ cần thiết và mô phỏng một số phụ thuộc bên ngoài. Phần được mô phỏng và giới hạn của bằng chứng phải được ghi rõ.

## 3. Phân biệt môi trường với namespace, tenant và dữ liệu

Trong thực tế, các thuật ngữ này đôi khi bị dùng thay thế nhau nhưng không hoàn toàn giống nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Environment | Tập hợp cấu hình, dịch vụ, tài nguyên và phụ thuộc dùng cho một mục đích triển khai/kiểm thử | Integration, QA, staging |
| Namespace | Phạm vi logic để nhóm và cô lập tài nguyên trong một nền tảng | Namespace Kubernetes theo pull request |
| Tenant | Phạm vi dữ liệu và quyền của một khách hàng/đơn vị trong ứng dụng đa thuê bao | Tenant kiểm thử của nhóm thanh toán |
| Database/schema riêng | Phạm vi lưu trữ tách biệt cho dữ liệu kiểm thử | Schema test_run_482 |
| Container/VM | Đơn vị đóng gói hoặc máy tính cung cấp môi trường thực thi | Container PostgreSQL hoặc VM kiểm thử |
| Preview deployment | Bản triển khai tạm gắn với nhánh hoặc pull request | URL preview cho một thay đổi giao diện |

Một namespace riêng trong cluster dùng chung có thể cung cấp mức cô lập tốt cho workload và dữ liệu, nhưng vẫn chia sẻ kernel, mạng, control plane hoặc database nền. Một tenant riêng có thể cô lập dữ liệu logic nhưng không bảo đảm tài nguyên CPU hay bộ nhớ được dành riêng. Vì vậy, cần đánh giá mức cô lập thực tế theo từng chiều.

## 4. Các chiều cần đánh giá khi chọn môi trường

### 4.1. Mức cô lập

Xác định điều gì cần được cô lập:

- **Tài nguyên tính toán:** CPU, bộ nhớ, GPU, dung lượng lưu trữ và giới hạn đồng thời.
- **Dữ liệu:** database, schema, bucket, queue, cache và file.
- **Cấu hình:** feature flag, biến môi trường, secret, endpoint và tham số dịch vụ.
- **Phiên bản:** ứng dụng, service dependency, schema và image.
- **Mạng và bảo mật:** route, firewall, chứng chỉ, danh tính và quyền truy cập.
- **Trạng thái:** session, message, cache, scheduler và dữ liệu nền.
- **Thời gian:** lịch chạy, đồng hồ, timezone và thời điểm hết hạn.

Mức cô lập cần tương ứng với rủi ro. Kiểm thử đơn vị có thể chỉ cần tiến trình riêng; kiểm thử API có thể cần database riêng; kiểm thử hiệu năng có thể cần tài nguyên và mạng riêng; kiểm thử tích hợp có thể cần một số dịch vụ thật trong môi trường phối hợp.

### 4.2. Độ trung thực so với môi trường đích

Độ trung thực (fidelity) phản ánh mức độ môi trường kiểm thử đại diện cho điều kiện mà hệ thống sẽ hoạt động. Cần xem xét:

- Phiên bản runtime, hệ điều hành và thư viện.
- Phiên bản database, broker, cache và schema.
- Cấu hình mạng, TLS, gateway và DNS.
- Tài nguyên, topology, số replica và giới hạn kết nối.
- Dữ liệu, phân bố, kích thước và trạng thái cache.
- Cơ chế xác thực, phân quyền và secret.
- Dịch vụ bên ngoài thật, sandbox hay simulator.

Môi trường giống sản xuất hơn không tự động tốt hơn cho mọi test. Kiểm thử nhanh và cô lập thường cần một môi trường đơn giản; xác nhận hiệu năng, bảo mật hoặc triển khai cần môi trường đại diện hơn. Điều quan trọng là biết giới hạn của mỗi kết quả.

### 4.3. Tốc độ phản hồi

Đo tổng thời gian từ lúc yêu cầu môi trường đến khi có kết quả:

- Thời gian cấp phát tài nguyên.
- Thời gian tải image và khởi động dịch vụ.
- Thời gian migration và seed dữ liệu.
- Thời gian chờ health check.
- Thời gian chạy test.
- Thời gian thu thập artifact và dọn dẹp.

Một môi trường tạm có mức cô lập cao nhưng mất 20 phút để khởi tạo có thể không phù hợp với mọi pull request. Có thể dùng môi trường tạm cho kiểm thử nhanh với phụ thuộc đóng gói sẵn, còn các kiểm thử dài chạy theo lịch hoặc trên môi trường riêng.

### 4.4. Khả năng tái lập

Môi trường có thể được tạo lại với cùng phiên bản, cấu hình và dữ liệu hay không? Cần phiên bản hóa hạ tầng dưới dạng mã, image, manifest, schema, cấu hình và script seed. Ghi lại commit, build ID, dependency version, seed và tham số quan trọng của lần chạy.

Môi trường dùng chung có thể khó tái lập nếu cấu hình bị thay đổi thủ công. Môi trường riêng cũng có thể trôi cấu hình theo thời gian. Môi trường tạm có lợi thế khi được tạo từ cấu hình có phiên bản, nhưng chỉ khi mọi phụ thuộc quan trọng đều được quản lý.

### 4.5. Chi phí và mức sử dụng

Không chỉ tính chi phí máy chủ. Cần tính:

- Chi phí tài nguyên và lưu trữ.
- Giấy phép phần mềm hoặc thiết bị.
- Chi phí vận hành, nâng cấp và hỗ trợ.
- Thời gian chờ của nhóm.
- Chi phí xử lý xung đột và flaky test.
- Chi phí tạo, giữ và dọn môi trường tạm.
- Chi phí dữ liệu, backup, artifact và giám sát.

Môi trường riêng có thể nhàn rỗi nhưng cần thiết cho các phép đo có kiểm soát. Môi trường dùng chung tiết kiệm tài nguyên nhưng có thể tạo chi phí ẩn do chờ đợi và xung đột. Môi trường tạm có thể tự động thu hồi tài nguyên nhưng cần kiểm soát số lượng và thời gian tồn tại.

### 4.6. Khả năng vận hành và sở hữu

Mỗi môi trường cần có owner hoặc nhóm chịu trách nhiệm về trạng thái, phiên bản, quyền truy cập, cảnh báo, backup, bảo trì và xử lý sự cố. Với môi trường tạm, cần xác định ai chịu trách nhiệm cho bộ điều khiển provisioning, template và cleanup.

Nếu không có chủ sở hữu, môi trường có thể bị bỏ quên, dùng phiên bản lỗi thời hoặc tích tụ dữ liệu. Việc có một URL hoạt động không đồng nghĩa môi trường được quản lý tốt.

## 5. Chọn mô hình theo loại kiểm thử

Không cần ép một loại kiểm thử vào một mô hình duy nhất. Bảng dưới đây là định hướng ban đầu:

| Hoạt động kiểm thử | Mô hình thường phù hợp | Lý do và lưu ý |
|---|---|---|
| Unit test | Tiến trình cục bộ hoặc runner cô lập | Nhanh, ít phụ thuộc; thường không cần môi trường dịch vụ đầy đủ |
| Component/repository test | Container hoặc môi trường tạm | Có thể tạo database/broker theo phiên bản và dữ liệu riêng |
| API test | Môi trường tạm hoặc namespace riêng; shared cho một số luồng tích hợp | Cần dữ liệu cô lập và endpoint ổn định |
| Contract test | Môi trường tạm hoặc provider verification trên runner; shared sandbox khi cần | Hợp đồng cần được xác minh với phiên bản provider phù hợp |
| Integration test xuyên dịch vụ | Shared environment có quản trị hoặc ephemeral stack nếu khả thi | Cần nhiều dịch vụ phối hợp và tổ hợp phiên bản rõ |
| End-to-end test | Staging/shared được kiểm soát hoặc preview environment | Cần hành trình thực tế; nên giới hạn số kịch bản dài |
| Kiểm thử hiệu năng | Dedicated hoặc môi trường có tài nguyên cô lập | Tránh tải từ nhóm khác làm sai số đo |
| Kiểm thử bảo mật | Dedicated hoặc môi trường được phê duyệt với dữ liệu an toàn | Cần kiểm soát phạm vi, quyền và tác động |
| Kiểm thử tương thích thiết bị | Dedicated device lab hoặc lịch dùng chung có quản lý | Phần cứng và hệ điều hành có thể không dễ tạo tạm |
| Kiểm thử phục hồi/chaos | Môi trường riêng hoặc môi trường được giới hạn rõ | Cần kiểm soát blast radius và khả năng khôi phục |

Một chiến lược phổ biến là:

~~~text
Pull request
    |
    v
Runner/unit test và môi trường tạm cho API/component
    |
    v
Môi trường tích hợp dùng chung hoặc stack tạm xuyên dịch vụ
    |
    v
Môi trường riêng cho hiệu năng/bảo mật/chuyên biệt
    |
    v
Staging có kiểm soát và xác nhận trước phát hành
    |
    v
Smoke test và giám sát sau triển khai
~~~

Luồng thực tế có thể chạy một số bước song song hoặc theo lịch. Mỗi bước cần chỉ rõ loại rủi ro được xác nhận và phần nào chưa được kiểm tra.

## 6. Quy trình lựa chọn mô hình môi trường

### Bước 1: Xác định mục tiêu và rủi ro

Mô tả hành vi cần kiểm tra, hậu quả nếu lỗi và bằng chứng cần có. Ví dụ, kiểm thử concurrency cần tài nguyên và trạng thái có thể kiểm soát; kiểm thử giao diện có thể cần một trình duyệt và API test environment; kiểm thử hiệu năng cần cấu hình tài nguyên đại diện.

### Bước 2: Liệt kê phụ thuộc

Xác định ứng dụng, database, broker, cache, dịch vụ ngoài, thiết bị, gateway, hệ thống xác thực và dữ liệu cần thiết. Phân loại phụ thuộc có thể đóng gói, mô phỏng, dùng chung hoặc phải truy cập qua sandbox/thiết bị thật.

### Bước 3: Xác định mức cô lập cần thiết

Đánh giá khả năng test run ảnh hưởng lẫn nhau. Nếu một test sửa dữ liệu dùng chung, chạy song song có thể gây sai kết quả. Nếu kiểm thử tải chia sẻ CPU và mạng với nhóm khác, số đo có thể không đáng tin.

### Bước 4: Xác định độ trung thực cần thiết

Liệt kê những khác biệt có thể làm thay đổi kết quả: phiên bản database, topology, dữ liệu, cache, quyền, mạng, cấu hình hoặc phụ thuộc. Chọn môi trường có đủ độ trung thực cho rủi ro đang xác nhận và ghi rõ phần khác biệt.

### Bước 5: So sánh tốc độ, chi phí và khả năng vận hành

Ước lượng thời gian khởi tạo, thời gian chờ, tài nguyên, công sức hỗ trợ, mức sử dụng và chi phí dọn dẹp. Đánh giá khả năng tự động hóa, theo dõi và phục hồi.

### Bước 6: Chọn mô hình hoặc tổ hợp

Chọn môi trường riêng, dùng chung hoặc tạm theo lần chạy. Có thể kết hợp, ví dụ tạo namespace tạm trong cluster dùng chung nhưng kết nối đến một sandbox đối tác cố định. Ghi rõ phần nào được cô lập và phần nào vẫn dùng chung.

### Bước 7: Định nghĩa vòng đời và quy tắc sử dụng

Quy định cách yêu cầu/tạo môi trường, điều kiện sẵn sàng, phiên bản, dữ liệu, quyền, thời hạn, cleanup và xử lý sự cố. Với môi trường dùng chung, xác định lịch, quy tắc thay đổi và thông báo. Với môi trường tạm, xác định TTL và cơ chế thu hồi.

### Bước 8: Đo lường và xem xét lại

Theo dõi thời gian chờ, tỷ lệ môi trường sẵn sàng, flaky test, xung đột, mức sử dụng, chi phí và lỗi do sai khác môi trường. Xem xét lại khi kiến trúc, số nhóm, tải kiểm thử hoặc yêu cầu bảo mật thay đổi.

## 7. Quản trị môi trường riêng

### 7.1. Xác định mục đích và giới hạn

Mỗi môi trường riêng cần nêu rõ được dùng cho việc gì, ai được sử dụng, phụ thuộc nào được kết nối và loại kiểm thử nào được phép chạy. Ví dụ, môi trường performance dành cho đo tải có thể không cho phép triển khai tùy ý trong thời gian đo.

### 7.2. Quản lý cấu hình và phiên bản

Dùng cấu hình có phiên bản và quy trình triển khai được kiểm soát. Ghi nhận image, runtime, database, schema, cấu hình gateway và feature flag. Tránh chỉnh sửa thủ công không có lịch sử vì sẽ làm mất khả năng tái lập.

### 7.3. Lịch bảo trì và trạng thái

Đặt lịch cập nhật, backup, kiểm tra dung lượng, chứng chỉ và dependency. Có dashboard hoặc thông tin trạng thái để người dùng biết môi trường sẵn sàng, đang bảo trì hay bị lỗi.

### 7.4. Tránh môi trường riêng bị lệch

Môi trường riêng tồn tại lâu có nguy cơ drift: phiên bản và cấu hình dần khác chuẩn. Định kỳ tái tạo hoặc đối chiếu cấu hình với baseline. Nếu có khác biệt có chủ đích, ghi rõ lý do và giới hạn kết quả kiểm thử.

## 8. Quản trị môi trường dùng chung

### 8.1. Chủ sở hữu và catalog

Mỗi môi trường dùng chung cần có owner, mô tả mục đích, URL/endpoint nội bộ, thành phần, phiên bản hiện tại, lịch bảo trì và kênh hỗ trợ. Catalog giúp nhóm biết môi trường nào phù hợp và ai có quyền thay đổi.

### 8.2. Điều phối lịch sử dụng và triển khai

Với hoạt động có tác động lớn như hồi quy đầu cuối, migration hoặc kiểm thử tải, có thể cần đặt lịch. Không phải mọi thao tác đều cần đặt lịch; namespace và dữ liệu riêng có thể cho phép nhiều nhóm chạy song song.

Quy định thời điểm đóng băng phiên bản, cách thông báo triển khai và cách xử lý khi một nhóm cần thay đổi khẩn cấp. Ghi lại phiên bản từng dịch vụ trong mỗi lần chạy để hiểu tổ hợp đã được kiểm thử.

### 8.3. Cô lập dữ liệu và trạng thái

Dùng tenant, schema, namespace hoặc tiền tố dữ liệu riêng cho từng nhóm/test run. Nếu không thể cô lập hoàn toàn, quy định quyền ghi, lịch chạy và quy trình reset. Test cần dọn dữ liệu do chính nó tạo ra và tránh xóa dữ liệu của nhóm khác.

Cache, queue và file storage cũng cần được tính đến. Chỉ tách database nhưng dùng chung queue hoặc cache có thể vẫn gây nhiễu. Có thể dùng key prefix, queue riêng hoặc consumer group riêng nếu nền tảng hỗ trợ.

### 8.4. Theo dõi thay đổi và sức khỏe

Theo dõi trạng thái dịch vụ, CPU, bộ nhớ, dung lượng, queue lag, kết nối database, chứng chỉ, DNS và lỗi triển khai. Khi môi trường không khỏe, công bố trạng thái để nhóm không kết luận nhầm lỗi môi trường thành lỗi sản phẩm.

### 8.5. Xử lý xung đột

Khi phát hiện hai nhóm ảnh hưởng lẫn nhau, xác định thành phần dùng chung, thời điểm thay đổi và dữ liệu bị tác động. Khôi phục môi trường, chạy smoke test và thông báo các nhóm. Sau đó quyết định có cần tăng mức cô lập, thêm namespace hay thay đổi lịch sử dụng.

## 9. Tự động hóa môi trường tạm theo lần chạy

### 9.1. Vòng đời tiêu chuẩn

Một môi trường tạm nên có vòng đời tự động và có thể quan sát:

~~~text
Yêu cầu môi trường (PR/commit/test run)
                 |
                 v
       Cấp phát tài nguyên/namespace
                 |
                 v
       Triển khai phiên bản xác định
                 |
                 v
       Seed dữ liệu và cấu hình
                 |
                 v
       Health check và readiness
                 |
                 v
       Chạy kiểm thử và thu thập artifact
                 |
                 v
       Giữ môi trường để điều tra (nếu cần)
                 |
                 v
       Cleanup và xác nhận thu hồi
~~~

Nếu test thất bại, có thể giữ môi trường trong một khoảng thời gian giới hạn để điều tra. Cần có TTL và cơ chế thu hồi tự động để tránh môi trường lỗi tồn tại vô hạn.

### 9.2. Gắn môi trường với định danh lần chạy

Đặt tên hoặc label theo PR, commit hoặc run ID. Metadata nên bao gồm:

- Owner hoặc nhóm yêu cầu.
- Commit/build và phiên bản image.
- Thời điểm tạo và TTL.
- Namespace, tenant hoặc database/schema.
- Trạng thái provisioning/readiness/test/cleanup.
- Liên kết đến pipeline và artifact.

Không đưa thông tin nhạy cảm vào tên hoặc label. ID nên đủ duy nhất để tránh hai test run dùng chung tài nguyên ngoài ý muốn.

### 9.3. Quản lý tài nguyên và giới hạn đồng thời

Đặt quota cho CPU, memory, storage, số pod, database connection và số môi trường đồng thời. Có thể giới hạn số preview environment theo nhóm hoặc ưu tiên pull request quan trọng. Khi hết quota, pipeline nên báo trạng thái chờ rõ ràng thay vì treo không thời hạn.

Theo dõi thời gian sống trung bình, tỷ lệ môi trường bị rò rỉ và chi phí theo nhóm. Thu hồi môi trường đã hết TTL, nhưng giữ artifact và metadata cần thiết trước khi xóa.

### 9.4. Readiness và phụ thuộc

Không bắt đầu test chỉ vì tài nguyên đã được tạo. Cần kiểm tra dịch vụ sẵn sàng, migration hoàn tất, dữ liệu seed xong, endpoint có thể truy cập và phụ thuộc đáp ứng. Dùng health check và timeout hữu hạn.

Nếu môi trường tạm phụ thuộc dịch vụ dùng chung, ghi rõ phiên bản và trạng thái của dịch vụ đó. Một môi trường chỉ cô lập ứng dụng nhưng vẫn phụ thuộc vào database hoặc API chung có thể chưa tái lập hoàn toàn.

### 9.5. Lưu bằng chứng trước cleanup

Trước khi thu hồi môi trường, lưu báo cáo, log đã làm sạch, ảnh, trace, cấu hình và định danh phiên bản. Nếu cần điều tra sâu, có thể giữ môi trường với TTL ngắn được phê duyệt. Không phụ thuộc vào việc môi trường còn tồn tại để giữ bằng chứng.

### 9.6. Cleanup an toàn

Cleanup cần giới hạn đúng tài nguyên của run ID. Xóa namespace hoặc database dùng chung theo wildcard có thể gây mất dữ liệu ngoài phạm vi. Script cleanup nên xác minh owner/label, ghi lại tài nguyên đã xóa và có thể chạy lại an toàn.

## 10. Kết hợp ba mô hình trong một chiến lược

Một tổ chức có thể dùng cả ba mô hình theo mục tiêu:

| Lớp môi trường | Mô hình | Ví dụ sử dụng |
|---|---|---|
| Runner/unit | Tạm theo job | Unit test và phân tích tĩnh trong pipeline |
| Component/API | Tạm theo lần chạy | Container database và namespace riêng cho mỗi pull request |
| Integration | Dùng chung có quản trị hoặc stack tạm | Kiểm thử phối hợp nhiều dịch vụ |
| Performance/security | Riêng hoặc có cửa sổ sử dụng riêng | Đo tải, kiểm thử xâm nhập có kiểm soát |
| Staging/release | Dùng chung được kiểm soát hoặc riêng | Hồi quy trước phát hành và xác nhận cấu hình |
| Device lab | Riêng hoặc dùng chung theo lịch | Kiểm thử thiết bị vật lý, trình duyệt và hệ điều hành |

Ví dụ, pipeline của một dịch vụ đặt hàng có thể tạo môi trường tạm gồm ứng dụng và database cho API test. Sau đó, một tập contract test chạy với provider verification. Kiểm thử đầu cuối xuyên dịch vụ chạy trên integration environment dùng chung đã công bố phiên bản. Kiểm thử tải chạy trên cụm riêng để tránh ảnh hưởng các nhóm. Staging được dùng cho xác nhận phát hành cuối cùng với dữ liệu tổng hợp gần thực tế.

Sự kết hợp này cần có bản đồ phụ thuộc và quy tắc rõ. Nếu test trên môi trường tạm gọi sang dịch vụ dùng chung, kết quả vẫn phụ thuộc trạng thái dịch vụ đó. Không mô tả môi trường là hoàn toàn cô lập khi chỉ một phần được tạo riêng.

## 11. Bảo mật, quyền truy cập và dữ liệu

Mọi mô hình môi trường đều cần kiểm soát bảo mật:

- Dùng danh tính và quyền tối thiểu theo vai trò.
- Cấp credential qua secret manager hoặc cơ chế được phê duyệt; không ghi cứng vào repository, manifest hoặc log.
- Tách secret giữa môi trường phát triển, kiểm thử và sản xuất.
- Dùng dữ liệu tổng hợp hoặc dữ liệu đã được xử lý theo chính sách.
- Hạn chế kết nối từ môi trường kiểm thử đến hệ thống sản xuất.
- Giới hạn quyền tạo tải, gửi email, thanh toán hoặc tác dụng phụ bên ngoài.
- Quản lý chứng chỉ, TLS, firewall, DNS và network policy.
- Ghi log truy cập và thay đổi cấu hình theo yêu cầu.
- Có thời hạn lưu dữ liệu, artifact và tài nguyên.

Môi trường tạm có thời gian sống ngắn vẫn có thể bị truy cập trái phép nếu endpoint công khai hoặc secret bị lộ. Môi trường dùng chung cần phân tách tenant và quyền; môi trường riêng cần kiểm tra quyền truy cập và cập nhật bản vá.

## 12. Đánh giá độ tin cậy của kết quả theo mô hình môi trường

### 12.1. Ghi rõ điều kiện chạy

Mỗi kết quả kiểm thử quan trọng nên liên kết với:

- Environment ID và mô hình môi trường.
- Phiên bản ứng dụng, dịch vụ và dependency.
- Cấu hình, feature flag và tài nguyên.
- Seed, namespace/tenant và trạng thái dữ liệu.
- Thời điểm chạy và trạng thái phụ thuộc.
- Mã test, run ID và artifact.

Nhờ đó, nhóm có thể phân biệt kết quả do sản phẩm với kết quả do môi trường hoặc dữ liệu.

### 12.2. Nhận diện lỗi môi trường

Các dấu hiệu có thể gồm nhiều test không liên quan cùng thất bại, health check không đạt, tài nguyên cạn, dịch vụ phụ thuộc không sẵn sàng hoặc cấu hình khác dự kiến. Tuy nhiên, không nên tự động phân loại mọi lỗi đồng loạt là lỗi môi trường. Cần thu thập bằng chứng và xác định nguyên nhân.

Nếu môi trường không khỏe, đánh dấu kết quả bị chặn hoặc chưa xác định theo quy ước. Không tính test chưa chạy thành đạt. Sau khi sửa môi trường, chạy lại tập kiểm thử bị ảnh hưởng và ghi liên kết với lần chạy trước.

### 12.3. Kiểm soát drift

So sánh cấu hình thực tế với cấu hình khai báo. Theo dõi thay đổi phiên bản, secret reference, network policy, schema, feature flag và dependency. Với môi trường dùng chung hoặc riêng tồn tại lâu, nên có lịch tái tạo hoặc kiểm tra drift.

Môi trường tạm giảm thời gian drift nhưng không loại bỏ hoàn toàn rủi ro nếu image hoặc dependency tag không được ghim, hoặc dịch vụ bên ngoài thay đổi độc lập.

## 13. Đo lường hiệu quả của môi trường

Theo dõi cả trải nghiệm nhóm và chất lượng kỹ thuật:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Provisioning time | Thời gian từ yêu cầu đến khi môi trường sẵn sàng | Tối ưu pipeline và thời gian chờ |
| Readiness success rate | Tỷ lệ môi trường đạt health check trong giới hạn | Đánh giá độ tin cậy của cấp phát và cấu hình |
| Environment availability | Thời gian môi trường sẵn sàng khi cần | Đánh giá shared/dedicated environment |
| Queue/wait time | Thời gian chờ tài nguyên hoặc lịch sử dụng | Phát hiện thiếu năng lực hoặc điều phối kém |
| Conflict rate | Số lần test bị ảnh hưởng do dữ liệu/cấu hình dùng chung | Đánh giá nhu cầu cô lập |
| Cleanup success rate | Tỷ lệ môi trường được thu hồi đúng hạn | Phát hiện rò rỉ tài nguyên |
| Environment drift | Mức sai khác giữa cấu hình thực tế và baseline | Cải thiện tái lập |
| Flaky rate | Tỷ lệ kết quả không ổn định do test/môi trường | Phân loại nguyên nhân và tăng độ tin cậy |
| Cost per run | Chi phí tài nguyên và vận hành cho một lần chạy | So sánh mô hình theo giá trị |
| Fidelity gap | Các khác biệt quan trọng so với môi trường đích | Hiểu giới hạn của bằng chứng |

Không tối ưu một chỉ số riêng lẻ. Giảm provisioning time bằng cách bỏ health check có thể làm tăng test thất bại giả; tăng mức sử dụng bằng cách chia sẻ mọi tài nguyên có thể tạo xung đột; giữ môi trường lâu hơn giúp điều tra nhưng làm tăng chi phí. Cần đánh giá tổng thể.

## 14. Ma trận quyết định lựa chọn môi trường

Bảng sau giúp định hướng lựa chọn ban đầu:

| Tiêu chí | Môi trường riêng | Môi trường dùng chung | Môi trường tạm theo lần chạy |
|---|---|---|---|
| Cô lập thay đổi | Cao nếu tài nguyên và cấu hình thực sự riêng | Thấp đến trung bình, phụ thuộc phân vùng | Cao với tài nguyên được tạo riêng |
| Tái lập | Tốt nếu cấu hình được quản lý; có nguy cơ drift | Phụ thuộc kỷ luật quản trị và lịch sử thay đổi | Tốt nếu provisioning và dependency được phiên bản hóa |
| Thời gian sẵn sàng | Thường nhanh sau khi đã vận hành | Có sẵn nhưng có thể phải chờ lịch/tài nguyên | Có thêm thời gian provisioning và seed |
| Chi phí tài nguyên | Có thể cao do tài nguyên dành riêng | Có thể tiết kiệm nhờ chia sẻ | Linh hoạt nhưng cần quota và cleanup |
| Kiểm thử xuyên nhóm | Phù hợp nếu môi trường được thiết kế cho tích hợp | Thường phù hợp | Khó nếu cần nhiều dịch vụ hoặc phụ thuộc không thể tạo mới |
| Kiểm thử hiệu năng | Phù hợp khi cần kiểm soát tải | Dễ bị nhiễu bởi nhóm khác | Phù hợp nếu có đủ tài nguyên và cấu hình đại diện |
| Chạy song song | Cần cấp nhiều môi trường riêng hoặc vùng tài nguyên | Có thể xung đột nếu thiếu namespace | Phù hợp nếu quota và dữ liệu được cô lập |
| Công sức vận hành | Owner duy trì dài hạn | Cần điều phối, lịch, catalog và xử lý xung đột | Cần tự động hóa lifecycle, quota và cleanup |
| Thiết bị/phụ thuộc đặc biệt | Thường phù hợp | Có thể dùng chung theo lịch | Thường khó tạo tạm cho từng run |

Một cách ra quyết định thực tế:

1. Nếu kết quả cần đo tài nguyên, tải hoặc phần cứng có kiểm soát, ưu tiên môi trường riêng.
2. Nếu mục tiêu là xác nhận tích hợp thật giữa nhiều nhóm và các bên cần cùng quan sát trạng thái, cân nhắc môi trường dùng chung có quản trị.
3. Nếu cần phản hồi nhanh, chạy song song và tái lập theo commit, ưu tiên môi trường tạm.
4. Nếu phụ thuộc không thể tạo mới, kết hợp môi trường tạm với một sandbox hoặc dịch vụ dùng chung, đồng thời ghi rõ phần phụ thuộc.
5. Nếu không thể đạt mức cô lập hoặc độ trung thực cần thiết, điều chỉnh phạm vi kiểm thử hoặc bổ sung bằng chứng ở môi trường khác.

## 15. Ví dụ thực tế

### Ví dụ A: Môi trường tạm cho pull request

Một nhóm phát triển dịch vụ hồ sơ muốn kiểm tra API khi mở pull request. Pipeline tạo namespace riêng, triển khai image theo commit, tạo schema database, seed dữ liệu tổng hợp và chạy API test. Khi hoàn tất, pipeline lưu báo cáo và thu hồi namespace.

Một test thất bại có thể giữ namespace thêm một khoảng thời gian ngắn để điều tra. TTL vẫn được áp dụng; nếu hết hạn, hệ thống lưu artifact rồi xóa tài nguyên. Nhóm theo dõi thời gian provisioning, tỷ lệ readiness và số lần cleanup thất bại.

### Ví dụ B: Môi trường dùng chung cho tích hợp nhiều dịch vụ

Một sản phẩm gồm order, payment, inventory và notification do các nhóm khác nhau sở hữu. Nhóm duy trì integration environment với phiên bản dịch vụ được công bố, lịch triển khai và dữ liệu theo tenant. Trước khi chạy hồi quy xuyên dịch vụ, pipeline xác nhận health check và phiên bản các thành phần.

Một nhóm có thể triển khai thay đổi trong namespace riêng nếu kiến trúc hỗ trợ. Nếu phải triển khai vào cùng stack, cần thông báo và phối hợp lịch. Khi test thất bại, nhóm kiểm tra phiên bản và thay đổi gần nhất của từng dịch vụ để xác định phạm vi ảnh hưởng.

### Ví dụ C: Môi trường riêng cho kiểm thử hiệu năng

Một API báo cáo cần đáp ứng mục tiêu p95 khi dữ liệu tăng lên hàng trăm triệu bản ghi. Nhóm dùng cụm riêng có cấu hình tài nguyên được kiểm soát, dữ liệu tổng hợp theo phân bố đã xác định và lịch chạy không bị tải từ nhóm khác ảnh hưởng.

Nhóm ghi lại phiên bản database, index, cache, topology, CPU, bộ nhớ và mô hình tải. Kết quả trên cụm này được dùng để đánh giá hiệu năng trong cấu hình đã thử; các khác biệt so với sản xuất vẫn cần được ghi rõ.

### Ví dụ D: Kết hợp môi trường tạm với sandbox đối tác

Một dịch vụ đặt vé cần gọi API đối tác để xác nhận chỗ. Mỗi pull request tạo ứng dụng và database riêng, nhưng gọi đến sandbox đối tác dùng chung. Vì sandbox có giới hạn tài khoản và dữ liệu, nhóm cấp một test account theo lịch và làm sạch dữ liệu sau khi chạy.

Các tình huống timeout, phản hồi trùng và lỗi hiếm được kiểm tra bằng simulator trong môi trường tạm. Một tập kiểm thử nhỏ với sandbox xác nhận hợp đồng và xác thực thật. Báo cáo phải phân biệt kết quả mô phỏng với kết quả sandbox.

### Ví dụ E: Phòng thiết bị dùng chung theo lịch

Một ứng dụng di động cần kiểm tra trên một số thiết bị vật lý và phiên bản hệ điều hành. Không thể tạo môi trường thiết bị tạm cho mỗi commit. Nhóm quản lý device lab dùng chung với lịch đặt chỗ, trạng thái pin/kết nối, phiên bản hệ điều hành và quy trình reset thiết bị.

Test tự động trên emulator chạy trong pipeline cho phản hồi nhanh; kiểm thử trên thiết bị vật lý chạy theo lịch hoặc trước phát hành. Mỗi báo cáo ghi model, OS version, app build và cấu hình thiết bị để có thể tái hiện.

## 16. Mẫu mô tả và cấp phát môi trường

Một yêu cầu môi trường có thể được mô tả bằng cấu trúc như sau:

~~~yaml
environment_request:
  id: ENV-PR-482
  model: ephemeral
  owner: order-team
  purpose: "API và component test cho pull request"

source:
  commit: "a81f2d"
  application_image: "order-service:build-1842"
  database_image: "postgres:16.4"

isolation:
  namespace: "pr-482"
  database_schema: "test_pr_482"
  data_seed: 41027
  shared_dependencies:
    - "partner-sandbox"

readiness:
  health_checks:
    - "order-service"
    - "database"
  timeout_seconds: 180

lifecycle:
  ttl_hours: 8
  preserve_on_failure_minutes: 45
  cleanup: true

evidence:
  attach_run_id: true
  save_test_report: true
  save_sanitized_logs: true
~~~

Đây là ví dụ minh họa, không phải manifest triển khai có thể dùng trực tiếp. Tên image, secret, namespace, quyền và TTL phải theo chính sách nền tảng. Không ghi credential vào file cấu hình hoặc artifact.

## 17. Những sai lầm thường gặp

- **Dùng một môi trường cho mọi loại kiểm thử:** nhu cầu cô lập, độ trung thực và tài nguyên khác nhau.
- **Gọi namespace là cô lập hoàn toàn:** vẫn có thể chia sẻ node, network, database hoặc control plane.
- **Dùng môi trường chung không có owner:** không rõ ai chịu trách nhiệm khi cấu hình hoặc dữ liệu bị thay đổi.
- **Không ghi phiên bản thành phần:** khó biết tổ hợp dịch vụ nào đã được kiểm thử.
- **Chỉ tạo môi trường tạm mà không cleanup:** tài nguyên và dữ liệu tồn dư làm tăng chi phí.
- **Cleanup quá rộng:** xóa nhầm namespace, database hoặc artifact của nhóm khác.
- **Bắt đầu test trước readiness:** tạo lỗi ngẫu nhiên do dịch vụ chưa sẵn sàng.
- **Dùng shared dependency mà không ghi nhận:** kết quả không thể tái lập khi dependency thay đổi.
- **Đo hiệu năng trên tài nguyên bị tranh chấp:** số đo bị nhiễu và dẫn đến kết luận sai.
- **Giữ môi trường lỗi vô thời hạn:** chi phí tăng và tạo bề mặt tấn công không cần thiết.
- **Đồng nhất staging với production:** khác biệt dữ liệu, tài nguyên, mạng và quyền vẫn có thể tồn tại.
- **Không lưu artifact trước khi thu hồi:** mất bằng chứng khi môi trường tạm bị xóa.
- **Không theo dõi drift:** môi trường riêng hoặc dùng chung dần khác cấu hình chuẩn.
- **Không phân biệt kết quả thật và mô phỏng:** người đọc có thể hiểu nhầm mức độ tích hợp đã được xác nhận.

## 18. Checklist lựa chọn và quản trị môi trường

### Trước khi lựa chọn

- [ ] Mục tiêu, rủi ro và loại kiểm thử đã được xác định.
- [ ] Các dịch vụ, dữ liệu, thiết bị và phụ thuộc cần thiết đã được liệt kê.
- [ ] Mức cô lập về tài nguyên, dữ liệu, cấu hình, phiên bản và trạng thái được xác định.
- [ ] Độ trung thực cần thiết và khác biệt với môi trường đích được ghi nhận.
- [ ] Thời gian provisioning, thời gian chờ và chi phí được ước lượng.
- [ ] Có owner và năng lực vận hành phù hợp.
- [ ] Đã quyết định dùng riêng, dùng chung, tạm theo lần chạy hoặc kết hợp.

### Khi vận hành môi trường riêng hoặc dùng chung

- [ ] Mục đích, owner, phiên bản và trạng thái môi trường được công bố.
- [ ] Cấu hình và thay đổi có lịch sử.
- [ ] Dữ liệu, namespace, tenant, queue và cache được phân vùng phù hợp.
- [ ] Có quy tắc lịch sử dụng, triển khai và thông báo thay đổi.
- [ ] Health check, giám sát và quy trình khôi phục hoạt động.
- [ ] Có kiểm tra drift và lịch bảo trì.
- [ ] Quyền truy cập và secret được quản lý an toàn.

### Khi vận hành môi trường tạm

- [ ] Môi trường gắn với PR/commit/run ID và owner.
- [ ] Provisioning, deployment, seed và readiness được tự động hóa.
- [ ] Có quota và giới hạn số môi trường chạy đồng thời.
- [ ] TTL và cleanup được cấu hình, kiểm tra đúng phạm vi.
- [ ] Artifact và metadata được lưu trước khi thu hồi.
- [ ] Có cơ chế giữ môi trường thất bại trong thời gian giới hạn để điều tra.
- [ ] Phụ thuộc dùng chung và giới hạn cô lập được ghi rõ.

### Khi đánh giá kết quả

- [ ] Mỗi lần chạy ghi environment ID, phiên bản, cấu hình và dữ liệu.
- [ ] Lỗi môi trường được phân biệt với lỗi sản phẩm dựa trên bằng chứng.
- [ ] Kết quả bị chặn hoặc chưa xác định không bị tính là đạt.
- [ ] Mức độ đại diện của môi trường được nêu trong báo cáo.
- [ ] Thời gian chờ, readiness, xung đột, drift, cleanup và chi phí được theo dõi.
- [ ] Mô hình môi trường được xem xét lại khi kiến trúc hoặc nhu cầu thay đổi.

## Kết luận

Chọn môi trường riêng, dùng chung hay tạm theo lần chạy là quyết định cân bằng giữa cô lập, độ trung thực, tốc độ, chi phí và khả năng vận hành. Môi trường riêng phù hợp khi cần kiểm soát tài nguyên hoặc điều kiện chuyên biệt; môi trường dùng chung hỗ trợ phối hợp tích hợp nếu có owner và quy tắc rõ; môi trường tạm hỗ trợ phản hồi nhanh, chạy song song và tái lập khi vòng đời được tự động hóa. Nhiều chiến lược cần kết hợp cả ba. Khi nhóm ghi rõ phạm vi cô lập, phiên bản, dữ liệu, phụ thuộc, vòng đời và giới hạn bằng chứng, kết quả kiểm thử sẽ dễ tin cậy và dễ giải thích hơn.

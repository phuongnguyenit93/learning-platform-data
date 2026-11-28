# Control baseline: tập kiểm soát nền cho yêu cầu bảo mật

## 1. Mục tiêu bài học

Trong thiết kế yêu cầu bảo mật, **control baseline** là một tập kiểm soát nền được chọn làm điểm xuất phát cho một phạm vi hệ thống xác định. Baseline mô tả mức bảo vệ cần có, điều kiện áp dụng và cách chứng minh đáp ứng. Nhóm dự án tiếp tục điều chỉnh tập nền theo tài sản, mô hình đe dọa, mức tác động và nghĩa vụ áp dụng.

Học xong bài này, bạn có thể:

- Phân biệt baseline với danh mục kiểm soát, chính sách, cấu hình kỹ thuật và yêu cầu của một hệ thống cụ thể.
- Chọn và điều chỉnh baseline dựa trên rủi ro, thay vì sao chép một checklist.
- Chuyển kiểm soát nền thành yêu cầu có phạm vi, hành vi, ngưỡng đo và tiêu chí kiểm thử.
- Liên kết rủi ro, yêu cầu, quyết định kiến trúc, bằng chứng và người chịu trách nhiệm.
- Quản lý thiếu hụt, ngoại lệ và phiên bản baseline trong vòng đời phát triển.

Các mã kiểm soát, cấp baseline, thời hạn và ngưỡng số trong bài đều là **ví dụ nội bộ để học cách đặc tả**. Chúng không phải mã của một tiêu chuẩn bên ngoài hay mức tuân thủ bắt buộc. Khi áp dụng, tổ chức phải xác định giá trị phù hợp và người có thẩm quyền phê duyệt.

## 2. Baseline giải quyết vấn đề gì?

Giả sử ba nhóm cùng xây dựng API xử lý dữ liệu khách hàng. Nhóm A yêu cầu xác thực cho mọi thao tác đọc dữ liệu; nhóm B chỉ kiểm tra token tại gateway; nhóm C có một endpoint xuất dữ liệu được gọi trực tiếp mà không đi qua gateway.

Nếu mỗi nhóm tự diễn giải “API phải an toàn”, mức bảo vệ sẽ phụ thuộc vào kinh nghiệm của từng người. Một baseline thống nhất có thể quy định:

> Mọi đường truy cập dữ liệu không công khai phải xác minh danh tính và kiểm tra quyền theo chủ thể, hành động và tài nguyên; đường gọi trực tiếp cũng phải chịu kiểm soát.

Từ quy định này, từng hệ thống phải xác định endpoint nào thuộc phạm vi, thành phần nào thực thi, ca kiểm thử nào chứng minh và ai xử lý khi có đường truy cập bị bỏ sót.

Baseline đem lại ba lợi ích chính:

1. **Tạo mặt bằng bảo vệ chung:** dự án không phải phát hiện lại những nhu cầu nền tảng.
2. **Làm rõ khoảng thiếu hụt:** so sánh trạng thái hiện tại với tập kiểm soát đã chọn.
3. **Tạo cơ sở truy vết:** biết vì sao một yêu cầu tồn tại và bằng chứng nào cho thấy nó được đáp ứng.

Baseline không đảm bảo rằng mọi rủi ro đã được xử lý. Một chức năng mới, một đường tích hợp mới hoặc cách lạm dụng đặc thù vẫn có thể đòi hỏi kiểm soát bổ sung từ threat modeling.

### 2.1. Các khái niệm dễ nhầm

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Chính sách bảo mật | Tổ chức yêu cầu nguyên tắc nào? | Truy cập dữ liệu phải phù hợp trách nhiệm công việc. |
| Danh mục kiểm soát | Có những biện pháp bảo vệ nào để lựa chọn? | Xác thực mạnh, phân quyền, quản lý khóa, giám sát, sao lưu. |
| Control baseline | Tập kiểm soát nền nào được áp dụng cho phạm vi này? | Dịch vụ có dữ liệu khách hàng phải có các kiểm soát xác thực, cách ly dữ liệu, audit và khôi phục đã chọn. |
| Yêu cầu bảo mật hệ thống | Hệ thống cụ thể phải có hành vi kiểm chứng được nào? | API xuất dữ liệu chỉ cho phép vai trò được duyệt truy cập tài nguyên trong tenant của người gọi. |
| Thiết kế và triển khai | Cơ chế nào đáp ứng yêu cầu? | Dịch vụ kiểm tra chính sách quyền với tenant lấy từ ngữ cảnh danh tính đã xác minh. |
| Bằng chứng xác minh | Dựa vào đâu kết luận đã đáp ứng? | Kết quả kiểm thử chéo tenant, cấu hình triển khai, bản ghi quyết định cấp quyền. |

Một baseline có thể chứa cả kiểm soát kỹ thuật lẫn hoạt động tổ chức, như xét duyệt quyền định kỳ hoặc diễn tập phục hồi. Tuy nhiên, bài học này tập trung vào cách chuyển chúng thành yêu cầu phục vụ thiết kế, phát triển và kiểm thử.

## 3. Phạm vi và rủi ro phải đi trước lựa chọn baseline

Trước khi chọn tập kiểm soát, cần mô tả ít nhất:

- **Tài sản và dữ liệu:** dữ liệu công khai, dữ liệu khách hàng, thông tin định danh, bí mật dịch vụ.
- **Tác nhân và đặc quyền:** khách chưa đăng nhập, người dùng, quản trị viên, tài khoản máy, nhà cung cấp.
- **Bề mặt truy cập:** giao diện web, API, tác vụ nền, công cụ quản trị, kênh hỗ trợ và đường truy cập trực tiếp.
- **Ranh giới tin cậy:** trình duyệt với API, tenant với tenant, ứng dụng với kho dữ liệu, dịch vụ với hệ thống ngoài.
- **Mức tác động:** hậu quả khi mất tính bí mật, tính toàn vẹn hoặc tính sẵn sàng.
- **Ràng buộc áp dụng:** cam kết hợp đồng, yêu cầu nội bộ và nghĩa vụ đã được người phụ trách xác định.

Không nên chỉ dùng một nhãn “rủi ro trung bình” để quyết định mọi kiểm soát. Một ứng dụng có mức tác động tổng thể vừa phải vẫn có thể có luồng thay đổi tài khoản quản trị cần bảo vệ chặt hơn.

### 3.1. Một cách tổ chức baseline nội bộ

Có thể tổ chức baseline theo tập nền chung và các gói bổ sung:

| Tập kiểm soát | Điều kiện kích hoạt minh họa | Nội dung điển hình |
|---|---|---|
| Nền chung | Mọi dịch vụ trong phạm vi quản lý | Quản lý danh tính, quyền tối thiểu, bảo vệ bí mật, ghi nhận sự kiện quan trọng, quy trình xử lý sự cố. |
| Bổ sung cho dữ liệu khách hàng | Hệ thống lưu hoặc xử lý dữ liệu không công khai của khách hàng | Phân tách dữ liệu, hạn chế xuất dữ liệu, kiểm soát thời hạn lưu, audit truy cập nhạy cảm. |
| Bổ sung cho đặc quyền cao | Có quản trị từ xa hoặc thao tác thay đổi quyền | Xác thực mạnh, kiểm tra lại danh tính cho thao tác nhạy cảm, giám sát thay đổi quyền. |
| Bổ sung cho dịch vụ cần phục hồi nhanh | Gián đoạn hoặc mất dữ liệu vượt ngưỡng được chấp nhận | Mục tiêu phục hồi, sao lưu được bảo vệ và diễn tập khôi phục. |

Các tập bổ sung có thể đồng thời áp dụng. Chúng không nhất thiết tạo thành một thang điểm duy nhất.

Điều kiện áp dụng phải kiểm chứng được. “Áp dụng cho hệ thống quan trọng” là chưa đủ; cần xác định quan trọng theo tiêu chí nào, ai phân loại và hồ sơ phân loại nằm ở đâu.

## 4. Quy trình chuyển baseline thành yêu cầu

### Bước 1: Xác định đơn vị áp dụng

Ghi rõ baseline áp dụng cho một ứng dụng, một dịch vụ, một nền tảng hay một luồng nghiệp vụ. Liệt kê thành phần nằm trong phạm vi và các phụ thuộc bên ngoài.

Ví dụ, phạm vi “dịch vụ hồ sơ khách hàng” có thể bao gồm API, worker xuất dữ liệu, kho lưu tệp, giao diện quản trị và pipeline triển khai. Nếu chỉ tính API chính, đường xuất dữ liệu có thể bị bỏ sót.

### Bước 2: Liên kết mục tiêu bảo vệ với kịch bản rủi ro

Mục tiêu “bảo vệ dữ liệu khách hàng” cần được cụ thể hóa:

- Người dùng tenant A thử truy cập hồ sơ của tenant B.
- Kẻ tấn công chiếm tài khoản quản trị rồi cấp thêm quyền.
- Người vận hành vô tình đưa token vào log.
- Tài khoản có quyền ghi dữ liệu xóa cả bản chính và bản sao lưu.

Mỗi kịch bản cần có hậu quả và giả định liên quan. Đây là căn cứ để chọn kiểm soát, mức yêu cầu và ưu tiên xử lý.

### Bước 3: Chọn tập nền và bổ sung theo điều kiện

Chọn baseline đã được tổ chức phê duyệt, ghi phiên bản và ngày áp dụng. Thêm các gói kiểm soát do loại dữ liệu, đặc quyền hoặc mục tiêu phục hồi kích hoạt.

Nếu mô hình đe dọa phát hiện rủi ro ngoài phạm vi tập nền, bổ sung kiểm soát và ghi lý do. Không chờ baseline chung được cập nhật mới xử lý rủi ro riêng của hệ thống.

### Bước 4: Tailoring — điều chỉnh có căn cứ

Tailoring là điều chỉnh baseline cho đúng bối cảnh. Mỗi thay đổi cần có lý do và khả năng truy vết:

| Kiểu điều chỉnh | Ví dụ | Điều phải làm rõ |
|---|---|---|
| Cụ thể hóa tham số | Xác định thời gian hết hạn phiên và thời hạn thu hồi quyền | Giá trị, điểm bắt đầu đo và cách đo. |
| Tăng cường | Thêm xác thực lại trước khi cấp quyền quản trị | Rủi ro nào kích hoạt và những luồng nào bị ảnh hưởng. |
| Dùng kiểm soát dùng chung | Dùng dịch vụ danh tính của nền tảng | Phần nền tảng bảo đảm, phần ứng dụng vẫn phải thực hiện và bằng chứng được dùng lại. |
| Đánh dấu không áp dụng | Không có đăng nhập bằng mật khẩu do ứng dụng hoàn toàn dùng nhà cung cấp danh tính | Kiến trúc chứng minh điều kiện, phạm vi loại trừ và kiểm soát danh tính thay thế trong luồng thực tế. |
| Đề xuất kiểm soát bù trừ | Chưa có cơ chế tự động nên áp dụng giới hạn phạm vi và giám sát bổ sung | Hiệu quả, hạn chế, thời hạn và rủi ro còn lại cần được chấp thuận. |

Không áp dụng khác với chưa làm được. “Nhóm chưa có thời gian triển khai” là thiếu hụt, không phải lý do để đánh dấu không áp dụng.

### Bước 5: Viết yêu cầu có thể kiểm chứng

Một mẫu diễn đạt hữu ích:

> Với [phạm vi/điều kiện], [thành phần/chủ thể] phải [hành vi bảo vệ], đạt [ngưỡng hoặc kết quả quan sát được]. Khi [tình huống lỗi], hệ thống phải [hành vi đã xác định]. Xác minh bằng [phương pháp và bằng chứng].

Không phải yêu cầu nào cũng cần một con số. “Mọi yêu cầu truy cập chéo tenant đều bị từ chối” có thể kiểm chứng bằng quy tắc quyết định quyền và tập ca kiểm thử thích hợp. Tuy nhiên, một vài ca kiểm thử thành công không đủ để chứng minh mọi đường truy cập đều đã được bao phủ; cần thêm kiểm kê và rà soát thiết kế.

### Bước 6: Gắn yêu cầu với thiết kế và kiểm thử

Đối với từng yêu cầu:

- Chỉ rõ điểm thực thi trong kiến trúc.
- Xác định người chịu trách nhiệm triển khai và người xác minh.
- Viết ca kiểm thử hợp lệ, bị từ chối, đường đi thay thế và tình huống lỗi.
- Chỉ rõ bằng chứng cần lưu, phiên bản được xác minh và nơi lưu được kiểm soát quyền truy cập.

Không dừng ở câu “đã dùng thư viện bảo mật”. Cần chứng minh thư viện được cấu hình và gọi đúng trên toàn bộ đường đi liên quan.

### Bước 7: Quyết định xử lý khoảng thiếu hụt

Yêu cầu chưa đạt phải dẫn đến hành động rõ ràng: hoàn thiện trước mốc phát hành, giảm phạm vi chức năng, trì hoãn triển khai hoặc xin ngoại lệ có thời hạn.

Mức ưu tiên phải xét khả năng bị khai thác và tác động nghiệp vụ. Không đếm số mục hoàn thành để thay cho đánh giá mức rủi ro.

## 5. Hồ sơ tối thiểu cho một kiểm soát nền

Để baseline có thể sử dụng trong phát triển, mỗi kiểm soát cần đủ thông tin cho người triển khai và người xác minh:

| Trường | Ý nghĩa |
|---|---|
| Mã và phiên bản | Định danh ổn định để truy vết thay đổi. |
| Mục tiêu bảo vệ | Tài sản hoặc thuộc tính an toàn cần bảo vệ. |
| Điều kiện áp dụng | Khi nào kiểm soát bắt buộc và cách xác định điều kiện đó. |
| Nội dung yêu cầu | Hành vi cần có, phạm vi và tham số phải điền. |
| Căn cứ rủi ro | Kịch bản đe dọa hoặc nghĩa vụ đã được xác nhận. |
| Trách nhiệm | Chủ kiểm soát, nhóm triển khai, bên cung cấp kiểm soát dùng chung nếu có. |
| Phương pháp xác minh | Kiểm tra cấu hình, thử nghiệm, rà soát kiến trúc, diễn tập hoặc kết hợp. |
| Tiêu chí đạt | Kết quả quan sát được để kết luận đáp ứng. |
| Bằng chứng | Loại bằng chứng, phiên bản và thời điểm xác minh. |
| Trạng thái áp dụng | Áp dụng, không áp dụng có lý do, hoặc ngoại lệ được phê duyệt. |
| Chu kỳ và sự kiện rà soát | Khi nào cần đánh giá lại, ngoài lịch định kỳ. |

Cần phân biệt **trạng thái áp dụng** với **trạng thái triển khai**. Một kiểm soát “áp dụng” có thể đang “chưa triển khai”, “đã triển khai nhưng chưa xác minh” hoặc “đã xác minh đạt”. Gộp tất cả vào một ô “Done” dễ che khuất thiếu hụt.

Ví dụ bản ghi có cấu trúc dưới đây chỉ minh họa nội dung một yêu cầu, không phải cấu hình chạy của ứng dụng:

```yaml
control_id: BL-AUTHZ-01
baseline_version: "1.0"
title: Cách ly truy cập dữ liệu giữa các tenant
applicability: Mọi đường truy cập dữ liệu riêng của tenant
risk_refs:
  - RISK-03
requirement_ids:
  - SEC-REQ-017
owner: Nhóm dịch vụ hồ sơ
enforcement: API, worker xuất dữ liệu và tầng truy vấn dữ liệu
verification:
  - Rà soát điểm thực thi quyền
  - Kiểm thử API chéo tenant và tác vụ nền
pass_criteria:
  - Không trả dữ liệu hoặc tạo tệp xuất của tenant khác
  - Yêu cầu bị từ chối không làm thay đổi dữ liệu
applicability_status: APPLICABLE
implementation_status: PLANNED
```

Trường bằng chứng được bổ sung khi có kết quả thực tế. Không điền “PASS” chỉ vì bản thiết kế đã được chấp thuận.

## 6. Baseline minh họa cho một dịch vụ nhiều tenant

Xét một dịch vụ lưu hồ sơ khách hàng, có giao diện web, API, worker xuất dữ liệu và giao diện quản trị. Các yêu cầu bên dưới được đánh số để dùng trong ví dụ truy vết; chúng không tạo thành baseline đầy đủ cho mọi hệ thống.

| Mã kiểm soát | Mục tiêu | Yêu cầu hệ thống minh họa | Xác minh chủ yếu |
|---|---|---|---|
| BL-AUTHN-01 | Chống truy cập bằng danh tính không hợp lệ | SEC-REQ-010: API dữ liệu riêng chỉ chấp nhận thông tin xác thực hợp lệ; token sai chữ ký, hết hạn hoặc sai đối tượng nhận phải bị từ chối. | Kiểm thử token và rà soát cấu hình xác minh. |
| BL-PRIV-01 | Hạn chế chiếm dụng đặc quyền | SEC-REQ-011: Luồng đăng nhập quản trị phải yêu cầu MFA; các đường đăng nhập dự phòng cũng phải được kiểm kê và bảo vệ. | Kiểm thử toàn bộ đường đăng nhập quản trị. |
| BL-AUTHZ-01 | Cách ly dữ liệu tenant | SEC-REQ-017: Mọi thao tác trên tài nguyên tenant phải kiểm tra quyền với tenant của danh tính đã xác minh và tài nguyên đích. | Ma trận quyền, kiểm thử API và worker. |
| BL-DATA-01 | Bảo vệ dữ liệu khi truyền và lưu | SEC-REQ-021: Dữ liệu khách hàng phải được bảo vệ trên các chặng truyền và các bản lưu đã kiểm kê; quyền sử dụng khóa tách khỏi quyền đọc bản lưu theo thiết kế được duyệt. | Kiểm tra luồng dữ liệu, cấu hình lưu trữ và quyền quản lý khóa. |
| BL-LOG-01 | Truy vết hành động nhạy cảm | SEC-REQ-030: Thay đổi quyền, xuất dữ liệu và thao tác quản trị phải có sự kiện audit chứa các trường quy định, không chứa bí mật xác thực. | Thực hiện thao tác mẫu, kiểm tra sự kiện và thử quyền truy cập log. |
| BL-REC-01 | Khôi phục sau mất dữ liệu | SEC-REQ-040: Dịch vụ phải đạt RPO 1 giờ và RTO 4 giờ trong kịch bản khôi phục đã xác định, có bằng chứng diễn tập. | Khôi phục từ bản sao lưu và đo kết quả. |

Những mô tả ngắn trong bảng cần được mở rộng thành đặc tả, đặc biệt về ranh giới áp dụng, cấu hình cụ thể và hành vi khi phụ thuộc bị lỗi. Các mục tiếp theo cho thấy cách mở rộng.

## 7. Đặc tả yêu cầu theo từng nhóm kiểm soát

### 7.1. Xác thực và vòng đời danh tính

Yêu cầu “có đăng nhập” bỏ sót nhiều quyết định thiết kế. Cần làm rõ:

- Loại chủ thể nào đăng nhập và dùng phương thức xác thực nào.
- Ai phát hành thông tin xác thực, ứng dụng kiểm tra những thuộc tính nào.
- Thời hạn phiên và cách kết thúc phiên khi tài khoản bị khóa.
- Cách thu hồi quyền truy cập sau thay đổi nhân sự hoặc sự cố.
- Cách phục hồi tài khoản và quản lý các đường truy cập khẩn cấp.

Ví dụ mở rộng SEC-REQ-010:

> API hồ sơ phải từ chối token truy cập không vượt qua kiểm tra chữ ký, bên phát hành, đối tượng nhận và thời hạn. Không được tin tenant hoặc vai trò từ một token chưa được xác minh. Khi dịch vụ xác thực cần thiết không khả dụng và không có căn cứ xác minh hợp lệ tại chỗ theo thiết kế, yêu cầu phải bị từ chối và được ghi nhận mà không lưu token nguyên vẹn.

Ca kiểm thử cần gồm token hợp lệ, bị sửa, hết hạn và token hợp lệ nhưng dành cho dịch vụ khác. Nếu thiết kế cho phép xác minh tại chỗ, phải làm rõ cơ chế cập nhật khóa và thời hạn thông tin được dùng.

Nếu yêu cầu khóa tài khoản phải có hiệu lực trong một khoảng thời gian, nhóm phải chọn cách thực hiện phù hợp như kiểm tra trạng thái, danh sách thu hồi hoặc vòng đời token. Việc token có chữ ký hợp lệ không tự chứng minh tài khoản vẫn được phép truy cập.

### 7.2. Phân quyền và tenant isolation

Ví dụ mở rộng SEC-REQ-017:

> Trên API và worker xuất dữ liệu, mọi thao tác đọc, sửa, xóa hoặc xuất tài nguyên phải kiểm tra chủ thể, hành động và tenant sở hữu tài nguyên. Giá trị tenant do người gọi gửi chỉ được dùng sau khi đối chiếu với ngữ cảnh danh tính và quyền đã xác minh. Khi thiếu thông tin quyết định quyền, hệ thống phải từ chối thao tác.

Các kiểm tra cần có:

1. Người dùng được phép truy cập tài nguyên đúng tenant.
2. Người dùng thử đổi mã tài nguyên sang tenant khác.
3. Người dùng cùng tenant nhưng không có quyền cho hành động đó.
4. Tác vụ nền được tạo khi còn quyền nhưng thực thi sau khi quyền đã thay đổi.
5. Đường truy cập trực tiếp bỏ qua giao diện hoặc gateway.
6. Yêu cầu bị từ chối không tạo tệp xuất, URL tải xuống hoặc tác dụng phụ trái phép.

Hành vi của tác vụ sau thay đổi quyền phải được đặc tả theo nghiệp vụ. Nếu cần quyền hiện hành tại thời điểm thực thi, worker phải kiểm tra lại thay vì chỉ tin quyết định lúc tạo tác vụ.

Kiểm tra ở giao diện giúp trải nghiệm người dùng, nhưng điểm thực thi quyền phải nằm ở thành phần người gọi không thể tự bỏ qua.

### 7.3. Bảo vệ dữ liệu và bí mật

“Mã hóa dữ liệu” cần được tách thành các phạm vi có thể xác minh:

- Chặng truyền từ người dùng tới điểm kết thúc kết nối bảo mật và các chặng tiếp theo.
- Cơ sở dữ liệu, tệp xuất, bản sao lưu, snapshot và dữ liệu tạm.
- Vị trí lưu khóa, quyền sử dụng khóa và trách nhiệm quản lý.
- Nơi bí mật ứng dụng được cấp phát, sử dụng, thay thế và thu hồi.
- Quy tắc thời hạn lưu và xóa dữ liệu ở từng loại bản sao.

Một yêu cầu có thể quy định rằng tệp xuất chỉ được lưu tại kho đã cấu hình bảo vệ dữ liệu, có quyền tải xuống giới hạn theo người nhận và được xóa theo thời hạn được duyệt. Tiêu chí kiểm thử phải bao gồm thử tải tệp bằng danh tính khác, kiểm tra cấu hình kho và kiểm tra tiến trình xóa.

Thuật toán, giao thức và tham số cụ thể phải được chọn theo chính sách kỹ thuật hiện hành đã được người phụ trách xác nhận. Không để cụm “mã hóa mạnh” làm tiêu chí đạt.

Mã hóa bản lưu không thay thế kiểm tra quyền khi ứng dụng đang đọc và trả dữ liệu ở dạng rõ cho người dùng.


### 7.4. Logging và khả năng truy vết

Ví dụ mở rộng SEC-REQ-030:

> Mọi thao tác thay đổi quyền, xuất dữ liệu và thay đổi cấu hình bảo mật phải tạo sự kiện audit gồm thời điểm, định danh chủ thể, tenant, loại hành động, tài nguyên hoặc phạm vi bị tác động, kết quả và mã tương quan. Không ghi mật khẩu, token truy cập, khóa bí mật hoặc toàn bộ nội dung hồ sơ vào sự kiện.

Đặc tả tiếp theo cần xác định:

- Những thành phần nào phát sinh sự kiện, kể cả worker và công cụ quản trị.
- Cách liên kết các sự kiện của cùng một thao tác qua nhiều dịch vụ.
- Ai được đọc log và ai được thay đổi cấu hình thu thập.
- Cách phát hiện mất sự kiện, sửa hoặc xóa log trái phép.
- Thời hạn lưu, cơ chế xóa và căn cứ lựa chọn.
- Hành vi khi bộ thu log không khả dụng.

Không thể mặc định mọi thao tác phải dừng khi hệ thống log lỗi. Một thao tác cấp quyền quản trị có thể cần bị chặn nếu không bảo đảm ghi nhận theo chính sách; một luồng khác có thể dùng hàng đợi bền vững với giới hạn rõ ràng. Yêu cầu phải xác định phương án, dung lượng đệm, xử lý khi đầy và cảnh báo tương ứng.

Tiêu chí đạt gồm tạo được sự kiện đúng khi thành công, khi bị từ chối và khi lỗi; không lộ bí mật; người không có quyền không thể đọc hoặc xóa log. Chỉ nhìn thấy một dòng log trong môi trường phát triển chưa đủ chứng minh toàn bộ yêu cầu.

### 7.5. Sao lưu và phục hồi

Trong ví dụ SEC-REQ-040:

- **RPO (Recovery Point Objective)** là mục tiêu về mức mất dữ liệu chấp nhận được, được biểu diễn theo thời gian. RPO 1 giờ nghĩa là trong kịch bản được xét, điểm dữ liệu có thể khôi phục không được cũ hơn thời điểm sự cố quá 1 giờ.
- **RTO (Recovery Time Objective)** là mục tiêu về thời gian khôi phục dịch vụ tới mức hoạt động đã thống nhất. RTO 4 giờ cần đi kèm định nghĩa thời điểm bắt đầu đo và điều kiện kết thúc.

Đặc tả có thể viết:

> Với kịch bản mất cơ sở dữ liệu chính, dịch vụ phải khôi phục tới trạng thái nghiệp vụ đã thống nhất trong 4 giờ tính từ thời điểm dịch vụ mất khả năng phục vụ được ghi nhận trong diễn tập. Điểm dữ liệu khôi phục phải cách thời điểm sự cố không quá 1 giờ. Việc khôi phục phải bao gồm dữ liệu, cấu hình và các phụ thuộc cần thiết để đọc được dữ liệu đã bảo vệ.

Cần kiểm tra thêm:

- Bản sao lưu có nằm ngoài phạm vi xóa của tài khoản ứng dụng bị chiếm dụng hay không.
- Khóa hoặc thông tin cần để giải mã có thể được khôi phục theo quy trình được duyệt hay không.
- Dữ liệu phục hồi có nhất quán giữa cơ sở dữ liệu, tệp đính kèm và trạng thái tác vụ hay không.
- Những bước thủ công có người thực hiện thay thế và hướng dẫn cập nhật hay không.
- Điểm phục hồi có được đánh giá là an toàn trong kịch bản dữ liệu bị sửa trái phép hay không.

Tác vụ backup báo thành công chưa chứng minh RPO hoặc RTO. Với chu kỳ sao lưu 1 giờ, thời gian chạy, lần sao lưu lỗi hoặc bản sao không dùng được vẫn có thể khiến mất dữ liệu vượt 1 giờ. Bằng chứng cần có diễn tập khôi phục và phép đo phù hợp với kịch bản.

## 8. Truy vết từ rủi ro tới bằng chứng

Chuỗi truy vết giúp trả lời câu hỏi: “Nếu bỏ hoặc thay đổi kiểm soát này, rủi ro nào sẽ tăng?”

```text
Mục tiêu bảo vệ + tài sản + kịch bản đe dọa
                    |
                    v
          Rủi ro cần được xử lý
                    |
                    v
       Kiểm soát nền + tailoring
                    |
                    v
        Yêu cầu bảo mật cụ thể
                    |
                    v
       Quyết định kiến trúc / cơ chế
                    |
                    v
       Kiểm thử, rà soát, diễn tập
                    |
                    v
     Bằng chứng + thiếu hụt + rủi ro còn lại
```

Một bảng truy vết tối thiểu:

| Rủi ro | Kiểm soát | Yêu cầu | Điểm thực thi | Xác minh và bằng chứng |
|---|---|---|---|---|
| RISK-03: Người dùng đọc dữ liệu tenant khác | BL-AUTHZ-01 | SEC-REQ-017 | Kiểm tra quyền tại API và worker; truy vấn giới hạn tài nguyên được phép | TC-017-A/B/C, báo cáo rà soát đường truy cập và kết quả trên bản phát hành xác định. |
| RISK-07: Chiếm tài khoản quản trị | BL-PRIV-01 | SEC-REQ-011 | Nhà cung cấp danh tính và chính sách truy cập quản trị | Kết quả thử đăng nhập, đường dự phòng và quy trình phục hồi tài khoản. |
| RISK-11: Mất dữ liệu sau sự cố | BL-REC-01 | SEC-REQ-040 | Cơ chế sao lưu, quyền bảo vệ bản sao và quy trình khôi phục | Báo cáo diễn tập, thời điểm dữ liệu phục hồi, thời gian đạt trạng thái hoạt động. |

Quan hệ thường là nhiều với nhiều: một rủi ro cần nhiều kiểm soát; một kiểm soát hỗ trợ nhiều yêu cầu. Không ép toàn bộ quan hệ vào một dòng nếu điều đó làm mất thông tin.

Bằng chứng nên gắn với phiên bản triển khai, môi trường, thời điểm và phạm vi kiểm tra. Kết quả kiểm thử của phiên bản cũ không tự động chứng minh một bản phát hành đã thay đổi điểm thực thi quyền.

Không đưa token, dữ liệu cá nhân thật hoặc bí mật vào hồ sơ chỉ để làm bằng chứng. Dùng dữ liệu thử và thông tin đã được giảm thiểu khi có thể; quản lý quyền truy cập bằng chứng theo độ nhạy cảm của nó.

## 9. Kiểm soát dùng chung và trách nhiệm được kế thừa

Một nền tảng có thể cung cấp dịch vụ danh tính, kho log hoặc sao lưu. Nhóm ứng dụng có thể dùng lại bằng chứng cho phần kiểm soát do nền tảng thực hiện, nhưng phải xác định rõ ranh giới.

Ví dụ với nhà cung cấp danh tính tập trung:

| Trách nhiệm nền tảng | Trách nhiệm ứng dụng |
|---|---|
| Vận hành đăng nhập và chính sách MFA đã thỏa thuận. | Chỉ chấp nhận thông tin xác thực hợp lệ dành cho chính ứng dụng. |
| Cung cấp thông tin khóa và cơ chế cập nhật. | Xác minh đúng bên phát hành, đối tượng nhận và thời hạn; xử lý lỗi phù hợp. |
| Quản lý nhóm hoặc thuộc tính danh tính theo phạm vi dịch vụ. | Ánh xạ danh tính sang quyền nghiệp vụ và kiểm tra quyền trên tài nguyên. |
| Cung cấp bằng chứng về phần kiểm soát được cam kết. | Xác minh việc tích hợp, cấu hình và các đường truy cập thay thế. |

“Đã dùng SSO” không kết luận rằng phân quyền tenant đã được bảo đảm. “Kho dữ liệu hỗ trợ mã hóa” cũng không chứng minh mọi bản sao đã bật tính năng đó.

Hồ sơ kế thừa nên ghi nhà cung cấp kiểm soát, phạm vi được bảo đảm, điều kiện sử dụng, bằng chứng còn phù hợp và phần ứng dụng phải tự xác minh. Nếu nhà cung cấp thay đổi cấu hình hoặc phạm vi dịch vụ, cần đánh giá tác động tới các yêu cầu phụ thuộc.

## 10. Quản lý thiếu hụt và ngoại lệ

Baseline chỉ hữu ích khi mục chưa đạt được hiển thị và có người chịu trách nhiệm. Không nên đổi nội dung yêu cầu để một triển khai chưa đáp ứng trở thành “đạt”.

### 10.1. Phân biệt bốn tình huống

| Tình huống | Cách xử lý |
|---|---|
| Áp dụng và đã xác minh đạt | Ghi bằng chứng cùng phạm vi và thời điểm đánh giá. |
| Áp dụng nhưng chưa đạt | Mở hành động khắc phục, ưu tiên theo rủi ro và gắn mốc xử lý. |
| Không áp dụng do điều kiện thực tế không tồn tại | Ghi căn cứ, người xác nhận và điều kiện khiến phải đánh giá lại. |
| Áp dụng nhưng cần tạm chấp nhận thiếu hụt | Xin ngoại lệ có thời hạn, biện pháp bổ sung và người chấp nhận rủi ro còn lại. |

Ngoại lệ không có nghĩa là kiểm soát đã đạt. Kiểm soát bù trừ cũng không mặc nhiên tương đương kiểm soát gốc; cần đánh giá hiệu quả của nó đối với cùng kịch bản rủi ro.

### 10.2. Hồ sơ ngoại lệ minh họa

Giả sử một công cụ quản trị cũ chưa hỗ trợ MFA. Nhóm đề xuất cho phép sử dụng trong 14 ngày để hoàn tất chuyển đổi.

Hồ sơ cần ghi:

- Kiểm soát và yêu cầu bị ảnh hưởng: BL-PRIV-01, SEC-REQ-011.
- Phạm vi: đúng công cụ, tài khoản và thao tác nào.
- Nguyên nhân thiếu hụt, tác động và rủi ro còn lại.
- Biện pháp tạm thời: tài khoản cá nhân, truy cập qua cổng quản trị có MFA, giới hạn mạng và thời gian truy cập, giám sát thao tác.
- Giới hạn của biện pháp: còn đường truy cập nào bỏ qua cổng, phiên tồn tại bao lâu, ai kiểm tra.
- Người chịu trách nhiệm sửa, kế hoạch thay thế, ngày hết hạn và người có thẩm quyền chấp nhận rủi ro.
- Hành động khi hết hạn: thu hồi đường truy cập hoặc thực hiện quyết định mới đã được phê duyệt trước thời điểm đó.

Nếu công cụ vẫn có thể được gọi trực tiếp để bỏ qua cổng quản trị, đề xuất chưa chứng minh được hiệu quả bù trừ. Cần kiểm tra thực tế đường đi, không chỉ dựa trên sơ đồ.

Không tự động gia hạn ngoại lệ. Gia hạn phải xem xét lại rủi ro, mức sử dụng, hiệu quả giám sát và tiến độ khắc phục.

## 11. Baseline trong vòng đời phát triển và compliance

### 11.1. Tại các mốc của sản phẩm

| Mốc | Hoạt động cần thực hiện | Kết quả |
|---|---|---|
| Khởi tạo hoặc thay đổi phạm vi | Phân loại dữ liệu, tài sản, tác động và chọn baseline | Phiên bản baseline cùng phạm vi áp dụng. |
| Phân tích yêu cầu và threat modeling | Điều chỉnh kiểm soát, bổ sung rủi ro đặc thù | Yêu cầu, lý do áp dụng và tiêu chí chấp nhận. |
| Thiết kế | Chỉ rõ điểm thực thi, phụ thuộc và trách nhiệm | Quyết định kiến trúc và kế hoạch xác minh. |
| Triển khai và kiểm thử | Kiểm tra các hành vi và cấu hình liên quan | Bằng chứng, thiếu hụt và hành động khắc phục. |
| Quyết định phát hành | Đánh giá yêu cầu chưa đạt và ngoại lệ còn hiệu lực | Quyết định bởi người có thẩm quyền theo mức rủi ro. |
| Vận hành và thay đổi | Theo dõi thay đổi, sự cố và hiệu lực kiểm soát | Đánh giá lại, cập nhật yêu cầu hoặc baseline khi cần. |

Không chỉ rà soát theo lịch. Cần đánh giá lại khi thêm API công khai, thêm loại dữ liệu, thay đổi mô hình tenant, chuyển nhà cung cấp danh tính, sửa cơ chế quyền hoặc phát hiện sự cố làm sai giả định thiết kế.

### 11.2. Kiểm soát phiên bản

Mỗi hệ thống nên biết mình đang áp dụng baseline phiên bản nào và đã tailoring ra sao. Khi baseline chuyển từ phiên bản 1.0 lên 1.1:

1. Xác định mục được thêm, bỏ, sửa nội dung hoặc sửa tham số.
2. Tìm yêu cầu và hệ thống chịu ảnh hưởng qua liên kết truy vết.
3. Đánh giá khoảng thiếu hụt và tác động triển khai.
4. Xác định thời hạn chuyển đổi cùng cơ chế xử lý ngoại lệ.
5. Xác minh lại phần thay đổi và cập nhật bằng chứng.

Không thay phiên bản trên giấy mà giữ nguyên các yêu cầu cũ chưa được đối chiếu.

### 11.3. Liên hệ với compliance

Baseline có thể giúp tổ chức hóa các yêu cầu xuất phát từ nghĩa vụ đã xác định. Tuy nhiên, đáp ứng baseline nội bộ không tự động chứng minh đáp ứng toàn bộ một hợp đồng, quy định hoặc chương trình đánh giá bên ngoài.

Cần tách rõ:

- Nguồn nghĩa vụ và phạm vi thực sự áp dụng.
- Cách tổ chức diễn giải nghĩa vụ thành mục tiêu kiểm soát.
- Kiểm soát và yêu cầu được chọn để đáp ứng.
- Phương pháp đánh giá và bằng chứng mà bên có thẩm quyền chấp nhận.
- Phần nghĩa vụ chưa được baseline bao phủ.

Một kiểm soát có thể hỗ trợ nhiều nghĩa vụ, nhưng không nên dùng một ánh xạ tên gọi để khẳng định tương đương hoàn toàn. Nội dung, phạm vi và cách kiểm chứng mới quyết định mức đáp ứng.

## 12. Đánh giá mức bao phủ mà không tạo cảm giác an toàn giả

Một dashboard có thể báo “đạt 90%” khi 9 trong 10 kiểm soát được đánh dấu hoàn thành. Nếu mục còn lại là cách ly tenant, mức rủi ro vẫn có thể không chấp nhận được.

Có thể theo dõi đồng thời:

- Số yêu cầu áp dụng đã xác minh đạt trên tổng số yêu cầu áp dụng, kèm phiên bản và phạm vi.
- Số yêu cầu rủi ro cao chưa đạt và tuổi của thiếu hụt.
- Số kiểm soát đã triển khai nhưng chưa có bằng chứng phù hợp.
- Số ngoại lệ sắp hết hạn hoặc đã hết hạn.
- Số thay đổi ảnh hưởng kiểm soát nhưng chưa đánh giá lại.
- Số kiểm soát dùng chung chưa có xác nhận về phạm vi và trách nhiệm.

Nếu tính tỷ lệ, phải công bố mẫu số và cách xử lý mục không áp dụng. Không tính ngoại lệ thành “đã đạt”; không cộng các phần trăm cơ học để suy ra “hệ thống an toàn bao nhiêu phần trăm”.

Mục tiêu của đo lường là hỗ trợ quyết định xử lý rủi ro, không phải tối ưu số ô được đánh dấu.

## 13. Những lỗi thường gặp

| Lỗi | Vì sao thiếu hiệu quả | Cách sửa |
|---|---|---|
| Sao chép toàn bộ danh mục kiểm soát thành baseline | Không xét phạm vi, tạo nhiều mục hình thức và khó triển khai | Chọn theo điều kiện áp dụng, tác động và rủi ro; lưu lý do. |
| Viết “phải bảo mật”, “mã hóa mạnh”, “log đầy đủ” | Người triển khai và kiểm thử không có cùng cách hiểu | Chỉ rõ hành vi, dữ liệu, điểm thực thi, tham số và tiêu chí đạt. |
| Chỉ bảo vệ giao diện chính | API trực tiếp, worker và công cụ quản trị có thể đi vòng | Kiểm kê đường truy cập và kiểm thử đường thay thế. |
| Coi tính năng có sẵn là đã đáp ứng | Tính năng có thể chưa bật hoặc không bao phủ đúng phạm vi | Kiểm tra cấu hình thực tế và hành vi trên bản triển khai. |
| Dùng kiểm soát dùng chung để bỏ mọi trách nhiệm ứng dụng | Ranh giới giữa nền tảng và ứng dụng bị bỏ trống | Ghi rõ phần kế thừa và phần phải tự triển khai, xác minh. |
| Đánh dấu không áp dụng vì chưa triển khai | Che giấu khoảng thiếu hụt đang tồn tại | Giữ trạng thái áp dụng, tạo hành động hoặc ngoại lệ. |
| Xem bản thiết kế là bằng chứng triển khai đạt | Chưa chứng minh hành vi thực tế | Kết hợp rà soát thiết kế với kiểm thử, cấu hình và diễn tập. |
| Phê duyệt ngoại lệ vô thời hạn | Rủi ro tạm thời trở thành mặc định | Đặt hạn, chủ sở hữu, kế hoạch sửa và điều kiện kết thúc. |

## 14. Bài tập thực hành

Bạn phụ trách bổ sung chức năng xuất hồ sơ khách hàng. Người dùng tạo tác vụ từ API; worker tạo tệp trên kho lưu trữ; người dùng tải tệp qua liên kết. Hệ thống dùng nhà cung cấp danh tính tập trung.

Hãy thực hiện:

1. Xác định tài sản, tác nhân, ranh giới tin cậy và phạm vi áp dụng baseline cho cả ba bước.
2. Viết ít nhất ba kịch bản rủi ro, gồm truy cập chéo tenant, thay đổi quyền trong lúc chờ và rò rỉ liên kết tải.
3. Chọn kiểm soát nền, chỉ rõ phần được kế thừa từ nền tảng và phần ứng dụng chịu trách nhiệm.
4. Viết ba yêu cầu có tiêu chí đạt, gồm một yêu cầu phân quyền, một yêu cầu audit và một yêu cầu vòng đời tệp.
5. Lập bảng truy vết tới điểm thực thi, ca kiểm thử và bằng chứng.
6. Giả sử worker chưa kiểm tra lại quyền tại thời điểm thực thi: ghi thiếu hụt và đề xuất cách xử lý trước khi phát hành.

### Gợi ý đánh giá kết quả

- Danh tính khởi tạo tác vụ, tenant và tài nguyên cần được ràng buộc trong dữ liệu tác vụ; worker không được tin một tenant tùy ý chưa xác minh.
- Nếu chính sách yêu cầu quyền hiện hành khi thực thi và khi tải xuống, hai điểm đó phải được kiểm tra hoặc có cơ chế tương đương được đặc tả rõ.
- Liên kết tải cần được coi là một phần của mô hình truy cập. Nếu là liên kết mang quyền truy cập, phải đánh giá nguy cơ chuyển tiếp, thời hạn hiệu lực và cơ chế thu hồi; không mặc định người giữ liên kết chính là người khởi tạo.
- Sự kiện audit cần liên kết được tạo tác vụ, hoàn tất hoặc thất bại, và tải tệp khi thuộc phạm vi theo dõi; không ghi nguyên liên kết bí mật vào log.
- Quy tắc xóa cần bao phủ tệp xuất và các bản sao thuộc phạm vi. Các bản lưu có vòng đời riêng phải được nhận diện trong yêu cầu thay vì bỏ qua.
- Quyết định cho phát hành khi còn thiếu hụt cần dựa trên đánh giá rủi ro và thẩm quyền được xác định, không dựa vào tỷ lệ mục đã hoàn thành.

## 15. Câu hỏi tự kiểm tra

1. Khi nào một mục nên là “không áp dụng”, khi nào phải là “áp dụng nhưng chưa đạt”?
2. Một API chỉ kiểm tra token ở gateway có thể đáp ứng baseline trong điều kiện nào? Cần kiểm tra thêm đường truy cập nào?
3. Tại sao MFA tập trung không thay thế kiểm tra quyền truy cập tài nguyên của ứng dụng?
4. Một kiểm soát đã triển khai nhưng chưa có bằng chứng phù hợp nên được báo cáo ra sao?
5. Vì sao sao lưu mỗi giờ chưa đủ chứng minh RPO 1 giờ?
6. Một ngoại lệ phải chứa thông tin nào để người khác có thể đánh giá lại?
7. Khi baseline đổi phiên bản, cần làm gì để biết hệ thống vẫn đáp ứng?
8. Tại sao đáp ứng baseline nội bộ chưa đủ để kết luận tuân thủ toàn bộ một nghĩa vụ bên ngoài?

Một baseline có giá trị sử dụng khi mỗi kiểm soát áp dụng dẫn tới yêu cầu cụ thể, có chủ sở hữu, có cách xác minh và có quyết định rõ ràng đối với phần chưa đạt. Đó là cách nối mục tiêu an toàn và mô hình đe dọa với thiết kế, kiểm thử và quản lý rủi ro trong suốt vòng đời hệ thống.


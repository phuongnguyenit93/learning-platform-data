# JEA command coverage: đo độ phủ tác vụ quản trị trong PAM

## 1. Độ phủ JEA phải trả lời câu hỏi nào?

Just Enough Administration (JEA) giới hạn những thao tác quản trị mà một người có thể thực hiện qua một endpoint PowerShell được cấu hình cho nhiệm vụ cụ thể. Trong chương Metrics của PAM, **JEA command coverage** giúp trả lời: bao nhiêu tác vụ quản trị hợp lệ đã thực hiện được qua giao diện JEA, với đúng phạm vi tài nguyên và không làm lộ thêm quyền ngoài thiết kế?

Nếu đội vận hành được phép khởi động lại đúng một dịch vụ ứng dụng, việc nhìn thấy lệnh `Restart-Service` chưa đủ chứng minh độ phủ. Cần biết người đó có khởi động lại đúng dịch vụ được giao hay không, có bị từ chối khi nhắm tới dịch vụ khác hay không, và kết quả đó thuộc phiên bản cấu hình nào.

Ví dụ, một endpoint cho phép:

- Đọc trạng thái của dịch vụ ứng dụng được giao.
- Khởi động lại dịch vụ đó trong quy trình đã được phê duyệt.
- Đọc nhóm log vận hành thuộc ứng dụng.
- Thực hiện các tác vụ khác thông qua hàm quản trị có phạm vi xác định.

Nếu endpoint đồng thời cho phép đọc tùy ý mọi file dưới danh tính thực thi có quyền cao, dashboard độ phủ vẫn có thể xanh trong khi ranh giới least privilege đã bị phá vỡ. Vì vậy, số lệnh khả dụng chỉ là thông tin về bề mặt được mở; nó không phải thước đo đầy đủ cho hiệu quả kiểm soát JEA.

Trong bài này, các công thức và tên chỉ số là một thiết kế đo lường nội bộ minh họa. Không giả định PowerShell hoặc một sản phẩm PAM cung cấp sẵn một chỉ số chuẩn duy nhất mang tên “JEA command coverage”.

## 2. Phân biệt lệnh, tác vụ và quyền thực sự

Ba khái niệm sau thường bị trộn lẫn:

| Khái niệm | Ví dụ | Vai trò trong đo lường |
|---|---|---|
| Lệnh khả dụng | Người dùng gọi được `Restart-AppService` | Cho biết giao diện quản trị được công bố |
| Tác vụ quản trị | Khởi động lại dịch vụ của ứng dụng Billing tại môi trường kiểm thử | Là đơn vị có ý nghĩa nghiệp vụ để đánh giá độ phủ |
| Quyền có hiệu lực | Danh tính thực thi có thể tác động tới tài nguyên nào, bằng những đường nào | Xác định phạm vi kiểm soát và hậu quả nếu cấu hình hoặc hàm bao bị lỗi |

Một lệnh có thể phục vụ nhiều tác vụ. Ngược lại, một tác vụ có thể cần nhiều lệnh hoặc nhiều bước. Đếm từng cmdlet như một tác vụ sẽ làm sai mẫu số khi đội kỹ thuật tách hoặc gộp hàm.

Cũng cần tách **người kết nối** khỏi **danh tính thực thi**. Endpoint JEA có thể chạy thao tác dưới một danh tính khác với tài khoản của người kết nối, tùy cấu hình. Kiểm thử phải đi qua endpoint bằng đúng tài khoản và nhóm được cấp quyền, thay vì dùng tài khoản quản trị trên máy chủ để chạy lệnh trực tiếp.

Đường kiểm soát cần quan sát là:

```text
Người dùng và nhóm được cấp quyền
    -> endpoint JEA cụ thể
    -> role capability có hiệu lực
    -> lệnh, tham số và hàm bao được công bố
    -> kiểm tra phạm vi bên trong hàm
    -> danh tính thực thi và tài nguyên đích
    -> kết quả, audit và bằng chứng
```

Độ phủ đúng phải gắn với toàn bộ đường này. Kết quả “lệnh chạy thành công” trên máy quản trị không thay thế được bằng chứng “người vận hành đúng vai trò thực hiện được tác vụ qua endpoint JEA”.

### 2.1. Những gì không nên tính như tác vụ quản trị

Một endpoint có thể có các lệnh phục vụ khám phá, hiển thị kết quả hoặc hoạt động của phiên. Không tự động coi mọi tên do cơ chế khám phá lệnh trả về là một tác vụ PAM đã được bảo vệ.

Tương tự, một hàm trợ giúp nội bộ được gọi bên trong hàm bao không nhất thiết là một giao diện mà người dùng được phép gọi trực tiếp. Cần kiểm tra cả hai mặt: tác vụ hợp lệ hoạt động và đường gọi nội bộ không bị công bố ngoài chủ đích.

## 3. Chọn đơn vị đo trước khi xây dashboard

Đơn vị nên là một **hợp đồng thao tác** có thể kiểm thử, thay vì một tên lệnh đứng riêng. Có thể biểu diễn bằng bộ thuộc tính:

```text
operation_id
+ nhóm người dùng
+ endpoint
+ môi trường
+ tài nguyên đích
+ hành động
+ điều kiện và tham số được phép
+ phiên bản chính sách
```

Ví dụ hai hợp đồng khác nhau:

```text
OP-SVC-RESTART:
Nhóm AppOps được khởi động lại dịch vụ Billing tại môi trường test
qua endpoint AppOps-Test, chỉ bằng AppId nằm trong danh sách cho phép.

OP-LOG-READ:
Nhóm AppOps được đọc log vận hành Billing trong khoảng thời gian giới hạn
qua endpoint AppOps-Test, không được tự cung cấp đường dẫn file.
```

Cùng một hàm có thể được mở ở môi trường test nhưng chưa được triển khai ở production. Không được suy rộng kết quả kiểm thử test thành độ phủ production. Đội đo lường phải chốt rõ mỗi dòng kiểm kê đại diện cho một môi trường riêng hay chỉ cho một loại tác vụ; quy ước đó phải giữ ổn định giữa các kỳ.

Khi một loại tác vụ áp dụng cho nhiều máy chủ, nên theo dõi thêm phạm vi triển khai. Một phép thử đạt trên một máy không chứng minh tất cả endpoint cùng tên trên các máy khác có cấu hình giống nhau.

### 3.1. Hồ sơ tối thiểu của một hợp đồng

| Trường | Ý nghĩa |
|---|---|
| `operation_id` | Mã ổn định, không đổi chỉ vì đổi tên hàm |
| `owner` | Chủ sở hữu nghiệp vụ và người duyệt phạm vi |
| `principal_scope` | Nhóm hoặc vai trò được phép kết nối |
| `endpoint_scope` | Endpoint, máy chủ hoặc nhóm máy nằm trong phạm vi |
| `resource_scope` | Tài nguyên và môi trường được phép tác động |
| `command_surface` | Hàm hoặc cmdlet được công bố, cùng ràng buộc tham số |
| `positive_tests` | Trường hợp hợp lệ phải thực hiện thành công |
| `negative_tests` | Trường hợp vượt quyền phải bị chặn |
| `risk_weight` | Trọng số đã thống nhất trước kỳ đo |
| `evidence_policy` | Bằng chứng cần lưu, thời hạn hiệu lực và điều kiện kiểm thử lại |
| `policy_version` | Phiên bản cấu hình và mã hàm bao được đánh giá |

Thiếu những trường này, dashboard dễ đo “cái hiện đang có” thay vì đo khoảng cách với nhu cầu quản trị đã được duyệt.

## 4. Cố định mẫu số bằng danh mục tác vụ

Bắt đầu từ nhu cầu vận hành thực tế: runbook, yêu cầu hỗ trợ, danh mục dịch vụ, tài khoản đặc quyền và các đường truy cập đang được sử dụng. Sau đó xác định tác vụ nào đủ điều kiện đưa qua JEA.

Không lấy danh sách lệnh đang mở trên endpoint làm toàn bộ mẫu số. Cách đó loại khỏi phép đo mọi tác vụ chưa được triển khai và có thể tạo ra mức 100% ngay từ đầu.

Một kỳ đo cần có:

1. Danh mục tác vụ trong phạm vi được phê duyệt.
2. Quy tắc đưa vào, loại ra và đánh dấu chưa xác định.
3. Mốc chốt danh mục và phiên bản.
4. Phân loại rủi ro, môi trường và chủ sở hữu.
5. Danh sách ngoại lệ có lý do, người duyệt và ngày hết hạn.

Tác vụ đang tồn tại nhưng chưa khảo sát phải xuất hiện dưới trạng thái `UNKNOWN` hoặc một chỉ số độ đầy đủ kiểm kê riêng. Không âm thầm bỏ chúng khỏi báo cáo.

Nếu tác vụ buộc phải dùng một kênh khác và được chấp nhận là không thuộc phạm vi JEA, ghi nhận rõ lý do cùng kiểm soát thay thế. Một ngoại lệ không tự biến thành tác vụ đã được JEA bao phủ.

### 4.1. Ngăn việc làm đẹp mẫu số

Giả sử có 20 tác vụ trong danh mục, trong đó 12 tác vụ thực hiện được qua JEA. Việc chuyển 8 tác vụ còn lại sang mục “khác” mà không có thay đổi phạm vi được duyệt không phải là cải thiện độ phủ.

Khi phạm vi thay đổi hợp lệ, báo cáo nên trình bày hai phép nhìn:

- Kết quả trên danh mục hiện hành, phục vụ quyết định vận hành.
- So sánh trên một tập tác vụ chung giữa hai kỳ, phục vụ đánh giá xu hướng.

Một tỷ lệ tăng vì danh mục thu hẹp cần được giải thích khác với tỷ lệ tăng vì đã triển khai thêm tác vụ an toàn.

## 5. Bộ chỉ số nên đi cùng nhau

### 5.1. Độ phủ chức năng

Gọi:

- `N`: số tác vụ đủ điều kiện trong danh mục đã chốt.
- `P`: số tác vụ vượt qua toàn bộ kiểm thử hợp lệ bắt buộc, trên phạm vi triển khai được khai báo.

```text
Functional coverage = P / N × 100%
```

Chỉ số này cho biết người vận hành có làm được công việc qua JEA hay chưa. Nó chưa chứng minh các hành vi vượt quyền đã bị chặn.

Nếu `N = 0`, kết quả là `N/A`, kèm lý do và trạng thái kiểm kê. Không báo 100% cho một mẫu số rỗng.

### 5.2. Độ phủ có ràng buộc quyền

Một tác vụ chỉ được tính là đã bao phủ an toàn trong kỳ đo khi đồng thời thỏa các điều kiện đã định:

```text
SafeCovered(i) =
    FunctionalPass(i)
    AND MandatoryNegativeTestsPass(i)
    AND IntendedRoleBoundaryPass(i)
    AND EvidenceFresh(i)
    AND NoDisqualifyingOpenDefect(i)
```

```text
Safe coverage = số tác vụ SafeCovered / N × 100%
```

Trong công thức này:

- `MandatoryNegativeTestsPass` yêu cầu tất cả kiểm thử từ chối bắt buộc của tác vụ đều đạt.
- `IntendedRoleBoundaryPass` kiểm tra đúng nhóm, đúng endpoint và không có quyền bổ sung ngoài thiết kế.
- `EvidenceFresh` yêu cầu bằng chứng còn hiệu lực theo chính sách và phù hợp phiên bản đang chạy.
- `NoDisqualifyingOpenDefect` loại khỏi tử số các tác vụ đang có lỗi mở đủ nghiêm trọng để vô hiệu hóa kết luận.

Đây là định nghĩa vận hành có thể kiểm chứng, không phải tuyên bố rằng kiểm thử đã chứng minh hệ thống tuyệt đối an toàn. Tập kiểm thử hữu hạn luôn cần được cập nhật khi có thay đổi hoặc phát hiện đường vượt quyền mới.

### 5.3. Độ phủ có trọng số rủi ro

Nếu mọi tác vụ đều có trọng số bằng nhau, một tác vụ đọc trạng thái và một tác vụ thay đổi dịch vụ trọng yếu sẽ đóng góp như nhau. Có thể bổ sung trọng số `w_i`:

```text
Weighted safe coverage =
    Σ(w_i × SafeCovered(i)) / Σ(w_i) × 100%
```

Trong đó `SafeCovered(i)` bằng 1 nếu đạt, bằng 0 nếu không đạt. Trọng số phải được thống nhất trước khi thấy kết quả. Không giảm trọng số của một tác vụ chỉ vì tác vụ đó đang thất bại.

Luôn công bố cả số lượng tuyệt đối. Một tỷ lệ có trọng số tốt không thể hiện rõ rằng hàng chục tác vụ nhỏ vẫn còn sử dụng quyền quản trị rộng.

### 5.4. Tỷ lệ kiểm thử từ chối đạt

```text
Negative-test pass rate =
    số kiểm thử vượt quyền bị chặn đúng
    / tổng kiểm thử vượt quyền bắt buộc × 100%
```

Tỷ lệ này bổ sung cho độ phủ, nhưng không thay thế điều kiện “mọi kiểm thử bắt buộc đều đạt” ở cấp tác vụ.

Một kiểm thử cho phép tác động tài nguyên production ngoài phạm vi là lỗi nghiêm trọng, kể cả khi 99 kiểm thử còn lại đều bị chặn. Không lấy 99% làm cơ sở chấp nhận lỗi đó.

### 5.5. Độ đầy đủ bằng chứng và phạm vi triển khai

Hai chỉ số bổ trợ thường hữu ích:

```text
Evidence completeness =
    số tác vụ có bộ bằng chứng bắt buộc hợp lệ / N × 100%

Deployment verification coverage =
    số đơn vị triển khai đã xác minh cấu hình và kiểm thử theo chính sách
    / tổng đơn vị triển khai thuộc phạm vi × 100%
```

“Đơn vị triển khai” có thể là cặp máy chủ–endpoint hoặc một đơn vị khác đã được chốt. Nếu dùng lấy mẫu, phải ghi rõ thiết kế mẫu, giới hạn suy rộng và các trường hợp bắt buộc kiểm tra riêng.

### 5.6. Mức sử dụng thực tế

Độ phủ thể hiện khả năng thực hiện tác vụ qua JEA; mức sử dụng thể hiện người vận hành có thực sự đi qua kênh đó hay không.

```text
Observed JEA usage =
    số lần thực hiện tác vụ trong phạm vi qua JEA
    / tổng số lần thực hiện cùng loại tác vụ quan sát được qua mọi kênh × 100%
```

Mẫu số chỉ đáng tin khi quan sát được các kênh liên quan. Nếu chưa thu thập được thao tác từ RDP, phiên PowerShell khác hoặc tài khoản dùng chung, ghi rõ giới hạn. Không tuyên bố đã loại bỏ đường quản trị rộng chỉ từ log của endpoint JEA.

## 6. Ví dụ tính toán: tỷ lệ chức năng cao vẫn có thể che lỗi quyền

Một đội vận hành có sáu tác vụ thuộc cùng một phạm vi đo đã chốt:

| Mã | Tác vụ | Trọng số | Kiểm thử hợp lệ | Kiểm thử từ chối bắt buộc | Được tính an toàn |
|---|---|---:|---|---|---|
| OP-01 | Khởi động lại dịch vụ ứng dụng | 5 | Đạt | Đạt | Có |
| OP-02 | Đọc trạng thái dịch vụ ứng dụng | 4 | Đạt | Đạt | Có |
| OP-03 | Đọc log vận hành ứng dụng | 4 | Đạt | Có lỗi vượt phạm vi | Không |
| OP-04 | Tái khởi tạo application pool được duyệt | 3 | Chưa đạt | Chưa đủ bằng chứng | Không |
| OP-05 | Đọc độ dài hàng đợi ứng dụng | 2 | Đạt | Đạt | Có |
| OP-06 | Đọc trạng thái cấu hình cho phép | 2 | Đạt | Đạt | Có |

Giả định các tác vụ được đánh dấu “Có” cũng đã đạt điều kiện vai trò, phiên bản cấu hình và bằng chứng còn hiệu lực.

Kết quả:

```text
Tổng số tác vụ:                            6
Tác vụ đạt chức năng:                      5
Tác vụ được tính an toàn:                  4

Functional coverage:                      5 / 6  = 83,3%
Safe coverage:                            4 / 6  = 66,7%

Tổng trọng số:                            5 + 4 + 4 + 3 + 2 + 2 = 20
Trọng số đạt chức năng:                    5 + 4 + 4 + 2 + 2     = 17
Trọng số được tính an toàn:                5 + 4 + 2 + 2         = 13

Weighted functional coverage:             17 / 20 = 85%
Weighted safe coverage:                   13 / 20 = 65%
```

OP-03 đọc được log cần thiết nhưng một kiểm thử còn đọc được nội dung ngoài ứng dụng được cấp quyền. Đây là lỗi ranh giới quyền, không phải một phần trăm độ phủ còn thiếu thông thường.

Nếu toàn bộ tập có 20 kiểm thử từ chối và 19 kiểm thử đạt, tỷ lệ đạt là 95%. Dù vậy, OP-03 vẫn bị loại khỏi tử số an toàn. Tùy chính sách xử lý lỗi, endpoint có thể cần bị hạn chế hoặc tạm dừng cho tới khi khắc phục.

Hành động ưu tiên là xử lý lỗi vượt phạm vi OP-03, sau đó hoàn thiện OP-04. Việc bổ sung nhiều lệnh đọc ít rủi ro không giải quyết lỗi quyền đang mở.

## 7. Ma trận kiểm thử cho từng tác vụ JEA

Mỗi dòng kiểm kê cần liên kết tới các trường hợp kiểm thử cụ thể. Chỉ kiểm tra `Get-Command` hoặc danh sách role capability chưa đủ: khám phá lệnh xác nhận giao diện, không xác nhận toàn bộ hành vi.

### 7.1. Kiểm thử hợp lệ

Đối với tác vụ khởi động lại dịch vụ:

- Người dùng thuộc đúng nhóm kết nối được endpoint được cấp.
- Lệnh quản trị công bố xuất hiện và nhận đúng các tham số dự kiến.
- Dịch vụ trong danh sách được phép được tác động theo hợp đồng.
- Kết quả thực tế được xác minh bằng một quan sát độc lập thích hợp.
- Không phát sinh thay đổi ngoài mục tiêu được khai báo.
- Bằng chứng liên kết được người kết nối, phiên và yêu cầu thao tác.

Không dùng “không ném exception” làm tiêu chí duy nhất. Hàm có thể bỏ qua thao tác, trả về thông báo thành công giả hoặc chạy sai mục tiêu.

Với hành động làm thay đổi trạng thái, cần môi trường kiểm thử, tiền điều kiện và phương án khôi phục phù hợp. Bài toán đo lường không tự tạo quyền chạy thao tác phá gián đoạn trên production.

### 7.2. Kiểm thử từ chối

| Nhóm kiểm thử | Ví dụ | Kết quả cần chứng minh |
|---|---|---|
| Sai chủ thể | Người ngoài nhóm AppOps kết nối endpoint | Truy cập bị từ chối theo cấu hình |
| Sai tài nguyên | AppOps yêu cầu thao tác ứng dụng khác | Không có tác động lên tài nguyên ngoài phạm vi |
| Sai hành động | Gọi một thao tác không được công bố | Không thực hiện được hành động đó |
| Sai tham số | Dùng tùy chọn mở rộng quyền hoặc vượt giá trị cho phép | Bị từ chối trước khi gây thay đổi |
| Sai hình thức đầu vào | Gửi mảng, wildcard hoặc dữ liệu không đúng hợp đồng | Bị giới hạn theo hợp đồng, không mở rộng đích |
| Đường gọi thay thế | Gọi trực tiếp lệnh nền thay vì hàm bao | Không vượt được lớp kiểm tra dự kiến |
| Sai môi trường | Dùng endpoint test để yêu cầu tài nguyên production | Không tác động được tài nguyên production |
| Trộn vai trò | Tài khoản đồng thời thuộc nhiều nhóm được gán role | Tập quyền có hiệu lực vẫn phù hợp thiết kế |

Chỉ đưa một tình huống vào kiểm thử bắt buộc khi nó áp dụng cho hợp đồng và đã xác định cách đánh giá. Ví dụ, nếu hàm chỉ nhận `AppId` và không nhận đường dẫn thì việc kiểm thử đường dẫn tùy ý trực tiếp trên giao diện đó không giống kiểm thử một hàm nhận `Path`.

“Bị từ chối” cũng cần chứng cứ. Nếu lệnh lỗi do DNS hoặc dịch vụ đã dừng, đó không phải bằng chứng bộ kiểm soát tham số hoạt động.

### 7.3. Trạng thái kiểm thử nên tách rõ

```text
PASS          Đạt điều kiện mong đợi và có bằng chứng.
FAIL          Hành vi quan sát được trái với hợp đồng.
NOT_RUN       Chưa thực hiện.
INCONCLUSIVE  Đã chạy nhưng chưa kết luận, ví dụ lỗi hạ tầng.
NOT_APPLICABLE Không áp dụng, có lý do được duyệt.
```

`NOT_RUN` và `INCONCLUSIVE` không được quy đổi thành đạt. Trường hợp `NOT_APPLICABLE` cần có lý do; không được dùng để loại mọi kiểm thử khó thực hiện.

## 8. Hàm bao và ràng buộc tham số ảnh hưởng trực tiếp đến độ phủ

JEA có thể công bố cmdlet, hàm hoặc những thành phần khác tùy cấu hình. Vì vậy, cùng một tác vụ cần được đánh giá theo bề mặt thật sự được mở.

Với một nhu cầu hẹp, giao diện như sau thường dễ xác định phạm vi hơn một tham số đích tùy ý:

```powershell
# Hợp đồng giao diện minh họa, không phải mã triển khai endpoint.
Restart-AppService -AppId Billing
Get-AppOperationsLog -AppId Billing -WindowMinutes 15
```

Trong thiết kế minh họa:

- `AppId` được ánh xạ ở phía máy chủ sang tài nguyên được duyệt.
- Người gọi không tự truyền tên máy, tài khoản thực thi hoặc đường dẫn.
- Khoảng thời gian và số lượng kết quả được giới hạn.
- Hàm bao không nhận đoạn script hoặc chuỗi lệnh tùy ý để thực thi.
- Lệnh nền không được công bố thêm theo cách bỏ qua ràng buộc của hàm bao.

Một hàm có tên hẹp nhưng bên trong chuyển chuỗi người dùng vào cơ chế thực thi lệnh tùy ý vẫn có thể mở quyền rộng. Khi đo, phải gắn kết quả với phiên bản mã hàm bao; chỉ so sánh tên hàm giữa hai kỳ sẽ bỏ qua thay đổi này.

### 8.1. Tính đến tổ hợp role capability

Quyền thực tế của một tài khoản phụ thuộc vào các vai trò áp dụng cho tài khoản đó. Nếu một tài khoản thuộc nhiều nhóm, kết quả có thể rộng hơn bài kiểm thử thực hiện bằng tài khoản chỉ thuộc một nhóm.

Tối thiểu, ma trận nên có:

1. Người chỉ thuộc nhóm vai trò được đánh giá.
2. Người thuộc các tổ hợp nhóm có thể xuất hiện trong thực tế.
3. Người không được cấp quyền endpoint.
4. Các trường hợp thay đổi nhóm liên quan theo quy trình cấp và thu hồi quyền.

Thực hiện kiểm thử trên phiên mới khi cần phản ánh thay đổi cấu hình hoặc ngữ cảnh xác thực. Không coi một phiên đã mở từ trước là bằng chứng rằng thay đổi cấp hoặc thu hồi quyền đã có hiệu lực đầy đủ.

### 8.2. Tách lỗi JEA với lỗi quyền của danh tính thực thi

Nếu một lệnh được công bố đúng nhưng thất bại vì danh tính thực thi thiếu quyền lên dịch vụ, độ phủ chức năng chưa đạt. Nếu danh tính thực thi có quyền rất rộng, chức năng có thể đạt nhưng hậu quả của lỗi hàm bao sẽ lớn hơn.

Vì vậy, một kế hoạch cải thiện hợp lý phối hợp cả hai tầng: giới hạn giao diện JEA và giới hạn quyền cần thiết của danh tính thực thi. Không tăng quyền của danh tính thực thi đến mức quản trị toàn máy chỉ để làm xanh mọi kiểm thử.

## 9. Thu thập dữ liệu và bằng chứng có thể truy ngược

Một bản ghi kết quả nên đủ để người khác kiểm tra lại kết luận mà không phải dựa vào ảnh chụp dashboard.

Ví dụ mô hình dữ liệu minh họa:

```yaml
measurement:
  scope_id: appops-test
  inventory_version: inventory-12
  policy_version: policy-8
  test_suite_version: suite-6
  measured_at_utc: "2026-11-01T02:00:00Z"

operation:
  id: OP-SVC-RESTART
  endpoint: AppOps-Test
  environment: test
  principal_scope: AppOps-Test-Operators
  resource_scope: Billing
  risk_weight: 5

result:
  functional_pass: true
  mandatory_negative_tests_pass: true
  intended_role_boundary_pass: true
  evidence_fresh: true
  disqualifying_open_defect: false
  positive_tests_passed: 3
  positive_tests_required: 3
  negative_tests_passed: 7
  negative_tests_required: 7

evidence:
  run_id: jea-run-1042
  endpoint_config_digest: sha256-example-config
  role_capability_digest: sha256-example-role
  wrapper_module_digest: sha256-example-module
  test_report_ref: evidence/jea-run-1042/report
  session_record_ref: evidence/jea-run-1042/session
  change_request_ref: CHG-EXAMPLE
```

Các giá trị digest trong ví dụ là ký hiệu minh họa, không phải checksum hợp lệ. Trong hệ thống thật, dùng giá trị được tính từ artifact thực tế và ghi rõ cách xác định bộ cấu hình có hiệu lực.

### 9.1. Bằng chứng nào cần được ghép với nhau?

Một bộ bằng chứng có thể gồm:

- Định danh bộ kiểm thử và thời điểm chạy.
- Tài khoản hoặc định danh được bảo vệ của người kết nối, cùng nhóm áp dụng.
- Máy chủ, endpoint và phiên bản cấu hình.
- Phiên bản module chứa hàm bao.
- Đầu vào kiểm thử đã lọc dữ liệu nhạy cảm.
- Kết quả mong đợi, kết quả thực tế và mã trường hợp.
- Transcript, log sự kiện hoặc dữ liệu audit đã được cấu hình.
- Quan sát xác nhận trạng thái tài nguyên trước và sau thao tác.
- Phiếu thay đổi hoặc phê duyệt có liên quan.

Không giả định có transcript là đã có mọi dữ liệu cần thiết. Mức chi tiết và tính liên kết phụ thuộc cấu hình logging, cách thực thi và nguồn quan sát. Cần xác minh nguồn nào thực sự ghi nhận được điều cần chứng minh.

Không đưa mật khẩu, token, nội dung bí mật hoặc log ứng dụng chứa dữ liệu nhạy cảm vào nhãn metric. Lưu bằng chứng ở nơi có phân quyền, chính sách lưu giữ và bảo vệ tính toàn vẹn phù hợp.

### 9.2. Khi nào bằng chứng hết hiệu lực?

Không chỉ tuổi của bản ghi quyết định độ mới. Bằng chứng có thể không còn áp dụng ngay khi:

- Thay đổi endpoint hoặc role capability.
- Thay đổi mã hàm bao, module phụ thuộc hoặc hành vi lệnh nền.
- Thay đổi nhóm được cấp quyền hoặc danh tính thực thi.
- Thay đổi tài nguyên đích, quyền hệ điều hành hoặc môi trường.
- Phát hiện đường vượt quyền liên quan đến trường hợp đã kiểm thử.

Chính sách cần quy định sự kiện nào làm kết quả trở thành `STALE` và phải kiểm thử lại phần nào. Không đặt một thời hạn dài rồi coi mọi thay đổi bên trong thời hạn đó đều được bảo đảm.

## 10. Tính metric từ bộ dữ liệu minh họa bằng PowerShell

Đoạn sau chỉ tính số liệu trong bộ nhớ từ sáu tác vụ ở ví dụ. Nó không kết nối endpoint, không chạy lệnh quản trị và không phải bộ kiểm thử JEA.

```powershell
$operations = @(
    [pscustomobject]@{ Id = 'OP-01'; Weight = 5; Functional = $true;  Safe = $true  }
    [pscustomobject]@{ Id = 'OP-02'; Weight = 4; Functional = $true;  Safe = $true  }
    [pscustomobject]@{ Id = 'OP-03'; Weight = 4; Functional = $true;  Safe = $false }
    [pscustomobject]@{ Id = 'OP-04'; Weight = 3; Functional = $false; Safe = $false }
    [pscustomobject]@{ Id = 'OP-05'; Weight = 2; Functional = $true;  Safe = $true  }
    [pscustomobject]@{ Id = 'OP-06'; Weight = 2; Functional = $true;  Safe = $true  }
)

$totalCount = $operations.Count
$totalWeight = ($operations | Measure-Object -Property Weight -Sum).Sum

$functionalOps = @($operations | Where-Object { $_.Functional })
$safeOps = @($operations | Where-Object { $_.Safe })

$functionalWeight = ($functionalOps | Measure-Object -Property Weight -Sum).Sum
$safeWeight = ($safeOps | Measure-Object -Property Weight -Sum).Sum

if ($totalCount -eq 0 -or $totalWeight -le 0) {
    throw 'Mau so khong hop le; phai bao N/A va kiem tra danh muc.'
}

[pscustomobject]@{
    TotalOperations              = $totalCount
    FunctionalOperations         = $functionalOps.Count
    SafeOperations               = $safeOps.Count
    FunctionalCoveragePercent    = [math]::Round(
        100.0 * $functionalOps.Count / $totalCount, 2
    )
    SafeCoveragePercent          = [math]::Round(
        100.0 * $safeOps.Count / $totalCount, 2
    )
    WeightedFunctionalPercent    = [math]::Round(
        100.0 * $functionalWeight / $totalWeight, 2
    )
    WeightedSafePercent          = [math]::Round(
        100.0 * $safeWeight / $totalWeight, 2
    )
}
```

Kết quả mong đợi:

```text
TotalOperations              : 6
FunctionalOperations         : 5
SafeOperations               : 4
FunctionalCoveragePercent    : 83.33
SafeCoveragePercent          : 66.67
WeightedFunctionalPercent    : 85
WeightedSafePercent          : 65
```

Trong pipeline thật, không nhập tay cột `Safe` để đạt mục tiêu báo cáo. Giá trị này phải được suy ra từ các điều kiện đã chốt ở mục 5.2 và bộ bằng chứng tương ứng. Cũng cần kiểm tra mã tác vụ không trùng, trọng số hợp lệ và không thiếu dòng trong danh mục.

Không tính trung bình cộng tỷ lệ của các nhóm nếu mẫu số khác nhau. Khi cần tổng hợp độ phủ không trọng số, cộng tử số và mẫu số tương ứng rồi mới chia; khi dùng trọng số, cộng phần đóng góp trọng số theo cùng một định nghĩa.

## 11. Dashboard phải dẫn tới quyết định

Một dashboard có ích nên cho người vận hành nhìn thấy tỷ lệ, số tuyệt đối và lý do chưa đạt.

| Nhóm thông tin | Cách trình bày gợi ý | Quyết định hỗ trợ |
|---|---|---|
| Phạm vi | Phiên bản danh mục, số tác vụ, môi trường | Hiểu mẫu số và giới hạn của báo cáo |
| Chức năng | Tác vụ đạt / tổng tác vụ | Ưu tiên nhu cầu vận hành chưa được phục vụ |
| Ranh giới quyền | Tác vụ an toàn, lỗi từ chối theo mức độ | Khắc phục hoặc hạn chế endpoint có lỗi quyền |
| Trọng số | Độ phủ an toàn có trọng số | Ưu tiên khoảng trống rủi ro cao |
| Bằng chứng | Số tác vụ stale, not-run, inconclusive | Lập lịch xác minh lại |
| Triển khai | Endpoint hoặc máy chủ đã xác minh / trong phạm vi | Phát hiện chênh lệch cấu hình |
| Sử dụng | Tỷ lệ thực hiện qua JEA và đường quản trị khác | Xác định chỗ còn dùng quyền rộng |
| Ngoại lệ | Số ngoại lệ và ngày hết hạn | Xem xét gia hạn hoặc đóng ngoại lệ |

Nên có khả năng mở từ một tác vụ chưa đạt sang test case, bằng chứng, lỗi và chủ sở hữu. Một biểu đồ chỉ có đường phần trăm không cho biết đội nào cần làm gì.

### 11.1. Gate quan trọng hơn một ngưỡng chung

Ví dụ chính sách nội bộ minh họa:

```text
- Có lỗi cho phép thao tác ngoài phạm vi:
  mở sự cố và áp dụng biện pháp hạn chế theo mức độ.

- Tác vụ rủi ro cao thiếu kiểm thử bắt buộc:
  không tính là an toàn; cần kế hoạch xử lý có người chịu trách nhiệm.

- Bằng chứng không còn khớp cấu hình đang chạy:
  đánh dấu stale và xác minh lại trước khi khôi phục kết luận.

- Coverage giảm sau một thay đổi:
  kiểm tra cả regression, lỗi thu thập và thay đổi mẫu số.
```

Không có một ngưỡng phần trăm phù hợp với mọi tổ chức. Các mục tiêu cần gắn với rủi ro, nhu cầu vận hành và chất lượng quan sát. Một lỗi quyền nghiêm trọng không nên được bù bằng điểm tốt ở nhóm ít rủi ro.

## 12. Quy trình vận hành một kỳ đo

### Bước 1: Chốt phạm vi

Xác nhận danh mục tác vụ, môi trường, endpoint, chủ thể được cấp quyền và trọng số. Đưa các trường chưa khảo sát vào danh sách phải làm rõ.

### Bước 2: Liên kết tác vụ với giao diện JEA

Ghi rõ lệnh hoặc hàm bao nào cung cấp tác vụ, tham số nào được mở và tài nguyên nào nằm trong phạm vi. Xác minh không có đường gọi khác làm bỏ qua ràng buộc dự kiến.

### Bước 3: Chuẩn bị kiểm thử

Định nghĩa trường hợp hợp lệ, vượt quyền, tiền điều kiện, kết quả cần quan sát và cách khôi phục. Xác định trường hợp nào phải chạy ở từng endpoint, trường hợp nào có thể dùng bằng chứng cấu hình kết hợp lấy mẫu theo chính sách.

### Bước 4: Thực hiện bằng đúng chủ thể

Kiểm thử qua endpoint bằng tài khoản đại diện cho vai trò thực. Dùng phiên mới khi cần phản ánh phiên bản hoặc ngữ cảnh quyền mới. Thu thập kết quả mà không đưa dữ liệu nhạy cảm vào metric.

### Bước 5: Phân loại kết quả

Tách `FAIL`, `NOT_RUN`, `INCONCLUSIVE` và `STALE`. Lỗi hạ tầng không phải bằng chứng chặn quyền; tác vụ chạy được nhưng vượt phạm vi không phải tác vụ an toàn.

### Bước 6: Tính và công bố

Tính độ phủ chức năng, an toàn, trọng số, bằng chứng và phạm vi triển khai. Công bố cả tử số, mẫu số, phiên bản danh mục và ngoại lệ.

### Bước 7: Xử lý khoảng trống

Ưu tiên lỗi vượt quyền, sau đó giải quyết thiếu chức năng theo rủi ro và tác động vận hành. Giao chủ sở hữu, thời hạn và tiêu chí xác minh lại.

### Bước 8: Gắn với thay đổi và thu hồi quyền

Sau thay đổi endpoint, nhóm, hàm bao hoặc tài nguyên, vô hiệu hóa các kết luận không còn áp dụng và chạy lại phần kiểm thử liên quan. Dùng kết quả để hỗ trợ lộ trình giảm quyền thường trực, nhưng chỉ đóng đường quyền rộng sau khi đánh giá đủ nhu cầu, ngoại lệ và phương án khẩn cấp.

## 13. Các sai lệch thường gặp

### “Mở nhiều lệnh hơn thì coverage tốt hơn”

Mở thêm lệnh có thể tăng khả năng vận hành và đồng thời tăng bề mặt đặc quyền. Chỉ tính cải thiện khi phục vụ tác vụ trong danh mục và đạt ràng buộc kiểm thử.

### “Lệnh xuất hiện thì tác vụ đã được hỗ trợ”

Khám phá lệnh không chứng minh quyền thực thi lên tài nguyên, kết quả nghiệp vụ hoặc tính đúng đắn của ràng buộc tham số. Cần kiểm thử hành vi.

### “Positive test đạt nên có thể bỏ negative test”

Một đầu vào hợp lệ chạy được không chứng minh đầu vào vượt phạm vi bị chặn. Hai loại kiểm thử trả lời hai câu hỏi khác nhau.

### “Endpoint hỏng thì mọi yêu cầu bị chặn, vậy kiểm soát tốt”

Endpoint hỏng không cung cấp được chức năng và cũng không chứng minh ranh giới quyền khi endpoint hoạt động. Ghi lỗi hạ tầng, giữ kết quả chưa kết luận và đo lại.

### “Test bằng admin nhanh hơn và tương đương”

Tài khoản admin có thể có nhóm, endpoint access hoặc đường quyền khác. Phải đo dưới chủ thể đại diện cho phạm vi được báo cáo.

### “Giữ nguyên tên endpoint thì bằng chứng cũ vẫn đúng”

Tên không xác định toàn bộ cấu hình. Hàm bao hoặc role capability đã thay đổi có thể khiến kết quả cũ không còn áp dụng.

### “Coverage 100% nghĩa là không cần tài khoản quản trị nữa”

Coverage chỉ có ý nghĩa trên danh mục, phạm vi và bộ kiểm thử được khai báo. Cần kiểm tra mức sử dụng thực tế, tác vụ ngoài danh mục, truy cập khẩn cấp và các đường quyền còn lại trước khi quyết định thu hồi.

### “Bỏ tác vụ chưa xong khỏi danh mục để so sánh cho đẹp”

Đó là thay đổi mẫu số, không phải cải thiện kỹ thuật. Giữ lịch sử danh mục và giải thích thay đổi phạm vi.

## 14. Bài tập áp dụng

Một đội báo cáo “đã đưa 18 trong 20 tác vụ quản trị qua JEA”. Trong 18 tác vụ đó, hai tác vụ có bằng chứng hết hiệu lực và một tác vụ khác còn lỗi cho phép tác động tài nguyên ngoài phạm vi. Giả định ba tác vụ này khác nhau; 15 tác vụ còn lại đạt tất cả điều kiện an toàn. Hai tác vụ chưa đưa qua JEA đều còn thuộc phạm vi.

Hãy xác định:

1. Độ phủ chức năng theo dữ liệu đã có là bao nhiêu?
2. Độ phủ an toàn là bao nhiêu?
3. Cần bổ sung dữ liệu gì để tính độ phủ có trọng số?
4. Vì sao chưa thể kết luận người vận hành đã bỏ đường quản trị rộng?
5. Hành động nào cần được ưu tiên?

Gợi ý phân tích:

- Báo cáo chức năng ban đầu là `18 / 20 = 90%`; cần làm rõ bằng chứng hết hiệu lực có làm kết luận chức năng hiện tại thành chưa xác minh hay không. Nếu chính sách chức năng yêu cầu bằng chứng hiện hành, phải loại hai tác vụ đó khỏi tử số chức năng và báo `16 / 20 = 80%`.
- Theo điều kiện an toàn đã nêu, chỉ 15 tác vụ đủ điều kiện: `15 / 20 = 75%`.
- Cần trọng số được duyệt của đủ 20 tác vụ, không chỉ 15 tác vụ đạt.
- Cần quan sát cách thực hiện tác vụ qua các kênh khác cùng tình trạng quyền thường trực còn tồn tại.
- Lỗi cho phép tác động tài nguyên ngoài phạm vi phải được đánh giá và xử lý theo mức độ; hai tác vụ stale cần xác minh lại, hai tác vụ chưa triển khai cần kế hoạch khép khoảng trống.

Bài tập cho thấy định nghĩa độ mới phải được ghi ngay trong hợp đồng metric. Nếu hai nhóm hiểu khác nhau về “đạt chức năng”, cùng một danh mục có thể tạo ra các tỷ lệ không so sánh được.

## 15. Điểm cần nhớ

JEA command coverage nên đo các tác vụ quản trị được thực hiện qua đúng endpoint, đúng người, đúng tài nguyên và đúng tham số. Số lượng tên lệnh được mở không thể thay thế danh mục tác vụ và kiểm thử hành vi.

Một bộ chỉ số có ý nghĩa trong PAM cần kết hợp độ phủ chức năng, độ phủ có ràng buộc quyền, trọng số rủi ro, bằng chứng còn hiệu lực, phạm vi triển khai và mức sử dụng thực tế. Khi có lỗi vượt quyền, quyết định xử lý phải dựa trên lỗi cụ thể; một tỷ lệ tổng hợp cao không xóa được rủi ro đó.

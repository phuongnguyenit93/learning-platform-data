# Đo mức giảm standing privilege

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), **standing privilege** là quyền đặc biệt tồn tại sẵn để một chủ thể có thể sử dụng mà không cần được cấp lại quyền cho từng khoảng công việc. Ví dụ gồm quyền quản trị được gán thường trực cho người dùng, quyền đặc biệt của tài khoản dịch vụ và đường truy cập trực tiếp tới một tài khoản quản trị dùng chung.

Chương **JIT và JEA** hướng tới hai thay đổi: chỉ kích hoạt quyền trong thời gian cần thiết bằng Just-in-Time (JIT), và thu hẹp khả năng được thực hiện bằng Just-Enough Administration/Access (JEA). Đo mức giảm standing privilege cần chứng minh cả quyền nào đã được loại bỏ, quyền nào chỉ được thu hẹp, và quyền tạm thời có thực sự hết hiệu lực trên hệ thống đích hay không.

Bài học trình bày phương pháp đo áp dụng cho người quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Kết quả đo phải có thể truy ngược tới kiểm kê quyền, dữ liệu thực thi, cấu hình PAM và bằng chứng phục vụ kiểm toán hoặc ứng phó sự cố.

## 1. Cần trả lời những câu hỏi nào?

Một báo cáo có ý nghĩa cần trả lời được:

1. Có bao nhiêu danh tính còn giữ ít nhất một quyền đặc biệt thường trực?
2. Những danh tính đó còn làm được những thao tác gì trên những tài nguyên nào?
3. Quyền đặc biệt tồn tại trong bao lâu, kể cả quyền được kích hoạt tạm thời?
4. Có những đường truy cập nào đi vòng PAM, chưa được kiểm kê hoặc chưa chứng minh được việc thu hồi?
5. Mức giảm có duy trì được trong vận hành thực tế mà vẫn đáp ứng công việc không?

Số tài khoản được đưa vào vault, số lần đổi mật khẩu hoặc số phiên đi qua PAM không trực tiếp trả lời các câu hỏi trên. Các hoạt động đó có giá trị quản lý credential và giám sát, nhưng không tự chứng minh đặc quyền thường trực đã giảm.

## 2. Thống nhất định nghĩa trước khi tính toán

### 2.1. Phân biệt các trạng thái quyền

| Trạng thái | Ý nghĩa trong phép đo | Cách theo dõi |
| --- | --- | --- |
| Quyền thường trực | Quyền thực thi đã tồn tại liên tục, không phụ thuộc một lần kích hoạt có giới hạn cho nhiệm vụ cụ thể | Tính vào standing privilege |
| Quyền eligible | Chủ thể đủ điều kiện yêu cầu hoặc kích hoạt một quyền nhưng quyền thực thi chưa hoạt động | Theo dõi riêng phạm vi eligible và điều kiện kích hoạt |
| Quyền JIT đang hoạt động | Quyền thực thi được bật trong khoảng thời gian được cấp | Tính vào tổng thời gian phơi lộ đặc quyền |
| Quyền đã thu hồi hiệu lực | Các điểm thực thi thuộc phạm vi đo không còn chấp nhận quyền đó | Kết thúc khoảng hiệu lực khi có bằng chứng |
| Quyền không rõ trạng thái | Thiếu dữ liệu để xác nhận tồn tại hoặc thu hồi | Báo chưa xác định, không mặc định bằng không |

Quyền eligible không được cộng vào standing privilege chỉ vì bản ghi đủ điều kiện còn tồn tại. Tuy nhiên, khả năng tự kích hoạt quyền mạnh mà không có kiểm soát phù hợp vẫn là một rủi ro riêng. Báo cáo cần nêu rõ kích hoạt có yêu cầu phê duyệt độc lập, xác thực bổ sung, ràng buộc ngữ cảnh hay chỉ cần chủ thể tự yêu cầu.

Một token có thời hạn ngắn cũng không tự đồng nghĩa với JIT. Nếu tài khoản dịch vụ liên tục tự nhận token mới và luôn có cùng quyền đặc biệt, khả năng sử dụng quyền có thể vẫn là thường trực trong toàn bộ cửa sổ đo.

### 2.2. Tách danh tính, tài khoản và credential

Một người có thể sở hữu nhiều tài khoản; một tài khoản dịch vụ có thể có nhiều credential; một credential có thể cho phép truy cập tới nhiều tài nguyên. Vì vậy phải ghi rõ đơn vị đang đếm.

- **Danh tính:** người hoặc workload được nhận diện ổn định.
- **Tài khoản/principal:** đối tượng được nền tảng dùng để gán quyền.
- **Credential:** phương tiện xác thực, chẳng hạn mật khẩu, khóa hoặc token.
- **Quyền hiệu lực:** khả năng thực sự có thể sử dụng sau khi xét vai trò, nhóm, kế thừa, điều kiện và cơ chế thực thi của nền tảng.

Nếu nhiều người sử dụng một tài khoản quản trị dùng chung, không được coi việc chỉ có một tài khoản là bằng chứng chỉ có một người có quyền. Nên báo cáo cả số principal đặc quyền lẫn số chủ thể có khả năng sử dụng principal đó, trong giới hạn mà bằng chứng ánh xạ cho phép.

Đổi mật khẩu chỉ thay credential. Chuyển credential vào vault chỉ thay cách quản lý hoặc cấp phát credential. Muốn xác nhận giảm quyền phải xem những khả năng truy cập nào còn tồn tại sau thay đổi.

### 2.3. Chọn ranh giới hệ thống

Phạm vi đo cần ghi rõ:

```text
Loại chủ thể: người dùng, tài khoản dịch vụ, workload, tài khoản khẩn cấp
Tài nguyên: hệ thống, môi trường và tập tài sản được kiểm kê
Khả năng đặc quyền: bộ thao tác được phân loại theo ngữ nghĩa
Đường truy cập: trực tiếp, qua nhóm, qua vai trò, qua PAM, qua ủy quyền
Cửa sổ thời gian: thời điểm bắt đầu và kết thúc, cùng múi giờ chuẩn
Nguồn bằng chứng: IAM, hệ thống đích, PAM, danh mục tài sản và kho kiểm toán
```

Nếu chỉ đo một nhóm máy chủ production, không trình bày kết quả như mức giảm của toàn tổ chức. Nếu chưa đo được tài khoản dịch vụ, phải nêu phần đó chưa được bao phủ.

## 3. Xây dựng đơn vị quyền có thể so sánh

Đếm tên vai trò thường không đủ. Hai vai trò có thể cùng tên nhưng khác tài nguyên; hai tên khác nhau có thể cấp cùng khả năng; một vai trò có thể được tách thành nhiều vai trò nhỏ mà tổng quyền không thay đổi.

Một đơn vị phân tích hữu ích là bộ ba chuẩn hóa:

```text
(danh_tính, tài_nguyên, khả_năng_đặc_quyền)
```

Gắn thêm điều kiện và khoảng hiệu lực nếu chúng ảnh hưởng đến quyền thực thi. Ví dụ:

```text
(user:ops-17, cluster:prod-a, service.reload)
(workload:backup-02, database:orders, backup.restore)
```

Chuẩn hóa cần dựa trên khả năng thực tế. Không nên đánh đồng “đọc chỉ số sức khỏe” với “đọc toàn bộ dữ liệu” chỉ vì cả hai cùng có từ `read`. Tương tự, một quyền có thể nạp mã, sửa chính sách hoặc tạo credential cho tài khoản mạnh hơn cần được phân tích về khả năng mở rộng quyền.

### Quyền hiệu lực và đường cấp quyền

Cùng một bộ ba có thể được cấp trực tiếp và qua một nhóm. Khi tính số quyền hiệu lực hoặc thời gian phơi lộ, chỉ tính một lần cho cùng khả năng trong cùng thời điểm. Tuy nhiên, vẫn phải giữ các đường cấp quyền trong bằng chứng để chứng minh đã loại bỏ tất cả đường thường trực.

Ví dụ:

```text
Trước thay đổi:
  ops-17 -> gán trực tiếp -> quản trị prod-a
  ops-17 -> nhóm platform-admin -> quản trị prod-a

Sau khi xóa gán trực tiếp:
  ops-17 -> nhóm platform-admin -> quản trị prod-a
```

Số bản ghi gán quyền giảm một, nhưng quyền quản trị hiệu lực của `ops-17` chưa giảm. Nếu một đường thường trực còn tồn tại, chuyển đường còn lại sang JIT cũng chưa loại bỏ standing privilege cho khả năng đó.

## 4. Thiết lập baseline và mẫu số

**Baseline** là trạng thái tham chiếu trước thay đổi, có thời điểm, phạm vi và nguồn dữ liệu xác định. Nó không chỉ là một con số chụp từ giao diện quản trị.

Một baseline nên lưu:

- Danh sách chủ thể, tài nguyên và quyền đặc biệt trong phạm vi.
- Các quan hệ nhóm, vai trò, kế thừa và ủy quyền cần để tính quyền hiệu lực.
- Đường truy cập trực tiếp và credential đang có thể sử dụng.
- Khoảng hiệu lực của quyền trong cửa sổ đo.
- Trạng thái bao phủ dữ liệu, phần chưa xác định và ngoại lệ.
- Phiên bản quy tắc chuẩn hóa và cách tính chỉ số.

### 4.1. Dùng hai góc nhìn về mẫu số

| Góc nhìn | Mục đích | Điều cần chú ý |
| --- | --- | --- |
| Nhóm cố định từ baseline | Đo tác động lên cùng tập đối tượng ban đầu | Chủ thể hoặc tài nguyên bị loại khỏi phạm vi phải có lý do và bằng chứng |
| Toàn bộ phạm vi đang vận hành | Phát hiện quyền mới, tài sản mới và tăng trưởng ngoài dự án | Mẫu số thay đổi nên không thể chỉ so tỷ lệ mà bỏ số tuyệt đối |

Ví dụ, chuyển 50 tài khoản cũ sang JIT nhưng tạo thêm 50 tài khoản quản trị thường trực mới có thể cho kết quả tốt trên nhóm cũ và không cải thiện toàn hệ thống. Hai góc nhìn giúp phát hiện tình huống này.

### 4.2. Cửa sổ thời gian phải tương đương

Nếu đo thời gian phơi lộ, so sánh hai cửa sổ cùng độ dài hoặc chuẩn hóa theo thời lượng. Nên chọn các giai đoạn có tính chất vận hành tương đương và ghi nhận yếu tố như đợt triển khai lớn, sự cố hoặc kỳ nghỉ.

Với cửa sổ có độ dài khác nhau, có thể dùng mức phơi lộ trung bình:

```text
Mức quyền hiệu lực trung bình = tổng quyền-phút / số phút của cửa sổ
```

Không dùng số lần kích hoạt giảm trong một tuần ít việc để kết luận chính sách đã thu hẹp quyền. Số lần kích hoạt và lượng công việc là ngữ cảnh bổ sung.

## 5. Bộ chỉ số cốt lõi

### 5.1. Số danh tính còn standing privilege

Gọi `N0` là số danh tính có ít nhất một quyền đặc biệt thường trực ở baseline, và `N1` là số tương ứng sau thay đổi trên phạm vi so sánh đã thống nhất.

```text
Mức giảm tuyệt đối = N0 - N1
Tỷ lệ giảm = (N0 - N1) / N0 × 100%
```

Nếu `N0 = 0`, tỷ lệ giảm không xác định; báo `N/A`, cùng số tuyệt đối. Nếu quyền tăng, tỷ lệ giảm có thể âm và phải giữ dấu âm.

Chỉ số này dễ giải thích nhưng không thể hiện độ rộng của quyền. Một tài khoản từ quản trị toàn cụm xuống chỉ được nạp lại một dịch vụ vẫn có thể còn một quyền đặc biệt thường trực; số danh tính có quyền không thay đổi dù JEA đã giảm phạm vi đáng kể.

Nên tách ít nhất người dùng, workload/tài khoản dịch vụ, tài khoản dùng chung và tài khoản khẩn cấp. Với nhóm cố định, có thể đo thêm tỷ lệ **loại bỏ hoàn toàn** quyền thường trực: số danh tính baseline đã xác nhận không còn bất kỳ đường thường trực nào, chia cho tổng số danh tính baseline có quyền.

### 5.2. Số quyền đặc biệt hiệu lực thường trực

Gọi `G0` và `G1` là số bộ ba chuẩn hóa còn thường trực trước và sau thay đổi.

```text
Tỷ lệ giảm phạm vi quyền thường trực = (G0 - G1) / G0 × 100%
```

Chỉ số này phản ánh cả chuyển quyền sang JIT và thu hẹp quyền bằng JEA. Nhưng số lượng bộ ba không thể tự hiện giá trị rủi ro: một quyền đọc dữ liệu nhạy cảm và một quyền tạo quản trị viên không nhất thiết có cùng mức tác động.

Định nghĩa bộ ba phải nhất quán giữa các lần đo. Đổi cách tách một khả năng thành nhiều khả năng nhỏ sẽ làm thay đổi số đếm dù quyền thực tế không đổi.

### 5.3. Thời gian phơi lộ đặc quyền

Để đo thời gian, với mỗi bộ ba chuẩn hóa `g`, tìm tập khoảng thời gian mà quyền thực sự có hiệu lực trong cửa sổ `W`.

```text
E(g) = độ dài hợp của các khoảng quyền hiệu lực của g, sau khi cắt theo W
E_total = tổng E(g) trên các bộ ba
E_standing = tổng thời gian thuộc các đường quyền thường trực
```

Đơn vị có thể là **quyền-phút**, trong đó một quyền là một bộ ba đã chuẩn hóa. `E_total` phải hợp nhất khoảng thời gian trên mọi đường cấp quyền cho cùng bộ ba trước khi cộng, tránh đếm trùng.

Nếu một đường thường trực đã cấp quyền cả tuần, một lần JIT chồng lên cùng bộ ba không tạo thêm thời gian phơi lộ cho bộ ba đó. Khi tách phần chỉ có quyền tạm thời, cần lấy phần thời gian JIT nằm ngoài các khoảng đã được quyền thường trực bao phủ.

```text
Tỷ lệ giảm phơi lộ = (E_total_baseline - E_total_after)
                    / E_total_baseline × 100%
```

Đo tổng phơi lộ giúp phát hiện trường hợp standing privilege đã giảm trên cấu hình nhưng phiên hoặc token tạm thời gần như hoạt động liên tục.

### 5.4. Mức phơi lộ có trọng số

Khi cần ưu tiên rủi ro, có thể gán trọng số cố định `w(g)` theo tác động của khả năng và độ nhạy cảm của tài nguyên:

```text
E_weighted = tổng [w(g) × E(g)]
```

Đây là chỉ số ưu tiên theo mô hình đã chọn, không phải xác suất xảy ra sự cố hoặc giá trị thiệt hại. Phải công bố thang trọng số, cơ sở chọn, phiên bản và cách xử lý quyền mới. Nếu đổi trọng số giữa hai kỳ, cần tính lại baseline hoặc trình bày rõ ảnh hưởng của thay đổi phương pháp.

### 5.5. Chỉ số bao phủ và chất lượng thu hồi

| Chỉ số | Cách hiểu |
| --- | --- |
| Bao phủ kiểm kê | Tài sản có dữ liệu quyền đủ mới / tài sản thuộc phạm vi đã biết |
| Bao phủ đường truy cập | Những đường truy cập đặc quyền đã đánh giá so với danh sách kiểm kê; kèm phần chưa xác định |
| Tỷ lệ kích hoạt được đóng vòng | Lần kích hoạt có bằng chứng bắt đầu và kết thúc hiệu lực / lần kích hoạt thuộc diện cần xác minh |
| Độ trễ thu hồi | Thời gian từ mốc phải thu hồi đến lúc quyền thực tế không còn được chấp nhận |
| Quyền tồn dư | Quyền còn dùng được sau thời điểm phải hết hạn hoặc bị thu hồi |
| Quyền mới phát sinh | Quyền thường trực được tạo thêm trong kỳ, tách khỏi quyền đã loại bỏ |

Mẫu số kiểm kê chỉ phản ánh những gì tổ chức đã biết. Một tỷ lệ bao phủ cao trên danh mục thiếu tài sản vẫn có thể bỏ sót vùng rủi ro. Cần đối chiếu các nguồn phát hiện tài sản và ghi rõ giới hạn này.

Với độ trễ thu hồi, nên báo trung vị, phân vị cao và giá trị lớn nhất, đồng thời tách các trường hợp chưa xác nhận. Không loại các lần thu hồi thất bại khỏi mẫu rồi kết luận thời gian thu hồi tốt.

## 6. Ví dụ tính toán xuyên suốt

Các con số dưới đây là giả định phục vụ học tập. Phạm vi được giữ cố định giữa hai cửa sổ bảy ngày, mỗi cửa sổ có:

```text
T = 7 × 24 × 60 = 10.080 phút
```

### 6.1. Baseline

Có 20 danh tính người dùng và 10 danh tính dịch vụ. Mỗi danh tính giữ thường trực một bộ quyền gồm **10 khả năng đặc biệt chuẩn hóa trên cùng một phạm vi tài nguyên đã xác định**.

Không có quyền trùng lặp giữa các đường cấp, không có khoảng mất dữ liệu, và toàn bộ quyền có hiệu lực suốt cửa sổ.

```text
Danh tính còn quyền thường trực: 20 + 10 = 30
Số quyền thường trực chuẩn hóa: 30 × 10 = 300
Phơi lộ baseline: 300 × 10.080 = 3.024.000 quyền-phút
```

### 6.2. Sau triển khai JIT và JEA

- Trong 20 người dùng, 3 người còn bộ 10 quyền thường trực theo ngoại lệ được ghi nhận.
- 17 người còn lại chỉ eligible; mỗi người kích hoạt bộ 10 quyền hai lần trong tuần, mỗi lần có hiệu lực thực tế 30 phút, không chồng lấn trên cùng người.
- Cả 10 danh tính dịch vụ vẫn có quyền đặc biệt thường trực.
- Trong nhóm dịch vụ, 4 danh tính vẫn có 10 quyền; 6 danh tính được JEA thu hẹp từ 10 xuống còn 2 quyền đặc biệt mỗi danh tính.
- Không tồn tại đường truy cập thường trực khác, và việc hết hạn JIT đã được xác minh ở điểm thực thi.

### 6.3. Số danh tính có standing privilege

```text
Sau thay đổi: 3 người + 10 dịch vụ = 13 danh tính
Giảm tuyệt đối: 30 - 13 = 17 danh tính
Tỷ lệ giảm: 17 / 30 × 100% ≈ 56,67%
```

Riêng nhóm người dùng, tỷ lệ giảm là `(20 - 3) / 20 = 85%`. Riêng nhóm dịch vụ, số danh tính có standing privilege giảm `0%`, vì cả 10 vẫn có ít nhất một quyền đặc biệt thường trực.

Không thể lấy kết quả 85% của nhóm người dùng để đại diện cho toàn bộ 30 danh tính.

### 6.4. Số quyền thường trực chuẩn hóa

```text
Người dùng thường trực: 3 × 10 = 30 quyền
Dịch vụ giữ bộ quyền cũ: 4 × 10 = 40 quyền
Dịch vụ được thu hẹp: 6 × 2 = 12 quyền
Tổng sau thay đổi: 30 + 40 + 12 = 82 quyền

Tỷ lệ giảm: (300 - 82) / 300 × 100% ≈ 72,67%
```

JEA của sáu danh tính dịch vụ đóng góp vào mức giảm phạm vi quyền dù không làm giảm số danh tính còn quyền thường trực. Trên riêng nhóm dịch vụ, số quyền giảm từ 100 xuống 52, tương đương 48%.

### 6.5. Tổng thời gian phơi lộ

```text
Phơi lộ từ quyền thường trực:
  82 × 10.080 = 826.560 quyền-phút

Thời gian kích hoạt JIT theo danh tính:
  17 × 2 × 30 = 1.020 danh-tính-phút

Phơi lộ từ JIT:
  1.020 × 10 = 10.200 quyền-phút

Tổng sau thay đổi:
  826.560 + 10.200 = 836.760 quyền-phút

Tỷ lệ giảm tổng phơi lộ:
  (3.024.000 - 836.760) / 3.024.000 × 100% ≈ 72,33%
```

Trong ví dụ, quyền JIT không chồng lên quyền thường trực của cùng bộ ba nên có thể cộng trực tiếp. Trong dữ liệu thật, cần hợp nhất khoảng thời gian trước khi cộng.

### 6.6. Cách diễn giải báo cáo

| Chỉ số | Baseline | Sau thay đổi | Mức giảm |
| --- | --- | --- | --- |
| Danh tính có quyền thường trực | 30 | 13 | 56,67% |
| Quyền thường trực chuẩn hóa | 300 | 82 | 72,67% |
| Tổng phơi lộ trong bảy ngày | 3.024.000 quyền-phút | 836.760 quyền-phút | 72,33% |
| Danh tính dịch vụ có quyền thường trực | 10 | 10 | 0% |

Kết luận phù hợp là chương trình đã giảm đáng kể phạm vi và thời gian tồn tại quyền trong nhóm được đo, nhưng vẫn còn 13 danh tính có quyền thường trực. Sáu tài khoản dịch vụ đã được thu hẹp quyền; chúng chưa được chuyển thành quyền tạm thời. Mười bảy người dùng vẫn có khả năng kích hoạt quyền eligible, cần tiếp tục giám sát điều kiện kích hoạt và việc thu hồi.

Mức giảm 72,33% phơi lộ không có nghĩa rủi ro sự cố giảm đúng 72,33%. Khả năng bị khai thác còn phụ thuộc danh tính, thiết bị, credential, kiểm soát kích hoạt và tác động của từng quyền.

## 7. Từ dữ liệu nguồn đến bằng chứng đo lường

### 7.1. Những nguồn cần liên kết

| Nguồn | Thông tin chính | Giới hạn cần đối chiếu |
| --- | --- | --- |
| IAM hoặc thư mục danh tính | Principal, nhóm, vai trò, eligible và lịch sử gán quyền | Có thể chưa phản ánh quyền cục bộ hoặc thời gian hệ thống đích áp dụng |
| Hệ thống đích | Quyền cục bộ, chính sách tài nguyên, phiên và kết quả truy cập | Cần ánh xạ đúng principal và tài sản |
| PAM/JIT | Yêu cầu, phê duyệt, kích hoạt, phiên, yêu cầu thu hồi | Thông báo kết thúc chưa tự chứng minh quyền thực tế đã mất |
| Vault hoặc nguồn credential | Cấp phát, luân chuyển, thu hồi credential | Một credential hết hạn không chứng minh các credential khác đã hết quyền |
| Danh mục tài sản | Chủ sở hữu, môi trường, mức nhạy cảm và trạng thái tài sản | Cần kiểm tra độ đầy đủ và độ mới |
| Kho kiểm toán | Sự kiện có thời gian, mã tương quan và dấu vết xử lý | Cần phát hiện khoảng trống và bảo vệ khỏi sửa/xóa trái phép |

Đối với vault, cần phân biệt người có quyền yêu cầu một phiên bị kiểm soát với người có thể lấy credential quản trị để sử dụng tùy ý. Hai đường truy cập có mức kiểm soát và cách đánh giá standing privilege khác nhau.

### 7.2. Mẫu bản ghi khoảng hiệu lực

Ví dụ JSON sau minh họa mô hình dữ liệu tự định nghĩa, không phải định dạng bắt buộc của một sản phẩm PAM:

```json
{
  "subject_id": "user:ops-17",
  "principal_id": "principal:ops-17-admin",
  "resource_id": "cluster:prod-a",
  "capability_id": "service.reload",
  "grant_type": "jit_active",
  "grant_path_id": "path:activation-5021",
  "activation_id": "ACT-5021",
  "effective_from": "2026-11-03T02:00:00Z",
  "effective_until": "2026-11-03T02:30:00Z",
  "revocation_confirmed_at": "2026-11-03T02:30:00Z",
  "evidence_ref": "audit:access-check-7102",
  "measurement_rule_version": "pam-metrics-v1"
}
```

`effective_until` phải phản ánh mốc kết thúc hiệu lực theo bằng chứng được chấp nhận, không đơn thuần sao chép thời hạn đã yêu cầu. Nếu không xác nhận được thu hồi, cần lưu trạng thái chưa xác định hoặc khoảng quan sát tiếp theo, thay vì điền một thời điểm kết thúc giả định.

Một lần kiểm tra chỉ chứng minh điều kiện được kiểm tra tại điểm và thời điểm đó. Nếu hệ thống có nhiều điểm thực thi hoặc nhiều loại phiên, phương pháp xác nhận phải nói rõ những gì đã được kiểm tra và phần chưa bao phủ.

### 7.3. Chuẩn hóa thời gian và lịch sử

Dùng một chuẩn thời gian nhất quán, chẳng hạn UTC, và cửa sổ nửa mở `[bắt đầu, kết thúc)` để tránh tính trùng ở ranh giới hai kỳ. Phân biệt thời điểm sự kiện xảy ra với thời điểm dữ liệu được thu thập.

Cần có ảnh chụp trạng thái tại đầu kỳ hoặc lịch sử đủ để tái dựng các quyền đã tồn tại trước cửa sổ. Chỉ đọc sự kiện “cấp mới” trong tuần sẽ bỏ sót quyền thường trực đã được cấp từ nhiều tháng trước.

Nếu chỉ chụp trạng thái hằng ngày, có thể bỏ lỡ kích hoạt ngắn giữa hai lần chụp. Báo cáo phải nêu độ phân giải dữ liệu và giới hạn của ước lượng thời gian; không trình bày số phút chính xác như thể đã quan sát liên tục.

## 8. Cách tính khoảng quyền mà không đếm trùng

Đoạn giả mã sau mô tả cách tính, không phải chương trình để chạy trực tiếp:

```text
for each normalized_key = (subject, resource, capability, relevant_conditions):
    all_intervals = []
    standing_intervals = []

    for each effective_grant_path of normalized_key:
        interval = intersect(grant_path.effective_interval, measurement_window)
        if interval is valid and nonempty:
            all_intervals.add(interval)
            if grant_path.is_standing:
                standing_intervals.add(interval)

    merged_all = union_of_overlapping_or_adjacent(all_intervals)
    merged_standing = union_of_overlapping_or_adjacent(standing_intervals)

    exposure_total += duration(merged_all)
    exposure_standing += duration(merged_standing)
    exposure_temporary_only += duration(merged_all minus merged_standing)
```

Chỉ gộp các quyền có cùng ngữ nghĩa và điều kiện hiệu lực tương đương. Một quyền chỉ có hiệu lực trong một ngữ cảnh hạn chế không nên bị gộp mù quáng với quyền không có điều kiện rồi mất thông tin giới hạn.

Các bản ghi chưa xác định thời điểm kết thúc phải đi theo một quy tắc riêng. Có thể báo phần phơi lộ đã xác nhận cùng phần chưa xác định; hoặc tính thêm một kịch bản bảo thủ coi quyền còn hiệu lực đến cuối kỳ. Phải gắn nhãn rõ đó là giả định, không trộn vào số đã xác nhận mà không giải thích.

Không đếm mọi phút trong một phiên đăng nhập như quyền đặc biệt nếu quyền chưa được kích hoạt; cũng không dùng thời lượng video phiên làm đại diện duy nhất cho khoảng quyền có hiệu lực trên đích.

## 9. Xác minh thu hồi và phát hiện standing privilege trá hình

### 9.1. Quyền hết hạn trên PAM nhưng còn hiệu lực ở đích

Các nguyên nhân có thể gồm:

- Phiên hiện tại vẫn dùng token đã phát hành với quyền cũ.
- Thay đổi thành viên nhóm hoặc chính sách chưa đến mọi điểm thực thi.
- Một credential khác, khóa dự phòng hoặc tài khoản cục bộ vẫn còn hoạt động.
- Kích hoạt tạo ra quyền hoặc credential thứ cấp chưa được dọn dẹp.
- Tiến trình hoặc kết nối dài hạn tiếp tục có khả năng thao tác đặc quyền.

Vì vậy nên lưu cả mốc hết hạn theo chính sách và mốc xác nhận mất quyền. Với một khoảng quyền đã đo được, thời gian tồn dư là phần sau mốc phải kết thúc mà quyền vẫn có hiệu lực. Nếu mất dữ liệu ngay sau mốc hết hạn, đó là thiếu bằng chứng, chưa đủ để kết luận đã thu hồi thành công.

### 9.2. Kích hoạt gần như liên tục

Một danh tính được chuyển sang eligible nhưng liên tục tái kích hoạt quyền có thể vẫn có phơi lộ cao. Theo dõi:

```text
Tỷ lệ thời gian có quyền của danh tính
  = hợp thời gian có quyền trong cửa sổ / độ dài cửa sổ
```

Khi phân tích một quyền cụ thể, dùng khoảng hiệu lực của quyền đó; khi phân tích danh tính, hợp các khoảng có ít nhất một quyền đặc biệt và không cộng trùng các quyền đang đồng thời hoạt động.

Cần xem thêm tổng thời gian, độ dài lần kích hoạt dài nhất, số lần gia hạn và khoảng trống giữa các lần kích hoạt. Ngưỡng cảnh báo tùy nhiệm vụ và mức nhạy cảm của hệ thống; không có một ngưỡng phần trăm phù hợp cho mọi môi trường.

### 9.3. Quyền mở rộng gián tiếp

Một tài khoản chỉ còn “sửa cấu hình” có thể vẫn mở được đường chạy mã đặc quyền nếu dịch vụ nạp cấu hình theo cách đó. Một người không còn vai trò quản trị trực tiếp nhưng có quyền thêm mình vào nhóm quản trị cũng còn đường nâng quyền quan trọng.

Nếu chưa mô hình hóa được đầy đủ các đường này, báo riêng các khả năng thay đổi chính sách, cấp quyền và tạo credential. Không khẳng định đã loại bỏ quyền đặc biệt chỉ dựa trên việc tên vai trò quản trị biến mất.

## 10. Dashboard nên cho thấy gì?

Một dashboard phục vụ vận hành và kiểm toán nên có các nhóm thông tin song song:

| Nhóm thông tin | Nội dung |
| --- | --- |
| Phạm vi | Tập tài sản, nhóm danh tính, kỳ đo và phiên bản quy tắc |
| Kết quả | Số danh tính thường trực, số quyền thường trực, tổng quyền-phút và thay đổi so với baseline |
| Phần còn lại | Quyền thường trực còn tồn tại theo hệ thống, chủ sở hữu và lý do |
| Eligible và kích hoạt | Phạm vi eligible, điều kiện kích hoạt, thời lượng và tần suất thực tế |
| Thu hồi | Độ trễ, quyền tồn dư và trường hợp chưa xác nhận |
| Chất lượng dữ liệu | Độ mới, độ bao phủ, sự kiện đến muộn và khoảng trống |
| Vận hành | Thời gian chờ cấp quyền, yêu cầu thất bại và tác động tới công việc |

Nên tách theo người dùng và danh tính dịch vụ, production và các môi trường khác, mức nhạy cảm tài nguyên, chủ sở hữu nghiệp vụ và loại ngoại lệ. Một con số tổng có thể che khuất việc giảm nhiều quyền ít tác động nhưng giữ nguyên các quyền mạnh nhất.

Trên cùng biểu đồ, giữ số tuyệt đối cạnh tỷ lệ phần trăm. Đường xu hướng giúp thấy quyền thường trực có tăng trở lại sau giai đoạn chuyển đổi hay không. Với dữ liệu thiếu, cần hiển thị trạng thái chưa xác định thay vì một cột bằng không.

Không đặt mục tiêu giảm quyền mà bỏ qua khả năng hoàn thành công việc. Theo dõi thời gian chờ kích hoạt, tỷ lệ thao tác hợp lệ bị chặn và các lần phải dùng quyền khẩn cấp. Những chỉ số này giúp phát hiện thiết kế JIT/JEA thiếu tác vụ cần thiết, trước khi người vận hành tạo đường đi vòng.

## 11. Những cách đo dễ tạo kết luận sai

| Cách báo cáo | Vấn đề | Cách sửa |
| --- | --- | --- |
| “100% tài khoản đã vào vault nên không còn standing privilege” | Credential được quản lý nhưng quyền có thể vẫn thường trực | Đo quyền thực thi và mọi đường sử dụng credential |
| Chỉ đếm số gán quyền đã xóa | Bỏ sót quyền qua nhóm hoặc vai trò khác | Tính quyền hiệu lực và giữ dấu vết các đường cấp |
| Chỉ đo người dùng | Bỏ qua tài khoản dịch vụ và workload | Tách các quần thể và báo phần chưa được đo |
| Lấy trạng thái hiện tại để đại diện cả tháng | Không thấy quyền tồn tại giữa các lần chụp | Dùng lịch sử và khoảng hiệu lực, hoặc ghi rõ giới hạn ước lượng |
| Coi thời hạn yêu cầu là thời điểm mất quyền | Bỏ sót token, phiên hoặc thu hồi thất bại | Đối chiếu tại điểm thực thi |
| Loại ngoại lệ và break-glass khỏi mẫu số | Che giấu phần quyền thường trực còn lại | Giữ trong phạm vi và gắn nhãn riêng |
| Đổi cách phân loại quyền giữa hai kỳ | Số giảm có thể do phương pháp | Cố định quy tắc hoặc tính lại baseline |
| Bỏ các hệ thống chưa gửi dữ liệu | Thiếu dữ liệu làm chỉ số trông tốt hơn | Báo bao phủ, phần chưa xác định và tác động lên kết luận |
| Chỉ công bố tỷ lệ giảm | Giảm từ 2 xuống 1 và từ 2.000 xuống 1.000 trông giống nhau | Kèm số tuyệt đối, phạm vi và độ nhạy cảm |
| Gọi phần trăm giảm phơi lộ là phần trăm giảm rủi ro | Hai đại lượng không tương đương | Giải thích đơn vị và giới hạn của chỉ số |

## 12. Ngoại lệ, break-glass và tài khoản dịch vụ

Một số quyền thường trực có thể vẫn cần tồn tại do giới hạn kỹ thuật hoặc yêu cầu khẩn cấp. Chúng cần được kiểm kê với chủ sở hữu, lý do, phạm vi, kiểm soát bù, ngày xem xét lại và kế hoạch xử lý.

Nếu tài khoản break-glass giữ quyền quản trị thường trực, quyền đó vẫn phải xuất hiện trong báo cáo standing privilege. Có thể phân tích riêng do khác mục đích sử dụng, nhưng không loại khỏi tổng rồi tuyên bố toàn hệ thống đã hết quyền thường trực.

Với tài khoản dịch vụ, cần phân biệt ba loại cải thiện:

1. **Quản lý credential tốt hơn:** vault, luân chuyển, giảm lộ lọt; chưa nhất thiết giảm quyền.
2. **Thu hẹp quyền thường trực:** JEA giảm tài nguyên hoặc khả năng được phép; có thể giảm phạm vi nhưng không giảm số danh tính còn quyền.
3. **Loại bỏ hoặc giới hạn thời gian quyền:** workload chỉ nhận quyền cần thiết cho tác vụ và mất quyền hiệu lực sau tác vụ; cần bằng chứng thực thi và thu hồi.

Không bắt buộc mọi workload phải dùng cùng quy trình phê duyệt tương tác như người dùng. Cơ chế cấp quyền có thể dựa trên danh tính workload và ngữ cảnh pipeline tin cậy. Điều cần đo vẫn là quyền nào có thể được sử dụng, trong thời gian nào và theo điều kiện nào.

## 13. Bài thực hành lập kế hoạch đo

Bạn phụ trách chuyển một nhóm vận hành sang JIT/JEA. Hãy lập một bản thiết kế đo trước khi chuyển đổi.

### Bước 1: Chốt phạm vi và cách hiểu quyền

Liệt kê nhóm danh tính, tài nguyên, đường truy cập và các khả năng đặc biệt. Chọn mã định danh ổn định để đổi tên tài khoản hoặc tài sản không làm mất lịch sử. Xác định ai xác nhận mỗi tài khoản dịch vụ và ngoại lệ.

### Bước 2: Lập baseline có bằng chứng

Chọn cửa sổ đo, nguồn trạng thái đầu kỳ và lịch sử thay đổi. Ghi riêng quyền thường trực, eligible, quyền tạm thời, tài khoản dùng chung và phần chưa xác định. Đối chiếu ít nhất các đường cấp quyền quan trọng trên nguồn quản lý lẫn hệ thống đích.

### Bước 3: Định nghĩa bộ chỉ số và mẫu số

Chọn số danh tính còn quyền thường trực, số quyền chuẩn hóa và quyền-phút làm ba góc nhìn chính. Bổ sung chỉ số bao phủ, thu hồi và vận hành. Với mỗi chỉ số, ghi công thức, đơn vị, nguồn dữ liệu và cách xử lý dữ liệu thiếu.

### Bước 4: Chọn cách xác nhận kết thúc quyền

Mô tả bằng chứng đủ để kết thúc một khoảng hiệu lực, như trạng thái thu hồi tại hệ thống đích và kiểm tra truy cập phù hợp trong môi trường được phép. Ghi rõ giới hạn của từng loại bằng chứng, đặc biệt với phiên dài hạn và hệ thống có độ trễ áp dụng chính sách.

### Bước 5: Báo cáo trước và sau trên cùng cơ sở

Đưa số tuyệt đối cạnh tỷ lệ, tách các quần thể và ngoại lệ. Chứng minh giảm quyền hiệu lực thay vì chỉ giảm bản ghi gán quyền. Báo quyền mới phát sinh, phần chưa đo được và các tác động vận hành.

### Hồ sơ bàn giao tối thiểu

- Định nghĩa phạm vi, standing privilege, bộ ba chuẩn hóa và cửa sổ đo.
- Baseline, số liệu sau thay đổi và phiên bản quy tắc tính.
- Dấu vết từ chỉ số tổng tới danh tính, quyền, tài nguyên và bằng chứng nguồn.
- Danh sách quyền thường trực còn lại, ngoại lệ và phần chưa xác định.
- Kết quả theo dõi thu hồi, hoạt động JIT và khả năng hoàn thành công việc.

Dữ liệu quyền và danh tính cũng có thể nhạy cảm. Phân quyền truy cập hồ sơ đo, chỉ công bố mức chi tiết cần thiết và bảo vệ tính toàn vẹn của bằng chứng. Một chỉ số tổng có thể chia sẻ rộng hơn danh sách tài khoản quản trị và đường truy cập cụ thể.

## 14. Tự kiểm tra kiến thức

**1. Đưa 100 tài khoản quản trị vào vault có đồng nghĩa giảm 100 standing privilege không?**  
Không. Vault có thể cải thiện quản lý credential trong khi các tài khoản vẫn giữ nguyên quyền thường trực. Cần đo quyền hiệu lực và những chủ thể còn có thể sử dụng quyền đó.

**2. Tại sao số danh tính còn quyền thường trực không đổi dù JEA thành công?**  
Một danh tính có thể từ nhiều quyền mạnh xuống còn một quyền đặc biệt hẹp. Nó vẫn thuộc nhóm có quyền thường trực, nhưng phạm vi quyền và có thể cả mức tác động đã giảm.

**3. Khi nào một lần JIT được coi là kết thúc trong phép đo phơi lộ?**  
Khi có bằng chứng phù hợp rằng quyền không còn được chấp nhận tại các điểm thực thi thuộc phạm vi đo. Thời hạn yêu cầu hoặc thông báo kết thúc phiên PAM chưa chắc đủ.

**4. Hai đường cấp quyền giống nhau có được cộng hai lần không?**  
Không khi đếm quyền hiệu lực hoặc thời gian phơi lộ của cùng bộ ba. Phải hợp nhất quyền và khoảng thời gian, nhưng vẫn giữ hai đường trong bằng chứng để kiểm tra việc loại bỏ.

**5. Có thể lấy số giảm 72% quyền-phút để kết luận rủi ro giảm 72% không?**  
Không. Quyền-phút đo mức tồn tại quyền theo mô hình chuẩn hóa. Rủi ro còn phụ thuộc khả năng bị khai thác, sức mạnh của quyền, độ nhạy cảm của tài nguyên và các kiểm soát khác.

Đo mức giảm standing privilege cần nối được kiểm kê quyền với khả năng thực thi và thời gian hiệu lực. Bộ số liệu có giá trị khi cho thấy rõ phần đã giảm, phần còn tồn tại, phần chưa xác minh và bằng chứng cho từng kết luận.
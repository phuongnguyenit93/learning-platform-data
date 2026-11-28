# Không dùng account người cho service

Một tác vụ đối soát thanh toán chạy mỗi đêm bằng tài khoản của người đã viết nó. Tài khoản ấy có quyền đọc dữ liệu sản xuất, chỉnh cấu hình và truy cập nhiều hệ thống để phục vụ công việc hằng ngày. Khi người đó đổi vai trò, bật chính sách xác thực mới hoặc nghỉ việc, tác vụ có thể ngừng chạy. Khi tác vụ bị xâm nhập, kẻ tấn công có thể nhận luôn những quyền vốn dành cho con người.

Vấn đề không chỉ nằm ở mật khẩu được lưu trong cấu hình. Danh tính thực thi, vòng đời quyền và trách nhiệm giải trình đang bị gắn sai đối tượng.

Trong quản lý truy cập đặc quyền — Privileged Access Management, viết tắt là PAM — một nguyên tắc thiết kế quan trọng là:

> Workload phải sử dụng danh tính được cấp cho chính workload đó. Người xây dựng, phê duyệt và vận hành workload phải được nhận diện riêng.

Bài học này giải thích cách áp dụng nguyên tắc đó cho service account, tác vụ theo lịch, ứng dụng, pipeline và các thành phần hạ tầng. Mục tiêu là tách quyền chạy máy khỏi quyền của người vận hành, kiểm soát credential và giữ đủ bằng chứng để truy vết hoặc ứng phó sự cố.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân biệt danh tính con người, danh tính workload và danh tính hệ điều hành mà tiến trình chạy dưới đó.
- Nhận ra các cách service sử dụng ngầm quyền của người, kể cả khi không có mật khẩu trong cấu hình.
- Thiết kế danh tính riêng theo workload và môi trường, với chủ sở hữu và quyền được giải thích rõ.
- Lập kế hoạch chuyển đổi một service đang dùng account người mà không bỏ sót phụ thuộc.
- Xây dựng kiểm thử chứng minh workload không còn phụ thuộc vào phiên đăng nhập hoặc vòng đời tài khoản cá nhân.

## 2. Ba câu hỏi phải trả lời riêng

Khi đọc một log truy cập, hãy tách ba câu hỏi:

1. **Ai chịu trách nhiệm về workload?** Đây là trách nhiệm quản trị của đội hoặc người được chỉ định.
2. **Danh tính nào thực hiện yêu cầu?** Đây là principal được hệ thống đích xác thực.
3. **Ai đã thay đổi hoặc kích hoạt hành động?** Đây có thể là người triển khai, người phê duyệt, hệ thống lập lịch hoặc một service khác.

Một người có thể sở hữu quy trình nghiệp vụ mà không phải là principal chạy quy trình đó.

Ví dụ:

| Thành phần | Danh tính phù hợp | Trách nhiệm |
| --- | --- | --- |
| Kỹ sư sửa mã nguồn | Tài khoản cá nhân của kỹ sư | Tạo thay đổi có thể truy vết |
| Người duyệt phát hành | Tài khoản cá nhân của người duyệt | Phê duyệt theo phạm vi được giao |
| Pipeline triển khai | Danh tính riêng của pipeline | Đưa bản phát hành đã duyệt lên môi trường đích |
| Service đang chạy | Danh tính runtime của service | Thực hiện chức năng nghiệp vụ được cấp |
| Nhân sự xử lý sự cố | Tài khoản cá nhân và cơ chế nâng quyền được kiểm soát | Điều tra, can thiệp trong thời gian được phép |

Không có lý do mặc định để pipeline kế thừa toàn bộ quyền của người bấm nút triển khai, hoặc để service kế thừa toàn bộ quyền của pipeline.

Một thiết kế rõ ràng phải trả lời được cả ba câu hỏi mà không phải đoán từ tên một account dùng chung.

## 3. “Account người” không chỉ là username và password

Account người là danh tính được quản trị theo vòng đời của một cá nhân và phục vụ hoạt động tương tác của cá nhân đó. Nó thường liên quan đến đăng nhập, thiết bị cá nhân, nhóm quyền công việc, phiên làm việc và quy trình nhân sự.

Workload có thể phụ thuộc vào account người qua nhiều đường:

- Service đăng nhập hệ thống đích bằng username và password cá nhân.
- Cron job chạy dưới user cá nhân trên máy chủ.
- Tác vụ theo lịch dùng credential đã lưu của một nhân viên.
- Ứng dụng sử dụng API key hoặc personal access token do một người tạo.
- Pipeline dùng refresh token của người từng cấu hình tích hợp.
- Container nhận file credential từ thư mục cá nhân của người triển khai.
- Một SDK tự tìm credential trong phiên đăng nhập của nhà phát triển khi cấu hình workload bị thiếu.
- Script dùng SSH agent hoặc phiên xác thực còn hiệu lực của người đang mở terminal.

Vì vậy, câu hỏi kiểm tra không chỉ là “Có mật khẩu cá nhân trong file không?” mà còn là:

> Nếu toàn bộ phiên đăng nhập, token cá nhân và quyền của người tạo service bị thu hồi, service có tiếp tục hoạt động đúng thiết kế không?

Câu trả lời phải được chứng minh bằng cấu hình và thử nghiệm phù hợp, không chỉ bằng việc đổi tên biến môi trường từ `USER_PASSWORD` thành `SERVICE_PASSWORD`.

## 4. Phân biệt các lớp danh tính

Một tiến trình có thể mang nhiều danh tính ở các ranh giới khác nhau.

### 4.1. Danh tính tại hệ điều hành

Danh tính này quyết định tiến trình được đọc file nào, mở tài nguyên nào và thực hiện thao tác cục bộ nào.

Ví dụ, một tiến trình trên Linux có thể chạy dưới user chuyên dụng `svc_invoice_export`; một dịch vụ trên Windows có thể chạy dưới account dịch vụ phù hợp với mô hình quản trị của tổ chức.

Danh tính cục bộ không tự động trở thành danh tính truy cập database hoặc API.

### 4.2. Danh tính khi truy cập hệ thống đích

Đây là principal mà database, kho dữ liệu, API hoặc nền tảng cloud nhìn thấy.

Một ứng dụng chạy dưới user chuyên dụng vẫn vi phạm nguyên tắc tách danh tính nếu nó kết nối database bằng account cá nhân của quản trị viên.

Ngược lại, ứng dụng dùng danh tính workload để gọi API nhưng chạy với quyền hệ điều hành quá rộng vẫn có rủi ro vượt quá nhu cầu.

Cần kiểm tra từng ranh giới: tiến trình → hệ điều hành, tiến trình → kho bí mật, tiến trình → database, tiến trình → API.

### 4.3. Danh tính của tác nhân khởi tạo

Người dùng có thể bấm nút yêu cầu tạo báo cáo. Service xử lý yêu cầu bằng danh tính của service và ghi nhận người đã yêu cầu báo cáo.

Trong trường hợp này:

- Người dùng là tác nhân nghiệp vụ.
- Service là tác nhân thực thi.
- Quyền của người dùng với báo cáo và quyền của service với hệ thống lưu trữ là hai phạm vi khác nhau.

Không cần cho service đăng nhập bằng password của người dùng để ghi lại người đã yêu cầu thao tác.

### 4.4. Luồng ủy quyền thay mặt người dùng

Một số ứng dụng thực sự cần gọi hệ thống khác trong ngữ cảnh người dùng. Đây là trường hợp ủy quyền được thiết kế rõ ràng, không phải lý do để lưu credential cá nhân và dùng vô thời hạn.

Luồng đó cần xác định được:

- Ứng dụng nào được phép nhận ủy quyền.
- Người dùng nào đã cấp hoặc khởi tạo ủy quyền.
- Phạm vi và thời hạn của quyền.
- Cách thu hồi quyền.
- Cách hệ thống đích và log phân biệt ứng dụng với người được đại diện.

Nếu một tác vụ nền phải tiếp tục chạy kể cả khi người khởi tạo rời tổ chức, cần xem lại liệu đó có thật sự là tác vụ thay mặt người dùng hay là chức năng tổ chức cần danh tính workload riêng.

Không tự chuyển một luồng ủy quyền người dùng thành quyền ứng dụng rộng hơn chỉ để tránh lỗi token. Việc thay đổi mô hình quyền cần được chủ tài nguyên phê duyệt.

## 5. Vì sao account người gây khó cho PAM?

### 5.1. Quyền bị phình theo công việc của cá nhân

Nhân viên có thể được cấp thêm quyền để xử lý một dự án khác. Nếu service dùng cùng account, service có thể nhận thêm quyền không liên quan.

Chiều ngược lại cũng xảy ra: để service hoạt động, đội vận hành giữ quyền đặc biệt trên tài khoản của nhân viên, dù người đó không còn cần quyền ấy.

PAM cần quyền được giải thích bằng nhiệm vụ và tài nguyên cụ thể. Một account vừa phục vụ con người vừa phục vụ máy làm mối quan hệ này khó đánh giá.

### 5.2. Vòng đời nhân sự trở thành vòng đời dịch vụ

Các sự kiện hợp lệ như đổi mật khẩu, nghỉ phép dài hạn, thay thiết bị, đổi vai trò hoặc nghỉ việc có thể gây gián đoạn workload.

Khi đó, đội vận hành dễ đề nghị ngoại lệ: không đổi mật khẩu, bỏ yêu cầu xác thực hoặc giữ account của người đã nghỉ việc. Những ngoại lệ này kéo dài một thiết kế sai và tạo thêm điểm khó kiểm soát.

### 5.3. Log mất khả năng phân biệt nguồn hành động

Nếu cùng account thực hiện truy vấn từ laptop và tác vụ đêm, log chỉ ghi username sẽ không đủ để quy trách nhiệm.

Địa chỉ IP hoặc giờ chạy hỗ trợ điều tra nhưng không thay thế danh tính tách biệt. Proxy, máy dùng chung, failover và truy cập từ xa có thể làm những dấu hiệu đó không còn rõ ràng.

### 5.4. Sự cố workload có thể lan sang quyền của con người

Khi kẻ tấn công lấy được credential mà service sử dụng, phạm vi tác động phụ thuộc vào quyền của credential đó.

Nếu credential thuộc account cá nhân có quyền quản trị rộng, một lỗi trong ứng dụng có thể trở thành điểm vào nhiều hệ thống khác. Tách danh tính giúp tạo ranh giới quyền; mức giảm rủi ro còn phụ thuộc vào phân quyền, bảo vệ credential và kiểm soát sử dụng.

### 5.5. Thu hồi quyền trở thành lựa chọn khó

Nếu account vừa dùng cho service vừa dùng cho người, khóa account để xử lý nghi vấn có thể làm gián đoạn dịch vụ. Giữ account hoạt động lại có thể kéo dài rủi ro.

Danh tính tách biệt cho phép điều tra và thu hồi theo đối tượng chính xác hơn. Tuy nhiên, vẫn phải tính đến token đã phát hành, phiên đang mở và cache quyền; đổi mật khẩu hoặc khóa account không bảo đảm mọi phiên đều chấm dứt tức thì.

## 6. Service account đúng nghĩa cần có gì?

Một tên bắt đầu bằng `svc_` chỉ là quy ước nhận diện. Để trở thành danh tính được quản trị, service account cần có hồ sơ tối thiểu:

| Thuộc tính | Câu hỏi phải trả lời |
| --- | --- |
| Workload sử dụng | Account phục vụ ứng dụng hoặc tác vụ nào? |
| Môi trường | Dùng ở development, test hay production? |
| Chủ sở hữu | Đội nào chịu trách nhiệm và ai là đầu mối dự phòng? |
| Chủ tài nguyên | Ai có quyền phê duyệt truy cập hệ thống đích? |
| Phạm vi quyền | Được làm gì, trên tài nguyên nào, vì lý do nào? |
| Cơ chế xác thực | Dùng danh tính nền tảng, chứng thư, token hay secret? |
| Nơi chạy hợp lệ | Workload được xác thực từ nền tảng hoặc ngữ cảnh nào? |
| Quản lý vòng đời | Ai tạo, rà soát, đổi quyền, xoay credential và thu hồi? |
| Quan sát và bằng chứng | Log nào chứng minh account được sử dụng đúng mục đích? |

Chủ sở hữu phải có thể được bàn giao khi nhân sự thay đổi. Hồ sơ “người sở hữu là anh A” mà không có đội chịu trách nhiệm và quy trình tiếp quản vẫn tạo phụ thuộc cá nhân.

Ví dụ hồ sơ dưới đây là **mẫu tài liệu nội bộ**, không phải cấu hình có thể đưa trực tiếp vào một sản phẩm PAM:

```yaml
identity_record:
  workload: invoice-export
  environment: production
  purpose: "Đọc hóa đơn đủ điều kiện và ghi tệp xuất theo lịch"
  owner_team: finance-platform
  backup_team: platform-operations
  resource_approver: finance-data-owner
  runtime_principal: invoice-export-prod
  authentication: platform-issued-workload-credential
  permissions:
    - resource: invoice_export_view
      action: read
    - resource: invoice-export-output
      action: create-approved-output
  interactive_login: prohibited-by-policy
  review_trigger:
    - ownership-change
    - dependency-change
    - security-incident
    - scheduled-review
```

Cụm `interactive_login: prohibited-by-policy` thể hiện chủ đích quản trị. Muốn biến nó thành kiểm soát thực tế phải cấu hình phù hợp ở hệ điều hành, hệ thống đích và nền tảng danh tính.

Không chỉ đổi tên account cá nhân hiện có thành account dịch vụ. Cách đó có thể giữ nguyên nhóm quyền thừa, credential cũ và lịch sử ủy quyền. Thông thường cần tạo principal riêng, cấp quyền có chủ đích rồi chuyển workload sang principal mới.

## 7. Chọn mức tách danh tính phù hợp

Mục tiêu là cô lập theo ranh giới cần kiểm soát, không phải tạo số account lớn nhất có thể.

### 7.1. Tách người khỏi workload

Đây là ranh giới bắt buộc trong thiết kế bài học này. Người triển khai không cho service mượn credential cá nhân để chạy lâu dài.

### 7.2. Tách môi trường

Danh tính test không nên truy cập production chỉ vì hai môi trường chạy cùng mã nguồn. Môi trường phát triển thường có phạm vi người truy cập và cách vận hành khác production.

Nếu cùng credential được dùng ở nhiều môi trường, một sự cố ở môi trường ít được bảo vệ có thể ảnh hưởng tài nguyên nhạy cảm hơn.

### 7.3. Tách workload có quyền và vòng đời khác nhau

Một tác vụ xuất báo cáo không nên dùng chung account với tác vụ thay đổi cấu trúc dữ liệu.

Có thể tách thêm theo tenant, miền dữ liệu hoặc mức nhạy cảm khi yêu cầu cô lập đòi hỏi. Ngược lại, nhiều bản sao của cùng một workload có thể sử dụng cùng danh tính logic nếu nền tảng hỗ trợ và log vẫn phân biệt được instance thực thi.

### 7.4. Tách triển khai khỏi runtime

Quyền sửa cấu hình hoặc triển khai bản phát hành không đồng nghĩa với quyền mà ứng dụng cần khi chạy.

Runtime thường không cần quản lý tài khoản, sửa chính sách truy cập hoặc thay đổi hạ tầng. Nếu service chỉ cần đọc một view và ghi tệp xuất, credential triển khai không nên được giữ trong container sau khi triển khai.

Việc tách này cũng giúp đội điều tra phân biệt “ai thay đổi chương trình” với “chương trình đã làm gì”.

## 8. Chọn cơ chế xác thực cho workload

Chọn theo khả năng của nền tảng và hệ thống đích, đồng thời giảm lượng credential dài hạn mà ứng dụng phải giữ.

### 8.1. Danh tính workload do nền tảng cung cấp

Trong một số môi trường, nền tảng có thể xác nhận workload và cấp credential có thời hạn hoặc hỗ trợ liên kết danh tính với hệ thống đích.

Thiết kế cần giới hạn rõ workload nào được nhận danh tính nào. Nếu bất kỳ pod, máy hoặc repository nào cũng có thể nhận cùng quyền production, việc loại bỏ password chưa giải quyết đúng ranh giới truy cập.

Cần xem xét điều kiện tin cậy như môi trường, namespace, service account của nền tảng, nguồn triển khai hoặc thuộc tính tương đương mà hệ thống thực tế hỗ trợ.

### 8.2. Account dịch vụ được quản lý

Một số nền tảng hỗ trợ account dịch vụ với cơ chế quản lý credential thay cho việc con người tự phân phối mật khẩu.

Lợi ích chỉ phát huy khi workload và hệ thống đích hỗ trợ đúng cơ chế đó. Vẫn phải kiểm soát máy hoặc workload được phép sử dụng danh tính và quyền mà danh tính nhận được.

### 8.3. Secret hoặc chứng thư khi hệ thống đích yêu cầu

Nếu phải dùng password, API key, private key hoặc chứng thư, credential phải thuộc danh tính workload và được quản lý theo vòng đời riêng.

Cần xác định:

- Nơi lưu bí mật và cơ chế workload lấy bí mật.
- Ai hoặc principal nào được đọc credential.
- Cách ứng dụng nhận phiên bản credential mới.
- Cách thu hồi credential cũ và xử lý phiên còn hiệu lực.
- Cách giám sát việc đọc và sử dụng credential.
- Quy trình xử lý khi nghi ngờ lộ bí mật.

Vault giải quyết việc lưu và phân phối bí mật khi được cấu hình đúng. Vault không tự biến password cá nhân thành credential phù hợp cho service.

Một service lấy password của quản trị viên từ vault vẫn đang dùng danh tính quản trị viên.

### 8.4. Không tự động quay về credential cá nhân

Một lỗi thiết kế thường gặp là chuỗi xác thực có nhánh dự phòng:

```text
Thử credential của workload
    ↓ thất bại
Thử credential trong thư mục người dùng
    ↓ thất bại
Thử phiên đăng nhập tương tác còn lưu
```

Nhánh dự phòng như vậy có thể làm bài kiểm thử chạy thành công trên máy nhà phát triển nhưng thất bại trong production, hoặc làm runtime vô tình dùng quyền của người.

Mã giả dưới đây minh họa nguyên tắc kiểm tra; các hàm là khái niệm, không phải API của một SDK cụ thể:

```text
identity = load_expected_workload_identity(runtime_configuration)

if identity is unavailable:
    emit_error_without_secrets("WORKLOAD_IDENTITY_UNAVAILABLE")
    stop_or_apply_documented_failure_policy()

if identity.principal_id != expected_runtime_principal:
    emit_error_without_secrets("UNEXPECTED_RUNTIME_PRINCIPAL")
    stop_or_apply_documented_failure_policy()

connect_to_target_using(identity)
```

Trong triển khai thực tế, dùng cách kiểm tra principal hoặc cấu hình ràng buộc mà nền tảng hỗ trợ. Kiểm tra ở ứng dụng là lớp bổ sung; hệ thống cấp danh tính và hệ thống đích vẫn phải thực thi ranh giới quyền.

Không ghi access token, password hoặc private key vào log để chứng minh danh tính.

## 9. Ví dụ thiết kế: tác vụ xuất hóa đơn

Giả sử `invoice-export` chạy theo lịch, đọc hóa đơn đủ điều kiện và ghi tệp vào vùng đầu ra. Nó không cần tạo người dùng, sửa quyền, xóa dữ liệu gốc hoặc đọc toàn bộ dữ liệu tài chính.

### 9.1. Hiện trạng

```text
Người vận hành Lan
  ├── đăng nhập bằng lan.personal
  ├── triển khai bằng lan.personal
  └── tác vụ đêm cũng kết nối database bằng lan.personal

Database chỉ nhìn thấy: lan.personal
```

Tác vụ đêm kế thừa các quyền của Lan và phụ thuộc vào vòng đời account của Lan. Log database không phân biệt được truy vấn tương tác với truy vấn từ workload nếu thiếu bằng chứng bổ sung.

### 9.2. Thiết kế đích

```text
Lan ── thay đổi / phê duyệt theo quyền cá nhân ──> Quy trình phát hành
                                                     │
                                                     ▼
                                      Danh tính triển khai riêng
                                                     │
                                                     ▼
                                             invoice-export
                                                     │
                                         Danh tính runtime riêng
                                            ┌────────┴────────┐
                                            ▼                 ▼
                                     View hóa đơn       Vùng đầu ra
```

Bảng quyền minh họa:

| Danh tính | Được phép | Không có trong quyền mặc định |
| --- | --- | --- |
| Người vận hành | Xem trạng thái, yêu cầu chạy lại theo quy trình | Dùng credential runtime để đăng nhập tùy ý |
| Danh tính triển khai | Cập nhật đúng thành phần ứng dụng | Đọc dữ liệu hóa đơn chỉ vì có quyền triển khai |
| Danh tính runtime | Đọc view đã duyệt, tạo tệp ở vùng đầu ra được chỉ định | Sửa schema, quản lý account, cấp quyền |
| Danh tính điều tra tạm thời | Thao tác theo phê duyệt và thời hạn sự cố | Giữ quyền quản trị vô thời hạn |

Tên view và vùng đầu ra phải ánh xạ sang cơ chế phân quyền thực tế của hệ thống đích. Nếu kho lưu trữ cần thao tác bổ sung để hoàn tất ghi tệp, đội triển khai phải xác minh chính xác những thao tác đó rồi cấp quyền tương ứng.

Không chỉ cấp quyền trên tài liệu rồi giả định hệ thống đã giới hạn đúng.

### 9.3. Lưu ý về quyền triển khai

Một principal có thể sửa mã nguồn hoặc cấu hình đang chạy có khả năng làm workload sử dụng quyền runtime theo cách khác.

Vì vậy, tách principal triển khai và runtime là cần thiết nhưng chưa đủ. Cần kiểm soát nguồn bản phát hành, phê duyệt thay đổi, quyền sửa tham số danh tính và khả năng đưa mã tùy ý vào production.

Không được kết luận rằng “pipeline không có quyền đọc database” đồng nghĩa với “người sửa pipeline hoàn toàn không thể tác động đến dữ liệu”.

## 10. Chuyển đổi service đang dùng account người

Chuyển đổi cần thực hiện theo từng phụ thuộc và có cửa sổ quan sát. Không khóa account cá nhân ngay sau khi tạo được một account mới.

### Bước 1: Lập danh sách điểm sử dụng

Với từng workload, ghi nhận:

- Máy, container, service hoặc bộ lập lịch nơi nó chạy.
- Hệ thống đích và hành động thực sự cần.
- Principal hiện tại mà hệ thống đích ghi nhận.
- Nguồn credential và đường nạp credential.
- Lịch chạy, retry, job ít chạy và tiến trình phụ.
- Chủ sở hữu nghiệp vụ, chủ kỹ thuật và chủ tài nguyên.
- Hành vi khi mất xác thực hoặc mất quyền.

Bao gồm cả đường xử lý lỗi, tiến trình dọn dẹp, script hỗ trợ và tác vụ chạy theo tháng hoặc quý. Một phụ thuộc ít hoạt động vẫn có thể gây sự cố sau thời điểm chuyển đổi.

Khi thu thập, ưu tiên metadata về vị trí và loại credential. Không chép password hoặc token vào bảng kiểm kê hay ticket.

### Bước 2: Xác nhận account nguồn có phải account người không

Kiểm tra vòng đời và cách quản trị account, không chỉ tên.

Một account tên `batch-admin` nhưng do một người tự tạo, dùng tương tác hằng ngày và giữ token riêng vẫn có thể mang đầy đủ vấn đề của account cá nhân.

Ngược lại, một danh tính có tên lịch sử khó hiểu có thể đã được quản trị như account workload. Trường hợp đó cần làm rõ hồ sơ và quyền trước khi quyết định tạo mới.

### Bước 3: Thiết kế quyền và danh tính đích

Tách yêu cầu thành hành động cụ thể trên tài nguyên cụ thể.

Ví dụ, “cần quyền database” chưa đủ rõ. Có thể yêu cầu thực là “đọc các cột đã được duyệt từ view xuất hóa đơn ở production”. Chủ tài nguyên phải xác nhận phạm vi này.

Tạo principal workload mới khi cần. Không sao chép toàn bộ nhóm quyền của người sang principal mới và gọi đó là least privilege.

### Bước 4: Thiết lập đường cấp credential

Cấu hình nguồn danh tính hoặc kho bí mật phù hợp; giới hạn workload nào được sử dụng.

Nếu hệ thống dùng secret, tạo credential mới cho principal mới thay vì dùng lại giá trị bí mật của account cá nhân. Nếu có certificate hoặc trust relationship, kiểm tra ràng buộc với đúng workload và môi trường.

Cập nhật cấu hình để đường lấy credential rõ ràng và không còn nhánh dự phòng về phiên của người.

### Bước 5: Kiểm thử chức năng và ranh giới quyền

Thử đường thành công lẫn đường bị từ chối trong môi trường được phép:

- Workload hoàn tất nghiệp vụ tối thiểu.
- Workload không đọc hoặc sửa tài nguyên ngoài phạm vi.
- Workload vẫn chạy khi không có phiên tương tác của người.
- Workload không tiếp tục bằng credential cá nhân khi danh tính đích bị thiếu.
- Log hệ thống đích ghi nhận principal mới.
- Retry không che giấu lỗi xác thực hoặc tạo vòng lặp gây quá tải.

Nếu tác vụ tạo tác động bên ngoài như chuyển tiền, gửi email hoặc phát hành hóa đơn, không chạy song song hai phiên bản chỉ để so sánh. Dùng môi trường thử nghiệm, chế độ đối chiếu không tạo tác động hoặc kế hoạch chuyển đổi có kiểm soát trùng lặp.

### Bước 6: Chuyển đổi có kiểm soát

Chọn cửa sổ phù hợp với lịch chạy và mức ảnh hưởng. Ghi lại:

- Thời điểm chuyển và người chịu trách nhiệm.
- Phiên bản cấu hình trước và sau.
- Principal mới dự kiến xuất hiện ở hệ thống đích.
- Điều kiện xác định thành công.
- Điều kiện và cách quay lui.
- Cách xử lý job đang chạy, connection pool và credential cache.

Quay lui phải phục hồi một trạng thái đã được phê duyệt và ghi nhận. Nếu sự cố bắt nguồn từ credential cũ bị lộ, quay lại dùng credential đó không phải phương án khôi phục phù hợp.

Với job có khóa, hàng đợi hoặc tác dụng phụ, phải kiểm tra cơ chế bảo đảm chỉ một lượt thực thi hợp lệ khi chuyển phiên bản. Đổi principal có thể làm thay đổi quyền trên file khóa, vùng tạm hoặc checkpoint.

### Bước 7: Loại bỏ phụ thuộc cũ

Sau khi có bằng chứng vận hành đủ theo lịch chạy:

- Xóa tham chiếu credential cũ khỏi cấu hình và hệ thống phân phối.
- Thu hồi token, grant hoặc quyền từng được cấp riêng để workload dùng account người.
- Xử lý bản sao secret còn trong cấu hình cũ, bản sao lưu vận hành hoặc nơi lưu khác theo quy trình của tổ chức.
- Kiểm tra truy cập còn lại từ principal cũ.
- Cập nhật hồ sơ sở hữu và hướng dẫn vận hành.

Không xóa hoặc khóa toàn bộ account người nếu account đó vẫn phục vụ công việc hợp lệ khác. Phạm vi thu hồi phải nhắm đúng credential và quyền phụ thuộc của workload; việc xử lý account nhân sự tuân theo quy trình riêng.

Nếu credential cá nhân từng được nhúng trong mã nguồn hoặc phát tán, cần xử lý như khả năng lộ credential: thu hồi hoặc thay credential liên quan và rà soát phạm vi. Chỉ xóa một dòng khỏi phiên bản cấu hình hiện tại không làm các bản sao cũ mất hiệu lực.

## 11. Kiểm chứng “không còn phụ thuộc vào người”

Một service chạy thành công một lần chưa đủ để chứng minh đã tách danh tính.

Bộ kiểm thử dưới đây là các tiêu chí thiết kế. Chọn phạm vi thử nghiệm đã được phê duyệt; không khóa account production của người khác để thử tùy ý.

| Kiểm tra | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- |
| Không có phiên đăng nhập cá nhân trên runtime thử nghiệm | Workload vẫn xác thực bằng danh tính đích | Cấu hình nguồn danh tính và log principal ở hệ thống đích |
| Không cấp credential workload | Tác vụ báo lỗi rõ hoặc áp dụng chính sách lỗi đã duyệt | Log lỗi không chứa secret, không có lần truy cập bằng account người |
| Đổi quyền của người triển khai trong môi trường thử nghiệm | Không tự làm thay đổi quyền runtime đã thiết kế | So sánh principal và kết quả kiểm thử quyền |
| Thử thao tác ngoài phạm vi | Hệ thống đích từ chối | Sự kiện từ chối có principal và tài nguyên |
| Thu hồi quyền workload trong môi trường thử nghiệm | Truy cập bị chặn theo đặc tính hiệu lực của hệ thống | Thời điểm thu hồi, hết hiệu lực token/phiên và kết quả truy cập |
| Chạy lại sau khởi động mới | Không cần người đăng nhập trước | Kết quả chạy từ runtime mới, không có cache credential cá nhân |
| Chuyển người sở hữu theo quy trình | Dịch vụ vẫn vận hành và hồ sơ được bàn giao | Hồ sơ sở hữu cùng bằng chứng vận hành |

Khi đánh giá phép thử thu hồi, ghi rõ có token tự chứa, phiên dài hạn, connection pool hay cache quyền hay không. Phải biết cơ chế nào làm quyền mất hiệu lực và giới hạn thời gian nào được chấp nhận.

Nếu workload dùng ủy quyền thay mặt người dùng, kỳ vọng khác với workload tổ chức độc lập: thu hồi quyền ủy quyền của người dùng có thể phải khiến tác vụ liên quan dừng. Điều cần chứng minh là hành vi đúng mô hình đã thiết kế, không phải mọi tác vụ đều phải sống độc lập với mọi người dùng.

## 12. Log và bằng chứng cần giữ

Log tốt giúp nối chuỗi “ai thay đổi → workload nào chạy → principal nào truy cập → tài nguyên nào bị tác động”.

Ví dụ sự kiện dưới đây là cấu trúc minh họa, không phải schema bắt buộc:

```json
{
  "event_type": "scheduled_export_completed",
  "workload": "invoice-export",
  "environment": "production",
  "runtime_principal_id": "invoice-export-prod",
  "trigger_type": "schedule",
  "execution_id": "export-run-example-01",
  "release_id": "release-example-17",
  "target_resource": "invoice_export_view",
  "result": "success"
}
```

Với hành động do người yêu cầu, có thể ghi thêm định danh người khởi tạo ở trường riêng theo chính sách dữ liệu và cơ chế tin cậy của hệ thống.

Không lấy một chuỗi `requested_by` do client tự gửi rồi coi đó là bằng chứng xác thực. Cần gắn thông tin tác nhân với ngữ cảnh đã được xác thực ở ranh giới nhận yêu cầu.

Ngoài log ứng dụng, giữ bằng chứng từ hệ thống danh tính và hệ thống đích khi có thể. Một ứng dụng bị xâm nhập có thể ghi sai thông tin về chính nó.

Không đưa các giá trị sau vào log, ticket hoặc ảnh chụp bằng chứng:

- Password hoặc private key.
- Access token, refresh token và session cookie.
- Chuỗi kết nối có credential.
- Toàn bộ bản ghi secret từ vault.

Định danh principal, phiên bản credential không bí mật, thời điểm và mã sự kiện thường hữu ích hơn việc thu thập chính giá trị bí mật.

## 13. Các nhầm lẫn thường gặp

### “Đã lưu password trong vault nên account cá nhân dùng cho service cũng được”

Vault cải thiện cách bảo vệ và phân phối password; principal đích vẫn là người đó. Vòng đời, quyền và log vẫn bị trộn.

Cần chuyển sang danh tính workload phù hợp, rồi quản lý credential của danh tính ấy.

### “Tạo một account service toàn quyền để mọi ứng dụng dùng chung”

Đây là thay phụ thuộc một người bằng phụ thuộc một danh tính dùng chung có phạm vi quá rộng.

Khi account bị lộ hoặc bị khóa, nhiều workload cùng bị ảnh hưởng. Khi audit, khó gắn hành động với workload cụ thể. Cần tách theo ranh giới quyền, môi trường và vòng đời thực tế.

### “Account bị cấm đăng nhập tương tác thì đã đủ an toàn”

Cấm đăng nhập tương tác là một kiểm soát, không phải toàn bộ thiết kế. API key hoặc password của account vẫn có thể bị dùng từ nơi khác nếu hệ thống đích và điều kiện xác thực cho phép.

Cần kiểm soát nguồn sử dụng, quyền trên tài nguyên và credential.

### “Service account bắt buộc phải có quyền quản trị”

Service account mô tả đối tượng sử dụng danh tính, không mô tả mức đặc quyền. Nhiều service chỉ cần quyền nghiệp vụ hẹp.

Nếu workload thật sự cần thao tác quản trị, hãy cấp phạm vi nhỏ nhất có thể và xem xét giới hạn thời gian, phê duyệt hoặc thành phần thực thi chuyên trách tùy khả năng hệ thống.

### “Cứ cho service dùng MFA của nhân viên là đúng”

Workload không nên phụ thuộc vào việc một người chấp nhận yêu cầu xác thực lặp lại để chạy tác vụ định kỳ.

Cần chọn cơ chế xác thực dành cho máy. Đối với người quản trị việc tạo và sử dụng danh tính workload, vẫn áp dụng kiểm soát xác thực và nâng quyền phù hợp.

### “Người vận hành cần sửa sự cố nên phải biết password runtime”

Quyền vận hành không mặc nhiên đồng nghĩa với quyền lấy credential ứng dụng.

Ưu tiên thao tác quản trị qua danh tính cá nhân, đường truy cập được kiểm soát và phạm vi được phê duyệt. Nếu có tình huống bắt buộc tiếp cận credential runtime, phải ghi nhận mục đích, người thực hiện, thời hạn và xử lý credential sau sử dụng theo chính sách.

Không dùng account service như tài khoản đăng nhập chung cho đội.

## 14. Tình huống thực hành

Đội tài chính có job `settlement-summary` chạy lúc cuối ngày. Job chạy dưới user cá nhân trên một máy chủ và lấy token API từ thư mục người dùng. Người tạo job sắp chuyển nhóm.

Job thực hiện ba việc:

1. Đọc giao dịch đã chốt.
2. Ghi báo cáo vào vùng lưu trữ của đội tài chính.
3. Gửi thông báo hoàn tất qua một tích hợp.

Token hiện tại thuộc người tạo job và có thêm quyền quản lý cấu hình tích hợp. Một script dọn dẹp theo tuần cũng dùng cùng token.

### Yêu cầu phân tích

- Xác định các ranh giới danh tính đang bị trộn.
- Đề xuất danh tính hệ điều hành và danh tính truy cập từng hệ thống đích.
- Chỉ ra quyền nào không nên chuyển sang runtime mới.
- Lập kế hoạch chuyển đổi có tính đến script chạy theo tuần.
- Xác định bằng chứng chứng minh job không dùng token cá nhân.
- Mô tả cách xử lý nếu hệ thống thông báo chỉ hỗ trợ token gắn với người dùng.

### Hướng giải thích

Trước hết, cần tách người tạo job khỏi principal chạy tiến trình và khỏi principal gọi API. Quyền quản lý cấu hình tích hợp không thuộc chức năng gửi thông báo nên không được sao chép mặc định.

Có thể sử dụng một danh tính runtime cho cùng workload nếu cơ chế xác thực và các ranh giới quyền cho phép; cũng có thể cần nhiều principal đích do mỗi hệ thống có mô hình danh tính riêng. Điều quan trọng là các principal ấy đều được gắn với workload, môi trường và chủ sở hữu rõ ràng.

Script dọn dẹp phải được phân tích riêng về phạm vi xóa và vòng đời. Không mặc định chuyển quyền xóa sang job xuất báo cáo nếu chức năng này có thể tách biệt.

Nếu hệ thống thông báo chỉ hỗ trợ token người dùng, cần xác minh các lựa chọn tích hợp được hệ thống hỗ trợ và làm rõ luồng ủy quyền. Có thể cần thay đổi tích hợp hoặc chấp nhận một ngoại lệ được quản trị trong thời gian chuyển đổi. Không tự tạo một account “người giả” và tuyên bố đã có danh tính workload được hỗ trợ.

Ngoại lệ phải ghi nhận hạn chế kỹ thuật, phạm vi, chủ sở hữu, thời hạn xem xét và kế hoạch xử lý. Nó không xóa rủi ro hay thay thế nhu cầu chuyển sang mô hình phù hợp.

Bằng chứng cần nối được cấu hình đã triển khai, nguồn cấp credential, principal xuất hiện ở hệ thống đích và kết quả chạy qua các chu kỳ liên quan. Không lấy việc job chạy thành công khi người tạo vẫn đang đăng nhập làm kết luận cuối cùng.

## 15. Tiêu chí hoàn thành một lần chuyển đổi

Một lần chuyển đổi đạt yêu cầu khi có thể trả lời rõ các điểm sau:

- Workload có danh tính thực thi phù hợp với từng hệ thống đích và không còn mượn credential cá nhân ngoài luồng ủy quyền đã thiết kế.
- Danh tính và quyền được tách theo môi trường, phạm vi nhiệm vụ và vòng đời cần kiểm soát.
- Chủ sở hữu và người phê duyệt tài nguyên được ghi nhận, có cơ chế bàn giao.
- Runtime không âm thầm sử dụng credential cá nhân làm dự phòng.
- Credential được cấp, lưu, thay thế và thu hồi theo quy trình của danh tính workload.
- Kiểm thử đã bao phủ cả chức năng, từ chối quyền ngoài phạm vi và các phụ thuộc ít chạy.
- Log phân biệt được người thay đổi, tác nhân khởi tạo và principal thực thi.
- Tham chiếu và quyền cũ phục vụ workload đã được xử lý, với bằng chứng đủ để kiểm tra lại.

Tách account người khỏi service tạo nền tảng cho least privilege, quản lý credential, giám sát và ứng phó sự cố. Giá trị của việc tách nằm ở ranh giới danh tính có thể kiểm chứng: con người chịu trách nhiệm bằng danh tính cá nhân, còn workload thực thi bằng quyền được cấp cho đúng nhiệm vụ của nó.

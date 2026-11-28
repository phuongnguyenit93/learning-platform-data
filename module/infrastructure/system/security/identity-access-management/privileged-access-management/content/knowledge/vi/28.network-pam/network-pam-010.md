# Dual approval for firewall change

Một thay đổi firewall có hai dấu phê duyệt trong ticket nhưng người thực hiện lại cài một rule khác. Hoặc rule được duyệt vẫn giữ nguyên tên address group, trong khi thành viên của group đã bị mở rộng trước lúc triển khai. Hồ sơ có đủ chữ “Approved”, nhưng lưu lượng được cho phép không còn đúng nội dung đã được xem xét.

Dual approval for firewall change là cơ chế yêu cầu hai quyết định phê duyệt hợp lệ, độc lập theo chính sách trước khi một thay đổi firewall được thực thi. Trong Privileged Access Management (PAM), mục tiêu không chỉ là thêm một bước xác nhận mà là ngăn một principal tự đề xuất, tự cho phép và tự áp dụng một thay đổi đặc quyền ngoài kiểm soát.

Bài học sử dụng một mô hình cụ thể: hai người phê duyệt khác nhau, đại diện cho hai trách nhiệm đã quy định, được tách khỏi người yêu cầu và người thực thi đối với những thay đổi thuộc diện kiểm soát này. Tổ chức có thể chọn cấu trúc khác theo rủi ro; cần định nghĩa rõ thay vì mặc định mọi mô hình “hai người” đều có cùng ý nghĩa.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt hai phê duyệt với MFA, review kỹ thuật và kiểm soát hai người.
- Xác định thay đổi firewall nào cần được xem xét như một hành động đặc quyền.
- Ràng buộc approval với artifact, cấu hình nền, đối tượng phụ thuộc và thiết bị đích.
- Tách quyền soạn, duyệt, cài đặt và sửa quy trình phê duyệt.
- Thiết kế kiểm tra trước triển khai, xử lý thay đổi đồng thời và thất bại một phần.
- Lưu bằng chứng, kết thúc quyền và kiểm tra vòng đời rule sau khi thay đổi.

## 2. Dual approval có nghĩa gì?

Chính sách cần trả lời ít nhất:

1. Cần bao nhiêu người phê duyệt?
2. Họ phải đại diện cho trách nhiệm nào?
3. Ai không được tính là người phê duyệt hợp lệ?
4. Họ phê duyệt nội dung và đích nào?
5. Phê duyệt có hiệu lực đến khi nào?
6. Thay đổi nào khiến phê duyệt không còn dùng được?
7. Hệ thống nào ngăn thực thi khi chưa đủ điều kiện?

Ví dụ một chính sách có hai vị trí:

| Vị trí phê duyệt | Trách nhiệm |
| --- | --- |
| Chủ sở hữu dịch vụ hoặc dữ liệu | Xác nhận nhu cầu kết nối, dữ liệu và hệ thống liên quan |
| Người phụ trách an ninh mạng hoặc policy | Đánh giá phạm vi mở, ranh giới mạng, kiểm soát và ảnh hưởng |

Hai người không chỉ ký cùng một câu hỏi chung. Mỗi người cần biết mình chịu trách nhiệm đánh giá phần nào và có đủ thông tin cho quyết định đó.

### 2.1. Không đồng nhất với MFA

MFA giúp xác thực mạnh hơn một principal. Một người dùng hai yếu tố không trở thành hai người phê duyệt độc lập.

Ngược lại, hai người phê duyệt bằng các tài khoản yếu hoặc chia sẻ credential vẫn có rủi ro giả mạo. Cần cả danh tính đáng tin và tính độc lập theo chính sách.

### 2.2. Không đồng nhất với một người viết, một người duyệt

Một quy trình có người đề xuất và một người duyệt có thể là kiểm soát hai người. Nó chưa chắc đáp ứng chính sách yêu cầu hai người phê duyệt tách khỏi người đề xuất.

Tài liệu và hệ thống cần dùng thuật ngữ nhất quán. Không báo cáo “dual approval” chỉ từ tổng số người xuất hiện trong ticket.

### 2.3. Hai tài khoản chưa chắc là hai người

Cần liên kết tài khoản tới định danh người đáng tin. Một người dùng hai tài khoản hoặc cùng một tài khoản dùng chung không đáp ứng mô hình hai người độc lập của bài này.

Nếu một người thuộc cả hai nhóm phê duyệt, chính sách vẫn phải ngăn cùng người đó lấp cả hai vị trí.

## 3. Phạm vi thay đổi firewall cần xem xét

Một thay đổi không chỉ là thêm một dòng allow.

| Loại thay đổi | Tác động cần xem xét |
| --- | --- |
| Thêm, sửa hoặc xóa rule | Mở hoặc chặn luồng, thay ranh giới truy cập |
| Đổi thứ tự rule | Thay kết quả xử lý theo ngữ nghĩa của engine |
| Sửa address hoặc service object | Ảnh hưởng tất cả rule tham chiếu |
| Sửa group lồng nhau | Mở rộng hoặc thu hẹp phạm vi gián tiếp |
| Thay NAT | Thay ánh xạ và đối tượng thực tế mà policy áp dụng |
| Đổi zone, interface hoặc route liên quan | Thay đường đi, miền tin cậy hoặc phạm vi match |
| Tắt logging hoặc profile kiểm soát | Giảm khả năng quan sát hoặc kiểm tra lưu lượng |
| Sửa schedule hoặc thời hạn rule | Kéo dài hoặc đổi thời điểm có hiệu lực |
| Đổi policy chung hoặc template | Tác động nhiều firewall và miền quản trị |
| Thay quyền người quản trị | Mở đường cho các thay đổi policy tiếp theo |

Không chỉ xét số dòng diff. Sửa một object dùng chung có thể tác động nhiều rule và thiết bị hơn một thay đổi dài nhưng cục bộ.

### 3.1. Ngữ nghĩa phụ thuộc engine

Thứ tự xử lý policy, NAT, trạng thái kết nối và các lớp kiểm soát khác nhau theo nền tảng.

Người duyệt cần thấy luồng trước và sau khi giải quyết những ngữ nghĩa đó. Không chỉ đọc chuỗi source, destination và port rồi giả định tất cả firewall xử lý giống nhau.

### 3.2. Quy tắc tạm thời vẫn cần owner

Một rule để xử lý sự cố cần chủ sở hữu, mục đích, thời điểm xem xét lại và cơ chế kết thúc.

Ghi “temporary” trong comment không tự làm rule hết hiệu lực. Một rule mở ngắn hạn nhưng không có thành phần dọn sẽ dễ trở thành ngoại lệ lâu dài.

## 4. Tách nhiệm vụ và quyền hiệu lực

Một mô hình tham khảo:

```text
Người yêu cầu / soạn thay đổi
               |
               v
      Artifact được chốt phiên bản
               |
       +-------+-------+
       |               |
       v               v
  Phê duyệt A     Phê duyệt B
  nhu cầu         rủi ro / policy
       |               |
       +-------+-------+
               |
               v
   Bộ thực thi chỉ nhận nội dung hợp lệ
               |
               v
     Firewall và kết quả thực tế
```

### 4.1. Người soạn

Được tạo đề xuất và chuẩn bị cấu hình trong phạm vi được giao. Không tự sửa bản ghi approval hoặc biến nội dung chưa duyệt thành bản đã duyệt.

Nếu người này có quyền trực tiếp cài policy bằng đường khác, phải quản lý đường đó hoặc ghi rõ giới hạn của cơ chế.

### 4.2. Người phê duyệt

Có quyền đọc thông tin cần thiết và quyết định trong trách nhiệm được giao. Không mặc định cần quyền sửa rule hoặc cài cấu hình.

Hệ thống cần xác minh người duyệt còn đủ thẩm quyền theo chính sách áp dụng, approval chưa bị rút và danh tính không trùng các vai trò bị loại trừ.

### 4.3. Người hoặc workload thực thi

Chỉ nhận khả năng cài nội dung và phạm vi đã được phép. Nếu dùng workload, credential của nó là đặc quyền và phải có chủ sở hữu, phạm vi cùng audit.

Không cho executor nhận một ticket đã duyệt rồi gửi SQL, CLI hoặc payload policy tùy ý bằng credential rộng.

### 4.4. Người quản trị quy trình

Người sửa nhóm approver, điều kiện chấp nhận, template và danh tính executor có khả năng ảnh hưởng chốt kiểm soát.

Quyền này cần được quản trị riêng. Nếu người đề xuất có thể tự thêm mình vào nhóm duyệt hoặc đổi cấu hình để chỉ cần một chữ ký, sự tách nhiệm vụ chưa có tác dụng thực tế.

## 5. Nội dung phải đủ để hai người quyết định

Một gói đề xuất nên giải thích cả mục đích và thay đổi hiệu lực.

| Nhóm | Thông tin cần có |
| --- | --- |
| Nhu cầu | Dịch vụ nào cần kết nối, ai sở hữu, vì sao cần |
| Nguồn | Principal hệ thống, mạng hoặc tập endpoint được phép |
| Đích | Dịch vụ, dữ liệu, địa chỉ hoặc object tương ứng |
| Giao thức | Protocol, port, ứng dụng hoặc cơ chế match |
| Đường đi | Zone, NAT, route và thiết bị có liên quan |
| Thay đổi | Trạng thái trước, trạng thái sau và vị trí rule |
| Kiểm soát | Logging, profile kiểm tra và các ràng buộc |
| Phạm vi | Firewall, context, tenant, policy package và đích push |
| Thời gian | Cửa sổ triển khai và vòng đời rule |
| Kiểm chứng | Luồng phải đi được, luồng phải bị chặn |
| Phục hồi | Nội dung rollback, điều kiện và người quyết định |

### 5.1. Review cả object phụ thuộc

Tên như application-servers hoặc trusted-networks không nói đủ phạm vi.

Cần xem thành viên, group lồng nhau, service object và những policy khác bị ảnh hưởng khi sửa object. Nếu cấu hình có dữ liệu động, xác định đặc tính biến động nào đã nằm trong phạm vi được duyệt.

Không bắt người duyệt ký một bản mô tả hẹp trong khi executor có thể mở rộng group sau đó mà vẫn dùng approval cũ.

### 5.2. Review các luồng bị ảnh hưởng, không chỉ luồng mong muốn

Một yêu cầu mở HTTPS cho một dịch vụ có thể vô tình cho phép cả mạng nguồn hoặc nhiều đích khác.

Cần nêu những kiểm tra phủ định: nguồn không được phép, port khác, đích khác hoặc miền khác vẫn phải bị chặn theo mục tiêu.

Không dùng một phép thử thành công của người yêu cầu làm bằng chứng rằng mọi ranh giới còn nguyên.

### 5.3. Logging và dữ liệu nhạy cảm

Cấu hình và báo cáo có thể lộ sơ đồ mạng, metadata nội bộ hoặc secret tích hợp. Người duyệt cần đủ thông tin nhưng không phải mọi bí mật thô.

Bảo vệ artifact, bản export và kênh thông báo theo phạm vi. Không gửi credential firewall trong ticket để executor dễ thao tác.

## 6. Ràng buộc approval với đúng artifact

Một approval có ích phải trả lời được: người này đã xem và cho phép **phiên bản nào**, trên **đích nào**, trong **điều kiện nào**?

Gói được duyệt có thể bao gồm:

- Nội dung thay đổi được chuẩn hóa.
- Revision cấu hình nền.
- Phiên bản và phạm vi object phụ thuộc.
- Danh sách đích triển khai.
- Kết quả phân tích tác động và kiểm tra.
- Cửa sổ chạy, vòng đời rule và kế hoạch phục hồi.
- Định danh hoặc digest để đối chiếu nội dung.

### 6.1. Ví dụ hồ sơ minh họa

```yaml
change_id: CHG-example-529
change_revision: 3
artifact:
  reference: immutable-policy-artifact-example
  digest: "sha256:<digest-da-tinh>"
baseline_revision: policy-revision-example-84
targets:
  - firewall_id: FW-LAB-A
    context: payments-lab
  - firewall_id: FW-LAB-B
    context: payments-lab
approval_slots:
  - service-owner
  - network-security
deployment_window:
  starts_at: "2026-01-12T14:00:00Z"
  ends_at: "2026-01-12T14:30:00Z"
rule_lifecycle:
  mode: temporary
  expires_at: "2026-01-12T18:00:00Z"
rollback_artifact: rollback-example-revision-3
```

Đây là dữ liệu thiết kế, không phải một manifest triển khai firewall. Các timestamp chỉ minh họa hai loại thời hạn.

### 6.2. Digest không tự chứng minh thẩm quyền

Hash giúp đối chiếu nội dung, nhưng không chứng minh ai duyệt và có được phép duyệt không.

Bản ghi approval phải được bảo vệ, liên kết với principal đáng tin và tham chiếu đúng artifact. Client không được tự gửi approved=true cùng một digest rồi được coi là đã đủ hai quyết định.

Nếu người có quyền sửa artifact cũng có thể sửa toàn bộ bản ghi approval không có dấu vết, cơ chế đối chiếu chưa đủ bảo vệ.

### 6.3. Thay đổi sau phê duyệt

Khi sửa source, destination, service, NAT, object, logging, đích triển khai hoặc phạm vi khác có ý nghĩa, phải xác định approval hiện tại còn hợp lệ không.

Một cách thiết kế là tạo revision mới và yêu cầu lại những phê duyệt bị ảnh hưởng theo chính sách. Không giữ nguyên trạng thái Approved chỉ vì ticket vẫn có cùng mã.

Đối với dữ liệu động như nhóm được cập nhật từ nguồn ngoài, cần ràng buộc và cơ chế theo dõi đã được định nghĩa. Không giả vờ có snapshot cố định nếu policy thực tế cho phép thành viên tiếp tục thay đổi.

## 7. Từ hai nút Approve đến chốt thực thi

### 7.1. Kiểm tra từng quyết định

Với mỗi approval:

- Đúng change revision và artifact.
- Đúng slot trách nhiệm.
- Principal hợp lệ, không phải tài khoản dùng chung.
- Không trùng người yêu cầu hoặc executor theo mô hình của bài.
- Không dùng cùng người cho hai slot.
- Chưa bị rút hoặc hết hạn.
- Đáp ứng các điều kiện bổ sung của policy.

Nếu một approval bị từ chối hoặc rút, quyết định thực thi phải phản ánh trạng thái đó. Không giữ một cờ tổng approved đã được tính từ trước mà không kiểm tra lại.

### 7.2. Không chỉ đếm số bản ghi

Hai dòng approval của cùng người không đáp ứng yêu cầu hai người.

Hai người cùng nhóm cũng chưa chắc đáp ứng hai slot trách nhiệm. Cần ánh xạ người duyệt hợp lệ vào từng slot, với điều kiện mỗi slot được một người khác nhau đảm nhiệm.

Một workflow native có thể cung cấp approval group. Ví dụ, FortiManager mô tả approval matrix với thành viên từ từng nhóm phê duyệt tham gia chấp nhận thay đổi. Cần kiểm tra cấu hình và tính độc lập của những người thực tế, không suy từ tên nhóm. [Workflow approval của FortiManager](https://docs.fortinet.com/document/fortimanager/latest/administration-guide/446472/workflow-approval).

### 7.3. Chặn ở nơi có khả năng cài policy

Nếu UI kiểm tra hai approval nhưng API install không kiểm tra, người có API key có thể bỏ qua quy trình.

Chốt cần nằm trên đường thực thi được quản trị hoặc được nền tảng firewall cưỡng chế. Quản lý cả CLI, API, controller, pipeline và truy cập local khẩn cấp.

Không cần xây mọi chức năng trong một ứng dụng duy nhất, nhưng phải nối được quyết định phê duyệt với khả năng triển khai thực tế.

## 8. Kiểm tra lại ngay trước triển khai

Phê duyệt hợp lệ lúc 13:00 chưa chắc vẫn phù hợp lúc 14:00 nếu cấu hình nền hoặc object đã thay đổi.

### 8.1. Nội dung cần đối chiếu

- Artifact có còn nguyên phiên bản đã duyệt?
- Hai approval còn hợp lệ?
- Cửa sổ chạy đã bắt đầu và chưa kết thúc?
- Principal thực thi có đúng không?
- Target list, context và policy package có đúng không?
- Baseline và phụ thuộc có thay đổi ảnh hưởng quyết định không?
- Có thay đổi đang chờ của người khác bị gộp vào không?
- Có yêu cầu hủy hoặc thu hồi không?

### 8.2. Tránh khoảng trống giữa kiểm tra và thực thi

Một quy trình đọc baseline rồi chờ lâu trước khi push có thể bỏ lỡ thay đổi đồng thời.

Tùy nền tảng, có thể dùng khóa cấu hình, kiểm tra revision có điều kiện, snapshot hoặc điều phối thay đổi để giữ quan hệ giữa nội dung đã kiểm tra và nội dung được cài.

Nếu nền tảng không hỗ trợ bảo đảm đó, cần mô tả giới hạn và quy trình giảm rủi ro, không tuyên bố chỉ một lần đọc trước đã loại bỏ mọi thay đổi cạnh tranh.

### 8.3. Baseline thay đổi không được xử lý bằng push mù

Khi có thay đổi liên quan, dừng để đối chiếu, dựng lại diff và đánh giá lại approval theo chính sách.

Nếu native commit cần gộp thêm thay đổi chưa thuộc gói được duyệt, không tự mở rộng phạm vi chỉ để commit thành công. Tách thay đổi, điều phối hoặc xin phê duyệt cho nội dung mới theo yêu cầu thực tế.

## 9. Tách validation, commit, push và hiệu lực

Nhiều hệ thống quản lý có nhiều giai đoạn. Một trạng thái thành công ở manager chưa chứng minh firewall đã áp dụng đúng rule.

Ví dụ, tài liệu Panorama phân biệt preview, validation, commit ở hệ thống quản lý và push tới thiết bị. Vì vậy, cần kiểm tra đúng scope và kết quả tại đích theo mô hình triển khai. [Quy trình preview, validate và commit](https://docs.paloaltonetworks.com/panorama/administration/administer-panorama/preview-validate-or-commit-configuration-changes).

### 9.1. Validation không thay thế phê duyệt

Validation có thể kiểm tra cú pháp, tham chiếu và những điều kiện nền tảng hỗ trợ. Nó không tự trả lời kết nối đó có được chủ sở hữu dữ liệu cho phép hay rủi ro mở mạng có chấp nhận được không.

Ngược lại, có đủ approval cũng không bảo đảm cấu hình hợp lệ hoặc thiết bị đủ khả năng nhận cấu hình.

Hai lớp kiểm tra có mục đích khác nhau và đều cần phản ánh trong quyết định triển khai.

### 9.2. Quyền commit không mặc định là quyền duyệt

Một principal có khả năng commit hoặc install là chủ thể thực thi đặc quyền. Nó chỉ được sử dụng khả năng đó khi chốt phê duyệt đã cho phép.

Không suy rằng tách nút Edit và Commit là đã có hai người phê duyệt độc lập. Cũng không suy rằng người có quyền commit chỉ cài được thay đổi của chính họ nếu nền tảng cho gộp nhiều thay đổi.

### 9.3. Giữ nguyên scope cài đặt

Scope cần bao gồm policy package, context, device group, template hoặc đơn vị tương ứng.

Kiểm tra những giá trị mặc định của nút install/push. Một lựa chọn mặc định rộng có thể triển khai tới nhiều đích hơn danh sách đã được duyệt.

Nếu cấu hình có kế thừa, cần hiểu những đích chịu ảnh hưởng thực tế. Chốt quyền không chỉ kiểm tra tên group trong ticket mà phải đối chiếu phạm vi triển khai.

### 9.4. Theo dõi job đến trạng thái thực tế

Phân biệt đã nhận yêu cầu, đang validation, đã commit, đang push, thành công, thất bại và chưa xác định.

Lưu định danh job và kết quả trên từng đơn vị triển khai. HTTP thành công khi tạo job không chứng minh thay đổi đã có hiệu lực.

Nếu kết nối tới manager mất sau khi gửi, tra cứu trạng thái trước khi retry. Không tạo hai lần triển khai chỉ vì client không nhận được phản hồi đầu tiên.

## 10. Logic quyết định thực thi tham khảo

Đây là mô tả quy trình, không phải một policy engine hoàn chỉnh:

```text
1. Nạp yêu cầu và revision từ nguồn đáng tin.
2. Xác thực principal thực thi.
3. Nạp artifact, baseline, phụ thuộc và target list đã chốt.
4. Xác minh bản ghi approval và thẩm quyền của từng người.
5. Gán hai slot cho hai người hợp lệ khác nhau.
6. Kiểm tra thời hạn, trạng thái rút/hủy và cửa sổ thực hiện.
7. Đối chiếu cấu hình hiện tại và thay đổi đang chờ.
8. Giữ ràng buộc revision / khóa theo khả năng nền tảng.
9. Cấp quyền thực thi hẹp và gửi đúng artifact.
10. Theo dõi kết quả, kiểm chứng tại đích và kết thúc quyền.
```

Nếu một điều kiện bắt buộc không xác minh được, không tự coi là đúng để tiếp tục thay đổi.

### 10.1. Chỉ tin dữ liệu từ nguồn có thẩm quyền

Client có thể gửi change_id hoặc artifact reference, nhưng server phải tự lấy trạng thái và đối chiếu.

Những trường như approved_by, target_count hoặc baseline_revision do client khai không được dùng để tự chứng minh điều kiện đã đạt.

### 10.2. Phê duyệt bị rút trước lúc thực thi

Cần kiểm tra trạng thái mới nhất tại điểm quyết định. Nếu job đã bắt đầu, định nghĩa cách xử lý hủy phù hợp với giai đoạn: chưa gửi, đang cài hoặc đã áp dụng một phần.

Không báo “đã hủy” chỉ vì dừng giao diện trong khi backend vẫn tiếp tục push.

### 10.3. Một approval không được dùng lại tùy ý

Bản ghi phê duyệt cần gắn với đúng change revision và điều kiện triển khai.

Việc chạy lại cùng artifact sau một lỗi có thể hợp lệ trong phạm vi đã được cho phép, nhưng phải kiểm tra baseline, thời hạn và trạng thái đích. Nó không mặc định được dùng cho một lần mở rule ở môi trường khác hoặc nhiều ngày sau.

### 10.4. Cấp quyền JIT cho executor

PAM có thể cấp một phiên hoặc credential cho đúng job, thiết bị và cửa sổ triển khai.

Nếu thiết bị chỉ hỗ trợ role rộng hơn thay đổi cụ thể, cần kiểm soát artifact, đường sử dụng và audit bổ sung. Phải ghi rõ giới hạn; không mô tả credential toàn quyền là “chỉ sửa một rule” nếu engine không cưỡng chế điều đó.

Thời hạn ngắn cũng không ngăn executor tạo user, key hoặc thay policy khác nếu nó còn có khả năng đó. Kiểm tra quyền và tồn dư vẫn cần thiết.

## 11. Kiểm chứng sau cài đặt

### 11.1. Đối chiếu cấu hình hiệu lực

Xác định rule, object và trạng thái thực tế trên từng đích. Không chỉ đọc cấu hình ứng viên trong manager.

Kiểm tra những trường quan trọng như source, destination, service, action, vị trí, schedule, logging và profile áp dụng. Xem cả phần kế thừa hoặc cấu hình local có thể thay đổi kết quả.

### 11.2. Thử luồng được phép

Dùng nguồn, đích và điều kiện nằm trong phạm vi thử nghiệm được ủy quyền.

Mục tiêu là chứng minh luồng nghiệp vụ cần thiết hoạt động qua đúng đường và đúng rule, không chỉ thấy một kết nối thành công từ bất kỳ nơi nào.

Kết nối được không thay thế xác thực và phân quyền tại ứng dụng đích. Firewall quyết định một lớp kết nối, không tự cấp quyền nghiệp vụ cho người gọi.

### 11.3. Thử luồng phải bị chặn

Nêu trước tập kiểm tra có mục tiêu:

- Nguồn ngoài phạm vi không được mở thêm.
- Đích khác không nhận quyền ngoài ý muốn.
- Dịch vụ hoặc port không được yêu cầu vẫn bị kiểm soát.
- Luồng qua miền khác không được vô tình mở.

Không mở rộng việc thử thành khảo sát hay truy cập ngoài phạm vi được giao.

### 11.4. Session đã tồn tại

Với firewall có theo dõi trạng thái, sửa hoặc xóa rule không được mặc định coi là chấm dứt mọi kết nối trước đó. Hành vi phụ thuộc nền tảng, policy và loại lưu lượng.

Nếu mục tiêu yêu cầu kết thúc một kết nối, cần kiểm tra và sử dụng cơ chế phù hợp trong phạm vi được cho phép. Không xóa toàn bộ session của production chỉ để kiểm tra một thay đổi nhỏ.

### 11.5. Logging và đường quản trị

Xác minh dấu vết lưu lượng và sự kiện thay đổi được ghi như dự kiến. Kiểm tra PAM, AAA, manager và nơi nhận log vẫn hoạt động.

Một thay đổi policy thành công nhưng làm mất khả năng quản trị hoặc quan sát cần được xử lý theo tiêu chí dừng hoặc phục hồi đã xác định.

## 12. Thất bại một phần và rollback

### 12.1. Một nhóm thiết bị có thể không cùng trạng thái

Khi triển khai tới nhiều firewall hoặc một kiến trúc dự phòng, một đích có thể thành công trong khi đích khác thất bại.

Cần biết đơn vị triển khai thực tế và cơ chế đồng bộ của nền tảng. Không giả định mọi target là một transaction duy nhất.

Hồ sơ phải nêu rõ:

| Đích | Revision mong muốn | Trạng thái thực tế | Việc tiếp theo |
| --- | --- | --- | --- |
| FW-LAB-A | Revision 3 | Đã xác minh áp dụng | Theo dõi |
| FW-LAB-B | Revision 3 | Chưa áp dụng, job lỗi | Đánh giá retry hoặc rollback |
| Toàn thay đổi | Revision 3 | Chưa hoàn tất | Không đóng như thành công |

Bảng chỉ minh họa cách ghi trạng thái, không mô tả cơ chế HA của một sản phẩm cụ thể.

### 12.2. Rollback cần nội dung và thẩm quyền

Xác định trước thay đổi ngược, điều kiện kích hoạt, người được quyết định và phạm vi.

Một rollback nằm trong gói đã được duyệt có thể được thực thi theo điều kiện đã chốt. Nếu cần mở rộng nội dung hoặc ảnh hưởng các thay đổi khác, phải đánh giá lại thẩm quyền phù hợp.

Không coi rollback là quyền khôi phục tùy ý toàn bộ cấu hình cũ.

### 12.3. Không ghi đè thay đổi hợp lệ của người khác

Snapshot trước thay đổi có thể không còn là trạng thái đúng nếu có việc khác đã hoàn thành sau đó.

Cần đối chiếu baseline hiện tại và ảnh hưởng của rollback. Ưu tiên phương án phục hồi được đánh giá đúng phạm vi thay vì đè một bản cấu hình cũ lên toàn thiết bị.

Nếu nền tảng chỉ hỗ trợ khôi phục rộng, điều này phải nằm trong phân tích tác động và điều phối thay đổi từ trước.

### 12.4. Retry cần kiểm tra lại điều kiện

Retry có thể cần đọc kết quả job cũ, xác minh trạng thái đích và xem approval còn hiệu lực.

Không tự mở rộng push scope hoặc tắt validation để vượt lỗi. Khi lỗi cho thấy nội dung hoặc phụ thuộc không còn phù hợp, quay lại quy trình đối chiếu.

## 13. Hai thời hạn: quyền thay đổi và vòng đời rule

Cửa sổ triển khai và thời gian rule hoạt động là hai điều khác nhau.

Trong hồ sơ ví dụ:

- Executor được thực hiện thay đổi từ 14:00 đến 14:30.
- Rule tạm được phép có hiệu lực đến 18:00.

Sau 14:30, quyền sửa policy của executor phải kết thúc theo thiết kế. Rule vẫn có thể tiếp tục hoạt động đến 18:00 vì đó là vòng đời đã được duyệt, không phải bằng chứng rằng executor còn quyền.

### 13.1. Rule thường trực

Với rule không tạm thời, vẫn cần chủ sở hữu và lịch rà soát phù hợp. Hai approval cho một lần cài đặt không xác nhận rằng nhu cầu kết nối tồn tại mãi.

Khi dịch vụ hoặc dữ liệu thay đổi, đánh giá lại policy và người chịu trách nhiệm.

### 13.2. Rule tạm thời

Cần cơ chế schedule hoặc controller thực thi hết hạn theo khả năng nền tảng.

Kiểm tra múi giờ, nguồn thời gian, hành vi khi manager mất và khả năng dọn tại đích. Một trường expires_at trong ticket không tự làm thiết bị ngừng cho phép luồng.

Nếu việc xóa hoặc vô hiệu rule là một hành động được định sẵn trong gói phê duyệt, ràng buộc nó với đúng đối tượng và điều kiện. Khi trạng thái hiện tại đã khác khiến cleanup có tác động mới, phải xử lý theo nhánh được thiết kế.

### 13.3. Gia hạn không chỉ sửa ngày

Kéo dài rule là tiếp tục cho phép truy cập. Cần kiểm tra nhu cầu còn tồn tại, phạm vi và rủi ro hiện tại.

Nếu chính sách yêu cầu dual approval cho gia hạn, phải có hai quyết định phù hợp với revision mới. Không cho chủ sở hữu tự đổi schedule rồi giữ approval của thời hạn trước.

### 13.4. Hết hạn rule và kết thúc session

Tới hạn không được báo cáo rằng mọi luồng đã ngừng nếu chưa kiểm tra hành vi session của nền tảng.

Cần bằng chứng rule không còn cho phép theo thiết kế và những kết nối tồn tại được xử lý theo mục tiêu đã phê duyệt.

## 14. Trường hợp khẩn cấp

Một sự cố có thể yêu cầu thay đổi nhanh, nhưng “khẩn cấp” không tự tạo quyền bỏ chốt.

Chính sách cần chuẩn bị:

- Điều kiện kích hoạt và người xác nhận.
- Các vai trò phê duyệt dự phòng.
- Kênh quyết định khi ticket hoặc SSO chính không hoạt động.
- Phạm vi thay đổi và thời hạn.
- Bằng chứng tạm thời và cách đối chiếu sau đó.
- Cơ chế kết thúc quyền và rule phát sinh.

Nếu tổ chức có đường ngoại lệ với mức phê duyệt khác, phải gọi đúng tên và ghi rõ thẩm quyền. Hậu kiểm sau sự cố không được báo cáo nhầm là hai phê duyệt trước triển khai.

### 14.1. Chuẩn bị người dự phòng

Hai approval không nên phụ thuộc duy nhất vào hai cá nhân không có người thay thế. Thiết kế nhóm đủ năng lực và cách xác minh người có quyền tại thời điểm cần.

Không giải quyết thiếu người bằng tài khoản approver dùng chung hoặc nhờ người khác cho mượn credential.

### 14.2. Bảo vệ đường break-glass

Credential local hoặc đường truy cập trực tiếp có thể cần cho phục hồi. Nó phải được kiểm kê, bảo quản và giám sát.

Nếu người dùng thường xuyên dùng đường này để cài policy không đủ approval, quy trình bình thường chỉ là hình thức. Cần có bằng chứng về việc sử dụng và đối chiếu các thay đổi phát sinh.

### 14.3. Quyền phục hồi không làm mất trách nhiệm giải trình

Dù dùng đường nào, cần nối được người quyết định, người thực hiện, thay đổi thật và tác động.

Nếu audit chính mất, ghi nhận giới hạn bằng chứng và thực hiện phương án bổ sung đã được phép. Không tuyên bố mọi điều kiện kiểm soát đều đạt khi chưa xác minh được.

## 15. Audit và bảo vệ quy trình

Một chuỗi kiểm toán hữu ích là:

```text
Change request
   → revision và artifact
   → hai quyết định độc lập
   → kiểm tra trước triển khai
   → grant / phiên / principal thực thi
   → job và kết quả từng firewall
   → kiểm tra lưu lượng, rollback nếu có
   → thu hồi quyền và vòng đời rule
```

### 15.1. Thông tin cần lưu

| Nhóm | Nội dung minh họa |
| --- | --- |
| Yêu cầu | Chủ thể, mục đích, dữ liệu và dịch vụ |
| Artifact | Revision, digest, baseline và phụ thuộc |
| Approval | Principal, slot, quyết định, thời điểm, điều kiện |
| Thực thi | Executor, credential reference phù hợp, job ID, target scope |
| Kết quả | Revision tại đích, trạng thái từng target, kiểm tra dịch vụ |
| Sự cố | Lỗi, retry, hủy, rollback và trạng thái chưa xác định |
| Kết thúc | Quyền đã thu hồi, phiên đã xử lý, rule đã rà soát hoặc hết hạn |

Không lưu password hoặc API key trong hồ sơ để liên kết. Dùng tham chiếu có kiểm soát.

### 15.2. Bảo vệ quyền sửa approval

Người duyệt không được tùy ý sửa quyết định lịch sử của người khác. Người quản trị hệ thống cũng cần dấu vết khi thay nhóm duyệt, chính sách hoặc bản ghi.

Thiết kế cần phát hiện thay đổi có thể ảnh hưởng tính toàn vẹn của quyết định. Tách quyền quản trị bằng chứng phù hợp với mức rủi ro; không chỉ lưu tất cả trong cùng một bảng mà mọi người vận hành đều sửa được.

### 15.3. Những tín hiệu đáng điều tra

- Cùng một người xuất hiện ở cả hai slot bằng các tài khoản khác nhau.
- Thay artifact hoặc object ngay sau khi đủ approval.
- Push scope rộng hơn hồ sơ.
- Executor chạy thao tác ngoài artifact.
- Tạo user, API key hoặc thay AAA trong phiên cài policy.
- Phê duyệt rất nhanh nhưng không có thông tin review cần thiết.
- Thay nhóm approver gần thời điểm cài đặt.
- Truy cập trực tiếp thay cho đường triển khai được quản lý.
- Rule tạm tồn tại quá thời hạn hoặc bị gia hạn liên tục.
- Job thất bại một phần nhưng ticket đã đóng thành công.

Tín hiệu cần được đối chiếu, không tự kết luận gian lận. Mục tiêu là phát hiện chênh lệch có ảnh hưởng tới thẩm quyền và phạm vi.

### 15.4. Chỉ số chất lượng

Theo dõi tỷ lệ thay đổi có đủ bằng chứng, thay đổi sau duyệt, phạm vi push lệch, rule tạm quá hạn và thời gian xử lý trạng thái chưa xác minh.

Không chỉ tối ưu thời gian duyệt hoặc số lượng ticket đóng. Hai chữ ký nhanh không có ích nếu người duyệt không thấy đúng nội dung.

## 16. Tình huống thực hành

Một ứng dụng cần gọi dịch vụ đối tác qua HTTPS từ tập máy được xác định. Change request ban đầu đề xuất một rule hẹp, có hiệu lực trong đợt kiểm thử.

### 16.1. Hai trách nhiệm xem xét

Chủ sở hữu ứng dụng xác nhận dịch vụ, tập nguồn, đích và thời gian thử.

Người phụ trách policy xem zone, NAT, object phụ thuộc, vị trí rule, logging, các luồng phải bị chặn và phạm vi firewall.

Hai người duyệt revision 3, gắn với artifact và baseline cụ thể.

### 16.2. Phát hiện thay đổi trước lúc push

Trước khi chạy, executor phát hiện address group nguồn đã được bổ sung một mạng khác bởi change khác.

Dù rule vẫn giữ nguyên tên group và port, phạm vi hiệu lực đã khác phần được duyệt. Job dừng để đối chiếu, dựng lại tác động và xử lý approval phù hợp.

Không dùng lý do “chỉ thay group, không thay rule” để giữ nguyên quyết định cũ.

### 16.3. Thực thi nội dung đúng phạm vi

Sau khi revision và quyết định được cập nhật, executor cài đúng artifact tới đúng target.

Kết quả được kiểm tra tại từng firewall. Luồng hợp lệ đi được; những nguồn ngoài phạm vi vẫn bị kiểm soát theo bài thử đã được phép.

Nếu một target lỗi, trạng thái toàn thay đổi vẫn là chưa hoàn tất. Đội vận hành chọn retry hoặc rollback theo điều kiện đã duyệt.

### 16.4. Kết thúc

Quyền cài policy của executor được thu hồi, phiên được xử lý và không có credential hoặc grant mới ngoài nhiệm vụ.

Rule tạm được theo dõi đến hạn. Việc hết hạn được xác minh trên policy và hành vi kết nối theo thiết kế. Hồ sơ giữ đủ liên kết giữa hai quyết định, nội dung đã cài và kết quả.

## 17. Bộ kiểm tra nghiệm thu

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Chưa có approval | Không triển khai qua đường được kiểm soát |
| Chỉ có một approval hợp lệ | Chưa đạt chốt hai quyết định |
| Cùng người dùng hai tài khoản | Không được tính thành hai người độc lập |
| Một người thuộc hai nhóm | Không lấp được cả hai slot trong mô hình này |
| Người yêu cầu hoặc executor tự duyệt | Không được tính khi chính sách loại trừ |
| Approval sai revision hoặc hết hạn | Không được sử dụng để cài |
| Approval bị rút trước thực thi | Quyết định được kiểm tra lại |
| Artifact đổi sau duyệt | Chốt phát hiện nội dung mới |
| Address group phụ thuộc thay đổi | Phạm vi hiệu lực được đánh giá lại |
| Baseline hoặc thay đổi đang chờ khác dự kiến | Không gộp và push mù |
| Đổi target hoặc context | Không sử dụng approval cho đích khác |
| Gọi API install trực tiếp | Không bỏ qua điều kiện kiểm soát |
| Executor có credential rộng | Đường sử dụng và thao tác ngoài artifact được kiểm soát, phát hiện |
| Manager commit thành công, một firewall lỗi | Trạng thái phản ánh thất bại một phần |
| Phản hồi job mất | Tra cứu trước retry |
| Rollback gặp thay đổi mới của người khác | Không ghi đè ngoài phạm vi |
| Rule tạm tới hạn | Có cơ chế dọn và kiểm tra tại đích |
| Có session mở trước khi rule hết hạn | Hành vi được xử lý đúng mục tiêu |
| Quyền executor hết hạn | Grant và phiên được kiểm chứng riêng với vòng đời rule |
| Hai approval đầy đủ và nội dung hợp lệ | Thay đổi được thực hiện và có bằng chứng kết quả |

Thực hiện kiểm tra trên môi trường, nguồn và đích được phép. Không dùng nghiệm thu để mở lưu lượng ngoài nhu cầu hoặc làm mất đường quản trị production không có kế hoạch.

## 18. Bài tập áp dụng

Một tổ chức có quy trình hai approval trong ticket, nhưng:

- Người tạo rule có thể sửa address object sau khi được duyệt.
- Cùng một người được dùng hai tài khoản thuộc hai nhóm duyệt.
- API key của pipeline có thể push mọi policy package.
- Manager đánh dấu commit thành công dù một số target chưa nhận cấu hình.
- Rule tạm chỉ có ngày hết hạn trong comment.
- Cleanup và rollback chưa được ràng buộc với phạm vi được phép.

Hãy thiết kế lại:

1. Định nghĩa người duyệt độc lập và các vai trò bị loại trừ.
2. Xác định nội dung phải chốt trong artifact.
3. Ràng buộc baseline, object phụ thuộc và target scope.
4. Đặt chốt trên đường thực thi thực tế.
5. Xử lý thay đổi đồng thời, retry và thất bại một phần.
6. Tách thời hạn quyền executor khỏi vòng đời rule.
7. Thiết kế bằng chứng và bộ kiểm tra phủ định.
8. Chuẩn bị nhánh khẩn cấp và phục hồi có thẩm quyền.

Một đáp án tốt chỉ rõ thành phần nào cưỡng chế từng điều kiện. Thêm một nút Approve mà không kiểm soát artifact và đường push chưa giải quyết bài toán.

## 19. Tiêu chí hoàn thành

Dual approval cho thay đổi firewall đạt mục tiêu khi chứng minh được:

- Hai người và hai trách nhiệm được định nghĩa, xác thực và kiểm tra độc lập.
- Nhu cầu, rủi ro và phạm vi hiệu lực được cung cấp đủ để quyết định.
- Approval gắn với đúng revision, artifact, baseline, phụ thuộc và target.
- Thay đổi có ý nghĩa sau duyệt được đối chiếu lại theo chính sách.
- CLI, API, pipeline và manager không tạo đường triển khai ngoài kiểm soát thường ngày.
- Quyền executor có phạm vi, thời hạn và bằng chứng sử dụng.
- Validation, commit, push và trạng thái thực tế được phân biệt.
- Thất bại một phần, hủy, retry và rollback có quy trình rõ ràng.
- Rule tạm và quyền quản trị có vòng đời được kiểm chứng riêng.
- Audit nối được hai quyết định với nội dung đã cài và kết quả.

Hai approval có giá trị khi chúng ràng buộc được thẩm quyền với đúng thay đổi firewall được thực hiện. Số lượng chữ ký là một điều kiện; tính độc lập, phạm vi hiệu lực và chốt tại đường triển khai mới giúp điều kiện đó trở thành kiểm soát đặc quyền có tác dụng.


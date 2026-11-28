# Test onboarding trong Privileged Access Management

## 1. Mục tiêu của kiểm thử onboarding

Onboarding trong Privileged Access Management (PAM) là quá trình đưa một tài nguyên hoặc tài khoản đặc quyền vào phạm vi quản lý đã được phê duyệt. Tùy kiến trúc, quá trình này có thể bao gồm đăng ký máy đích, nhận diện tài khoản, gán chủ sở hữu, đưa credential vào vault, gắn chính sách truy cập, cấu hình luân chuyển và kiểm tra đường kết nối.

**Test onboarding phải chứng minh tài khoản được quản lý đúng, truy cập được theo quyền cho phép và không tạo thêm đường truy cập ngoài chính sách.** Một bản ghi xuất hiện trong giao diện PAM chưa đủ để kết luận onboarding thành công.

Ví dụ, tài khoản quản trị được thêm vào vault nhưng credential sai thì chưa thể phục vụ vận hành. Ngược lại, credential đúng nhưng một nhóm không liên quan có quyền checkout lại là lỗi kiểm soát truy cập. Nếu tài khoản dịch vụ được đổi mật khẩu mà ứng dụng phụ thuộc vẫn giữ giá trị cũ, onboarding có thể làm gián đoạn dịch vụ dù giao diện báo thành công.

Sau bài học, người học có thể:

- Xác định điều kiện đầu vào và tiêu chí nghiệm thu cho một luồng onboarding PAM.
- Thiết kế ca kiểm thử cho tài khoản quản trị, tài khoản dịch vụ và các tài nguyên có tên dễ trùng.
- Kiểm tra chính sách, credential, quyền truy cập, audit và tác động đến hệ thống đích.
- Phân biệt lỗi cấu hình, lỗi kết nối và lỗi trạng thái từng phần.
- Lập bộ bằng chứng đủ để quyết định chấp nhận, sửa lỗi hoặc rollback một đợt onboarding.

Bài học sử dụng mô hình trung lập sản phẩm. Các tên trạng thái, sự kiện và cấu hình bên dưới là quy ước minh họa của phòng lab; khi áp dụng phải ánh xạ sang chức năng thực tế của hệ thống PAM đang triển khai.

## 2. Xác định chính xác đối tượng được onboard

### 2.1. Tài nguyên và tài khoản là hai đối tượng khác nhau

Tài nguyên là nơi quyền đặc biệt có hiệu lực: máy chủ, thiết bị mạng, cơ sở dữ liệu, nền tảng cloud hoặc một hệ thống quản trị. Tài khoản là danh tính có quyền trên tài nguyên đó.

Một máy chủ có thể đã được đăng ký nhưng tài khoản quản trị của nó chưa được vault quản lý. Một tài khoản có thể đã có trong kho credential nhưng chưa được cấu hình đi qua session broker. Khi thiết kế ca kiểm thử, cần nêu rõ thành phần nào nằm trong phạm vi.

| Đối tượng | Ví dụ phòng lab | Điều cần xác minh |
| --- | --- | --- |
| Tài nguyên | Máy chủ `srv-lab-a` | Đúng định danh, môi trường, endpoint và phương thức kết nối |
| Tài khoản | `ops-admin` trên `srv-lab-a` | Đúng tài khoản đích, loại tài khoản và chủ sở hữu |
| Credential | Mật khẩu hoặc khóa của tài khoản | Đúng bí mật, đúng phiên bản, được bảo vệ theo chính sách |
| Chính sách | Truy cập có phê duyệt, giới hạn thời gian | Đúng người dùng, nhóm, hành động, thời hạn và đường truy cập |
| Phụ thuộc | Dịch vụ sử dụng tài khoản `svc-report-lab` | Được nhận diện và có phương án cập nhật credential phù hợp |
| Bằng chứng | Mã yêu cầu, audit event, kết quả kết nối | Liên kết được toàn bộ chuỗi thao tác và kết quả thực tế |

Không dùng mỗi tên đăng nhập làm khóa nhận diện. Hai máy có thể cùng có tài khoản cục bộ tên `ops-admin`. Một phép đối chiếu phù hợp cần phân biệt ít nhất định danh tài nguyên, phạm vi danh tính và định danh tài khoản mà hệ thống đích cung cấp.

Địa chỉ IP hoặc hostname cũng có thể thay đổi. Nếu PAM hỗ trợ một định danh tài nguyên ổn định, ca kiểm thử nên xác nhận mapping đó thay vì chỉ so sánh nhãn hiển thị.

### 2.2. Discovery không đồng nghĩa với onboarding

Discovery giúp tìm tài nguyên và tài khoản có khả năng cần quản lý. Kết quả discovery có thể thiếu chủ sở hữu, có tài khoản đã vô hiệu hóa hoặc chứa đối tượng không thuộc phạm vi phê duyệt.

Vì vậy, cần kiểm thử ranh giới giữa hai bước:

1. Tài khoản được phát hiện nhưng chưa được duyệt có bị cấp quyền sử dụng trong PAM hay không?
2. Một lần chạy discovery lại có tự thay đổi chính sách của đối tượng đã được quản lý không?
3. Tài khoản bị loại khỏi phạm vi có bị onboard ngoài ý muốn không?
4. Dữ liệu discovery cũ có khiến hệ thống gắn credential vào nhầm tài nguyên không?

Một luồng an toàn có thể tự động hóa nhiều bước, nhưng tiêu chí lựa chọn và quyền thay đổi phải rõ ràng. Không suy ra rằng mọi tài khoản phát hiện được đều phải được đưa vào vault.

## 3. Mô hình trạng thái dùng để thiết kế ca kiểm thử

Có thể dùng chuỗi trạng thái minh họa sau để phân tích onboarding:

```text
Đề xuất đối tượng
    → Xác minh định danh, chủ sở hữu và phạm vi
    → Phê duyệt
    → Đăng ký tài nguyên/tài khoản
    → Nạp hoặc thiết lập credential
    → Gắn chính sách
    → Xác minh khả năng sử dụng
    → Đưa vào quản lý vận hành
```

Chuỗi này không quy định sản phẩm phải thực thi các bước theo đúng thứ tự trên. Một số hệ thống gắn chính sách trước khi nạp credential; một số hệ thống xác minh kết nối ở nhiều giai đoạn. Điều cần giữ là các bất biến kiểm soát.

**Bất biến** là điều phải luôn đúng trong những trạng thái mà tổ chức đã quy định. Ví dụ:

- Trước khi đủ điều kiện nghiệm thu, tài khoản chưa được công bố cho người dùng vận hành thông thường.
- Credential của đối tượng A không được dùng để kết nối đối tượng B.
- Việc gắn tài khoản vào nhóm quản lý không tự tạo thêm đặc quyền trên máy đích.
- Người thực hiện onboarding không mặc nhiên được xem bí mật vừa nạp.
- Thao tác thành công hoặc thất bại đều để lại dấu vết phù hợp.
- Trạng thái không xác định phải được điều tra trước khi retry một thao tác có thể đã thay đổi credential.

Không nên dùng một cờ `success=true` để thay thế mọi tiêu chí. Có thể tách kết quả theo các chiều:

```text
identity_verified
owner_verified
credential_verified
policy_verified
authorized_access_verified
unauthorized_access_denied
dependency_verified
audit_verified
```

Nếu một chiều nằm ngoài phạm vi, ghi rõ lý do là “không áp dụng”. Nếu chưa thực hiện được, ghi “chưa kiểm tra”, không đổi thành “đạt”.

## 4. Chuẩn bị môi trường, quyền và baseline

### 4.1. Dùng tài khoản và tài nguyên thử nghiệm có phạm vi rõ

Bắt đầu bằng tài nguyên lab hoặc môi trường kiểm thử đã được cho phép. Không thử onboarding hàng loạt trên production chỉ để xem hệ thống phản ứng ra sao.

Một bộ dữ liệu nhỏ nhưng có chủ đích thường hữu ích hơn nhiều bản ghi giống hệt nhau:

| Mã | Tài nguyên/tài khoản lab | Mục đích |
| --- | --- | --- |
| A1 | `srv-lab-a / ops-admin` | Luồng quản trị thông thường |
| A2 | `srv-lab-b / ops-admin` | Kiểm tra trùng tên tài khoản trên tài nguyên khác |
| A3 | `srv-lab-a / svc-report-lab` | Kiểm tra tài khoản dịch vụ và phụ thuộc |
| A4 | `srv-lab-a / disabled-admin-lab` | Kiểm tra tài khoản bị vô hiệu hóa |
| A5 | Tài khoản đã có bản ghi PAM | Kiểm tra duplicate và retry |
| A6 | Đối tượng có chủ sở hữu chưa xác minh | Kiểm tra điều kiện từ chối hoặc cách ly |

Các credential trong bộ dữ liệu phải là bí mật thử nghiệm. Trong tài liệu và báo cáo chỉ dùng mã tham chiếu; không chèn giá trị mật khẩu, private key hoặc token.

Với A3, chuẩn bị một dịch vụ lab có kiểm tra sức khỏe và một giao dịch nghiệp vụ đơn giản. Một tiến trình vẫn đang chạy chưa chứng minh credential mới hoạt động, vì tiến trình có thể còn giữ kết nối cũ.

### 4.2. Phân biệt các vai trò kiểm thử

Tối thiểu nên có các danh tính thử nghiệm sau:

- Người đề xuất onboarding.
- Người có quyền phê duyệt theo chính sách.
- Tài khoản connector thực hiện thao tác kỹ thuật trên đích.
- Người vận hành được cấp quyền sử dụng tài khoản sau onboarding.
- Người dùng không có quyền với đối tượng.
- Người đọc audit hoặc người xác minh bằng chứng.

Không bắt buộc mỗi vai trò là một con người khác nhau trong mọi tổ chức. Tuy nhiên, ca kiểm thử phải xác định lúc nào cần tách nhiệm vụ và chứng minh các quyền thực tế đúng với yêu cầu.

Đặc biệt, quyền thêm tài khoản vào vault không nhất thiết bao gồm quyền đọc bí mật. Quyền vận hành phiên cũng không nhất thiết bao gồm quyền export credential.

### 4.3. Lưu baseline trước khi thay đổi

Baseline giúp phân biệt ảnh hưởng do onboarding với trạng thái đã tồn tại. Cần ghi nhận:

- Định danh tài nguyên và tài khoản, môi trường, trạng thái bật/tắt hoặc khóa.
- Chủ sở hữu nghiệp vụ và người chịu trách nhiệm kỹ thuật.
- Nhóm, role và quyền đặc biệt hiện có trên hệ thống đích.
- Chính sách PAM dự kiến: ai được sử dụng, dùng cách nào, trong bao lâu.
- Cách quản lý credential hiện tại và việc có đổi credential lúc onboarding hay không.
- Phụ thuộc đã biết, phép kiểm tra sức khỏe và giao dịch xác minh.
- Cấu hình kết nối cần thiết, bằng chứng kiểm tra máy đích và nguồn audit.
- Mã yêu cầu thay đổi, phiên bản chính sách, thời điểm bắt đầu và phương án phục hồi.

Chỉ thu thập dữ liệu cần thiết. Không tạo “baseline” bằng cách xuất toàn bộ vault hoặc lưu credential ra một file đối chiếu.

Với quyền trên máy đích, có thể lưu danh sách role hoặc bản chụp cấu hình đã loại bỏ bí mật. Với credential, lưu mã phiên bản hoặc metadata phù hợp; không công bố hash mật khẩu hay dữ liệu có thể hỗ trợ dò bí mật.

### 4.4. Chốt trước kết quả mong đợi

Một số câu hỏi phải được trả lời trước khi chạy:

- Onboarding có bao gồm đổi credential lần đầu hay chỉ xác minh credential hiện tại?
- Có cho phép checkout mật khẩu hay chỉ khởi tạo phiên qua broker?
- Có phê duyệt trước khi công bố tài khoản cho người dùng không?
- Tài khoản dịch vụ được cập nhật phụ thuộc bằng cơ chế nào?
- Lỗi xác minh sẽ giữ đối tượng ở trạng thái chờ hay rollback?
- Thời gian chờ chấp nhận được và người chịu trách nhiệm xử lý là ai?
- Tài khoản bị vô hiệu hóa có được phép đăng ký như một đối tượng cách ly không?

Không có một đáp án áp dụng cho mọi triển khai. Ca kiểm thử phải so sánh với chính sách đã chốt, thay vì tự chọn kết quả thuận tiện sau khi thấy hệ thống chạy.

## 5. Thiết kế ca kiểm thử theo rủi ro

Một ca kiểm thử có thể dùng cấu trúc sau:

```yaml
testId: PAM-ONB-001
title: Onboarding tài khoản quản trị lab
targetRef: ASSET-LAB-A
accountRef: ACCOUNT-LAB-A1
preconditions:
  - Đã xác minh định danh và chủ sở hữu
  - Credential thử nghiệm còn hiệu lực
  - Chính sách truy cập thử nghiệm đã được phê duyệt
action:
  - Gửi một yêu cầu onboarding
  - Chờ đến trạng thái kết thúc trong thời hạn kiểm thử
  - Xác minh quyền và khả năng truy cập theo chính sách
expected:
  - Tạo đúng một mapping tài nguyên và tài khoản
  - Credential chỉ được sử dụng theo quyền đã duyệt
  - Người không có quyền bị từ chối
  - Có bằng chứng liên kết yêu cầu với kết quả
evidence:
  - requestId
  - policyVersion
  - targetVerificationRef
  - auditEventRefs
```

Đây là mẫu tài liệu kiểm thử, không phải schema cấu hình của một sản phẩm PAM.

Một ma trận bao phủ tối thiểu có thể gồm:

| Nhóm | Ca kiểm thử | Điều quan sát chính |
| --- | --- | --- |
| Luồng chuẩn | Onboard A1 với đầu vào hợp lệ | Đúng mapping, chính sách, credential và audit |
| Định danh | Onboard A1 và A2 cùng tên tài khoản | Hai tài khoản không bị hợp nhất hoặc dùng nhầm credential |
| Quyền | Người không được cấp quyền gửi yêu cầu hoặc sử dụng tài khoản | Bị từ chối tại đúng ranh giới |
| Dữ liệu đầu vào | Thiếu chủ sở hữu, sai loại nền tảng, sai phạm vi tài khoản | Từ chối hoặc cách ly theo quy định |
| Credential | Credential sai, hết hiệu lực hoặc chưa được cấp | Không công bố tài khoản như đã sẵn sàng |
| Kết nối | Đích không thể truy cập hoặc không xác minh được danh tính máy đích | Lỗi rõ ràng, không bỏ qua kiểm tra bảo mật |
| Trùng lặp | Gửi lại cùng yêu cầu | Kết quả nhất quán, không tạo bản ghi hoặc thay đổi dư |
| Đồng thời | Hai yêu cầu cùng onboard một tài khoản | Có cơ chế kiểm soát xung đột |
| Phụ thuộc | Onboard tài khoản dịch vụ có đổi credential | Ứng dụng hoạt động với credential được quản lý |
| Lỗi từng phần | Đích đã đổi credential nhưng phản hồi bị mất | Phát hiện trạng thái không xác định và phục hồi có kiểm soát |
| Audit | Thành công, thất bại, từ chối và retry | Truy vết được, không lộ bí mật |
| Rollback | Hủy một onboarding chưa đạt | Khôi phục trạng thái quản lý đúng, không mất khả năng vận hành |

Ma trận giúp tổ chức công việc, nhưng mỗi dòng vẫn cần đầu vào, bước thực hiện và điều kiện đạt riêng. “Kiểm tra quyền” không phải là một ca kiểm thử đủ cụ thể.

## 6. Thực hiện luồng onboarding thành công

### 6.1. Bước 1 — Xác minh yêu cầu và định danh

Dùng A1 để gửi yêu cầu onboarding. Đối chiếu định danh tài nguyên, loại tài khoản, chủ sở hữu và phạm vi được duyệt.

Kiểm tra hệ thống có giữ đúng các trường định danh hay tự điền giá trị làm thay đổi ý nghĩa. Ví dụ, `ops-admin` cục bộ trên máy lab không được tự hiểu thành tài khoản domain chỉ vì hai đối tượng trùng tên.

Nếu kết nối dùng SSH, TLS hoặc một cơ chế xác minh máy đích khác, cần xác nhận việc kiểm tra danh tính đích hoạt động theo cấu hình đã duyệt. Không chấp nhận “kết nối thành công” nhờ tắt kiểm tra host key hoặc chứng thư chỉ để làm ca kiểm thử đạt.

Kết quả mong đợi: yêu cầu tham chiếu đúng đối tượng và được xử lý bởi vai trò có thẩm quyền.

### 6.2. Bước 2 — Kiểm tra connector và quyền thao tác

Connector phải có đủ quyền cho thao tác được giao, nhưng không tự cần quyền rộng hơn chỉ vì luồng onboarding đã bắt đầu.

Cần xác định connector đang làm gì:

- Chỉ xác minh credential được cung cấp.
- Khám phá hoặc đọc thuộc tính tài khoản.
- Đổi credential ban đầu.
- Cập nhật một phụ thuộc.
- Thực hiện reconciliation bằng một danh tính riêng được ủy quyền.

Các chức năng này có thể cần quyền khác nhau. Ca kiểm thử nên xác nhận thao tác thành công với tập quyền được phê duyệt và thất bại rõ ràng khi thiếu quyền bắt buộc.

Một luồng kiểm thử không được tự nâng connector lên quyền quản trị toàn hệ thống rồi coi đó là cách sửa lỗi. Nếu tập quyền ban đầu không phù hợp, cần ghi lại yêu cầu quyền thực tế và đưa qua quy trình phê duyệt cấu hình.

### 6.3. Bước 3 — Nạp hoặc thiết lập credential

Theo dõi credential được nạp vào đúng vault hoặc vùng quản lý, gắn với đúng tài khoản và chính sách truy cập.

Nếu chính sách chỉ yêu cầu nạp credential hiện tại, xác nhận onboarding không tự đổi mật khẩu trên đích. Nếu chính sách yêu cầu đổi lần đầu, xác nhận hoạt động đổi diễn ra trên đúng tài khoản và vault giữ phiên bản có hiệu lực sau thao tác.

Không cần nhìn thấy bí mật để xác minh. Có thể dùng cơ chế kiểm tra credential của PAM hoặc một phép kết nối thử được kiểm soát, kết hợp với metadata phiên bản và bằng chứng phía đích.

Một thông báo “đã lưu secret” chỉ chứng minh một giá trị đã được lưu. Nó chưa chứng minh giá trị đó dùng được trên tài khoản đích.

### 6.4. Bước 4 — Xác minh chính sách trước khi sử dụng

Dùng người vận hành được cấp quyền để thử đúng hành động mà chính sách cho phép. Sau đó dùng người không có quyền để thử cùng hành động.

Ví dụ, nếu tài khoản chỉ được dùng qua session broker:

- Người được phép tạo phiên theo luồng phê duyệt đã định.
- Người đó không tự được quyền xem hoặc export credential nếu chính sách không cho phép.
- Người ngoài nhóm không thể khởi tạo phiên chỉ vì biết mã tài khoản.
- Quyền quản lý metadata không tự chuyển thành quyền checkout.

Nếu có JIT, kiểm tra quyền được cấp trong thời hạn đã duyệt và hành vi sau khi hết hạn. Nếu có JEA, kiểm tra tập thao tác được phép theo cấu hình tương ứng. Không đánh dấu các tiêu chí này đạt khi hệ thống thử nghiệm chưa triển khai chúng; phải ghi rõ phạm vi.

### 6.5. Bước 5 — Xác nhận khả năng sử dụng ở máy đích

Một phiên mở được chưa đủ để chứng minh đã đăng nhập đúng đối tượng. Trong phòng lab, xác minh bằng thông tin danh tính không chứa bí mật và một hành động vô hại đã thống nhất.

Các bằng chứng nên trả lời được:

- Kết nối đến đúng tài nguyên nào?
- Danh tính hiệu lực trên đích là tài khoản nào?
- Hành động cho phép có thực hiện được không?
- Hành động ngoài quyền có bị từ chối không?
- Máy đích có ghi nhận lần xác thực tương ứng không?

Nếu PAM dùng một tài khoản gateway hoặc cơ chế ánh xạ danh tính, phải xác minh cả tài khoản khởi tạo phiên và tài khoản hiệu lực trên đích theo thiết kế. Không yêu cầu hai danh tính này giống nhau khi kiến trúc vốn có ánh xạ.

### 6.6. Bước 6 — So sánh với baseline và nghiệm thu

So sánh quyền trên máy đích trước và sau onboarding. Bất kỳ role mới, nhóm mới hoặc thay đổi trạng thái tài khoản nào đều phải có lý do trong yêu cầu đã được duyệt.

Tiếp theo, xác nhận audit, phụ thuộc, trạng thái quản lý và đường truy cập sau onboarding. Chỉ nghiệm thu khi toàn bộ tiêu chí bắt buộc đạt.

Một kết quả mẫu:

```text
PAM-ONB-001
Mapping đúng tài nguyên/tài khoản: PASS
Credential dùng được theo cơ chế được duyệt: PASS
Quyền người vận hành: PASS
Người không có quyền bị từ chối: PASS
Quyền trên đích không tăng ngoài phạm vi: PASS
Audit liên kết đầy đủ: PASS
Kết quả tổng: PASS
```

Không suy từ kết quả này rằng mọi tài khoản cùng nền tảng đều tự động đạt. Tài khoản dịch vụ, tài khoản bị khóa hoặc tài khoản thuộc phạm vi danh tính khác vẫn cần các ca riêng.

## 7. Kiểm thử đầu vào không hợp lệ và ranh giới quyền

### 7.1. Thiếu hoặc sai metadata

Thử bỏ chủ sở hữu bắt buộc, gán sai môi trường hoặc chọn sai loại tài khoản. Hệ thống phải từ chối, yêu cầu bổ sung hoặc đưa vào trạng thái cách ly đúng theo chính sách.

Ca kiểm thử cần quan sát cả dữ liệu sau lỗi. Một thông báo từ chối trên giao diện nhưng phía sau vẫn tạo tài khoản có thể sử dụng là lỗi.

Với dữ liệu được chuẩn hóa, cần kiểm tra quy tắc thực tế. Ví dụ, không tự giả định tên tài khoản phân biệt chữ hoa/chữ thường trên mọi nền tảng. Mục tiêu là tránh tạo mapping sai khi nền tảng và PAM xử lý tên khác nhau.

### 7.2. Tài khoản bị vô hiệu hóa hoặc đang khóa

Dùng A4 để kiểm tra onboarding có vô tình bật lại tài khoản hay mở khóa ngoài phạm vi không.

Có triển khai cho phép đăng ký tài khoản bị vô hiệu hóa để kiểm kê, nhưng giữ nó không thể sử dụng. Có triển khai từ chối ngay từ đầu. Cả hai chỉ được coi là phù hợp khi khớp chính sách đã chốt.

Không thử credential sai lặp lại đến mức gây khóa một tài khoản dùng chung. Dùng tài khoản lab, số lần thử được giới hạn và điều kiện dừng rõ ràng.

### 7.3. Người dùng không có quyền

Kiểm tra riêng quyền gửi yêu cầu, phê duyệt, sửa policy, nạp credential và sử dụng tài khoản. Một người có quyền ở giai đoạn này có thể không có quyền ở giai đoạn khác.

Nếu có API quản trị, cần kiểm tra cùng ranh giới bằng một client thử nghiệm được phép. Việc giao diện ẩn nút không chứng minh máy chủ đã kiểm tra quyền.

Kết quả mong đợi là yêu cầu trái quyền bị từ chối mà không tạo tác dụng phụ. Audit cần phản ánh hành vi từ chối với lượng thông tin phù hợp, không làm lộ credential hoặc chi tiết nhạy cảm cho người gọi.

### 7.4. Nhầm tài nguyên hoặc nhầm tài khoản

Dùng A1 và A2 để xác minh cùng tên đăng nhập không dẫn đến dùng chung credential hoặc chính sách ngoài ý muốn.

Thay đổi một trường trong yêu cầu lab để trỏ đến tài nguyên không thuộc phạm vi người đề xuất. Kết quả phải tuân theo kiểm tra phạm vi trên đối tượng thực tế, không chỉ dựa vào quyền tạo yêu cầu chung.

Một ca kiểm thử hữu ích là xác minh không thể thay account reference sau phê duyệt để thực thi onboarding cho đối tượng khác. Nếu hệ thống cho phép sửa yêu cầu, các thay đổi quan trọng phải được xử lý theo quy trình phê duyệt tương ứng.

## 8. Kiểm thử lỗi từng phần, retry và đồng thời

### 8.1. Phân biệt thất bại chắc chắn với kết quả chưa xác định

Trong hệ thống phân tán, timeout không luôn có nghĩa thao tác chưa xảy ra.

Ví dụ:

1. PAM gửi yêu cầu đổi credential lần đầu.
2. Máy đích thực hiện thành công.
3. Kết nối bị ngắt trước khi PAM nhận xác nhận.
4. PAM hoặc người vận hành nhìn thấy timeout.

Nếu retry bằng cách đổi credential lần nữa mà không kiểm tra trạng thái, vault và đích có thể tiếp tục lệch nhau. Vì vậy, ca kiểm thử phải quan sát cả tác dụng phía đích, trạng thái vault và cơ chế phục hồi.

Chỉ mô phỏng lỗi này trên tài nguyên lab có phương án phục hồi. Không ngắt kết nối của một connector phục vụ production chỉ để tạo lỗi.

| Điểm lỗi mô phỏng | Rủi ro | Điều cần xác minh |
| --- | --- | --- |
| Trước khi tạo bản ghi | Yêu cầu bị treo hoặc báo sai thành công | Không có đối tượng sẵn sàng sử dụng ngoài ý muốn |
| Sau khi tạo bản ghi, trước khi nạp credential | Bản ghi trống bị công bố | Đối tượng ở trạng thái chưa sẵn sàng, có đường xử lý |
| Sau khi lưu credential, trước khi gắn policy | Quyền mặc định quá rộng | Không có quyền sử dụng ngoài phê duyệt |
| Sau khi đích đã đổi credential, trước xác nhận | Vault và đích có thể lệch | Phát hiện được và có quy trình xác minh/phục hồi |
| Sau khi gắn policy, trước khi hoàn tất audit | Thiếu bằng chứng hoặc hoàn tất giả | Cơ chế phát hiện và xử lý đáp ứng yêu cầu audit đã định |
| Khi cập nhật phụ thuộc dịch vụ | Gián đoạn ứng dụng | Xác định phụ thuộc nào đã cập nhật và cách phục hồi |

Không phải sản phẩm nào cũng hỗ trợ chèn lỗi ở mọi điểm. Nếu không thể mô phỏng an toàn, ghi ca đó chưa thực hiện và chọn phương pháp xác minh khác đã được thống nhất; không tự tạo bằng chứng.

### 8.2. Retry và tính idempotent

Tính idempotent có nghĩa việc gửi lại một yêu cầu tương đương không tạo thêm tác dụng ngoài điều đã được quy định cho yêu cầu đó.

Trong onboarding, cần thử các tình huống:

- Gửi lại cùng mã yêu cầu khi lần trước đang chạy.
- Gửi lại sau khi đã thành công nhưng client không nhận được phản hồi.
- Gửi lại sau một lỗi đã xác định chưa thay đổi máy đích.
- Gửi yêu cầu mới cho một tài khoản đã được quản lý.
- Gửi lại với cùng mã nhưng nội dung quan trọng đã khác.

Không bắt buộc mọi hệ thống đều trả cùng một mã phản hồi. Điều cần chứng minh là không tạo tài khoản trùng, không nhân đôi quyền và không thực hiện đổi credential ngoài ý muốn.

Nếu sản phẩm có idempotency key, kiểm tra phạm vi và thời gian hiệu lực của khóa theo hợp đồng thực tế. Không giả định dùng cùng khóa mãi mãi sẽ được chống lặp.

### 8.3. Hai yêu cầu đồng thời

Cho hai danh tính thử nghiệm gửi yêu cầu onboard cùng A5 trong một khoảng thời gian gần nhau.

Kết quả phù hợp có thể là một yêu cầu thành công, yêu cầu còn lại nhận trạng thái đã tồn tại hoặc đang xử lý. Một thiết kế khác có thể hợp nhất yêu cầu. Dù theo cách nào, cần bảo đảm:

- Chỉ có một mapping quản lý có hiệu lực cho cùng đối tượng theo thiết kế.
- Không trộn credential hoặc policy từ hai yêu cầu.
- Chủ sở hữu và phê duyệt không bị ghi đè âm thầm.
- Có thể giải thích yêu cầu nào tạo tác dụng thực tế.
- Retry sau đó không tạo trạng thái mâu thuẫn.

Nếu hệ thống cho phép nhiều bản ghi đại diện cùng một tài khoản vì một lý do kiến trúc, ca kiểm thử phải xác minh cơ chế điều phối credential giữa các bản ghi đó. Không coi nhiều bản ghi là lỗi chỉ dựa vào số lượng, cũng không bỏ qua nguy cơ hai tác nhân tự luân chuyển cùng credential.

## 9. Kiểm thử tài khoản dịch vụ khi onboarding

Tài khoản dịch vụ cần thêm kiểm tra vì nó có thể đang được ứng dụng sử dụng liên tục.

Với A3, trước hết lập danh sách phụ thuộc được biết: dịch vụ, lịch chạy, connection pool hoặc cấu hình sử dụng credential. Discovery có thể hỗ trợ nhưng không thay thế xác nhận của chủ ứng dụng.

Nếu onboarding không đổi credential, kiểm tra:

- Dịch vụ vẫn hoạt động.
- PAM xác minh credential đúng đối tượng.
- Lịch rotation hoặc cơ chế cấp credential động không được kích hoạt ngoài phạm vi đã duyệt.
- Các quyền mới trong vault không làm lộ credential cho nhóm không liên quan.

Nếu onboarding bao gồm đổi credential, kiểm tra cả quá trình chuyển tiếp:

1. Ghi nhận dịch vụ và giao dịch lab đang hoạt động trước thay đổi.
2. Thực hiện onboarding trong cửa sổ thử nghiệm đã thống nhất.
3. Xác nhận credential được thay đổi trên đúng tài khoản.
4. Xác nhận các phụ thuộc trong phạm vi nhận được phiên bản có hiệu lực.
5. Buộc tạo một kết nối hoặc lần xác thực mới bằng phương pháp an toàn của ứng dụng lab.
6. Chạy giao dịch xác minh, kiểm tra lỗi xác thực và trạng thái dịch vụ.
7. Xác nhận cách xử lý các phụ thuộc chưa cập nhật hoặc đang ngoại tuyến.

Không dùng việc tiến trình còn sống làm bằng chứng duy nhất. Một connection pool còn giữ kết nối cũ có thể che giấu lỗi credential cho đến lần tái kết nối.

Cũng không mặc định một lỗi ở phụ thuộc có nghĩa phải đổi credential trở lại ngay. Quyết định phục hồi phải xét phiên bản hiện tại trên đích, trạng thái từng phụ thuộc và khả năng đồng bộ lại. Đổi qua lại không kiểm soát có thể làm tình hình khó xác định hơn.

## 10. Kiểm tra đường truy cập sau onboarding

Onboarding tạo một đường truy cập được quản lý, nhưng không tự chứng minh mọi đường khác đã được kiểm soát.

Cần đối chiếu với mục tiêu triển khai. Nếu yêu cầu chỉ là đưa credential vào vault, không được tuyên bố đã loại bỏ mọi truy cập trực tiếp. Nếu yêu cầu bắt buộc đi qua broker, phải có bằng chứng các đường trực tiếp thuộc phạm vi đã bị hạn chế theo thiết kế.

Các kiểm tra có thể bao gồm:

- Credential cũ còn hiệu lực hay không, nếu đã có bước thay đổi credential.
- Khóa công khai hoặc phương thức xác thực khác có còn tạo đường truy cập ngoài chính sách không.
- Nhóm quản trị hiện hữu có được xử lý đúng yêu cầu hay không.
- Người dùng có thể sử dụng credential đã cache sau khi quyền PAM hết hạn hay không.
- Phiên đã mở trước onboarding được xử lý theo chính sách nào.

Việc đổi mật khẩu không nhất thiết kết thúc một phiên đang mở, thu hồi mọi token hoặc xóa một SSH key độc lập. Do đó, cần tách “đã đổi credential” khỏi “đã thu hồi mọi phương thức truy cập”.

Trong ca kiểm thử onboarding, chỉ kiểm tra và thay đổi những đường truy cập thuộc yêu cầu đã duyệt. Các đường khác được phát hiện phải được ghi thành phát hiện hoặc hạng mục xử lý, không tự ý xóa khóa hay đóng phiên của người dùng.

## 11. Thu thập bằng chứng mà không làm lộ bí mật

### 11.1. Liên kết yêu cầu với tác dụng thực tế

Một bộ bằng chứng tốt phải nối được yêu cầu, hành động trong PAM và quan sát tại đích.

Ví dụ dòng thời gian minh họa:

```text
09:00:00Z  REQ-LAB-001 được gửi cho ASSET-LAB-A / ACCOUNT-LAB-A1
09:00:04Z  Chính sách POLICY-LAB-07 được phê duyệt
09:00:08Z  PAM ghi nhận mapping đối tượng
09:00:12Z  Kiểm tra credential hoàn tất
09:00:18Z  Người vận hành được phép mở phiên thử
09:00:22Z  Máy đích xác nhận danh tính hiệu lực
09:00:30Z  Người không có quyền bị từ chối mở phiên
09:00:40Z  Ca kiểm thử kết thúc
```

Các mốc trên chỉ minh họa. Khi thực hiện cần dùng timestamp thực, thống nhất múi giờ và ghi nhận độ lệch đồng hồ nếu có.

Nếu cùng một mã correlation không đi xuyên suốt các hệ thống, dùng bảng ánh xạ giữa mã yêu cầu PAM, mã công việc connector, mã phiên và bằng chứng phía đích. Không nối sự kiện chỉ bằng việc chúng xảy ra gần nhau khi có nhiều yêu cầu đồng thời.

### 11.2. Nội dung bằng chứng cần giữ

Thông thường cần giữ:

- Mã ca kiểm thử, người thực hiện, thời điểm và phiên bản môi trường.
- Mã đối tượng và yêu cầu thay đổi.
- Phiên bản policy, kết quả phê duyệt và vai trò được sử dụng.
- Kết quả xác minh credential theo cơ chế được phép.
- Kết quả truy cập được cho phép và bị từ chối.
- So sánh quyền trên đích trước/sau.
- Audit event, mã lỗi và bằng chứng phụ thuộc khi có.
- Kết quả phục hồi, trạng thái cuối và các tiêu chí chưa kiểm tra.

Không đưa mật khẩu, private key, token, cookie phiên hoặc nội dung clipboard chứa bí mật vào báo cáo. Nếu log vô tình chứa bí mật, xử lý theo quy trình bảo vệ dữ liệu và thay credential khi cần; không chỉ che giá trị trên ảnh chụp rồi bỏ qua bản log gốc.

Kho bằng chứng phải có quyền đọc và thời hạn lưu phù hợp. Screenshot hữu ích để minh họa, nhưng nên kết hợp với bản ghi có cấu trúc hoặc audit có thể đối chiếu.

## 12. Rollback và tiêu chí dừng

### 12.1. Rollback không đơn giản là xóa bản ghi PAM

Nếu onboarding chưa đổi gì trên đích, rollback có thể chủ yếu là gỡ quyền tạm và xử lý đối tượng chưa hoàn tất.

Nếu đã đổi credential, xóa bản ghi trong vault trước khi phục hồi có thể làm mất phương tiện quản trị. Nếu đã cập nhật một số phụ thuộc, quay lại credential cũ trên đích có thể khiến các phụ thuộc đã cập nhật bị lỗi.

Vì vậy, rollback phải dựa trên trạng thái thực tế:

1. Dừng các tác nhân tự động có thể tiếp tục thay đổi cùng đối tượng theo quy trình được phép.
2. Xác định thao tác nào đã hoàn tất trên PAM, đích và phụ thuộc.
3. Dùng đường phục hồi được ủy quyền để khôi phục trạng thái credential nhất quán.
4. Kiểm tra khả năng quản trị và giao dịch ứng dụng cần thiết.
5. Thu hồi quyền tạm, xử lý bản ghi dư và giữ bằng chứng theo chính sách.
6. Xác nhận trạng thái cuối với người chịu trách nhiệm tài nguyên.

Không khôi phục mật khẩu cũ chỉ vì thuận tiện nếu chính sách không cho phép tái sử dụng hoặc mật khẩu đó có nguy cơ đã lộ. Một credential mới, được đồng bộ đúng, có thể là phương án phục hồi phù hợp hơn.

Việc gỡ đối tượng khỏi PAM cũng không mặc nhiên cho phép xóa tài khoản thật trên máy đích. Tài khoản, bản ghi quản lý và lịch sử audit là các đối tượng có vòng đời khác nhau.

### 12.2. Điều kiện dừng ngay một ca kiểm thử

Đặt trước các điều kiện dừng, chẳng hạn:

- Phát hiện đang thao tác nhầm tài nguyên hoặc nhầm môi trường.
- Quyền trên đích tăng ngoài yêu cầu.
- Credential bị lộ vào log hoặc công cụ thu thập.
- Mất khả năng quản trị hoặc dịch vụ lab bị gián đoạn quá ngưỡng đã thống nhất.
- Không xác định được credential có hiệu lực sau lỗi từng phần.
- Có tác nhân khác đang quản lý cùng tài khoản và gây xung đột.

Khi dừng, giữ trạng thái và bằng chứng cần thiết cho điều tra. Không lặp lại thao tác đổi credential để “thử đến khi được”.

## 13. Đánh giá kết quả và xử lý lỗi thường gặp

| Hiện tượng | Khả năng cần kiểm tra | Hướng xác minh |
| --- | --- | --- |
| UI báo thành công nhưng kết nối thất bại | Sai mapping, credential không hợp lệ, policy hoặc kết nối chưa sẵn sàng | Đối chiếu định danh, kết quả xác minh credential và audit phía đích |
| Người ngoài nhóm vẫn mở được phiên | Quyền kế thừa hoặc policy gán sai | Kiểm tra quyền hiệu lực và nguồn cấp quyền |
| Chỉ lỗi trên máy có cùng tên tài khoản | Nhận diện đối tượng thiếu phạm vi | So sánh tài nguyên, account reference và scope danh tính |
| Dịch vụ vẫn chạy nhưng lần kết nối mới lỗi | Pool hoặc phiên cũ che lỗi credential | Tạo xác thực mới có kiểm soát và kiểm tra giao dịch |
| Retry tạo nhiều bản ghi | Thiếu kiểm soát duplicate hoặc yêu cầu không có định danh ổn định | Đối chiếu mã yêu cầu và mapping cuối |
| Timeout sau đổi credential | Kết quả thực thi chưa xác định | Xác minh trạng thái đích và vault trước khi quyết định retry |
| Onboarding làm tài khoản bị khóa | Kiểm tra credential sai lặp lại | Dừng retry, đối chiếu số lần thử và chính sách khóa |
| Audit không nối được các bước | Thiếu correlation, lệch thời gian hoặc thiếu nguồn log | Đối chiếu mã công việc, mã phiên và độ lệch đồng hồ |

Bảng này là hướng điều tra, không phải kết luận nguyên nhân. Mỗi lỗi cần bằng chứng trước khi thay đổi cấu hình.

Có thể dùng bốn kết quả cho từng ca:

- **PASS:** mọi tiêu chí bắt buộc trong phạm vi đã đạt và có bằng chứng.
- **FAIL:** có quan sát chứng minh một tiêu chí không đạt.
- **BLOCKED:** không thể thực hiện hoặc không thể quan sát đủ vì thiếu điều kiện.
- **NOT RUN:** chưa thực hiện.

Kết quả tổng không được là PASS nếu các ca bắt buộc còn FAIL, BLOCKED hoặc NOT RUN. Các tiêu chí không áp dụng phải có giải thích và được xác định theo phạm vi, không dùng để bỏ qua lỗi.

## 14. Bài thực hành tổng hợp

Tình huống: nhóm vận hành muốn đưa hai tài khoản quản trị cục bộ có cùng tên trên hai máy lab và một tài khoản dịch vụ vào PAM. Người vận hành được mở phiên theo phê duyệt nhưng không được xem mật khẩu. Tài khoản dịch vụ có một ứng dụng lab cần được xác thực lại sau thay đổi credential.

Thực hiện theo trình tự:

1. Lập danh sách ba đối tượng với định danh tài nguyên, account reference và chủ sở hữu.
2. Ghi baseline quyền, trạng thái tài khoản, đường truy cập và phụ thuộc.
3. Chốt phạm vi: tài khoản nào đổi credential lần đầu, tài khoản nào chỉ nạp và xác minh.
4. Viết ca luồng chuẩn cho từng loại tài khoản.
5. Viết ca từ chối cho người không có quyền và ca cấm xem credential đối với người chỉ có quyền mở phiên.
6. Viết ca phân biệt hai tài khoản cùng tên.
7. Kiểm tra gửi lại một yêu cầu thành công và gửi đồng thời hai yêu cầu cho cùng đối tượng.
8. Mô phỏng một lỗi từng phần phù hợp khả năng lab; ghi rõ trạng thái quan sát được.
9. Kiểm tra giao dịch ứng dụng bằng một lần xác thực mới có kiểm soát.
10. Thực hiện phục hồi nếu ca thử yêu cầu, xác minh trạng thái cuối và thu hồi quyền tạm.
11. Tổng hợp kết quả cùng bằng chứng, phát hiện và phần chưa kiểm tra.

Báo cáo cuối cần trả lời được: đối tượng nào thực sự đã được quản lý, ai sử dụng được, credential nào đang có hiệu lực theo mã phiên bản, phụ thuộc nào đã xác minh và có đường truy cập nào chưa nằm trong phạm vi kiểm soát.

Không ghi giá trị credential trong câu trả lời. Nếu không thể xác định một điều bằng chứng, báo rõ điểm đó thay vì suy từ thông báo trên giao diện.

## 15. Điểm cần ghi nhớ

Test onboarding PAM phải kiểm chứng cả tính đúng của đối tượng, tính đúng của quyền và khả năng vận hành sau khi tiếp nhận. Vault có bản ghi, connector kết nối được và ứng dụng vẫn chạy là ba quan sát khác nhau; không quan sát nào tự thay thế toàn bộ tiêu chí nghiệm thu.

Một bộ kiểm thử hiệu quả bao gồm luồng thành công, luồng bị từ chối, tài khoản trùng tên, retry, lỗi từng phần và ảnh hưởng đến phụ thuộc. Kết quả cần được đối chiếu với chính sách đã chốt, có bằng chứng phía PAM lẫn phía đích khi phù hợp, và có phương án phục hồi dựa trên trạng thái thực tế.

# Router administrator

## Mục tiêu bài học

Trong chương Network PAM của module Privileged Access Management (PAM), **router administrator** là danh tính được phép thực hiện những thao tác quản trị trên router: thay đổi cấu hình, điều khiển đường quản trị, xử lý định tuyến hoặc quản lý các thành phần ảnh hưởng tới mạng.

Quyền này có thể tác động tới nhiều hệ thống phía sau router. Một thay đổi nhỏ ở route, ACL hoặc cấu hình quản trị có thể làm mất kết nối, mở đường truy cập ngoài ý định hoặc cắt chính đường dùng để khôi phục thiết bị.

Bài học tập trung vào kiểm soát quyền đặc biệt, không thay thế tài liệu cấu hình của từng nền tảng. Tên role, policy và mã giả là mô hình thiết kế. Những ví dụ liên quan Cisco IOS hoặc IOS XE chỉ minh họa cho nền tảng được nêu, không phải cú pháp chung cho mọi router.

Sau bài học, bạn có thể:

- Xác định những đường quản trị cần đưa vào phạm vi PAM.
- Phân biệt authentication, authorization và accounting.
- Thiết kế quyền theo nhiệm vụ thay vì cấp quản trị rộng cho mọi người.
- Áp dụng JIT, JEA, vault và kiểm soát phiên.
- Thực hiện thay đổi có phê duyệt, phương án phục hồi và xác minh độc lập.
- Liên kết bằng chứng người dùng, phiên, lệnh và trạng thái cấu hình thực tế.

## 1. Vì sao quyền quản trị router có phạm vi ảnh hưởng lớn?

Router không chỉ là một máy chủ để đăng nhập. Nó tham gia chuyển tiếp lưu lượng, duy trì trạng thái điều khiển và cung cấp các giao diện quản trị.

Có thể phân tích ba mặt phẳng:

| Mặt phẳng | Vai trò khái niệm | Rủi ro khi bị tác động sai |
|---|---|---|
| Data plane | Chuyển tiếp lưu lượng theo trạng thái được thiết lập | Mất kết nối, đi sai đường hoặc bị ảnh hưởng phạm vi dịch vụ |
| Control plane | Duy trì thông tin điều khiển như định tuyến | Thay đổi đường đi hoặc làm mất ổn định mạng |
| Management plane | Cấu hình, giám sát và điều khiển thiết bị | Mở quyền quản trị, tắt bằng chứng hoặc tự khóa đường phục hồi |

Một principal được sửa cấu hình router có thể tác động sang cả ba. Vì vậy, chỉ bảo vệ mật khẩu đăng nhập là chưa đủ.

### Một thay đổi có thể vượt phạm vi một thiết bị

Ví dụ, một kỹ sư sửa policy định tuyến để xử lý sự cố của một dịch vụ. Nếu policy áp dụng rộng hơn dự kiến, tác động có thể lan tới nhiều mạng hoặc site.

Thiết kế PAM cần biết:

- Người dùng được thao tác trên thiết bị nào.
- Được sửa thành phần nào của cấu hình.
- Nhiệm vụ ảnh hưởng những dịch vụ và phụ thuộc nào.
- Có thể mở thêm quyền hoặc thay đổi bằng chứng hay không.
- Khi mất đường quản trị, ai và bằng cách nào có thể phục hồi.

Không đánh giá mức rủi ro chỉ bằng số lệnh trong một ticket.

## 2. Kiểm kê mọi đường quản trị

Một router có thể có nhiều giao diện quản trị. Chỉ đưa SSH qua bastion vào PAM trong khi một API hoặc console vẫn có quyền rộng sẽ tạo đường ngoài kiểm soát.

| Đường truy cập | Điều cần xác định |
|---|---|
| CLI qua SSH | Danh tính, xác minh thiết bị, quyền lệnh và phiên |
| Giao diện web | Xác thực, role, session, certificate và khả năng ghi bằng chứng |
| API quản trị | Token, phạm vi thao tác, thời hạn và log |
| NETCONF hoặc giao thức cấu hình khác | Danh tính, quyền dữ liệu cấu hình và khả năng giao dịch |
| SNMP | Mức bảo vệ, quyền đọc/ghi và phạm vi đối tượng |
| Console trực tiếp | Người được tiếp cận, cách xác thực và bằng chứng |
| Console server hoặc đường out-of-band | Quyền trên cả thiết bị trung gian và router |
| Công cụ tự động hóa | Danh tính workload, nguồn artifact và phạm vi thiết bị |
| Đường hỗ trợ của nhà cung cấp | Người dùng, thời hạn, giám sát và điều kiện kết thúc |

SNMPv3 có mô hình bảo mật với các mức khác nhau; việc chỉ nhìn số phiên bản không đủ kết luận một luồng quản trị đã có cả xác thực và bảo mật nội dung. [RFC 3414: SNMPv3 USM](https://www.rfc-editor.org/info/rfc3414/)

### Danh mục thiết bị

Một bản ghi quản trị nên có:

```text
device_id
platform_and_version
site_and_environment
owner_team
management_endpoints
trusted_host_identity
aaa_profile
supported_admin_interfaces
permission_profiles
credential_references
out_of_band_reference
evidence_sources
recovery_runbook
```

Không lưu password, shared secret hoặc private key trong danh mục. Dùng tham chiếu tới kho được bảo vệ.

Địa chỉ IP hoặc hostname không nên là bằng chứng danh tính duy nhất. Cần cơ chế xác minh thiết bị phù hợp với giao thức và nguồn đăng ký tin cậy.

### Out-of-band cũng là một hệ thống đặc quyền

Một console server có thể mở quyền tới nhiều thiết bị. Nếu nó bị chiếm quyền, phạm vi ảnh hưởng có thể vượt một router.

Cần quản lý quyền đăng nhập console server, quyền chọn cổng, credential dự phòng và ghi nhận phiên. Đừng coi một đường nằm ngoài mạng dữ liệu là tự động an toàn.

## 3. Tách vai trò theo nhiệm vụ

Không phải ai làm việc với router cũng cần quyền quản trị toàn bộ.

| Vai trò minh họa | Khả năng cần thiết | Quyền không nên mặc nhiên có |
|---|---|---|
| Người quan sát | Xem trạng thái phù hợp để chẩn đoán | Đọc secret, thay cấu hình hoặc xóa log |
| Người vận hành dịch vụ | Chạy một tập thao tác đã định | Sửa AAA, mở tài khoản hoặc thay toàn bộ định tuyến |
| Người thay đổi cấu hình | Sửa đúng phần cấu hình trong kế hoạch | Sửa cơ chế kiểm soát quyền nếu nhiệm vụ không cần |
| Người quản trị AAA | Quản lý policy truy cập theo quy trình | Tự phê duyệt mọi thay đổi mạng |
| Kiểm toán viên | Đọc bằng chứng và đối soát | Thay quyền hoặc sửa bằng chứng |
| Danh tính tự động hóa | Thực thi artifact theo phạm vi thiết bị | Mở shell tự do hoặc chọn mọi target |
| Người ứng cứu khẩn cấp | Khôi phục theo tình huống được thiết kế | Trở thành tài khoản dùng chung thường trực |

Các role là yêu cầu thiết kế. Mức độ phân tách thực tế phụ thuộc khả năng thiết bị, AAA và công cụ trung gian.

### “Chỉ đọc” vẫn cần kiểm soát nội dung

Một lệnh xem cấu hình có thể hiển thị thông tin nhạy cảm, topology hoặc giá trị phục vụ xác thực. Không coi mọi lệnh bắt đầu bằng show là vô hại.

Cần phân loại đầu ra và chỉ cung cấp những gì nhiệm vụ cần. Nếu phải lấy cấu hình đầy đủ để điều tra, bảo vệ bản chụp như dữ liệu nhạy cảm.

### Cấp quyền theo hành động và ngữ cảnh

Một yêu cầu nên cụ thể hơn “admin router”:

```text
Chủ thể: người vận hành được xác thực
Thiết bị: router được đăng ký
Nhiệm vụ: thay policy đã được duyệt
Phạm vi: đúng đối tượng cấu hình và giá trị được phép
Thời hạn: cửa sổ thay đổi
Đường truy cập: giao diện được kiểm soát
Bằng chứng: phiên, lệnh hoặc API và trạng thái trước/sau
```

Nếu thiết bị chỉ cung cấp quyền rộng, phải ghi nhận giới hạn đó và đánh giá cách broker, runbook hoặc kiểm soát bổ sung giới hạn công việc. Không đặt tên role “limited” rồi suy luận nó thực sự hẹp.

## 4. AAA: ba quyết định khác nhau

AAA gồm:

- **Authentication:** chủ thể là ai.
- **Authorization:** chủ thể được làm gì.
- **Accounting:** hoạt động được ghi nhận thế nào.

TACACS+ cung cấp các thành phần authentication, authorization và accounting tách biệt. Việc bật một phần không mặc nhiên cấu hình đầy đủ hai phần còn lại. [Cisco IOS XE: Configuring TACACS](https://www.cisco.com/c/en/us/td/docs/routers/ios/config/17-x/sec-vpn/b-security-vpn/m_sec-cfg-tacacs-0.html)

### Đăng nhập thành công không đủ chứng minh phân quyền đúng

Một hệ thống có thể xác thực tập trung nhưng sau đó đưa mọi người vào mức quyền quá rộng. Cũng có thể CLI được kiểm soát nhưng API dùng một role khác không chịu cùng giới hạn.

Cần kiểm chứng:

1. Ai được tạo phiên.
2. Role hoặc mức quyền được gán.
3. Những lệnh hoặc thao tác bị cho phép và bị từ chối.
4. Những giao diện khác có cùng ranh giới không.
5. Hành vi khi AAA hoặc đường bằng chứng gặp lỗi.

### Command authorization

Trên Cisco IOS XE, command authorization qua TACACS+ có thể đưa lệnh của người quản trị tới AAA để quyết định cho phép hoặc từ chối theo cấu hình. [Cisco IOS XE: Hardening Guide](https://sec.cloudapps.cisco.com/security/center/resources/IOS_XE_hardening)

Đây là một cơ chế hữu ích, nhưng không nên coi nó là lời bảo đảm chung cho mọi lệnh, mode, API và phiên bản. Thiết kế cần kiểm thử đúng phạm vi hỗ trợ và cấu hình đang dùng.

Nếu chỉ kiểm tra đăng nhập rồi không kiểm tra các hành động nhạy cảm, việc thu hẹp cửa sổ đăng nhập không giới hạn đầy đủ công việc trong phiên.

### Bảo vệ luồng AAA

TACACS+ truyền thống mô tả cơ chế obfuscation không đạt mức mã hóa hiện đại. Cần bảo vệ đường truyền và kiểm tra cơ chế transport được hai đầu hỗ trợ. [RFC 8907: TACACS+ Security](https://www.rfc-editor.org/info/rfc8907/)

Không kết luận “dùng TACACS+ nên mọi dữ liệu quản trị đã được bảo vệ đầy đủ”. Cần đánh giá xác thực peer, transport, secret liên kết và ranh giới mạng thực tế.

## 5. PAM nằm ở đâu trong đường quản trị?

Một kiến trúc có thể là:

```text
Người dùng có danh tính riêng
       |
       | xác thực và điều kiện truy cập
       v
PAM: eligibility, yêu cầu, phê duyệt
       |
       | phiên hoặc thao tác trong phạm vi được duyệt
       v
Broker / bastion / runner
       |
       | giao thức quản trị được bảo vệ
       v
Router
       |
       +--> AAA: quyết định quyền
       |
       +--> Nguồn bằng chứng độc lập
```

Đây là mô hình, không yêu cầu mọi triển khai có cùng thành phần.

### Duy trì khả năng quy trách nhiệm

Tốt nhất, thiết bị và AAA có thể phân biệt từng danh tính. Nếu một tích hợp bắt buộc dùng danh tính kỹ thuật chung ở router, PAM phải liên kết được người dùng gốc, phiên và thao tác thực tế.

Một username chung xuất hiện trong log router không tự cho biết ai là người yêu cầu. Cũng không nên phát credential chung cho người dùng rồi kỳ vọng mọi truy cập đều đi qua broker.

### Xác minh đúng router

Với SSH, cần quy trình tin cậy host key phù hợp. Với API bảo vệ bằng TLS, cần kiểm tra certificate và đích theo cấu hình tin cậy.

Không tự động chấp nhận một thay đổi danh tính thiết bị chỉ vì hostname vẫn giống. Router có thể được thay phần cứng hoặc thay khóa hợp lệ, nhưng quá trình cập nhật trust phải được quản lý riêng.

### Kiểm soát đường truy cập trực tiếp

Nếu người dùng còn có thể kết nối thẳng bằng credential lấy từ vault, session recording của broker không bao phủ đường đó.

Cần xác định những đường trực tiếp được phép, chủ thể sử dụng và bằng chứng tương ứng. Mục tiêu là không có đường đặc quyền ngoài ý định, không phải chỉ thêm một công cụ vào sơ đồ.

## 6. JIT và JEA cho router administrator

### JIT giới hạn thời điểm

Một quyền JIT có thể gắn với:

- Danh tính người hoặc job.
- Device ID và giao diện quản trị.
- Role hoặc gói thao tác.
- Ticket và kế hoạch bất biến.
- Thời điểm bắt đầu và deadline.
- Điều kiện xác thực tăng cường.
- Người phê duyệt và chủ hệ thống.
- Cách kết thúc phiên và xác minh.

Kiểm tra thời hạn khi bắt đầu phiên là chưa đủ nếu phiên có thể tiếp tục vô thời hạn. Cần xác định deadline áp dụng với việc tạo phiên, từng thao tác hay toàn bộ thời gian phiên tồn tại.

### JEA giới hạn công việc

Một runbook có thể chỉ cho phép sửa đúng một đối tượng policy với giá trị đã duyệt. Người dùng không nhận một CLI tùy ý.

Giới hạn phải bao gồm tham số, artifact, target và danh tính thực thi. Nếu người dùng có thể chèn một đoạn cấu hình tùy ý hoặc sửa runbook, giao diện hẹp không còn tạo giới hạn thực tế.

### Không chỉ kiểm tra chuỗi đầu lệnh

Một quy tắc cho phép theo tiền tố hoặc biểu thức đơn giản có thể hiểu sai mode cấu hình, đối tượng đích hoặc các biến thể cú pháp.

Cần dựa vào khả năng phân quyền của nền tảng và kiểm thử các trường hợp có ý nghĩa. Với automation, ưu tiên một mô hình dữ liệu hoặc kế hoạch thay đổi có cấu trúc khi phù hợp.

Không suy luận rằng một ACL trên đường SSH đã thực thi quyền cho một API quản trị khác.

### Hết hạn quyền khác hoàn tác cấu hình

Một route hoặc policy được áp dụng hợp lệ có thể cần tiếp tục tồn tại sau cửa sổ JIT. Việc kết thúc quyền không nên tự động xóa thay đổi nghiệp vụ nếu kế hoạch không yêu cầu.

Ngược lại, tài nguyên hoặc cấu hình tạm phục vụ một sự cố cần một bước dọn riêng. Phải xác định rõ điều gì hết hạn:

```text
Khả năng tạo phiên mới
Quyền thao tác trong phiên
Phiên đang tồn tại
Cấu hình tạm
Thay đổi nghiệp vụ được giữ lại
```

## 7. Credential và secret cần quản lý riêng

Một router có thể liên quan nhiều loại secret:

| Loại | Mục đích |
|---|---|
| Credential cá nhân hoặc liên kết danh tính | Xác thực người quản trị |
| Credential kỹ thuật cho automation | Cho phép runner hoặc broker truy cập |
| Tài khoản local dự phòng | Phục hồi khi đường trung tâm không sử dụng được |
| Secret tăng quyền theo cơ chế thiết bị | Mở một mức thao tác đặc biệt nếu nền tảng có |
| Shared secret với AAA | Liên kết thiết bị với dịch vụ AAA theo cơ chế hỗ trợ |
| Secret hoặc khóa cho SNMP/API | Xác thực hoặc bảo vệ kênh quản trị tương ứng |
| Credential của console server | Mở đường out-of-band |

Không gộp chúng vào một “mật khẩu router” duy nhất.

### Rotation cần biết bên nào sử dụng

Thay credential local không tự thay shared secret của AAA. Thay secret ở server AAA mà router chưa cập nhật có thể làm hỏng đường xác thực hoặc bằng chứng.

Quy trình phải có thứ tự, test kết nối mới và đường khôi phục. Không xác nhận rotation chỉ từ một phiên đã tồn tại trước khi thay đổi.

### Cấu hình và backup có thể chứa dữ liệu xác thực

Bản chụp cấu hình, transcript và file hỗ trợ cần quyền đọc, nơi lưu và thời hạn phù hợp. Không đính kèm cấu hình đầy đủ vào ticket công khai nội bộ chỉ để chứng minh đã làm việc.

Một giá trị được hiển thị ở dạng che giấu hoặc biến đổi không nên tự động được coi là không nhạy cảm. Phải đánh giá theo khả năng thực tế và nền tảng.

### Tài khoản dự phòng phải có vòng đời

Tài khoản local khẩn cấp cần chủ sở hữu, nơi giữ secret, quyền lấy, cơ chế theo dõi và diễn tập. Sau khi sử dụng, xử lý credential và phiên theo quy trình.

Không để tài khoản dự phòng trở thành đường vận hành thường xuyên tránh phê duyệt.

## 8. Thực hiện thay đổi mà không tự khóa đường quản trị

Một kế hoạch thay đổi router cần có cả mục tiêu nghiệp vụ và khả năng phục hồi.

### Trước thay đổi

Xác định:

- Device ID, nền tảng và phiên bản.
- Baseline cấu hình được quan sát.
- Đối tượng cấu hình sẽ sửa và các giá trị được phép.
- Tác động dự kiến tới quản trị, AAA, logging và lưu lượng.
- Đường out-of-band có thực sự sử dụng được không.
- Phương án quay lại và điều kiện kích hoạt.
- Người có thẩm quyền xác nhận kết quả.
- Cách xử lý nếu lệnh timeout hoặc mất phiên.

Một dòng “có console dự phòng” trong danh mục không chứng minh console hoạt động. Cần kiểm thử theo mức rủi ro và chính sách của tổ chức.

### Bảo vệ baseline

Nếu cấu hình đã đổi sau khi kế hoạch được duyệt, một patch hoặc script dựa trên baseline cũ có thể tác động sai.

Runner nên so sánh trạng thái cần thiết hoặc revision phù hợp trước khi áp dụng. Không chỉ kiểm tra hostname.

Nếu dùng bản chụp cấu hình, giữ bản gốc tại nơi được bảo vệ. Bản diff dùng để phê duyệt cần che secret nhưng vẫn đủ thông tin đánh giá tác động. Không biến việc che dữ liệu thành lý do bỏ qua một thay đổi quyền quan trọng.

### Trong thay đổi

Giới hạn tác vụ theo kế hoạch. Khi phát hiện khác biệt ngoài dự kiến, dừng hoặc đi theo nhánh ngoại lệ đã được xác định, thay vì mở rộng quyền ngay trong phiên.

Một lệnh trả về thành công chỉ chứng minh một phần xử lý của thiết bị. Cần đọc lại trạng thái và kiểm tra tác động thực tế theo đúng phạm vi.

### Sau thay đổi

Phân biệt ít nhất:

1. Thiết bị đã nhận cấu hình.
2. Cấu hình hoạt động khớp ý định.
3. Trạng thái vận hành liên quan đạt yêu cầu.
4. Đường quản trị và bằng chứng vẫn sử dụng được.
5. Cấu hình được lưu bền theo kế hoạch nếu nền tảng yêu cầu.
6. Quyền và phiên được kết thúc đúng cách.

Không đóng ticket chỉ vì prompt đã quay lại.

## 9. Candidate, commit và rollback không giống nhau trên mọi router

Một số nền tảng cung cấp candidate configuration, commit hoặc cơ chế xác nhận thay đổi. Nền tảng khác có thể áp dụng cấu hình theo cách khác.

NETCONF định nghĩa các capability, trong đó có candidate và confirmed commit. Khi capability tương ứng được hỗ trợ, confirmed commit có thể quay lại cấu hình nếu không được xác nhận theo điều kiện quy định. [RFC 6241: NETCONF](https://www.rfc-editor.org/info/rfc6241/)

Thiết kế phải kiểm tra capability và ngữ nghĩa thật của thiết bị, không suy luận từ việc có một endpoint NETCONF.

### Kế hoạch kiểm chứng

Một luồng khái niệm:

```text
Đọc baseline
    --> chuẩn bị thay đổi
    --> kiểm tra hợp lệ
    --> áp dụng bằng cơ chế phù hợp
    --> xác minh độc lập
    --> xác nhận / lưu theo kế hoạch
    --> đọc lại trạng thái cuối
```

Các bước không tự tạo một giao dịch nguyên tử cho toàn mạng.

### Xác minh từ một đường độc lập

Nếu chỉ kiểm tra qua chính phiên vừa sửa đường quản trị, có thể không phát hiện một số tác động hoặc không còn khả năng xác nhận sau khi mất kết nối.

Kế hoạch có thể sử dụng một nguồn kiểm tra độc lập cho những điều kiện cần thiết, như khả năng tiếp cận quản trị hoặc trạng thái dịch vụ được phép quan sát. Không mở rộng phép thử ra ngoài phạm vi được giao.

### Xử lý thay đổi đồng thời

Một rollback diện rộng có thể hoàn tác cả thay đổi hợp lệ của người khác. Cần biết ownership, cửa sổ thay đổi và khả năng khóa hoặc điều phối mà nền tảng hỗ trợ.

Việc một controller giữ lock trong cơ sở dữ liệu của nó không tự ngăn người khác cấu hình trực tiếp router.

### Cấu hình đang chạy và cấu hình sau khởi động

Thiết bị có thể phân biệt trạng thái hoạt động với dữ liệu được dùng khi khởi động. NETCONF cũng có capability startup riêng. [RFC 6241: Configuration Datastores](https://www.rfc-editor.org/info/rfc6241/)

Do đó, kế hoạch cần nói rõ có lưu bền hay không và cách xác minh. Không cho rằng “commit thành công” trên mọi nền tảng đều có cùng ý nghĩa về khả năng tồn tại sau reboot.

Không dùng reboot thực tế trên production chỉ để chứng minh một thay đổi PAM đã lưu đúng, nếu điều đó không thuộc kế hoạch.

## 10. Luồng automation có kiểm soát

Một kế hoạch bất biến có thể được biểu diễn như sau:

```yaml
# Mô hình giảng dạy; không phải cấu hình chạy được của router hoặc PAM.
changeId: network-change-351
revision: 2
requester: engineer-18
executor: network-runner
target:
  deviceId: router-site-A
  expectedPlatformProfile: registered-router-profile
  managementInterface: approved-interface
task:
  profile: update-approved-route-policy
  objectRef: policy-for-service-A
  artifactRef: reviewed-artifact-revision
  baselineRef: approved-baseline-reference
constraints:
  allowUserAdministration: false
  allowAaaChanges: false
  allowLoggingChanges: false
  allowOtherDevices: false
validity:
  start: approved-start
  deadline: approved-deadline
recovery:
  runbookRef: verified-recovery-runbook
verification:
  planRef: approved-verification-plan
```

Những điều kiện trong mô hình chỉ có hiệu lực nếu được ánh xạ vào quyền và kiểm tra thực tế. Một trường allowAaaChanges=false không có tác dụng nếu runner vẫn nhận một script tùy ý có thể sửa AAA.

### Mã giả thực thi

```text
function executeApprovedRouterChange(session, changeId):
    actor = authenticate(session)
    plan = loadImmutableApprovedPlan(changeId)

    require actorMayRequest(actor, plan)
    require approvalValidForExactRevision(plan)
    require trustedNow() within plan.validity

    target = trustedDeviceInventory(plan.deviceId)
    require target.allowedFor(plan.executor, plan.taskProfile)

    connection = openVerifiedManagementConnection(target)
    require observedDeviceIdentity(connection) matches target.identity

    observed = readRequiredBaseline(connection)
    require baselineCompatible(observed, plan.baselineRef)

    operation = reserveExecutionIntent(plan.id, plan.revision, target.id)
    artifact = loadTrustedArtifact(plan.artifactRef)
    require artifactMatchesApprovedTask(artifact, plan)

    result = applyWithSupportedRecoveryMechanism(
        connection,
        artifact,
        operation,
        plan.recovery
    )

    evidence = runApprovedVerification(plan.verification, target, result)

    if evidence.satisfiesPlan:
        finalizeAccordingToPlatformAndPlan(connection, plan)
        verifyFinalState(connection, plan)
    else:
        enterApprovedRecoveryPath(operation, plan, evidence)

    recordMetadataAndProtectedEvidence(operation, evidence)
    endAccessAccordingToPolicy(operation)
```

Các hàm là trách nhiệm thiết kế. Chúng không bảo đảm mọi router cung cấp giao dịch, rollback hoặc identity check giống nhau.

### Timeout không đồng nghĩa chưa thay đổi

Một lệnh hoặc API có thể đã tác động cấu hình nhưng phản hồi bị mất. Không gửi lại một thay đổi không idempotent chỉ vì phía client timeout.

Cần đọc lại trạng thái, đối soát journal và quyết định bước tiếp theo. Nếu chưa biết kết quả, ghi trạng thái chưa xác định.

### Retry không được mở rộng phạm vi

Giữ change ID, revision, target và artifact ổn định. Một retry không được tự chọn thiết bị thay thế, tăng quyền hoặc dùng một credential rộng hơn nếu kế hoạch chưa cho phép.

Nếu deadline đã hết trong lúc tác vụ còn dang dở, phải có nhánh xử lý an toàn. Không tự gia hạn vô thời hạn chỉ vì job chưa kết thúc.

## 11. AAA gặp lỗi và đường break-glass

### Phân biệt từ chối với không thể xác thực

Trong cơ chế method list của Cisco IOS XE, phản hồi từ chối xác thực khác với lỗi hoặc không có phản hồi; việc chuyển sang phương thức tiếp theo phụ thuộc kết quả đó. [Cisco IOS XE: Configuring Authentication](https://www.cisco.com/c/en/us/td/docs/routers/ios-xe/security-vpn/security-vpn/m_sec-cfg-authentifcn-0.html)

Điểm cần kiểm thử:

```text
AAA hoạt động và từ chối người dùng
    khác
AAA không sử dụng được
```

Không thiết kế đường local như một cách tự động vượt qua mọi quyết định deny. Cũng không suy luận rằng xác thực fallback thành công sẽ bảo đảm authorization và accounting fallback đúng ý định.

### Break-glass cần được chuẩn bị trước

Một đường khẩn cấp nên xác định:

- Trường hợp được phép sử dụng.
- Người có quyền yêu cầu và lấy credential.
- Cách xác thực khi hệ thống trung tâm gặp sự cố.
- Thiết bị, giao diện và nhiệm vụ được phép.
- Bằng chứng dự phòng khi kênh chính không sẵn sàng.
- Cách kết thúc, rotation và đối soát sau khôi phục.

Nếu tất cả đường phục hồi phụ thuộc vào chính router hoặc AAA đang lỗi, cần điều chỉnh thiết kế trước sự cố.

### Không biến mất kết nối thành lý do mở mọi quyền

Khi một thay đổi làm mất đường quản trị, dùng runbook phục hồi đã định. Không tự tạo một tài khoản dùng chung không thời hạn hoặc tắt toàn bộ kiểm soát ở nhiều router để xử lý một thiết bị.

Quyền ứng cứu có thể rộng hơn nhiệm vụ thường ngày, nhưng vẫn cần phạm vi, trách nhiệm và bằng chứng phù hợp.

### Khi logging không sẵn sàng

Tổ chức cần quyết định trước loại thay đổi nào bị chặn và cơ chế khẩn cấp nào được dùng. Không lặng lẽ coi việc không có log là điều kiện bình thường.

Nếu phải dùng một nguồn bằng chứng dự phòng, bảo vệ nó và đối soát khi hệ thống chính trở lại. Không ghi credential vào transcript để thay thế bằng chứng xác thực.

### Phục hồi xong chưa phải kết thúc

Sau sự cố cần:

1. Kiểm tra tài khoản và đường local đã sử dụng.
2. Xử lý credential và phiên liên quan.
3. Đối soát mọi thay đổi cấu hình.
4. Khôi phục AAA và thu thập bằng chứng.
5. Xác minh không còn quyền khẩn cấp ngoài kế hoạch.
6. Ghi rõ phần chưa hoàn tất và người xử lý.

Một tài khoản break-glass tồn tại trong vault vẫn cần được rà soát, ngay cả khi nhiều tháng không sử dụng.

## 12. Bằng chứng từ phiên tới trạng thái mạng

Có ít nhất bốn lớp bằng chứng:

```text
Yêu cầu và approval
    --> đăng nhập / phiên
    --> lệnh hoặc API
    --> cấu hình và trạng thái được quan sát
```

Không dùng một lớp thay thế toàn bộ các lớp khác.

### Accounting và recording có vai trò khác nhau

Accounting có thể cung cấp sự kiện về phiên hoặc lệnh theo cấu hình. Recording có thể hỗ trợ xem lại tương tác. Cả hai đều cần được kiểm tra độ bao phủ.

Một transcript cho thấy người dùng gõ lệnh không tự chứng minh lệnh được chấp nhận hoặc trạng thái cuối đúng. Một bản diff cấu hình cũng không tự cho biết người nào đã thực hiện nếu thiếu liên kết danh tính.

### Thông tin nên liên kết

| Nhóm bằng chứng | Nội dung điển hình |
|---|---|
| Chủ thể | Danh tính gốc, danh tính tại router, executor |
| Thẩm quyền | Change ID, revision, người duyệt và phạm vi |
| Phiên | Session reference, giao diện, thời gian bắt đầu/kết thúc |
| Thiết bị | Device ID, identity đã xác minh, nền tảng |
| Thao tác | Lệnh hoặc API được phép ghi nhận, kết quả và mã lỗi |
| Cấu hình | Baseline, thay đổi thực tế và trạng thái cuối |
| Vận hành | Kết quả các phép kiểm tra đã được duyệt |
| Kết thúc | Chặn phiên mới, xử lý phiên cũ, thu hồi và ngoại lệ |

Cần có chiến lược liên kết giữa các nguồn, không mặc định mọi hệ thống có cùng một session ID.

### Bảo vệ nội dung nhạy cảm

Output cấu hình, support bundle và recording có thể chứa secret hoặc thông tin nội bộ. Cần:

- Quyền đọc và xuất dữ liệu.
- Phân loại và che dữ liệu phù hợp.
- Thời hạn lưu.
- Khả năng phát hiện xóa hoặc ngừng thu thập.
- Cách cung cấp bằng chứng cho kiểm toán mà không phát tán credential.

Không đặt toàn bộ khả năng xóa bằng chứng vào cùng principal đang được giám sát.

### Thời gian và khoảng trống bằng chứng

Các thiết bị và dịch vụ cần có nguồn thời gian phù hợp để đối soát. Nếu log đến trễ hoặc mất một đoạn, báo rõ giới hạn.

“Không tìm thấy sự kiện” có thể nghĩa là không có hoạt động, nhưng cũng có thể do log bị gián đoạn. Cần kiểm tra trạng thái thu thập trước khi kết luận.

## 13. Nhà cung cấp, người hỗ trợ và phiên từ xa

Một đối tác hỗ trợ có thể cần quyền chẩn đoán trong thời gian ngắn. Không nên cấp một tài khoản dùng chung lâu dài với cùng quyền của nhóm quản trị nội bộ.

Kế hoạch nên có:

- Danh tính được xác minh.
- Thiết bị và mục đích hỗ trợ.
- Người nội bộ chịu trách nhiệm.
- Role hoặc tập thao tác phù hợp.
- Thời hạn.
- Yêu cầu giám sát nếu cần.
- Giới hạn tải cấu hình hoặc support bundle ra ngoài.
- Kết thúc quyền và xử lý credential.

Không coi việc người hỗ trợ kết nối qua VPN là đã kiểm soát đầy đủ quyền router. VPN chỉ là một phần đường truy cập.

### Phân biệt quyền xem và quyền thay đổi

Một phiên hỗ trợ có thể bắt đầu với quyền quan sát. Nếu cần thay cấu hình, thực hiện thay đổi phạm vi theo quy trình; không mặc định mở sẵn mọi khả năng để tránh xin lại.

Khi cần chia sẻ đầu ra, kiểm tra dữ liệu nhạy cảm và nơi nhận theo phạm vi đã được cho phép.

## 14. Ứng phó khi tài khoản quản trị bị chiếm quyền

Đổi password là một bước, không phải toàn bộ xử lý.

Cần đánh giá:

- Phiên CLI, web hoặc API còn sống.
- Credential hoặc tài khoản mới đã được tạo.
- Trust, AAA, đường quản trị hoặc logging bị sửa.
- Cấu hình định tuyến và kiểm soát lưu lượng bị thay đổi.
- Cấu hình được lưu bền hoặc artifact triển khai bị sửa.
- Secret và bản backup có thể đã bị tiếp cận.

### Một trình tự xử lý theo bằng chứng

1. Bảo vệ đường ứng cứu và nguồn bằng chứng phù hợp.
2. Chặn tạo phiên mới từ đường bị ảnh hưởng.
3. Xử lý các phiên và credential liên quan theo khả năng thiết bị.
4. Đọc lại cấu hình và so sánh với baseline đáng tin.
5. Kiểm tra các đường tạo quyền bền vững.
6. Phục hồi thay đổi theo kế hoạch được phép.
7. Xác minh độc lập khả năng quản trị và trạng thái dịch vụ.
8. Rà soát những thiết bị khác cùng dùng credential hoặc policy bị ảnh hưởng.

Trình tự cụ thể phụ thuộc mức khẩn cấp. Không chờ thu thập mọi chi tiết nếu việc chặn ảnh hưởng đang diễn ra cần được ưu tiên.

### Không dùng chính một nguồn đã bị ảnh hưởng làm bằng chứng duy nhất

Nếu tài khoản quản trị có thể sửa logging hoặc cấu hình, cần đối chiếu với nguồn độc lập khi có. Một bản running configuration hiện tại có thể không cho biết toàn bộ thay đổi đã xảy ra và bị xóa sau đó.

Cũng không suy luận rằng lưu lượng bình thường ở thời điểm kiểm tra đã chứng minh không có thay đổi quyền tồn đọng.

## 15. Tình huống: thay policy nhưng cắt đường về AAA

### Bối cảnh

Một kỹ sư được duyệt sửa policy cho một dịch vụ. Thay đổi vô tình ảnh hưởng đường router dùng tới AAA và nơi thu thập log.

Phiên hiện tại vẫn tồn tại, nhưng một lần đăng nhập mới không đi qua đường mong muốn. Nếu chỉ kiểm tra phiên cũ, nhóm có thể tưởng mọi thứ hoạt động.

### Điểm cần xác minh

- Đúng policy và phạm vi đã được áp dụng chưa.
- Từ router còn đi tới AAA theo đường được thiết kế không.
- Một phiên mới xác thực và nhận đúng quyền được không.
- Accounting hoặc log có tới đích không.
- Out-of-band có dùng được nếu cần phục hồi không.
- Cấu hình có được xác nhận hoặc lưu đúng kế hoạch không.

### Cách xử lý thiết kế

Đưa các điều kiện trên vào verification plan trước thay đổi. Nếu không đạt, đi theo cơ chế rollback hoặc phục hồi phù hợp với nền tảng.

Không chỉ mở toàn bộ fallback để đăng nhập được rồi coi sự cố đã xong. Cần khôi phục đúng ranh giới quyền, kiểm tra các đường khẩn cấp đã dùng và đối soát bằng chứng.

Tình huống cho thấy xác minh đăng nhập mới, phân quyền và bằng chứng phải nằm trong kế hoạch thay đổi mạng, không phải việc làm thêm nếu còn thời gian.

## 16. Bài thực hành trong môi trường lab

Dùng router hoặc mô hình lab được phép, không kết nối tới mạng production và không dùng secret thật.

### Bước 1: Lập bản đồ đường quản trị

Liệt kê CLI, API, web, SNMP, console, AAA, PAM và công cụ tự động hóa đang có.

Với mỗi đường, xác định principal, role, credential reference, cách xác minh đích và nguồn bằng chứng.

### Bước 2: Định nghĩa ba nhiệm vụ

Ví dụ:

```text
Quan sát:
  xem trạng thái cần thiết, không đọc secret hoặc sửa cấu hình

Thay đổi hẹp:
  sửa đúng một đối tượng lab theo artifact đã duyệt

Ứng cứu:
  khôi phục đường quản trị theo runbook có kiểm soát
```

Ánh xạ sang khả năng thực tế của thiết bị. Không chỉ đổi tên role trên giấy.

Trên thiết bị Cisco IOS phù hợp, các lệnh quan sát như show version, show users hoặc show ip interface brief có thể hỗ trợ thực hành. Cần kiểm tra quyền và nội dung đầu ra trên phiên bản lab; không đưa nguyên dữ liệu nhạy cảm vào báo cáo.

### Bước 3: Kiểm tra các tình huống

| Tình huống | Kết quả mong đợi |
|---|---|
| Đúng người, đúng router và còn thời hạn | Chỉ mở quyền theo nhiệm vụ |
| Người quan sát thử sửa cấu hình | Bị chặn |
| Lệnh xem có thể lộ cấu hình nhạy cảm | Được giới hạn hoặc bảo vệ theo phân loại |
| Người dùng đổi target sau phê duyệt | Kế hoạch cũ không còn hợp lệ |
| Artifact bị sửa sau khi duyệt | Không được thực thi như artifact cũ |
| Router có identity không khớp inventory | Dừng và điều tra, không tự chấp nhận |
| CLI bị giới hạn nhưng API còn quyền rộng | Phát hiện là đường quyền ngoài thiết kế |
| AAA hoạt động và từ chối người dùng | Không tự chuyển thành quyền local rộng |
| AAA không sử dụng được | Đường dự phòng hoạt động đúng chính sách đã kiểm thử |
| Authentication thành công nhưng authorization sai | Phát hiện trước khi báo kiểm soát hoàn tất |
| Cấu hình thay đổi đường tới AAA hoặc logging | Verification plan phát hiện |
| Lệnh timeout sau khi có thể đã áp dụng | Đối soát trạng thái, không retry mù |
| Có thay đổi đồng thời ngoài baseline | Dừng hoặc xử lý theo kế hoạch, không ghi đè mù |
| Cơ chế rollback được kích hoạt | Phục hồi đúng phạm vi và xác minh lại |
| Hết hạn JIT trong khi phiên còn sống | Xử lý theo chính sách phiên, không chỉ đóng ticket |
| Rotation credential | Kết nối mới được kiểm chứng, phiên cũ được xử lý riêng |
| Sử dụng break-glass | Có bằng chứng, kết thúc quyền và đối soát |
| Đóng phiên hỗ trợ của đối tác | Không để lại tài khoản hoặc credential ngoài kế hoạch |
| Kiểm tra log và recording | Nối được người dùng, thao tác, target và kết quả; không phát tán secret |
| Khởi động lại mô hình lab nếu thuộc kế hoạch | Xác minh trạng thái lưu bền theo đúng nền tảng |

### Bước 4: Hoàn thiện hồ sơ

Hồ sơ nên có:

- Danh mục đường quản trị.
- Ma trận nhiệm vụ và quyền.
- Một kế hoạch JIT cùng artifact bất biến.
- Verification plan và recovery runbook.
- Bằng chứng của một lần cho phép và một số lần từ chối.
- Một lỗi AAA hoặc mất đường quản trị được mô phỏng.
- Cách xử lý credential, phiên và cấu hình tạm sau thực hành.

Nếu một khả năng chỉ được mô hình hóa mà chưa kiểm chứng trên thiết bị, ghi rõ giới hạn đó. Không dùng sơ đồ để thay cho kết quả thực thi.

## 17. Các lỗi thiết kế thường gặp

**Chỉ bảo vệ SSH mà bỏ các giao diện khác.** Phải kiểm kê mọi đường quản trị và khả năng ghi cấu hình.

**Xác thực tập trung nhưng cấp cùng quyền rộng cho mọi người.** Authentication không thay authorization theo nhiệm vụ.

**Cho rằng mọi lệnh xem đều an toàn.** Đầu ra có thể chứa secret hoặc thông tin nhạy cảm.

**Dùng một credential quản trị chung ở nhiều thiết bị.** Phạm vi ảnh hưởng và khó khăn quy trách nhiệm tăng lên; cần thiết kế danh tính và scope phù hợp.

**Coi fallback là cách vượt mọi deny.** Phân biệt không thể sử dụng AAA với việc AAA đã từ chối.

**Chỉ kiểm tra phiên hiện tại sau thay đổi.** Phải xác minh đường tạo phiên mới, quyền hiệu lực và nguồn bằng chứng liên quan.

**Giả định mọi router có cùng commit và rollback.** Cần kiểm tra nền tảng, capability và cơ chế lưu cấu hình.

**Đóng JIT nhưng không xử lý phiên.** Deadline của yêu cầu và khả năng thao tác thực tế phải được đối soát.

**Tự động rollback mọi cấu hình khi hết hạn quyền.** Thu hồi quyền khác hoàn tác thay đổi nghiệp vụ; chỉ làm theo kế hoạch.

**Giữ break-glass như đường vận hành thường xuyên.** Cần phạm vi, diễn tập, kiểm soát sử dụng và xử lý sau phục hồi.

Router administrator là một quyền có thể làm thay đổi cả mạng lẫn chính cơ chế quản trị mạng. PAM cần gắn danh tính với nhiệm vụ, kiểm soát mọi đường truy cập và giữ bằng chứng từ approval tới trạng thái thực tế. Sự kết hợp giữa quyền hẹp, thời hạn rõ và khả năng phục hồi đã kiểm chứng giúp quyền quản trị đáp ứng công việc mà vẫn có thể đối soát.

# Service account owner: người chịu trách nhiệm cho tài khoản dịch vụ

Service account là danh tính được phần mềm, dịch vụ hoặc tác vụ tự động sử dụng để truy cập tài nguyên. Dù không có một người đăng nhập hằng ngày bằng tài khoản đó, tổ chức vẫn cần biết ai chịu trách nhiệm về mục đích sử dụng, quyền truy cập, credential và thời điểm ngừng tài khoản.

**Service account owner** là cá nhân hoặc nhóm được chỉ định chịu trách nhiệm quản lý vòng đời và theo dõi việc sử dụng tài khoản dịch vụ. Owner phải có khả năng giải thích vì sao tài khoản tồn tại, phối hợp xử lý thay đổi hoặc sự cố và xác nhận tài khoản còn cần thiết hay không.

Một tài khoản có tên rõ ràng nhưng không có owner có thể tiếp tục giữ quyền trong nhiều năm sau khi ứng dụng đã bị thay thế. Ngược lại, một owner được ghi trên danh sách nhưng không nhận cảnh báo, không biết dependency và không có đường yêu cầu xử lý cũng chưa tạo ra ownership có hiệu lực.

## 1. Ownership là trách nhiệm quản trị, không phải danh tính thực thi

Giả sử tác vụ `invoice-export` chạy mỗi đêm bằng tài khoản `svc-invoice-export-prod`. Trong nhật ký truy cập tài nguyên, chủ thể thực hiện thao tác thường là tài khoản dịch vụ hoặc một danh tính workload tương ứng. Nhóm vận hành ứng dụng có thể là owner của tài khoản này, nhưng điều đó không biến mọi thao tác của tác vụ thành thao tác trực tiếp của một thành viên trong nhóm.

Cần phân biệt ba câu hỏi:

| Câu hỏi | Thành phần trả lời |
| --- | --- |
| Ai hoặc phần mềm nào đang truy cập? | Danh tính đã được xác thực, như service account hoặc workload identity |
| Danh tính đó được làm gì? | Chính sách cấp quyền tại tài nguyên và các điều kiện áp dụng |
| Ai chịu trách nhiệm về việc tài khoản tồn tại và được sử dụng đúng mục đích? | Service account owner và quy trình quản trị liên quan |

Owner không nhất thiết là người trực tiếp tạo tài khoản. Một pipeline hạ tầng có thể tạo tài khoản thay cho nhóm ứng dụng. Owner cũng không nhất thiết giữ credential: credential có thể được cấp tự động cho workload hoặc được quản lý bởi một thành phần chuyên dụng.

Tài liệu quản trị service account của Microsoft Entra mô tả owner là người dùng hoặc nhóm chịu trách nhiệm quản lý và giám sát tài khoản. Tài liệu cũng đề nghị ghi nhận mục đích, quyền dự kiến và chu kỳ rà soát cùng thông tin ownership. [Nguồn: Governing Microsoft Entra service accounts](https://learn.microsoft.com/en-us/entra/architecture/govern-service-accounts).

### Lưu ý về từ “Owner” trong sản phẩm

Một nhãn `owner` trong inventory, một quan hệ sở hữu đối tượng trong directory và một role có tên `Owner` có thể mang ý nghĩa rất khác nhau. Có nền tảng gắn quyền quản trị thực tế với quan hệ sở hữu; có nơi nhãn chỉ là metadata để định tuyến liên hệ.

Vì vậy, không được suy luận rằng “được ghi là owner” luôn cho phép đổi credential hoặc cấp quyền. Cũng không được mặc nhiên cấp role quản trị rộng nhất chỉ để thể hiện trách nhiệm. Phải đọc ý nghĩa của quyền và quan hệ sở hữu trên nền tảng đang dùng.

## 2. Một owner có hiệu lực cần đáp ứng điều gì?

Ownership cần đủ rõ để một người khác có thể tìm được đầu mối và xử lý một quyết định thực tế. Tối thiểu, owner nên có khả năng:

- Xác nhận dịch vụ, script hoặc tác vụ nào đang dùng tài khoản và phục vụ mục đích gì.
- Giải thích những tài nguyên và thao tác cần thiết cho mục đích đó.
- Biết nơi nhận cảnh báo, đường xử lý credential và cách phối hợp với đội IAM hoặc nền tảng.
- Tham gia rà soát quyền, xác nhận tiếp tục sử dụng hoặc yêu cầu thu hồi.
- Bàn giao trách nhiệm khi cá nhân, nhóm hoặc dịch vụ thay đổi.

Tổ chức có thể chọn owner là một cá nhân hoặc một nhóm ổn định. Nhóm thường giúp giảm phụ thuộc vào một nhân viên, nhưng một nhóm không có thành viên hoạt động hoặc không có kênh trực vẫn có thể trở thành đầu mối không liên lạc được.

Với tài khoản quan trọng, cần có đường liên hệ dự phòng và người điều phối khi có sự cố. Điều này không có nghĩa là nhân bản mọi quyền cho nhiều người. Trách nhiệm liên hệ và quyền thay đổi tài khoản là hai việc phải được thiết kế riêng.

Người tạo tài khoản chỉ được xem là owner nếu đã được chỉ định và chấp nhận trách nhiệm theo quy trình. Một địa chỉ email xuất hiện trong lịch sử tạo tài khoản không đủ chứng minh ownership hiện tại.

## 3. Phân tách trách nhiệm giữa các vai trò

Một mô hình phân công minh họa có thể gồm các vai trò sau. Tên gọi cụ thể thay đổi theo tổ chức, nhưng mỗi quyết định cần có người chịu trách nhiệm rõ ràng.

| Vai trò | Trách nhiệm điển hình | Không nên mặc định |
| --- | --- | --- |
| Service account owner | Chịu trách nhiệm về mục đích, nhu cầu tiếp tục sử dụng, dependency và phối hợp vòng đời | Có toàn quyền trên mọi tài nguyên |
| Quản trị viên IAM hoặc nền tảng | Thực hiện cấp phát, thay đổi binding, vô hiệu hóa và các kiểm soát kỹ thuật được phê duyệt | Hiểu đầy đủ nghiệp vụ của mọi tài khoản |
| Chủ tài nguyên hoặc chủ dữ liệu | Quyết định tài khoản có được truy cập tài nguyên thuộc phạm vi mình quản lý hay không | Trực tiếp vận hành credential của ứng dụng |
| Người vận hành workload | Triển khai, theo dõi hoạt động, kiểm tra kết nối và xử lý lỗi ứng dụng | Có thể tự tăng quyền khi tác vụ thất bại |
| Nhóm an ninh hoặc ứng cứu | Đánh giá rủi ro, điều phối điều tra và các biện pháp chặn khi có sự cố | Thay thế mọi trách nhiệm vận hành của owner |

Một nhóm có thể đảm nhiệm nhiều vai trò trong hệ thống nhỏ. Khi đó vẫn cần xác định ai yêu cầu, ai phê duyệt và ai thực hiện thay đổi nhạy cảm. Tài khoản có quyền cao có thể cần kiểm soát độc lập hơn tài khoản chỉ đọc một tập dữ liệu công khai nội bộ.

Không nên để việc ghi nhiều owner dẫn đến không ai chịu trách nhiệm cuối cùng. Nếu dùng một nhóm owner, cần xác định cơ chế nhóm nhận và xử lý yêu cầu: hàng đợi công việc, người trực hoặc đầu mối được phân công.

## 4. Hồ sơ ownership nên chứa những gì?

Hồ sơ ownership có thể nằm trong inventory IAM, CMDB hoặc danh mục dịch vụ. Điều quan trọng là tìm được tài khoản bằng định danh ổn định và liên hệ được với đúng chủ sở hữu, thay vì dựa hoàn toàn vào tên hiển thị.

Một bản ghi có ích thường liên kết các thông tin sau:

| Thông tin | Mục đích |
| --- | --- |
| Định danh tài khoản và nền tảng | Tránh nhầm tài khoản cùng tên ở directory, tenant hoặc project khác |
| Workload, dịch vụ và môi trường | Xác định chính xác phạm vi sử dụng, như production hoặc staging |
| Mục đích và lý do tồn tại | Làm cơ sở đánh giá tài khoản còn cần thiết |
| Nhóm hoặc cá nhân owner | Xác định trách nhiệm; ưu tiên định danh có thể đối chiếu với directory |
| Kênh liên hệ và escalation | Định tuyến review, cảnh báo và sự cố |
| Tài nguyên và quyền được phê duyệt | So sánh quyền thực tế với nhu cầu |
| Những bên được dùng hoặc mạo danh tài khoản | Nhận diện đường truy cập gián tiếp và phạm vi ảnh hưởng |
| Cách cấp credential và nơi quản lý | Biết phải thao tác qua hệ thống nào, không lưu secret trong hồ sơ |
| Dependency và lịch chạy | Tránh vô hiệu hóa nhầm tác vụ ít hoạt động |
| Lần review, ngày review tiếp theo và trạng thái vòng đời | Theo dõi quyết định và thời hạn xử lý |

Ví dụ dưới đây chỉ là bản ghi inventory minh họa cho bài học, không phải schema cấu hình của một nhà cung cấp:

```yaml
accountRef: "directory-A/account-4821"
displayName: "svc-invoice-export-prod"
serviceRef: "service-catalog/invoice-export"
environment: "production"
purpose: "Đọc hóa đơn đã chốt và ghi tệp xuất vào vùng báo cáo"
owner:
  teamRef: "directory-A/group-finance-platform"
  contactRoute: "finance-platform-oncall"
escalationRoute: "platform-duty-manager"
accessIntent:
  - resource: "invoice-finalized-view"
    operation: "read"
  - resource: "report-storage/invoice-export"
    operation: "write"
credentialManagement: "Cấp credential ngắn hạn qua nền tảng workload"
executionSchedule: "Hằng đêm; có tác vụ đối soát cuối tháng"
lifecycleState: "active"
reviewEvidenceRef: "change-record/EXAMPLE-1042"
```

Không đặt mật khẩu, private key, client secret hoặc bearer token vào các field của inventory. Tên nơi quản lý credential giúp người có thẩm quyền tìm đúng quy trình; nó không nên trở thành một bản sao credential.

Metadata ownership không tự thực thi quyền truy cập. Nếu bản ghi ghi “chỉ đọc” nhưng binding thực tế cho phép quản trị, tài khoản vẫn có thể mang quyền quản trị. Cần đối chiếu cấu hình hiệu lực, kể cả quyền nhận qua nhóm, vai trò kế thừa hoặc đường impersonation.

## 5. Trách nhiệm owner trong vòng đời tài khoản

### 5.1. Trước khi tạo

Owner xác định mục đích, workload sử dụng và môi trường hoạt động. Quyền đề xuất phải diễn đạt bằng tài nguyên và thao tác cụ thể, chẳng hạn đọc một view hoặc ghi vào một vùng lưu trữ, thay vì yêu cầu “toàn quyền để tránh lỗi”.

Cần xem nền tảng có thể cấp danh tính trực tiếp cho workload hay không. Nếu vẫn phải quản lý credential lâu dài, phải có lý do, nơi lưu được kiểm soát và quy trình thay đổi hoặc thu hồi. Lựa chọn cơ chế xác thực không làm mất yêu cầu có owner.

Một tài khoản dùng chung cho nhiều ứng dụng không liên quan làm giảm khả năng xác định chủ sở hữu và phạm vi ảnh hưởng. Việc tách tài khoản nên bám vào mục đích, ranh giới quyền và môi trường, thay vì tạo thật nhiều tài khoản nhưng không quản lý được.

### 5.2. Khi đưa vào sử dụng

Owner phối hợp kiểm tra tài khoản đúng đích, workload nhận được credential theo cơ chế đã chọn và quyền thực tế đáp ứng đúng nhu cầu. Các đường truy cập cần thiết phải hoạt động; những đường ngoài phạm vi phải bị từ chối.

Cần xác nhận cảnh báo đến được đúng kênh và nhật ký đủ để liên hệ hoạt động với dịch vụ, môi trường hoặc phiên chạy khi cần. Nhật ký của service account không tự nhận diện được người đã khởi phát một pipeline nếu hệ thống không lưu mối liên hệ đó.

### 5.3. Trong thời gian hoạt động

Owner theo dõi việc sử dụng cùng người vận hành, tham gia review quyền và cập nhật dependency khi dịch vụ thay đổi. Một quyền chỉ cần trong giai đoạn migration phải được xem xét thu hồi sau migration, thay vì tiếp tục tồn tại vì không ai nhớ mục đích ban đầu.

Sự kiện như đổi ứng dụng, mở quyền mới, đổi nhóm vận hành, lộ credential hoặc thay mô hình cấp phát cần kích hoạt đánh giá phù hợp. Chu kỳ review định kỳ không nên là lý do trì hoãn xử lý một thay đổi đã biết.

### 5.4. Khi dịch vụ ngừng hoạt động

Owner xác nhận các dependency đã được thay thế hoặc chấm dứt, phối hợp ngừng cấp credential, thu hồi quyền và xử lý credential còn tồn tại theo cơ chế nền tảng. Việc xóa tài khoản cần theo quy trình có bằng chứng và thời điểm phù hợp.

Không kết luận “không dùng” chỉ từ vài ngày không có log. Một tài khoản có thể phục vụ đóng sổ cuối tháng, khôi phục thảm họa hoặc công việc theo mùa. Cũng không coi thiếu log là bằng chứng an toàn nếu pipeline thu thập log đang lỗi.

## 6. Ownership và nguyên tắc ít quyền nhất

Có hai nhóm quyền cần được đánh giá riêng:

1. **Quyền của service account trên tài nguyên:** tài khoản được đọc, ghi hoặc quản trị những gì.
2. **Quyền của người hoặc workload đối với service account:** ai có thể dùng danh tính đó, yêu cầu token, mạo danh, tạo credential hoặc thay chính sách liên quan.

Nhóm thứ hai rất dễ bị bỏ sót. Một người không trực tiếp có quyền đọc dữ liệu vẫn có thể lấy được quyền tương đương nếu được tùy ý tạo credential cho một service account có quyền đọc dữ liệu đó. Mức rủi ro cụ thể phụ thuộc cơ chế và điều kiện áp dụng, nhưng phải xét đường truy cập gián tiếp này.

Owner cần đủ khả năng quan sát và phối hợp xử lý trách nhiệm của mình. Không phải mọi owner đều cần quyền tự cấp credential, đổi mọi binding hoặc phê duyệt mọi yêu cầu của chính mình.

Với thao tác quản trị có tác động lớn, có thể áp dụng cấp quyền theo thời gian, phê duyệt, phân tách người yêu cầu và người duyệt hoặc kiểm soát tương đương theo rủi ro. Đây là thiết kế quyền thực tế, không phải chỉ thêm tên owner vào một bảng.

Service account cũng không nên trở thành tài khoản dùng chung để con người đăng nhập hằng ngày. Nếu cần kiểm thử hoặc xử lý sự cố dưới danh tính dịch vụ, hãy dùng một cơ chế được phê duyệt, có giới hạn và ghi được danh tính người yêu cầu. Truyền credential cho cả nhóm làm mất khả năng quy trách nhiệm và mở rộng phạm vi lộ bí mật.

## 7. Bàn giao ownership khi nhân sự hoặc nhóm thay đổi

Ownership phải chuyển giao được mà không phụ thuộc vào việc người cũ nhớ gửi một email. Quy trình bàn giao cần có bên nhận chấp nhận trách nhiệm và khả năng vận hành thực tế.

Một trình tự có thể áp dụng là:

1. Kiểm kê những service account do người hoặc nhóm cũ chịu trách nhiệm, gắn với đúng định danh của họ.
2. Xác định nhóm nhận và kiểm tra nhóm đó còn hoạt động, có người phụ trách và có khả năng hỗ trợ dịch vụ.
3. Bàn giao mục đích, quyền, lịch chạy, dependency, đường quản lý credential, cảnh báo và những ngoại lệ đang mở.
4. Ghi nhận bên nhận chấp nhận ownership trước hoặc đồng thời với thời điểm có hiệu lực đã thống nhất.
5. Cập nhật inventory và cấu hình liên hệ liên quan; kiểm tra cảnh báo thực sự đến nơi nhận mới.
6. Rà soát quyền của người hoặc nhóm cũ: quyền quản trị, tạo credential, impersonation và truy cập kho bí mật nếu có.
7. Lưu bằng chứng chuyển giao và theo dõi các phần việc còn lại.

Đổi owner trong inventory không tự thu hồi quyền kỹ thuật của owner cũ. Ngược lại, thu hồi tài khoản nhân viên không tự chuyển trách nhiệm của những service account mà người đó quản lý.

Không nên mặc nhiên vô hiệu hóa mọi service account của một nhân viên ngay khi người đó nghỉ việc: chúng có thể đang phục vụ production. Cần xử lý đồng thời hai việc: thu hồi quyền của nhân viên và xác lập người tiếp nhận tài khoản dịch vụ. Nếu có dấu hiệu xâm nhập, biện pháp cô lập khẩn cấp được quyết định theo tình huống sự cố.

Chuyển nhóm quản lý cũng không mặc nhiên buộc thay danh tính của workload. Có thể giữ nguyên service account nếu phạm vi và quyền còn phù hợp; điều cần thay là ownership và các quyền quản trị liên quan. Nếu chuyển môi trường hoặc ranh giới tin cậy, cần đánh giá một đợt di chuyển danh tính riêng.

## 8. Xử lý service account không có owner

Một tài khoản có thể được xem là mất ownership khi field owner trống, owner đã rời tổ chức, nhóm bị xóa hoặc đầu mối không thể xác nhận trách nhiệm. Việc owner không phản hồi một lần chưa đủ kết luận tài khoản không còn sử dụng.

### 8.1. Xác minh và tìm dependency

Đầu mối IAM hoặc nền tảng được tổ chức chỉ định cần tìm ứng dụng, script, lịch chạy và tài nguyên liên quan. Có thể dùng nhật ký, lịch sử thay đổi và danh mục dịch vụ trong phạm vi quyền hạn của quy trình điều tra.

Người tạo tài khoản và người thay đổi gần nhất là manh mối, không phải bằng chứng chắc chắn về owner hiện tại. Một kỹ sư nền tảng có thể đã tạo hàng trăm tài khoản thay cho các nhóm khác.

### 8.2. Giao đầu mối tạm thời và hạn xử lý

Nếu chưa xác định được owner chính thức, cần một đầu mối tạm thời chịu trách nhiệm xử lý đến khi có kết luận. Ghi rõ trạng thái đang xác minh, phạm vi được phép duy trì và thời hạn giải quyết. Không để một nhãn “temporary” kéo dài vô hạn.

### 8.3. Ra quyết định theo rủi ro và dependency

Tài khoản quyền cao, có hoạt động bất thường hoặc credential bị lộ có thể cần hạn chế khẩn cấp. Tài khoản ít quyền đang phục vụ một batch job đã biết có thể cần một kế hoạch chuyển giao có kiểm soát. Không dùng một hành động xóa hàng loạt cho mọi tình huống.

Trong trường hợp bình thường, vô hiệu hóa hoặc hạn chế có kiểm soát có thể tạo cơ hội quan sát tác động trước khi xóa vĩnh viễn, nếu nền tảng hỗ trợ và quy trình cho phép. Tuy nhiên, khả năng khôi phục và tác dụng của thao tác disable khác nhau giữa các hệ thống, cần được xác minh trước.

Không giả định disable tài khoản sẽ lập tức hủy mọi token, credential hoặc phiên đã được cấp. Quyết định thu hồi phải xét cả điểm cấp phát, điểm xác minh và cơ chế thực thi quyền tại tài nguyên.

## 9. Ví dụ hoàn chỉnh: tài khoản xuất báo cáo hóa đơn

Nhóm Finance Platform là owner của `svc-invoice-export-prod`. Một pipeline tạo tài khoản theo yêu cầu đã được phê duyệt; đội nền tảng hỗ trợ cấp credential ngắn hạn. Chủ dữ liệu hóa đơn phê duyệt quyền đọc view hóa đơn đã chốt, còn chủ vùng lưu trữ phê duyệt quyền ghi vào đường dẫn báo cáo tương ứng.

Tài khoản không cần đọc mọi bảng trong cơ sở dữ liệu, không cần quản trị vùng lưu trữ và không được dùng cho staging. Nhóm owner phải biết những giới hạn này để review quyền thực tế, nhưng không nhất thiết có quyền tự thay đổi chúng.

Ba tình huống cho thấy ownership ảnh hưởng đến vận hành như thế nào:

| Tình huống | Owner cần phối hợp thực hiện |
| --- | --- |
| Tác vụ chuyển sang đọc dữ liệu từ hệ thống mới | Xác nhận nhu cầu mới, xin quyền từ chủ tài nguyên mới, kiểm tra rồi thu hồi quyền cũ không còn dùng |
| Nhóm Finance Platform sáp nhập với nhóm khác | Chỉ định nhóm nhận, bàn giao dependency và cảnh báo, rà soát quyền quản trị của nhóm cũ |
| Báo cáo hóa đơn được thay bằng một sản phẩm khác | Xác nhận tác vụ cuối kỳ và dependency, ngừng sử dụng tài khoản, thu hồi quyền và xử lý tài khoản theo quy trình |

Nếu một thành viên owner nghỉ việc, tác vụ đêm vẫn có thể phải chạy. Quyền cá nhân của người đó cần được thu hồi; trách nhiệm tài khoản chuyển cho đầu mối còn hoạt động. Không chuyển credential sang tài khoản cá nhân của nhân viên mới để duy trì dịch vụ.

Khi phát hiện truy cập ngoài lịch dự kiến, owner cung cấp ngữ cảnh nghiệp vụ và phối hợp với đội ứng cứu. Cần đối chiếu lịch chạy đặc biệt hoặc tác vụ chạy lại, đồng thời bảo toàn bằng chứng và chặn truy cập theo mức độ sự cố. Việc “đây là tài khoản của nhóm tôi” không đủ để khẳng định hoạt động đó hợp lệ.

## 10. Rà soát ownership bằng bằng chứng

Một lần review có ích cần đưa ra quyết định về tài khoản và quyền của nó, không chỉ xác nhận field owner khác rỗng.

Những câu hỏi trọng tâm gồm:

- Tài khoản còn phục vụ mục đích đã ghi nhận không? Workload nào đang sử dụng và ai xác nhận?
- Owner và kênh liên hệ còn hoạt động, có nhận trách nhiệm không?
- Quyền thực tế và những bên có thể sử dụng danh tính có còn phù hợp không?
- Credential được cấp, lưu, gia hạn và thu hồi theo cơ chế nào? Có ngoại lệ nào cần hết hạn không?
- Dependency, lịch chạy ít thường xuyên và kế hoạch ngừng dịch vụ đã được cập nhật chưa?
- Quyết định giữ nguyên, giảm quyền, chuyển owner hay ngừng tài khoản được ghi ở đâu và ai thực hiện?

Chỉ số theo dõi có thể gồm tỷ lệ tài khoản có owner hợp lệ, số tài khoản quá hạn review, thời gian xử lý ownership bị mất và số quyền quản trị cũ chưa được thu hồi sau bàn giao. Không chỉ tối ưu tỷ lệ “đã có tên owner”: một trường được điền nhưng không thể liên lạc vẫn có thể che giấu vấn đề.

Chu kỳ review cần dựa trên rủi ro và đặc điểm dịch vụ. Ngoài lịch định kỳ, các thay đổi nhân sự, quyền, môi trường hoặc sự cố đã biết cần được xử lý theo sự kiện.

## 11. Câu hỏi tự kiểm tra

**Người chạy lệnh tạo service account có tự động là owner không?**

Không nhất thiết. Người đó có thể thực hiện thay mặt nhóm ứng dụng. Cần có sự chỉ định và xác nhận trách nhiệm hiện tại, thay vì suy luận từ lịch sử tạo tài khoản.

**Ghi một nhóm vào field owner có bảo đảm nhóm đó kiểm soát tài khoản không?**

Không. Field có thể chỉ là metadata, còn quyền quản trị được cấp bằng cơ chế khác. Nếu nền tảng có quan hệ owner mang quyền thực tế, phải đánh giá chính các quyền đó. Trách nhiệm và cấu hình quyền cần được kiểm tra riêng.

**Có owner rồi thì có thể giao cho owner toàn quyền và bỏ review không?**

Không. Owner phải giúp duy trì mục đích và quyền tối thiểu; bản thân quyền của owner cũng cần đúng nhu cầu. Review còn phải xét những người hoặc workload có thể mạo danh tài khoản hoặc tạo credential cho nó.

**Một service account không có log trong một tuần có thể xóa ngay không?**

Chưa đủ cơ sở. Cần kiểm tra độ đầy đủ của log, lịch chạy, tác vụ định kỳ và dependency. Quyết định ngừng tài khoản phải có bằng chứng phù hợp với mức rủi ro và quy trình của hệ thống.

**Điều gì chứng minh bàn giao ownership đã hoàn tất?**

Bên nhận đã chấp nhận trách nhiệm, hồ sơ và đường liên hệ được cập nhật, cảnh báo đến đúng nơi, dependency được bàn giao và quyền của bên cũ được rà soát, xử lý. Chỉ sửa một nhãn owner chưa chứng minh toàn bộ các điều kiện đó.

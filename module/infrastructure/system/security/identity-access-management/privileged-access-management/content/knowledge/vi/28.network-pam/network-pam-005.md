# Network configuration proxy

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích vai trò của proxy trong truy cập đặc quyền tới thiết bị mạng.
- Phân biệt proxy chuyển tiếp phiên với hệ thống hiểu và kiểm soát thay đổi cấu hình.
- Thiết kế liên kết giữa danh tính, phê duyệt, credential và phiên thiết bị.
- Lập quy trình kiểm tra trước thay đổi, áp dụng, xác minh và phục hồi.
- Xử lý thay đổi đồng thời, timeout, mất đường quản trị và quyền tồn dư.

## 1. Network configuration proxy là gì?

Trong bài này, **network configuration proxy** là thành phần trung gian cho phép người dùng hoặc hệ thống tự động hóa truy cập và thay đổi cấu hình thiết bị mạng thông qua một đường được quản lý.

Thiết bị đích có thể là router, switch, firewall hoặc thành phần mạng được quản trị qua giao diện CLI hay API. Thành phần trung gian có thể được triển khai dưới dạng session gateway, broker hoặc dịch vụ điều phối thay đổi.

Đây là mô hình kiến trúc trong Network PAM, không phải tên một tính năng có hành vi thống nhất ở mọi nhà cung cấp.

Proxy có thể giúp:

- Xác thực người yêu cầu.
- Kiểm tra phê duyệt và thời hạn.
- Chọn đúng thiết bị và quyền.
- Cấp hoặc sử dụng credential thay vì tiết lộ cho người dùng.
- Giới hạn đường truy cập theo khả năng triển khai.
- Ghi bằng chứng và liên kết hành động.
- Điều phối xác minh, phục hồi và đóng phiên.

Không phải sản phẩm nào mang tên proxy cũng có đủ các khả năng trên.

### 1.1. Phạm vi bài học

Nội dung tập trung vào đường quản trị và thay đổi cấu hình mạng. Nó không mô tả việc cấu hình forward proxy cho người dùng truy cập web hoặc reverse proxy phục vụ ứng dụng.

Một thay đổi qua proxy có thể ảnh hưởng cả đường quản trị lẫn lưu lượng nghiệp vụ. Vì vậy, PAM cần kết hợp kiểm soát quyền với quản lý thay đổi cấu hình.

## 2. Ba mức năng lực khác nhau

| Mức | Proxy làm gì? | Giới hạn cần hiểu |
|---|---|---|
| Chuyển tiếp kết nối | Đưa lưu lượng tới thiết bị đích | Có thể không hiểu lệnh hoặc nội dung cấu hình |
| Quản lý phiên | Xác thực, mở phiên, quản lý credential, ghi tương tác | Chưa chắc kiểm soát được mọi tác động của lệnh |
| Điều phối cấu hình | Hiểu đối tượng thay đổi, kế hoạch, trạng thái và xác minh | Phụ thuộc protocol, model và khả năng thiết bị |

### 2.1. Có phiên được ghi không đồng nghĩa có thay đổi được kiểm soát

Một phiên CLI có video hoặc transcript vẫn có thể cho phép người dùng thay nhiều phần cấu hình ngoài kế hoạch trước khi bị phát hiện.

Ngược lại, một API broker có thể kiểm tra payload trước khi gửi nhưng không nhìn thấy thao tác qua đường console ngoài băng nếu đường đó không được tích hợp.

Cần mô tả chính xác điều gì được chặn, điều gì chỉ được ghi và điều gì nằm ngoài độ bao phủ.

### 2.2. Proxy không tự tạo đường truy cập độc quyền

Nếu máy người dùng vẫn kết nối trực tiếp được tới cổng quản trị và có credential phù hợp, việc yêu cầu “mọi người dùng proxy” có thể chỉ là quy trình.

Muốn đường quản trị đi qua kiểm soát dự kiến, cần phối hợp mạng quản trị, quyền thiết bị, danh tính và các ngoại lệ. Đồng thời vẫn cần một đường khẩn cấp được quản lý để khôi phục khi đường chính hỏng.

## 3. Kiến trúc tham chiếu

~~~text
Người vận hành / pipeline
          │
          ▼
Xác thực danh tính và điều kiện truy cập
          │
          ▼
Yêu cầu thay đổi + phê duyệt + kế hoạch
          │
          ▼
Proxy / broker / bộ điều phối
          │
          ├── Kho credential hoặc nguồn cấp danh tính
          ├── Chính sách quyền và phạm vi
          ├── Trạng thái công việc và bằng chứng
          └── Kênh quản trị tới thiết bị
                        │
                        ▼
                Router / switch / firewall
                        │
                        ▼
            Kiểm tra cấu hình và hoạt động thực tế
~~~

### 3.1. Hai phía của phiên

Proxy có thể kết thúc một phiên từ người dùng và tạo một phiên khác tới thiết bị. Khi đó, xác thực upstream và downstream là hai bước cần được quản lý.

MFA ở phía người dùng không tự chứng minh thiết bị nhận diện được cá nhân đó. Thiết bị có thể chỉ thấy một danh tính dịch vụ của proxy.

### 3.2. Ba lớp quyền cần đồng nhất

- Người dùng được yêu cầu thao tác gì.
- Proxy được phép thực hiện gì thay người dùng.
- Thiết bị thực sự cho principal downstream làm gì.

Nếu proxy dùng một tài khoản toàn quyền cho mọi nhiệm vụ, phạm vi hậu quả khi proxy hoặc policy bị lỗi có thể rất lớn.

Khi giao thức và thiết bị hỗ trợ, nên giới hạn cả ở phía đích. NACM là một mô hình chuẩn để giới hạn operation và nội dung NETCONF/RESTCONF theo người dùng. [RFC 8341: Network Configuration Access Control Model](https://www.rfc-editor.org/rfc/rfc8341.html).

### 3.3. Proxy là tài sản đặc quyền

Một proxy có thể mở phiên tới nhiều thiết bị, lấy credential và sửa cấu hình. Vì vậy, quyền quản trị proxy, policy, phần mềm thực thi và kho credential đều nằm trong phạm vi PAM.

Không nên chỉ kiểm soát người vận hành thiết bị mà bỏ qua người có thể đổi chính sách proxy.

## 4. Lựa chọn đường giao thức

### 4.1. SSH và CLI

CLI thuận tiện cho tác vụ tương tác nhưng có thể phụ thuộc ngữ cảnh, phiên bản thiết bị và cách diễn giải lệnh.

Một bộ lọc chuỗi không tự hiểu hết tác động của:

- Chế độ cấu hình hiện tại.
- Lệnh viết tắt hoặc cách biểu diễn khác.
- Import hoặc nạp một cấu hình.
- Script, macro hoặc công cụ phụ trợ.
- Chuyển sang giao diện quản trị khác.
- Thao tác tạo người dùng hoặc sửa phương thức xác thực.

Danh sách lệnh cho phép cần được kiểm thử theo nền tảng. Không gọi nó là kiểm soát đầy đủ chỉ vì có một regex chặn từ khóa.

### 4.2. NETCONF

NETCONF mô tả thao tác cấu hình bằng RPC và công bố capability. Candidate, confirmed commit và rollback-on-error là những khả năng phải được kiểm tra; không mặc định thiết bị có đủ. [RFC 6241: NETCONF](https://www.rfc-editor.org/rfc/rfc6241.html).

Điểm thiết kế cho proxy là chọn luồng thực thi dựa trên capability thực tế, thay vì chạy cùng một chuỗi thao tác trên mọi thiết bị.

### 4.3. RESTCONF hoặc API cấu hình

RESTCONF cung cấp giao diện HTTP cho dữ liệu YANG. Cơ chế ETag và If-Match có thể giúp từ chối cập nhật khi phiên bản tài nguyên không còn khớp. [RFC 8040: RESTCONF](https://www.rfc-editor.org/rfc/rfc8040.html).

API có cấu trúc giúp kiểm tra payload và đối tượng, nhưng không tự bảo đảm thay đổi đúng nghiệp vụ hoặc có thể rollback trên nhiều thiết bị.

### 4.4. Giao diện web và API riêng của nhà cung cấp

Mức kiểm soát phụ thuộc sản phẩm và phiên bản. Một proxy chỉ ghi hình web có thể không hiểu diff cấu hình; một API riêng có thể có ngữ nghĩa commit khác protocol chuẩn.

Bản kiểm kê cần ghi đường được hỗ trợ, những thao tác bị giới hạn và những phần chưa thể xác minh.

## 5. Danh tính, credential và quy trách nhiệm

### 5.1. Dùng danh tính cá nhân ở đầu vào

Mỗi người cần đăng nhập bằng danh tính có thể quy trách nhiệm. Không dùng một tài khoản proxy chung cho cả ca trực.

Yêu cầu, phê duyệt và lần mở phiên cần được liên kết với danh tính đó bằng dữ liệu được bảo vệ.

### 5.2. Lựa chọn danh tính tại thiết bị

Có thể có các mô hình:

- Danh tính cá nhân được thiết bị nhận diện.
- Danh tính tạm thời được cấp theo yêu cầu.
- Danh tính dịch vụ của proxy có phạm vi giới hạn.
- Credential dùng chung được proxy quản lý khi chưa có lựa chọn phù hợp hơn.

Cần đánh giá độ hỗ trợ và mức rủi ro, không giả định một mô hình dùng được cho mọi thiết bị.

### 5.3. Khi thiết bị chỉ thấy danh tính proxy

Cần giữ chuỗi liên kết:

~~~text
Cá nhân → yêu cầu → phê duyệt → công việc proxy
        → phiên downstream → hành động → kết quả thiết bị
~~~

Tên người được chèn vào mô tả hoặc command comment chỉ là dữ liệu tương quan nếu có thể bị người dùng tự sửa. Nó không tự thay thế bằng chứng xác thực.

### 5.4. Không tiết lộ credential khi không cần

Nếu kiến trúc hỗ trợ, proxy sử dụng credential mà không trả giá trị cho người dùng. Tuy nhiên, điều đó không tự làm quyền hẹp hơn hoặc ngăn người có phiên gây hậu quả.

Credential downstream cần được bảo vệ trong bộ nhớ, log, tệp tạm và bản chẩn đoán. Khi giá trị đã được tiết lộ, phải có phương án xử lý khả năng tái sử dụng.

## 6. Kiểm kê thiết bị và đường quản trị

Một hồ sơ thiết bị phục vụ cấu hình nên có:

| Nội dung | Ý nghĩa |
|---|---|
| Định danh ổn định | Tránh thao tác nhầm thiết bị có tên giống nhau |
| Môi trường và owner | Phân biệt lab, staging, production |
| Vai trò mạng | Hiểu tác động của lỗi cấu hình |
| Đường quản trị | CLI, API, console hoặc đường khác |
| Capability | Cách kiểm tra, commit và phục hồi được hỗ trợ |
| Danh tính downstream | Principal nào thực hiện thay đổi |
| Quyền đích | Phạm vi cấu hình và operation được phép |
| Kho credential | Tham chiếu, không phải giá trị bí mật |
| Nguồn audit | Proxy, thiết bị và hệ thống giám sát liên quan |
| Đường khẩn cấp | Cách tiếp cận khi mất mạng quản trị |
| Cấu hình mong muốn | Nguồn quản lý và cơ chế đối soát |
| Trạng thái lưu bền | Cách xác minh thay đổi còn sau khởi động theo thiết bị |

Không chỉ dùng địa chỉ IP làm định danh duy nhất. Địa chỉ có thể được tái sử dụng, đi qua NAT hoặc trỏ tới thành phần khác sau thay đổi.

Proxy phải xác minh danh tính đầu xa theo cơ chế giao thức, chẳng hạn trust của host key hoặc chứng chỉ được quản lý. Bỏ kiểm tra danh tính để phiên dễ mở có thể dẫn đến cấp credential cho sai đích.

## 7. Phê duyệt đúng thay đổi

### 7.1. Không chỉ phê duyệt quyền đăng nhập

Một người được phép mở phiên không tự được phép sửa mọi cấu hình.

Kế hoạch cần nêu:

- Thiết bị đích.
- Phạm vi cấu hình được sửa.
- Payload hoặc tập lệnh đã được xem xét.
- Baseline và điều kiện đầu vào.
- Thứ tự thiết bị.
- Cửa sổ thực hiện.
- Kiểm tra thành công và điều kiện dừng.
- Phương án phục hồi.
- Người thực hiện và người xác minh.

### 7.2. Phê duyệt bản được thực thi

Nếu một template được render thành cấu hình theo từng thiết bị, người duyệt cần hiểu bản render thực tế hoặc những ràng buộc đã được máy kiểm tra.

Không duyệt template rồi cho phép thay tùy ý biến đầu vào, đích hoặc phiên bản template sau đó.

Có thể gắn phê duyệt với một kế hoạch bất biến theo phiên bản. Digest giúp nhận biết nội dung thay đổi khi được triển khai đúng, nhưng không tự tạo thẩm quyền hoặc thay thế bảo vệ bản ghi kế hoạch.

### 7.3. Cấu hình chứa secret cần cách xem xét riêng

Bản diff có thể chứa khóa, community string, credential hoặc giá trị đã được mã hóa theo cách vẫn cần bảo vệ.

Người duyệt thường cần biết tham chiếu secret hoặc metadata, không nhất thiết cần xem giá trị. Bản cấu hình đầy đủ nếu phải lưu phải có quyền truy cập và mã hóa phù hợp.

### 7.4. Thứ tự cũng có thể là nội dung bảo mật

Thứ tự rule trong ACL hoặc chính sách có thể làm thay đổi hành vi. Không chuẩn hóa bằng cách sắp xếp mọi dòng rồi cho rằng hai cấu hình tương đương.

Phép so sánh cần hiểu model hoặc quy tắc riêng của thiết bị.

## 8. Kiểm tra trước thay đổi

### 8.1. Xác minh baseline hiện tại

Cấu hình có thể đã thay đổi từ lúc duyệt. Cần so sánh trạng thái hiện tại với baseline được dùng để lập kế hoạch.

Nếu sai lệch quan trọng, dừng hoặc lập kế hoạch lại theo quy trình. Không tự ghi đè cấu hình mới chỉ để áp dụng bản đã duyệt cũ.

### 8.2. Phát hiện thay đổi chưa thuộc công việc

Nếu có cấu hình chờ hoặc vùng làm việc đang được người khác dùng, proxy không nên tự xóa hoặc gộp nó khi chưa xác định ownership.

Bản candidate dùng chung hoặc cấu hình tạm có thể chứa thay đổi ngoài yêu cầu hiện tại. Việc commit toàn bộ có thể vô tình áp dụng cả phần chưa được duyệt.

### 8.3. Kiểm tra đường quản trị và phụ thuộc

Một thay đổi ACL, route hoặc DNS có thể làm mất đường tới:

- Proxy.
- Kho credential.
- Nguồn xác thực.
- Hệ thống audit.
- Nơi nhận kết quả kiểm tra.
- Đường khôi phục.

Kế hoạch phải xem xét những phụ thuộc đó trước, không chỉ thử kết nối thiết bị tại thời điểm bắt đầu.

### 8.4. Kiểm tra cơ chế phục hồi có thật

Bản sao cấu hình không bảo đảm phục hồi được nếu không còn đường đưa nó trở lại thiết bị.

Cần biết ai giữ đường ngoài băng, credential nào còn dùng được và các bước phục hồi có được thử trên nền tảng tương ứng chưa.

## 9. Luồng thay đổi có kiểm soát

Một quy trình tham chiếu:

1. Xác thực người hoặc pipeline.
2. Kiểm tra yêu cầu, phạm vi và thời hạn.
3. Xác minh thiết bị và danh tính đầu xa.
4. Kiểm tra baseline và capability.
5. Điều phối quyền thay đổi để tránh xung đột.
6. Chuẩn bị cấu hình và kiểm tra nội dung.
7. Áp dụng bằng cơ chế phù hợp.
8. Đối soát phản hồi và trạng thái thiết bị.
9. Kiểm tra đường quản trị, mạng và chức năng liên quan.
10. Hoàn tất xác nhận và lưu bền khi thiết kế yêu cầu.
11. Giải phóng tài nguyên quản trị đúng ownership.
12. Đóng phiên, quyền và hồ sơ bằng chứng.

Các bước là mô hình quyết định, không phải chuỗi lệnh chung cho mọi vendor.

### 9.1. Giới hạn quy trình và giới hạn kỹ thuật

Việc ghi “chỉ sửa ACL quản trị” trong ticket là giới hạn quy trình. Một principal downstream bị thiết bị chặn sửa phần khác là giới hạn kỹ thuật.

Nên kết hợp hai loại khi có thể. Nếu thiết bị không hỗ trợ quyền hẹp, phải ghi rõ giới hạn còn lại và tăng khả năng quan sát, xác minh phù hợp.

### 9.2. Chặn thao tác không thuộc kế hoạch

Proxy hiểu cấu hình có thể kiểm tra schema, đối tượng và tham số. Nhưng cần kiểm thử những đường không đi qua parser dự kiến, chẳng hạn import, API khác hoặc phiên tương tác phụ.

Không gán nhãn “configuration-aware” chỉ vì proxy lưu text người dùng gửi.

## 10. Hiểu đúng candidate, confirmed commit và rollback

### 10.1. Candidate không mặc nhiên là vùng riêng

Với NETCONF, candidate có thể được chia sẻ giữa nhiều phiên. Capability và khóa cấu hình cần được xét để tránh tác động thay đổi của người khác.

Confirmed commit có cơ chế quay về nếu không được xác nhận trong thời hạn; hành vi còn phụ thuộc phiên và lựa chọn persist. rollback-on-error xử lý lỗi của một edit theo phạm vi capability, không thay thế toàn bộ quy trình phục hồi dịch vụ. [RFC 6241, các mục 8.3–8.5](https://www.rfc-editor.org/rfc/rfc6241.html#section-8.3).

### 10.2. Không xác nhận chỉ vì phiên vẫn mở

Một thay đổi có thể giữ kết nối từ proxy nhưng làm hỏng lưu lượng người dùng hoặc đường quản trị khác.

Điều kiện xác nhận nên dựa trên kiểm tra được kế hoạch định nghĩa: đúng cấu hình, đúng khả năng tiếp cận và đúng hành vi mạng. Không dùng một phản hồi thành công duy nhất làm bằng chứng toàn diện.

### 10.3. Đồng hồ rollback là trạng thái cần quản lý

Khi dùng cơ chế xác nhận có thời hạn, cần biết:

- Thời hạn nào đang có hiệu lực.
- Phiên hoặc thành phần nào có thể xác nhận.
- Điều gì xảy ra khi proxy lỗi.
- Điều gì xảy ra khi thiết bị khởi động lại.
- Ai xử lý nếu chưa đủ bằng chứng trước hạn.

Không gia hạn hoặc xác nhận mù quáng để tránh rollback trong khi chưa hiểu trạng thái.

### 10.4. Rollback cấu hình không đảo ngược mọi hậu quả

Lưu lượng đã bị lộ, gián đoạn đã xảy ra hoặc trạng thái ở hệ thống ngoài có thể không tự phục hồi khi cấu hình cũ được đưa lại.

Một bản cấu hình cũ cũng có thể chứa vấn đề bảo mật đã được sửa. Quyết định phục hồi phải xét tình huống hiện tại, không chỉ mục tiêu quay về bất kỳ trạng thái cũ nào.

## 11. Thay đổi đồng thời và chống ghi đè

### 11.1. Hai lớp điều phối

Proxy có thể điều phối theo thiết bị hoặc công việc. Thiết bị có thể có khóa hoặc cơ chế điều kiện phiên bản riêng.

Khóa trong cơ sở dữ liệu của proxy không tự buộc mọi người dùng ngoài proxy tuân thủ. Ngược lại, một khóa datastore không tự giải quyết toàn bộ điều phối nhiều thiết bị.

### 11.2. Kiểm tra điều kiện ngay tại lúc ghi

Nếu có cơ chế cập nhật có điều kiện, cần đưa baseline hoặc version vào quyết định tại hệ thống đích. Đọc trước rồi ghi không điều kiện vẫn có khoảng trống khi trạng thái thay đổi giữa hai bước.

Khi không có khả năng đó, phải có phương án phối hợp và đối soát phù hợp, đồng thời ghi rõ mức bảo đảm còn lại.

### 11.3. Tiến trình cũ có thể tiếp tục sau khi mất quyền điều phối

Trong một triển khai HA, worker bị chậm có thể tiếp tục sau khi hệ thống đã giao công việc cho worker khác. Nếu chỉ dựa vào lease hết hạn, có thể có hai bên cùng ghi.

Thiết kế cần ngăn thực thi từ owner đã cũ hoặc phát hiện và đối soát trước khi tiếp tục. Cách thực hiện phụ thuộc proxy và khả năng thiết bị.

### 11.4. Không cleanup thay đổi không thuộc mình

Giải phóng khóa, hủy vùng cấu hình hoặc khôi phục baseline phải kiểm tra ownership và trạng thái hiện tại.

Một bước cleanup chạy muộn có thể làm mất thay đổi hợp lệ mới nếu nó chỉ dựa vào tên công việc hoặc một bản snapshot cũ.

## 12. Timeout, retry và phục hồi proxy

### 12.1. Timeout không chứng minh thao tác thất bại

Thiết bị có thể đã nhận cấu hình nhưng phản hồi bị mất. Nếu proxy gửi lại toàn bộ, có thể gây thay đổi trùng, ghi đè hoặc tác động không mong muốn.

Trạng thái công việc cần phân biệt:

- Chưa gửi.
- Đã gửi, chưa rõ kết quả.
- Đích xác nhận tiếp nhận.
- Cấu hình quan sát được.
- Hoạt động thực tế đã xác minh.
- Đang chờ xác nhận hoặc phục hồi.
- Hoàn tất hoặc còn ngoại lệ.

Tên trạng thái là ví dụ nội bộ.

### 12.2. Mã công việc không tạo exactly-once ở thiết bị

Một request ID giúp liên kết và chống gửi lại ở phía proxy nếu được triển khai đúng. Nó không tự bảo đảm thiết bị chỉ thực hiện một lần.

Cần kiểm tra khả năng truy vấn trạng thái, xác định kết quả và ngữ nghĩa của thao tác đích.

### 12.3. Proxy HA cần lưu trạng thái đủ để tiếp tục

Trước khi worker thay thế thực hiện tiếp, nó cần biết thiết bị nào đã được thay đổi, baseline, phản hồi, điều kiện xác nhận và thời hạn còn lại.

Không chỉ chuyển một phiên đăng nhập sang node mới rồi giả định mọi trạng thái cấu hình vẫn như trước. Những handle hoặc token phục hồi nếu có phải được bảo vệ như thông tin nhạy cảm tương ứng.

### 12.4. Không tự động commit lại khi chưa hiểu trạng thái

Nếu thiết bị đang chờ xác nhận, một lần retry sai có thể làm mất khả năng quay về hoặc áp dụng thêm thay đổi.

Bước đầu tiên sau lỗi là quan sát và đối soát, không phải luôn chạy lại từ đầu.

## 13. Nhiều thiết bị không tự tạo một giao dịch chung

Một thay đổi mạng thường đi qua nhiều thiết bị. Thành công trên từng thiết bị không tự bảo đảm toàn bộ hệ thống cùng chuyển trạng thái một cách nguyên tử.

Cần lập kế hoạch:

- Thứ tự áp dụng.
- Quan hệ phụ thuộc.
- Nhóm canary hoặc phạm vi thử đầu tiên.
- Điều kiện chuyển sang thiết bị tiếp theo.
- Hành vi khi một thiết bị thất bại.
- Cấu hình tương thích trong thời gian chuyển tiếp.
- Cách phục hồi từng phần.
- Kết quả mong muốn sau mọi bước.

### 13.1. Không đánh dấu cả batch thành công từ một phản hồi

Ghi trạng thái theo từng thiết bị và từng giai đoạn. Nếu hai thiết bị đã đổi và thiết bị thứ ba chưa rõ kết quả, báo cáo phải phản ánh trạng thái hỗn hợp.

### 13.2. Rollback theo thứ tự cũng cần được thiết kế

Khôi phục mọi thiết bị cùng lúc có thể gây thêm gián đoạn. Cần hiểu việc quay lại trên thiết bị nào sẽ ảnh hưởng đường điều khiển hoặc lưu lượng tới thiết bị còn lại.

Không coi bản sao cấu hình riêng lẻ là một kế hoạch phục hồi toàn mạng.

## 14. Ví dụ: thay ACL cho đường quản trị

Một đội cần thay ACL trên hai thiết bị lab để chỉ cho phép nguồn quản trị được chọn. Thay đổi có thể ảnh hưởng chính đường proxy tới thiết bị.

### 14.1. Kế hoạch minh họa

~~~yaml
change_id: NET-LAB-042
plan_version: 3
purpose: Restrict management access on two lab devices
targets:
  - device_id: router-lab-a
    baseline_ref: baseline-lab-a-17
    change_ref: rendered-change-a-3
  - device_id: switch-lab-b
    baseline_ref: baseline-lab-b-09
    change_ref: rendered-change-b-3
execution:
  order:
    - router-lab-a
    - switch-lab-b
  stop_on:
    - baseline_mismatch
    - unknown_apply_result
    - management_health_failure
verification:
  - confirm_expected_configuration
  - confirm_allowed_management_path
  - confirm_disallowed_path_is_blocked
  - confirm_relevant_service_health
recovery:
  path_ref: approved-lab-out-of-band-runbook
~~~

Đây là mô hình kế hoạch, không phải định dạng của thiết bị hoặc sản phẩm PAM. Các tham chiếu phải trỏ tới bản được bảo vệ khỏi thay đổi ngoài thẩm quyền.

### 14.2. Trước khi thực hiện

Proxy xác minh hai thiết bị, baseline và đường ngoài băng. Người duyệt xem bản render cuối cùng và những kiểm tra được dùng.

Nếu cấu hình đang chờ của router chứa phần không thuộc kế hoạch, dừng để xác định ownership; không tự discard cho “sạch”.

### 14.3. Thực hiện trên thiết bị đầu tiên

Chọn cơ chế áp dụng tương ứng capability. Nếu có cơ chế phục hồi có thời hạn được hỗ trợ và đã kiểm thử, sử dụng theo kế hoạch.

Kiểm tra không chỉ đường từ proxy mà cả đường quản trị hợp lệ khác và một đường phải bị chặn. Đánh giá chức năng mạng liên quan.

### 14.4. Mất phản hồi

Nếu mất kết nối sau khi gửi thay đổi, ghi trạng thái chưa rõ. Dùng đường quan sát hoặc khôi phục đã chuẩn bị để xác minh.

Không đánh dấu thất bại rồi tự gửi lại; cũng không xác nhận thay đổi chỉ vì một nguồn giám sát vẫn xanh.

### 14.5. Hoàn tất batch

Chỉ chuyển sang thiết bị thứ hai khi đạt điều kiện. Sau cả hai, đối chiếu cấu hình thực tế, tính lưu bền theo thiết bị và trạng thái dịch vụ.

Báo cáo nên nêu kết quả từng thiết bị, phần đã xác nhận và ngoại lệ còn mở.

## 15. Mã giả cho bộ điều phối

~~~text
apply_network_change(actor, request_id):
    request = load_protected_request(request_id)
    plan = load_approved_plan(request.plan_version)

    authorize(actor, plan.targets, plan.actions)
    verify_approval_and_window(request, plan)
    establish_job_ownership(request)

    for target in plan.execution_order:
        verify_job_still_authorized(request)
        verify_remote_device_identity(target)

        capability = inspect_supported_operations(target)
        observed = inspect_configuration_and_pending_changes(target)

        require_expected_baseline(observed, plan)
        require_no_unowned_changes(observed)
        acquire_supported_coordination(target)

        mode = choose_preapproved_apply_mode(capability, plan)
        result = apply_approved_payload(target, mode)

        if result.is_uncertain:
            record_needs_reconciliation(target)
            stop_expansion_to_next_target()
            reconcile_before_retry()
            return

        verify_configuration_and_network_behavior(target)

        if mode.requires_confirmation:
            require_confirmation_conditions(plan, target)
            confirm_using_correct_job_context(target)

        verify_required_persistence(target)
        release_only_owned_coordination(target)
        record_target_result_without_secrets(target)

    close_temporary_access(request)
    verify_final_state_and_evidence(request)
~~~

Đây là mã giả, không phải script để chạy trên thiết bị. Hệ thống thật cần xử lý lỗi ở từng bước, bao gồm thất bại khi lưu bằng chứng, đóng phiên hoặc giải phóng tài nguyên quản trị.

Một lỗi giữa quy trình không nên làm mất thông tin về phần đã áp dụng.

## 16. Audit và bảo vệ cấu hình nhạy cảm

### 16.1. Chuỗi bằng chứng cần có

| Nhóm | Nội dung |
|---|---|
| Danh tính | Người yêu cầu, người duyệt, người thực hiện |
| Kế hoạch | Phiên bản, thiết bị, payload và baseline được duyệt |
| Cấp quyền | Danh tính downstream, thời hạn và mã liên kết |
| Phiên | Điểm mở/đóng và giao thức |
| Thao tác | Yêu cầu, phản hồi, kết quả từng giai đoạn |
| Trạng thái | Cấu hình trước/sau theo phạm vi được phép lưu |
| Xác minh | Kết quả kiểm tra đường quản trị và dịch vụ |
| Phục hồi | Quyết định, kết quả và phần chưa rõ |
| Kết thúc | Quyền, credential, phiên và ngoại lệ |

### 16.2. Transcript không luôn là cấu hình cuối

Một lệnh đã được gửi không chứng minh thiết bị chấp nhận. Một phản hồi thành công cũng có thể chỉ chứng minh một bước của quy trình.

Cần kết hợp audit proxy, audit thiết bị và quan sát trạng thái. Nếu thiết bị chỉ thấy tài khoản proxy, giữ liên kết tới danh tính cá nhân ở nơi đáng tin cậy.

### 16.3. Cấu hình có thể là dữ liệu mật

Bản sao, diff và transcript có thể chứa secret, thông tin topology hoặc cấu hình bảo vệ. Không lưu tất cả ở một kho log mọi người đều đọc được.

Có thể cần tách metadata vận hành khỏi artifact đầy đủ được mã hóa và phân quyền riêng. Làm sạch dữ liệu ở nơi phân tích không tự bảo vệ các bản thô đã lưu trước đó.

### 16.4. Cảnh báo hữu ích

- Thao tác ngoài thiết bị hoặc phạm vi được duyệt.
- Baseline khác trước lúc áp dụng.
- Có phiên trực tiếp ngoài đường quản lý.
- Thay cấu hình AAA, audit hoặc chính proxy.
- Kết quả áp dụng chưa rõ quá hạn.
- Thiết bị đang chờ xác nhận nhưng không còn owner.
- Quyền tạm thời hoặc credential chưa đóng.
- Cấu hình thực tế lệch nguồn mong muốn.

Mỗi cảnh báo cần owner và bước xử lý, không chỉ ghi thêm một dòng vào dashboard.

## 17. Đóng quyền và đường khẩn cấp

### 17.1. Đóng phiên không tự hoàn nguyên cấu hình

Kết thúc phiên CLI hoặc API không có nghĩa cấu hình vừa thay biến mất. Ngược lại, một cơ chế xác nhận có thời hạn có thể làm cấu hình quay lại theo điều kiện của nó.

Runbook cần biết đúng mô hình, thay vì coi logout là một cách rollback chung.

### 17.2. Xử lý credential và khả năng tạo phiên mới

Khi công việc kết thúc, chặn cấp mới ngoài cửa sổ, đóng những phiên liên quan và xử lý credential đã được tiết lộ hoặc cần thay theo chính sách.

Thu hồi ở proxy không tự chứng minh một credential được sao chép trước đó không còn dùng trực tiếp tại thiết bị. Phải kiểm tra cả phía đích và các đường quản trị được phép.

### 17.3. Đường ngoài băng vẫn thuộc PAM

Console server, tài khoản cục bộ hoặc đường quản trị khẩn cấp cần owner, credential, phê duyệt và audit phù hợp.

Không để mọi kiểm soát phụ thuộc vào chính đường mạng đang được thay đổi. Nhưng cũng không biến đường dự phòng thành lối truy cập không được quản lý.

### 17.4. Không đóng hồ sơ khi còn trạng thái không rõ

Nếu chưa xác minh được cấu hình, trạng thái lưu bền, phiên hoặc phục hồi, báo cáo phải nêu phần đó và người chịu trách nhiệm.

Một batch có thể hoàn tất kỹ thuật một phần; trạng thái tổng phải phản ánh đúng phần còn mở.

## 18. Kiểm thử triển khai proxy

Các kiểm thử nên dùng thiết bị lab hoặc thay đổi được phê duyệt với phạm vi kiểm soát.

| Ca kiểm thử | Kết quả cần chứng minh |
|---|---|
| Người chưa được duyệt mở phiên | Không nhận quyền ngoài chính sách |
| Chọn thiết bị sai | Bị từ chối hoặc phát hiện trước thao tác |
| Host key/chứng chỉ không khớp | Không âm thầm cấp credential |
| Đổi payload sau phê duyệt | Yêu cầu bị đánh giá lại |
| Baseline bị thay bởi phiên khác | Không ghi đè mù quáng |
| Có candidate không thuộc công việc | Không tự commit hoặc xóa |
| Mất kết nối sau khi gửi | Chuyển đối soát trước retry |
| Proxy chuyển node HA | Tiếp tục theo ownership và trạng thái được xác minh |
| Mất đường quản trị do cấu hình | Cơ chế phục hồi hoạt động theo kế hoạch |
| Thiết bị không hỗ trợ capability dự kiến | Dừng hoặc dùng phương án đã được duyệt |
| Thất bại ở thiết bị giữa batch | Báo cáo trạng thái từng thiết bị và xử lý từng phần |
| Người dùng thử đường khác | Quyền và giám sát bao phủ theo thiết kế |
| Transcript chứa dữ liệu giả nhạy cảm | Không lộ sang nơi lưu ngoài quyền |
| Công việc hết hạn | Không còn khả năng ngoài chính sách chưa được xử lý |

Không chỉ kiểm tra “kết nối qua proxy được”. Cần chứng minh các giới hạn và khả năng phục hồi khi có lỗi.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Coi proxy là một tunnel đủ cho PAM | Chưa kiểm soát nội dung và quyền | Xác định năng lực từng lớp |
| Ghi hình rồi cho tài khoản toàn quyền | Có bằng chứng nhưng vẫn gây hậu quả lớn | Giới hạn quyền tại proxy và đích |
| Chỉ cấm một số chuỗi CLI | Có thể bỏ sót ngữ cảnh hoặc đường thay thế | Kiểm thử theo nền tảng và model |
| Không kiểm tra danh tính thiết bị | Có thể thao tác hoặc cấp credential sai đích | Quản lý trust đầu xa |
| Duyệt template nhưng không kiểm soát đầu vào | Payload thực khác kế hoạch | Gắn duyệt với bản render hoặc ràng buộc cụ thể |
| Commit cả vùng đang có thay đổi người khác | Áp dụng phần chưa được duyệt | Kiểm tra ownership và điều phối |
| Nghĩ mọi thiết bị hỗ trợ confirmed commit | Phục hồi không như kế hoạch | Kiểm tra capability và diễn tập |
| Xác nhận chỉ vì kết nối còn sống | Bỏ sót lỗi data plane | Kiểm tra hành vi mạng liên quan |
| Retry ngay khi timeout | Ghi trùng hoặc ghi đè | Đối soát trạng thái trước |
| Coi nhiều thiết bị là một transaction | Báo cáo sai trạng thái hỗn hợp | Quản lý kết quả và phục hồi từng phần |
| Bản backup có nhưng không có đường đưa lại | Không phục hồi được lúc mất kết nối | Kiểm thử đường khẩn cấp |
| Log mọi cấu hình ở nơi đọc rộng | Lộ secret và topology | Phân loại và bảo vệ artifact |
| Đóng phiên rồi coi quyền đã hết | Có thể còn credential dùng trực tiếp | Xác minh phía đích và đường cấp mới |

## 20. Thực hành

### Bài tập 1: Đánh giá năng lực proxy

Một hệ thống mở SSH, lấy mật khẩu từ vault và ghi transcript. Nó không phân tích cấu hình.

Hãy chỉ ra hệ thống đã kiểm soát được gì và chưa kiểm soát được gì. Đề xuất những kiểm tra cần có trước khi dùng nó cho thay đổi firewall sản xuất.

### Bài tập 2: Thiết kế kế hoạch thay ACL

Một thay đổi có thể ảnh hưởng đường từ proxy tới router.

Hãy lập điều kiện đầu vào, bản cấu hình cần duyệt, phép kiểm tra sau thay đổi và đường phục hồi. Giải thích vì sao chỉ ping từ proxy chưa đủ để xác nhận toàn bộ mục tiêu.

### Bài tập 3: Xử lý timeout

Proxy mất phản hồi ngay sau khi gửi cấu hình. Thiết bị có thể đã áp dụng và có thể đang chờ xác nhận.

Hãy thiết kế trạng thái công việc, thông tin cần đối soát và hành động không được thực hiện mù quáng. Nêu cách bàn giao khi proxy chuyển sang node khác.

### Bài tập 4: Phát hiện thay đổi đồng thời

Kế hoạch được duyệt theo baseline A, nhưng trước khi chạy, một người khác đã tạo thay đổi B.

Hãy mô tả cách phát hiện, giữ nguyên phần của người khác và quyết định duyệt lại. Phân biệt khóa của proxy với cơ chế điều phối tại thiết bị.

### Bài tập 5: Báo cáo batch một phần

Hai thiết bị đã đạt trạng thái mong muốn, thiết bị thứ ba chưa rõ kết quả và thiết bị thứ tư chưa được xử lý.

Hãy viết báo cáo kết quả, owner và bước tiếp theo mà không gọi cả batch là thành công hoặc thất bại đồng nhất.

## 21. Điểm cần ghi nhớ

Network configuration proxy có giá trị khi kết nối danh tính, quyền, kế hoạch thay đổi và bằng chứng thực thi. Chỉ chuyển tiếp lưu lượng hoặc lưu transcript chưa đủ để bảo đảm cấu hình đúng phạm vi.

Một thiết kế PAM đầy đủ kiểm tra thiết bị, capability, baseline và ownership, rồi xác minh cả cấu hình lẫn hoạt động mạng. Timeout, thay đổi đồng thời và mất đường quản trị phải có trạng thái rõ và phương án phục hồi trước khi hệ thống được dùng cho thay đổi quan trọng.

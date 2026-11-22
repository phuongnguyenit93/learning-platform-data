# Kiểm tra hành trình có xác thực, dữ liệu và tác dụng phụ

Một hành trình đầu cuối chỉ được xác nhận thành công khi người dùng phù hợp có thể hoàn thành công việc trong điều kiện xác thực thực tế, dữ liệu được lưu đúng và các tác dụng phụ phát sinh đúng theo quy tắc nghiệp vụ. Một màn hình hiển thị thông báo thành công chưa đủ chứng minh giao dịch đã hoàn tất. Tương tự, API trả về mã thành công chưa bảo đảm quyền truy cập được áp dụng đúng, dữ liệu không bị ghi trùng hoặc thông báo đã được gửi đúng người.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, kiểm thử hệ thống và E2E cần kết hợp ba lớp bằng chứng: **xác thực và quyền**, **trạng thái dữ liệu**, và **tác dụng phụ**. Nhóm phải theo dõi được hành trình từ điểm bắt đầu đến kết quả cuối, kể cả các tương tác bất đồng bộ và các hệ thống phụ thuộc. Mục tiêu là xác nhận sản phẩm thực hiện đúng công việc mà người dùng và doanh nghiệp mong đợi, đồng thời không tạo ra tác động ngoài ý muốn.

## 1. Xác định hành trình và ranh giới cần kiểm tra

### Phân biệt kiểm thử hệ thống và kiểm thử đầu cuối

Kiểm thử hệ thống đánh giá hệ thống đã tích hợp trong cấu hình được xác định. Kiểm thử đầu cuối (end-to-end, E2E) đi theo một luồng nghiệp vụ qua các thành phần và ranh giới cần thiết để xác minh kết quả có ý nghĩa với người dùng hoặc doanh nghiệp.

Hai cách kiểm thử có thể sử dụng cùng một môi trường và một số kịch bản. Điểm khác biệt chính nằm ở mục tiêu và phạm vi:

| Góc nhìn | Kiểm thử hệ thống | Kiểm thử E2E |
|---|---|---|
| Phạm vi | Hành vi và yêu cầu của hệ thống đã tích hợp | Một hành trình hoặc giao dịch xuyên suốt các thành phần liên quan |
| Điểm bắt đầu | Có thể bắt đầu từ giao diện, API hoặc một điểm vào hệ thống | Thường bắt đầu từ tác nhân hoặc sự kiện nghiệp vụ đại diện |
| Kết quả | Hệ thống đáp ứng yêu cầu trong cấu hình đã chọn | Người dùng hoặc quy trình đạt được kết quả cuối mong muốn |
| Bằng chứng | Hành vi chức năng, phi chức năng, trạng thái và cấu hình | Trạng thái cuối, dữ liệu, quyền và tác dụng phụ trên toàn hành trình |
| Ví dụ | Kiểm tra hệ thống quản lý đơn hàng đáp ứng quy tắc và hiệu năng | Người mua đặt hàng, thanh toán, nhận xác nhận và xem được trạng thái đơn |

Một bài E2E không nhất thiết phải kiểm tra mọi dịch vụ của tổ chức. Phạm vi nên bao gồm các thành phần có ảnh hưởng đến hành trình và kết quả cần xác thực. Những hệ thống ngoài phạm vi có thể được mô phỏng hoặc kiểm tra qua hợp đồng, nhưng giới hạn đó phải được ghi rõ.

### Chọn hành trình có giá trị và rủi ro cao

Bắt đầu từ mục tiêu người dùng và kết quả kinh doanh. Các hành trình thường đáng ưu tiên gồm:

- Đăng ký, xác minh danh tính và kích hoạt tài khoản.
- Đăng nhập, làm mới phiên và khôi phục quyền truy cập.
- Tạo, sửa, phê duyệt hoặc hủy một giao dịch quan trọng.
- Thanh toán, hoàn tiền, gia hạn hoặc thay đổi thuê bao.
- Mời thành viên, phân quyền và quản lý dữ liệu theo tenant.
- Gửi nội dung, tải tệp hoặc thực hiện quy trình có tác dụng phụ bên ngoài.
- Hoàn thành công việc cần nhiều dịch vụ và xử lý bất đồng bộ.

Ưu tiên dựa trên tần suất, mức tác động, khả năng xảy ra lỗi, độ phức tạp tích hợp, độ bất định và khả năng phục hồi. Một hành trình ít xảy ra nhưng có thể làm lộ dữ liệu hoặc ghi nhận sai giao dịch vẫn cần được kiểm tra kỹ.

### Xác định điểm bắt đầu, điểm kết thúc và các ranh giới

Với mỗi hành trình, ghi rõ:

1. Tác nhân khởi tạo: người dùng, lịch chạy, webhook hay hệ thống khác.
2. Điều kiện trước: tài khoản, vai trò, trạng thái, dữ liệu và cấu hình cần có.
3. Các bước nghiệp vụ: hành động, phản hồi và chuyển trạng thái.
4. Thành phần tham gia: giao diện, API, dịch vụ, database, cache, queue và nhà cung cấp.
5. Điểm đồng bộ và bất đồng bộ: nơi người dùng chờ phản hồi và nơi xử lý tiếp diễn sau đó.
6. Điều kiện hoàn thành: trạng thái nghiệp vụ có thẩm quyền và tác dụng phụ cần thiết.
7. Nhánh lỗi: điều kiện từ chối, timeout, retry, hủy và phục hồi.

Một sơ đồ đơn giản có thể giúp nhóm thống nhất ranh giới:

~~~mermaid
flowchart LR
    U["Người dùng"] --> UI["Giao diện"]
    UI --> API["API / Backend"]
    API --> AUTH["Dịch vụ xác thực"]
    API --> DB[("Database")]
    API --> Q[["Queue / Event"]]
    Q --> W["Worker"]
    W --> DB
    W --> EXT["Dịch vụ bên ngoài"]
    DB --> READ["API đọc trạng thái"]
    READ --> UI
    EXT --> CB["Webhook / Callback"]
    CB --> API
~~~

Sơ đồ chỉ minh họa một mô hình. Hãy điều chỉnh theo kiến trúc thực tế, đặc biệt là nguồn dữ liệu có thẩm quyền, nơi kiểm tra quyền, nơi tạo tác dụng phụ và cơ chế nhận kết quả bất đồng bộ.

## 2. Xác thực danh tính và quyền truy cập trong hành trình

### Chuẩn bị danh tính đại diện

Kiểm thử cần sử dụng tài khoản đại diện cho vai trò thực tế. Không nên dùng một tài khoản quản trị duy nhất cho mọi kịch bản vì cách đó có thể che giấu lỗi phân quyền.

Một bộ danh tính có thể gồm:

| Danh tính | Vai trò | Mục tiêu xác thực |
|---|---|---|
| Người dùng chưa đăng nhập | Anonymous | Chỉ truy cập chức năng công khai; được chuyển đến luồng đăng nhập khi cần |
| Người dùng thông thường | Member | Chỉ thao tác trên dữ liệu và chức năng được cấp |
| Người quản trị tenant | Tenant admin | Quản lý thành viên và cấu hình trong đúng tenant |
| Người phê duyệt | Approver | Phê duyệt giao dịch thuộc phạm vi trách nhiệm |
| Người dùng tenant khác | External tenant member | Không thể đọc hoặc sửa dữ liệu tenant đang kiểm thử |
| Tài khoản bị khóa hoặc thu hồi | Disabled user | Không thể tiếp tục hành động được bảo vệ |

Danh tính cần có thông tin xác định vai trò, tenant, trạng thái tài khoản và quyền. Dữ liệu thử nghiệm phải được tạo theo quy trình được phép, không sử dụng mật khẩu, token hoặc thông tin cá nhân thật của khách hàng.

### Xác minh đăng nhập và vòng đời phiên

Một hành trình được xác thực thường phụ thuộc vào cookie phiên, access token, refresh token hoặc cơ chế định danh liên kết. Kiểm thử cần xem xét:

- Đăng nhập thành công với thông tin xác thực hợp lệ.
- Thông tin xác thực sai, tài khoản không tồn tại hoặc bị khóa.
- Token hết hạn, bị thu hồi hoặc sai chữ ký.
- Làm mới token khi phiên còn hiệu lực và khi refresh token hết hạn.
- Đăng xuất và vô hiệu hóa phiên theo chính sách.
- Mở nhiều phiên hoặc đăng nhập từ nhiều thiết bị nếu sản phẩm hỗ trợ.
- Phiên bị thu hồi trong khi người dùng đang thực hiện hành trình.
- Điều hướng về trang yêu cầu đăng nhập và quay lại đúng điểm sau khi đăng nhập.

Không chỉ kiểm tra giao diện chuyển sang trạng thái đã đăng nhập. Cần xác minh request được gửi với danh tính đúng, backend xác thực token hoặc phiên, và hành động được thực thi trong phạm vi quyền tương ứng.

### Kiểm tra quyền ở từng ranh giới

Quyền có thể được kiểm tra ở giao diện, API, dịch vụ nghiệp vụ và database. Ẩn nút trên giao diện không phải là kiểm soát bảo mật đầy đủ. Người dùng vẫn có thể gửi request trực tiếp.

Với mỗi hành động, hãy xác định:

- Ai được phép thực hiện?
- Trên tài nguyên nào và trong tenant nào?
- Điều kiện trạng thái nào phải thỏa mãn?
- Có cần vai trò, quyền cụ thể hoặc quan hệ sở hữu không?
- Khi quyền thay đổi, hiệu lực được áp dụng ngay hay sau một khoảng đồng bộ?
- Hành vi khi bị từ chối có làm lộ dữ liệu hay thông tin nội bộ không?

Kịch bản nên bao gồm cả quyền hợp lệ và không hợp lệ. Ví dụ, thành viên có thể xem đơn hàng của tenant mình nhưng không thể sửa phương thức thanh toán; quản trị viên tenant A không thể xem thành viên hoặc đơn hàng của tenant B.

### Xác minh quyền theo thời gian và trạng thái

Một lỗi thường bị bỏ qua là quyền thay đổi trong khi phiên vẫn còn hiệu lực. Ví dụ, quản trị viên thu hồi vai trò của một thành viên, nhưng cache hoặc token cũ vẫn cho phép thành viên thực hiện hành động.

Kiểm thử các tình huống:

- Vai trò bị thay đổi sau khi đăng nhập.
- Thành viên bị xóa khỏi tenant trong lúc phiên còn hiệu lực.
- Quyền phê duyệt bị thu hồi trước khi người dùng xác nhận.
- Tài khoản bị khóa khi có request đang chờ.
- Phiên cũ được sử dụng sau khi đăng xuất hoặc thu hồi.
- Dữ liệu cache phân quyền chưa được invalidation.

Tiêu chí cần phản ánh chính sách thực tế về thời điểm quyền có hiệu lực. Không giả định mọi hệ thống đều thu hồi token tức thời; hãy kiểm tra cam kết và giới hạn được thiết kế.

## 3. Chuẩn bị dữ liệu và trạng thái trước khi chạy

### Xác định dữ liệu đầu vào và nguồn có thẩm quyền

Mỗi kịch bản cần mô tả dữ liệu trước khi chạy, dữ liệu do hành trình tạo ra và nơi dùng để xác minh kết quả. Ví dụ, với giao dịch thanh toán, database nghiệp vụ có thể là nguồn có thẩm quyền cho trạng thái đơn hàng; nhà cung cấp thanh toán là nguồn xác nhận giao dịch; cache chỉ là bản sao phục vụ đọc.

Một bộ dữ liệu cần xác định:

- ID tài khoản, tenant và vai trò.
- ID tài nguyên, đơn hàng, giao dịch hoặc quy trình.
- Trạng thái ban đầu và quan hệ giữa các bản ghi.
- Dữ liệu hợp lệ, dữ liệu biên và dữ liệu cần bị từ chối.
- Phiên bản cấu hình, chính sách và feature flag.
- Các bản ghi liên quan trong queue, outbox hoặc hệ thống phụ thuộc.

Dùng ID duy nhất cho mỗi lần chạy để có thể truy vết và tránh va chạm với lần chạy khác.

### Tạo fixture có thể lặp lại

Fixture là dữ liệu và trạng thái được chuẩn bị để kịch bản có thể chạy nhất quán. Một fixture tốt có thể được tạo lại từ đầu, có quan hệ rõ và không phụ thuộc vào kết quả của lần chạy trước.

Nên xác định:

1. Setup tạo tài khoản, quyền, tenant và dữ liệu ban đầu.
2. Cách xác minh setup đã hoàn tất.
3. ID hoặc nhãn liên kết với lần chạy.
4. Điều kiện dọn dẹp và dữ liệu cần giữ lại để điều tra.
5. Cách xử lý khi setup dừng giữa chừng.

Không dùng tài khoản dùng chung có trạng thái bị thay đổi liên tục bởi nhiều suite. Nếu môi trường buộc phải dùng dữ liệu chung, cần khóa phạm vi hoặc dùng namespace riêng cho từng lần chạy.

### Tránh phụ thuộc vào thứ tự chạy

Mỗi kịch bản nên độc lập hoặc khai báo rõ phụ thuộc. Một bài kiểm thử không nên thành công chỉ vì bài trước tình cờ tạo sẵn dữ liệu.

Kiểm tra bằng cách chạy riêng từng kịch bản và chạy theo thứ tự khác nhau. Nếu có chuỗi hành trình nhiều bước, hãy xác định đó là một kịch bản E2E duy nhất hay một nhóm kịch bản có trạng thái được quản lý rõ.

### Quản lý dữ liệu nhạy cảm

Dùng dữ liệu tổng hợp hoặc đã khử định danh. Tránh đưa mật khẩu, token, số thẻ, thông tin cá nhân hoặc bí mật nhà cung cấp vào mã kiểm thử, log, ảnh chụp và báo cáo.

Với dữ liệu có tác dụng phụ thật như gửi email hoặc tạo giao dịch, chỉ dùng sandbox, tài khoản thử nghiệm và địa chỉ nhận được phép. Cần xác định thời hạn lưu, người có quyền truy cập và cách xóa dữ liệu sau khi hoàn tất.

## 4. Xác minh trạng thái dữ liệu sau hành trình

### Kiểm tra dữ liệu được lưu đúng

Sau khi hoàn tất hành trình, kiểm tra trạng thái ở nguồn có thẩm quyền. Tùy nghiệp vụ, có thể xác minh:

- Bản ghi chính được tạo hoặc cập nhật đúng một lần.
- Trường dữ liệu, quan hệ và trạng thái đúng với yêu cầu.
- Thời điểm tạo, cập nhật và người thực hiện chính xác.
- Tenant, chủ sở hữu và phạm vi truy cập được gán đúng.
- Các bản ghi liên quan được tạo, cập nhật hoặc giữ lại theo quy tắc.
- Không có dữ liệu dở dang hoặc trạng thái mâu thuẫn.

Ví dụ, sau khi người dùng tạo đơn hàng, kiểm tra đơn có đúng người mua, sản phẩm, số lượng, giá, tiền tệ và trạng thái. Không chỉ kiểm tra trang chi tiết hiển thị các giá trị đó; hãy xác minh dữ liệu lưu và các quan hệ liên quan.

### Xác minh tính toàn vẹn và bất biến nghiệp vụ

Một số điều kiện cần đúng xuyên suốt hành trình. Ví dụ:

- Một giao dịch thanh toán chỉ được ghi nhận một lần theo khóa nghiệp vụ.
- Tổng tiền đơn hàng bằng tổng các thành phần theo quy tắc làm tròn.
- Đơn hàng không thể ở trạng thái đã giao nếu chưa qua các bước bắt buộc.
- Thành viên chỉ thuộc tenant được mời.
- Số dư hoặc số lượng tồn kho không xuống dưới giới hạn cho phép.
- Một yêu cầu bị từ chối không tạo ra tác dụng phụ không được phép.

Những điều kiện này thường được gọi là invariant hoặc bất biến nghiệp vụ. Hãy kiểm tra trước và sau hành trình, kể cả khi có lỗi giữa chừng.

### Kiểm tra tính nhất quán giữa nhiều nơi lưu trữ

Một hành trình có thể cập nhật database, cache, search index, data warehouse và hệ thống bên ngoài. Không phải tất cả nơi đều cập nhật đồng bộ.

Cần xác định:

- Nguồn dữ liệu có thẩm quyền cho từng trạng thái.
- Thời gian đồng bộ tối đa được chấp nhận.
- Trạng thái trung gian mà người dùng có thể nhìn thấy.
- Cách phát hiện bản sao bị lệch hoặc cập nhật bị mất.
- Quy trình đối soát và đồng bộ lại.

Nếu hệ thống dùng eventual consistency, không nên khẳng định mọi bản sao phải giống nhau ngay sau request. Hãy xác định điều kiện chờ có giới hạn và tiêu chí hội tụ. Kiểm thử phải thất bại khi quá thời hạn mà trạng thái vẫn không nhất quán.

### Kiểm tra dữ liệu không được tạo hoặc thay đổi

Kiểm thử chỉ xác nhận dữ liệu mong đợi xuất hiện là chưa đủ. Hãy kiểm tra những gì không được phép xảy ra:

- Không tạo đơn hàng hoặc giao dịch trùng.
- Không cấp quyền ngoài phạm vi.
- Không thay đổi dữ liệu tenant khác.
- Không gửi thông báo khi giao dịch bị từ chối.
- Không ghi dữ liệu nhạy cảm vào trường hoặc log không phù hợp.
- Không để lại bản ghi tạm, lock hoặc trạng thái chờ vô hạn.

Các kiểm tra phủ định này đặc biệt quan trọng với hành trình có phân quyền hoặc tác dụng phụ.

## 5. Xác minh tác dụng phụ của hành trình

### Phân biệt kết quả chính và tác dụng phụ

Kết quả chính là trạng thái nghiệp vụ mà hành trình cần tạo ra, ví dụ đơn hàng được xác nhận. Tác dụng phụ là hành động phát sinh từ kết quả đó, như gửi email, phát sự kiện, trừ tồn kho, tạo hóa đơn, cập nhật chỉ mục tìm kiếm hoặc gọi nhà cung cấp.

Một tác dụng phụ có thể đồng bộ hoặc bất đồng bộ. Nó có thể thành công, thất bại, được retry hoặc đến muộn. Nhóm cần xác định tác dụng phụ nào là bắt buộc để coi hành trình hoàn tất và tác dụng phụ nào có thể xử lý sau.

| Tác dụng phụ | Điều cần xác minh |
|---|---|
| Gửi email hoặc SMS | Đúng người nhận, nội dung, mẫu, trạng thái và số lần gửi |
| Phát sự kiện | Đúng loại sự kiện, payload, ID, thời điểm và số lần phát |
| Trừ tồn kho | Đúng mặt hàng, số lượng và không trừ lặp |
| Tạo hóa đơn | Đúng khách hàng, số tiền, thuế, tiền tệ và liên kết giao dịch |
| Cập nhật cache hoặc search index | Dữ liệu được làm mới trong giới hạn thời gian |
| Gọi dịch vụ bên ngoài | Đúng endpoint, dữ liệu, quyền và trạng thái phản hồi |
| Ghi audit log | Đúng người thực hiện, hành động, tài nguyên và thời điểm |

### Kiểm tra số lần và người nhận của tác dụng phụ

Một tác dụng phụ có thể đúng nội dung nhưng sai số lần hoặc sai đối tượng. Với email, cần kiểm tra địa chỉ nhận, template, biến dữ liệu và số lần gửi. Với webhook, cần kiểm tra chữ ký, event ID và trạng thái giao nhận. Với thanh toán, cần xác minh số tiền và mã tham chiếu.

Dùng sandbox hoặc sink test để quan sát tác dụng phụ. Không gửi email, SMS, giao dịch hoặc thông báo thật đến người không tham gia kiểm thử nếu chưa được cho phép.

### Kiểm tra thứ tự và điều kiện phát sinh

Tác dụng phụ chỉ nên xảy ra khi điều kiện nghiệp vụ thỏa mãn. Ví dụ, chỉ gửi email xác nhận thanh toán sau khi trạng thái thanh toán được xác nhận; không gửi email thành công khi giao dịch mới ở trạng thái đang xử lý.

Kiểm thử:

- Sự kiện được phát sau khi thay đổi nghiệp vụ commit.
- Tác dụng phụ không xảy ra nếu transaction rollback.
- Tác dụng phụ không phát sinh khi request bị từ chối.
- Sự kiện đến trễ không làm trạng thái lùi.
- Một lần retry không tạo tác dụng phụ trùng.
- Tác dụng phụ lỗi có được ghi nhận và xử lý lại không.

Với xử lý bất đồng bộ, hãy kiểm tra cả trạng thái tạm thời và trạng thái cuối. Một API có thể trả về mã 202 Accepted nghĩa là đã tiếp nhận yêu cầu, không có nghĩa tác vụ đã hoàn tất.

### Xác minh audit trail

Audit log giúp truy vết ai đã thực hiện hành động nào, trên tài nguyên nào và khi nào. Với hành trình quan trọng, kiểm tra:

- Actor và danh tính được ghi đúng.
- Hành động và tài nguyên có định danh chính xác.
- Thời điểm và correlation ID có thể nối với các sự kiện khác.
- Trường dữ liệu nhạy cảm được che giấu hoặc loại bỏ.
- Bản ghi audit không bị mất khi có lỗi.
- Người dùng không có quyền sửa hoặc xóa log ngoài chính sách.

Audit log cần phản ánh sự kiện nghiệp vụ thực tế, không chỉ ghi nhận request đã được gửi.

## 6. Kiểm tra luồng bất đồng bộ và trạng thái trung gian

### Theo dõi từ tiếp nhận đến hoàn tất

Một hành trình có thể trả phản hồi trước khi worker hoàn tất công việc. Ví dụ, người dùng gửi yêu cầu xuất báo cáo; API tạo job và trả mã tác vụ; worker xử lý dữ liệu; hệ thống cập nhật trạng thái và gửi thông báo khi xong.

Cần xác minh các trạng thái:

- Đã tiếp nhận.
- Đang chờ xử lý.
- Đang xử lý.
- Hoàn thành.
- Thất bại có thể thử lại.
- Thất bại cuối cùng hoặc cần can thiệp.
- Đã hủy nếu nghiệp vụ hỗ trợ.

Mỗi trạng thái phải có ý nghĩa và chuyển tiếp hợp lệ. Không để trạng thái chờ kéo dài vô hạn mà không cảnh báo hoặc cơ chế phục hồi.

### Kiểm tra polling, webhook và thông báo

Nếu giao diện polling để lấy trạng thái, kiểm tra khoảng thời gian, giới hạn retry, xử lý timeout và dừng polling khi đã có kết quả cuối. Nếu hệ thống dùng webhook, kiểm tra chữ ký, xác thực nguồn, sự kiện trùng và sự kiện đến sai thứ tự.

Thông báo nên phản ánh trạng thái có thẩm quyền. Nếu tác vụ thất bại, không gửi thông báo hoàn tất. Nếu kết quả chưa chắc chắn, cần hiển thị trạng thái đang xử lý thay vì suy đoán thành công hoặc thất bại.

### Kiểm tra retry và idempotency xuyên hành trình

Khi request hoặc sự kiện được gửi lại, hành trình không được tạo tác dụng phụ lặp ngoài quy tắc. Kiểm tra:

- Client gửi lại do timeout.
- Gateway retry request.
- Worker xử lý lại sau khi dừng trước ack.
- Webhook từ nhà cung cấp được gửi nhiều lần.
- Người dùng nhấn nút nhiều lần hoặc mở nhiều tab.
- Một sự kiện cũ đến sau sự kiện mới.

Dùng idempotency key, event ID hoặc khóa nghiệp vụ theo thiết kế. Xác minh cùng một thao tác lặp tạo ra một kết quả nghiệp vụ duy nhất, và các lần gọi lại nhận được trạng thái nhất quán.

## 7. Thiết kế oracle cho hành trình E2E

### Không chỉ dựa vào thông báo trên giao diện

Test oracle là cơ sở để xác định kết quả đúng. Một oracle tốt kết hợp nhiều bằng chứng:

- Phản hồi giao diện hoặc API.
- Trạng thái database có thẩm quyền.
- Sự kiện, queue hoặc outbox.
- Tác dụng phụ quan sát được ở sandbox.
- Audit log và trace.
- Trạng thái được trả về từ hệ thống phụ thuộc.

Ví dụ, sau khi hoàn tất thanh toán, cần xác minh giao dịch thành công ở nhà cung cấp sandbox, đơn hàng ở trạng thái đã thanh toán, hóa đơn được tạo đúng, sự kiện phát ra một lần và email xác nhận được gửi đúng người nhận.

Không nên phụ thuộc vào truy vấn database trực tiếp nếu điều đó vi phạm ranh giới hoặc che giấu lỗi API. Dùng giao diện công khai hoặc công cụ kiểm tra được phê duyệt cho từng loại bằng chứng. Truy vấn database chỉ nên là oracle bổ sung khi phù hợp và được phép.

### Dùng điều kiện chờ thay vì thời gian ngủ cố định

Với tác vụ bất đồng bộ, kiểm thử nên chờ một điều kiện cụ thể trong thời hạn xác định. Ví dụ: đợi trạng thái job chuyển sang COMPLETED tối đa 30 giây; nếu quá hạn, báo lỗi kèm trạng thái cuối quan sát được.

Tránh ngủ cố định quá lâu vì làm suite chậm, hoặc ngủ quá ngắn khiến kiểm thử chập chờn. Điều kiện chờ cần có:

- Trạng thái hoặc sự kiện cần quan sát.
- Khoảng thời gian tối đa.
- Tần suất kiểm tra hợp lý.
- Thông tin chẩn đoán khi hết thời gian.
- Hành vi dọn dẹp nếu tác vụ chưa hoàn tất.

Thời hạn cần dựa trên yêu cầu dịch vụ và môi trường, không chọn tùy tiện chỉ để bài kiểm thử chạy xanh.

### Xác minh bất biến xuyên suốt

Một oracle mạnh có thể kiểm tra invariant ở nhiều điểm, không chỉ trạng thái cuối. Ví dụ:

- Người dùng không bao giờ truy cập dữ liệu ngoài tenant.
- Giao dịch không bị ghi nhận thành công trước khi được xác nhận.
- Tổng tiền không thay đổi ngoài các quy tắc đã định.
- Mỗi event ID chỉ tạo tác dụng nghiệp vụ một lần.
- Trạng thái không chuyển lùi khi sự kiện đến muộn.
- Một hành động bị từ chối không tạo audit hoặc tác dụng phụ thành công giả.

Những điều kiện này giúp phát hiện lỗi thoáng qua hoặc trạng thái trung gian nguy hiểm mà kiểm tra cuối cùng có thể bỏ sót.

## 8. Quản lý tác động và dọn dẹp sau kiểm thử

### Phân loại tác dụng phụ theo khả năng đảo ngược

Trước khi chạy, hãy phân loại tác dụng phụ:

- **Dễ đảo ngược:** dữ liệu thử nghiệm có thể xóa, job có thể hủy hoặc cache có thể làm mới.
- **Có thể bù trừ:** giao dịch cần hoàn tiền, đơn hàng cần hủy hoặc sự kiện cần phát hành thao tác bù.
- **Khó hoặc không thể đảo ngược:** email đã gửi ra ngoài, thông báo đã đến người thật, dữ liệu đã được chia sẻ hoặc giao dịch thật đã phát sinh.

Ưu tiên sandbox, tài khoản giả lập và dữ liệu tổng hợp. Với tác dụng phụ không thể đảo ngược, chỉ thực hiện khi có môi trường và quyền rõ ràng. Kịch bản cần ghi rõ đối tượng nhận, phạm vi, giới hạn và cách xử lý nếu chạy nhầm.

### Dọn dẹp có kiểm soát

Sau khi chạy, dọn dữ liệu do test tạo ra theo ID của lần chạy. Cần cân nhắc:

- Bản ghi chính và bản ghi liên quan.
- Cache key và index.
- Message trong queue, outbox hoặc DLQ.
- Tài khoản, phiên và token thử nghiệm.
- Tệp, báo cáo hoặc job đã tạo.
- Giao dịch sandbox và tác dụng phụ có thể hủy.

Không xóa dữ liệu dùng chung hoặc dữ liệu không thuộc lần chạy. Nếu cần giữ lại để điều tra, gắn nhãn, giới hạn quyền truy cập và đặt thời hạn dọn dẹp.

### Bảo đảm dọn dẹp kể cả khi test thất bại

Dọn dẹp nên chạy trong cơ chế teardown hoặc quy trình khôi phục có thể thực hiện lại. Nếu test dừng giữa chừng, cần xác định tài nguyên nào có thể còn sót và cách tìm chúng bằng run ID hoặc correlation ID.

Không để teardown che giấu lỗi chính. Nếu hành trình thất bại và cleanup cũng thất bại, báo cáo cần ghi nhận cả hai để tránh rò rỉ dữ liệu hoặc làm sai kết quả lần chạy sau.

## 9. Xử lý lỗi và nhánh âm tính

### Xác minh hành vi từ chối đúng

Một hành trình tốt không chỉ thành công trong điều kiện hợp lệ mà còn từ chối đúng khi điều kiện không thỏa mãn. Ví dụ:

- Người chưa đăng nhập truy cập tài nguyên được bảo vệ.
- Người dùng tenant khác đọc hoặc sửa tài nguyên.
- Token hết hạn hoặc bị thu hồi.
- Dữ liệu đầu vào sai hoặc thiếu.
- Giao dịch bị từ chối hoặc vượt hạn mức.
- Trạng thái nghiệp vụ không cho phép thực hiện hành động.
- Dịch vụ phụ thuộc không khả dụng.

Với mỗi trường hợp, kiểm tra mã hoặc thông báo lỗi, trạng thái dữ liệu, audit log và tác dụng phụ. Một request bị từ chối không được tạo giao dịch, gửi thông báo thành công hoặc thay đổi quyền ngoài dự kiến.

### Kiểm tra timeout và kết quả không xác định

Timeout không đồng nghĩa thao tác thất bại. Có thể request đã được xử lý nhưng phản hồi bị mất. Với hành trình có tác dụng phụ, cần truy vấn trạng thái hoặc dùng idempotency key trước khi gửi lại.

Ví dụ, người dùng bấm thanh toán, nhà cung cấp xử lý thành công nhưng callback chậm. Giao diện không nên khuyến khích tạo giao dịch mới ngay. Hãy xác minh trạng thái đang xử lý, cơ chế đối soát và cách người dùng tiếp tục.

### Kiểm tra phục hồi sau lỗi giữa chừng

Chủ động gây lỗi tại một số điểm an toàn trong môi trường kiểm thử:

- Sau khi ghi dữ liệu nhưng trước khi phát sự kiện.
- Sau khi consumer thực hiện tác dụng phụ nhưng trước khi ack.
- Sau khi nhà cung cấp hoàn tất nhưng trước khi callback được xử lý.
- Sau khi thu hồi quyền nhưng trước khi cache được cập nhật.
- Khi người dùng đóng trình duyệt hoặc mất kết nối giữa hành trình.

Sau phục hồi, kiểm tra dữ liệu, trạng thái, tác dụng phụ và khả năng tiếp tục. Nếu quy trình cần thao tác bù hoặc hỗ trợ thủ công, xác minh hướng dẫn và quyền thực hiện.

## 10. Ví dụ: hành trình tạo tài khoản, mời thành viên và kích hoạt thuê bao

Giả sử một sản phẩm SaaS cho phép quản trị viên đăng ký, xác minh email, tạo không gian làm việc, mời thành viên và kích hoạt thuê bao bằng thanh toán sandbox.

### Điều kiện trước

- Có tài khoản quản trị viên thử nghiệm chưa được kích hoạt.
- Có tenant riêng cho lần chạy.
- Có địa chỉ email sandbox nhận được thư.
- Có gói thuê bao và giá thử nghiệm đã cấu hình.
- Dịch vụ định danh, đăng ký, thanh toán và thông báo đang ở môi trường kiểm thử.
- Có correlation ID hoặc run ID để theo dõi toàn hành trình.

### Các bước và bằng chứng

| Bước | Hành động | Bằng chứng cần xác minh |
|---|---|---|
| 1 | Đăng ký tài khoản | Tài khoản được tạo ở trạng thái chờ xác minh; không có thuê bao đang hoạt động |
| 2 | Mở liên kết xác minh | Token hợp lệ được chấp nhận; tài khoản chuyển sang trạng thái đã xác minh |
| 3 | Đăng nhập | Phiên được tạo cho đúng tài khoản; quyền ban đầu đúng |
| 4 | Tạo không gian làm việc | Tenant được tạo và gắn đúng chủ sở hữu |
| 5 | Mời thành viên | Lời mời gắn đúng tenant, email và vai trò; email sandbox được gửi một lần |
| 6 | Thành viên chấp nhận | Thành viên được thêm đúng tenant; không thể truy cập tenant khác |
| 7 | Chọn gói và thanh toán sandbox | Giao dịch có đúng số tiền, tiền tệ và tham chiếu; trạng thái không bị đánh dấu thành công quá sớm |
| 8 | Nhận callback thanh toán | Chữ ký và trạng thái được xác minh; callback lặp không tạo giao dịch trùng |
| 9 | Kích hoạt thuê bao | Thuê bao được gắn đúng tenant và thời hạn; audit log ghi đúng actor |
| 10 | Đọc lại trạng thái | Giao diện, API và nguồn dữ liệu có thẩm quyền nhất quán trong giới hạn đã định |

### Các nhánh lỗi cần bổ sung

- Liên kết xác minh hết hạn hoặc đã được sử dụng.
- Email mời không được gửi hoặc lời mời đã tồn tại.
- Thành viên chấp nhận lời mời sau khi lời mời bị thu hồi.
- Quản trị viên mất quyền trong lúc thiết lập.
- Thanh toán bị từ chối hoặc callback đến trễ.
- Callback được gửi lại nhiều lần.
- Dịch vụ kích hoạt thuê bao tạm thời không khả dụng.
- Người dùng đóng trình duyệt sau khi thanh toán được xử lý.
- Thành viên cố truy cập dữ liệu của tenant khác.

Với mỗi nhánh, xác minh trạng thái cuối và các tác dụng phụ. Ví dụ, thanh toán bị từ chối không được kích hoạt thuê bao hoặc gửi email xác nhận thành công. Callback lặp không được tạo nhiều hóa đơn hoặc gia hạn nhiều lần.

## 11. Tính ổn định, khả năng chẩn đoán và thực thi trong pipeline

### Giữ kịch bản E2E đáng tin cậy

E2E thường dễ bị ảnh hưởng bởi mạng, môi trường, dữ liệu và dịch vụ bên ngoài. Để giảm kiểm thử không ổn định:

- Dùng dữ liệu riêng cho mỗi lần chạy.
- Chờ điều kiện nghiệp vụ thay vì chờ số giây cố định.
- Dùng locator và API ổn định, tránh phụ thuộc vào chi tiết giao diện dễ thay đổi.
- Giới hạn phụ thuộc vào dịch vụ bên ngoài bằng sandbox hoặc test double có mục tiêu.
- Làm rõ tiêu chí retry của chính bài kiểm thử; không retry vô hạn để che lỗi.
- Thu thập trace, log, ảnh chụp và trạng thái khi thất bại.
- Dọn dữ liệu bằng run ID để các lần chạy không ảnh hưởng lẫn nhau.

Không nên bỏ qua một bài kiểm thử quan trọng chỉ vì nó thỉnh thoảng thất bại. Hãy phân loại lỗi do sản phẩm, môi trường, dữ liệu hoặc test harness; gán người xử lý và thời hạn.

### Phân chia vòng chạy

Có thể tổ chức:

| Vòng | Phạm vi | Mục đích |
|---|---|---|
| Pull request | Một số hành trình cốt lõi, nhanh, ổn định | Phát hiện lỗi chặn sớm |
| Sau tích hợp | Các hành trình có nhiều dịch vụ và quyền | Xác minh hợp đồng và trạng thái xuyên thành phần |
| Trước phát hành | Bộ E2E đại diện, nhánh lỗi và tác dụng phụ | Hỗ trợ quyết định phát hành |
| Theo lịch hoặc sau triển khai | Kiểm tra smoke, synthetic transaction và tín hiệu vận hành | Phát hiện suy giảm trong môi trường thực |

Không cần chạy toàn bộ kịch bản dài ở mọi thay đổi. Chọn theo rủi ro, thời gian phản hồi và khả năng cô lập. Các kịch bản bảo mật hoặc giao dịch trọng yếu có thể cần chạy ở nhiều vòng.

### Báo cáo kết quả có thể điều tra

Một báo cáo thất bại cần nêu:

- Run ID, phiên bản ứng dụng và môi trường.
- Danh tính, vai trò và tenant thử nghiệm.
- Hành trình, bước thất bại và điều kiện trước.
- Request/response hoặc sự kiện có liên quan, đã loại bỏ dữ liệu nhạy cảm.
- Trạng thái dữ liệu và tác dụng phụ quan sát được.
- Correlation ID, trace và log.
- Trạng thái cleanup.
- Phân loại lỗi và người chịu trách nhiệm.

Báo cáo “bước 5 thất bại” không đủ để điều tra nếu thiếu dữ liệu và trạng thái hệ thống.

## 12. Những sai lầm thường gặp

- **Chỉ kiểm tra thông báo thành công:** không chứng minh trạng thái nghiệp vụ đã được lưu đúng.
- **Dùng tài khoản quản trị cho mọi kịch bản:** che giấu lỗi phân quyền và cách ly tenant.
- **Chỉ kiểm tra quyền trên giao diện:** bỏ sót việc backend không bảo vệ API.
- **Không kiểm tra dữ liệu sau hành trình:** bỏ sót dữ liệu trùng, thiếu hoặc sai quan hệ.
- **Bỏ qua tác dụng phụ:** email, sự kiện, hóa đơn hoặc cập nhật tồn kho có thể sai dù giao diện đúng.
- **Coi mã 202 Accepted là hoàn tất:** công việc bất đồng bộ có thể vẫn đang chờ hoặc thất bại.
- **Không kiểm tra retry và idempotency:** một request lặp có thể tạo nhiều tác dụng phụ.
- **Dùng dữ liệu và tài khoản chung:** tạo phụ thuộc thứ tự và kết quả không ổn định.
- **Chờ bằng thời gian cố định:** làm test chậm hoặc chập chờn khi môi trường biến động.
- **Không xác định nguồn dữ liệu có thẩm quyền:** các bản sao có độ trễ bị hiểu nhầm là lỗi hoặc được chấp nhận sai.
- **Không dọn dẹp sau thất bại:** để lại tài khoản, giao dịch hoặc thông điệp làm ảnh hưởng lần chạy sau.
- **Gửi tác dụng phụ thật ngoài ý muốn:** gây ảnh hưởng đến người dùng hoặc hệ thống bên ngoài.
- **Không thu thập bằng chứng xuyên thành phần:** khó xác định lỗi nằm ở xác thực, dữ liệu, queue hay nhà cung cấp.

## 13. Đầu ra cần có trước khi chốt kiểm thử hành trình

Một kế hoạch kiểm thử hệ thống và E2E đủ dùng nên có:

1. **Mô tả hành trình:** tác nhân, điểm bắt đầu, điểm kết thúc, bước nghiệp vụ và thành phần tham gia.
2. **Ma trận danh tính và quyền:** vai trò, tenant, trạng thái tài khoản và hành động được phép hoặc bị từ chối.
3. **Điều kiện và dữ liệu trước:** fixture, trạng thái ban đầu, ID duy nhất và nguồn dữ liệu có thẩm quyền.
4. **Kịch bản chính và nhánh lỗi:** thành công, từ chối, timeout, retry, hủy và phục hồi.
5. **Oracle:** phản hồi giao diện/API, dữ liệu lưu, sự kiện, audit log và tác dụng phụ.
6. **Tiêu chí hoàn tất bất đồng bộ:** trạng thái cuối, thời hạn chờ và điều kiện hội tụ.
7. **Kế hoạch tác dụng phụ:** sandbox, người nhận thử nghiệm, số lần mong đợi và cách bù trừ.
8. **Môi trường và cấu hình:** phiên bản, feature flag, phụ thuộc, tài khoản và quyền.
9. **Quan sát và chẩn đoán:** run ID, correlation ID, log, trace, ảnh chụp và trạng thái khi lỗi.
10. **Dọn dẹp và phục hồi:** tài nguyên cần xóa, dữ liệu cần giữ để điều tra và quy trình xử lý dở dang.
11. **Truy vết và trách nhiệm:** mục tiêu, rủi ro, người chạy, người điều tra và người phê duyệt.
12. **Giới hạn và rủi ro còn lại:** thành phần được mô phỏng, tác dụng phụ chưa xác minh và khác biệt môi trường.

Trước khi thực thi, hãy rà soát:

- Hành trình có bắt đầu và kết thúc bằng điều kiện nghiệp vụ rõ ràng không?
- Danh tính và quyền có đại diện cho các vai trò thực tế không?
- Có kiểm tra cả quyền hợp lệ, quyền bị từ chối và thay đổi quyền giữa phiên không?
- Dữ liệu trước và sau có thể truy vết và xác minh tại nguồn có thẩm quyền không?
- Tác dụng phụ có đúng nội dung, người nhận, số lần và thứ tự không?
- Các trạng thái bất đồng bộ có thời hạn chờ và tiêu chí hoàn tất không?
- Timeout, retry, sự kiện trùng và lỗi giữa chừng có được kiểm tra không?
- Môi trường và dữ liệu có cô lập, an toàn và có thể dọn dẹp không?
- Khi thất bại, nhóm có đủ log, trace và trạng thái để điều tra không?
- Giới hạn của kiểm thử có được ghi nhận trước quyết định phát hành không?

Kiểm thử hành trình có xác thực, dữ liệu và tác dụng phụ tạo ra bằng chứng có ý nghĩa khi nhóm xác minh được cả người thực hiện, quyền, trạng thái cuối và các tác động phát sinh. Hãy cập nhật kịch bản khi quy tắc xác thực, mô hình quyền, dữ liệu, tích hợp hoặc hành trình thay đổi. Nhờ đó, kết quả E2E phản ánh đúng trải nghiệm và tác động nghiệp vụ mà sản phẩm tạo ra.


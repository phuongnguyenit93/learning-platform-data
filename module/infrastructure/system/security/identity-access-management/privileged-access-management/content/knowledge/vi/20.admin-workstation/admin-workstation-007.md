# Clipboard control — Kiểm soát clipboard trong môi trường quản trị đặc quyền

## 1. Vì sao clipboard là một đường dữ liệu cần quản lý?

Clipboard giúp người vận hành sao chép ticket ID, địa chỉ tài nguyên, lệnh, log và nhiều loại nội dung khác. Trong môi trường quản trị đặc quyền, cùng chức năng đó cũng có thể:

- Đưa mật khẩu, token hoặc dữ liệu nhạy cảm ra khỏi phiên được kiểm soát.
- Đưa lệnh hoặc nội dung không đáng tin vào máy trạm quản trị.
- Chuyển dữ liệu giữa hai phiên hoặc hai vùng có mức tin cậy khác nhau.
- Để lại bản sao trong lịch sử clipboard, công cụ quản lý clipboard hoặc dịch vụ đồng bộ.

**Clipboard control** là tập chính sách và cơ chế giới hạn việc đọc, ghi hoặc chuyển nội dung qua clipboard theo ranh giới được xác định.

Trong PAM, cần phân biệt hai phạm vi:

1. Clipboard cục bộ trên máy trạm quản trị (PAW).
2. Clipboard được chuyển hướng giữa PAW và một phiên từ xa.

Tắt clipboard redirection của phiên từ xa không nhất thiết tắt clipboard bên trong máy từ xa. Ngược lại, quản lý clipboard của PAW không tự bảo đảm gateway hoặc hệ thống đích đã chặn mọi đường sao chép.

Mục tiêu là cho phép luồng dữ liệu cần thiết cho công việc mà không mặc nhiên mở một đường hai chiều cho mọi nội dung. Kiểm soát này hỗ trợ least privilege, bảo vệ credential và giám sát phiên; nó không thay thế các kiểm soát đó.

## 2. Mô hình rủi ro: bí mật đi ra, nội dung không đáng tin đi vào

### 2.1. Rủi ro bảo mật dữ liệu

Một phiên có thể hiển thị:

- Credential được checkout từ vault.
- Token hoặc khóa trong output.
- Cấu hình nhạy cảm.
- Dữ liệu khách hàng hoặc dữ liệu vận hành.
- Log chứa thông tin nội bộ.

Nếu cho phép sao chép từ phiên ra PAW rồi từ PAW sang công cụ khác, dữ liệu có thể đi xa hơn phạm vi được duyệt.

Ngay cả khi người vận hành không cố ý, họ có thể dán nhầm secret vào ticket, cửa sổ chat hoặc phiên khác. Lịch sử clipboard và đồng bộ có thể giữ lại nội dung sau khi phiên đã kết thúc.

### 2.2. Rủi ro toàn vẹn

Chiều ngược lại cũng cần kiểm soát. Nội dung từ email, ticket, website hoặc máy ít tin cậy hơn có thể được dán vào terminal hay giao diện quản trị.

Rủi ro gồm:

- Dán nhiều dòng mà không nhận ra.
- Ký tự điều khiển hoặc cách hiển thị gây hiểu sai.
- Nội dung bị thay đổi bởi phần mềm trên endpoint.
- Đích hoặc môi trường trong đoạn lệnh không đúng.
- Dán vào sai cửa sổ đang có quyền cao.

Một đoạn văn trông như hướng dẫn không tự trở thành mã hoặc lệnh được phê duyệt.

### 2.3. Rủi ro lưu giữ

Xóa nội dung đang hiển thị trong clipboard không chứng minh mọi bản sao đã bị xóa. Nội dung có thể đã nằm trong:

- Lịch sử clipboard.
- Ứng dụng quản lý clipboard.
- Đồng bộ giữa thiết bị.
- Ứng dụng đã nhận dữ liệu.
- Log hoặc bản ghi phiên.
- Bộ nhớ, file tạm hoặc bản sao lưu.

Vì vậy, thiết kế nên giảm việc đưa bí mật vào clipboard từ đầu, thay vì chỉ dựa vào việc tự xóa sau một khoảng thời gian.

### 2.4. Rủi ro chuyển chéo phiên

Một người có thể mở đồng thời phiên production và staging. Nếu cả hai cùng chia sẻ clipboard với PAW, clipboard cục bộ có thể trở thành cầu nối giữa hai vùng.

Cần đánh giá đường dữ liệu hoàn chỉnh, không chỉ từng phiên riêng lẻ.

## 3. Định nghĩa rõ chiều truyền và điểm kiểm soát

Trong bài học này:

- **Local** là PAW mà người vận hành đang sử dụng.
- **Remote** là môi trường hoặc phiên quản trị từ xa.
- **Inbound** là local → remote.
- **Outbound** là remote → local.

Một sản phẩm có thể dùng tên chiều khác. Khi cấu hình, phải đối chiếu với đường truyền thực tế, không đoán từ tên tùy chọn.

| Chiều | Nhu cầu hợp lệ có thể có | Rủi ro chính |
|---|---|---|
| Local → remote | Dán ticket ID hoặc thông tin đã kiểm tra | Đưa nội dung không đáng tin vào vùng quản trị |
| Remote → local | Lấy thông tin chẩn đoán được phép | Đưa dữ liệu hoặc secret ra ngoài phiên |
| Hai chiều | Một số tác vụ hỗ trợ cần trao đổi dữ liệu | Kết hợp cả hai loại rủi ro và dễ chuyển chéo phiên |
| Không chuyển hướng | Công việc có thể thực hiện trong phiên | Cần có đường làm việc thay thế cho nhu cầu thực tế |

Cho phép một chiều không đồng nghĩa chiều đó luôn an toàn. Nội dung đi vào có thể ảnh hưởng tính toàn vẹn; nội dung đi ra có thể ảnh hưởng tính bí mật.

Một luồng nhiều hop có thể gồm:

~~~text
Clipboard trên PAW
    ↔ cơ chế clipboard của client hoặc trình duyệt
    ↔ gateway hoặc nền tảng phiên
    ↔ clipboard trong môi trường từ xa
    ↔ ứng dụng đích
~~~

Nếu có nhiều hop, cần kiểm soát tại từng ranh giới có thể truyền dữ liệu. Một hop bị chặn không bảo đảm mọi đường khác đều bị chặn.

## 4. Clipboard không chỉ chứa plain text

### 4.1. Định dạng có thể khác nhau

Tùy hệ điều hành, ứng dụng và giao thức, clipboard có thể chứa:

- Plain text.
- Nội dung định dạng như HTML hoặc rich text.
- Hình ảnh.
- Tham chiếu file hoặc dữ liệu file qua cơ chế liên quan.
- Nhiều biểu diễn của cùng một nội dung.

Một chính sách “chỉ cho text” cần được thực thi và kiểm thử trên các định dạng mà triển khai thực sự hỗ trợ. Không chỉ kiểm tra một ứng dụng rồi kết luận mọi ứng dụng có cùng hành vi.

Chuyển sang plain text có thể giảm một số rủi ro định dạng, nhưng không loại bỏ rủi ro của chính nội dung. Mật khẩu, token và lệnh nguy hiểm đều có thể là plain text.

### 4.2. Giới hạn kích thước không phải kiểm soát secret đầy đủ

Giới hạn số byte hoặc số ký tự có thể hỗ trợ giảm khối lượng hoặc kiểm soát trải nghiệm. Tuy nhiên:

- Secret có thể rất ngắn.
- Dữ liệu có thể được chia thành nhiều lần.
- Ký tự và kích thước hiển thị không luôn tương ứng đơn giản.
- Nội dung nhạy cảm không được xác định chỉ bằng độ dài.

Giới hạn kích thước là một điều kiện phụ, không phải bằng chứng rằng nội dung được phép chuyển.

### 4.3. Phân loại nội dung có giới hạn

DLP hoặc kiểm tra nội dung có thể hỗ trợ phát hiện một số loại dữ liệu. Không nên giả định có thể nhận ra mọi secret hoặc mọi đoạn mã không phù hợp.

Cần quản lý false positive, false negative và cách xử lý khi không phân loại được. Dữ liệu do người dùng tự gắn nhãn “không nhạy cảm” chưa phải bằng chứng đủ nếu chính sách yêu cầu nguồn phân loại đáng tin cậy.

Một bộ lọc clipboard cũng thường không hiểu đầy đủ ý nghĩa nghiệp vụ của một đoạn text. Cho phép dán một chuỗi không đồng nghĩa cho phép thực thi chuỗi đó trong terminal.

## 5. Thiết kế chính sách theo công việc và vùng tin cậy

### 5.1. Bắt đầu từ luồng dữ liệu cần thiết

Với mỗi loại công việc, xác định:

- Người dùng cần sao chép thông tin gì?
- Từ ứng dụng và vùng nào?
- Tới ứng dụng và vùng nào?
- Có chứa secret hoặc dữ liệu nhạy cảm không?
- Có thể thay bằng một luồng có cấu trúc và kiểm soát tốt hơn không?
- Ai có thẩm quyền chấp thuận ngoại lệ?
- Bằng chứng nào chứng minh luồng đã đúng chính sách?

Ví dụ, dán ticket ID vào một trường đã kiểm tra khác với dán một script tùy ý vào shell quản trị.

Nếu cần phân biệt hai trường hợp, ứng dụng phải có điểm kiểm tra thích hợp. Một channel clipboard tổng quát không tự biết nội dung sẽ được dán vào ô ticket hay terminal.

### 5.2. Mức chính sách minh họa

| Bối cảnh | Hướng chính sách có thể chọn |
|---|---|
| Quản trị hệ thống danh tính hoặc vault nhạy cảm | Chặn chuyển hướng hoặc chỉ cho phép ngoại lệ hẹp đã được kiểm soát |
| Tác vụ có action định sẵn | Ưu tiên form hoặc API có cấu trúc thay vì clipboard vào shell |
| Chẩn đoán cần xuất log | Dùng cơ chế xuất dữ liệu đã kiểm tra và có nơi nhận rõ |
| Dán định danh yêu cầu | Dùng trường nhập có schema và xác minh phía máy chủ |
| Nhà cung cấp truy cập từ xa | Xác định rõ endpoint, chiều truyền và cơ chế phê duyệt dữ liệu |
| Phiên khẩn cấp | Giữ kiểm soát mặc định; ngoại lệ có phạm vi và thời hạn nếu cần |

Đây là các lựa chọn thiết kế, không phải cấu hình bắt buộc giống nhau cho mọi tổ chức.

### 5.3. Chính sách phải bao phủ danh tính và thời gian

Có thể cần ràng buộc theo:

- Principal đã xác thực.
- Vai trò và entitlement.
- Tài nguyên hoặc nhóm hệ thống.
- Session ID.
- Loại dữ liệu và chiều truyền.
- Định dạng được hỗ trợ.
- Thời gian và yêu cầu đã được duyệt.

Không nên cho phép một người đổi cấu hình clipboard toàn cục chỉ vì họ được duyệt một ngoại lệ cho một phiên.

## 6. Thực thi trên PAW, PAM và hệ thống từ xa

### 6.1. Cấu hình phía máy chủ phải có hiệu lực

Một tùy chọn trên client có thể chỉ thể hiện sở thích người dùng. Nếu chính sách yêu cầu chặn, điểm thực thi phải không cho client tự bật lại để vượt giới hạn.

Tùy kiến trúc, cơ chế có thể nằm ở:

- Chính sách endpoint trên PAW.
- Client quản trị được quản lý.
- Gateway hoặc dịch vụ session.
- Chính sách trên môi trường từ xa.
- Ứng dụng hoặc form có kiểm tra nội dung.
- Hệ thống chuyển file hoặc xuất dữ liệu riêng.

Cần biết từng cơ chế chặn điều gì và không chặn điều gì.

### 6.2. Đường web và ứng dụng native có thể khác nhau

Một portal HTML, một client native và một công cụ remote desktop có thể dùng các cơ chế clipboard khác nhau.

Quyền clipboard của trình duyệt không tự tương đương với chính sách clipboard của phiên từ xa. Việc một thao tác bị chặn trên web cũng không chứng minh client khác đã bị chặn.

Phải kiểm tra các đường được phép, bao gồm reconnect, phiên cũ và phiên được mở từ một công cụ khác.

### 6.3. Nhiều phiên và môi trường dùng chung

Cần tránh dữ liệu của phiên này xuất hiện ở phiên khác hoặc người dùng khác.

Phải xác minh:

- Clipboard và channel được gắn đúng session.
- Mở nhiều phiên không làm mất ranh giới.
- Chuyển người dùng không để lộ nội dung phiên trước.
- Một session đã kết thúc không tiếp tục truyền dữ liệu.
- Môi trường gateway dùng chung không tạo clipboard chung ngoài ý định.

Dọn clipboard có thể hỗ trợ, nhưng không thay thế cách ly phiên và quyền truy cập phù hợp.

### 6.4. Các đường dữ liệu khác vẫn cần được xem xét

Tắt clipboard redirection không tự chặn:

- Truyền file.
- Kéo thả.
- Drive redirection.
- In.
- Download từ ứng dụng.
- Chụp màn hình hoặc nhận dạng nội dung từ hình ảnh.
- Nhập tay.
- Một kết nối mạng khác có thể mang dữ liệu ra ngoài.

Không nên tuyên bố “không thể lấy dữ liệu ra” chỉ vì clipboard đã bị chặn. Cần quản lý các đường liên quan theo mô hình đe dọa và nhu cầu công việc.

## 7. Các luồng thay thế giúp giảm nhu cầu clipboard

### 7.1. Sử dụng credential qua PAM mà không hiển thị cho người dùng

Nếu kiến trúc hỗ trợ, người vận hành có thể mở phiên hoặc thực hiện tác vụ bằng credential do PAM quản lý mà không cần sao chép mật khẩu.

Cần kiểm tra cơ chế thực tế. Một tính năng mang tên credential injection không tự chứng minh bí mật không đi qua clipboard hoặc không thể xuất hiện trong log, bộ nhớ hay giao diện.

Thiết kế nên xác định:

- Bí mật được lấy và sử dụng ở đâu.
- Người dùng hoặc client có nhận bí mật không.
- Có dùng clipboard trung gian không.
- Cách xử lý sau sử dụng.
- Hệ thống đích có thể làm lộ lại bí mật không.

Không chuyển rủi ro từ thao tác copy của con người sang một đường copy tự động không quan sát được.

### 7.2. Dùng tác vụ và tham số có cấu trúc

Thay vì dán chuỗi lệnh tùy ý:

~~~text
Action: service.restart
Resource: svc-prod-payments-02
Request reference: PAM-REQ-4207
~~~

Một form hoặc API có thể kiểm tra action, tài nguyên, phê duyệt và tham số. Cách này giảm nhu cầu đưa mã tự do từ vùng ít tin cậy vào môi trường đặc quyền.

Nội dung được dán vào form vẫn phải được xác minh. Không ghép thẳng giá trị đó thành shell command.

### 7.3. Đưa script và công cụ qua đường phân phối được quản trị

Nếu công việc cần script:

1. Xác định nguồn và mục đích.
2. Kiểm tra nội dung và phụ thuộc theo mức rủi ro.
3. Quản lý phiên bản.
4. Phân phối qua kho hoặc cơ chế được phép.
5. Giới hạn quyền thực thi.
6. Ghi nhận kết quả.

Chữ ký hoặc checksum hỗ trợ xác minh nguồn hoặc tính toàn vẹn trong mô hình tương ứng. Chúng không tự chứng minh script phù hợp với công việc hoặc không có hành vi ngoài ý muốn.

### 7.4. Xuất log qua một luồng được kiểm soát

Nếu cần đưa thông tin chẩn đoán ra ticket, có thể dùng cơ chế xuất có phạm vi:

- Chọn dữ liệu và thời gian cần thiết.
- Loại bỏ hoặc che dữ liệu không cần thiết.
- Kiểm tra nơi nhận.
- Gắn với request hoặc incident.
- Lưu bằng chứng về lần xuất.

Không sao chép toàn bộ output có thể chứa secret chỉ vì một vài dòng cần cho hỗ trợ.

## 8. Dán vào terminal: kiểm soát nội dung và ý định

### 8.1. Paste có thể dẫn đến thực thi

Tùy terminal, ứng dụng và nội dung, ký tự xuống dòng hoặc thao tác dán có thể khiến lệnh được xử lý theo cách người dùng không dự kiến.

Một số cơ chế hiển thị hoặc paste protection có thể giúp giảm nhầm lẫn, nhưng không nên coi là ranh giới bảo mật đầy đủ.

Trước khi thao tác đặc quyền, cần biết:

- Nội dung đến từ đâu.
- Có bao nhiêu dòng và thành phần.
- Có ký tự hoặc phần không hiển thị rõ không.
- Tài nguyên và môi trường được nhắc tới.
- Quyền của phiên hiện tại.
- Tác dụng phụ và dữ liệu trả về.

Không dựa vào việc đoạn text “trông quen” để cho phép nó chạy.

### 8.2. Clipboard control không thay thế authorization

Cho phép một nội dung đi vào phiên không đồng nghĩa người dùng được quyền thực hiện nội dung đó.

PAM hoặc hệ thống đích vẫn cần giới hạn action, tài nguyên và tham số. Nếu người dùng có shell toàn quyền, việc kiểm soát clipboard không tự giới hạn mọi lệnh họ có thể nhập tay.

Ngược lại, một tác vụ JEA hoặc API hạn chế có thể tiếp nhận thông tin cần thiết mà không cho phép mở rộng thành thực thi tùy ý.

### 8.3. Nội dung đã kiểm tra có thể bị thay trước khi dùng

Nếu endpoint hoặc một công cụ có quyền thay clipboard, nội dung lúc người dùng copy có thể khác lúc paste.

PAW, chính sách ứng dụng và bảo vệ endpoint giúp giảm rủi ro. Với tác vụ nhạy cảm, đầu vào có cấu trúc và ràng buộc phía máy chủ thường dễ kiểm chứng hơn việc dựa vào một chuỗi clipboard có thể thay đổi.

Không coi clipboard là một kênh truyền có tính toàn vẹn chỉ vì người dùng vừa xem nội dung nguồn.

## 9. Vòng đời phiên và thay đổi chính sách

### 9.1. Khi mở phiên

PAM nên xác định chính sách hiệu lực trước khi cho phép channel truyền dữ liệu. Cần bảo đảm client không gửi nội dung trong khoảng cấu hình chưa áp dụng.

Nếu thiết kế không thực thi được một chế độ yêu cầu, phải báo rõ và xử lý theo chính sách. Không hiển thị “clipboard disabled” trong khi channel vẫn hoạt động.

### 9.2. Trong phiên

Nếu quyền hoặc mức rủi ro thay đổi, cần biết sản phẩm có thể cập nhật clipboard policy cho phiên hiện hữu hay không.

Một số kiến trúc có thể cần đóng và tạo lại kết nối để áp dụng thay đổi. Cách xử lý phải được chuẩn bị, xét cả công việc đang chạy và yêu cầu bảo vệ dữ liệu.

Không giả định sửa cấu hình trung tâm luôn tác động ngay tới mọi phiên đã mở.

### 9.3. Reconnect và resume

Phiên được nối lại phải áp dụng chính sách còn hiệu lực. Không để một lần reconnect khôi phục chế độ clipboard rộng hơn hoặc giữ ngoại lệ đã hết hạn.

Cần kiểm tra cả:

- Client đổi cấu hình trước khi reconnect.
- Người dùng đổi thiết bị.
- Phiên được mở qua công cụ khác.
- Chính sách đã đổi trong lúc mất kết nối.

### 9.4. Kết thúc và dọn dữ liệu

Có thể dọn nội dung clipboard trong phạm vi hệ thống kiểm soát để giảm dữ liệu còn lại. Nhưng việc dọn phải được mô tả đúng khả năng:

- Có thể chỉ dọn clipboard hiện tại.
- Có thể không xóa lịch sử, đồng bộ hoặc dữ liệu ứng dụng đã nhận.
- Có thể không kiểm soát được endpoint bên ngoài.
- Không chứng minh bộ nhớ hoặc mọi bản sao đã được xóa.

Nếu secret đã đi ra ngoài phạm vi, cần đánh giá và xử lý secret đó. Chỉ dọn clipboard không thay thế thu hồi hoặc đổi credential khi cần.

## 10. Ngoại lệ, khả năng sử dụng và truy cập khẩn cấp

### 10.1. Ngoại lệ phải đủ hẹp

Một ngoại lệ có thể cần chỉ rõ:

| Thuộc tính | Ví dụ |
|---|---|
| Người dùng | Kỹ sư được chỉ định |
| Phiên và tài nguyên | Một phiên trên một hệ thống |
| Chiều | Chỉ remote → local |
| Loại dữ liệu | Thông tin chẩn đoán đã được kiểm tra |
| Thời hạn | Trong khoảng được duyệt |
| Nơi nhận | Kho hoặc ticket được phép |
| Người quyết định | Chủ thể có thẩm quyền theo chính sách |
| Bằng chứng | Request, thời điểm, kết quả và việc hết ngoại lệ |

Đây là ví dụ về ý định. Một channel clipboard chung có thể không thực thi được mọi ràng buộc theo loại dữ liệu hoặc nơi nhận. Khi không hỗ trợ, cần dùng luồng xuất dữ liệu phù hợp hơn.

### 10.2. Không mở hai chiều cho mọi phiên để xử lý một nhu cầu

Nếu chỉ cần xuất một đoạn log, nên xử lý đúng nhu cầu đó. Không nên thay chính sách toàn cục thành cho phép mọi người copy hai chiều rồi dự kiến sẽ tắt lại sau.

Ngoại lệ hết hạn cần được thực thi và xác minh, đặc biệt với phiên đang mở.

### 10.3. Khả năng tiếp cận và công việc thực tế

Một số người dùng có thể cần cơ chế nhập liệu hoặc công cụ hỗ trợ phù hợp. Chính sách phải có đường làm việc được kiểm soát, không chỉ chặn rồi yêu cầu mọi người tự giải quyết.

Có thể dùng form có cấu trúc, tác vụ tự động, công cụ được quản lý hoặc một ngoại lệ được đánh giá. Không nên ép người vận hành gõ lại bí mật dài như giải pháp mặc định nếu có thể dùng một cơ chế an toàn hơn.

### 10.4. Break-glass vẫn cần quản lý đường dữ liệu

Khẩn cấp không tự yêu cầu bật clipboard. Nếu cần nới một ràng buộc, phải ghi rõ lý do, phạm vi, người có thẩm quyền và hạn kết thúc.

Sau sự cố, cần kiểm tra:

- Dữ liệu nào đã được chuyển theo bằng chứng hiện có.
- Có secret nào cần xử lý không.
- Phiên cũ còn hoạt động không.
- Ngoại lệ đã hết hiệu lực chưa.
- Chính sách thường đã được khôi phục thực tế chưa.

Không ghi phê duyệt lùi thời gian để làm hồ sơ trông như một lần cho phép thông thường.

## 11. Chính sách và logic minh họa

Cấu hình dưới đây chỉ diễn tả ý định thiết kế, không phải cú pháp của một sản phẩm:

~~~yaml
clipboard_policy:
  scope: "privileged-production-sessions"

  default_redirection:
    local_to_remote: "deny"
    remote_to_local: "deny"

  local_endpoint:
    managed_clipboard_history_required: true
    unmanaged_clipboard_sync_allowed: false
    unapproved_clipboard_managers_allowed: false

  exceptions:
    require_authorized_decision: true
    bind_to_session_and_direction: true
    require_expiry: true
    do_not_expand_other_sessions: true

  enforcement:
    client_preference_cannot_override_policy: true
    reevaluate_on_reconnect: true
    unsupported_required_control: "deny-or-use-approved-alternative"

  evidence:
    record_policy_and_transfer_result: true
    record_raw_clipboard_content_by_default: false
    exclude_reusable_secrets: true
~~~

Các mục local_endpoint là yêu cầu quản lý, không khẳng định mọi hệ điều hành đều có cùng chức năng. Phải kiểm tra khả năng thực thi của nền tảng được chọn.

Mã giả cho một channel có khả năng kiểm tra chuyển dữ liệu:

~~~text
authorize_clipboard_transfer(session, transfer):
    require(session.is_active)
    require(session.principal_is_authenticated)

    policy = load_effective_policy(session)
    require(policy.is_current_enough_for_this_operation)

    require(transfer.direction_is_allowed_by(policy))
    require(transfer.format_is_supported_and_allowed_by(policy))
    require(transfer.meets_applicable_size_and_content_rules)

    if transfer.requires_exception:
        require(exception_matches_session_direction_and_scope)
        require(exception.is_current)

    enforce_transfer_or_deny()
    record_sanitized_result_without_clipboard_payload()
~~~

Đây là mô hình logic. Không nên giả định mọi giao thức cung cấp đủ dữ liệu để kiểm tra từng transfer hoặc biết nội dung sẽ được dán vào ứng dụng nào.

~~~mermaid
flowchart TD
    A[Yêu cầu chuyển clipboard] --> B[Xác định phiên, chiều và định dạng]
    B --> C[Đọc chính sách có hiệu lực]
    C --> D{Channel và phạm vi được phép?}
    D -- Không --> E[Chặn và ghi lý do phù hợp]
    D -- Có --> F[Kiểm tra các điều kiện thực sự được hỗ trợ]
    F --> G{Điều kiện đạt?}
    G -- Không --> E
    G -- Có --> H[Cho chuyển trong phạm vi]
    H --> I[Ghi metadata và kết quả]
~~~

## 12. Bằng chứng, DLP và giới hạn quan sát

### 12.1. Không tạo kho secret qua log clipboard

Một hệ thống ghi nguyên văn mọi nội dung copy có thể vô tình thu thập mật khẩu, token và dữ liệu nhạy cảm vào nơi có nhiều người đọc.

Mặc định nên cân nhắc metadata như:

- Session ID và request ID.
- Principal.
- Chính sách và phiên bản.
- Chiều truyền.
- Định dạng và kích thước nếu cần.
- Cho phép hoặc từ chối.
- Nhóm lý do.
- Ngoại lệ liên quan.

Không mặc định thay nội dung bằng một bản băm rồi coi như hết rủi ro. Với dữ liệu dễ đoán hoặc ngắn, bản băm cũng có thể tạo khả năng đối chiếu ngoài ý muốn.

Nếu có nhu cầu xử lý nội dung cho DLP hoặc điều tra, cần xác định mục đích, quyền truy cập, thời gian lưu và cách bảo vệ dữ liệu tương ứng.

### 12.2. Ví dụ sự kiện đã lược bỏ nội dung

~~~json
{
  "event": "clipboard_transfer_decision",
  "session_ref": "pam-session-4207",
  "request_ref": "PAM-REQ-4207",
  "principal_ref": "engineer-17",
  "direction": "remote-to-local",
  "format_class": "text",
  "policy_ref": "production-clipboard-policy-v3",
  "outcome": "denied",
  "reason_class": "direction-not-permitted",
  "payload_recorded": false
}
~~~

Không ghi một nhãn như “đã kiểm tra không có secret” nếu thực tế hệ thống chỉ chặn theo chiều. Bằng chứng phải phản ánh đúng điều đã được quan sát và thực thi.

### 12.3. DLP không thay thế quyền và cách ly

DLP có thể không nhận ra mọi dữ liệu đã biến đổi hoặc mọi secret chưa được biết trước. Nó cũng có thể chặn nhầm dữ liệu hợp lệ.

Cần có tuyến xử lý phù hợp, không để người dùng tự vô hiệu hóa toàn bộ kiểm soát mỗi khi có một lần chặn nhầm.

Tương tự, bản ghi phiên không tự ngăn dữ liệu đi ra. Quan sát, ngăn chặn và xử lý sau sự kiện là các khả năng khác nhau.

## 13. Tình huống: nhà cung cấp cần lấy log để chẩn đoán

Một kỹ sư nhà cung cấp được duyệt truy cập dịch vụ production qua PAM. Chính sách phiên chặn clipboard hai chiều.

Kỹ sư cần:

- Đưa mã sự cố vào công cụ quản trị.
- Lấy một số thông tin chẩn đoán để gửi nhóm hỗ trợ.
- Thực hiện một tác vụ restart được cho phép.

Một cách xử lý có kiểm soát:

1. Mã sự cố được nhập qua trường có schema và liên kết phía máy chủ.
2. Tác vụ restart được thực hiện qua action giới hạn, không cần dán script tùy ý.
3. Log được chọn trong phạm vi thời gian và tài nguyên cần thiết.
4. Dữ liệu nhạy cảm được xử lý theo quy trình trước khi xuất.
5. Bản xuất đi tới nơi nhận đã được phép và gắn với request.
6. Nếu vẫn cần ngoại lệ clipboard, ngoại lệ được giới hạn đúng phiên, chiều và thời gian theo khả năng thực thi.
7. Sau công việc, quyền truy cập và ngoại lệ được kết thúc, bằng chứng được đối chiếu.

Nếu một mật khẩu đã bị copy ra ngoài, xóa clipboard trên PAW không chứng minh kỹ sư không còn bản sao. Cần xử lý credential và các đường sử dụng theo đánh giá sự cố.

Nếu client của nhà cung cấp không thuộc phạm vi tổ chức quản lý, khả năng kiểm soát lịch sử và đồng bộ cục bộ có thể hạn chế. Chính sách phải xét endpoint đầu vào và luồng dữ liệu, không chỉ dựa vào việc phiên đi qua portal.

## 14. Triển khai và kiểm chứng

Có thể bắt đầu bằng cách lập bản đồ các luồng clipboard đang được dùng, xác định công việc cần giữ và chuẩn bị luồng thay thế trước khi áp dụng chặn.

Cần thử với giao thức, client và ứng dụng thực tế. Một kết quả ở môi trường này không tự đại diện cho mọi đường truy cập khác.

| Ca kiểm thử | Kết quả cần đạt |
|---|---|
| Chặn local → remote | Nội dung không được chuyển qua channel bị chặn |
| Chặn remote → local | Nội dung không được chuyển theo chiều bị chặn |
| Chỉ cho một chiều | Chiều còn lại vẫn bị chặn |
| Client tự bật chia sẻ clipboard | Không vượt được chính sách bắt buộc |
| Nội dung HTML, ảnh hoặc định dạng khác | Xử lý đúng khả năng và chính sách đã công bố |
| Text chứa dữ liệu nhạy cảm | Không được coi là an toàn chỉ vì là plain text |
| Copy file hoặc kéo thả | Không bị bỏ sót nếu thuộc phạm vi kiểm soát dữ liệu |
| Copy nội bộ trong phiên từ xa | Hành vi đúng phạm vi chính sách; không nhầm với redirection |
| Mở đồng thời nhiều phiên | Không chuyển chéo ngoài ranh giới được phép |
| Người dùng khác đăng nhập môi trường dùng chung | Không nhận nội dung của phiên trước |
| Reconnect sau khi chính sách thay đổi | Áp dụng chính sách còn hiệu lực |
| Ngoại lệ hết hạn trong phiên đang mở | Không tiếp tục truyền theo ngoại lệ cũ ngoài cơ chế đã công bố |
| Dịch vụ policy hoặc kiểm tra nội dung không khả dụng | Không tự mở clipboard rộng hơn |
| Credential injection được sử dụng | Kiểm chứng đường bí mật thực tế, không chỉ tên tính năng |
| Dọn clipboard khi kết thúc | Đúng phạm vi có thể kiểm soát; không tuyên bố xóa mọi bản sao |
| Lịch sử hoặc đồng bộ clipboard | Được quản lý theo chính sách endpoint |
| Log, DLP và file chẩn đoán | Không tạo bản sao secret ngoài kiểm soát |
| Luồng xuất log hoặc nhập tham số thay thế | Đáp ứng công việc mà vẫn giữ ranh giới đã định nghĩa |

Một bài kiểm thử cần quan sát kết quả chuyển dữ liệu thực tế, không chỉ ảnh chụp một tùy chọn “disabled”. Nếu triển khai không hỗ trợ một ràng buộc, cần mô tả rõ giới hạn và chọn cơ chế khác phù hợp.

Clipboard control có giá trị khi được gắn với ranh giới tin cậy và nhu cầu công việc cụ thể. Trong PAM, thiết kế tốt quản lý cả dữ liệu đi ra, nội dung đi vào, vòng đời phiên và các đường thay thế; đồng thời tránh tạo thêm bản sao bí mật trong chính hệ thống giám sát.

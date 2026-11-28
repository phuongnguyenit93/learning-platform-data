# Session monitoring policy

## Mục tiêu bài học

Trong chương **Governance** của quản lý truy cập đặc quyền (**Privileged Access Management — PAM**), **session monitoring policy** là chính sách quy định những hoạt động đặc quyền nào phải được quan sát, bằng chứng nào cần thu thập, ai được theo dõi hoặc xem lại và phải xử lý thế nào khi có dấu hiệu bất thường hay mất khả năng giám sát.

Chính sách áp dụng cho truy cập quản trị, tài khoản dịch vụ và các đường điều khiển hạ tầng nhạy cảm. Nó kết nối nhu cầu công việc, least privilege, JIT/JEA, quản lý credential và quy trình ứng phó với khả năng truy vết hành động thực tế.

Sau bài học, bạn có thể:

- Phân biệt giám sát phiên, ghi phiên, audit hành động và kiểm soát phiên.
- Xác định phạm vi, mức bằng chứng và giới hạn bao phủ theo loại truy cập.
- Phân công trách nhiệm giám sát, xem lại, can thiệp và bảo vệ bằng chứng.
- Thiết kế cách xử lý khi broker, recorder, collector hoặc kho bằng chứng gặp lỗi.
- Chuyển yêu cầu chính sách thành tiêu chí kiểm tra có thể đối chiếu.

## 1. Chính sách cần giải quyết vấn đề gì?

Một yêu cầu “ghi lại mọi phiên admin” nghe rõ ràng nhưng còn thiếu nhiều quyết định:

- Phiên nào được tính là phiên đặc quyền?
- Phiên qua broker có phải là đường truy cập duy nhất không?
- Truy cập API hoặc workload tự động được quan sát thế nào?
- Dữ liệu ghi lại gồm metadata, lệnh, hình ảnh hay hành động tại đích?
- Ai nhận cảnh báo và ai có thẩm quyền kết thúc phiên?
- Nếu không ghi được bằng chứng, có được tiếp tục truy cập không?
- Ai được xem nội dung nhạy cảm và trong mục đích nào?
- Lưu bằng chứng bao lâu, bảo vệ ra sao và xóa theo quy trình nào?

Chính sách tốt trả lời những câu hỏi này theo phạm vi và rủi ro. Nó không chỉ yêu cầu bật một tùy chọn trên công cụ PAM.

### Giám sát không thay thế phân quyền

Một phiên được ghi đầy đủ vẫn có thể gây tác động lớn nếu tài khoản có quyền quá rộng. Ghi phiên hỗ trợ phát hiện, truy vết và điều tra; least privilege, JIT và JEA giới hạn khả năng hoặc thời gian sử dụng quyền.

Tương tự, credential nằm trong vault không tự chứng minh mọi lần sử dụng đều qua phiên được giám sát. Cần xem cả đường truy cập trực tiếp, bản sao credential và giao thức ngoài broker.

## 2. Phân biệt các cơ chế

| Cơ chế | Vai trò chính | Giới hạn cần hiểu |
| --- | --- | --- |
| Metadata phiên | Ghi ai, khi nào, từ đâu, tới đâu và kết quả thiết lập phiên | Không mô tả đầy đủ mọi hành động trong phiên |
| Ghi phiên | Lưu nội dung quan sát được như màn hình hoặc luồng terminal theo khả năng công cụ | Không bảo đảm thấy mọi hoạt động nền hoặc mọi kênh phụ |
| Audit hành động | Ghi thao tác tại ứng dụng, hệ điều hành hoặc nền tảng đích | Có thể thiếu ngữ cảnh người khởi tạo nếu dùng chung principal |
| Giám sát trực tiếp | Quan sát phiên đang diễn ra hoặc tín hiệu gần thời gian thực | Không có nghĩa luôn có người theo dõi mọi phiên |
| Phát hiện tự động | Áp dụng quy tắc hoặc phân tích để tạo cảnh báo | Có thể có cảnh báo sai hoặc bỏ sót; cần ngữ cảnh |
| Kiểm soát phiên | Cho phép giới hạn, tạm dừng hoặc kết thúc theo khả năng nền tảng | Có thể ảnh hưởng công việc và không luôn thu hồi mọi đường truy cập khác |

Cần nói chính xác chính sách yêu cầu cơ chế nào. “Đã ghi hình” không đồng nghĩa “đã phát hiện hành động nguy hiểm”. “Đã đóng kết nối broker” cũng chưa chắc kết thúc mọi tiến trình hoặc credential còn dùng được tại đích.

## 3. Xác định phạm vi bằng đường truy cập

Phạm vi nên liên kết với danh tính, tài khoản tại đích, tài nguyên, giao thức và loại nhiệm vụ. Chỉ lập danh sách người dùng thuộc nhóm admin có thể bỏ sót tài khoản dịch vụ hoặc quyền gián tiếp.

```text
Người hoặc workload khởi tạo
              |
              v
Xác thực và nhận quyền / credential
              |
              v
Broker, cổng quản trị hoặc API
              |
              v
Phiên / kết nối tại hệ thống đích
              |
              v
Hành động và tác động trên tài nguyên
```

Mỗi mắt xích có thể cung cấp bằng chứng khác nhau. Cần biết mắt xích nào bị bỏ qua khi truy cập trực tiếp hoặc khi một công cụ trung gian thực hiện hành động thay chủ thể.

### Những đường cần được xem xét

| Loại truy cập | Bằng chứng có thể cần | Điểm dễ bỏ sót |
| --- | --- | --- |
| Terminal quản trị | Metadata, luồng terminal, audit tại đích và dữ liệu tương quan | Tunnel, tác vụ nền, chuyển danh tính hoặc kết nối phụ |
| Desktop quản trị | Metadata, hình ảnh theo khả năng công cụ và audit ứng dụng/đích | Truyền file, clipboard, kênh phụ hoặc hoạt động ngoài desktop được ghi |
| Web console quản trị | Đăng nhập, principal, hành động API và audit tài nguyên | Chỉ ghi trang đăng nhập mà không có hành động phía sau |
| Truy cập cơ sở dữ liệu | Danh tính, nguồn, phiên kết nối và hành động phù hợp với nền tảng | Connection pool, tài khoản chung và dữ liệu truy vấn nhạy cảm |
| CLI hoặc API | Principal, role, request, tài nguyên, kết quả và liên kết tới lần chạy | Nhiều lời gọi không tạo một phiên tương tác duy nhất |
| Workload tự động | Workload, lần chạy, credential được cấp và audit hành động tại đích | Giả định tự động hóa phải có bản ghi màn hình như người quản trị |
| Truy cập khẩn cấp | Người khởi tạo, lý do, cơ chế nhận quyền và bằng chứng khả dụng | Đường khẩn cấp vô tình nằm ngoài mọi cơ chế truy vết |
| Hỗ trợ bên thứ ba | Người sử dụng thực tế, người bảo trợ, tài nguyên và thời gian | Chỉ lưu tên công ty hoặc tên tài khoản dùng chung |

Đối với API và tự động hóa, audit hành động cùng dữ liệu tương quan thường có ý nghĩa hơn việc cố tạo một bản ghi video. Chính sách cần đặt yêu cầu bằng chứng phù hợp với cơ chế truy cập.

### Phần chưa bao phủ phải được thể hiện

Nếu công cụ chỉ hỗ trợ một số giao thức, ghi rõ giới hạn. Đường chưa hỗ trợ cần được chặn, thay bằng luồng khác, bổ sung audit hoặc xử lý qua ngoại lệ theo quyết định phù hợp.

Một cơ chế quan sát mạng không tự đọc được nội dung được mã hóa đầu cuối. Muốn có bằng chứng nội dung cần điểm thu thập phù hợp và nằm trong phạm vi được phép. Không ghi “bao phủ toàn bộ” khi thực tế chỉ thấy kết nối và lượng dữ liệu.

## 4. Xác định mức giám sát theo rủi ro

Chính sách có thể phân loại theo tác động, môi trường và khả năng thực hiện hành động nhạy cảm. Không nhất thiết ghi cùng mức nội dung cho mọi phiên.

| Câu hỏi rủi ro | Ảnh hưởng tới thiết kế |
| --- | --- |
| Phiên có thể sửa IAM, credential hoặc trust không? | Cần truy vết chặt và điều kiện can thiệp rõ |
| Có thể tác động nhiều hệ thống hoặc dữ liệu nhạy cảm không? | Cần xác định tài nguyên, hành động và phạm vi bằng chứng |
| Có dùng tài khoản hoặc credential chung không? | Cần tăng khả năng gắn phiên với chủ thể thực tế |
| Là truy cập thường ngày, tác vụ hiếm gặp hay khẩn cấp? | Cần luồng nhận quyền, giám sát và xem lại phù hợp |
| Nội dung phiên có thể chứa dữ liệu nhạy cảm không? | Cần tối thiểu hóa thu thập và giới hạn người xem |
| Nền tảng có thể ghi và kiểm soát đến đâu? | Cần kiểm tra khả năng và phần không được bảo đảm |

Ví dụ, tổ chức có thể yêu cầu ghi phiên tương tác và xem lại theo sự kiện đối với quản trị production, trong khi dùng audit API cho workload phát hành. Đây là lựa chọn thiết kế cần được chốt trong chính sách cụ thể, không phải quy tắc chung cho mọi hệ thống.

Không dùng nhãn “ít rủi ro” chỉ vì phiên ngắn. Một phiên rất ngắn vẫn có thể tạo principal hoặc credential dài hạn.

## 5. Những thông tin cần có để quy trách nhiệm

Mục tiêu là nối được chủ thể khởi tạo với tài khoản và hành động tại đích, thay vì chỉ biết credential nào đã được lấy.

| Nhóm dữ liệu | Ví dụ cần cân nhắc |
| --- | --- |
| Định danh nguồn | ID người dùng hoặc workload, hệ thống danh tính và nguồn xác thực |
| Danh tính tại đích | Tài khoản, principal, role và môi trường |
| Ngữ cảnh công việc | Yêu cầu, nhiệm vụ, thay đổi hoặc trường hợp ứng phó liên quan |
| Thời gian | Bắt đầu, kết thúc, thời gian sự kiện và tình trạng đồng bộ thời gian |
| Đường truy cập | Broker, giao thức, đích, nguồn và kết nối liên quan |
| Cấp quyền | Grant JIT, điều kiện kích hoạt hoặc tham chiếu cấp credential |
| Hành động | Thao tác, tài nguyên, kết quả và audit tại đích khi có |
| Tình trạng bằng chứng | Đủ, thiếu một đoạn, lỗi recorder hoặc nguồn chưa bao phủ |
| Tương quan | Session ID, request ID, run ID hoặc tham chiếu phù hợp |

Chỉ lưu metadata cần thiết theo mục đích và phạm vi đã định. Không yêu cầu ghi giá trị credential để chứng minh principal đã được sử dụng.

### Tài khoản dùng chung cần dữ liệu tương quan

Nếu hai người cùng dùng một tài khoản tại đích, tên tài khoản đó không phân biệt được hành động của từng người. Cần liên kết phiên, thời gian, kết nối và nguồn khởi tạo.

Một bản ghi checkout credential chỉ chứng minh credential đã được cấp hoặc lấy theo cơ chế đó. Nó chưa đủ để gán mọi hành động xảy ra sau đó cho người checkout, nhất là khi credential còn bản sao hoặc có nhiều bên sử dụng.

Với workload, liên kết lần chạy với principal thực thi và hành động ở đích. Không gán toàn bộ hành động cho người phê duyệt pipeline chỉ vì họ đứng đầu chuỗi công việc.

## 6. Phân công trách nhiệm và quyền can thiệp

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| Chủ sở hữu chính sách | Chốt phạm vi, yêu cầu bằng chứng và quy tắc ngoại lệ |
| Chủ sở hữu hệ thống | Xác nhận tác động vận hành và đường truy cập cần bảo vệ |
| Đội vận hành PAM | Duy trì broker, recorder, liên kết phiên và tình trạng thu thập |
| Đội giám sát hoặc ứng phó | Tiếp nhận cảnh báo, phân tích và thực hiện bước xử lý được giao |
| Người có quyền can thiệp | Tạm dừng, kết thúc hoặc hạn chế phiên theo điều kiện và thẩm quyền |
| Người xem lại bằng chứng | Truy cập đúng mục đích, phạm vi và thời gian được cho phép |
| Đơn vị quản lý kho bằng chứng | Bảo vệ lưu trữ, kiểm soát truy cập, vòng đời và khả năng truy xuất |

Không mặc định người vận hành PAM được xem mọi nội dung phiên. Quyền cấu hình công cụ, quyền xem bản ghi và quyền xóa bằng chứng nên được phân tách phù hợp với mức nhạy cảm.

Chính sách cần nêu ai được can thiệp khi người thực hiện đang xử lý sự cố production. Cảnh báo tự động có thể là tín hiệu để điều tra; tự động kết thúc mọi phiên có cảnh báo có thể gây tác động không mong muốn.

### Việc xem bằng chứng cũng cần được truy vết

Nên ghi ai xem, tải xuống, chia sẻ hoặc thay đổi trạng thái bản ghi, với lý do phù hợp. Cơ chế này giúp phát hiện sử dụng bằng chứng ngoài mục đích và hỗ trợ kiểm tra trách nhiệm của người điều tra.

Nếu cần theo dõi trực tiếp, phải có quy tắc về mục đích, bên được phép và cách thông báo theo chính sách áp dụng. Không coi khả năng kỹ thuật của công cụ là quyền mặc nhiên để quan sát mọi người dùng.

## 7. Thiết kế tín hiệu phát hiện và quy trình phản ứng

Các tín hiệu có thể liên quan tới:

- Thao tác vượt nhiệm vụ hoặc truy cập tài nguyên ngoài scope.
- Sửa IAM, tạo credential hoặc thay trust ngoài luồng đã xác nhận.
- Tác động bất thường tới audit hoặc cơ chế phục hồi.
- Truyền dữ liệu qua kênh không được phép cho nhiệm vụ.
- Đăng nhập hoặc sử dụng đặc quyền từ nguồn chưa được chấp nhận.
- Mất luồng ghi, thiếu heartbeat hoặc thời gian sự kiện bất thường.

Mỗi quy tắc nên liên kết với loại rủi ro, nguồn dữ liệu, người nhận và bước xử lý. Nếu không có khả năng nhìn thấy hành động, không nên tuyên bố có quy tắc phát hiện đáng tin cậy cho hành động đó.

### Không đồng nhất chuỗi lệnh với tác động

Một chuỗi ký tự trong terminal có thể xuất hiện trong tài liệu hoặc output, không phải lệnh đã chạy. Một thao tác nhạy cảm cũng có thể được thực hiện qua API, script hoặc công cụ khác mà không xuất hiện đúng chuỗi đang tìm.

Nên đối chiếu ngữ cảnh phiên, audit tại đích, tài nguyên và kết quả. Quy tắc đơn giản có thể hữu ích nhưng cần được mô tả đúng giới hạn.

### Phản ứng phải có mục tiêu cụ thể

Có thể bắt đầu bằng xác minh ngữ cảnh, liên hệ người chịu trách nhiệm hoặc tăng mức theo dõi. Khi có căn cứ và thẩm quyền, có thể hạn chế, tạm dừng hoặc kết thúc phiên.

Đóng phiên qua broker có thể chưa dừng tác vụ nền, phiên phụ hoặc credential đã lấy. Nếu mục tiêu là thu hồi khả năng truy cập, cần xem cơ chế quyền, token, credential và trạng thái tại đích theo nền tảng.

Kết quả phản ứng cần ghi rõ hành động đã áp dụng và điều gì đã được xác minh, thay vì chỉ ghi “đã chặn” khi mới gửi một lệnh kết thúc kết nối.

## 8. Xử lý khi khả năng giám sát bị suy giảm

Chính sách cần quyết định trước cách phản ứng với từng loại lỗi. Chỉ yêu cầu “recorder phải hoạt động” chưa đủ nếu không nói điều gì xảy ra khi nó ngừng hoạt động.

| Tình huống | Quyết định cần xác định |
| --- | --- |
| Không sẵn sàng ghi trước khi mở phiên | Có từ chối phiên thông thường, chuyển luồng hay dùng ngoại lệ nào không? |
| Mất ghi trong phiên đang hoạt động | Ai được cảnh báo, có thể tiếp tục trong điều kiện nào và ai quyết định kết thúc? |
| Không chuyển được bản ghi tới kho | Có vùng đệm được bảo vệ, giới hạn dung lượng và thời gian chờ nào? |
| Vùng đệm đầy hoặc không bảo đảm lưu được | Có dừng cấp phiên mới hoặc áp dụng phản ứng khác không? |
| Audit tại đích không hoạt động | Bằng chứng còn lại có đáp ứng nhiệm vụ không và ai chấp nhận khoảng trống? |
| Thời gian giữa các nguồn sai lệch | Cách ghi tình trạng và khôi phục khả năng tương quan là gì? |
| Kho bằng chứng không đọc được | Có thể tiếp tục ghi không, ai xử lý và kiểm tra truy xuất lại thế nào? |

**Fail-closed** thường chỉ việc từ chối hoặc ngừng một luồng khi điều kiện kiểm soát bắt buộc không được đáp ứng. **Fail-open** cho phép tiếp tục trong tình trạng đó. Cần nói rõ quyết định áp dụng cho phiên mới, phiên đang chạy hay một bước cụ thể; không dùng một nhãn chung cho toàn hệ thống.

Không có một lựa chọn duy nhất phù hợp với mọi tài nguyên. Từ chối phiên quản trị thông thường có thể phù hợp khi thiếu ghi bắt buộc. Với tác vụ phục hồi đang chạy, kết thúc ngay có thể gây tác động lớn; cần quy trình và thẩm quyền riêng.

### Phân biệt thu thập tại chỗ với lưu trữ tập trung

Lỗi chuyển bản ghi không nhất thiết đồng nghĩa nội dung đã ngừng được thu thập. Ngược lại, trạng thái “đã kết nối tới kho” cũng không chứng minh nội dung phiên đầy đủ.

Nếu dùng vùng đệm, cần bảo vệ truy cập và dữ liệu lưu, theo dõi dung lượng, kiểm tra chuyển tiếp và xác nhận bản ghi tại kho. Chính sách phải xử lý trường hợp vùng đệm không còn bảo đảm giữ được bằng chứng.

### Không che khoảng trống bằng một trạng thái thành công

Một phiên có thể được phép tiếp tục theo ngoại lệ nhưng bằng chứng vẫn thiếu một đoạn. Lưu rõ thời điểm thiếu, nguồn còn khả dụng và quyết định tiếp tục. Không tự gắn nhãn bản ghi đầy đủ vì phiên đã kết thúc bình thường.

## 9. Quản lý đường khẩn cấp và ngoại lệ

Truy cập khẩn cấp cần được thiết kế trước, với mục đích và điều kiện rõ ràng. Khi broker hoặc hệ thống danh tính gặp lỗi, đường khẩn cấp phải phù hợp với tình huống mà nó được thiết kế phục vụ.

Một hồ sơ ngoại lệ nên làm rõ:

- Chủ thể và tài nguyên được phép sử dụng.
- Nhiệm vụ, lý do và phần kiểm soát chưa đáp ứng.
- Thời gian hiệu lực và điều kiện kết thúc.
- Người quyết định và người chịu trách nhiệm theo dõi.
- Bằng chứng thay thế có thể thu thập.
- Cách xem lại sau sử dụng và xử lý credential hoặc quyền phát sinh.

Ngoại lệ không phải đường bỏ qua giám sát vô thời hạn. Nếu không có bản ghi phiên, các nguồn thay thế như audit tại đích hoặc hồ sơ công việc cần được nêu đúng giới hạn; không mô tả chúng như bản ghi nội dung đầy đủ khi không có khả năng đó.

Sau truy cập khẩn cấp, cần xem xét hành động, quyền được tạo thêm và credential đã sử dụng theo quy trình tương ứng. Chỉ đóng phiên chưa đủ chứng minh mọi thay đổi đã được kiểm soát.

Nếu cùng một ngoại lệ được dùng thường xuyên, cần xem lại thiết kế hoặc khả năng công cụ thay vì liên tục gia hạn mà không giải quyết nguyên nhân.

## 10. Tối thiểu hóa dữ liệu nhạy cảm trong bản ghi

Phiên quản trị có thể hiển thị dữ liệu sản xuất, thông tin cá nhân, credential hoặc chi tiết phục hồi. Bằng chứng phiên vì vậy có thể nhạy cảm tương đương hoặc hơn tài nguyên đang được quản trị.

Chính sách cần xác định mục đích thu thập và mức chi tiết cần thiết. Có thể giảm việc hiển thị bí mật, dùng cơ chế cấp credential không tiết lộ cho người dùng và áp dụng chức năng che dữ liệu phù hợp khi công cụ hỗ trợ.

### Kiểm tra khả năng che dữ liệu thực tế

Che một ô mật khẩu trên màn hình không tự loại bỏ cùng dữ liệu khỏi terminal output, clipboard, metadata, file truyền hoặc audit của ứng dụng. Cần kiểm tra từng lớp bằng dữ liệu giả trong môi trường thực hành phù hợp.

Không khẳng định “đã ẩn mọi bí mật” chỉ vì giao diện phát lại có một vùng màu đen. Cần xác định dữ liệu thực sự được loại bỏ trước lưu, chỉ bị che ở giao diện hay vẫn tồn tại ở bản xuất.

Nếu phát hiện bí mật trong bằng chứng đã thu, hạn chế truy cập và xử lý theo quy trình dữ liệu nhạy cảm hoặc sự cố credential. Việc tạo bản đã làm sạch để chia sẻ cần có dấu vết và phân biệt rõ với nguồn gốc của bằng chứng.

Không tùy tiện sửa nội dung để xóa dấu vết sự kiện. Việc giữ, hạn chế, thay thế hoặc xóa dữ liệu nhạy cảm phải có quyết định và lịch sử phù hợp với chính sách bằng chứng.

### Không thu toàn bộ dữ liệu chỉ vì có thể thu

Ví dụ, không phải mọi hệ thống đều cần lưu toàn bộ nội dung truy vấn hoặc kết quả dữ liệu để đáp ứng mục tiêu giám sát. Có thể cần định danh hành động, tài nguyên và kết quả thực thi thay vì sao chép toàn bộ dữ liệu trả về.

Mức thu thập phải đủ cho mục tiêu đã xác định, đồng thời tránh tạo một kho dữ liệu nhạy cảm vượt nhu cầu.

## 11. Bảo vệ tính toàn vẹn, truy cập và vòng đời bằng chứng

### 11.1. Kiểm soát truy cập

Quyền xem trực tiếp, phát lại, tải xuống, chia sẻ và xóa có tác động khác nhau. Nên cấp theo nhiệm vụ, phạm vi và thời gian cần thiết, với mức xem xét độc lập phù hợp.

Người yêu cầu bằng chứng cần nêu mục đích như điều tra sự kiện hoặc kiểm tra tác vụ. Không mặc định mọi thành viên đội vận hành được xem toàn bộ phiên của tổ chức.

Việc xuất bản ghi ra ngoài hệ thống có thể làm mất các kiểm soát truy cập ban đầu. Cần quản lý bản xuất, nơi nhận và trách nhiệm bảo vệ.

### 11.2. Tính toàn vẹn và xuất xứ

Các biện pháp có thể gồm kiểm soát quyền sửa/xóa, tách vai trò quản trị, bảo vệ đường truyền, kiểm tra toàn vẹn và lịch sử xử lý bản ghi. Cần bảo vệ cả nội dung lẫn metadata và liên kết tương quan.

Hash giúp kiểm tra dữ liệu có khớp với giá trị tham chiếu hay không. Nếu người sửa nội dung cũng sửa được giá trị hash mà không bị phát hiện, hash đơn lẻ không đủ chứng minh bằng chứng nguyên vẹn.

Tương tự, mã hóa dữ liệu lưu không tự ngăn một tài khoản có quyền xóa hợp lệ xóa bản ghi. Thiết kế phải xét cả truy cập, vòng đời khóa và quyền quản trị kho bằng chứng.

Thời gian không đồng bộ có thể làm sai thứ tự sự kiện. Khi có sai lệch, lưu tình trạng và giới hạn của kết luận thay vì âm thầm sắp lại thời gian như thể mọi nguồn đều chính xác.

### 11.3. Lưu giữ và xóa

Thời hạn lưu cần dựa trên mục đích, mức rủi ro và các yêu cầu áp dụng của tổ chức. Không có một số ngày chung trong bài học này cho mọi loại bằng chứng.

Cần xác định thời điểm bắt đầu tính hạn, các loại dữ liệu, nơi lưu, bản xuất và cách xử lý bản sao. Nếu cơ chế backup không hỗ trợ xóa riêng một bản ghi ngay lập tức, phải nêu cách quản lý vòng đời phù hợp thay vì hứa xóa ở mọi nơi mà không có khả năng thực hiện.

Khi có quyết định giữ bằng chứng cho một vụ việc, lưu phạm vi, thẩm quyền, trách nhiệm xem lại và điều kiện kết thúc việc giữ. Không biến mọi bản ghi thành lưu vô thời hạn chỉ vì có thể hữu ích trong tương lai.

## 12. Mẫu chính sách có cấu trúc

Ví dụ sau là **mô hình minh họa**, không phải cấu hình để triển khai trực tiếp. Các lựa chọn là giả định của một tổ chức mẫu:

```yaml
session_monitoring_policy:
  id: pam-session-monitoring-example-005
  version: example-v1
  scope:
    environment: production
    subjects:
      - privileged-human-access
      - privileged-workload-access
    target_inventory_ref: protected-inventory/production-systems
  evidence_requirements:
    brokered_terminal:
      - session-metadata
      - terminal-recording
      - target-audit-correlation
    brokered_desktop:
      - session-metadata
      - desktop-recording
      - relevant-target-audit
    api_and_workloads:
      - source-identity
      - run-or-request-correlation
      - target-action-audit
  failure_handling:
    new_normal_interactive_session: deny-if-required-recording-unavailable
    active_session: follow-approved-degradation-response
    evidence_transfer_failure: protected-buffer-and-alert-with-defined-limits
    emergency_access: separate-documented-emergency-process
  response:
    alert_owner: security-monitoring
    intervention_authority_ref: protected-policy/session-intervention
    verify_target_effect: required
  evidence_access:
    purpose_reference: required
    role_scope_and_time_limit: required
    access_audit: required
  evidence_lifecycle:
    retention_policy_ref: protected-policy/evidence-retention
    sensitive_data_handling_ref: protected-policy/recording-data-handling
  assurance:
    coverage_review_ref: protected-records/session-monitoring-coverage
    exceptions_ref: protected-records/session-monitoring-exceptions
```

Chính sách triển khai cần bổ sung định nghĩa cụ thể về giới hạn vùng đệm, thẩm quyền, điều kiện can thiệp và tiêu chí bằng chứng đủ. Những tham chiếu trong ví dụ phải được thay bằng quy trình thực sự tồn tại và có chủ sở hữu.

Không dùng `target_inventory_ref` để mặc định cấp quyền truy cập mọi tài nguyên trong inventory. Phạm vi được quản lý và grant cho một nhiệm vụ vẫn là hai quyết định riêng.

## 13. Ví dụ: phiên hỗ trợ production qua desktop quản trị

Một kỹ sư của nhà cung cấp được cấp quyền tạm thời để xử lý lỗi ứng dụng A. Chính sách của tình huống yêu cầu phiên desktop qua broker, có ghi phiên và liên kết với yêu cầu hỗ trợ.

Trong quá trình làm việc:

1. Kỹ sư đăng nhập bằng danh tính riêng và nhận quyền trên tài nguyên được giao.
2. Broker mở desktop quản trị và ghi metadata cùng hình ảnh.
3. Công cụ trên desktop kích hoạt một job chạy dưới tài khoản dịch vụ.
4. Job gọi API của hệ thống đích.
5. Recorder bị mất luồng ghi trước khi kỹ sư kết thúc công việc.

### Cần quan sát những gì?

| Thành phần | Bằng chứng và quyết định cần có |
| --- | --- |
| Người hỗ trợ | Danh tính riêng, người bảo trợ, mục đích và quyền tạm thời |
| Phiên desktop | Đích, thời gian, session ID và tình trạng bản ghi |
| Job được kích hoạt | Run ID, người hoặc phiên yêu cầu và danh tính thực thi |
| API tại đích | Principal, hành động, tài nguyên và kết quả |
| Lỗi recorder | Thời điểm bắt đầu thiếu, cảnh báo và phản ứng đã thực hiện |
| Kết thúc công việc | Trạng thái phiên, quyền tạm thời, credential và tác vụ còn chạy |

Bản ghi màn hình có thể cho thấy thao tác kích hoạt job nhưng không bảo đảm thấy toàn bộ hành động API. Cần liên kết audit của job và hệ thống đích.

Khi recorder lỗi, đội vận hành áp dụng luồng suy giảm đã định. Nếu phiên được phép tiếp tục theo ngoại lệ, lưu đúng tình trạng thiếu bằng chứng và nguồn thay thế. Nếu kết thúc phiên, cần xem job có tiếp tục chạy hay không.

### Những kết luận không nên đưa ra

- “Có video nên mọi hành động tại đích đều được ghi đầy đủ.”
- “Đã đóng desktop nên job và mọi quyền liên quan đều đã dừng.”
- “Tài khoản đích là tài khoản dịch vụ nên không thể gắn với yêu cầu hỗ trợ.”
- “Phiên kết thúc thành công nên đoạn thiếu ghi không cần báo cáo.”

Kết luận cần bám vào từng nguồn bằng chứng và phạm vi nó thực sự bao phủ.

## 14. Chuyển chính sách thành tiêu chí kiểm tra

Có thể kiểm tra bằng tài khoản, tài nguyên và dữ liệu thực hành, với những hành động an toàn phù hợp. Không cần thực hiện thao tác phá hủy trên production để chứng minh cơ chế giám sát hoạt động.

| Ca kiểm tra | Kết quả cần đối chiếu |
| --- | --- |
| Hai người dùng cùng tài khoản tại đích qua hai phiên | Phân biệt được chủ thể nguồn, session ID và kết nối tương ứng |
| Truy cập bằng giao thức ngoài phạm vi recorder | Có chặn, luồng thay thế hoặc ngoại lệ rõ; không báo bao phủ đầy đủ |
| Phiên tạo kết nối phụ hoặc truyền file | Xác định bằng chứng và kiểm soát cho kênh đó theo chính sách |
| Workload gọi API | Có principal, lần chạy hoặc request và audit đích phù hợp |
| Recorder không sẵn sàng trước phiên | Xử lý phiên mới đúng quy tắc đã chốt |
| Recorder ngừng giữa phiên | Có cảnh báo, ghi khoảng trống và phản ứng đúng thẩm quyền |
| Kho bằng chứng tạm không nhận dữ liệu | Vùng đệm và giới hạn được kiểm tra; có xác nhận chuyển tiếp lại |
| Dữ liệu nhạy cảm giả xuất hiện trong phiên | Xác định việc che ở nguồn, trong lưu trữ, phát lại và bản xuất |
| Người không có mục đích được chấp nhận yêu cầu xem bản ghi | Truy cập bị giới hạn theo cơ chế đã định |
| Người điều tra xem hoặc tải bản ghi | Có audit và phạm vi truy cập tương ứng |
| Nội dung hoặc metadata bị thay đổi trong môi trường thực hành | Cơ chế toàn vẹn và cảnh báo thể hiện đúng khả năng |
| Phiên bị kết thúc qua broker | Kiểm tra trạng thái tại đích và phần truy cập còn tồn tại |

Cần lưu kết quả và giới hạn của từng ca. Một ca phát lại video thành công chưa chứng minh truy cập trực tiếp đã bị chặn hoặc quá trình xóa theo hạn hoạt động.

Khi đổi giao thức, phiên bản công cụ, kiến trúc hoặc đường truy cập, xem lại những ca liên quan. Chính sách cần được kiểm tra theo thay đổi thực tế, không chỉ tồn tại dưới dạng tài liệu.

## 15. Chỉ số và bằng chứng quản trị

Các chỉ số nên phân biệt phạm vi, chất lượng bằng chứng và khả năng phản ứng:

- Số đường truy cập đặc quyền đã được phân loại về giám sát.
- Số đường chưa bao phủ hoặc đang có ngoại lệ.
- Tỷ lệ phiên thuộc diện bắt buộc ghi có bằng chứng đạt tiêu chí.
- Số phiên thiếu đoạn, lỗi ghi hoặc chưa chuyển đủ tới kho.
- Thời gian tiếp nhận và xử lý cảnh báo theo định nghĩa đã chốt.
- Số lần xem hoặc xuất bằng chứng ngoài quy trình được phát hiện.
- Số ngoại lệ hết hạn nhưng chưa được xử lý.

### Ví dụ về mẫu số

Giả sử trong một tập đã xác định có **20 phiên thuộc diện bắt buộc ghi**: 16 có bằng chứng đủ, 3 thiếu một phần và 1 không có bản ghi. Tỷ lệ đạt tiêu chí của tập đó là **16/20 = 80%**.

Không loại bốn phiên lỗi khỏi mẫu số để báo 100%. Cũng không dùng con số 80% này để khẳng định 80% mọi truy cập đặc quyền của tổ chức đã được giám sát, nếu tập thống kê chỉ gồm phiên qua broker.

Để phát hiện đường vòng, cần đối chiếu inventory, cấu hình truy cập và audit tại đích. Log của broker chỉ nhìn thấy những gì đi qua broker trong phạm vi nó ghi nhận.

### Hồ sơ phục vụ review chính sách

Nên liên kết phiên bản chính sách, phạm vi, chủ sở hữu, bằng chứng kiểm tra, giới hạn công cụ, ngoại lệ và các phát hiện chưa xử lý. Khi chính sách thay đổi, giữ khả năng xác định quy tắc nào có hiệu lực tại thời điểm của phiên.

## 16. Những điểm cần ghi nhớ

- Session monitoring policy quy định phạm vi, bằng chứng, trách nhiệm và phản ứng, không chỉ yêu cầu bật ghi phiên.
- Ghi phiên, audit hành động, phát hiện và kiểm soát phiên có vai trò khác nhau.
- Bằng chứng cần nối chủ thể nguồn với principal và hành động tại đích.
- API, workload tự động, truyền file và kết nối phụ cần cách quan sát phù hợp.
- Mất khả năng ghi phải có quy tắc cho phiên mới, phiên đang chạy và đường khẩn cấp.
- Bản ghi có thể chứa dữ liệu nhạy cảm; quyền xem, xuất, giữ và xóa đều cần được quản lý.
- Kết thúc phiên chưa tự chứng minh mọi tác vụ, token hoặc credential đã hết khả năng.
- Chỉ số phải giữ khoảng trống trong phạm vi và không đồng nhất “qua broker” với “toàn bộ truy cập”.

Một chính sách hữu ích giúp trả lời được **ai đã dùng đặc quyền, làm gì, trên tài nguyên nào, dựa vào bằng chứng nào và ai chịu trách nhiệm khi có vấn đề**. Kết hợp nó với giới hạn quyền, quản lý credential và xác minh ở hệ thống đích giúp PAM kiểm soát cả khả năng truy cập lẫn hành động thực tế.

# UAC policy

## Mục tiêu của bài học

User Account Control (UAC) là thành phần kiểm soát nâng quyền trên Windows. Trong Endpoint PAM, cấu hình UAC giúp xác định cách hệ điều hành xử lý một yêu cầu chạy chương trình với quyền quản trị: yêu cầu đồng ý, yêu cầu credential quản trị hoặc từ chối yêu cầu.

Một chính sách UAC tốt phải đi cùng việc loại bỏ local admin thường trực, cấp quyền tối thiểu cho đúng tác vụ, kiểm soát credential và thu thập bằng chứng. Bật UAC nhưng vẫn để mọi người dùng giữ local admin không giải quyết được toàn bộ bài toán quản lý đặc quyền.

Sau bài học, bạn có thể:

- Phân biệt đăng nhập bằng tài khoản quản trị với chạy một tiến trình đã được nâng quyền.
- Giải thích sự khác nhau giữa consent prompt và credential prompt.
- Chọn hành vi UAC phù hợp cho máy người dùng, máy quản trị và tình huống hỗ trợ.
- Kết hợp UAC với cơ chế nâng quyền theo ứng dụng hoặc theo tác vụ của Endpoint PAM.
- Thiết kế kiểm thử, ghi nhận ngoại lệ và thu thập bằng chứng để kiểm toán.

Phạm vi bài học là chính sách UAC cho endpoint Windows trong chương Endpoint PAM. UAC không thay thế vault, JIT/JEA, kiểm soát ứng dụng, giám sát phiên hay quy trình break-glass của hệ thống PAM.

## 1. Tình huống mở đầu: nhiều hộp thoại chưa chắc kiểm soát tốt

Một doanh nghiệp có 600 laptop Windows. Người dùng đều thuộc nhóm local Administrators vì trước đây cần tự cài phần mềm. UAC đã bật và thường xuyên xuất hiện hộp thoại hỏi đồng ý. Khi gặp hộp thoại, phần lớn người dùng chọn “Yes” theo thói quen.

Bộ phận bảo mật đề xuất tăng số lần hiện hộp thoại. Trong khi đó, nhóm Endpoint PAM phát hiện ba vấn đề quan trọng hơn:

1. Quyền quản trị tồn tại liên tục dù người dùng chỉ cần nâng quyền vài tác vụ mỗi tháng.
2. Người dùng được đồng ý nâng quyền cho nhiều chương trình ngoài danh mục đã duyệt.
3. Nhật ký không liên kết rõ ứng dụng, phiên bản, người dùng, yêu cầu hỗ trợ và lý do nghiệp vụ.

UAC vẫn có ích: nó hỗ trợ phân tách quá trình làm việc thông thường với quá trình nâng quyền và làm rõ thời điểm cần quyết định. Tuy nhiên, nút “Yes” không phải là phê duyệt nghiệp vụ của tổ chức.

Hướng xử lý phù hợp là loại bỏ local admin thường trực, áp dụng chính sách UAC nhất quán và cung cấp một luồng nâng quyền có giới hạn thông qua Endpoint PAM.

> Câu hỏi thiết kế không chỉ là “có hiện hộp thoại không”, mà là “ai được thực hiện tác vụ đặc quyền nào, bằng cơ chế gì và để lại bằng chứng nào”.

## 2. Nền tảng: access token và Admin Approval Mode

### 2.1 Access token xác định ngữ cảnh quyền của tiến trình

Khi xử lý truy cập vào tài nguyên, Windows sử dụng ngữ cảnh bảo mật của tiến trình hoặc luồng thực thi. Access token chứa các thông tin như danh tính, nhóm và đặc quyền liên quan.

Trong cấu hình UAC thông thường với Admin Approval Mode, một thành viên nhóm Administrators có thể làm việc bằng token đã được lọc thay vì sử dụng đầy đủ quyền quản trị cho mọi chương trình. Khi thực hiện nâng quyền thành công, chương trình được khởi chạy với token quản trị phù hợp.

Điều này tạo ra sự khác biệt giữa:

- Tài khoản có tư cách thành viên Administrators.
- Một tiến trình cụ thể đang chạy với quyền đã nâng.
- Một người dùng tiêu chuẩn không có sẵn quyền quản trị để tự đồng ý sử dụng.

Hành vi của tài khoản Administrator tích hợp và một số cấu hình đặc biệt có thể khác, nên phải được đánh giá riêng trong chính sách.

### 2.2 Elevation không phải thay đổi toàn bộ phiên làm việc

Nếu một quản trị viên mở một công cụ bằng “Run as administrator”, các cửa sổ khác không tự động trở thành cửa sổ quản trị. Chương trình vừa nâng quyền và các tiến trình khác vẫn có ngữ cảnh thực thi riêng.

Tuy nhiên, phạm vi tác động của chương trình đã nâng có thể lớn. Nếu nó tạo tiến trình con, chạy script, nạp plugin hoặc gọi công cụ khác, chuỗi thực thi có thể tiếp tục mang quyền cao, tùy cách chương trình tạo tiến trình và token được sử dụng.

Vì vậy, cho phép nâng quyền một chương trình không chỉ là cho phép mở giao diện của chương trình đó. Cần kiểm tra các chức năng mà chương trình có thể thực hiện sau khi nâng quyền.

### 2.3 Người dùng tiêu chuẩn và quản trị viên gặp yêu cầu khác nhau

| Ngữ cảnh | Nguồn quyền quản trị | Hành vi cần xem xét |
|---|---|---|
| Quản trị viên đang dùng token đã lọc | Quyền quản trị của chính tài khoản đó | Có thể được hỏi đồng ý hoặc nhập credential tùy chính sách |
| Người dùng tiêu chuẩn | Không có quyền quản trị sẵn để tự đồng ý | Có thể bị từ chối hoặc phải cung cấp credential của tài khoản quản trị |
| Tác vụ được Endpoint PAM broker thực hiện | Cơ chế agent hoặc dịch vụ được tổ chức cho phép | Phải tuân thủ rule, phạm vi tác vụ và cơ chế ghi log riêng |
| Service hoặc scheduled task chạy bằng danh tính đặc quyền | Cấu hình của service hoặc task | Không thể giả định sẽ xuất hiện hộp thoại UAC tương tác |

Một tác vụ chạy quyền SYSTEM thông qua service không trở nên an toàn chỉ vì UAC đang bật. Service đó cần được bảo vệ và kiểm soát theo mô hình đặc quyền của chính nó.

## 3. Consent prompt và credential prompt

### 3.1 Consent prompt: đồng ý sử dụng quyền đã có

Consent prompt yêu cầu người dùng xác nhận một hoạt động nâng quyền khi ngữ cảnh và chính sách cho phép. Với quản trị viên đang dùng token đã lọc, đây thường là quyết định sử dụng quyền quản trị của chính tài khoản.

Hộp thoại có thể hiển thị tên chương trình, publisher và thông tin nguồn. Các chi tiết đó hỗ trợ nhận biết yêu cầu, nhưng không chứng minh rằng hoạt động đã được chủ ứng dụng hoặc bộ phận bảo mật phê duyệt.

Một chương trình có chữ ký hợp lệ vẫn có thể:

- Thực hiện chức năng vượt nhu cầu công việc.
- Nhận tham số nguy hiểm.
- Nạp nội dung không được kiểm soát.
- Có lỗ hổng hoặc bị sử dụng sai mục đích.

### 3.2 Credential prompt: cần credential của danh tính quản trị

Credential prompt yêu cầu cung cấp credential phù hợp để chạy chương trình bằng danh tính có quyền cần thiết. Khi người dùng tiêu chuẩn nhập credential của một tài khoản quản trị khác, tiến trình nâng quyền có thể chạy dưới danh tính đó.

Điểm này ảnh hưởng trực tiếp đến điều tra:

- Người đăng nhập tương tác có thể là nhân viên A.
- Danh tính chạy tiến trình nâng quyền có thể là tài khoản hỗ trợ B.
- Người phê duyệt yêu cầu trong Endpoint PAM có thể là quản lý C.

Ba vai trò này cần được phân biệt trong bằng chứng. Chỉ lưu tên tài khoản quản trị B sẽ không đủ để trả lời ai yêu cầu và tại sao tác vụ được thực hiện.

Credential prompt cũng không phải lý do để phát mật khẩu local admin dùng chung cho người dùng. Nếu tổ chức cần luồng này, credential phải được quản lý qua PAM/vault và cơ chế cấp phát, giới hạn thời gian, kiểm toán, luân chuyển phù hợp.

### 3.3 Secure desktop bảo vệ tương tác với prompt

Secure desktop tách giao diện yêu cầu nâng quyền khỏi desktop tương tác thông thường. Nó giúp hạn chế khả năng chương trình thông thường cùng desktop can thiệp vào giao diện prompt.

Secure desktop có giới hạn:

- Nó không biến một yêu cầu nâng quyền nguy hiểm thành yêu cầu an toàn.
- Nó không xác minh mục đích nghiệp vụ của tác vụ.
- Nó không khôi phục độ tin cậy cho endpoint đã bị kiểm soát ở mức đặc quyền cao.
- Nó không loại bỏ hoàn toàn khả năng người dùng bị lừa bởi giao diện giả mạo bên ngoài luồng thật.

Không hướng dẫn người dùng suy luận chỉ từ hiệu ứng làm tối màn hình. Người dùng cần bắt đầu tác vụ từ nguồn đã biết, nhận diện yêu cầu dự kiến và dừng lại nếu yêu cầu xuất hiện bất ngờ.

## 4. UAC giải quyết phần nào của Endpoint PAM?

UAC hỗ trợ một số kiểm soát quan trọng:

- Duy trì ngữ cảnh làm việc thông thường với quyền hạn chế hơn cho quản trị viên khi cấu hình phù hợp.
- Đặt một bước xử lý tại thời điểm chương trình yêu cầu nâng quyền.
- Áp dụng hành vi nâng quyền thống nhất cho từng nhóm endpoint.
- Hỗ trợ người dùng nhận biết thay đổi ngữ cảnh quyền.

Những yêu cầu sau cần cơ chế bổ sung:

| Yêu cầu PAM | Vì sao riêng UAC chưa đủ | Kiểm soát bổ sung |
|---|---|---|
| Chỉ nâng quyền cho một ứng dụng nghiệp vụ | Đồng ý tại prompt không giới hạn đầy đủ chức năng ứng dụng | Rule ứng dụng, publisher/hash, đường dẫn và tham số |
| Quyền chỉ tồn tại 15 phút | Prompt không phải bộ quản lý vòng đời quyền | JIT và cơ chế thu hồi đã kiểm thử |
| Phải có ticket hợp lệ | UAC không xác minh ticket nghiệp vụ | Workflow phê duyệt và liên kết ticket |
| Không tiết lộ mật khẩu quản trị | Credential prompt vẫn cần giải pháp quản lý credential | Vault, broker hoặc cơ chế nâng quyền không trao mật khẩu |
| Ghi rõ ai yêu cầu, ai phê duyệt | Danh tính tiến trình chưa phản ánh đầy đủ quy trình | Log tương quan từ Endpoint PAM |
| Ngăn một chương trình không được phép chạy | UAC không phải chính sách cho phép ứng dụng toàn diện | Application control và bảo vệ endpoint |

Không sử dụng UAC như ranh giới bảo mật đủ để cô lập mã độc khỏi quyền quản trị của cùng một người dùng vốn đã là local admin. Loại bỏ quyền quản trị thường trực vẫn là bước nền tảng.

## 5. Các nhóm chính sách UAC cần đánh giá

Trên máy quản lý bằng Group Policy, các thiết lập UAC thường nằm trong nhóm Security Options của chính sách bảo mật máy tính. Có thể quản lý một số thiết lập tương ứng qua nền tảng quản trị endpoint khác. Tên hiển thị và khả năng áp dụng cần được đối chiếu với Windows và công cụ quản trị đang sử dụng.

### 5.1 Run all administrators in Admin Approval Mode

Thiết lập này chi phối việc sử dụng UAC và Admin Approval Mode cho quản trị viên. Baseline cần duy trì UAC hoạt động; không tắt cơ chế chỉ để một ứng dụng cũ chạy được.

Thay đổi trạng thái nền tảng của UAC có thể cần khởi động lại để có hiệu lực đầy đủ. Kế hoạch triển khai phải ghi rõ thời điểm áp dụng, yêu cầu khởi động lại và cách kiểm tra sau đó.

Nếu ứng dụng chỉ hoạt động khi tắt UAC, cần điều tra:

- Ứng dụng đang ghi vào tài nguyên hệ thống nào?
- Chức năng nào thực sự cần quyền cao?
- Có thể sửa đường dẫn dữ liệu, ACL hoặc đóng gói lại không?
- Có thể tách phần cài đặt khỏi phần chạy hằng ngày không?

Tắt UAC toàn máy để khắc phục một lỗi ứng dụng làm mở rộng ngoại lệ vượt xa ứng dụng đó.

### 5.2 Behavior of the elevation prompt for administrators

Nhóm lựa chọn này điều khiển cách quản trị viên trong Admin Approval Mode được xử lý khi nâng quyền, chẳng hạn hỏi đồng ý, hỏi credential hoặc nâng quyền không cần hỏi trong một số cấu hình.

Cần đánh giá cả mức kiểm soát lẫn khả năng vận hành:

- Hỏi đồng ý có thể phù hợp với quản trị viên sử dụng tài khoản quản trị riêng trên máy quản trị được kiểm soát.
- Hỏi credential tạo yêu cầu xác thực tại thời điểm nâng quyền, nhưng không tự tạo phê duyệt theo tác vụ hoặc cơ chế chống đánh cắp credential toàn diện.
- Nâng quyền không cần hỏi làm mất bước tương tác quan trọng và thường không phù hợp với baseline endpoint người dùng.

Một số lựa chọn phân biệt chương trình Windows với chương trình khác. Không suy luận rằng mọi hoạt động nâng quyền đều phải có prompt giống nhau hoặc mọi chương trình được hệ điều hành tin cậy đều an toàn trong mọi chuỗi thực thi.

### 5.3 Behavior of the elevation prompt for standard users

Có hai định hướng thường gặp:

**Tự động từ chối yêu cầu nâng quyền**

Phù hợp khi người dùng tiêu chuẩn phải gửi yêu cầu qua Endpoint PAM hoặc cổng hỗ trợ. Cần bảo đảm luồng nâng quyền thay thế thực sự hoạt động; nếu chỉ chặn mà chưa có luồng hợp lệ, người dùng sẽ bị gián đoạn.

**Yêu cầu credential**

Phù hợp với một số mô hình hỗ trợ được kiểm soát. Người hỗ trợ hoặc luồng PAM cung cấp danh tính quản trị theo quy trình được duyệt.

Không cung cấp một mật khẩu quản trị dùng chung để người dùng tự xử lý tất cả các prompt. Hành động đó đưa quyền quản trị thường trực trở lại dưới hình thức khác.

### 5.4 Switch to the secure desktop when prompting for elevation

Baseline thường cần giữ secure desktop cho prompt tương tác. Khi công cụ hỗ trợ từ xa không xử lý được giao diện này, phải kiểm tra cơ chế hỗ trợ chính thức của công cụ, phân quyền operator và quyền điều khiển phiên.

Không coi việc tắt secure desktop trên toàn bộ laptop là phương án mặc định để giải quyết lỗi chia sẻ màn hình. Nếu cần ngoại lệ, xác định phạm vi endpoint, lý do, biện pháp bù và ngày hết hạn.

### 5.5 Admin Approval Mode for the Built-in Administrator account

Tài khoản Administrator tích hợp cần được quản lý riêng. Trạng thái của tài khoản, chính sách Admin Approval Mode và cơ chế credential recovery đều ảnh hưởng đến luồng khẩn cấp.

Không dùng tài khoản này cho công việc thường ngày chỉ để tránh prompt. Trong mô hình break-glass, cần có:

- Chủ sở hữu tài khoản và điều kiện được sử dụng.
- Credential khác nhau giữa các endpoint và được quản lý an toàn.
- Bằng chứng truy xuất và sử dụng.
- Luân chuyển credential sau sử dụng khi quy trình yêu cầu.
- Kiểm tra trạng thái quyền và chính sách sau khi kết thúc.

### 5.6 Detect application installations and prompt for elevation

Cơ chế phát hiện cài đặt có thể hỗ trợ một số ứng dụng cài đặt cũ. Không dùng nó làm danh mục cho phép cài phần mềm.

Cách đóng gói, manifest và cơ chế triển khai ảnh hưởng đến hành vi yêu cầu nâng quyền. Một tệp không hiện prompt không đồng nghĩa nó vô hại; một tệp hiện prompt cũng không đồng nghĩa nó là installer được duyệt.

Ưu tiên phân phối phần mềm bằng kênh quản trị được kiểm soát, với gói cài đặt và nguồn nội dung đã được xác minh.

### 5.7 Chữ ký số, UIAccess và tương thích ứng dụng

Các chính sách liên quan đến xác thực chữ ký, UIAccess hoặc virtualization cần được đánh giá trong baseline tương thích:

- Yêu cầu chữ ký có thể giảm một số đường chạy ngoài kiểm soát nhưng không thay thế allowlist theo tác vụ.
- Chương trình UIAccess có khả năng tương tác đặc biệt với giao diện; không nới chính sách hoặc vị trí cài đặt chỉ để bỏ qua quy trình hỗ trợ.
- Virtualization cho file/registry hỗ trợ một số hành vi ứng dụng cũ; nó không phải quyền ghi thật vào tài nguyên hệ thống và không bảo đảm áp dụng cho mọi ứng dụng.

Nếu thay đổi các chính sách này, dùng pilot với ứng dụng đại diện. Không gom mọi thiết lập UAC thành một nút “bật bảo mật cao” rồi triển khai khi chưa biết tác động.

## 6. Chọn baseline theo nhóm endpoint

Bảng dưới là ví dụ thiết kế để thảo luận, không phải cấu hình chung cho mọi tổ chức.

| Nhóm endpoint | Mô hình tài khoản | Định hướng UAC | Luồng nâng quyền hợp lệ |
|---|---|---|---|
| Laptop nhân viên | Người dùng tiêu chuẩn | UAC bật; standard-user elevation theo baseline đã chọn | Endpoint PAM cho tác vụ cụ thể hoặc triển khai phần mềm tập trung |
| Máy phát triển | Người dùng tiêu chuẩn cho công việc hằng ngày | UAC bật; tránh admin thường trực chỉ vì cần nhiều công cụ | Rule cho công cụ/tác vụ có giới hạn, môi trường phát triển tách biệt |
| Máy quản trị chuyên dụng | Tài khoản quản trị riêng, được kiểm soát | Admin Approval Mode và prompt theo baseline máy quản trị | Tác vụ quản trị gắn với quyền đã cấp, ghi log và giới hạn đích |
| Máy hỗ trợ kỹ thuật | Tài khoản hỗ trợ tách biệt | UAC và secure desktop được kiểm thử với công cụ remote | Workflow hỗ trợ có ticket và phân quyền operator |
| Kiosk hoặc endpoint chuyên dụng | Danh tính vận hành hạn chế | Hạn chế nâng quyền tương tác | Kênh bảo trì được kiểm soát và quy trình khẩn cấp |

### 6.1 Chốt các quyết định trước khi chọn giá trị cấu hình

Một bản baseline cần trả lời tối thiểu:

1. Nhóm người nào vẫn có quyền quản trị và vì sao?
2. Người dùng tiêu chuẩn được nhập credential quản trị hay phải qua broker?
3. Tác vụ nào được cho phép mà không cần người phê duyệt trực tiếp mỗi lần?
4. Tác vụ nào cần ticket, lý do và phê duyệt?
5. Khi endpoint offline hoặc agent lỗi, cơ chế hỗ trợ là gì?
6. Ai chịu trách nhiệm kiểm thử sau cập nhật Windows, agent và ứng dụng?
7. Dữ liệu nào chứng minh tác vụ đã diễn ra theo đúng chính sách?

Nếu những câu hỏi này chưa có câu trả lời, việc chọn một giá trị registry chưa tạo thành chính sách PAM hoàn chỉnh.

### 6.2 Tránh xung đột giữa các nguồn quản trị

Một endpoint có thể nhận cấu hình từ domain Group Policy, local policy, MDM hoặc công cụ bảo mật. Không suy luận đơn giản rằng nguồn nào “luôn thắng” trong mọi trường hợp; thứ tự và khả năng áp dụng phụ thuộc thiết lập và cơ chế quản lý cụ thể.

Nên chỉ định nguồn quản trị chính cho từng thiết lập, sau đó kiểm tra:

- Endpoint có nằm đúng nhóm nhận chính sách không?
- Giá trị cấu hình dự kiến có trở thành cấu hình hiệu lực không?
- Có công cụ remediation nào tự đổi lại không?
- Có yêu cầu khởi động lại hoặc đăng nhập lại chưa hoàn tất không?
- Chính sách ngoại lệ có vô tình áp dụng cho nhóm rộng hơn không?

## 7. Kết hợp UAC với Endpoint PAM theo tác vụ

### 7.1 Luồng nâng quyền có kiểm soát

~~~mermaid
flowchart TD
    A[Người dùng tiêu chuẩn cần tác vụ đặc quyền] --> B[Endpoint PAM đánh giá yêu cầu]
    B --> C{Khớp rule hợp lệ?}
    C -->|Không| D[Từ chối hoặc chuyển phê duyệt]
    C -->|Có| E[Kiểm tra ứng dụng, nội dung và phạm vi]
    E --> F[Thực thi bằng cơ chế nâng quyền đã thiết kế]
    F --> G[Ghi danh tính, tác vụ và kết quả]
    G --> H[Thu hồi quyền hoặc kết thúc phiên đặc quyền]
~~~

Sơ đồ mô tả luồng logic. Không phải sản phẩm Endpoint PAM nào cũng dùng cùng cơ chế token hoặc hiển thị cùng prompt. Cần kiểm thử cơ chế thực tế thay vì giả định rằng mọi lần agent nâng quyền đều phải hiện hộp thoại UAC chuẩn.

Nếu standard-user elevation bị từ chối, luồng broker có thể vẫn hoạt động khi nó sử dụng dịch vụ được phân quyền để thực thi tác vụ. Đây phải là hành vi được thiết kế và kiểm thử, không phải một giả định để triển khai.

### 7.2 Rule phải bao quát những gì chương trình sẽ chạy

Ví dụ doanh nghiệp cho phép nâng quyền công cụ cấu hình VPN:

- Binary được phát hành qua kênh quản trị.
- Đường dẫn cài đặt được bảo vệ khỏi ghi sửa bởi người dùng tiêu chuẩn.
- Publisher hoặc hash được kiểm tra phù hợp với vòng đời cập nhật.
- Tham số chỉ cho phép thao tác đã duyệt.
- Không cho người dùng chọn script hoặc plugin tùy ý để chạy dưới quyền cao.
- Rule có owner và phạm vi nhóm endpoint rõ ràng.

Chỉ khớp tên “vpn-config.exe” là quá yếu. Người dùng có thể đặt một tệp khác cùng tên ở thư mục họ kiểm soát. Ngay cả khi binary gốc được bảo vệ, cấu hình, thư viện hoặc script mà nó nạp vẫn có thể là đầu vào nguy hiểm.

### 7.3 Hạn chế nâng quyền trình thông dịch và công cụ tổng quát

Cho phép nâng quyền PowerShell, Command Prompt hoặc một trình thông dịch với tham số tùy ý thường mở ra phạm vi quyền lớn hơn một tác vụ nghiệp vụ cụ thể.

Nếu nhu cầu là đổi một cấu hình mạng xác định, cân nhắc:

- Một hành động được broker cung cấp với tham số đã kiểm tra.
- Một gói thay đổi được ký và triển khai qua kênh quản trị.
- Một giao diện tác vụ hạn chế thay cho shell quản trị đầy đủ.
- Một phiên đặc quyền ngắn được phê duyệt và ghi nhận khi thật sự cần shell.

Không dùng sự xuất hiện của prompt UAC làm bằng chứng rằng một shell quản trị rộng đã được giới hạn đúng mức.

### 7.4 JIT không kết thúc chỉ bằng việc xóa thành viên nhóm

Nếu tổ chức dùng cơ chế tạm thêm người dùng vào Administrators, cần xử lý vòng đời token và tiến trình đang chạy. Token đã tạo không tự động được thay đổi chỉ vì thành viên nhóm trong cấu hình đã bị xóa.

Điều kiện kết thúc phải được thiết kế theo cơ chế thực tế, chẳng hạn kết thúc tiến trình đặc quyền, yêu cầu đăng xuất hoặc áp dụng cơ chế thu hồi của agent đã được xác minh.

“Đã xóa khỏi nhóm” và “không còn khả năng tiếp tục sử dụng quyền đã cấp” là hai kết quả cần kiểm tra riêng.

## 8. Kiểm tra trạng thái bằng thao tác chỉ đọc

Các ví dụ sau phục vụ quan sát trên máy kiểm thử được phép quản trị. Chúng không thay đổi policy.

### 8.1 Quan sát ngữ cảnh tiến trình hiện tại

~~~powershell
whoami /user
whoami /groups
whoami /priv
~~~

Thực hiện trong cửa sổ thông thường và một cửa sổ đã được nâng quyền hợp lệ, sau đó so sánh nhóm, trạng thái nhóm và đặc quyền.

Không kết luận chỉ từ việc tên “Administrators” có xuất hiện trong kết quả hay không. Nhóm có thể xuất hiện với trạng thái không cho phép sử dụng như một nhóm được bật để cấp quyền, chẳng hạn deny-only trong token đã lọc.

Tên hiển thị có thể khác theo ngôn ngữ hệ điều hành. Khi xây dựng kiểm tra tự động, nên sử dụng định danh ổn định thích hợp thay vì chỉ so khớp tên nhóm được bản địa hóa.

### 8.2 Đọc các giá trị UAC liên quan

~~~powershell
$uacPolicyPath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'

Get-ItemProperty -LiteralPath $uacPolicyPath |
    Select-Object EnableLUA,
                  ConsentPromptBehaviorAdmin,
                  ConsentPromptBehaviorUser,
                  PromptOnSecureDesktop,
                  FilterAdministratorToken
~~~

Đây là ảnh chụp cấu hình cục bộ, không phải bằng chứng duy nhất về toàn bộ hành vi thực thi.

Lưu ý khi diễn giải:

- EnableLUA và PromptOnSecureDesktop là những giá trị quan trọng để kiểm tra trạng thái UAC và secure desktop.
- Các giá trị hành vi prompt cần được ánh xạ đúng với lựa chọn policy của môi trường.
- Giá trị không có trong kết quả không tự động có nghĩa “đã tắt”; cần xét mặc định và nguồn cấu hình.
- Có thể tồn tại thay đổi chưa hoàn tất hiệu lực do yêu cầu khởi động lại.
- Endpoint PAM có thể có chính sách nâng quyền bổ sung ngoài các giá trị này.

Không sửa registry trực tiếp để “chữa nhanh” trên máy sản xuất nếu tổ chức đang quản lý các thiết lập đó qua policy.

### 8.3 Đối chiếu nguồn chính sách

Trên endpoint dùng Group Policy, có thể quan sát báo cáo văn bản:

~~~powershell
gpresult /scope computer /r
~~~

Quyền cần thiết và thông tin hiển thị phụ thuộc ngữ cảnh chạy. Kết quả này hỗ trợ xác định chính sách máy tính được áp dụng, nhưng không thay thế kiểm tra chi tiết từng thiết lập và thử hành vi nâng quyền.

Với MDM hoặc công cụ quản trị khác, thu thập báo cáo cấu hình hiệu lực tương ứng. Không dùng riêng báo cáo Group Policy để khẳng định mọi chính sách quản trị endpoint đều đúng.

## 9. Kế hoạch triển khai theo từng vòng

### 9.1 Chuẩn bị

Lập danh sách các tác vụ đang cần local admin và phân biệt:

- Cài đặt hoặc cập nhật phần mềm.
- Chạy ứng dụng hằng ngày.
- Thay đổi cấu hình hệ thống.
- Hỗ trợ từ xa.
- Bảo trì thiết bị hoặc driver.
- Khôi phục khi agent hoặc kết nối mạng gặp sự cố.

Mỗi tác vụ cần owner và phương án xử lý. Không mặc định rằng “chạy ứng dụng” cần cùng quyền với “cài đặt ứng dụng”.

### 9.2 Pilot

Chọn nhóm máy có ứng dụng và điều kiện đại diện: người dùng thông thường, lập trình viên, người làm việc từ xa, máy ít kết nối mạng và máy có công cụ hỗ trợ.

Thực hiện thay đổi qua kênh quản trị dự kiến dùng thật. Pilot bằng sửa registry thủ công có thể không phát hiện lỗi phạm vi áp dụng hoặc xung đột chính sách.

### 9.3 Mở rộng

Chỉ mở rộng khi các trường hợp bắt buộc đã có kết quả rõ ràng:

- Công việc thông thường vẫn chạy dưới quyền tiêu chuẩn.
- Tác vụ đã duyệt thực thi được qua luồng PAM.
- Tác vụ ngoài phạm vi bị chặn hoặc yêu cầu phê duyệt đúng.
- Hỗ trợ từ xa hoạt động với secure desktop theo thiết kế.
- Luồng khẩn cấp được diễn tập.
- Log đủ để tái dựng một yêu cầu.

### 9.4 Rollback có kiểm soát

Rollback cần chỉ rõ phiên bản baseline, phạm vi endpoint, người thực hiện và thời điểm hết hiệu lực. Với thay đổi cần reboot, phải có cách xác nhận endpoint đã hoàn tất reboot.

Không mặc định rollback nghĩa là cấp lại local admin cho toàn bộ người dùng hoặc tắt UAC. Có thể rollback một rule, một nhóm triển khai hoặc một thay đổi tương thích ứng dụng cụ thể.

## 10. Ma trận kiểm thử tối thiểu

| Mã | Điều kiện và thao tác | Kết quả cần chứng minh |
|---|---|---|
| UAC-01 | Người dùng tiêu chuẩn mở ứng dụng thường | Ứng dụng chạy bình thường, không đòi quyền cao không cần thiết |
| UAC-02 | Người dùng tiêu chuẩn yêu cầu nâng quyền ngoài rule | Bị từ chối hoặc đi vào luồng phê duyệt đã quy định |
| UAC-03 | Ứng dụng được duyệt nâng quyền qua Endpoint PAM | Chạy được đúng tác vụ và có log tương quan |
| UAC-04 | Đổi tên một tệp ngoài nguồn tin cậy thành tên ứng dụng được phép | Không được cấp quyền chỉ vì trùng tên |
| UAC-05 | Chạy ứng dụng được phép từ vị trí người dùng ghi được | Không được cấp quyền nếu rule yêu cầu vị trí cài đặt được bảo vệ |
| UAC-06 | Truyền tham số ngoài phạm vi cho công cụ được nâng | Bị từ chối hoặc bị giới hạn theo thiết kế |
| UAC-07 | Quản trị viên hợp lệ yêu cầu nâng quyền tương tác | Prompt và secure desktop phù hợp baseline |
| UAC-08 | Kết thúc khoảng thời gian JIT | Không còn tiến trình hoặc phiên giữ quyền ngoài thời hạn cho phép |
| UAC-09 | Hỗ trợ từ xa gặp prompt trên secure desktop | Operator xử lý được bằng luồng đã duyệt, có bằng chứng hỗ trợ |
| UAC-10 | Endpoint offline hoặc agent gặp lỗi | Luồng khẩn cấp đúng chính sách; không tự chuyển sang cho phép mọi yêu cầu |
| UAC-11 | Ứng dụng cập nhật phiên bản | Rule tiếp tục đúng phạm vi hoặc từ chối có kiểm soát, không mở rộng ngoài dự kiến |
| UAC-12 | Kiểm tra sau reboot và đồng bộ policy | Cấu hình hiệu lực khớp baseline và không bị nguồn khác ghi đè |

Các thử nghiệm tệp thay thế, tham số và ứng dụng phải thực hiện bằng dữ liệu kiểm thử lành tính trong môi trường được phép. Mục đích là xác minh giới hạn rule, không cần triển khai mã khai thác.

Mỗi ca kiểm thử cần lưu người thực hiện, endpoint, phiên bản Windows, phiên bản agent, phiên bản policy, thời điểm, kết quả dự kiến và kết quả thực tế.

## 11. Nhật ký và bằng chứng phục vụ kiểm toán

### 11.1 Những dữ liệu nên liên kết

Đối với một lần nâng quyền được Endpoint PAM quản lý, cố gắng liên kết các trường sau:

| Nhóm thông tin | Ví dụ dữ liệu |
|---|---|
| Người yêu cầu | User, thiết bị, phiên đăng nhập |
| Phê duyệt | Approver, ticket, lý do, thời gian và thời hạn |
| Đối tượng thực thi | Tên ứng dụng, đường dẫn, publisher, hash hoặc phiên bản |
| Quyết định | Rule ID, phiên bản policy, cho phép hoặc từ chối |
| Ngữ cảnh quyền | Danh tính chạy tiến trình và cơ chế nâng quyền |
| Kết quả | Bắt đầu, kết thúc, lỗi, tiến trình liên quan khi có |
| Thu hồi | Thời điểm quyền hết hạn và bằng chứng kết thúc tác vụ |

Không phải nguồn log nào cũng có toàn bộ trường. Xác định dữ liệu nào do agent, Windows, hệ thống ticket hoặc vault cung cấp và tương quan bằng định danh thích hợp.

### 11.2 Log Windows cần được cấu hình phù hợp

Nhật ký tạo tiến trình, khi bật chính sách audit tương ứng, có thể hỗ trợ quan sát danh tính và ngữ cảnh thực thi. Một số thông tin chi tiết chỉ có khi cấu hình audit bổ sung được bật.

Không giả định rằng mặc định Windows ghi một bản ghi đầy đủ cho mọi hộp thoại UAC, bao gồm cả người phê duyệt và ticket. Luồng phê duyệt nghiệp vụ cần bằng chứng từ hệ thống quản lý yêu cầu hoặc Endpoint PAM.

Command line có thể chứa dữ liệu nhạy cảm. Không truyền mật khẩu vào tham số để tiện audit; áp dụng phân quyền truy cập, bảo vệ log và chính sách lưu giữ phù hợp.

### 11.3 Câu hỏi kiểm toán cần trả lời được

Một mẫu kiểm toán tốt có thể yêu cầu tái dựng:

> Trên laptop FIN-042, vì sao công cụ cấu hình mạng được nâng quyền lúc 10:15, ai yêu cầu, rule nào cho phép, chương trình nào thực sự chạy và khi nào quyền kết thúc?

Ảnh chụp hộp thoại UAC không đủ để trả lời toàn bộ câu hỏi. Cần liên kết cấu hình hiệu lực, quyết định PAM và kết quả thực thi.

## 12. Xử lý các lỗi vận hành thường gặp

### 12.1 “Không có prompt, vậy UAC bị tắt?”

Không thể kết luận chỉ từ một lần không thấy prompt.

Các khả năng gồm:

- Chương trình không yêu cầu quyền cao.
- Chương trình đã được mở từ một tiến trình có quyền cao.
- Service hoặc agent thực hiện tác vụ bằng cơ chế riêng.
- Chính sách prompt có hành vi khác dự kiến.
- Chương trình từ chối thao tác hoặc sử dụng vị trí dữ liệu khác thay vì thực hiện nâng quyền.

Cần quan sát token, cấu hình hiệu lực, tiến trình cha và log Endpoint PAM để xác định nguyên nhân.

### 12.2 “Nhập mật khẩu quản trị rồi nhưng ứng dụng vẫn lỗi”

Nâng quyền không sửa được mọi lỗi. Nguyên nhân có thể là quyền trên tài nguyên mạng, policy ứng dụng, application control, driver, cấu hình hoặc dữ liệu theo người dùng.

Khi chạy dưới danh tính quản trị khác, ứng dụng có thể dùng profile, credential mạng và thư mục dữ liệu khác. Đừng giải quyết bằng cách tiếp tục mở rộng quyền khi chưa xác định tài nguyên bị từ chối.

### 12.3 “Ứng dụng chỉ lỗi sau khi bỏ local admin”

Xác định thao tác cụ thể gây lỗi và phân loại:

1. Có thể sửa ACL ở một thư mục dữ liệu giới hạn không?
2. Có thể chuyển cấu hình khỏi vùng hệ thống không?
3. Có phần nào chỉ cần chạy một lần lúc cài đặt không?
4. Có thể tạo tác vụ nâng quyền có giới hạn không?
5. Nếu vẫn cần ngoại lệ, phạm vi và thời hạn nhỏ nhất là gì?

Không cấp quyền ghi rộng vào thư mục chương trình hoặc service để làm ứng dụng chạy. Nếu một thành phần được nâng quyền nạp nội dung từ vùng người dùng ghi được, thay đổi ACL có thể tạo đường chiếm quyền.

### 12.4 “Remote support không bấm được prompt”

Kiểm tra công cụ có hỗ trợ secure desktop theo chế độ vận hành được phép hay không, operator có đúng quyền hay không và phiên hỗ trợ có đi đúng kênh không.

Nếu cần cơ chế hỗ trợ khác, ghi nhận ngoại lệ và kiểm thử lại. Tránh để một hạn chế của công cụ trở thành nguyên nhân nới UAC cho mọi endpoint.

### 12.5 “Policy đúng trong console nhưng máy chạy khác”

Kiểm tra đúng thiết bị, nhóm đích, lần đồng bộ gần nhất, nguồn cấu hình cạnh tranh, trạng thái reboot và phiên token hiện tại.

Phân biệt rõ:

- Giá trị được quản trị viên khai báo.
- Giá trị cục bộ đang quan sát.
- Hành vi thực tế trong một phiên cụ thể.

Ba lớp này có thể chưa đồng nhất tại thời điểm đang xử lý sự cố.

## 13. Ngoại lệ và break-glass

Một ngoại lệ UAC nên có hồ sơ tối thiểu:

- Ứng dụng hoặc tác vụ cụ thể và lý do chưa xử lý theo baseline.
- Owner nghiệp vụ và owner kỹ thuật.
- Nhóm endpoint được áp dụng.
- Thay đổi chính xác so với baseline.
- Rủi ro thực tế và biện pháp bù.
- Ngày hết hạn và tiêu chí đóng ngoại lệ.
- Kết quả kiểm thử và người duyệt.

Ví dụ, một công cụ bảo trì thiết bị cũ cần nâng quyền trên 12 máy chuyên dụng trong 30 ngày. Phương án có thể là rule giới hạn cho công cụ đó, điều kiện người vận hành và khoảng thời gian bảo trì, đi kèm giám sát. Không cần suy rộng thành quyền quản trị thường trực cho toàn bộ bộ phận.

Break-glass cần được thiết kế trước khi agent hoặc kết nối mạng gặp sự cố. Nếu có credential local recovery, phải quản lý an toàn, xác định ai được truy xuất, theo dõi sử dụng và xử lý credential sau khi kết thúc. Endpoint offline cũng cần tạo hoặc giữ bằng chứng theo khả năng của cơ chế đã chọn, rồi đồng bộ khi khôi phục kết nối.

Sau sự kiện, kiểm tra endpoint đã trở lại baseline, tiến trình đặc quyền đã kết thúc và ngoại lệ tạm đã được gỡ.

## 14. Ví dụ hoàn chỉnh: nâng quyền công cụ cấu hình VPN

### 14.1 Yêu cầu nghiệp vụ

Nhân viên đôi khi cần sửa cấu hình VPN theo một mẫu được công ty cung cấp. Công cụ có phần cần quyền hệ thống, nhưng người dùng không cần shell quản trị hay quyền cài phần mềm tùy ý.

### 14.2 Thiết kế

- Người dùng làm việc hằng ngày bằng tài khoản tiêu chuẩn.
- UAC hoạt động theo baseline của laptop nhân viên.
- Yêu cầu nâng quyền thông thường ngoài luồng được xử lý theo policy standard user.
- Endpoint PAM chỉ cho phép công cụ VPN được quản lý trong đường dẫn bảo vệ.
- Rule xác minh danh tính tệp và chỉ cho phép nhóm tham số được duyệt.
- Mẫu cấu hình được phân phối qua kênh tin cậy; người dùng không chọn script tùy ý.
- Log liên kết user, endpoint, rule, phiên bản công cụ và kết quả.
- Tác vụ kết thúc sau khi áp dụng cấu hình; không để lại cửa sổ quản trị tổng quát.

Nếu agent dùng broker để thực thi, phải xác nhận cách broker tương tác với baseline UAC trên đúng nhóm máy. Không dựa vào giả định “rule đã có thì mọi cấu hình UAC đều tương thích”.

### 14.3 Kiểm chứng

Thử cả luồng hợp lệ và các biến thể:

1. Công cụ đúng nguồn, đúng phiên bản, tham số hợp lệ: cho phép.
2. Công cụ cùng tên trong Downloads: từ chối.
3. Công cụ hợp lệ nhưng tham số yêu cầu chạy chương trình khác: từ chối.
4. Người dùng ngoài nhóm được phép: từ chối hoặc yêu cầu phê duyệt.
5. Máy offline: tuân theo policy offline đã thiết kế, không tự cho phép mọi tác vụ.
6. Agent lỗi: chuyển sang hỗ trợ hoặc break-glass có kiểm soát.
7. Sau tác vụ: không còn tiến trình đặc quyền ngoài dự kiến.

### 14.4 Bằng chứng hoàn thành

Hồ sơ triển khai có baseline UAC, rule Endpoint PAM, kết quả các ca kiểm thử, log một lần thực thi mẫu và hướng dẫn hỗ trợ. Số lượng prompt không phải tiêu chí thành công chính; tiêu chí là tác vụ hợp lệ chạy được trong phạm vi quyền đã xác định.

## 15. Bài thực hành

Trong một máy kiểm thử được phép quản trị, xây dựng phương án UAC cho hai nhóm: nhân viên tiêu chuẩn và kỹ thuật viên hỗ trợ.

### Phần A — Phân tích

Ghi nhận mô hình tài khoản, các tác vụ cần quyền cao, luồng credential và công cụ hỗ trợ từ xa. Chọn hành vi standard-user elevation và giải thích vì sao phù hợp với luồng Endpoint PAM.

### Phần B — Quan sát

Sử dụng các lệnh chỉ đọc trong bài để so sánh ngữ cảnh tiến trình thường với tiến trình được nâng quyền hợp lệ. Ghi nhận cấu hình UAC và nguồn quản trị chính sách. Không thay đổi cấu hình ngoài phạm vi được giao.

### Phần C — Thiết kế rule

Chọn một công cụ nghiệp vụ giả định và mô tả:

- Tệp hoặc publisher được tin cậy.
- Vị trí cài đặt và quyền ghi.
- Tham số được phép.
- Người dùng và endpoint được áp dụng.
- Điều kiện phê duyệt hoặc thời hạn.
- Các trường log cần có.
- Hành vi khi offline và cách thu hồi quyền.

### Phần D — Kiểm thử và bàn giao

Chọn ít nhất sáu ca trong ma trận kiểm thử, gồm luồng hợp lệ, luồng bị từ chối, hỗ trợ từ xa và thu hồi quyền.

Đầu ra là một bản baseline có lý do lựa chọn, một rule mô tả được phạm vi, kết quả kiểm thử và một mẫu bằng chứng tái dựng được tác vụ. Không dùng ảnh chụp prompt làm đầu ra duy nhất.

## 16. Tự kiểm tra

**1. Người dùng thấy consent prompt mỗi ngày có đồng nghĩa tổ chức đã quản lý đặc quyền tốt không?**

Không. Cần đánh giá quyền thường trực, phạm vi chương trình được nâng, phê duyệt, vòng đời quyền và bằng chứng. Tần suất prompt không phản ánh đầy đủ những yếu tố này.

**2. Người dùng tiêu chuẩn có thể tự đồng ý để sử dụng quyền quản trị như một thành viên Administrators không?**

Không. Họ không có sẵn quyền quản trị đó. Luồng có thể yêu cầu credential của danh tính quản trị, bị từ chối hoặc sử dụng cơ chế broker đã được tổ chức cho phép.

**3. Secure desktop có chứng minh ứng dụng được yêu cầu nâng quyền là an toàn không?**

Không. Nó bảo vệ một phần tương tác với prompt. Độ tin cậy của ứng dụng, nội dung được nạp và mục đích tác vụ vẫn cần kiểm soát riêng.

**4. Xóa người dùng khỏi nhóm Administrators sau 15 phút đã bảo đảm thu hồi mọi quyền chưa?**

Chưa. Cần kiểm tra token, tiến trình và phiên đã được tạo trước đó. Cơ chế thu hồi phải được thiết kế và kiểm thử.

**5. Một ứng dụng có chữ ký hợp lệ có nên được nâng quyền với mọi tham số không?**

Không. Chữ ký giúp xác minh nguồn hoặc tính toàn vẹn theo cơ chế tương ứng, nhưng không giới hạn toàn bộ chức năng và đầu vào của ứng dụng.

**6. Vì sao tài khoản chạy tiến trình chưa đủ để xác định người yêu cầu?**

Vì tiến trình có thể chạy bằng tài khoản hỗ trợ hoặc danh tính broker khác với người đăng nhập. Cần tương quan user, ticket, approver và rule.

**7. Khi ứng dụng chỉ chạy được sau khi tắt UAC, bước tiếp theo là gì?**

Phân tích tác vụ và tài nguyên cần quyền, kiểm tra khả năng sửa ứng dụng hoặc đóng gói, rồi thiết kế nâng quyền có giới hạn. Không coi tắt UAC toàn máy là kết luận mặc định.

## 17. Điểm cần ghi nhớ

UAC policy là một phần của kiểm soát nâng quyền trên endpoint Windows. Hiệu quả của nó phụ thuộc vào mô hình tài khoản, hành vi prompt, secure desktop và cách phối hợp với công cụ quản trị endpoint.

Trong Endpoint PAM, ưu tiên quyền tiêu chuẩn cho công việc hằng ngày, nâng quyền theo đúng tác vụ, bảo vệ credential và kiểm chứng việc thu hồi. Một baseline có thể vận hành được phải có luồng hỗ trợ, ngoại lệ có thời hạn, kiểm thử thực tế và bằng chứng đủ để giải thích từng lần sử dụng quyền quản trị.

# Cô lập admin workstation

## 1. Mục tiêu và phạm vi

Admin workstation là máy trạm dùng để thực hiện công việc quản trị: truy cập vault, mở phiên PAM, xin quyền JIT, kết nối tới máy chủ, quản trị cloud hoặc vận hành hạ tầng nhạy cảm. Máy này có thể là thiết bị vật lý chuyên dụng, máy ảo quản trị hoặc một môi trường desktop từ xa được kiểm soát. Trong bài học, thuật ngữ này chỉ môi trường thực sự chạy phiên và công cụ quản trị, không mặc định là mọi máy cá nhân của quản trị viên.

Khi một admin workstation bị nghi xâm nhập, rủi ro không dừng ở dữ liệu trên máy. Kẻ tấn công có thể lợi dụng phiên đã xác thực, credential đã được cấp, token của công cụ dòng lệnh, khóa SSH, quyền JIT đang hiệu lực hoặc đường kết nối tới hệ thống khác. Vì vậy, cô lập máy trạm là một phần của ứng phó sự cố PAM, phải phối hợp với kiểm soát danh tính, quyền đặc biệt và phiên truy cập.

Sau bài này, người học cần thực hiện được các việc sau:

- Xác định đúng máy trạm và các đường quản trị có liên quan.
- Chọn biện pháp cô lập phù hợp với mức khẩn cấp và khả năng bảo toàn bằng chứng.
- Phối hợp thu hồi quyền, đóng phiên và xử lý credential từ một môi trường tin cậy.
- Kiểm chứng việc cô lập bằng kết quả quan sát được.
- Đặt điều kiện khôi phục mà không đưa môi trường hoặc credential đáng ngờ trở lại hoạt động.

**Cô lập thành công không đồng nghĩa sự cố đã được xử lý xong.** Thiết bị có thể đã mất kết nối nhưng phiên tới máy chủ vẫn còn sống; token đã bị sao chép có thể được dùng ở nơi khác; một tài khoản dịch vụ có thể vẫn giữ quyền quá rộng. Kết quả cần đạt là giảm khả năng tiếp tục gây hại và xác định rõ phần rủi ro chưa được kiểm soát.

## 2. Vì sao admin workstation cần được xử lý như một điểm tin cậy đặc biệt?

Một máy trạm quản trị thường đứng tại giao điểm của ba loại quyền:

| Thành phần | Ví dụ | Rủi ro khi máy trạm bị xâm nhập |
|---|---|---|
| Danh tính con người | Tài khoản quản trị, phiên SSO, thiết bị đã đăng ký | Hành động có thể tiếp tục mang danh người quản trị hợp lệ |
| Vật liệu xác thực | Khóa riêng, token, credential vừa checkout từ vault | Có thể bị sao chép và sử dụng ngoài máy ban đầu |
| Đường truy cập đặc quyền | Phiên PAM, VPN quản trị, kết nối tới control plane | Có thể bị dùng để chuyển tiếp sang hệ thống có giá trị cao |

Ví dụ, một quản trị viên đã xác thực đa yếu tố để mở phiên tới máy chủ cơ sở dữ liệu. Nếu phần mềm độc hại chiếm được môi trường máy trạm sau thời điểm đó, yêu cầu nhập lại mật khẩu không phải lúc nào cũng là rào cản đối với phiên đã mở. Cần đánh giá phiên hiện hữu và quyền đang hoạt động, không chỉ trạng thái mật khẩu.

Tương tự, việc đổi mật khẩu tài khoản quản trị không tự chứng minh rằng mọi token, khóa SSH hay phiên ở hệ thống đích đều đã mất hiệu lực. Cơ chế thu hồi phụ thuộc từng loại thông tin xác thực và từng hệ thống. Runbook phải ghi rõ đã xử lý đối tượng nào, ở đâu và kiểm tra bằng cách nào.

Một nguyên tắc quan trọng là **không dùng chính máy trạm đang nghi xâm nhập để điều khiển quá trình khắc phục**. Đăng nhập tài khoản cứu hộ hoặc mở vault từ máy đó có thể làm lộ thêm credential. Kênh điều phối và công cụ quản trị ứng cứu cần được chuyển sang môi trường đã được xác minh độc lập.

## 3. Các tín hiệu có thể dẫn tới quyết định cô lập

Một cảnh báo đơn lẻ không phải lúc nào cũng chứng minh thiết bị đã bị chiếm quyền. Tuy nhiên, khi ảnh hưởng tiềm tàng liên quan tới quyền quản trị cao, đội ứng phó có thể cần cô lập trước khi có kết luận điều tra đầy đủ.

Những tín hiệu đáng chú ý gồm:

- Phát hiện hoạt động đáng ngờ liên quan tới kho credential hoặc tiến trình quản trị.
- Một phiên PAM sử dụng tài khoản đúng nhưng nguồn truy cập, thời điểm hoặc hành động không phù hợp với công việc.
- Quyền JIT được xin hoặc sử dụng ngoài phạm vi thay đổi đã được duyệt.
- Máy trạm tạo kết nối quản trị tới nhiều đích không có trong nhiệm vụ hiện tại.
- Công cụ bảo vệ bị vô hiệu hóa, mất liên lạc bất thường hoặc có dấu hiệu bị can thiệp.
- Token, khóa hoặc credential gắn với máy trạm xuất hiện trong một sự cố khác.
- Quản trị viên xác nhận không thực hiện hành động đang được ghi nhận dưới danh tính của mình.

Trước khi tác động, xác định thiết bị bằng nhiều thuộc tính nếu có thể: mã thiết bị trong hệ thống quản lý, tên máy, người đang sử dụng, mã phiên, địa chỉ mạng và thời điểm quan sát. Địa chỉ IP đơn lẻ không phải định danh bền vững; nó có thể thay đổi hoặc đại diện cho một cổng mạng dùng chung.

Trong trường hợp có dấu hiệu phá hoại đang diễn ra, không trì hoãn cô lập chỉ để hoàn thiện tất cả thuộc tính. Ghi nhận các thông tin đã biết, người quyết định và lý do hành động khẩn cấp; bổ sung điều tra sau khi đã giảm nguy cơ trước mắt.

## 4. Xác định đối tượng cần cô lập: thiết bị, phiên, danh tính và credential

Cô lập admin workstation gồm nhiều lớp độc lập. Có thể triển khai song song tùy tình huống và cơ chế kiểm soát sẵn có.

| Lớp | Hành động điển hình | Điều hành động đó chưa giải quyết |
|---|---|---|
| Thiết bị | Chặn lưu lượng từ máy trạm bằng cơ chế quản lý hoặc kiểm soát mạng | Token đã bị sao chép sang máy khác |
| Đường truy cập | Thu hồi truy cập VPN hoặc ngăn thiết bị vào vùng quản trị | Phiên đã tồn tại tại máy chủ đích |
| Phiên | Chấm dứt phiên PAM, phiên quản trị và phiên tại đích có liên quan | Credential còn khả năng tạo phiên mới |
| Danh tính và quyền | Thu hồi JIT, hạn chế hoặc tạm khóa tài khoản bị ảnh hưởng | Khóa hoặc tài khoản khác mà kẻ tấn công đã lấy được |
| Credential | Thu hồi token, vô hiệu khóa hoặc luân chuyển secret có nguy cơ lộ | Cấu hình độc hại hoặc quyền tồn tại lâu dài đã được tạo trước đó |

Không cần áp dụng mọi hành động cho mọi tài khoản trong tổ chức. Cần lập phạm vi theo chứng cứ, thời gian có nguy cơ và mức nhạy cảm. Khi chưa đủ thông tin, có thể mở rộng phạm vi kiểm soát có lý do và cập nhật dần thay vì tuyên bố đã biết chính xác toàn bộ ảnh hưởng.

Đối với một phiên PAM, tối thiểu cần đối chiếu người khởi tạo, thiết bị nguồn, tài khoản đặc quyền được sử dụng, hệ thống đích, thời điểm mở và tình trạng phiên. Nếu kết nối có nhiều chặng, cần kiểm tra từng chặng liên quan; đóng cửa sổ trên máy trạm không phải bằng chứng phiên ở đích đã chấm dứt.

## 5. Chuẩn bị kênh ứng cứu đáng tin cậy

Trước khi nhập bất kỳ credential ứng cứu nào, xác định môi trường sẽ dùng để điều khiển sự cố. Môi trường đó có thể là một máy trạm quản trị dự phòng, một môi trường ứng cứu được xây dựng riêng hoặc một kênh quản trị ngoài băng đã được kiểm soát.

Kênh ứng cứu cần đáp ứng các yêu cầu thực tế:

1. Có căn cứ cho thấy nó không cùng nằm trong phạm vi nghi xâm nhập.
2. Có thể xác thực người xử lý và ghi nhận hành động theo từng cá nhân.
3. Có đủ quyền cho biện pháp đã được phê duyệt, không cấp quyền rộng hơn chỉ vì đang có sự cố.
4. Có đường truy cập tới hệ thống quản lý cần dùng mà không phụ thuộc vào máy trạm đáng ngờ.
5. Có phương án dự phòng nếu hệ thống danh tính hoặc PAM chính cũng bị ảnh hưởng.

Tài khoản break-glass chỉ nên dùng khi cần thiết theo quy trình. Cần kiểm tra nơi sử dụng, thời hạn, người phê duyệt, nhật ký và kế hoạch thay credential sau sự cố. Không đưa credential break-glass vào kênh chat chung hoặc lưu trong ghi chú điều tra.

Nếu nghi ngờ máy trạm đã làm lộ quyền quản trị của chính nền tảng PAM, đội ứng cứu phải xem xét độ tin cậy của control plane PAM. Không thể mặc định mọi lệnh thu hồi hoặc mọi nhật ký ở đó vẫn đáng tin chỉ vì giao diện đang hoạt động.

## 6. Chọn hình thức cô lập

### 6.1. Cô lập bằng cơ chế quản lý thiết bị

Một hệ thống quản lý hoặc bảo vệ endpoint có thể cung cấp thao tác cách ly thiết bị. Lợi ích là có thể thực hiện từ xa và lưu lại dấu vết của hành động. Tuy nhiên, thông báo nhận lệnh chưa đủ để kết luận thiết bị đã thực thi.

Cần kiểm tra:

- Thiết bị được chọn có đúng là máy trạm cần xử lý không.
- Lệnh đã được thực thi hay chỉ đang chờ thiết bị kết nối.
- Phạm vi chặn bao gồm các giao diện và đường truy cập liên quan nào.
- Các kết nối đang tồn tại có thực sự bị ngắt theo cơ chế đó không.
- Ngoại lệ liên lạc phục vụ quản lý hoặc thu thập bằng chứng còn hoạt động ra sao.

Chỉ giữ lại kênh quản lý nếu cơ chế hỗ trợ, đã kiểm chứng và có phạm vi tối thiểu. Ngoại lệ quá rộng có thể tạo đường vòng ra ngoài mạng. Nếu agent bị can thiệp hoặc không phản hồi, chuyển sang biện pháp độc lập ở mạng hoặc tại chỗ.

### 6.2. Cô lập ở lớp mạng

Có thể sử dụng cơ chế kiểm soát mạng để chặn máy trạm khỏi vùng quản trị, chuyển sang vùng cách ly hoặc chặn các kết nối cụ thể. Đây là lựa chọn hữu ích khi không thể tin cậy agent trên thiết bị.

Cần chú ý đường mạng có dây, không dây, VPN, giao diện ảo và những đường ra khác mà thiết bị thực sự có. Một quy tắc chỉ chặn lưu lượng tại một cổng mạng sẽ không chứng minh các đường còn lại đã bị loại bỏ.

Biện pháp tại mạng cũng có thể ảnh hưởng tới thiết bị hoặc người dùng khác nếu định danh không chính xác. Trước khi áp dụng quy tắc theo địa chỉ mạng, đối chiếu phạm vi và kiểm tra tác động dự kiến. Không chặn cả một vùng mạng lớn chỉ vì chưa tìm được đúng thiết bị, trừ khi quyết định ứng phó đã xác nhận nhu cầu đó.

### 6.3. Cô lập vật lý

Khi điều khiển từ xa không khả dụng hoặc không đáng tin, nhân sự tại chỗ có thể ngắt các đường mạng được xác định. Cần hướng dẫn rõ thiết bị nào, đường kết nối nào và cách xác nhận hoàn tất.

Rút cáp mạng không xử lý kết nối không dây hoặc kết nối qua thiết bị khác. Đóng nắp máy cũng không phải một biện pháp cô lập có thể kiểm chứng ổn định.

Không mặc định tắt nguồn ngay lập tức. Tắt máy có thể làm mất dữ liệu dễ biến đổi phục vụ điều tra. Ngược lại, nếu thiết bị đang tiếp tục gây thiệt hại và không có cách ngăn chặn phù hợp, ưu tiên giảm thiệt hại có thể dẫn tới quyết định tắt nguồn. Người chỉ huy sự cố cần ghi nhận căn cứ và hệ quả của quyết định đó.

### 6.4. Admin workstation là máy ảo hoặc desktop từ xa

Phải phân biệt thiết bị đầu cuối của quản trị viên với môi trường desktop thực sự đang chạy phiên quản trị. Ngắt đầu cuối không đảm bảo tiến trình trong desktop từ xa đã dừng; ngắt desktop từ xa không chứng minh máy đầu cuối không làm lộ token.

Nếu môi trường quản trị là máy ảo, cần xem xét kết nối tại lớp mạng ảo, console, cơ chế khôi phục và độ tin cậy của nền tảng quản lý. Ảnh chụp máy ảo không mặc định chứa toàn bộ dữ liệu bộ nhớ, cũng không thay thế quy trình thu thập bằng chứng. Lựa chọn kỹ thuật cần được đội điều tra xác định theo nền tảng và mục tiêu thu thập.

## 7. Quy trình xử lý theo các mốc kiểm soát

Sơ đồ dưới đây thể hiện quan hệ giữa các việc chính. Một số việc có thể chạy đồng thời; không cần đợi thu thập xong toàn bộ bằng chứng mới ngăn chặn hành vi đang gây hại.

~~~mermaid
flowchart TD
    A[Phát hiện máy trạm quản trị đáng ngờ] --> B[Xác định thiết bị và mức khẩn cấp]
    B --> C[Kích hoạt kênh ứng cứu tin cậy]
    C --> D[Cô lập thiết bị và đường quản trị]
    C --> E[Thu hồi phiên, quyền và credential liên quan]
    D --> F[Kiểm chứng ngăn chặn]
    E --> F
    F --> G[Mở rộng điều tra và bảo toàn bằng chứng]
    G --> H[Khôi phục môi trường quản trị sạch]
    H --> I[Xác nhận điều kiện kết nối lại]
~~~

### Mốc 1 — Ghi nhận và nhận quyền điều phối

Tạo mã sự cố, ghi thời điểm theo một chuẩn thời gian thống nhất và xác định người chỉ huy. Tách vai trò điều phối, vận hành PAM, vận hành endpoint hoặc mạng, điều tra và chủ hệ thống đích khi cần.

Thông tin ban đầu nên bao gồm:

- Định danh thiết bị và người sử dụng.
- Tín hiệu kích hoạt, thời điểm phát hiện và khoảng thời gian có nguy cơ.
- Phiên PAM hoặc hoạt động quản trị đang biết.
- Hệ thống quan trọng có thể bị ảnh hưởng.
- Hành động khẩn cấp đã được thực hiện.
- Mức độ chắc chắn và các giả định chưa được xác minh.

### Mốc 2 — Ngăn chặn khả năng tiếp tục sử dụng quyền quản trị

Thực hiện cô lập qua kênh đã chọn. Đồng thời, đội PAM và IAM đánh giá việc chặn cấp thêm quyền JIT, thu hồi quyền đang hiệu lực, kết thúc phiên và hạn chế danh tính có nguy cơ.

Không coi việc người dùng đăng xuất khỏi một giao diện là đủ. Kiểm tra phiên tại broker, hệ thống đích và các hệ thống danh tính có liên quan theo cơ chế thực tế.

Một quyền JIT hết hạn cũng chưa phải bằng chứng mọi công việc đã khởi tạo dưới quyền đó đều dừng. Nếu có tiến trình hoặc tác vụ chạy tiếp trên máy đích, phải điều tra và xử lý tại đích.

### Mốc 3 — Xác định phạm vi credential

Lập danh sách credential có thể đã đi qua máy trạm trong khoảng thời gian có nguy cơ:

- Secret được checkout hoặc sử dụng trực tiếp.
- Token của công cụ quản trị, token truy cập API và phiên trình duyệt liên quan.
- Khóa SSH hoặc chứng chỉ đã được sử dụng.
- Credential dịch vụ được quản trị viên xem, thay hoặc cấu hình.
- Credential ứng cứu đã vô tình được nhập vào máy trong quá trình xử lý ban đầu.

Không cần xuất giá trị secret để lập danh sách. Sử dụng mã credential, tài khoản, đích sử dụng, phiên và thời điểm. Tránh sao chép thêm vật liệu xác thực vào hồ sơ sự cố.

Với mỗi mục, xác định biện pháp riêng: thu hồi token, vô hiệu khóa, thay secret, thu hồi chứng chỉ theo cơ chế hiện có hoặc chặn đường sử dụng tại đích. Nếu cơ chế thu hồi không tác động ngay tới đối tượng đã phát hành, ghi rõ khoảng trễ và biện pháp bù đắp.

### Mốc 4 — Giữ bằng chứng và mở rộng điều tra

Thu thập theo quy trình điều tra được tổ chức chấp nhận. Ưu tiên dữ liệu có nguy cơ mất, đồng thời bảo đảm việc thu thập không mở lại đường truy cập quản trị nguy hiểm.

Đối chiếu nhật ký từ nhiều nguồn: endpoint, PAM, IAM, vault, VPN, mạng và hệ thống đích. Nhật ký của chính máy nghi bị chiếm quyền có thể không đầy đủ; không sử dụng nó làm nguồn duy nhất để khẳng định không có hoạt động khác.

Xem xét các đích đã được truy cập. Cô lập một máy trạm không xóa cấu hình độc hại, tài khoản mới, tác vụ tự động hoặc quyền tồn tại lâu dài đã được tạo trên hệ thống khác.

### Mốc 5 — Khôi phục có kiểm soát

Chuẩn bị máy trạm sạch hoặc xây dựng lại từ nguồn tin cậy phù hợp với loại sự cố. Đánh giá cấu hình, bản vá, chính sách quản trị, agent bảo vệ và đăng ký thiết bị trước khi cấp lại quyền.

Không đưa nguyên hồ sơ người dùng, token cache, khóa riêng hoặc công cụ chưa rõ nguồn từ máy nghi xâm nhập sang máy mới. Dữ liệu cần phục hồi phải qua quy trình đánh giá riêng.

Khôi phục quyền theo nhu cầu công việc, thời hạn và phạm vi tối thiểu. Theo dõi chặt các phiên đầu tiên sau khôi phục và giữ khả năng thu hồi nhanh nếu xuất hiện tín hiệu bất thường.

## 8. Xử lý credential và phiên mà không gây gián đoạn không kiểm soát

Đổi hàng loạt secret ngay khi có cảnh báo có thể làm hỏng dịch vụ phụ thuộc và khiến đội vận hành mất đường ứng cứu. Nhưng giữ credential có nguy cơ lộ chỉ để tránh gián đoạn cũng để lại rủi ro.

Cần phân loại theo khả năng bị lộ, mức quyền, khả năng sử dụng từ xa, hệ thống phụ thuộc và cơ chế thay thế. Khi credential đang bị lợi dụng, chặn khả năng sử dụng trước; quy trình chuyển đổi vận hành tiếp tục theo kế hoạch sự cố.

| Đối tượng | Biện pháp cần xem xét | Bằng chứng cần tìm |
|---|---|---|
| Tài khoản quản trị con người | Hạn chế đăng nhập, thu hồi phiên và quyền JIT | Phiên cũ không dùng được, không cấp lại quyền trái phép |
| Token quản trị | Thu hồi theo cơ chế của hệ thống phát hành hoặc tài nguyên đích | Yêu cầu sử dụng token cũ bị từ chối tại đúng đích |
| Khóa SSH | Gỡ quyền tin cậy hoặc vô hiệu cơ chế cấp quyền tương ứng | Khóa cũ không tạo được phiên ở những đích trong phạm vi |
| Secret dịch vụ | Luân chuyển có phối hợp với các consumer đã xác định | Consumer dùng secret mới; secret cũ bị từ chối |
| Phiên PAM | Chấm dứt và đối chiếu trạng thái ở hệ thống đích | Không còn phiên hoặc tác vụ đặc quyền chưa được xử lý |

Các cơ chế trong bảng không phải lệnh dùng chung cho mọi sản phẩm. Runbook triển khai cần ánh xạ sang hệ thống thực tế, bao gồm quyền thực hiện và cách xác minh.

Khi luân chuyển secret dịch vụ, phải biết dịch vụ nào sử dụng và cách chúng nhận giá trị mới. Không phát tán secret mới qua kênh sự cố. Nếu cần giai đoạn chuyển tiếp, ghi thời hạn, cơ chế giám sát và thời điểm vô hiệu giá trị cũ; không để hai secret cùng hợp lệ vô thời hạn vì quên bước kết thúc.

Đối với token hoặc chứng chỉ chưa thể thu hồi ngay, có thể cần biện pháp bù tại hệ thống đích hoặc đường truy cập. Ghi rõ biện pháp đó chỉ bao phủ nơi nào. Việc chặn một nguồn mạng không loại bỏ khả năng dùng token từ nguồn khác.

## 9. Bảo toàn bằng chứng và khả năng kiểm toán

Mục tiêu của bằng chứng là giúp giải thích đã xảy ra việc gì, ai thực hiện hành động ứng phó và vì sao kết luận ngăn chặn có căn cứ.

Một hồ sơ tối thiểu có thể bao gồm:

- Cảnh báo gốc và dữ liệu định danh thiết bị tại thời điểm phát hiện.
- Dòng thời gian: phát hiện, quyết định, gửi lệnh, nhận xác nhận, kiểm chứng.
- Mã yêu cầu cô lập và kết quả thực thi ở endpoint hoặc lớp mạng.
- Mã phiên PAM, tài khoản đặc quyền, đích truy cập và thời điểm đóng phiên.
- Danh sách quyền và credential đã thu hồi hoặc luân chuyển, chỉ dùng định danh tham chiếu.
- Dữ liệu điều tra được thu thập, người thu thập, nguồn và phương thức bảo quản.
- Các kiểm tra không thành công, ngoại lệ còn tồn tại và người nhận trách nhiệm xử lý tiếp.

Giá trị băm giúp phát hiện thay đổi của một tệp bằng chứng sau khi thu thập, nhưng không tự chứng minh nội dung ban đầu đầy đủ hoặc nguồn thu thập đáng tin. Cần kết hợp với nhật ký thu thập, kiểm soát truy cập và lịch sử chuyển giao.

Dữ liệu bộ nhớ, bản ghi phiên và nhật ký có thể chứa thông tin nhạy cảm hoặc credential. Lưu chúng trong kho bằng chứng có kiểm soát, hạn chế người được đọc và áp dụng chính sách lưu giữ phù hợp. Không dán toàn bộ dữ liệu vào ticket hoặc kênh chat chỉ để tiện trao đổi.

Mẫu ghi nhận dưới đây chỉ dùng giá trị giả và định danh tham chiếu:

~~~yaml
incident_id: IR-DEMO-005
device:
  inventory_id: PAW-LAB-17
  user_ref: ADMIN-DEMO-A
containment:
  endpoint_state: isolated
  verified_at_utc: "2026-01-15T09:18:00Z"
  evidence_ref: EVIDENCE-DEMO-12
privileged_access:
  pam_session_refs:
    - SESSION-DEMO-81
  session_termination: verified_at_target
  jit_grants: revoked
  credential_actions_ref: ACTIONS-DEMO-07
open_items:
  - "Xác minh các đích mà token quản trị có thể truy cập"
recovery:
  reconnect_approved: false
~~~

Mẫu này không phải cấu hình thực thi và không chứa secret. Giá trị “isolated” chỉ nên được ghi sau khi có kiểm chứng; nếu lệnh còn chờ, ghi đúng trạng thái chờ và biện pháp thay thế.

## 10. Kiểm chứng cô lập bằng kết quả cụ thể

Cần phân biệt ba mức bằng chứng:

1. **Đã gửi yêu cầu:** hệ thống quản lý nhận thao tác.
2. **Đã thực thi:** thiết bị hoặc lớp kiểm soát xác nhận áp dụng.
3. **Đã đạt mục tiêu:** các đường truy cập và quyền liên quan bị ngăn chặn theo phạm vi đã đặt ra.

Mức thứ ba mới trả lời được câu hỏi quan trọng của ứng phó. Mỗi kiểm tra cần nguồn quan sát độc lập khi có thể và tránh tạo thêm hoạt động rủi ro trên thiết bị đáng ngờ.

| Mục tiêu | Kiểm tra phù hợp | Điều chưa thể suy ra |
|---|---|---|
| Máy trạm không vào vùng quản trị | Quan sát kiểm soát mạng và kết quả kiểm tra được phép qua các đường liên quan | Credential đã sao chép không dùng được ở nơi khác |
| Phiên PAM đã đóng | Đối chiếu trạng thái broker và hệ thống đích | Mọi tác vụ đã khởi tạo đều đã dừng |
| Quyền JIT đã thu hồi | Kiểm tra quyền hiệu lực và ngăn yêu cầu dùng quyền cũ | Các quyền thường trực khác đã hết |
| Credential cũ bị vô hiệu | Kiểm tra có kiểm soát ở đúng hệ thống sử dụng | Mọi consumer đều dùng cấu hình mới |
| Kênh điều tra còn hoạt động | Xác nhận liên lạc quản lý được phép, đúng phạm vi | Các kết nối ngoài phạm vi cũng an toàn |

Không đăng nhập lại bằng credential có nguy cơ lộ chỉ để “thử xem còn dùng được không” nếu cách thử có thể phát tán secret hoặc mở phiên nguy hiểm. Sử dụng cơ chế kiểm tra được hệ thống hỗ trợ, tài khoản kiểm chứng hoặc đội có thẩm quyền theo runbook.

Nếu không thể kiểm tra một lớp, kết luận phải nói rõ. Ví dụ: “Đã xác minh chặn truy cập từ máy trạm; chưa xác minh thu hồi token tại hệ thống X.” Đây là thông tin để điều phối hành động tiếp theo, không nên bị rút gọn thành “đã cô lập hoàn toàn”.

## 11. Tình huống minh họa

### Bối cảnh

Một quản trị viên sử dụng PAW-LAB-17 để mở phiên PAM vào máy chủ ứng dụng. Trong lúc phiên đang hoạt động, hệ thống giám sát phát hiện hoạt động đáng ngờ trên máy trạm. Vault cho thấy tài khoản này vừa sử dụng một secret quản trị khác trong cùng khoảng thời gian.

Những dữ kiện chưa biết gồm: secret có thực sự bị lấy ra hay không, token nào còn hiệu lực và máy chủ đích có bị thay đổi cấu hình không. Đội ứng phó không đợi biết hết mới ngăn chặn.

### Cách xử lý

Người chỉ huy xác nhận đúng thiết bị qua mã quản lý và phiên PAM, sau đó điều phối ba nhóm công việc:

- Nhóm endpoint cô lập PAW-LAB-17, kiểm tra trạng thái thực thi và đường kết nối còn lại.
- Nhóm PAM và IAM thu hồi quyền đang hoạt động, kết thúc phiên liên quan và xác định credential có nguy cơ.
- Nhóm hệ thống đích đối chiếu phiên, tác vụ đang chạy và các thay đổi gần thời điểm cảnh báo.

Các thao tác được điều khiển từ máy ứng cứu đã kiểm chứng. Nhóm điều tra bảo quản nhật ký và dữ liệu cần thiết theo quy trình; không nhập thêm credential vào PAW-LAB-17.

Sau khi broker báo phiên đã đóng, nhóm đích vẫn tìm thấy một tác vụ được khởi tạo trong khoảng thời gian nghi vấn. Tác vụ đó cần được đánh giá riêng. Kết quả này cho thấy đóng phiên là cần thiết nhưng chưa đủ để kết thúc ứng phó.

Secret có nguy cơ được luân chuyển theo danh sách consumer. Nhóm vận hành kiểm tra consumer nhận giá trị mới, sau đó xác nhận giá trị cũ không còn sử dụng được tại các đích trong phạm vi.

### Điều kiện để chuyển sang khôi phục

Chỉ chuyển bước khi các đường truy cập chính đã được kiểm soát, việc thu thập bằng chứng đã được điều phối và các điểm chưa rõ có người phụ trách. Máy trạm mới được chuẩn bị từ nguồn tin cậy, nhận credential mới qua cơ chế an toàn và được cấp quyền JIT theo nhiệm vụ.

Nếu điều tra phát hiện credential đã bị dùng từ một thiết bị khác, phạm vi sự cố mở rộng sang nguồn đó và các đích liên quan. Cô lập PAW-LAB-17 vẫn là một kết quả có ích, nhưng không phải ranh giới cuối cùng của sự cố.

## 12. Những sai lầm thường gặp

**Chỉ rút cáp rồi coi là xong.** Thiết bị có thể còn đường mạng khác, còn phiên tại đích hoặc có credential đã bị sao chép. Cần xác minh từng lớp có liên quan.

**Đổi mật khẩu nhưng giữ nguyên phiên và token.** Mỗi loại đối tượng có vòng đời và cơ chế thu hồi riêng. Theo dõi hành động theo định danh credential và hệ thống sử dụng.

**Dùng máy nghi xâm nhập để đăng nhập tài khoản cứu hộ.** Hành động này có thể mở rộng phạm vi lộ lọt. Chuyển sang môi trường ứng cứu tin cậy trước khi nhập credential mới.

**Tắt máy theo phản xạ trong mọi trường hợp.** Có thể làm mất dữ liệu phục vụ điều tra. Cân nhắc thiệt hại đang diễn ra, khả năng ngăn chặn khác và mục tiêu thu thập bằng chứng.

**Giữ một ngoại lệ mạng rộng để tiện điều tra.** Ngoại lệ cần được giới hạn, theo dõi và thu hồi. Nếu chưa biết chính xác phạm vi ngoại lệ, không nên coi việc cô lập đã được kiểm chứng.

**Mở lại kết nối chỉ vì công cụ quét không còn báo lỗi.** Một kết quả quét không chứng minh môi trường đã sạch hoặc mọi quyền tồn tại lâu dài đã bị loại bỏ. Khôi phục cần dựa trên kết luận điều tra và các tiêu chí tin cậy.

**Luân chuyển secret dịch vụ mà không xác định consumer.** Có thể gây gián đoạn, tạo nhu cầu dùng lại secret cũ hoặc buộc đội vận hành mở rộng quyền. Phối hợp phục hồi dịch vụ với vô hiệu credential có nguy cơ.

**Chỉ xem nhật ký trên máy trạm.** Đối chiếu với PAM, IAM, vault và hệ thống đích để giảm phụ thuộc vào một nguồn có thể bị can thiệp.

## 13. Điều kiện kết nối lại và đóng giai đoạn ngăn chặn

Kết nối lại là một thay đổi trạng thái có chủ đích, không phải thao tác tự động sau một khoảng thời gian. Người có thẩm quyền cần xác nhận tối thiểu:

- Môi trường sẽ dùng để quản trị đã được xây dựng hoặc đánh giá lại theo quy trình phù hợp.
- Phạm vi danh tính, phiên, quyền JIT và credential liên quan đã được xử lý; phần chưa xử lý có biện pháp bù và người chịu trách nhiệm.
- Các hệ thống đích trong phạm vi đã được đánh giá về phiên, tác vụ và thay đổi đáng ngờ.
- Bằng chứng cần giữ đã được bảo quản trước các thao tác có thể làm mất dữ liệu.
- Quyền được cấp lại theo least privilege, có thời hạn khi phù hợp và không khôi phục quyền rộng chỉ để tiện thao tác.
- Hệ thống giám sát có khả năng theo dõi các phiên sau khôi phục.
- Có tiêu chí tái cô lập và người trực tiếp nhận cảnh báo nếu dấu hiệu cũ xuất hiện lại.

Không cần chờ hoàn tất mọi hoạt động điều tra dài hạn để khôi phục một máy quản trị sạch, nếu các rủi ro còn lại đã được đánh giá và chấp nhận bởi đúng người có thẩm quyền. Tuy nhiên, phải phân biệt khôi phục năng lực vận hành với kết luận đóng toàn bộ sự cố.

Sau sự cố, rà soát vì sao máy trạm có thể tiếp cận những quyền hoặc credential đó. Các cải tiến có thể gồm giảm secret được hiển thị trực tiếp, giới hạn quyền thường trực, tăng sử dụng JIT/JEA, tách môi trường làm việc thường ngày khỏi môi trường quản trị và chuẩn bị đường ứng cứu độc lập. Chọn cải tiến theo nguyên nhân đã xác minh.

## 14. Bài tập thực hành theo mô phỏng

Thực hiện trong môi trường lab với tài khoản, máy trạm và đích thử nghiệm được phép. Không dùng credential sản xuất hoặc cố tạo phần mềm độc hại để diễn tập.

### Đề bài

Một admin workstation mô phỏng có hai đường kết nối mạng và một phiên PAM tới máy chủ lab. Tài khoản quản trị có một quyền JIT còn hiệu lực. Một token thử nghiệm của công cụ quản trị cũng đang tồn tại.

Hãy lập và thực hiện kịch bản diễn tập:

1. Xác định thiết bị, phiên PAM, quyền JIT, token và hệ thống đích.
2. Chọn kênh ứng cứu và ghi lý do coi kênh đó là tin cậy.
3. Mô phỏng cô lập thiết bị bằng cơ chế đã được phê duyệt trong lab.
4. Kiểm tra cả hai đường kết nối và các ngoại lệ được giữ.
5. Kết thúc phiên và đối chiếu trạng thái ở máy chủ đích.
6. Thu hồi quyền JIT và token thử nghiệm theo cơ chế có sẵn.
7. Ghi kết quả kiểm chứng, phần chưa xác minh và điều kiện khôi phục.

### Sản phẩm cần nộp

Một bảng thời gian, một sơ đồ đường truy cập, một danh sách hành động theo từng lớp và các tham chiếu bằng chứng. Không đưa giá trị token, mật khẩu hoặc khóa riêng vào tài liệu.

Bài diễn tập đạt mục tiêu khi người khác có thể dựa vào hồ sơ để phân biệt rõ: yêu cầu nào đã được gửi, biện pháp nào đã thực thi, đường truy cập nào đã bị chặn và rủi ro nào còn mở. Nếu chỉ có ảnh giao diện “success” mà không có kiểm chứng tại phạm vi cần bảo vệ, bài diễn tập chưa chứng minh được hiệu quả ngăn chặn.

## 15. Câu hỏi tự kiểm tra

1. Vì sao cô lập mạng của admin workstation chưa đủ để xử lý token đã bị sao chép?
2. Vì sao phải kiểm tra cả broker PAM và hệ thống đích khi kết thúc một phiên quản trị?
3. Khi nào việc ưu tiên ngăn thiệt hại có thể ảnh hưởng tới lựa chọn bảo toàn dữ liệu dễ biến đổi?
4. Làm thế nào giữ kênh điều tra mà không tạo ngoại lệ mạng quá rộng?
5. Vì sao thay secret dịch vụ phải đi cùng xác định consumer và vô hiệu giá trị cũ?
6. Những bằng chứng nào cần có trước khi cho môi trường quản trị kết nối lại?

Các câu trả lời nên thể hiện được mối liên hệ giữa thiết bị, danh tính, phiên, credential và hệ thống đích. Đó là cơ sở để biến thao tác cô lập một máy thành biện pháp ứng phó PAM có thể kiểm chứng và kiểm toán.

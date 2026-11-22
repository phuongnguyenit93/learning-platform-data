# Phân tách trách nhiệm bảo trì hạ tầng và cơ sở dữ liệu

Trong chương **Exadata và Cloud@Customer** của module **CLOUD_PROVIDERS_ORACLE**, việc xác định ai bảo trì từng lớp là điều kiện để vận hành cơ sở dữ liệu an toàn. Oracle có thể quản lý phần cứng Exadata và hạ tầng dịch vụ, trong khi khách hàng vẫn phải quyết định nhiều công việc liên quan đến máy ảo, phần mềm cơ sở dữ liệu, dữ liệu và ứng dụng.

Vì vậy, câu “Oracle vận hành Exadata” chưa đủ để lập kế hoạch bảo trì. Đội vận hành cần biết chính xác loại dịch vụ đang dùng, thành phần nào được thay đổi, ai cho phép thay đổi, ai thực thi và ai kiểm chứng kết quả. Với Cloud@Customer, cần bổ sung trách nhiệm của đơn vị quản lý trung tâm dữ liệu tại chỗ.

Bài học này giúp người học:

- Phân biệt bảo trì hạ tầng Exadata với bảo trì môi trường máy ảo và cơ sở dữ liệu.
- Lập ma trận trách nhiệm giữa Oracle, quản trị OCI, DBA, đội ứng dụng và đội trung tâm dữ liệu.
- Tổ chức cửa sổ bảo trì có kiểm thử, theo dõi, phân quyền và phương án khôi phục.
- Hiểu giới hạn của RAC, Data Guard, bản sao lưu và tự động hóa khi bảo trì.

## 1. Xác định mô hình dịch vụ trước khi chia trách nhiệm

Không thể áp dụng một ma trận trách nhiệm cho mọi sản phẩm có chữ Exadata. Cần phân biệt ít nhất ba mô hình sau:

| Mô hình | Đặc điểm vận hành | Hệ quả đối với bảo trì |
| --- | --- | --- |
| Exadata Database Service trên hạ tầng chuyên dụng trong OCI | Oracle cung cấp hạ tầng Exadata trong trung tâm dữ liệu của Oracle; khách hàng quản trị môi trường cơ sở dữ liệu theo phạm vi dịch vụ | Oracle bảo trì hạ tầng; khách hàng quản lý vòng đời môi trường cơ sở dữ liệu thuộc quyền kiểm soát của mình bằng các chức năng được hỗ trợ |
| Exadata Database Service on Cloud@Customer | Hạ tầng Exadata đặt tại trung tâm dữ liệu khách hàng, được Oracle quản lý theo mô hình dịch vụ | Giữ ranh giới giữa hạ tầng do Oracle quản lý và môi trường cơ sở dữ liệu của khách hàng; bổ sung trách nhiệm cơ sở vật chất và kết nối tại chỗ |
| Autonomous Database trên Exadata hoặc Cloud@Customer | Oracle tự động hóa và quản lý thêm nhiều công việc ở lớp phần mềm cơ sở dữ liệu | Không dùng nguyên ma trận của Exadata Database Service; cần xác định phạm vi Oracle thực hiện và các lựa chọn lịch bảo trì mà dịch vụ cho phép |

Phần thực hành trong bài tập trung vào **Exadata Database Service**, bao gồm triển khai trên Cloud@Customer. Autonomous Database được dùng để làm rõ sự khác biệt về trách nhiệm, không được coi là cùng một mô hình vận hành.

Trước khi thực hiện một thay đổi thật, cần đối chiếu đúng loại tài nguyên, thế hệ hạ tầng, phiên bản phần mềm và chức năng bảo trì đang được dịch vụ hỗ trợ. Các tùy chọn tự động hóa, quyền điều chỉnh lịch và cách thực thi có thể khác nhau giữa các mô hình.

## 2. Nhìn hệ thống theo từng lớp

Luồng phụ thuộc có thể biểu diễn như sau:

```text
Ứng dụng, connection pool, giao dịch nghiệp vụ
                    ↓
Database / CDB / PDB / Database Home
                    ↓
Grid Infrastructure, Clusterware, ASM
                    ↓
Máy ảo khách và hệ điều hành bên trong máy ảo
                    ↓
Hạ tầng Exadata: máy chủ, lưu trữ, lớp ảo hóa, mạng nội bộ
                    ↓
Trung tâm dữ liệu: điện, làm mát, vị trí đặt máy, kết nối bên ngoài
```

Đây là sơ đồ phụ thuộc để phân tích tác động, không phải bản mô tả chi tiết kiến trúc của mọi thế hệ Exadata.

### 2.1. Lớp hạ tầng do Oracle quản lý

Trong phạm vi dịch vụ, Oracle quản lý các thành phần hạ tầng như phần cứng Exadata, hệ thống lưu trữ, lớp ảo hóa và mạng nội bộ của hệ thống. Bảo trì có thể bao gồm thay thế linh kiện, cập nhật phần mềm hạ tầng, firmware hoặc các thành phần hệ thống liên quan.

Khách hàng theo dõi thông báo, chuẩn bị tải công việc và phối hợp cửa sổ bảo trì. Khách hàng không tự đăng nhập vào thành phần hạ tầng do Oracle quản lý để vá hoặc sửa như khi sở hữu một hệ thống Exadata tự vận hành.

### 2.2. Lớp máy ảo và môi trường cơ sở dữ liệu

Với Exadata Database Service, khách hàng chịu trách nhiệm quản lý môi trường cơ sở dữ liệu trong phạm vi dịch vụ giao cho mình. Phạm vi này bao gồm kế hoạch vòng đời phần mềm, tính tương thích của ứng dụng, cấu hình và nhiều quyết định bảo trì ở lớp máy ảo khách, Grid Infrastructure và Database Home.

Các lớp này có thể có thao tác do dịch vụ thực hiện, công cụ Oracle hỗ trợ hoặc cơ chế tự động hóa theo cấu hình. Điều đó không có nghĩa khách hàng được miễn trách nhiệm xác định lịch, chuẩn bị hệ thống và xác minh ứng dụng sau thay đổi. Ngược lại, cũng không nên suy ra DBA phải tự chạy lệnh vá thủ công cho mọi lớp.

Phải phân biệt **hệ điều hành của máy ảo khách** với **hệ điều hành/lớp ảo hóa của máy chủ hạ tầng**. Việc Oracle bảo trì máy chủ vật lý không chứng minh máy ảo khách đã được cập nhật trong cùng đợt.

### 2.3. Lớp dữ liệu và ứng dụng

Khách hàng quản lý dữ liệu, schema, tài khoản ứng dụng, phân quyền nghiệp vụ, cấu hình kết nối và khả năng xử lý lỗi của ứng dụng. Một cơ sở dữ liệu có thể ở trạng thái OPEN sau bảo trì nhưng ứng dụng vẫn lỗi vì connection pool giữ kết nối cũ hoặc driver không xử lý được việc chuyển phiên.

Vì thế, DBA xác minh trạng thái cơ sở dữ liệu; đội ứng dụng xác minh giao dịch nghiệp vụ. Hai kết quả này bổ sung cho nhau.

## 3. Tách người chịu trách nhiệm, người phê duyệt và người thực thi

Một công việc bảo trì thường có nhiều vai trò:

| Vai trò | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Chủ trì trong tổ chức khách hàng | Ai bảo đảm phần việc của khách hàng được chuẩn bị và hoàn tất? | DBA lead chủ trì đợt bảo trì Database Home |
| Người phê duyệt | Ai chấp nhận thời điểm, tác động và phương án khôi phục? | Chủ hệ thống nghiệp vụ chấp nhận cửa sổ bảo trì |
| Người thực thi | Ai thực hiện thay đổi kỹ thuật? | Dịch vụ Oracle, đội Oracle hoặc người vận hành được cấp quyền |
| Người kiểm chứng | Ai xác nhận hệ thống đạt điều kiện phục vụ? | DBA kiểm tra database; đội ứng dụng chạy giao dịch thử |

Ví dụ, khách hàng có thể cấu hình hoặc yêu cầu lịch bảo trì qua chức năng dịch vụ, còn Oracle thực hiện thay đổi hạ tầng. Trong trường hợp đó, khách hàng vẫn cần chuẩn bị ứng dụng và tổ chức kiểm chứng, nhưng không trở thành đơn vị thực thi bản vá hạ tầng.

Ngược lại, việc dịch vụ cung cấp nút bấm cập nhật Database Home không chuyển trách nhiệm kiểm tra tính tương thích SQL, driver và ứng dụng sang Oracle.

Mỗi đầu việc cần có một đầu mối chủ trì rõ ràng. Tránh ghi chung “Oracle và khách hàng chịu trách nhiệm” mà không chỉ ra bên nào làm gì và bằng chứng hoàn tất là gì.

## 4. Ma trận trách nhiệm tham khảo

Ma trận sau áp dụng ở mức nguyên tắc cho **Exadata Database Service**. Phạm vi hợp đồng dịch vụ và cơ chế hỗ trợ của tài nguyên thực tế quyết định cách thực thi cụ thể.

| Hạng mục | Phần việc của Oracle | Phần việc của khách hàng | Bằng chứng cần giữ |
| --- | --- | --- | --- |
| Phần cứng Exadata | Bảo trì, sửa chữa, thay thế theo phạm vi dịch vụ | Phối hợp tác động, thông báo nội bộ; hỗ trợ tiếp cận tại chỗ nếu cần | Thông báo bảo trì, hồ sơ hỗ trợ, kết quả hoàn tất |
| Lưu trữ, firmware, lớp ảo hóa và mạng nội bộ Exadata | Bảo trì các thành phần hạ tầng do Oracle quản lý | Chuẩn bị tải công việc và kiểm chứng sau bảo trì | Trạng thái tác vụ và số liệu vận hành trước/sau |
| Máy ảo khách và hệ điều hành bên trong máy ảo | Cung cấp cơ chế, công cụ hoặc tự động hóa theo khả năng dịch vụ | Quản lý kế hoạch vòng đời, cấu hình và việc bảo trì thuộc phạm vi khách hàng; phối hợp khi dịch vụ thực thi | Phiên bản, lịch, kết quả kiểm tra và trạng thái tác vụ |
| Grid Infrastructure, Clusterware, ASM | Cung cấp bản phát hành và cơ chế bảo trì được hỗ trợ | Lập kế hoạch, kiểm tra tương thích và điều phối thực thi theo mô hình dịch vụ | Kết quả kiểm tra trước bảo trì và sức khỏe cluster sau bảo trì |
| Database Home và phiên bản cơ sở dữ liệu | Cung cấp phần mềm, bản vá và khả năng cập nhật được hỗ trợ | Chọn lộ trình, kiểm thử, phê duyệt và xác minh cập nhật | Phiên bản mục tiêu, trạng thái bản vá và kết quả ứng dụng |
| Schema, SQL, dữ liệu và tài khoản nghiệp vụ | Hỗ trợ trong phạm vi dịch vụ khi phát sinh sự cố | Quản trị và bảo vệ dữ liệu, kiểm thử tính đúng đắn nghiệp vụ | Nhật ký thay đổi, kiểm thử và kiểm tra quyền |
| Sao lưu và phục hồi | Cung cấp chức năng theo cấu hình và phạm vi dịch vụ | Xác định chính sách, theo dõi kết quả, bảo vệ quyền truy cập và diễn tập phục hồi | Lịch sử sao lưu, kết quả phục hồi thử, RPO/RTO đo được |
| Tính sẵn sàng của ứng dụng | Duy trì các thành phần dịch vụ trong phạm vi Oracle quản lý | Thiết kế RAC/Data Guard khi phù hợp, cấu hình kết nối và kiểm thử lỗi | Kết quả chuyển dịch vụ, reconnect và giao dịch thử |
| IAM và truy cập tài nguyên | Vận hành cơ chế IAM của nền tảng | Tổ chức compartment, policy, nhóm, quyền vận hành và tài khoản cơ sở dữ liệu | Policy đã duyệt và nhật ký truy cập phù hợp từng lớp |
| Giám sát và thông báo | Cung cấp trạng thái và tín hiệu thuộc dịch vụ | Cấu hình cảnh báo, người nhận, ca trực và quy trình xử lý | Lịch sử cảnh báo và xác nhận tiếp nhận |
| Chi phí và dung lượng | Cung cấp tài nguyên và số liệu sử dụng theo dịch vụ | Dự trù năng lực, quản lý tài nguyên bổ sung và kiểm tra hóa đơn | Kế hoạch dung lượng, ngân sách và quyết định sử dụng |

Ma trận cần được chuyển thành đầu việc có tên nhóm hoặc người phụ trách thực tế. Tên vai trò như “DBA” chỉ hữu ích khi có người trực, người thay thế và kênh liên hệ rõ ràng.

## 5. Cloud@Customer: thiết bị đặt tại chỗ, trách nhiệm vẫn chia theo lớp

Cloud@Customer đưa hạ tầng vào trung tâm dữ liệu của khách hàng. Vị trí đặt máy làm phát sinh thêm sự phối hợp tại chỗ, nhưng không biến dịch vụ thành một hệ thống mà khách hàng tự bảo trì toàn bộ.

### 5.1. Những phần khách hàng phải chuẩn bị

Tùy thiết kế và yêu cầu triển khai đã thống nhất, đội trung tâm dữ liệu và mạng của khách hàng phụ trách các điều kiện như:

- Điện, làm mát, không gian đặt thiết bị và kiểm soát ra vào.
- Kết nối thuộc mạng khách hàng, định tuyến, phân giải tên và các quy tắc mạng cần thiết theo thiết kế.
- Duy trì đường kết nối quản trị/dịch vụ mà giải pháp yêu cầu để Oracle có thể vận hành và hỗ trợ.
- Quy trình cho phép kỹ thuật viên tiếp cận thiết bị, phối hợp an ninh và xử lý sự cố cơ sở vật chất.

Phạm vi cụ thể của cổng mạng, tuyến kết nối và trách nhiệm từng thiết bị phải lấy từ hồ sơ triển khai của hệ thống. Không suy đoán rằng mọi thành phần mạng trong trung tâm dữ liệu đều do Oracle quản lý.

### 5.2. Những phần không nên tự ý thay đổi

Khách hàng không tự thay ổ đĩa, cập nhật firmware, sửa cấu hình mạng nội bộ Exadata hoặc thay đổi phần mềm hạ tầng do Oracle quản lý. Khi có lỗi, cần cung cấp bằng chứng và phối hợp Oracle theo quy trình hỗ trợ.

Tương tự, không tùy tiện chặn kết nối quản trị vì cho rằng ứng dụng vẫn truy cập được database. Đường truy cập ứng dụng và đường phục vụ quản trị có thể đáp ứng các mục đích khác nhau; mất một đường có thể làm tác vụ vận hành hoặc hỗ trợ bị gián đoạn.

### 5.3. Ví dụ phân định sự cố

| Hiện tượng | Đầu mối kiểm tra ban đầu | Cách phối hợp |
| --- | --- | --- |
| Trung tâm dữ liệu mất điện hoặc làm mát bất thường | Đội cơ sở vật chất khách hàng | Khôi phục điều kiện tại chỗ và phối hợp Oracle kiểm tra hệ thống |
| Dịch vụ báo lỗi phần cứng Exadata | Oracle theo phạm vi dịch vụ | Khách hàng cung cấp tác động nghiệp vụ và hỗ trợ tiếp cận nếu cần |
| Ứng dụng không kết nối được sau thay đổi firewall khách hàng | Đội mạng khách hàng và đội ứng dụng | Kiểm tra tuyến, luật mạng và tên miền; phối hợp Oracle khi có bằng chứng liên quan dịch vụ |
| Database bị lỗi sau thay đổi schema | DBA và đội ứng dụng | Khoanh vùng thay đổi dữ liệu/SQL; mở hỗ trợ Oracle nếu cần |
| Không thực hiện được tác vụ quản trị | Đội OCI/DBA và đầu mối Oracle | Kiểm tra IAM, trạng thái tác vụ, kết nối quản trị và trạng thái dịch vụ |

“Đầu mối kiểm tra ban đầu” không phải kết luận nguyên nhân. Đội vận hành phải chuyển tiếp bằng chứng khi ranh giới lỗi thay đổi.

## 6. Hai lịch bảo trì cần được phối hợp

### 6.1. Lịch bảo trì hạ tầng

Đây là lịch liên quan đến các thành phần do Oracle quản lý. Khách hàng cần:

1. Theo dõi thông báo và xác định tài nguyên bị ảnh hưởng.
2. Kiểm tra quyền chọn hoặc điều chỉnh lịch mà dịch vụ thực tế cho phép.
3. Đánh giá khả năng chịu tải khi một thành phần tạm thời rời hệ thống.
4. Điều chỉnh các tác vụ nặng như batch, nhập dữ liệu hoặc sao lưu nếu có xung đột.
5. Bố trí người kiểm chứng trong và sau cửa sổ bảo trì.

Không mặc định mọi đợt bảo trì đều có thể trì hoãn theo ý khách hàng. Thay đổi khẩn cấp hoặc yêu cầu của dịch vụ có thể có cơ chế xử lý riêng.

### 6.2. Lịch bảo trì môi trường cơ sở dữ liệu

Đây là kế hoạch cho các thành phần như hệ điều hành máy ảo khách, Grid Infrastructure, Database Home hoặc nâng cấp phiên bản cơ sở dữ liệu trong phạm vi khách hàng điều phối.

Mỗi loại thay đổi có yêu cầu tương thích, kiểm tra và phục hồi khác nhau. Cập nhật bản vá trong một dòng phiên bản không có cùng mức tác động với nâng cấp sang phiên bản chính mới.

Thông thường nên tránh chồng một đợt bảo trì hạ tầng với một thay đổi phần mềm cơ sở dữ liệu lớn. Nếu buộc phải phối hợp, cần có thứ tự rõ ràng, xác nhận thành công giữa các bước và một người điều phối chung.

Việc gộp các thay đổi chỉ để giảm số cửa sổ có thể làm khó xác định nguyên nhân và khó khôi phục khi xảy ra lỗi.

## 7. Rolling maintenance và giới hạn của tính sẵn sàng

Rolling maintenance xử lý lần lượt các thành phần khi kiểu thay đổi và cấu hình được hỗ trợ. Cách này có thể giúp hệ thống tiếp tục phục vụ trong lúc một phần tài nguyên được bảo trì.

Tuy nhiên, rolling không đồng nghĩa mọi giao dịch đều không bị ảnh hưởng. Cần xem xét:

- Thay đổi có thật sự hỗ trợ thực hiện rolling hay cần dừng rộng hơn.
- Các node còn lại có đủ CPU, bộ nhớ, khả năng I/O và số phiên kết nối.
- Dịch vụ database có được bố trí và chuyển phù hợp giữa các instance.
- Ứng dụng có xử lý mất kết nối, hết thời gian chờ và kết nối lại.
- Các giao dịch dài có thể kết thúc trước thời điểm node bị đưa ra bảo trì hay không.

RAC hỗ trợ khả năng sẵn sàng ở lớp cluster, nhưng không tự giải quyết mọi lỗi logic của ứng dụng hoặc dữ liệu. Data Guard có thể hỗ trợ kế hoạch phục hồi và chuyển vai trò, nhưng cần cấu hình, giám sát và kiểm thử riêng.

Nếu có standby, thứ tự cập nhật primary và standby phải tuân theo kiểu thay đổi, phiên bản và quy trình được hỗ trợ. Không áp dụng một quy tắc “luôn vá standby trước” cho mọi tình huống.

Cũng cần phân biệt hai nhóm dấu hiệu:

- **Đường quản trị/điều khiển:** xem tài nguyên, gửi tác vụ, theo dõi lịch và trạng thái bảo trì.
- **Đường phục vụ dữ liệu:** ứng dụng kết nối và thực hiện giao dịch.

Lỗi ở đường quản trị chưa đủ để kết luận database đã dừng. Ngược lại, giao diện báo tác vụ hoàn tất chưa đủ để kết luận giao dịch nghiệp vụ hoạt động bình thường.

## 8. Quy trình bảo trì có thể áp dụng

### 8.1. Trước bảo trì: xác lập phạm vi và điều kiện bắt đầu

Phiếu thay đổi nên ghi rõ:

- Loại dịch vụ, tài nguyên mục tiêu, compartment, VM cluster và database liên quan.
- Lớp được thay đổi, phiên bản hiện tại, phiên bản mục tiêu và các phụ thuộc.
- Người chủ trì, người thực thi, người phê duyệt, người kiểm chứng và kênh liên lạc.
- Thời gian bắt đầu, thời gian dừng quyết định và cửa sổ phục vụ nghiệp vụ trở lại.
- Dự kiến ảnh hưởng, ngưỡng chấp nhận được và trường hợp phải dừng.
- Phương án khôi phục riêng cho phần mềm, cấu hình và dữ liệu.

Sau đó hoàn tất các việc chuẩn bị:

1. Kiểm tra sức khỏe cluster, trạng thái database, dung lượng và các cảnh báo chưa xử lý.
2. Chạy các bước kiểm tra trước bảo trì mà công cụ dịch vụ hỗ trợ.
3. Kiểm thử thay đổi trên môi trường phù hợp, bao gồm hành vi ứng dụng và kết nối lại.
4. Xác minh bản sao lưu, khả năng truy cập và kết quả phục hồi thử có liên quan.
5. Kiểm tra standby, độ trễ và phương án chuyển vai trò nếu đưa Data Guard vào kế hoạch.
6. Lưu số liệu nền về độ trễ, thông lượng, lỗi kết nối và tài nguyên còn dự phòng.
7. Xác nhận lịch Oracle và lịch nội bộ không xung đột; chuẩn bị ca trực phù hợp.

Nếu cluster đang mất dự phòng hoặc chưa rõ khả năng khôi phục, người chủ trì cần xử lý điều kiện đó trước khi bắt đầu một thay đổi tự nguyện.

### 8.2. Trong bảo trì: quan sát và kiểm soát tiến độ

Người thực thi dùng đúng luồng bảo trì được dịch vụ hỗ trợ và ghi lại mã tác vụ hoặc hồ sơ hỗ trợ liên quan. Đội giám sát theo dõi cả tiến độ kỹ thuật lẫn tác động ứng dụng.

Không khởi chạy lại thao tác chỉ vì giao diện phản hồi chậm. Trước hết phải kiểm tra xem tác vụ cũ đã được hệ thống nhận hay chưa. Hai yêu cầu trùng có thể làm việc điều phối phức tạp hơn.

Nếu một bước thất bại, lưu thời điểm, bước đang chạy, thông báo lỗi và ảnh hưởng quan sát được. Không sửa trực tiếp thành phần Oracle quản lý để “chữa cháy”. Với tác vụ thuộc khách hàng, cũng cần kiểm tra trạng thái và quy trình khôi phục được hỗ trợ trước khi can thiệp tiếp.

### 8.3. Sau bảo trì: xác nhận khả năng phục vụ

Kiểm chứng theo thứ tự phụ thuộc:

1. **Tác vụ:** trạng thái kết thúc và các cảnh báo cần xử lý.
2. **Cluster/máy ảo:** các thành phần dự kiến đã trở lại, không còn node hoặc tài nguyên ở trạng thái ngoài kế hoạch.
3. **Database:** instance, database, PDB và service liên quan hoạt động theo thiết kế.
4. **Phần mềm:** phiên bản và trạng thái cập nhật phù hợp với thay đổi vừa thực hiện.
5. **Ứng dụng:** kết nối mới, giao dịch đọc/ghi và luồng nghiệp vụ thiết yếu thành công.
6. **Bảo vệ dữ liệu:** sao lưu và standby tiếp tục hoạt động trong ngưỡng đã thống nhất.
7. **Vận hành:** cảnh báo bảo trì được khôi phục và số liệu hiệu năng nằm trong phạm vi chấp nhận.

Chỉ đóng phiếu khi có đủ bằng chứng theo phạm vi thay đổi. Một lần kiểm tra kết nối thành công không thay thế cho việc xác nhận giao dịch nghiệp vụ.

## 9. Ví dụ: bảo trì hệ thống ERP trên Cloud@Customer

Giả sử một doanh nghiệp chạy ERP trên Exadata Database Service on Cloud@Customer với RAC hai node và một standby phục vụ phương án phục hồi. Oracle thông báo một đợt bảo trì hạ tầng vào cuối tuần. Đội DBA cũng có nhu cầu cập nhật phần mềm cơ sở dữ liệu.

### 9.1. Chia công việc

| Nhóm | Công việc trước cửa sổ | Công việc trong/sau cửa sổ |
| --- | --- | --- |
| Oracle | Thông báo phạm vi và điều phối phần hạ tầng thuộc dịch vụ | Thực hiện bảo trì hạ tầng và cung cấp trạng thái theo quy trình dịch vụ |
| DBA | Kiểm tra RAC, dịch vụ, sao lưu, standby và tải dự phòng | Theo dõi database, kiểm tra trạng thái và cung cấp bằng chứng |
| Đội ứng dụng | Kiểm thử reconnect và giao dịch ERP; điều chỉnh batch | Chạy luồng nghiệp vụ thử và theo dõi lỗi ứng dụng |
| Đội OCI/IAM | Kiểm tra quyền vận hành và kênh nhận thông báo | Hỗ trợ truy cập, theo dõi tác vụ và nhật ký quản trị |
| Đội trung tâm dữ liệu/mạng | Kiểm tra điện, làm mát, kết nối và lịch thay đổi mạng | Duy trì điều kiện tại chỗ, phối hợp tiếp cận khi cần |
| Chủ hệ thống ERP | Chấp nhận cửa sổ, giới hạn ảnh hưởng và tiêu chí dừng | Quyết định phục vụ trở lại dựa trên kết quả kỹ thuật và nghiệp vụ |

### 9.2. Quyết định về hai thay đổi

Đội vận hành dành một cửa sổ riêng cho bảo trì hạ tầng. Sau khi xác nhận hệ thống ổn định, họ mới thực hiện cập nhật Database Home trong cửa sổ khác theo kế hoạch đã kiểm thử.

Trong cửa sổ hạ tầng, DBA không tự thực hiện thêm bản vá cơ sở dữ liệu. Nếu cần thay đổi phạm vi, người chủ trì phải cập nhật kế hoạch và xác nhận lại điều kiện thực hiện.

### 9.3. Đặt tiêu chí đo được

Doanh nghiệp có thể đặt ngưỡng nội bộ, chẳng hạn:

- Không chấp nhận giao dịch đã ghi nhận thành công bị mất.
- Tỷ lệ lỗi kết nối và độ trễ giao dịch phải nằm trong giới hạn đã kiểm thử.
- Tải khi chỉ còn một node phục vụ phải còn đủ dự phòng cho tải dự kiến.
- Nếu standby được dùng làm phương án khôi phục, trạng thái và độ trễ của nó phải đáp ứng mục tiêu đã chọn.

Các ngưỡng phải được gắn với số đo và thời gian quan sát cụ thể của hệ thống. Đây là tiêu chí nội bộ của ví dụ, không phải cam kết SLA hay bảo đảm RPO/RTO mặc định của Oracle.

## 10. Sao lưu, rollback và chuyển vai trò giải quyết các vấn đề khác nhau

Ba khái niệm thường bị gộp nhầm trong phiếu thay đổi:

| Cơ chế | Mục đích chính | Điều không được mặc định |
| --- | --- | --- |
| Rollback thay đổi phần mềm | Trở về trạng thái phần mềm/cấu hình trước đó theo cách được hỗ trợ | Mọi bản vá hoặc nâng cấp đều có thể quay lại nhanh và không ảnh hưởng dữ liệu |
| Khôi phục từ bản sao lưu | Phục hồi dữ liệu hoặc database về trạng thái phù hợp | Một bản sao lưu database chứa đủ mọi thành phần máy ảo, Grid Infrastructure và phần mềm cần khôi phục |
| Switchover/failover | Chuyển vai trò phục vụ sang hệ thống khác theo thiết kế | Mọi standby đều hợp lệ, độc lập và sẵn sàng tiếp nhận tải tại mọi thời điểm |

Một bản sao lưu thành công vẫn cần được đánh giá về thời điểm, tính đầy đủ, quyền truy cập và khả năng phục hồi trong thời gian yêu cầu. Nếu khôi phục cần khóa mã hóa, mật khẩu hoặc cấu hình ngoài database, kế hoạch phải bảo đảm những thành phần đó có thể được truy cập khi cần.

RPO là mục tiêu về lượng dữ liệu có thể mất, thường biểu diễn bằng thời gian; RTO là mục tiêu về thời gian khôi phục khả năng phục vụ. Để xác nhận có đạt các mục tiêu này, cần đo cả thời gian phát hiện, quyết định, thực thi khôi phục và kiểm chứng ứng dụng.

Với Cloud@Customer, cần xét cả lỗi cơ sở vật chất tại nơi đặt thiết bị. Một standby nằm trong cùng miền sự cố có thể không đáp ứng mục tiêu khôi phục khi cả địa điểm bị ảnh hưởng.

## 11. Phân quyền, nhật ký và cảnh báo

### 11.1. Phân quyền theo công việc

Trong OCI, compartment và IAM giúp tổ chức phạm vi tài nguyên và quyền thao tác. Có thể phân vai theo nhu cầu:

- Nhóm chỉ xem trạng thái và nhận thông báo bảo trì.
- Nhóm được quản lý lịch hoặc khởi chạy thao tác trên tài nguyên cần thiết.
- Nhóm quản trị IAM, độc lập với công việc bảo trì thường ngày khi tổ chức yêu cầu.
- Tài khoản hoặc principal tự động hóa được cấp quyền giới hạn cho đúng phạm vi tài nguyên.

Quyền OCI không thay thế quyền trong hệ điều hành hoặc cơ sở dữ liệu. Một người xem được VM cluster trên OCI không đương nhiên có quyền thực hiện SQL quản trị trong database.

Đối với truy cập hỗ trợ từ xa trên Cloud@Customer, cần thực hiện theo cơ chế kiểm soát và ghi nhận mà triển khai dịch vụ hỗ trợ. Không tự giả định mọi phiên hỗ trợ đều cần cùng một thao tác phê duyệt hoặc đều có cùng cơ chế truy cập.

### 11.2. Gắn nhật ký với đúng lớp

Nhật ký quản trị OCI giúp truy vết các thao tác quản lý tài nguyên thuộc phạm vi ghi nhận. Nhật ký hệ điều hành, nhật ký database, nhật ký ứng dụng và hồ sơ hỗ trợ trả lời những câu hỏi khác.

Một hồ sơ bảo trì tốt liên kết được thời gian, người khởi tạo, tài nguyên, mã tác vụ, lỗi và kết quả kiểm chứng. Không dùng một loại nhật ký để kết luận về mọi hoạt động trong hệ thống.

### 11.3. Có người nhận và xử lý cảnh báo

| Tín hiệu | Người nhận chính | Hành động mong đợi |
| --- | --- | --- |
| Thông báo lịch bảo trì hạ tầng | Đầu mối OCI và người chủ trì bảo trì | Đối chiếu lịch nghiệp vụ, chuẩn bị nguồn lực |
| Tác vụ bảo trì lỗi hoặc kéo dài bất thường | Người thực thi và ca trực | Kiểm tra trạng thái, lưu bằng chứng, phối hợp hỗ trợ |
| Mất kết nối hoặc lỗi giao dịch | Đội ứng dụng và DBA | Xác định phạm vi, kiểm tra database/service/kết nối |
| Sao lưu lỗi hoặc standby trễ | DBA và người phụ trách phục hồi | Khôi phục mức bảo vệ dữ liệu, đánh giá lại khả năng tiếp tục bảo trì |
| Bất thường điện, làm mát, mạng tại chỗ | Đội trung tâm dữ liệu và mạng | Xử lý điều kiện tại chỗ, phối hợp Oracle theo tác động |

Nếu tạm ngừng một số cảnh báo trong cửa sổ bảo trì, phải có giới hạn thời gian và người khôi phục. Vẫn cần giữ khả năng phát hiện các sự cố vượt phạm vi dự kiến.

## 12. Tự động hóa có kiểm soát

Tự động hóa phù hợp với việc thu thập trạng thái, kiểm tra điều kiện bắt đầu, nhắc lịch và tổng hợp bằng chứng. Các thao tác thay đổi phải dùng API, công cụ hoặc luồng dịch vụ thực tế được hỗ trợ cho tài nguyên.

Ví dụ sau là **mẫu hồ sơ kế hoạch nội bộ**, không phải định dạng đầu vào cho OCI CLI hay một API Oracle:

```yaml
maintenance_plan:
  change_id: CHG-ERP-042
  service_model: Exadata Database Service on Cloud@Customer
  target_layer: infrastructure
  customer_coordinator: dba-lead
  technical_executor: Oracle
  business_approver: erp-owner
  validators:
    - dba-on-call
    - erp-on-call
  prerequisites:
    - cluster_health_accepted
    - backup_recovery_evidence_accepted
    - application_reconnect_test_passed
    - site_and_network_ready
  stop_conditions:
    - unexpected_loss_of_redundancy
    - business_error_threshold_exceeded
  completion_evidence:
    - maintenance_task_result
    - database_health_result
    - erp_transaction_test_result
```

Hệ thống điều phối có thể kiểm tra các điều kiện trong hồ sơ trước khi cho phép bắt đầu bước tiếp theo. Tuy nhiên, giá trị `technical_executor: Oracle` chỉ mô tả trách nhiệm trong kế hoạch, không tự gửi yêu cầu bảo trì cho Oracle.

Nếu tự động gọi thao tác thay đổi, cần lưu mã tác vụ, kiểm tra trạng thái trước khi thử lại và xử lý trường hợp yêu cầu đã được nhận nhưng kết nối phản hồi bị ngắt. Thông tin xác thực phải được quản lý bằng cơ chế bảo mật phù hợp, không ghi mật khẩu vào hồ sơ kế hoạch hoặc nhật ký.

### 12.1. Ví dụ kiểm tra database sau bảo trì

DBA có thể dùng các truy vấn chỉ đọc sau với tài khoản được cấp quyền đọc các view cần thiết:

```sql
-- Quan sát các instance đang hiển thị trong cluster.
SELECT inst_id, instance_name, status, database_status, version
FROM gv$instance
ORDER BY inst_id;

-- Xác nhận vai trò và chế độ mở của database đang kết nối.
SELECT db_unique_name, database_role, open_mode
FROM v$database;

-- Quan sát lịch sử áp dụng phần SQL của các bản vá.
SELECT patch_id, action, status, action_time, description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

Các truy vấn này chỉ cung cấp một phần bằng chứng:

- Cần so sánh số instance quan sát được với cấu hình dự kiến; kết quả truy vấn tự nó không chứng minh đủ mọi node.
- Trường `version` trong `gv$instance` không thay thế việc xác nhận đầy đủ inventory và mức bản vá phần mềm.
- `dba_registry_sqlpatch` phản ánh lịch sử phần SQL của bản vá trong phạm vi truy vấn; không phải inventory của firmware, hệ điều hành hay Grid Infrastructure.
- Với CDB/PDB, cần kiểm tra đúng container và các PDB thuộc phạm vi thay đổi bằng quyền và phương pháp phù hợp.
- Muốn kết luận phục vụ tốt, vẫn phải kiểm tra database service, ứng dụng và chỉ số vận hành.

Chỉ cấp quyền đọc cần thiết; không cấp quyền quản trị rộng chỉ để chạy báo cáo sức khỏe.

## 13. Kiểm soát chi phí trong kế hoạch bảo trì

Khả năng bảo trì và ngân sách liên quan trực tiếp đến nhau. Nếu hệ thống chỉ đủ tài nguyên khi tất cả node đều hoạt động, một lần bảo trì rolling có thể gây thiếu năng lực phục vụ.

Kế hoạch nên tính đến:

- Tài nguyên dự phòng để chịu tải khi một phần hệ thống tạm dừng.
- Môi trường kiểm thử và tài nguyên cần cho diễn tập phục hồi.
- Dung lượng lưu trữ bổ sung, Database Home cũ hoặc dữ liệu thử được giữ trong thời gian khôi phục.
- Chi phí của phương án standby và các tài nguyên bổ sung theo mô hình tính phí thực tế.
- Thời gian trực vận hành và chi phí nghiệp vụ nếu cửa sổ kéo dài.

Không mặc định tắt hoặc xóa tài nguyên sẽ giảm chi phí theo cùng cách ở mọi hợp đồng. Với Cloud@Customer, việc đánh giá phải dựa trên cam kết và cấu hình dịch vụ đã mua.

Sau khi hết thời gian giữ phương án khôi phục, người phụ trách nên rà soát các tài nguyên bổ sung và xử lý theo kế hoạch đã duyệt. Không xóa môi trường hoặc phần mềm cũ ngay khi tác vụ cập nhật vừa báo thành công.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu và hành động phù hợp |
| --- | --- |
| “Oracle quản lý Exadata nên database tự được vá toàn bộ” | Kiểm tra riêng từng lớp; Oracle quản lý hạ tầng không đồng nghĩa toàn bộ môi trường khách hàng đã được cập nhật |
| “Cloud@Customer đặt trong phòng máy của mình nên có thể tự sửa phần cứng” | Phân chia theo phạm vi quản lý dịch vụ; phối hợp Oracle cho thành phần Oracle quản lý |
| “Có RAC thì ứng dụng chắc chắn không gián đoạn” | Kiểm thử rolling, dự phòng tài nguyên, cấu hình service và hành vi kết nối lại |
| “Có backup nên mọi thay đổi đều rollback được” | Xác định riêng cách khôi phục phần mềm, cấu hình và dữ liệu; đo thời gian thực tế |
| “Tác vụ trên giao diện thành công là đã xong” | Kiểm chứng phiên bản, sức khỏe database và luồng nghiệp vụ |
| “Mất kết nối quản trị nghĩa là dữ liệu ngừng phục vụ” | Kiểm tra độc lập đường quản trị và đường truy cập dữ liệu |
| “Cùng là Exadata nên dùng một runbook cho Autonomous và Exadata Database Service” | Lập runbook theo đúng mô hình dịch vụ và phạm vi khách hàng được phép quản lý |
| “Tự động hóa sẽ thay người chịu trách nhiệm” | Tự động hóa thực thi và thu thập bằng chứng; vẫn phải có người sở hữu quyết định và kết quả |

## 15. Checklist bàn giao cho ca bảo trì

Trước khi nhận ca, người vận hành cần trả lời được:

- [ ] Hệ thống dùng loại dịch vụ nào, lớp nào được thay đổi?
- [ ] Ai chủ trì, ai phê duyệt, ai thực thi và ai kiểm chứng từng phần?
- [ ] Thông báo Oracle đã được đối chiếu với lịch nghiệp vụ và các thay đổi khác?
- [ ] Cluster, máy ảo, database và ứng dụng đã đáp ứng điều kiện bắt đầu?
- [ ] Đã kiểm tra năng lực phục vụ khi giảm tài nguyên và hành vi kết nối lại?
- [ ] Bản sao lưu và phương án phục hồi có bằng chứng sử dụng được?
- [ ] Nếu có standby, trạng thái và kế hoạch sử dụng đã được xác nhận?
- [ ] Với Cloud@Customer, điện, làm mát, mạng và đầu mối tại chỗ đã sẵn sàng?
- [ ] Quyền thao tác, cảnh báo và kênh hỗ trợ đã được kiểm tra?
- [ ] Có ngưỡng dừng, mốc ra quyết định và hướng khôi phục cho đúng lớp?
- [ ] Đã xác định bằng chứng cần lưu để đóng phiếu thay đổi?

Kết quả cần đạt là một ranh giới trách nhiệm có thể thực thi: Oracle thực hiện phần hạ tầng thuộc phạm vi quản lý của dịch vụ; khách hàng tổ chức vòng đời môi trường cơ sở dữ liệu, bảo vệ dữ liệu và xác nhận ứng dụng. Với Cloud@Customer, khách hàng còn phải duy trì các điều kiện trung tâm dữ liệu và kết nối thuộc phạm vi của mình. Mọi cửa sổ bảo trì cần nối được những phần việc đó thành một kế hoạch có người phụ trách, điều kiện bắt đầu và tiêu chí hoàn tất rõ ràng.
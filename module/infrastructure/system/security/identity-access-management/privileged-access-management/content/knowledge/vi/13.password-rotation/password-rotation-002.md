# Rotation khi nghi bị lộ

## Mục tiêu bài học

Trong chương **Password rotation**, rotation khi nghi bị lộ là việc thay đổi mật khẩu có kiểm soát để chấm dứt khả năng sử dụng một bí mật không còn được tin cậy, đồng thời xử lý những đường truy cập và phụ thuộc liên quan.

Trong **Privileged Access Management (PAM)**, đối tượng có thể là tài khoản quản trị, tài khoản dịch vụ hoặc tài khoản có quyền trên hạ tầng nhạy cảm. Rotation phải gắn với kiểm kê quyền, least privilege, JIT/JEA, vault, giám sát phiên và bằng chứng phục vụ ứng phó sự cố.

**Đổi mật khẩu thành công không tự chứng minh sự cố đã được kiểm soát.** Credential cũ có thể còn được chấp nhận ở một phần hệ thống, phiên đã mở có thể tiếp tục hoạt động và một chủ thể đã dùng đặc quyền có thể tạo thêm đường truy cập.

Sau bài học, bạn có thể:

- Phân biệt rotation khẩn cấp với rotation theo lịch.
- Xác định phạm vi tài khoản, nguồn lộ và những khả năng còn hiệu lực.
- Chọn đường thực hiện đáng tin cậy để tránh lộ ngay mật khẩu mới.
- Điều phối thay đổi giữa vault, hệ thống đích và bên phụ thuộc.
- Xử lý kết quả chưa xác định mà không thử lại một cách mù quáng.
- Xác minh việc mất hiệu lực của credential cũ, xử lý phiên và lưu bằng chứng.
- Duy trì dịch vụ bằng phương án phù hợp thay vì khôi phục bí mật đã bị nghi lộ.

## 1. Khi nào cần coi credential không còn đáng tin cậy?

Những dấu hiệu có thể dẫn đến đánh giá khẩn cấp gồm:

- Mật khẩu xuất hiện trong log, mã nguồn, tệp cấu hình hoặc bản xuất không được phép.
- Có truy xuất bí mật từ danh tính, nguồn hoặc phạm vi bất thường.
- Thiết bị của người quản trị hoặc môi trường chạy workload bị nghi kiểm soát.
- Có đăng nhập hoặc hành động ở đích không phù hợp với công việc đã biết.
- Một người không còn được phép vẫn có thể giữ bản sao mật khẩu dùng chung.
- Vault, broker, connector hoặc cơ chế phân phối bí mật có dấu hiệu bị xâm phạm.
- Có bằng chứng chia sẻ credential ngoài quy trình được chấp nhận.

Một tín hiệu bất thường chưa tự chứng minh tài khoản đã bị chiếm quyền. Tuy nhiên, không nhất thiết phải chờ có bằng chứng sử dụng thành công mới xử lý một bí mật đã xuất hiện ở nơi không được phép.

### Phân biệt các kết luận

| Kết luận | Ý nghĩa |
| --- | --- |
| Có dấu hiệu bất thường | Cần đối chiếu ngữ cảnh và mức rủi ro |
| Có khả năng lộ | Không còn đủ cơ sở tin rằng bí mật chỉ nằm trong phạm vi được phép |
| Đã xác nhận lộ | Có bằng chứng bí mật hoặc bản sao đã nằm ngoài phạm vi được chấp nhận |
| Đã có sử dụng trái phép | Có bằng chứng về hành động không được phép |
| Đã xử lý credential | Có bằng chứng về thay đổi và mất hiệu lực theo phạm vi xác định |
| Đã kết thúc sự cố | Có quyết định rộng hơn, bao gồm các tác động và việc còn lại |

Tránh dùng một trạng thái “đã đổi mật khẩu” để thay thế tất cả các kết luận trên.

## 2. Rotation khẩn cấp khác rotation theo lịch ở đâu?

| Khía cạnh | Theo lịch | Khi nghi bị lộ |
| --- | --- | --- |
| Mục tiêu chính | Duy trì vòng đời theo chính sách | Cắt khả năng dùng một bí mật không còn tin cậy |
| Mức khẩn cấp | Theo kế hoạch và điều kiện vận hành | Theo khả năng gây tác động và dấu hiệu đang bị lạm dụng |
| Nguồn phân phối | Luồng đã được thiết kế | Phải đánh giá luồng đó còn đáng tin không |
| Bên phụ thuộc | Chuẩn bị theo lịch | Cần điều phối nhanh, có thể chấp nhận gián đoạn theo thẩm quyền |
| Credential cũ | Xử lý theo kế hoạch chuyển đổi | Không được mặc định tiếp tục cho dùng lâu để thuận tiện |
| Phiên và quyền phát sinh | Theo mục tiêu vòng đời | Cần xem xét như một phần containment |
| Khôi phục | Theo phương án đã chuẩn bị | Phải tránh làm sống lại bí mật bị nghi lộ |

Khẩn cấp không có nghĩa đổi mọi mật khẩu có thể tìm thấy mà không hiểu phạm vi. Cũng không có nghĩa trì hoãn mọi hành động đến khi kiểm kê hoàn hảo.

Cần phối hợp hai việc: hạn chế tác động hiện tại và hoàn thiện phạm vi xử lý. Quyết định ưu tiên thuộc người có thẩm quyền theo quy trình ứng phó.

## 3. Xác định mục tiêu containment cụ thể

Trước khi thay đổi, cần phát biểu mục tiêu có thể xác minh.

Ví dụ:

> Mật khẩu phiên bản cũ của tài khoản dịch vụ A không còn xác thực được tại hệ thống đích thuộc phạm vi; ứng dụng hợp lệ chuyển sang credential mới qua đường phân phối được tin cậy; phiên và đường truy cập phát sinh được xử lý theo quyết định ứng phó.

Mục tiêu này có nhiều phần, không chỉ một lệnh đổi mật khẩu.

### Những hành động có thể cần phối hợp

- Hạn chế cấp thêm credential từ vault.
- Thu hồi quyền của danh tính đang bị nghi kiểm soát.
- Hạn chế đường mạng hoặc đường phiên trong phạm vi phù hợp.
- Dừng một workload, job hoặc môi trường thực thi không còn đáng tin.
- Đổi hoặc reset mật khẩu tại nguồn có thẩm quyền.
- Chuyển các consumer hợp lệ sang bí mật mới.
- Xử lý token, phiên, khóa hoặc principal phát sinh.
- Bảo toàn và liên kết bằng chứng.

Mỗi hành động có phạm vi và tác động khác nhau. Chặn lấy bí mật mới không thu hồi được bản sao đã lấy; đổi mật khẩu không tự kết thúc mọi phiên.

## 4. Phân công trách nhiệm trước và trong thay đổi

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| Người điều phối sự cố | Xác định ưu tiên, phạm vi quyết định và phối hợp |
| Credential hoặc account owner | Giải thích nhu cầu, tài khoản và quan hệ sử dụng |
| Resource owner | Xác nhận tác động và thẩm quyền trên tài nguyên |
| Đội PAM/IAM | Quản lý vault, quyền cấp, connector và thao tác được giao |
| Chủ sở hữu ứng dụng hoặc consumer | Chuyển credential, kiểm tra chức năng và xử lý cache |
| Đội nền tảng hoặc hệ thống đích | Hỗ trợ reset, phiên, cụm và khôi phục |
| Đội bảo mật | Phân tích bằng chứng, theo dõi và đánh giá đường truy cập khác |

Một người có thể giữ nhiều vai trò, nhưng phải biết ai quyết định khi an toàn và tính sẵn sàng có xung đột.

Nếu chưa tìm được owner nghiệp vụ, cần có đầu mối điều phối tạm thời. Không để khoảng trống ownership làm trì hoãn vô thời hạn containment đã có thẩm quyền.

Quyền khẩn cấp cần có phạm vi, thời gian và bằng chứng. Không tự biến tài khoản thực hiện rotation thành quản trị toàn hệ thống vĩnh viễn.

## 5. Khoanh vùng đúng credential và hệ thống đích

Một tên tài khoản không đủ xác định phạm vi.

Cần ghi nhận:

- Principal và ID gốc khi có.
- Nguồn xác thực có thẩm quyền.
- Hệ thống, tenant, miền, instance hoặc cụm liên quan.
- Môi trường và endpoint.
- Bản ghi vault và phiên bản credential đã biết.
- Khoảng thời gian có khả năng bị phân phối ngoài phạm vi.
- Người, workload, broker hoặc công cụ đã có thể nhận.
- Các consumer và những phần chưa kiểm kê đủ.
- Quyền của principal và khả năng tạo đường truy cập khác.

Không sao chép giá trị mật khẩu vào hồ sơ để định danh đối tượng. Dùng tham chiếu được bảo vệ và thông tin phiên bản.

### Mật khẩu dùng lại và nhiều bản ghi quản lý

Nếu có dấu hiệu cùng một bí mật được dùng cho nhiều tài khoản hoặc môi trường, cần mở rộng đánh giá theo bằng chứng và mức rủi ro.

Không mặc định đổi một bản ghi vault là đã xử lý mọi đích. Cũng không mặc định hai bản ghi có tên khác nhau là hai credential độc lập.

Cần đối soát quan hệ thực tế, tránh để nhiều bộ rotation cùng thay đổi một principal.

### Nguồn xác thực bên ngoài

Nếu mật khẩu do hệ thống thư mục hoặc nguồn danh tính khác quản lý, thay đổi phải đi đến đúng nguồn có thẩm quyền. Một thao tác cục bộ tại ứng dụng đích có thể không tác động tới cơ chế xác thực đang dùng.

Không áp dụng một lệnh reset chung cho mọi loại tài khoản.

## 6. Bảo toàn bằng chứng mà không kéo dài phơi lộ

Những dữ liệu cần bảo toàn có thể gồm:

- Thời điểm và nơi phát hiện.
- Định danh credential, principal và tài nguyên.
- Các lần truy xuất, thay đổi policy và quyết định truy cập.
- Nguồn, phiên và hành động tại đích.
- Danh tính thực hiện containment hoặc rotation.
- Kết quả, lỗi và những điểm chưa xác định.

Bằng chứng cần được giới hạn quyền truy cập vì có thể mô tả hạ tầng đặc quyền.

### Không lan truyền bí mật trong quá trình xử lý

Không dán mật khẩu vào ticket, chat, ảnh chụp hoặc báo cáo. Nếu log chứa bí mật, cần hạn chế tiếp cận và bảo toàn dữ liệu liên quan theo quy trình, đồng thời ngăn tiếp tục phát tán.

Không tùy tiện xóa mọi log để “xóa mật khẩu” vì có thể làm mất bằng chứng điều tra. Việc xử lý bản chứa bí mật cần phân biệt dữ liệu phục vụ điều tra với bản sao đang tiếp tục tạo rủi ro.

Nếu bắt buộc phải xử lý vật liệu nhạy cảm trong điều tra, dùng cơ chế được bảo vệ và đúng thẩm quyền; báo cáo thông thường chỉ chứa tham chiếu.

### Làm song song khi cần

Thu thập bằng chứng không nên trở thành lý do chờ vô thời hạn trong khi khả năng lạm dụng đang tồn tại. Cần phối hợp những hành động bảo toàn và containment phù hợp với mức khẩn cấp.

Ghi rõ các giới hạn dữ liệu khi chưa thể hoàn thiện toàn bộ trước thay đổi.

## 7. Đường rotation phải còn đáng tin cậy

Nếu mật khẩu mới đi qua đúng môi trường đang bị kiểm soát, nó có thể lộ ngay sau khi được tạo.

Cần đánh giá:

- Máy hoặc danh tính của người thực hiện.
- Broker, connector và tiến trình rotation.
- Vault, policy và bên có quyền đọc.
- Pipeline hoặc công cụ nhận và phân phối bí mật.
- Môi trường runtime của consumer.
- Đích thực hiện xác thực.
- Cơ chế ghi log có làm lộ phản hồi không.

### Ví dụ về tái lộ

Một mật khẩu database bị lộ qua log của pipeline. Chỉ đổi mật khẩu rồi chạy lại pipeline với cùng cấu hình in biến bí mật có thể lặp lại sự cố.

Nếu runner bị nghi kiểm soát, xóa một dòng log không làm runner trở lại đáng tin. Cần đánh giá hoặc thay thế môi trường thực thi theo quy trình trước khi đưa credential mới vào đó.

### Thứ tự theo phụ thuộc tin cậy

Khi một danh tính mạnh có thể đọc hoặc reset nhiều credential, cần xem xét đường kiểm soát đó trước khi coi rotation ở các đích là bền vững.

Có thể cần bảo vệ hoặc phục hồi nguồn danh tính, quyền vault, connector hoặc môi trường quản trị, rồi mới phân phối bí mật mới.

Không có một thứ tự cứng áp dụng cho mọi sự cố. Kế hoạch phải dựa trên quan hệ quyền, trạng thái đang bị lạm dụng và yêu cầu duy trì dịch vụ. Những biện pháp hạn chế tạm thời có thể được thực hiện song song.

## 8. Chuẩn bị mật khẩu mới và phương án chuyển đổi

Mật khẩu mới cần được tạo bằng cơ chế ngẫu nhiên phù hợp cho mục đích bảo mật, đáp ứng giới hạn của hệ thống đích và không dùng lại giữa những tài khoản độc lập.

Không tạo mật khẩu bằng cách thêm một ký tự vào bản cũ hoặc dùng một chuỗi dễ đoán theo tên sự cố.

Cần kiểm tra khả năng của connector và đích:

- Độ dài, tập ký tự và quy tắc chấp nhận.
- Có cần mật khẩu hiện tại để đổi hay có cơ chế reset.
- Có ràng buộc ngăn đổi liên tiếp không.
- Có cho phép nhiều credential cùng hiệu lực không.
- Có đồng bộ trong cụm không và theo cơ chế nào.
- Có thể xác minh trạng thái mà không gây khóa tài khoản không.

Không tự tắt chính sách toàn hệ thống để vượt một lỗi tương thích. Nếu cần đường reset hoặc ngoại lệ, phải dùng cơ chế đúng thẩm quyền và ghi phạm vi.

### Một credential hiện hành

Nếu đích chỉ chấp nhận một mật khẩu, việc đổi có thể làm kết nối mới của consumer dùng bản cũ thất bại. Cần điều phối cập nhật hoặc chấp nhận một khoảng gián đoạn theo quyết định phù hợp.

Không hứa không gián đoạn khi khả năng hệ thống không hỗ trợ.

### Giai đoạn hai credential

Nếu nền tảng hỗ trợ nhiều credential, có thể chuyển consumer trước khi thu hồi bản cũ. Tuy nhiên, khi nghi bị lộ, mỗi khoảng cùng tồn tại vẫn giữ một đường rủi ro.

Cần giới hạn thời gian chuyển tiếp theo quyết định ứng phó và xác minh việc thu hồi cuối. Không giữ bản cũ vô thời hạn như một “dự phòng”.

## 9. Thực hiện rotation như một chuỗi trạng thái

~~~mermaid
flowchart TD
    Suspect[Phát hiện nghi lộ] --> Scope[Khoanh vùng và quyết định containment]
    Scope --> Trust[Chuẩn bị đường thực hiện tin cậy]
    Trust --> Prepare[Chuẩn bị phiên bản mới được bảo vệ]
    Prepare --> Apply[Áp dụng tại nguồn có thẩm quyền]
    Apply --> Unknown[Kết quả chưa xác định]
    Unknown --> Reconcile[Đối soát có kiểm soát]
    Reconcile --> Verify[Xác minh ở đích]
    Apply --> Verify
    Verify --> Consumers[Chuyển và kiểm tra consumer]
    Consumers --> Revoke[Xử lý credential cũ và phiên liên quan]
    Revoke --> Observe[Theo dõi và ghi bằng chứng]
~~~

Sơ đồ là mô hình trách nhiệm, không phải thứ tự lệnh có thể dùng nguyên trạng trên mọi nền tảng. Một số bước cần diễn ra song song hoặc theo trình tự khác do cơ chế đích.

### Bảo vệ trạng thái đang chuyển

Trong quá trình đổi, có thể cần lưu một phiên bản ứng viên hoặc trạng thái thao tác để phục hồi sau lỗi. Những dữ liệu đó phải được bảo vệ như bí mật, có quyền truy cập và vòng đời rõ ràng.

Không ghi mật khẩu ứng viên vào log để tránh “mất dấu” khi timeout.

### Không công bố thành công quá sớm

Phân biệt:

1. Đã tạo mật khẩu mới.
2. Đã gửi yêu cầu thay đổi.
3. Đích đã chấp nhận.
4. Vault hoặc hệ thống quản lý đã ghi đúng trạng thái.
5. Kết nối mới đã xác thực.
6. Consumer đã hoạt động.
7. Credential cũ và các phiên đã được xử lý trong phạm vi.

Mỗi trạng thái cần bằng chứng tương ứng. Thành công ở bước đầu không thay thế kết quả của các bước sau.

### Điều phối theo principal

Cần tránh hai bộ điều phối hoặc hai người đồng thời thay cùng một mật khẩu. Cơ chế khóa, phiên bản hoặc điều phối tương đương phải phù hợp với nền tảng.

Khi tiếp nhận lại một công việc đã chạy dở, phải biết trạng thái trước đó thay vì mặc định bắt đầu một rotation mới.

## 10. Xác minh tại đích và bên phụ thuộc

### 10.1. Kết nối mới bằng credential mới

Kiểm tra từ đúng đường sử dụng và đúng principal. Một phiên cũ đang hoạt động không chứng minh mật khẩu mới đã được dùng.

Với ứng dụng có connection pool, cần cách xác minh kết nối mới mà không đóng toàn bộ phiên ngoài kế hoạch.

Với broker, cần giữ liên kết người yêu cầu, tài khoản đích và phiên. Với connector, cần biết kết quả xác minh thuộc đúng tài khoản và endpoint.

### 10.2. Tác vụ hợp lệ

Đăng nhập được chưa chứng minh consumer có thể hoàn thành nhiệm vụ.

Cần chọn tác vụ đại diện đã được chấp nhận, chẳng hạn chức năng ứng dụng hoặc thao tác quản trị hẹp. Nếu nhiệm vụ cần ghi dữ liệu, một phép đọc đơn giản có thể chưa đủ.

Cách thử phải phù hợp với tác động; không dùng thao tác phá hủy trên production để làm bằng chứng.

### 10.3. Credential cũ không còn hiệu lực

Có thể xác minh bằng cơ chế trạng thái hoặc kiểm tra xác thực được kiểm soát mà nền tảng hỗ trợ.

Nếu thực hiện thử xác thực bằng phiên bản cũ, phải bảo vệ vật liệu đó, giới hạn số lần và xét nguy cơ khóa tài khoản. Không lấy bí mật từ một bản rò rỉ không tin cậy rồi phát tán để thử trên hàng loạt đích.

Cần phân biệt bị từ chối vì credential không còn hợp lệ với lỗi mạng, sai endpoint hoặc dịch vụ không sẵn sàng.

### 10.4. Cụm và phạm vi xác thực

Một endpoint thành công chưa chứng minh mọi nguồn xác thực thuộc phạm vi đã đồng nhất. Cần xét các node, vùng hoặc cơ chế cache có liên quan theo thiết kế thực tế.

Nếu hệ thống có độ trễ áp dụng, ghi rõ phần đã xác minh, phần đang chờ và giới hạn chấp nhận theo quyết định. Không tự đặt một thời gian chung rồi coi hết thời gian đó là đã an toàn.

## 11. Phiên, token và đường truy cập phát sinh

Đổi mật khẩu chủ yếu tác động đến một cơ chế xác thực. Nó không tự xử lý mọi khả năng được tạo trước đó.

Những đối tượng cần xem xét theo nền tảng gồm:

- Phiên quản trị hoặc kết nối database đang hoạt động.
- Token hoặc phiên đăng nhập có vòng đời độc lập.
- Khóa, chứng thư hoặc phương thức xác thực được thêm vào.
- Principal hoặc tài khoản mới.
- Role và binding được cấp thêm.
- Cấu hình workload, job hoặc pipeline đã bị sửa.
- Quyền quản lý audit, backup hoặc cơ chế phục hồi.

Không nên tuyên bố “đã đổi mật khẩu nên mọi truy cập đã hết”.

### Xử lý phiên có tác động

Kết thúc phiên có thể làm ngắt tác vụ hợp lệ. Người điều phối cần cân nhắc mức rủi ro và khả năng duy trì dịch vụ trong phạm vi được giao.

Nếu không kết thúc ngay được một phiên còn hiệu lực, phải ghi đó là phần rủi ro tồn tại cùng biện pháp xử lý, không coi là đã hoàn tất thu hồi.

### Những credential khác

Mật khẩu, token, khóa API, khóa SSH và chứng thư có cơ chế phát hành, thu hồi và kiểm tra khác nhau.

Nếu bằng chứng cho thấy các loại credential khác bị ảnh hưởng, cần luồng xử lý tương ứng. Không cho rằng đổi mật khẩu đồng nghĩa mọi khóa hoặc chứng thư của principal cũng mất hiệu lực.

## 12. Xử lý lỗi và kết quả chưa xác định

| Tình huống | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Mất kết nối sau yêu cầu đổi | Không biết đích đã đổi chưa | Giữ trạng thái chưa xác định và đối soát |
| Vault còn bản cũ, đích đã đổi | Consumer nhận credential không khớp | Xác minh và đưa trạng thái quản lý về đúng phiên bản |
| Vault có bản mới, đích chưa chấp nhận | Kết nối mới thất bại | Không phát hành trạng thái đã xác minh quá sớm |
| Consumer chưa nạp lại | Một phần dịch vụ tiếp tục dùng bản cũ | Điều phối chuyển đổi và kiểm tra từng consumer |
| Retry liên tục | Có thể khóa tài khoản hoặc làm lệch thêm | Giới hạn retry, phân loại lỗi và dừng đúng điều kiện |
| Đường quản trị bị nghi kiểm soát | Mật khẩu mới có thể bị lộ lại | Dùng hoặc phục hồi đường thực hiện tin cậy |
| Một đích trong phạm vi chưa cập nhật | Credential cũ có thể còn được chấp nhận | Giữ công việc mở, hạn chế đường rủi ro và xác minh tiếp |

Một thông báo lỗi không luôn chứng minh thao tác chưa xảy ra. Retry cần dựa trên trạng thái và khả năng lặp của hành động.

### Phục hồi theo hướng an toàn

Các phương án có thể gồm:

- Hoàn tất cập nhật consumer sang credential mới đã xác minh.
- Thực hiện reset có kiểm soát bằng danh tính phục hồi được bảo vệ.
- Dùng một credential mới khác qua đường tin cậy.
- Chuyển sang danh tính thay thế có phạm vi phù hợp theo quyết định.
- Hạn chế tạm thời đường truy cập trong khi xử lý dịch vụ.

Không mặc định khôi phục mật khẩu bị nghi lộ để mọi kết nối hoạt động lại. Nếu phải đưa ra quyết định khẩn cấp có rủi ro, cần đúng thẩm quyền, phạm vi, biện pháp bù đắp và thời hạn xử lý tiếp.

Một backup hoặc tệp cấu hình cũ cũng có thể đưa credential bị nghi lộ trở lại. Khôi phục phải đi cùng đối soát vòng đời bí mật.

## 13. Ví dụ xuyên suốt: mật khẩu dịch vụ xuất hiện trong log

Một pipeline triển khai in nhầm mật khẩu của tài khoản dịch vụ A vào log. Tài khoản này đang được API và một job nền dùng chung. Có truy cập bất thường tại đích, nhưng chưa đủ bằng chứng xác định nguồn sử dụng.

### 13.1. Khoanh vùng và hạn chế

Nhóm ứng phó xác định bản ghi vault, principal, quyền và các consumer đã biết. Quyền tiếp cận log chứa bí mật được hạn chế, bằng chứng được bảo vệ và cấu hình tiếp tục in bí mật được xử lý.

Nếu có dấu hiệu runner bị kiểm soát, không đưa mật khẩu mới trở lại runner đó trước khi có biện pháp phù hợp.

Nhóm xem xét hạn chế đường truy cập và các lần cấp mới theo thẩm quyền, đồng thời chuẩn bị rotation.

### 13.2. Thay đổi qua đường tin cậy

Bộ rotation được xác minh về danh tính, quyền và endpoint. Phiên bản mới được quản lý an toàn, áp dụng tại nguồn xác thực và kiểm tra.

API được chuyển sang phiên bản mới. Một kết nối mới thực hiện được chức năng hợp lệ.

### 13.3. Phụ thuộc chưa chuyển xong

Job nền vẫn dùng cấu hình cũ và bắt đầu gặp lỗi xác thực. Nhóm không bật lại mật khẩu cũ chỉ để job chạy.

Consumer owner phối hợp dừng retry không cần thiết, cập nhật cơ chế nhận bí mật và kiểm tra lần chạy phù hợp. Trong lúc đó, trạng thái chuyển đổi vẫn chưa hoàn tất.

### 13.4. Kiểm tra phạm vi còn lại

Nhóm xác minh credential cũ theo cơ chế đích, xử lý các phiên liên quan theo quyết định và kiểm tra thay đổi quyền hoặc principal trong cửa sổ nghi vấn.

Audit được liên kết giữa lần lộ, lần truy xuất, thao tác rotation, kết nối mới và hành động ở đích. Những nguồn thiếu dữ liệu được ghi rõ.

### 13.5. Kết luận đúng phạm vi

Có thể xác nhận rotation của credential trong phạm vi đã hoàn tất khi các tiêu chí liên quan đạt. Việc điều tra truy cập bất thường, khả năng lộ dữ liệu và đường truy cập phát sinh vẫn có thể tiếp tục.

Không đóng toàn bộ sự cố chỉ vì API đã kết nối lại.

## 14. Hồ sơ rotation khẩn cấp

Ví dụ sau là **mô tả hồ sơ minh họa, không phải cấu hình chạy trực tiếp của một sản phẩm**. Hồ sơ không chứa giá trị bí mật.

~~~yaml
emergency_rotation:
  reference: rotation-incident-example
  incident_reference: protected-incident-record
  reason: suspected-credential-disclosure
  coordinator_reference: authorized-incident-role

scope:
  principal_reference: service-a-runtime
  authentication_authority: production-platform-a
  managed_credential_reference: service-a-password
  affected_version_reference: version-example-old
  target_scope_reference: approved-target-scope

trusted_execution:
  management_path: verified-recovery-path
  distribution_path: approved-secret-delivery
  compromised_old_value_as_normal_fallback: prohibited

dependencies:
  - consumer_reference: service-a-api
    verification: complete
  - consumer_reference: service-a-background-job
    verification: pending

verification:
  new_target_authentication: complete
  required_consumer_operations: pending
  old_credential_invalidity: complete
  existing_session_handling: pending
  additional_access_paths_review: in-progress

evidence:
  secret_value_in_report: false
  rotation_operation_reference: protected-operation-record
  target_verification_reference: protected-target-evidence

decision:
  rotation_closure: not-yet-complete
  incident_closure: separate-decision
~~~

Các trạng thái trong hồ sơ cần có bằng chứng tương ứng. “Complete” cho một phần không tự đóng các mục còn pending.

Thông tin nguồn thực thi tin cậy cũng phải được xác nhận; một nhãn “verified” do người yêu cầu tự điền không đủ.

## 15. Tiêu chí hoàn tất và bàn giao

Một mục rotation khi nghi lộ có thể cần các tiêu chí sau, tùy phạm vi:

- Đúng principal, credential và nguồn xác thực được xác định.
- Nguồn phát tán hoặc đường không tin cậy đã được xử lý trong phạm vi quyết định.
- Credential mới được tạo và phân phối qua đường được chấp nhận.
- Đích chấp nhận credential mới.
- Những consumer trong phạm vi dùng được cơ chế mới và tác vụ hợp lệ.
- Credential cũ không còn hiệu lực trên phạm vi cần xử lý.
- Phiên, token và đường quyền phát sinh được xử lý hoặc có trạng thái rõ.
- Audit và bằng chứng liên kết được những kết luận trên.
- Quyền khẩn cấp hoặc biện pháp tạm thời được review.
- Người vận hành nhận bàn giao cùng phần việc còn lại.

### Trạng thái cần tách riêng

| Trạng thái | Ý nghĩa |
| --- | --- |
| Đang containment | Hạn chế tác động và hoàn thiện phạm vi |
| Rotation chưa rõ kết quả | Cần đối soát thay đổi tại đích hoặc kho |
| Credential mới đã xác minh | Chưa tự chứng minh consumer và phiên cũ đã xử lý |
| Đã chuyển consumer | Chưa tự chứng minh mọi đường truy cập phát sinh đã bị thu hồi |
| Rotation hoàn tất trong phạm vi | Đạt tiêu chí của credential và phạm vi đã định nghĩa |
| Sự cố còn mở | Những vấn đề điều tra hoặc khắc phục khác còn tồn tại |

Nếu còn một ngoại lệ, phải ghi tài nguyên, chủ sở hữu, rủi ro, biện pháp bù đắp và thời hạn hoặc điều kiện xem xét. Không tính ngoại lệ thành đã vô hiệu hóa credential cũ.

## 16. Theo dõi sau thay đổi và cải thiện kiểm soát

Sau rotation, cần theo dõi các tín hiệu liên quan:

- Lỗi xác thực còn dùng phiên bản cũ.
- Job hoặc consumer bị bỏ sót.
- Truy xuất bí mật từ nguồn không mong đợi.
- Phiên hoặc hoạt động đặc quyền còn tồn tại.
- Thay đổi principal, role hoặc phương thức xác thực.
- Log hoặc cấu hình tiếp tục làm lộ bí mật.
- Ngoại lệ và quyền khẩn cấp chưa được kết thúc.

Không có cảnh báo chưa đủ chứng minh không còn hoạt động nếu đường giám sát thiếu dữ liệu.

### Chỉ số cần tách

Có thể đo khoảng thời gian từ lúc phát hiện đến hạn chế đường cấp mới, đến xác minh credential cũ mất hiệu lực, đến hoàn tất chuyển consumer và đến xử lý phiên.

Các mốc này phản ánh những kết quả khác nhau. Không dùng thời gian đổi mật khẩu trên vault làm đại diện cho toàn bộ thời gian containment.

Cửa sổ có khả năng phơi lộ cũng cần ghi giới hạn: thời điểm phát hiện có thể muộn hơn thời điểm bí mật bắt đầu bị tiếp cận ngoài phạm vi.

### Giảm nguy cơ tái diễn

Tùy nguyên nhân, có thể cần:

- Sửa cơ chế ghi log và xử lý bí mật trong pipeline.
- Tách principal cho các consumer khác mục đích.
- Thu hẹp quyền ở đích và quyền truy xuất vault.
- Giảm phân phối bí mật trực tiếp cho con người.
- Dùng danh tính hoặc credential ngắn hạn khi phù hợp.
- Cải thiện kiểm kê consumer và kiểm tra rotation.
- Bảo vệ đường quản trị, audit và phục hồi.

JIT, JEA và vault hỗ trợ giảm rủi ro nhưng không tự sửa một workload bị kiểm soát hoặc một principal có quyền quá rộng.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chờ có bằng chứng đăng nhập trái phép mới xử lý bí mật đã lộ | Kéo dài khả năng bị sử dụng | Đánh giá khẩn cấp theo phơi lộ và mức tác động |
| Chỉ đổi giá trị trong vault | Đích có thể vẫn chấp nhận bản cũ | Thay đúng nguồn xác thực và xác minh |
| Đưa mật khẩu mới qua runner không tin cậy | Bí mật mới có thể lộ ngay | Xử lý đường thực thi và phân phối |
| Đổi mật khẩu rồi coi mọi phiên đã hết | Đặc quyền có thể tiếp tục | Kiểm tra phiên, token và quyền phát sinh |
| Không kiểm kê consumer | Gây gián đoạn hoặc giữ đường dùng bản cũ | Điều phối consumer và kiểm tra kết nối mới |
| Retry đổi liên tục khi timeout | Lệch trạng thái hoặc khóa tài khoản | Giữ trạng thái chưa xác định và đối soát |
| Khôi phục mật khẩu nghi lộ để giảm lỗi | Mở lại đường rủi ro | Chọn phương án phục hồi phù hợp qua đường tin cậy |
| Dán bí mật vào ticket điều tra | Tạo thêm bản sao ngoài kiểm soát | Dùng tham chiếu và bằng chứng được bảo vệ |
| Xóa mọi log chứa bí mật ngay lập tức | Có thể mất bằng chứng | Phối hợp bảo toàn và hạn chế phát tán |
| Rotation xong là đóng sự cố | Bỏ sót tác động hoặc đường truy cập khác | Tách tiêu chí rotation với quyết định kết thúc sự cố |

## 18. Bài tập tự đánh giá

Một mật khẩu quản trị bị lộ trong log triển khai. Nhóm đổi mật khẩu bằng chính pipeline đó, cập nhật vault và thấy một phiên quản trị đang mở vẫn chạy được. Ứng dụng bắt đầu lỗi ở những kết nối mới. Để khôi phục nhanh, nhóm định đưa mật khẩu cũ trở lại.

Hãy trả lời:

1. Vì sao mật khẩu mới có thể vẫn chưa đáng tin?
2. Phiên đang hoạt động chứng minh điều gì và chưa chứng minh điều gì?
3. Cần kiểm tra những lớp nào khi ứng dụng lỗi kết nối mới?
4. Vì sao khôi phục mật khẩu cũ có thể làm mất mục tiêu containment?
5. Cần bằng chứng nào trước khi đóng mục rotation?
6. Những vấn đề nào có thể còn khiến sự cố tiếp tục mở?

### Gợi ý phân tích

**Đường thực hiện:** pipeline có thể vẫn ghi bí mật hoặc không còn đáng tin. Cần xử lý nguồn phát tán và môi trường trước khi coi mật khẩu mới đã được bảo vệ.

**Phiên:** chỉ chứng minh phiên hiện hữu còn hoạt động theo cơ chế đích. Chưa chứng minh credential mới dùng được hoặc mọi phiên cũ đã bị thu hồi.

**Ứng dụng:** kiểm tra đúng principal, nguồn xác thực, phiên bản, phân phối, cache, endpoint và tác vụ. Không mặc định lỗi là thiếu quyền rồi cấp admin rộng hơn.

**Khôi phục:** mật khẩu cũ đã không còn tin cậy; dùng lại có thể làm người giữ bản sao truy cập trở lại. Cần phương án tiến tới trạng thái mới đã xác minh.

**Đóng rotation:** cần xác nhận credential mới, consumer, bản cũ, phiên và bằng chứng theo phạm vi.

**Đóng sự cố:** còn phải xét đường truy cập phát sinh, hành động tại đích, dữ liệu bị ảnh hưởng, nguồn lộ và những phần chưa điều tra đủ.

## 19. Những điểm cần ghi nhớ

- Rotation khi nghi lộ là một phần của containment, không chỉ là thay giá trị mật khẩu.
- Phải xác định đúng principal, nguồn xác thực, consumer và những đường truy cập còn hiệu lực.
- Mật khẩu mới cần được tạo, áp dụng và phân phối qua đường tin cậy.
- Vault, đích và consumer có trạng thái khác nhau; kết quả chưa rõ phải được đối soát.
- Đổi mật khẩu không tự thu hồi mọi phiên, token, khóa hoặc quyền được tạo trước đó.
- Không mặc định phục hồi bằng bí mật đã bị nghi lộ; phương án duy trì dịch vụ phải xét mục tiêu an toàn.
- Chỉ kết luận theo phần đã xác minh và tách hoàn tất rotation khỏi kết thúc toàn bộ sự cố.

# Phân biệt criuengine, simengine và cơ chế riêng của nhà cung cấp

Trong CRaC, cụm từ checkpoint/restore có thể xuất hiện ở nhiều lớp khác nhau. Có lớp API để ứng dụng chuẩn bị tài nguyên, có engine thực hiện việc lưu và khôi phục tiến trình, và có nền tảng cloud tự cung cấp cơ chế snapshot cùng vòng đời triển khai riêng. Ba lớp này liên quan với nhau nhưng không đồng nghĩa.

criuengine thường là engine thực hiện checkpoint/restore thật bằng CRIU trên Linux. simengine thường mô phỏng chu trình callback CRaC để nhà phát triển kiểm tra cách ứng dụng đóng và mở lại tài nguyên. Cơ chế riêng của nhà cung cấp có thể snapshot một môi trường thực thi ở cấp container, máy ảo hoặc nền tảng serverless, do nhà cung cấp kiểm soát. Một số nền tảng hỗ trợ callback theo API CRaC, nhưng không vì thế mà sử dụng CRIU hoặc tạo ra ảnh checkpoint có thể mang sang một môi trường CRaC khác.

Muốn chọn đúng môi trường thực hành, cần xác định mình đang kiểm tra điều gì: logic vòng đời tài nguyên, khả năng checkpoint/restore thật của tiến trình, hay tích hợp với nền tảng triển khai cụ thể.

## 1. Phân biệt CRaC, engine và cơ chế của nền tảng

### CRaC là gì?

CRaC (Coordinated Restore at Checkpoint) là mô hình phối hợp để ứng dụng chuẩn bị trước khi checkpoint và khôi phục tài nguyên sau khi restore. API CRaC cho phép ứng dụng đăng ký các resource và triển khai callback vòng đời, phổ biến nhất là:

- beforeCheckpoint: dừng hoặc chuẩn bị tài nguyên trước khi tiến trình được chụp.
- afterRestore: tạo lại hoặc xác minh tài nguyên sau khi tiến trình được khôi phục.

API này mô tả phần ứng dụng cần phối hợp. Nó không tự quyết định ảnh tiến trình được tạo ra bằng CRIU, snapshot máy ảo hay công nghệ nào khác.

### Engine là gì?

Engine là thành phần phía runtime/JDK thực hiện yêu cầu checkpoint và restore. Engine nối phần điều phối của CRaC với cơ chế thực thi cụ thể. Tên, cách cấu hình, khả năng và mức độ hỗ trợ engine phụ thuộc vào bản JDK hoặc nhà cung cấp.

Trong ngữ cảnh bài học này, hai tên cần phân biệt là:

- criuengine: engine dùng CRIU để thực hiện checkpoint/restore tiến trình thật trên môi trường Linux tương thích.
- simengine: engine mô phỏng chu trình CRaC, thường dùng để chạy thử các callback mà không tạo ảnh tiến trình có thể restore như CRIU.

Tên gọi chính xác và giá trị cấu hình có thể khác giữa các bản phân phối JDK. Không nên suy ra rằng mọi JDK đều hỗ trợ cả hai engine hoặc dùng cùng một tham số khởi chạy.

### Cơ chế riêng của nhà cung cấp là gì?

Một nhà cung cấp cloud hoặc nền tảng runtime có thể triển khai snapshot theo cách riêng. Nền tảng có thể chụp toàn bộ môi trường thực thi, quản lý thời điểm tạo snapshot, lưu ảnh, nhân bản môi trường khi có yêu cầu và gọi hook ở những thời điểm do nền tảng quy định.

CRaC API có thể là giao diện để ứng dụng chuẩn bị tài nguyên trong một nền tảng như vậy. Tuy nhiên, công nghệ snapshot phía dưới, định dạng ảnh, giới hạn môi trường, thời điểm callback và quy trình triển khai vẫn do nền tảng quyết định.

## 2. Vị trí của từng thành phần trong luồng checkpoint/restore

Có thể hình dung các lớp theo luồng sau:

~~~mermaid
flowchart TD
    A[Ứng dụng Java] --> B[Resource và callback CRaC]
    B --> C[Runtime / JDK CRaC]
    C --> D{Cơ chế thực thi}
    D --> E[criuengine]
    D --> F[simengine]
    D --> G[Cơ chế snapshot của nhà cung cấp]
    E --> H[CRIU trên Linux]
    F --> I[Mô phỏng vòng đời callback]
    G --> J[Snapshot do nền tảng quản lý]
~~~

Ứng dụng dùng callback để đưa tài nguyên về trạng thái an toàn. Runtime/JDK điều phối các callback. Engine hoặc nền tảng thực hiện phần snapshot/restore. Mỗi lớp có trách nhiệm riêng:

| Thành phần | Trách nhiệm chính | Không tự bảo đảm |
|---|---|---|
| API CRaC và Resource | Cho ứng dụng biết thời điểm chuẩn bị và khôi phục tài nguyên | Không tự lưu database, message broker hay dữ liệu nghiệp vụ |
| criuengine | Điều phối checkpoint/restore tiến trình qua CRIU | Không làm cho mọi kernel, socket, file descriptor hoặc tài nguyên native đều tương thích |
| simengine | Mô phỏng chu trình để thử callback và logic vòng đời | Không chứng minh ảnh tiến trình thật có thể được tạo và restore thành công |
| Cơ chế riêng của nhà cung cấp | Chụp, lưu, nhân bản và khôi phục môi trường theo hợp đồng của nền tảng | Không mặc nhiên tương thích với CRIU hoặc có thể xuất/nhập ảnh giữa các nhà cung cấp |

## 3. criuengine: checkpoint/restore thật bằng CRIU

CRIU là viết tắt của Checkpoint/Restore In Userspace. Đây là công cụ trên Linux có khả năng lưu trạng thái của một tiến trình và khôi phục tiến trình từ trạng thái đã lưu, trong phạm vi mà kernel, CRIU và cấu hình môi trường hỗ trợ.

Khi JDK sử dụng criuengine, yêu cầu checkpoint từ runtime được chuyển tới cơ chế CRIU. Trước khi chụp, callback CRaC cho ứng dụng cơ hội đóng hoặc chuẩn bị tài nguyên. Sau khi tiến trình được restore, callback phục hồi tài nguyên được gọi theo vòng đời CRaC.

### Đặc điểm của criuengine

- Thực hiện checkpoint/restore tiến trình thật, bao gồm trạng thái bộ nhớ và những trạng thái tiến trình mà CRIU hỗ trợ trong môi trường đang chạy.
- Phụ thuộc vào Linux, kernel, phiên bản CRIU, kiến trúc CPU, quyền hệ thống và cấu hình container hoặc namespace.
- Cần có công cụ CRIU và các điều kiện hệ thống tương thích trong môi trường tạo checkpoint và restore.
- Có thể kiểm tra những vấn đề thực tế liên quan tới tiến trình, tài nguyên hệ điều hành và khả năng khôi phục.
- Ảnh checkpoint gắn với nhiều chi tiết của môi trường nguồn. Không nên mặc định có thể chuyển ảnh tùy ý giữa các máy, kernel, kiến trúc, phiên bản JDK hoặc cấu hình container khác nhau.

### Các điều kiện cần kiểm tra

Trước khi thực hành với criuengine, hãy xác nhận:

1. JDK đang dùng được xây dựng với hỗ trợ CRaC và có engine CRIU tương ứng.
2. Hệ điều hành là Linux và phiên bản kernel đáp ứng yêu cầu của phiên bản CRIU.
3. CRIU đã được cài đặt và có thể chạy trong môi trường đích.
4. Người dùng hoặc container có quyền cần thiết để CRIU thao tác với tiến trình.
5. Các giới hạn về cgroup, namespace, filesystem, network và bảo mật của môi trường container đã được xử lý.
6. Thư viện native, socket, file descriptor và các tài nguyên mà ứng dụng sử dụng có cách xử lý phù hợp.
7. Môi trường restore đáp ứng các điều kiện tương thích của ảnh đã tạo.

Có thể bắt đầu kiểm tra ở mức hệ điều hành bằng các lệnh:

~~~bash
uname -a
criu --version
criu check
java -version
~~~

Các lệnh trên chỉ cung cấp thông tin ban đầu. criu check kiểm tra một số điều kiện của CRIU trên host; kết quả thành công không chứng minh ứng dụng Java cụ thể sẽ checkpoint/restore được. Vẫn cần thử với đúng JDK, ứng dụng, quyền chạy và cấu hình triển khai.

### Những gì criuengine không giải quyết thay ứng dụng

CRIU xử lý trạng thái tiến trình trong phạm vi hỗ trợ của nó. Nó không biến checkpoint thành một transaction phân tán. Database vẫn có thể tiếp tục nhận giao dịch; broker vẫn có thể phát thông điệp; token vẫn có thể hết hạn; lease vẫn có thể được cấp cho tiến trình khác. Ứng dụng phải dùng callback và logic nghiệp vụ để đóng, xác minh hoặc tạo lại các tài nguyên này.

Ví dụ, một JDBC connection còn được tham chiếu trong heap không có nghĩa database vẫn giữ session tương ứng. Trước checkpoint, ứng dụng nên đóng connection pool theo hướng dẫn của thư viện; sau restore, tạo pool mới và kiểm tra kết nối trước khi nhận lưu lượng.

## 4. simengine: mô phỏng vòng đời để phát triển và kiểm tra

simengine thường được cung cấp để nhà phát triển thử nghiệm tích hợp CRaC mà không phải thiết lập toàn bộ môi trường checkpoint/restore của CRIU. Engine mô phỏng trình tự callback trước checkpoint và sau restore trong cùng một tiến trình hoặc theo cách mô phỏng do JDK cung cấp.

Mục tiêu của nó là giúp phát hiện vấn đề trong code quản lý tài nguyên:

- Ứng dụng có đăng ký resource đúng cách không?
- beforeCheckpoint có đóng hoặc flush tài nguyên cần thiết không?
- afterRestore có tạo lại client, pool hoặc subscription không?
- Callback có xử lý được trường hợp tài nguyên chưa được khởi tạo hoặc đã đóng không?
- Ứng dụng có thể trở lại trạng thái sẵn sàng sau chu trình callback không?

### Phạm vi kiểm tra của simengine

simengine hữu ích khi phát triển ban đầu vì có thể kiểm tra nhanh logic callback mà không cần tạo ảnh tiến trình thật. Nó cũng giúp đưa kiểm tra vòng đời tài nguyên vào quy trình phát triển thường ngày.

Tuy nhiên, một chu trình mô phỏng không tái hiện đầy đủ việc tiến trình bị dừng, bộ nhớ được lưu, trạng thái hệ điều hành được phục hồi và tiến trình tiếp tục chạy từ ảnh checkpoint. Tùy cách triển khai của JDK, mô phỏng có thể gọi callback trong cùng tiến trình mà không có khoảng thời gian dừng thực tế.

Vì vậy, simengine không chứng minh được:

- CRIU có thể chụp và restore tiến trình trên kernel hiện tại.
- Mọi socket, file descriptor, thread, file lock hoặc tài nguyên native có thể khôi phục.
- Container, namespace, volume và quyền hệ thống đáp ứng yêu cầu checkpoint.
- Trạng thái bên ngoài không thay đổi trong thời gian tiến trình dừng.
- Một ảnh checkpoint có thể chuyển sang host hoặc môi trường khác.
- Ứng dụng hoạt động đúng khi tiến trình thực sự được thay thế hoặc khi nền tảng tạo nhiều bản restore.

### Dùng simengine đúng mục đích

Hãy dùng nó như một bước kiểm tra sớm cho logic ứng dụng:

1. Đăng ký các resource CRaC mà ứng dụng sử dụng.
2. Chạy ứng dụng với engine mô phỏng theo hướng dẫn của bản JDK.
3. Kích hoạt chu trình mô phỏng checkpoint/restore.
4. Quan sát log của beforeCheckpoint và afterRestore.
5. Xác minh connection pool, client, scheduler và consumer đã chuyển về trạng thái mong muốn.
6. Gửi một yêu cầu nghiệp vụ sau mô phỏng để kiểm tra ứng dụng vẫn hoạt động.

Nếu callback lỗi hoặc tài nguyên không được tái tạo, sửa logic ở bước này trước khi chuyển sang thử nghiệm checkpoint thật.

## 5. Cơ chế checkpoint/restore riêng của nhà cung cấp

Một số nền tảng cloud cung cấp khả năng snapshot môi trường thực thi để giảm thời gian khởi động. Thay vì yêu cầu người dùng tự vận hành CRIU, nền tảng quản lý quá trình khởi tạo, chụp trạng thái, lưu ảnh và tạo môi trường mới từ ảnh đó.

Các cơ chế này có thể snapshot ở những lớp khác nhau:

- **Cấp tiến trình:** lưu trạng thái một tiến trình hoặc nhóm tiến trình theo khả năng của runtime.
- **Cấp container:** lưu trạng thái môi trường container cùng những tài nguyên mà nền tảng hỗ trợ.
- **Cấp máy ảo:** lưu trạng thái máy ảo hoặc môi trường thực thi ảo hóa.
- **Cấp serverless:** nền tảng tạo snapshot của execution environment sau giai đoạn khởi tạo rồi phục hồi các bản sao khi cần xử lý invocation.

Tên gọi, phạm vi và hành vi phụ thuộc vào sản phẩm cụ thể. Không nên gọi tất cả các cơ chế này là CRIU engine.

### Ví dụ: AWS Lambda SnapStart

AWS Lambda SnapStart là ví dụ về cơ chế snapshot do nhà cung cấp quản lý. Với phiên bản Lambda được cấu hình SnapStart, nền tảng tạo snapshot của execution environment sau giai đoạn khởi tạo và dùng snapshot đó để tạo môi trường phục hồi khi xử lý invocation.

Đối với Java, ứng dụng có thể dùng các hook tương thích với CRaC, chẳng hạn resource triển khai beforeCheckpoint và afterRestore, để chuẩn bị tài nguyên trước lúc snapshot và làm mới tài nguyên sau khi môi trường được phục hồi. Nền tảng quản lý việc tạo và phục hồi snapshot; ứng dụng không cần tự vận hành CRIU cho quy trình SnapStart.

Điều này không có nghĩa SnapStart dùng criuengine. Cơ chế snapshot bên dưới do AWS quản lý và tuân theo giới hạn, vòng đời, cấu hình phiên bản cùng quy tắc triển khai của Lambda. Ảnh snapshot đó không phải ảnh CRIU mà người dùng có thể tùy ý mang sang một máy Linux khác để restore.

Ví dụ này cũng cho thấy vì sao cần tách API callback khỏi engine. Ứng dụng có thể tái sử dụng ý tưởng quản lý resource qua hook CRaC, trong khi nền tảng thực thi snapshot bằng công nghệ riêng.

### Các điểm cần đọc trong tài liệu nhà cung cấp

Trước khi dùng một cơ chế managed snapshot, hãy tìm hiểu cụ thể:

- Snapshot được tạo vào thời điểm nào: lúc build, lúc publish phiên bản, sau khởi tạo hay theo yêu cầu?
- Hook nào được hỗ trợ? Nền tảng có nhận API org.crac hay cần một API riêng?
- beforeCheckpoint và afterRestore được gọi vào thời điểm nào, trong tiến trình nào và với bảo đảm gì?
- Những tài nguyên nào bị giới hạn hoặc phải tạo lại sau restore?
- Snapshot có được dùng để tạo nhiều instance đồng thời không?
- Thông tin nào được giữ giữa các lần restore và thông tin nào phải lấy lại từ dịch vụ bên ngoài?
- Có giới hạn về vùng triển khai, kiến trúc CPU, phiên bản runtime, kích thước ảnh hoặc thời gian lưu ảnh không?
- Cách triển khai phiên bản mới, rollback, xóa snapshot và quan sát lỗi restore là gì?

Đặc biệt, hãy xác định nền tảng có gọi hook một lần khi tạo snapshot hay gọi lại theo từng bản restore. Không được tự suy ra vòng đời callback chỉ từ tên phương thức; phải theo hợp đồng của sản phẩm.

## 6. Bảng so sánh ba lựa chọn

| Tiêu chí | criuengine | simengine | Cơ chế riêng của nhà cung cấp |
|---|---|---|---|
| Mục tiêu | Checkpoint/restore tiến trình thật | Mô phỏng chu trình CRaC để phát triển | Tối ưu khởi tạo và phục hồi trên nền tảng cụ thể |
| Cách thực thi | Dùng CRIU trên Linux tương thích | Mô phỏng callback theo cách JDK triển khai | Snapshot do runtime hoặc hạ tầng của nhà cung cấp quản lý |
| Ảnh tiến trình thật | Có, trong phạm vi CRIU hỗ trợ | Thông thường không | Có snapshot theo định dạng và phạm vi riêng của nền tảng |
| Yêu cầu CRIU | Có | Không nhất thiết | Không nhất thiết; tùy nền tảng |
| Phụ thuộc hệ điều hành | Rất rõ, chủ yếu là Linux và điều kiện kernel/CRIU | Thường ít phụ thuộc hơn cho việc thử callback | Theo runtime, dịch vụ và vùng triển khai của nhà cung cấp |
| Kiểm tra callback ứng dụng | Có | Có, đây là mục tiêu chính | Có nếu nền tảng hỗ trợ hook tương ứng |
| Kiểm tra khả năng restore tài nguyên hệ điều hành | Có trong môi trường thật, nhưng chỉ trong phạm vi hỗ trợ | Không đầy đủ | Theo phạm vi snapshot và hợp đồng nền tảng |
| Tính di động của ảnh | Bị giới hạn bởi môi trường và tương thích kỹ thuật | Không có ảnh thật để di chuyển | Thường gắn với dịch vụ, phiên bản và môi trường của nhà cung cấp |
| Nơi phù hợp | Thử nghiệm tích hợp và triển khai CRaC tự quản lý trên Linux | Phát triển cục bộ, kiểm tra callback sớm | Triển khai trên dịch vụ cloud hỗ trợ snapshot |

Không có lựa chọn nào thay thế trách nhiệm lưu trữ dữ liệu nghiệp vụ và phối hợp với hệ thống bên ngoài. Khác biệt chủ yếu nằm ở nơi thực hiện snapshot, mức độ kiểm soát của nhóm phát triển và phạm vi môi trường được hỗ trợ.

## 7. Cấu hình engine và kiểm tra đúng bản JDK

Không nên sao chép một tham số chọn engine từ hướng dẫn của bản JDK này sang bản JDK khác mà chưa kiểm tra. Các bản phân phối CRaC có thể khác nhau về:

- Tên engine được đóng gói.
- Giá trị hợp lệ của tham số chọn engine.
- Cách bật checkpoint/restore và cách gọi thao tác checkpoint.
- Đường dẫn tới CRIU và các tùy chọn dòng lệnh.
- Phiên bản CRIU được hỗ trợ.
- Cách đóng gói thư viện CRaC API và module cần thiết.
- Tính năng mô phỏng có sẵn trong bản build hay không.

Quy trình an toàn là xác định chính xác vendor, phiên bản JDK và tài liệu tương ứng, rồi dùng đúng tham số engine được tài liệu đó công bố. Có thể biểu diễn lệnh khởi chạy theo dạng khái quát:

~~~bash
java <tham-so-chon-engine-theo-ban-JDK> -jar application.jar
~~~

Phần <tham-so-chon-engine-theo-ban-JDK> là chỗ cần thay bằng cú pháp thật của JDK đang sử dụng. Đây không phải tham số Java có thể dùng nguyên văn.

Trước khi chạy, ghi lại phiên bản để có thể tái hiện môi trường:

~~~bash
java -version
criu --version
uname -a
~~~

Khi so sánh hai môi trường, cần ghi cả vendor JDK, phiên bản build, kiến trúc CPU, kernel, phiên bản CRIU và cấu hình container. Chỉ ghi “đã dùng CRaC” là chưa đủ để giải thích vì sao một ảnh checkpoint hoạt động ở máy này nhưng thất bại ở máy khác.

## 8. Quy trình thực hành từ mô phỏng đến môi trường thật

Một lộ trình thực hành hợp lý có thể chia thành ba cấp độ.

### Cấp độ 1: kiểm tra callback bằng simengine

Ở cấp độ này, tập trung vào logic ứng dụng:

1. Tạo một resource quản lý kết nối tới dịch vụ ngoài.
2. Đăng ký resource với global context CRaC.
3. Trong beforeCheckpoint, dừng nhận công việc mới và đóng tài nguyên cần tạo lại.
4. Trong afterRestore, mở kết nối mới và xác minh trạng thái.
5. Chạy chu trình mô phỏng và kiểm tra log, trạng thái tài nguyên cùng khả năng xử lý yêu cầu tiếp theo.

Mục tiêu là tìm lỗi trong callback nhanh và dễ lặp lại.

### Cấp độ 2: kiểm tra checkpoint/restore bằng criuengine

Khi callback đã hoạt động, chuyển sang môi trường Linux có CRIU:

1. Chuẩn bị đúng JDK, CRIU, kernel, quyền và cấu hình container.
2. Chạy ứng dụng với engine CRIU theo hướng dẫn của JDK.
3. Tạo checkpoint bằng cơ chế mà bản JDK cung cấp.
4. Thực hiện restore theo đúng quy trình và môi trường được hỗ trợ.
5. Kiểm tra ứng dụng đã phục hồi trạng thái tiến trình và tạo lại các kết nối bên ngoài.
6. Thử các tình huống như database khởi động lại, token hết hạn hoặc file thay đổi trong khoảng thời gian tiến trình dừng.

Mục tiêu là xác minh cả runtime, CRIU, hệ điều hành và ứng dụng hoạt động cùng nhau.

### Cấp độ 3: triển khai trên nền tảng của nhà cung cấp

Nếu đích đến là dịch vụ managed snapshot, hãy chuyển sang kiểm tra trên đúng dịch vụ:

1. Đọc hợp đồng snapshot và vòng đời hook của nền tảng.
2. Xác nhận JDK/runtime và API callback được hỗ trợ.
3. Đóng gói ứng dụng theo quy trình triển khai của nhà cung cấp.
4. Tạo phiên bản hoặc cấu hình snapshot theo hướng dẫn của dịch vụ.
5. Kích hoạt môi trường phục hồi và kiểm tra hook, readiness, kết nối cùng dữ liệu nghiệp vụ.
6. Thử nhiều instance phục hồi đồng thời, rollback và cập nhật phiên bản.

Mục tiêu là xác minh hành vi trong đúng môi trường production dự kiến. Kết quả từ simengine hoặc criuengine không thay cho kiểm thử tích hợp với dịch vụ managed.

~~~mermaid
flowchart TD
    A[Viết và đăng ký Resource CRaC] --> B[Kiểm tra callback với simengine]
    B --> C{Callback hoạt động đúng?}
    C -- Chưa --> D[Sửa logic vòng đời tài nguyên]
    D --> B
    C -- Rồi --> E[Kiểm tra CRIU và Linux]
    E --> F[Checkpoint/restore thật với criuengine]
    F --> G{Môi trường thật hoạt động đúng?}
    G -- Chưa --> H[Điều tra JDK, CRIU, kernel và tài nguyên]
    H --> E
    G -- Rồi --> I[Nếu cần, tích hợp nền tảng managed]
    I --> J[Kiểm tra hook và hợp đồng của nhà cung cấp]
~~~

Không phải dự án nào cũng cần cả ba cấp độ. Nếu ứng dụng chỉ chạy trên một nền tảng managed, cấp độ 1 giúp kiểm tra logic callback và cấp độ 3 kiểm tra hợp đồng thực tế của nền tảng. Nếu nhóm tự quản lý CRIU trên Linux, cấp độ 2 là bước kiểm chứng chính.

## 9. Ví dụ resource dùng chung cho các môi trường hỗ trợ CRaC

API Resource cho phép ứng dụng mô tả cách quản lý vòng đời của một tài nguyên. Ví dụ dưới đây minh họa một client cần đóng trước checkpoint và kết nối lại sau restore:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExternalClientResource implements Resource {
    private volatile ExternalClient client;

    public ExternalClientResource() {
        Core.getGlobalContext().register(this);
        client = connect();
    }

    public ExternalClient client() {
        ExternalClient current = client;
        if (current == null) {
            throw new IllegalStateException("Client is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        ExternalClient current = client;
        client = null;
        if (current != null) {
            current.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) {
        client = connect();
    }

    private ExternalClient connect() {
        // Tạo client mới theo cấu hình và thông tin xác thực hiện tại.
        return ExternalClient.connect();
    }
}
~~~

ExternalClient trong ví dụ là lớp minh họa của ứng dụng, không phải lớp có sẵn trong JDK. Trong dự án thật, thay bằng client cụ thể và áp dụng quy trình đóng/mở được thư viện hỗ trợ.

Đoạn code cho thấy ứng dụng quản lý vòng đời tài nguyên qua API CRaC. Nó không chọn engine và không quyết định cách snapshot được tạo. Cùng một ý tưởng callback có thể được kiểm tra bằng simengine, chạy cùng criuengine trên JDK hỗ trợ CRIU, hoặc tích hợp với nền tảng managed nếu nền tảng hỗ trợ API tương ứng.

Trong thực tế, cần bổ sung bước quiescing để bảo đảm không có request đang sử dụng client khi beforeCheckpoint đóng nó. afterRestore cũng cần xử lý trường hợp dịch vụ chưa sẵn sàng, retry có giới hạn và chỉ báo readiness sau khi kết nối cần thiết đã hoạt động.

## 10. Các nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| CRaC chính là CRIU | CRaC cung cấp mô hình phối hợp và API; CRIU là một công cụ Linux có thể được engine sử dụng để checkpoint/restore |
| criuengine và simengine chỉ khác tốc độ | Chúng khác mục tiêu và mức độ thực thi: một bên thực hiện checkpoint thật, bên kia mô phỏng vòng đời |
| Test qua simengine thành công nghĩa là có thể deploy bằng CRIU | Mô phỏng không kiểm tra đầy đủ kernel, quyền, container, CRIU và khả năng phục hồi tài nguyên hệ điều hành |
| Có criuengine nghĩa là mọi Linux đều chạy được | Khả năng thực tế phụ thuộc kernel, CRIU, kiến trúc, quyền và cấu hình môi trường |
| Nền tảng có hook CRaC nghĩa là dùng CRIU | Nền tảng có thể dùng công nghệ snapshot riêng và chỉ tái sử dụng API callback |
| Snapshot của nhà cung cấp có thể restore bằng CRIU | Ảnh thường gắn với định dạng và dịch vụ của nhà cung cấp |
| Callback afterRestore làm mọi dịch vụ bên ngoài tự hoạt động | Ứng dụng vẫn phải tạo lại kết nối, làm mới token, xác minh lease và kiểm tra readiness |
| Một checkpoint chỉ tạo một instance | Một số nền tảng có thể dùng snapshot để tạo nhiều instance; cần xử lý identity và trạng thái phân tán |
| Engine mô phỏng có thể thay thế kiểm thử production | Mỗi môi trường có hợp đồng, giới hạn và hành vi restore riêng cần được kiểm tra trực tiếp |

## 11. Chọn môi trường theo mục tiêu

Hãy bắt đầu từ mục tiêu kiểm tra:

- Nếu cần kiểm tra nhanh beforeCheckpoint, afterRestore, việc đóng/mở pool và trạng thái readiness, bắt đầu bằng simengine.
- Nếu cần chứng minh tiến trình Java có thể được checkpoint và restore thật trên Linux do nhóm quản lý, dùng criuengine cùng đúng JDK, kernel, CRIU và cấu hình triển khai.
- Nếu ứng dụng chạy trên một dịch vụ cloud có snapshot riêng, làm theo tài liệu của dịch vụ đó và kiểm tra hook mà dịch vụ hỗ trợ. Không giả định ảnh snapshot tương thích với CRIU.
- Nếu muốn chuyển từ môi trường tự quản lý sang managed snapshot, giữ logic nghiệp vụ và nguyên tắc quản lý tài nguyên ở lớp ứng dụng, sau đó điều chỉnh phần tích hợp theo hợp đồng của nền tảng.

Trước khi kết luận môi trường đã sẵn sàng, hãy kiểm tra cả ba nhóm:

1. **Ứng dụng:** resource được đăng ký đúng, callback an toàn, thao tác có thể lặp lại, cache và trạng thái nghiệp vụ được xác minh.
2. **Runtime và engine:** đúng JDK, đúng engine, đúng phiên bản và đúng quy trình checkpoint/restore.
3. **Nền tảng:** kernel, container, quyền, storage, network, dịch vụ ngoài và quy tắc snapshot của nhà cung cấp đều đáp ứng yêu cầu.

Phân biệt rõ criuengine, simengine và cơ chế riêng của nhà cung cấp giúp chọn đúng công cụ cho từng bước. simengine rút ngắn vòng lặp phát triển callback; criuengine kiểm chứng checkpoint/restore thật bằng CRIU trên Linux; cơ chế managed giúp tận dụng snapshot do nền tảng vận hành theo hợp đồng riêng. Dù chọn cách nào, ứng dụng vẫn phải chủ động quản lý tài nguyên, dữ liệu bền vững và các hệ thống bên ngoài trong suốt vòng đời checkpoint/restore.

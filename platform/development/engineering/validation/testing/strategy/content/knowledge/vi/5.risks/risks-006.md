# Rủi ro: Chọn độ sâu kiểm thử theo mức rủi ro và khả năng phát hiện lỗi

## 1. Vì sao độ sâu kiểm thử phải dựa trên rủi ro?

Không phải mọi chức năng đều có hậu quả như nhau khi xảy ra lỗi. Một lỗi hiển thị sai màu nút có thể gây bất tiện nhỏ; một lỗi tính sai số tiền, cấp quyền sai hoặc làm mất dữ liệu có thể gây thiệt hại lớn. Đồng thời, có lỗi rất dễ phát hiện bằng một assertion ở API, nhưng có lỗi chỉ xuất hiện khi nhiều dịch vụ phối hợp, khi tải tăng, khi mạng gián đoạn hoặc khi một sự kiện đến trễ.

Trong VALIDATION_TESTING_STRATEGY, chọn độ sâu kiểm thử là quyết định phân bổ công sức để tạo đủ bằng chứng về chất lượng của sản phẩm. Quyết định này cần xem xét đồng thời:

- **Mức độ tác động:** nếu hành vi sai xảy ra, người dùng, dữ liệu, hoạt động kinh doanh hoặc tổ chức chịu hậu quả gì?
- **Khả năng xảy ra:** điều kiện gây lỗi có thường gặp, dễ kích hoạt hoặc đã từng xuất hiện không?
- **Khả năng phát hiện:** bộ kiểm thử hiện tại có thể nhận ra lỗi đó với độ tin cậy nào, ở đúng ranh giới và trước khi phát hành hay không?

Độ sâu không đơn giản là số lượng ca kiểm thử. Nó thể hiện mức độ kiểm tra các đường đi, trạng thái, ranh giới tích hợp, điều kiện lỗi và bằng chứng cần thu thập. Một bộ kiểm thử ngắn nhưng có oracle chính xác tại ranh giới rủi ro cao có thể hữu ích hơn hàng trăm ca kiểm thử lặp lại cùng một hành vi.

Mục tiêu là bảo đảm các rủi ro quan trọng có cách phát hiện đủ tin cậy, đồng thời giữ thời gian phản hồi và chi phí kiểm thử ở mức phù hợp.

## 2. Phân biệt rủi ro sản phẩm và rủi ro dự án

**Rủi ro sản phẩm** liên quan đến khả năng sản phẩm không đáp ứng nhu cầu hoặc gây hậu quả khi được sử dụng: sai nghiệp vụ, mất dữ liệu, lộ thông tin, gián đoạn dịch vụ, hiệu năng không đạt hoặc trải nghiệm không thể hoàn thành.

**Rủi ro dự án** liên quan đến khả năng hoạt động phát triển và kiểm thử gặp trở ngại: thiếu môi trường, dữ liệu đến muộn, công cụ không ổn định, thiếu chuyên gia, thời gian phát hành ngắn hoặc phụ thuộc chưa sẵn sàng.

Hai nhóm có liên hệ nhưng cần được xử lý khác nhau. Rủi ro sản phẩm quyết định hành vi nào cần được xác nhận và bằng chứng nào là đủ. Rủi ro dự án ảnh hưởng đến khả năng thu thập bằng chứng và cần có biện pháp giảm thiểu như chuẩn bị môi trường, bổ sung quyền truy cập hoặc điều chỉnh kế hoạch.

Trong bài này, trọng tâm là rủi ro sản phẩm và khoảng trống phát hiện lỗi. Rủi ro dự án vẫn cần được ghi nhận vì nó có thể làm giảm độ tin cậy của kết quả kiểm thử.

## 3. Đánh giá mức rủi ro

### 3.1. Xác định tình huống lỗi trước khi chấm điểm

Đánh giá rủi ro nên bắt đầu từ một tình huống cụ thể, không bắt đầu bằng một con số tổng quát cho cả module. Mô tả theo cấu trúc:

1. **Điều kiện:** trong hoàn cảnh nào lỗi có thể xảy ra?
2. **Lỗi hoặc sai lệch:** hệ thống có thể làm gì sai?
3. **Hậu quả:** ai hoặc dữ liệu nào bị ảnh hưởng?
4. **Cách phát hiện hiện tại:** kiểm thử, giám sát hay người dùng có thể nhận ra lỗi bằng cách nào?
5. **Khoảng trống:** điều gì khiến lỗi có thể lọt qua trước khi phát hành hoặc không được phát hiện khi đang vận hành?

Ví dụ: khi hai người cùng đặt một khung giờ, một giao dịch đồng thời có thể khiến cả hai đơn đều được xác nhận. Hậu quả là đặt trùng lịch. Nếu kiểm thử chỉ chạy từng yêu cầu tuần tự và không kiểm tra trạng thái cuối trong cơ sở dữ liệu, bộ kiểm thử hiện tại có khoảng trống về phát hiện lỗi đồng thời.

Mô tả cụ thể giúp nhóm chọn được điều kiện kiểm thử và oracle phù hợp, thay vì chỉ tăng số lượng ca kiểm thử.

### 3.2. Ba yếu tố đánh giá

Có thể dùng thang điểm từ 1 đến 5 để xếp hạng tương đối. Mỗi nhóm cần thống nhất định nghĩa thang điểm trước khi chấm để tránh việc cùng một điểm có ý nghĩa khác nhau giữa các thành viên.

| Yếu tố | Điểm thấp | Điểm cao |
| --- | --- | --- |
| Tác động (I) | Bất tiện nhỏ, dễ khôi phục, ít người bị ảnh hưởng | Thiệt hại tài chính lớn, mất hoặc lộ dữ liệu, vi phạm nghĩa vụ, ảnh hưởng an toàn hoặc gián đoạn nghiêm trọng |
| Khả năng xảy ra (L) | Điều kiện hiếm, khó kích hoạt, ít xuất hiện trong vận hành | Điều kiện phổ biến, đường đi thường dùng, dễ tái hiện hoặc đã có lịch sử lỗi |
| Khoảng trống phát hiện (G) | Có oracle đáng tin cậy, kiểm thử lặp lại ổn định và quan sát rõ | Khó quan sát, không có oracle phù hợp, chỉ kiểm thử giả lập hoặc lỗi có thể bị che khuất |

Ở yếu tố G, điểm càng cao nghĩa là lỗi càng khó được phát hiện bởi các kiểm soát hiện có. Cần đánh giá năng lực phát hiện của toàn bộ cơ chế trước phát hành, gồm kiểm thử tự động, kiểm thử thủ công, rà soát, giám sát trong môi trường tiền phát hành và các kiểm soát có thể tạo bằng chứng. Không nên chấm điểm chỉ dựa vào việc nhóm đã có một ca kiểm thử mang tên tương ứng.

### 3.3. Điểm ưu tiên rủi ro

Một cách xếp hạng đơn giản là:

\[
R = I \times L \times G
\]

Trong đó:

- I là mức độ tác động.
- L là khả năng xảy ra.
- G là khoảng trống phát hiện lỗi.

Với thang 1–5, R nằm trong khoảng 1–125. Có thể dùng ngưỡng khởi đầu để phân loại:

| Điểm R | Mức ưu tiên tham khảo | Hướng xử lý |
| --- | --- | --- |
| 1–19 | Thấp | Duy trì kiểm thử nền tảng phù hợp và theo dõi thay đổi |
| 20–49 | Trung bình | Bổ sung kiểm thử ở ranh giới liên quan và kiểm tra trường hợp lỗi chính |
| 50–79 | Cao | Tăng độ sâu, bao phủ luồng quan trọng, lỗi tích hợp và điều kiện bất lợi |
| 80–125 | Rất cao | Ưu tiên kiểm thử nhiều tầng, xác nhận độc lập và yêu cầu bằng chứng rõ trước quyết định phát hành |

Đây là thang xếp hạng nội bộ, không phải xác suất thống kê hay tiêu chuẩn phổ quát. Nhóm cần điều chỉnh ngưỡng theo sản phẩm, quy định và mức chấp nhận rủi ro. Một tình huống có tác động nghiêm trọng như lộ dữ liệu hoặc sai lệch giao dịch có thể cần được nâng mức ưu tiên ngay cả khi điểm nhân thấp do khả năng xảy ra được đánh giá thấp.

Điểm số hỗ trợ thảo luận và sắp thứ tự công việc; nó không thay thế phán đoán chuyên môn, yêu cầu bắt buộc hoặc quyết định của người chịu trách nhiệm rủi ro.

### 3.4. Ví dụ chấm điểm

Giả sử sản phẩm có ba tình huống:

| Tình huống lỗi | I | L | G | R | Lý do chính |
| --- | ---: | ---: | ---: | ---: | --- |
| Sai khoảng cách hiển thị ở một màn hình ít dùng | 1 | 2 | 1 | 2 | Tác động nhỏ và dễ nhận ra khi kiểm tra giao diện |
| Đặt trùng khung giờ khi có yêu cầu đồng thời | 4 | 3 | 4 | 48 | Có thể ảnh hưởng nhiều khách; kiểm thử tuần tự không phát hiện được |
| Thanh toán bị ghi nhận hai lần khi callback được gửi lặp | 5 | 3 | 5 | 75 | Ảnh hưởng tài chính; thiếu kiểm thử lặp và đối soát trạng thái |

Điểm số ở bảng là ví dụ minh họa. Nhóm cần dựa vào dữ liệu sử dụng, lịch sử sự cố, kiến trúc và kiểm soát thực tế để chấm cho sản phẩm của mình.

## 4. Đánh giá khả năng phát hiện lỗi

Khả năng phát hiện là yếu tố quan trọng vì hai rủi ro có cùng mức tác động và khả năng xảy ra vẫn có thể cần độ sâu kiểm thử khác nhau. Nếu một lỗi được phát hiện ổn định bằng kiểm thử thành phần nhanh, nhóm có thể dựa vào kiểm soát đó cho nhiều lần chạy. Nếu lỗi chỉ xuất hiện ở một chuỗi tương tác bất đồng bộ và không có dấu vết quan sát, cần bổ sung kiểm thử hoặc cải thiện khả năng quan sát trước khi kết luận rằng rủi ro đã được kiểm soát.

### 4.1. Các câu hỏi để đánh giá năng lực phát hiện

- **Độ bao phủ hành vi:** có kiểm tra đường thành công, lỗi, biên và các trạng thái chuyển tiếp liên quan không?
- **Chất lượng oracle:** tiêu chí pass/fail có phát hiện được sai lệch nghiệp vụ hay chỉ xác nhận rằng request không bị lỗi kỹ thuật?
- **Vị trí quan sát:** có thể kiểm tra trạng thái tại đúng ranh giới nơi lỗi phát sinh không?
- **Tính đại diện của môi trường:** môi trường và phụ thuộc có tái hiện được điều kiện có khả năng gây lỗi không?
- **Khả năng tái lập:** cùng dữ liệu và điều kiện có cho kết quả ổn định để phân biệt lỗi thật với nhiễu không?
- **Độc lập của bằng chứng:** kết quả có được xác nhận từ nguồn khác khi cần, ví dụ đối soát giao dịch hoặc kiểm tra trạng thái cuối?
- **Thời điểm phát hiện:** lỗi được phát hiện trước khi phát hành hay chỉ sau khi người dùng gặp sự cố?

Một bài kiểm thử có thể chạy thành công nhưng vẫn có năng lực phát hiện thấp nếu assertion quá yếu. Ví dụ, kiểm tra API trả về HTTP 200 không đủ để xác nhận đơn hàng đã được thanh toán đúng, tồn kho được cập nhật và thông báo được phát một lần.

### 4.2. Oracle và quan sát

Oracle xác định kết quả nào là đúng. Với mỗi rủi ro, cần chọn oracle ở mức phù hợp:

| Loại hành vi | Oracle có thể dùng |
| --- | --- |
| Quy tắc tính toán | Giá trị mong đợi, bảng quyết định, bất biến hoặc thuộc tính toán học |
| API | Schema, mã phản hồi, nội dung, quyền truy cập và trạng thái nghiệp vụ |
| Tương tác dịch vụ | Hợp đồng provider-consumer, sự kiện được phát và phản hồi theo thời hạn |
| Giao dịch dữ liệu | Bất biến, tính duy nhất, tính toàn vẹn tham chiếu và trạng thái sau giao dịch |
| Xử lý bất đồng bộ | Điều kiện trạng thái cuối, correlation ID, retry và dead-letter |
| Hiệu năng | Phân vị độ trễ, thông lượng, tỷ lệ lỗi và giới hạn tài nguyên dưới tải xác định |
| Phục hồi | Thời gian phục hồi, dữ liệu được bảo toàn và khả năng tiếp tục nghiệp vụ |

Quan sát tốt làm tăng khả năng phát hiện và rút ngắn thời gian phân tích lỗi. Log có cấu trúc, metric, distributed trace, correlation ID và trạng thái nghiệp vụ nên được thiết kế cùng chiến lược kiểm thử. Không ghi token, secret hoặc dữ liệu cá nhân không cần thiết vào bằng chứng.

### 4.3. Phân biệt phát hiện lỗi với xác nhận không có lỗi

Một kiểm thử pass chỉ cung cấp bằng chứng rằng các điều kiện đã chạy không làm lộ sai lệch theo oracle đã chọn. Nó không chứng minh không còn lỗi ở mọi dữ liệu, tải, môi trường hoặc thời điểm khác.

Độ tin cậy của kết luận phụ thuộc vào phạm vi đầu vào, tính đại diện của dữ liệu, khả năng kích hoạt lỗi và độ nhạy của oracle. Vì vậy, báo cáo nên nêu rõ điều kiện đã kiểm tra và các giới hạn còn lại thay vì suy rộng quá mức từ một lần chạy thành công.

## 5. Chọn độ sâu kiểm thử theo mức rủi ro

Độ sâu được quyết định bằng cách kết hợp mức rủi ro, khoảng trống phát hiện, khả năng kiểm soát thành phần và chi phí tạo bằng chứng. Bảng dưới đây là hướng dẫn tham khảo, không phải quy tắc cứng.

| Mức ưu tiên | Độ sâu kiểm thử gợi ý | Bằng chứng cần có |
| --- | --- | --- |
| Thấp | Kiểm thử thành phần hoặc kiểm tra cơ bản tại nơi hành vi được tạo ra; rà soát thay đổi có liên quan | Kết quả kiểm thử ổn định, oracle rõ và liên kết với yêu cầu |
| Trung bình | Bổ sung kiểm thử hợp đồng hoặc tích hợp cho ranh giới có liên quan; kiểm tra trường hợp lỗi phổ biến | Request/response, trạng thái dữ liệu và kết quả tương tác |
| Cao | Kiểm thử thành phần, hợp đồng, tích hợp và luồng hệ thống trọng yếu; bao phủ lỗi, biên, đồng thời, timeout hoặc retry khi liên quan | Bằng chứng ở nhiều ranh giới, khả năng tái hiện và báo cáo rủi ro còn lại |
| Rất cao | Kiểm thử nhiều tầng trong môi trường đại diện; kiểm thử tiêu cực, phục hồi, tải hoặc bảo mật phù hợp; rà soát độc lập và xác nhận trước phát hành | Oracle độc lập khi cần, trace đầy đủ, kết quả phục hồi và phê duyệt rủi ro |

Không nên thêm mọi loại kiểm thử cho mọi rủi ro. Chọn phương pháp có khả năng kích hoạt và phát hiện đúng chế độ lỗi. Ví dụ, kiểm thử tải không giúp phát hiện lỗi phân quyền nếu không có kịch bản bảo mật; kiểm thử giao diện không đủ để chứng minh tính idempotent của callback.

### 5.1. Độ sâu theo tầng kiểm thử

~~~mermaid
flowchart TD
    R["Mô tả tình huống lỗi"] --> S["Đánh giá tác động, khả năng xảy ra<br/>và khoảng trống phát hiện"]
    S --> D{"Rủi ro và khoảng trống<br/>ở mức nào?"}
    D -->|"Thấp"| U["Kiểm thử thành phần<br/>và kiểm tra cơ bản"]
    D -->|"Trung bình"| C["Thêm contract test<br/>và kiểm thử tích hợp"]
    D -->|"Cao"| E["Thêm luồng hệ thống<br/>và các điều kiện lỗi"]
    D -->|"Rất cao"| H["Môi trường đại diện, kiểm thử phục hồi<br/>hoặc tải/bảo mật, rà soát độc lập"]
    U --> V["Đánh giá oracle và bằng chứng"]
    C --> V
    E --> V
    H --> V
    V --> G{"Rủi ro còn lại<br/>được chấp nhận?"}
    G -->|"Chưa"| M["Bổ sung kiểm soát hoặc<br/>điều chỉnh phạm vi"]
    M --> S
    G -->|"Rồi"| P["Ghi nhận quyết định<br/>và điều kiện theo dõi"]
~~~

### 5.2. Khi nào cần tăng độ sâu?

Tăng độ sâu khi có một hoặc nhiều dấu hiệu:

- Hành vi có hậu quả lớn như giao dịch tài chính, quyền truy cập, dữ liệu cá nhân hoặc dữ liệu không thể khôi phục.
- Luồng đi qua nhiều dịch vụ, nhiều nhóm sở hữu hoặc nhà cung cấp bên ngoài.
- Có xử lý bất đồng bộ, cạnh tranh tài nguyên, retry, timeout hoặc thứ tự sự kiện.
- Thay đổi ảnh hưởng hợp đồng công khai, schema dữ liệu hoặc cơ chế xác thực.
- Lỗi trước đây đã lọt qua kiểm thử hoặc chỉ được phát hiện trong production.
- Oracle hiện tại không kiểm tra trạng thái cuối hoặc bằng chứng thiếu tính độc lập.
- Môi trường kiểm thử khác đáng kể với môi trường thực tế.
- Có thay đổi kiến trúc, công nghệ hoặc nhà cung cấp làm tăng độ không chắc chắn.

Tăng độ sâu có thể là bổ sung dữ liệu biên, kiểm thử đồng thời, contract test, fault injection, kiểm tra phục hồi, xác nhận thủ công theo kịch bản hoặc thêm trace. Chọn biện pháp gắn trực tiếp với khoảng trống đã xác định.

### 5.3. Khi nào có thể giữ độ sâu hiện tại?

Có thể giữ độ sâu hiện tại khi hành vi ít tác động, được kiểm soát tốt, có oracle rõ ràng, kết quả ổn định và không có thay đổi đáng kể ở các ranh giới liên quan. Quyết định này vẫn cần được ghi nhận cùng cơ sở đánh giá và điều kiện xem xét lại.

Không nên giảm độ sâu chỉ vì thời gian phát hành ngắn. Nếu nguồn lực hạn chế, hãy ưu tiên theo rủi ro, ghi rõ phần chưa được xác nhận và chuyển quyết định chấp nhận rủi ro cho người có thẩm quyền.

## 6. Ví dụ áp dụng: luồng thanh toán và đặt lịch

Giả sử nền tảng đặt lịch cho phép khách hàng chọn khung giờ, thanh toán và nhận xác nhận. Những rủi ro sau minh họa cách kết hợp mức tác động, khả năng xảy ra và khoảng trống phát hiện.

| Rủi ro | Cách lỗi có thể xảy ra | Khoảng trống phát hiện thường gặp | Độ sâu phù hợp |
| --- | --- | --- | --- |
| Đặt trùng khung giờ | Hai yêu cầu đồng thời cùng đọc trạng thái còn trống trước khi ghi | Chỉ kiểm thử tuần tự, không xác nhận tính duy nhất ở trạng thái cuối | Kiểm thử đồng thời ở tầng tích hợp, kiểm tra ràng buộc dữ liệu và luồng đặt lịch |
| Ghi nhận thanh toán hai lần | Callback lặp kích hoạt cập nhật giao dịch nhiều lần | Chỉ mô phỏng một callback thành công | Contract test, callback lặp, kiểm tra idempotency và đối soát trạng thái giao dịch |
| Thanh toán thành công nhưng lịch vẫn chờ | Event hoặc callback bị trễ, mất hoặc xử lý lỗi | Chỉ kiểm tra phản hồi tức thời từ API thanh toán | Kiểm thử bất đồng bộ, retry, dead-letter, đối soát và kiểm tra trạng thái cuối |
| Người dùng xem được lịch của người khác | Kiểm tra quyền chỉ ở giao diện | Không thử truy cập trực tiếp API bằng danh tính khác | Kiểm thử phân quyền ở API, kiểm thử âm tính theo vai trò và kiểm tra rò rỉ dữ liệu |
| Hệ thống chậm khi cao điểm | Tải đồng thời làm cạn kết nối hoặc tăng thời gian xử lý | Bộ kiểm thử chức năng chỉ chạy với tải thấp | Kiểm thử tải với mô hình sử dụng đại diện, đo phân vị độ trễ và tỷ lệ lỗi |

Ví dụ chi tiết với callback thanh toán lặp:

1. Tạo một đặt lịch ở trạng thái chờ thanh toán.
2. Gửi callback hợp lệ với cùng mã giao dịch và cùng định danh sự kiện hai lần.
3. Xác nhận hệ thống chỉ ghi nhận một giao dịch thanh toán và không tạo hai lần chuyển trạng thái.
4. Kiểm tra phản hồi cho callback lặp theo hợp đồng đã định nghĩa.
5. Đối chiếu trạng thái giao dịch và đặt lịch bằng correlation ID.
6. Thử callback đến sau khi tác vụ đối soát đã chạy để kiểm tra xử lý trạng thái đến trễ.

Kiểm thử này sâu hơn một ca API thành công đơn lẻ vì nó chủ động tạo điều kiện lỗi và xác nhận bất biến nghiệp vụ ở trạng thái cuối. Nếu hệ thống không cung cấp khả năng quan sát hoặc dữ liệu đối soát cần thiết, khoảng trống đó phải được xử lý trước khi tuyên bố rủi ro đã được kiểm soát.

## 7. Ưu tiên trong điều kiện nguồn lực có hạn

Khi không thể kiểm thử mọi thứ ở cùng độ sâu, sắp xếp công việc theo thứ tự:

1. Các rủi ro có tác động nghiêm trọng hoặc yêu cầu bắt buộc về an toàn, bảo mật, pháp lý và dữ liệu.
2. Các hành trình nghiệp vụ cốt lõi và những thay đổi ảnh hưởng trực tiếp đến chúng.
3. Các ranh giới tích hợp có lịch sử lỗi, phụ thuộc bên ngoài hoặc khả năng phát hiện thấp.
4. Các lỗi đã từng lọt ra production và những khu vực có thay đổi lớn.
5. Các chức năng ít tác động, dễ phát hiện và có thể khôi phục.

Ưu tiên theo rủi ro không có nghĩa bỏ qua kiểm thử nền tảng. Mọi thay đổi vẫn cần mức kiểm tra tối thiểu phù hợp, chẳng hạn biên dịch, phân tích tĩnh, kiểm thử thành phần liên quan và kiểm tra hồi quy cơ bản. Phần tăng thêm được dành cho các tình huống có rủi ro cao hơn.

Một kế hoạch cắt giảm phạm vi nên nêu:

- Các rủi ro đã được kiểm thử ở độ sâu đầy đủ.
- Các rủi ro chỉ có bằng chứng một phần.
- Các tình huống chưa được kiểm tra và lý do.
- Biện pháp giảm thiểu hoặc giám sát bổ sung.
- Người chịu trách nhiệm chấp nhận rủi ro còn lại và thời điểm xem xét lại.

## 8. Theo dõi và điều chỉnh độ sâu theo bằng chứng

Độ sâu kiểm thử không nên cố định mãi. Sau mỗi lần chạy, sự cố, thay đổi kiến trúc hoặc phản hồi người dùng, nhóm cần cập nhật đánh giá.

Các tín hiệu hữu ích gồm:

| Tín hiệu | Điều nó cho biết | Hành động có thể cần |
| --- | --- | --- |
| Lỗi lọt ra production | Có thể thiếu kịch bản, oracle hoặc môi trường đại diện | Phân tích nguyên nhân và bổ sung kiểm thử ở nơi có thể phát hiện sớm |
| Tỷ lệ flaky cao | Tín hiệu kiểm thử thiếu ổn định | Sửa dữ liệu dùng chung, đồng bộ, thời gian chờ hoặc phụ thuộc |
| Nhiều lỗi tích hợp | Hợp đồng hoặc phối hợp giữa nhóm có vấn đề | Tăng contract test, kiểm thử tích hợp và quản lý version |
| Không phân loại được lỗi nhanh | Bằng chứng và quan sát chưa đủ | Bổ sung log có cấu trúc, trace và correlation ID |
| Thay đổi ít nhưng lỗi lặp lại | Kiểm thử hồi quy có thể chưa bao phủ nguyên nhân | Thêm kịch bản hồi quy theo lỗi đã xác nhận |
| Rủi ro giảm sau kiểm soát mới | Khả năng xảy ra hoặc khoảng trống phát hiện đã thay đổi | Chấm lại rủi ro và xem xét tối ưu độ sâu |

Khi một lỗi được phát hiện, hãy bổ sung kiểm thử tái hiện trước hoặc cùng lúc với sửa lỗi nếu có thể. Kiểm thử mới cần kiểm tra nguyên nhân gốc và điều kiện gây lỗi, không chỉ lặp lại biểu hiện bề mặt.

Các chỉ số nên được đọc cùng phạm vi và chất lượng oracle. Tỷ lệ pass tăng có thể do bộ kiểm thử đã bỏ bớt tình huống khó; số lượng test tăng có thể chỉ tạo thêm trùng lặp. Hãy theo dõi độ bao phủ rủi ro, lỗi lọt, độ ổn định và thời gian phát hiện cùng nhau.

## 9. Mẫu ghi nhận quyết định về độ sâu kiểm thử

Có thể dùng mẫu sau cho mỗi rủi ro quan trọng:

~~~text
ID / tên rủi ro:
Hành trình và thành phần liên quan:
Mô tả điều kiện và lỗi có thể xảy ra:
Hậu quả đối với người dùng / dữ liệu / hoạt động:

Tác động (I, 1-5):
Khả năng xảy ra (L, 1-5):
Khoảng trống phát hiện (G, 1-5):
Điểm ưu tiên R = I x L x G:
Giả định và dữ liệu hỗ trợ đánh giá:

Kiểm thử hiện có:
Oracle và bằng chứng hiện có:
Khoảng trống cần xử lý:
Độ sâu kiểm thử được chọn:
Điều kiện pass / quality gate:
Rủi ro còn lại:
Người chấp nhận rủi ro:
Điều kiện và thời điểm đánh giá lại:
~~~

Mẫu này giúp giải thích vì sao một rủi ro cần thêm kiểm thử hoặc vì sao độ sâu hiện tại được xem là đủ. Nó cũng tạo dấu vết cho quyết định khi phạm vi, nguồn lực hoặc điều kiện phát hành thay đổi.

## 10. Checklist chọn độ sâu kiểm thử

- [ ] Mô tả lỗi tiềm ẩn bằng điều kiện, sai lệch và hậu quả cụ thể.
- [ ] Đánh giá tác động đến người dùng, dữ liệu, tài chính, an toàn và hoạt động.
- [ ] Ước lượng khả năng xảy ra dựa trên tần suất sử dụng, độ phức tạp và lịch sử lỗi.
- [ ] Đánh giá khả năng phát hiện bằng oracle, độ bao phủ, môi trường và quan sát hiện có.
- [ ] Ghi rõ giả định và giới hạn của thang điểm rủi ro.
- [ ] Chọn tầng kiểm thử và điều kiện lỗi phù hợp với chế độ lỗi cần phát hiện.
- [ ] Với rủi ro cao, có bằng chứng tại các ranh giới liên quan và kiểm tra trạng thái cuối.
- [ ] Kiểm tra timeout, retry, đồng thời, phục hồi hoặc tải khi các điều kiện đó có liên quan.
- [ ] Xác định quality gate và người có thẩm quyền chấp nhận rủi ro còn lại.
- [ ] Lưu kết quả, phiên bản, dữ liệu, môi trường và bằng chứng để tái lập.
- [ ] Cập nhật độ sâu khi có lỗi lọt, thay đổi kiến trúc hoặc tín hiệu vận hành mới.

Chọn độ sâu kiểm thử theo rủi ro giúp nhóm tập trung vào những sai lệch có hậu quả lớn và khó phát hiện. Khi mỗi mức đầu tư kiểm thử gắn với một tình huống lỗi, một oracle và bằng chứng cụ thể, chiến lược có thể giải thích được, điều chỉnh được và hỗ trợ quyết định phát hành một cách có trách nhiệm.

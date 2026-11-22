# Đánh giá nhu cầu triển khai độc lập của từng năng lực

## 1. Mục tiêu và bối cảnh

Khi lựa chọn kiến trúc microservices, câu hỏi thực tế không phải là “Có thể tách chức năng này thành một service không?”, mà là **“Năng lực nghiệp vụ này có đủ nhu cầu và đủ điều kiện để được triển khai độc lập không?”**. Một hệ thống có thể gồm nhiều module rõ ràng mà vẫn triển khai chung; ngược lại, việc chia thành nhiều tiến trình, container hoặc kho mã không tự động tạo ra tính độc lập.

Sau bài này, người học có thể:
- Phân biệt **nhu cầu triển khai độc lập** với nhu cầu mở rộng tài nguyên, phân quyền mã nguồn và phân ranh giới nghiệp vụ.
- Thu thập bằng chứng về tốc độ phát hành, tính ổn định, đội ngũ, dữ liệu, phụ thuộc và chi phí vận hành cho từng năng lực.
- Xác định ranh giới nào có thể phát hành và quay lui mà ít buộc các năng lực khác thay đổi đồng thời.
- Đưa ra lựa chọn có căn cứ giữa module trong modular monolith, service độc lập hoặc phương án chuyển đổi từng bước.
- Ghi lại quyết định, điều kiện tiên quyết, tiêu chí kiểm chứng và thời điểm đánh giá lại.

**Phạm vi:** Bài tập trung vào quyết định triển khai độc lập ở cấp **năng lực nghiệp vụ (business capability)** trong bối cảnh kiến trúc hệ thống và microservices. Quyết định chi tiết về công nghệ triển khai, nền tảng hạ tầng hoặc công cụ điều phối chỉ xuất hiện khi tác động trực tiếp đến tính độc lập.

## 2. Mô hình tư duy: năng lực, ranh giới, đơn vị triển khai

**Năng lực nghiệp vụ** là điều tổ chức cần làm để tạo ra giá trị: quản lý danh mục sản phẩm, định giá, giỏ hàng, đặt hàng, thanh toán, quản lý tồn kho, vận chuyển hoặc gửi thông báo. Nó mô tả *khả năng thực hiện công việc*, không đồng nghĩa với một màn hình, một bảng dữ liệu, một lớp Java hay một endpoint.

**Ranh giới nghiệp vụ** là phạm vi trách nhiệm và quy tắc mà một thành phần nắm giữ. Trong thiết kế hướng miền, một bounded context có thể là ứng viên tốt cho ranh giới service, nhưng không có quy tắc “một bounded context bắt buộc bằng một microservice”. Một bounded context có thể chứa nhiều module, hoặc vẫn chạy chung trong một ứng dụng.

**Đơn vị triển khai (deployment unit)** là thứ được xây dựng, phát hành, khởi động, cập nhật và quay lui như một đơn vị. Một service chỉ thực sự độc lập về triển khai khi thay đổi thông thường của nó có thể đi vào sản xuất mà không bắt buộc phải phát hành đồng bộ các đơn vị còn lại.

Ví dụ đơn giản:

    Năng lực: Thanh toán
        |
        +-- Quy tắc: ủy quyền thanh toán, hoàn tiền, đối soát
        +-- Dữ liệu sở hữu: giao dịch và trạng thái thanh toán
        +-- Hợp đồng: yêu cầu thu tiền, sự kiện kết quả thanh toán
        +-- Đơn vị triển khai dự kiến: payment-service

Nếu payment-service vẫn yêu cầu checkout-service nâng phiên bản cùng lúc ở mỗi lần thay đổi, hoặc cả hai cùng ghi trực tiếp vào một nhóm bảng có ràng buộc chặt, thì độc lập triển khai chỉ mới tồn tại trên sơ đồ.

### Ba câu hỏi cần tách riêng

| Câu hỏi | Điều cần đánh giá | Không được suy diễn |
|---|---|---|
| Có nên đặt **ranh giới riêng**? | Quy tắc, từ vựng, dữ liệu và trách nhiệm có thực sự khác nhau? | Ranh giới rõ nghĩa là phải có tiến trình riêng |
| Có cần **triển khai riêng**? | Tần suất thay đổi, quyền tự chủ phát hành, cô lập lỗi, nghĩa vụ vận hành có khác đáng kể? | Nhiều commit nghĩa là phải có nhiều service |
| Có cần **mở rộng riêng**? | Tải, tài nguyên, độ trễ và cách xử lý tăng trưởng có khác biệt? | Tải cao luôn đòi microservice; có thể dùng worker, cache, partition |

Ba quyết định này liên quan nhưng không đồng nhất. Một module có thể có ranh giới rất sạch mà chưa cần triển khai độc lập. Một luồng xử lý nền có thể cần mở rộng riêng trước khi cần tách toàn bộ năng lực thành service.

## 3. Định nghĩa đúng “triển khai độc lập”

Đừng chỉ kiểm tra có pipeline CI/CD, Docker image hay repository riêng. Với một thay đổi nhỏ, bình thường của năng lực X, hãy hỏi:

1. Có thể **build và triển khai X** mà không bắt buộc xây dựng, triển khai lại Y không?
2. Khi X chạy phiên bản mới còn Y ở phiên bản cũ, các **API, sự kiện, thông điệp và schema** vẫn tương thích chứ?
3. Có thể **quay lui hoặc vô hiệu hóa** thay đổi của X khi có lỗi mà không bắt Y quay lui cùng lúc không?
4. X có quyền sở hữu rõ ràng đối với **quy tắc, dữ liệu và hợp đồng** mà nó thay đổi không?
5. X có cơ chế **quan sát, cảnh báo, kiểm thử và xử lý sự cố** đủ để đội phụ trách tự chịu trách nhiệm cho lần phát hành đó không?

Nếu câu trả lời liên tục là “phải chờ hoặc đổi cùng Y”, hãy tìm **phụ thuộc khiến phát hành đồng bộ**: chia sẻ schema, gọi API không tương thích, thư viện chung bị khóa phiên bản, một giao dịch trải qua nhiều service hoặc quy trình phê duyệt vốn yêu cầu cùng một lần phát hành.

Có thể ghi ba trạng thái thay vì nhị phân:
- **Độc lập hiện có:** Phát hành và quay lui riêng đã được kiểm chứng thực tế.
- **Có thể độc lập sau khi xử lý điều kiện:** Ranh giới tương đối rõ, nhưng còn hợp đồng, dữ liệu hoặc pipeline cần tách.
- **Chưa độc lập:** Các thay đổi thường xuyên phải được phát hành đồng bộ; chọn tách vật lý lúc này có thể chỉ làm tăng chi phí.

## 4. Vì sao một năng lực có thể cần triển khai riêng?

### 4.1. Nhịp thay đổi và tần suất phát hành khác nhau

Một nhóm liên tục thử nghiệm giá, khuyến mãi, thuật toán đề xuất hoặc giao diện khách hàng có thể cần phát hành nhiều lần mỗi ngày. Trong khi đó, năng lực đối soát tài chính có thể có chu kỳ kiểm thử và phê duyệt dài hơn.

**Tín hiệu có giá trị:** Các bản phát hành của năng lực A thường xuyên phải chờ lịch phát hành của B; thời gian chờ chiếm tỷ trọng lớn trong thời gian đưa thay đổi đến người dùng; việc phát hành chung tạo rủi ro hoặc chi phí phối hợp rõ rệt.

**Câu hỏi kiểm chứng:** Trong 6–12 tuần gần đây, có bao nhiêu lần thay đổi của A bị chậm *chỉ vì* phải phát hành chung? Mỗi lần chậm bao lâu, tác động đến khách hàng hoặc kinh doanh thế nào?

**Giới hạn:** Nếu cả hệ thống phát hành ít lần, có một đội nhỏ và không có nút thắt phối hợp, thêm nhiều pipeline riêng có thể làm vận hành chậm hơn.

### 4.2. Cô lập lỗi và giới hạn phạm vi ảnh hưởng

Một lỗi ở tính năng gửi email, xử lý ảnh hoặc gợi ý sản phẩm không nên làm sập luồng đặt hàng. Tách runtime có thể giúp khoanh vùng tài nguyên, giới hạn quyền và áp dụng cơ chế chịu lỗi.

Tuy nhiên, tách service **không tự động cô lập lỗi**. Nếu luồng checkout gọi đồng bộ đến recommendation-service và chờ vô thời hạn, sự cố đề xuất vẫn có thể làm checkout treo. Cần timeout, giới hạn đồng thời, circuit breaker khi phù hợp, cách trả kết quả dự phòng và khả năng vận hành suy giảm có kiểm soát.

**Câu hỏi kiểm chứng:** Khi năng lực A bị lỗi hoặc chậm, năng lực B có thể tiếp tục cung cấp chức năng cốt lõi ở mức chấp nhận được không? Có thể đặt giới hạn tài nguyên, mạng và chính sách phục hồi riêng không?

### 4.3. Tải và đặc tính tài nguyên khác nhau

Tìm kiếm có thể cần chỉ mục và truy vấn nhiều; tạo báo cáo có thể tốn CPU; xử lý hình ảnh có thể dùng hàng đợi và worker; thanh toán cần điều khiển chính xác tính đúng đắn hơn là tăng số luồng vô hạn.

Phát hành riêng giúp thay đổi cấu hình, tốc độ mở rộng và chu kỳ cập nhật thành phần theo nhu cầu. Nhưng **nhu cầu scale riêng không nhất thiết dẫn đến service nghiệp vụ riêng**: một tiến trình worker, hàng đợi công việc, cơ chế cache, tách workload đọc/ghi hoặc phân vùng dữ liệu đôi khi đã đủ.

**Bằng chứng cần có:** Biểu đồ tải theo giờ, mức CPU/RAM/IO, p95/p99 latency, queue depth, giới hạn tài nguyên, dự báo tăng trưởng và chi phí của các phương án.

### 4.4. Chủ sở hữu và khả năng tự chủ của đội ngũ

Một nhóm có thể phụ trách trọn vòng đời của năng lực: thiết kế, xây dựng, triển khai, trực vận hành và khắc phục sự cố. Độc lập triển khai có giá trị khi giảm chờ giữa các đội, hỗ trợ trách nhiệm rõ ràng và tránh tranh chấp trên một codebase quá rộng.

Ngược lại, với 2–4 kỹ sư duy trì nhiều service, sự phân mảnh có thể tạo gánh nặng trực vận hành, quản lý phiên bản, bảo mật và kiểm thử nhiều hơn lợi ích. **Không dùng số lượng đội hoặc sơ đồ tổ chức làm căn cứ duy nhất**: ranh giới nghiệp vụ vẫn cần gắn kết nội tại.

### 4.5. Yêu cầu bảo mật, tuân thủ và mức độ rủi ro khác nhau

Năng lực thanh toán, dữ liệu nhạy cảm hoặc xử lý giao dịch quan trọng có thể cần giới hạn quyền truy cập, kiểm toán, phê duyệt phát hành và chính sách lưu giữ dữ liệu riêng. Triển khai tách biệt đôi khi giúp tạo ranh giới kiểm soát cụ thể.

Nhưng khác biệt tuân thủ không tự động bắt buộc microservice. Có thể dùng module có quyền hạn rõ, cơ sở dữ liệu tách schema, chính sách xác thực hoặc quy trình quản trị riêng trong cùng ứng dụng nếu thỏa yêu cầu thực tế. Nên xác minh với các bên sở hữu rủi ro thay vì suy đoán yêu cầu pháp lý.

### 4.6. Thay đổi công nghệ và vòng đời phụ thuộc

Một năng lực có yêu cầu chuyên biệt về runtime, thư viện, storage engine hoặc mô hình xử lý có thể hưởng lợi từ vòng đời triển khai riêng. Tuy nhiên, **“muốn thử công nghệ mới”** tự nó là lý do yếu: đa công nghệ làm tăng chi phí vận hành, quan sát, đào tạo, bảo mật và hỗ trợ sự cố.

## 5. Thu thập bằng chứng trước khi chấm nhu cầu

Cần tách **số liệu quan sát**, **giả thuyết**, **ràng buộc bắt buộc** và **sở thích thiết kế**. Mỗi năng lực nên có bản ghi ngắn:

| Nhóm bằng chứng | Câu hỏi thực tế | Ví dụ dữ liệu |
|---|---|---|
| Thay đổi và phát hành | Năng lực này thay đổi bao lâu một lần? Bao nhiêu phát hành phải đi chung? | Lịch phát hành, lịch sử PR, lead time, blocked days |
| Phụ thuộc thay đổi | Sửa A có hay bắt sửa B trong cùng một đợt không? | Tỉ lệ PR/issue đồng thay đổi, dependency map |
| Tác động sự cố | Khi A lỗi, B có bắt buộc lỗi theo không? | Incident, hậu quả, sơ đồ call chain |
| Tải và tài nguyên | Đường cong tải và loại tài nguyên có tách biệt không? | RPS, latency, CPU, RAM, queue |
| Sở hữu nghiệp vụ | Ai quyết định quy tắc và chịu trách nhiệm kết quả? | Bản đồ năng lực, người phụ trách, ranh giới dữ liệu |
| Dữ liệu và giao dịch | A có thể sở hữu dữ liệu của mình không? Có bất biến xuyên ranh giới nào không? | Schema, truy vấn liên bảng, transaction, invariants |
| Hợp đồng và tương thích | Giao diện giữa A–B thay đổi ra sao? | OpenAPI, sự kiện, compatibility tests |
| Năng lực vận hành | Đội có thể trực, cảnh báo, quay lui và khôi phục độc lập không? | SLO, runbook, pipeline, dashboard |
| Chi phí | Vận hành riêng tăng chi phí bao nhiêu, đổi lại lợi ích gì? | Hạ tầng, on-call, quan sát, thời gian phối hợp |

Không cần đợi bộ dữ liệu hoàn hảo. Hãy đánh dấu “chưa đo” và ưu tiên đo các yếu tố có thể đảo ngược quyết định. Phỏng vấn nhóm sản phẩm, kỹ sư và vận hành nên dùng để bổ sung ngữ cảnh cho số liệu, không thay thế bằng chứng.

## 6. Quy trình đánh giá theo từng năng lực

### Bước 1 — Vẽ bản đồ năng lực, không bắt đầu từ bảng dữ liệu

Liệt kê năng lực cấp phù hợp: Danh mục, Định giá, Giỏ hàng, Đặt hàng, Thanh toán, Tồn kho, Giao vận, Thông báo. Với mỗi năng lực, ghi giá trị nó cung cấp, các quy tắc chính và bên sử dụng.

Tránh chia quá nhỏ theo mỗi CRUD, mỗi controller hoặc mỗi bảng. Một “service cập nhật địa chỉ”, “service kiểm tra mã giảm giá” và “service lấy tổng tiền” có thể chỉ là các thao tác trong cùng một ranh giới nghiệp vụ. Độ gắn kết về quy tắc thường quan trọng hơn số endpoint.

### Bước 2 — Phân loại phụ thuộc

Với từng cặp A–B, phân biệt:
- **Phụ thuộc dữ liệu:** cùng sửa bảng, dùng khóa ngoại xuyên miền, truy vấn join trực tiếp, dùng schema nội bộ của nhau.
- **Phụ thuộc giao dịch:** một bất biến bắt buộc phải đúng đồng thời, có transaction chung hoặc cần một trạng thái nhất quán ngay lập tức.
- **Phụ thuộc hợp đồng:** client và server buộc nâng phiên bản cùng lúc; thay đổi cấu trúc message làm hỏng bên nhận.
- **Phụ thuộc runtime:** A gọi B đồng bộ trong đường đi quan trọng; B chậm khiến A không thể hoàn thành.
- **Phụ thuộc tổ chức:** quy trình duyệt, kiểm thử, đội vận hành hoặc lịch phát hành buộc đi cùng nhau.

Tách từng loại là cần thiết vì biện pháp xử lý khác nhau. Một hợp đồng API chưa tương thích có thể sửa bằng phiên bản chuyển tiếp; một bất biến đòi transaction nguyên tử xuyên dữ liệu đôi khi khiến việc tách vật lý không phù hợp.

### Bước 3 — Đánh giá mức cần thiết và lợi ích

Có thể dùng thang **0–2** để làm rõ thảo luận, không coi tổng điểm là chân lý:
- **0:** Chưa thấy nhu cầu độc lập cụ thể.
- **1:** Có nhu cầu nhưng không thường xuyên hoặc có phương án đơn giản hơn.
- **2:** Nhu cầu lặp lại, tác động đáng kể, có bằng chứng và khó giải quyết bằng triển khai chung.

Đánh giá năm tiêu chí: (a) tắc nghẽn phát hành; (b) yêu cầu cô lập lỗi; (c) tải và tài nguyên; (d) tự chủ nhóm; (e) khác biệt về kiểm soát/rủi ro. Ghi kèm **bằng chứng, độ tin cậy và phương án thay thế** cho mỗi điểm.

Tổng điểm chỉ là tín hiệu để sắp xếp trao đổi. Hai năng lực cùng được 7 điểm vẫn có thể nhận quyết định khác nhau nếu một bên đang chia sẻ giao dịch nguyên tử, còn bên kia có hợp đồng ổn định và sở hữu dữ liệu riêng.

### Bước 4 — Kiểm tra khả năng tách về kỹ thuật và tổ chức

Dù lợi ích cao, không nên vội tách khi những điều kiện sau chưa giải quyết được:

1. Có một người/đội **sở hữu đầy đủ trách nhiệm** phát hành, trực vận hành và quyết định thay đổi.
2. Có khả năng **sở hữu dữ liệu rõ ràng**; bên ngoài chỉ truy cập qua hợp đồng, sự kiện hoặc bản sao đọc được thiết kế có chủ ý.
3. Quy tắc nghiệp vụ có thể được giữ bên trong ranh giới mà không phải gọi chéo quá nhiều ở mỗi bước.
4. Hợp đồng có đường **tiến hóa tương thích** trong giai đoạn hai phiên bản cùng tồn tại.
5. Có cách bảo toàn **bất biến và quy trình nghiệp vụ** khi một bước thất bại: từ chối, bù trừ, thử lại, xử lý thủ công hoặc thiết kế lại giao dịch.
6. Có pipeline, logging, tracing, đo lường, kiểm thử và runbook vừa đủ để vận hành độc lập.
7. Chi phí phát sinh có thể được chấp nhận và có người chịu trách nhiệm.

Nếu một điều kiện chưa đạt, kết luận hữu ích có thể là “Có nhu cầu, nhưng cần xử lý X và Y trước khi tách”, thay vì ép thành “Có” hoặc “Không”.

### Bước 5 — So sánh các lựa chọn ở cùng một vấn đề

| Lựa chọn | Thích hợp khi | Đổi lại |
|---|---|---|
| **Module trong modular monolith** | Nhóm nhỏ, phụ thuộc nghiệp vụ chặt, phát hành chung chưa gây đau; cần ranh giới mã nguồn rõ | Triển khai chung và chia sẻ tài nguyên runtime |
| **Module + worker hoặc hàng đợi riêng** | Nút thắt chủ yếu ở tải tác vụ nền, xử lý bất đồng bộ hoặc thời gian chạy | Cần quản lý hàng đợi, retry và tính lặp; ranh giới phát hành có thể vẫn chung |
| **Tách một service độc lập** | Lợi ích phát hành/cô lập rõ, hợp đồng ổn định, dữ liệu và trách nhiệm tương đối độc lập | Mạng, hệ phân tán, vận hành, sự cố mới |
| **Tách theo giai đoạn** | Nhu cầu có thật nhưng còn chia sẻ dữ liệu/hợp đồng; cần giảm rủi ro thay đổi | Vận hành song song tạm thời, cơ chế chuyển tiếp và kiểm soát dữ liệu |

Đánh giá cả **chi phí của không tách** (thời gian chờ, tác động sự cố, tốc độ đổi mới) lẫn **chi phí của tách** (hạ tầng, pipeline, giao tiếp mạng, bảo mật, observability, on-call, kiểm thử liên service và migration).

### Bước 6 — Ghi quyết định và điều kiện đánh giá lại

Một quyết định tốt cần chỉ ra **lý do tại thời điểm ra quyết định**, không biến lựa chọn hiện tại thành nguyên tắc bất biến. Ghi ngày, người tham gia, các phương án, bằng chứng, giả định, hậu quả, người sở hữu hành động và tín hiệu để xem lại.

Ví dụ kích hoạt đánh giá lại: số lần phát hành bị chặn tăng liên tục qua hai chu kỳ; sự cố phụ thuộc vượt ngưỡng thống nhất; lưu lượng tác vụ tăng vượt năng lực tách workload; hoặc nhóm vận hành mới có khả năng chịu trách nhiệm một service riêng.

## 7. Tình huống minh họa: nền tảng thương mại điện tử

Giả sử hệ thống ban đầu là modular monolith gồm bốn năng lực: **Catalog**, **Checkout/Order**, **Payment** và **Notification**. Các con số sau là *giả định minh họa*, không phải tiêu chuẩn áp dụng cho mọi tổ chức.

| Năng lực | Bằng chứng giả định | Quyết định ban đầu |
|---|---|---|
| Catalog | Đọc nhiều; cập nhật thông tin sản phẩm thường xuyên; cache đáp ứng nhu cầu; không có chờ phát hành đáng kể | Giữ module riêng trong cùng ứng dụng; tối ưu cache và truy vấn trước |
| Checkout/Order | Giao dịch chứa nhiều bất biến tức thời; thay đổi đồng thời với chính sách giá/khuyến mãi; rủi ro nghiệp vụ cao | Giữ ranh giới nghiệp vụ rõ; chưa tách nếu buộc có giao dịch đồng bộ chéo |
| Payment | Phải kiểm soát quyền, đối soát và quy trình phát hành riêng; đội phụ trách rõ; API ít thay đổi; cần cô lập rủi ro | Ứng viên tách service, với điều kiện xử lý tương thích và dữ liệu |
| Notification | Lưu lượng gửi tăng theo chiến dịch; xử lý chậm hoặc lỗi không được chặn đặt hàng; tính chất bất đồng bộ | Ưu tiên tách worker/queue; cân nhắc service riêng khi nhịp phát hành và quyền sở hữu biện minh được |

### Phân tích Payment kỹ hơn

Checkout muốn xác nhận đơn hàng; Payment chịu trách nhiệm quy tắc thanh toán và trạng thái giao dịch. Nếu để Checkout trực tiếp sửa bảng payment_transaction, thì Payment có image và pipeline riêng vẫn không tự chủ dữ liệu. Trước khi tách, cần chuyển về giao diện sở hữu rõ ràng, chẳng hạn:

    Checkout --> yêu cầu thanh toán --> Payment
    Checkout <-- mã giao dịch / trạng thái -- Payment
    Payment  --> sự kiện kết quả --> các bên quan tâm

Điều kiện thiết kế:
- Payment sở hữu trạng thái giao dịch và bảo đảm **idempotency** cho yêu cầu có thể được gửi lại.
- Checkout không diễn giải các cột nội bộ của Payment, mà dựa trên hợp đồng ổn định và trạng thái nghiệp vụ đã công bố.
- Callback hoặc event có thể đến muộn, trùng lặp hoặc sai thứ tự; bên nhận có cơ chế nhận diện trùng, quy tắc chuyển trạng thái và đối soát.
- Một lỗi mạng không thể được suy ra là “chưa trừ tiền”; hệ thống cần truy vấn trạng thái hoặc đối soát trước khi thực hiện lại hành động có hậu quả tài chính.
- Chính sách giữ đơn, hết hạn, hoàn tiền, bù trừ và xử lý thủ công phải có người sở hữu nghiệp vụ.

Nếu bài toán đòi tính nguyên tử tuyệt đối giữa nhiều bảng của Checkout và Payment mà chưa có cách thay đổi luồng nghiệp vụ, hãy ghi nhận đó là **rào cản tách**. Không nên thay một transaction nội bộ bằng chuỗi lời gọi mạng chỉ vì mong muốn có microservice.

### Phân tích Notification kỹ hơn

Notification có thể nhận một sự kiện “Đơn hàng đã xác nhận”, đưa công việc vào hàng đợi và gửi thông báo theo lô. Khi cổng email lỗi, checkout vẫn hoàn tất; công việc được retry có giới hạn và chuyển vào dead-letter queue khi cần xử lý.

Ở đây lợi ích chính là **cô lập workload và khả năng chịu lỗi**. Tách một nhóm worker tiêu thụ hàng đợi có thể giải quyết vấn đề dù phần cấu hình template vẫn là module của ứng dụng ban đầu. Chỉ tạo notification-service riêng khi nhu cầu phát hành, quản trị dữ liệu, đội phụ trách hoặc tích hợp đa kênh thực sự đủ lớn.

### Kết luận cho ví dụ

Không cần tách tất cả bốn năng lực thành bốn service. Quyết định có thể là **một hệ thống modular monolith được phân ranh giới tốt, một luồng worker bất đồng bộ, và một ứng viên Payment tách theo giai đoạn**. Khi số liệu thay đổi, quyết định có thể thay đổi.

## 8. Ma trận quyết định để sử dụng trong cuộc họp kiến trúc

Tạo một hàng cho mỗi năng lực. Không điền điểm theo cảm giác; mỗi điểm cần nguồn bằng chứng và người xác nhận.

| Năng lực | Lợi ích phát hành (0–2) | Cô lập sự cố (0–2) | Tải riêng (0–2) | Tự chủ nhóm (0–2) | Kiểm soát riêng (0–2) | Rào cản chính | Phương án |
|---|---:|---:|---:|---:|---:|---|---|
| Catalog | 1 | 0 | 1 | 1 | 0 | Truy vấn và cache chung | Module |
| Checkout/Order | 1 | 2 | 1 | 1 | 1 | Giao dịch và bất biến | Module, kiểm soát giới hạn |
| Payment | 2 | 2 | 1 | 2 | 2 | Sở hữu dữ liệu, hợp đồng | Chuẩn bị tách service |
| Notification | 1 | 2 | 2 | 1 | 0 | Retry và event delivery | Worker/queue; xem lại |

**Cách dùng:** Đây là ví dụ định tính nhằm làm rõ thảo luận, không phải bảng xếp hạng tự động. Năng lực có điểm cao vẫn có thể bị hoãn vì rào cản dữ liệu; năng lực điểm thấp vẫn có thể cần phân tách vì một yêu cầu kiểm soát đã được xác minh. Có thể điều chỉnh tiêu chí theo mục tiêu tổ chức, nhưng nên giữ nguyên bộ tiêu chí trong một kỳ đánh giá để tránh hợp lý hóa kết quả sau khi đã chọn giải pháp.

## 9. Các rào cản thường làm mất tính độc lập khi đã tách service

### 9.1. Dữ liệu dùng chung và truy cập chéo

**Dấu hiệu:** Service A sửa bảng do B quản lý; nhiều service dùng chung một bộ migration; schema đổi buộc toàn hệ thống nâng cấp.

**Hướng xử lý:** Chỉ định nguồn sự thật và chủ sở hữu dữ liệu; đưa truy cập ngoài ranh giới qua API/sự kiện; tạo read model khi cần truy vấn tổng hợp; áp dụng quá trình chuyển đổi schema có các bước tương thích trước khi xóa cột cũ. “Database per service” là một kiểu thực thi quyền sở hữu, không có nghĩa nhất thiết mỗi service phải dùng một máy cơ sở dữ liệu vật lý riêng.

### 9.2. Hợp đồng yêu cầu nâng cấp đồng thời

**Dấu hiệu:** Bất kỳ đổi tên trường JSON hoặc giá trị enum nào cũng buộc bên gửi và bên nhận deploy cùng lúc.

**Hướng xử lý:** Ưu tiên thay đổi tương thích ngược, áp dụng mở rộng trước–thu hẹp sau (expand–migrate–contract), consumer-driven contract tests khi phù hợp, và một khoảng thời gian cho hai phiên bản hoạt động song song. Hệ thống không thể độc lập phát hành nếu “triển khai đúng thứ tự trong năm phút” luôn là điều kiện bắt buộc.

### 9.3. Lời gọi đồng bộ kéo dài qua nhiều service

**Dấu hiệu:** Một yêu cầu người dùng đi qua nhiều chặng A → B → C → D; mọi chặng phải sẵn sàng; lỗi một chặng làm trễ toàn bộ.

**Hướng xử lý:** Xác định đường đi quan trọng; chỉ gọi đồng bộ khi câu trả lời cần ngay; dùng sự kiện/hàng đợi khi phù hợp; quy định timeout, retry có ngân sách, circuit breaker, giới hạn tải và kết quả dự phòng. Không biến mọi tương tác thành bất đồng bộ nếu nghiệp vụ thật sự cần phản hồi nhất quán ngay.

### 9.4. Giao dịch phân tán và nhất quán dữ liệu

**Dấu hiệu:** Một bước nghiệp vụ cần cập nhật đồng thời dữ liệu do nhiều service sở hữu, nhưng hệ thống giả định transaction ACID cũ vẫn hoạt động xuyên các service.

**Hướng xử lý:** Làm rõ bất biến nào cần đúng ngay, bất biến nào chấp nhận nhất quán cuối cùng (eventual consistency). Khi nghiệp vụ cho phép, thiết kế quy trình có trạng thái rõ ràng, thực hiện lại an toàn, bù trừ và đối soát. Transactional outbox có thể giúp ghi thay đổi dữ liệu và thông điệp cần phát trong cùng transaction cục bộ; phía nhận vẫn cần chịu được thông điệp trùng. Không xem saga là công thức thay thế trực tiếp mọi transaction.

### 9.5. Thư viện chung và cấu hình chung khóa phiên bản

**Dấu hiệu:** Sửa một model chung buộc hàng chục service nâng thư viện trong cùng ngày; một pipeline chung áp đặt lịch phát hành đồng bộ.

**Hướng xử lý:** Chỉ chia sẻ các thư viện ổn định, nhỏ và thật sự có tính nền tảng; tránh dùng chung mô hình miền thay cho hợp đồng. Tách pipeline hoặc giai đoạn phát hành khi mang lại quyền tự chủ thực tế; vẫn duy trì chính sách bảo mật và nền tảng chung cần thiết.

### 9.6. Độc lập trên sơ đồ nhưng thiếu năng lực vận hành

**Dấu hiệu:** Service có deployment riêng nhưng không ai nhận cảnh báo, không có đo lường, không có cơ chế quay lui hoặc mọi lần triển khai phải nhờ một nhóm hạ tầng duy nhất thao tác thủ công.

**Hướng xử lý:** Xây dựng mức tối thiểu về CI/CD, smoke test, tracing xuyên yêu cầu, metric chính, log có correlation ID, cảnh báo có người nhận, runbook và phương thức rollback/roll-forward. Quyền tự chủ phải đi cùng trách nhiệm.

## 10. Kiểm chứng trước khi tuyên bố triển khai độc lập

Đề xuất một phép thử trên môi trường đại diện sản xuất, sử dụng thay đổi tương thích nhỏ trong một năng lực ứng viên:

1. **Thử phát hành riêng:** Triển khai phiên bản mới của A trong khi B vẫn chạy phiên bản cũ. Xác nhận chức năng chính hoạt động và không cần thao tác bắt buộc trên B.
2. **Thử tương thích hai chiều:** Trong cửa sổ chuyển đổi, A mới/B cũ và A cũ/B mới có hành vi tương thích ở những kịch bản cần hỗ trợ.
3. **Thử quay lui hoặc vô hiệu hóa:** Khi A lỗi, có thể giảm tác động bằng rollback, roll-forward hoặc feature flag phù hợp mà không phải triển khai lại B.
4. **Thử cô lập lỗi:** Làm A chậm, tạm thời không sẵn sàng hoặc trả lỗi có kiểm soát; quan sát SLO của B, timeout, tài nguyên và phương án suy giảm.
5. **Thử dữ liệu:** Kiểm tra schema migration, sự kiện đến trễ/trùng, retry, tính nhất quán và quá trình đối soát; không chạy thử hủy hoại trên dữ liệu sản xuất.
6. **Thử vận hành:** Đội sở hữu có thể phát hiện lỗi, truy vết, phản ứng và khôi phục theo runbook đã thống nhất.

Ghi kết quả **đạt / chưa đạt / chưa kiểm chứng** và bằng chứng kèm theo. Một service được phát hành riêng thành công một lần vẫn chưa chứng minh rằng mọi thay đổi tương lai sẽ độc lập; tiếp tục theo dõi các đợt phát hành thực tế.

### Chỉ số theo dõi sau khi quyết định

- **Tỉ lệ phát hành độc lập:** Số lần A triển khai mà không buộc các thành phần khác cùng triển khai / tổng số lần triển khai A.
- **Thời gian chờ vì phụ thuộc:** Thời gian phát hành A bị kẹt bởi nhóm, lịch hoặc phiên bản khác.
- **Lead time và tần suất triển khai:** Dùng để xem quyền tự chủ có thật sự rút ngắn thời gian đưa giá trị đến khách hàng.
- **Change failure rate và thời gian khôi phục:** Theo dõi liệu số lần phát hành tăng có đi kèm rủi ro mới hay không.
- **Mức ảnh hưởng khi sự cố:** Năng lực nào vẫn đáp ứng SLO khi A không khỏe.
- **Chi phí vận hành trên năng lực:** Hạ tầng, theo dõi, trực sự cố, giấy phép, kiểm thử, nhân lực bảo trì.

Đọc các chỉ số cùng nhau: số lần triển khai tăng nhưng sự cố liên service và thời gian xử lý cũng tăng chưa chắc là cải thiện.

## 11. Những ngộ nhận thường gặp

**“Mỗi business capability phải là một microservice.”** Không. Bản đồ năng lực giúp nhận diện trách nhiệm; ranh giới triển khai còn phụ thuộc nhu cầu thay đổi, mức gắn kết và năng lực vận hành.

**“Một service có repository, Docker image và database riêng thì đã độc lập.”** Chưa đủ. Nếu schema, hợp đồng hoặc quy trình buộc triển khai đồng bộ, quyền tự chủ vẫn bị giới hạn.

**“Tách service luôn cô lập lỗi.”** Không. Lời gọi mạng đồng bộ, shared infrastructure, tài nguyên dùng chung và cấu hình retry sai có thể khuếch đại sự cố.

**“Chia nhỏ càng nhiều thì nhóm càng nhanh.”** Khi service quá nhỏ, thời gian xử lý giao tiếp, thay đổi hợp đồng, test liên service và trực vận hành có thể lớn hơn thời gian viết tính năng.

**“Khác biệt về tải nghĩa là phải tách nghiệp vụ.”** Có thể cần tách worker, cache, batch processor, storage hoặc cấu hình trước. So sánh giải pháp với nguyên nhân đo được.

**“Đã chọn modular monolith là thất bại của microservices.”** Modular monolith có thể là lựa chọn chủ động, hiệu quả và có khả năng tiến hóa. Ranh giới module tốt còn giúp tách service về sau khi có đủ lý do.

**“Điểm trong ma trận thay thế được phán đoán kiến trúc.”** Điểm giúp làm rõ bất đồng và xếp ưu tiên khảo sát; tính khả thi và bất biến nghiệp vụ có thể quan trọng hơn tổng điểm.

## 12. Mẫu biên bản quyết định kiến trúc (ADR)

Sử dụng mẫu sau cho **một năng lực**. Điền bằng số liệu và ràng buộc của hệ thống cụ thể:

    ADR: Cân nhắc triển khai độc lập cho <tên năng lực>
    Ngày / người quyết định:
    Bối cảnh và tác động đang quan sát:
    Ranh giới nghiệp vụ và dữ liệu đang sở hữu:
    Phụ thuộc với các năng lực khác:
    Số liệu phát hành, sự cố và tải:
    Các lựa chọn:
      A. Module trong ứng dụng hiện tại
      B. Tách workload/worker
      C. Tách service độc lập
      D. Tách dần sau khi xử lý phụ thuộc
    Quyết định và lý do:
    Giả định / rủi ro / chi phí:
    Điều kiện tiên quyết và người chịu trách nhiệm:
    Phép thử độc lập triển khai:
    Chỉ số theo dõi và ngưỡng xem xét lại:
    Ngày đánh giá lại:

Ví dụ ngắn: “Chưa tách Catalog trong quý này vì vấn đề chính là tải đọc, đã có thể tối ưu cache và chưa ghi nhận thời gian chờ phát hành đáng kể. Xem xét lại khi cache không đáp ứng mục tiêu độ trễ hoặc khi thay đổi Catalog thường xuyên chặn phát hành Checkout.” Đây là một **giả thuyết có thể kiểm chứng**, thay vì khẳng định vĩnh viễn.

## 13. Bài thực hành ra quyết định

Một hệ thống đăng ký khóa học có ba năng lực:
- **Enrollment:** Ghi danh học viên, kiểm tra điều kiện tiên quyết, giữ chỗ.
- **Billing:** Tạo hóa đơn, nhận kết quả thanh toán và hoàn tiền.
- **Email:** Gửi xác nhận và nhắc lịch.

Giả định: Enrollment và Billing cùng thay đổi quy tắc giá mỗi tháng; Email có nhiều đợt tăng tải và nhà cung cấp gửi thư thường xuyên lỗi; cả ba hiện đang dùng chung một cơ sở dữ liệu và được triển khai mỗi tuần.

**Yêu cầu thực hành:**
1. Liệt kê thêm ít nhất ba dữ liệu cần thu thập trước khi quyết định có tách từng năng lực.
2. Chỉ ra phụ thuộc nào buộc thay đổi đồng bộ và phân loại thành dữ liệu, hợp đồng, giao dịch, runtime hoặc tổ chức.
3. Đề xuất một phương án cho mỗi năng lực: giữ module, tách worker hoặc tách service; nêu một lợi ích và một chi phí cụ thể.
4. Mô tả một phép thử phát hành độc lập cho năng lực có khả năng tách cao nhất.
5. Ghi một điều kiện khiến bạn thay đổi quyết định sau ba tháng.

**Gợi ý tự đối chiếu:** Email thường là ứng viên tốt để tách luồng bất đồng bộ nhằm bảo vệ Enrollment khỏi sự cố nhà cung cấp thư, nhưng điều đó chưa mặc nhiên yêu cầu email-service riêng. Với Enrollment–Billing, cần làm rõ ranh giới dữ liệu, bất biến về ghi danh/thanh toán và khả năng xử lý thanh toán đến muộn hoặc trùng trước khi quyết định tách. Không có một đáp án duy nhất đúng khi thiếu số liệu về phát hành, sự cố và nguồn lực.

## 14. Ghi nhớ để áp dụng

Hãy quyết định theo thứ tự: **hiểu năng lực → đo nhu cầu khác biệt → phân tích phụ thuộc → so sánh phương án → kiểm tra khả năng vận hành → thử phát hành độc lập → xem xét lại bằng số liệu**.

Tách một năng lực thành microservice chỉ có giá trị khi tổ chức nhận được quyền tự chủ hoặc sự cô lập mà mình **thực sự cần**, trong khi chi phí kết nối và vận hành vẫn kiểm soát được. Khi nhu cầu chưa đủ rõ, xây dựng ranh giới module, quyền sở hữu dữ liệu và hợp đồng tốt trong modular monolith thường là bước tiến có giá trị, đồng thời giữ lựa chọn tách vật lý khi bằng chứng xuất hiện.
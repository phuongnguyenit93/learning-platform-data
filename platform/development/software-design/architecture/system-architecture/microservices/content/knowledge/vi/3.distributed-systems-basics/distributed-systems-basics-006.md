# Các mức nhất quán dữ liệu và nhất quán cuối cùng

## 1. Bối cảnh: vì sao microservices phải nói rõ về nhất quán?

Trong một ứng dụng đơn khối (monolith), một số thao tác có thể đọc và cập nhật nhiều bảng trong cùng một giao dịch cơ sở dữ liệu. Khi các năng lực được tách thành microservices, mỗi service thường sở hữu dữ liệu của mình; lời gọi qua mạng, thông điệp và bản sao dữ liệu không còn cập nhật tại cùng một thời điểm. Người dùng có thể đặt hàng thành công nhưng màn hình lịch sử đơn hàng chưa xuất hiện đơn mới ngay; tồn kho đã bị giữ chỗ trong hệ thống đặt hàng nhưng chỉ mục tìm kiếm vẫn hiển thị số lượng cũ trong vài giây.

Sự chậm trễ này không nhất thiết là lỗi. Nó trở thành vấn đề khi hệ thống **hứa một mức nhất quán mạnh hơn mức thực tế** hoặc khi nghiệp vụ không thể chịu được sự chênh lệch dữ liệu.

Câu hỏi thiết kế là: **Đối với từng dữ liệu và từng thao tác, người dùng có thể quan sát trạng thái cũ trong bao lâu, những bất biến nào phải luôn đúng, và hệ thống sẽ xử lý thế nào khi các bản sao chưa đồng bộ?**

Mục tiêu sau bài học:
- Phân biệt tính nhất quán (consistency) với tính đúng đắn của quy tắc nghiệp vụ, tính cô lập giao dịch và độ bền dữ liệu.
- Hiểu các mức bảo đảm thường gặp: tuyến tính (linearizability), thứ tự tuần tự (sequential consistency), nhân quả (causal consistency), nhất quán cuối cùng (eventual consistency), độ cũ dữ liệu có giới hạn (bounded staleness) và các bảo đảm theo phiên (session guarantees).
- Phân tích cách đồng bộ/bất đồng bộ, bản sao đọc, sự kiện, bộ nhớ đệm và mạng ảnh hưởng đến quan sát của người dùng.
- Thiết kế luồng nghiệp vụ chấp nhận trạng thái đang xử lý, sự kiện trễ/trùng/sai thứ tự, khả năng thử lại và đối soát.
- Chọn mức nhất quán bằng bất biến và bằng chứng đo lường, thay vì dùng nhãn “strong” hoặc “eventual” cho toàn hệ thống.

**Định hướng:** Không có yêu cầu mọi dữ liệu trong một hệ thống dùng cùng mức nhất quán. Số dư khả dụng, hạn mức giao dịch, giỏ hàng, chỉ mục tìm kiếm, số lượt xem và email xác nhận có thể cần những bảo đảm khác nhau.

## 2. Các khái niệm nền tảng cần phân biệt

### 2.1. Trạng thái chuẩn, bản sao và góc nhìn quan sát

- **Nguồn sự thật (source of truth):** Nơi có quyền quyết định trạng thái có hiệu lực của một dữ liệu hoặc bất biến. Ví dụ service Tồn kho quản lý số lượng khả dụng của từng SKU.
- **Bản sao (replica):** Một bản dữ liệu được đồng bộ từ nơi khác để tăng khả năng đọc, chịu lỗi hoặc phục vụ khu vực địa lý.
- **Bản chiếu phục vụ đọc (read projection/materialized view):** Dữ liệu được biến đổi cho mục đích truy vấn, chẳng hạn bảng tổng hợp đơn hàng trong trang cá nhân. Nó có thể cập nhật sau khi nguồn sự thật đã cam kết giao dịch.
- **Bộ nhớ đệm (cache):** Bản sao có thời hạn hoặc chính sách vô hiệu hóa. Cache cũ có thể xuất hiện ngay cả khi cơ sở dữ liệu gốc bảo đảm đọc mạnh.
- **Quan sát (observation):** Kết quả mà client nhìn thấy theo thời gian. Mức nhất quán là cam kết về những lịch sử đọc/ghi nào được phép quan sát.

Một hình dung đơn giản:

    10:00:00.000  Service A ghi trạng thái đơn = PAID vào dữ liệu sở hữu
    10:00:00.020  Giao dịch của A commit thành công
    10:00:00.035  A phát sự kiện OrderPaid vào luồng truyền
    10:00:00.120  Service B cập nhật read model lịch sử đơn hàng
    10:00:00.150  Client đọc B và thấy PAID

Trong khoảng 20–120 ms, A đã xác nhận trạng thái mới nhưng B vẫn có thể hiển thị trạng thái cũ. Con số chỉ để minh họa; trễ thực tế còn phụ thuộc hàng đợi, mạng, retry, lỗi và tải hệ thống.

### 2.2. Nhất quán không đồng nghĩa với tính đúng đắn

Trong lý thuyết hệ phân tán, “nhất quán” thường nói về **thứ tự và tính mới của giá trị quan sát được**. Trong ACID, chữ **C – Consistency** nói về việc một giao dịch đưa cơ sở dữ liệu từ trạng thái hợp lệ sang trạng thái hợp lệ theo ràng buộc đã định nghĩa. Hai cách dùng có liên quan nhưng **không đồng nhất**.

Ví dụ: Một ứng dụng có thể cung cấp đọc tuyến tính với giá trị tồn kho là -3, nếu hệ thống cho phép các thao tác sai quy tắc được commit. Đọc “mới nhất” không sửa được lỗi thiếu kiểm soát oversell. Ngược lại, một bản chiếu có độ trễ vài giây vẫn có thể phục vụ tốt việc xem thống kê, miễn mọi nghiệp vụ có ràng buộc tiền bạc dùng nguồn sự thật để quyết định.

Cũng cần phân biệt:
- **Isolation (cô lập giao dịch):** Các transaction đồng thời tác động lẫn nhau và được quan sát như thế nào trong một hệ dữ liệu.
- **Durability (bền vững):** Giao dịch đã được xác nhận có tồn tại sau lỗi/khởi động lại hay không theo cam kết của hệ lưu trữ.
- **Availability (khả dụng):** Hệ thống có trả được phản hồi hợp lệ khi có yêu cầu hay không.
- **Consistency model (mô hình nhất quán):** Quy tắc về giá trị và thứ tự mà các thao tác đọc/ghi có thể thấy.

Một cơ sở dữ liệu hỗ trợ transaction ACID không tự động bảo đảm mọi replica hoặc mọi read model trong hệ thống có cùng trạng thái ngay sau commit.

### 2.3. Độ tươi dữ liệu và độ hội tụ

**Độ tươi (freshness)** trả lời “Giá trị này chậm so với nguồn chuẩn bao lâu?”. Có thể đo bằng thời gian kể từ lần cập nhật cuối, tuổi phiên bản, hoặc lag của dòng sự kiện. **Hội tụ (convergence)** nghĩa là những bản sao sẽ đi về một kết quả tương thích theo quy tắc hợp nhất khi ngừng có ghi mới và quá trình đồng bộ cuối cùng được thực hiện thành công.

Không nên dùng “eventual” để ngụ ý “chắc chắn đồng bộ trong 5 giây”. Nhất quán cuối cùng cơ bản không cung cấp giới hạn thời gian cố định; muốn có cam kết như p99 trễ dưới 2 giây thì cần **SLO riêng, đo lường và cơ chế xử lý vi phạm**.

## 3. Nhìn các mức nhất quán qua hành vi đọc và ghi

Mức bảo đảm có thể được mô tả theo hai khía cạnh: **mức toàn cục** áp dụng cho mọi client và **mức theo phiên** áp dụng cho một client hoặc một chuỗi thao tác. Các mô hình không nhất thiết xếp thành một hàng từ yếu đến mạnh; bảo đảm nhân quả, độ cũ có giới hạn và bảo đảm phiên giải quyết các loại yêu cầu khác nhau.

### 3.1. Nhất quán tuyến tính — linearizability

Một hệ tuyến tính cho phép hình dung mỗi thao tác thành công xảy ra tại **một điểm tức thời** giữa lúc bắt đầu và lúc trả kết quả. Nếu ghi X=2 đã hoàn tất trước khi một lần đọc X bắt đầu, lần đọc đó phải thấy 2 hoặc giá trị của một thao tác ghi xảy ra sau đó. Nó tôn trọng thứ tự thời gian thực giữa các thao tác không chồng lấn.

Ví dụ:

    Client A: write(balance=90) --- trả thành công
                                      |
    Client B:                          +--- read(balance) => 90 hoặc mới hơn

Nếu Client B bắt đầu đọc **sau** khi A nhận xác nhận ghi thành công, kết quả 100 cũ sẽ vi phạm tính tuyến tính đối với cùng đối tượng, giả sử không có ghi khác làm giá trị trở lại 100.

Phù hợp với:
- Điều khiển quyền sở hữu độc quyền, khóa, bộ đếm số chỗ còn lại cần quyết định tại một nguồn.
- Kiểm soát số lượng tồn kho khả dụng theo ràng buộc cứng.
- Cập nhật cấu hình an toàn hoặc chuyển trạng thái mà việc đọc cũ dẫn tới quyết định nguy hiểm.

Đổi lại: thường cần phối hợp giữa các nút và phải quyết định cách hành xử khi mạng chia cắt; latency và khả dụng cho một số thao tác có thể bị ảnh hưởng.

**Lưu ý:** Một transaction có isolation serializable chưa chắc linearizable theo thời gian thực. Serializable yêu cầu có lịch sắp xếp tương đương tuần tự cho các giao dịch; linearizability còn ràng buộc thứ tự thực giữa các thao tác không chồng lấn. Muốn kết hợp cả hai đối với giao dịch, có khái niệm strict serializability.

### 3.2. Nhất quán tuần tự — sequential consistency

Các thao tác của mọi client có thể được giải thích bằng **một thứ tự tuần tự chung**, trong đó thứ tự các thao tác của **mỗi client** được giữ. Tuy nhiên, thứ tự đó không nhất thiết phải tôn trọng thời gian thực giữa các client.

Ví dụ A hoàn tất ghi rồi B mới bắt đầu đọc, B vẫn có thể thấy giá trị cũ nếu thứ tự tuần tự được giải thích phù hợp với thứ tự nội bộ của từng client. Đây là điểm khác linearizability.

Trong thực hành ứng dụng, ít khi chỉ dựa vào nhãn “sequential”; hãy xác định chính xác phạm vi, đối tượng và cơ chế hệ lưu trữ thực sự cam kết.

### 3.3. Nhất quán nhân quả — causal consistency

Nếu thao tác B **phụ thuộc nhân quả** vào thao tác A, mọi người quan sát B phải có thể quan sát A trước hoặc cùng lúc theo quy tắc của hệ thống. Các thao tác độc lập, đồng thời có thể được các bản sao nhìn thấy theo thứ tự khác nhau.

Ví dụ:
1. Người dùng đăng bài P.
2. Người dùng khác đọc P và tạo bình luận C trả lời P.
3. Một client đã thấy C không nên thấy “bình luận về bài chưa tồn tại” vì P chưa hiện diện trong góc nhìn của client ấy.

Quan hệ nhân quả không chỉ là timestamp gần nhau. Hệ thống phải theo dõi hoặc truyền thông tin phụ thuộc, chẳng hạn thông qua phiên bản, logical clocks hay context được hỗ trợ bởi cơ sở dữ liệu/giao thức. Nếu không có cơ chế này, xử lý sự kiện theo thời gian đến không đảm bảo causal consistency.

### 3.4. Nhất quán cuối cùng — eventual consistency

Nếu **không còn cập nhật mới** và thông điệp cùng cơ chế đồng bộ cuối cùng được truyền, áp dụng thành công, các replica sẽ **hội tụ** về trạng thái được xác định. Trong khi đang đồng bộ, các replica có thể cho kết quả khác nhau và một lần đọc có thể thấy dữ liệu cũ.

Ví dụ:

    T0:      Giá sản phẩm ở nguồn chuẩn = 120
    T0+10ms: Bản chiếu tìm kiếm vẫn = 100
    T0+2s:   Bản chiếu nhận sự kiện, cập nhật = 120

Trường hợp này phù hợp nếu giá hiển thị trong tìm kiếm chỉ để tham khảo và giá xác nhận cuối cùng được kiểm tra ở Pricing/Checkout. Nếu dùng giá 100 cũ để chốt số tiền trong giao dịch mà không kiểm tra, hệ thống đã áp dụng sai mức nhất quán.

**Điều kiện cần nói rõ:** “Eventual” không có nghĩa mọi lỗi tự được sửa. Nếu message mất, consumer bị kẹt vô hạn, thao tác merge không xác định hoặc bản ghi bị xóa sai, dữ liệu có thể không hội tụ. Hệ thống cần cơ chế chuyển phát, retry, khôi phục và đối soát đủ cho cam kết thực tế.

### 3.5. Độ cũ có giới hạn — bounded staleness

Hệ thống có thể cam kết bản đọc không cũ hơn **một khoảng thời gian K** hoặc **một số phiên bản cập nhật** theo giao thức cụ thể. Cam kết này mạnh hơn lời hứa “sau cùng sẽ đúng” ở khía cạnh độ cũ, nhưng chưa nhất thiết tạo thứ tự tuyến tính toàn cục.

Ví dụ hợp đồng đọc dashboard: “Độ trễ cập nhật tối đa được phép là 30 giây; nếu không xác minh được độ trễ, hiển thị trạng thái dữ liệu chưa cập nhật và không dùng kết quả để ra quyết định thanh toán”.

Phải phân biệt **đảm bảo kỹ thuật** của hạ tầng dữ liệu với **mục tiêu SLO**. Việc quan sát p99 lag 3 giây không chứng minh mọi lần đọc đều bị giới hạn trong 3 giây.

### 3.6. Các bảo đảm nhất quán theo phiên — session guarantees

Một người dùng thường kỳ vọng ứng dụng ổn định trong phiên của mình, dù dữ liệu toàn hệ thống đồng bộ bất đồng bộ:

| Bảo đảm | Ý nghĩa đối với một phiên | Ví dụ |
|---|---|---|
| **Read-your-writes** | Sau khi chính bạn ghi thành công, các lần đọc tiếp theo của bạn không thấy trạng thái trước ghi | Vừa sửa tên hồ sơ, tải lại vẫn thấy tên mới |
| **Monotonic reads** | Một khi phiên đã thấy phiên bản mới hơn, không quay về phiên bản cũ hơn ở lần đọc sau | Chuyển giữa các replica vẫn không “mất” đơn hàng đã nhìn thấy |
| **Monotonic writes** | Những lần ghi liên tiếp của cùng phiên được áp dụng theo thứ tự phù hợp | Đổi ảnh đại diện A rồi B, B không bị A ghi đè về sau |
| **Writes-follow-reads** | Ghi dựa trên dữ liệu đã đọc được đặt sau các cập nhật mà phiên đã quan sát | Trả lời một bình luận mà client đã nhìn thấy |

Ví dụ lỗi read-your-writes:

    09:00:00  POST /profile   → ghi primary, trả 200
    09:00:01  GET /profile    → đọc replica đang chậm, trả tên cũ
    09:00:03  GET /profile    → replica bắt kịp, trả tên mới

Giải pháp có thể là đọc từ primary trong cửa sổ ngắn, dùng session token/phiên bản tối thiểu, chờ replica bắt kịp có timeout, hoặc dùng kết quả vừa ghi để cập nhật giao diện tạm thời với trạng thái được chỉ rõ. Mỗi lựa chọn có chi phí và rủi ro riêng.

## 4. Bảng so sánh sử dụng trong thiết kế

| Mức/bảo đảm | Quan sát được phép | Điểm có giá trị | Cần làm rõ |
|---|---|---|---|
| Linearizable | Đọc bắt đầu sau ghi hoàn tất phải thấy ghi đó hoặc mới hơn | Quyết định tại dữ liệu có ràng buộc cứng | Phạm vi đối tượng/transaction, partition, latency |
| Sequential | Có một thứ tự chung giữ thứ tự thao tác từng client | Thứ tự thao tác hợp lý theo client | Không nhất thiết giữ thứ tự thời gian thực |
| Causal | Không thấy hậu quả trước nguyên nhân | Thảo luận, cộng tác, chuỗi cập nhật có phụ thuộc | Theo dõi quan hệ nhân quả và merge |
| Eventual | Có thể thấy dữ liệu cũ; hội tụ khi đồng bộ hoàn tất | Search index, feed, analytics, read model | Không bảo đảm thời gian hội tụ cố định |
| Bounded staleness | Dữ liệu không vượt ngưỡng cũ được cam kết | Báo cáo có độ tươi tối thiểu | Cơ chế áp ngưỡng và hành vi khi vượt |
| Read-your-writes | Chính phiên không thấy trạng thái trước ghi vừa hoàn tất | Hồ sơ, giỏ hàng, cập nhật trực tiếp | Token phiên, route đọc, thời hạn |
| Monotonic reads | Phiên không bị lùi về phiên bản cũ | Giao diện ổn định khi đổi replica | Theo dõi phiên bản đã thấy |

**Không xem đây là thang điểm**: linearizability mạnh theo thời gian thực, còn causal và session guarantees áp vào những quan hệ khác nhau. Luôn ghi rõ bảo đảm áp dụng cho **một key, một collection, một transaction, một service hay toàn hệ thống**.

## 5. Những lựa chọn hạ tầng tạo ra khác biệt nhất quán

### 5.1. Replication đồng bộ và bất đồng bộ

**Đồng bộ (synchronous replication):** Bên ghi có thể chờ số bản sao hoặc đa số cần thiết xác nhận trước khi trả thành công. Điều này có thể giảm khoảng cách dữ liệu giữa các replica đủ điều kiện, nhưng không bảo đảm mọi follower trả đọc tuyến tính; hành vi đọc phụ thuộc giao thức, quorum, leader lease và cách xử lý thành viên mạng.

**Bất đồng bộ (asynchronous replication):** Primary có thể xác nhận ghi trước khi follower nhận được cập nhật. Đọc follower có thể thấy dữ liệu cũ, và khi primary gặp lỗi ngay sau khi xác nhận, hệ thống có thể có rủi ro mất dữ liệu ở replica được bầu mới nếu cơ chế failover không bảo toàn những ghi đã xác nhận.

**Điểm cần hỏi nhà cung cấp/thiết kế:** Ghi thành công nghĩa là đã bền vững ở đâu? Replica nào được phép nhận đọc? Có cam kết read-after-write không? Failover có thể bỏ mất ghi nào đã ACK? Khi mạng chia cắt, thao tác nào bị từ chối?

### 5.2. Leader, follower và quorum

Hệ thống kiểu leader-based thường gửi ghi qua leader và nhân bản sang follower. Để đọc mới nhất theo mô hình có leader, có thể cần đọc qua leader hoặc xác nhận leader còn hợp lệ; đọc follower tùy ý có thể cũ.

Trong một số mô hình nhân bản theo quorum với N bản sao, W xác nhận ghi và R xác nhận đọc, điều kiện thường được nhắc là **R + W > N**. Đây chỉ là trực giác về tập bản sao giao nhau dưới **các giả định cụ thể**; nó không tự bảo đảm linearizability trong mọi hệ thống. Các biến thể như sloppy quorum, hinted handoff, xung đột phiên bản, ghi đồng thời, failure detection và cơ chế chọn bản mới nhất có thể làm kết luận đơn giản bị sai.

Ví dụ N=3, W=2, R=2 có thể có một nút nằm trong cả nhóm đọc và ghi. Nhưng ứng dụng vẫn phải biết node/phiên bản nào được chọn, thông tin ghi đã được bền vững ra sao và thuật toán xử lý xung đột có đúng điều kiện không. **Không cấu hình quorum chỉ bằng công thức mà bỏ qua tài liệu của datastore cụ thể.**

### 5.3. Cache và replica đọc

Một primary mạnh vẫn có thể tạo trải nghiệm eventual consistency khi kết quả đi qua:
- Cache có TTL chưa hết.
- CDN phục vụ tài liệu hoặc API response cũ.
- Read replica trễ theo dòng ghi.
- Read model cập nhật từ sự kiện.
- Trình duyệt giữ dữ liệu lạc hậu hoặc bỏ qua kết quả ghi.

Vì vậy phải thiết kế **end-to-end consistency** cho đường đi thực tế. Không đủ để nói “database của chúng ta ACID” khi UI đọc một cache chưa bị vô hiệu hóa.

### 5.4. Sự kiện và bản chiếu đọc (CQRS)

Với CQRS, đường ghi và đường đọc có thể dùng mô hình khác nhau. Thông thường:

    Client -> Command API -> Source of Truth -> Commit
                                             |
                                             +-> Event/Outbox
                                                  |
                                                  v
                                            Consumer
                                                  |
                                                  v
                                          Read Projection
                                                  |
    Client <- Query API <-------------------------+

Đường ghi có thể bảo vệ các bất biến trong một transaction cục bộ; đường đọc từ projection có thể cập nhật sau. Điều này không làm CQRS mặc nhiên cần event sourcing, cũng không có nghĩa mọi truy vấn CQRS phải bất đồng bộ.

Cần mô tả trong hợp đồng: khi lệnh ghi trả thành công thì **đã hoàn tất phần nào**, khi nào projection có thể thấy dữ liệu mới, và client cần xử lý trạng thái chờ thế nào.

## 6. CAP và PACELC: dùng đúng phạm vi

### 6.1. CAP nói gì?

Trong một hệ lưu trữ phân tán có khả năng xảy ra **network partition**, mô hình CAP chỉ ra căng thẳng giữa:
- **C — Consistency:** Nhất quán kiểu single-copy/linearizable theo mô hình CAP.
- **A — Availability:** Yêu cầu gửi tới một nút không lỗi phải nhận được phản hồi hợp lệ (không chỉ là trang lỗi) trong mô hình.
- **P — Partition tolerance:** Hệ thống phải xét trường hợp mạng bị chia cắt khiến các nhóm nút không giao tiếp được.

Khi partition xảy ra, một thiết kế không thể đồng thời hứa phản hồi thành công mọi yêu cầu và duy trì tính nhất quán mạnh ấy ở mọi phía. Hệ thống có thể từ chối/treo một số thao tác để bảo toàn nhất quán, hoặc cho phép thao tác tiến triển rồi hòa giải xung đột theo chính sách.

Không suy diễn:
- “Microservices bắt buộc chọn AP” là sai: lựa chọn có thể khác theo từng thao tác, từng dữ liệu.
- “CA tồn tại bình thường trên mạng có partition mà không đánh đổi” là thiếu điều kiện.
- “CP nghĩa là hệ thống luôn ngừng hoạt động khi có một lỗi bất kỳ” là quá đơn giản.
- “CAP cho biết mọi chuyện về độ trễ” là sai: CAP không giải thích đầy đủ lựa chọn trong thời gian mạng khỏe.

### 6.2. PACELC bổ sung điều gì?

PACELC là cách ghi nhớ rằng **nếu có partition (P), cân nhắc availability (A) và consistency (C); còn bình thường (Else), cân nhắc latency (L) và consistency (C)**.

Ví dụ việc chờ xác nhận qua vùng địa lý xa có thể giúp bảo đảm ghi mạnh hơn nhưng tăng thời gian phản hồi. Một read model gần người dùng có thể giảm latency nhưng nhận cập nhật sau vài trăm ms hoặc vài giây.

Đây là **khung tư duy**, không phải sơ đồ tự động phân loại hệ thống. Các datastore có nhiều chế độ đọc/ghi và giao thức khác nhau; cần xác minh hành vi thực tế theo cấu hình và thất bại cụ thể.

## 7. Chọn mức nhất quán từ quy tắc nghiệp vụ

Một tiêu chí quan trọng là **bất biến nghiệp vụ (business invariant)**: điều bắt buộc luôn đúng trong phạm vi một quyết định.

| Năng lực / tình huống | Bất biến hoặc kỳ vọng | Lựa chọn thường phù hợp |
|---|---|---|
| Trừ số lượng vé cuối cùng | Không xác nhận bán vượt số vé được phép | Quyết định nguyên tử tại nơi sở hữu tồn kho; đọc mạnh hoặc cơ chế phân bổ chặt |
| Ghi nhận thanh toán | Không ghi nhận hai lần cùng một giao dịch; trạng thái không nhảy lùi sai | Transaction cục bộ + idempotency + state machine; đối soát |
| Hiển thị số lượt xem | Có thể trễ vài giây hoặc phút | Eventual consistency; cộng dồn theo lô |
| Trang tìm kiếm sản phẩm | Kết quả có thể chậm, nhưng checkout xác minh giá/tồn | Index eventual + kiểm tra tại nguồn chuẩn trước chốt |
| Sửa hồ sơ cá nhân | Người sửa mong nhìn thấy thay đổi ngay | Read-your-writes hoặc phản hồi lưu trạng thái rõ |
| Bảng điều khiển doanh thu | Số liệu cần có thời điểm chốt và mức trễ công bố | Snapshot/bounded-staleness SLO + dấu thời gian |
| Danh sách bạn bè và bình luận | Một bình luận không nên xuất hiện trước bài mà nó tham chiếu | Causal/ordering phù hợp, hoặc UI xử lý dữ liệu chưa đủ |
| Khóa phân tán, cấp lease | Một thời điểm chỉ một chủ sở hữu hợp lệ | Cơ chế đồng thuận/lease có fencing token và kiểm soát hiệu lực |

Quan trọng: **Không cần toàn hệ thống linearizable để bảo toàn một bất biến.** Có thể dùng lệnh ghi có điều kiện tại aggregate sở hữu quy tắc, optimistic concurrency hoặc phân bổ quota trước; các màn hình và projections liên quan vẫn eventual.

### Phân biệt trạng thái hiển thị với quyền ra quyết định

Ví dụ trang sản phẩm hiển thị “Còn 1 chiếc” từ cache 2 giây trước. Đây có thể chấp nhận được nếu đó là **thông tin tham khảo** và hệ thống xác nhận lại tồn kho tại lúc giữ hàng.

Ngược lại, nếu checkout tin vào cache để khẳng định “đặt hàng thành công”, nó có thể vi phạm bất biến dù cache chỉ chậm 100 ms. Tốc độ trễ thấp không thay thế được thẩm quyền dữ liệu.

## 8. Thiết kế một luồng eventual consistency có kiểm soát

Giả sử nghiệp vụ đặt hàng gồm **Order**, **Inventory** và **Payment**. Mỗi service sở hữu một phần dữ liệu và không chia sẻ transaction ACID xuyên cả ba.

### 8.1. Vạch rõ trạng thái nghiệp vụ

Một luồng minh họa:

    OrderCreated
         |
         v
    PENDING_RESERVATION
         |--- InventoryReserved ---> PENDING_PAYMENT
         |                               |--- PaymentSucceeded ---> CONFIRMED
         |                               +--- PaymentFailed ------> CANCELLING
         +--- InventoryRejected ----> REJECTED

    CANCELLING --(release reservation / refund if necessary)--> CANCELLED

Đây là **một mô hình khả thi**, không phải trạng thái tiêu chuẩn cho mọi sản phẩm. Trạng thái phải thể hiện điều nghiệp vụ đã biết, điều đang chờ và điều có thể khôi phục. Không nên báo “Đơn hàng hoàn tất” ngay khi chỉ mới ghi OrderCreated, trừ khi hợp đồng sản phẩm định nghĩa rõ “đã nhận yêu cầu” là hoàn tất phần nào.

### 8.2. Tách cam kết cục bộ khỏi hiệu ứng xuyên service

- Order commit đơn ở trạng thái **PENDING** trong transaction của Order.
- Một sự kiện hoặc lệnh đáng tin cậy yêu cầu Inventory giữ chỗ.
- Inventory dùng transaction cục bộ để kiểm tra số lượng và giữ chỗ; trả kết quả dưới dạng thông điệp.
- Order cập nhật trạng thái dựa trên kết quả và tiếp tục yêu cầu Payment khi phù hợp.
- Nếu Payment thất bại, quy trình cần trả lại số lượng giữ chỗ hoặc chuyển sang xử lý có kiểm soát.

Không có “một transaction duy nhất” xuyên ba service chỉ vì một API bên ngoài trả một mã HTTP. Hãy xem quy trình như **nhiều trạng thái trung gian hữu hạn**, mỗi trạng thái có chủ sở hữu và đường phục hồi.

### 8.3. Nguồn sự thật của từng dữ liệu

| Dữ liệu | Service quyết định | Bản sao chấp nhận trễ |
|---|---|---|
| Đơn hàng và trạng thái đặt hàng | Order | Lịch sử đơn ở trang cá nhân, báo cáo |
| Khả dụng và giữ chỗ tồn kho | Inventory | Badge “còn hàng”, chỉ mục tìm kiếm |
| Giao dịch, xác nhận và hoàn tiền | Payment | Trang tổng hợp đơn, thống kê |
| Gửi email/SMS | Notification | Báo cáo trạng thái gửi |

Consumer không nên sửa trực tiếp bảng thuộc service khác. Bản chiếu nhận cập nhật qua hợp đồng, nhưng khi cần ra quyết định có bất biến, phải dùng service sở hữu hoặc một cơ chế được ủy quyền có bảo đảm tương đương.

## 9. Đảm bảo phát sự kiện: tránh bài toán ghi kép

### 9.1. Lỗi dual write

Đoạn giả mã sau có lỗ hổng:

~~~text
BEGIN transaction
  UPDATE orders SET status = 'PAID' WHERE id = 42;
COMMIT
publish("OrderPaid", orderId=42);
~~~

Nếu ứng dụng chết giữa COMMIT và publish, database có đơn PAID nhưng hệ thống đọc hoặc service khác không bao giờ biết sự kiện. Đảo thứ tự publish trước commit lại có thể tạo sự kiện cho một giao dịch cuối cùng rollback.

### 9.2. Transactional outbox

Một cách thực hành phổ biến là **ghi bản ghi nghiệp vụ và bản ghi cần phát** trong cùng transaction của **một datastore**:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID', version = version + 1
WHERE id = 42 AND status = 'PENDING_PAYMENT';

INSERT INTO outbox (
    event_id, aggregate_type, aggregate_id, event_type, payload, created_at
) VALUES (
    'evt-42-paid', 'Order', '42', 'OrderPaid',
    '{"orderId":42,"status":"PAID","version":5}', CURRENT_TIMESTAMP
);

COMMIT;
~~~

Đây chỉ là mã minh họa, không phải SQL chạy nguyên trạng cho mọi dialect. Trong triển khai thực tế, cần kiểm tra số hàng UPDATE để bảo đảm chuyển trạng thái hợp lệ, dùng event ID duy nhất, và ghi outbox chỉ khi thay đổi nghiệp vụ thật sự xảy ra. Event ID không nên suy ra cố định từ order ID nếu một đơn có thể tạo nhiều sự kiện cùng loại qua các lần chuyển trạng thái hợp lệ.

Một publisher riêng đọc outbox và gửi thông điệp. Publisher có thể gửi thành công rồi chết trước khi đánh dấu đã gửi, dẫn tới **gửi lại cùng sự kiện**. Vì vậy outbox giúp tránh mất sự kiện do dual write, nhưng **không tạo exactly-once processing end-to-end**.

Cần có:
- Quy tắc chọn/bảo vệ bản ghi outbox khi nhiều publisher chạy song song.
- Cơ chế retry có giới hạn, backoff, quan sát độ trễ và bản ghi lỗi.
- Chỉ xóa hoặc lưu trữ outbox khi điều kiện khôi phục đã rõ.
- Phân biệt “đã publish cho broker” và “mọi consumer đã áp dụng”.

Có thể phát outbox qua polling hoặc change data capture (CDC) nếu hạ tầng phù hợp. Hợp đồng nghiệp vụ không nên phụ thuộc vào cơ chế chuyển tải cụ thể.

## 10. Consumer an toàn trước trùng lặp và sai thứ tự

### 10.1. At-least-once delivery và idempotency

Nhiều hệ truyền thông điệp có thể phát lại sau timeout, reconnect, rebalance hoặc crash. Consumer nên xử lý trùng an toàn trong phạm vi effect của mình.

Một mẫu giản lược:

~~~text
onMessage(event):
    begin local transaction
        if processed_events already contains event.eventId:
            commit
            ack message
            return

        validate event schema and business transition
        update local projection or state
        insert processed_events(eventId)
    commit

    ack message
~~~

**Điểm mấu chốt:** Ghi nhận đã xử lý và tác động lên dữ liệu **phải cùng transaction cục bộ** khi có thể, nếu không vẫn có cửa sổ crash. Bảng processed_events cần unique constraint trên event ID theo phạm vi thích hợp; khi hai consumer đua nhau xử lý cùng ID, unique constraint hoặc khóa giao dịch phải ngăn effect nhân đôi.

Nếu tác động là API tới bên ngoài (ví dụ gửi SMS hoặc thực hiện thanh toán), transaction cục bộ không bao trùm được hệ bên ngoài. Cần **idempotency key**, trạng thái yêu cầu, retry cẩn trọng và cơ chế đối soát theo bảo đảm của nhà cung cấp. Giao thức end-to-end thường đạt “effectively once” trong phạm vi định nghĩa, không nên hứa exactly once tuyệt đối qua mọi ranh giới.

### 10.2. Message ordering và version guard

Một hàng đợi có thể đảm bảo thứ tự **trong một partition/key** nhưng không đảm bảo giữa mọi key, mọi consumer hoặc qua retry/rehydration. Nếu sự kiện của một đơn đến như sau:

    OrderStatusChanged(order=42, version=7, status=PAID)
    OrderStatusChanged(order=42, version=6, status=PENDING_PAYMENT)

Consumer cập nhật mù theo thứ tự nhận sẽ làm trạng thái lùi về PENDING_PAYMENT.

Có thể thiết kế read model với **version tăng đơn điệu theo aggregate**:

~~~sql
UPDATE order_projection
SET status = :status,
    source_version = :incoming_version
WHERE order_id = :order_id
  AND source_version < :incoming_version;
~~~

Tùy trường hợp cần xử lý record chưa tồn tại bằng UPSERT có điều kiện. Cũng cần quyết định khi nhận version 7 nhưng thiếu version 6: nếu sự kiện là **snapshot trạng thái đầy đủ**, có thể cho phép bỏ qua version cũ; nếu là **delta phụ thuộc trình tự**, phải chờ/replay đúng thứ tự hoặc tái xây dựng từ nguồn.

Không nên dùng timestamp máy chủ để xác định thứ tự nếu đồng hồ có thể lệch, trừ khi hệ thống đã định nghĩa được clock và chính sách hợp nhất đáng tin cậy.

### 10.3. Xóa dữ liệu và bản ghi đánh dấu (tombstone)

Nếu nguồn xóa một thực thể nhưng sự kiện cập nhật cũ đến sau, read model có thể “hồi sinh” dữ liệu đã xóa. Dùng version/sequence và tombstone, hoặc chính sách dọn dẹp có bảo đảm replay để ngăn hiện tượng này.

Khi có yêu cầu xóa dữ liệu nhạy cảm, tombstone cũng phải thiết kế tương thích với yêu cầu lưu trữ và xóa; không giữ payload nhạy cảm vô thời hạn chỉ để hỗ trợ đồng bộ.

## 11. Xung đột ghi và hợp nhất dữ liệu

Eventual consistency có thể phát sinh **nhiều ghi đồng thời** khi nhiều bản sao chấp nhận cập nhật. Nếu chỉ có một nguồn ghi tuần tự hóa các lệnh, bài toán xung đột khác với hệ đa chủ ghi (multi-primary).

Các chiến lược:

| Chiến lược | Mô tả | Nguy cơ |
|---|---|---|
| Single writer/leader | Mọi thay đổi cho cùng key đi qua nơi điều phối | Giới hạn khả dụng hoặc độ trễ khi leader lỗi |
| Optimistic concurrency | Ghi chỉ thành công nếu version đọc trước vẫn đúng | Client phải xử lý conflict/retry |
| Last-write-wins | Một cập nhật “mới hơn” thắng theo timestamp/phiên bản được chọn | Có thể mất thay đổi hợp lệ; timestamp lệch |
| Merge theo quy tắc miền | Kết hợp dựa trên ngữ nghĩa nghiệp vụ | Cần xác định tính kết hợp/giao hoán và xử lý trường hợp khó |
| CRDT | Kiểu dữ liệu với phép hợp nhất đảm bảo hội tụ dưới giả định phù hợp | Không phù hợp mọi bất biến; cấu trúc và metadata có chi phí |
| Điều phối thủ công | Con người hoặc quy trình đối soát chọn kết quả | Trễ, chi phí vận hành, cần nhật ký kiểm toán |

**Ví dụ:** Số lượt “like” có thể phù hợp kiểu bộ đếm hỗ trợ gộp. Nhưng số vé còn lại là bất biến *không được bán quá số lượng*; không thể cứ cộng/gộp mọi cập nhật rồi tin rằng eventual consistency tự bảo toàn giới hạn. Nếu cho nhiều vùng tự cấp vé khi mất mạng, cần phân bổ quota/quyền trước và quy tắc thu hồi/điều hòa.

Với optimistic concurrency, có thể hình dung:

~~~sql
UPDATE inventory
SET available = available - 1,
    version = version + 1
WHERE sku = :sku
  AND available >= 1
  AND version = :expected_version;
~~~

Nếu số dòng cập nhật bằng 0, thao tác **chưa được xác nhận**: phải đọc lại và quyết định retry, báo hết hàng, hoặc trả kết quả có điều kiện. Đây là bảo vệ bất biến tại nguồn được phép quyết định, dù các read model khác còn trễ.

## 12. Nhất quán giao dịch và nhất quán giữa service

### 12.1. Isolation levels không phải replication consistency levels

Trong một database, các mức isolation quen thuộc gồm:
- **Read committed:** Tránh đọc dữ liệu chưa commit; không tự bảo đảm lặp lại cùng truy vấn sẽ thấy cùng giá trị.
- **Repeatable read:** Tùy hệ quản trị, giúp lặp lại đọc theo snapshot/khóa; hành vi phantom và write skew khác nhau giữa sản phẩm.
- **Serializable:** Các transaction đồng thời có kết quả tương đương một thứ tự thực thi tuần tự hợp lệ; có thể yêu cầu retry khi phát hiện xung đột.

Những mức trên nói về **giao dịch đồng thời**. Một request đọc từ replica cách primary vài giây không trở thành “serializable mới nhất” chỉ vì cơ sở dữ liệu nền có transaction serializable. Phải xác định đường đọc và thời điểm commit.

### 12.2. Nhất quán mạnh trong một ranh giới, eventual qua ranh giới

Một chiến lược phổ biến là:
1. Đặt các bất biến cần nguyên tử trong **một ranh giới sở hữu** nếu hợp lý.
2. Giải quyết lệnh tại nguồn chuẩn bằng transaction cục bộ, điều kiện cập nhật và khóa/phiên bản phù hợp.
3. Phát kết quả cho các service khác qua hợp đồng có thể thử lại.
4. Cho phép read model hoặc tác vụ không quan trọng hội tụ theo thời gian.
5. Thể hiện trạng thái chưa hoàn thành cho người dùng thay vì che giấu.

Ví dụ giữ chỗ tồn kho cần quyết định nguyên tử ở Inventory; bảng tổng hợp “Đơn đang được chuẩn bị” có thể cập nhật sau qua sự kiện. **Strong tại điểm ra quyết định** và **eventual ở màn hình tổng hợp** hoàn toàn có thể tồn tại cùng lúc.

### 12.3. Saga không phải transaction ACID xuyên hệ thống

Saga điều phối một chuỗi transaction cục bộ, có hoạt động bù trừ (compensation) khi cần. Bù trừ **không nhất thiết đảo ngược hoàn hảo** một tác động đã xảy ra. Một email đã gửi không thể thu hồi khỏi hộp thư; giao dịch chuyển tiền có thể yêu cầu nghiệp vụ hoàn tiền riêng; một chỗ đã đặt giữ có thể không còn trống khi thực hiện bù trừ.

Khi thiết kế saga, cần xác định:
- Trạng thái trung gian, timeout, điều kiện hoàn tất.
- Idempotency cho từng bước và từng thao tác bù trừ.
- Retry có điểm dừng, dead-letter queue, báo động và con đường xử lý thủ công.
- Điều kiện thất bại tạm thời so với thất bại nghiệp vụ cuối cùng.
- Cách chống tác động đến trễ làm đảo ngược trạng thái đã quyết định.

Một saga có thể hỗ trợ tính đúng đắn cuối cùng của **quy trình**, nhưng không biến mọi dữ liệu xuyên service thành một transaction nguyên tử.

## 13. Trải nghiệm người dùng khi dữ liệu chưa hội tụ

### 13.1. Đặt tên trạng thái chính xác

Thay vì trả ngay “Thành công” cho toàn bộ quy trình, hệ thống có thể phân biệt:
- **Đã nhận yêu cầu:** Request hợp lệ, hệ thống đã lưu bền vững đủ để xử lý tiếp.
- **Đang xử lý:** Một hoặc nhiều bước ngoài ranh giới cục bộ đang chờ.
- **Đã xác nhận:** Những bất biến cần thiết để cam kết nghiệp vụ đã hoàn tất.
- **Không thực hiện được / cần xử lý:** Quy trình thất bại, cần bù trừ hoặc đối soát.

Ví dụ API tạo đơn:

~~~http
POST /orders
Idempotency-Key: order-client-8f2c

HTTP/1.1 202 Accepted
Location: /orders/ord-123

{
  "orderId": "ord-123",
  "status": "PENDING_RESERVATION",
  "statusUrl": "/orders/ord-123"
}
~~~

Đây là ví dụ hợp đồng có thể chọn, không bắt buộc mọi hệ dùng HTTP 202. Nếu tại thời điểm trả phản hồi hệ thống đã hoàn tất cam kết cục bộ/hiệu lực nghiệp vụ như hợp đồng định nghĩa, một mã 201/200 cũng có thể phù hợp. Điều quan trọng là không đánh đồng “đã nhận” với “đã hoàn tất”.

### 13.2. Read-your-writes ở giao diện

Khi vừa sửa địa chỉ giao hàng, client thường mong thấy dữ liệu vừa sửa. Các cách:
1. API ghi trả lại giá trị và version đã commit; UI tạm thời hiển thị kết quả đó.
2. Lần đọc ngay sau ghi đi tới nguồn chuẩn hoặc replica có version tối thiểu.
3. Client gửi token phiên/causal token đến dịch vụ đọc.
4. Nếu read model chưa kịp, hiển thị “Đang đồng bộ” và thăm dò lại với timeout.

**Cẩn trọng với optimistic UI:** Không hiển thị “đã thanh toán” khi mới chỉ yêu cầu chuyển tiền. Với thao tác có tác động tài chính, trạng thái phải dựa trên xác nhận đáng tin cậy từ nguồn có thẩm quyền; UI có thể báo “đang xác minh kết quả”.

### 13.3. Không để một trang “giật lùi” thời gian

Nếu load đầu tiên thấy đơn là SHIPPED, lần load thứ hai từ một replica cũ lại trả PACKING, UI bị lùi trạng thái. Có thể giữ **version mới nhất đã thấy trong phiên**, yêu cầu đọc version tối thiểu hoặc hiển thị trạng thái đã biết kèm ghi chú đang đồng bộ.

Không sử dụng so sánh thứ tự chuỗi trạng thái đơn giản cho state machine có các nhánh độc lập, hoàn tiền hoặc sửa lỗi. Cần **version có trật tự** hoặc quy tắc chuyển trạng thái được định nghĩa trên cùng aggregate.

## 14. Đo lường và vận hành eventual consistency

Một hệ thống eventual consistency mà không biết mình đang trễ bao lâu rất khó vận hành. Nên đo tách biệt các giai đoạn:

    DB commit
       -> outbox ready
       -> broker accepted
       -> consumer received
       -> projection committed
       -> query sees version

Các chỉ số hữu ích:
- **Outbox backlog/age:** Số sự kiện chờ phát và tuổi sự kiện lâu nhất.
- **Broker consumer lag:** Độ trễ vị trí/offset hoặc thời gian theo nguồn đo phù hợp.
- **End-to-end propagation delay:** Thời gian từ lúc commit nguồn đến lúc projection áp dụng thành công.
- **Version gap:** Chênh lệch phiên bản đã áp dụng và phiên bản nguồn ở phạm vi có thể quan sát.
- **Retry, duplicate, poison event, DLQ:** Lượng sự kiện thử lại, xử lý trùng hoặc phải can thiệp.
- **Reconciliation mismatch:** Số lượng bản chiếu sai nguồn và thời gian khôi phục.
- **Read-your-writes violation:** Số phiên nhận lại phiên bản cũ sau khi ghi thành công.
- **Business impact:** Đơn bị treo, giữ chỗ quá hạn, số tiền phải đối soát, sự cố hiển thị sai.

### Một ví dụ hợp đồng đo lường

Với lịch sử đơn hàng:
- Mục tiêu vận hành (ví dụ) p99 propagation lag dưới **3 giây**.
- Khi lag vượt **10 giây**, cảnh báo hệ thống và hiển thị dấu hiệu dữ liệu đang cập nhật.
- Khi lag quá lớn hoặc chưa đo được, không dùng projection để quyết định hoàn tiền hoặc xuất kho.
- Có thể tái xây dựng projection từ nguồn xác thực hoặc sự kiện lưu trữ được kiểm soát.

Đây là **ngưỡng minh họa**, không phải thời gian phổ quát. Mục tiêu p99 cũng không đồng nghĩa với giới hạn cứng cho mọi lần cập nhật. Nếu nghiệp vụ đòi giới hạn cứng, giải pháp phải cưỡng chế hoặc từ chối thao tác khi không bảo đảm.

### Sự kiện lỗi, DLQ và đối soát

Dead-letter queue giúp không để một message lỗi chặn vĩnh viễn toàn bộ luồng. Tuy nhiên, “đã chuyển vào DLQ” **chưa phải là hội tụ thành công**. Cần người sở hữu, thời hạn xử lý, khả năng sửa/replay an toàn và kiểm soát thứ tự.

Đối soát có thể thực hiện định kỳ bằng so sánh version, tổng hợp theo khóa hoặc kiểm tra nghiệp vụ tại nguồn. Quy trình sửa chữa phải idempotent và có nhật ký kiểm toán; không nên coi xóa toàn bộ projection và tạo lại là cách duy nhất nếu khối lượng dữ liệu lớn hoặc có yêu cầu sẵn sàng cao.

## 15. Thử nghiệm sự cố để chứng minh bảo đảm

Không nên chỉ kiểm thử “gửi event xong và có dữ liệu”. Thiết kế tình huống lỗi:

| Tình huống | Cần quan sát | Kết quả mong muốn |
|---|---|---|
| Publisher chết sau commit, trước publish | Outbox còn dữ liệu không? | Event được phát lại khi phục hồi |
| Publisher chết sau broker ACK, trước đánh dấu outbox | Có bản sao event không? | Consumer chịu trùng an toàn |
| Consumer chết sau cập nhật projection, trước ACK | Có apply lại không? | Trạng thái không tăng hiệu ứng hai lần |
| Event version 8 đến trước version 7 | Có lùi trạng thái hoặc mất delta không? | Version guard/replay theo ngữ nghĩa |
| Một replica hoặc cache chậm | Client vừa ghi có thấy dữ liệu cũ? | Hành vi đúng cam kết phiên |
| Broker bị ngắt trong 2 phút | Backlog, retry, SLO hiển thị ra sao? | Hệ thống suy giảm có kiểm soát và hội tụ sau khôi phục |
| Giao dịch thanh toán trả timeout | Có vô tình gọi thu tiền lại? | Truy vấn/đối soát bằng idempotency key |
| Bản chiếu mất một khoảng dữ liệu | Có rebuild/reconcile được không? | Phục hồi nhất quán với nguồn |

Thực hiện trên môi trường thử nghiệm phù hợp hoặc qua fault injection có kiểm soát. Tránh thử nghiệm làm mất dữ liệu hoặc ảnh hưởng thanh toán thật trong sản xuất nếu không có kế hoạch vận hành được phê duyệt.

## 16. Các sai lầm phổ biến

**“Eventual consistency nghĩa là không quan tâm dữ liệu chính xác.”** Không đúng. Nó cho phép một số góc nhìn trễ; các bất biến quan trọng vẫn cần được bảo vệ tại nơi ra quyết định.

**“Sau 5 giây mọi replica chắc chắn giống nhau.”** Chỉ đúng nếu đó là cam kết được giao thức hoặc vận hành kiểm soát. Eventual consistency cơ bản không có giới hạn thời gian mặc định.

**“Sự kiện được broker nhận thì nghiệp vụ đã hoàn tất.”** Broker ACK không đồng nghĩa consumer đã áp dụng hoặc khách hàng đã nhận email.

**“Sử dụng Kafka/queue là có exactly-once trên mọi hệ thống.”** Một nền tảng có thể có bảo đảm xử lý cụ thể bên trong phạm vi giao dịch của nó; cơ sở dữ liệu ngoài, webhook và nhà cung cấp thanh toán vẫn cần idempotency/đối soát.

**“Đảm bảo thứ tự toàn cục là miễn phí.”** Thứ tự thường chỉ có hiệu lực trong một khóa/partition hoặc nhóm giao dịch; tăng phối hợp toàn cục có chi phí latency và throughput.

**“Cứ dùng timestamp lớn nhất là đúng.”** LWW có thể làm mất cập nhật hợp lệ, đặc biệt khi đồng hồ khác nhau hoặc nghiệp vụ có thao tác không giao hoán.

**“Đọc từ primary thì mọi màn hình luôn nhất quán.”** Trang có thể còn cache, read model, dữ liệu tổng hợp hoặc quy trình nhiều service chưa hoàn tất.

**“Nếu dùng eventual consistency thì không cần transaction.”** Transaction cục bộ, conditional update, unique constraint và state machine thường càng quan trọng để bảo vệ điểm ra quyết định.

**“Một service riêng nghĩa là một consistency model riêng cho mọi dữ liệu.”** Một service có thể đưa ra API đọc mạnh cho lệnh quyết định và endpoint đọc bản chiếu trễ; hợp đồng phải nêu rõ.

**“Có retry là sẽ xử lý đúng.”** Retry không kiểm soát có thể tạo trùng thanh toán, làm quá tải hệ phụ thuộc, thay đổi thứ tự hoặc kéo dài vô hạn. Mọi retry cần chính sách, nhận diện trùng và điểm dừng.

## 17. Quy trình ra quyết định cho một luồng nghiệp vụ cụ thể

### Bước 1 — Liệt kê thao tác và dữ liệu

Ví dụ “đặt hàng” gồm: tạo yêu cầu, giữ chỗ tồn kho, tính tiền, xác nhận thanh toán, phát hành đơn, gửi thông báo, cập nhật dashboard. Ghi rõ dữ liệu nào là nguồn sự thật và ai có quyền thay đổi.

### Bước 2 — Viết bất biến bằng câu có thể kiểm thử

Thay vì “tồn kho phải nhất quán”, viết: “Với mỗi SKU, tổng số lượng đã bán và đã giữ chỗ có hiệu lực không vượt quá số lượng được phép phân bổ, trừ khi nghiệp vụ chấp nhận bán vượt theo chính sách xác định”. Với thanh toán: “Mỗi yêu cầu nghiệp vụ có một định danh idempotency; thử lại cùng định danh không tạo thêm khoản thu tương đương”.

### Bước 3 — Xác định giới hạn chấp nhận quan sát cũ

Hỏi trực tiếp:
- Ai đang đọc dữ liệu, ở thời điểm nào, để hiển thị hay **để quyết định**?
- Nếu người dùng thấy dữ liệu cũ trong 1 giây, 10 giây hay 1 phút thì hậu quả gì?
- Có yêu cầu read-your-writes hoặc monotonic reads trong phiên không?
- Khi nguồn chuẩn không truy cập được, nên từ chối giao dịch hay tạm chấp nhận yêu cầu?

### Bước 4 — Chọn cơ chế nhỏ nhất đáp ứng yêu cầu

Với bất biến cứng: transaction, conditional write, optimistic locking, leader/quorum hoặc một authority cụ thể tùy bài toán. Với hiển thị chấp nhận trễ: cache/replica/read model, sự kiện và giao diện trạng thái. Với nhiều bước nghiệp vụ: state machine và phối hợp/bù trừ có khả năng khôi phục.

Đừng áp dụng cơ chế đắt nhất cho toàn bộ luồng chỉ vì một thao tác cần bảo đảm mạnh.

### Bước 5 — Xác định hợp đồng và cửa sổ bất đồng bộ

Ghi rõ:
- Một lệnh được coi là chấp nhận hoặc hoàn tất ở bước nào?
- Sự kiện được nhận ít nhất một lần hay có bảo đảm nào khác?
- Consumer xử lý trùng, sai thứ tự và version cũ ra sao?
- Một bản chiếu được phép trễ đến mức nào theo SLO?
- Khi không đáp ứng SLO, API và giao diện hiển thị gì?

### Bước 6 — Thử nghiệm và đo sau triển khai

Chạy thử sự cố, đối soát dữ liệu, đo lag p95/p99 và theo dõi số lần vi phạm bảo đảm theo phiên. Cập nhật lựa chọn khi chi phí hoặc ràng buộc nghiệp vụ thay đổi. Không đánh đồng “triển khai chạy được” với “đã chứng minh đúng mức nhất quán đã hứa”.

## 18. Mẫu quyết định kiến trúc (ADR)

~~~text
ADR: Mức nhất quán cho <dữ liệu/luồng>
Ngày / người sở hữu:
Nguồn sự thật:
Các bên ghi và các bên đọc:
Bất biến không được vi phạm:
Những trường hợp cho phép đọc cũ:
Bảo đảm theo thời gian thực hoặc theo phiên:
Giới hạn độ trễ / SLO và cách đo:
Hành vi khi mạng chia cắt hoặc service đích lỗi:
Cơ chế: transaction, quorum, outbox, event, projection, cache...
Idempotency, version, ordering và conflict resolution:
Trạng thái trung gian, timeout và bù trừ:
Cảnh báo, DLQ, đối soát và thủ tục phục hồi:
Các phương án đã cân nhắc:
Rủi ro và chi phí:
Phép thử chấp nhận:
Tín hiệu đánh giá lại:
~~~

**Ví dụ quyết định có phạm vi:** “Trang tìm kiếm sản phẩm đọc từ index cập nhật bất đồng bộ với SLO p99 trễ dưới 5 giây. Giá và số lượng tồn tại màn hình tìm kiếm chỉ để tham khảo; lệnh đặt hàng sẽ xác minh lại tại nguồn chuẩn. Khi index lag vượt ngưỡng, trang hiển thị trạng thái dữ liệu đang cập nhật. Không dùng index để duyệt thanh toán hoặc giữ chỗ tồn kho.” Những con số chỉ là giả định minh họa.

## 19. Bài thực hành: ứng dụng bán vé

Một nền tảng bán vé có 500 chỗ cho sự kiện và ba thành phần:
- **Reservation** nhận yêu cầu giữ chỗ.
- **Payment** thực hiện thanh toán qua nhà cung cấp.
- **TicketView** xây dựng màn hình “Vé của tôi” từ sự kiện.

Giả định 2.000 người truy cập cùng lúc; projection có thể trễ 4 giây; một message được giao trùng sau khi consumer restart; một sự kiện “ReservationExpired” đến sau “PaymentSucceeded”; và trang chi tiết vé có cache 10 giây.

**Yêu cầu:**
1. Chỉ ra nguồn sự thật và bất biến khi cấp chỗ. Vì sao không thể dựa trên số chỗ còn lại từ TicketView?
2. Nêu mức nhất quán cần ở thao tác **giữ chỗ**, mức chấp nhận được cho **danh sách vé**, và bảo đảm phiên nên có sau khi thanh toán.
3. Thiết kế state machine tối thiểu cho PENDING, RESERVED, PAID, EXPIRED, FAILED. Nêu điều kiện chuyển để sự kiện cũ không đảo ngược trạng thái đã xác nhận.
4. Đề xuất event ID, version theo reservation và idempotency key ở bên Payment. Mô tả xử lý khi message trùng.
5. Nêu ít nhất hai metric để biết TicketView đang hội tụ đúng và đúng SLO.
6. Giải thích hệ thống sẽ làm gì khi xảy ra network partition: từ chối cấp vé mới, tiếp nhận yêu cầu chờ, hay cho phép tạm giữ theo quota được phân bổ?

### Gợi ý đối chiếu

Một cách tiếp cận phù hợp là giữ chỗ tại Reservation bằng transaction/conditional update để không vượt giới hạn cấp chỗ; Payment bảo vệ thao tác thu tiền bằng định danh idempotency và đối soát; TicketView là projection eventual, có thể trễ nhưng phải xử lý version và trùng lặp. Sau khi thanh toán, giao diện có thể dùng trạng thái trả từ nguồn có thẩm quyền hoặc token phiên để tránh hiển thị lùi. Sự kiện hết hạn đến trễ không được xóa một vé PAID khi quy tắc nghiệp vụ đã xác nhận thanh toán có hiệu lực. Nếu yêu cầu không thể bảo đảm cấp chỗ trong partition, hệ thống cần trả trạng thái chưa xác nhận hoặc từ chối cam kết, theo chính sách đã công bố.

## 20. Ghi nhớ

1. **Nhất quán là một hợp đồng quan sát**: Ai đọc gì, sau ghi nào, trong phạm vi và thời gian nào?
2. **Bất biến nghiệp vụ quyết định mức bảo đảm tại điểm ra quyết định**; read model hiển thị có thể nhận bản sao trễ.
3. **Eventual consistency cho phép hội tụ theo thời gian**, không tự tạo cam kết vài giây, không tự sửa mất sự kiện hay xung đột sai.
4. **Outbox, idempotency, version, retry có kiểm soát, state machine và đối soát** là các công cụ thực hành để xử lý nhiều transaction cục bộ.
5. **Bảo đảm theo phiên** như read-your-writes và monotonic reads ảnh hưởng trực tiếp đến trải nghiệm người dùng.
6. **CAP/PACELC là khung đánh đổi theo điều kiện**, không phải nhãn để gán cứng toàn bộ microservices.
7. **Đo lag, thử lỗi và diễn đạt trạng thái trung gian** là một phần của thiết kế nhất quán, không chỉ là việc vận hành về sau.

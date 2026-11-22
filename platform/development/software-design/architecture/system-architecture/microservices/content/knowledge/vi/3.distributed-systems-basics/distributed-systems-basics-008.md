# Đánh đổi giữa độ trễ và nhất quán khi hệ thống hoạt động bình thường

## Mục tiêu bài học

Trong hệ thống phân tán, dữ liệu thường tồn tại ở nhiều bản sao (replica), nhiều tiến trình hoặc nhiều vùng triển khai. Ngay cả khi **không có sự cố chia cắt mạng**, các bản sao vẫn cần thời gian truyền và xử lý thông tin. Vì vậy, một yêu cầu cần phản hồi nhanh có thể phải chấp nhận đọc dữ liệu chưa mới nhất, còn một yêu cầu cần nhìn thấy dữ liệu mới nhất có thể phải chờ trao đổi giữa các nút.

Đây là chủ đề **Latency versus Consistency trong điều kiện hoạt động bình thường** — phần “Else” trong cách nhìn **PACELC**. Nó trả lời câu hỏi thực tế: **Khi mọi thành phần vẫn kết nối được với nhau, hệ thống ưu tiên trả lời sớm hay ưu tiên mức nhất quán cao hơn?**

Sau bài này, người học có thể:

- Giải thích vì sao độ trễ và mức nhất quán có thể đánh đổi khi các replica hoạt động bình thường.
- Phân biệt tình huống có network partition trong CAP với tình huống không có partition trong PACELC.
- Phân biệt strong consistency, eventual consistency, bounded staleness và các bảo đảm nhất quán theo phiên.
- Phân tích tác động của đọc tại replica, ghi đồng bộ, ghi bất đồng bộ, quorum và vị trí địa lý đến độ trễ.
- Chọn chính sách nhất quán phù hợp theo từng luồng nghiệp vụ và biết cách đo lường kết quả.

## 1. Bối cảnh: Vì sao “bình thường” vẫn có độ trễ?

Giả sử một ứng dụng có hai bản sao dữ liệu:

- Replica A ở gần người dùng, trả lời truy vấn nhanh.
- Replica B nhận cập nhật từ A qua mạng và phục vụ người dùng ở khu vực khác.

Tại thời điểm t0, cả A và B đều chứa phiên bản hồ sơ người dùng v7. Tại t1, người dùng cập nhật tên trên A; A ghi nhận v8. Việc chuyển v8 sang B mất một khoảng thời gian. Tại t2, một yêu cầu đọc được chuyển tới B khi B vẫn ở v7.

~~~text
Thời gian →
Người dùng              Replica A                 Replica B
    |                       |                         |
    | -- đổi tên = v8 ----> |                         |
    |                       | -- gửi cập nhật v8 ---> |
    | <--- ghi thành công -- |                         |
    |                       |                         |
    | -------- đọc tại B ---------------------------> |
    | <-------------------------- trả về v7 ---------- |
    |                       |                    nhận v8
~~~

Trong ví dụ, **không có đứt mạng**. Chỉ có sự khác biệt giữa thời điểm bản sao A ghi nhận thay đổi và thời điểm B áp dụng thay đổi. Yêu cầu đọc tại B có thể trả lời rất nhanh nhưng nhìn thấy dữ liệu cũ.

Nếu hệ thống yêu cầu đọc thấy v8 ngay sau khi ghi, nó có thể phải chuyển đọc về nút nắm trạng thái mới nhất, đợi B đồng bộ, hoặc thực hiện một giao thức phối hợp khác. Các bước này làm tăng độ trễ và phụ thuộc vào điều kiện mạng.

Lưu ý: độ trễ và mức cũ của dữ liệu là hai đại lượng khác nhau:

- **Latency:** thời gian một yêu cầu mất từ lúc gửi tới lúc có phản hồi, thường đo bằng mili giây.
- **Staleness:** mức độ dữ liệu trả về chậm hơn phiên bản hoặc thời điểm cập nhật mới nhất; có thể biểu diễn theo thời gian, phiên bản hay sequence.
- **Consistency guarantee:** quy tắc chính xác về những kết quả đọc/ghi mà hệ thống cam kết cho phép.

Một truy vấn 5 ms không tự động là truy vấn “tốt” nếu dữ liệu trả về vi phạm quy tắc nghiệp vụ. Một truy vấn 150 ms cũng không tự động là “tốt” chỉ vì nó đợi thêm: phải biết nó đợi để bảo đảm điều gì.

## 2. CAP và PACELC: Hai tình huống khác nhau

### 2.1. CAP tập trung vào trường hợp có chia cắt mạng

Định lý CAP mô tả giới hạn khi một hệ thống phân tán gặp **network partition**: các nhóm nút không thể liên lạc đáng tin cậy với nhau. Trong điều kiện đó, hệ thống không thể đồng thời bảo đảm đầy đủ:

- **Consistency theo nghĩa CAP:** thường gắn với linearizability — thao tác có thể được quan sát như xảy ra theo một thứ tự đơn nhất, tôn trọng thứ tự thời gian thực.
- **Availability theo nghĩa CAP:** các yêu cầu đến nút không lỗi đều được phản hồi theo yêu cầu của định nghĩa, ngay cả trong partition.

“Availability” trong CAP có nghĩa kỹ thuật cụ thể; không đồng nghĩa đơn giản với số “chín” trong SLA uptime. Trong một phân vùng mạng thực tế, thiết kế có thể phải từ chối/chờ một số thao tác để không trả kết quả mâu thuẫn, hoặc tiếp tục nhận thao tác ở nhiều phía và xử lý xung đột về sau.

Tuy nhiên, **CAP không nói rằng cứ không mất mạng thì tính nhất quán và độ trễ không còn liên quan**.

### 2.2. PACELC bổ sung lựa chọn khi không có partition

PACELC là một cách mô tả thiết kế hệ thống phân tán theo hai nhánh:

~~~text
               Có network partition (P)?
                       /             \
                     Có              Không (Else)
                     |                    |
              Chọn ưu tiên          Chọn ưu tiên
             Availability (A)      Latency (L)
                  hoặc                hoặc
             Consistency (C)      Consistency (C)
~~~

Có thể nhớ thành: **P → A/C; Else → L/C**.

Trong nhánh **Else**, hệ thống vẫn hoạt động, nhưng muốn một thao tác quan sát được trạng thái nhất quán giữa nhiều nút thì thường phải trả chi phí phối hợp qua mạng. Nếu ưu tiên phản hồi gần người dùng và giảm số vòng giao tiếp, hệ thống có thể phải chấp nhận dữ liệu cũ hoặc một số thứ tự quan sát không đồng bộ.

PACELC là **mô hình giải thích đánh đổi**, không phải một định lý quy định mọi thao tác đều buộc chọn một trong hai cực. Nếu dữ liệu chỉ nằm trên một nút, yêu cầu được xử lý cục bộ, hoặc mạng rất nhanh, một thao tác có thể vừa có độ trễ thấp vừa có bảo đảm mạnh. Mức đánh đổi phụ thuộc cách phân bố dữ liệu, yêu cầu nhất quán, thuật toán, khoảng cách và tải.

### 2.3. Bảng so sánh nhanh

| Tiêu chí | CAP khi partition | PACELC khi hoạt động bình thường |
| --- | --- | --- |
| Điều kiện | Có nhóm nút mất khả năng liên lạc | Các nút vẫn liên lạc được |
| Trọng tâm | Có tiếp tục đáp ứng yêu cầu hay bảo vệ tính nhất quán? | Trả lời nhanh hay chờ phối hợp để có bảo đảm nhất quán mạnh hơn? |
| Tác động thường gặp | Một số yêu cầu bị từ chối/chờ, hoặc phát sinh phiên bản xung đột | Tăng RTT, tail latency, hoặc đọc giá trị còn cũ |
| Câu hỏi thiết kế | Làm gì khi phân vùng xảy ra? | Khi mạng bình thường, thao tác nào cần phản hồi gần nhất và thao tác nào cần xác nhận toàn cục? |

Bài này tập trung vào nhánh **Else**. Không nên dùng CAP như lý do duy nhất để chọn chính sách đọc/ghi trong ngày thường.

## 3. Hiểu đúng các mức nhất quán dữ liệu

Trong thực hành, “strong” và “eventual” là hai đầu của nhiều bảo đảm khác nhau. Để ra quyết định, phải chỉ rõ **đối tượng, thao tác và thứ tự quan sát** đang được bảo đảm.

### 3.1. Linearizability (nhất quán mạnh theo thời gian thực)

Một thao tác đọc/ghi trên một đối tượng được xem như có một thời điểm có hiệu lực duy nhất nằm giữa lúc bắt đầu và lúc kết thúc thao tác. Nếu ghi v8 đã **hoàn tất** trước khi một đọc mới bắt đầu, đọc đó không thể thấy v7 trong khi không có ghi khác hợp lệ thay đổi trạng thái.

Ví dụ: người dùng đổi địa chỉ nhận hàng, hệ thống xác nhận cập nhật hoàn tất, rồi người dùng xem lại địa chỉ. Với bảo đảm linearizable cho đối tượng đó, truy vấn mới phải thấy dữ liệu phù hợp với bản ghi đã hoàn tất.

Để đạt bảo đảm này với dữ liệu nhân bản, hệ thống thường cần giao thức xác định thứ tự ghi, giao tiếp tới leader, quorum/consensus hoặc cơ chế tương đương. Cơ chế cụ thể phụ thuộc cơ sở dữ liệu và cấu hình.

**Đừng đồng nhất linearizability với serializability.** Linearizability thường nói về thứ tự thời gian thực của các thao tác; serializability nói về tính tương đương với một lịch thực thi tuần tự của các transaction. Một hệ thống có thể bảo đảm một thuộc tính mà chưa bảo đảm thuộc tính còn lại cho mọi giao dịch.

### 3.2. Eventual consistency (nhất quán cuối cùng)

Nếu các cập nhật ngừng lại và hệ thống tiếp tục chuyển/áp dụng thay đổi thành công, các replica cuối cùng sẽ hội tụ về trạng thái thống nhất theo quy tắc của hệ thống. Trong khoảng thời gian trung gian, các replica có thể trả về giá trị khác nhau.

Ví dụ: sau khi người dùng thay ảnh đại diện, trang hồ sơ ở khu vực khác vẫn thấy ảnh cũ trong một thời gian.

**Eventual không có nghĩa “chắc chắn sau 2 giây”.** Muốn cam kết thời gian cũ tối đa cần cơ chế, giới hạn và điều kiện rõ ràng. Nếu replication bị backlog, retry hoặc xử lý xung đột chậm, độ trễ hội tụ có thể dài hơn dự kiến.

### 3.3. Bounded staleness (dữ liệu cũ có giới hạn)

Một số hệ thống có thể bảo đảm dữ liệu đọc chỉ chậm tối đa một khoảng thời gian hoặc số phiên bản nhất định, trong các điều kiện được công bố. Chẳng hạn một truy vấn chấp nhận dữ liệu chậm tối đa 5 giây; nếu bản sao chưa đạt, nó phải đợi, chuyển sang nguồn khác hoặc báo lỗi theo chính sách.

Bounded staleness nằm giữa hai cực đối với nhiều workload: cho phép trả lời nhanh bằng replica gần người dùng nhưng vẫn đặt giới hạn cụ thể cho độ cũ của kết quả.

Giới hạn này phải được **hệ thống thực thi và đo được**; chỉ cấu hình cache TTL=5 giây không tự chứng minh mọi dữ liệu luôn cũ tối đa 5 giây, vì còn thời điểm tải, đồng bộ và nguồn dữ liệu.

### 3.4. Bảo đảm theo phiên: read-your-writes và monotonic reads

Khi không cần toàn bộ hệ thống nhìn thấy cập nhật mới nhất cùng lúc, trải nghiệm người dùng vẫn có thể cần các bảo đảm cục bộ.

- **Read-your-writes:** một phiên sau khi ghi thành công có thể nhìn thấy ít nhất chính thay đổi đã ghi.
- **Monotonic reads:** một phiên đã thấy phiên bản v8 thì những lần đọc tiếp theo không bị quay ngược về v7.
- **Monotonic writes:** các ghi của cùng một thực thể/phiên được áp dụng theo thứ tự phù hợp.
- **Causal consistency:** các thao tác có quan hệ nguyên nhân-kết quả được quan sát theo thứ tự nhân quả.

Ví dụ, hệ thống có thể cho hầu hết người dùng đọc bản sao gần nhất, nhưng sau khi người A vừa cập nhật hồ sơ, tạm định tuyến các lượt đọc của A tới nguồn đã nhận bản ghi của A. Cách này có thể cải thiện read-your-writes mà chưa cần mọi yêu cầu đọc toàn cầu phải tuyến về một nơi.

Đây là **bảo đảm của kiến trúc và giao thức**, không tự xuất hiện chỉ nhờ bật sticky session trên load balancer.

### 3.5. Độ bền dữ liệu (durability) là thuộc tính khác

Một ghi được trả “thành công” sau khi một nút xử lý, sau khi nhiều nút chấp nhận, hay sau khi dữ liệu được ghi bền vững xuống đĩa là các chính sách khác nhau.

Độ bền, nhất quán, tính sẵn sàng và độ trễ có liên quan nhưng **không phải cùng một khái niệm**. Khi thiết kế API ghi, phải mô tả rõ ý nghĩa của “success”; số lượt xác nhận (ACK) không tự cho biết mức bền vững nếu chưa hiểu cách từng nút ghi nhật ký hoặc lưu trữ.

## 4. Độ trễ phát sinh từ đâu?

Thời gian phục vụ một yêu cầu có thể gồm:

~~~text
Client → Gateway → Service → Data node → Replica coordination → Data node → Service → Client
            |           |               |
          queue        xử lý          mạng + chờ ACK
~~~

Các yếu tố chính:

1. **Round-trip time (RTT):** thời gian truyền đi-về qua mạng. Khoảng cách địa lý và tuyến mạng giới hạn mức cải thiện khả thi.
2. **Số vòng giao tiếp:** một vòng tới leader khác với nhiều vòng trao đổi hoặc xác nhận từ các nút.
3. **Lập hàng và xử lý:** CPU, I/O, lock, transaction, queue và contention ảnh hưởng thời gian phản hồi.
4. **Quorum và nút chậm:** khi cần đủ số phản hồi, một nút chậm có thể làm tăng độ trễ hoặc phần đuôi của phân phối.
5. **Đọc lại để xác nhận phiên bản:** đọc trên replica đang chậm có thể phải chờ cập nhật, hỏi leader hoặc được chuyển tuyến.
6. **Phục vụ gần người dùng:** cache/replica gần giảm đường mạng nhưng có thể chỉ chứa một snapshot chưa mới nhất.

Nên xem **P50, P95, P99 latency**, không chỉ trung bình. Một kiến trúc có trung bình 20 ms nhưng P99 900 ms có thể gây trải nghiệm tệ hơn một kiến trúc ổn định 60–100 ms đối với luồng nhạy cảm.

### Ví dụ giả định về latency

Giả sử một yêu cầu tới replica gần có thời gian xử lý 8 ms. Liên lạc thêm một nút ở khu vực xa cần khoảng 70 ms RTT và một lượt xác nhận phụ. Khi đọc được phép dùng dữ liệu gần, ứng dụng có thể trả lời sau khoảng 8 ms. Khi bắt buộc xác minh trạng thái mới nhất qua nút xa, độ trễ có thể tăng đáng kể.

Các con số chỉ minh họa **cấu trúc chi phí**, không phải số liệu tốc độ mạng cố định hay cam kết của một sản phẩm database. Thời gian thực phụ thuộc topology, giao thức, tải và việc các bước có thể chạy song song.

## 5. Ba chiến lược nhân bản và đánh đổi phổ biến

### 5.1. Ghi đồng bộ qua nhiều bản sao

Một ghi được xem là hoàn tất theo chính sách khi các xác nhận bắt buộc từ replica hoặc quorum đã đến.

~~~text
Client          Leader                 Replica
  |                |                       |
  | -- write v8 -->|                       |
  |                | -- replicate v8 ----> |
  |                | <----- required ACK --|
  | <-- success ---|                       |
~~~

**Ưu điểm:** có thể giúp tạo nền cho bảo đảm về thứ tự và khả năng nhìn thấy ghi đã hoàn tất, tùy thuật toán. **Chi phí:** ghi thường phải chờ giao tiếp và một số nút đủ điều kiện; tail latency có thể tăng khi replica chậm.

Không phải mọi hệ thống “ghi đồng bộ” đều linearizable: cần xem cách chọn leader, xử lý đọc, epoch/term và bảo vệ trước bản sao lạc hậu.

### 5.2. Ghi bất đồng bộ sang bản sao

Leader trả kết quả sau khi đáp ứng chính sách xác nhận cục bộ; thông tin được chuyển tiếp sang replica phía sau.

~~~text
Client          Leader                 Replica
  |                |                       |
  | -- write v8 -->|                       |
  | <-- success ---|                       |
  |                | -- replicate v8 ----> |
  |                |                       | -- apply v8
~~~

**Ưu điểm:** đường phản hồi ghi không phải đợi nút xa, giúp giảm độ trễ trong điều kiện bình thường. **Chi phí:** sau khi ghi thành công, replica khác vẫn có thể trả v7. Rủi ro mất một số ghi khi failover còn phụ thuộc chính sách durability và vị trí ACK.

Đọc từ leader có thể trả trạng thái mới hơn so với đọc từ follower, nhưng bảo đảm cụ thể còn tùy database, isolation level và cách xử lý đồng thời.

### 5.3. Đọc từ replica gần nhất

Định tuyến đọc tới vị trí gần người dùng, nhất là dữ liệu ít thay đổi hoặc chịu được cũ trong thời gian ngắn.

Ưu điểm là giảm RTT và tải trên primary. Nhược điểm là cần xác định **staleness budget**, cách đọc sau khi ghi, cách cache bị vô hiệu, và cách trả lời khi bản sao quá chậm. Một replica nhanh không làm cho dữ liệu tự động mới nhất.

### 5.4. Quorum đọc/ghi

Với một mô hình quorum đơn giản gồm N replica:

- W là số replica tối thiểu cần phản hồi cho một ghi.
- R là số replica tối thiểu cần tham gia một lần đọc.

Điều kiện **R + W > N** làm cho tập replica đọc và tập replica ghi **có giao nhau**, nếu chúng lấy từ cùng một tập nút và bảo đảm quorum đúng như giả định.

Ví dụ N=3, W=2, R=2: bất kỳ tập 2 nút đọc và tập 2 nút ghi đều chia sẻ ít nhất một nút. Tuy vậy, **giao nhau chưa đủ để khẳng định linearizability**. Còn cần thuật toán chọn phiên bản, cách xử lý ghi đồng thời, phiên bản đã commit, thay đổi membership, quorum thực tế, hinted handoff và những cơ chế đặc thù của database.

Trade-off thường gặp:

| Cấu hình minh họa | Đường đọc | Đường ghi | Nhận xét |
| --- | --- | --- | --- |
| R=1, W=2, N=3 | Có thể đọc rất nhanh | Ghi chờ 2 phản hồi | Đọc một replica có thể gặp dữ liệu cũ |
| R=2, W=1, N=3 | Đọc chờ 2 phản hồi | Ghi có thể nhanh hơn | Tính mới nhất phụ thuộc cách đọc/chọn phiên bản |
| R=2, W=2, N=3 | Cả đọc và ghi cùng chờ nhiều nút | Cân bằng số bản sao tham gia | Có giao quorum nhưng vẫn cần giao thức đúng |
| R=3, W=3, N=3 | Đọc và ghi đợi tất cả | Có thể rất chậm khi nút lag | Không phải cứ đợi tất cả là tự động giải quyết mọi race |

Các cấu hình là **mô hình để suy luận**, không phải công thức cài đặt áp dụng nguyên xi cho mọi cơ sở dữ liệu.

## 6. Phân tích ba tình huống nghiệp vụ

### Tình huống A — Cập nhật hồ sơ và hiển thị ngay

**Yêu cầu:** người dùng đổi tên hiển thị, nhận thông báo thành công, rồi mở lại trang và mong thấy tên mới.

**Rủi ro:** cập nhật thành công trên primary nhưng request GET kế tiếp đến read replica đang lag; giao diện hiển thị tên cũ và người dùng tưởng thao tác thất bại.

**Lựa chọn thực dụng:** đảm bảo read-your-writes cho phiên vừa ghi. Có thể chọn một trong các thiết kế phù hợp với storage:

- Đọc từ primary sau khi ghi trong một khoảng phù hợp.
- Mang theo version/token của thao tác ghi và chỉ trả lời từ replica đã bắt kịp version đó.
- Chờ đồng bộ có timeout và fallback đọc primary.
- Cập nhật trạng thái ngay trên client nhưng vẫn đồng bộ và xác minh khi cần, tránh nhầm optimistic UI với cam kết đã ghi bền vững.

**Đánh đổi:** một số yêu cầu của người vừa sửa có độ trễ cao hơn; hầu hết request xem hồ sơ có thể tiếp tục dùng replica nhanh.

### Tình huống B — Chốt đơn hàng và kiểm soát tồn kho

**Yêu cầu:** không được xác nhận hai đơn sử dụng cùng một đơn vị tồn kho còn lại.

**Rủi ro:** hai request đồng thời cùng đọc tồn kho = 1 trên hai replica rồi đều kết luận “còn hàng”. Dữ liệu đọc cũ hoặc race ở bước ghi có thể vi phạm bất biến.

**Lựa chọn thực dụng:** quy tắc giữ tồn phải được bảo vệ **ở ranh giới quyết định ghi** bằng cơ chế có tính nguyên tử phù hợp: transaction có isolation đúng, conditional update, version compare-and-swap, khóa hợp lệ hoặc thiết kế reservation. Chỉ đọc có consistency mạnh nhưng sau đó cập nhật không nguyên tử cũng chưa đủ ngăn overselling.

Ví dụ pseudocode:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE sku = :sku
  AND available >= 1;
~~~

Chỉ xác nhận giữ tồn khi câu lệnh cập nhật nguyên tử đã thực sự ảnh hưởng đúng một bản ghi, cộng với việc xử lý transaction và idempotency phù hợp. Ví dụ trên minh họa cách ràng buộc bất biến ở thao tác ghi; cú pháp và cam kết atomicity phải đối chiếu với hệ quản trị thực tế.

**Đánh đổi:** bước chốt đơn có thể chậm hơn vì cần đi tới nguồn có thẩm quyền, chờ khóa hoặc đồng thuận. Tốc độ xem danh sách sản phẩm có thể được ưu tiên hơn bằng cache hoặc read replica; **không áp một chính sách duy nhất cho mọi endpoint**.

### Tình huống C — Dashboard phân tích và bộ đếm lượt xem

**Yêu cầu:** trang thống kê lượt xem, biểu đồ doanh số và các số liệu tổng hợp cập nhật tương đối nhanh; sai lệch vài giây có thể chấp nhận nếu được công bố.

**Rủi ro:** nếu yêu cầu mỗi lần mở dashboard đều phải thu thập trạng thái mới nhất từ mọi shard hoặc khu vực, độ trễ tăng mạnh và tạo thêm tải.

**Lựa chọn thực dụng:** cập nhật bất đồng bộ qua sự kiện/queue, tổng hợp theo cửa sổ thời gian, đặt cache TTL và hiển thị “cập nhật lúc …”. Cần xác định quy tắc xử lý sự kiện trùng, đến muộn, đảo thứ tự và khả năng tái tính toán.

**Đánh đổi:** giảm latency và chi phí trên đường đọc; người dùng chấp nhận số liệu trễ theo một cam kết phù hợp. Với báo cáo quyết toán hoặc nghĩa vụ pháp lý, có thể chọn một luồng đối soát chặt chẽ hơn.

## 7. Chọn chính sách theo thao tác, không chỉ theo hệ thống

Một ứng dụng thường có nhiều mức nhất quán cùng lúc. Ví dụ:

| Thao tác | Hệ quả nếu đọc dữ liệu cũ | Bảo đảm cần cân nhắc | Cách tiếp cận |
| --- | --- | --- | --- |
| Xem bài viết công khai | Hiển thị phiên bản trước trong thời gian ngắn | Eventual / bounded staleness | CDN/cache/replica gần |
| Sửa hồ sơ rồi xem lại | Người dùng không thấy sửa đổi của mình | Read-your-writes | Read primary hoặc version token |
| Kiểm tra quyền đã bị thu hồi | Người bị thu hồi vẫn được truy cập | Nhất quán mạnh hoặc cơ chế thu hồi có giới hạn nghiêm ngặt | Điểm quyết định quyền có thẩm quyền, cache có chính sách chặt |
| Giữ hàng còn lại | Bán vượt tồn | Atomic invariant khi ghi | Transaction/conditional write |
| Xem lượt xem, like | Con số có thể chậm cập nhật | Eventual | Aggregate async |
| Xác nhận thanh toán | Hiển thị đã trả tiền khi chưa có trạng thái chuẩn | Quy trình trạng thái và nguồn sự thật rõ | Xác minh trạng thái và idempotent processing |

Cần phân biệt **dữ liệu có thể cũ** với **quyết định có thể sai**. Một trang sản phẩm hiển thị “còn hàng” dựa vào cache có thể là thông tin tham khảo, nhưng bước đặt hàng phải xác nhận bằng cơ chế đáng tin cậy trước khi cam kết.

## 8. Giảm độ trễ mà vẫn giữ bảo đảm cần thiết

### 8.1. Đưa xử lý quan trọng đến gần dữ liệu có thẩm quyền

Nếu phần lớn các thao tác cần nhất quán trên cùng một miền, đặt compute và database gần nhau có thể giảm chi phí phối hợp. Tách replica chỉ đọc ở vùng khác cho các truy vấn có thể chịu stale.

Không phải cứ đặt nhiều bản sao gần người dùng là đồng thời cải thiện toàn bộ độ trễ đọc/ghi: nếu mọi ghi cần xác nhận xuyên vùng, người ghi vẫn phải chịu RTT liên vùng.

### 8.2. Phân cấp yêu cầu nhất quán theo endpoint

Ví dụ một contract API có thể ghi rõ:

~~~text
GET  /products/{id}          → có thể đọc cache/replica
GET  /me/profile             → read-your-writes trong phiên
POST /orders                 → bảo vệ bất biến đặt hàng
GET  /analytics/summary      → dữ liệu trễ tối đa theo SLO báo cáo
~~~

Định nghĩa mức nhất quán **trong hợp đồng sử dụng dữ liệu**, không chỉ trong mô tả kỹ thuật. Người dùng cần biết kết quả có thể chậm cập nhật hay chưa được xác nhận cuối cùng.

### 8.3. Phiên bản và token để biết replica đã bắt kịp chưa

Gắn version hoặc log sequence cho dữ liệu đã ghi. Nếu một yêu cầu cần ít nhất version v42, tầng đọc có thể:

1. Thử replica gần nhất.
2. Kiểm tra replica đã áp dụng ít nhất v42 chưa.
3. Nếu chưa, chờ tối đa theo ngân sách latency, chuyển tuyến tới nguồn mới hơn hoặc trả trạng thái theo chính sách.

Token chỉ hữu ích nếu backend kiểm tra được thứ tự phiên bản và bảo đảm áp dụng đúng. Tạo timestamp phía client rồi so sánh với đồng hồ trên các máy khác không đủ để chứng minh thứ tự cập nhật.

### 8.4. Caches và invalidation

Cache làm giảm chi phí đọc nhưng tạo thêm một mức độ cũ:

~~~text
Client → CDN / app cache → read replica → authoritative store
~~~

Mỗi lớp có chính sách TTL, invalidation, refresh và fallback. Với dữ liệu nhạy cảm như thu hồi quyền, cache phải có chiến lược phù hợp với mức rủi ro và cam kết về thời gian phản ánh thay đổi.

**Cache TTL** không phải một lời hứa toàn cục về staleness nếu dữ liệu nguồn vốn đã cũ hoặc có cơ chế làm mới không ổn định.

### 8.5. Tách đường đọc và ghi một cách có kiểm soát

Các hệ thống có thể dùng read model, materialized view hoặc CQRS để phục vụ truy vấn nhanh, còn lệnh thay đổi nghiệp vụ đi qua write model có thẩm quyền.

Điều này làm xuất hiện độ trễ cập nhật projection; cần xử lý retry, duplicate event, thứ tự cập nhật và quan sát projection lag. Không nên giả định “có event thì dữ liệu sẽ cập nhật tức thời”.

### 8.6. Batching, bất đồng bộ và giảm vòng mạng

Tối ưu số vòng request/response, dùng batching ở vị trí phù hợp và xử lý async cho công việc không cần hoàn tất trước khi trả kết quả. Điều quan trọng là không phát “success” theo nghĩa đã hoàn thành nghiệp vụ nếu thực tế mới chỉ nhận công việc vào hàng đợi.

Có thể phân biệt các trạng thái phản hồi:

~~~text
202 Accepted        Đã nhận yêu cầu để xử lý sau
PROCESSING          Đang thực hiện tác vụ bất đồng bộ
CONFIRMED           Điều kiện nghiệp vụ đã được kiểm chứng
FAILED              Tác vụ thất bại hoặc không thể xác nhận
~~~

Mã HTTP chỉ là một ví dụ cách biểu đạt; business status và API contract phải nhất quán với việc hệ thống đã xác nhận điều gì.

## 9. Ví dụ thiết kế với một dịch vụ Spring Boot

Giả sử hệ thống có primary database và một read replica. Một tầng dịch vụ có thể chọn nguồn đọc dựa trên loại thao tác:

~~~java
public interface CustomerReader {
    CustomerView findById(String customerId);
}

// Adapter đi đến nguồn có thẩm quyền cho yêu cầu cần dữ liệu mới.
public final class PrimaryCustomerReader implements CustomerReader {
    private final CustomerStore primary;

    public PrimaryCustomerReader(CustomerStore primary) {
        this.primary = primary;
    }

    @Override
    public CustomerView findById(String customerId) {
        return primary.load(customerId);
    }
}

// Adapter cho phép đọc bản sao gần hơn khi nghiệp vụ chấp nhận stale.
public final class ReplicaCustomerReader implements CustomerReader {
    private final CustomerStore replica;

    public ReplicaCustomerReader(CustomerStore replica) {
        this.replica = replica;
    }

    @Override
    public CustomerView findById(String customerId) {
        return replica.load(customerId);
    }
}

// Dịch vụ ứng dụng lựa chọn chính sách theo use case.
public final class CustomerQueryService {
    private final CustomerReader primaryReader;
    private final CustomerReader replicaReader;

    public CustomerQueryService(
            CustomerReader primaryReader,
            CustomerReader replicaReader) {
        this.primaryReader = primaryReader;
        this.replicaReader = replicaReader;
    }

    public CustomerView readForCurrentUser(String id) {
        return primaryReader.findById(id);
    }

    public CustomerView readPublicPreview(String id) {
        return replicaReader.findById(id);
    }
}
~~~

Ví dụ cho thấy **quyết định nhất quán thuộc về use case** và khả năng định tuyến dữ liệu thuộc adapter. Nó không chứng minh primary luôn linearizable cho mọi transaction: cần xác minh cấu hình database, isolation, transaction, failover và read routing. Với read-your-writes trên nhiều phiên bản triển khai, có thể cần thêm version token hoặc chính sách stickiness theo phiên; hai adapter trên mới chỉ là cấu trúc minh họa.

### Cách xây dựng contract cho một thao tác

Ví dụ mô tả một API đọc hồ sơ:

~~~text
Endpoint: GET /me/profile
Guarantee: Read-your-writes cho cập nhật hồ sơ đã trả CONFIRMED.
Latency target: p95 < 200 ms trong vùng triển khai mục tiêu.
Fallback: Khi replica chưa bắt kịp, dùng primary trong time budget.
Over budget: Trả lỗi/tín hiệu tạm thời theo API contract.
Observability: latency p95/p99, route primary/replica, replica lag.
~~~

Các ngưỡng ở đây là ví dụ để minh họa cách viết SLO; nhóm dự án phải tự chọn dựa trên nhu cầu thực và số liệu đo được.

## 10. Đo lường đánh đổi trong thực tế

Không thể đánh giá chính sách chỉ bằng thông số cấu hình. Cần đo đồng thời **latency** và **mức chính xác/độ mới của dữ liệu** ở các luồng tiêu biểu.

| Chỉ số | Câu hỏi được trả lời |
| --- | --- |
| Read latency P50/P95/P99 | Truy vấn nhanh ở mức trung bình và trong tình huống chậm ra sao? |
| Write ACK latency P95/P99 | Xác nhận ghi phải chờ bao lâu theo chính sách hiện có? |
| Replica lag theo thời gian/sequence | Replica thường và tối đa chậm sau nguồn bao nhiêu? |
| Tỷ lệ stale read | Bao nhiêu lượt đọc nhìn thấy phiên bản cũ theo tiêu chí kiểm tra? |
| Tỷ lệ read-your-writes violation | Có bao nhiêu lần phiên đọc không thấy chính thay đổi đã xác nhận? |
| Conflict/reconciliation count | Bao nhiêu cập nhật cần xử lý xung đột hoặc tái đồng bộ? |
| Timeout và retry rate | Chính sách chờ nhất quán có gây lỗi hoặc khuếch đại tải không? |
| Primary/replica traffic split | Đường đọc mới có thật sự giảm tải và RTT không? |
| Business invariant violations | Có xảy ra bán vượt tồn, xác nhận sai trạng thái hay cấp quyền sai không? |

Nếu database có công cụ đo native replication lag, sử dụng chỉ số đó cùng synthetic read/write probe. Một chỉ số “lag trung bình” có thể che giấu P99 lag cao; việc đo cần có phân phối theo vùng, loại truy vấn và thời gian.

### Kịch bản thử nghiệm

Giả sử cần lựa chọn giữa hai cấu hình đọc:

- **Phương án A:** tất cả GET hồ sơ qua primary.
- **Phương án B:** GET từ replica gần, riêng phiên vừa ghi dùng primary hoặc chờ version.

Có thể thử:

1. Chạy workload đọc/ghi đại diện (có đồng thời), ghi nhận P50/P95/P99.
2. Sau mỗi lần ghi xác nhận, tạo GET ngay và ghi nhận version được trả.
3. Thử với replica lag có kiểm soát để kiểm chứng fallback khi hoạt động bình thường nhưng áp lực tải cao.
4. So sánh vi phạm read-your-writes, tải primary, chi phí và trải nghiệm.
5. Chọn theo SLO và bất biến nghiệp vụ, ghi nhận trade-off vào quyết định kiến trúc.

Đây là kiểm chứng về **đặc tính runtime**, tách biệt với kiểm thử lỗi chia cắt mạng.

## 11. Những hiểu lầm cần tránh

### “Không có partition thì mọi replica đều có cùng dữ liệu”

Không đúng. Truyền và áp dụng bản ghi mất thời gian ngay cả khi kết nối bình thường. Replica lag, cache lag và cập nhật bất đồng bộ xuất hiện ở hệ thống khỏe mạnh.

### “Eventual consistency đồng nghĩa dữ liệu sai”

Không hẳn. Dữ liệu được phép cũ so với nguồn trong một cửa sổ thời gian xác định bởi chính sách. Nó có thể hoàn toàn phù hợp với trường hợp hiển thị thông tin ít nhạy cảm; với quyết định giao dịch quan trọng thì có thể không phù hợp.

### “Chỉ cần bật quorum R + W > N là có strong consistency”

Không đủ. Điều kiện giao nhau của quorum không tự cung cấp thứ tự ghi đúng, bảo vệ khỏi race, failover cũ hoặc đảm bảo một đọc mới luôn phản ánh ghi đã hoàn tất. Cần hiểu cam kết cụ thể của database và giao thức.

### “Đọc từ leader lúc nào cũng mạnh, đọc replica lúc nào cũng yếu”

Không thể kết luận chung. Leader có thể có cơ chế bảo đảm khác nhau; follower cũng có thể hỗ trợ consistent read theo token, read index hoặc chờ bắt kịp. Hãy đọc tài liệu semantics của từng sản phẩm và cấu hình.

### “Độ trễ thấp nhất phải luôn là mục tiêu số một”

Không đúng với những thao tác mà đọc cũ gây hậu quả lớn: chuyển tiền, chống bán vượt tồn, kiểm tra quyền, trạng thái thanh toán. Điều cần tối ưu là **đạt mục tiêu latency trong khi giữ đúng các bảo đảm nghiệp vụ**.

### “Nhất quán mạnh nghĩa là không bao giờ có bất đồng bộ”

Không đúng. Hệ thống có thể đồng bộ trên đường ghi hoặc điểm quyết định cần bảo đảm mạnh, còn notification, search index và analytics cập nhật bất đồng bộ. Một sản phẩm có thể kết hợp nhiều chính sách.

### “Tăng timeout sẽ giải quyết trade-off”

Timeout dài hơn đôi khi cho thêm thời gian để replica bắt kịp, nhưng cũng tăng tail latency và chiếm tài nguyên. Phải có policy rõ cho fallback, trả lỗi và giới hạn tải; không có timeout nào thay thế được thiết kế về thứ tự phiên bản.

## 12. Khung lựa chọn cho kiến trúc sư và kỹ sư

Khi thêm một replica, cache hoặc vùng triển khai, hãy trả lời tuần tự:

1. **Đang đọc/ghi cái gì?** Xác định entity, thao tác và phạm vi transaction.
2. **Nếu dữ liệu cũ thì hậu quả nào xảy ra?** Chỉ là trải nghiệm hiển thị, hay vi phạm bất biến và gây thiệt hại?
3. **Bảo đảm tối thiểu là gì?** Linearizability, transaction isolation, read-your-writes, monotonic reads, bounded staleness hay eventual consistency?
4. **Dữ liệu được nhân bản thế nào?** Single leader, multi-leader, quorum, async replication, cache hoặc materialized view?
5. **Có cần giao tiếp qua vùng hay không?** Vị trí của client, service, primary, replicas và số RTT trên đường xử lý.
6. **Ngân sách latency thực tế là bao nhiêu?** P95/P99 mục tiêu, timeout và cách trả lỗi khi chưa đạt bảo đảm.
7. **Đo vi phạm như thế nào?** Version token, invariant checks, replica lag, stale read rate và business errors.
8. **Khi nhu cầu thay đổi sẽ xử lý ra sao?** Policy riêng theo endpoint và tiêu chí xem xét lại.

Có thể ghi một bảng quyết định ngắn:

~~~text
Operation:       Confirm inventory reservation
Correctness:     Không cho xác nhận vượt tồn
Guarantee:       Atomic conditional write tại nguồn có thẩm quyền
Latency budget:  Theo SLO checkout, đo p95/p99
Replica reads:   Chỉ dùng cho xem tồn kho mang tính tham khảo
Fallback:        Không xác nhận đơn nếu chưa kiểm chứng được invariant
Revisit:         Khi tải/chi phí/độ trễ vượt ngưỡng đã thống nhất
~~~

## 13. Bài tập tình huống

**Bài 1.** Người dùng cập nhật email, API ghi trả 200, nhưng lần GET tiếp theo hiển thị email cũ. Không có sự cố mạng. Điều gì có thể đã xảy ra và nên bảo vệ trải nghiệm nào?

*Gợi ý:* GET có thể được định tuyến đến read replica chưa áp dụng bản ghi. Xem xét read-your-writes và xác định điểm API được phép báo cập nhật thành công.

**Bài 2.** Nền tảng tin tức có hàng triệu lượt đọc bài viết, nội dung thay đổi không thường xuyên; yêu cầu hiển thị nhanh trên nhiều khu vực. Nên cân nhắc gì?

*Gợi ý:* Replica gần, CDN/cache và cơ chế invalidate. Chấp nhận dữ liệu cũ có giới hạn và có chính sách đối với bài bị thu hồi hoặc thông tin bắt buộc cập nhật ngay.

**Bài 3.** N=3, W=2, R=2. Có thể tuyên bố mọi GET linearizable không?

*Gợi ý:* Chưa. Điều kiện giao quorum chỉ là một thành phần; cần kiểm tra thuật toán ghi/đọc, phiên bản, ghi đồng thời, thay đổi membership và semantics thực tế.

**Bài 4.** Dữ liệu thống kê có thể trễ 10 giây, nhưng p99 của endpoint hiện rất cao vì đọc qua nút xa. Hãy đề xuất phương án đo và cải thiện.

*Gợi ý:* Xác định bounded staleness được thực thi như thế nào; dùng replica/projection gần, kiểm tra lag P99, phân tích RTT và so sánh với mục tiêu latency.

## 14. Tổng kết

Ngay cả khi hệ thống phân tán hoạt động bình thường, các replica vẫn có độ trễ đồng bộ và việc xác nhận trạng thái mới nhất có thể đòi hỏi thêm phối hợp. **PACELC** giúp đặt đúng câu hỏi: ngoài lựa chọn Availability/Consistency khi có partition, hệ thống còn phải cân nhắc **Latency/Consistency khi không có partition**.

Không có một chế độ tốt nhất cho mọi dữ liệu. Hệ thống thực dụng thường dùng phản hồi nhanh cho đọc có thể chịu stale, read-your-writes cho thao tác sau khi người dùng vừa ghi, và cơ chế ghi nguyên tử hoặc đồng thuận phù hợp cho các bất biến nghiệp vụ. Quyết định phải dựa trên **ngữ nghĩa dữ liệu, tác hại của dữ liệu cũ, P95/P99 latency, replica lag và kiểm chứng thực tế**, thay vì chọn nhãn “strong” hay “eventual” theo cảm tính.

# Causal consistency và quan hệ nguyên nhân-kết quả

Một người dùng đăng bài viết mới, sau đó một người khác đọc bài và để lại bình luận. Ở vùng dữ liệu A, cả **bài viết** lẫn **bình luận** đã tồn tại. Nhưng nếu ứng dụng đọc qua replica ở vùng B và hệ thống cập nhật hai bản ghi theo những đường bất đồng bộ khác nhau, người dùng tại B có thể thấy **bình luận nhắc tới một bài viết mà chính replica đó chưa thấy**.

Đây là vấn đề **thứ tự nhân quả**, không đơn thuần là độ trễ sao chép. Bình luận được tạo **vì tác giả đã đọc bài viết**; hai sự kiện có quan hệ nguyên nhân–kết quả. Hệ thống cần bảo đảm khi quan sát **kết quả**, người đọc cũng có thể quan sát được **những nguyên nhân mà kết quả phụ thuộc**, theo cùng một mô hình dữ liệu và lịch sử được bảo đảm.

**Causal consistency (nhất quán nhân quả)** là mô hình nhất quán cho phép các replica/khách hàng có thể nhìn thấy những thao tác **không liên quan nhân quả** theo thứ tự khác nhau, nhưng phải tôn trọng thứ tự **có quan hệ nhân quả**. Nó là lựa chọn hữu ích trong hệ NoSQL phân tán nhiều vùng khi muốn giảm nhu cầu áp đặt **một thứ tự toàn cục** lên tất cả các cập nhật, đồng thời tránh một số bất thường gây khó hiểu cho người dùng.

Bài học thuộc **Database No SQL → Các mô hình nhất quán** này tập trung vào: xác định quan hệ *happens-before*; phân biệt causal consistency với eventual, sequential và linearizable consistency; cách vận chuyển **causal context** qua phiên và vùng dữ liệu; metadata như **vector clock, version vector, Lamport clock, hybrid logical clock**; cách xử lý cập nhật đồng thời; các giới hạn về giao dịch, tồn kho, phân quyền; và cách kiểm thử mô hình này trong hệ thống Java.

> **Phạm vi:** “Causal consistency” không phải tên một mức đọc duy nhất xuất hiện giống nhau trong mọi NoSQL. Bảo đảm thực tế phụ thuộc engine, driver, phiên, read concern, write concern, cách nhân bản và đường truy cập. Các ví dụ kiến trúc, con số và kết quả thử nghiệm dưới đây là minh họa; không suy diễn một sản phẩm có bảo đảm nào nếu chưa đối chiếu tài liệu đúng phiên bản.

## 1. Vì sao “đọc được dữ liệu mới” chưa đủ?

Giả sử có ba tác nhân:

- **An** tạo bài viết P-42.
- **Bình** đọc P-42 rồi viết bình luận C-7 tham chiếu P-42.
- **Chi** ở vùng dữ liệu khác tải trang bình luận.

Các sự kiện:

~~~~text
A: Write Post(P-42)
        |
        v
B: Read Post(P-42) -> success
        |
        v
B: Write Comment(C-7, postId=P-42)
        |
        v
C: Read Comments -> C-7
C: Read Post(P-42) -> not found
~~~~

Nếu Chi nhìn thấy C-7 nhưng bản ghi hoặc phiên bản P-42 làm cơ sở cho C-7 chưa được áp dụng trên đường đọc được dùng, hệ thống đã lộ **kết quả trước nguyên nhân** trong một mô hình mà chúng ta muốn bảo toàn causal visibility.

Điểm quan trọng là hệ thống không cần mọi người nhìn thấy bài viết và bình luận **ngay tức thì**. Nó chỉ cần không công bố hoặc trả một hiệu ứng phụ thuộc trước khi những dependency của nó đã đủ hiển thị theo hợp đồng.

### 1.1. Một cặp cập nhật độc lập không nhất thiết có thứ tự chung

Ở cùng thời gian:

~~~~text
Vùng VN:  Alice thích sản phẩm P-1.
Vùng EU:  Bob đổi ảnh đại diện của tài khoản B-2.
~~~~

Nếu Alice và Bob không tương tác và không có thông tin nào được truyền từ thao tác này sang thao tác kia, hai sự kiện có thể **đồng thời theo quan hệ nhân quả**, ngay cả khi đồng hồ tường có thể ghi một sự kiện sớm hơn vài mili giây.

Causal consistency không buộc mọi replica phải trình bày hai sự kiện độc lập theo cùng một thứ tự ngay lập tức. Điều này giúp tránh chi phí phối hợp **toàn cục** đối với những thao tác không liên quan.

### 1.2. Causal consistency giải quyết cái gì?

Nó nhằm loại những lịch sử mà **người quan sát nhìn thấy một hiệu ứng nhưng không nhìn thấy lịch sử nhân quả cần thiết của hiệu ứng đó**.

Nó **không tự bảo đảm**:

- Mọi người đọc ở mọi nơi thấy dữ liệu mới nhất theo thời gian thực.
- Một cập nhật được nhân bản tới mọi replica trong 100 ms.
- Hai writer độc lập cùng sửa một khóa sẽ không xung đột.
- Tất cả các trường trong nhiều document được commit nguyên tử.
- Một số lượng tồn kho không bao giờ âm.
- Một lệnh chuyển tiền không bao giờ bị retry trùng.
- Một quyền vừa bị thu hồi sẽ lập tức bị mọi request trên thế giới từ chối.

Đó là các yêu cầu thuộc những lớp khác: **replication freshness, conflict resolution, transaction atomicity, isolation, linearizability, authorization và idempotency**.

## 2. Định nghĩa quan hệ happens-before

Mô hình nhân quả thường được diễn giải bằng quan hệ **happens-before**, ký hiệu:

\[
a \rightarrow b
\]

Đọc là: “sự kiện a xảy ra trước b **theo quan hệ nhân quả**”.

Quan hệ được xây từ ba loại liên kết cơ bản.

### 2.1. Program order: thứ tự trong một tác nhân

Nếu một client chạy tuần tự:

~~~~text
a. Write profile.displayName = "An"
b. Write profile.bio = "Java developer"
~~~~

và ứng dụng có một thứ tự thao tác được xác lập:

\[
a \rightarrow b
\]

Cập nhật b được phát sau a trong cùng luồng tác nhân. Một causal implementation phải truyền đủ thông tin để replica khác không áp dụng/hiển thị b theo cách bỏ qua dependency a.

**Lưu ý:** Nếu hai request được phát **đồng thời** từ hai thread trong cùng ứng dụng, không thể tự suy ra chúng có program order nhân quả. Muốn có thứ tự thì ứng dụng phải phối hợp hoặc truyền causal context rõ ràng.

### 2.2. Reads-from: một thao tác đọc quan sát một write

Giả sử:

~~~~text
a. An viết Post(P-42) phiên bản 1
b. Bình đọc và thực sự nhìn thấy Post(P-42) phiên bản 1
c. Bình viết Comment(C-7) dựa trên bài viết đó
~~~~

Khi b đọc giá trị được ghi bởi a:

\[
a \rightarrow b
\]

Vì b và c nằm trong program order của cùng luồng Bình:

\[
b \rightarrow c
\]

Nên c phụ thuộc gián tiếp vào a.

Đây là **quan hệ dữ liệu làm bằng chứng**: việc Bình nhìn thấy bài viết là lý do bình luận có thể được viết với ý nghĩa ấy.

### 2.3. Transitivity: quan hệ bắc cầu

Nếu:

\[
a \rightarrow b
\]

và:

\[
b \rightarrow c
\]

thì:

\[
a \rightarrow c
\]

Như vậy, một tác vụ có thể phụ thuộc **gián tiếp** vào một thay đổi mà chính client tạo tác vụ chưa từng đọc trực tiếp.

Ví dụ:

~~~~text
A: Tạo dự án Project-9
        |
        v
B: Đọc dự án -> Tạo Task-21
        |
        v
C: Đọc Task-21 -> Tạo Comment-7
~~~~

Comment-7 **gián tiếp phụ thuộc** vào Project-9 thông qua Task-21. Một causal view có Comment-7 cần phù hợp với các dependency trước đó, không chỉ với Task-21.

### 2.4. Concurrency theo nhân quả

Hai sự kiện a và b được gọi là **concurrent** trong nghĩa quan hệ nhân quả khi:

\[
a \not\rightarrow b
\quad\text{và}\quad
b \not\rightarrow a
\]

Ký hiệu ngắn:

\[
a \parallel b
\]

“Concurrent” ở đây không yêu cầu hai CPU thực thi đúng một thời điểm. Nó có nghĩa **không có đường thông tin nhân quả đã được xác lập giữa hai sự kiện**.

### 2.5. Sơ đồ DAG cho causal history

~~~~mermaid
flowchart LR
    A["a: Tạo Post"] --> B["b: Đọc Post"]
    B --> C["c: Viết Comment"]
    C --> E["e: Đọc Comment"]
    D["d: Like sản phẩm độc lập"] 
~~~~

Trong đồ thị này:
- a có trước b, c và e về mặt nhân quả.
- c có trước e.
- d có thể concurrent với a/b/c/e.
- Đồ thị quan hệ nhân quả là **thứ tự từng phần (partial order)**, không cần một thứ tự toàn cục cho mọi sự kiện.

**Thứ tự thời gian thực** và **thứ tự nhân quả** khác nhau. Một thao tác hoàn tất trước thao tác khác tại hai client hoàn toàn độc lập không tự tạo liên kết happens-before nếu không có truyền thông/phụ thuộc tương ứng.

## 3. Causal consistency là bảo toàn causal past

Một cách phát biểu trực giác:

> Nếu một client nhìn thấy thao tác b, hệ thống phải bảo đảm những thao tác thuộc **causal past** của b cũng có thể được nhìn thấy theo view nhất quán mà client đang quan sát.

Tập **causal past** của b:

\[
Past(b) = \{a \mid a \rightarrow b\}
\]

Một tập thay đổi hiển thị H cần có tính **đóng xuống theo quan hệ nhân quả (causally downward-closed)**:

\[
b\in H \land a\rightarrow b \implies a\in H
\]

Công thức thể hiện ý tưởng: một snapshot/view không được chứa hiệu ứng b mà lại bỏ một dependency a cần thiết trong cùng lịch sử.

### 3.1. Điều này không có nghĩa field luôn còn giá trị cũ

Giả sử:

~~~~text
a: Write x = 1
b: Read x = 1
c: Write y = "seen x=1"
d: Write x = 2 (sau a)
~~~~

Một view có c và x=2 **không mặc nhiên vi phạm nhân quả**. Giá trị x=1 từng là dependency của c nhưng có thể đã được **phiên bản mới hợp lệ thay thế**. Yêu cầu là view và thứ tự phiên bản phải **bao hàm lịch sử/tiến triển phù hợp**, không phải bắt UI mãi hiển thị đúng bytes x=1.

Tương tự, nếu sau khi đăng bình luận, bài viết bị **xóa hợp lệ**, việc thấy bình luận nhưng GET bài viết trả “đã xóa” **không tự chứng minh** có vi phạm causal consistency. Để kiểm chứng chuẩn phải xét **version, tombstone, thứ tự delete và view**, không chỉ assert “parent luôn tồn tại”.

### 3.2. Phụ thuộc được công bố khác việc tự đoán từ tên trường

Một comment có trường postId=P-42 là **tham chiếu nghiệp vụ**, nhưng causal dependency chỉ được hệ thống hiểu nếu cơ chế ứng dụng/database ghi nhận được quan hệ thông tin tương ứng.

Ví dụ service C tạo comment từ một **ID được gõ thủ công**, chưa hề đọc bài viết và không mang causal context, database không tự biết postId tạo ra quan hệ reads-from.

Muốn bảo đảm “không có comment trước post”, có thể cần:

- Đọc/kiểm tra post tại nguồn có thẩm quyền rồi truyền causal context.
- Cập nhật atomically nếu nằm trong cùng transaction/aggregate.
- Dùng event stream có dependency token/sequence.
- Thiết kế workflow không publish comment trước khi xác nhận post đã tồn tại.

**Causal consistency chỉ bảo vệ những quan hệ nhân quả được biểu diễn và duy trì trong hệ thống**, không tự suy luận mọi ràng buộc từ nội dung JSON.

## 4. Bốn bảo đảm phiên thường đi cùng causal consistency

Causal consistency thường được giải thích qua những **session guarantees**. Một session ở đây là chuỗi thao tác của một tác nhân/ứng dụng được nhận diện với causal context thích hợp; nó không nhất thiết bằng một TCP connection.

| Bảo đảm | Ý nghĩa trực giác | Ví dụ |
| --- | --- | --- |
| **Read-your-writes (RYW)** | Sau khi client đã ghi thành công, lần đọc tiếp trong phiên không quay về trạng thái trước lần ghi đó | Vừa đổi tên, trang cá nhân vẫn thấy tên mới |
| **Monotonic reads (MR)** | Khi đã quan sát một phiên bản, client không bị phục vụ một view “cũ hơn” về quan hệ cần giữ | Đã thấy comment mới rồi refresh không mất comment chỉ vì đổi replica |
| **Monotonic writes (MW)** | Các lần ghi tuần tự của client được áp dụng theo thứ tự nhân quả của phiên | Đặt status DRAFT rồi PUBLISHED không bị replica lộ PUBLISHED trước DRAFT cần thiết |
| **Writes-follow-reads (WFR)** | Một write sau khi read một trạng thái phải mang/tuân thủ những dependency đã được quan sát | Đọc Post rồi viết Comment thì Comment phụ thuộc Post |

Những khái niệm này có liên hệ chặt với causal consistency, nhưng **không được mặc định một driver chỉ bật một cờ “session” sẽ mang đủ bốn bảo đảm**. Phải xem tài liệu engine: session nào, thao tác nào, read/write concerns nào, token/metadata nào.

### 4.1. Read-your-writes

~~~~text
Client C:
  Write profile.name = "Lan"  -> ACK
  Read profile.name          -> phải thấy "Lan"
                               hoặc phiên bản hợp lệ mới hơn
~~~~

Nếu request đọc bị chuyển sang replica chưa nhận write, một giải pháp là **đợi replica bắt kịp, định tuyến sang replica khác hoặc báo chưa thể đáp ứng**, chứ không trả âm thầm bản cũ dưới hợp đồng RYW.

### 4.2. Monotonic reads

~~~~text
Read 1 ở Region A: thấy Post v9
Read 2 ở Region B: chỉ có Post v7
~~~~

Nếu cùng phiên được bảo đảm monotonic reads, Read 2 không được trả một view bỏ qua trạng thái đã quan sát ở Read 1. Cơ chế có thể chờ, reroute hoặc dùng token xác nhận vùng B đã đủ tiến độ.

**Monotonic reads không có nghĩa mọi read phải là phiên bản mới nhất toàn cầu**. Nó chỉ tránh bước lùi so với causal context đã thấy.

### 4.3. Monotonic writes

~~~~text
Write 1: Thêm sản phẩm P-42
Write 2: Bật P-42.active=true
~~~~

Nếu Write 2 là thao tác sau Write 1 của cùng tác nhân, một replica không nên công bố active=true theo cách chưa áp dụng dependency tạo sản phẩm trong causal view.

### 4.4. Writes-follow-reads

~~~~text
Client Bình:
  Read profile version 5 của An
  Write notification "Đã xem profile version 5"
~~~~

Write notification phải mang dependency **profile version 5** mà client đã quan sát. Đây là chỗ một số kiến trúc mất nhân quả nếu service đọc ở một database rồi service khác gửi update bằng một client mới **không mang causal context**.

### 4.5. Các phiên song song không tự có chung causal context

Client A xem bài viết. Một background worker nhận request không kèm **định danh/version token**, dù trong cùng ứng dụng rộng hơn, không tự có bằng chứng đã đọc ấy.

Để kết nối hai thao tác thành quan hệ nhân quả cần chuyển metadata hợp lệ:

~~~~text
Read Post at service A -> causalContext C
Service A -> command to service B (payload + C)
Service B -> Write Comment with C
~~~~

Nếu bỏ C và chỉ gửi postId, implementation có thể chỉ bảo đảm causal order nội bộ một phiên DB riêng, không bảo đảm phụ thuộc liên service.

## 5. So sánh các mô hình nhất quán

Một cách trực quan:

| Mô hình | Đòi thứ tự/bảo đảm gì? | Điều vẫn có thể xảy ra |
| --- | --- | --- |
| **Eventual consistency** | Khi ngừng ghi và hệ hoạt động đúng, các bản sao cuối cùng hội tụ theo cơ chế conflict resolution | Replica có thể thấy hiệu ứng trước dependency; đọc mới rồi cũ |
| **Causal consistency** | Bảo toàn thứ tự của những thao tác có quan hệ nhân quả trong view và session được bảo vệ | Hai thao tác concurrent có thể được quan sát theo thứ tự khác; đọc không nhất thiết mới nhất |
| **Sequential consistency** | Có một lịch sử tuần tự hợp lệ cho các operation, bảo toàn program order của mỗi tác nhân | Không nhất thiết tôn trọng thứ tự thời gian thực giữa hai client độc lập |
| **Linearizability** | Mỗi operation có hiệu ứng như xảy ra tại một điểm giữa invoke/response, tôn trọng real-time order của những operation không chồng lấp | Có thể đòi phối hợp và bị ảnh hưởng nhiều hơn khi mạng phân vùng |
| **Serializable transaction** | Các transaction cho kết quả tương đương một thứ tự tuần tự của transaction | Không nhất thiết tôn trọng real-time order nếu không có thêm bảo đảm |
| **Strict serializability** | Serializable và tôn trọng real-time order của transaction | Thường chi phí phối hợp cao hơn với transaction phân tán |

Bảng là mô tả khái niệm. **Linearizability thường được định nghĩa trên operation của một đối tượng/dịch vụ**, còn serializability trên nhóm transaction; không gộp chúng thành cùng một thuộc tính.

### 5.1. Vì sao causal mạnh hơn eventual ở khía cạnh thứ tự?

Eventual convergence thông thường chỉ nói **các replica cuối cùng đạt một trạng thái hội tụ**, không yêu cầu trong mọi thời điểm tạm thời phải tôn trọng quan hệ a -> b.

Causal consistency thêm yêu cầu về **visibility order** của dependency.

Ví dụ:

~~~~text
a: PostCreated
b: CommentCreated phụ thuộc a

Eventual-only replica:
  nhận b -> hiển thị comment
  nhận a sau 10 giây -> hiển thị post

Causal replica:
  nhận b trước nhưng biết b cần a
  chưa công bố b tới khi a đã hiển thị theo view
~~~~

Causal consistency không bảo đảm **a hoặc b sẽ tới ngay**, chỉ buộc cách hiển thị tôn trọng dependency.

### 5.2. Vì sao causal không đòi một thứ tự duy nhất cho mọi concurrent write?

Hai người dùng độc lập cập nhật hai profile:

~~~~text
a: Update profile of A ở VN
b: Update profile of B ở EU
a || b
~~~~

Replica VN có thể thấy a trước b, replica EU có thể thấy b trước a mà vẫn phù hợp với causal ordering. Không có dependency nào đòi hai nơi thống nhất thứ tự hiển thị tức thời.

Với sequential consistency, mô hình cần một lịch sử tuần tự chung tương ứng với các quan sát được cho phép; causal không áp đặt cùng mức thứ tự giữa các operation độc lập.

### 5.3. Causal consistency không phải linearizability

Giả sử hai client không chia sẻ session/context:

~~~~text
10:00:00 Client A write price=1390000 -> ACK
10:00:01 Client B ở vùng khác read price -> 1500000
~~~~

Một hệ causal có thể cho phép B đọc giá cũ nếu **B chưa có causal dependency từ A** và hợp đồng không đòi real-time visibility toàn cục. Một hệ tuyến tính hóa cho đối tượng price với write/read không chồng lấp như ví dụ phải tôn trọng việc write đã hoàn tất trước read bắt đầu.

**Dựa vào causal consistency để chốt giá/tồn kho/khóa duy nhất trong mọi client** thường không đủ nếu cần một điểm quyết định real-time toàn cục.

## 6. Quan hệ nhân quả không đồng nghĩa với thứ tự timestamp

Một lỗi thiết kế phổ biến:

~~~~text
if eventA.timestamp < eventB.timestamp:
    assume A causes B
~~~~

Điều này **không đúng**.

Hai sự kiện ở hai máy không có tương tác có thể có timestamp khác nhau nhưng vẫn **concurrent**. Clock skew, NTP adjustment, thiết bị offline và thời gian nhận trễ càng khiến kết luận sai.

### 6.1. Ví dụ clock skew

~~~~text
Máy A đồng hồ nhanh +300 ms:
  Event a được ghi 10:00:00.500

Máy B đồng hồ chậm -200 ms:
  Event b nhận thông tin từ a rồi phát lúc 10:00:00.350
~~~~

Theo timestamp, b “sớm hơn” a. Theo quan hệ nhân quả thực:

\[
a \rightarrow b
\]

**Đồng hồ tường không đủ để nhận diện happens-before**.

### 6.2. Lamport clock: tôn trọng một chiều, không nhận diện đủ concurrency

Lamport logical clock tăng theo mỗi sự kiện và cập nhật khi nhận thông điệp. Nó bảo đảm:

\[
a\rightarrow b \implies L(a)<L(b)
\]

Nhưng chiều ngược lại **không đúng**:

\[
L(a)<L(b) \centernot\implies a\rightarrow b
\]

Hai sự kiện concurrent có thể có scalar timestamp khác nhau. Lamport clock có ích để xây một thứ tự mở rộng quan hệ nhân quả hoặc protocol ordering, nhưng **chỉ so hai số Lamport không đủ khẳng định a là nguyên nhân của b**.

### 6.3. Hybrid logical clock (HLC)

Một **HLC** kết hợp thành phần gần với thời gian vật lý và thành phần logic để sắp thứ tự thời gian có ý nghĩa hơn đồng hồ thô khi hệ trao đổi thông điệp.

Nhưng **HLC riêng lẻ không tự lưu toàn bộ dependency graph**. Hai HLC được sắp theo một thứ tự không chứng minh mọi sự kiện trước đó có quan hệ nhân quả với nhau.

Một hệ có thể dùng HLC làm **version/timestamp** và dùng metadata/context khác để bảo vệ causal visibility. Không lấy “có HLC” làm bằng chứng tự động có causal consistency end-to-end.

## 7. Vector clock và version vector

Vector clock là công cụ thường dùng để biểu diễn thứ tự từng phần và nhận biết concurrency.

Giả sử có hai replica **VN** và **EU**. Một causal vector có hai thành phần:

~~~~text
V = [counter_VN, counter_EU]
~~~~

Ví dụ:

~~~~text
a tại VN: [1,0]
b tại VN sau a: [2,0]
c tại EU nhận thông tin a rồi ghi: [1,1]
d tại VN sau b: [3,0]
~~~~

Ta định nghĩa quan hệ component-wise:

\[
V_a \le V_b
\iff
\forall i,\ V_a[i]\le V_b[i]
\]

Và quan hệ nhỏ hơn thực sự:

\[
V_a < V_b
\iff
V_a \le V_b
\land
\exists j,\ V_a[j]<V_b[j]
\]

### 7.1. Ví dụ có phụ thuộc

Cho:

~~~~text
V(a) = [1,0]
V(c) = [1,1]
~~~~

Vì [1,0] <= [1,1] và khác nhau nên a có trước c theo quan hệ vector clock được tạo/duy trì đúng:

\[
V(a) < V(c)
\]

Replica biết c cần tiến độ bao gồm thành phần [1,0].

### 7.2. Ví dụ concurrent

Cho:

~~~~text
V(b) = [2,0]
V(c) = [1,1]
~~~~

V(b) không <= V(c) vì 2 > 1 ở VN. V(c) cũng không <= V(b) vì 1 > 0 ở EU. Hai vector **không so sánh được**:

\[
V(b) \parallel V(c)
\]

Điều này thể hiện rằng c đã biết a nhưng chưa biết b, còn b chưa biết cập nhật mới tại EU.

### 7.3. Merge causal context

Khi client đã quan sát hai trạng thái, context có thể được hợp nhất bằng maximum theo từng thành phần:

\[
merge([2,0],[1,1])=[2,1]
\]

Đó là cơ chế khái niệm của **causal context union**. Một request tiếp theo mang [2,1] sẽ phụ thuộc vào tiến độ đã quan sát từ cả hai nguồn.

### 7.4. Version vector không phải công cụ miễn phí

Nếu hệ có N actor/replica độc lập, vector thường có thể có O(N) thành phần. Với hàng nghìn actor, metadata và việc đổi membership có thể đắt.

Các tối ưu có thể bao gồm:
- Vector theo **replication group/shard** thay vì per user.
- Sparse/compact vectors.
- Dotted version vectors.
- Causal context được server cấp dưới dạng opaque token.
- Dependency tracking theo checkpoint hoặc stable frontier.
- Gom hoặc dọn metadata khi đủ điều kiện an toàn.

**Không tự phát minh vector clock format rồi bỏ thành phần cũ tùy tiện**, vì loại metadata quá sớm có thể làm hệ không còn phân biệt dependency hoặc event concurrent.

## 8. Causal delivery: nhận b trước a thì xử lý ra sao?

Giả sử có hai write:

~~~~text
a: PostCreated(P-42)
b: CommentCreated(C-7, P-42), phụ thuộc a
~~~~

Replica B nhận b trước do hai đường mạng có độ trễ khác nhau.

Một causal replication protocol có thể đính kèm dependency context:

~~~~json
{
  "eventId": "b",
  "kind": "CommentCreated",
  "aggregateId": "C-7",
  "dependsOn": {
    "VN": 17,
    "EU": 4
  },
  "payload": {
    "postId": "P-42"
  }
}
~~~~

Giả sử replica chỉ mới áp dụng:

~~~~json
{
  "VN": 16,
  "EU": 4
}
~~~~

Nó chưa đạt dependency **VN:17**. Do đó có thể:
1. Nhận event b và lưu vào **pending/buffer**.
2. Yêu cầu hoặc đợi event thiếu từ VN.
3. Khi đã đạt VN:17, áp dụng b theo protocol.
4. Công bố b cho những truy vấn thuộc causal view phù hợp.

~~~~mermaid
flowchart TD
    B["Nhận event b"] --> C{"Đủ dependency context?"}
    C -->|Chưa| P["Buffer b, đợi/fetch a"]
    P --> C
    C -->|Đủ| A["Áp dụng / hiển thị b"]
~~~~

Đây là **mô hình thuật toán**, không phải logic buộc mọi hệ phải có một queue toàn cục.

### 8.1. Pseudocode cho dependency check

~~~~text
onReceive(update):
    deps = update.causalDependencies

    if localVisibleFrontier dominates deps:
        applyUpdateSafely(update)
        advanceLocalFrontier(update)
        retryBufferedUpdates()
    else:
        buffer(update)
        fetchOrWaitForMissingDependencies(deps)
~~~~

**Visible frontier dominates deps** có ý nghĩa khi phiên bản/counter được xây đúng bởi protocol. Nếu engine chỉ có một số sequence riêng từng key, không thể tự ghép chúng thành vector toàn cluster rồi tuyên bố đã bảo đảm causality.

### 8.2. Khi dependency không thể tới

Một event có thể bị mất khỏi log, replica nguồn chết hoặc mạng bị phân vùng. Nếu hệ bắt buộc bảo toàn causal consistency, nó không thể đơn giản **công bố b mà bỏ a**.

Các lựa chọn phụ thuộc thiết kế:
- Chờ tới khi a có mặt.
- Fetch a từ replica/backup khác.
- Route read sang replica đã có đủ causal past.
- Trả timeout/temporarily unavailable cho read/write phụ thuộc.
- Dùng snapshot/checkpoint có chứng minh đã bao gồm dependency.
- Khởi động quy trình repair khi thiếu dữ liệu.

**Không được “sửa latency” bằng cách phá dependency order một cách âm thầm** nếu API đang cam kết causal consistency.

## 9. Multi-region: causal context theo người dùng

Một người dùng di chuyển từ vùng VN sang Singapore hoặc EU:

~~~~text
Region VN:
  User write profile v12 -> ACK

Region EU:
  User refresh profile.
  Replica EU mới ở v10.
~~~~

Nếu request mới không mang session context, một hệ eventual-only có thể trả v10. Để giữ read-your-writes, application/session phải mang **causal token tương ứng v12** để vùng EU biết cần đạt tiến độ nào.

### 9.1. Session token

Một token minh họa (không phải format của sản phẩm cụ thể):

~~~~json
{
  "sessionId": "S-778",
  "causalContext": {
    "VN": 120,
    "EU": 48
  },
  "issuedAt": "2026-11-14T09:00:00Z",
  "tokenVersion": 1
}
~~~~

Khi client gọi read:
- Gửi token cho server theo API hợp đồng.
- Server chỉ phục vụ từ view đáp ứng dependency của token.
- Nếu replica chưa đạt, có thể chờ, chuyển vùng hoặc trả trạng thái tạm thời không đáp ứng.
- Kết quả read mới trả lại **context cập nhật** để client dùng tiếp.

### 9.2. Phiên không nhất thiết là kết nối TCP

Nếu mobile app đổi kết nối mạng hoặc request rơi vào một node khác, causal session cần tiếp tục qua **logical session**. Nếu context chỉ nằm trong memory của một instance stateless API, request tới instance khác có thể mất bảo đảm.

Các phương án:
- Driver hỗ trợ session/causal token theo hợp đồng.
- API gateway/cookie/header mang opaque token được ký/kiểm tra.
- Backend lưu per-session context ở kho phù hợp.
- Truyền context qua event/command khi chuyển sang worker khác.

**Đừng giả định sticky session load balancer đủ**: failover, autoscaling hoặc background queue có thể thay đường xử lý.

### 9.3. Session token phải được bảo vệ

Causal context có thể ảnh hưởng mức dữ liệu mà server chờ/đọc. Không tin token do client tự sửa với giá trị cực lớn:

~~~~json
{
  "causalContext": {
    "VN": 999999999999999
  }
}
~~~~

Một token không hợp lệ có thể khiến request chờ mãi hoặc gây áp lực tài nguyên. Với token truyền qua client:
- Dùng format/driver chính thức khi có.
- Xác minh tính toàn vẹn hoặc ký token nếu thuộc hợp đồng bảo mật.
- Giới hạn kích thước, phiên bản, TTL và định danh cluster/tenant.
- Không cho phép client tùy ý nâng clock/dependency.
- Không để token của tenant này tiết lộ topology hoặc dữ liệu của tenant khác.

Các biện pháp bảo mật token là yêu cầu ứng dụng; chúng không thay thế chính sách phân quyền của dữ liệu nguồn.

## 10. Chuyển causal context qua nhiều microservice

Ví dụ một hệ thống diễn đàn:

~~~~mermaid
flowchart LR
    API["Gateway"] --> POST["Post service"]
    POST --> PDB[("Post DB")]
    POST --> BUS["Event bus"]
    BUS --> COMMENT["Comment service"]
    COMMENT --> CDB[("Comment DB")]
    CDB --> FEED["Feed service"]
~~~~

Quy trình:
1. Post service tạo bài và nhận **causal context C1** từ source.
2. Client đọc bài, tiếp tục giữ/merge C1.
3. Client gửi CreateComment kèm C1.
4. Comment service tạo comment với dependency C1 theo protocol được hỗ trợ.
5. Feed service chỉ công bố comment trong view đáp ứng C1.

### 10.1. Event bus không tự biến hai database thành causal store

Broker có thể bảo đảm order **trong một partition/stream cụ thể** nhưng không tự bảo đảm quan hệ nhân quả xuyên mọi stream, consumer và database.

Ví dụ:
- PostCreated được phát trên topic POSTS.
- CommentCreated được phát trên topic COMMENTS.
- Hai consumer ở các cluster khác nhau.
- COMMENTS xử lý nhanh hơn POSTS.

Không thể mặc định đọc được CommentCreated là PostCreated đã visible ở mọi downstream.

Nếu cần causal visibility end-to-end, phải:
- Biểu diễn dependency trong event/metadata.
- Chọn cách đồng bộ apply/publish phù hợp.
- Dùng một hệ read model sở hữu hai loại dữ liệu với thứ tự hợp lệ.
- Hoặc thay đổi workflow để không hiển thị comment trước khi nguồn bài được nhìn thấy.

### 10.2. Cross-database causality là hợp đồng ứng dụng

Nếu Post DB cung cấp một loại token còn Comment DB dùng một protocol độc lập, **không được lấy JSON của token này nhét vào database kia rồi mong có causal ordering**.

Có thể thiết kế layer điều phối:
- Shared event log có checkpoint/causal dependency.
- Projection được xây theo event DAG.
- API chờ một downstream checkpoint xác định.
- Truyền version nguồn và kiểm tra khi render.

**Causal consistency trong một database không tự suy rộng thành causal consistency của toàn bộ hệ microservice.**

## 11. Một ví dụ Java mô hình hóa causal context

Để thấy cách **merge và so sánh dependency**, có thể mô tả vector context bằng Java 21:

~~~~java
import java.util.HashMap;
import java.util.Map;

public record CausalContext(Map<String, Long> versions) {
    public CausalContext {
        versions = Map.copyOf(versions);
    }

    public boolean dominates(CausalContext prerequisite) {
        return prerequisite.versions.entrySet().stream()
                .allMatch(entry ->
                        versions.getOrDefault(entry.getKey(), 0L)
                                >= entry.getValue()
                );
    }

    public CausalContext merge(CausalContext other) {
        Map<String, Long> result = new HashMap<>(versions);
        other.versions.forEach((replica, version) ->
                result.merge(replica, version, Math::max)
        );
        return new CausalContext(result);
    }
}
~~~~

Ví dụ dùng:

~~~~java
CausalContext seenInVN =
        new CausalContext(Map.of("VN", 12L, "EU", 3L));

CausalContext seenInEU =
        new CausalContext(Map.of("VN", 11L, "EU", 8L));

CausalContext merged = seenInVN.merge(seenInEU);
// merged = {VN=12, EU=8}

boolean enough = merged.dominates(
        new CausalContext(Map.of("VN", 12L, "EU", 5L))
);
// true
~~~~

Đây là **mô hình giáo dục về phép so sánh vector**, **không phải implementation đầy đủ của một causal database**. Nó chưa giải quyết:
- Ai được phép cấp phiên bản và tăng clock.
- Khi nào một update bền vững hoặc đã visible.
- Replica membership/reconfiguration.
- Gap trong log và duplicate.
- Conflict resolution cho concurrent versions.
- Shard/tenant isolation và bảo mật token.
- Metadata compaction/GC.
- Read snapshot và transaction semantics.

### 11.1. Interface ứng dụng có thể giữ context tách biệt

Một abstraction minh họa:

~~~~java
public record CausalRead<T>(
        T value,
        CausalContext observedContext
) {}

public record CausalWrite(
        String operationId,
        CausalContext dependencies
) {}

public interface CausalDocumentStore<T> {
    CausalRead<T> read(
            String id,
            CausalContext requiredContext
    );

    CausalContext write(
            String id,
            T document,
            CausalWrite options
    );
}
~~~~

Hợp đồng kỳ vọng:
- Read chỉ trả một trạng thái phù hợp với requiredContext hoặc phản hồi **không thể đáp ứng tạm thời**.
- Write mang causalDependencies của những read/write trước.
- Server trả **context đã quan sát hoặc tạo ra** để client merge.

**Đừng implement interface này bằng một GET/PUT bình thường rồi chỉ truyền Map trong HTTP headers.** Cần engine/protocol thật sự sử dụng metadata để điều khiển visibility.

### 11.2. Phân biệt dependency context với business version

Một product có **aggregateVersion=18**. Đó là sequence theo **một aggregate**. Nó không nói consumer đã nhìn thấy **version 7 của tài khoản chủ sở hữu** hay **version 12 của chính sách danh mục**.

Causal context có thể gồm nhiều dependency xuyên khóa/actor; aggregateVersion một chiều chỉ giúp so sánh cập nhật của **cùng aggregate**.

## 12. MongoDB: causal session cần read/write concern phù hợp

MongoDB hỗ trợ các cơ chế **causally consistent sessions** trong phạm vi được tài liệu của sản phẩm quy định. Một trường hợp thường gặp để nhận đầy đủ bảo đảm session nhân quả là dùng **majority write concern** và **majority read concern**, cùng các operation được thực hiện theo thứ tự thích hợp trong session.

Ví dụ Java driver minh họa:

~~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

public final class CausalSessionExample {
    public static Document updateThenRead(
            MongoClient mongoClient,
            String databaseName,
            String id,
            String body
    ) {
        MongoCollection<Document> notes = mongoClient
                .getDatabase(databaseName)
                .getCollection("notes")
                .withWriteConcern(WriteConcern.MAJORITY)
                .withReadConcern(ReadConcern.MAJORITY);

        ClientSessionOptions options = ClientSessionOptions.builder()
                .causallyConsistent(true)
                .build();

        try (ClientSession session =
                     mongoClient.startSession(options)) {
            // Giả định document id đã tồn tại.
            notes.updateOne(
                    session,
                    eq("_id", id),
                    set("body", body)
            );

            // Read tiếp trong cùng session.
            return notes.find(session, eq("_id", id)).first();
        }
    }
}
~~~~

Đoạn code là ví dụ của **luồng tuần tự read-your-writes** với session. Cần xử lý trường hợp document chưa tồn tại, kết quả matchedCount, exception, retry policy, cấu hình cluster và phương án session migration theo yêu cầu ứng dụng.

**Lưu ý vận hành:**
- Không chạy đồng thời nhiều operation trên cùng session khi driver không hỗ trợ mức concurrency đó.
- Một causal session **không phải multi-document transaction**.
- Truyền causal context giữa các session/client không nhất thiết chỉ bằng cách chuyển một session ID chuỗi; hãy dùng API/driver chính thức theo hợp đồng.
- Không mặc định mọi query qua full-text index ngoài database, cache hoặc downstream service cũng có bảo đảm cùng session.
- Causal consistency không nâng một read thành **linearizable read**.

### 12.1. Majority không thay thế hoàn toàn causal session

WriteConcern.MAJORITY và ReadConcern.MAJORITY tác động tới những thuộc tính ghi/đọc theo hợp đồng của MongoDB, nhưng để bảo vệ **quan hệ phụ thuộc cụ thể trong phiên** vẫn phải dùng API/session đúng cách.

Ngược lại, chỉ bật causallyConsistent(true) mà bỏ qua write/read concern cần thiết không nên được diễn giải như một bảo đảm bền vững mạnh trong mọi tình huống.

### 12.2. Những NoSQL khác không tự có cùng semantic

DynamoDB hỗ trợ strongly consistent reads cho một số đường đọc trên bảng theo điều kiện dịch vụ, trong khi **Global Secondary Index** được cập nhật bất đồng bộ. Không gọi một GSI query eventual là “causal” chỉ vì request trước đó vừa ghi bảng.

Cassandra có consistency levels và cơ chế đọc/ghi phân tán riêng. Đặt LOCAL_QUORUM hoặc QUORUM không đồng nghĩa toàn bộ các thao tác xuyên khóa, phiên và vùng dữ liệu tự có một causal session context được duy trì; phải xem bảo đảm cụ thể.

Redis có thao tác nguyên tử trên một node và replication riêng. Một sequence GET/SET trên nhiều client/node không tự trở thành causal consistency phân tán toàn cục.

**Không suy từ tên một tính năng “session”, “quorum”, “strong read” hoặc “replica” ra bảo đảm nhân quả xuyên toàn hệ.**

## 13. Causal consistency và xung đột cập nhật concurrent

Causal order bảo đảm **đặt đúng thứ tự những gì đã có dependency**. Nó không tự chọn giá trị thắng khi **hai writer concurrent sửa cùng một key**.

Ví dụ hai vùng ngắt kết nối:

~~~~text
Ban đầu:
  profile.nickname = "Lan"

Region VN:
  a: Set nickname = "Lana"

Region EU:
  b: Set nickname = "Lani"

a || b
~~~~

Hai replica có thể tạm khác nhau. Khi kết nối lại, cần **conflict resolution** để hội tụ hoặc hiển thị nhiều nhánh.

### 13.1. Last-write-wins (LWW)

Một số hệ chọn phiên bản “mới nhất” theo timestamp/tie-breaker.

Lợi ích:
- Đơn giản để tạo ra một giá trị cuối.
- Hạn chế việc giữ nhiều sibling versions lâu dài.

Rủi ro:
- Có thể làm mất một cập nhật hợp lệ.
- Timestamp vật lý bị lệch không phản ánh đúng ý định.
- Version “thắng” không nhất thiết là thao tác có quan hệ nhân quả mới nhất nếu thiết kế timestamp sai.
- Merge độc lập của các field có thể tạo trạng thái không mong muốn.

Nếu a và b concurrent, chọn một winner là **chính sách giải quyết xung đột**, không chứng minh write còn lại chưa từng xảy ra.

### 13.2. Multi-value register hoặc sibling values

Hệ có thể lưu cả hai phiên bản concurrent:

~~~~json
{
  "nickname": [
    {
      "value": "Lana",
      "version": {"VN": 8, "EU": 2}
    },
    {
      "value": "Lani",
      "version": {"VN": 7, "EU": 3}
    }
  ]
}
~~~~

Ứng dụng hoặc conflict resolver quyết định cách hợp nhất.

Nhược điểm: UX khó nếu dữ liệu là nickname hoặc địa chỉ thanh toán; cần policy rõ để chọn.

### 13.3. CRDT và causal convergence

Một **CRDT** có thể cho phép merge deterministic những update concurrent theo một đại số phù hợp. Ví dụ set các “like” theo userId hoặc bộ đếm được thiết kế cho merge; cách giải quyết tùy CRDT.

Causal consistency có thể kết hợp với cơ chế hội tụ, thường được thảo luận trong các mô hình **causal+**: giữ causal ordering đồng thời bảo đảm các replica có thể hội tụ về kết quả tương thích khi nhận cùng tập update.

Tuy nhiên:
- CRDT không tự giữ mọi bất biến tài chính/tồn kho.
- Cùng một logical event bị giao trùng có thể cần identity/dedup tùy loại CRDT.
- Add-wins/remove-wins có ngữ nghĩa khác nhau với quyền và xóa.
- Những thao tác không giao hoán có thể cần reconciliation hoặc coordination.

### 13.4. Causal ordering không ép hai event độc lập phải giao hoán

Hai update concurrent có thể không giao hoán:

~~~~text
a: Set stock = 5
b: Set stock = 10
~~~~

Áp dụng theo hai thứ tự khác nhau có thể tạo hai kết quả. Muốn hội tụ, hệ cần **một quy tắc xác định conflict** hoặc một ranh giới ghi có coordination. Causal consistency **không tự giải quyết** điểm này.

## 14. Causal consistency không thay thế transaction nguyên tử

Giả sử một order cần hai ghi:

~~~~text
a: Decrement inventory BOOK-42
b: Create order O-901
~~~~

Nếu a -> b, causal order có thể ngăn một replica nhìn thấy b trước dependency a **trong causal view được bảo vệ**. Nhưng điều đó **không đồng nghĩa** hai thay đổi là **một transaction all-or-nothing**.

Nếu thao tác a commit rồi thao tác b thất bại:
- Inventory có thể đã giảm.
- Order chưa tồn tại.
- Causal consistency không tự rollback inventory.

Cần transaction bao trùm cả hai bản ghi, hoặc **reservation + saga/compensation**.

### 14.1. Thứ tự visibility khác tính nguyên tử của nhóm

Hai yêu cầu:

1. **Causal ordering:** nếu b phụ thuộc a thì không công bố b trước khi a đủ visible.
2. **Atomic visibility:** hai update trong một batch/transaction được nhìn thấy **cùng nhau** hoặc không nhìn thấy cái nào.

Chúng liên quan nhưng khác nhau. Một hệ có thể bảo đảm cái thứ nhất mà không bảo đảm cái thứ hai.

### 14.2. Không đảm bảo một bản snapshot toàn cục “mới nhất”

Một transaction cần đọc một tập khóa ở **cùng snapshot hợp lệ**. Causal read có thể bảo vệ dependency, nhưng nó không tự cung cấp serializable transaction hoặc snapshot có thời điểm mới nhất toàn cục.

Ví dụ:

~~~~text
T1 đọc limit=10
T2 đọc usedA=6
T3 đọc usedB=5
T4 quyết định thêm quota
~~~~

Nếu các read không có ranh giới nhất quán phù hợp, phép tính vẫn có thể sai vì giá trị bị thay đổi bởi writer concurrent. Causal consistency không chặn **write skew** hoặc **oversell**.

## 15. Các bất biến nghiệp vụ nào cần mạnh hơn causal?

| Bài toán | Causal có giúp gì? | Còn cần gì? |
| --- | --- | --- |
| Feed/bình luận | Tránh hiệu ứng hiện trước những dependency đã quan sát | Xử lý delete, index lag, moderation |
| Thay đổi profile và thông báo | Bảo toàn thứ tự user đổi profile trước khi event liên quan hiển thị | Session context end-to-end |
| Giỏ hàng không nhạy | Tránh phiên đọc quay lùi; merge các update concurrent | Conflict semantics, item identity |
| Lịch sử tài liệu cộng tác | Giữ causal ordering giữa các edit phụ thuộc | OT/CRDT/conflict strategy |
| Số lượt like | Có thể cho phép concurrent update và hội tụ | Dedup user/event, CRDT nếu cần |
| Tồn kho cứng | Tránh hiện order trước một số dependency | **Conditional reserve/transaction** không âm |
| Ví tiền/thanh toán | Trật tự event giúp audit/read model | **Ledger, atomic debit, idempotency, isolation** |
| Độc quyền slot đặt phòng | Trật tự các thao tác đã quan sát | **Unique/conditional guard** |
| Thu hồi quyền truy cập | Lan truyền thứ tự policy update và event phụ thuộc | Kiểm tra quyền ở điểm có thẩm quyền, fail closed khi cần |
| Thay đổi cấu hình an toàn | Không áp dụng update phụ thuộc trước cấu hình cần thiết | Version/epoch và blocking theo chính sách |

### 15.1. Phân quyền là ví dụ đặc biệt nhạy cảm

Giả sử admin **thu hồi quyền** ở vùng VN. Một client không có causal dependency đến lệnh thu hồi ở vùng EU vẫn có thể đọc trạng thái cũ dưới hợp đồng causal-only. Nếu yêu cầu là “sau khi lệnh thu hồi được xác nhận, **không request mới nào được phép** trên toàn hệ”, chỉ causal consistency **không đủ**.

Có thể cần:
- Kiểm tra authorization tại nguồn/điểm quyết định mạnh hơn.
- Policy version/epoch và token revocation.
- Đường read bảo đảm mức nhất quán phù hợp.
- Fail closed khi vùng phục vụ không xác minh được trạng thái mới.

**Đừng dùng causal consistency như một lời hứa thu hồi quyền tức thời toàn cầu.**

### 15.2. Tồn kho có thể thấy trạng thái “đúng thứ tự” nhưng vẫn oversell

Hai vùng cùng đọc available=1 mà không liên hệ causally:

~~~~text
VN: Read 1 -> Create Reservation A
EU: Read 1 -> Create Reservation B
~~~~

Nếu hai giao dịch độc lập dựa trên dữ liệu cũ và không có atomic guard/escrow, cả hai có thể đặt được hàng. Quan hệ giữa Reservation A và B là **concurrent**, nên causal ordering không áp đặt một winner.

Cần **conditional update**, một chủ sở hữu quota, transaction hoặc phân bổ quyền kiểu escrow.

## 16. Tính sẵn sàng khi mạng phân vùng

Causal consistency có thể tránh **phối hợp toàn cục cho các thao tác độc lập**, nhưng một client đã quan sát dependency ở vùng A rồi truy cập vùng B đang bị ngăn nhận dependency có thể gặp lựa chọn khó:

~~~~text
Client đã thấy Post version 12 tại VN.
Client sang EU, replica EU chỉ có version 10.
Mạng VN -> EU đang đứt.
~~~~

Nếu bảo vệ monotonic reads/RYW, EU không thể cứ trả version 10 rồi vẫn nói đã tuân thủ cùng session.

Các khả năng:
- **Wait:** chờ dependency tới; latency tăng.
- **Reroute:** phục vụ từ replica đã có dependency, nếu kết nối còn.
- **Fail/temporarily unavailable:** trả lỗi có khả năng retry/khôi phục.
- **Degrade với hợp đồng khác:** chỉ khi API/client **chấp nhận rõ ràng** chuyển sang read yếu hơn; không âm thầm vi phạm cam kết.

### 16.1. Causal consistency không có nghĩa mọi request luôn không-blocking

Một số thiết kế causal store có thể duy trì **availability cao** cho write độc lập trong phân vùng mạng. Tuy nhiên request mang dependency mà replica hiện tại chưa có có thể cần chờ hoặc bị từ chối.

Vì thế phải đo **dependency wait time và unavailable rate**, không chỉ độ trễ ghi bình thường.

### 16.2. Đồng bộ địa lý và p99

Giả sử:
- Người dùng ở VN tạo 100 update/giây.
- Replica EU nhận stream trễ 200 ms bình thường.
- Một sự cố khiến lag tăng 15 giây.
- Người dùng mang causal token mới từ VN tới EU.

Đọc từ EU có thể phải chờ gần mức lag hoặc reroute; một tài liệu thiết kế ghi “local read = 5 ms” không đủ nếu client đã có dependency vượt tiến độ replica.

**Chi phí của bảo đảm nhân quả xuất hiện ở những lượt truy cập mang dependency**, không chỉ ở tốc độ đồng bộ trung bình.

## 17. Causal context qua message queue và retry

Một pipeline:

~~~~text
Read Customer v7
   -> Create Order O-901 (dep Customer v7)
   -> Publish OrderCreated
   -> Consumer tạo Notification
~~~~

Nếu broker giao OrderCreated hai lần hoặc consumer retry, causal context giúp biết update phụ thuộc Customer v7; nhưng nó **không làm sự kiện idempotent**.

### 17.1. Causal và idempotent là hai thuộc tính khác nhau

- **Causal:** Notification phải tôn trọng dependency OrderCreated và Customer v7.
- **Idempotency:** giao hai lần cùng eventId không gửi hai notification hoặc trừ tồn kho hai lần.

Một event có thể gồm:

~~~~json
{
  "eventId": "evt-order-901",
  "aggregateId": "O-901",
  "aggregateVersion": 1,
  "causalContext": {
    "VN": 25,
    "EU": 9
  },
  "payload": {
    "orderId": "O-901",
    "customerId": "C-77"
  }
}
~~~~

Consumer cần **dedup eventId** và/hoặc conditional state transition bên cạnh dependency tracking.

### 17.2. Sự kiện mất ACK không làm mất quan hệ nhân quả nếu retry đúng

Nếu một write đã commit ở source rồi ACK mất:
- Client không được tự suy ra write chưa xảy ra.
- Retry nên dùng **operationId** hoặc transaction identity phù hợp.
- Causal context phải được cập nhật từ kết quả đã xác minh.
- Nếu outcome chưa rõ, giữ trạng thái UNKNOWN và reconcile.

Causal consistency bảo vệ **thứ tự sự kiện đã được nhận diện**, nhưng không tự giải quyết **ambiguity của commit**.

## 18. Delete, tombstone và causal history

Xóa dữ liệu là một update có quan hệ nhân quả.

~~~~text
a: Create Post P-42
b: Comment C-7 phụ thuộc a
c: Delete Post P-42 sau a
~~~~

Tùy thời điểm và concurrency giữa b, c, có những lịch sử hợp lệ khác nhau. Một replica có thể thấy comment và một tombstone cho post, điều đó **có thể hoàn toàn hợp lệ**.

### 18.1. Delete phải có version/order

Nếu replica giữ một bản Post cũ, rồi nhận Delete nhưng sau đó lại nhận Create/Update cũ do mạng trễ, không được để tài liệu đã xóa hồi sinh theo cách phá quy tắc phiên bản/conflict resolution.

Cần:
- Tombstone hoặc metadata tương đương.
- Version/causal context để biết Delete phụ thuộc cập nhật nào.
- Quy tắc xử lý **concurrent update vs delete**.
- Retention/garbage collection an toàn cho replica chậm.

### 18.2. Garbage collection metadata nhân quả

Nếu loại toàn bộ causal history sau một ngày nhưng một replica khác có thể offline bảy ngày, hệ cần biết cách đối phó khi event cũ quay lại.

Một implementation có thể dùng **stable frontier**, checkpoint hoặc snapshot để chứng minh tất cả những dependency trước một mốc đã được tích hợp và metadata có thể được rút gọn. Điều này phải theo protocol; không tự xóa vector/tombstone chỉ để giảm dung lượng.

### 18.3. Legal deletion khác việc không còn query-visible

Một bản ghi không còn hiện ở feed không chứng minh mọi replica, WAL, snapshot, backup và search index đã xóa dữ liệu theo yêu cầu pháp lý. Causal consistency không phải một cơ chế bảo đảm xóa vĩnh viễn hoặc compliance tự động.

## 19. Cache, search index và read model có thể phá nhân quả end-to-end

Giả sử backend database causal-consistent, nhưng API đọc qua cache:

~~~~text
Source:
  Write profile v12, then Write notification v2 dependent on v12.

Cache profile:
  vẫn ở v10.

Notification read model:
  đã thấy v2.
~~~~

Ứng dụng render notification v2 nhưng profile v10. **Causal consistency ở source không tự lan qua cache/projection**.

### 19.1. Causal-aware caching

Một cache có thể gắn:
- **Value version**.
- **Causal context/checkpoint** được source chấp nhận.
- **Source-of-truth identifier**.
- Chính sách refresh/fallback khi token yêu cầu cao hơn cache version.

Pseudocode:

~~~~text
readProfile(id, requiredContext):
    cached = cache.get(id)

    if cached exists and cached.context satisfies requiredContext:
        return cached.value

    authoritative = source.read(id, requiredContext)
    cache.put(id, authoritative.value, authoritative.context)
    return authoritative.value
~~~~

Không sử dụng so sánh tùy ý giữa một aggregateVersion và một causal vector khác dạng. Cache phải hiểu cùng mô hình version/dependency với nguồn.

### 19.2. Search index có query visibility riêng

Một event đã được indexer áp dụng có thể chưa **searchable** do refresh hoặc segment publish. Nếu UI cần thấy Post trước Comment, consumer ACK event thôi chưa đủ; cần xét **query-visible checkpoint** của đường search thật.

Có thể cần:
- Chỉ publish Comment khi search view đã thấy dependency.
- Render Post từ source trong trường hợp search chưa bắt kịp.
- Chờ index đạt checkpoint với timeout.
- Trả trạng thái đang đồng bộ thay vì hiển thị thông tin không nhất quán.

### 19.3. Pagination qua nhiều phiên bản

Nếu một feed cập nhật liên tục, trang 1 và trang 2 có thể thuộc hai snapshot khác nhau. Causal consistency không tự bảo đảm một danh sách phân trang là **snapshot bất biến**. Muốn tránh trùng/bỏ sót khi phân trang, có thể cần cursor, tie-breaker và snapshot token theo khả năng công nghệ.

**Độ mới, nhân quả và snapshot consistency là ba mục tiêu có giao nhau nhưng không giống nhau.**

## 20. Xác định đơn vị phiên và đường đi thông tin

Một hệ thống có thể có:
- Session web của người dùng.
- Session driver/database.
- Transaction session.
- Message consumer context.
- Request/trace context.

Chúng **không tự đồng nghĩa**. Để bảo vệ causal consistency, thiết kế phải xác định:
1. **Ai là tác nhân?** Người dùng, thiết bị, service hay workflow?
2. **Thao tác nào có quan hệ thứ tự?** Những read/write tuần tự hoặc dependency explicit.
3. **Metadata được lưu ở đâu?** Driver session, token, server session store hay event log.
4. **Context sống qua restart không?** Nếu không, session guarantee có thể mất.
5. **Context truyền qua boundary nào?** Browser → API → worker → DB.
6. **Read nào phải tôn trọng token?** Primary, replica, GSI, search, cache?
7. **Khi dependency chưa có, hệ làm gì?** Wait, route, fail hay downgrade có báo rõ?
8. **Khi context quá lớn, có thể compact theo protocol nào?**

### 20.1. Trường hợp mobile app offline

Mobile app xem Post v12 rồi offline. Trong lúc offline, user viết Comment C-7.

Nếu app lưu được causal context v12 và có cơ chế gửi write mang dependency khi online trở lại, backend có thể bảo đảm C-7 không được công bố sai causal order trên những đường được hỗ trợ.

Nếu app chỉ gửi postId, server có thể không biết comment dựa vào v12 hay vào một bản sao khác; cần kiểm tra/rebase logic ở nguồn hoặc yêu cầu client gửi **read token** phù hợp.

### 20.2. Nhiều tab hoặc thiết bị của cùng người dùng

Tab 1 đã thấy profile v12; Tab 2 còn context v10. Nếu nghiệp vụ hứa **monotonic read trên toàn account**, cần đồng bộ/merge context giữa tab và thiết bị hoặc dựa vào backend session state. Một causal session tách biệt theo tab **không tự đưa RYW qua thiết bị khác**.

Phạm vi của guarantee phải được công bố chính xác: **theo DB session, HTTP session, thiết bị, account hay toàn hệ**?

## 21. Observability: đo nhân quả chứ không chỉ replication lag

Một dashboard replication chỉ có **lag trung bình = 100 ms** không chứng minh causal consistency được giữ.

Các nhóm chỉ số cần theo dõi:

| Nhóm | Chỉ số | Điều cần hiểu |
| --- | --- | --- |
| **Dependency** | Missing dependency count, age | Event nào bị chặn chờ causal past? |
| **Causal delivery** | Buffered updates, buffer age, apply rate | Hệ có thể xử lý event out-of-order không? |
| **Session** | RYW/monotonic-read violations theo probe | Client có nhìn thấy view cũ hơn không? |
| **Visibility** | Commit-to-query-visible p95/p99 | Kết quả phụ thuộc bao lâu mới đọc được? |
| **Replication** | Per-region stream lag, oldest unreplicated event | Vùng nào đang chậm? |
| **Blocking** | Causal-wait duration, timeout count | Cái giá latency của bảo đảm |
| **Metadata** | Causal token bytes, vector entries, merge cost | Chi phí lưu/truyền context |
| **Conflict** | Concurrent version count, resolution outcomes | Có mất/merge update không? |
| **Recovery** | Gap repair, replay, snapshot bootstrap | Replica sau offline có giữ causal order không? |
| **Foreground** | API p50/p95/p99, error, achieved throughput | Người dùng bị ảnh hưởng thế nào? |
| **Resource** | CPU, memory, network, storage | Tải metadata và buffer có lớn không? |

### 21.1. Event lag không phải causal violation

Một replica còn trễ 20 giây nhưng **không hiển thị hiệu ứng trước nguyên nhân** có thể vẫn giữ causal consistency. Ngược lại, một replica chỉ trễ 50 ms nhưng công bố một comment trước post có thể đã vi phạm.

**Freshness SLO** và **causal ordering invariant** phải được đo riêng.

### 21.2. Đừng chỉ kiểm tra một giá trị hiện hành

Nếu Post P-42 đã có v3 sau khi v1 và v2 được dùng để tạo comment, test cần kiểm tra view causal của **phiên bản được phụ thuộc**, không chỉ check giá trị hiện tại theo ID.

Có thể dùng synthetic objects và version markers trong môi trường test:
- Mỗi update có unique operationId.
- Event có dependency ID/version được nhận diện.
- Probe lưu read session context và applied versions.
- Phân tích có một read trả child nhưng causal past chưa được bao gồm không.

### 21.3. Tracing theo dependency chain

Một trace có thể lưu các ID khác nhau:

~~~~text
requestId       = REQ-442
sessionId       = S-778
postOperationId = OP-201
commentOpId     = OP-202
causalContextId = CTX-889
traceId         = TRACE-...
~~~~

Đừng đưa **full vector với hàng nghìn thành phần** vào metric label có cardinality khổng lồ. Log/tracing có thể giữ thông tin mẫu đủ để điều tra nhưng phải tránh lộ dữ liệu người dùng và giới hạn thông tin nhạy cảm.

## 22. Thiết kế thử nghiệm có kiểm soát

Một bài test muốn xác nhận causal consistency phải xây được **dependency thực sự**, không chỉ phát nhiều write liên tiếp rồi so timestamp.

### 22.1. Bộ dữ liệu tối thiểu

~~~~text
Post:
  id = P-42
  version = 1
  operationId = A

Comment:
  id = C-7
  postId = P-42
  dependsOn = A
  operationId = B

Like:
  id = L-8
  targetId = P-42
  operationId = D
  không có dependency với B nếu concurrent
~~~~

Kịch bản:
1. Writer A tạo Post; ghi lại ACK và causal context.
2. Writer B **đọc được Post** từ session phù hợp.
3. Writer B tạo Comment với context đã quan sát.
4. Writer D độc lập tạo Like.
5. Thay đổi thứ tự delivery để vùng EU nhận B trước A.
6. Reader C ở EU thử đọc Comment và Post theo cùng hợp đồng causal session.
7. Quan sát rằng Comment B không được công bố trước dependency A theo view yêu cầu.
8. Cho D đến trước/sau tùy ý: thứ tự D với B **không bị ràng buộc** nếu concurrent.

### 22.2. Ma trận test

| Kịch bản | Điều chỉnh | Bất biến/kết quả |
| --- | --- | --- |
| Program order | Một client ghi a rồi b | Không hiển thị b theo cách bỏ a |
| Read-then-write | Client đọc a rồi ghi b | b mang dependency a |
| Transitive chain | a -> b -> c qua ba service | Reader thấy c phải có causal past của a và b |
| Concurrent writes | Hai client không trao context | Không đòi thứ tự tổng; conflict rule hợp lệ |
| Out-of-order delivery | Gửi b tới replica trước a | Buffer/wait/fetch; không công bố b sớm |
| Session migration | Write VN, read EU trễ | RYW/monotonic read hoặc wait/reroute |
| Multiple tabs | Context mỗi tab khác nhau | Bảo đảm đúng phạm vi đã công bố |
| Message replay | Broker phát event trùng | Causal + idempotency không nhân đôi effect |
| Network partition | EU thiếu dependency | Không âm thầm trả view vi phạm |
| Clock skew | Đổi thời gian máy trong môi trường test phù hợp | Không suy nhân quả từ clock vật lý |
| Replica restart | Node khôi phục từ snapshot cũ | Không apply child trước causal history |
| Tombstone GC | Delete và late old update | Không hồi sinh dữ liệu trái rule |
| Search lag | Source đủ context, search thiếu | Không nhầm source guarantee với UI guarantee |
| Large token | Context có nhiều actor | Giới hạn bộ nhớ/băng thông và an toàn input |
| Cross-region failover | Client chuyển vùng sau ACK | Session context không bị mất |
| Multi-item workflow | a rồi b ở hai key | Không tự giả định atomic batch |
| Hot user/session | Nhiều operation trong một phiên | Đo dependency wait, p99 và throughput |

### 22.3. Thử nghiệm không nên bắt buộc concurrent updates có cùng thứ tự

Nếu a || b, một assertion kiểu:

~~~~text
"Region VN và EU phải nhìn thấy a trước b tại mọi thời điểm"
~~~~

có thể **đòi mạnh hơn causal consistency**. Test đúng nên chỉ buộc:

~~~~text
Nếu a -> b, không quan sát b mà thiếu causal past a.
Nếu a || b, thứ tự có thể khác, nhưng conflict resolution
phải làm đúng theo hợp đồng convergence của sản phẩm.
~~~~

### 22.4. Chú ý test delete

Một bài test đơn giản “đọc Comment mà không GET được Post là failure” có thể **báo lỗi giả** nếu Post đã bị Delete hợp lệ sau Create.

Để test chính xác:
- Ghi version Create, Update và Delete.
- Lưu causal dependency.
- Dùng read/visibility metadata hoặc snapshot hợp lệ.
- Kiểm tra replica không thiếu causal past cần thiết.
- Phân biệt **không tồn tại vì chưa nhận Create** với **không tồn tại vì đã nhận Delete sau đó**.

## 23. So sánh performance giữa eventual, causal và mạnh hơn

Giả sử một ứng dụng đa vùng có:
- 20.000 read/s.
- 5.000 write/s.
- 80% thao tác độc lập giữa những người dùng.
- 20% thao tác có dependency chain (post -> comment -> notification).
- Replication lag bình thường 80 ms, khi sự cố tăng 10 giây.
- SLO p99 đọc thông thường 150 ms.

Một kết quả benchmark **giả định**:

| Kịch bản | p99 đọc | Dependency wait p99 | Causal violation | Ghi chú |
| --- | ---: | ---: | --- | --- |
| Eventual-only, không truyền context | 40 ms | 0 ms | Có thể có | Đọc nhanh nhưng có thể thấy effect trước cause |
| Causal, dependency đã local | 55 ms | 0–10 ms | Không theo hợp đồng | Metadata và kiểm tra dependency |
| Causal, session di chuyển tới replica trễ | 280 ms | 220 ms | Không theo hợp đồng | Chờ hoặc chuyển vùng |
| Causal, region bị phân vùng | Timeout/fail | Không đáp ứng | Không công bố vi phạm | Có thể giảm availability |
| Đọc global strong theo đường hỗ trợ | 350 ms | Không đo cùng cách | Bảo đảm mạnh hơn theo phạm vi | Phối hợp/latency tăng |

**Tất cả con số là giả định, không thể dùng để so sánh sản phẩm thực.** Causal consistency có thể rất hiệu quả khi các dependency sẵn có tại replica gần nhất, nhưng khi session mang token từ vùng mới cập nhật sang vùng còn trễ, p99 có thể bị chi phối bởi **chờ dependency**.

### 23.1. Một SLO duy nhất là không đủ

Nên tách:
- **Causal correctness:** số lần vi phạm = 0 trong những lịch sử kiểm chứng được.
- **Freshness:** p99 hoặc tỷ lệ update query-visible trong deadline.
- **Availability:** request bị từ chối do dependency chưa có.
- **Latency:** p50/p95/p99 theo request có/không mang dependency.
- **Recovery:** thời gian bắt kịp sau network partition.
- **Cost:** metadata bytes, buffer size, network traffic và replica capacity.

Không được giảm causal violations bằng cách **không tính những request timeout** mà không báo availability. Tương tự, không được cải thiện p99 bằng cách trả dữ liệu stale trái hợp đồng.

## 24. Một runbook khi thấy hiệu ứng trước nguyên nhân

Tình huống: feed hiển thị bình luận nhưng chưa thấy bài viết tương ứng.

### Bước 1 — Xác định causal relation thật

- Bình luận có thực sự được tạo **sau khi đọc Post phiên bản nào**?
- Có operationId/dependency token từ phiên đọc đó không?
- Post có được tạo trong transaction khác rồi xóa hợp lệ không?
- Bài viết không hiển thị do quyền riêng tư/moderation/filter hay chưa được nhân bản?
- Hai loại dữ liệu có đi qua **cùng causal store** hay qua hai read model độc lập?

**Không kết luận từ postId duy nhất** rằng hệ đã thiết lập causal dependency.

### Bước 2 — Truy vết version và đường đọc

- Source Post/Comment ở version nào?
- Replica nào phục vụ request?
- Causal context của phiên có được gửi không?
- Broker/CDC đã nhận event nào?
- Search/cache đã tới checkpoint nào?
- Client có đổi session/region trước khi đọc không?

### Bước 3 — Phân biệt stale read với dependency violation

- Replica chỉ chưa có bản mới nhưng chưa lộ child? Có thể là lag bình thường.
- Replica đã hiển thị child trong khi thiếu dependency? Có thể vi phạm.
- Child có context nhưng service bỏ qua khi render? Lỗi end-to-end propagation.
- Parent đã bị delete sau đó? Cần kiểm tra history thay vì chỉ nhìn GET not found.

### Bước 4 — Bảo vệ người dùng khi đang sửa

Theo hợp đồng và mức nhạy cảm:
- Tạm chờ hoặc ẩn update phụ thuộc chưa đủ context.
- Route read tới vùng đã có dependencies.
- Dùng source read đúng version khi cần.
- Trả “đang đồng bộ” với retry token nếu không thể đáp ứng.
- Với authorization/tồn kho, dùng đường kiểm tra mạnh hơn hoặc fail closed.

### Bước 5 — Khôi phục và xác minh

- Sửa propagation session token hoặc event dependencies.
- Repair stream bị thiếu, checkpoint và replica.
- Tránh replay child trước parent; xử lý duplicate idempotent.
- Kiểm thử lại chuỗi a -> b -> c qua nhiều vùng.
- Theo dõi dependency backlog, p99 causal wait, read session violations.
- Nếu lỗi từ downstream search/cache, ghi rõ phạm vi guarantee đã bị phá ở tầng nào.

## 25. Những nhầm lẫn thường gặp

1. **“Causal consistency nghĩa là mọi replica luôn có dữ liệu mới nhất.”** Không; nó bảo toàn quan hệ nhân quả, không đòi real-time visibility toàn cầu.
2. **“Cứ timestamp nhỏ hơn là nguyên nhân.”** Không; hai sự kiện độc lập có thể concurrent dù clock khác nhau.
3. **“Một client ghi a rồi b là mọi replica lập tức thấy cả hai.”** Không; có thể trễ, nhưng không công bố b trái dependency a trong view được bảo vệ.
4. **“Eventual consistency cũng tự giữ thứ tự post -> comment.”** Không có bảo đảm causal ordering nếu không được thiết kế.
5. **“Causal consistency = sequential consistency.”** Không; causal chỉ áp thứ tự từng phần lên các operation có dependency.
6. **“Causal consistency = linearizability.”** Không; linearizability thêm yêu cầu real-time order cho những operation không chồng lấp.
7. **“Có vector clock là hệ tự causally consistent.”** Không; cần protocol áp dụng/hiển thị và truyền context đúng.
8. **“Lamport clock biết chắc hai event concurrent.”** Scalar clock không đủ để nhận biết concurrency từ phép so số.
9. **“HLC tự lưu mọi dependency.”** Không; HLC không tự là vector đầy đủ của causal past.
10. **“Cùng requestId nghĩa là cùng causal session.”** RequestId và session context có vai trò khác nhau.
11. **“Mọi HTTP request trong một account tự chia sẻ causal past.”** Không nếu context không được đồng bộ/truyền.
12. **“Broker giữ thứ tự trong partition nên mọi topic có causal order.”** Không; cross-stream dependencies cần cơ chế riêng.
13. **“Database causal-consistent nghĩa là cache/search cũng vậy.”** Không; downstream phải bảo vệ context độc lập.
14. **“Thấy comment nhưng không GET được post luôn là lỗi.”** Post có thể đã bị xóa hợp lệ hoặc bị filter.
15. **“Không có conflict khi giữ causal ordering.”** Hai writer concurrent vẫn có thể xung đột.
16. **“Causal tự giải quyết oversell.”** Không; inventory cần conditional/transaction/escrow.
17. **“Causal tự giải quyết exactly-once khi retry.”** Không; cần operation identity/idempotency.
18. **“Causal transaction nghĩa là all-or-nothing nhiều document.”** Không; causal visibility và transaction atomicity khác nhau.
19. **“Một region thiếu dependency vẫn có thể trả bản cũ và cam kết RYW.”** Không; phải chờ/route/fail hoặc thay đổi hợp đồng có báo rõ.
20. **“Replication lag thấp chứng minh không vi phạm nhân quả.”** Không; phải đo dependency ordering thật.
21. **“Causal token có thể được client tùy tiện sửa clock.”** Không; cần format/validation/security.
22. **“Causal context chỉ cần giữ trong Java ThreadLocal.”** Không đủ qua service, instance, queue hoặc thiết bị.
23. **“Causal consistency đảm bảo xóa dữ liệu pháp lý trên toàn hệ.”** Không; backup/index/replica có vòng đời riêng.
24. **“Một test chạy tuần tự trên một replica đủ.”** Không; phải tạo out-of-order delivery, region migration và failure.
25. **“Causal consistency lúc nào cũng nhanh hơn strong consistency.”** Chi phí phụ thuộc workload, topology và dependency wait thực tế.

## 26. Bài tập thực hành: diễn đàn đa vùng

Một nền tảng diễn đàn triển khai Java 21 và NoSQL có:

- **Ba vùng**: VN, EU, US.
- Dữ liệu gồm Post, Comment, Reaction và UserProfile.
- Post và Comment dùng hai collection; feed được dựng qua stream/index bất đồng bộ.
- Có 20.000 read/s và 5.000 write/s ở tải đỉnh.
- Replication lag bình thường 100 ms, có thể tăng lên 15 giây khi lỗi mạng.
- Mobile app có thể đổi vùng trong một phiên, hoặc tạo comment khi offline.
- Một số người dùng sửa profile rồi ngay lập tức bình luận.
- Dịch vụ auth có thao tác thu hồi quyền truy cập, không được vi phạm chính sách.
- Hệ thống cần giữ comment/reaction hợp lệ, hỗ trợ sửa và xóa post.

### Phần A — Vẽ quan hệ happens-before

Cho các sự kiện:

~~~~text
a: An tạo Post P-42 ở VN.
b: Bình đọc P-42 tại VN.
c: Bình viết Comment C-7 phụ thuộc b.
d: Chi đổi ảnh đại diện tại EU mà không thấy a/b/c.
e: Dũng đọc C-7 ở US rồi gửi Reaction R-5.
~~~~

1. Hãy vẽ DAG cho a, b, c, e.
2. Sự kiện d có nhất thiết đứng trước hoặc sau c không?
3. Viết tập causal past của e.
4. Nếu US nhận e trước c và a, phải làm gì để giữ causal visibility?

**Gợi ý:** a -> b -> c -> e; d có thể concurrent. Một view công bố e phải bao hàm những dependency tương ứng theo protocol.

### Phần B — Vector clock

Giả sử hai vector:

~~~~text
V1 = [VN=4, EU=2, US=1]
V2 = [VN=4, EU=3, US=1]
V3 = [VN=5, EU=2, US=1]
~~~~

Hãy trả lời:
- V1 và V2 có quan hệ nào?
- V2 và V3 có so sánh được không?
- merge(V2,V3) là gì?
- Vì sao một timestamp vật lý của V2/V3 không đủ kết luận event nào gây ra event nào?

**Gợi ý:** V1 < V2; V2 và V3 incomparable; merge = [VN=5, EU=3, US=1].

### Phần C — Session migration

Mobile app ở VN đã nhìn thấy Post v12 rồi chuyển sang EU. Replica EU mới có v10.

1. Làm sao truyền causal context?
2. EU có được trả v10 dưới hợp đồng monotonic reads không?
3. Khi mất mạng VN–EU, server nên wait, route hay fail theo API nào?
4. Đề xuất SLI cho **causal-wait p99** và timeout.

### Phần D — Conflict concurrent

Hai người dùng cùng sửa title của một post ở hai vùng mà không có dependency. So sánh:
- Last-write-wins.
- Multi-value register.
- Một cơ chế chỉnh sửa hợp nhất OT/CRDT khi phù hợp.

Mỗi cách có thể mất dữ liệu hay cần UI giải quyết xung đột thế nào? Causal consistency **có đủ chọn một winner** hay không?

### Phần E — Xóa bài viết

An tạo P-42, Bình viết comment sau khi đọc P-42, rồi một moderator xóa P-42. Feed trả comment nhưng GET P-42 trả “đã xóa”.

- Có chắc là causal violation không?
- Cần metadata/version nào để phân biệt **chưa nhận Create** với **đã nhận Delete**?
- Có cần giữ tombstone và causal context khi replica EU offline lâu ngày không?

### Phần F — Tồn kho và phân quyền

Một sản phẩm chỉ còn một món, hai vùng concurrent reserve. Một nhân viên khác thu hồi quyền truy cập của tài khoản X ở vùng VN.

- Vì sao causal consistency không tự chống oversell?
- Khi đã ACK revoke, liệu mọi request mới ở US có bị từ chối lập tức chỉ bằng causal consistency không?
- Đề xuất **conditional guard/escrow** cho inventory và **authorization source/epoch/fail-closed** cho quyền.

### Phần G — Quan sát và fault injection

Lập kế hoạch thử:
1. Làm chậm PostCreated nhưng phát CommentCreated trước tới một replica.
2. Chuyển session từ VN sang EU khi EU đang lag.
3. Thử comment từ mobile offline có dependency token.
4. Cho event trùng và sai thứ tự khi broker retry.
5. Phân vùng mạng 15 giây.
6. Rebuild search index từ snapshot trong lúc event vẫn đến.
7. Giữ reader/snapshot cũ và xóa post.
8. Cho hai writer concurrent sửa cùng field.

Mỗi test phải ghi **điều kiện nhân quả được tạo như thế nào**, thao tác read cụ thể dùng để kiểm chứng, kết quả chấp nhận được, và những metric: **dependency wait, pending age, p99, errors, duplicate effects, reconciliation mismatch**.

### Phần H — API Java và context propagation

Thiết kế hai endpoint:

~~~~http
POST /posts
POST /comments
~~~~

Một request tạo comment cần mang postId và causal context từ lần đọc post trước. Hãy mô tả:
- Token được server phát hành/kiểm tra ra sao?
- Context được merge sau nhiều read thế nào?
- Khi context của client vượt tiến độ replica thì phản hồi gì?
- Làm sao tránh để client giả mạo vector quá lớn?
- Khi đẩy message qua queue, context có được giữ không?
- Nếu search index chưa searchable, UI có giải pháp nào?

### Hướng giải

Với feed, causal consistency có thể giúp giữ quan hệ **Post -> Comment -> Reaction** mà không bắt mọi thao tác độc lập có cùng một thứ tự toàn cục. Nhưng hệ cần **session/causal metadata xuyên service và region**, cùng cơ chế buffer/wait/reroute khi replica chưa nhận dependency. Những thao tác concurrent cần conflict resolution riêng; những bất biến như inventory, thanh toán và thu hồi quyền cần đường quyết định mạnh hơn. Search, cache và broker phải tham gia hợp đồng visibility hoặc được xem là lớp eventual với fallback/UX rõ ràng.

**Kết luận:** **Causal consistency bảo vệ quan hệ nguyên nhân–kết quả, không bảo vệ một thứ tự thời gian thực toàn cục.** Nó yêu cầu khi một hiệu ứng được quan sát thì **causal past của hiệu ứng** không bị bỏ qua trong view hợp lệ. Để đạt điều đó trong NoSQL phân tán, cần nhận diện **program order, reads-from và transitivity**, vận chuyển **causal context** qua phiên/service/vùng, xử lý **out-of-order replication**, và theo dõi **dependency wait cùng query visibility**. Hai thao tác concurrent vẫn cần conflict resolution; những nghiệp vụ đòi atomic multi-item, uniqueness, chống oversell hoặc thu hồi quyền tức thời cần **bảo đảm bổ sung phù hợp**. Hãy thiết kế causal consistency theo **đường đọc/ghi thật của ứng dụng**, rồi kiểm chứng bằng lịch sử có dependency và sự cố mạng, thay vì chỉ nhìn tên mức consistency hoặc độ trễ replication trung bình.

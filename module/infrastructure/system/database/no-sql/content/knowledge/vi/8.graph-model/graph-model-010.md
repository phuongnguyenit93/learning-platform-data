# Phân phối đồ thị trên nhiều máy và chi phí quan hệ xuyên vùng

Một cơ sở dữ liệu đồ thị (graph database) mô tả thực thể dưới dạng **đỉnh (vertex/node)** và quan hệ dưới dạng **cạnh (edge/relationship)**. Điểm mạnh của mô hình này là ứng dụng có thể đi theo quan hệ: từ một người dùng tới bạn bè, từ một tài khoản tới thiết bị từng đăng nhập, hoặc từ một sản phẩm tới các sản phẩm có liên hệ. Khi toàn bộ đồ thị nằm trên một máy, một phép duyệt quan hệ có thể khai thác cấu trúc lân cận gần nhau. Khi đồ thị vượt khả năng của một máy, câu hỏi phức tạp hơn xuất hiện: **đỉnh và cạnh sẽ được đặt ở đâu, một bước duyệt có phải gọi sang máy khác không, và điều gì xảy ra nếu máy đó ở một vùng địa lý khác?**

Phân phối đồ thị có thể tăng khả năng lưu trữ, thông lượng và độ sẵn sàng; đổi lại, nó tạo chi phí **định tuyến, truyền dữ liệu, phối hợp cập nhật, duy trì bản sao và chịu lỗi**. Hai truy vấn có cùng số cạnh được duyệt vẫn có thể chênh lệch độ trễ lớn nếu truy vấn thứ nhất đi chủ yếu trong một phân vùng, còn truy vấn thứ hai phải vượt qua nhiều phân vùng hoặc trung tâm dữ liệu.

Bài này dùng một mạng xã hội và một mạng phát hiện gian lận làm ví dụ. Các sơ đồ, mã giả và số liệu được đưa ra để giải thích và thiết kế thí nghiệm; **chúng không phải benchmark đã chạy**. Tên gọi *shard*, *partition*, *region*, các bảo đảm ACID, cách phân phối cạnh và tính năng traversal phân tán có thể khác nhau giữa các sản phẩm đồ thị. Không nên suy từ khả năng chạy Cypher/Gremlin của một sản phẩm rằng nó tự động hỗ trợ phân phối quan hệ trên nhiều máy với cùng chi phí.

## 1. Từ mô hình đồ thị đến bài toán phân phối

Trong mạng xã hội, ta có:

- Đỉnh `User` chứa thông tin người dùng.
- Cạnh có hướng `FOLLOWS` nối một người dùng tới người được theo dõi.
- Đỉnh `Post` đại diện bài viết.
- Cạnh `AUTHORED` nối người dùng với bài viết do họ tạo.
- Cạnh `LIKED` nối người dùng với bài viết được thích.

Một đoạn đồ thị:

~~~text
     FOLLOWS          FOLLOWS
  (Alice) ------> (Bình) ------> (Chi)
     |                              ^
     +----------- FOLLOWS ----------+
     |
     +--- AUTHORED ---> (Bài viết P1)
                            ^
                            |
                        LIKED
                            |
                          (Dung)
~~~

Các truy vấn nghiệp vụ khác nhau:

| Mã | Câu hỏi | Mẫu duyệt |
|---|---|---|
| G1 | Alice đang theo dõi ai? | 1-hop từ Alice theo `FOLLOWS` |
| G2 | Bạn của bạn có thể gợi ý cho Alice? | 2-hop, loại trùng và loại người đã theo dõi |
| G3 | Alice và Chi có cùng kết nối nào? | Giao của hai tập lân cận |
| G4 | Các tài khoản nào chia sẻ thiết bị với tài khoản bị nghi vấn? | 2–3 hop qua `Device` |
| G5 | Có đường liên kết ngắn giữa hai tài khoản không? | Duyệt đồ thị có giới hạn độ sâu và số đỉnh |
| G6 | Tính độ quan trọng của mọi đỉnh | Thuật toán lặp hoặc phân tích toàn đồ thị |

G1 có thể rất rẻ nếu toàn bộ hàng xóm của Alice nằm gần nơi lưu Alice. G2 có thể mở rộng ra hàng trăm hoặc hàng triệu ứng viên. G5 cần nhiều vòng trao đổi giữa các phần khác nhau của đồ thị; G6 lại là workload phân tích, khác bản chất với các phép duyệt tương tác ngắn.

**Không thể chọn chiến lược phân phối từ số lượng đỉnh và cạnh đơn thuần.** Cần biết các truy vấn xuất phát từ khóa nào, thường đi bao nhiêu hop, phân bố bậc đỉnh ra sao, các quan hệ nào được duyệt cùng nhau, và những truy vấn nào yêu cầu nhất quán tức thời.

## 2. “Vùng” có thể mang nhiều ý nghĩa

Trong kỹ thuật phân phối đồ thị, cần tách ba phạm vi để không nhầm chi phí:

| Phạm vi | Ý nghĩa | Ví dụ về chi phí phát sinh |
|---|---|---|
| **Phân vùng logic (partition/shard)** | Một phần của tập đỉnh/cạnh được giao cho một nhóm sở hữu | Lookup owner, một traversal cần đổi shard |
| **Máy hoặc miền lỗi (node/rack/availability zone)** | Nơi một hay nhiều shard/replica thực sự chạy | RPC nội bộ, hop qua rack/zone, replica lag, lỗi mạng |
| **Vùng địa lý (geographic region)** | Trung tâm dữ liệu có khoảng cách đáng kể về địa lý | WAN RTT, egress, độ trễ đồng bộ liên vùng, tuân thủ vị trí dữ liệu |

Một cạnh nối hai đỉnh thuộc **hai shard** nhưng cùng máy có chi phí khác một cạnh phải đi từ Hà Nội sang Frankfurt. Một shard có thể có bản sao ở nhiều máy/vùng; “đỉnh thuộc shard S2” không nhất thiết có nghĩa mỗi lần đọc phải đi đến đúng một máy cố định.

Trong phần còn lại:

- **Quan hệ xuyên phân vùng (cross-partition edge)** là cạnh có hai đầu nằm ở các phân vùng khác nhau theo mô hình sở hữu hiện tại.
- **Quan hệ xuyên vùng địa lý (cross-region edge)** là trường hợp một phép đọc/ghi theo cạnh phải lấy dữ liệu hoặc phối hợp qua các vùng địa lý khác nhau.
- **Tính cục bộ (locality)** là mức độ dữ liệu mà một truy vấn thường cần đã nằm trong phạm vi có thể xử lý với ít phối hợp mạng nhất.

Hai chi phí có liên hệ nhưng không đồng nhất: một cạnh cross-partition có thể vẫn được xử lý cục bộ nhờ bản sao hoặc cache; ngược lại, một phân vùng chỉ có replica ở vùng khác vẫn có chi phí WAN.

## 3. Khi đồ thị lớn, hệ thống lưu đỉnh và cạnh ở đâu?

Một mô hình đồ thị logic:

~~~text
Vertex A --FOLLOWS--> Vertex B --FOLLOWS--> Vertex C
~~~

có thể được chia cho nhiều chủ sở hữu vật lý:

~~~mermaid
flowchart LR
    subgraph S1["Shard S1 / máy 1"]
      A["Đỉnh A"]
      AX["Danh sách cạnh xuất phát từ A"]
    end
    subgraph S2["Shard S2 / máy 2"]
      B["Đỉnh B"]
      BX["Danh sách cạnh xuất phát từ B"]
    end
    subgraph S3["Shard S3 / máy 3"]
      C["Đỉnh C"]
    end
    A -->|"FOLLOWS"| B
    B -->|"FOLLOWS"| C
    A -.-> AX
    B -.-> BX
~~~

Sơ đồ chỉ là trực quan hóa. Cách một sản phẩm thực sự lưu cạnh có thể gồm:

1. Lưu cạnh cùng **đỉnh nguồn**, giúp duyệt cạnh đi ra nhanh.
2. Lưu cạnh cùng **đỉnh đích**, giúp duyệt cạnh đi vào nhanh.
3. Lưu hai hướng hoặc **bản sao adjacency**, tăng hiệu năng đọc nhưng tăng chi phí đồng bộ.
4. Chia cạnh thành phân vùng riêng hoặc sử dụng một dịch vụ chỉ mục/định tuyến.
5. Chia dữ liệu theo workload và cache/phân phối một phần lân cận.

Do đó, không nên giả định mỗi truy vấn đồ thị phân tán luôn phải đi qua máy chứa **toàn bộ** hai đầu cạnh. Cần quan sát **đường truy cập thực sự của engine**: lấy được ID hàng xóm ở đâu, khi nào cần thuộc tính của hàng xóm, khi nào phải vượt shard, và dữ liệu được cache/bản sao như thế nào.

### 3.1. Sở hữu dữ liệu và bản sao

**Owner** là nơi hệ thống quy định chịu trách nhiệm chính hoặc có thẩm quyền ghi một phần dữ liệu theo thiết kế. **Replica** là bản sao giúp tăng sẵn sàng hoặc phục vụ đọc. Một đỉnh có thể có nhiều bản sao nhưng cần quy định rõ nơi cập nhật, cách phân giải xung đột và mức độ mới của từng bản sao.

Một câu hỏi thiết kế bắt buộc:

> Nếu cạnh A→B được lưu gần A, còn thông tin trạng thái của B nằm ở shard khác, truy vấn cần chính xác tên/trạng thái mới nhất của B có thể trả lời chỉ bằng bản adjacency tại A không?

Nếu bản adjacency chỉ chứa ID, hệ thống vẫn cần lấy thuộc tính B hoặc dùng projection/cache có cơ chế làm mới rõ ràng.

## 4. Phân phối theo đỉnh: vertex partitioning và edge cut

Chiến lược dễ hiểu nhất là gán mỗi đỉnh cho một shard. Những cạnh nối hai đỉnh thuộc cùng shard là **cạnh nội bộ**; cạnh nối hai đỉnh ở hai shard là **cạnh cắt (cut edge)**.

~~~text
Shard S1                    Shard S2
  (A) -----> (B)            (D) -----> (E)
   |           |              ^
   v           +--------------+
  (C)                cạnh cắt B -> D
~~~

Gọi `p(v)` là shard sở hữu đỉnh `v`. Với đồ thị vô hướng để đếm minh họa, một cạnh `(u,v)` là cut edge nếu `p(u) != p(v)`. Với đồ thị có hướng, có thể đếm cạnh cắt theo chiều duyệt và gán trọng số theo workload.

Tỷ lệ cạnh cắt đơn giản:

\[
\text{Cut ratio} =
\frac{\#\{(u,v)\in E:p(u)\ne p(v)\}}{|E|}
\]

Ví dụ có 100.000 cạnh, 8.000 cạnh nối hai shard thì cut ratio là 8%. Nó cho biết cấu trúc bị cắt ở mức nào, nhưng **không trực tiếp bằng tỷ lệ RPC mạng**: một truy vấn có thể không đi qua các cạnh đó, nhiều cạnh có thể được batch trong một RPC, hoặc bản sao ở nơi đọc đã có dữ liệu.

Với các truy vấn không đều, nên cân nhắc tỷ lệ cắt **có trọng số truy cập**:

\[
\text{Weighted cut ratio} =
\frac{\sum_{e\in E}w(e)\cdot I[p(u_e)\ne p(v_e)]}
     {\sum_{e\in E}w(e)}
\]

Trong đó `w(e)` là tần suất hoặc mức quan trọng của việc duyệt cạnh đó trong một khoảng quan sát. Đây là mô hình phân tích do người thiết kế dùng; muốn tính chính xác cần telemetry, không chỉ dữ liệu đồ thị tĩnh.

### 4.1. Mục tiêu cạnh tranh: ít cắt và phân bố đều

Một thuật toán phân vùng lý tưởng muốn nhiều cạnh được duyệt cùng nhau ở cùng shard. Nhưng nếu gom toàn bộ một cộng đồng cực lớn vào một shard, shard đó có thể quá tải hoặc vượt khả năng bộ nhớ.

Hai mục tiêu thường mâu thuẫn:

- **Giảm giao tiếp xuyên shard:** cố giữ các đỉnh liên hệ chặt ở gần nhau.
- **Cân bằng tài nguyên:** phân bố số đỉnh, số cạnh, tải đọc/ghi, RAM và CPU để không có shard quá nóng.

Chọn một shard cho mọi đỉnh làm cut ratio bằng 0 nhưng không giải quyết bài toán phân phối. Bất kỳ đánh giá partitioning nào cũng cần đo **độ lệch tải và kích thước** bên cạnh cut ratio.

## 5. Phân phối theo cạnh và bài toán đỉnh bậc cao

Trong đồ thị thực, phân bố bậc thường rất lệch. Một tài khoản nổi tiếng có thể có hàng triệu người theo dõi, còn người dùng bình thường chỉ có vài chục. Đỉnh có số cạnh đặc biệt lớn thường gọi là **supernode** hoặc **hub**.

Nếu gán toàn bộ các cạnh kề với một hub cho đúng một shard, shard ấy có thể phải trả lời quá nhiều truy vấn, duy trì adjacency rất lớn, hoặc chịu tải cập nhật tập trung.

Một hướng khác là **edge partitioning/vertex cut**: phân phối cạnh của hub lên nhiều shard, chấp nhận rằng một đỉnh có nhiều bản sao hoặc phần đại diện ở nhiều nơi.

~~~text
                 (Hub H) — đỉnh logic
                      |
          +-----------+-----------+
          |           |           |
       Shard 1     Shard 2     Shard 3
       cạnh H-*    cạnh H-*    cạnh H-*
          |           |           |
       A, B, C      D, E, F     G, H, I
~~~

Ưu điểm có thể là phân tán tải đọc/ghi adjacency và tránh tập trung quá nhiều cạnh ở một máy. Đổi lại, thao tác muốn đọc **toàn bộ** hàng xóm hub phải hợp nhất nhiều phần; thuộc tính của hub có thể cần đồng bộ tới nhiều replica; cập nhật và xóa có thêm chi phí phối hợp.

| Chiến lược | Dữ liệu được chia chủ yếu theo | Lợi ích tiềm năng | Đánh đổi |
|---|---|---|---|
| Vertex partitioning / edge cut | Đỉnh thuộc shard; cạnh có thể cắt ranh giới | Dễ định vị owner của đỉnh | Hub có thể quá tải; traversal qua cut edge |
| Edge partitioning / vertex cut | Cạnh chia cho shard; đỉnh có thể có nhiều phần đại diện | Phân tán adjacency của hub | Phải hợp nhất hàng xóm, đồng bộ trạng thái đỉnh |
| Hybrid | Đỉnh bình thường theo owner, hub hoặc cạnh đặc biệt chia thêm | Cân bằng giữa locality và tải lệch | Quy tắc routing/phục hồi phức tạp |
| Replicated neighborhood | Sao chép phần lân cận hay dùng | Giảm remote read | Tốn RAM/storage và duy trì độ mới |

Những tên chiến lược là họ phương pháp; mỗi sản phẩm có thể chỉ hỗ trợ một phần hoặc dùng cơ chế nội bộ khác. Không nên đổi cấu trúc dữ liệu trong ứng dụng chỉ vì thuật ngữ “vertex cut” nếu hệ quản trị đang dùng không hỗ trợ cách đặt dữ liệu đó.

## 6. Một phép duyệt hai hop đi qua những máy nào?

Giả sử Alice ở shard S1, hai người được Alice theo dõi ở S2 và S3. Để đề xuất bạn của bạn, hệ thống cần tìm hàng xóm tiếp theo của các đỉnh trên.

~~~mermaid
flowchart LR
    subgraph P1["S1"]
      A["Alice"]
    end
    subgraph P2["S2"]
      B["Bình"]
      D["Dung"]
    end
    subgraph P3["S3"]
      C["Chi"]
      E["Em"]
    end
    A --> B
    A --> C
    B --> D
    C --> E
~~~

Các bước logic:

1. Tra danh sách hàng xóm trực tiếp của Alice.
2. Nhận ID các đỉnh thuộc frontier bước 1.
3. Xác định shard sở hữu từng đỉnh frontier.
4. Đọc adjacency của các đỉnh này, có thể gửi RPC sang S2 và S3.
5. Hợp nhất, bỏ trùng ứng viên, lọc Alice và người đã được theo dõi.
6. Xếp hạng kết quả và chỉ trả số lượng cần thiết.

Bước 4 tạo khác biệt lớn. Nếu hàng xóm của Alice cùng shard S1, traversal có thể xử lý tương đối cục bộ. Nếu frontier trải trên nhiều shard, coordinator phải thực hiện fan-out; nếu dữ liệu ở vùng địa lý xa, từng vòng frontier còn chịu WAN latency.

### 6.1. Frontier phình theo số hop

Với `d` là số hàng xóm trung bình, một phép duyệt không giới hạn có thể tạo số đường đi bậc `k` xấp xỉ `d^k` trong trường hợp đơn giản không xét trùng lặp:

\[
\text{Số đường đi tiềm năng sau }k\text{ hop}\approx d^k
\]

Nếu trung bình mỗi đỉnh có 100 hàng xóm:

| Độ sâu | Số đường đi tiềm năng theo mô hình thô | Rủi ro |
|---|---:|---|
| 1 hop | 100 | Thường nhỏ |
| 2 hop | 10.000 | Cần lọc, giới hạn kết quả trung gian |
| 3 hop | 1.000.000 | Fan-out lớn; có thể quá đắt cho API tương tác |
| 4 hop | 100.000.000 | Khó đáp ứng độ trễ yêu cầu nếu duyệt tự do |

Đây là **số đường đi tiềm năng**, không phải số đỉnh duy nhất; đồ thị thực có chu trình và đỉnh trùng, còn thuật toán có thể cắt nhánh, deduplicate và áp hạn mức. Ngược lại, một supernode có bậc hàng triệu làm số lần mở rộng còn lớn hơn mô hình theo trung bình. Do đó giới hạn `maxDepth`, `maxVisitedVertices`, `maxEdges` và ngân sách thời gian không chỉ là tối ưu mà còn là bảo vệ tài nguyên.

### 6.2. Batching và fan-out

Nếu frontier có 1.000 đỉnh phân bố trên 8 shard, hệ thống không nhất thiết cần **1.000 RPC**. Có thể nhóm các yêu cầu theo shard, gửi song song 8 batch, rồi merge kết quả.

Tuy nhiên, giảm số round trip không làm mất tổng dữ liệu phải truyền; còn cần kiểm soát response lớn, hàng đợi tại shard và tình huống **straggler** (một shard chậm khiến cả truy vấn phải chờ). Khi nhiều traversal đồng thời đều gửi batch sang cùng một shard nóng, độ trễ p99 có thể tăng mạnh dù p50 chưa thay đổi nhiều.

## 7. Tính chi phí của một quan hệ xuyên vùng

Chi phí mạng gồm ít nhất hai phần khác nhau: **độ trễ cố định của một lần trao đổi** và **thời gian chuyển số byte dữ liệu**. Một cách ước lượng định tính:

\[
T_{\text{remote}}\approx T_{\text{RTT}}+
\frac{\text{bytes transferred}}{\text{effective bandwidth}}+
T_{\text{queue}}+T_{\text{server}}
\]

Với một traversal nhiều vòng phụ thuộc nhau:

\[
T_{\text{traversal}}\approx
\sum_{\text{frontier rounds}}\max_{\text{RPC song song trong vòng}}T_{\text{RPC}}
+T_{\text{merge}}+T_{\text{application}}
\]

Các công thức này **không phải mô hình hiệu năng chính xác** của mọi engine; chúng giúp phân biệt latency, throughput, queue và độ sâu phụ thuộc. Nếu round 2 chỉ biết hàng xóm sau khi round 1 xong, hai vòng không thể hoàn toàn chồng lên nhau, dù các RPC **trong cùng một vòng** có thể song song.

### 7.1. Ví dụ độ trễ minh họa

Giả sử môi trường thử có các số đo/giá trị **giả định**:

- Một RPC nội vùng với payload nhỏ: 1–3 ms.
- Một RPC sang vùng địa lý xa: 40–70 ms.
- Một phép duyệt cần ba vòng mở rộng frontier theo thứ tự.
- Mỗi vòng có nhiều RPC song song; phải đợi kết quả cần thiết của vòng trước.

Trong trường hợp lý tưởng chỉ xét khoảng RTT, ba vòng remote có thể đã đóng góp **120–210 ms** trước khi tính queue, CPU, dữ liệu trả, timeout và retry. Nếu cùng các vòng xử lý cục bộ, phần mạng cố định có thể nhỏ hơn nhiều. Đây không phải cam kết rằng mọi request xuyên vùng đều có đúng thời gian đó; RTT, số vòng, cách prefetch và cache phụ thuộc triển khai.

Một truy vấn chỉ có **một bước từ A đến B** có thể đắt nếu B ở vùng xa và thuộc tính của B không có bản sao cục bộ. Ngược lại, hàng trăm cạnh cross-partition trong cùng datacenter đôi khi được batch và thực hiện nhanh hơn một chuỗi ba round trip WAN phụ thuộc nhau.

### 7.2. Chi phí không chỉ là latency

Truyền dữ liệu xuyên vùng còn có thể tạo:

- **Băng thông và egress:** chi phí tiền hoặc quota theo byte ra khỏi region/VPC/provider.
- **Serialization:** mã hóa ID, thuộc tính và danh sách lân cận thành request/response.
- **Tail latency:** chỉ một shard chậm có thể kéo dài toàn bộ query chờ merge.
- **Backpressure:** frontier lớn đẩy nhiều request về một nhóm node.
- **Retry amplification:** lỗi mạng làm cùng đường duyệt bị gọi nhiều lần.
- **Bản sao và đồng bộ:** khi một cạnh/đỉnh cập nhật, dữ liệu liên quan có thể phải được propagate.
- **Ràng buộc vị trí dữ liệu:** một số thuộc tính không được phép sao chép sang vùng khác.

Do vậy “giảm số cạnh xuyên vùng” chỉ là một phần của mục tiêu. Cần đo **remote RPC per query, remote bytes, vùng truy cập, p95/p99, tỷ lệ timeout và chi phí đồng bộ**.

## 8. So sánh các cách chia đồ thị

Không có partition key tương đương dùng chung cho mọi đồ thị. Có thể cân nhắc nhiều họ chiến lược, sau đó đo theo workload:

| Chiến lược | Cách hoạt động | Điểm thuận lợi | Hạn chế cần kiểm tra |
|---|---|---|---|
| Hash theo ID đỉnh | `shard = hash(vertexId) % N` hoặc định tuyến tương đương | Đơn giản, thường phân bố số đỉnh khá đều | Quan hệ cộng đồng dễ bị cắt rộng |
| Range theo ID/khóa | Các miền giá trị vào các shard cụ thể | Tốt nếu truy vấn/range trùng cách chia | Lệch tải nếu dữ liệu không đều hoặc ID tăng đơn điệu |
| Theo tenant | Đặt phần lớn đồ thị một tenant cùng vùng/shard | Hữu ích với đồ thị nhiều tenant độc lập | Tenant lớn gây mất cân bằng; không hỗ trợ tốt liên tenant |
| Theo cộng đồng | Gom các đỉnh kết nối dày vào cùng shard | Có thể giảm cross-shard traversal | Tốn công phân vùng, cần cập nhật khi graph đổi |
| Theo địa lý | Đặt đỉnh gần nơi truy cập phổ biến hoặc nơi dữ liệu phải cư trú | Giảm WAN cho truy vấn mang tính địa phương | Quan hệ xuyên địa lý và người dùng di chuyển gây đánh đổi |
| Theo đỉnh nóng/cạnh | Chia adjacency của hub qua nhiều shard | Giảm tải tập trung | Đọc toàn bộ hub và consistency phức tạp |
| Hybrid / workload-aware | Kết hợp tenant, cộng đồng, mức nóng, replica | Tối ưu gần với truy vấn thực tế | Routing, rebalancing và vận hành khó hơn |

Hash cho phép bắt đầu đơn giản, nhưng xác suất cạnh nội shard giữa các đỉnh gán gần độc lập vào `N` shard cân bằng thường chỉ xấp xỉ `1/N`. Phần lớn cạnh có thể bị cắt nếu cộng đồng không được bảo toàn. Đây là phân tích xác suất trong điều kiện gán độc lập; không phản ánh mọi hàm hash hay đồ thị.

Ngược lại, mô hình theo cộng đồng có thể giữ phần lớn cạnh trong shard, nhưng phải giải quyết trường hợp cộng đồng lớn vượt tài nguyên một máy, hoặc hai cộng đồng thường được truy vấn chung nhưng lại bị đặt ở hai vùng khác nhau.

## 9. Đặt dữ liệu theo truy vấn, không chỉ theo cạnh

Nếu 80% truy vấn xuất phát từ một người dùng và đi 1–2 hop trong cộng đồng, chiến lược gom cộng đồng có thể rất phù hợp. Nhưng nếu 80% truy vấn tìm đường từ tài khoản đáng ngờ đến bất kỳ thiết bị đã dùng trên toàn hệ, đặt theo tenant hay quốc gia có thể tạo nhiều edge cut, vì hành vi gian lận thường xuyên qua ranh giới.

Ví dụ hệ phát hiện gian lận:

~~~text
(Account A) --USES--> (Device X) <--USES-- (Account B)
     |                                         |
     +-- TRANSFER_TO --> (Account C) <---------+
                           |
                          USES
                           v
                        (Device Y)
~~~

Q1: “Thiết bị X đang được bao nhiêu tài khoản dùng?” xuất phát từ `Device X`.

Q2: “Các tài khoản trong hai hop quanh Account A có chia sẻ thiết bị không?” xuất phát từ `Account A` và mở rộng sang `Device`.

Q3: “Có chuỗi chuyển tiền nào nối A tới C trong tối đa bốn hop?” là traversal theo loại cạnh và chiều cụ thể.

Một chiến lược đặt Account theo tenant và Device theo ID có thể tối ưu một loại query nhưng tạo chi phí cho loại khác. Hơn nữa, một thiết bị phổ biến được dùng chung bởi hàng nghìn tài khoản có thể là **supernode**.

Các quyết định cần ghi thành **access-pattern matrix**:

| Query | Đỉnh bắt đầu | Cạnh duyệt | Độ sâu | Filter | Giới hạn/độ trễ mong muốn |
|---|---|---|---|---|---|
| F1 | Device ID | `USED_BY` | 1 | Tài khoản còn hiệu lực | Trả 100 gần nhất |
| F2 | Account ID | `USES` rồi `USED_BY` | 2 | Loại thiết bị, khoảng thời gian | p95 mục tiêu |
| F3 | Account ID | `TRANSFER_TO` | ≤4 | Rủi ro và thời gian | Hạn số đỉnh đã thăm |
| F4 | Tenant ID | Toàn bộ graph của tenant | Toàn đồ thị | Tổng hợp | Chạy job phân tích |

Không có lý do kỹ thuật nào bảo đảm một bố trí đỉnh/cạnh sẽ tốt cho cả F1–F4. Hãy chọn theo đường quan trọng và có phương án riêng cho truy vấn phân tích.

## 10. Một cạnh được lưu một lần hay nhiều lần?

Nếu hệ tự xây tầng graph trên key–value/document store, có thể dùng bảng adjacency theo đỉnh nguồn:

~~~text
out:A -> [B, C, D]
out:B -> [C]
out:C -> [E]
~~~

Đường `A -> B` dễ đọc từ `out:A`. Muốn tìm tất cả đỉnh có cạnh **đến** B lại cần chỉ mục ngược hoặc đọc rộng. Một phương án là giữ cả hai chiều:

~~~text
out:A -> [B, C, D]
in:B  -> [A, ...]
~~~

Tăng tốc đọc hai chiều nhưng tạo **hai đường ghi**. Khi thêm cạnh `A -> B`, hệ phải giữ `out:A` và `in:B` đồng bộ theo yêu cầu nghiệp vụ. Nếu chúng nằm trên hai shard hoặc hai region, cập nhật không còn là thao tác đơn giản trên một bản ghi.

Một mô hình có ID cạnh ổn định:

~~~json
{
  "edgeId": "follows:a:b",
  "source": "a",
  "target": "b",
  "type": "FOLLOWS",
  "createdAt": "2026-11-14T09:00:00Z",
  "version": 3
}
~~~

Có thể chọn **một bản cạnh có thẩm quyền** rồi tạo các projection phục vụ `out`/`in`, hoặc dùng transaction được sản phẩm hỗ trợ nếu yêu cầu cập nhật nguyên tử. Khi chọn eventual consistency, API phải chấp nhận và xử lý khoảng thời gian một phía đã thấy cạnh mà phía kia chưa thấy.

### 10.1. Thêm và xóa quan hệ

Câu hỏi về đúng đắn:

1. Nếu người dùng theo dõi B thành công, B có phải thấy ngay follower mới hay không?
2. Nếu A hủy theo dõi B, kết quả recommendation có được tạm thấy cạnh cũ?
3. Nếu A bị xóa, có cần xóa mọi cạnh kề trong một giao dịch hay được thực hiện theo job?
4. Nếu cập nhật đầu ra thành công nhưng cập nhật đầu vào thất bại, cơ chế retry nào không tạo cạnh trùng?
5. Nếu hai region cùng cập nhật trạng thái cạnh, quy tắc xác định phiên bản hoặc xung đột là gì?

Đối với các quyết định nhạy cảm như chặn tài khoản, chuyển tiền và quyền truy cập, độ trễ đồng bộ quan hệ có thể không chấp nhận được. Không nên lấy tính sẵn sàng của recommendation làm tiêu chuẩn cho mọi loại cạnh.

## 11. Replication, cache và locality của hàng xóm

Có ba hướng giảm nhu cầu hỏi qua mạng:

1. **Đặt cùng nơi (colocation):** đưa đỉnh hay được duyệt cùng nhau vào một shard hoặc vùng.
2. **Sao chép (replication):** giữ bản sao của dữ liệu ở vùng cần đọc.
3. **Cache kết quả/adjacency:** lưu lân cận hoặc kết quả truy vấn phổ biến gần nơi phát sinh request.

Mỗi cách giảm một loại chi phí và tạo một loại đánh đổi.

| Phương án | Tiết kiệm được gì? | Phải quản lý gì? |
|---|---|---|
| Đặt theo cộng đồng | Bớt remote traversal giữa các đỉnh trong cộng đồng | Repartition khi cộng đồng thay đổi, cân bằng tải |
| Replica read ở vùng địa phương | Bớt RTT WAN trong một số đường đọc | Replication lag, consistency, quyền truy cập vùng |
| Cache adjacency | Giảm lookup cạnh lặp lại | TTL/invalidation, cache stampede, bộ nhớ |
| Cache kết quả 2-hop | Tránh tính lại traversal đắt | Invalidation khi nhiều cạnh thay đổi |
| Materialized projection | Trả tập kết quả phổ biến đã tính sẵn | Xây dựng, replay, đối soát và độ mới dữ liệu |
| Prefetch/batch frontier | Giảm số vòng RPC nhỏ | Tăng lượng dữ liệu dự đoán và bộ nhớ tạm |

Một danh sách 20 bạn bè phổ biến có thể cache dễ. Một kết quả “tất cả đường đi tối đa bốn hop từ tài khoản này” có thể thay đổi vì rất nhiều cạnh, nên cache và invalidation phức tạp hơn đáng kể.

**Cache không tự giải quyết tính đúng đắn.** Với quyền truy cập, chặn tài khoản hoặc kiểm soát gian lận, kết quả cũ có thể gây hậu quả nghiệp vụ. Cần chỉ rõ loại quan hệ nào cho phép stale data và tối đa bao lâu.

## 12. Khi edge đi qua vùng địa lý xa

Giả sử hệ có hai vùng địa lý:

~~~text
Region VN                      Region EU
  Shard A                         Shard B
  (User V1) --- FOLLOWS -------> (User E1)
  (User V2)                       (User E2)
~~~

Nếu request của V1 được xử lý tại VN và cần lấy metadata/cạnh kề của E1 tại EU, hệ có thể tạo RPC WAN. Có các cách tiếp cận:

- **Gọi trực tiếp EU:** ít bản sao hơn, nhưng phụ thuộc latency và availability WAN.
- **Đọc replica E1 tại VN:** nhanh hơn khi bản sao hợp lệ, nhưng phải chấp nhận hoặc kiểm soát lag.
- **Cache một phần adjacency E1 tại VN:** tiết kiệm remote read lặp lại, cần chính sách hết hạn.
- **Đặt các nhóm quan hệ phổ biến gần nhau:** giảm cross-region cho workload chính, nhưng thay đổi vị trí dữ liệu có ràng buộc vận hành/pháp lý.
- **Tách truy vấn:** trả kết quả cục bộ nhanh, bổ sung dữ liệu xuyên vùng bất đồng bộ nếu giao diện/nghiệp vụ cho phép.

Các yếu tố địa lý cần xét cụ thể gồm: độ trễ liên vùng, phí egress, mục tiêu khôi phục, quy định nơi cư trú của dữ liệu, định tuyến request, quyền thao tác và trường hợp mất kết nối cả vùng.

### 12.1. Đọc gần người dùng hay gần dữ liệu?

Đặt API tại region của người dùng không bảo đảm query nhanh nếu hầu hết cạnh/đỉnh cần đọc ở region khác. Ngược lại, chuyển toàn bộ request sang region chứa dữ liệu có thể giảm RPC graph nhưng tăng latency giữa client và API. Phải đo **end-to-end latency** từ client đến kết quả, không chỉ thời gian giữa graph engine và storage.

Khi routing phức tạp, đôi khi cần coordinator chọn vị trí thực thi gần **phần lớn frontier** hoặc vùng sở hữu dữ liệu chính, thay vì luôn cố định một gateway.

### 12.2. Một lần ghi xuyên vùng đòi hỏi gì?

Nếu một quan hệ được ghi ở region VN rồi cần xuất hiện ở EU, có thể có các hợp đồng:

- **Ghi cục bộ, replicate bất đồng bộ:** ghi nhanh hơn, chấp nhận một khoảng lag và nguy cơ khác biệt tạm thời.
- **Ghi có xác nhận nhiều replica/region:** tăng điều phối và latency, mức bảo đảm phụ thuộc hệ và cấu hình.
- **Mô hình một vùng ghi chủ đạo:** định tuyến ghi về owner, đơn giản hóa xung đột nhưng có WAN và rủi ro vùng owner.
- **Nhiều vùng có thể ghi:** tăng tính sẵn sàng/địa phương nhưng phải thiết kế conflict resolution và bất biến.

Không được gán các tên gọi “strong consistency”, “linearizable” hay “exactly once” chỉ dựa trên số replica. Cần đọc bảo đảm chính thức của sản phẩm, đặt consistency ở đường đọc/ghi và thử lỗi thật.

## 13. Khi partition và replica bị lỗi

Một traversal có thể bắt đầu thành công ở S1 rồi thất bại tại S3. Hệ thống phải xác định trả lỗi, trả kết quả từng phần hay thử replica khác.

~~~mermaid
flowchart TD
    A["Request traversal 2-hop"] --> B["Đọc frontier từ S1"]
    B --> C["Gọi S2 và S3"]
    C --> D{"S3 timeout?"}
    D -->|Không| E["Merge đủ kết quả"]
    D -->|Có| F{"Có replica / chính sách retry?"}
    F -->|Có| G["Thử đường dự phòng với timeout giới hạn"]
    F -->|Không| H["Trả lỗi hoặc kết quả partial có nhãn rõ"]
    G --> I{"Đủ kết quả tin cậy?"}
    I -->|Có| E
    I -->|Không| H
~~~

Không thể tự ý trả “không có đường liên hệ” khi một shard chứa đỉnh liên quan chưa phản hồi. Đối với truy vấn phát hiện gian lận, **thiếu dữ liệu** phải được phân biệt với **không tồn tại đường đi**. Với gợi ý bạn bè, kết quả partial có thể chấp nhận được khi được sản phẩm cho phép và được đánh dấu/có cơ chế xử lý rõ ràng.

Timeout và retry cần giới hạn theo **ngân sách toàn request**, ví dụ request có deadline 300 ms thì không thể mỗi hop retry ba lần với timeout 300 ms. Mỗi lần retry có thể tăng tải lên các shard đang quá tải; dùng backpressure, budget và circuit breaker phù hợp.

## 14. Thực hành truy vấn đồ thị theo lân cận và nhiều hop

Để có ngôn ngữ cụ thể, dùng cú pháp **Cypher** cho mô hình logic mạng xã hội. Những câu dưới đây minh họa biểu thức truy vấn; khả năng phân phối thực sự phải được xác nhận trên graph engine được chọn. Viết Cypher được không có nghĩa graph engine sẽ tự chia các đỉnh giữa nhiều máy.

### 14.1. Tìm người Alice theo dõi

~~~cypher
MATCH (u:User {id: $userId})-[:FOLLOWS]->(friend:User)
RETURN friend.id AS friendId
LIMIT 50;
~~~

Đường truy cập mong muốn: định vị Alice bằng `User.id`, lấy adjacency cạnh đi ra và đọc những thuộc tính cần thiết của các friend. Nếu ID friend nằm trong cạnh hoặc projection adjacency, một số bước có thể được phục vụ cục bộ; nếu cần profile friend không có tại nơi truy vấn, có thể phải gọi shard owner.

### 14.2. Gợi ý bạn của bạn

~~~cypher
MATCH (u:User {id: $userId})-[:FOLLOWS]->(f:User)
      -[:FOLLOWS]->(candidate:User)
WHERE candidate <> u
  AND NOT EXISTS {
    MATCH (u)-[:FOLLOWS]->(candidate)
  }
RETURN candidate.id AS candidateId,
       count(DISTINCT f) AS mutualFollowees
ORDER BY mutualFollowees DESC
LIMIT 20;
~~~

Query có hai bước mở rộng và một bước loại ứng viên đã được theo dõi. Mỗi bước cần kiểm tra **tập frontier**. Nếu Alice theo dõi 5.000 tài khoản, trong đó có supernode, lượng kết quả trung gian có thể rất lớn dù cuối cùng chỉ trả 20 người.

`LIMIT 20` ở cuối **không tự bảo đảm engine chỉ duyệt 20 ứng viên**; muốn giới hạn công việc, phải hiểu kế hoạch thực thi, index, thứ tự mở rộng, các phép lọc có thể đẩy xuống và cách planner xử lý top-k.

### 14.3. Duyệt có giới hạn chiều sâu trong phát hiện gian lận

Truy vấn minh họa quan hệ tài khoản dùng chung thiết bị:

~~~cypher
MATCH (a:Account {id: $accountId})-[:USES]->(d:Device)
      <-[:USES]-(other:Account)
WHERE other <> a
RETURN DISTINCT other.id AS relatedAccountId
LIMIT 100;
~~~

Về mặt logic nó là 2-hop. Nếu `Device` là supernode, hệ có thể gặp rất nhiều kết quả trung gian. Cần bổ sung filter theo thời gian, loại thiết bị, tiêu chí rủi ro và ngân sách duyệt từ nghiệp vụ. Trong phân tán, việc đọc adjacency từ `Device` có thể trở thành nút cổ chai hoặc fan-out sang rất nhiều shard.

### 14.4. Khả năng tối ưu phụ thuộc engine

Các sản phẩm có thể hỗ trợ index điểm bắt đầu, query plan, thống kê cardinality, distributed traversal, locality-aware execution, cache hoặc projection khác nhau. Không nên so sánh hai graph DB chỉ bằng việc cú pháp query ngắn hơn. Phải đo **số đỉnh/cạnh đã mở rộng, số remote request, bytes truyền, số round phụ thuộc và độ trễ thực**.

## 15. Tránh N+1 và những frontier quá rộng

Một sai lầm triển khai phổ biến:

~~~text
Đọc 500 người Alice theo dõi.
for mỗi người:
    gọi remote API để lấy danh sách người họ theo dõi.
Sau đó hợp nhất.
~~~

Nếu mỗi lần gọi mạng mất vài chục millisecond, serial loop có thể rất chậm. Gửi 500 request song song không giải quyết hoàn toàn vấn đề vì có thể gây áp lực connection pool và shard nóng.

Cách tiếp cận:

1. **Lấy frontier bằng một truy vấn**, giới hạn số lượng theo yêu cầu.
2. **Nhóm ID theo shard owner** nếu tầng API/engine cho phép.
3. **Batch** các truy vấn hàng xóm và áp dụng mức song song tối đa.
4. **Lọc sớm** theo loại cạnh, thời gian, thuộc tính và quyền truy cập.
5. **Deduplicate sớm** để không duyệt lại cùng đỉnh nhiều lần khi không cần.
6. **Chặn supernode** hoặc dùng xử lý riêng nếu nó tạo quá nhiều nhánh.
7. **Dừng theo ngân sách** số đỉnh/cạnh, dữ liệu trả và deadline.
8. **Đo cả phần không trả về**: số trung gian đã duyệt trước khi lấy `LIMIT 20`.

Nếu một query đòi hỏi tính mọi đường đi giữa hàng triệu node, nó có thể là **bài toán phân tích ngoại tuyến** hơn là API đồng bộ. Với truy vấn tương tác, hãy yêu cầu nghiệp vụ chỉ rõ độ sâu, loại cạnh và cách cắt nhánh.

## 16. Tính đúng đắn khi quan hệ thay đổi đồng thời

Đồ thị phân tán không đứng yên trong lúc được duyệt. Giả sử khi đang đọc G2, Alice bỏ theo dõi Bình và Chi vừa thêm quan hệ mới. Kết quả có thể được ghép từ các snapshot khác nhau nếu engine không bảo đảm một góc nhìn nhất quán cho toàn traversal.

Cần hỏi:

- Query được phép dùng **eventual consistency** hay phải là snapshot tại một thời điểm?
- Có yêu cầu **read-your-writes** sau khi thêm/xóa cạnh không?
- Xóa đỉnh có cần xóa mọi cạnh kề trước khi một truy vấn khác trả kết quả?
- Khi hai vùng cùng cập nhật cùng cạnh, phải áp dụng thứ tự và conflict resolution nào?
- Một truy vấn xác nhận “không có quan hệ” có được kết luận như vậy nếu một shard timeout?

Với recommendation, một số kết quả cũ trong vài giây có thể chấp nhận. Với quyền truy cập, quy tắc chặn hoặc giao dịch, có thể cần mức nhất quán chặt hơn. Bảo đảm cần được ghi thành **hợp đồng nghiệp vụ cho từng đường truy cập**, không dùng một thiết lập chung mà không hiểu chi phí.

### 16.1. Khóa định danh và ràng buộc duy nhất

Nếu quan hệ `FOLLOWS` không cho phép trùng cùng cặp nguồn–đích, có thể dùng định danh ổn định `follows:<sourceId>:<targetId>` trong model triển khai riêng. Tuy nhiên, unique key ở một shard không tự bảo đảm unique toàn cụm nếu cùng cạnh được ghi vào hai vùng khác nhau mà không có cơ chế phối hợp.

Khi xóa/hủy quan hệ, phải xác định cách xử lý bản sao, cache, projection và event đến trễ. Một sự kiện “thêm cạnh” đến sau “xóa cạnh” có thể hồi sinh quan hệ nếu không dùng phiên bản, thứ tự sự kiện hoặc cơ chế chống xung đột phù hợp.

## 17. Dữ liệu nhiều tenant và ranh giới truy cập

Graph đa tenant thường có các mối liên hệ **trong tenant** và đôi khi **giữa tenant**. Đặt theo tenant có thể giảm cross-shard đối với truy vấn nội bộ, nhưng không được coi partitioning là cơ chế phân quyền.

Ví dụ:

~~~text
Tenant A: Account A1 -> Device Shared
Tenant B: Account B1 -> Device Shared
~~~

Một hệ phát hiện gian lận có thể cần quan hệ qua `Device Shared`, nhưng ứng dụng của Tenant A không nhất thiết có quyền xem tài khoản của Tenant B. Truy vấn cross-tenant phải qua hợp đồng dữ liệu riêng: những thuộc tính nào được chia sẻ, kết quả có bị ẩn danh hay chỉ trả điểm rủi ro, ai được phép yêu cầu và dấu vết kiểm toán.

Ràng buộc vị trí dữ liệu cũng quan trọng. Nếu dữ liệu cá nhân chỉ được lưu ở một vùng theo chính sách, việc **sao chép đỉnh hoặc thuộc tính đầy đủ** sang vùng khác để tăng locality có thể vi phạm yêu cầu. Có thể cần projection tối thiểu, token hóa định danh hoặc xử lý phân tán trả về kết quả đã giới hạn. Những giải pháp đó làm thay đổi khả năng truy vấn và phải được cân nhắc ngay từ bước thiết kế.

## 18. Cân bằng lại shard khi đồ thị phát triển

Chiến lược phân phối từng tốt ở thời điểm ban đầu có thể suy giảm:

- Một cộng đồng lớn nhanh và làm shard chứa nó quá tải.
- Một user từ thường trở thành supernode.
- Mẫu truy vấn chuyển từ 1-hop sang 3-hop.
- Người dùng truy cập chủ yếu từ vùng địa lý khác.
- Thêm tenant hoặc tăng số shard từ 4 lên 16.
- Thuộc tính đỉnh/cạnh và retention làm dung lượng tăng không đều.

**Repartitioning** là quá trình chuyển trách nhiệm lưu/truy cập dữ liệu giữa các shard. Nó không chỉ là copy đỉnh: cần chuyển cạnh hoặc adjacency, cập nhật routing metadata, xử lý ghi đang diễn ra và tránh trả kết quả sai trong thời gian chuyển đổi.

Một quy trình thiết kế có thể gồm:

~~~text
Lập partition map mới
   |
   v
Xác định đỉnh/cạnh cần di chuyển
   |
   v
Copy snapshot và đồng bộ thay đổi phát sinh
   |
   v
Đối chiếu dữ liệu, quan hệ và version
   |
   v
Chuyển routing có kiểm soát
   |
   v
Theo dõi lỗi, độ trễ và xử lý bản sao cũ
~~~

Cơ chế thực tế phụ thuộc engine, một số sản phẩm tự động rebalance còn một số yêu cầu thao tác ứng dụng. Phải có khả năng rollback hoặc phục hồi, tránh trường hợp trong lúc chuyển shard, query thấy đỉnh nhưng không thấy cạnh.

**Duy trì locality có chi phí lâu dài.** Cộng đồng của đồ thị thay đổi khi người dùng kết bạn, chuyển vùng hay thực hiện giao dịch; muốn luôn giảm edge cut thì có thể phải chuyển dữ liệu thường xuyên. Lợi ích truy vấn phải được so với chi phí migration và ảnh hưởng ghi.

## 19. Graph OLTP và graph analytics khác nhau

Không phải mọi workload đồ thị đều được tối ưu bằng cùng cấu trúc phân phối.

**Online traversal (OLTP):** đọc vài hop từ một hoặc vài đỉnh bắt đầu, có deadline nhỏ; thường cần index tốt để tìm điểm xuất phát và locality của lân cận.

**Graph analytics:** PageRank, connected components, label propagation, community detection hoặc tính centrality; thường duyệt khối lượng lớn cạnh qua nhiều vòng lặp, có thể phù hợp với hệ xử lý phân tán theo batch, message passing và snapshot.

Ví dụ thuật toán PageRank cần nhiều vòng cập nhật điểm từ lân cận. Dù mỗi cạnh không cần request riêng, **tổng số thông điệp qua cut edges** vẫn có thể rất lớn trong mỗi vòng.

Nếu hệ chỉ cần recommendation dựa trên bảng điểm tính trước, việc phục vụ điểm từ một projection có thể phù hợp hơn chạy PageRank mỗi khi user mở trang. Ngược lại, một truy vấn tìm đường đi mới phát sinh có thể cần duyệt trực tuyến nếu chưa có kết quả tính trước.

| Nhu cầu | Đặc điểm quan trọng | Hướng suy nghĩ |
|---|---|---|
| Lấy 20 người theo dõi | 1-hop, latency thấp | Adjacency theo đỉnh, paging, cache |
| Gợi ý qua bạn của bạn | 2-hop, frontier lớn | Locality, giới hạn candidate, batch, top-k |
| Phát hiện kết nối rủi ro | 2–4 hop, filter theo loại cạnh | Bounding, freshness, đầy đủ kết quả |
| PageRank toàn hệ | Nhiều vòng trên nhiều cạnh | Graph analytics engine, partition communication, checkpoint |
| Đếm quan hệ tổng theo vùng | Tổng hợp hoặc histogram | Materialized aggregate/columnar analytics |
| Duyệt theo sự kiện cập nhật | Graph thay đổi liên tục | Stream update, index/adjacency maintenance |

Vì vậy, trước khi mua hay thiết kế một distributed graph database, cần xác định engine phải phục vụ giao dịch tương tác, phân tích toàn đồ thị hay cả hai bằng những thành phần tách biệt.

## 20. Thực nghiệm mô phỏng phân vùng trước khi triển khai cụm thật

Có thể học tác động của **edge cut** bằng một mô phỏng nhỏ sử dụng Python tiêu chuẩn, không cần cluster. Mô phỏng này tính tỷ lệ cạnh xuyên shard và độ lệch số đỉnh/cạnh, **không đo latency mạng thực**.

Tập dữ liệu giả lập:

- 10.000 đỉnh thuộc 20 cộng đồng.
- 8 shard.
- Mỗi đỉnh có một số cạnh đi ra; một số nhỏ là hub.
- Phần lớn cạnh đi tới đỉnh cùng cộng đồng.
- So sánh **hash theo ID** và **gán cùng cộng đồng về một shard**.

Lưu thành `graph_partition_lab.py`:

~~~python
from collections import Counter
from random import Random

SEED = 20261114
N = 10_000
COMMUNITIES = 20
SHARDS = 8
GROUP_SIZE = N // COMMUNITIES

rng = Random(SEED)

def community(v):
    return min(v // GROUP_SIZE, COMMUNITIES - 1)

def hash_shard(v):
    # Ánh xạ ổn định minh họa, không dùng Python hash() thay đổi theo process.
    return (v * 2654435761) % SHARDS

def community_shard(v):
    return community(v) % SHARDS

def random_vertex_in_community(group):
    begin = group * GROUP_SIZE
    end = min(begin + GROUP_SIZE, N)
    return rng.randrange(begin, end)

edges = []

for source in range(N):
    # 1% đỉnh là hub: mỗi hub có nhiều quan hệ hơn.
    degree = rng.randint(100, 250) if source % 100 == 0 else rng.randint(3, 12)

    for _ in range(degree):
        if rng.random() < 0.85:
            target_group = community(source)
        else:
            target_group = rng.randrange(COMMUNITIES)

        target = random_vertex_in_community(target_group)

        if target == source:
            continue

        edges.append((source, target))

def inspect(name, shard_of):
    vertex_counts = Counter(shard_of(v) for v in range(N))
    cut_edges = 0
    edge_load = Counter()

    for source, target in edges:
        s = shard_of(source)
        t = shard_of(target)
        edge_load[s] += 1
        if s != t:
            cut_edges += 1

    ratio = cut_edges / len(edges)
    print(f"\n{name}")
    print(f"edges={len(edges)}, cut_edges={cut_edges}, cut_ratio={ratio:.3%}")
    print("vertex_count_per_shard:", sorted(vertex_counts.items()))
    print("outgoing_edge_load:", sorted(edge_load.items()))
    print("max/min edge load:", max(edge_load.values()) / min(edge_load.values()))

inspect("hash by vertex", hash_shard)
inspect("community placement", community_shard)
~~~

Chạy:

~~~bash
python graph_partition_lab.py
~~~

### Cách diễn giải

Với dữ liệu giả lập có 85% quan hệ trong cùng cộng đồng, cách gán theo cộng đồng **có lý do** để tạo ít cut edges hơn hash độc lập theo ID. Tuy nhiên, 20 cộng đồng phân vào 8 shard không đều tuyệt đối; cộng đồng và hub có thể tạo độ lệch edge load. Kết quả in ra dùng để thảo luận hai mục tiêu cùng lúc: **locality và cân bằng tải**.

Khi thay `0.85` thành `0.20`, quan hệ giữa cộng đồng nhiều hơn; lợi ích gom theo cộng đồng có thể giảm. Khi tăng số hub hoặc tạo một cộng đồng lớn gấp 20 lần, chiến lược gom cộng đồng có thể không còn cân bằng.

Giới hạn của mô phỏng:

- Không mô phỏng replica, cache, network, consistency, persistence hay CPU.
- Coi một cạnh cắt là một đơn vị chi phí, trong khi thực tế RPC có thể batch.
- Không gán trọng số tần suất duyệt: cạnh hiếm và cạnh được đọc hàng nghìn lần được đếm như nhau.
- Chưa mô hình hóa write hotspots, thay đổi graph theo thời gian hoặc việc shard nằm ở hai region.

Vì vậy hãy dùng nó để **kiểm tra trực giác về partitioning**, rồi chuyển sang thực nghiệm trên engine cụ thể trước khi ra quyết định production.

## 21. Thực nghiệm trên cụm: đo traversal thay vì chỉ đếm cạnh

Khi có graph engine hỗ trợ phân tán thực sự, hãy thiết kế một benchmark cố định về dữ liệu, truy vấn và cấu hình.

### 21.1. Bộ dữ liệu

Một kế hoạch giả định:

| Thành phần | Giá trị khởi đầu để chuẩn bị thử |
|---|---|
| Đỉnh | 1 triệu User và 200 nghìn Device |
| Cạnh | 10 triệu FOLLOWS, 2 triệu USES |
| Cộng đồng | 100 nhóm, độ lớn lệch nhau |
| Hub | 0,1% đỉnh có degree cao |
| Phân vùng | 4, 8 rồi 16 shard |
| Vùng địa lý | Một region trước, sau đó hai region nếu hạ tầng cho phép |
| Dữ liệu biến động | 5% cạnh mỗi ngày được thêm/xóa trong bài mô phỏng |

Những số liệu này chỉ mô tả dữ liệu cần chuẩn bị, không phải mức “phải đạt” cho một graph database. Nếu môi trường học yếu, giảm quy mô nhưng giữ tính **lệch bậc, cộng đồng và các cạnh xuyên cộng đồng**.

### 21.2. Các truy vấn thử

| Workload | Đường truy cập | Mục tiêu quan sát |
|---|---|---|
| W1 | G1 1-hop từ user thường | Baseline locality và read latency |
| W2 | G1 từ supernode | Độ lớn adjacency, hot shard |
| W3 | G2 2-hop trong cộng đồng | Frontier, merge, edge cut |
| W4 | G2 2-hop xuyên cộng đồng | Cross-shard RPC và remote bytes |
| W5 | G4 2–3 hop qua Device | Hot Device và tính đúng đắn kết quả |
| W6 | Thêm/xóa FOLLOWS/USES | Write latency, lag, fan-out cập nhật |
| W7 | Cùng query nhưng remote region | RTT, egress, timeout, read consistency |
| W8 | Mất một shard/replica giữa traversal | Độ sẵn sàng và xử lý partial result |

### 21.3. Các chỉ số phải thu

Không nên dừng ở “query mất bao nhiêu ms”. Một bảng đo nên có:

| Nhóm | Chỉ số |
|---|---|
| Kết quả | Số đỉnh/cạnh tìm được, số kết quả sau lọc, tính đầy đủ |
| Độ trễ | p50, p95, p99, timeout, error rate, client end-to-end |
| Mức mở rộng | Hop thực tế, số frontier, số đỉnh/cạnh đã thăm, số lần deduplicate |
| Mạng | Remote RPC/query, RPC theo shard/region, byte truyền, egress |
| Cân bằng | Vertex/edge counts, CPU, RAM, hàng đợi, hot shard |
| Consistency | Replication lag, stale reads, lỗi cập nhật projection |
| Vận hành | Thời gian rebalance, thời gian phục hồi và tài nguyên bị tiêu thụ |
| Kinh tế | Bộ nhớ lưu, bản sao, transfer liên vùng và chi phí duy trì |

**Đếm cut edges không thay thế metric theo truy vấn.** Một phân hoạch có cut ratio 5% nhưng tất cả cạnh bị cắt lại nằm trên đường truy vấn G2 phổ biến có thể chậm hơn phân hoạch cut ratio 15% mà phần lớn cạnh cắt không được truy cập.

### 21.4. So sánh công bằng

1. Cố định phiên bản engine, loại máy, topology, dữ liệu, replication/consistency và cấu hình client.
2. Chạy warm-up, sau đó đo một khoảng đủ dài với concurrency và query mix đã định nghĩa.
3. Ghi **offered request rate** và **achieved throughput**; nếu load generator quá tải, không coi đó là năng lực hệ thống.
4. Thử các chính sách partition, giữ workload và dữ liệu càng giống nhau càng tốt.
5. Tăng concurrency và quy mô cạnh; quan sát p99 và các shard chậm thay vì chỉ trung bình.
6. Thử hot nodes, cross-community hops, cache cold/warm và tình huống thiếu replica có kiểm soát.
7. Đánh giá tác động write và rebalance, bởi phương án đọc tốt có thể cập nhật rất đắt.
8. Giải thích kết luận bằng phạm vi thử nghiệm và trade-off, không lấy một lần đo làm chân lý.

## 22. Một ví dụ phân tích chi phí hoàn chỉnh

Giả sử một request gợi ý bạn bè tạo ba frontier round và phải truy cập hai region. Có hai phương án:

**Phương án A — Hash theo ID:**

- Đỉnh phân bố khá đều trên 8 shard.
- Nhiều quan hệ trong cùng cộng đồng vẫn bị cắt.
- Mỗi query 2-hop thường gửi batch sang 6–8 shard.
- Ghi ít cần di chuyển cộng đồng; routing tương đối đơn giản.

**Phương án B — Gom cộng đồng:**

- Phần lớn quan hệ nội bộ được xử lý trong 1–2 shard.
- Query đi xuyên cộng đồng vẫn cần remote.
- Một cộng đồng cực lớn có nguy cơ tạo hot shard.
- Khi graph thay đổi, việc định vị lại đỉnh/cạnh và cân bằng tải tốn thêm công.

Giả sử một phép đo sau này thu được các số **minh họa**:

| Chỉ số giả định | A: Hash | B: Cộng đồng |
|---|---:|---:|
| Cut ratio | 76% | 14% |
| Remote RPC trung bình cho G2 | 9 | 3 |
| G2 p95 | 180 ms | 90 ms |
| G2 p99 | 390 ms | 310 ms |
| CPU của shard nóng nhất | 63% | 92% |
| Latency thêm cạnh p95 | 22 ms | 27 ms |
| Thời gian rebalance định kỳ | Thấp hơn | Cao hơn |

**Đây là bảng giả định để luyện diễn giải, không phải kết quả đo thật.** B nhìn có lợi rõ về G2 trung bình, nhưng shard nóng nhất chạm tải cao có thể khiến p99 xấu đi khi concurrency tăng. Nếu người dùng chỉ đánh giá cut ratio và p95, họ có thể bỏ qua rủi ro vận hành của cộng đồng quá lớn.

Một kết luận hợp lệ cần nói rõ: B tốt trong workload và cấu hình thử này, song cần xử lý supernode và kiểm chứng tại tải đỉnh trước khi triển khai. Có thể hybrid hoặc chia cộng đồng lớn thành nhiều phần, sau đó đo lại.

## 23. Khi nào cần đổi mô hình hoặc truy vấn?

Các dấu hiệu nên cân nhắc lại thiết kế:

- Traversal tương tác thường xuyên vượt nhiều shard trong mỗi hop.
- Kết quả chỉ cần top 20 nhưng engine phải mở hàng triệu cạnh trước khi lọc.
- Một supernode làm một shard nóng dù các shard còn lại rảnh.
- Cache/replica tạo độ trễ đồng bộ vượt mức nghiệp vụ cho phép.
- Một quan hệ phải cập nhật quá nhiều projection và thời gian ghi tăng mạnh.
- API gọi nhiều region chỉ để lấy vài thuộc tính mà có thể trả bằng projection phù hợp.
- Rebalance liên tục chuyển dữ liệu vì cộng đồng thay đổi nhanh.
- Graph analytics toàn hệ gây nghẽn graph OLTP phục vụ người dùng.

Hướng thay đổi có thể là giảm hop, lọc theo loại cạnh/thời gian sớm hơn, đổi partitioning, sao chép có giới hạn, tạo projection phục vụ query phổ biến hoặc tách workload phân tích sang hệ xử lý riêng. Mỗi thay đổi phải giữ rõ **nguồn dữ liệu có thẩm quyền, cách đồng bộ và tiêu chí đúng đắn**.

## 24. Bài thực hành tổng hợp

**Đề bài:** một ứng dụng chống gian lận có 2 triệu tài khoản, 300 nghìn thiết bị và các cạnh `USES`, `TRANSFERS_TO`. Tài khoản được chia theo tenant và region, nhưng một thiết bị có thể gắn với nhiều tài khoản khác tenant. Sản phẩm yêu cầu tìm các tài khoản chia sẻ thiết bị trong hai hop với p95 dưới 200 ms ở tải mục tiêu do nhóm tự đặt ra.

Hãy thực hiện:

1. **Mô hình hóa:** vẽ hai loại đỉnh và hai loại cạnh có hướng; xác định cạnh nào cần tra ngược, thuộc tính nào phải luôn mới.
2. **Viết query pattern:** một truy vấn 1-hop, một truy vấn 2-hop và một truy vấn 3-hop có filter theo thời gian. Giới hạn số đỉnh/cạnh tối đa và số kết quả.
3. **Chia dữ liệu:** so sánh hash theo Account ID, theo tenant/region và theo cộng đồng. Với mỗi cách, chỉ ra edge cut và hot-shard risk.
4. **Phân tích supernode:** có một thiết bị gắn với 100.000 tài khoản. Đề xuất cách xử lý và chi phí hợp nhất lân cận.
5. **Ước lượng WAN:** giả sử RTT liên vùng 50 ms, yêu cầu có hai vòng remote phụ thuộc nhau. Tính chi phí mạng tối thiểu gần đúng trong trường hợp không có cache, chưa tính CPU/queue.
6. **Đánh giá đúng đắn:** nếu cạnh `USES` mới chỉ được ghi tại vùng A, vùng B có được trả “không có kết nối” như một kết luận chắc chắn không? Đề xuất hợp đồng freshness.
7. **Đề xuất khả năng phục hồi:** một shard timeout ở hop thứ hai. API nên báo lỗi, trả partial hay retry trong tình huống phát hiện gian lận? Giải thích.
8. **Lập benchmark:** định nghĩa dữ liệu lệch, query mix, 4/8 shard, 1/2 region và những metric phải đo.
9. **Chọn mô hình:** nêu quyết định theo kết quả đo dự kiến và điều kiện khiến cần đo lại sau này.

### Câu hỏi tự kiểm tra

- Vì sao cut ratio thấp chưa chắc đồng nghĩa p99 thấp?
- Vertex partitioning và edge partitioning khác nhau ở việc phân tán một supernode thế nào?
- Tại sao ba vòng remote phụ thuộc nhau có thể đắt hơn mười RPC gửi song song trong một vòng?
- Khi graph có cộng đồng lớn, hash theo ID và community placement thường đánh đổi điều gì?
- Một bản sao adjacency tại region gần người dùng có thể trả kết quả sai trong tình huống nào?
- Vì sao chỉ `LIMIT 20` ở cuối truy vấn 2-hop không tự giới hạn số cạnh trung gian được duyệt?
- Repartition cần làm gì với các cập nhật xảy ra trong khi dữ liệu đang được chuyển?
- Khi mất kết nối một shard, tại sao “không tìm thấy đường đi” và “chưa thể xác định” phải khác nhau?
- Vì sao đường duyệt 1-hop và PageRank toàn hệ có thể cần chiến lược xử lý khác nhau?
- Ràng buộc dữ liệu theo khu vực ảnh hưởng thế nào đến quyết định sao chép đỉnh/cạnh sang region khác?

## 25. Kết nối thiết kế đồ thị với vận hành phân tán

Phân phối đồ thị là bài toán đồng thời của **quan hệ**, **tải**, **vị trí dữ liệu** và **độ đúng đắn**. Một partitioning hiệu quả phải đặt gần nhau những dữ liệu thường được duyệt chung, nhưng vẫn giữ được cân bằng tài nguyên. Cạnh xuyên shard có thể tạo RPC và thao tác merge; khi những RPC ấy đi xuyên vùng địa lý, latency WAN, chi phí truyền và trạng thái replica càng đáng kể. Supernode, nhiều hop và frontier lớn làm những chi phí này dễ tăng đột biến.

Khi thiết kế, hãy bắt đầu từ **truy vấn nghiệp vụ và giới hạn độ sâu**, đánh giá distribution của degree và cộng đồng, chọn chiến lược placement phù hợp, rồi thực nghiệm bằng **remote hops, bytes, p95/p99, hot shard, write latency, replication lag và chi phí rebalance**. Kết quả tốt không chỉ là một query nhanh trong phòng lab, mà là biết **vì sao nó nhanh, trường hợp nào sẽ chậm, cách phát hiện sự suy giảm và phương án giữ tính đúng đắn khi máy hoặc vùng không còn sẵn sàng**.

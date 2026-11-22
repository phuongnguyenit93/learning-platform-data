# Đánh đổi nhất quán và tính sẵn sàng khi xảy ra phân vùng mạng

## Mục tiêu học tập

Sau khi hoàn thành bài học, người học có thể:

1. Giải thích đúng các khái niệm **consistency**, **availability** và **network partition** trong định lý CAP, phân biệt chúng với ACID, SLA và tính sẵn sàng ở nghĩa vận hành thông thường.
2. Vẽ lịch thực thi khi hai nhóm máy chủ không thể trao đổi thông điệp và nhận diện vì sao không thể vừa bảo đảm đọc/ghi tuyến tính vừa luôn hoàn thành mọi yêu cầu tại mọi nhóm còn hoạt động.
3. Phân tích hành vi **ưu tiên nhất quán (CP)** và **ưu tiên phục vụ yêu cầu (AP)** theo từng loại thao tác, thay vì gắn nhãn máy móc cho cả sản phẩm database.
4. Giải thích tác động của leader, quorum, replication đồng bộ/bất đồng bộ, split-brain, fencing token và failover đến kết quả ghi đã xác nhận.
5. Lựa chọn đường đọc/ghi cho ứng dụng Java theo bất biến nghiệp vụ, mức chịu đựng dữ liệu cũ, RPO/RTO và yêu cầu trải nghiệm người dùng.
6. Thiết kế retry, idempotency và kiểm thử partition có chủ đích mà không làm phát sinh ghi trùng hoặc vi phạm dữ liệu.

Bài thuộc chương **Nền tảng phân tán** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module nghiên cứu lưu trữ dữ liệu bền vững trong ứng dụng Java, bao gồm mô hình dữ liệu, schema, query, index, transaction, isolation, concurrency, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng. Khi kho dữ liệu mở rộng qua nhiều node hoặc vùng địa lý, cần bổ sung một câu hỏi: **Điều gì được phép xảy ra khi các node không còn liên lạc được với nhau?**

## 1. Một tình huống thực tế: hai vùng không nói chuyện được

Giả sử dịch vụ bán hàng có hai vùng triển khai **A** và **B**, đều có người dùng truy cập. Mỗi vùng có một bản sao trạng thái sản phẩm. Trước sự cố:

~~~text
                          Người dùng
                       /             \
                    Vùng A          Vùng B
                    Replica A      Replica B
                       |               |
                       +------ mạng ---+
                              |
                        Dữ liệu đồng bộ
~~~

Sản phẩm `id=101` có giá `100000` và version `v7` tại cả hai vùng. Mạng giữa A và B bị đứt trong khi hai vùng vẫn nhận request từ client:

~~~text
                   PHÂN VÙNG MẠNG

              +--------------+      X      +--------------+
Client A ---> |  Vùng A      |   không     |  Vùng B      | <--- Client B
              |  Replica A   |   trao đổi  |  Replica B   |
              |  v7          |   được      |  v7          |
              +--------------+             +--------------+
~~~

Lúc này người dùng ở A yêu cầu đổi giá thành `120000`, còn người dùng ở B muốn xem hoặc đổi giá. Vì A và B không liên lạc được, B không thể biết chắc A đã cập nhật thành công hay chưa.

Có hai hướng đánh đổi:

- **Đặt tính nhất quán lên trước:** từ chối hoặc tạm ngừng một số thao tác ở nhóm không đủ quyền xác nhận trạng thái mới, chấp nhận một phần người dùng không được phục vụ.
- **Đặt khả năng nhận yêu cầu lên trước:** mỗi nhóm tiếp tục xử lý bằng trạng thái cục bộ, chấp nhận kết quả đọc có thể cũ hoặc các cập nhật xung đột phải được hợp nhất về sau.

Không thể giải quyết mâu thuẫn này chỉ bằng cách tăng tốc mạng hay thêm một index. Khi thông điệp không đến được đích, một nhóm không có thông tin để biết những thay đổi đã xảy ra ở nhóm khác.

## 2. CAP: chính xác ba chữ cái nói về điều gì?

**Định lý CAP** mô tả giới hạn của một kho dữ liệu phân tán trong mô hình có phân vùng mạng: khi hệ thống không thể bảo đảm truyền thông giữa các node, nó không thể đồng thời bảo đảm **tính nhất quán tuyến tính (linearizability)** và **tính sẵn sàng theo định nghĩa CAP** cho mọi thao tác trên dữ liệu liên quan.

### 2.1. C — Consistency: tính nhất quán tuyến tính

Trong cách phát biểu CAP thường dùng, C gần với **linearizability**: mỗi thao tác trên một đối tượng dữ liệu phải có thể được hiểu như xảy ra tức thời tại một điểm nằm giữa lúc gọi và lúc hoàn thành; các thao tác không chồng lấn nhau phải tôn trọng thứ tự thời gian thực.

Ví dụ:

~~~text
T1: Client A ghi price = 120000 -> đã nhận ACK thành công
T2: Sau ACK, Client B đọc price cùng key
Yêu cầu tuyến tính: B phải thấy 120000 hoặc giá trị mới hơn,
                   không được thấy 100000 từ bản cũ.
~~~

Nếu A đã hoàn thành write trước khi B bắt đầu read và không có một write khác xen vào, B phải thấy giá mới. Nếu hai thao tác **đang chồng lấn**, nhiều kết quả có thể hợp lệ tùy thứ tự tuyến tính hóa.

**C của CAP không đồng nghĩa:**

- Chữ **C của ACID** (consistency của ràng buộc bất biến/schema).
- Tất cả transaction toàn hệ thống đều serializable theo mọi ý nghĩa.
- Mọi replica có byte giống nhau ở mọi thời điểm.
- Kết quả nhất quán “cuối cùng sẽ giống nhau” (*eventual consistency*).

Một database có thể bảo vệ `CHECK (stock >= 0)` và tính nguyên tử của transaction tại một node mà vẫn cung cấp **đọc stale** trên replica; ACID tại một node không tự chứng minh linearizability trên các vùng.

### 2.2. A — Availability: khả năng hoàn thành yêu cầu

A trong CAP là yêu cầu về **liveness**: mọi request gửi đến một node không hỏng phải cuối cùng nhận được phản hồi hợp lệ theo giao diện dữ liệu, kể cả khi có phân vùng.

Nó **không đồng nghĩa** với KPI uptime 99,9%, HTTP load balancer còn khỏe, hay service luôn trả về bất kỳ thông báo nào. Một API trả `503 Service Unavailable` cho thao tác ghi quan trọng tại một nhóm node không thực sự hoàn thành thao tác đó; như vậy nhóm ấy không đạt availability theo nghĩa mạnh của CAP cho thao tác đó.

Định nghĩa lý thuyết không gắn thời hạn phản hồi cụ thể. Trong vận hành, phản hồi rất chậm cũng có thể vô dụng. Vì thế cần bổ sung latency, SLO, deadline và chính sách khi request chờ quá lâu.

Một lỗi nghiệp vụ hợp lệ, như `INSUFFICIENT_STOCK` khi tồn kho thực sự không đủ, khác với một từ chối kỹ thuật vì không thể xác định dữ liệu mới nhất.

### 2.3. P — Partition: mất khả năng trao đổi thông điệp đáng tin cậy

Partition là tình huống một nhóm node không thể trao đổi thông điệp đáng tin cậy với nhóm khác. Có thể do đứt mạng, firewall, định tuyến sai, đứt kết nối liên vùng hoặc thông điệp bị trì hoãn/mất quá lâu để phân biệt với lỗi.

Một node có thể vẫn sống, CPU và database hoạt động bình thường, nhưng không liên lạc được với quorum hoặc leader. Trong mô hình phân tán bất đồng bộ, không thể luôn phân biệt tức thì giữa “node đã hỏng” và “mạng chỉ đang chậm”.

**P không phải một tính năng chỉ cần bật hoặc tắt.** Với hệ thống nhiều node, phân vùng là một loại sự cố cần thiết kế đối phó. Câu hỏi thực tế là hệ thống sẽ làm gì khi partition xuất hiện, không phải “có muốn P hay không”.

### 2.4. Phát biểu cần nhớ

**Khi có partition, không thể đồng thời đảm bảo cả C tuyến tính và A theo CAP tại mọi nhóm node còn hoạt động đối với cùng thao tác dữ liệu liên quan.**

Cách nói “chọn hai trong ba C, A, P” thường gây hiểu lầm: khi mạng hoạt động bình thường, nhiều hệ thống có thể vừa phục vụ nhanh vừa trả dữ liệu mới; còn lúc mạng bị phân vùng, P là **điều kiện sự cố phải chịu**, nên đánh đổi quan trọng là **C với A**, theo phạm vi key/operation đang xét.

## 3. Chứng minh bằng một lịch thực thi nhỏ

Giả sử có hai node X và Y cùng lưu một key `k`, ban đầu `k=0`. Mạng X–Y bị cắt.

~~~text
Thời gian        X                              Y
   |             |                              |
   v             |------ mạng bị cắt ----------X|
                 |                              |
   t1            | Client X: WRITE(k=1)         |
   t2            | WRITE trả ACK thành công      |
   t3            |                              | Client Y: READ(k)
   t4            |                              | ?
~~~

Y chưa nhận được thông điệp nào từ X sau t1. Từ góc nhìn Y, hai thế giới không thể phân biệt:

1. X không có write mới: giá trị đúng là `0`.
2. X đã write `1` và được xác nhận: giá trị mới nhất là `1`.

Nếu Y **buộc phải trả lời READ ngay cả khi không liên lạc được với X**, nó không thể luôn chọn đúng giá trị của cả hai thế giới. Nếu Y **chờ đến khi biết trạng thái mới nhất**, nó có thể không hoàn thành request khi partition kéo dài. Đây là xung đột cốt lõi.

Không có thuật toán đọc local nào vừa đảm bảo đáp án luôn tuyến tính vừa không cần liên lạc/phối hợp trong mọi lịch phân vùng. Có thể thiết kế quyền sở hữu key, quorum hoặc leader để chỉ một phía được phép xác nhận write, nhưng khi đó phía còn lại phải chờ hoặc từ chối một số thao tác.

## 4. Ưu tiên nhất quán (CP) trong thời gian phân vùng

Một thiết kế ưu tiên C có thể chỉ cho phép nhóm **có đủ quorum và quyền lãnh đạo hợp lệ** thực hiện write; những nhóm còn lại không được tự xác nhận cập nhật xung đột.

Ví dụ cluster 3 node phân bố 2–1:

~~~text
Partition:
   Nhóm 1 (kết nối được)       |    Nhóm 2 (bị cô lập)
   N1 <--> N2                 X            N3
       2/3 node                            1/3 node
       Có majority                        Không majority
       Có thể bầu/giữ leader              Không được commit write
~~~

Trong một hệ đồng thuận kiểu majority quorum được cấu hình đúng, nhóm 2/3 có thể tiếp tục các thao tác cần majority nếu có leader hợp lệ. Nhóm 1/3 thường phải từ chối write đòi tính tuyến tính hoặc chờ mạng phục hồi.

**Cái giá:** các client chỉ truy cập được nhóm 1/3 có thể không ghi được, thậm chí không đọc được với yêu cầu đọc tuyến tính. Dù các máy ấy vẫn hoạt động, hệ thống đã hy sinh availability theo nghĩa CAP tại đó để không xác nhận dữ liệu mâu thuẫn.

Một số hệ thống cho phép **đọc stale có chủ đích từ nhóm minority** trong khi chặn write. Khi đó không nên gắn nhãn “mọi thao tác đều C”: mức bảo đảm đã thay đổi **theo từng đường đọc/ghi**.

### 4.1. Majority là điều kiện phối hợp, không phải phép màu

Quorum chỉ hữu ích khi thiết kế giao thức bảo đảm:

- Quorum xác nhận các quyết định quan trọng có giao nhau theo quy tắc membership.
- Không có hai leader cùng hợp lệ cho cùng epoch/term theo cách có thể xác nhận các write xung đột.
- Các node không chấp nhận write từ leader cũ sau khi leadership thay đổi.
- Replica và log áp dụng đúng thuật toán; không tự suy quorum chỉ từ số máy đang ping được.

Với 3 voter cố định, majority là 2. Với 5 voter cố định, majority là 3. Khi thay đổi membership, cần cơ chế reconfiguration an toàn; chỉ đổi danh sách node ở mỗi máy mà không có giao thức chuyển đổi có thể phá quy tắc giao quorum.

## 5. Ưu tiên khả năng phục vụ (AP) trong thời gian phân vùng

Một hệ thống ưu tiên A có thể cho phép cả hai phía tiếp tục chấp nhận các thao tác mà contract cho phép. Ví dụ mỗi vùng lưu các bài viết nháp độc lập hoặc bộ đếm lượt thích ước lượng.

~~~text
Trước partition: k = 0

Vùng A nhận update k = 10
Vùng B nhận update k = 20

Mạng phục hồi:
   Hệ thống phải chọn/quyết định cách hợp nhất hai nhánh.
~~~

Hai node đều hoàn thành request, nhưng không thể có một lịch tuyến tính duy nhất trong đó mọi client luôn nhìn thấy “ghi thành công mới nhất” theo thời gian thực trong lúc hai bên không liên lạc.

**Eventual consistency** là một lựa chọn thường gặp: nếu không còn cập nhật mới và cơ chế đồng bộ cuối cùng hoạt động, các bản sao sẽ hội tụ. **Hội tụ không tự xảy ra chỉ vì cho phép ghi ở hai vùng.** Hệ thống cần quy tắc merge, xác định conflict, versioning, anti-entropy, repair và xử lý xung đột có chủ đích.

### 5.1. Xung đột không phải lúc nào cũng giải bằng “ghi cuối thắng”

Một cách đơn giản là last-write-wins (LWW) theo timestamp. Nhưng timestamp từ máy khác nhau có thể không phản ánh thứ tự nghiệp vụ do clock skew và cách phát sự kiện. LWW còn có thể **mất một cập nhật đã được xác nhận** khi chọn một nhánh bỏ nhánh còn lại.

Ví dụ hai người cùng sửa địa chỉ giao hàng ở hai vùng: không phải lúc nào việc chọn “timestamp lớn hơn” cũng thể hiện ý muốn người dùng. Có thể cần giữ cả hai phiên bản rồi yêu cầu xử lý conflict.

Với dữ liệu cộng dồn, có thể dùng CRDT hoặc phép merge phù hợp nhằm giữ được các cập nhật đồng thời mà không cần một leader chung cho mọi thao tác. Tuy nhiên, **không phải mọi bất biến kinh doanh đều biểu diễn được bằng một phép merge an toàn**.

### 5.2. Vì sao tồn kho và thanh toán khó theo hướng AP thuần túy?

Giả sử tồn kho chung còn một sản phẩm:

~~~text
A thấy stock = 1 -> chấp nhận bán 1
B thấy stock = 1 -> chấp nhận bán 1
Mạng đang phân vùng nên A và B chưa đồng bộ
Kết quả nghiệp vụ: đã hứa bán tổng 2 trong khi chỉ có 1
~~~

Sau khi mạng phục hồi, phép merge không thể làm biến mất lời hứa đã gửi cho hai khách hàng. Có thể hoàn tiền/bù trừ, nhưng đó là chi phí nghiệp vụ, không phải đã giữ được bất biến “không bán quá tồn kho”.

Một kiến trúc có thể **phân bổ quota/tồn kho riêng cho từng vùng trước khi mất mạng**: A được bán tối đa một lượng đã cấp, B dùng lượng riêng. Đây là cách điều chỉnh bài toán để từng vùng không phải cùng cạnh tranh một đơn vị tồn kho. Nó có chi phí: tồn kho có thể nằm rỗi ở vùng này trong khi vùng khác báo hết, phải có quy trình chuyển quota và cơ chế chống cấp trùng.

## 6. Bảng so sánh theo hành vi, không theo nhãn sản phẩm

| Tiêu chí | Ưu tiên C khi partition | Ưu tiên A khi partition |
| --- | --- | --- |
| Hành vi tại nhóm không đủ thông tin | Chờ/từ chối một số thao tác đòi kết quả tuyến tính | Có thể phục vụ dựa trên trạng thái cục bộ |
| Kết quả đọc | Có thể yêu cầu leader/quorum để tránh stale | Có thể đọc bản chưa đồng bộ |
| Kết quả ghi | Chỉ xác nhận khi giao thức đồng thuận thỏa điều kiện | Có thể nhận ghi ở nhiều phía, cần merge |
| Nguy cơ chính | Không phục vụ được một phần request trong partition | Conflict, stale read, mất cập nhật khi merge không đúng |
| Phù hợp với | Số dư, quyền sở hữu duy nhất, đặt ghế cần bất biến chặt | Feed, telemetry, nháp, bộ đếm có phép merge được |
| Đổi lại sau phục hồi | Cần khôi phục quorum/leader và xử lý request bị chặn | Cần hội tụ, repair, giải quyết conflict và đối soát |

Không nên chỉ ghi “database X là CP, database Y là AP”. Cùng một sản phẩm có thể hỗ trợ **strong read ở đường này**, **stale read ở đường khác**, hoặc cấu hình consistency khác nhau tùy table, operation, cluster topology và phiên bản.

## 7. Quorum: công cụ phối hợp và những giới hạn cần hiểu

Giả sử một hệ lưu bản sao trên `N` node. Trong một mô hình **quorum read/write đơn giản**:

- `W`: số replica phải chấp nhận ghi trước khi trả ACK.
- `R`: số replica tham gia đọc.
- `N`: số replica được xem là thành viên của tập bản sao.

Một điều kiện giao nhau thường được nêu là:

`R + W > N`

Với `N=3`, chọn `R=2`, `W=2` khiến mọi tập hai node trong một tập ba node cố định giao nhau ít nhất một node.

**Điều kiện giao quorum không tự bảo đảm linearizability.** Vẫn phải xét:

1. Node giao nhau có chắc lưu bản ghi mới đã commit và trả đúng version không?
2. Có ghi đồng thời không? Khi nào write được coi là thành công?
3. Reader chọn phiên bản nào, có cơ chế read repair/coordination hay không?
4. Có sloppy quorum, hinted handoff, replica tạm thời hoặc membership thay đổi không?
5. Node cũ có thể nhận write sau khi leader mới được bầu không?
6. Network delay và timeout có tạo read ở phiên bản trước một write đã ACK không?

Trong hệ đồng thuận leader-based, quorum còn liên quan đến **term/epoch, log ordering và commit index**, không đơn giản là “đọc từ hai máy rồi lấy giá trị lớn nhất”.

### 7.1. Khi partition 2–1

Nếu yêu cầu `W=2` trên 3 replica cố định, nhóm đơn độc không đủ hai ACK nên không thể hoàn thành write theo chính sách đó. Nhóm hai node có thể tiếp tục, nhưng nếu dùng một giao thức leader/quorum thì còn cần trạng thái leadership hợp lệ. Chấp nhận `W=1` ở minority có thể tăng khả năng ghi cục bộ nhưng làm thay đổi bảo đảm conflict/durability.

Chọn quorum là quyết định gắn với rủi ro nghiệp vụ. Không có một con số R/W tối ưu cho mọi loại dữ liệu.

## 8. Leader, split-brain và fencing token

**Split-brain** là tình huống hai phía đều tin mình có quyền thực hiện thao tác độc quyền cho cùng dữ liệu. Nó đặc biệt nguy hiểm với primary database hoặc hệ thống cấp phát tài nguyên.

Ví dụ:

~~~text
Trước sự cố:
   Primary A -> nhận write
   Standby B -> theo A

Partition:
   A vẫn chạy nhưng không liên lạc được B
   Nhóm B bầu/promote primary mới

Rủi ro:
   A vẫn nhận write từ client cũ
   B cũng nhận write từ client mới
~~~

Nếu hai primary cùng ghi độc lập lên cùng logical dataset mà không có cơ chế chống xung đột, khi kết nối phục hồi sẽ có lịch sử dữ liệu phân kỳ.

**Fencing** nhằm ngăn actor cũ tiếp tục tác động sau khi quyền đã chuyển cho actor mới. Một phương án là dùng epoch/token tăng đơn điệu; mỗi write phải mang token hiện hành, và tầng thực thi từ chối token cũ. Một số hệ thống dùng cơ chế cô lập node cũ ở hạ tầng hoặc storage fencing.

~~~text
A sở hữu lease/token = 7
A bị cô lập; B được cấp token = 8

Write từ B(token=8) -> được phép
Write từ A(token=7) -> phải bị từ chối tại điểm bảo vệ chung
~~~

**Lease dựa vào thời gian không đủ nếu node cũ vẫn có thể ghi ngoài hợp đồng lease** hoặc khi clock/GC pause gây sai lệch giả định. Fencing chỉ hữu ích khi mọi thao tác nguy hiểm đều bị kiểm tra tại một **tài nguyên có quyền từ chối token cũ**.

Không được suy ra rằng cứ đặt `synchronized` hoặc distributed lock ở Java thì đã tránh split-brain. Nếu network partition ngăn việc duy trì lock nhưng writer cũ vẫn ghi được DB/storage, cần một lớp fencing thực sự.

## 9. Replication đồng bộ, bất đồng bộ và lời hứa về dữ liệu

Một primary–standby setup thường dùng replication để cải thiện khả năng phục hồi và phục vụ đọc. Tuy nhiên, từ “có replica” không cho biết write ACK nào chắc chắn có trên standby.

### 9.1. Bất đồng bộ: commit nhanh hơn, có cửa sổ mất dữ liệu khi failover

~~~text
Client -> Primary: UPDATE
Primary: ghi WAL cục bộ -> COMMIT ACK
Primary ---- WAL chưa kịp đến ----> Standby

Primary hỏng/mất kết nối ngay sau ACK
Standby được promote nhưng có thể thiếu update vừa ACK
~~~

Trong tình huống này, thay đổi có thể đã **bền vững trên primary** nhưng chưa được sao chép. Nếu primary không thể phục hồi và standby cũ được dùng làm nguồn mới, hệ thống có thể mất những transaction đã được ACK với client trước đó. Điều này ảnh hưởng đến **RPO của quá trình failover**, dù durability cục bộ trên primary từng đúng.

### 9.2. Đồng bộ: chờ replica, đổi lấy độ trễ và nguy cơ chặn ghi

Khi cấu hình synchronous replication đủ mạnh, primary có thể chờ một hoặc nhiều standby xác nhận mức bền vững tương ứng trước khi trả COMMIT cho client.

~~~text
Client -> Primary: COMMIT
Primary -> Standby: WAL
Standby -> Primary: ACK theo mức chờ cấu hình
Primary -> Client: COMMIT OK
~~~

Nếu partition khiến không có standby đủ điều kiện trả ACK, commit có thể **chờ**, gây giảm availability của thao tác ghi. Đó là một lựa chọn thiết kế để cải thiện mức bảo vệ đối với các sự cố được giả định.

Tuy nhiên, “replication đồng bộ” **không tự đảm bảo zero data loss trong mọi sự cố và mọi cách failover**. Cần kiểm tra điều kiện xác nhận, tập standby được chờ, ai được promote, storage flush, failure domain và việc client mất phản hồi commit.

### 9.3. PostgreSQL: điều cần xác minh

PostgreSQL hỗ trợ streaming replication và các cấu hình như `synchronous_commit`, `synchronous_standby_names`. Khi thiết kế:

- `synchronous_commit = on` thông thường có ý nghĩa WAL cục bộ được flush trước khi ACK; nếu có synchronous standby được cấu hình đúng, còn chờ các ACK đồng bộ tương ứng.
- `remote_write`, `on`, `remote_apply` có các điều kiện chờ phía standby khác nhau khi sử dụng synchronous replication.
- `synchronous_commit = off` có thể trả ACK trước khi WAL commit record được flush cục bộ, tạo thêm cửa sổ mất commit gần thời điểm crash.
- Synchronous replication trong PostgreSQL không mặc nhiên thiết lập một cơ chế bầu leader/quorum failover toàn diện. Quy trình promote, tránh split-brain và chọn standby phải được thiết kế/kiểm tra riêng.

Các chế độ, mặc định và khả năng chính xác phụ thuộc phiên bản PostgreSQL và topology. Không thay đổi cấu hình độ bền trên production chỉ để tăng một phép đo throughput mà chưa được phê duyệt bởi yêu cầu dữ liệu.

## 10. CAP khác với PACELC: khi mạng bình thường vẫn có đánh đổi

CAP tập trung vào trường hợp **partition**. Nhưng khi mạng hoạt động bình thường, việc chờ xác nhận qua nhiều vùng vẫn ảnh hưởng độ trễ.

Khung tư duy **PACELC** nhấn mạnh:

- **P → A/C:** khi có partition, phải đánh đổi availability với consistency.
- **ELSE → L/C:** khi không có partition, thường đánh đổi **latency** với mức consistency mong muốn, đặc biệt trong kiến trúc nhiều vùng.

Ví dụ:

- Đọc từ replica gần người dùng có thể nhanh, nhưng replica có thể trễ primary.
- Đọc cần tuyến tính có thể phải đến leader hoặc qua giao thức xác nhận, tăng network hop.
- Ghi chờ synchronous standby ở vùng xa có thể giảm rủi ro mất commit khi failover, nhưng kéo dài thời gian `COMMIT`.

PACELC là khung phân tích, **không phải một bảng phân loại bất biến cho mọi sản phẩm**. Một hệ thống có thể chọn consistency mạnh cho thanh toán, bounded staleness cho danh mục và eventual consistency cho telemetry, kể cả khi dùng cùng một nền tảng lưu trữ.

## 11. Lựa chọn semantics đọc: “mới nhất” không phải nhu cầu duy nhất

| Mức yêu cầu | Ví dụ | Cân nhắc |
| --- | --- | --- |
| Tuyến tính cho một key | Đọc trạng thái đơn vừa được xác nhận | Leader/quorum hoặc đường đọc có cơ chế nhất quán được hỗ trợ |
| Read-your-writes | Người dùng sửa hồ sơ rồi mở lại | Session affinity, token/version watermark hoặc đọc nguồn đủ mới |
| Monotonic reads | Người dùng không nhìn phiên bản mới rồi quay lại cũ | Theo dõi version/session, tránh chuyển tới replica trễ |
| Bounded staleness | Giá hiển thị được phép trễ tối đa vài giây | Theo dõi replica lag và đặt ngưỡng/switch-to-primary |
| Eventual consistency | Feed gợi ý, thống kê tham khảo | Hợp nhất dữ liệu, TTL, reconciliation và đo lag |
| Snapshot nhất quán nhiều hàng | Báo cáo chốt số liệu tại một mốc | DB transaction/snapshot hoặc pipeline xuất bản snapshot phù hợp |

**Đọc từ primary không tự chứng minh mọi bảo đảm tuyến tính trong mọi kiến trúc**, đặc biệt trong failover, cache, transaction isolation hoặc khi còn nhiều writer. Cần xét giao thức leadership và sự nhất quán của chính API.

### 11.1. Read-your-writes sau khi ghi ở vùng A, đọc ở vùng B

Nếu client vừa cập nhật profile ở primary A và sau đó được load balancer chuyển đến vùng B đang đọc từ replica trễ, client có thể nhìn thấy profile cũ. Cách xử lý:

1. Sau write, trả một `version` hoặc token phù hợp.
2. Đường read ở B chỉ sử dụng replica nếu đã áp dụng tới version/token yêu cầu; nếu chưa, chờ trong deadline hoặc chuyển sang nguồn đọc mạnh hơn.
3. Nếu không còn nguồn phù hợp, trả trạng thái có chủ đích; không âm thầm trình bày dữ liệu cũ như kết quả bảo đảm read-your-writes.

Version theo từng hàng và WAL LSN là hai khái niệm khác nhau; không thể tự so sánh số version của một entity với WAL position nếu thiếu ánh xạ. Giao thức theo dõi tiến độ phải được thiết kế cho topology cụ thể.

## 12. Thiết kế nghiệp vụ: sản phẩm nào được phép từ chối khi partition?

Một kiến trúc tốt không bắt mọi đường đi có cùng mức consistency:

| Nghiệp vụ | Bất biến cần giữ | Phương án cân nhắc |
| --- | --- | --- |
| Đặt chỗ một ghế duy nhất | Không có hai đặt chỗ thành công cho cùng ghế | UNIQUE/transaction tại authority phù hợp; chặn write khi không đủ phối hợp |
| Trừ tồn kho | Không nhận vượt số lượng khả dụng | Conditional UPDATE, quota phân vùng có kiểm soát hoặc từ chối khi thiếu authority |
| Chuyển tiền | Không tạo giá trị từ hai lịch sử mâu thuẫn | Ledger/transaction, consistency mạnh, idempotency và đối soát |
| Cập nhật mô tả sản phẩm | Cho phép sửa khi một vùng offline? | Có thể dùng version và reconciliation nếu nghiệp vụ chấp nhận conflict |
| Bộ đếm lượt xem | Chấp nhận số liệu hội tụ sau | Counter có phép merge phù hợp, event aggregation |
| Feed hoạt động | Cho phép nhận nội dung cũ ngắn hạn | Cache và replication bất đồng bộ, eventual consistency |
| Thu hồi quyền truy cập | Hành động nhạy cảm không dùng quyền đã thu hồi | Đường kiểm tra authoritative hoặc cơ chế epoch/quyền có bảo đảm được định nghĩa |
| Dashboard vận hành | Có thể trễ vài giây/phút | Bounded staleness và hiển thị thời điểm dữ liệu |

**Các bất biến như “một ghế chỉ bán một lần” phải được bảo vệ tại kho dữ liệu hoặc cơ chế authority đã được chứng minh.** Caching, Java thread safety hay việc một server nhận HTTP 200 không thể thay thế transaction/constraint.

### 12.1. Chọn cách suy giảm chức năng có kiểm soát

Khi không có quorum, dịch vụ có thể:

- Cho phép xem danh mục từ cache kèm dấu “dữ liệu được cập nhật lúc …”.
- Ngừng nhận checkout mới hoặc trả trạng thái “chưa thể xác nhận”, không giả tạo thành công.
- Cho phép đưa yêu cầu vào hàng đợi có định danh duy nhất, nhưng phải phân biệt **“đã tiếp nhận yêu cầu”** với **“đã đặt hàng thành công”**.
- Sử dụng quota đã cấp riêng từng vùng để thực hiện những write nằm trong quyền của vùng.
- Trả `503`/phản hồi có deadline cho thao tác cần consistency mạnh, kèm chính sách retry idempotent.

Một request được xếp hàng chưa chắc đã tạo ra một write được commit. API phải công khai trạng thái và cách truy vấn kết quả để tránh người dùng hiểu nhầm.

## 13. Java/JDBC: bảo vệ write ở nguồn có thẩm quyền

Ví dụ PostgreSQL giữ tồn kho theo tenant:

~~~sql
CREATE TABLE products (
    tenant_id  BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    available  INTEGER NOT NULL CHECK (available >= 0),
    version    BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, product_id)
);

INSERT INTO products (tenant_id, product_id, available)
VALUES (42, 101, 1);
~~~

Khi có một primary có quyền nhận write, thao tác trừ tồn kho nên đưa điều kiện vào DB:

~~~sql
UPDATE products
SET available = available - ?,
    version = version + 1
WHERE tenant_id = ?
  AND product_id = ?
  AND available >= ?;
~~~

Khi hai request đồng thời chạy trên **cùng authority DB**, database phối hợp tranh chấp trên hàng và câu UPDATE có điều kiện tránh trừ xuống âm. **Nếu kiến trúc cho phép hai primary phân kỳ độc lập dưới partition**, không được suy rằng hai UPDATE ở hai phía sẽ bảo vệ bất biến tổng; cần authority/quorum hoặc quota phân vùng.

Ví dụ Java 17/JDBC:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class InventoryRepository {
    private final DataSource primaryDataSource;

    public InventoryRepository(DataSource primaryDataSource) {
        this.primaryDataSource = primaryDataSource;
    }

    /**
     * Kết quả true chỉ nghĩa statement được DB chấp nhận và
     * commit thành công qua connection dùng autocommit.
     * Không tự retry khi kết quả commit có thể chưa xác định.
     */
    public boolean reserveOnce(
            long tenantId, long productId, int quantity)
            throws SQLException {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        String sql = """
            UPDATE products
            SET available = available - ?,
                version = version + 1
            WHERE tenant_id = ?
              AND product_id = ?
              AND available >= ?
            """;

        try (Connection connection = primaryDataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            // Ví dụ này chủ động yêu cầu autocommit cho một statement.
            connection.setAutoCommit(true);

            statement.setInt(1, quantity);
            statement.setLong(2, tenantId);
            statement.setLong(3, productId);
            statement.setInt(4, quantity);

            int updated = statement.executeUpdate();
            return updated == 1;
        }
    }
}
~~~

Ví dụ chỉ thể hiện **một UPDATE có điều kiện trên một authority**. Nó chưa đủ cho toàn bộ quy trình đặt hàng gồm nhiều bảng, idempotency, outbox hay phát hiện trạng thái commit không chắc chắn.

Đặc biệt, nếu `executeUpdate()` ném `SQLException` do mất kết nối, không biết chắc phía server đã commit statement autocommit hay chưa. **Không gọi lại `reserveOnce()` vô điều kiện**: có thể trừ tồn kho hai lần. Một API production cần dùng `request_key` duy nhất, kết quả giao dịch được lưu bền và quy trình đối soát.

### 13.1. Hợp đồng một transaction có idempotency key

Một phương án thiết kế cho một primary authority:

~~~sql
CREATE TABLE reservation_requests (
    tenant_id  BIGINT NOT NULL,
    request_key TEXT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    outcome    TEXT NOT NULL
               CHECK (outcome IN ('PENDING', 'RESERVED', 'REJECTED')),
    PRIMARY KEY (tenant_id, request_key)
);
~~~

Quy trình:

1. Client gửi `tenant_id`, `product_id`, `quantity` và một `request_key` cố định cho yêu cầu logic.
2. Transaction tạo bản ghi `PENDING` theo khóa duy nhất. Nếu cùng key đã tồn tại, kiểm tra payload và trả **outcome đã commit** thay vì trừ lần nữa.
3. Nếu key mới, thực hiện conditional UPDATE tồn kho; ghi `RESERVED` nếu cập nhật một hàng, hoặc `REJECTED` nếu không đủ.
4. Commit cả trạng thái request và thay đổi tồn kho **cùng một transaction**. Chỉ xác nhận đặt chỗ thành công khi biết commit thành công.
5. Nếu client mất phản hồi COMMIT, mở connection mới tới authority phù hợp để tra cứu bằng `request_key`. Nếu không thấy bản ghi, chỉ thử lại bằng **cùng key** và giao thức unique constraint; transaction cũ có thể chưa hoàn tất.

**Đừng gửi yêu cầu sang một primary mới sau failover với key mới** chỉ vì không nhận phản hồi từ primary cũ. Giao thức failover và replication phải bảo vệ lịch sử request hoặc có khả năng đối soát/bù trừ khi một commit cũ không còn trên primary mới.

## 14. Khi ACK COMMIT bị mất: partition có thể tạo kết quả chưa xác định

~~~text
App Java                   Primary DB                 Standby
   |                           |                        |
   |------- COMMIT ----------->|                        |
   |                           | WAL/COMMIT thành công   |
   |                           |---- replication ------>|
   |           X mất ACK       |                        |
   |<-----------X--------------|                        |
   | SQLException              |                        |
~~~

Từ phía Java, đây là **unknown transaction outcome**. Có thể:

- COMMIT không tới primary.
- Primary nhận COMMIT nhưng rollback do lỗi.
- Primary đã commit cục bộ, nhưng phản hồi không tới client.
- Primary commit rồi failover diễn ra trước khi replica cần thiết nhận log, tùy replication policy.

Một lần retry chỉ an toàn khi thiết kế **idempotency + authority + cơ chế đối soát** bảo vệ được việc lặp. Không thể giải quyết bằng cách tăng `maxRetries` hoặc catch mọi `SQLException`.

Với các transaction quan trọng, cần chỉ rõ “commit được xác nhận” nghĩa là bền vững ở đâu và “failover thành công” dựa trên bản sao đạt mức nào. Đây là câu nối giữa CAP, ACID durability, replication và chính sách phục hồi.

## 15. RPO, RTO và tính sẵn sàng đo được

Trong vận hành, hai chỉ tiêu thường quan trọng:

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa chấp nhận được khi cần khôi phục.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận được để đưa dịch vụ trở lại hoạt động theo yêu cầu.

| Lựa chọn | Tác động có thể có đến RPO | Tác động đến RTO/latency/availability |
| --- | --- | --- |
| Async replication | Có cửa sổ commit chưa tới standby | Commit ít chờ mạng xa; failover có thể phải đối soát dữ liệu |
| Sync replication đủ điều kiện | Giảm rủi ro mất commit đã ACK trong phạm vi sự cố được hỗ trợ | COMMIT có thể chờ khi standby/network lỗi |
| Nhiều voter majority | Có thể duy trì quorum khi mất một node trong cấu hình phù hợp | Minority không thể hoàn thành một số thao tác |
| Multi-primary cho ghi độc lập | Có thể tiếp tục ghi ở nhiều vùng | Phải giải quyết conflict, không giữ mọi bất biến chung |
| Backup/PITR | Phục hồi từ lịch sử khi dữ liệu bị xóa/hỏng | Restore có thể tốn thời gian, không cung cấp availability tức thì |
| Cache/replica đọc gần client | Không phải cơ chế bảo vệ commit | Có thể giảm latency, nhưng cần ghi rõ staleness |

**Replication không thay thế backup.** Xóa nhầm và lỗi logic có thể được nhân bản rất nhanh. Ngược lại, backup không khiến một write được ACK trên primary chắc chắn đã xuất hiện trên standby đang phục vụ sau failover. Cả hai đều cần trong kiến trúc persistence có yêu cầu bảo vệ dữ liệu.

## 16. Kiểm thử partition có chủ đích

Một hệ phân tán cần kiểm thử cả **safety** (không vi phạm bất biến) và **liveness** (phục vụ được những thao tác nào) khi network không ổn định.

### 16.1. Kịch bản ba node bị tách 2–1

Trong môi trường test được phép:

1. Thiết lập cluster 3 voter với trạng thái ban đầu đã đồng bộ.
2. Xác nhận read/write ở điều kiện bình thường.
3. Dùng cơ chế fault injection tạo phân vùng để nhóm `N1,N2` không liên lạc được `N3`.
4. Gửi read/write riêng tới từng nhóm, đo phản hồi, mã lỗi và deadline.
5. Kiểm tra nhóm có quorum có leader hợp lệ được phép hoàn thành thao tác nào.
6. Kiểm tra minority không được xác nhận một write cần tính tuyến tính nếu thiếu quorum.
7. Phục hồi mạng, chờ catch-up rồi kiểm tra log/state, các request đã ACK và những request chưa xác định.
8. Thử tình huống leader cũ quay lại; xác minh fencing và trạng thái không phân kỳ.

**Không làm test network partition bằng cách cắt mạng production** nếu không có quy trình an toàn và ủy quyền vận hành. Những thử nghiệm này nên ở test/staging hoặc môi trường lab có thể khôi phục.

### 16.2. Ma trận kiểm tra theo thao tác

| Tình huống | Câu hỏi cần xác minh |
| --- | --- |
| Client ở minority gọi strong write | Bị chặn/từ chối có chủ đích hay sai lầm ACK? |
| Client ở minority gọi stale read | Hợp đồng có cho phép đọc cũ không, có hiển thị version/time? |
| Client chuyển từ minority sang majority | Có đọc lùi phiên bản không? |
| Leader cũ được phục hồi | Có nhận write sai epoch/term không? |
| COMMIT ACK bị mất | Idempotency key có tránh ghi trùng và đối soát được không? |
| Primary hỏng trước khi standby nhận WAL | Số commit đã ACK bị ảnh hưởng theo RPO nào? |
| Quorum vừa đủ rồi thêm một voter hỏng | Service có suy giảm có kiểm soát không? |
| Event replication đến trễ hoặc đảo thứ tự | Có version/ordering guard phù hợp không? |
| Cache còn bản cũ sau failover | API có trả dữ liệu trái hợp đồng strong read không? |
| Vùng bị cô lập ghi telemetry | Dữ liệu có hợp nhất về sau mà không mất thông tin cần giữ không? |
| Hai vùng dùng cùng idempotency key | Có một authority hoặc quy tắc chống trùng toàn cục không? |
| Node reconnect với clock lệch | LWW/lease có gây mất cập nhật hoặc split-brain không? |

Một bài test chỉ giết hẳn process không thay thế test **partition**: trong partition, node có thể còn hoạt động và vẫn tiếp nhận traffic, khiến nguy cơ split-brain cao hơn. Cũng không nên chỉ chạy thử trong mạng latency thấp rồi coi như đã kiểm chứng kiến trúc nhiều vùng.

### 16.3. Chỉ số cần quan sát

- Khả năng hoàn thành các operation theo vùng: số request thành công, timeout, 503 và phản hồi được đưa vào queue.
- Leader/term/epoch, quorum health, tỷ lệ bầu leader, thời gian failover.
- Replication lag, WAL sent/write/flush/replay progress, snapshot catch-up.
- Số trường hợp conflict, reconciliation, stale read và vi phạm read-your-writes.
- Số request có unknown commit outcome, thời gian đối soát và tỷ lệ idempotent duplicate.
- p50/p95/p99 read/write/commit latency, connection pool pending, lock wait và timeout.
- Số transaction được ACK nhưng không xuất hiện trên primary mới sau failover trong test kiểm soát.

Không chỉ đo uptime 99,9%. Một hệ thống có thể luôn trả HTTP 200 nhưng dữ liệu sai, hoặc bảo vệ mọi bất biến mà người dùng ở minority không thể hoàn thành công việc. **Metric phải phản ánh cả tính đúng đắn và khả năng phục vụ của từng use case.**

## 17. Những ngộ nhận thường gặp

**“CAP nghĩa là mỗi database được chọn đúng hai trong ba chữ.”** Khi partition xảy ra, C tuyến tính và A theo CAP không thể cùng được đảm bảo mọi nơi cho dữ liệu liên quan; lựa chọn có thể khác theo operation.

**“Consistency trong CAP là chữ C của ACID.”** Hai khái niệm khác nhau: linearizability của lịch sử phân tán so với tính hợp lệ của bất biến dữ liệu trong transaction.

**“Nếu server trả 503 thì vẫn đạt availability vì đã phản hồi.”** Một phản hồi từ chối kỹ thuật không hoàn thành yêu cầu dữ liệu theo định nghĩa availability của CAP.

**“Partition tolerance chỉ cần bật khi muốn mở rộng.”** Mạng có thể phân vùng bất kể cấu hình; cần xác định hành vi chịu lỗi.

**“Quorum `R + W > N` luôn đảm bảo đọc tuyến tính.”** Điều kiện giao tập là chưa đủ; cần thuật toán xử lý đồng thời, membership và version/commit ordering.

**“Leader lease là đủ để ngăn split-brain.”** Cần đảm bảo leader cũ thực sự bị fencing tại nơi kiểm soát write, không chỉ hết hạn trên giấy.

**“Có synchronous standby thì mọi failover đều zero loss.”** Phải kiểm tra mức ACK, standby được chờ, promote policy và fault model; synchronous replication không tự thiết kế leader election an toàn.

**“Async replication luôn sai.”** Nó có thể hợp lý với dữ liệu chấp nhận RPO lớn hơn 0 hoặc workload đọc; nhưng phải công khai cửa sổ mất dữ liệu.

**“Eventual consistency nghĩa là dữ liệu cuối cùng tự hội tụ.”** Cần thuật toán đồng bộ/merge và xử lý conflict; một số bất biến không giải được bằng hợp nhất đơn giản.

**“Dùng CRDT thì có thể bán hai ghế cho hai người và tự sửa về sau.”** CRDT hỗ trợ một số phép merge, không biến một lời hứa độc quyền vi phạm thành đúng.

**“Đọc từ primary luôn là strong read.”** Phải xét authority, failover, cache, transaction và giao thức read thực tế.

**“SQLException nghĩa là COMMIT thất bại.”** Nếu mất phản hồi, DB có thể đã commit; retry thiếu idempotency gây ghi trùng.

**“Replication là backup.”** Replica có thể cùng chứa xóa nhầm; backup/PITR phục vụ mục tiêu phục hồi khác.

## 18. Bài tập thực hành

**Bài 1 — lịch CAP.** Hai node X/Y cùng lưu `k=0`, partition xảy ra, X ACK `WRITE(k=1)`; sau đó Y nhận `READ(k)`. Hãy giải thích tại sao Y không thể vừa luôn trả lời vừa chắc chắn tuyến tính. Đề xuất hai chính sách khác nhau và hậu quả với client.

**Bài 2 — majority 3 node.** Cluster chia 2–1. Xác định nhóm nào có thể tạo majority nếu yêu cầu 2/3, nhóm nào phải chặn write. Nếu vẫn cho minority ghi độc lập, cần xử lý xung đột gì khi mạng phục hồi?

**Bài 3 — quorum không đủ.** Với `N=3, R=2, W=2`, chứng minh tập read/write giao nhau. Sau đó nêu ít nhất ba lý do điều kiện đó **chưa tự chứng minh** linearizability trong thực tế.

**Bài 4 — mua hàng xuyên vùng.** Một sản phẩm chỉ còn 1 đơn vị, hai vùng cùng bị cô lập và mỗi vùng nhận checkout. Hãy thiết kế: (a) phương án giữ một authority hoặc quorum; (b) phương án cấp quota cho từng vùng. So sánh availability, khả năng bán quá tồn kho và trải nghiệm khách hàng.

**Bài 5 — mất ACK COMMIT.** Java `executeUpdate()`/COMMIT bị socket timeout; người dùng bấm lại. Hãy thiết kế schema lưu `request_key` duy nhất, transaction cập nhật tồn kho và ghi kết quả, quy trình đối soát sau failover. Vì sao dùng key mới mỗi lần retry là sai?

**Bài 6 — RPO/RTO.** Primary dùng async streaming replication, client đã ACK write nhưng standby chưa nhận WAL, primary hỏng không phục hồi được. Phân tích kết quả sau promotion, RPO thực tế và cách thay đổi kiến trúc nếu nghiệp vụ không chấp nhận mất write đã ACK.

**Bài 7 — read-your-writes.** Người dùng vừa đổi địa chỉ tại vùng A, request sau được chuyển sang vùng B đọc replica đang trễ. Hãy đề xuất version/token, tiêu chí đọc replica, cách chuyển sang primary và phản hồi khi không thể đáp ứng deadline.

**Bài 8 — test partition.** Tạo ma trận cho các tình huống leader cũ còn sống, thiếu quorum, latency cực cao, ACK mất và mạng phục hồi. Định nghĩa metric chứng minh **safety** và **liveness**, không chỉ kiểm tra có nhận được HTTP 200.

## Ghi nhớ

**Khi phân vùng mạng xảy ra, hệ thống phân tán không thể đồng thời cam kết mọi thao tác đều có tính nhất quán tuyến tính và mọi node không hỏng đều hoàn thành request bất chấp thiếu liên lạc.** Đây là ý nghĩa quan trọng của CAP. Thiết kế ưu tiên C thường chặn một số thao tác ở phía không đủ quorum; thiết kế ưu tiên A có thể phục vụ từ trạng thái cục bộ nhưng phải chấp nhận stale/conflict và có quy trình hội tụ. Khi mạng bình thường, PACELC nhắc rằng latency và consistency cũng có thể đánh đổi.

Đối với Java persistence, lựa chọn phải đi từ **bất biến nghiệp vụ và mô hình sự cố**: bảo vệ giao dịch/khóa duy nhất ở authority phù hợp, hiểu quorum và failover, không đánh đồng replication với backup, công khai mức staleness của các đường đọc, dùng idempotency khi commit chưa rõ, và kiểm thử network partition bằng lịch thực thi có chủ đích. Một hệ thống đáng tin không chỉ “luôn trả lời” mà phải biết **khi nào có thể cam kết kết quả đúng** và khi nào cần từ chối hoặc xác minh trước khi tiếp tục.

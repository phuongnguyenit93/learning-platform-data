# CAP trong tình huống phân hoạch mạng và giới hạn cách diễn giải

> **Bối cảnh:** Software Design Architecture → System Architecture → Microservices → Nền tảng phân tán.
>
> **Mục tiêu:** hiểu CAP thực sự phát biểu điều gì, vì sao phân hoạch mạng buộc hệ thống phải đánh đổi giữa hai tính chất cụ thể, và cách vận dụng kết quả đó khi thiết kế dữ liệu và quy trình nghiệp vụ của hệ thống microservices.

## 1. Vấn đề CAP giải quyết là gì?

Một hệ thống phân tán thường đặt các bản sao dữ liệu trên nhiều nút hoặc nhiều vùng để xử lý tải, chịu lỗi phần cứng và phục vụ người dùng gần hơn. Các nút cần trao đổi thông tin để biết giá trị nào đã được ghi, ai được phép ghi và kết quả nào nên trả về.

Bình thường, các nút liên lạc được với nhau. Nhưng mạng có thể mất gói, mất kết nối một chiều, chậm bất thường, lỗi định tuyến hoặc chia thành những nhóm không thể trao đổi thông tin. Trạng thái đó được gọi là **network partition — phân hoạch mạng**.

Ví dụ một kho dữ liệu đơn giản lưu số lượng hàng còn lại. Nó có ba bản sao ở A, B và C:

~~~text
                     Trước sự cố
                  A  <-->  B  <-->  C
                  |       dữ liệu: 10       |
                  
                   Khi mạng bị phân hoạch
              [ Nút A ]   X   [ Nút B <--> Nút C ]
                 nhóm 1            nhóm 2

              Người dùng X        Người dùng Y
                  |                    |
                  v                    v
              ghi/đọc ở A        ghi/đọc ở B hoặc C
~~~

Giả sử một người ở nhóm 1 vừa được xác nhận đã đặt mua một sản phẩm. Người khác ở nhóm 2 lập tức muốn xem tồn kho, nhưng nhóm 2 không thể biết việc mua hàng vừa được xác nhận ở nhóm 1. Nếu cả hai phía tiếp tục trả lời theo dữ liệu riêng, chúng có thể cho ra các kết quả không phù hợp với một lịch sử chung nhất quán. Nếu một phía đợi hoặc từ chối thao tác cho đến khi có liên lạc, người dùng phía đó mất khả năng thực hiện thao tác đúng lúc.

Đây là trọng tâm của **định lý CAP**: trước một phân hoạch khiến các nút liên quan không thể trao đổi thông tin, hệ thống không thể đồng thời bảo đảm **consistency (theo nghĩa mạnh của CAP)** và **availability (theo định nghĩa của CAP)** cho mọi thao tác liên quan.

CAP là một giới hạn lý thuyết của hệ phân tán. Nó không phải một bộ ba tùy chọn để đội phát triển bật/tắt tùy ý.

## 2. Ba chữ C, A và P phải được hiểu chính xác

### 2.1. C — Consistency: một lịch sử quan sát như một bản sao duy nhất

**Consistency trong CAP thường được diễn giải bằng tính linearizability** (nhất quán tuyến tính): mỗi thao tác đọc/ghi có vẻ xảy ra tức thời tại một điểm giữa lúc bắt đầu và lúc kết thúc; tất cả thao tác tương thích với một thứ tự duy nhất và thứ tự đó phải tôn trọng quan hệ thời gian thực giữa những thao tác không chồng lấn.

Hình dung hệ thống có một biến X, ban đầu X = 0:

~~~text
Thời gian --------->

Client 1: WRITE X=1 ------- nhận SUCCESS
Client 2:                             READ X ------- phải thấy 1 hoặc giá trị mới hơn
~~~

Nếu lệnh đọc của Client 2 **bắt đầu sau khi** lệnh ghi thành công của Client 1 **đã kết thúc**, một hệ thống linearizable không thể trả giá trị cũ 0 nếu chưa có một lệnh ghi mới hợp lệ thay thế.

Nếu hai thao tác chồng thời gian, có thể tồn tại nhiều cách sắp thứ tự hợp lệ. Linearizability không có nghĩa mọi replica luôn chứa cùng byte trong mọi microsecond; yêu cầu là **các phản hồi được trả cho client** phù hợp với một lịch sử như thể chỉ có một bản sao có thẩm quyền.

Lưu ý: C trong CAP **không đồng nghĩa** với chữ C trong ACID của cơ sở dữ liệu. ACID Consistency nói đến việc transaction duy trì các ràng buộc hợp lệ của database; CAP Consistency nói đến một bảo đảm về thứ tự và khả năng quan sát thao tác giữa nhiều nút.

### 2.2. A — Availability: các nút còn hoạt động đều phải phản hồi thao tác hợp lệ

Trong mô hình CAP, **availability** đòi hỏi mỗi yêu cầu gửi đến một nút **không bị hỏng** cuối cùng phải nhận một phản hồi **thành công, hợp lệ với loại thao tác đó**, thay vì bị bỏ mặc chờ vô hạn hoặc từ chối chỉ vì không phối hợp được với phía khác.

Nếu một bên phân hoạch vẫn đang chạy nhưng không thể đáp ứng lệnh ghi vì thiếu quorum, hệ thống đó đã hy sinh A theo định nghĩa CAP đối với yêu cầu ấy, dù nó vẫn có thể trả HTTP 503 rất nhanh.

Cần phân biệt:

- **CAP availability:** thuộc tính lý thuyết “mỗi request hợp lệ tới nút không hỏng cuối cùng được phục vụ”.
- **Service availability/SLA/SLO:** phần trăm request thành công, chẳng hạn 99,9% theo một khoảng thời gian; còn phụ thuộc timeout thực tế, tải, lỗi ứng dụng, vận hành và định nghĩa thành công.
- **Responsiveness/latency:** phản hồi nhanh đến mức nào. CAP không tự đưa ra cam kết p95 = 100 ms hay timeout 2 giây.
- **Node health:** tiến trình đang chạy không có nghĩa thao tác nghiệp vụ có thể hoàn thành.

Một dịch vụ được vận hành rất tốt với uptime cao vẫn có thể chọn hành vi CP trong lúc phân hoạch; “CP” không đồng nghĩa dịch vụ luôn chậm hoặc thường xuyên ngừng hoạt động.

### 2.3. P — Partition tolerance: phân hoạch là tình huống mà thiết kế phải đối diện

**Partition tolerance** nghĩa là hệ thống tiếp tục phải được xem xét khi các thông điệp giữa các nhóm nút bị mất hoặc bị trì hoãn tùy ý trong mô hình. Với những hệ phân tán chạy qua mạng thực, không thể chứng minh mạng sẽ luôn thông suốt. Vì vậy thường phải chuẩn bị cho P như một giả định sự cố có thể xảy ra, không phải một “tính năng” bật lên bằng cấu hình.

Phân hoạch khác với việc một nút bị tắt hoàn toàn. Nút A vẫn có thể khỏe mạnh và tiếp nhận người dùng, trong khi không thể nói chuyện với B, C. Đây là tình huống khó vì **cả hai phía đều tưởng mình còn đang hoạt động** và muốn tiếp tục ra quyết định.

Timeout không đủ để phân biệt chắc chắn “bên kia chết” với “bên kia còn sống nhưng mạng rất chậm”. Trong thực tế hệ thống phải đặt deadline và dùng cơ chế quorum/leader/fencing để quyết định thao tác nào an toàn; không được suy luận rằng cứ hết timeout thì phiên cũ đã dừng xử lý.

## 3. Vì sao không thể đồng thời giữ C và A khi phân hoạch?

Xét hai replica A và B cùng lưu giá trị X = 0. Tại thời điểm mạng bị chia, A và B không thể gửi thông điệp cho nhau.

~~~text
Replica A                         Replica B
   X=0                                X=0
    |                                  |
    |    Mạng đứt giữa A và B          |
    X==================================X
    |                                  |
Client 1: WRITE X=1                   |
    |                                  |
    | trả SUCCESS                      |
    |                         Client 2: READ X
    |                                  |
    |                         B không nhận được WRITE
    |                                  |
    |                         B có thể trả gì?
~~~

Giả sử lệnh WRITE của Client 1 đã thành công **trước khi** Client 2 bắt đầu READ. Nếu B trả X = 0, hệ thống vi phạm linearizability: người dùng đọc thấy lịch sử lùi về trước một thao tác đã hoàn tất. Nếu B muốn biết giá trị mới nhất nhưng không thể liên lạc với A, B phải chờ, báo không thể phục vụ, hoặc tìm bằng chứng khác để trả lời an toàn. Khi đó B không còn bảo đảm availability theo định nghĩa CAP.

Để cả A và B luôn phục vụ thao tác trong một phân hoạch kéo dài, một phía có nguy cơ trả kết quả không phù hợp với một thứ tự duy nhất. Không có giao thức nào loại bỏ được mâu thuẫn đó cho các thao tác đọc/ghi tổng quát trong mô hình liên lạc bị cắt đứt.

**Phân biệt quan trọng:** đây là tình huống xung đột giữa hai bảo đảm *khi phân hoạch thực sự ảnh hưởng đến thao tác*. Không có phân hoạch, nhiều hệ thống vừa cho kết quả linearizable vừa phục vụ tốt. Định lý không tuyên bố mỗi ngày hệ thống chỉ được sở hữu hai đặc điểm trong ba đặc điểm.

## 4. Hành vi CP: giữ tính nhất quán, có thể từ chối một phần yêu cầu

Một hệ thường được gọi là **CP** khi, trước phân hoạch, nó không trả kết quả trái với bảo đảm linearizability đã cam kết. Nó có thể phải chặn/từ chối một số thao tác ở những nút không có đủ khả năng xác nhận trạng thái chung.

Ví dụ một cụm ba replica dùng cơ chế leader và majority quorum:

~~~text
N = 3: A, B, C
Quorum đa số = 2 trong 3 nút

Khi phân hoạch:
    Nhóm 1                Nhóm 2
      [A]           X     [B] <--> [C]
     1/3 nút                   2/3 nút

A: không có quorum       B,C: có thể đạt quorum
=> không tự xác nhận      => có thể tiếp tục xác nhận
   ghi mới an toàn           ghi mới theo giao thức
~~~

Nếu giao thức consensus/replication được thiết kế đúng, phía B–C có thể tiếp tục ghi với điều kiện có leader hợp lệ. Nút A phải từ chối hoặc hoãn những thao tác không thể chứng minh an toàn; nếu A vẫn phục vụ dữ liệu cũ, API phải **ghi rõ đó là stale read và không còn cam kết linearizability cho phản hồi đó**.

Không phải cứ đặt N = 3 và quy tắc “W = 2, R = 2” là tự động có linearizability. Cần xem giao thức bầu leader, thứ tự commit, khả năng đọc đúng tuyến, thay đổi membership, fencing token, xử lý leader cũ và các điều kiện khi có partition. Một công thức quorum giao cắt là trực giác hữu ích, nhưng chưa đủ thay cho đặc tả consistency của hệ lưu trữ.

### 4.1. Ứng dụng thực tế: giữ tồn kho và thanh toán

Giả sử kho còn đúng một sản phẩm. Hai vùng bị ngắt liên lạc và mỗi vùng nhận một đơn đặt hàng. Nếu cả hai đều cho phép trừ một đơn vị từ cùng một tồn kho toàn cục, hệ thống có thể oversell.

Nếu yêu cầu bất biến là **không được xác nhận bán vượt số lượng đã được dành**, ta có thể chọn chỉ cho phép vùng còn quorum xác nhận reservation; vùng khác nhận trạng thái “chưa thể đặt hàng”, “đang chờ xác nhận” hoặc yêu cầu thử lại.

~~~text
Reserve 1 sản phẩm
       |
       v
 Có thể xác nhận trạng thái mới nhất và commit an toàn?
       |                                  |
      Có                                 Không
       |                                  |
  Tạo reservation atomically      Không xác nhận đã giữ hàng
  và trả CONFIRMED                Trả PENDING / UNAVAILABLE
~~~

Trong thực tế, code vẫn cần xử lý đồng thời, idempotency key, transaction boundary và việc thanh toán đã xử lý nhưng phản hồi bị mất. CAP không thay thế các cơ chế bảo đảm tính đúng đắn đó.

### 4.2. CP không đồng nghĩa “toàn hệ thống phải dừng”

Với ba replica chia 1–2, phía đa số có thể tiếp tục phục vụ. Với hai nhóm bằng nhau hoặc một cụm không đạt quorum, có thể không bên nào ghi được. Một số thao tác không cần dữ liệu đang phân hoạch vẫn hoạt động bình thường.

Tùy mô hình, hệ thống còn có thể:

- Cho phép đọc trạng thái cũ nhưng gắn nhãn **stale**, giảm mức bảo đảm của đúng thao tác đọc đó.
- Chuyển traffic tới vùng có quorum nếu đường đi client → vùng đó còn hoạt động.
- Dùng dữ liệu chỉ đọc đã công bố trước cho tác vụ không yêu cầu freshness.
- Trả thông báo đang xử lý thay cho lời hứa đã hoàn thành nghiệp vụ.

Thiết kế cần nói rõ API nào duy trì tính nhất quán mạnh và API nào được phép giảm mức bảo đảm.

## 5. Hành vi AP: tiếp tục phục vụ khi bị chia cắt, chấp nhận dữ liệu có thể lệch

Một thiết kế thường gọi là **AP** khi những nút còn hoạt động trên các phía phân hoạch tiếp tục chấp nhận và trả lời thao tác, dù không thể bảo đảm một thứ tự quan sát linearizable trên toàn hệ thống.

Ví dụ mỗi vùng cho phép người dùng thêm sản phẩm vào danh sách yêu thích:

~~~text
Ban đầu: favorites = {A}

Vùng 1: thêm B -> {A, B}
                     \ 
                      \    mạng đang phân hoạch
                      /
Vùng 2: thêm C -> {A, C}

Sau khi mạng phục hồi:
   hợp nhất theo quy tắc tập hợp -> {A, B, C}
~~~

Nếu dữ liệu được mô hình hóa thành tập có phép hợp nhất phù hợp (ví dụ một loại CRDT thích hợp), hai phía có thể hội tụ mà không làm mất thao tác thêm độc lập. Tuy nhiên xóa phần tử, quyền truy cập, thứ tự ưu tiên hay việc duy trì số lượng chính xác có thể yêu cầu mô hình phức tạp hơn.

**Điểm mấu chốt:** hệ thống AP không có nghĩa “dữ liệu sai cũng không sao”. Nó cần **chính sách hội tụ** và cần biết tính chất nghiệp vụ nào được phép thay đổi tạm thời.

### 5.1. Xử lý xung đột khi mạng nối lại

Nếu hai phía cùng sửa một bản ghi, phải quyết định hợp nhất như thế nào:

| Cơ chế | Ý tưởng | Điều cần cẩn trọng |
| --- | --- | --- |
| Last-write-wins | Chọn một phiên bản theo quy tắc thời gian/phiên bản | Có thể làm mất cập nhật; lệch đồng hồ hoặc timestamp không phản ánh thứ tự nghiệp vụ |
| Merge theo miền | Kết hợp thay đổi dựa trên ý nghĩa dữ liệu | Cần quy tắc rõ khi hai thay đổi xung đột thực sự |
| CRDT | Thiết kế cấu trúc có phép gộp hội tụ khi nhận các cập nhật trùng, trễ, sai thứ tự trong điều kiện mô hình của nó | Không phù hợp với mọi bất biến; phải chọn kiểu dữ liệu và semantics đúng |
| Hòa giải thủ công | Ghi nhận các phiên bản và yêu cầu chủ sở hữu/người dùng xử lý | Tăng chi phí UX, vận hành và truy vết |
| Tách quyền trước | Phân bổ trước quota/escrow/quyền sở hữu tài nguyên cho từng vùng | Mỗi vùng chỉ xử lý được phần quyền đã cấp; phải có quy trình tái phân bổ |

Không thể dùng “eventually consistent” như một câu trả lời đầy đủ nếu chưa định nghĩa: **eventual theo điều kiện nào, hội tụ thành gì, sau bao lâu, và bất biến nào được bảo vệ?**

### 5.2. Có thể duy trì một số ràng buộc ngay cả khi ưu tiên khả dụng

Ví dụ tổng tồn kho là 10 đơn vị, hệ thống **phân bổ trước** quyền giữ 6 đơn vị cho vùng A và 4 đơn vị cho vùng B. Trong phân hoạch, mỗi vùng chỉ xác nhận số reservation nằm trong quota được giao. Khi đó có thể phục vụ nhiều yêu cầu cục bộ mà vẫn không vượt tổng quyền cấp phát.

Sự đánh đổi là một vùng có thể hết quota trong khi vùng kia còn dư, nhưng mạng đang đứt khiến hai vùng chưa thể chuyển quyền. Phân bổ quyền trước phù hợp một số bài toán nhưng không cho phép chấp nhận vô hạn các thao tác toàn cục tùy ý.

Ví dụ này cũng cho thấy **mức bảo đảm phụ thuộc vào mô hình dữ liệu và loại thao tác**. Ta có thể đạt sự sẵn sàng cục bộ với một bất biến nhất định bằng cách hạn chế quyền ghi, không nhất thiết giải quyết mọi thao tác đọc/ghi như một register linearizable duy nhất.

## 6. So sánh hành vi khi có phân hoạch

| Tình huống | Hướng ưu tiên nhất quán mạnh (CP) | Hướng ưu tiên phục vụ (AP) |
| --- | --- | --- |
| Nút không liên lạc được với phía có dữ liệu mới nhất | Hoãn/từ chối thao tác không thể chứng minh đúng | Dùng trạng thái cục bộ theo mức consistency đã công bố |
| Ghi đồng thời ở hai phía | Có cơ chế điều phối, quorum hoặc ownership ngăn commit xung đột | Có thể nhận nhiều cập nhật, sau đó hòa giải/hội tụ |
| Trải nghiệm người dùng | Có thể thấy PENDING, retry hoặc UNAVAILABLE | Có thể thấy thao tác thành công cục bộ nhưng hiển thị trạng thái tạm thời |
| Dữ liệu sau khi mạng nối lại | Đồng bộ replica từ thứ tự commit đã được chấp nhận | Chuyển và hợp nhất các cập nhật phân kỳ |
| Rủi ro nghiệp vụ chính | Một phần yêu cầu không thể hoàn thành lúc phân hoạch | Xung đột, đọc cũ, tác dụng phụ của việc dùng dữ liệu chưa hội tụ |
| Phù hợp hơn khi | Bất biến mạnh, thứ tự thời gian thực hoặc giới hạn tài nguyên toàn cục là điều kiện cứng | Có thể chấp nhận kết quả tạm thời, thao tác hợp nhất được hoặc nghiệp vụ có chiến lược hòa giải |

Bảng chỉ mô tả **hành vi của những thao tác liên quan**, không dán nhãn vĩnh viễn cho cả công ty, cả microservice hoặc mọi endpoint. Một hệ thống có thể dùng strong consistency cho reservation, dữ liệu cache eventual cho danh mục, và queue để xử lý thông báo. Khi các thành phần tương tác, cần đánh giá tính đúng đắn của **toàn workflow**, không chỉ từng database.

## 7. Những giới hạn và cách hiểu sai CAP phổ biến

### Hiểu sai 1: “Hệ thống chỉ được chọn hai trong ba: C, A, P”

Cách nói này che mất điều kiện quan trọng **khi có phân hoạch**. Khi mạng hoạt động tốt, ta có thể cung cấp cả phản hồi khả dụng và linearizable. Khi mạng phân hoạch làm một thao tác không thể biết trạng thái toàn cục, ta phải xem xét ưu tiên C hoặc A cho thao tác đó.

Với hệ phân tán thực, không thể đảm bảo mãi mãi không có partition; nói “chọn CA, bỏ P” mà vẫn triển khai trên nhiều máy qua mạng thực thường chỉ có nghĩa đang **giả định mạng không hỏng**. Khi giả định đó thất bại, thiết kế vẫn phải có hành vi xác định.

### Hiểu sai 2: “P là điều kiện để hệ thống luôn hoạt động nếu một node chết”

Phân hoạch mạng và lỗi máy chủ là hai mô hình sự cố khác nhau. P là khả năng vẫn xác định được hành vi khi các nút không liên lạc được; chịu lỗi node còn phụ thuộc replication, quorum, leader election, vùng lỗi độc lập, durability và recovery.

### Hiểu sai 3: “CAP Consistency chính là ACID Consistency”

ACID liên quan tính atomicity, consistency theo invariant, isolation và durability của transaction. CAP thường xét linearizability của đối tượng dữ liệu phân tán. Một database có transaction ACID nội bộ không vì vậy mà mọi read replica qua mạng có thể đọc nhất quán tuyến tính. Ngược lại, một key-value store có linearizable read/write đơn key chưa có nghĩa hỗ trợ transaction ACID đa bản ghi.

Cũng cần phân biệt:

- **Strong/linearizable consistency:** phản hồi quan sát được như một bản sao duy nhất và tuân theo thứ tự thời gian thực.
- **Sequential consistency:** có một thứ tự toàn cục bảo toàn thứ tự thao tác từng client nhưng không nhất thiết bảo toàn thời gian thực giữa các client.
- **Causal consistency:** các thao tác có quan hệ nhân quả được quan sát theo thứ tự nhân quả.
- **Eventual consistency:** nếu không có cập nhật mới và điều kiện giao tiếp/đồng bộ phù hợp được khôi phục, các bản sao cuối cùng có thể hội tụ.
- **Session guarantees:** read-your-writes, monotonic reads, v.v. có thể cải thiện trải nghiệm dù không đạt linearizability trên mọi nút.

Những mức nhất quán này khác nhau; không nên gom tất cả thành nhãn “C” hoặc “không C”.

### Hiểu sai 4: “AP nghĩa là eventual consistency, CP nghĩa là mọi thao tác đều có transaction”

AP thường đi kèm các mô hình hội tụ, nhưng việc công bố eventual consistency không tự động chứng minh hệ thống khả dụng dưới mọi phân hoạch. Một dịch vụ eventual consistency vẫn có thể từ chối thao tác vì leader, thiếu local replica, chính sách bảo mật hoặc quá tải. Tương tự, CP không bảo đảm transaction nhiều bảng, nhiều service, hoặc atomic workflow nghiệp vụ.

### Hiểu sai 5: “CAP Availability = uptime 99,99%”

Một hệ thống 99,99% uptime có thể từ chối yêu cầu ở phân vùng thiểu số để bảo toàn consistency, trong khi vẫn đạt tỷ lệ thành công thống kê cao cả tháng. Hai khái niệm đo những thứ khác nhau. Với sản phẩm, vẫn cần SLO latency, error budget, recovery time, throughput và khả năng xử lý trạng thái pending.

### Hiểu sai 6: “Nếu chọn AP, cứ thêm retry là dữ liệu sẽ đúng”

Retry không giải quyết các xung đột ngữ nghĩa. Một message bị gửi lặp, ghi trễ hoặc đảo thứ tự có thể gây trừ tiền hai lần, trả lại hàng sai hoặc ghi đè thay đổi mới. Cần idempotency, versioning, deduplication, chính sách merge và reconciliation theo nghiệp vụ.

### Hiểu sai 7: “CAP phân loại được toàn bộ hệ thống microservices chỉ bằng một nhãn”

Trong một sản phẩm có hàng chục luồng, cùng một service có thể cung cấp những endpoint với mức consistency khác nhau. Bản thân một request HTTP giữa API Gateway và Payment Service chưa đủ dữ kiện để kết luận “chọn CP/AP”; trước hết cần xác định **đối tượng dữ liệu nào có replica, thao tác nào cần một thứ tự chung, và chuyện gì xảy ra khi liên lạc giữa các replica bị cắt**.

### Hiểu sai 8: “Hễ không có partition là không phải đánh đổi nữa”

Ngay cả lúc không phân hoạch, hệ thống có thể phải chọn mức consistency mạnh với chi phí tăng latency, hoặc phản hồi nhanh từ replica gần người dùng với khả năng đọc cũ. CAP không mô tả toàn bộ các đánh đổi về latency, throughput, chi phí lưu trữ, hiệu năng tải cao hay chi phí bảo trì.

## 8. PACELC: mở rộng tư duy cho cả lúc mạng bình thường

Một cách bổ sung cho CAP là mô hình **PACELC**, mô tả hai câu hỏi:

~~~text
Nếu có Partition (P):
  đánh đổi giữa Availability (A) và Consistency (C).

Else (E) — khi không có partition:
  đánh đổi giữa Latency (L) và Consistency (C).
~~~

Ví dụ có hai replica ở hai châu lục:

- Nếu buộc xác nhận ghi sau khi đồng bộ qua vùng địa lý xa, việc trả lời có thể chậm hơn nhưng dễ cung cấp bảo đảm nhất quán mạnh.
- Nếu chấp nhận đọc từ bản sao gần người dùng hoặc ghi cục bộ, latency có thể thấp hơn nhưng mức freshness hoặc linearizability cần được nêu cụ thể.
- Nếu vùng xa tạm không liên lạc, những thao tác cần đồng thuận nhiều vùng có thể bị chặn; còn thao tác cục bộ có thể tiếp tục với mức bảo đảm khác.

PACELC là **mô hình suy nghĩ về tradeoff**, không phải phép đo tự động hay nhãn chính xác cho mọi hệ thống. Nhiều database cho phép thay đổi consistency theo thao tác; đường đi request, quorum, topology và thiết kế dữ liệu quyết định kết quả thực tế.

Vì vậy khi chọn database, nên đọc và kiểm thử bảo đảm cụ thể: mức đọc/ghi được hỗ trợ, cơ chế commit, multi-region replication, phản hồi khi mất quorum, latency đo được và phương thức failover. Tên “CP/AP” trong tài liệu giới thiệu chỉ là điểm bắt đầu.

## 9. Áp dụng CAP vào kiến trúc Microservices

### 9.1. Đừng nhầm ranh giới service với ranh giới dữ liệu

Một hệ thống có thể gồm Order Service, Inventory Service, Payment Service và Catalog Service. CAP liên quan trực tiếp nhất tới những đối tượng/dịch vụ lưu trạng thái bị phân tán và cần điều phối. Ví dụ:

~~~text
              Client
                |
                v
           API Gateway
                |
         +------+------+------------------+
         |             |                  |
         v             v                  v
    Order Service  Catalog Service   Payment Service
         |             |                  |
         v             v                  v
    Order Store   Replica/Cache      Payment Store
         |
         v
    Inventory Service -> Inventory Replica Group
         |
         v
    Event Broker -> Notification Consumer
~~~

Không thể chỉ nhìn sơ đồ có nhiều ô và kết luận “microservices là AP”. Phải xét từng thành phần: dữ liệu được nhân bản thế nào, client gọi vào đâu, nơi nào quyết định ghi, network partition xảy ra ở liên kết nào và phản hồi nào được xem là thành công.

### 9.2. Đơn hàng và kho: giữ bất biến trước

Ví dụ tồn kho còn một sản phẩm và hai vùng đang mất kết nối. **Bất biến nghiệp vụ** là không được xác nhận hai reservation cho cùng một đơn vị tồn.

Hướng an toàn thường là một nguồn dữ liệu có thẩm quyền cùng transaction hoặc consensus bảo vệ reservation. Vùng không thể xác nhận phải trả trạng thái chưa chắc chắn/không thể đặt hàng, không tự xác nhận đơn đã thành công.

Nếu yêu cầu sản phẩm bắt buộc nhận đơn offline, có thể **tách “tiếp nhận yêu cầu” khỏi “xác nhận hàng đã được giữ”**:

~~~text
Nhận yêu cầu lúc offline -> ACCEPTED_FOR_PROCESSING
                                 |
                               đồng bộ
                                 |
                      Kiểm tra tồn và reserve an toàn
                        /                    \
                 CONFIRMED                  REJECTED
~~~

Việc nhận yêu cầu xử lý là khả dụng hơn, nhưng cam kết nghiệp vụ của nó yếu hơn so với “đã giữ được hàng”. API và giao diện phải thể hiện chính xác sự khác biệt.

### 9.3. Thanh toán: timeout không chứng minh thất bại

Payment Service có thể đã ghi thành công giao dịch trước khi response bị mất. Nếu Order Service chỉ thấy timeout và gửi lại lệnh charge bằng mã mới, khách hàng có nguy cơ bị trừ tiền hai lần.

Cách thiết kế:

1. Mỗi lần dự định thanh toán dùng một **idempotency key** ổn định; Payment định nghĩa rõ phạm vi và thời gian lưu của key.
2. Nếu timeout, truy vấn trạng thái giao dịch theo idempotency key hoặc mã giao dịch; không tự ý kết luận thất bại.
3. Chỉ chuyển Order sang PAID khi có bằng chứng xử lý thanh toán phù hợp.
4. Có quy trình reconciliation, compensation/refund và xử lý trường hợp callback/event đến trễ hoặc trùng.
5. Phân biệt trạng thái UNKNOWN/PENDING với FAILED để tránh nói sai với người dùng.

Đây là bài toán consistency và failure handling của **workflow**. CAP giải thích vì sao không thể hứa phản hồi chắc chắn trong mọi tình huống mạng bị cắt; Saga, outbox, idempotency và reconciliation giải quyết những phần còn lại của luồng nghiệp vụ.

### 9.4. Giỏ hàng và danh sách yêu thích: có thể ưu tiên phục vụ

Chức năng thêm sản phẩm vào favorites thường chấp nhận người dùng thao tác khi offline rồi đồng bộ sau. Có thể dùng event/operation id và phép merge phù hợp với kiểu dữ liệu.

Tuy nhiên giỏ hàng có số lượng, xóa, khuyến mãi và xác nhận giá mới phức tạp hơn một tập hợp chỉ có thao tác thêm. Cần định nghĩa rõ xóa thắng thêm hay ngược lại, xung đột số lượng thế nào, và **checkout phải kiểm tra lại giá/tồn kho** tại thời điểm đặt hàng. Khả năng thêm vào giỏ không phải lời hứa đã giữ hàng.

### 9.5. Catalog và nội dung đọc: đọc cũ có thể chấp nhận, tùy thuộc ngữ cảnh

Danh mục sản phẩm, hướng dẫn, ảnh và cấu hình ít rủi ro có thể dùng cache, CDN hoặc read replica với mức trễ công bố. Trái lại, giá hợp đồng, quyền truy cập hoặc trạng thái ngừng bán có thể đòi bảo đảm mới hơn tùy sản phẩm.

Cần nêu tuổi dữ liệu, cách invalidation, TTL, hành vi khi không cập nhật được và dữ liệu nào không được dùng để đưa ra quyết định tài chính. Nếu đọc cache cũ trong sự cố, hãy coi đó là **degraded consistency mode** của endpoint, không tuyên bố vừa có linearizability vừa dùng tùy ý bản cũ.

### 9.6. Broker và giao tiếp bất đồng bộ không tự làm hệ thống AP

Đẩy event qua broker giúp tách thời điểm hoạt động giữa producer và consumer, nhưng broker cũng có replica, leader, partition, retention, backpressure và yêu cầu consistency riêng. Producer có thể không publish được, consumer có thể trễ, gửi lặp hoặc xử lý sai thứ tự.

Để giảm tác động khi mất mạng:

- Dùng transactional outbox nếu cần tránh database commit mà sự kiện liên quan bị mất.
- Thiết kế consumer idempotent, có retry có giới hạn và dead-letter handling.
- Theo dõi queue depth, consumer lag, tuổi message và thời gian từ phát event tới áp dụng.
- Định nghĩa nghiệp vụ có cho phép “event đã được nhận” nhưng “quy trình chưa hoàn thành” hay không.
- Khi phục hồi, replay và reconciliation dựa vào nguồn dữ liệu có thẩm quyền.

**Eventual consistency giữa các service** không đồng nghĩa mọi thành phần hay mọi yêu cầu trong hệ đều AP theo CAP.

## 10. Tình huống phân tích: tồn kho một sản phẩm trên hai vùng

Giả sử hệ thống có hai vùng Đông và Tây, cùng phục vụ đơn hàng. Một SKU chỉ còn một sản phẩm. Cả hai vùng nhận yêu cầu mua gần như cùng lúc, nhưng liên kết đồng bộ giữa hai vùng vừa bị đứt.

**Yêu cầu 1:** không bán vượt kho. **Yêu cầu 2:** khách ở cả hai vùng đều muốn đặt hàng ngay. Đây là hai nhu cầu có thể xung đột khi một đơn vị tồn kho toàn cục phải được điều phối.

### Phương án A — Giữ một vùng có thẩm quyền

~~~text
  Vùng Đông                  Vùng Tây
  request A                  request B
      |                          |
   owner/quorum             không thấy owner/quorum
      |                          |
   xác nhận đặt             chưa thể xác nhận
~~~

Ưu tiên bảo đảm số lượng được giữ là chính xác. Một phía có thể bị từ chối/đợi hoặc phải chuyển hướng traffic sang phía có thẩm quyền nếu đường mạng client còn cho phép. Đây là lựa chọn phù hợp khi oversell gây hậu quả đáng kể.

### Phương án B — Cả hai phía đều xác nhận bán hàng

Hai phía đều nhìn thấy tồn = 1 và đều trừ 1. Khi mạng nối lại, tổng số đơn đã xác nhận là 2 trong khi kho chỉ có 1. Nếu cam kết với khách là “đã đặt được hàng”, mô hình này vi phạm bất biến nghiệp vụ; một bước hòa giải sau đó sẽ phải hủy/bù một đơn. Không thể che giấu hậu quả bằng cách gọi đây là “eventual consistency”.

### Phương án C — Nhận đơn chờ xác nhận

Cả hai phía có thể tiếp nhận ý định mua và cấp mã theo dõi, nhưng ghi rõ “đang kiểm tra tồn”. Khi đồng bộ trở lại, hệ thống dùng nguồn tồn kho có thẩm quyền để quyết định đơn nào được xác nhận. Khả năng **tiếp nhận** được giữ cao, nhưng tính **hoàn tất nghiệp vụ ngay** thấp hơn.

### Phương án D — Phân quyền giữ chỗ trước

Nếu nhiều SKU và số lượng đủ lớn, mỗi vùng có thể được phân bổ trước quyền giữ một phần tồn kho. Mỗi vùng chỉ xác nhận trong hạn mức của mình. Mô hình này giảm phụ thuộc liên vùng khi phân hoạch, nhưng có thể khiến một vùng báo hết quota dù vùng kia còn hàng; phải có cơ chế cân bằng lại quyền khi mạng phục hồi.

**Bài học:** cùng một yêu cầu “website vẫn hoạt động khi mạng đứt”, có nhiều cách định nghĩa trạng thái thành công. Cần tách “đã nhận request”, “đã ghi ý định”, “đã reserve” và “đã thanh toán” vì mỗi cam kết kéo theo bảo đảm dữ liệu khác nhau.

## 11. Cách chọn tradeoff theo loại thao tác

Thay vì gán nhãn toàn hệ thống, lập bảng quyết định cho từng **lệnh, truy vấn và bất biến**:

| Thao tác | Mức đúng đắn cần giữ | Phản ứng hợp lý khi phân hoạch | Hệ quả cần công bố |
| --- | --- | --- | --- |
| Giữ chỗ tồn kho hiếm | Không hai đơn cùng chiếm một đơn vị quyền giữ | Chỉ commit khi có thẩm quyền/quorum; nếu không thì PENDING/UNAVAILABLE | Có thể từ chối hoặc chậm xác nhận |
| Thanh toán | Không charge trùng; trạng thái có bằng chứng | Idempotency, query trạng thái, reconcile; không đoán kết quả | UNKNOWN/PENDING có thể xuất hiện |
| Xem danh mục | Cho phép trễ ngắn theo chính sách | Dùng bản sao/cache phù hợp | Có thể thấy dữ liệu cũ |
| Thêm yêu thích | Hợp nhất được thao tác độc lập | Ghi cục bộ và đồng bộ/hợp nhất | Cập nhật có thể xuất hiện muộn ở thiết bị khác |
| Gửi thông báo | Chống gửi trùng khi cần và không làm hỏng giao dịch chính | Xếp hàng, retry, deduplication | Thông báo có thể trễ |
| Xem dashboard phân tích | Chấp nhận số liệu gần thời gian thực | Đọc snapshot gần nhất kèm timestamp | Kết quả chưa phản ánh tất cả giao dịch mới |
| Thay đổi quyền bảo mật | Quyền bị thu hồi phải được áp dụng theo chính sách rủi ro | Có thể fail closed khi không xác thực được trạng thái quyền mới nhất | Một số thao tác bị chặn trong sự cố |

Bảng là ví dụ thiết kế, **không phải quy định phổ quát**. Chẳng hạn quyền bảo mật có thể đòi mức freshness khác nhau; một số tác vụ xem catalog cũng phải chặn khi thông tin giá hoặc pháp lý quá cũ.

### 11.1. Những câu hỏi quyết định

1. **Đối tượng dữ liệu nào?** Bản ghi đơn hàng, số dư, quota, giỏ hàng hay cache? Có bao nhiêu replica và ai có quyền ghi?
2. **Bất biến nào không được vi phạm?** Không trừ tiền trùng, không vượt tồn, không cấp quyền trái phép, hay chỉ cần hội tụ?
3. **Người dùng được hứa gì khi nhận SUCCESS?** “Đã nhận yêu cầu” khác “đã hoàn thành”; phản hồi HTTP 202/200/201 phải phản ánh semantics thực tế.
4. **Khi partition kéo dài, bên nào được tiếp tục?** Đa số nút, vùng sở hữu dữ liệu, hay mọi vùng theo quota phân trước?
5. **Nếu chọn trả dữ liệu cũ, độ cũ tối đa và UX là gì?** Cần session guarantee, version, timestamp hoặc nhãn degraded mode nào?
6. **Nếu hai phía đều ghi, hợp nhất như thế nào?** Có xung đột không thể tự động giải quyết không; ai chịu trách nhiệm hòa giải?
7. **Khi phản hồi mất, request đã thực thi chưa?** Có idempotency key, trạng thái pending, truy vấn kết quả và deduplication không?
8. **Khi mạng nối lại, kiểm chứng gì?** Dữ liệu có hội tụ, sự kiện có bị bỏ sót, quyền ghi cũ có bị fencing và queue có kẹt không?

## 12. Kiến trúc và giao thức giúp hiện thực hóa lựa chọn

### 12.1. Quorum và leader

Consensus/leader-based replication giúp xác định nhóm nào có thể commit thao tác theo một thứ tự được thống nhất. Hệ thống cần ngăn một leader cũ ghi tiếp sau khi đã mất quyền điều hành; có thể dùng term/epoch/fencing token theo cơ chế của nền tảng.

Quorum majority làm giảm nguy cơ hai nhóm độc lập cùng ghi được cùng một lịch sử, nhưng cần hiểu giới hạn số lỗi có thể chịu, topology và kịch bản mất mạng. Cần kiểm thử **cả đọc lẫn ghi**: đọc từ replica chậm có thể không linearizable ngay cả khi ghi đã commit an toàn.

### 12.2. Idempotency, deduplication và trạng thái không chắc chắn

Một request có thể được thực thi thành công nhưng response bị mất. Muốn retry an toàn, client dùng cùng idempotency key và server trả lại cùng kết quả đã ghi nhận cho cùng ý định nghiệp vụ, theo hợp đồng rõ ràng.

~~~text
Client                         Payment
  | POST /charge (key=K)          |
  |------------------------------>|
  |                               | đã charge và ghi nhận K
  |             [mất response]    |
  X                               |
  | POST /charge (key=K)          |
  |------------------------------>|
  |                               | thấy K đã xử lý
  |<------------------------------|
  | trả trạng thái của giao dịch K|
~~~

Không được tự đổi key khi retry cùng ý định thanh toán. Bản ghi key phải được duy trì đủ lâu theo nghiệp vụ và không thể chỉ lưu trong RAM của một replica dễ mất. Đồng thời cần chống reuse key cho một payload khác.

### 12.3. Outbox, event và reconciliation

Nếu transaction nội bộ thành công nhưng phát event ra broker thất bại, các service khác có thể không bao giờ biết thay đổi. Transactional Outbox giúp gắn việc ghi sự kiện vào cùng commit cục bộ của dữ liệu nghiệp vụ. Dispatcher gửi đi sau; consumer vẫn cần idempotent vì event có thể được gửi lại.

Reconciliation là quá trình kiểm tra sự khác biệt giữa nguồn dữ liệu chính và các read model/các hệ phụ thuộc, sửa lại trạng thái hoặc đưa tác vụ vào hàng xử lý sự cố. Đây là cơ chế quan trọng cho workflow nhiều service và không thể thay bằng chỉ một tuyên bố “eventual consistency”.

### 12.4. Cache, stale reads và phiên bản dữ liệu

Khi muốn tiếp tục phục vụ truy vấn trong partition, có thể dùng cache với TTL, read replica hoặc local snapshot. API nên nêu rõ đặc tính freshness và tránh sử dụng kết quả cũ để ra quyết định cần dữ liệu mới nhất.

Có thể kèm version/ETag, timestamp nguồn hoặc policy cache; với thao tác ghi, dùng điều kiện version nhằm phát hiện concurrent modification khi mô hình cho phép. Version check trên một replica cục bộ **không tự giải quyết** xung đột giữa hai vùng không liên lạc, nên vẫn cần owner/quorum hoặc merge.

## 13. Kiểm thử CAP dưới sự cố mạng thực tế

Để biết hệ thống thực sự thực hiện cam kết, chỉ kiểm thử “tắt hẳn một pod” là chưa đủ. Cần mô phỏng **những nút vẫn sống nhưng liên lạc bị đứt hoặc chập chờn**. Môi trường thử có thể dùng network fault injection, proxy giả lập lỗi, chính sách mạng hoặc chaos test ở staging, phù hợp nền tảng đang vận hành.

### 13.1. Bộ tình huống tối thiểu

- Chia cụm 3 replica thành 1–2; gửi read/write từ cả hai nhóm. Xác minh phía không có quyền không xác nhận thao tác vi phạm bảo đảm strong consistency.
- Chia cụm 2–2 hoặc cắt đường tới quorum; đo hành vi timeout, retry và trạng thái người dùng.
- Gửi WRITE thành công tại phía có quorum, sau đó READ từ đường truy cập khác; xác minh freshness theo consistency đã công bố.
- Mô phỏng mất response **sau khi server đã commit**; retry cùng idempotency key không tạo giao dịch kép.
- Cố ý làm leader cũ “sống lại” sau failover; bảo đảm fencing/ngữ cảnh term chặn thao tác không hợp lệ.
- Với dữ liệu được phép phân kỳ, ghi xung đột ở cả hai phía; nối mạng lại và xác minh quy tắc merge, không mất cập nhật ngoài dự kiến.
- Mô phỏng event duplicate, reorder, queue lag và dead-letter; kiểm tra trạng thái cuối và quy trình reconciliation.
- Đo thời gian hệ thống chuyển sang degraded mode, thời gian phục hồi, p95/p99, tỷ lệ request lỗi, số tác vụ PENDING quá hạn và số sai lệch dữ liệu còn tồn.

### 13.2. Bằng chứng cần lưu

Không chỉ ghi “test pass”, hãy lưu topology phân hoạch, thao tác và thứ tự thời gian, request ID/idempotency key, trạng thái replica/leader, commit index hoặc version nếu có, log/tracing tương ứng, phản hồi người dùng và kết quả đối chiếu sau phục hồi.

Một kiểm thử CAP có giá trị phải chỉ ra **cam kết nào được bảo vệ và thao tác nào mất khả dụng hoặc giảm consistency**, chứ không chỉ chứng minh dịch vụ tự khởi động lại.

### 13.3. Quan sát trong production

Theo dõi những tín hiệu tương ứng với tradeoff đã chọn: quorum loss, leader changes, replication lag, stale read rate, conflict rate, số lần phải merge thủ công, retry rate, duplicate command, consumer lag, thời gian PENDING và chi phí phục hồi. Cảnh báo theo ảnh hưởng nghiệp vụ (đơn không xác nhận, thanh toán không rõ trạng thái, dữ liệu quyền truy cập quá cũ), thay vì chỉ quan sát CPU hay số pod đang chạy.

Nếu chủ động chọn CP cho thao tác quan trọng, việc trả lỗi khi mất quorum có thể là **hành vi đúng để giữ an toàn dữ liệu**. Nhưng vẫn cần cảnh báo vận hành và kế hoạch khôi phục; không nên tô đẹp lỗi đó thành “hệ thống hoàn toàn khả dụng”.

## 14. Tóm tắt bản chất của CAP

- **CAP Consistency** là tính chất quan sát như một bản sao duy nhất theo thứ tự thời gian thực (linearizability); không phải đồng nghĩa với ACID Consistency.
- **CAP Availability** yêu cầu các nút không bị hỏng phục vụ thao tác hợp lệ; không phải chỉ trả HTTP response nhanh hoặc đạt một tỷ lệ uptime theo tháng.
- **Partition** là tình huống các nút còn hoạt động nhưng không thể trao đổi thông tin đáng tin cậy. Hệ thống thực tế phải chuẩn bị cho tình huống này.
- **Khi partition ảnh hưởng thao tác, không thể đồng thời cam kết C và A theo nghĩa CAP**. Có thể giữ C bằng cách từ chối/hoãn một số thao tác, hoặc giữ A bằng cách chấp nhận mức nhất quán yếu hơn với cơ chế hội tụ/hòa giải.
- **Hành vi phụ thuộc từng đối tượng dữ liệu và từng thao tác**. Không nên gán nhãn CP/AP cho toàn bộ kiến trúc microservices mà bỏ qua ranh giới dữ liệu, lời hứa với người dùng và sự cố thực tế.
- **CAP không mô tả mọi tradeoff**. Khi mạng bình thường vẫn phải cân nhắc latency–consistency (PACELC), và luôn cần xử lý timeout, retry, idempotency, Saga/outbox, bảo mật, quan sát và khôi phục.
- **Ưu tiên bắt đầu từ bất biến nghiệp vụ**: điều gì tuyệt đối không được sai; điều gì có thể chờ; điều gì có thể hiển thị cũ; điều gì có thể hội tụ sau khi mạng phục hồi.

### Câu hỏi tự kiểm tra

1. Hai replica không liên lạc. A xác nhận thành công ghi X = 5; sau đó B được hỏi giá trị X. Vì sao B không thể vừa trả lời theo dữ liệu cũ vừa cam kết linearizability?
2. Một dịch vụ trả HTTP 503 ngay khi mất quorum. Việc phản hồi nhanh này có thỏa availability theo CAP không? Vì sao?
3. Nếu hai vùng cùng nhận đơn mua một sản phẩm duy nhất, phân biệt “đã nhận yêu cầu” với “đã giữ hàng” giúp thay đổi lời hứa nghiệp vụ thế nào?
4. Vì sao database hỗ trợ transaction ACID không đủ để kết luận mọi read replica của nó là linearizable?
5. Khi mạng bình thường, đọc replica gần người dùng để giảm latency tạo ra loại tradeoff nào mà câu nói “chọn hai trong ba” không mô tả?
6. Hãy thiết kế hai endpoint: một endpoint giữ chỗ tồn kho và một endpoint lưu danh sách yêu thích. Ghi rõ mức consistency, hành vi khi partition, cách retry, cách phục hồi và trạng thái UI cho từng endpoint.

Có thể coi một quyết định CAP là hoàn chỉnh khi đội phát triển trả lời được: **“Nếu mạng bị chia ngay giữa một thao tác đã được người dùng gửi, hệ thống sẽ phản hồi chính xác điều gì, giữ invariant nào, và làm sao sửa hoặc hoàn tất những việc còn dở sau khi mạng phục hồi?”**

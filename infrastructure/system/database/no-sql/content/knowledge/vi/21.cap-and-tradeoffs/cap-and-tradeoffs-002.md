# Ý nghĩa consistency, availability và partition tolerance trong định lý

Trong hệ thống NoSQL phân tán, dữ liệu có thể nằm trên nhiều máy và được nhân bản để tăng khả năng mở rộng hoặc chịu lỗi. Một câu hỏi nền tảng là: **khi mạng bị chia cắt, hệ có thể vừa cho mọi phía tiếp tục phục vụ yêu cầu vừa bảo đảm mọi thao tác đọc/ghi quan sát như trên một bản dữ liệu duy nhất hay không?**

**Định lý CAP** trả lời câu hỏi đó trong một mô hình phân tán xác định. Ba chữ cái chỉ:

- **C — Consistency:** trong cách phát biểu CAP thông dụng và chặt chẽ, là **linearizability** hay *atomic consistency* của các thao tác trên đối tượng dữ liệu: hành vi đọc/ghi phải tương đương một thứ tự tuần tự hợp lệ, tôn trọng thứ tự thời gian thực.
- **A — Availability:** mọi yêu cầu gửi tới một node **không bị lỗi** trong phạm vi được xét cuối cùng phải nhận được **một kết quả hợp lệ**, không bị hệ thống treo hoặc từ chối vĩnh viễn chỉ vì không liên lạc được với phía khác.
- **P — Partition tolerance:** mô hình cho phép **mất, trễ vô hạn hoặc gián đoạn trao đổi thông điệp giữa các nhóm node**; hệ thống phải được đánh giá cả khi những phân vùng mạng như vậy xảy ra.

Điều thường được tóm tắt thành “chọn hai trong ba” cần được hiểu chính xác hơn:

> **Nếu một phân vùng mạng có thể xảy ra, một hệ đọc/ghi trên dữ liệu được nhân bản không thể bảo đảm đồng thời linearizability và availability vô điều kiện cho mọi phía của phân vùng.**

CAP **không** nói rằng mọi NoSQL DBMS cố định mãi mãi thuộc một trong ba loại, **không** nói chỉ có hai ưu tiên về hiệu năng, và **không** dùng chữ C để nói về ràng buộc nghiệp vụ của ACID.

Bài này trình bày từng thuộc tính dựa trên **lịch sử thao tác đọc/ghi**, chứng minh trực giác vì sao xuất hiện đánh đổi, xem các lựa chọn CP/AP trong một ví dụ cụ thể, rồi áp dụng vào replication, quorum, thanh toán, tồn kho, giỏ hàng và thiết kế API.

## 1. Bối cảnh: một khóa dữ liệu, hai bản sao

Giả sử hệ lưu một khóa `stock:SKU-7`, giá trị ban đầu là 10, trên hai node:

~~~text
                     Trạng thái ban đầu

       Node A                                 Node B
  stock:SKU-7 = 10                       stock:SKU-7 = 10
          │                                     │
          └────────── mạng liên lạc ────────────┘
~~~

Mọi thứ đơn giản khi A và B trao đổi thông điệp bình thường. Client có thể ghi lên A và một cơ chế replication chuyển thay đổi sang B.

Nhưng giả sử mạng bị chia:

~~~text
       Node A               X X X             Node B
  stock:SKU-7 = 10       Không liên lạc    stock:SKU-7 = 10
        ▲                                         ▲
        │                                         │
     Client 1                                  Client 2
~~~

Client 1 gửi:

~~~text
write(stock:SKU-7, 9)
~~~

Client 2 gửi:

~~~text
read(stock:SKU-7)
~~~

Nếu A xác nhận write thành công nhưng không thể thông báo cho B, B phải làm gì?

1. **Trả 10 ngay:** giúp client 2 tiếp tục đọc nhưng có thể là giá trị cũ.
2. **Chờ hoặc từ chối đọc cho tới khi biết giá trị mới:** bảo vệ yêu cầu đọc mới nhất, nhưng client 2 không còn được phục vụ vô điều kiện.
3. **Đoán 9:** không hợp lệ; B không thể biết A đã ghi 9, 8 hay chưa ghi gì.

Đây là mâu thuẫn cơ bản của CAP. Để hiểu đầy đủ, trước tiên phải làm rõ “nhất quán”, “sẵn sàng” và “phân vùng” là những thuộc tính **có định nghĩa**, không chỉ là ba khẩu hiệu.

## 2. CAP nói về hệ phân tán chứ không phải một bảng đơn lẻ

Một hệ phân tán có thể gồm:

~~~text
                         Client / API
                             │
                   Routing / Coordinator
                      ┌──────┴──────┐
                      ▼             ▼
                    Node A        Node B
                   Replica 1     Replica 2
                      │             │
                      └──────┬──────┘
                             ▼
                      Replication / repair
~~~

Ba khái niệm cần tách:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Replication** | Nhiều bản sao logic của dữ liệu |
| **Partitioning/sharding dữ liệu** | Chia dữ liệu thành các nhóm khóa được giao cho những node khác nhau |
| **Network partition** | Các nhóm node không thể trao đổi thông điệp như bình thường |

**Data partition** và **network partition** không phải một. Một DBMS có thể chia dữ liệu thành 100 shard và hoạt động bình thường. CAP quan tâm tới trường hợp **kết nối giữa các thành phần cần phối hợp bị lỗi**, khiến nhóm này không thể xác nhận thông tin từ nhóm kia.

### Một hệ có sharding nhưng không nhân bản?

Nếu mỗi khóa chỉ tồn tại trên một node, một client ở phía mạng không thể truy cập node chủ của khóa đó có thể **không đọc được khóa**. Vấn đề availability vẫn tồn tại, nhưng mâu thuẫn đọc giá trị cũ trên nhiều replica được nhìn thấy rõ nhất ở mô hình **nhiều bản sao cùng phục vụ một dữ liệu logic**.

CAP áp dụng cho các bảo đảm của dịch vụ trong môi trường thông điệp có thể mất, chứ không yêu cầu mọi hệ phải có cùng sơ đồ replication.

## 3. Đọc CAP bằng một lịch sử thao tác

Một **history** lưu những sự kiện client gọi và nhận phản hồi:

~~~text
inv_A(write(x,1))
ret_A(OK)
inv_B(read(x))
ret_B(0)
~~~

Giả sử `x` ban đầu bằng 0 và không có write nào khác. Điểm quan trọng là:

~~~text
Write của A đã trả OK
             trước khi
Read của B bắt đầu
~~~

Ta gọi đây là **thứ tự thời gian thực** giữa hai thao tác không chồng lấn.

### Hai lịch có kết quả đọc cũ nhưng khác ý nghĩa

**Lịch H1 — đọc chồng lên lúc ghi:**

~~~text
Thời gian ──────────────────────────────────────>

A: [──────── write x=1 ───────────] OK
B:       [──── read x ────] 0
~~~

Nếu B đọc trong lúc A vẫn đang ghi, ta có thể đặt điểm hiệu lực của read **trước** write. Đọc 0 **có thể** linearizable.

**Lịch H2 — đọc sau khi write đã hoàn thành:**

~~~text
Thời gian ──────────────────────────────────────>

A: [── write x=1 ──] OK
B:                         [── read x ──] 0
~~~

Không thể đặt B trước A mà vẫn tôn trọng thời gian thực. Với một thanh ghi chỉ có các thao tác trên, H2 **vi phạm linearizability**.

Điều này quan trọng vì CAP không đơn thuần nói “các node có cùng value trong cùng một mili giây hay không”. Nó nói về **lịch sử client được phép quan sát khi thao tác hoàn thành và đọc/ghi chồng lấn**.

## 4. C trong CAP: consistency nghĩa là linearizability

Trong phát biểu CAP cổ điển, **Consistency (C)** thường được formal hóa như **atomic consistency**, tương đương với **linearizability của thao tác trên đối tượng được xét**.

Một history linearizable nếu có thể tưởng tượng mỗi thao tác xảy ra **tức thời tại một điểm** giữa thời điểm gọi và nhận phản hồi, sao cho:

1. Kết quả phù hợp với **đặc tả tuần tự** của đối tượng.
2. Nếu thao tác P hoàn thành trước khi Q bắt đầu, P phải đứng trước Q trong thứ tự đó.
3. Các thao tác đang chồng lấn có thể được sắp theo một thứ tự hợp lệ nếu kết quả cho phép.

### Đặc tả một thanh ghi đơn giản

~~~text
register x, initial value = 0

write(x, v):
  giá trị hiện tại trở thành v
  trả OK

read(x):
  trả giá trị hiện tại
~~~

Lịch tuần tự hợp lệ:

~~~text
write(x,1) → OK
read(x)    → 1
write(x,2) → OK
read(x)    → 2
~~~

Trong mô hình linearizable, nếu `write(x,1)` đã hoàn thành và không có write nào làm x đổi lại, một `read(x)` bắt đầu sau đó **không được trả 0**.

### C không có nghĩa “mọi node luôn giống hệt nhau trong RAM”

Một hệ có thể có replica chưa cập nhật **bên trong** nhưng vẫn phục vụ reads linearizable bằng cách:

- Định tuyến đọc tới leader hoặc nơi có trạng thái đáng tin.
- Phối hợp quorum/giao thức xác nhận phiên bản.
- Chờ replica bắt kịp rồi mới trả giá trị.
- Từ chối hoặc không hoàn thành yêu cầu khi không thể xác nhận trạng thái.

Nhất quán là ràng buộc **hành vi có thể quan sát**, không yêu cầu mọi bản sao vật lý phải đồng bộ cùng một chu kỳ CPU.

### Linearizability của một key không tự tạo transaction nhiều key

Giả sử chuyển 100 đơn vị tiền:

~~~text
write(wallet:A, oldA - 100)
write(wallet:B, oldB + 100)
~~~

Hai write riêng lẻ đều có thể linearizable, nhưng một reader ở giữa vẫn thấy A đã trừ còn B chưa cộng. Nếu nghiệp vụ yêu cầu **chuyển tiền nguyên tử**, cần transaction hoặc cấu trúc ledger/giao thức phù hợp.

**Ranh giới C phải ghi rõ:** một key, một document, một object, một transaction hay một API tổng hợp?

## 5. C của CAP khác C của ACID

Đây là nhầm lẫn phổ biến nhất:

| Thuật ngữ | Câu hỏi cần trả lời |
| --- | --- |
| **CAP Consistency** | Client có thể quan sát những thứ tự đọc/ghi nào? Có linearizable không? |
| **ACID Consistency** | Các giao dịch đã commit có bảo toàn constraint/invariant được định nghĩa không? |
| **Transaction isolation** | Các giao dịch đồng thời có nhìn và ảnh hưởng nhau theo mức nào? |
| **Replica convergence** | Các bản sao đã hội tụ về trạng thái nào và khi nào? |

Ví dụ kho hàng:

~~~text
available = -3
~~~

Nếu một writer ghi `-3` bằng một thao tác linearizable, hệ có thể **thỏa CAP C cho key** nhưng vẫn phá **bất biến nghiệp vụ** `available >= 0`. Linearizability không tự biết rằng tồn kho không được âm.

Ngược lại, nguồn chính có thể luôn bảo toàn invariant kho nhưng một read replica trả trạng thái cũ sau write đã ACK. Khi đó **bất biến tại nguồn** có thể đúng, song **đường đọc replica** không linearizable.

**Không nên viết “ACID nên là CP” hay “eventual consistency nên không có C của ACID”.** Đó là ghép hai khái niệm ở hai tầng khác nhau.

## 6. A trong CAP: availability là một bảo đảm tiến triển

**Availability (A)** trong CAP không phải “uptime 99,99%” và cũng không phải “p95 dưới 100 ms”.

Ở mức lý thuyết, availability yêu cầu **mỗi request gửi đến một node không bị lỗi phải cuối cùng nhận được một phản hồi hợp lệ** của thao tác, ngay cả khi mạng có phân vùng trong mô hình đang xét.

Ý nghĩa của các từ:

- **Mỗi request:** không chỉ những request dễ xử lý hoặc tới phía có nhiều replica.
- **Node không bị lỗi:** không đòi một máy đã crash trả lời; phân vùng mạng không tự biến node vẫn chạy thành máy đã crash.
- **Cuối cùng:** là thuộc tính liveness; phát biểu CAP cơ bản không đưa ra một deadline theo mili giây.
- **Phản hồi hợp lệ:** đáp ứng ngữ nghĩa của thao tác trong mô hình, không phải cứ trả thông điệp bất kỳ là được.

### Vì sao trả HTTP 503 không chứng minh CAP availability?

Giả sử:

~~~text
GET /stock/SKU-7
  → HTTP 503 Service Unavailable
~~~

Một phản hồi lỗi rõ ràng **rất có ích trong vận hành**: caller không treo vô hạn và có thể retry. Nhưng nó không tương đương với yêu cầu **trả một giá trị đọc hợp lệ** của register trong phát biểu CAP.

Nếu cứ trả `503` rồi tính là “available”, một hệ có thể từ chối tất cả request trong mọi phân vùng và vẫn được gắn nhãn A; điều đó làm định lý mất ý nghĩa.

**Lưu ý về mô hình:** nếu một ứng dụng định nghĩa lỗi là một kết quả nghiệp vụ hợp lệ (ví dụ “không đủ hàng”), cần phân biệt lỗi nghiệp vụ đúng với việc hệ **không thể phục vụ do thiếu phối hợp mạng**. CAP đánh giá thao tác theo đặc tả dịch vụ đã chọn, không theo mọi mã HTTP có thể xuất hiện.

### Availability không đồng nghĩa khả năng hoạt động liên tục của cả cụm

Một dịch vụ có thể xử lý phần lớn traffic từ phía majority trong partition nhưng phía minority không đọc/ghi được một số khóa. Theo định nghĩa A mạnh của CAP, dịch vụ **không bảo đảm availability cho mọi yêu cầu tới mọi non-failing node** trong tình huống ấy, dù chỉ số uptime người dùng trong thực tế vẫn rất cao.

## 7. Phân biệt CAP availability với SLO vận hành

Trong thực tế, team thường nói:

~~~text
Availability SLO: 99.95% request thành công trong 30 ngày
Latency SLO:      p95 < 150 ms
Error budget:     mức lỗi cho phép của kỳ đo
~~~

Đây là những **chỉ tiêu vận hành đo được**. CAP A là một **thuộc tính của thuật toán trong mô hình lỗi**.

| Câu hỏi | CAP availability | SLO/uptime |
| --- | --- | --- |
| Có đòi mọi request tới node sống được trả kết quả hợp lệ? | Theo phát biểu định lý: có | Thường là tỷ lệ yêu cầu trong cửa sổ |
| Có giới hạn 100 ms không? | Không tự xác định | Có thể có latency SLO riêng |
| Trả 503 khi minority không liên lạc được có đủ A không? | Không, nếu thao tác cần trả dữ liệu hợp lệ | Có thể bị tính lỗi theo SLI, phụ thuộc định nghĩa |
| Có thể bảo đảm 99,95% uptime nhưng không thỏa CAP A không? | Có | Có |
| Có thể có thuật toán thỏa CAP A nhưng response rất chậm không? | Về mặt liveness có thể | Có thể vi phạm latency SLO |

Không nên dùng “hệ CP chỉ đạt 50% uptime” hoặc “hệ AP luôn 100% uptime”. **CAP không cho con số tỷ lệ vận hành** và không bảo đảm phần mềm/hardware không lỗi.

## 8. P trong CAP: partition tolerance là gì?

**Network partition** xảy ra khi các thành phần còn hoạt động **không thể trao đổi thông điệp với nhau một cách tin cậy**.

~~~text
            Trước lỗi                     Khi lỗi

    Node A <-------> Node B         Node A  X  Node B
             OK                           Không trao đổi
~~~

Thực tế phức tạp hơn:

- Một chiều gửi được, chiều ngược lại không.
- Một phần thông điệp bị mất, phần khác bị trễ rất lâu.
- Các nhóm node trong cùng vùng hoạt động nhưng khác vùng không kết nối.
- DNS, routing, firewall hoặc switch gây mất một số đường đi.
- Node vẫn chạy nhưng tắc nghẽn hoặc GC pause khiến đồng đội tưởng nó không trả lời.

**Partition tolerance (P)** trong cách dùng CAP hiện đại thường có nghĩa **không được giả định rằng mạng luôn kết nối tốt**: những lỗi phân vùng này nằm trong mô hình cần xử lý.

### P không phải một tính năng có thể tắt để tránh sự cố

Trong môi trường nhiều máy, thiết kế có thể cố giảm xác suất network partition, nhưng **không thể loại bỏ hoàn toàn khả năng mất liên lạc bằng việc đặt cấu hình “P=false”**.

Nếu một hệ chỉ có các bảo đảm mạnh và sẵn sàng **khi mạng không bị partition**, đó là một giả định về môi trường hoạt động, không phải chiến thắng định lý CAP.

### Partition tolerance khác sharding dữ liệu

~~~text
Data partition:
  keys A–M ở shard 1, keys N–Z ở shard 2
  → cách chia nơi lưu

Network partition:
  shard 1 không thể liên hệ shard 2
  → sự cố giao tiếp
~~~

Có nhiều shard không có nghĩa đang bị network partition. Có network partition không có nghĩa các bản ghi bị tự động chia lại đúng theo các shard ban đầu.

## 9. P nghĩa là “vẫn hoạt động”, vậy hoạt động kiểu nào?

Cần diễn đạt cẩn thận. Một hệ *chịu được sự xuất hiện của phân vùng* có thể:

1. **Giữ consistency:** chỉ một phía đủ điều kiện phục vụ thao tác mạnh, các phía khác chờ/từ chối.
2. **Giữ availability:** nhiều phía tiếp tục trả kết quả nhưng có thể tạm khác nhau và phải xử lý xung đột sau đó.
3. **Chọn theo thao tác:** read catalog dùng đường eventual, còn cập nhật quota phải được điều phối.

Cả ba là những chiến lược **đối phó với partition**. Không có nghĩa “hễ có P thì mọi phía luôn đọc/ghi thành công” — đó chính là bảo đảm A mà một thiết kế CP có thể phải hy sinh.

Một cách diễn đạt tốt hơn:

> **P là điều kiện lỗi phải xét; khi điều kiện ấy xảy ra, hệ phải chọn bảo đảm nào được ưu tiên cho từng operation.**

Trong nhiều hệ production, sự lựa chọn còn phụ thuộc read/write concern, client routing, quorum, leader election, loại key và nghiệp vụ.

## 10. Phát biểu chính xác hơn của định lý CAP

Ở mức trực giác của kết quả Gilbert–Lynch, xét một dịch vụ dữ liệu phân tán hỗ trợ đọc/ghi, trong mô hình mạng có thể **mất thông điệp vô hạn**:

> Không có thuật toán nào bảo đảm đồng thời **linearizability** và **availability** cho mọi thao tác đối với mọi lịch thực thi có thể xảy ra trong mô hình đó.

Ta có thể ghi:

~~~text
Điều kiện:
  Network partition có thể xảy ra

Hai mục tiêu:
  C = linearizable reads/writes
  A = every request at non-failing node eventually completes validly

Kết luận:
  Không thể bảo đảm C và A cho tất cả history
  dưới mọi network partition được cho phép.
~~~

### Định lý không nói gì?

Nó **không** nói:

- Mọi ứng dụng chắc chắn mất dữ liệu khi mạng lỗi.
- Một hệ phân tán chỉ có thể chọn hai đặc tính, không hơn không kém.
- Trong điều kiện bình thường phải đánh đổi consistency lấy availability ở mọi thao tác.
- Một hệ AP không thể hỗ trợ CAS hoặc transaction trong bất kỳ phạm vi nào.
- Một hệ CP không bao giờ phản hồi request khi có partition.
- Một hệ “CA” miễn nhiễm với sự cố mạng.
- P có thể tùy ý tắt trong thực tế để nhận cả C và A vô điều kiện.

Định lý là một **giới hạn bảo đảm trong trường hợp xấu nhất** của mô hình truyền thông, không phải bảng phân loại marketing cứng cho mọi sản phẩm.

## 11. Lập luận bất khả bằng hai kịch bản không thể phân biệt

Đây là cách trực quan để thấy vì sao CAP đúng mà không cần thuật toán consensus phức tạp.

Giả sử:

~~~text
Key x ban đầu = 0
Replica A: x=0
Replica B: x=0

Mạng giữa A và B bị chia hoàn toàn.
Hai node vẫn chạy và đều nhận request từ client riêng.
~~~

### Kịch bản S0 — không có ghi ở A

~~~text
Network partition: A  X  B

Client B:
  read(x) → ?
~~~

Nếu đòi availability, B **cuối cùng phải trả kết quả hợp lệ**. Vì không có write nào, một thanh ghi hợp lệ phải trả `0`.

### Kịch bản S1 — A đã ghi, B không thể biết

~~~text
Network partition: A  X  B

Client A:
  write(x,1) → OK

Sau khi write của A hoàn thành:

Client B:
  read(x) → ?
~~~

Nếu đòi availability ở A, A phải hoàn thành write dù không liên hệ được B. Nhưng vì mạng bị chia, **B không nhận được thông điệp nào phân biệt S1 với S0**.

Từ góc nhìn B trước khi trả lời:

~~~text
S0: local x=0; không nhận thông điệp từ A
S1: local x=0; không nhận thông điệp từ A
~~~

B có cùng trạng thái thông tin trong hai kịch bản. Với một thuật toán buộc phải trả kết quả hợp lệ ở S0, nó phải có khả năng trả 0. Nhưng ở S1, vì write A đã hoàn thành trước read B, **linearizability đòi read B trả 1**.

Nếu B trả 0 ở S1, nó vi phạm C. Nếu B chờ đến khi biết A đã ghi gì, trong một partition không kết thúc B có thể chờ vĩnh viễn, vi phạm A. Nếu B cố đoán 1, nó sai trong S0; không tồn tại cách đoán luôn đúng với mọi giá trị có thể được ghi.

**Mâu thuẫn nằm ở thiếu thông tin**, không chỉ ở tốc độ mạng hay hiệu năng CPU.

### Kết luận của lập luận

Trong cùng một lỗi partition:

- Muốn A tiếp tục chấp nhận write và B tiếp tục trả read mà không phối hợp: **phải cho phép một số lịch không linearizable**.
- Muốn giữ linearizability cho cả hệ: **ít nhất một số thao tác cần chờ/từ chối khi không thể phối hợp**.

Đó là đánh đổi CAP.

## 12. CP: ưu tiên consistency khi partition xảy ra

Thuật ngữ **CP** thường dùng cho thiết kế ưu tiên **linearizable behavior** và chấp nhận giảm availability của một số request trong lúc mạng bị chia.

~~~text
                       Network partition

       Nhóm majority                         Nhóm minority
     Replica A + Replica C             X          Replica B
             │                                     │
   Có quorum / leader hợp lệ              Không có quorum
             │                                     │
       Có thể phục vụ                          Chờ hoặc báo
       những thao tác                         không thể phục vụ
       phù hợp                                 thao tác mạnh
~~~

Một hệ CP thường dùng **quorum, leader election, consensus hoặc cơ chế điều phối khác** để chỉ những nhóm có đủ thông tin và quyền mới commit những thay đổi cần strong consistency.

### Điều được bảo vệ

Nếu client đã nhận write success theo giao thức và read sau đó cũng được chấp nhận trong phạm vi bảo đảm mạnh, kết quả đọc phải phù hợp với lịch tuyến tính của các thao tác.

### Điều phải hy sinh

Một request tới phía không thể xác nhận trạng thái đáng tin:

- Có thể phải đợi.
- Có thể bị timeout.
- Có thể bị từ chối rõ ràng.
- Có thể được chuyển route tới nhóm còn quyền phục vụ, **nếu đường mạng cho phép**.

Không phải mọi client đều có thể tiếp tục làm mọi thao tác trong mọi partition. Điều này **không có nghĩa toàn cụm hoàn toàn ngừng hoạt động**.

### Ví dụ nghiệp vụ

Một dịch vụ chiếm `username` duy nhất, hoặc phát hành vé ghế A12 chỉ một người sở hữu, có thể chọn:

~~~text
Nếu không thể xác định chủ sở hữu/commit đáng tin:
  không cấp quyền sở hữu mới
  trả trạng thái chưa thể xác nhận / yêu cầu thử lại
~~~

Từ chối cấp thêm trong lúc partition có thể tốt hơn cấp hai người cùng một ghế rồi giải quyết tranh chấp sau.

## 13. AP: ưu tiên availability khi partition xảy ra

**AP** thường nói về hệ tiếp tục phục vụ yêu cầu ở những phía mạng bị chia, chấp nhận một mô hình **yếu hơn linearizability**, rồi đồng bộ/hợp nhất sau khi mạng phục hồi.

~~~text
                      Network partition

     Node A                                   Node B
   cart = [P1]              X               cart = [P1]
      │                                           │
Client A thêm P2                             Client B thêm P3
      │                                           │
      ▼                                           ▼
cart = [P1,P2]                              cart = [P1,P3]
      │                                           │
      └───────────── khi mạng hồi phục ────────────┘
                           │
                           ▼
                 Merge theo ngữ nghĩa dữ liệu
                 có thể ra [P1,P2,P3]
~~~

Nếu hai phía phục vụ thao tác trên cùng một giỏ hàng khi không liên lạc được, trạng thái tạm thời có thể khác nhau. Trong bối cảnh giỏ hàng, việc **merge các thay đổi** có thể có ích hơn từ chối người dùng thêm sản phẩm.

### AP không đồng nghĩa “đọc gì cũng được”

Ngay cả khi cho đọc cũ hoặc ghi trên nhiều replica, hệ vẫn cần đặc tả:

- Mỗi thao tác `add(item)` có bị trùng khi retry không?
- Nếu một phía xóa P1, phía khác thêm P1, kết quả merge thế nào?
- Hai phía cùng cập nhật số lượng thì cộng, ghi đè hay chọn phiên bản?
- Xung đột được giải quyết bằng LWW, version vector, merge ứng dụng hay CRDT?
- Sau khi liên lạc lại, hệ có điều kiện tiến triển để hội tụ không?

**Availability không tự mang theo eventual consistency hay conflict resolution đúng.** Một hệ muốn được coi là AP dùng được cần thêm thiết kế những quy tắc đó.

### Một số dữ liệu không phù hợp tự do merge

- Trừ số dư có điều kiện không âm.
- Cấp phát ghế duy nhất.
- Giữ hàng không vượt tồn.
- Ghi nhận thanh toán một lần.

Nếu cả hai phía mạng đều cấp phát cùng số lượng giới hạn, **đến lúc merge mới phát hiện vượt quota** có thể đã quá muộn để hủy hậu quả bên ngoài.

## 14. CP và AP trong một bảng tình huống

Giả sử một key `x` đã được ghi ở phía A trong partition:

| Câu hỏi | Hướng CP | Hướng AP |
| --- | --- | --- |
| Phía B không thể liên hệ A | Có thể từ chối/chờ các thao tác cần bảo đảm mạnh | Có thể phục vụ read/write cục bộ theo mô hình yếu |
| B đọc ngay sau write ở A đã ACK | Không trả giá trị vi phạm linearizability trên đường read mạnh | Có thể trả bản cũ nếu mô hình cho phép |
| B tự ghi cùng key | Có thể bị chặn nếu B thiếu quyền/quorum | Có thể được chấp nhận và tạo xung đột |
| Khi mạng hồi phục | Đồng bộ nhóm từng có quyền commit | Cần reconcile các phiên bản/xung đột |
| Rủi ro chính | Một số người dùng không thực hiện được thao tác | Đọc cũ, cập nhật xung đột, invariant xuyên replica |
| Dữ liệu phù hợp để khảo sát | Quota, unique claim, quyền sở hữu | Feed, thích/bỏ thích, cart, thông tin có thể hội tụ |

**Bảng mô tả lựa chọn khái niệm.** Sản phẩm thực có thể cung cấp cả đường mạnh và đường eventual cho các operation khác nhau.

## 15. “Chọn hai trong ba” vì sao dễ gây hiểu lầm?

Slogan phổ biến:

~~~text
CAP = choose any two of C, A, P
~~~

giúp nhớ tên ba thuộc tính, nhưng dễ dẫn tới ba suy luận sai.

### Sai lầm 1 — có thể đơn giản chọn CA và loại bỏ P

Trong hệ nhiều node, **mạng vẫn có thể chia cắt**. Một hệ chỉ hứa đồng thời C và A **nếu mạng không phân vùng** có thể là lựa chọn hợp lý trong một phạm vi hẹp, nhưng nó **không giải quyết trường hợp lỗi partition**.

Nếu một thiết kế “CA” tiếp tục phục vụ trong partition:

- Hoặc nó phải nới lỏng C ở vài đường đọc/ghi.
- Hoặc phải từ chối/chờ một số request, nới lỏng A.

Không có một nút “không chọn P” làm mạng tự hết lỗi.

### Sai lầm 2 — hệ AP không bao giờ có C

Một hệ ưu tiên availability trong một số phân vùng có thể vẫn cung cấp:

- Atomic update ở một node.
- Compare-and-set trong một phạm vi được phối hợp.
- Strong read khi không có partition.
- Transaction cục bộ.

CAP nói về **bảo đảm đồng thời trong trường hợp xấu nhất cho tất cả thao tác/phía**, không cấm từng operation có bảo đảm mạnh hơn dưới điều kiện cụ thể.

### Sai lầm 3 — hệ CP không có availability

Một thiết kế CP có thể vẫn phục vụ **phần lớn request** từ nhóm majority. Nó không thỏa availability vô điều kiện của CAP khi minority bị cô lập, nhưng không đồng nghĩa mọi người dùng đều không truy cập được dịch vụ.

**Cách ghi chính xác hơn:** khi network partition xảy ra và hai yêu cầu không thể cùng bảo đảm, hệ chọn **giữ linearizability hoặc giữ khả năng tiếp tục phản hồi hợp lệ ở mọi phía** cho những thao tác bị ảnh hưởng.

## 16. Khi không có partition, CAP không quyết định mọi đánh đổi

Ngay cả khi mạng hoạt động, hệ thống vẫn phải chọn:

- Đọc leader hay follower?
- Chờ quorum hay trả từ cache?
- Đồng bộ replica trước hay sau ACK?
- Chấp nhận chậm thêm 20 ms để giảm staleness?
- Xây index/read model bất đồng bộ để giảm tải ghi?

Định lý CAP chủ yếu nói về **giới hạn khi có partition**. Nó không mô tả đầy đủ mọi quyết định về latency, consistency và replication **trong vận hành bình thường**.

### PACELC giúp mở rộng cách nghĩ

Một heuristic kiến trúc thường dùng là **PACELC**:

~~~text
If Partition (P):
  trade off Availability (A) vs Consistency (C)
Else (E):
  trade off Latency (L) vs Consistency (C)
~~~

Ý tưởng: ngay cả khi không có phân vùng mạng, chờ nhiều replica để nhận dữ liệu mới hơn có thể tốn latency hơn đọc một bản sao gần client.

PACELC hữu ích để đặt câu hỏi nhưng **không phải kết luận rằng mọi hệ bắt buộc xếp vào đúng một ô cố định**. Latency còn liên quan topology, cache, hardware, load và cách triển khai.

## 17. Một ví dụ ba replica: quorum và nhóm majority

Giả sử có ba node:

~~~text
N = 3 replicas

          A -------- B
           \        /
            \      /
               C
~~~

Hệ dùng giao thức cần **quorum 2/3** để xác nhận một thay đổi mạnh.

Khi C bị cô lập:

~~~text
        A <------> B        X        C
        nhóm 2/3                   nhóm 1/3
        có quorum                 không quorum
~~~

Trong một thiết kế phù hợp:

- A/B có thể tiếp tục commit những thay đổi được giao thức cho phép.
- C không được tự ý commit một giá trị xung đột với đa số nếu hệ đang giữ một lịch tuyến tính chung.
- Client chỉ liên hệ được C có thể phải chờ hoặc nhận lỗi không thể phục vụ.

### Vì sao majority giúp hạn chế hai nhóm cùng commit?

Với 3 replica, hai tập gồm 2 replica **luôn giao nhau ít nhất một node**. Hai quorum thực sự tách biệt hoàn toàn không thể đồng thời tồn tại trong cùng membership ba node.

Nhưng **tính giao nhau tập hợp chưa đủ chứng minh linearizability**. Giao thức còn phải quản lý:

- Leader/term/epoch và quyền ghi.
- Thứ tự ghi concurrent.
- Log/version được commit.
- Read path có thực sự kiểm tra trạng thái đã commit không.
- Thay đổi membership và phục hồi sau crash.

Đừng kết luận “N=3, W=2, R=2 nên tự động CP” chỉ từ số học.

## 18. Điều kiện R + W > N cần được hiểu đúng

Trong hệ replicated key-value, thường nhắc:

\[
R+W>N
\]

với:

- `N`: số bản sao cho một key theo cấu hình đang xét.
- `W`: số bản sao phải ACK một write.
- `R`: số bản sao đọc/nhận phản hồi khi read.

Ví dụ `N=3, W=2, R=2`:

~~~text
Write x=1 được A,B xác nhận.

Replica A = 1
Replica B = 1
Replica C = 0

Read từ B,C có thể thấy:
  B → 1
  C → 0
~~~

Tập read và write giao nhau ở B. Nếu giao thức chọn đúng phiên bản, nó **có thể** trả giá trị mới.

### Vì sao đây chưa phải phép chứng minh CAP C?

Không được bỏ qua:

1. Hai write đồng thời có thể cạnh tranh và đến replica theo thứ tự khác nhau.
2. Phép chọn version mới có thể dùng timestamp chịu ảnh hưởng clock skew.
3. Replica tạm thời/sloppy quorum có thể làm thay đổi tập giao nhau.
4. Một write chỉ thành công một phần có thể để lại phiên bản mà read nhìn thấy.
5. Reconfiguration/membership change có thể làm giả định N thay đổi.
6. Một read cần biết phiên bản nào **đã commit**, không chỉ số byte mới nhất trên một node.

Muốn bảo đảm linearizability, cần **giao thức có chứng minh đúng dưới mô hình lỗi**, chứ không chỉ phép cộng quorum.

## 19. Split-brain và nguy cơ hai leader

Giả sử một cluster trước đó có leader A:

~~~text
        Leader A
          │
       Follower B
          │
       Follower C
~~~

Sau khi mạng chia:

~~~text
Nhóm 1: A  X  Nhóm 2: B,C
~~~

Nếu A vẫn nghĩ mình là leader và B/C chọn leader mới, có thể xảy ra **split-brain** nếu cả hai phía được phép commit những cập nhật xung đột mà không có fencing/quorum phù hợp.

### Fencing token / term / epoch

Một hướng bảo vệ là mỗi nhiệm kỳ leader có **thế hệ tăng dần**:

~~~text
Leader A: term=7
Leader B: term=8
~~~

Các thao tác từ term cũ phải bị từ chối ở nguồn/tài nguyên có thẩm quyền sau khi term mới đã có quyền, theo giao thức.

**Quan trọng:** chỉ đặt một biến `isLeader=true` trong RAM của A không đủ. Khi A mất liên lạc, A có thể không biết quyền của mình đã hết. Cần cơ chế phối hợp/fencing bảo đảm leader cũ không thể gây tác động sai.

### Lease có giải quyết tất cả không?

Lease dựa vào thời gian có thể hữu ích, nhưng phải xét:

- Clock drift và monotonic time.
- Process pause dài.
- Thời hạn lease và thời gian chờ.
- Việc tài nguyên ngoài DB có kiểm tra fencing token không.

Không tự suy rằng “hết 5 giây lease” là bằng chứng tuyệt đối an toàn trong mọi môi trường bất đồng bộ.

## 20. Availability theo từng phía không giống availability cho toàn bộ workload

Khi partition, một cluster CP có thể:

~~~text
Majority: 98% request của người dùng → vẫn hoạt động
Minority: 2% request → bị từ chối/chờ
~~~

Tỷ lệ trên là **ví dụ giả định**. Dịch vụ vẫn có thể đạt một uptime SLO cao trong thực tế vì phần lớn client được route tới majority. Nhưng nếu mục tiêu CAP A là **mọi yêu cầu tới node còn hoạt động đều hoàn thành hợp lệ bất kể partition**, thiết kế này không đạt.

Ngược lại, một cluster AP có thể chấp nhận ghi ở cả hai phía nhưng sau đó gây công việc bù trừ và một số kết quả người dùng bị thay đổi khi hợp nhất.

**Đánh đổi thực tế** không chỉ có “request được trả hay không”, mà còn gồm:

- Tỷ lệ khách hàng bị ảnh hưởng bởi partition.
- Khả năng failover/reroute.
- Thời gian phát hiện sự cố.
- Độ cũ dữ liệu.
- Hậu quả nghiệp vụ của một cập nhật xung đột.
- Chi phí reconciliation sau khi mạng hồi phục.

CAP không thay thế kỹ thuật SRE và thiết kế trải nghiệm lỗi; nó đặt một **giới hạn không thể vượt qua bằng tối ưu thông thường**.

## 21. CP có thể chọn từ chối write nhưng vẫn phục vụ một số read

Không nhất thiết mọi thao tác trên một node phải có cùng lựa chọn.

Ví dụ node phía minority:

~~~text
GET /catalog              → có thể trả bản cache cũ
GET /inventory/authoritative → không phục vụ strong read
POST /reserve-stock       → từ chối khi không thể commit quorum
GET /help-page            → vẫn trả nội dung tĩnh
~~~

Đây có thể là **thiết kế đúng của một sản phẩm**, nhưng không nên quảng bá toàn API là linearizable:

- `GET /catalog` được định nghĩa theo mô hình eventual/stale.
- `POST /reserve-stock` yêu cầu một đường commit mạnh.
- `GET /inventory/authoritative` có thể trả lỗi nếu không có quorum.

**CAP là đánh đổi theo bảo đảm của thao tác**, không buộc ứng dụng phải “đóng cửa tất cả endpoints” trong một partition.

### Bảo đảm cuối cùng nằm ở API mà người dùng thấy

Nếu database chính giữ strong consistency nhưng API trả hàng cũ từ cache sau khi xác nhận giữ hàng, thì **API** có thể không giữ read-your-writes hoặc linearizability mà người dùng kỳ vọng.

Phải xét toàn đường:

~~~text
Client → API → Cache → Read model → Database → Replica
~~~

Không chỉ đặt nhãn CP/AP cho thành phần DB ở cuối chuỗi.

## 22. AP không đồng nghĩa eventual consistency tự động đúng

Một hệ cho cả hai phía ghi cùng một key có thể kết thúc với:

~~~text
Phía A: quantity = 2
Phía B: quantity = 4
~~~

Khi kết nối lại, cần một **conflict resolution rule**:

- LWW theo timestamp/sequence.
- Multi-value register và đưa xung đột cho ứng dụng quyết định.
- Merge theo operation semantics.
- CRDT thích hợp để hội tụ.
- Một quy trình bù trừ theo business rules.

### Ví dụ LWW làm mất ý định

Ban đầu counter bằng 10:

~~~text
Partition A: tăng +1 → ghi giá trị 11
Partition B: tăng +1 → ghi giá trị 11
~~~

Merge LWW giữ 11, nhưng **hai lần tăng độc lập** đáng lẽ tạo 12 nếu nghiệp vụ yêu cầu bảo toàn cả hai hiệu ứng.

Vì thế AP có thể cần lưu **operation** thay vì chỉ lưu **giá trị đã tính**, hoặc dùng cấu trúc merge phù hợp.

### CRDT không miễn phí và không tự bảo vệ mọi invariant

Một CRDT counter có thể hội tụ các increment độc lập, nhưng điều kiện:

~~~text
available >= 0
~~~

với nhiều bên cùng được giảm hạn mức có thể bị vi phạm nếu mỗi phía **không biết các khoản giảm ở phía khác**.

Cần cấp quota trước theo escrow/budget, phối hợp lúc quyết định hoặc đổi quy tắc nghiệp vụ. Không nên coi “dùng CRDT” là lời giải chung cho cấp phát hàng và thanh toán.

## 23. Câu chuyện tồn kho: vì sao dữ liệu nào cũng AP là nguy hiểm?

Kho chỉ còn 1 chiếc:

~~~text
Global stock = 1

Partition xảy ra:

Node A thấy stock=1       X       Node B thấy stock=1
Client A mua 1                    Client B mua 1
Node A chấp nhận                  Node B chấp nhận
~~~

Sau khi nối mạng, hệ phát hiện **đã bán 2 chiếc khi chỉ có 1**.

Nếu nghiệp vụ không cho phép oversell, ít nhất một phía phải:

- Từ chối quyết định cấp phát khi không thể phối hợp, **hoặc**
- Chỉ dùng một lượng quota đã **được phân bổ độc quyền** trước đó cho từng phía, **hoặc**
- Có một giao thức khác bảo đảm không hai phía tiêu cùng một quyền sở hữu.

### Escrow / pre-allocation

Ví dụ trước khi partition:

~~~text
Tổng stock = 10

Node A được cấp quyền bán tối đa 4
Node B được cấp quyền bán tối đa 6
~~~

Khi mạng chia, A và B có thể bán trong **quota riêng không chồng nhau** mà không vượt tổng 10. Nhưng:

- Chuyển quota từ A sang B cần phối hợp.
- A hết quota nhưng B còn quota: A có thể phải từ chối dù tổng toàn hệ vẫn còn hàng.
- Giao thức phân bổ và thu hồi quota phải bảo vệ invariant.

Đây là một cách **đưa ràng buộc mạnh sang giai đoạn phân bổ quyền**, không phải bác bỏ CAP: khi cần chuyển quyền giữa hai phía bị chia cắt, đánh đổi lại xuất hiện.

## 24. Giỏ hàng và danh sách yêu thích: vì sao một số dữ liệu có thể AP?

Người dùng thêm sản phẩm vào giỏ từ hai thiết bị:

~~~text
Thiết bị A: add(P2)
Thiết bị B: add(P3)
~~~

Nếu trải nghiệm cho phép dữ liệu hội tụ về sau, một thiết kế AP có thể lưu các thao tác và merge.

Nhưng cần định nghĩa rõ:

1. **Add khác Set:** thêm P2 không giống ghi đè cả giỏ bằng danh sách mới.
2. **Remove có ngữ nghĩa gì:** xóa P2 trước/sau thêm P2, thao tác nào thắng?
3. **Số lượng**: hai lần tăng quantity có được cộng cả hai không?
4. **Idempotency**: message retry có được tính thêm lần không?
5. **Phiên người dùng**: sau khi thêm, thiết bị có được yêu cầu read-your-writes không?
6. **Thanh toán**: phải kiểm tra giá và tồn thực tại nguồn ở bước cuối.

Do đó, lựa chọn AP hợp lý thường đi cùng **mô hình merge theo nghiệp vụ** và một **điểm kiểm tra mạnh** ở bước commit cuối.

## 25. Một workflow có thể dùng nhiều mô hình cùng lúc

Ví dụ đặt hàng:

~~~text
1. Tìm kiếm sản phẩm
   → Search index eventual, có thể hơi cũ

2. Thêm vào giỏ hàng
   → Operation merge/idempotent phù hợp

3. Xem số tồn hiển thị
   → Ước lượng, có thể stale và có nhãn rõ ràng

4. Chốt đặt hàng
   → Conditional reservation ở nguồn có thẩm quyền

5. Thu tiền
   → Payment idempotency và workflow bảo vệ side effects

6. Xem báo cáo doanh số
   → Read model/aggregation có độ trễ cho phép
~~~

Nếu bước 4 không thể tiếp cận quorum trong partition, ứng dụng có thể giữ giỏ hàng và báo “chưa thể xác nhận đơn” thay vì khẳng định đã bán thành công.

### Phân loại theo chi phí sai

| Chức năng | Hậu quả nếu thấy dữ liệu cũ | Hướng ưu tiên thường gặp |
| --- | --- | --- |
| Danh sách sản phẩm | Hình/miêu tả chậm cập nhật | Đọc nhanh, chấp nhận staleness có giới hạn |
| Số lượt thích | Chênh một ít trong thời gian ngắn | Eventual, hội tụ đúng theo ngữ nghĩa |
| Giỏ hàng nhiều thiết bị | Sản phẩm tạm chưa hiện | Session guarantees + merge |
| Giữ ghế duy nhất | Hai người cùng được xác nhận | Coordination/conditional strong decision |
| Cấp voucher quota | Vượt số lượng được phép | Atomic quota allocation |
| Thanh toán | Trừ tiền trùng/không ghi nhận | Transaction/idempotency, đối soát |
| Dashboard | Số liệu không theo thời gian thực | Read model + watermark/as-of time |

Đây là **gợi ý thiết kế**, không phải quy định tất cả ứng dụng phải chọn giống nhau. Hợp đồng cuối cùng xuất phát từ invariant và trải nghiệm được cam kết.

## 26. Trong một partition, timeout của client có ý nghĩa gì?

Giả sử:

~~~text
Client → write x=1 tới node A
          |
          v
Node A commit thành công
          |
          X ACK bị mất do mạng

Client nhận timeout
~~~

Client không thể tự kết luận:

- “write chắc chắn thất bại”, hoặc
- “write chắc chắn đã commit”.

Đây là **unknown outcome**. Nó tồn tại cả trong hệ có strong consistency.

### Retry sai có thể tạo hiệu ứng trùng

~~~text
POST /charge paymentId=P1
  → timeout sau commit

Client retry bằng paymentId=P2
  → có nguy cơ thu tiền hai lần
~~~

CAP không giải quyết idempotency. Cần:

- **Request ID ổn định** cho cùng một ý định.
- Uniqueness/conditional claim hoặc transaction phù hợp.
- API cho phép truy vấn trạng thái đã commit.
- Retry có giới hạn và phân biệt lỗi tạm thời với lỗi nghiệp vụ.

Khi một phía CP không thể xác nhận kết quả, trả lỗi “chưa xác định” có thể an toàn hơn giả định thành công hoặc thất bại.

## 27. CAP khác durability và replication safety

Một hệ có thể linearizable nhưng mất dữ liệu nếu máy lưu duy nhất bị hỏng vật lý và không có backup; một hệ có nhiều replica bền vững vẫn có thể trả stale read.

Phân biệt:

| Thuộc tính | Bảo vệ điều gì? |
| --- | --- |
| Linearizability | Thứ tự đọc/ghi có thể quan sát |
| Availability theo CAP | Request tới node sống cuối cùng nhận kết quả hợp lệ |
| Partition tolerance | Mô hình vẫn xét mạng bị chia cắt |
| Durability | Ghi đã commit sống sót qua lỗi theo phạm vi cam kết |
| Replication | Có bản sao để phục hồi/phục vụ |
| Backup | Khôi phục sau xóa nhầm/corruption/sự cố lớn |
| Idempotency | Cùng một ý định bị gửi lặp không tạo tác động thừa |

Không nên nói “AP thì dữ liệu kém bền vững” hoặc “CP thì không mất dữ liệu” như một quy tắc. Cần xem write acknowledgment, disk persistence, replication topology, quorum, backup và recovery.

### Khả năng đọc cũ không đồng nghĩa mất ghi

Một follower tạm trả `x=0` trong khi leader đã commit `x=1` có thể là vấn đề **freshness/linearizability của đường đọc**, không nhất thiết nghĩa write `x=1` bị mất.

Ngược lại, một leader đã ACK một write chưa đủ bền vững có thể mất dữ liệu khi crash — đó là vấn đề **durability**, không phải định nghĩa C/A/P.

## 28. CAP và tính nhất quán của transaction

Một dịch vụ có thể có:

~~~text
Single-key read/write: linearizable
Multi-key transaction: snapshot isolation
Search index: eventual
Cache: TTL-based
~~~

Đó không mâu thuẫn. Các hoạt động có **đối tượng, phạm vi và lịch sử riêng**.

### Serializable không đồng nghĩa linearizable

- **Serializable transaction:** các transaction tương đương một thứ tự tuần tự hợp lệ.
- **Linearizable operation:** thêm ràng buộc thứ tự thời gian thực giữa những thao tác không chồng lấn.
- **Strict serializability:** kết hợp serializability với thứ tự thời gian thực ở mức transaction.

Nếu một dịch vụ cần chuyển tiền nhiều record với thứ tự thời gian thực được bảo đảm, phải xác định transaction model tương ứng. **Không thể chỉ ghi “CAP: C=true”** để suy ra đủ isolation/atomicity/durability cho cả quy trình.

### Read-your-writes cũng không mặc định có

Một hệ eventual có thể hỗ trợ **session token** để client sau khi ghi luôn thấy phiên bản của chính mình hoặc mới hơn. Đó là một bảo đảm bổ sung theo phiên, không tự biến mọi client/read route thành linearizable.

## 29. Ví dụ sản phẩm NoSQL: đừng gán nhãn cứng

Các hệ thường có những cơ chế khác nhau:

### MongoDB replica set

Có thể chọn read preference/read concern/write concern và transaction options theo nhu cầu. Trong một cấu hình, client có thể đọc primary; trong cấu hình khác, client đọc secondary và quan sát replication lag.

**Không nói “MongoDB luôn CP” hoặc “luôn AP” cho mọi truy vấn** mà không nêu:

- Read route.
- Write acknowledgment.
- Replica set membership và failover.
- Read concern, session và transaction scope.

### Apache Cassandra

Các thao tác có consistency levels theo replica và cơ chế conditional update/LWT trong phạm vi hỗ trợ. Mức xác nhận khác nhau dẫn đến đánh đổi khả năng phục vụ khi replica không liên lạc, và cách nhìn thấy ghi.

`ONE`, `QUORUM` hoặc `ALL` không phải nhãn CAP trực tiếp. Cần xem định nghĩa consistency level, cách xử lý conflict, replication factor, topology và loại thao tác.

### Amazon DynamoDB

Cần phân biệt strong/eventual reads ở những API được hỗ trợ, đường đọc base table so với global secondary index, và ngữ nghĩa sao chép giữa vùng. Một transaction/conditional write của bảng nguồn **không tự làm GSI đang đồng bộ bất đồng bộ thành strong read**.

### Redis và replica

Một Redis primary xử lý nhiều thao tác theo thứ tự trên instance, nhưng read replica có thể trễ; failover, persistence, `WAIT` và mô hình cluster liên quan đến các bảo đảm khác. Không chỉ nhìn tốc độ `GET`/`SET` để suy ra tính nhất quán xuyên failover.

### Hệ consensus chuyên dụng

Một key/value service dùng consensus cho các thao tác cần thứ tự mạnh có thể từ chối request ở nhóm không có quorum khi partition. Đó là một lựa chọn điển hình của hướng CP cho những operation đó.

**Nguyên tắc:** đánh giá **operation + consistency options + topology + fault model**, không phân loại chỉ dựa trên tên thương mại của DBMS.

## 30. Java mô phỏng lựa chọn CP và AP khi mạng bị chia

Đoạn Java sau chỉ nhằm làm rõ **hành vi quan sát**. Nó không triển khai consensus, không phải database thật, không có network sockets và không chứng minh tính đúng đắn của một sản phẩm.

Ta tạo hai bản sao của một thanh ghi đơn giản. Sau khi partition, Node A ghi 1 và B chưa nhận thay đổi.

### 30.1. Mã minh họa

Tạo `CapChoiceDemo.java`:

~~~java
public final class CapChoiceDemo {

    static final class Replica {
        final String name;
        private int localValue;

        Replica(String name, int initialValue) {
            this.name = name;
            this.localValue = initialValue;
        }

        void localWrite(int newValue) {
            localValue = newValue;
        }

        int localRead() {
            return localValue;
        }

        void copyFrom(Replica source) {
            localValue = source.localValue;
        }
    }

    public static void main(String[] args) {
        Replica nodeA = new Replica("A", 0);
        Replica nodeB = new Replica("B", 0);

        boolean networkPartitioned = true;

        // Mô phỏng hướng ưu tiên availability ở A:
        // A chấp nhận write x=1 dù không liên hệ B.
        nodeA.localWrite(1);
        System.out.println("A write(x=1) -> OK");

        // Một read sau ACK ở B vẫn trả local value cũ.
        int eventualRead = nodeB.localRead();
        System.out.println(
                "AP-style B read(x) -> " + eventualRead);

        // Mô phỏng chính sách ưu tiên consistency:
        // Nếu không thể chứng minh trạng thái mới nhất,
        // B không được trả local value như một strong read.
        if (networkPartitioned) {
            System.out.println(
                    "CP-style B strongRead(x) -> UNAVAILABLE");
        } else {
            System.out.println(
                    "CP-style B strongRead(x) -> "
                    + nodeB.localRead());
        }

        // Mạng hồi phục; mô phỏng B bắt kịp.
        networkPartitioned = false;
        nodeB.copyFrom(nodeA);

        System.out.println(
                "After replication B read(x) -> "
                + nodeB.localRead());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CapChoiceDemo.java
java CapChoiceDemo
~~~

Output minh họa:

~~~text
A write(x=1) -> OK
AP-style B read(x) -> 0
CP-style B strongRead(x) -> UNAVAILABLE
After replication B read(x) -> 1
~~~

### 30.2. Điều ví dụ cho thấy

- Nếu A đã ACK ghi và B đọc `0` **sau đó**, đường read trả 0 không linearizable trong lịch đơn giản này.
- Nếu B không có thông tin cập nhật, đường **strong read** có thể phải chờ/từ chối, mất availability cho request đó.
- Sau khi replication hoàn tất, B đọc 1; đây là một dạng hội tụ.

### 30.3. Điều ví dụ không chứng minh

Mã chỉ **chọn hành vi giả lập**, không triển khai thuật toán chống split-brain hay quyết định một leader hợp lệ. Với một dịch vụ CP thật, A có thể **không được phép chấp nhận write** nếu A cũng không có quorum. Cách mô phỏng này cố ý giả định A đã có quyền commit để làm rõ ràng buộc read phía B.

Không dùng mã để so benchmark, kiểm nghiệm mạng bất đồng bộ hoặc kết luận về một DBMS cụ thể.

## 31. Mô phỏng hai partition và quyết định nhất quán

Xét một cluster năm node:

~~~text
N = 5

           Network partition

Group A (3 nodes)             Group B (2 nodes)
 A1, A2, A3          X          B1, B2
~~~

Một protocol cần đa số `3/5` có thể tiếp tục quyết định từ Group A, nếu còn các điều kiện cần khác; Group B không có majority.

Hãy thử đặt:

~~~text
Client X ở Group A: reserve(ticket=T42)
Client Y ở Group B: reserve(ticket=T42)
~~~

Nếu cả hai được xác nhận thành công trong hai nhóm không liên lạc, hệ đã tạo khả năng **double booking**. Một thiết kế duy trì một quyền sở hữu duy nhất sẽ không cho cả hai nhóm commit tự do.

### “B không phục vụ” là thất bại hay thiết kế đúng?

Đối với yêu cầu cấp vé duy nhất:

~~~text
B trả "không thể xác nhận, hãy thử lại"
~~~

có thể là hành vi **đúng về an toàn**, dù đây là sự suy giảm availability theo định nghĩa CAP.

Đối với đọc hướng dẫn sử dụng:

~~~text
B trả bản nội dung đã cache
~~~

có thể là trải nghiệm hợp lý vì thao tác không yêu cầu read mạnh cho cùng tài nguyên vé.

Hai chức năng có thể **chọn cam kết khác nhau** trong cùng một sự cố.

## 32. Phản ví dụ: “Còn hàng” trên replica không phải quyền được bán

Giả sử:

~~~text
T0: available = 1 ở hai replica
T1: A giữ chiếc cuối, trả OK cho client A
T2: B chưa nhận cập nhật, đọc available = 1
T3: Client B được UI hiển thị "Còn 1 chiếc"
~~~

Điều này có thể được **cho phép** nếu màn hình danh sách chỉ có eventual read.

Nhưng:

~~~text
T4: Client B nhấn "Đặt hàng"
T5: API lập tức xác nhận đặt thành công dựa trên read B cũ
~~~

Nếu source of truth đã hết hàng thì đây là **lỗi bảo vệ invariant**.

### Thiết kế đúng hơn

~~~text
GET /products/SKU-7
  → có thể trả estimatedAvailable=1 từ cache

POST /reservations
  → conditional atomic reservation ở nguồn
  → chỉ success nếu quota/tồn thực sự còn
~~~

Điểm chốt quyết định cần có **conditional write hoặc transaction với bảo đảm phù hợp**. UI hiển thị bản cũ không nhất thiết là bug nếu đã có hợp đồng freshness rõ và không được dùng làm căn cứ cấp phát cuối.

## 33. Một ứng dụng không thể “chọn AP” rồi quên hậu quả hội tụ

Ví dụ hai phía cùng chỉnh sửa hồ sơ:

~~~text
Ban đầu:
  city = "Da Nang"

Partition:
  A ghi city = "Ha Noi"
  B ghi city = "Hue"
~~~

Sau khi mạng phục hồi, kết quả là gì?

Các khả năng:

1. Chọn phiên bản theo timestamp.
2. Chọn version/epoch theo thứ tự hệ thống.
3. Lưu hai giá trị cho người dùng giải quyết.
4. Áp rule nghiệp vụ “thay đổi được user xác nhận cuối” dựa trên metadata đáng tin.

**Không có lời giải tự động đúng cho mọi dữ liệu.** Một rule phù hợp với `city` có thể sai với danh sách thành viên nhóm, quyền truy cập hoặc counter.

### Reconciliation cần kiểm thử

Khi thiết kế AP, phải kiểm thử:

- Cập nhật cùng key ở hai phía.
- Retry một operation nhiều lần.
- Message đến đảo thứ tự.
- Node offline lâu ngày rồi nhập lại.
- Tombstone/delete so với update cũ.
- Xung đột giữa phiên bản schema khác nhau.
- Bản sao chưa nhận đầy đủ lịch sử.

Nếu chỉ thử một write trên một phía, hệ có thể trông “ổn định” nhưng chưa kiểm tra phần khó nhất của lựa chọn availability.

## 34. Tính sẵn sàng của read và write có thể khác nhau

Một dịch vụ đôi khi:

~~~text
Read availability:  cao hơn
Write availability: thấp hơn
~~~

vì chấp nhận read cũ từ cache nhưng write cần quorum. Một hệ khác có thể nhận write local nhưng yêu cầu read phải phản ánh một phiên bản tối thiểu theo session token.

Vì thế khi mô tả CAP:

- Không chỉ nói “service available”.
- Hãy nói **read operation nào**, **write operation nào**, **trong lỗi mạng nào**.
- Có trả stale read không?
- Có nhận write sẽ phải reconcile sau không?
- Request đến minority bị gì?

### Mẫu phân loại thao tác

| Operation | Có thể chấp nhận dữ liệu cũ? | Có thể nhận ghi tách biệt? | Rủi ro nếu xung đột |
| --- | --- | --- | --- |
| Read tin tức | Có | Không liên quan | Thấp |
| Edit mô tả | Tùy sản phẩm | Có thể, có merge | Mất nội dung nếu LWW sai |
| Like/unlike | Có thể | Có, nếu data type/semantics phù hợp | Đếm sai/duplicate |
| Giữ hàng | Không được quyết định bằng dữ liệu cũ | Rất hạn chế; cần quota/fencing | Oversell |
| Chiếm username | Không được tạo hai chủ sở hữu | Cần unique claim | Trùng định danh |
| Tổng hợp dashboard | Có, nếu có độ trễ được phép | Ghi qua event/read model | Số tạm chưa đủ |

Việc một ứng dụng có nhiều loại operation không làm CAP “vô nghĩa”; nó yêu cầu **phân tích CAP ở phạm vi chính xác**.

## 35. Network partition khác node crash và node chậm

### Node crash

~~~text
Node B tắt hoàn toàn
~~~

Trong định nghĩa CAP A, một node đã thất bại **không bị yêu cầu** phải phản hồi. Tuy nhiên, từ phía client có thể khó phân biệt B thực sự crash hay B vẫn chạy nhưng mạng không tới được.

### Network partition

~~~text
Node A đang chạy     X     Node B đang chạy
~~~

Cả hai node còn sống, nhưng không thể phối hợp. Đây là trường hợp làm giới hạn C/A trở nên rõ.

### Slow node / delayed messages

~~~text
Node B đang chạy nhưng mất 30 giây mới trả lời
~~~

Trong một mô hình bất đồng bộ, node chậm và node mất kết nối có thể **không thể phân biệt trong một khoảng hữu hạn**. Timeout là quyết định vận hành, không phải bằng chứng tuyệt đối node đã chết.

Điều này giải thích vì sao leader election, failover và fencing khó: một leader cũ có thể tạm bị cô lập rồi xuất hiện lại, trong khi cụm đã chọn leader mới.

### Đừng suy CAP từ một lần ping thất bại

Một ping lỗi chỉ cho biết một đường kiểm tra không nhận phản hồi đúng hạn; để xác định hệ có partition làm ảnh hưởng correctness, phải xem topology, thông điệp của giao thức và các thao tác bị ảnh hưởng.

## 36. Khi chọn mô hình phải viết rõ lỗi nào được chấp nhận

Một đặc tả hữu ích:

~~~yaml
feature: "Reserve single seat"
data:
  key: "seatId"
  authority: "Reservation source"
requiredInvariant:
  - "At most one confirmed owner per seat"
operation:
  name: "reserve(seatId, requestId)"
  requires: "Conditional single-owner commit"
networkPartitionPolicy:
  majoritySide: "May continue if protocol permits"
  minoritySide: "Must not confirm ownership without authority"
response:
  success: "Only after the defined commit condition"
  unavailable: "Explicit retryable status; not a confirmed reservation"
retry:
  idempotencyKey: "requestId"
  unknownOutcome: "Look up committed requestId before replay"
reads:
  authoritative: "Must follow required consistency"
  informational: "May use stale cached view with label"
testing:
  - "Partition majority/minority"
  - "Concurrent reserves on both sides"
  - "Old leader returns after healing"
  - "Timeout after commit"
  - "Duplicate requestId"
~~~

Đây là **mẫu tài liệu**, không phải cấu hình của một DBMS. Từ “majority” chỉ có ý nghĩa khi hệ dùng giao thức và membership tương ứng.

### Vì sao một contract như vậy tốt hơn “CP”?

“CP” chỉ diễn đạt **ưu tiên chung**. Mẫu trên diễn đạt được:

- Quyền sở hữu nào tuyệt đối không được cấp trùng.
- Thành công được trả ở mốc nào.
- Phía không có quorum phải ứng xử ra sao.
- Client xử lý unknown outcome thế nào.
- Đường nào cho phép đọc cũ.

Nhờ đó, nhóm phát triển có thể viết test và xử lý sự cố cụ thể.

## 37. Kiểm thử CAP bằng cách ghi lịch sử

Để đánh giá một tuyên bố consistency/availability, cần tạo **workload và fault injection có kiểm soát**, đồng thời ghi lại invocation/response của client.

Ví dụ lịch:

~~~text
operationId | client | op        | start | end | result
----------- | ------ | --------- | ----- | --- | ------
W1          | A      | write x=1 | 10    | 20  | OK
R1          | B      | read x    | 30    | 40  | 0
~~~

Nếu `x` bắt đầu 0 và không có write hợp lệ khác, lịch này **không linearizable** vì W1 hoàn thành trước R1 bắt đầu.

### Các thành phần cần ghi

- ID của request và client/session.
- Key/transaction được thao tác.
- Thời điểm bắt đầu và kết thúc request từ góc nhìn client.
- Kết quả read, version hoặc lỗi.
- Node/route/replica đã phục vụ.
- Thời điểm fault injection và healing.
- Write acknowledgment level/consistency option.
- Retry và idempotency key.

### Phân biệt kiểm thử và chứng minh

Một lịch phản ví dụ **có thể chứng minh một bảo đảm bị vi phạm trong điều kiện được kiểm thử**. Ngược lại, hàng nghìn lần chạy không thấy vi phạm **không phải chứng minh toán học** rằng không có lịch lỗi nào khác.

Trong kiểm thử thực, timestamp của nhiều host có thể lệch; cần một phương pháp thu thập history đủ đáng tin để xác định ràng buộc real-time. Các framework kiểm tra lịch sử phân tán có thể hỗ trợ nhưng vẫn cần cấu hình fault model và workload đúng.

## 38. Ma trận câu hỏi kiểm chứng khi mạng bị chia

| Kịch bản | Câu hỏi quan trọng | Dấu hiệu rủi ro |
| --- | --- | --- |
| Leader mất liên lạc majority | Leader cũ có tiếp tục ACK write không? | Split-brain, commit xung đột |
| Minority nhận GET | GET có hứa strong không hay trả stale? | Vi phạm hợp đồng read |
| Minority nhận PUT | Có quyền commit thật không? | Hai phía cùng chấp nhận write |
| Client mất ACK | Tra được kết quả theo requestId không? | Duplicate effects |
| Partition lành lại | Phiên bản nào thắng, merge thế nào? | Mất thay đổi hoặc phá invariant |
| Replica lag lớn | API có chuyển route/chờ khi cần bản mới không? | Read-your-writes thất bại |
| Thay đổi membership | Quorum cũ và mới có phối hợp an toàn không? | Hai quorum không tương thích |
| Node cũ quay lại | Có fencing/epoch để bác stale leader không? | Ghi đè commit mới |
| Client failover giữa replicas | Session có bị đọc đi lùi không? | Monotonic reads bị phá |
| Disk crash sau ACK | Có replica/backup và durability đúng không? | Mất ghi đã xác nhận |

Những tình huống này không chỉ kiểm thử CAP; chúng kiểm tra **hậu quả của sự lựa chọn consistency/availability** đối với hệ thống và nghiệp vụ.

## 39. Những lỗi diễn giải CAP thường gặp

| Nhận định sai hoặc thiếu | Cách hiểu đúng |
| --- | --- |
| “CAP nghĩa chọn đúng hai trong ba, tắt cái còn lại.” | Trong partition, không thể bảo đảm đồng thời C và A cho mọi phía; P là điều kiện lỗi cần xét. |
| “C của CAP giống C của ACID.” | CAP C liên quan linearizability; ACID C liên quan invariant. |
| “Availability = server uptime 99,99%.” | CAP A là liveness của mọi request tới non-failing node trong mô hình, không phải tỷ lệ SLO. |
| “Trả 503 cũng có response nên luôn là available.” | Lỗi không thể phục vụ không phải kết quả đọc/ghi hợp lệ trong định nghĩa register của CAP. |
| “P là data partition/sharding.” | P nói về network partition, không phải chia khóa để lưu. |
| “Không chọn P thì network partition không xảy ra.” | Không thể cấu hình loại bỏ hoàn toàn lỗi truyền thông trong hệ nhiều node. |
| “AP thì dữ liệu luôn sai.” | AP cho phép một số history không linearizable; hệ vẫn có thể bảo toàn nhiều bảo đảm và hội tụ. |
| “AP nghĩa dữ liệu tự động merge đúng.” | Cần conflict resolution theo semantics và cơ chế repair cụ thể. |
| “CP luôn tắt cả cluster.” | Nhóm có quorum/leader hợp lệ vẫn có thể phục vụ nhiều thao tác. |
| “Quorum R+W>N chứng minh linearizability.” | Cần giao thức xử lý version, concurrency, membership và fault model. |
| “Có consensus thì bất kỳ follower nào cũng strong read.” | Read path phải thực hiện giao thức mạnh phù hợp; follower stale không tự linearizable. |
| “Network partition giống node crash.” | Cả hai node có thể vẫn chạy; lỗi là không trao đổi được. |
| “Một read trả cũ trong lúc write đang chạy là vi phạm C.” | Nếu operation chồng lấn, read cũ có thể linearizable. |
| “CAP quyết định p95 latency khi mạng khỏe.” | CAP không mô tả đầy đủ trade-off bình thường; PACELC giúp đặt câu hỏi khác. |
| “AP đồng nghĩa eventual consistency với deadline 1 giây.” | Eventual cần điều kiện hội tụ; không tự có deadline. |
| “Linearizable một key đủ cho transaction chuyển tiền.” | Multi-key atomicity/isolation là chiều khác. |
| “CP thì dữ liệu chắc chắn bền vững mãi.” | Durability, replication, backup và failure scope cần phân tích riêng. |
| “Một DBMS chỉ thuộc đúng một loại CP/AP.” | Bảo đảm khác theo API, consistency option, scope, route và topology. |

## 40. Bài tập thực hành

### Bài 1 — Gọi đúng tên ba thuộc tính

Hãy mô tả **Consistency, Availability, Partition tolerance** bằng một câu mỗi thuộc tính, không dùng từ “dữ liệu luôn đúng”, “server không down” hay “có nhiều shard” làm định nghĩa.

**Gợi ý:** C là lịch tuyến tính có thứ tự thời gian thực; A là request tới node sống cuối cùng nhận kết quả hợp lệ; P là môi trường cho phép các node không trao đổi thông điệp.

### Bài 2 — Phân loại history sau write

Khóa `x` ban đầu 0:

~~~text
A: write x=1 → OK
B: read x → 0
~~~

B bắt đầu đọc sau khi A đã nhận OK. Không có write khác. Lịch có linearizable không? Nếu read B bắt đầu **trước** ACK của A và chồng lấn write, kết luận thay đổi thế nào?

**Gợi ý:** trường hợp đầu vi phạm; trường hợp chồng lấn có thể sắp read trước write.

### Bài 3 — Viết lập luận bất khả

Hai node A/B bị phân vùng, `x=0`. Trong kịch bản S0 A không ghi; trong S1 A ghi `x=1` và đã ACK. B không nhận thông điệp từ A ở cả hai kịch bản. Tại sao B không thể luôn trả đúng read trong cả S0 và S1 nếu vẫn phải hoàn thành?

**Gợi ý:** hai trạng thái quan sát cục bộ của B là không thể phân biệt, nhưng linearizability đòi hai kết quả khác nhau.

### Bài 4 — 503 có nghĩa A không?

Khi minority không có quorum, API trả HTTP 503 ngay lập tức. Có thể nói API “vẫn available theo CAP” chỉ vì response đến nhanh không? Phân biệt với availability SLO.

**Gợi ý:** 503 không phải kết quả đọc/ghi hợp lệ như register yêu cầu; uptime/latency vận hành là khái niệm khác.

### Bài 5 — “CA” có giải quyết partition?

Một thiết kế tài liệu ghi “chúng ta chọn CA nên bỏ P”. Hãy sửa phát biểu đó cho hệ hai vùng triển khai có thể mất liên lạc.

**Gợi ý:** muốn có cả strong reads và vô điều kiện hoàn thành mọi request trong partition là bất khả; phải định nghĩa hành vi khi lỗi.

### Bài 6 — Quorum 5 replica

Với 5 node, cần majority 3 để commit. Mạng chia 3–2. Nhóm nào có khả năng tiếp tục các quyết định cần majority? Điều đó có nghĩa mọi request trên toàn hệ đều available không?

**Gợi ý:** nhóm 3 có quorum nếu các điều kiện giao thức thỏa; nhóm 2 không có, nên A vô điều kiện không được giữ.

### Bài 7 — Hai bên cùng giữ chiếc cuối

Kho còn 1 chiếc, hai partition cùng thấy giá trị 1 và cùng xác nhận bán 1. Hãy chỉ ra invariant bị phá và đề xuất hai cách tránh việc cả hai bên cấp phát cùng quyền sở hữu.

**Gợi ý:** CP conditional commit; hoặc quota được phân bổ độc quyền trước partition.

### Bài 8 — Giỏ hàng AP

Trong lúc partition, thiết bị A thêm P2, thiết bị B thêm P3. Khi kết nối lại, ứng dụng nên merge thế nào? Nếu A xóa P2 trong khi B cũng thêm P2 thì còn câu hỏi ngữ nghĩa nào?

**Gợi ý:** lưu operation ID, rule add/remove và retry; tránh last-write-wins cả object khiến mất thay đổi.

### Bài 9 — C của CAP và ACID

Một database xử lý `write(available,-3)` theo thứ tự linearizable. Nó có thỏa CAP C trên key không? Có bảo toàn ACID Consistency về invariant tồn kho không?

**Gợi ý:** có thể linearizable theo ngữ nghĩa register nhưng sai quy tắc nghiệp vụ; C của CAP không tự validate số tồn.

### Bài 10 — Single-key và multi-key

Một hệ hứa linearizable writes từng key. Chuyển 100 từ A sang B bằng hai write độc lập. Reader có thể thấy A đã giảm còn B chưa tăng không?

**Gợi ý:** có; cần transaction/aggregate bảo vệ atomicity của cả chuyển tiền.

### Bài 11 — Read preference và session

Sau khi người dùng tạo đơn thành công ở primary, lần đọc chi tiết từ follower không tìm thấy đơn. Hãy xác định điều kiện nào làm history vi phạm linearizability và đề xuất cách đạt read-your-writes.

**Gợi ý:** nếu read bắt đầu sau write ACK và đường đọc hứa linearizable; có thể route tới nguồn phù hợp hoặc dùng version/session token.

### Bài 12 — R + W > N

Với `N=3, R=2, W=2`, kiểm tra điều kiện giao nhau. Nêu ít nhất ba điều kiện/góc cạnh khác phải được giải quyết trước khi tuyên bố tất cả thao tác linearizable.

**Gợi ý:** write concurrent, version order, partial writes, membership, sloppy quorum, clock skew.

### Bài 13 — PACELC

Một dịch vụ không bị partition nhưng vẫn chọn đọc follower gần người dùng để có latency nhỏ, chấp nhận dữ liệu hơi cũ. Vì sao CAP một mình chưa mô tả đầy đủ đánh đổi này?

**Gợi ý:** PACELC xét latency vs consistency ngay cả khi không có partition.

### Bài 14 — Timeout sau commit

Client gửi một yêu cầu thanh toán; database đã commit nhưng ACK bị mất. Client retry bằng requestId mới. Lỗi gì có thể xuất hiện? CAP có tự bảo vệ không?

**Gợi ý:** duplicate effect; cần idempotency key ổn định và tra cứu unknown outcome.

### Bài 15 — Trường hợp node chậm

Node A phản hồi sau 20 giây, trong khi detector timeout ở 5 giây. Có thể khẳng định A đã crash không? Tại sao cần fencing khi chọn leader mới?

**Gợi ý:** lỗi mạng, chậm, GC pause có thể khó phân biệt; leader cũ có thể quay lại và thực hiện ghi lỗi thời.

### Bài 16 — Phân tích API hỗn hợp

Thiết kế bốn endpoint:

~~~text
GET /catalog
PUT /cart/items
POST /reservations
GET /analytics/sales
~~~

Với từng endpoint, hãy ghi mô hình read/write cần thiết, hành vi khi partition và rủi ro nghiệp vụ nếu đọc/ghi cũ hoặc xung đột.

**Gợi ý:** không nhất thiết chọn cùng một chính sách CP/AP cho cả bốn endpoint.

### Bài 17 — Tìm phản ví dụ bằng history

Cho hai lịch với `x=0`:

~~~text
H1:
  W1 [start=10, end=50] x=1 OK
  R1 [start=20, end=30] → 0

H2:
  W1 [start=10, end=20] x=1 OK
  R1 [start=30, end=40] → 0
~~~

Lịch nào tự tạo phản ví dụ linearizability, nếu không có thao tác khác? Hãy vẽ một thứ tự tuần tự hợp lệ cho lịch còn lại.

**Gợi ý:** H1 có overlap nên có thể đặt R1 trước W1; H2 không có cách giải thích đó.

### Bài 18 — Viết contract thử nghiệm

Hãy chọn một nghiệp vụ “cấp voucher tối đa 100 lượt” rồi điền:

~~~yaml
operation: "claimVoucher"
invariant: "..."
readRoute: "..."
commitCondition: "..."
onNetworkPartition: "..."
minorityBehavior: "..."
retryIdempotency: "..."
failureTests:
  - "..."
~~~

**Gợi ý:** yêu cầu quan trọng là không vượt quota; đừng quyết định cấp voucher chỉ bằng một read eventual từ cache.

## 41. Checklist khi áp dụng CAP vào thiết kế NoSQL

Trước khi đặt nhãn CP/AP, nhóm phát triển nên trả lời:

1. **Dữ liệu logic nào được nhân bản?** Khóa, document, partition, transaction?
2. **Nguồn có thẩm quyền là gì?** Leader, quorum, log đồng thuận hay một registry?
3. **Những read/write nào cần linearizable?** Có thao tác chỉ cần eventual/session consistency không?
4. **Khi mất liên lạc giữa các replica, phía nào được phép ACK một write?** Theo điều kiện gì?
5. **Phía không có quorum trả gì?** Chờ, lỗi rõ ràng, route lại hay dữ liệu cũ với contract khác?
6. **Một client có thể đọc stale dữ liệu đã chính mình ghi không?** Nếu không, session watermark được giữ thế nào?
7. **Hai phía có thể cùng ghi cùng một key không?** Nếu có, merge/conflict rule là gì?
8. **Ràng buộc nghiệp vụ nào không thể phục hồi bằng merge?** Tồn kho, unique claim, tiền, quyền sở hữu?
9. **Timeout sau commit được xử lý thế nào?** Có requestId và idempotency không?
10. **Khi mạng lành, xử lý replica và leader cũ thế nào?** Fencing, repair, replay, version ordering?
11. **Có phân biệt đọc thông tin và quyết định commit không?** Cache/read model có được dùng làm nguồn cấp phát không?
12. **SLO latency/uptime được đo riêng với CAP không?** Có mô tả tình huống lỗi cụ thể?
13. **Có fault injection và history capture không?** Có kiểm cả lỗi mạng, failover, crash và duplicate request?

Nếu những câu hỏi này chưa có câu trả lời, việc gắn một nhãn “CP”, “AP” hoặc “CA” chưa đủ làm tài liệu kiến trúc đáng tin.

## 42. Tổng kết

Ba thuộc tính trong CAP có ý nghĩa cụ thể:

1. **Consistency (C)** là bảo đảm hành vi đọc/ghi **linearizable** trong phạm vi được xét: có thể đặt mỗi thao tác vào một thứ tự tuần tự hợp lệ tôn trọng các thao tác hoàn thành trước đó theo thời gian thực. Nó không đồng nghĩa với bất biến nghiệp vụ của ACID.
2. **Availability (A)** là bảo đảm **mọi request tới node không bị lỗi cuối cùng được đáp ứng bằng kết quả hợp lệ** trong mô hình. Nó không phải uptime %, latency p95 hay việc trả nhanh một lỗi “không thể phục vụ”.
3. **Partition tolerance (P)** phản ánh khả năng **mạng chia cắt khiến các node còn sống không phối hợp được**. Trong hệ phân tán thực, đây là loại lỗi phải thiết kế để xử lý, không phải một tính năng có thể bỏ chọn nhằm né định lý.
4. **CAP giới hạn bảo đảm đồng thời trong partition.** Nếu phía A đã chấp nhận một write nhưng phía B không thể biết, B không thể vừa chắc chắn trả giá trị mới nhất vừa luôn hoàn thành mọi read. Muốn giữ C phải có lúc chờ/từ chối; muốn giữ A phải cho phép một số lịch có dữ liệu cũ/xung đột.
5. **CP/AP là hướng ưu tiên, không phải tem cố định cho mọi sản phẩm.** Một ứng dụng có thể dùng strong conditional writes cho cấp phát, eventual reads cho catalog và merge có kiểm soát cho giỏ hàng.
6. **CAP không thay thế các yêu cầu khác.** Durability, isolation, idempotency, conflict resolution, session guarantees, performance và backup đều cần được thiết kế/kiểm thử riêng.
7. **Định nghĩa mô hình bằng những lịch được phép và lịch bị cấm.** Một tuyên bố consistency có giá trị khi gắn với operation, đường đọc/ghi, mốc ACK, failure model và bất biến nghiệp vụ.

**Nguyên tắc thực hành:** thay vì hỏi đơn giản **“Database NoSQL này là CP hay AP?”**, hãy hỏi **“Khi hai nhóm node không trao đổi được thông điệp, thao tác nào vẫn được ACK, thao tác nào phải chờ, và người dùng được phép nhìn thấy lịch sử đọc/ghi nào?”**. Câu trả lời đó mới dẫn đến một lựa chọn consistency và availability có thể chứng minh, kiểm thử và vận hành.

# Consistency level và đánh đổi khi đọc ghi

Một khách hàng vừa thêm sản phẩm vào giỏ hàng trên điện thoại, sau đó mở website trên laptop. Nếu ứng dụng đọc dữ liệu từ một bản sao ở vùng Azure khác, liệu sản phẩm vừa thêm đã xuất hiện? Một hệ thống đặt chỗ có thể chấp nhận hiển thị số lượt xem chậm vài giây, nhưng không thể dễ dàng chấp nhận xác nhận hai người cùng sở hữu một vé duy nhất. Đây là các câu hỏi về **tính nhất quán dữ liệu (data consistency)**, cùng với tính đúng đắn của thao tác ghi.

**Azure Cosmos DB** là dịch vụ cơ sở dữ liệu phân tán toàn cầu, trong đó các bản sao dữ liệu có thể nằm ở nhiều vùng. Với **Azure Cosmos DB for NoSQL**, người thiết kế được chọn một trong **năm consistency levels**: **Strong, Bounded Staleness, Session, Consistent Prefix, Eventual**. Mức càng chặt thường đem lại cam kết về độ mới và thứ tự đọc mạnh hơn, nhưng có thể đánh đổi latency, khả năng mở rộng, throughput, chi phí Request Units và điều kiện triển khai đa vùng.

Điểm quan trọng nhất: **Consistency level nói về những giá trị mà thao tác đọc có thể quan sát so với các lần ghi đã được chấp nhận**. Nó **không tự thay thế** transaction, kiểm tra phiên bản, khóa nghiệp vụ, phân quyền hoặc chiến lược xử lý xung đột khi có nhiều writer.

Bài thuộc chương **Dữ liệu NoSQL với Cosmos DB** của mô-đun **CLOUD_PROVIDERS_AZURE**. Trong lộ trình Azure từ subscription, resource group và Microsoft Entra ID, mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu đến triển khai, giám sát, bảo vệ và kiểm soát chi phí, đây là nền tảng để lựa chọn chiến lược đọc/ghi đúng theo nghiệp vụ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích consistency và phân biệt **replication lag**, **stale reads** và lỗi ghi đồng thời.
2. So sánh năm mức Strong, Bounded Staleness, Session, Consistent Prefix và Eventual.
3. Giải thích read-your-writes, monotonic reads, consistent prefix, linearizability và session token.
4. Đánh giá sự khác nhau giữa **account default consistency** và việc yêu cầu mức đọc yếu hơn khi tính năng/API hỗ trợ.
5. Hiểu đánh đổi giữa độ mới dữ liệu, read latency, RU, availability và multi-region topology.
6. Chọn mức consistency cho giỏ hàng, danh mục, dashboard, cảm biến và nghiệp vụ tài chính.
7. Phân biệt consistency với **transactional batch**, **ETag/optimistic concurrency** và **multi-region write conflict resolution**.
8. Kiểm tra cấu hình, telemetry, SDK session và các tình huống lỗi bằng phương pháp an toàn.

## 1. Vì sao cơ sở dữ liệu phân tán có thể trả dữ liệu cũ?

Khi Azure Cosmos DB duy trì nhiều bản sao, một lần ghi cần được phân phối theo giao thức nhân bản của dịch vụ. Các bản sao và vùng có thể không cùng quan sát một phiên bản ở đúng một thời điểm.

~~~text
                    Azure Cosmos DB

             Client A ghi giỏ hàng v2
                        |
                        v
              Write/replication path
                        |
             +----------+----------+
             |                     |
             v                     v
        Region East             Region West
        Replica có v2           Replica còn v1
             |                     |
             |                     v
             |               Client B đọc
             |                     |
             +---------------------+

Nếu consistency cho phép stale read:
  Client B có thể quan sát v1 trong lúc replication chưa bắt kịp.
~~~

Sơ đồ chỉ minh họa **độ trễ lan truyền dữ liệu**; đường đi ghi thật, quorum và topology phụ thuộc tài khoản, partition, vùng và consistency đã cấu hình.

### Ví dụ phiên bản đơn giản

~~~text
12:00:00  Giỏ hàng = [A]          (v1)
12:00:01  Client ghi thêm B       (v2)
12:00:02  Một replica còn v1
12:00:03  Replica bắt kịp v2
~~~

Nếu đọc ở thời điểm 12:00:02 và hệ thống cho phép dữ liệu trễ, kết quả có thể là **[A]** dù write mới đã thành công ở một phía. Với yêu cầu chặt hơn, dịch vụ phải áp điều kiện để tránh trả kết quả không đáp ứng cam kết, đôi khi khiến đọc phải chờ hoặc đi theo đường truy cập khác.

### Replication lag khác lỗi ghi

- **Replication lag:** một bản sao chưa quan sát phiên bản được ghi gần đây.
- **Stale read:** client nhận bản dữ liệu cũ hơn trạng thái mới nhất.
- **Write conflict:** hai writer cập nhật cùng đối tượng với các giá trị khác nhau.
- **Lost update:** cập nhật sau vô tình ghi đè cập nhật trước mà không có bảo vệ đồng thời.
- **Application invariant violation:** quy tắc nghiệp vụ như số ghế không được âm bị phá vỡ.

Consistency level có liên hệ mạnh với hai mục đầu, nhưng không tự xử lý đầy đủ ba vấn đề còn lại.

## 2. Năm mức nhất quán trong Azure Cosmos DB

Từ **mạnh nhất** tới **linh hoạt nhất về quan sát bản sao**:

<table>
<tr><th>Thứ tự</th><th>Consistency level</th><th>Cam kết cốt lõi</th></tr>
<tr><td>1</td><td><b>Strong</b></td><td>Đọc quan sát dữ liệu đã commit theo ngữ nghĩa mạnh/linearizable được dịch vụ cam kết</td></tr>
<tr><td>2</td><td><b>Bounded Staleness</b></td><td>Đọc có thể trễ nhưng giới hạn trong mức K phiên bản hoặc T thời gian được cấu hình, giữ thứ tự tiền tố</td></tr>
<tr><td>3</td><td><b>Session</b></td><td>Cam kết nhất quán mạnh cho những thao tác trong cùng session, đặc biệt read-your-writes</td></tr>
<tr><td>4</td><td><b>Consistent Prefix</b></td><td>Đọc có thể trễ nhưng không thấy lịch sử ghi bị đảo thứ tự trong phạm vi cam kết</td></tr>
<tr><td>5</td><td><b>Eventual</b></td><td>Nếu không còn ghi mới, các bản sao cuối cùng sẽ hội tụ; không cam kết độ mới hoặc thứ tự đọc trước khi hội tụ</td></tr>
</table>

**Session** là mức consistency mặc định phổ biến của Azure Cosmos DB account for NoSQL nếu không chọn khác. “Mặc định” không có nghĩa một SDK/call bất kỳ luôn có read-your-writes khi ứng dụng làm mất session token.

### Một bảng đánh đổi định tính

| Level | Độ mới được cam kết | Thứ tự quan sát | Chi phí/latency đọc tương đối | Dùng phù hợp |
|---|---|---|---|---|
| **Strong** | Mạnh nhất, không trả bản đã cũ so với cam kết linearizability | Mạnh | Thường cao hơn, chịu ràng buộc topology | Đọc cần dữ liệu commit mới nhất khi tính năng hỗ trợ |
| **Bounded Staleness** | Có giới hạn K/T | Có consistent prefix | Thường cao hơn các mức yếu | Cần giới hạn độ trễ có định lượng |
| **Session** | Read-your-writes trong session | Các đảm bảo session | Cân bằng cho nhiều ứng dụng | Giỏ hàng, profile, SaaS phổ biến |
| **Consistent Prefix** | Không giới hạn thời gian cụ thể | Không quan sát lịch sử đảo thứ tự | Thường linh hoạt | Luồng sự kiện cần thứ tự nhưng chấp nhận trễ |
| **Eventual** | Không giới hạn thời gian cụ thể | Không cam kết thứ tự như prefix | Thường linh hoạt | Dashboard, counter, dữ liệu ít nhạy freshness |

“Cao hơn/thấp hơn” trong bảng là **định hướng thiết kế**, không phải SLA latency hay RU cố định. Hãy benchmark với workload, region và API thật.

## 3. Những thuật ngữ cần hiểu trước

| Thuật ngữ | Ý nghĩa bằng lời |
|---|---|
| **Read-your-writes** | Sau khi chính mình ghi thành công, những lần đọc trong phạm vi bảo đảm không quay về giá trị cũ hơn lần ghi đó |
| **Monotonic reads** | Một session đã quan sát phiên bản mới thì không quay về phiên bản cũ hơn |
| **Monotonic writes** | Các lần ghi của session được duy trì thứ tự phù hợp |
| **Writes-follow-reads** | Lần ghi trong session được sắp theo những trạng thái mà session đã đọc |
| **Consistent prefix** | Nếu lịch sử có A rồi B, reader không được thấy B mà bỏ qua A theo ngữ nghĩa thứ tự cam kết |
| **Linearizability** | Thao tác có thể được quan sát như xảy ra nguyên tử tại một thời điểm phù hợp với thứ tự thời gian thực |
| **Staleness bound** | Giới hạn mức dữ liệu đọc được phép tụt so với trạng thái cập nhật |
| **Session token** | Thông tin tiến độ nhất quán được dùng để duy trì cam kết session giữa các request |
| **Commit** | Ghi đã được hệ thống chấp nhận theo consistency và giao thức của dịch vụ |

### Read-your-writes không phải “mọi user đều thấy ngay”

~~~text
User A (session A):
    write cart v2 -> read cart -> thấy ít nhất v2 theo cam kết session

User B (session B):
    read cart ngay sau đó -> có thể còn v1 nếu consistency cho phép
~~~

Session consistency rất hữu ích cho trải nghiệm “tôi vừa lưu thì tôi phải thấy”, nhưng không buộc mọi session độc lập ở mọi vùng phải đồng thời thấy cùng một phiên bản tức thì.

### “Thứ tự” cần có phạm vi

Các mức consistency mô tả thứ tự quan sát bản ghi/phiên bản theo mô hình dịch vụ. Nó **không** tự chứng minh thứ tự nghiệp vụ qua nhiều containers, partitions, queues hoặc hệ thống bên ngoài. Nếu quy trình gồm Cosmos DB, Event Hubs và Service Bus thì cần chiến lược điều phối riêng.

## 4. Strong consistency: ưu tiên độ mới và thứ tự

**Strong consistency** hướng tới đọc dữ liệu mới nhất đã commit theo ngữ nghĩa linearizable được Azure Cosmos DB cung cấp. Khi yêu cầu đọc phù hợp với mức này, dịch vụ không được phép tùy tiện trả về một phiên bản cũ hơn trạng thái đã commit mà cam kết bắt buộc phải quan sát.

~~~text
Client A:
  write item version = 10
  nhận thành công

Client B:
  read sau khi write đã hoàn tất
  -> phải thỏa cam kết Strong đối với version = 10
~~~

### Khi nào cân nhắc Strong?

- Một số phép đọc cần quyết định dựa trên dữ liệu đã commit mới nhất.
- Trường hợp nghiệp vụ không chấp nhận đọc lại phiên bản cũ sau khi ghi đã xác nhận.
- Hệ thống có yêu cầu consistency chặt và khả năng chọn topology/tier phù hợp.

### Đánh đổi

Strong consistency có thể tăng read latency và mức dùng RU do phải đáp ứng điều kiện nhất quán chặt hơn. Trong tài khoản phân phối vùng, chi phí phối hợp bản sao và giới hạn vùng có thể đáng kể. **Strong có các hạn chế đối với tài khoản multi-region write và topology nhất định**; không mặc định có thể bật Strong trên mọi account/region configuration.

### Strong vẫn không thay thế transaction nghiệp vụ

Giả sử hai worker cùng đọc số ghế còn lại bằng 1, rồi cùng gửi yêu cầu giảm về 0. Dù từng read là Strong, thiết kế “read rồi write” tách rời vẫn có race nếu không kiểm soát cập nhật đồng thời.

Giải pháp có thể là **optimistic concurrency với ETag**, cập nhật có điều kiện hoặc **transactional batch** cho các thao tác nằm trong cùng logical partition, tùy bài toán.

## 5. Bounded Staleness: cho phép trễ nhưng có giới hạn

**Bounded Staleness** cho phép client đọc bản cũ trong **giới hạn độ trễ** được cấu hình. Cosmos DB diễn tả giới hạn qua hai tham số:

- **K (maxStalenessPrefix):** số phiên bản/operations tối đa mà dữ liệu đọc có thể tụt sau.
- **T (maxIntervalInSeconds):** khoảng thời gian trễ tối đa.

Dịch vụ áp cơ chế để dữ liệu không vượt khỏi các giới hạn theo ngữ nghĩa được quy định và vẫn tôn trọng **consistent prefix**.

~~~text
Chuỗi phiên bản: v1 -> v2 -> v3 -> v4 -> v5

Reader dùng Bounded Staleness:
   Có thể đọc bản cũ khi còn trong K/T được cho phép.
   Không được vượt quá giới hạn staleness đã cấu hình.
   Không được quan sát một lịch sử đảo thứ tự.
~~~

### Ví dụ cách nghĩ về K/T

Giả sử doanh nghiệp yêu cầu “dữ liệu thống kê không được trễ quá khoảng năm phút và số phiên bản được bỏ qua cũng phải có giới hạn”. Đây là ứng viên để **đánh giá** Bounded Staleness. Nhưng các giá trị K/T thực tế phải nằm trong khoảng hợp lệ của dịch vụ, đặc biệt khi tài khoản có nhiều vùng.

**Không tự gán K=5, T=5 giây cho mọi cấu hình**. Azure quy định miền giá trị và khả năng hỗ trợ tùy topology; nên xác nhận trên tài liệu và API khi lập cấu hình.

### Trade-off

- Có cam kết freshness rõ hơn Session/Consistent Prefix/Eventual.
- Phải chấp nhận thêm overhead phối hợp theo yêu cầu bound.
- Có ràng buộc topology và write-region; cần kiểm tra support matrix.
- Không phải lựa chọn mặc định cho mọi dashboard: nhiều hệ thống chấp nhận Eventual hoặc Session với chi phí/liveness tốt hơn.

### Bounded Staleness khác Session ở đâu?

**Session** cam kết người dùng nhìn lại những gì **chính session đã ghi**, nhưng không đặt một giới hạn thời gian stale chung cho mọi session. **Bounded Staleness** đặt bound cho dữ liệu quan sát, kể cả khi reader và writer không ở cùng session, trong phạm vi dịch vụ cam kết.

## 6. Session consistency: lựa chọn cân bằng phổ biến

**Session** là một lựa chọn rất thực tế cho ứng dụng web/mobile:

1. Người dùng cập nhật hồ sơ.
2. API ghi thành công vào Cosmos DB.
3. Cùng session đọc lại hồ sơ.
4. Người dùng mong thấy dữ liệu mình vừa lưu.

Session consistency cung cấp những bảo đảm như **read-your-writes**, **monotonic reads**, **monotonic writes**, **writes-follow-reads** và **consistent prefix** trong phạm vi session khi token/context được duy trì.

~~~text
Ứng dụng giỏ hàng:

Session S:
  write cart: [A]         -> v1
  write cart: [A, B]      -> v2
  read cart              -> phải quan sát trạng thái
                            thỏa cam kết của session S.

Session T khác:
  read cart tại vùng khác -> có thể quan sát v1
                            trong thời gian bản sao bắt kịp.
~~~

### Tại sao Session là điểm cân bằng?

Nó phù hợp với kỳ vọng phổ biến rằng người dùng thấy dữ liệu của chính mình, trong khi không buộc mọi read độc lập phải có ràng buộc mạnh như Strong.

**Session vẫn có thể trả dữ liệu cũ đối với ghi phát sinh từ session khác.** Một bảng tỷ giá hoặc inventory được các writer khác cập nhật liên tục cần được đánh giá thêm theo yêu cầu nghiệp vụ.

## 7. Session token và đường đi của request

Cosmos DB sử dụng **session token** để theo dõi tiến độ cần thiết cho session consistency. SDK thường tự quản lý token cho những thao tác thực hiện qua một **CosmosClient** sống đủ lâu và phù hợp.

~~~text
Client / API instance A
        |
        | Write item -> nhận session progress/token
        v
Azure Cosmos DB
        |
        v
Client / API instance A
        |
        | Read cùng session context
        v
Quan sát dữ liệu thỏa read-your-writes
~~~

### Vấn đề với ứng dụng stateless nhiều instances

~~~text
Mobile request 1
     |
     v
API instance A -> write -> session token tại A

Mobile request 2
     |
     v
API instance B -> read; B không có session token từ A

Không nên mặc định B có cùng cam kết session như A.
~~~

Nếu ứng dụng cần read-your-writes **xuyên qua API instances, Functions invocations hoặc các service khác nhau**, cần thiết kế cách duy trì/truyền **session token/context** theo SDK/API được hỗ trợ.

### Thực hành tốt

- Tái sử dụng **CosmosClient** hợp lý thay vì tạo một client mới cho mỗi request.
- Xác định vùng đọc/ghi của mỗi dịch vụ.
- Kiểm tra hành vi của session token khi client chuyển instance.
- Khi phải truyền token qua các tầng, bảo vệ dữ liệu, tránh log và không dùng token như credential.
- Test đường đi load balancer đổi backend instance ngay sau thao tác ghi.

**Session token không phải access token của Microsoft Entra ID.** Nó hỗ trợ consistency, không dùng để xác thực hay cấp quyền truy cập dữ liệu.

## 8. Consistent Prefix: giữ thứ tự, chấp nhận trễ

**Consistent Prefix** bảo đảm các bản đọc phản ánh một **tiền tố hợp lệ của lịch sử ghi**, tức không quan sát các cập nhật sau theo thứ tự trước các cập nhật đi trước trong phạm vi cam kết.

~~~text
Producer ghi theo thứ tự:
    Event A -> Event B -> Event C

Consistent Prefix có thể cho thấy:
    []
    [A]
    [A, B]
    [A, B, C]

Không được diễn giải là:
    [B, C] mà chưa có A trong cùng lịch sử thứ tự được bảo đảm
~~~

Ví dụ này là **ẩn dụ về thứ tự quan sát**, không phải cam kết Azure Cosmos DB tự trả về một mảng event toàn cục theo thứ tự giữa mọi partitions.

### Khi dùng?

- Màn hình sự kiện hoặc bản ghi hoạt động mà việc đảo thứ tự là gây khó hiểu.
- Hệ thống phân tích cần thứ tự cập nhật hợp lệ nhưng chấp nhận trễ.
- Một số read model không cần read-your-writes riêng cho từng user.

### Không có bound độ trễ

Consistent Prefix không tự hứa “chậm tối đa ba giây”. Nếu nghiệp vụ cần một giới hạn rõ ràng, cân nhắc Bounded Staleness nếu topology và chi phí phù hợp.

### Session mạnh hơn Prefix ở điểm nào?

Session bao gồm các bảo đảm bổ sung cho một session cụ thể, đặc biệt **read-your-writes** và **monotonic reads**. Consistent Prefix không thay thế những bảo đảm đó.

## 9. Eventual consistency: cuối cùng sẽ hội tụ

**Eventual** là mức yếu nhất trong năm levels. Nếu các lần ghi mới dừng và hệ thống hoạt động bình thường, các bản sao cuối cùng sẽ hội tụ về cùng trạng thái theo cơ chế của dịch vụ.

~~~text
Write v3
   |
   +-- Replica A đã có v3
   +-- Replica B còn v2
   +-- Replica C còn v1

Sau khi replication hội tụ:
   A, B, C cùng phản ánh trạng thái đã được giải quyết.
~~~

### Những điều Eventual không cam kết

- Không có upper bound cố định cho staleness trong hợp đồng level này.
- Không nhất thiết thỏa read-your-writes.
- Không đảm bảo monotonic reads như Session.
- Không có thứ tự tiền tố chặt như Consistent Prefix.
- Không đảm bảo business invariants hoặc exactly-once processing.

### Khi phù hợp?

- Dashboard tổng hợp cho phép hiển thị trễ.
- Dữ liệu quan sát/telemetry không cần đọc ngay giá trị mới nhất.
- Cache-like read model hoặc danh mục tham khảo ít nhạy về freshness.
- Một số phép đếm/lượt xem chấp nhận eventual convergence theo thiết kế.

### Rủi ro phổ biến

Không dùng Eventual cho một kiểm tra nghiệp vụ kiểu “nếu còn đúng một vé thì xác nhận mua” mà thiếu atomic conditional write/transaction. Một stale read có thể khiến nhiều client **đều nghĩ còn hàng**, còn cơ chế chống oversell phải nằm ở cập nhật có điều kiện hoặc mô hình nghiệp vụ.

## 10. Nhìn năm levels trên cùng một lịch sử

Giả sử item **stock** lần lượt được ghi:

~~~text
v1: stock=10
v2: stock=9
v3: stock=8
v4: stock=7
~~~

Ở một vùng xa, các bản sao có thể chưa đồng bộ hoàn toàn. Cách hiểu:

| Level | Reader có thể quan sát gì? |
|---|---|
| **Strong** | Trạng thái phù hợp với lần ghi mới nhất đã commit theo linearizability |
| **Bounded Staleness** | Một trạng thái cũ còn nằm trong giới hạn K/T và đúng thứ tự |
| **Session** | Đủ mới so với những ghi thuộc session của reader; ghi từ session khác có thể chưa tới |
| **Consistent Prefix** | Một tiền tố lịch sử hợp lệ, không buộc độ mới hay read-your-writes |
| **Eventual** | Có thể thấy trạng thái cũ và không được hứa thứ tự/độ mới tương ứng các mức mạnh hơn |

**Không được suy luận** “Strong luôn trả v4” nếu v4 chưa commit, hay “Session luôn trả v4” nếu v4 thuộc session khác. Cần phân biệt thời điểm request, acknowledgement và phạm vi bảo đảm.

## 11. Consistency không phải isolation level của SQL

Trong hệ quản trị quan hệ, bạn có thể quen với **Read Committed**, **Repeatable Read** hoặc **Serializable**. Những thuật ngữ đó liên quan transaction isolation; chúng không tương đương trực tiếp với consistency levels của Azure Cosmos DB.

| Câu hỏi | Cơ chế liên quan |
|---|---|
| Đọc replica xa có thể thấy bản cũ không? | **Consistency level** |
| Hai writer cập nhật cùng item có ghi đè nhau không? | **ETag / optimistic concurrency**, conflict resolution |
| Hai thay đổi có commit atomically với nhau không? | **Transactional batch/transaction scope** |
| Một tenant có được xem item của tenant khác không? | **Authentication + authorization + application checks** |
| Một request xử lý hai lần có tạo side effect trùng không? | **Idempotency / durable ledger** |
| Data bị mất trong sự cố vùng lớn đến mức nào? | **Replication topology, backup/DR, RPO/RTO** |

Việc chọn **Strong** không biến tất cả các write xuyên nhiều logical partitions thành một transaction.

## 12. Transaction scope và logical partition

Trong Azure Cosmos DB for NoSQL, **transactional batch** hỗ trợ thực hiện nhiều operations atomically **trong cùng một logical partition key** theo API và điều kiện hỗ trợ.

~~~text
Partition key: tenantId = tenant-A

Item order-1
Item order-summary
Item inventory-reservation

Nếu cùng logical partition và operation hợp lệ:
   Có thể thiết kế transactional batch.

Nếu nằm ở nhiều partition keys:
   Không thể tự coi đó là cùng một atomic batch.
~~~

### Thiết kế partition key ảnh hưởng tính đúng đắn

Một mô hình đặt hàng cần update đơn và reservation atomically có thể phải cân nhắc partition key theo **orderId** hoặc một aggregate phù hợp. Nhưng việc gom quá nhiều item vào một logical partition cũng có rủi ro hot partition và giới hạn kích thước/throughput.

**Không thiết kế partition key chỉ để tối ưu consistency.** Phải cân bằng locality của transaction, phân bố throughput, patterns truy vấn và khả năng tăng trưởng.

### Transactional batch không tạo Strong globally

Batch giúp các operations trong phạm vi hỗ trợ commit hoặc rollback cùng nhau. Client khác ở vùng xa vẫn chịu cam kết quan sát của consistency level tài khoản/requests.

## 13. ETag và optimistic concurrency control

Một item có thể mang trường hệ thống **_etag**. Khi cập nhật, client có thể yêu cầu thay đổi **chỉ thành công nếu ETag vẫn khớp** theo conditional request được SDK/API hỗ trợ.

~~~text
Item: {id: CART-01, quantity: 1, _etag: E1}

Worker A đọc E1
Worker B đọc E1

Worker A update quantity=2 với điều kiện ETag=E1
  -> thành công, item trở thành E2

Worker B update quantity=3 với điều kiện ETag=E1
  -> bị từ chối vì item không còn E1
  -> phải đọc lại, tính lại và retry an toàn
~~~

### Tại sao điều này cần dù đã bật Strong?

Hai worker có thể cùng đọc một phiên bản còn mới tại thời điểm của chúng, sau đó một worker ghi trước worker kia. Nếu write không có điều kiện, lần ghi sau có thể làm mất cập nhật trước. **ETag bảo vệ quyết định write dựa trên version**, là lớp khác với mức nhất quán đọc.

### Xử lý HTTP 412

Khi ETag/If-Match không khớp, Cosmos DB có thể phản hồi **HTTP 412 Precondition Failed**. Ứng dụng nên:

1. Không retry ngay cùng ETag cũ vô hạn.
2. Đọc lại item/trạng thái mới nhất trong phạm vi consistency cần thiết.
3. Tính lại logic nghiệp vụ.
4. Thử conditional update mới trong giới hạn retry.
5. Báo xung đột cho người dùng nếu không thể hợp nhất.

Không dùng cơ chế “last writer wins” ở client một cách ngẫu nhiên nếu cập nhật mang giá trị tài chính.

## 14. Multi-region reads và vấn đề locality

Cosmos DB có thể phân phối dữ liệu qua nhiều vùng Azure; client có thể đọc từ vùng gần để giảm network round-trip khi mô hình/consistency cho phép.

~~~text
             Write region
                Region A
                   |
         Replicate to read regions
             /             \
            v               v
         Region B          Region C
            ^                 ^
            |                 |
        Client B          Client C
~~~

### Đánh đổi chung

- Đọc ở vùng gần thường giảm network latency.
- Một bản sao vùng gần có thể trễ về phiên bản.
- Mức consistency càng mạnh có thể yêu cầu thêm phối hợp hoặc hạn chế đường đọc/ghi.
- Mất kết nối liên vùng ảnh hưởng khác nhau theo cấu hình.
- RU và độ trễ cần đo theo vùng thực sự mà SDK sử dụng.

### Preferred regions

SDK Cosmos DB có các cách cấu hình vùng ưu tiên/region routing theo phiên bản API. Nếu ứng dụng triển khai AKS tại Region B, việc chỉ định region ưu tiên có thể giảm độ trễ hoặc giúp thiết kế failover.

Nhưng **preferred region không bảo đảm đọc luôn mới nhất**. Tính mới phụ thuộc consistency, session token, trạng thái replica và điều kiện được dịch vụ hỗ trợ.

### Strong và multi-region writes

Không mặc định **Strong** được hỗ trợ với cấu hình **multiple write regions**. Trong Cosmos DB, các levels mạnh như Strong và Bounded Staleness có những ràng buộc đối với tài khoản multi-write/topology; trước khi thiết kế triển khai phải kiểm tra các tùy chọn đang được Azure cho phép.

## 15. Multi-region writes và xung đột

Trong mô hình multi-region writes được hỗ trợ, hai vùng có thể nhận cập nhật cùng item trong khoảng thời gian gần nhau. Nếu chúng ghi giá trị khác nhau, hệ thống cần **conflict resolution**.

~~~text
Region A: update item quantity = 4
Region B: update item quantity = 5
        \               /
         \             /
          v           v
          Conflict resolution
                  |
                  v
           Trạng thái cuối
~~~

**Consistency level không tự quyết định đúng sai nghiệp vụ của xung đột.** Một chính sách dựa trên last-write-wins hoặc custom logic (nếu hỗ trợ) có thể phù hợp với profile nhưng không chắc phù hợp với số dư tiền.

### Rủi ro ở mức nghiệp vụ

Nếu hai vùng ghi inventory dựa trên stock cũ, chỉ chọn Session hoặc Eventual không đủ bảo vệ không bán quá số hàng. Cần lựa chọn:

- Một nguồn quyết định/partition ownership cho tài nguyên khan hiếm.
- Conditional updates/ETag trong phạm vi hỗ trợ.
- Idempotency key và transaction boundaries.
- Xử lý conflict được định nghĩa theo domain.
- Reconciliation khi kết quả giữa các hệ thống khác nhau.

Không hứa có **global serializable business transaction** chỉ bằng cách bật replicated database.

## 16. Consistency và Request Units (RU)

Azure Cosmos DB dùng **Request Units (RU)** làm thước đo chi phí hoạt động đọc/ghi/truy vấn theo tài nguyên được cấp. RU của một operation phụ thuộc vào:

- Kích thước item.
- Loại thao tác: point read, query, create, replace, patch, delete.
- Indexing policy và chi phí ghi.
- Số partition tham gia query.
- Query complexity và lượng kết quả.
- Consistency level và những yếu tố dịch vụ liên quan.

### Ảnh hưởng của level tới read RU

Trong mô hình Cosmos DB for NoSQL, **Strong** và **Bounded Staleness** thường có chi phí **read RU cao hơn** so với **Session, Consistent Prefix, Eventual** cho cùng dữ liệu/điều kiện. Tài liệu Azure thường mô tả chi phí read mạnh hơn khoảng **gấp đôi** so với nhóm yếu hơn ở những trường hợp tiêu chuẩn, nhưng không dùng con số này làm dự báo tài chính tuyệt đối cho mọi query/topology.

~~~text
Cùng một point read trong cùng điều kiện minh họa:

Session/Eventual:
   RU đọc ở mức tham chiếu thấp hơn

Strong/Bounded Staleness:
   RU đọc có thể cao hơn

Số thực tế:
   Đo Request Charge trên workload và SDK/metrics.
~~~

### Consistency không phải nguồn chi phí duy nhất

Một cross-partition query quét nhiều items có thể tốn RU hơn nhiều so với point read, dù cả hai đều dùng Eventual. Trước khi nới consistency để giảm chi phí, hãy:

1. Chuyển sang **point read** khi biết id + partition key.
2. Kiểm tra partition key và truy vấn cross-partition.
3. Kiểm tra indexing policy.
4. Tối ưu data model và kích thước item.
5. Đo RU và latency theo thực tế.

## 17. Latency, throughput và availability

Một workload đọc thường xuyên có ba mục tiêu khó đồng thời tối ưu:

1. **Freshness:** có thấy được ghi mới nhất không?
2. **Latency:** một read mất bao lâu, đặc biệt ở p95/p99?
3. **Availability:** read có tiếp tục đáp ứng khi replica/region/link gặp sự cố không?

### Strong: cam kết chặt có cái giá

Khi bị giới hạn đường đọc hoặc cần phối hợp dữ liệu, Strong có thể tăng thời gian phản hồi và chịu những ràng buộc availability/topology nhất định. Đây là đánh đổi cần được cân nhắc với SLA.

### Session: trải nghiệm tốt cho user

Đối với nhiều web apps, Session cho phép người dùng thấy thay đổi của mình mà vẫn tận dụng sự linh hoạt hơn Strong. Nhưng ứng dụng cần duy trì session token đúng cách.

### Eventual: tăng sự linh hoạt, chấp nhận freshness yếu

Eventual có thể phù hợp những read models chịu trễ và phục vụ quy mô lớn. Tuy nhiên, không được dùng nó để suy ra **tính đúng đắn của lệnh ghi**.

### Không nên ghi số ms cố định

Không có quy tắc “Strong = 100 ms, Eventual = 5 ms” cho mọi tài khoản. Vùng Azure, phân bố client, số replicas, item size, cache, network và RU pressure tạo chênh lệch lớn. Cần load test theo vùng và giờ peak.

## 18. Read-after-write xuyên nhiều ứng dụng

Một trải nghiệm phổ biến:

~~~text
Mobile POST /cart/items
      |
      v
API Instance A -> Cosmos DB write cart v7
      |
      v
HTTP 200 thành công

Mobile GET /cart
      |
      v
API Instance B -> Cosmos DB read
      |
      v
Yêu cầu phải thấy ít nhất v7
~~~

### Nếu account dùng Session

Ứng dụng phải đảm bảo request B mang **cùng consistency context cần thiết**. Reuse client trong cùng instance chưa chắc đủ nếu mỗi request chuyển sang instance khác.

### Các cách thiết kế

- Điều phối session token/context xuyên API tiers một cách an toàn nếu SDK hỗ trợ.
- Cân nhắc routing request nhất quán theo session nếu kiến trúc phù hợp, nhưng không chỉ dựa vào sticky sessions như cơ chế dữ liệu duy nhất.
- Dùng trạng thái trả về từ write response để cập nhật UI ngay, rồi reconcile.
- Nếu cần cam kết mới nhất cho mọi session, đánh giá Strong và topology phù hợp.
- Với phép ghi quan trọng, thiết kế ETag/transaction chứ không chỉ nâng consistency.

### Test cần có

1. Ghi vào Region A.
2. Đọc ngay trên cùng SDK client/session.
3. Đọc qua một API instance khác.
4. Đọc ở Region B theo preferred region.
5. Lặp lại khi chuyển vùng/failover.
6. So sánh version/ETag và latency, không chỉ nhìn HTTP 200.

## 19. Override consistency ở request-level

Tài khoản Cosmos DB có **default consistency level**. Một số SDK/API cho phép request sử dụng **mức yếu hơn** mặc định trong phạm vi được hỗ trợ.

~~~text
Account default: Session
    |
    +-- Cart read: Session (theo account)
    |
    +-- Dashboard read: có thể yêu cầu Eventual
                       nếu SDK/API hỗ trợ override
~~~

**Không thể dùng request override để nâng lên mức mạnh hơn account default.** Ví dụ account mặc định Eventual không thể biến một read thành Strong chỉ bằng cách gắn header tùy ý.

### Lưu ý quan trọng

- Tập consistency levels được phép override phụ thuộc API/SDK và cấu hình tài khoản.
- Việc chọn mức yếu hơn cho một read không thay đổi consistency của toàn account.
- Tính chất session token và routing cần được kiểm chứng trong SDK sử dụng.
- Không tự gửi header consistency lạ nếu API không hỗ trợ.
- Không dùng override như cơ chế phân quyền: một read Eventual vẫn phải qua authentication/RBAC.

### Không đánh đổi tính đúng đắn vì tiết kiệm RU nhỏ

Nếu một màn hình hiển thị dữ liệu tài chính hoặc quyền truy cập, hãy ưu tiên cam kết nghiệp vụ. Chỉ nới consistency sau khi đã chứng minh ứng dụng chịu được stale reads và có reconciliation.

## 20. Chọn level cho giỏ hàng

### Yêu cầu

Người dùng thêm hoặc xóa item rồi cần thấy ngay thay đổi trên cùng phiên sử dụng. Các thiết bị khác có thể chấp nhận cập nhật chậm trong thời gian ngắn, nhưng không được tạo đơn hàng hai lần.

### Đề xuất khởi đầu

**Session consistency** là ứng viên tốt:

- Read-your-writes trong phiên của user.
- Thường không cần Strong toàn tài khoản.
- Hợp với read/write theo id và partition key.

### Những việc phải làm ngoài consistency

- Dùng **_etag** để phát hiện hai thiết bị cập nhật cùng giỏ.
- Thiết kế merge semantics khi cùng thêm/xóa item.
- Dùng idempotency key cho thao tác checkout.
- Đảm bảo session token khi request đi qua nhiều backend instances.
- Kiểm tra partition key theo user/tenant và rủi ro hot partitions.

### Câu hỏi kiểm thử

Nếu người dùng thêm A trên điện thoại rồi mở laptop ngay, mức Session trên **hai session độc lập** có chắc laptop thấy A không? **Không được khẳng định có**, nếu token/context không được truyền và các vùng chưa bắt kịp.

## 21. Chọn level cho danh mục sản phẩm

Danh mục sản phẩm được chỉnh sửa vài lần/ngày, hàng triệu lượt đọc. Màn hình chấp nhận thông tin mô tả có thể trễ một chút, nhưng giá thanh toán cuối cùng phải được kiểm tra lại.

### Đề xuất

- **Eventual** hoặc **Consistent Prefix** có thể phù hợp cho read model hiển thị.
- Nếu cùng một user vừa chỉnh sản phẩm ở trang quản trị và cần thấy thay đổi tức thì, **Session** và quản lý token có thể phù hợp.
- Với giá thanh toán, backend phải **xác thực giá ở bước checkout** bằng nguồn dữ liệu/quy tắc nghiệp vụ phù hợp.

### Cache là lớp riêng

Ngay cả khi Cosmos DB trả dữ liệu mới theo Strong, một CDN/API cache giữ sản phẩm trong 5 phút vẫn có thể trả giá cũ. Consistency của database **không điều khiển TTL của Redis/CDN/APIM cache**.

Thiết kế phải xét end-to-end freshness:

~~~text
Cosmos DB consistency
      +
SDK cache/routing
      +
Application cache
      +
CDN/API cache
      +
Mobile offline state
      =
Trải nghiệm dữ liệu người dùng nhìn thấy
~~~

## 22. Chọn level cho dashboard và analytics

Hệ thống ghi telemetry hoặc hoạt động ứng dụng vào Cosmos DB, dashboard cập nhật theo chu kỳ 10–30 giây.

**Eventual** có thể đủ khi:

- Các số liệu không dùng để phê duyệt giao dịch tức thời.
- Có nhãn **last updated at** rõ ràng.
- Sai lệch ngắn hạn có thể được điều chỉnh ở lần tải tiếp theo.

**Consistent Prefix** có thể hữu ích nếu người dùng quan tâm trình tự cập nhật và không muốn thấy sự kiện B trước sự kiện A trong phạm vi lịch sử bảo đảm.

Nếu dashboard dùng dữ liệu từ **Event Hubs → Stream Processor → Cosmos DB**, phần freshness thực tế còn phụ thuộc **consumer lag, checkpoint, batch/aggregation và thời gian ghi**. Nâng consistency Cosmos DB không giúp một consumer Event Hubs đang bị chậm 20 phút.

## 23. Chọn level cho inventory và tài chính

Một nghiệp vụ giữ chỗ hoặc trừ số dư có yêu cầu chặt:

~~~text
stock = 1

Buyer A muốn mua 1
Buyer B muốn mua 1

Nếu cả hai chỉ thực hiện:
  read stock
  if stock > 0: replace stock = stock - 1

Không có kiểm soát concurrency:
  có thể oversell hoặc mất cập nhật.
~~~

### Chọn Strong có đủ không?

**Không.** Strong có thể giúp read freshness trong topology phù hợp, nhưng hai read hợp lệ vẫn có thể cùng nhìn stock=1 trước khi writer đầu commit.

### Cơ chế thực sự cần

1. Conditional update theo **ETag** hoặc transaction phù hợp.
2. Partition/aggregate được thiết kế để bảo vệ invariant.
3. Idempotency key và ledger nghiệp vụ.
4. Retry/compensation khi xung đột.
5. Reconciliation với payment gateway/Service Bus.
6. Kiểm tra độ mới từ các nguồn khác, không chỉ Cosmos DB.

### Khi cân nhắc database khác?

Nếu nghiệp vụ yêu cầu transaction mạnh xuyên nhiều entities/partitions và nhiều hệ thống theo cách khó đáp ứng với Cosmos DB, phải đánh giá lại **data model hoặc loại database**, ví dụ Azure SQL Database hoặc mô hình event sourcing phù hợp, thay vì cố xử lý chỉ bằng consistency setting.

## 24. Tính mới và tính đúng đắn trong kiến trúc event-driven

Một ứng dụng Azure có thể dùng:

~~~text
API -> Service Bus Queue
        |
        v
      Worker
        |
        v
   Cosmos DB item
        |
        v
Change Feed processor
        |
        v
Search index / materialized view
~~~

### Những ranh giới riêng

- Service Bus có message delivery, lock, settlement, retry.
- Cosmos DB có write/read consistency và partition semantics.
- Change Feed có cơ chế quan sát thay đổi theo phạm vi và mode được hỗ trợ.
- Search index có replication/indexing delay riêng.

Nếu người dùng không tìm thấy đơn hàng mới trên search index, nguyên nhân có thể là **Change Feed/consumer lag** chứ không phải Session consistency của Cosmos DB.

### Change Feed không phải consistency level

Change Feed cung cấp cách xử lý thay đổi dữ liệu. Nó **không** biến mọi downstream projection thành Strong, và không tạo global transaction giữa Cosmos DB và một hệ thống khác.

## 25. Các metric cần đo

| Nhóm | Metric/telemetry | Ý nghĩa |
|---|---|---|
| **Request cost** | Request charge (RU) per operation | Chi phí read/write/query |
| **Throughput** | RU/s used, provisioned/autoscale limit | Tải so với năng lực |
| **Throttling** | HTTP 429 và retry-after | Có đang vượt RU budget không? |
| **Read latency** | p50/p95/p99 theo region và consistency | Ảnh hưởng trải nghiệm |
| **Write latency** | p50/p95/p99 theo region | Ảnh hưởng transaction/API |
| **Replication** | Replication lag và các metric vùng được cung cấp | Nhìn khả năng bắt kịp của replicas |
| **Errors** | 412, 404, 403, 408, 429, 5xx | Phân loại concurrency/auth/timeout/quota |
| **Session** | Read-your-writes tests, token propagation issues | Kiểm tra consistency context |
| **Query** | Cross-partition, index metrics, query plan | Tối ưu RU |
| **Partitioning** | Hot partition, skew và per-partition usage | Phát hiện mất cân bằng tải |
| **Business** | Duplicate orders, wrong stock, stale-visible reports | Kết quả nghiệp vụ |

Không phải mọi trường ở bảng là **Azure Monitor metric mặc định có sẵn đúng tên**. Một số như read-your-writes violations hoặc business stale-visible age cần **synthetic tests, SDK diagnostics và application telemetry**.

### Phân biệt 429 và stale read

- **HTTP 429 Too Many Requests:** thường là throttling vì RU/s/capacity; cần nhìn retry-after và SDK retry.
- **HTTP 412 Precondition Failed:** thường do conditional write/ETag không hợp lệ.
- **Stale read:** request có thể trả **200 OK nhưng giá trị cũ** theo consistency đang cho phép.

Không chẩn đoán mọi độ trễ do “Eventual consistency”; có thể là hot partition, 429 retries, network, cache hoặc query chậm.

## 26. Quan sát RU thay vì đoán chi phí

Một thí nghiệm tốt phải cố định:

- Cùng dữ liệu thử và partition key.
- Cùng loại operation (đặc biệt point read so với query).
- Cùng SDK/runtime và client region.
- Cùng thời điểm có tải tương đương.
- Cùng cache/index policy.
- Mức consistency được cấu hình hợp lệ.

### Bảng kết quả lab mẫu

| Operation | Level | RU đọc được | Latency p95 | Nhận xét |
|---|---|---|---|---|
| Point read item nhỏ | Session | **Đo thực tế** | **Đo thực tế** | Baseline |
| Point read cùng item | Strong | **Đo thực tế** | **Đo thực tế** | Chỉ thử nếu account/topology cho phép |
| Query cùng predicate | Session | **Đo thực tế** | **Đo thực tế** | Chú ý cross-partition |
| Query cùng predicate | Eventual | **Đo thực tế** | **Đo thực tế** | Khi request override được hỗ trợ |

Không điền số giả rồi trình bày như benchmark chính thức. Nếu backend có caching hoặc nhiều consumers ở các vùng khác nhau, cần ghi rõ để so sánh công bằng.

### RU capacity là lớp riêng

Cosmos DB có các lựa chọn throughput như provisioned RU/s, autoscale RU/s hoặc serverless capacity theo mô hình dịch vụ/tính năng. **Consistency không đồng nghĩa lựa chọn throughput**. Một account Session với RU/s quá thấp vẫn bị 429 liên tục; Strong không tự ngăn tăng chi phí khi query không tối ưu.

## 27. Azure portal: quan sát consistency của tài khoản

### Bước 1: xác định đúng tài nguyên

1. Đăng nhập Azure portal ở subscription được cấp quyền.
2. Mở Azure Cosmos DB account (API for NoSQL đúng phạm vi bài).
3. Xác định region, các vùng đọc/ghi và trạng thái failover.
4. Xác định tên database/container và partition key của workload.
5. Kiểm tra người chịu trách nhiệm dữ liệu và SLO/RPO/RTO.

### Bước 2: tìm phần consistency

Mở mục **Default consistency** hoặc trang cấu hình tương đương theo giao diện hiện hành. Quan sát level đang dùng và các tham số K/T nếu là Bounded Staleness.

**Chỉ xem cấu hình**, không chọn level mới trên production. Thay đổi account-level consistency có thể ảnh hưởng nhiều ứng dụng/cost/availability.

### Bước 3: xem dữ liệu vận hành

Tại **Metrics** hoặc Azure Monitor:

- Total requests và HTTP status distribution.
- Normalized RU consumption, throttled requests.
- Server-side latency, replication/availability metrics nếu có.
- Throughput/partition distribution.
- Region-specific behavior trong quá trình failover.

Kết hợp với SDK diagnostics và end-to-end request latency ở API. Metrics của Azure Monitor có thể khác hình thức theo tier/API.

## 28. Azure CLI: đọc consistency policy

Các lệnh dưới đây **chỉ đọc** cấu hình Azure. Không tạo account, thay regions hay đổi consistency. Thay thông tin placeholder bằng tài nguyên được phép truy cập.

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az cosmosdb show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<COSMOS_ACCOUNT_NAME>" \
  --query "{name:name,kind:kind,locations:locations,consistencyPolicy:consistencyPolicy}" \
  --output json
~~~

Kết quả có thể chứa:

~~~json
{
  "name": "cosmos-shop-lab",
  "consistencyPolicy": {
    "defaultConsistencyLevel": "Session"
  }
}
~~~

**JSON chỉ là cấu trúc minh họa**. Kết quả thật còn có metadata khác; nếu account Bounded Staleness, API có thể trả các thông số như maxStalenessPrefix/maxIntervalInSeconds.

### Xem SQL database và container

~~~bash
az cosmosdb sql database show \
  --resource-group "<RESOURCE_GROUP>" \
  --account-name "<COSMOS_ACCOUNT_NAME>" \
  --name "<DATABASE_NAME>" \
  --output json

az cosmosdb sql container show \
  --resource-group "<RESOURCE_GROUP>" \
  --account-name "<COSMOS_ACCOUNT_NAME>" \
  --database-name "<DATABASE_NAME>" \
  --name "<CONTAINER_NAME>" \
  --output json
~~~

Đối chiếu partition key path, indexing policy và container settings, không nhầm chúng với consistency level account. Những lệnh trên không đọc dữ liệu item.

### Không dùng lệnh update để “test một chút”

Đổi account consistency hoặc region có thể ảnh hưởng đến tất cả container/ứng dụng dùng tài khoản đó, có ràng buộc tính năng và chi phí. Mọi thay đổi cần change plan, canary/benchmark và rollback được chấp thuận.

## 29. SDK Python: đọc item theo Session consistency

Ví dụ sử dụng **Azure Cosmos DB SDK for Python** với **DefaultAzureCredential**. Mục tiêu là đọc một item có sẵn, không thay dữ liệu. Chỉ chạy trên tài khoản và container **lab** được cấp quyền đọc.

### Chuẩn bị

- Cosmos DB for NoSQL account và container tồn tại.
- Một item test có **id** và **partition key** đã biết.
- Microsoft Entra data-plane role phù hợp, chẳng hạn role đọc dữ liệu được hỗ trợ cho Cosmos DB for NoSQL.
- Network/DNS/Private Endpoint hoạt động.
- Python và thư viện SDK:

~~~bash
python -m pip install azure-cosmos azure-identity
~~~

Biến môi trường mẫu:

~~~bash
export COSMOS_ENDPOINT="https://cosmos-shop-lab.documents.azure.com:443/"
export COSMOS_DATABASE="shop-lab"
export COSMOS_CONTAINER="carts"
export COSMOS_ITEM_ID="cart-demo-001"
export COSMOS_PARTITION_KEY="tenant-demo"
~~~

### Đọc point read

~~~python
import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

endpoint = os.environ["COSMOS_ENDPOINT"]
database_name = os.environ["COSMOS_DATABASE"]
container_name = os.environ["COSMOS_CONTAINER"]
item_id = os.environ["COSMOS_ITEM_ID"]
partition_key = os.environ["COSMOS_PARTITION_KEY"]

credential = DefaultAzureCredential()
client = CosmosClient(endpoint, credential=credential)

try:
    database = client.get_database_client(database_name)
    container = database.get_container_client(container_name)

    item = container.read_item(
        item=item_id,
        partition_key=partition_key,
    )

    # Không ghi toàn bộ dữ liệu khách hàng vào stdout/log.
    print({
        "id": item.get("id"),
        "partitionKey": partition_key,
        "_etag": item.get("_etag"),
    })
finally:
    client.close()
    credential.close()
~~~

**Điểm cần biết:**

1. **read_item** là point read khi có id và partition key, thường tiết kiệm RU hơn query phải tìm item.
2. SDK dùng consistency theo account/client/request theo cấu hình thực tế; đoạn code không chứng minh account đang ở Session nếu chưa kiểm tra account.
3. DefaultAzureCredential không tự cấp quyền; cần role data plane, tenant và account phù hợp.
4. Tái sử dụng CosmosClient trong ứng dụng chạy dài là thực hành tốt; ví dụ đóng client khi kết thúc process lab.
5. Nếu item không tồn tại, SDK có thể trả lỗi 404; lỗi này khác stale-read và cần phân loại.
6. Không dùng mã này để in dữ liệu production hoặc lấy keys/secrets.

### Về session token trong SDK

SDK có cơ chế quản lý session consistency và token theo API/hành vi được hỗ trợ. Ví dụ không cố lấy token qua thuộc tính internal không ổn định. Với ứng dụng stateless cần truyền token giữa services, hãy sử dụng cách được tài liệu SDK hướng dẫn, kèm kiểm thử và kiểm soát bảo mật.

## 30. Lab read-your-writes an toàn

Mục tiêu là quan sát các trường hợp đọc ngay sau ghi ở mức consistency đã chọn. **Thao tác ghi chỉ được thực hiện trong container lab**. Không sửa tài liệu của người dùng thật.

### Dữ liệu mẫu

~~~json
{
  "id": "cart-demo-001",
  "tenantId": "tenant-demo",
  "version": 1,
  "items": ["book"]
}
~~~

Partition key giả định là **/tenantId**; container thực tế phải được tạo đúng partition key ngay từ đầu.

### Quy trình

1. Kiểm tra account default consistency và region từ CLI/portal.
2. Dùng cùng CosmosClient/session, đọc item v1.
3. Ghi item mới v2 chỉ trong lab, bằng conditional update/ETag khi cần.
4. Đọc lại ngay từ cùng client/session.
5. Đọc qua client/process khác không có session token của request trước.
6. Nếu có multi-region, lặp lại từ client đọc ở vùng khác khi được phép.
7. Ghi lại version, _etag, latency, RU và lỗi.
8. Đánh giá kết quả theo cam kết của level; không kết luận vi phạm chỉ vì hai sessions độc lập thấy giá trị khác nhau trong phạm vi level cho phép.

### Bảng nghiệm thu

| Test | Mong đợi |
|---|---|
| Same-session write rồi read với Session | Thỏa read-your-writes khi session context được giữ |
| New process không có token | Không tự khẳng định cùng cam kết session |
| Eventual read sau ghi | Có thể stale trong giai đoạn hội tụ |
| ETag conditional update cạnh tranh | Một update có thể bị 412 khi ETag đã đổi |
| Strong read nếu account hỗ trợ | Thỏa guarantee Strong đã cấu hình |
| RU/latency comparison | Có số liệu thực và cùng điều kiện |

Nếu số lần thử ít không quan sát thấy stale read, **không kết luận Eventual mạnh bằng Strong**. Trong lúc mạng tốt hoặc một vùng duy nhất, replication có thể bắt kịp nhanh hơn tốc độ bạn gửi request.

## 31. Thí nghiệm hai writers và ETag

**Mục tiêu:** chứng minh consistency level không đủ chống lost update.

~~~text
Item v1: { id: "counter", value: 10, _etag: E1 }

Worker A đọc v1/E1
Worker B đọc v1/E1

Worker A muốn tăng value lên 11
Worker B muốn giảm value xuống 9

Nếu cả hai replace vô điều kiện:
  cập nhật sau có thể che cập nhật trước.

Nếu dùng If-Match E1:
  A cập nhật thành công -> E2
  B dùng E1 -> conditional write thất bại
  B phải đọc E2 và tính lại.
~~~

### Các điều kiện thử an toàn

- Chỉ dùng item test không có giá trị nghiệp vụ.
- Ghi lại số lần 412 và số retries.
- Thử hạn mức retry thay vì vòng lặp vô hạn.
- Không tăng concurrency quá RU/s được cấp.
- Kiểm tra log không chứa account keys.

### Câu hỏi

Nếu bạn đổi account từ Session sang Strong, liệu worker B tự biết tăng/giảm trên v2 không? **Không**, logic write của ứng dụng vẫn cần conditional update hoặc transaction phù hợp.

## 32. Những sai lầm phổ biến

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Session nghĩa là tất cả user đọc cùng trạng thái” | Session scope có giới hạn | Read-your-writes của phiên được bảo vệ |
| “Eventual nghĩa là dữ liệu có thể mất mãi mãi” | Không phải bản chất cam kết | Các bản sao hội tụ nếu không còn ghi mới theo điều kiện dịch vụ |
| “Strong bảo đảm không oversell” | Two-step read/write vẫn race | Dùng atomic conditional update/transaction |
| “Consistent Prefix giới hạn trễ tối đa 5 giây” | Không có time bound như Bounded Staleness | Prefix nói về thứ tự |
| “Bounded Staleness không quan tâm K/T” | Bound là phần cốt lõi | Kiểm tra K/T và giới hạn hợp lệ |
| “Cosmos DB luôn mặc định Strong” | Mặc định phổ biến là Session | Kiểm tra account policy thực |
| “SDK tự truyền session qua mọi app instances” | Token/context có thể bị mất | Thiết kế session propagation |
| “Session token dùng để authenticate” | Token phục vụ consistency | Entra ID/RBAC/keys phục vụ auth |
| “Chọn Strong không tốn thêm RU” | Read cost có thể khác | Đo request charge |
| “Eventual luôn nhanh đúng 10 lần” | Không có hằng số chung | Benchmark theo workload |
| “Tăng RU/s giúp read mới hơn” | Capacity khác consistency | Chọn level và token đúng |
| “Nâng consistency giải quyết stale Redis cache” | Cache là lớp khác | Quản lý TTL/invalidation |
| “Multi-write không cần conflict resolution” | Writes cạnh tranh có thể xung đột | Thiết kế chính sách xử lý xung đột |
| “Cosmos DB là SQL transaction xuyên mọi partitions” | Transaction scope có giới hạn | Thiết kế logical partition/batch |
| “Read 200 OK chứng minh dữ liệu mới nhất” | Có thể là stale read hợp lệ | So sánh version/freshness |
| “Một test không thấy stale thì chắc chắn Strong” | Ít tải làm các replica hội tụ nhanh | Đối chiếu guarantees và thử đa vùng |

## 33. Bảo mật, quyền truy cập và mạng

Consistency không phải tính năng bảo vệ dữ liệu trước truy cập trái phép. Hãy thiết kế:

### Identity

- Ưu tiên **Microsoft Entra ID/managed identity** với Azure Cosmos DB for NoSQL khi SDK và service hỗ trợ.
- Cấp quyền **data plane** tối thiểu theo database/container và vai trò.
- Phân biệt Azure RBAC quản lý account với RBAC/role definitions dành cho **data operations**.
- Không lưu account keys trong code, Docker image, repository hoặc CI logs.

### Network

- Khi cần, dùng **Private Endpoint**, firewall, VNet và private DNS.
- Kiểm tra đường egress từ AKS, App Service, Functions hoặc VM tới account Cosmos DB.
- Dùng TLS và SDK version được hỗ trợ.
- Không mở toàn bộ public network chỉ để xử lý 403 hoặc timeout trước khi phân loại lỗi.

### Data protection

- Backup/restore và retention theo API/account/tier.
- Phân vùng tenant đúng; authorization ở ứng dụng vẫn cần thiết.
- Mã hóa theo chính sách dịch vụ và quản lý keys khi cần.
- Không log toàn bộ session token, access token hoặc dữ liệu cá nhân.

**Một item trả về đúng freshness nhưng thuộc tenant khác vẫn là lỗi bảo mật nghiêm trọng**. Consistency không cấp quyền xem dữ liệu.

## 34. Cost và năng lực kiến trúc

Một account Cosmos DB có chi phí liên quan:

- Throughput/provisioned RU/s hoặc autoscale/serverless theo mô hình chọn.
- Storage và index overhead.
- Số regions, replication và các đặc tính availability.
- Backup/restore, retention khi có khoản bổ sung.
- Network, private connectivity hoặc data transfer theo cấu hình.
- Monitoring/Log Analytics.
- Chi phí downstream khi dùng change feed và processors.

### Lựa chọn level ảnh hưởng gì?

Strong/Bounded Staleness có thể tăng RU cho read và tăng latency/giới hạn architecture, nhưng không nên so chi phí bằng số read đơn lẻ. Nếu mức consistency yếu gây nhiều reconciliation, xử lý trùng, hỗ trợ khách hàng hoặc sai dữ liệu, **tổng chi phí nghiệp vụ** có thể cao hơn.

### Ví dụ tổng chi phí theo tình huống

~~~text
Phương án A:
  Strong reads + backend logic đơn giản hơn
  nhưng RU/latency/topology cần kiểm chứng

Phương án B:
  Session reads + session token propagation
  + optimistic concurrency + idempotency

Phương án C:
  Eventual reads + cache/projection
  + reconciliation + monitoring freshness
~~~

Không có phương án luôn rẻ nhất. Hãy chấm điểm **SLO, RU, latency, số vùng, complexity và risk** với workload thật.

## 35. Chẩn đoán lỗi đọc/ghi

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| User vừa lưu nhưng read trả phiên bản cũ | Session token bị mất hoặc đọc ở session/vùng khác | SDK client reuse, token propagation, request path |
| Hai users thấy dữ liệu khác nhau | Consistency cho phép stale reads, caches khác nhau | Account level, vùng, cache, item version |
| 429 tăng khi chuyển Strong | RU demand tăng hoặc capacity chưa đủ | Request charge, RU/s, retries, hot partitions |
| Read latency p99 tăng | Consistency, region routing, 429, query hoặc network | Diagnostics theo vùng và loại operation |
| Update bị 412 | ETag đã thay đổi do ghi đồng thời | Đọc lại, tính lại, retry có giới hạn |
| Kết quả inventory sai dù dùng Strong | Lost update/multi-partition nghiệp vụ chưa atomic | Conditional writes, transaction/ledger |
| SDK đọc qua client mới thấy bản cũ | Session context không duy trì | Session token + topology |
| Dữ liệu dashboard trễ lâu | Change Feed/Event Hubs consumer lag hoặc cache | Downstream pipeline metrics |
| Multi-region write tạo xung đột | Hai vùng cùng sửa item | Conflict resolution và business key |
| Read trả 404 sau write | Sai id/partition key, region/session/cách đọc hoặc item bị xóa | Kiểm tra key, version, TTL, diagnostics |
| Query tốn RU dù dùng Eventual | Query cross-partition, index không phù hợp | Partition key, query plan, index metrics |
| Đổi account policy nhưng client không như mong đợi | Override/SDK session/cache hoặc rollout chưa tương thích | Config thực, SDK options, test controlled |
| API trả 200 nhưng dữ liệu quá cũ | Level chấp nhận stale hoặc lớp cache | Theo dõi staleness đo ở nghiệp vụ |
| 403 khi SDK truy cập | Data plane RBAC chưa đúng hoặc network/auth lỗi | Role assignments, identity, endpoint, TLS |

### Quy trình chẩn đoán theo sáu bước

1. **Account:** đúng subscription, API for NoSQL, default consistency và region configuration chưa?
2. **Operation:** point read hay query; có id/partition key đúng không?
3. **Session:** cùng SDK client/session token hay khác process/instance?
4. **Metrics:** RU, HTTP 429, latency, ETag, request diagnostics và vùng đọc?
5. **Concurrency:** conditional updates, transactions, conflict resolution có đúng không?
6. **Application:** cache, stream processor, auth hoặc business logic có làm dữ liệu sai/trễ không?

Đừng đổi Strong/Session trên production chỉ để sửa một lỗi 404 do **sai partition key**. Xác định đúng lớp nguyên nhân trước.

## 36. Case study: nền tảng bán hàng toàn cầu

Một công ty bán hàng chạy ứng dụng tại ba vùng Azure:

- **Catalog:** hàng triệu lượt xem/ngày, sản phẩm thay đổi mỗi giờ.
- **Cart:** người dùng thêm/xóa item, muốn thấy thay đổi ngay trên cùng phiên.
- **Inventory:** mỗi SKU có số lượng hữu hạn, không được oversell.
- **Orders:** phát message sang Service Bus và cần tránh tạo đơn trùng.
- **Analytics:** dashboard mỗi phút tổng hợp thay đổi từ Change Feed.
- **Data regions:** người dùng ở nhiều châu lục, cần latency thấp và phục hồi khi một vùng gặp sự cố.

### Nhiệm vụ

1. Chọn consistency level ban đầu cho Catalog, Cart, Inventory, Orders và Analytics.
2. Giải thích vì sao Inventory không an toàn chỉ nhờ Strong consistency.
3. Thiết kế ETag/conditional updates cho inventory hoặc mô hình reservation.
4. Đề xuất cách giữ session token khi requests của một user đi qua hai API instances.
5. Giải thích khi nào cần Strong và những giới hạn multi-region write.
6. Nêu cách Bounded Staleness cung cấp giới hạn trễ có định lượng và vì sao phải kiểm tra K/T.
7. Thiết kế partition key phù hợp cart/orders và giới hạn transaction.
8. Đánh giá hai read regions về latency, read RUs và failover.
9. Thiết kế idempotency key cho lệnh đặt đơn và Service Bus worker.
10. Tách lỗi stale Cosmos DB khỏi lỗi Change Feed/analytics projection lag.
11. Xây dựng test ghi/đọc cùng session, cross-instance và cross-region.
12. So sánh chi phí và rủi ro của hai phương án: Session mặc định + conditional writes, hay Strong ở topology hỗ trợ.

### Gợi ý lời giải

| Thành phần | Ứng viên level | Cơ chế bổ sung |
|---|---|---|
| Catalog | Eventual hoặc Session tùy UX | Cache TTL/invalidation, kiểm tra giá ở checkout |
| Cart | Session | Token propagation, ETag khi multi-device |
| Inventory | Session hoặc Strong theo điều kiện | Atomic conditional update/reservation, ledger |
| Orders | Session theo kiến trúc cụ thể | Idempotency, transactional scope, workflow |
| Analytics | Eventual/Consistent Prefix tùy ordering | Change Feed progress và freshness monitoring |

Đây là **gợi ý thiết kế để thảo luận**, không phải bắt buộc có năm Cosmos accounts. Account-level consistency, khả năng override, partitioning và mức nhạy dữ liệu có thể khiến hệ thống chọn tách workload sang nhiều accounts hoặc thay đổi mô hình dữ liệu.

## 37. Bài tập thực hành: chọn mức với yêu cầu định lượng

Ba API có nhu cầu:

**API A — dashboard:** chấp nhận dữ liệu trễ không quá vài chục giây theo SLO ứng dụng, nhưng không phải ràng buộc cơ sở dữ liệu bắt buộc; hiển thị dữ liệu 1 phút/lần.

**API B — profile:** sau thao tác lưu, user phải thấy dữ liệu mới trên session của mình; user khác có thể đợi đồng bộ.

**API C — lịch sử giao dịch:** các lần đọc phục vụ xác nhận nghiệp vụ phải đáp ứng cam kết mới nhất đã commit trong topology được phép, và update phải chống tranh chấp.

### Câu hỏi

1. API A có nhất thiết dùng Bounded Staleness không? Nếu chọn Eventual, làm sao kiểm soát freshness ở ứng dụng?
2. API B có thể dùng Session không? Phải làm gì với API stateless nhiều replicas?
3. API C cần những điều kiện gì để đánh giá Strong?
4. Với API C, có đủ an toàn nếu chỉ bật Strong mà không có ETag/transaction?
5. Khi Bounded Staleness có bound K/T, phải kiểm tra support matrix nào?
6. Làm sao đo RU và p99 trước/sau thay đổi?
7. Nếu một consumer đọc dữ liệu từ Redis cũ, consistency Cosmos DB có giúp gì?

### Gợi ý

**API A** có thể dùng Eventual nhưng cần monitor tuổi dữ liệu/consumer lag và cache freshness. **API B** là ví dụ điển hình của Session kèm token propagation. **API C** cần đánh giá Strong theo topology và chi phí, đồng thời vẫn dùng conditional writes/transaction và kiểm thử invariant.

## 38. Checklist triển khai production

| Nhóm | Điều phải xác minh |
|---|---|
| Đề bài | Freshness và ordering có yêu cầu định lượng hay chỉ yêu cầu cảm nhận? |
| Default policy | Biết consistency level và các tham số thực của account? |
| Topology | Số read/write regions và hạn chế consistency có tương thích? |
| Session | Session token/context có được duy trì xuyên API instances? |
| Partition | Logical partition key phù hợp point read, transaction và throughput? |
| Strong | Có lý do nghiệp vụ và đo được RU/latency/availability? |
| Bounded | K/T hợp lệ, có bằng chứng đáp ứng freshness? |
| Prefix | Có hiểu phạm vi ordering không? |
| Eventual | Có chấp nhận stale reads và thiết kế reconciliation không? |
| Concurrency | ETag/transaction/idempotency bảo vệ các lần ghi tranh chấp? |
| Multi-write | Conflict resolution phù hợp domain và đã thử failover? |
| SDK | Phiên bản, preferred regions, retry và token propagation được thử? |
| Cache | Không nhầm TTL/APIM/Redis với consistency database? |
| Monitoring | Read/write latency, RU, 412, 429, replication và freshness metrics? |
| Security | Entra ID/RBAC, TLS, Private Endpoint và bí mật được bảo vệ? |
| DR | Backup, restore drill, RPO/RTO và region failover được nghiệm thu? |
| Cost | Có so sánh RU, region, storage, monitor và chi phí ứng dụng? |
| Change | Canary, phê duyệt, rollback và documentation đã chuẩn bị? |

## 39. Câu hỏi tự kiểm tra

1. Consistency trong Azure Cosmos DB nói về mối quan hệ nào giữa read và write?
2. Phân biệt stale read với lost update.
3. Kể tên năm consistency levels theo thứ tự từ mạnh tới yếu.
4. Strong consistency đảm bảo điều gì về giá trị đã commit?
5. Bounded Staleness dùng K và T để giới hạn điều gì?
6. Vì sao không mặc định K=5, T=5 hợp lệ cho mọi topology?
7. Session consistency có read-your-writes cho mọi client độc lập không?
8. Session token có tác dụng gì? Có phải credential truy cập dữ liệu không?
9. Vì sao API stateless nhiều replicas có thể mất bảo đảm session mong đợi?
10. Consistent Prefix khác Eventual ở bảo đảm thứ tự nào?
11. Consistent Prefix có giới hạn thời gian stale không?
12. Eventual consistency có nghĩa các bản sao không bao giờ hội tụ không?
13. Nếu Strong đã bật, hai worker có thể tạo lost update khi update vô điều kiện không?
14. ETag/If-Match giải quyết lớp vấn đề nào?
15. HTTP 412 khác 429 trong Cosmos DB ra sao?
16. Transactional batch có scope tới tất cả partitions không?
17. Preferred region có thể cải thiện điều gì và không bảo đảm điều gì?
18. Vì sao multi-region writes cần xử lý xung đột?
19. Có thể nâng từ Eventual account lên Strong chỉ bằng request header không?
20. Vì sao Strong/Bounded Staleness có thể tốn thêm read RUs?
21. Point read khác cross-partition query về RU như thế nào?
22. Tại sao latency chỉ đo một lần là chưa đủ để so consistency?
23. User thêm giỏ hàng rồi đổi API instance cần kiểm thử gì?
24. Vì sao Redis cache có thể trả dữ liệu cũ dù Cosmos DB Strong?
25. Change Feed consumer lag khác replication staleness như thế nào?
26. Eventual có phù hợp tính lượt xem sản phẩm không? Điều kiện nào cần bổ sung?
27. Inventory có 1 món cuối cùng nên bảo vệ bằng cơ chế gì?
28. Vì sao Session consistency thường là điểm cân bằng cho web/mobile?
29. Một dashboard yêu cầu dữ liệu trễ tối đa 30 giây nên đo gì ngoài level?
30. Trong production, bạn sẽ làm gì trước khi đổi account-level consistency?

## Tài liệu tham khảo

- Microsoft Learn — *Consistency levels in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels
- Microsoft Learn — *Strong consistency in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels#strong-consistency
- Microsoft Learn — *Bounded staleness consistency*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels#bounded-staleness-consistency
- Microsoft Learn — *Session consistency*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels#session-consistency
- Microsoft Learn — *Consistency level choices in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels#consistency-levels-and-latency
- Microsoft Learn — *Azure Cosmos DB for NoSQL overview*: https://learn.microsoft.com/azure/cosmos-db/nosql/overview
- Microsoft Learn — *Partitioning and horizontal scaling*: https://learn.microsoft.com/azure/cosmos-db/partitioning-overview
- Microsoft Learn — *Transactional batch in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/nosql/transactional-batch
- Microsoft Learn — *Optimistic concurrency control with ETags*: https://learn.microsoft.com/azure/cosmos-db/nosql/database-transactions-optimistic-concurrency
- Microsoft Learn — *Request Units in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/request-units
- Microsoft Learn — *Monitor Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/monitor
- Microsoft Learn — *Global distribution and multi-region writes*: https://learn.microsoft.com/azure/cosmos-db/distribute-data-globally
- Microsoft Learn — *Azure Cosmos DB Python SDK*: https://learn.microsoft.com/python/api/overview/azure/cosmos-readme

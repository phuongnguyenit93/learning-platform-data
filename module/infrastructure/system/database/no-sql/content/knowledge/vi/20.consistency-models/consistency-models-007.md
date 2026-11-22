# Read-your-writes, monotonic reads và các bảo đảm theo phiên

## 1. Vấn đề thực tế: vừa lưu thành công, tải lại lại thấy dữ liệu cũ

Một ứng dụng sử dụng NoSQL thường có nhiều bản sao dữ liệu để tăng khả năng chịu lỗi và mở rộng khả năng đọc. Một bản ghi có thể được ghi vào node chính, rồi được sao chép đến các replica ở cùng hoặc khác vùng. Các replica không nhất thiết nhận thay đổi tại cùng một thời điểm.

Giả sử người dùng đổi tên hiển thị:

~~~text
09:00:00.000  Người dùng sửa tên "An" thành "An Nguyễn".
09:00:00.020  API cập nhật dữ liệu, trả "Lưu thành công".
09:00:00.050  Trang cá nhân được tải lại từ replica B.
09:00:00.070  Replica B vẫn trả tên "An".
09:00:00.120  Replica B mới nhận được thay đổi.
~~~

Trong mô hình nhất quán cuối cùng (**eventual consistency**), hành vi này có thể xảy ra nếu yêu cầu đọc được định tuyến đến một replica chưa bắt kịp. Nhưng từ góc nhìn người dùng, đây là trải nghiệm khó hiểu: **đã lưu thành công mà chính mình chưa nhìn thấy thay đổi**.

Một vấn đề khác xảy ra khi các lần đọc được gửi tới replica khác nhau:

~~~text
Đọc lần 1 ở replica A: profile.version = 12
Đọc lần 2 ở replica B: profile.version = 10
~~~

Người dùng đã nhìn thấy phiên bản mới rồi lại thấy phiên bản cũ. Ngay cả khi chưa thực hiện thao tác ghi nào, lịch sử quan sát trong phiên đã **đi ngược thời gian**.

Hai yêu cầu phổ biến nhằm hạn chế các hiện tượng này là:

- **Read-your-writes (RYW):** sau khi ghi thành công, chính phiên đó phải đọc thấy tác động của ghi.
- **Monotonic reads (MR):** sau khi phiên đã đọc thấy một trạng thái mới, những lần đọc tiếp theo không được quay lại trạng thái cũ hơn trong thứ tự nhất quán có liên quan.

Chúng là ví dụ của **session guarantees — các bảo đảm theo phiên**, được thiết kế để làm trải nghiệm của từng người dùng nhất quán hơn mà không nhất thiết đòi mọi client trên toàn hệ nhìn thấy trạng thái mới nhất ngay lập tức.

### Mục tiêu bài học

Sau bài, bạn có thể:

1. Mô tả đúng read-your-writes, monotonic reads, monotonic writes và writes-follow-reads.
2. Phân biệt tính nhất quán theo phiên với eventual, causal, linearizable và tính nhất quán giao dịch.
3. Phân tích timeline ghi/đọc qua nhiều replica và phát hiện chỗ vi phạm bảo đảm.
4. Hiểu vì sao sticky routing, session token, watermark và causal metadata có thể giúp duy trì phiên.
5. Thiết kế đường đọc/ghi phù hợp trong MongoDB, Azure Cosmos DB, DynamoDB, Cassandra và Redis.
6. Tránh nhầm version của dữ liệu với timestamp đồng hồ hoặc idempotency key.
7. Xử lý cache, failover, nhiều vùng, nhiều thiết bị, pagination và session hết hạn.
8. Viết kiểm thử và chỉ số giám sát trải nghiệm nhất quán theo phiên trong ứng dụng Java/NoSQL.

---

## 2. Nhắc lại: nhất quán cuối cùng cho phép những điều gì?

Một hệ có primary và các replica:

~~~mermaid
flowchart LR
    U["Người dùng"] --> API["API"]
    API --> P["Primary / Leader"]
    P --> A["Replica A"]
    P --> B["Replica B"]
    P --> C["Replica C"]
    API --> A
    API --> B
    API --> C
~~~

Nếu replication bất đồng bộ, khi primary đã chấp nhận bản cập nhật, một số replica vẫn có trạng thái trước đó.

~~~text
Primary:   version 15
Replica A: version 15
Replica B: version 13
Replica C: version 14
~~~

Một client đọc từ B có thể thấy 13; client đọc từ A thấy 15. Nếu các bản sao cuối cùng nhận được những cập nhật cần thiết và không còn ghi mới, hệ có thể hội tụ về trạng thái tương đương theo quy tắc conflict resolution của nó.

**Eventual consistency không đồng nghĩa dữ liệu luôn sai hoặc đọc tùy tiện.** Nó chỉ không tự cung cấp mọi bảo đảm tức thời giữa các thao tác khi bản sao còn trễ.

### 2.1. Những vấn đề khác nhau

| Hiện tượng | Ví dụ | Bảo đảm liên quan |
|---|---|---|
| Vừa ghi xong nhưng tự đọc thấy bản cũ | Đổi tên thành B, tải lại thấy A | Read-your-writes |
| Đã thấy mới rồi lại thấy cũ | Đọc v12, sau đó đọc v10 | Monotonic reads |
| Hai write của cùng phiên bị đảo thứ tự | Ghi A rồi B nhưng hệ xử lý B trước A | Monotonic writes |
| Write mới không phản ánh dữ liệu vừa đọc | Đọc một bản sửa mới rồi viết phản hồi không có quan hệ nhân quả phù hợp | Writes-follow-reads |
| Hai client cùng sửa, một ghi đè mất người kia | Cùng tăng counter bằng read-modify-write | Atomicity/CAS/transaction, không chỉ RYW |
| Một write được ACK rồi mất sau failover | Primary yếu durability bị rollback | Durability/commit policy, không chỉ session |
| Feed có record mới nhưng tìm kiếm chưa thấy | Search index chưa bắt kịp nguồn | Đường đọc/đồng bộ read model và session barrier |

Các bảo đảm theo phiên tập trung vào **trình tự quan sát của một phiên logic**. Chúng không tự thay thế các ràng buộc đồng thời hoặc điều kiện bảo toàn dữ liệu nghiệp vụ.

### 2.2. “Phiên” là gì?

Trong bài học, **session** là chuỗi thao tác logic của một client/người dùng mà hệ thống theo dõi thứ tự và các phụ thuộc cần thiết.

Một phiên có thể gắn với:

- Một đối tượng session trong database driver.
- Một chuỗi HTTP request dùng session token.
- Một thiết bị hoặc tab trình duyệt.
- Một user trên nhiều thiết bị, **nếu hệ thống chủ động chia sẻ context giữa chúng**.
- Một tác vụ backend có nhiều bước đọc/ghi theo thứ tự.

Không được mặc định “cùng tài khoản người dùng” nghĩa mọi tab, điện thoại và microservice tự chia sẻ session guarantees. Phạm vi của phiên phải được định nghĩa trong kiến trúc.

---

## 3. Định nghĩa chính xác read-your-writes (RYW)

**Read-your-writes** bảo đảm: sau khi một phiên đã thực hiện một write được coi là hoàn tất theo hợp đồng, những lần đọc sau đó của chính phiên phải phản ánh write ấy hoặc một trạng thái kế tiếp hợp lệ; không được phục vụ một bản cũ chưa biết write đó.

Ví dụ:

~~~text
Trạng thái đầu: profile.name = "An"  (version 5)

Session S:
  W(name = "An Nguyễn")          -> success, version 6
  R(profile)                     -> phải có version >= 6
~~~

Nếu read trả version 5, RYW bị vi phạm.

### 3.1. Sơ đồ vi phạm

~~~mermaid
sequenceDiagram
    participant S as Session S
    participant P as Primary
    participant R as Replica chậm

    S->>P: W(name=B)
    P-->>S: ACK version 6
    S->>R: R(profile)
    R-->>S: name=A, version 5
    Note over S,R: Vi phạm read-your-writes
    P-->>R: Replicate version 6
~~~

### 3.2. RYW không có nghĩa mọi client thấy ngay

Giả sử:

~~~text
Session S1: W(profile=v6), sau đó R(profile) -> v6
Session S2: R(profile) -> v5 trong một khoảng ngắn
~~~

Nếu contract chỉ hứa RYW cho S1 và eventual visibility cho S2, tình huống trên không nhất thiết vi phạm contract.

**RYW là bảo đảm theo phiên**, không phải mặc định là global strong consistency.

### 3.3. RYW không có nghĩa phải đọc lại đúng byte đã ghi

Giả sử session S ghi version 6. Sau đó một client khác hợp lệ ghi version 7. S đọc version 7. Điều này có thể hoàn toàn hợp lệ vì version 7 là trạng thái mới hơn, có chứa/được xác lập sau chuỗi cập nhật tương ứng.

Cần phân biệt:

- **Trạng thái đã ghi hoặc mới hơn trong thứ tự được công nhận:** có thể hợp lệ.
- **Trạng thái cũ thiếu write đã hoàn tất của chính phiên:** không hợp lệ đối với RYW.

Trong hệ có conflict resolution, version 7 có thể ghi đè một số field của version 6. Do đó RYW không có nghĩa giá trị field của phiên sẽ tồn tại mãi mãi bất chấp các write hợp lệ khác. Bảo đảm phải được hiểu theo thứ tự/version và semantics cập nhật.

### 3.4. Một write chưa xác định kết quả

Nếu client gặp timeout thay vì ACK, không thể tự suy ra write đã commit. RYW thường được diễn giải với các write đã hoàn tất thành công theo hợp đồng, còn request có kết quả **UNKNOWN** phải được đối soát hoặc thử lại idempotent.

Không nên “sửa” RYW bằng cách tự trả dữ liệu mà client vừa nhập khi DB chưa xác nhận trạng thái nguồn, rồi khẳng định ghi đã bền.

---

## 4. Định nghĩa chính xác monotonic reads (MR)

**Monotonic reads** bảo đảm rằng khi một phiên đã nhìn thấy một trạng thái/version, những lần đọc tiếp theo không được trả về một trạng thái **cũ hơn** trong thứ tự nhất quán liên quan.

Ví dụ:

~~~text
Session S:
  R(order) from replica A -> version 12
  R(order) from replica B -> version 10   X
~~~

Lần đọc thứ hai đã đi lùi từ 12 xuống 10: vi phạm monotonic reads.

### 4.1. Timeline

~~~mermaid
sequenceDiagram
    participant S as Session S
    participant A as Replica A
    participant B as Replica B

    S->>A: Read order
    A-->>S: version 12
    S->>B: Read order
    B-->>S: version 10
    Note over S,B: Monotonic reads bị vi phạm
~~~

### 4.2. “Monotonic” không phải giá trị số cứ tăng

Nếu một ứng dụng hiển thị số dư:

~~~text
balance = 1.000.000, version 20
balance =   900.000, version 21
~~~

Version 21 **mới hơn** version 20 mặc dù giá trị số dư nhỏ hơn. Monotonic reads nói về **thứ tự trạng thái được quan sát**, không phải trường nghiệp vụ có giá trị tăng dần.

Tương tự, nếu một Order chuyển từ `PAID` sang `REFUNDED`, phiên phải được phép thấy trạng thái `REFUNDED` mới hơn, dù “trạng thái đơn” không có quan hệ lớn-bé theo tên.

### 4.3. Monotonic reads không tự yêu cầu bản mới nhất toàn hệ

~~~text
Latest committed version trên primary: 15
Session trước đó mới thấy version:   12
Replica đang phục vụ:               13
~~~

Đọc version 13 có thể thỏa MR vì không đi lùi so với 12, dù chưa là version 15.

Đây là điểm khác với một bảo đảm mạnh như linearizable read, trong đó yêu cầu tôn trọng thứ tự thời gian thực theo định nghĩa của mô hình.

### 4.4. Nhiều bản ghi và các phiên bản không so sánh được

Trong hệ phân tán có các write đồng thời, không phải mọi version đều có thứ tự số tuyến tính toàn cục. Có thể có hai trạng thái đồng thời không có quan hệ “cái nào mới hơn” đơn giản.

Đối với một đối tượng có thứ tự version đáng tin, một `version >= seenVersion` có thể hữu ích. Với nhiều partition/key hoặc nhiều writer đồng thời, cần metadata như **causal history, vector clock hoặc token do DBMS quản lý**; chỉ so timestamp hay số version của hai đối tượng khác nhau thường không đủ.

### 4.5. Monotonic reads và delete

Nếu phiên đã đọc thấy một tombstone/record deleted ở version 12, lần đọc sau từ replica chậm không nên “làm sống lại” document ở version 10.

Vì vậy trạng thái xóa cũng cần nằm trong thứ tự version/causal context. TTL xóa vật lý một record hoặc cache evict chưa tự bảo đảm MR.

---

## 5. Hai bảo đảm còn lại: monotonic writes và writes-follow-reads

Bộ session guarantees thường được giới thiệu với bốn thuộc tính:

| Bảo đảm | Ký hiệu | Nội dung |
|---|---|---|
| Read-your-writes | RYW | Phiên đọc thấy những write đã hoàn tất của chính nó |
| Monotonic reads | MR | Phiên không quay lại trạng thái cũ hơn những gì đã đọc |
| Monotonic writes | MW | Các write của cùng phiên được áp dụng theo đúng thứ tự phiên |
| Writes-follow-reads | WFR | Write tiếp theo của phiên được sắp sau những write mà phiên đã quan sát qua read |

Hai thuộc tính đầu nói nhiều về **những lần đọc**; hai thuộc tính sau giúp duy trì **thứ tự nhân quả của write**.

### 5.1. Monotonic writes (MW)

Ví dụ người dùng sửa cùng một profile hai lần:

~~~text
Session S:
  W1: displayName = "An N."
  W2: displayName = "An Nguyễn"
~~~

Nếu W2 được áp dụng trước W1 ở một replica, kết quả cuối có thể quay lại tên cũ.

MW yêu cầu các write từ S được xử lý theo thứ tự logic phù hợp: **W1 trước W2**, không đảo ngược thứ tự của chính phiên.

MW không có nghĩa một phiên có thể ghi tùy ý cùng lúc mà hệ tự đoán đúng ý định. Khi có hai request concurrent không có quan hệ thứ tự rõ, ứng dụng cần định nghĩa cách sắp xếp/đồng bộ.

### 5.2. Writes-follow-reads (WFR)

Giả sử người dùng đọc một bài đăng version 9 rồi viết bình luận nói về nội dung đó:

~~~text
S:
  R(post) -> version 9
  W(comment = "Tôi đồng ý với thay đổi trên")
~~~

WFR yêu cầu write tạo comment được đặt **sau trong thứ tự nhân quả** so với trạng thái post đã được đọc. Một replica không nên áp dụng comment mà chưa có những phụ thuộc causal cần thiết rồi coi lịch sử đó độc lập hoàn toàn.

Bảo đảm này quan trọng với:

- Bình luận/phản hồi dựa trên nội dung vừa đọc.
- Workflow sau khi đọc trạng thái phê duyệt.
- Cập nhật quan hệ phụ thuộc giữa nhiều document.
- Tác vụ tiếp theo dựa trên một config hoặc quyền đã đọc.
- Hệ thống cộng tác nhiều bước trên các replica.

### 5.3. RYW khác WFR

- **RYW:** Tôi ghi A rồi tôi đọc A; phải thấy việc tôi vừa ghi.
- **WFR:** Tôi đọc A do người khác ghi rồi tôi ghi B; B phải được đặt sau các phụ thuộc đã quan sát từ A.

Một hệ có RYW tốt nhưng bỏ qua WFR vẫn có thể tạo causal anomaly giữa nhiều đối tượng.

### 5.4. Vì sao phải xét cả bốn?

Một session thường thực hiện chuỗi:

~~~text
Read profile
Update profile
Read profile
Read post
Write comment
Read comment
~~~

Chỉ giải quyết một lần read-after-write là chưa đủ nếu các write khác trong cùng phiên bị đảo thứ tự hoặc write mới không tôn trọng dữ liệu vừa đọc.

**Bộ bốn session guarantees giúp duy trì tính mạch lạc của phiên trong hệ phân tán**, nhưng không tự đảm bảo linearizability/serializability cho mọi client, mọi key và mọi transaction. Mức causal consistency toàn hệ còn phụ thuộc cách hệ quản lý và phổ biến các quan hệ nhân quả giữa các phiên.

---

## 6. Mối quan hệ với causal consistency

**Causal consistency** cố gắng bảo đảm những thao tác có quan hệ nguyên nhân–kết quả được quan sát theo thứ tự tương thích với quan hệ đó. Những thao tác độc lập/concurrent có thể không có một thứ tự chung duy nhất.

Quan hệ *happens-before* có thể gồm:

1. Các thao tác tuần tự trong một session.
2. Một thao tác ghi được quan sát bởi một thao tác đọc.
3. Một thao tác mới xảy ra sau thao tác đọc đó.
4. Tính bắc cầu của các quan hệ trên.

Ví dụ:

~~~text
A: đăng bài P
B: đọc bài P
B: viết bình luận C về P
C: đọc bình luận C
~~~

Nếu hệ biểu diễn quan hệ nhân quả đầy đủ, C không nên thấy bình luận phụ thuộc bài P trong một trạng thái mà P vẫn chưa được nhìn nhận theo quy tắc causal của hệ.

### 6.1. Causal không đồng nghĩa mọi thao tác có thứ tự tổng

Hai người dùng độc lập viết hai bình luận cùng lúc. Không nhất thiết phải có một thứ tự toàn cục duy nhất cho hai comment nếu chúng không có phụ thuộc. Causal consistency bảo vệ **phụ thuộc thực sự**, không nhất thiết ép mọi write concurrent vào cùng trình tự được mọi node quan sát ngay.

### 6.2. Session guarantees là góc nhìn theo phiên

Một session có thể yêu cầu RYW/MR/MW/WFR trong khi những session khác vẫn thấy dữ liệu khác thời điểm. Để hỗ trợ causal consistency liên client, hệ cần mang **causal context** từ một phiên sang những thao tác phụ thuộc và bảo vệ khi thay phiên, thay process hoặc truyền dữ liệu tới dịch vụ khác.

### 6.3. Không tự suy ra transaction isolation

Causal consistency không tự giải quyết:

- Hai client cùng trừ tồn kho cuối.
- Lost update khi đọc–sửa–ghi một document.
- Write skew giữa hai record.
- Ràng buộc uniqueness.
- Giao dịch nhiều document cần all-or-nothing.
- Đòi hỏi linearizable compare-and-set.

Các bài toán này có thể cần **atomic conditional write, CAS, transaction và bất biến nghiệp vụ**.

---

## 7. So sánh các mô hình nhất quán qua một bảng

| Mô hình/bảo đảm | Ví dụ yêu cầu | Không nhất thiết cung cấp |
|---|---|---|
| Eventual consistency | Cuối cùng replica hội tụ nếu không còn thay đổi | RYW/MR tức thời nếu không có cơ chế thêm |
| Read-your-writes | Sau khi lưu, chính phiên không đọc bản trước write | Client khác thấy ngay |
| Monotonic reads | Phiên đã thấy v12 không đọc v10 về sau | Luôn đọc bản mới nhất toàn hệ |
| Monotonic writes | Write thứ hai không được áp dụng trước write thứ nhất của phiên | Transaction nhiều bản ghi |
| Writes-follow-reads | Write mới tôn trọng dữ liệu mà phiên đã đọc | Thứ tự toàn cục cho write concurrent |
| Causal consistency | Các phụ thuộc nhân quả được giữ đúng khi quan sát | Mọi thao tác có một total order thời gian thực |
| Linearizability | Thao tác trông như có hiệu lực tại một thời điểm giữa invocation và response | Atomicity của transaction nhiều key nếu DB chỉ linearizable từng key |
| Serializability | Transaction tương đương một lịch chạy tuần tự | Thứ tự thời gian thực nếu không yêu cầu strict serializability |
| Strong read theo một khóa | Đọc dữ liệu mới nhất theo contract cụ thể của dịch vụ | Causal consistency xuyên nhiều key/region mặc định |

Không có một thứ tự đơn giản rằng mọi mục trong bảng tạo thành **một thang mạnh–yếu tuyến tính duy nhất**; các mô hình tập trung vào những quan hệ khác nhau. Đặc biệt, serializability và linearizability cần phân biệt **phạm vi đối tượng/transaction**.

### 7.1. Ba câu hỏi kiểm tra một giải pháp

Khi ai đó nói “hệ này hỗ trợ session consistency”, hãy hỏi:

1. **Phạm vi:** một key, partition, collection, region hay nhiều dịch vụ?
2. **Điều kiện:** phải dùng session SDK/token, read/write concern hay cùng một client instance không?
3. **Lỗi:** nếu replica không bắt kịp, request chờ, forward, retry hay thất bại?

Không trả lời được ba câu hỏi thì chưa thể đánh giá một bảo đảm trong kiến trúc thực tế.

---

## 8. Session context: làm sao hệ nhớ đã đọc và ghi đến đâu?

Một hệ cần biết **phiên đã quan sát hoặc tạo ra những phiên bản nào** để không phục vụ dữ liệu cũ hơn.

Mô hình khái niệm:

~~~json
{
  "sessionId": "s-42",
  "minimumVisibleVersions": {
    "profile:user-42": 12,
    "order:order-9001": 7
  },
  "lastWriteSequence": 1842
}
~~~

Đây là **minh họa về metadata logic**, không phải schema token chung có thể dùng với mọi DBMS.

Trong hệ thật, context có thể được biểu diễn bằng:

- Commit sequence number hoặc log sequence number.
- Logical clock / hybrid logical clock.
- Vector clock hoặc vector timestamp.
- Version token theo partition.
- Cluster time / operation time.
- Opaque session token do cơ sở dữ liệu hoặc SDK tạo ra.
- Cursor hoặc watermark của replication stream theo phạm vi.

### 8.1. Read barrier

Một session đã thấy version 12 của record X. Khi request đi tới replica B, replica có version 10.

Hệ có ba lựa chọn hợp lệ nếu muốn giữ MR:

1. **Chờ** B bắt kịp tối thiểu 12.
2. **Chuyển** request sang replica khác có trạng thái phù hợp.
3. **Báo không thể đáp ứng trong timeout**, để client retry hoặc xử lý lỗi.

Đọc và trả version 10 không đáp ứng MR.

### 8.2. Write barrier

Session vừa đọc version 12 ở một key, rồi write một record khác phụ thuộc vào nó. Hệ có thể cần đính kèm **causal context** cho write và bảo đảm nơi apply write đã có các phụ thuộc liên quan.

Một `minVersion=12` chỉ đúng khi biết version thuộc **đối tượng/chuỗi phiên bản nào**. Không được so số 12 của bảng Profile với số 12 của bảng Orders như thể chúng là một global sequence.

### 8.3. Metadata có thể là vector, không phải một số

Nếu phiên thao tác qua hai partition:

~~~text
Partition P: observed version 31
Partition Q: observed version 14
~~~

Một watermark đơn lẻ chỉ có ý nghĩa nếu DBMS cung cấp một thứ tự global tương thích. Nếu không, hệ có thể cần vector causal hoặc token opaque quản lý nhiều partition.

### 8.4. Timestamp đồng hồ không mặc nhiên là version causal

Hai node có thể có clock skew. Client đặt `Date.now()` hoặc `System.currentTimeMillis()` vào header rồi yêu cầu replica “đọc >= timestamp này” không tạo ra một consistency protocol đáng tin nếu các timestamp không liên kết với commit order của engine.

Với last-write-wins dựa trên timestamp, giá trị timestamp và causal ordering cũng không nhất thiết trùng nhau. Hãy dùng metadata được DBMS định nghĩa, không tự phát minh một khóa thời gian làm session token.

---

## 9. Các chiến lược triển khai bảo đảm theo phiên

### 9.1. Đọc/ghi trên cùng primary hoặc leader

Một cách thực dụng là cho session:

~~~text
WRITE -> primary A
READ  -> primary A
~~~

Nếu primary tiếp tục giữ write đã được commit và đường đọc đảm bảo nhìn thấy state cập nhật, RYW có thể được đáp ứng dễ hơn so với đọc từ replica bất đồng bộ.

Ưu điểm: đơn giản về routing.

Đánh đổi:

- Primary chịu thêm read load.
- Latency tăng với client ở xa.
- Không tự bảo vệ khi failover làm rollback write chưa committed.
- Không tự tạo causal session cho nhiều partition/dịch vụ.
- Cần hiểu mức read/write consistency thực tế của DBMS.

### 9.2. Sticky session / replica affinity

Định tuyến các request trong phiên tới cùng một replica có thể giúp tránh đọc mới–cũ khi replica này tiến triển tuần tự.

Nhưng:

- Nếu write đi primary A còn sticky read vào replica B đang chậm, RYW vẫn có thể thất bại.
- Khi replica B bị thay thế, phiên có thể đọc sang C cũ hơn nếu không giữ watermark.
- Một replica có thể phải resync/rollback sau sự cố.
- Load balancer sticky cookie không biết causal dependencies.

**Sticky routing là một tối ưu vận hành, không tự là bằng chứng đầy đủ của session consistency.**

### 9.3. Session token

Một response ghi/đọc có thể trả token biểu diễn mốc đã quan sát. Client gửi token trong request tiếp theo:

~~~text
POST /profiles/me
  -> ACK, Session-Consistency: opaque-token-T12

GET /profiles/me
  Session-Consistency: opaque-token-T12
  -> Chờ/route đến nơi >= T12
~~~

Đây là **API minh họa do ứng dụng tự thiết kế**, không phải tên header tiêu chuẩn của mọi DBMS.

Lợi ích:

- Phiên có thể di chuyển qua nhiều API server.
- Load balancer không bắt buộc ghim vào một máy.
- Có thể giữ ranh giới causal giữa các request khi token được truyền đúng.

Rủi ro:

- Token mất khi redirect, tab mới, request đến microservice khác.
- Token chỉ hợp lệ cho một partition/region hoặc thời hạn nhất định.
- Client không được giả mạo token làm vượt quyền.
- Token có thể chứa metadata nhạy cảm.
- Nếu replica chưa bắt kịp, request có thể chờ lâu hoặc timeout.

### 9.4. Đọc mạnh cho các request nhạy cảm

Một số hệ cho phép đọc từ nguồn có strong consistency trên base table/key. API có thể dùng đường đọc này ngay sau write, thay vì từ index/replica eventual.

Điều này thường dễ hơn tự triển khai causal token nếu nhu cầu chỉ là “đọc lại một item ngay sau khi lưu”. Nhưng không giải quyết tất cả trường hợp multi-key, cross-region hoặc search index.

### 9.5. Client-side overlay / optimistic UI

Sau khi API trả ACK, frontend có thể tạm hiển thị dữ liệu vừa ghi từ state local, trong lúc replica chưa bắt kịp.

Đây là **giải pháp trải nghiệm người dùng**, không tự là bảo đảm nhất quán của database. Nếu source write chưa commit hoặc bị rollback, client có thể hiển thị trạng thái không có thật.

Với dữ liệu quan trọng, cần phân biệt:

- `PENDING` — thao tác chưa được xác nhận.
- `SAVED` — nguồn đã xác nhận theo contract.
- `SYNCING` — read model/replica còn chưa theo kịp.
- `FAILED` hoặc `UNKNOWN` — cần xử lý lỗi/đối soát.

### 9.6. Cơ chế lai

Một hệ có thể:

- Dùng session token để ưu tiên replica gần nhất.
- Nếu chưa đủ watermark, chờ ngắn.
- Nếu quá chậm, chuyển sang primary hoặc trả lỗi rõ.
- Dùng cache overlay tạm để tránh UI nhảy lùi.
- Chỉ dùng strong read cho luồng thanh toán/cấp phát, read eventual cho feed.

Phương án phải được chọn theo **SLO latency, correctness và cost**.

---

## 10. Java: mô hình hóa session watermark ở tầng ứng dụng

Đối với một API tự xây cơ chế session version, có thể hình dung:

~~~java
public record SessionWatermark(
    String scope,
    long minimumVersion
) {}

public record VersionedProfile(
    String userId,
    String displayName,
    long version
) {}
~~~

Một interface khái niệm:

~~~java
public interface VersionedProfileStore {
    VersionedProfile update(
        String userId,
        String newName,
        String requestId
    );

    VersionedProfile readAtLeast(
        String userId,
        long minimumVersion
    );
}
~~~

`readAtLeast` ở đây là **API giả định**, không phải hàm sẵn có trong các Java driver NoSQL.

### 10.1. Luồng giữ watermark

~~~java
VersionedProfile saved = store.update(
    "user-42",
    "An Nguyễn",
    "update-profile-9001"
);

// Từ thời điểm đã biết version 12, phiên không được
// đọc về version 11 hay 10 trong phạm vi bảo đảm.
long minVersion = saved.version();

VersionedProfile visible = store.readAtLeast(
    "user-42",
    minVersion
);
~~~

Một implementation đúng phải chờ, route hoặc trả lỗi khi nơi đọc không đủ version. Nó không được đọc version 10 rồi tự sửa `visible.version = 12` trong response mà không có nội dung tương ứng.

### 10.2. Cập nhật watermark sau mỗi lần đọc

Nếu phiên đọc được version 15 ở một request sau, watermark phải tiến lên:

~~~java
long nextMinimum = Math.max(minVersion, visible.version());
~~~

`Math.max` chỉ hợp lý khi version có thứ tự tăng **cho cùng một scope** và không có nhánh concurrent không so sánh được. Không dùng cách này để cộng/trộn version của nhiều key độc lập.

### 10.3. Quy tắc khi replica không theo kịp

Pseudocode:

~~~java
ReadResult readWithSession(
    ResourceKey key,
    ConsistencyContext context,
    Duration timeout
) {
    // 1. Xác định phạm vi và phiên bản tối thiểu.
    // 2. Chọn replica có thể đáp ứng, hoặc chờ replication.
    // 3. Nếu đọc được state đúng watermark -> trả dữ liệu.
    // 4. Nếu hết timeout -> fallback có kiểm soát
    //    hoặc báo cannot_satisfy_consistency.
    // 5. Không trả state cũ hơn rồi gắn token mới.
    throw new UnsupportedOperationException("Illustrative API");
}
~~~

Không nên triển khai chính xác session consistency tự chế nếu DBMS/SDK đã có cơ chế session token và causality đáng tin; hãy ưu tiên đúng hợp đồng sản phẩm.

---

## 11. MongoDB: causally consistent sessions

MongoDB hỗ trợ session trong driver; một session cấu hình **causally consistent** có thể cung cấp những bảo đảm theo phiên khi tuân thủ các điều kiện của MongoDB.

### 11.1. Điều kiện quan trọng

Để những bảo đảm causal được cung cấp đúng như tài liệu của MongoDB, thông thường cần:

- Sử dụng một **client session** có `causallyConsistent = true`.
- Các read trong session dùng **read concern `majority`**.
- Các write trong session dùng **write concern `majority`**.
- Các thao tác trong session được thực hiện **tuần tự theo thứ tự logic**, không dùng chung một session cho những thao tác concurrent không kiểm soát.
- Hạ tầng/driver/server hỗ trợ tính năng và các semantics tương ứng.

Nếu bỏ qua read/write concern phù hợp, chỉ đặt tên biến `session` chưa đủ để suy ra toàn bộ causal guarantees.

### 11.2. Java MongoDB driver

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public final class ProfileExample {

    public void updateThenRead(MongoClient mongoClient) {
        MongoDatabase database = mongoClient.getDatabase("app");

        MongoCollection<Document> profiles = database
            .getCollection("profiles")
            .withReadConcern(ReadConcern.MAJORITY)
            .withWriteConcern(WriteConcern.MAJORITY);

        ClientSessionOptions options = ClientSessionOptions
            .builder()
            .causallyConsistent(true)
            .build();

        try (ClientSession session = mongoClient.startSession(options)) {
            profiles.updateOne(
                session,
                Filters.eq("_id", "user-42"),
                Updates.set("displayName", "An Nguyễn")
            );

            Document profile = profiles
                .find(session, Filters.eq("_id", "user-42"))
                .first();

            System.out.println(profile);
        }
    }
}
~~~

Đoạn mã nhằm minh họa **cùng một session và mức concern phù hợp**. Trong ứng dụng thật cần xử lý timeout, write failure, record không tồn tại, retryable writes và vòng đời session.

Đây không phải transaction nhiều document. Causal session bảo vệ thứ tự quan sát theo contract của MongoDB, nhưng **không tự biến hai update độc lập thành một transaction atomic**.

### 11.3. Thao tác phải tuần tự

Sai về ý tưởng:

~~~text
Cùng một ClientSession
  Task A: update profile
  Task B: read profile đồng thời
```

Nếu read và write chưa có quan hệ thứ tự thực sự, không thể đòi session đoán request nào phải nhìn thấy request nào. MongoDB sessions cũng có các giới hạn về thread-safety/concurrent use; ứng dụng cần tuân thủ hướng dẫn driver.

Đúng hơn:

~~~text
Await update acknowledgement
    ->
Read trong session với causal context đã được cập nhật
```

### 11.4. Causal session và read preference

Khi đọc qua replica phù hợp, causal metadata có thể khiến server đợi cho tới khi dữ liệu cần thiết xuất hiện thay vì trả snapshot quá cũ, tùy cơ chế DBMS. Nhưng chọn `secondary` không có nghĩa replica lúc nào cũng đáp ứng ngay.

Cần giám sát latency và timeout khi replica lag; không biến session guarantee thành lời hứa “đọc ở secondary luôn nhanh hơn”.

### 11.5. Session và transaction không giống nhau

| Causal session | Multi-document transaction |
|---|---|
| Theo dõi thứ tự/quan hệ nhân quả qua thao tác | Nhóm thao tác thành đơn vị commit/abort |
| Có thể có nhiều thao tác đọc/ghi tuần tự | Có phạm vi transaction và hạn chế cụ thể |
| Không tự bảo đảm thay đổi nhiều document cùng atomic | Có atomicity theo contract của MongoDB |
| Không tự chống lost update mọi tình huống | Có thể cần CAS/unique constraint tùy invariant |
| Giúp RYW/MR/MW/WFR khi đáp ứng điều kiện | Giải quyết một lớp bài toán consistency khác |

---

## 12. Azure Cosmos DB: session consistency và session token

Azure Cosmos DB là một ví dụ tiêu biểu về **Session consistency** như một consistency level của dịch vụ.

Theo mô hình này, một client session có thể được cung cấp các bảo đảm như:

- Read-your-writes.
- Monotonic reads.
- Monotonic writes.
- Writes-follow-reads.

Trong khi đó, các client/phiên khác có thể quan sát thay đổi với độ trễ theo hợp đồng, chứ không phải mọi người thấy write của một phiên tức thời.

### 12.1. Session token

SDK có thể quản lý một **session token** phản ánh tiến độ mà client đã quan sát. Token được dùng trong các request sau để yêu cầu mốc nhất quán phù hợp.

Ví dụ logic:

~~~text
Client A:
  Write profile -> receive token T12
  Read profile with T12 -> read version >= required state

Client B:
  No token from A
  Read profile -> may temporarily observe older state
~~~

Đây là mô hình khái niệm, không phải cú pháp header/SDK cụ thể.

### 12.2. Mở ứng dụng ở thiết bị khác

Người dùng lưu profile trên điện thoại, rồi mở laptop ngay. Hai thiết bị không mặc định chia sẻ session token.

Để yêu cầu trải nghiệm RYW xuyên thiết bị, hệ có thể:

- Chuyển consistency context qua backend/đường đăng nhập được kiểm soát.
- Dùng một read path mạnh hơn nếu dịch vụ hỗ trợ và hợp đồng yêu cầu.
- Chờ replica liên quan bắt kịp.
- Dùng API authoritative cho trường hợp cần nhìn ngay.

Không sao chép token tùy tiện qua các user/tenant. Token phục vụ consistency, **không phải chứng chỉ phân quyền**.

### 12.3. Phạm vi partition

Session tokens và mốc đọc có phạm vi theo cơ chế partition/replication của dịch vụ. Không giả định một số nguyên token có thể so sánh toàn bộ collections/containers/partitions.

Với query xuyên partition, cần hiểu SDK xử lý consistency context ra sao và có những giới hạn gì. Một ứng dụng tự truyền lại token bằng tay phải tuân thủ định dạng và phạm vi dịch vụ, không tự tách số version từ token opaque.

### 12.4. Client SDK và vòng đời

SDK có thể tự quản lý token khi dùng một client instance dài hạn. Khi tạo lại client cho mỗi HTTP request, hoặc khi request đi qua nhiều server không chia sẻ session context, cần xác minh liệu session guarantee mong muốn có còn được duy trì không.

Điểm thực tế: **tái sử dụng client đúng cách và quản lý token** có thể là yếu tố tính đúng đắn, không chỉ tối ưu kết nối.

### 12.5. Khi replica chưa đáp ứng token

Một read đòi mốc session mà replica chưa có không nên trả bản cũ rồi báo thành công nếu contract yêu cầu RYW/MR. Tùy SDK/dịch vụ, đường đọc có thể chờ, retry, định tuyến lại hoặc thất bại. Phải đo latency và xử lý lỗi này trong API.

---

## 13. DynamoDB: base-table strong read khác GSI eventual read

DynamoDB cho phép chọn **strongly consistent read** cho những kiểu đọc được hỗ trợ trên base table và local secondary index, trong những phạm vi dịch vụ tương ứng. Global Secondary Index (GSI) có **eventually consistent reads**.

### 13.1. Một vấn đề thực tế

~~~text
T0: PutItem thành công trên Orders base table.
T1: API Query GSI status=CREATED.
T2: GSI chưa nhận update, trả danh sách rỗng.
T3: GSI bắt kịp, item xuất hiện.
~~~

Nếu client vừa tạo Order rồi muốn xem ngay đơn vừa tạo, đọc từ GSI có thể vi phạm kỳ vọng RYW ở cấp ứng dụng.

### 13.2. Đọc trực tiếp từ base table

Ví dụ AWS SDK JavaScript v3:

~~~javascript
import { GetCommand } from "@aws-sdk/lib-dynamodb";

const result = await documentClient.send(new GetCommand({
  TableName: "Orders",
  Key: { orderId: "order-9001" },
  ConsistentRead: true
}));

console.log(result.Item);
~~~

`ConsistentRead: true` có ngữ nghĩa strong read trên các đường đọc mà DynamoDB hỗ trợ. Điều kiện là write đã hoàn tất thành công, đọc trong phạm vi/Region phù hợp và không có một write hợp lệ khác thay đổi trạng thái.

Nếu đã có `orderId`, một `GetItem` strong read thường là đường đọc phù hợp hơn việc query một GSI eventual chỉ để kiểm tra record vừa tạo.

### 13.3. Không áp `ConsistentRead: true` vào GSI

Đọc GSI không hỗ trợ strong consistency giống base table. Truy vấn GSI với yêu cầu strong read không phải cách sửa độ trễ replication của GSI.

Các chiến lược thay thế:

- Sau create, trả ngay Order từ kết quả write đã được xác nhận.
- Read-after-write theo khóa base table với strong read.
- Dùng read model nhưng chờ nó có version tương ứng.
- Thiết kế UX thông báo indexing đang cập nhật nếu nghiệp vụ cho phép.
- Chọn schema primary key phục vụ những access pattern cần consistency mạnh.

### 13.4. Global tables và multi-region

Khi dữ liệu được nhân bản đa region, các chế độ global table có semantics riêng. Một strong read trong Region A không mặc nhiên cho toàn bộ những bảo đảm mong muốn đối với một request ở Region B nếu replication giữa regions chưa đồng bộ theo cấu hình.

Vì thế một read-after-write xuyên region cần được phân tích theo **chế độ multi-region cụ thể**. Không suy ra “strong read” một vùng tức là linearizable global mọi vùng.

### 13.5. Không có session token ứng dụng chung chỉ vì có strong read

DynamoDB có các mức read consistency theo API, nhưng không tự cung cấp một “token causal xuyên GSI, cache, search và mọi Region” thay cho thiết kế ứng dụng.

Nếu workflow có nhiều read models, cần định nghĩa version/consistency barrier hoặc thực hiện bước xác nhận từ nguồn.

---

## 14. Cassandra: quorum overlap chưa phải causal session hoàn chỉnh

Cassandra thường phục vụ đọc/ghi qua coordinator với **consistency level (CL)** như `ONE`, `LOCAL_QUORUM`, `QUORUM`, `ALL`.

### 14.1. Khi đọc từ một replica

Giả sử RF=3:

~~~text
Replica A: version 8
Replica B: version 7
Replica C: version 6
~~~

Phiên ghi version 8 được một replica xác nhận, sau đó đọc CL `ONE` từ B có thể thấy version 7. Nếu contract ứng dụng yêu cầu RYW, đây là một rủi ro cần xử lý.

### 14.2. Quorum read và write

Trong những giả định phù hợp, với \(RF=3\), chọn \(W=2\) và \(R=2\) cho các tập replica giao nhau:

\[
R+W>RF.
\]

Điều này giúp làm giảm rủi ro đọc dữ liệu cũ dưới cơ chế đọc/repair và conflict resolution phù hợp. Nhưng không nên khẳng định chỉ từ công thức mà có **đầy đủ RYW/MR/MW/WFR trên mọi partition, datacenter và failure scenario**.

### 14.3. Những giới hạn thực tế

- Cassandra sử dụng timestamp/version và quy tắc conflict resolution đặc thù.
- `LOCAL_QUORUM` xét trong datacenter theo cấu hình, không phải toàn bộ các DC.
- Read/write ở datacenter khác có thể thấy replication lag.
- Một write có thể thất bại hoặc timeout nhưng vẫn được một số replica áp dụng.
- Các thao tác trên nhiều partition không tự là transaction serializable.
- Đọc qua bảng materialized/read model khác có thể thêm độ trễ.
- Nhiều request từ cùng client phải được sắp thứ tự thực sự nếu muốn MW/WFR.

### 14.4. Session guarantee ở tầng ứng dụng

Nếu hệ muốn RYW/MR xuyên nhiều vùng hoặc read model, có thể:

1. Ghi nhận version/causal context khi write thành công.
2. Truyền context trong phiên.
3. Yêu cầu đường đọc chỉ trả bản đáp ứng mốc đã biết.
4. Chờ hoặc chuyển sang đường đọc phù hợp khi replica chưa theo kịp.
5. Giới hạn timeout, tránh vòng retry vô hạn.
6. Đối soát kết quả unknown sau write timeout.

Đây là thiết kế thêm, không mặc định do việc đặt `QUORUM` ở mọi request mang lại.

---

## 15. Redis: primary đọc nhanh, replica có thể stale

Redis thường có một primary nhận write và replica theo sau bất đồng bộ tùy topology/cấu hình.

### 15.1. Một ví dụ vi phạm RYW

~~~text
Client:
  SET profile:42 "An Nguyễn" -> ACK ở primary
  GET profile:42 -> load balancer chọn replica chậm
  Result: "An"
~~~

Nếu mọi read của session đi primary đang giữ cập nhật và không có failover làm mất write, kỳ vọng RYW có thể dễ đáp ứng hơn. Nhưng replica lag tạo rủi ro nếu read route tùy tiện.

### 15.2. `WAIT` không đồng nghĩa causal consistency toàn hệ

Redis có lệnh `WAIT` giúp chờ một số replica xác nhận đã nhận những write liên quan theo semantics lệnh. Nhưng:

- Chờ replica nhận dữ liệu không tự tạo fsync trên replica.
- Không tự bảo đảm các service khác như MongoDB/search/cache đều theo kịp.
- Không tự làm mọi client đọc từ mọi replica có RYW.
- Không xóa rủi ro failover/rollback theo topology và persistence.

### 15.3. Persistence khác session guarantees

AOF/RDB giúp một số kiểu phục hồi sau crash, nhưng không tự ngăn đọc một replica stale. Ngược lại, đọc từ primary mới nhất trong memory không tự chứng minh dữ liệu đã bền khi mất điện.

**Visibility và durability là hai khía cạnh phải xem riêng.**

### 15.4. Khi Redis chỉ là cache

Ứng dụng có thể giữ source of truth trong một DB bền, còn Redis cache phục vụ read. Sau write:

- Invalidate cache liên quan.
- Cập nhật hoặc version cache entry theo protocol.
- Tránh stale cache entry ghi đè dữ liệu mới.
- Với RYW quan trọng, đọc nguồn hoặc yêu cầu cache tối thiểu version đã thấy.

Cache invalidation chạy bất đồng bộ có thể tạo RYW violation ở cấp API dù database nguồn hỗ trợ RYW tốt.

---

## 16. Session guarantees xuyên API gateway, cache và microservice

Một ứng dụng lớn có nhiều tầng:

~~~mermaid
flowchart LR
    User["Người dùng"] --> Gateway["API Gateway"]
    Gateway --> Profile["Profile Service"]
    Gateway --> Feed["Feed Service"]
    Profile --> Source["Document DB nguồn"]
    Profile --> Cache["Redis cache"]
    Source --> Stream["CDC / Outbox"]
    Stream --> Search["Search index"]
    Feed --> Search
~~~

Giả sử người dùng đổi tên:

1. Profile Service ghi thành công vào DB nguồn.
2. Response trả “Đã lưu”.
3. Feed Service đọc một read model/search chưa cập nhật.
4. Feed hiển thị tên cũ.

**Session guarantee của DB nguồn không tự đi xuyên CDC, cache và search.**

### 16.1. Muốn RYW ở cấp sản phẩm phải theo dõi điểm đọc thật

Cần xác định API nào có thể trả dữ liệu từ:

- Primary.
- Secondary.
- Cache.
- Search/index.
- Data warehouse.
- Materialized view.
- CDN hoặc application memory.

Một màn hình gồm năm thành phần có thể đọc từ năm nguồn với độ trễ khác nhau. “Cùng user session” không tự ép tất cả nguồn thống nhất.

### 16.2. Version trong event/read model

Một cách thiết kế:

~~~json
{
  "userId": "user-42",
  "profileVersion": 18,
  "displayName": "An Nguyễn"
}
~~~

Nếu CDC event update profile mang `profileVersion=18`, search index có thể lưu version đó. Đường đọc cho session có watermark 18 biết rằng một index result version 16 chưa đủ.

Nhưng một read model nhiều field cần version/causal semantics phù hợp: không nên dùng một số version tùy tiện để diễn tả tất cả quan hệ xuyên bảng.

### 16.3. Read fallback khi view chưa theo kịp

Ví dụ:

~~~text
GET /me
  desiredProfileVersion = 18

Read cache:
  cacheVersion = 16 -> không đáp ứng

Read authoritative DB:
  version = 18 -> trả kết quả
~~~

Điều này giúp RYW nhưng tăng tải nguồn. Cần ngân sách fallback và số lần retry; không để mọi request tại peak traffic vô tình quay về primary và làm nó quá tải.

### 16.4. Bảo mật token/session context

Nếu dùng header session token:

- Xác thực user/tenant trước khi áp dụng.
- Không coi token là authorization.
- Không dùng token của user A để đọc dữ liệu của user B.
- Hạn chế replay ngoài phạm vi.
- Cân nhắc ký/mã hóa nếu token do ứng dụng tự quản lý.
- Không log token chứa metadata nhạy cảm.
- Đặt giới hạn kích thước, lifetime và schema version.
- Tránh để client tùy ý tăng `minimumVersion` thành một giá trị không thể đạt, gây từ chối dịch vụ qua các request chờ.

Tốt nhất dùng opaque token do DBMS/SDK đã định nghĩa khi sản phẩm hỗ trợ.

---

## 17. Session kéo dài bao lâu và kết thúc như thế nào?

### 17.1. Một HTTP request không tự là cả session người dùng

Nếu mỗi request tạo một DB client/session mới rồi bỏ đi, session context có thể mất giữa các lượt:

~~~text
Request 1: write -> DB session A (đóng)
Request 2: read  -> DB session B (không biết A đã thấy gì)
~~~

Điều này có thể làm RYW/MR bị mất ở cấp sản phẩm, tùy DBMS/SDK và đường đọc.

### 17.2. Trình duyệt có nhiều tab

Hai tab có thể chia sẻ login cookie nhưng không chia sẻ causal watermark. Tab 1 đã thấy version 18, tab 2 vẫn đọc version 16.

Nếu yêu cầu monotonic reads **trên toàn user trong cùng trình duyệt**, cần cơ chế chia sẻ context phù hợp, hoặc dùng đường đọc mạnh. Nếu mỗi tab là một session độc lập, có thể chấp nhận khác biệt tạm thời nhưng phải nói rõ.

### 17.3. Đổi thiết bị

Người dùng sửa profile trên điện thoại rồi mở laptop. Để có RYW xuyên thiết bị, hai bên cần có context được truyền hoặc chọn đường đọc đáp ứng mức nhìn thấy đã được ghi nhận ở server.

Một token cục bộ trong điện thoại không tự xuất hiện trên laptop.

### 17.4. Phiên có thể bị mất khi service restart

Nếu session watermark chỉ nằm trong RAM của API instance, khi rolling deployment hoặc failover, request tiếp theo có thể chuyển sang server khác không biết mốc. Cần:

- Token mang theo request.
- Shared session store với durability/consistency phù hợp.
- Đường đọc mạnh khi cần.
- Hoặc hợp đồng nói rõ session scope bị giới hạn bởi lifecycle tương ứng.

### 17.5. Hết hạn token

Session token có thể hết hạn hoặc không còn hợp lệ sau topology/schema/partition changes tùy dịch vụ. Phải có hành vi được định nghĩa: lấy context mới có kiểm soát, fallback tới nguồn strong hoặc trả lỗi có thể retry; **không được âm thầm trả dữ liệu cũ hơn và vẫn tuyên bố đảm bảo MR**.

---

## 18. Monotonic reads trong thực tế: cache, paging và deletion

### 18.1. Cache trả version cũ hơn

~~~text
10:00:00  DB trả version 20
10:00:01  Request tiếp theo hit Redis cache version 18
~~~

Nếu cả hai cùng một session với MR, đường đọc thứ hai phải từ chối kết quả cache cũ hoặc tìm nơi có tối thiểu version 20.

### 18.2. Pagination không tự được ổn định bởi MR

Một feed phân trang:

~~~text
Page 1: 20 sự kiện mới nhất
Page 2: 20 sự kiện tiếp theo
~~~

Monotonic reads giúp tránh quay về replica cũ hơn, **nhưng không tự tạo một snapshot bất biến** cho cả hai trang.

Nếu item mới được thêm giữa hai request hoặc sort key thay đổi, offset pagination có thể trùng/bỏ sót. Để có snapshot ổn định, cần snapshot read/consistent cursor hoặc watermark theo nghiệp vụ phù hợp, ngoài MR.

### 18.3. Delete và tombstone

Một phiên đã thấy record được xóa ở version 22. Sau đó một replica stale trả record ở version 20: đây có thể là hiện tượng “resurrection” trái MR.

Cần quản lý delete marker/tombstone và version tương ứng. Xóa vật lý sớm hoặc mất metadata delete có thể khiến giải pháp tự chế không phân biệt được “chưa từng tồn tại” với “đã bị xóa”.

### 18.4. Dữ liệu tổng hợp

Nếu dashboard hiển thị tổng doanh thu ngày hôm nay từ materialized view, phiên đã thấy total version 40 rồi một request khác thấy version 37, điều đó có thể vi phạm MR theo contract. Nhưng không nên suy từ giá trị doanh thu tăng/giảm: tổng tiền có thể giảm hợp lệ sau refund.

**Mốc version/causal order**, không phải hướng thay đổi số tiền, mới là cơ sở.

---

## 19. Read-your-writes không ngăn lost update

Giả sử tồn kho có `available=1`.

Hai client:

~~~text
Client A: đọc 1
Client B: đọc 1
Client A: set available=0, tạo reservation A
Client B: set available=0, tạo reservation B
~~~

Mỗi client có thể đọc thấy chính write của mình, tức RYW, nhưng hệ vẫn tạo **hai reservation cho một đơn vị**.

Lỗi là **check-then-act không nguyên tử**. Cần:

- Conditional update: chỉ trừ nếu còn đủ.
- CAS/version để phát hiện thay đổi concurrent.
- Transaction bảo vệ counter và reservation record.
- Thiết kế invariant và retry phù hợp.

### 19.1. Ví dụ MongoDB conditional update

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "sku-42",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1, held: 1 }
  }
);

if (result.modifiedCount !== 1) {
  // Không đủ hàng hoặc resource không tồn tại.
}
~~~

Điều kiện và update trên cùng document là một thao tác nguyên tử theo semantics MongoDB. Nhưng nếu phải tạo reservation document riêng, vẫn cần transaction hoặc giao thức recovery thích hợp.

### 19.2. RYW không tự chống write skew

Hai nhân viên đọc một ràng buộc toàn hệ rồi cập nhật hai record khác nhau; dù mỗi người nhìn thấy write của mình, ràng buộc có thể bị phá nếu không có transaction isolation phù hợp.

**Session consistency giải quyết một lớp bất thường quan sát, không phải mọi bất biến dữ liệu.**

---

## 20. Durability và failover: đã nhìn thấy chưa chắc đã sống sót

Một tình huống:

~~~text
T0: Primary A nhận write version 12.
T1: A ACK nhưng write chưa đạt commit/durability policy mạnh.
T2: Session đọc từ A -> thấy version 12.
T3: A bị mất, replica B trở thành leader với version 11.
~~~

Nếu write 12 không thuộc lịch sử được commit và bị rollback, hệ không thể đơn giản “đợi B bắt kịp version 12” vì version đó có thể không bao giờ tồn tại trong lịch sử mới.

### 20.1. Các bảo đảm phải được ghép đúng

Muốn RYW/MR đáng tin qua failover, cần:

1. Ghi được ACK theo **durability/replication commitment** phù hợp.
2. Session context ghi nhận những write/read đã hoàn tất.
3. Failover protocol giữ những write đã committed theo contract.
4. Đường đọc sau failover tiếp tục áp dụng session watermark/causal context.
5. Nếu không thể đáp ứng, phải báo lỗi hoặc reconcile thay vì trả trạng thái sai.

### 20.2. Unknown write outcome

Client có thể timeout khi write đã commit hoặc chưa. Nếu retry với ID mới, có thể tạo duplicate; nếu đọc replica stale, có thể kết luận nhầm chưa ghi.

Dùng **idempotency key/conditional write** và đọc nguồn với consistency phù hợp để xác minh outcome.

### 20.3. Session token không phải chứng nhận durability

Một token nói “phiên đã thấy version X” không tự đảm bảo version X chống được mất node/region. Điều kiện durability phải đến từ DBMS và cấu hình ACK độc lập.

---

## 21. Multi-region: người dùng di chuyển giữa các vùng

Ví dụ một nền tảng có Region A ở châu Á và Region B ở châu Âu. Người dùng ghi ở A, rồi request đọc bị chuyển sang B.

~~~text
Region A: version 30
Region B: version 28
Session watermark: version 30
~~~

Nếu muốn RYW, B không nên phục vụ version 28 cho phiên đã ghi 30. Các lựa chọn:

- Route phiên về A.
- Chờ B bắt kịp đến mốc cần.
- Dùng dịch vụ/read mode hỗ trợ consistency mạnh hơn theo contract.
- Trả lỗi hoặc retry sau nếu không thể đáp ứng.

### 21.1. Độ trễ và tính sẵn sàng

Nếu mạng liên vùng bị phân vùng:

- Đọc tại B ngay lập tức có thể trả stale.
- Chờ B bắt kịp có thể treo đến timeout.
- Route về A có thể không khả dụng.
- Từ chối read tạm thời giúp giữ MR/RYW nhưng giảm availability.

Đây là đánh đổi thiết kế có chủ đích, không phải lỗi có thể xóa bằng một dòng cấu hình chung.

### 21.2. Cạnh tranh ghi nhiều vùng

Nếu cả A và B nhận write concurrent tới cùng key, conflict resolution có thể tạo những trạng thái không có thứ tự version đơn giản. Session consistency cần được hiểu theo semantics multi-master và policy giải quyết conflict của dịch vụ.

Không nên lấy đồng hồ vật lý của vùng A/B làm total order nhân quả cho mọi thao tác khi không có giao thức phù hợp.

### 21.3. Vùng của một token

Một session token có thể chỉ có hiệu lực theo partition hoặc trong một scope của dịch vụ. Khi đổi region, SDK hoặc ứng dụng phải xử lý token theo tài liệu chính thức, không tự giả định mọi region chấp nhận mọi token trong mọi chế độ.

---

## 22. API contract: khi nào trả `SAVED` và khi nào trả `PENDING`?

Một API cập nhật profile có thể biểu diễn:

~~~http
PATCH /me/profile
Content-Type: application/json
Idempotency-Key: profile-update-9001

{
  "displayName": "An Nguyễn"
}
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Session-Consistency: opaque-scope-version

{
  "userId": "user-42",
  "displayName": "An Nguyễn",
  "sourceVersion": 18,
  "status": "SAVED"
}
~~~

Tên `Session-Consistency` là **header ứng dụng minh họa**, không phải header chuẩn hoặc API có sẵn của mọi database.

### 22.1. Ba trạng thái cần tách

- **Accepted/PENDING:** đã nhận yêu cầu nhưng chưa biết commit thành công.
- **SAVED:** nguồn đã xác nhận theo write/durability contract.
- **VISIBLE:** đường đọc được dùng trong phiên đã đáp ứng watermark mong muốn.

Nhiều sản phẩm gộp `SAVED` và `VISIBLE` nếu đọc từ nguồn mạnh. Khi dùng read model bất đồng bộ, nên có thông tin/UX rõ ràng hơn.

### 22.2. GET mang theo consistency context

~~~http
GET /me/profile
Session-Consistency: opaque-scope-version
~~~

Nếu replica chỉ có version 16 nhưng token yêu cầu 18, backend có thể chờ, redirect nội bộ tới nguồn hoặc trả lỗi theo hợp đồng. Không nên trả version 16 và coi request thành công nếu đã hứa RYW/MR.

### 22.3. Tách `Idempotency-Key` và session token

Hai metadata có mục đích khác nhau:

| Metadata | Mục đích |
|---|---|
| `Idempotency-Key` | Nhận diện cùng ý định write khi retry |
| `Session-Consistency` | Ghi nhận mức dữ liệu đã quan sát/ghi để chặn read lùi |
| `ETag` / version | Conditional update, phát hiện thay đổi |
| Correlation/trace ID | Theo dõi request qua hệ thống |

Không dùng session token làm uniqueness key và không dùng ETag của một resource làm causal context toàn hệ nếu không có giao thức hỗ trợ.

---

## 23. Kiểm thử read-your-writes và monotonic reads

Chỉ đo trung bình latency không phát hiện đủ session anomalies. Cần ghi lại **lịch sử thao tác** cùng request/session ID và version nhận được.

### 23.1. Test RYW

1. Tạo một key mới và phiên S.
2. S ghi giá trị/version v1.
3. Chỉ khi write được xác nhận thành công, S đọc lại cùng key qua đường API production.
4. Bảo đảm read không trả trạng thái trước v1 theo order hợp lệ.
5. Lặp nhiều lần với load balancer/replica/caches.
6. Thử sau reconnect hoặc đổi API instance nếu session scope bao gồm tình huống đó.

Pseudocode:

~~~java
String sessionId = "session-42";

WriteResult write = api.updateProfile(
    sessionId, "user-42", "An Nguyễn"
);

if (write.success()) {
    Profile read = api.getProfile(sessionId, "user-42");

    assertTrue(
        read.version() >= write.committedVersion()
    );
}
~~~

Đây là mã khái niệm. So sánh số chỉ hợp lệ nếu `version` trong cùng scope có thứ tự tin cậy và read API có contract đó.

### 23.2. Test MR

1. S đọc một key và ghi lại version quan sát.
2. Lặp request qua các replica/caches.
3. Mỗi lần read phải trả trạng thái không cũ hơn đã thấy.
4. Cập nhật watermark của phiên.
5. Thử một replica đang trễ hoặc bị thay thế.

Pseudocode:

~~~java
long observed = -1;

for (int i = 0; i < 100; i++) {
    VersionedProfile profile = api.readProfile(sessionId);
    assertTrue(profile.version() >= observed);
    observed = profile.version();
}
~~~

Với hệ có các version concurrent hoặc order không tuyến tính, cần kiểm tra **causal relation** thay vì dùng `>=` số nguyên.

### 23.3. Test MW

Một phiên tuần tự gửi:

~~~text
W1(value=A)
await ACK
W2(value=B)
await ACK
```

Đo trên những đường đọc/replica có contract liên quan để phát hiện việc một trạng thái cũ được áp dụng sau trạng thái mới khi cả hai là write của cùng phiên.

### 23.4. Test WFR

Một phiên đọc document P version 9, rồi tạo document Q phụ thuộc version 9. Hệ phải đảm bảo causal context đi theo write Q và cách đọc Q không tạo lịch sử vi phạm phụ thuộc P theo contract.

Một test chỉ nhìn giá trị cuối có thể bỏ qua lỗi thứ tự; nên ghi event history và dependencies.

### 23.5. Test khi có failover

Trong môi trường thử nghiệm được phép:

- Ghi version X có ACK.
- Chuyển đọc từ primary sang secondary.
- Thực hiện failover có kiểm soát.
- Tiếp tục phiên với context trước đó.
- Xác định có read lùi hoặc mất committed write không.
- Ghi policy ACK/durability và mốc replication.

Không chủ động gây lỗi trên production nếu không có quy trình chấp thuận, dữ liệu thử và khả năng rollback.

### 23.6. Test nhiều vùng

Ghi ở Region A, đọc ở Region B cùng session context. Khi B chưa bắt kịp, kiểm tra backend:

- Chờ/route/fallback đúng.
- Không trả state cũ hơn token.
- Có timeout hợp lý.
- Không nhầm lag là không tồn tại record.

---

## 24. Theo dõi những chỉ số nào?

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| RYW | Số lần read trả version trước acknowledged write | Vi phạm trải nghiệm sau lưu |
| MR | Số lần phiên quan sát version lùi | Lỗi routing/cache/session |
| Token | Tỷ lệ request thiếu hoặc token không hợp lệ | Session context bị rơi |
| Replica | Replication lag p95/p99 | Khả năng đáp ứng watermark |
| Wait | Thời gian chờ read barrier | Chi phí session consistency |
| Fallback | Tỷ lệ read chuyển về primary | Tải bổ sung và rủi ro overload |
| Timeout | Read không đáp ứng min version trước deadline | SLO/availability trade-off |
| Cache | Cache entry stale so với token | Cache invalidation lỗi/chậm |
| Read model | Index lag và version gap | Đồng bộ view |
| Failover | Số request có unknown write outcome | Retry/reconciliation |
| Multi-region | Cross-region propagation lag | Trải nghiệm khi đổi vùng |
| UX | Số lần “lưu xong mà vẫn thấy cũ” | Kết nối kỹ thuật với sản phẩm |

### 24.1. Không log dữ liệu nhạy cảm chỉ để kiểm tra version

Nên log session identifier đã được giảm nhạy cảm, resource scope, version/token metadata ở dạng phù hợp và trace ID. Tránh log nguyên profile, payment payload hoặc session token chứa thông tin nhạy cảm.

### 24.2. Lấy mẫu không thay thế kiểm tra bất biến

Metric tổng hợp giúp phát hiện trend, nhưng có thể bỏ sót lỗi hiếm. Những API quan trọng có thể cần assertion hoặc sampling có mốc causal để điều tra read-after-write anomaly.

### 24.3. Đặt ngân sách latency

Nếu yêu cầu RYW buộc chờ replica, phải xác định:

~~~text
maxWaitForConsistency = ngân sách do sản phẩm quy định
fallbackToPrimary = có/không
onTimeout = retryable error / fallback / pending
```

Không cho phép request chờ vô hạn. Nhưng cũng không âm thầm phá guarantee bằng cách trả dữ liệu cũ hơn.

---

## 25. Quy trình quyết định khi thiết kế một màn hình

Một checklist để chọn mức nhất quán:

1. **Có thao tác ghi ngay trước thao tác đọc không?** Nếu có, RYW có quan trọng không?
2. **Màn hình có đổi giữa nhiều data source/replica không?** Nếu có, MR cần được xét.
3. **Có write phụ thuộc read vừa thấy không?** Nếu có, WFR/causal context quan trọng.
4. **Một phiên thực hiện nhiều write tuần tự không?** Nếu có, MW và order của request cần rõ.
5. **Có nhiều thiết bị hay vùng địa lý không?** Cần session context đi theo cách nào?
6. **Có read model bất đồng bộ không?** Cần source fallback hay wait watermark?
7. **Có transaction/invariant không?** Dùng CAS/transaction riêng; session guarantee chưa đủ.
8. **Nếu failover xảy ra, write đã ACK có còn tồn tại không?** Xét durability độc lập.
9. **Nếu nơi đọc chưa bắt kịp, hệ làm gì?** Wait, reroute, timeout hay giao diện pending?
10. **Có đo được vi phạm và latency bổ sung không?** Đặt metric và thử nghiệm.

### 25.1. Bảng lựa chọn tham khảo

| Tình huống | Nhu cầu chính | Hướng thiết kế |
|---|---|---|
| Người dùng vừa sửa profile | RYW | Đọc nguồn mạnh hoặc causal session/token |
| Người dùng cuộn feed qua replica | MR, pagination | Session watermark + cursor/snapshot khi cần |
| Người dùng sửa cùng ghi chú hai lần | MW | Sắp thứ tự writes và version |
| Bình luận sau khi đọc bài | WFR / causal | Truyền causal context hoặc ghi theo protocol |
| Hai người giữ một vé cuối | Invariant/concurrency | Atomic conditional update/transaction |
| Search ngay sau khi publish | RYW ở cấp sản phẩm | Wait search watermark hoặc fallback nguồn |
| Dashboard eventual | Có thể chấp nhận stale | Read model/cache với SLO freshness |
| Đơn hàng ngay sau thanh toán | Strong correctness + durability | Đọc nguồn, transaction, idempotency |
| Đổi region sau write | RYW xuyên vùng | Reroute, wait replica hoặc contract mạnh |
| Khôi phục sau failover | Durability + session continuity | Commit policy, token, reconciliation |

**Không áp dụng giải pháp mạnh nhất cho mọi request nếu sản phẩm không yêu cầu**, vì latency, availability và chi phí có thể tăng mà không đem lại giá trị.

---

## 26. Bài tập 1: phát hiện vi phạm RYW và MR

Một hệ có các trạng thái:

~~~text
Primary:   version 15
Replica A: version 14
Replica B: version 12
```

Session S:

~~~text
1. Write(version 15) -> ACK theo policy.
2. Read từ Replica A -> version 14.
3. Read từ Primary   -> version 15.
4. Read từ Replica B -> version 12.
```

Trả lời:

1. Bước 2 có vi phạm RYW không? Vì sao?
2. Bước 3 có đáp ứng RYW không?
3. Bước 4 có vi phạm MR không?
4. Nếu replica A/B chưa theo kịp, API có những lựa chọn nào ngoài việc trả stale?
5. Nếu ACK ở bước 1 không đủ durability và version 15 bị rollback khi failover, session token có đủ cứu dữ liệu không?

**Gợi ý:** sau khi chính phiên ghi 15 và nhận ACK, đọc 14 là không đủ cho RYW. Đã thấy 15 rồi đọc 12 là vi phạm MR. Session token chỉ diễn tả mốc đã thấy, không biến write chưa bền thành durable.

## 27. Bài tập 2: phân biệt bốn session guarantees

Hãy gán từng lịch sử cho bảo đảm phù hợp:

**Lịch sử A**

~~~text
S: W(profile=v7) -> ACK
S: R(profile) -> v6
```

**Lịch sử B**

~~~text
S: R(order) -> v10
S: R(order) -> v8
```

**Lịch sử C**

~~~text
S: W(note="Draft")
S: W(note="Final")
Replica apply "Final" trước rồi "Draft" sau
```

**Lịch sử D**

~~~text
S: R(post P version 9)
S: W(comment C nói về nội dung version 9)
Một bản sao expose C mà chưa thỏa phụ thuộc P9
```

Đáp án tham khảo:

- A: read-your-writes.
- B: monotonic reads.
- C: monotonic writes.
- D: writes-follow-reads / causal dependency.

Giải thích vì sao RYW tốt không tự giải quyết trường hợp C hoặc D.

## 28. Bài tập 3: thiết kế API sau khi đổi profile

Yêu cầu:

- Ứng dụng có nhiều Java API instances sau load balancer.
- Nguồn là MongoDB replica set.
- Profile read có thể đi secondary.
- Người dùng muốn tải lại ngay và luôn thấy tên vừa lưu.
- Người dùng có thể chuyển request giữa hai API instances.

Hãy đề xuất:

1. Session MongoDB cần cấu hình như thế nào?
2. Read concern và write concern nào liên quan?
3. Nếu DB session không kéo dài qua HTTP requests, context được truyền thế nào hoặc chọn read path nào?
4. Khi secondary còn lag, xử lý wait/route/timeout ra sao?
5. Vì sao cache có thể phá RYW dù MongoDB session đúng?
6. Nếu người dùng cập nhật profile hai lần liên tục, thứ tự write được giữ thế nào?
7. Nếu write timeout, API có được trả `SAVED` ngay không?

**Gợi ý:** Causal session với điều kiện majority phù hợp là một lựa chọn. Nếu app không chia sẻ session context qua HTTP, cân nhắc đọc primary/strong path hoặc cơ chế token do DBMS hỗ trợ. Đường cache phải được xét riêng.

## 29. Bài tập 4: DynamoDB GSI và thông báo “đã tạo”

Một API ghi Order:

~~~text
PutItem(Order) -> ACK
GET /orders?status=CREATED -> Query GSI -> []
```

Hãy trả lời:

1. Vì sao GSI có thể chưa có Order?
2. `ConsistentRead: true` có áp dụng cho GSI không?
3. Nếu biết `orderId`, đường đọc nào phù hợp hơn để RYW?
4. Nếu danh sách phải hiển thị Order mới ngay, có thể dùng cơ chế watermark/overlay/fallback nào?
5. Làm sao phân biệt “chưa index xong” với “Order không tồn tại”?
6. Vì sao một cache có thể tạo thêm trạng thái stale?

## 30. Bài tập 5: causal comments

Một mạng xã hội có:

~~~text
User A: W(post P version 7)
User B: R(P version 7)
User B: W(comment C)
User C: R(comment C)
```

Hãy vẽ một sơ đồ nhân quả và xác định:

- Những thao tác nào có quan hệ happens-before?
- WFR đòi hỏi gì ở write comment?
- Nếu post và comment ở các partition khác nhau, một version số trên mỗi partition có đủ không?
- Nếu User C chuyển region, làm sao bảo vệ causal dependency?
- Nếu hai user cùng bình luận độc lập, có bắt buộc một thứ tự toàn cục duy nhất không?

**Gợi ý:** Đường A ghi P → B đọc P → B ghi C tạo phụ thuộc. Hai comment độc lập có thể concurrent. Causal metadata phải biểu diễn được phạm vi phụ thuộc chứ không chỉ là timestamp client.

## 31. Bài tập 6: thiết kế test harness và báo cáo

Một hệ có ba replica được chọn ngẫu nhiên để đọc. Hãy xây test harness:

~~~text
Test RYW:
  write key with stable ID and version
  wait for ACK
  read through production routing
  assert returned state is not older

Test MR:
  read repeatedly in one session
  update observed watermark
  assert subsequent reads do not go backwards

Test failover:
  retain session context
  fail over in staging/test environment
  repeat reads and inspect unknown outcomes
```

Thu thập:

- DBMS và phiên bản.
- Write/read concern hoặc consistency level.
- Topology và replica routing.
- Session token usage.
- Số read requests và anomaly count.
- Replica lag, session wait latency, fallback rate.
- Những timeout do không thể đáp ứng token.
- Failure scenario và độ tin cậy của phép thử.

Phân biệt **lỗi không đáp ứng watermark** với **đã trả dữ liệu cũ mà báo thành công**. Trong một số kiến trúc, trả lỗi tạm thời là cách bảo toàn guarantee tốt hơn trả stale im lặng.

---

## 32. Những ngộ nhận thường gặp

| Ngộ nhận | Giải thích đúng |
|---|---|
| “Eventual consistency nghĩa luôn đọc dữ liệu cũ.” | Replica có thể đã cập nhật; eventual không bảo đảm đọc mới nhất tức thời. |
| “RYW nghĩa mọi user đều thấy write của tôi ngay.” | RYW là bảo đảm theo phiên, không tự global. |
| “RYW nghĩa field tôi ghi không bao giờ bị người khác thay.” | Write khác có thể hợp lệ thay đổi giá trị; phải xét version/order. |
| “MR nghĩa giá trị số cứ tăng.” | MR nói về thứ tự quan sát trạng thái/version. |
| “MR nghĩa luôn đọc bản mới nhất.” | MR chỉ yêu cầu không lùi so với những gì phiên đã thấy. |
| “Sticky session luôn đủ cho RYW.” | Replica sticky có thể chưa nhận write hoặc bị thay thế. |
| “Dùng primary một lần là mọi read model đã theo kịp.” | Cache/GSI/search có đường cập nhật riêng. |
| “Session cookie login là causal session token.” | Xác thực và causal metadata là hai cơ chế khác nhau. |
| “Timestamp client là version causal toàn hệ.” | Clock skew và concurrent writes khiến timestamp không đáng tin như commit order. |
| “Một version số dùng được cho mọi partition.” | Cần scope/version order hoặc vector/opaque token phù hợp. |
| “Bật causal session là transaction.” | Causal ordering không tạo atomic multi-document transaction. |
| “Quorum luôn cho đủ bốn session guarantees.” | Phụ thuộc protocol, scope, timestamps, topology và read path. |
| “MongoDB session mặc định cho mọi causal guarantee với mọi concern.” | Phải tuân thủ điều kiện causal consistency, majority concerns và thứ tự thao tác. |
| “DynamoDB strong read trên GSI là cách giải quyết.” | GSI không hỗ trợ strong consistent read như base table. |
| “Redis WAIT là RYW toàn hệ và fsync.” | WAIT có semantics replication riêng, không đồng nhất causal hoặc persistence. |
| “Cosmos session token của máy A tự có ở máy B.” | Cần quản lý/phân phối context theo phạm vi và SDK. |
| “Nếu đã nhận ACK thì chắc chắn không thể rollback.” | Phụ thuộc durability/commit policy và failure model. |
| “Timeout nghĩa write chắc chắn chưa thực hiện.” | Có thể server đã commit rồi response bị mất. |
| “RYW chống overselling/lost update.” | Cần conditional writes/transactions bảo vệ invariant. |
| “Monotonic reads làm pagination thành snapshot.” | Pagination/snapshot consistency là vấn đề riêng. |
| “Đã xóa record thì version không còn quan trọng.” | Tombstone/version giúp tránh đọc trạng thái cũ resurrect. |
| “Bất kỳ token nào cũng an toàn để client sửa.” | Phải kiểm tra scope, integrity, auth và giới hạn tài nguyên. |
| “Nếu replica lag, cứ trả stale cho nhanh.” | Điều đó có thể phá guarantee đã cam kết với phiên. |
| “Session guarantees không có chi phí.” | Wait, reroute, strong read và metadata có latency/cost. |

## 33. Kết luận

**Read-your-writes** và **monotonic reads** giải quyết hai trải nghiệm quan trọng trong hệ NoSQL phân tán:

- **Read-your-writes:** sau khi phiên ghi thành công, chính phiên không đọc lại một trạng thái thiếu write đó.
- **Monotonic reads:** sau khi phiên đã quan sát trạng thái mới hơn, những lần đọc tiếp theo không đi lùi về trạng thái cũ hơn.

Hai bảo đảm thường được xét cùng:

- **Monotonic writes:** các write của cùng phiên được duy trì theo thứ tự.
- **Writes-follow-reads:** write mới tôn trọng những dữ liệu mà phiên đã quan sát qua read.

Những thuộc tính này giúp ứng dụng có trải nghiệm nhất quán hơn trong khi vẫn sử dụng replica, cache và các mô hình replication không nhất thiết mạnh toàn cục. Để triển khai đúng cần:

1. **Định nghĩa session scope rõ ràng** — một request, một client instance, một tab, một thiết bị hay nhiều thiết bị.
2. **Mang theo causal context/watermark** qua các request và replica khi cần.
3. **Chỉ đọc từ nguồn đáp ứng mốc phiên**, hoặc chờ/route/fallback/trả lỗi khi chưa thể đáp ứng.
4. **Hiểu contract của DBMS** — MongoDB causal session, Cosmos DB session consistency, DynamoDB base-table strong read/GSI eventual, Cassandra consistency level và Redis replication.
5. **Không nhầm visibility với durability**, hay session guarantees với transaction/CAS.
6. **Xem xét toàn bộ đường dữ liệu** — API gateway, cache, search index, CDC, failover và nhiều vùng.
7. **Kiểm thử lịch sử thao tác và đo anomaly**, không chỉ nhìn kết quả cuối hoặc latency trung bình.

**Một hệ NoSQL có thể chấp nhận sự trễ giữa các client mà vẫn bảo đảm mỗi người dùng không phải chứng kiến chính phiên làm việc của mình quay ngược thời gian.**

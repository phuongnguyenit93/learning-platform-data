# Điều kiện bảo đảm đọc lại dữ liệu vừa ghi trong MongoDB

Một API vừa ghi thành công một đơn hàng vào MongoDB rồi lập tức truy vấn để trả kết quả. Trong môi trường thử nghiệm chỉ có một máy, việc **đọc lại dữ liệu vừa ghi** thường có vẻ hiển nhiên. Nhưng khi ứng dụng kết nối **replica set**, đọc từ secondary, sử dụng nhiều service, thực hiện retry hoặc xảy ra failover, lần đọc sau có thể chưa thấy bản ghi mới, thấy phiên bản cũ hoặc nhận lỗi.

Để lý giải đúng, cần phân biệt nhiều cơ chế thường bị gộp chung thành một câu “MongoDB có nhất quán không?”:

- **Read-your-writes (RYW)**: trong một chuỗi thao tác có quan hệ nhân quả, các lần đọc sau quan sát được hiệu ứng của những lần ghi trước đã hoàn tất theo điều kiện nhất quán đã chọn.
- **Write concern**: MongoDB phải nhận được những xác nhận nào trước khi báo một lệnh ghi thành công.
- **Read concern**: mức bảo đảm đối với dữ liệu mà lệnh đọc được phép quan sát.
- **Read preference**: ứng dụng đọc từ primary, secondary hay chọn node theo chính sách nào.
- **Causally consistent session**: MongoDB Driver mang thông tin thời điểm nhân quả giữa các thao tác trong cùng session, giúp bảo vệ những thứ tự như “ghi rồi đọc” khi kết hợp đúng read/write concern.
- **Transaction**: nhóm các thao tác được thực thi với quy tắc commit và visibility riêng.

Mục tiêu của bài là **xác định các điều kiện phải có**, không chỉ thuộc một cấu hình rời rạc. Chúng ta sẽ xây dựng các tình huống cụ thể, xem cách hoạt động của replication, sử dụng mongosh và MongoDB Java Sync Driver, xử lý tình huống đọc secondary, failover, lỗi mạng và các trường hợp API nhiều bước.

## 1. “Đọc lại dữ liệu vừa ghi” có nghĩa chính xác là gì?

Giả sử người dùng tạo hồ sơ:

~~~text
Thời điểm t1:  POST /profiles
               MongoDB ghi profile P-100
               Server xác nhận thành công

Thời điểm t2:  GET /profiles/P-100
               Ứng dụng mong thấy P-100
~~~

**Read-your-writes** yêu cầu thao tác đọc có quan hệ nhân quả sau khi ghi nhìn thấy hiệu ứng ghi đó, với những điều kiện bảo đảm tương ứng. Nếu thao tác ghi là:

~~~javascript
db.profiles.insertOne({
  _id: "P-100",
  displayName: "An",
  version: 1
});
~~~

thì câu hỏi đọc lại là:

~~~javascript
db.profiles.findOne({ _id: "P-100" });
~~~

Tuy nhiên, cần lưu ý ba khác biệt:

1. **Ghi đã thành công** khác với **client chắc chắn đã nhận được xác nhận**. Một timeout có thể làm kết quả ghi mơ hồ.
2. **Thấy hiệu ứng của ghi** khác với **thấy đúng toàn bộ giá trị y nguyên**: nếu một client khác cập nhật document sau đó, lần đọc hợp lệ có thể thấy phiên bản mới hơn.
3. **Đọc sau về mặt thời gian ở ứng dụng** chưa đủ bảo đảm rằng MongoDB biết hai thao tác có quan hệ nhân quả, nhất là khi chúng được gửi qua hai session hoặc hai node khác nhau.

### 1.1. Vì sao đọc nhầm bản cũ là vấn đề nghiệp vụ?

Ví dụ thực tế:

- **Tạo đơn hàng:** POST thành công nhưng màn hình lịch sử đơn trả danh sách thiếu đơn mới.
- **Cập nhật địa chỉ:** người dùng lưu địa chỉ mới, trang sau vẫn hiện địa chỉ cũ.
- **Đổi mật khẩu hoặc quyền:** thao tác bảo mật đã ghi nhưng một request đọc secondary thấy trạng thái trước đó.
- **Ghi số dư hoặc trạng thái thanh toán:** API xác nhận đã cập nhật, service khác lập tức đọc giá trị cũ và quyết định sai.
- **Đồng bộ kho:** worker cập nhật reservation rồi worker khác truy vấn từ node chưa nhận đủ oplog.

Tùy nghiệp vụ, hệ thống có thể **chấp nhận đọc trễ vài giây** hoặc phải bảo vệ **read-your-writes** nghiêm ngặt. Vì vậy, chọn cấu hình phải xuất phát từ yêu cầu nhất quán, độ trễ và khả năng chịu lỗi.

### 1.2. Bốn điều không nên đồng nhất

| Thuật ngữ | Câu hỏi mà nó trả lời |
|---|---|
| Read-your-writes | Client đã ghi X thì các lần đọc có quan hệ nhân quả sau đó có thấy hiệu ứng X không? |
| Monotonic reads | Đã thấy một trạng thái ở thời điểm T thì lần đọc có quan hệ nhân quả tiếp theo có bị quay về trạng thái cũ hơn không? |
| Majority durability | Một ghi được xác nhận bởi đa số thành viên theo cấu hình có được bảo vệ khỏi các kiểu rollback thông thường khi failover không? |
| Linearizable read | Một lần đọc đơn document có phản ánh các ghi đa số đã hoàn tất trước khi lần đọc bắt đầu theo thứ tự thời gian thực không? |

Read-your-writes thuộc nhóm bảo đảm nhân quả. Linearizability là mô hình nhất quán mạnh hơn cho các thao tác thuộc phạm vi áp dụng, nhưng có thêm điều kiện và chi phí. Một đọc từ primary có thể thuận tiện cho read-your-writes mà không tự động có nghĩa mọi lần đọc trong mọi tình huống đều là linearizable.

## 2. Replica set: nguồn gốc của việc đọc chậm hơn ghi

Trong replica set thông thường, ứng dụng ghi vào **primary**. Primary ghi nhận thao tác rồi secondary sao chép các thay đổi qua **oplog** và áp dụng chúng theo quá trình replication.

~~~text
                         Ứng dụng
                           |
                       insert X
                           |
                           v
                        PRIMARY
                           |
                    ghi X / oplog
                           |
           +---------------+---------------+
           |                               |
           v                               v
       SECONDARY A                     SECONDARY B
    áp dụng X sau trễ Δ1             áp dụng X sau trễ Δ2
           |                               |
       đọc thấy X?                      đọc thấy X?
    phụ thuộc thời điểm               phụ thuộc thời điểm
~~~

Các secondary không nhất thiết áp dụng cùng một thao tác **ngay tức thì**. Khoảng cách giữa thời điểm primary xác nhận và secondary áp dụng xong có thể biến động theo tải, mạng, cấu hình và sự cố.

### 2.1. Timeline: ghi primary rồi đọc secondary quá sớm

~~~text
Thời gian tăng dần --------------------------------------------------->

Primary:     write X --> ack write ---> ...

Secondary:   (chưa có X) ----------> apply X ---> ...

Client:      POST X --> 200/201
                           |
                           +-- GET từ secondary
                               Có thể thấy X chưa?
                               Chưa chắc, nếu node còn lag.
~~~

Ngay cả khi request GET được gửi **sau** response POST, nếu GET đi đến secondary chưa bắt kịp, kết quả có thể thiếu bản ghi X.

### 2.2. Primary và secondary có vai trò khác nhau

Trong một replica set bình thường:

- **Primary** tiếp nhận các ghi thông thường.
- **Secondary** sao chép và áp dụng các thay đổi để có thể phục vụ đọc theo read preference được cấu hình.
- Khi primary lỗi, replica set có thể bầu primary mới; trong quá trình đó, một số request có thể lỗi hoặc phải retry.

Đọc từ secondary có thể giúp phân phối tải cho một số workload, nhưng **không thể lấy mục tiêu phân phối tải làm bằng chứng rằng dữ liệu luôn mới nhất**.

### 2.3. Majority acknowledgment không đồng nghĩa mọi secondary đã cập nhật

Giả sử replica set có ba node: primary P, secondary S1 và S2. Với write concern **majority**, thao tác có thể được xác nhận khi đạt đa số theo cấu hình áp dụng; **không phải chờ mọi secondary**.

~~~text
P:  đã có X      |
S1: đã có X      | => đạt đa số, có thể xác nhận
S2: chưa có X    | => vẫn còn lag
~~~

Một lần đọc ngay sau đó từ S2 có thể chưa thấy X nếu không có cơ chế yêu cầu đọc ở thời điểm nhân quả phù hợp. Đây là lý do **w: "majority" không tự làm cho mọi secondary luôn bắt kịp tại mọi thời điểm**.

## 3. Ba nút cấu hình ảnh hưởng đến đọc lại

Cần tách **write concern**, **read concern** và **read preference** thành ba quyết định riêng.

### 3.1. Write concern: khi nào thao tác ghi được xác nhận?

Write concern xác định mức xác nhận mà lệnh ghi yêu cầu.

| Cấu hình | Ý nghĩa khái quát | Ý nghĩa với đọc lại |
|---|---|---|
| w: 1 | Primary xác nhận thao tác theo chính sách ghi áp dụng | Đọc ngay từ cùng primary thường nhìn thấy ghi đã hoàn tất, nhưng có nguy cơ rollback qua failover |
| w: "majority" | Ghi đạt yêu cầu xác nhận của đa số theo cấu hình replica set | Phù hợp với bảo đảm bền vững/causal consistency khi kết hợp read concern majority |
| w: 0 | Không chờ xác nhận ghi theo mức này | Không thể coi thao tác đã thành công chỉ vì client gửi lệnh |
| wtimeout | Giới hạn thời gian chờ write concern | Khi timeout, cần phân biệt trạng thái thực tế của ghi; không mặc định đã rollback |

Ví dụ:

~~~javascript
db.profiles.insertOne(
  {
    _id: "P-101",
    displayName: "Bình",
    version: 1
  },
  {
    writeConcern: { w: "majority", wtimeout: 10000 }
  }
);
~~~

Lệnh yêu cầu majority acknowledgment và giới hạn thời gian chờ tương ứng. **Nếu xảy ra writeConcernError hoặc mạng bị ngắt, hiệu ứng ghi có thể đã xảy ra**. Ứng dụng cần đối soát theo khóa nghiệp vụ, thay vì tự coi thất bại nghĩa là chưa ghi.

**w: "majority" không có nghĩa dữ liệu không thể mất trong mọi thảm họa ngoài mô hình giả định.** Cần xem cấu hình replica set, mức ghi mặc định, storage, backup và quy trình vận hành.

### 3.2. Read concern: đọc được phiên bản dữ liệu ở mức nào?

| Read concern | Đặc điểm chính | Điểm cần nhớ cho RYW |
|---|---|---|
| local | Đọc dữ liệu hiện có trên node phục vụ, có thể gồm thay đổi chưa majority-committed | Đọc từ primary thường thấy ghi vừa áp dụng, nhưng không bảo vệ trước rollback |
| majority | Đọc dữ liệu đã được majority-committed theo quy tắc của server | Có thể vẫn chưa đạt mốc nhân quả của lần ghi trước nếu thiếu causal session |
| linearizable | Hỗ trợ tính chất real-time cho một số thao tác đọc đơn document trên primary | Đòi hỏi điều kiện riêng, có thể phải chờ; không thay thế transaction nhiều document |
| snapshot | Đọc theo một snapshot nhất quán trong phạm vi tính năng/transaction hỗ trợ | Phù hợp khi cần tập dữ liệu nhất quán; không đồng nghĩa tự thấy mọi thay đổi ngoài transaction |
| available | Mức phù hợp với các trường hợp hỗ trợ; có thể đọc dữ liệu chưa majority-committed | Không là lựa chọn để bảo đảm RYW bền vững |

**Read concern "majority" không tự làm mọi read trở thành “dữ liệu mới nhất tuyệt đối”.** Nó liên quan đến trạng thái majority-committed mà node có thể cung cấp. Nếu đọc từ secondary chậm, cần cơ chế mang mốc nhân quả từ ghi sang đọc để buộc lần đọc không đứng trước ghi đó.

### 3.3. Read preference: kết nối đọc đi tới node nào?

| Read preference | Ý nghĩa | Ảnh hưởng tới đọc lại |
|---|---|---|
| primary | Đọc từ primary | Phù hợp với nhiều luồng cần nhìn thấy ngay ghi vừa được primary chấp nhận |
| primaryPreferred | Ưu tiên primary, có thể đọc secondary khi primary không sẵn | Phải dự tính tình huống chuyển sang secondary |
| secondary | Đọc từ secondary | Có thể gặp độ trễ replication; cần causal session nếu muốn RYW bền vững |
| secondaryPreferred | Ưu tiên secondary, có thể fallback primary | Tính mới dữ liệu tùy node phục vụ và chính sách đọc |
| nearest | Chọn node theo độ trễ theo quy tắc lựa chọn của driver | Node gần nhất không nhất thiết là node mới nhất |

**Read preference chỉ quyết định hướng đọc**, không làm secondary đồng bộ tức thì, không thay write concern và không tự tạo causal order.

### 3.4. Phân biệt “đã ghi” và “đã majority-committed”

Ví dụ w:1:

~~~text
Primary:  ghi X --> ACK
Secondary: chưa sao chép X
Primary:  lỗi trước khi X được majority-committed
Election: node mới không chứa X lên primary
~~~

Trong những điều kiện cho phép rollback, X có thể không còn sau failover. Một lần đọc từ primary cũ trước khi lỗi có thể đã thấy X, nhưng điều đó **không chứng minh X đã bền vững qua thay đổi primary**.

Nếu ứng dụng cần “ghi xong rồi đọc lại và vẫn đúng sau failover”, nên xem xét **majority write concern** và yêu cầu đọc phù hợp, thay vì chỉ dựa trên một lần read local thành công.

## 4. Những điều kiện nào thực sự bảo đảm read-your-writes?

Không thể trả lời bằng một câu “luôn bật majority” hoặc “chỉ cần dùng primary”. Cần xác định **đọc ở đâu**, **ghi được xác nhận ở mức nào**, **có giữ quan hệ nhân quả hay không** và **nghiệp vụ cần bảo đảm tới đâu**.

### 4.1. Trường hợp đơn giản: cùng primary, đọc sau ghi thành công

Trong một replica set đang hoạt động bình thường:

~~~text
Ghi vào primary
  -> primary xác nhận thành công
  -> đọc lại chính primary sau đó
  -> thông thường nhìn thấy hiệu ứng ghi
~~~

Ví dụ:

~~~javascript
db.orders.insertOne(
  { _id: "O-001", state: "CREATED" },
  { writeConcern: { w: 1 } }
);

db.orders.findOne({ _id: "O-001" });
~~~

Nếu lệnh insert thành công và lệnh đọc tiếp theo được thực hiện trên **cùng primary không thay đổi**, không có thao tác khác xóa/sửa đơn trước thời điểm đọc, read local thường nhìn thấy document vừa ghi.

Nhưng cấu hình này **không phải bảo đảm end-to-end bền vững trước mọi failover**. w:1 có thể được xác nhận trước khi ghi kịp replication tới đa số. Nếu primary đổi và ghi bị rollback, kết quả sau failover có thể khác.

Ngoài ra, nếu lần đọc được định tuyến sang secondary qua một middleware hoặc read preference khác, không thể lấy lập luận “primary đã có ghi” áp dụng trực tiếp cho node đọc.

### 4.2. Trường hợp cần đọc secondary và giữ quan hệ nhân quả

MongoDB hỗ trợ **causally consistent client sessions**. Khi client thực hiện các thao tác **tuần tự trong cùng session**, session có thể mang mốc thời gian nhân quả từ ghi sang đọc.

Để đạt các bảo đảm nhân quả như read-your-writes theo tài liệu MongoDB, cần kết hợp:

1. **Causally consistent session** được bật.
2. Các thao tác liên quan được thực hiện **trong cùng session** hoặc chuyển thông tin nhân quả một cách hợp lệ.
3. **Lệnh ghi dùng write concern "majority"**.
4. **Lệnh đọc dùng read concern "majority"**.
5. Thao tác được thực hiện **theo thứ tự có quan hệ nhân quả**, không chạy đồng thời nhiều thao tác trên cùng session.
6. Môi trường replica set/sharded deployment, phiên bản driver và server **hỗ trợ cơ chế session tương ứng**.

Khi điều kiện này được đáp ứng, lần đọc sau mang yêu cầu không được đọc ở mốc trước thao tác ghi đã được xác nhận trong session.

### 4.3. Bảng so sánh các trường hợp

| Tình huống | Kỳ vọng đọc lại | Giới hạn cần nhớ |
|---|---|---|
| w:1, đọc local từ cùng primary sau ACK | Thường thấy ghi vừa áp dụng | Có thể rollback qua failover; không áp dụng nếu đọc secondary |
| w:majority, đọc primary sau ACK | Phù hợp cho luồng cần nhìn thấy ghi đã majority-committed | Phải xử lý failover, lỗi mạng, thao tác khác cập nhật đồng thời |
| w:majority, đọc secondary local không có session | Có thể chưa thấy ghi ngay | Secondary có thể lag |
| w:majority, đọc secondary majority không có causal session | Không tự bảo đảm cùng mốc ghi vừa xác nhận | Majority snapshot trên secondary có thể chưa bắt kịp |
| w:majority + readConcern majority + causal session, đọc secondary | Bảo đảm RYW trong phạm vi ngữ nghĩa session khi thao tác tuần tự | Lần đọc có thể phải chờ secondary bắt kịp hoặc timeout |
| w:1 + readConcern majority + causal session | Không đáp ứng đầy đủ tiền đề majority write cho bảo đảm nhân quả | Ghi có nguy cơ rollback, không thay bằng session đơn lẻ |
| Ghi trong transaction nhưng chưa commit, đọc ngoài transaction | Chưa được quyền thấy ghi chưa commit | Đọc ngoài transaction không quan sát uncommitted writes |
| Ghi và đọc trong cùng transaction | Có thể đọc những thay đổi do chính transaction tạo trong phạm vi ngữ nghĩa transaction | Không đồng nghĩa transaction đã commit hoặc visible với client khác |
| Đọc linearizable từ primary kết hợp majority write thích hợp | Bảo đảm real-time mạnh cho thao tác thuộc phạm vi hỗ trợ | Có thể chờ/lỗi trong sự cố quorum, không áp dụng giống nhau cho mọi thao tác |

Bảng trên là bản đồ lựa chọn; **không phải mọi cách đọc đều có cùng mức đảm bảo**, và không có nghĩa “bật majority ở một phía” tự giải quyết tất cả.

### 4.4. Một sơ đồ quyết định nhanh

~~~text
Ứng dụng vừa ghi một document và phải đọc lại
                      |
                      v
           Có chấp nhận đọc trễ?
                 /          \
               Có          Không
               |             |
      Có thể dùng đọc         v
      secondary eventual    Đọc từ primary?
      + retry/polling         /         \
                          Có           Không
                          |              |
                Cân nhắc w majority       v
                + primary read       Đọc từ secondary
                          |              |
                          |         Causal session
                          |         + majority write
                          |         + majority read
                          |              |
                          +------+-------+
                                 |
                                 v
                          Xử lý failover,
                          timeout, retry,
                          dữ liệu thay đổi
~~~

Nếu yêu cầu không chỉ là RYW mà còn muốn **trật tự real-time được quan sát nhất quán giữa nhiều client** trên một document, hãy nghiên cứu read concern **linearizable** và những điều kiện/chi phí riêng. Nếu muốn nhiều document được nhìn thấy đồng thời theo một snapshot, hãy nghiên cứu transaction và read concern **snapshot**.

## 5. Causally consistent session hoạt động như thế nào?

Một session hỗ trợ causal consistency giúp MongoDB Driver gắn thông tin về tiến độ logic của các thao tác. Các mốc như **operationTime** và **clusterTime** hỗ trợ việc sắp thứ tự nhân quả; server có thể sử dụng **afterClusterTime** trong read concern để tránh trả một snapshot đứng trước mốc đã biết.

Hãy hình dung:

~~~text
Client session S

1. INSERT X trên primary, w:majority
               |
               v
        Server xác nhận thành công
               |
               v
        Session S ghi nhận mốc T
               |
               v
2. FIND X trên secondary, readConcern:majority
   + yêu cầu mốc nhân quả >= T
               |
        +------+------+
        |             |
 Secondary đã      Secondary chưa
 đạt mốc T         đạt mốc T
        |             |
        v             v
    Trả kết quả     Chờ bắt kịp hoặc
                    hết hạn/lỗi
~~~

Điểm then chốt là **session truyền thông tin nhân quả**, chứ không phải session khiến secondary replication ngay lập tức.

### 5.1. Đọc có thể chờ, không phải “bảo đảm luôn trả ngay”

Nếu secondary được chọn đang lag, lần đọc causal cần một snapshot đạt thời điểm yêu cầu. Nó có thể:

- Chờ node áp dụng những thay đổi cần thiết.
- Thành công khi node bắt kịp.
- Nhận lỗi do timeout, mất kết nối, node không khả dụng hoặc những giới hạn hoạt động khác.

Vì vậy, một bảo đảm nhất quán là **bảo đảm về phiên bản dữ liệu khi đọc thành công**, không phải cam kết lúc nào cũng hoàn thành trong một mili giây.

Thiết lập timeout và chính sách retry phù hợp; tránh chờ vô hạn khi hệ thống đang gặp sự cố.

### 5.2. Cùng MongoClient không đồng nghĩa cùng causal session

Ví dụ:

~~~text
POST request -> MongoClient A, session S1 -> ghi X
GET request  -> MongoClient A, session S2 -> đọc X
~~~

Hai request cùng dùng một **MongoClient** hay cùng connection pool không tự bảo đảm chúng ở trong **một causally consistent session**. Session là một ngữ cảnh logic riêng, có vòng đời và thông tin thời gian của nó.

Nếu backend khởi tạo session mới cho mỗi HTTP request, quan hệ nhân quả **không tự chuyển qua hai request** chỉ vì cùng process hoặc cùng user.

### 5.3. Không dùng một session đồng thời ở nhiều thread

Session trong MongoDB Driver không được coi là một đối tượng an toàn để chạy song song nhiều thao tác tùy ý. Trong một luồng causal, hãy thực hiện các thao tác theo thứ tự:

~~~text
write -> await success -> read -> await result
~~~

Không chuyển thành:

~~~text
start write
start read ngay khi write chưa có kết quả
~~~

khi mong muốn quan hệ nhân quả write-before-read. Nếu hai thao tác chạy đồng thời, không có cơ sở để yêu cầu read quan sát một write chưa được xác nhận và chưa được ghi nhận mốc nhân quả.

### 5.4. Vì sao majority read và majority write phải đi cùng?

Read concern majority bảo vệ tính chất chỉ đọc dữ liệu đã majority-committed, còn write concern majority bảo vệ mức xác nhận của ghi. Causal session liên kết thứ tự các thao tác trong phạm vi bảo đảm hỗ trợ.

Nếu chỉ đổi read concern sang majority nhưng ghi bằng w:1, phần ghi có thể chưa durable theo quorum. Nếu chỉ ghi majority nhưng đọc secondary majority không có mốc causal, node đọc có thể chưa tới thời điểm của ghi. Nếu bật session nhưng lệnh đọc/ghi không dùng các concern cần thiết, cũng không thể mặc định đạt **đầy đủ các bảo đảm causal consistency đã nêu**.

## 6. Phạm vi bảo đảm: session, request và nhiều service

Trong một chương trình có một session sống xuyên suốt thao tác ghi rồi đọc, thiết kế tương đối trực tiếp. Trong kiến trúc web/microservice, hai lời gọi có thể do hai instance khác nhau xử lý:

~~~text
Client
   |
   +-- POST /orders ---> service A ---> MongoDB primary
   |
   +-- GET /orders  ---> service B ---> MongoDB secondary
~~~

Ở đây, service B chưa chắc biết **mốc thời gian nhân quả của service A**. Các giải pháp thường chọn tùy nhu cầu:

1. **Route lần đọc ngay sau ghi về primary**, kết hợp write concern phù hợp với độ bền mong muốn.
2. **Thiết kế workflow trong một service/session** cho phần cần read-your-writes.
3. **Truyền causal metadata** giữa các service/session theo API và chính sách bảo mật hỗ trợ, khi thực sự cần đọc secondary mà vẫn giữ quan hệ nhân quả.
4. **Trả dữ liệu đã được ghi trong response POST** để giao diện không phải lập tức GET trong trường hợp không cần một đọc mới từ database.
5. **Chấp nhận eventual consistency có chủ đích**: client poll theo requestId/version với timeout/backoff phù hợp nếu nghiệp vụ cho phép.

### 6.1. Trả lại kết quả POST không phải một “read” tự động

Nếu API insert một order rồi trả chính đối tượng mà nó vừa gửi lên:

~~~json
{
  "orderId": "O-100",
  "state": "CREATED"
}
~~~

thì client có thể **hiển thị dữ liệu mới ngay** mà không cần chờ secondary. Nhưng điều này không chứng minh một GET độc lập đọc từ secondary cũng đã thấy order. Cần phân biệt **UI hiển thị kết quả command** và **database read-your-writes**.

### 6.2. Causal token giữa session khác nhau

Ở tầng driver, có những API liên quan tới **clusterTime/operationTime** và cách đưa session mới tiến tới một mốc đã biết, tùy driver. Đây là kỹ thuật cần nắm rõ mô hình an toàn và định dạng metadata; không nên tự phát minh một timestamp ở ứng dụng rồi cho rằng MongoDB sẽ dùng nó như mốc nhân quả hợp lệ.

Khi phải truyền mốc giữa service, cần xem xét:

- Mốc lấy từ **thao tác thực tế được server xác nhận**, không từ Date.now() của client.
- Session mới có cách **advance** thông tin causal theo API được hỗ trợ.
- Read concern, write concern và quyền truy cập được cấu hình thích hợp.
- Không tiết lộ metadata nội bộ nhạy cảm hoặc để client ngoài tự cung cấp mốc tùy ý.
- Cơ chế timeout/retry khi node đọc chưa bắt kịp.

Trong nhiều hệ thống, **đọc primary sau ghi majority** hoặc **giữ logic ghi–đọc trong một service** đơn giản hơn truyền causal metadata xuyên nhiều tầng. Chỉ tăng độ phức tạp khi lợi ích về phân phối tải và yêu cầu nhất quán chứng minh cần thiết.

### 6.3. Không nhầm read-your-writes với “read-your-transaction”

Trong transaction, các thao tác cùng transaction có thể nhìn thấy những thay đổi chính transaction đã ghi, dù chưa commit ra ngoài. Đó là **quy tắc visibility của transaction**. Read-your-writes **sau khi commit qua các session/node** lại phụ thuộc cách commit, read concern và quan hệ nhân quả.

Không nên lấy việc find trong cùng transaction đã thấy document rồi kết luận mọi read từ secondary bên ngoài transaction lập tức thấy document đó.

## 7. Thực hành trên replica set bằng mongosh

Các bảo đảm liên quan **primary/secondary, majority và causal session** cần một deployment hỗ trợ replication. Một MongoDB standalone không cho phép bạn thực sự quan sát secondary lag hoặc failover theo replica set.

Hãy kết nối vào một **replica set thử nghiệm** hoặc một cluster MongoDB phù hợp bằng mongosh. Không thử tắt primary, chặn replication hay thay cấu hình read/write concern trên hệ thống production để làm bài.

### 7.1. Kiểm tra môi trường

Trong mongosh:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Với replica set, phản hồi có thể có thông tin như **setName**, **isWritablePrimary**, **secondary** và danh sách host, tùy node và cấu hình. Bạn không cần sao chép toàn bộ output chứa địa chỉ nội bộ vào tài liệu chia sẻ công khai.

Khi có quyền phù hợp:

~~~javascript
rs.status();
~~~

Lệnh này giúp nhận biết các thành viên và trạng thái replication. Trong dịch vụ quản lý hoặc account không có quyền quản trị, lệnh có thể bị giới hạn. Khi đó hãy xác nhận topology qua công cụ quản lý được phép thay vì mở rộng quyền chỉ để làm bài.

### 7.2. Tạo collection thử nghiệm và khóa duy nhất

~~~javascript
use ryw_lab

db.orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_ryw_requestId" }
);
~~~

Giả sử mỗi lần tạo đơn của bài thực hành dùng một requestId riêng, ví dụ **R-240-001**.

~~~javascript
db.orders.insertOne(
  {
    _id: "O-240-001",
    requestId: "R-240-001",
    state: "CREATED",
    version: 1,
    updatedAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

Sau khi lệnh insert được xác nhận thành công, đọc từ primary:

~~~javascript
db.orders.findOne({ _id: "O-240-001" });
~~~

Nếu cùng kết nối đang định tuyến đọc từ primary và không có ghi cạnh tranh, kết quả sẽ chứa document vừa tạo. Đây là ví dụ dễ quan sát về việc read-after-write trên primary trong điều kiện bình thường.

### 7.3. Quan sát read concern majority trong một lệnh

Bạn có thể dùng lệnh find ở mức database command với readConcern tường minh:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "O-240-001" },
  readConcern: { level: "majority" }
});
~~~

Kết quả thường chứa **cursor.firstBatch** và metadata tương ứng. Đoạn này giúp quan sát một lần đọc với read concern majority **trên node được command định tuyến tới**. Nó **không phải thí nghiệm chứng minh secondary đã bắt kịp** nếu command vẫn chạy từ primary.

### 7.4. Tạo một causal session tường minh

Trong mongosh, session có thể được lấy từ Mongo connection:

~~~javascript
const session = db.getMongo().startSession({
  causalConsistency: true
});

const sdb = session.getDatabase("ryw_lab");

try {
  const writeResult = sdb.runCommand({
    insert: "orders",
    documents: [
      {
        _id: "O-240-SESSION",
        requestId: "R-240-SESSION",
        state: "CREATED",
        version: 1,
        updatedAt: new Date()
      }
    ],
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  });

  printjson(writeResult);

  if (writeResult.ok !== 1 || writeResult.n !== 1) {
    throw new Error("Write was not confirmed; do not assume success");
  }

  const readResult = sdb.runCommand({
    find: "orders",
    filter: { _id: "O-240-SESSION" },
    readConcern: { level: "majority" }
  });

  printjson(readResult.cursor.firstBatch);
} finally {
  session.endSession();
}
~~~

Ví dụ minh họa **thứ tự write → read trên cùng explicit session**, với majority write và majority read. Trong code ứng dụng, cần xử lý thêm lỗi writeConcern, exception, timeout và điều kiện rollback thay vì chỉ dựa trên trường ok trong một command result.

Lần đọc trong đoạn này **chưa yêu cầu secondary**: muốn kiểm tra hành vi đọc từ secondary trong một client session, hãy dùng API cấu hình **readPreference: secondary** của driver, như ví dụ Java ở phần sau. Không nên cho rằng thêm read concern majority vào lệnh là đã chuyển node đọc sang secondary.

**Nếu chạy lại**, cặp _id/requestId đã có sẽ làm insert thất bại do unique key. Hãy dùng mã thử nghiệm mới thay vì xóa dữ liệu ngoài ý muốn.

### 7.5. Một bài thử eventual consistency có chủ đích

Để thấy tác động của secondary lag, có thể sử dụng hai kết nối được cấu hình khác nhau:

- Kết nối ghi: route đến primary.
- Kết nối đọc: read preference secondary.

Sau một lệnh ghi mới được xác nhận, thử đọc bằng kết nối secondary **không có mốc causal**. Tùy môi trường và thời điểm, read có thể thấy document ngay hoặc chưa thấy. **Không thể bảo đảm tái hiện staleness bằng vài document** nếu secondary đang đồng bộ nhanh.

Không cố gây lag bằng cách làm gián đoạn replication của cluster chung. Để kiểm tra bắt buộc causal read, hãy dùng explicit session và cấu hình driver ở phần Java.

## 8. Java Sync Driver: bảo đảm đọc lại sau khi ghi ở secondary

Đối với một đoạn code cần **ghi trên primary rồi đọc ở secondary với causal ordering**, MongoDB Java Sync Driver cho phép:

1. Tạo **ClientSession** với **causallyConsistent(true)**.
2. Ghi bằng collection có **WriteConcern.MAJORITY**.
3. Đọc bằng collection có **ReadConcern.MAJORITY**.
4. Chọn **ReadPreference.secondary()** nếu chủ đích phải đọc một secondary.
5. Truyền **cùng ClientSession** vào cả insertOne và find.
6. Chờ kết quả ghi xong mới bắt đầu đọc.

### 8.1. Ví dụ Java hoàn chỉnh

Ví dụ dành cho project có dependency **mongodb-driver-sync** tương thích, biến môi trường **MONGODB_URI** trỏ tới replica set có secondary phục vụ đọc và các quyền phù hợp:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.util.Date;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public class ReadYourWritesDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        String id = "O-" + UUID.randomUUID();

        try (MongoClient client = MongoClients.create(uri);
             ClientSession session = client.startSession(
                     ClientSessionOptions.builder()
                             .causallyConsistent(true)
                             .build())) {

            MongoDatabase database = client.getDatabase("ryw_lab");
            MongoCollection<Document> orders =
                    database.getCollection("orders");

            MongoCollection<Document> writer = orders
                    .withWriteConcern(WriteConcern.MAJORITY);

            MongoCollection<Document> secondaryReader = orders
                    .withReadConcern(ReadConcern.MAJORITY)
                    .withReadPreference(ReadPreference.secondary());

            Document order = new Document("_id", id)
                    .append("requestId", id)
                    .append("state", "CREATED")
                    .append("version", 1)
                    .append("updatedAt", new Date());

            // Ghi trên primary, đợi majority acknowledgement.
            writer.insertOne(session, order);

            // Cùng session truyền quan hệ nhân quả tới lần đọc.
            // Nếu secondary chưa bắt kịp, đọc có thể chờ/lỗi.
            Document seen = secondaryReader
                    .find(session, Filters.eq("_id", id))
                    .maxTime(10, TimeUnit.SECONDS)
                    .first();

            if (seen == null) {
                throw new IllegalStateException(
                        "Order not found after acknowledged write: " + id);
            }

            System.out.println(seen.toJson());
        }
    }
}
~~~

**Điểm quan trọng trong code:**

- **ClientSessionOptions.causallyConsistent(true)** thể hiện rõ ý định bảo đảm thứ tự nhân quả.
- **writer.insertOne(session, order)** và **secondaryReader.find(session, ...)** dùng cùng session.
- **WriteConcern.MAJORITY** và **ReadConcern.MAJORITY** cung cấp các mức concern cần thiết cho bảo đảm nhân quả.
- **ReadPreference.secondary()** buộc lần đọc dùng secondary; nếu không có secondary phù hợp thì thao tác có thể thất bại thay vì tự chuyển sang primary.
- **maxTime(10, TimeUnit.SECONDS)** giúp giới hạn thời gian thực thi theo quy tắc MongoDB áp dụng; không phải cam kết toàn bộ thao tác mạng không bao giờ vượt 10 giây.
- **ClientSession** và **MongoClient** được đóng sau khi dùng xong trong chương trình CLI.

Trong ứng dụng web có nhiều request, thông thường **MongoClient được tái sử dụng dài hạn**, không tạo/đóng mỗi HTTP request. Còn session nên được tạo, sử dụng tuần tự và đóng theo **ranh giới nghiệp vụ** thích hợp.

### 8.2. Nếu muốn ưu tiên secondary nhưng chấp nhận fallback primary

Thay:

~~~java
ReadPreference.secondary()
~~~

bằng:

~~~java
ReadPreference.secondaryPreferred()
~~~

Khi có secondary phù hợp, driver có thể đọc từ secondary; nếu không có, nó có thể fallback sang primary theo read preference. Vì vậy, đừng khẳng định một request thực sự đi đến secondary chỉ vì code có **secondaryPreferred**. Muốn xác minh node được chọn, cần dùng command monitoring hoặc công cụ quan sát tương ứng.

### 8.3. Nếu chỉ đọc primary

Có thể cấu hình:

~~~java
MongoCollection<Document> primaryReader = orders
        .withReadPreference(ReadPreference.primary())
        .withReadConcern(ReadConcern.MAJORITY);
~~~

Với một ghi majority đã xác nhận trên primary, đây thường là thiết kế đơn giản hơn cho những API vừa ghi xong cần đọc lại. Tùy hợp đồng, vẫn có thể giữ causal session để quan hệ thứ tự được thể hiện tường minh và nhất quán trong luồng xử lý.

### 8.4. Nếu write gặp timeout hoặc writeConcernError

Không nên chuyển ngay sang:

~~~java
// Ví dụ sai về giả định logic:
// Nếu insertOne ném lỗi mạng -> tạo một id mới và insert lại.
~~~

Vì kết quả của lần ghi đầu có thể không xác định. Với thao tác tạo tài nguyên, nên dùng **requestId/idempotency key ổn định**, unique index và quy trình đối soát hoặc retry có giới hạn. Nếu không, client có thể tạo hai tài nguyên chỉ vì lần đầu ghi thành công nhưng phản hồi mất.

Đọc lại với causal session sau một **ghi chưa được xác nhận thành công** không tự tạo ra bằng chứng rằng ghi đã đạt majority. Trước hết cần xác minh trạng thái ghi hoặc thực hiện retry an toàn theo hợp đồng nghiệp vụ.

## 9. Spring Data MongoDB: truyền session qua tầng truy cập dữ liệu

Trong ứng dụng Spring Boot dùng Spring Data MongoDB, **MongoTemplate** hoặc repository giúp thao tác CRUD. Tuy nhiên, chỉ sử dụng cùng một bean MongoTemplate không bảo đảm hai request độc lập dùng chung causal session.

### 9.1. Một mẫu truy cập trong cùng session

Spring Data MongoDB có API giúp tạo một ngữ cảnh **MongoOperations** gắn với một ClientSession:

~~~java
import com.mongodb.client.ClientSession;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.MongoTemplate;

public class OrderService {
    private final MongoTemplate mongoTemplate;

    public OrderService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document insertThenRead(
            ClientSession session,
            Document order) {

        MongoOperations operations =
                mongoTemplate.withSession(session);

        operations.insert(order, "orders");

        return operations.findById(
                order.getString("_id"),
                Document.class,
                "orders"
        );
    }
}
~~~

Trong ví dụ:

- **withSession(session)** giúp các thao tác của ngữ cảnh MongoOperations sử dụng session được truyền vào.
- Caller phải đảm bảo session còn hiệu lực và các thao tác được thực hiện tuần tự.
- **Không có cấu hình majority concern trong đoạn code này**: để đạt causal guarantee cần cấu hình majority write/read concern cho các thao tác thực tế, đúng môi trường và phiên bản Spring Data.
- Truy vấn **findById** trên primary thường là mẫu đơn giản; nếu muốn đọc secondary trong cùng session, cần cấu hình read preference phù hợp và xác nhận thao tác thực tế dùng concern mong muốn.

Đừng xem đoạn này là cách tự động đạt RYW bền vững nếu MongoTemplate hoặc driver đang dùng các default concern không phù hợp.

### 9.2. Ai tạo và đóng ClientSession?

Thông thường session được tạo theo **một đơn vị công việc**, không giữ nó mãi trong một singleton Spring bean:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;

public class SessionBoundary {
    private final MongoClient client;
    private final OrderService orderService;

    public SessionBoundary(
            MongoClient client,
            OrderService orderService) {
        this.client = client;
        this.orderService = orderService;
    }

    public void processOrder() {
        ClientSessionOptions options = ClientSessionOptions.builder()
                .causallyConsistent(true)
                .build();

        try (ClientSession session = client.startSession(options)) {
            // Ở đây phải bảo đảm majority read/write concern
            // trong cấu hình thao tác thực tế khi cần causal RYW.
            orderService.insertThenRead(
                    session,
                    new org.bson.Document("_id", "O-SPRING-240")
                            .append("state", "CREATED")
            );
        }
    }
}
~~~

Code minh họa ranh giới session. Nếu chạy lại với cùng _id và dùng insert, lệnh thứ hai sẽ gặp duplicate key; trong API thực tế nên dùng mã yêu cầu nghiệp vụ ổn định và quy trình idempotency thích hợp.

### 9.3. Repository không tự mang session xuyên HTTP

Giả sử:

~~~text
POST /orders -> OrderRepository.save(...)
GET /orders  -> OrderRepository.findById(...)
~~~

Hai lần gọi repository có thể được thực thi trong hai HTTP request, hai thread và hai instance ứng dụng khác nhau. Không nên mặc định chúng có causal consistency end-to-end chỉ vì cùng repository interface.

Với luồng quan trọng, cần lựa chọn rõ một trong các hướng:

- **Read preference primary** cho những truy vấn cần nhìn thấy ghi mới.
- **Transaction hoặc session được quản lý rõ** cho một đơn vị công việc.
- **Causal token được truyền hợp lệ** khi phải kết nối hai yêu cầu qua nhiều service.
- **Polling/đối soát theo version hoặc requestId** khi chấp nhận đồng bộ trễ.

Việc chọn giải pháp phụ thuộc cấu hình Spring Data, MongoDB Driver và topology chứ không chỉ ở tên phương thức repository.

## 10. Read-your-writes trong MongoDB transaction

MongoDB hỗ trợ **multi-document transaction** trong những deployment đáp ứng điều kiện. Khi một transaction ghi document rồi đọc lại chính document ấy **bên trong cùng transaction**, thao tác đọc có thể quan sát những ghi chưa commit của chính transaction.

Ví dụ Java Sync Driver:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class TransactionReadOwnWrite {
    public static void createAndRead(
            ClientSession session,
            MongoCollection<Document> orders,
            String orderId) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        session.startTransaction(options);
        try {
            orders.insertOne(session,
                    new Document("_id", orderId)
                            .append("state", "CREATED"));

            Document ownWrite = orders.find(
                    session, Filters.eq("_id", orderId)).first();

            if (ownWrite == null) {
                throw new IllegalStateException(
                        "Missing own write inside transaction");
            }

            session.commitTransaction();
        } catch (RuntimeException ex) {
            if (session.hasActiveTransaction()) {
                session.abortTransaction();
            }
            throw ex;
        }
    }
}
~~~

Ví dụ diễn tả **đọc ghi của chính transaction**; cần truyền vào ClientSession và MongoCollection đã được khởi tạo. Trong ứng dụng thực, transaction có thể gặp **TransientTransactionError** hoặc **UnknownTransactionCommitResult** và cần retry theo chính sách/nhãn lỗi. Không đặt side effect HTTP ngoài MongoDB vào callback transaction có thể retry.

### 10.1. Một client khác có thấy document trước commit không?

Không. Một transaction khác hoặc một lần đọc ngoài transaction không tự nhìn thấy những ghi chưa commit của transaction này.

~~~text
Transaction A                      Client B
   |
   +-- insert X
   +-- find X -> thấy X
   |                                  find X -> chưa có X
   +-- commit
                                      |
                                      +-- sau commit:
                                          visibility phụ thuộc
                                          đọc từ node nào,
                                          read concern, causal order
~~~

Việc A đọc được X trong transaction **không có nghĩa B được đọc trước khi A commit**. Và ngay sau commit, đọc từ secondary không có causal ordering vẫn có thể chưa thấy thay đổi nếu node chưa bắt kịp.

### 10.2. Read concern snapshot khác linearizable

Read concern **snapshot** cho phép đọc một ảnh chụp nhất quán trong phạm vi transaction hoặc tình huống được hỗ trợ. Nó không biến mọi truy vấn thành linearizable theo thời gian thực. Trong một transaction đọc theo snapshot, thay đổi được client khác commit sau mốc snapshot có thể không hiện trong các lần đọc của transaction ấy.

Nếu yêu cầu là “ghi nhiều document rồi đọc tất cả chúng một cách nhất quán”, transaction có thể phù hợp. Nếu yêu cầu là “một client vừa ghi đơn document và client khác phải đọc kết quả mới nhất ngay theo real time”, cần xem read concern linearizable hoặc mô hình định tuyến primary và các điều kiện liên quan.

### 10.3. Commit majority quan trọng ở đâu?

Ghi nhiều document trong transaction không có nghĩa mọi document đã được majority-committed chỉ vì code đã chạy insert. Phải phân biệt **thao tác trong transaction**, **commit** và **write concern của commit**.

Khi transaction kết thúc thành công với write concern majority, ứng dụng có cơ sở bền vững hơn để cho các bước tiếp theo đọc những thay đổi đã commit. Nếu commit trả lỗi mạng và không rõ kết quả, không tự chạy lại toàn bộ nghiệp vụ với một mã mới; cần retry commit/đối soát theo cơ chế phù hợp của driver và khóa nghiệp vụ.

## 11. Linearizable read: khi nào cần mức mạnh hơn?

Đôi khi yêu cầu không chỉ là **client thấy dữ liệu mình đã ghi**, mà là **mọi client đọc một document phải tôn trọng thứ tự hoàn tất của các lệnh ghi đã majority-acknowledged trước đó**.

Read concern **linearizable** có thể hỗ trợ yêu cầu đó đối với **thao tác đọc phù hợp trên primary**, trong những điều kiện được MongoDB hỗ trợ. Nó thường được kết hợp với **majority write concern** để đạt bảo đảm real-time mong muốn.

### 11.1. Ví dụ đọc một document có _id xác định

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "O-240-001" },
  limit: 1,
  readConcern: { level: "linearizable" },
  maxTimeMS: 10000
});
~~~

Đây là một lệnh truy vấn đơn document trên primary theo cách sử dụng read concern linearizable thích hợp. **Không chọn readPreference secondary cho linearizable read**. Hãy xác minh phiên bản, loại thao tác được hỗ trợ và quyền truy cập trong deployment thật.

### 11.2. Vì sao linearizable read có thể chậm hoặc lỗi?

Để xác nhận không đọc từ một primary đã mất khả năng cam kết theo cấu hình replica set, MongoDB có thể cần trao đổi với những thành viên khác theo cơ chế thực thi. Khi mất quorum, partition mạng hoặc xảy ra election, read linearizable có thể phải chờ cho đến giới hạn thời gian hoặc trả lỗi.

**Consistency có thể đánh đổi latency và availability.** Nếu ứng dụng chỉ cần đọc lại ghi của chính mình trong một session, cấu hình causal majority hoặc primary read phù hợp có thể đơn giản và rẻ hơn yêu cầu linearizable cho mọi read.

### 11.3. Không áp dụng linearizable cho mọi truy vấn phức tạp

Mức này không phải công tắc chung để biến mọi phép aggregate, truy vấn nhiều document và transaction thành một snapshot real-time toàn cục. Nó có phạm vi hỗ trợ riêng, thường gắn với thao tác đọc xác định một document. Khi cần nhiều document nhất quán, xem transaction/snapshot; khi cần causal ordering, xem causal session.

### 11.4. So sánh ba lựa chọn điển hình

| Nhu cầu | Cách tiếp cận thường xem xét |
|---|---|
POST một document rồi GET ngay từ primary | Ghi với concern phù hợp; đọc primary sau ACK |
Ghi rồi đọc từ secondary cùng một chuỗi nghiệp vụ | Causal session, majority write + majority read, tuần tự |
Đọc một document phải phản ánh ghi majority hoàn tất trước đó theo real time | Linearizable read trên primary với điều kiện hỗ trợ |
Ghi và đọc nhiều document trong một transaction | Transaction với read concern snapshot và commit concern phù hợp |
Màn hình analytics có thể chấp nhận trễ | Secondary read/eventual consistency có quan sát lag |

Điểm quan trọng: không dùng mức consistency mạnh hơn nhu cầu một cách mù quáng, nhưng cũng không đánh đổi tính đúng đắn nghiệp vụ lấy tốc độ đọc khi dữ liệu được dùng cho quyết định quan trọng.

## 12. Failover, retry và kết quả ghi chưa rõ

Trong hệ thống phân tán, lỗi xuất hiện ở nhiều điểm khác nhau. Điều kiện đọc lại phụ thuộc vào **lệnh ghi đã thực sự hoàn tất chưa** và **client có mốc nhân quả đáng tin cậy không**.

### 12.1. Trường hợp ghi thành công nhưng response bị mất

~~~text
Client                     Primary                     Secondary
  |                           |                            |
  |--- insert order O-900 --->|                            |
  |                           |---- replicate ----------->|
  |                           |<---- majority ack ---------|
  |<----------- X ------------|                            |
      Mất response
~~~

Client không biết lệnh ghi đã thành công, dù server có thể đã ghi majority. Nếu client tạo **một orderId ngẫu nhiên mới** rồi gửi lại, hệ thống có thể tạo đơn thứ hai.

**Read-your-writes giả định bạn đã có một ghi được xác nhận theo điều kiện cần thiết**. Khi lệnh ghi có kết quả mơ hồ, bước đầu tiên là **xác định hoặc tái thực hiện an toàn ý định nghiệp vụ**, không phải mặc định rằng ghi chưa tồn tại.

Một mẫu bảo vệ:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, clientRequestId: 1 },
  { unique: true }
);
~~~

Nếu client có clientRequestId ổn định, backend có thể đọc theo khóa để đối soát. Nếu không thấy dữ liệu ở secondary, cũng không nên kết luận request chưa được xử lý; cần đọc nguồn có bảo đảm nhất quán phù hợp hoặc retry theo chính sách an toàn.

### 12.2. Retryable writes khác causal consistency

MongoDB Driver hỗ trợ **retryable writes** cho một số thao tác trong deployment phù hợp. Cơ chế này nhằm hỗ trợ thực hiện lại các lệnh ghi khi gặp một số lỗi tạm thời theo ngữ cảnh của driver.

**Causal consistency** giải quyết một câu hỏi khác: sau khi thao tác ghi được xác nhận và mốc causal được ghi nhận, các lần đọc sau trong session không được quay về trạng thái trước mốc đó theo điều kiện majority đã nêu.

| Cơ chế | Giải quyết |
|---|---|
| Retryable writes | Khả năng thử lại một số lệnh ghi khi có lỗi mạng/failover |
| Causal session | Thứ tự nhân quả của các thao tác được liên kết |
| Majority write concern | Mức xác nhận bền vững của ghi |
| Majority read concern | Mức nhìn thấy majority-committed data |
| Unique requestId/idempotency | Tránh tạo nhiều hiệu ứng nghiệp vụ khi HTTP/message lặp |

Chúng bổ sung nhau, không phải tên khác nhau của cùng một tính năng.

### 12.3. Nếu wtimeout xảy ra

Với:

~~~javascript
{
  writeConcern: {
    w: "majority",
    wtimeout: 5000
  }
}
~~~

Nếu chờ majority vượt thời hạn, client có thể nhận **write concern timeout/error**. Điều này không có nghĩa thao tác ghi chắc chắn bị hủy trên primary hoặc chưa bao giờ được áp dụng. Nó cũng không chứng minh ghi đã đạt majority tại thời điểm client nhận lỗi.

Để khôi phục:

1. Giữ nguyên **requestId** hoặc khóa nghiệp vụ.
2. Phân loại lỗi mạng, write concern và lỗi nghiệp vụ.
3. Thử lại một cách **idempotent** hoặc tra cứu trạng thái từ nguồn đọc phù hợp.
4. Nếu trạng thái còn mơ hồ, ghi nhận **UNKNOWN/NEEDS_RECONCILIATION** thay vì tuyên bố thành công hoặc tạo thao tác mới.

Không nên viết logic **catch any exception → insert với _id mới**.

### 12.4. Failover giữa ghi và đọc

Nếu lệnh ghi được xác nhận **w:1**, primary có thể lỗi trước khi ghi được replication bền vững. Một primary mới không chứa hiệu ứng đó có thể được bầu lên trong điều kiện cho phép rollback.

Nếu ghi được majority-acknowledged trong điều kiện replica set thông thường, nguy cơ rollback của ghi đã cam kết được giảm mạnh theo bảo đảm replication. Nhưng ứng dụng vẫn phải chịu các tình huống **election, retry, session timeout và read routing**.

Không nhầm **durability** với **availability**: dữ liệu bền vững không có nghĩa trong giai đoạn failover mọi read đều trả ngay mà không lỗi.

### 12.5. Primary mới không nhất thiết đã sẵn sàng tức thì

Trong election, driver có thể nhận lỗi server selection hoặc không tìm thấy primary theo read preference trong một khoảng thời gian. Nếu read không thành công, đó không phải bằng chứng document đã biến mất. Retry với backoff hợp lý, giới hạn thời gian và phân loại lỗi.

Nếu không thể phục vụ một đọc đúng mức nhất quán, hệ thống nên **trả lỗi hoặc chờ theo chính sách** thay vì im lặng fallback sang một secondary thiếu dữ liệu khi nghiệp vụ không cho phép.

## 13. Một lần GET có thể đọc từ cache nằm ngoài MongoDB

Ngay cả khi MongoDB được cấu hình đúng, ứng dụng có thể vẫn hiển thị bản cũ nếu GET không truy vấn trực tiếp MongoDB:

~~~text
POST /profile
   |
   v
MongoDB: displayName = "B"

GET /profile
   |
   v
Redis / in-memory cache / HTTP CDN
   |
   v
displayName = "A"
~~~

MongoDB causal consistency **không tự kiểm soát dữ liệu trong Redis, HTTP cache, CDN hoặc browser cache**. Muốn đạt read-your-writes ở mức API end-to-end, phải kiểm soát cả đường đọc ngoài MongoDB.

### 13.1. Những chiến lược phổ biến

- **Cache invalidation khi ghi:** xóa hoặc cập nhật entry liên quan sau khi ghi thành công theo hợp đồng.
- **Write-through hoặc write-behind có quy tắc rõ:** hiểu thời điểm cache và database nhất quán, nhất là khi có lỗi.
- **Versioned cache:** gắn version cho document và chỉ dùng cache entry đáp ứng mốc version client đã thấy.
- **Read-after-write bypass:** các request ngay sau ghi được route trực tiếp tới nguồn dữ liệu tin cậy trong một khoảng hoặc đến khi thấy version mới.
- **Optimistic UI:** hiển thị kết quả ghi rồi đồng bộ; nếu GET có thể stale, phải xử lý hợp lý ở giao diện.

Không có chiến lược nào miễn phí. Cache invalidation có thể gặp race; write-behind có thể tạo thêm thời gian trễ; bypass ảnh hưởng tải primary. Hãy chọn theo mức nhất quán mà sản phẩm cần.

### 13.2. Cache invalidation cũng có race

Ví dụ:

~~~text
Worker A: GET bản cũ từ DB
Worker B: UPDATE bản mới, invalidate cache
Worker A: lưu bản cũ vào cache sau khi invalidate
~~~

Kết quả cache lại có bản cũ. Vì vậy, chỉ gửi một lệnh delete cache sau update không phải lúc nào cũng đủ bảo đảm trong hệ thống cạnh tranh mạnh.

Giải pháp có thể gồm **versioning, compare-and-set, TTL thích hợp, hoặc cơ chế đồng bộ cache**; cần xét ngữ nghĩa của từng cache/store. Đừng tuyên bố MongoDB đã vi phạm RYW khi GET thực sự đọc một bản cũ ở cache ứng dụng.

### 13.3. Câu hỏi chẩn đoán quan trọng

Khi vừa cập nhật rồi GET thấy dữ liệu cũ, hãy xác định **GET thật sự lấy từ đâu**:

1. MongoDB primary?
2. MongoDB secondary?
3. Cache của service?
4. CDN/HTTP cache?
5. Trình duyệt hoặc state frontend chưa được cập nhật?
6. Một search index hoặc read model đồng bộ bất đồng bộ?

Hướng xử lý sẽ khác nhau hoàn toàn tùy câu trả lời.

## 14. Đọc secondary với maxStalenessSeconds có đủ không?

MongoDB Driver có chính sách **maxStalenessSeconds** trong một số read preference để giới hạn việc lựa chọn secondary bị chậm hơn một ngưỡng ước lượng.

Mô hình sử dụng:

~~~text
Read preference: secondary/secondaryPreferred
Max staleness: giới hạn độ trễ node được chọn theo tiêu chí driver
~~~

**Max staleness không đồng nghĩa bảo đảm read-your-writes**. Dù node được xem là chỉ trễ vài giây, một ghi mới cách đây một mili giây vẫn có thể chưa được áp dụng trên node đó.

### 14.1. So sánh hai cơ chế

| Cơ chế | Câu hỏi nó trả lời |
|---|---|
| maxStalenessSeconds | Có nên chọn secondary này khi nó có vẻ quá lạc hậu so với các node tham chiếu? |
| Causal session với afterClusterTime | Lần đọc này có được phép trả snapshot trước mốc ghi đã biết trong session không? |

Max staleness là **chính sách lựa chọn node**, không phải bằng chứng node đã áp dụng chính xác lệnh ghi mà client vừa thực hiện. Có thể dùng nó để tránh các secondary chậm quá mức cho workload chấp nhận eventual consistency, nhưng không dùng thay causal consistency.

### 14.2. Đọc gần người dùng không đồng nghĩa đọc mới nhất

Read preference **nearest** chọn node dựa trên độ trễ mạng và các quy tắc lựa chọn của driver. Một node ở khu vực gần ứng dụng có thể replication chậm hơn node ở khu vực xa hơn.

Nếu mục tiêu là **trả kết quả nhanh và có thể hơi cũ**, nearest/secondary là lựa chọn cần đánh giá. Nếu mục tiêu là **vừa ghi xong phải thấy ngay**, cần bổ sung bảo đảm về thời điểm dữ liệu, không chỉ tối ưu latency mạng.

## 15. Dùng version để kiểm tra yêu cầu “đã thấy bản ghi mới”

Trong một số ứng dụng, thay vì chỉ kiểm tra document tồn tại, cần bảo đảm giá trị đã tới **phiên bản ít nhất N**.

Ví dụ:

~~~javascript
{
  _id: "PROFILE-1",
  displayName: "B",
  version: 12,
  updatedAt: ISODate("2026-11-14T10:30:00Z")
}
~~~

Sau khi cập nhật thành công tới version 12, một GET có thể trả version 11 từ secondary/cache. Nếu client biết nó đã quan sát version 12 trong response POST, nó có thể nhận diện kết quả version 11 là **quá cũ so với tiến độ của chính mình**.

### 15.1. Conditional update để tăng version

~~~javascript
db.profiles.updateOne(
  { _id: "PROFILE-1", version: 11 },
  {
    $set: {
      displayName: "B",
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
~~~

Nếu matchedCount = 1, một update đã khớp phiên bản mong đợi và có thể tăng version lên 12. Nếu matchedCount = 0, document đã thay đổi hoặc không tồn tại; ứng dụng phải xử lý **optimistic concurrency conflict** thay vì ghi đè mù quáng.

### 15.2. Version giúp phát hiện stale nhưng không tự giải quyết stale

Nếu GET trả version 11, client có thể:

- Đọc lại từ primary.
- Thử lại secondary theo backoff với giới hạn.
- Chờ một đồng bộ read model/cache hoàn tất.
- Trả thông báo “đang đồng bộ” nếu sản phẩm cho phép.

Tuy nhiên, một con số version **không làm secondary tự áp dụng oplog**. Nếu phải bảo đảm nhân quả ở tầng database, nên dùng causal session đúng điều kiện thay vì chỉ gửi version rồi hy vọng đọc từ bất kỳ node nào sẽ có bản mới.

### 15.3. Version không thay thế kiểm soát truy cập

Nếu response mang version nhưng client không có quyền xem document, backend vẫn phải kiểm tra authentication/authorization. Không dùng một version hoặc operationTime như token truy cập có thể đoán hay chuyển nhượng tùy ý.

## 16. Định hướng khi ứng dụng có nhiều loại truy vấn

Một sản phẩm có thể cần **nhiều mức consistency khác nhau** theo nghiệp vụ, không phải chỉ một readPreference toàn ứng dụng:

| Loại đọc | Mức cần xem xét | Lý do |
|---|---|---|
| GET ngay sau khi tạo đơn trong luồng thanh toán | Primary read và majority write; hoặc causal session phù hợp | Tránh hiển thị “không thấy đơn” ngay sau thành công |
| Giao diện sửa thông tin cá nhân | RYW cho user, xác minh version hoặc causal read | Người dùng mong thấy trường vừa sửa |
| Thống kê doanh thu toàn hệ thống cập nhật theo phút | Có thể đọc secondary, chấp nhận lag xác định | Ưu tiên phân phối tải và throughput |
| Quyết định cấp quyền/bảo mật theo trạng thái mới nhất | Cần mức nhất quán/kiểm soát phù hợp mức rủi ro | Đọc state cũ có thể dẫn đến quyết định sai |
| Hàng đợi nghiệp vụ xử lý theo thứ tự | Causal sequence và điều kiện update nguyên tử | Không đưa ra side effect trước khi thấy trạng thái cần thiết |
| Đọc dữ liệu nhiều collection trong một phiên báo cáo | Snapshot/transaction theo yêu cầu | Tránh mỗi collection được quan sát ở thời điểm khác nhau |
| Xem lịch sử hoạt động chỉ cần gần thời gian thực | Secondary/eventual có thông báo đồng bộ | Có thể đánh đổi tính mới để giảm tải primary |

### 16.1. Đừng dùng mức consistency mạnh cho mọi analytics

Nếu dashboard được làm mới mỗi vài phút, việc yêu cầu linearizable read với từng document có thể tạo chi phí và làm giảm khả năng phục vụ mà không đem lại giá trị tương xứng. Với thống kê, vấn đề còn có thể là **data pipeline delay** chứ không chỉ replication lag.

### 16.2. Đừng dùng eventual consistency cho quyết định không thể đảo ngược

Nếu một process dùng số dư/trạng thái từ secondary để quyết định **trừ tiền, xuất hàng hoặc cấp quyền**, cần đánh giá nguy cơ đọc state cũ. RYW riêng lẻ của một client chưa bảo vệ mọi race giữa nhiều client. Có thể cần:

- Atomic conditional update và unique business constraints.
- Transaction cho các tài nguyên liên quan.
- Đọc/ghi với concern phù hợp và routing chính xác.
- Idempotency key khi request có thể được gửi lại.

**RYW không đồng nghĩa serializability của toàn bộ workflow.** Việc A thấy ghi của chính A không tự ngăn B cạnh tranh thay đổi cùng document.

## 17. Một truy vấn đọc thành công vẫn có thể không trả document mong đợi

Trước khi chẩn đoán sai consistency, kiểm tra **điều kiện truy vấn và dữ liệu**:

~~~javascript
db.orders.insertOne({
  _id: "O-CHECK",
  state: "CREATED",
  amountCents: NumberLong("100000")
});

db.orders.findOne({
  _id: "O-CHECK",
  state: "PAID"
});
~~~

Lần đọc trả null là **đúng filter**, vì document đang có state CREATED chứ không phải PAID; đó không phải bằng chứng replication chậm.

Tương tự, nếu field là **ObjectId** mà query dùng String, hoặc collection/database của reader khác writer, kết quả có thể không khớp dù dữ liệu đã có trên cùng node.

### 17.1. Những điều cần xác minh trước tiên

- Reader và writer có dùng **cùng cluster, database, collection** không?
- _id và các field được so sánh có đúng **BSON type** không?
- Query có thêm filter **tenantId, isDeleted, state** làm loại document không?
- Projection có **loại field** khiến ứng dụng hiểu nhầm là chưa được cập nhật không?
- Có transaction nào **chưa commit hoặc đã abort** không?
- GET có đọc qua cache/read model không?
- Có client khác sửa/xóa document sau khi writer hoàn tất không?
- Lỗi xảy ra **trước hay sau xác nhận ghi majority**?

Chỉ sau khi loại trừ những khả năng này mới nên kết luận dữ liệu “đọc bị stale” do replication hoặc cache.

## 18. Quy trình chẩn đoán khi “POST thành công nhưng GET không thấy”

Một báo cáo sự cố nên dựa trên chứng cứ, không chỉ dựa trên việc người dùng thấy giao diện chưa cập nhật.

### Bước 1. Xác định thời điểm và danh tính của thao tác

Thu thập một mẫu request với:

- **requestId/traceId** dùng để liên kết log.
- **_id hoặc business key** của document đã tạo.
- **Thời điểm bắt đầu và kết thúc lệnh ghi**.
- **Kết quả ghi**: acknowledged, write concern, exception, error label nếu có.
- **Thời điểm bắt đầu lần đọc** và kết quả query.
- **Database/collection/tenant** và BSON type của khóa.

Không lưu toàn bộ payload nhạy cảm vào log nếu không cần thiết. RequestId chỉ là mã truy vết, không thay thế kiểm tra quyền.

### Bước 2. Xác minh thao tác ghi thực sự được xác nhận

Phân biệt:

~~~text
ACK thành công, w:majority
ACK thành công, w:1
Write concern timeout
Network error, không rõ server đã nhận lệnh chưa
Transaction commit result unknown
Validation error, không ghi document
Duplicate key, document tương ứng có thể đã tồn tại
~~~

Mỗi trường hợp đòi hỏi hướng xử lý khác nhau. Đặc biệt, **timeout không tương đương không có dữ liệu**.

### Bước 3. Xác định node phục vụ lần đọc

Kiểm tra **read preference** ở cấp:

- Connection string.
- MongoClient/MongoDatabase/MongoCollection.
- Truy vấn có override riêng.
- Framework repository/service.
- Proxy/router và topology.

Một cấu hình tưởng là primary có thể bị override thành secondaryPreferred ở collection hoặc route ở tầng khác. Khi đọc từ secondary, cần đo replication lag và xác định có causal session hay không.

### Bước 4. Xác định concern và session

| Câu hỏi | Cần tìm ở đâu |
|---|---|
Ghi dùng w:1 hay majority? | WriteConcern cấu hình của operation/client/collection |
Đọc local hay majority? | ReadConcern ở operation/client/collection |
GET dùng primary hay secondary? | ReadPreference và node được driver chọn |
Ghi và đọc có cùng session? | Mã quản lý session của service/driver tracing |
Session causalConsistency có bật? | ClientSessionOptions |
Thứ tự có thật sự write-before-read? | Timeline và xử lý async/future |
GET có lấy từ cache không? | Cache hit/miss và data source |

Không cần ghi log toàn bộ nội dung session token trong sản phẩm chỉ để chẩn đoán. Hãy ưu tiên metadata phù hợp với chính sách bảo mật và công cụ observability đã được cấp quyền.

### Bước 5. Kiểm tra replication và topology

Trên môi trường có quyền phù hợp:

~~~javascript
rs.status();
~~~

Có thể đối chiếu trạng thái của các node và các mốc replication theo output thực tế. Nếu secondary rất chậm, read concern majority mà thiếu causal ordering vẫn có thể thấy snapshot trước ghi vừa xác nhận.

**Không nên cố tạo lag trên production** bằng cách chặn mạng, dừng secondary hoặc sửa cấu hình election. Thí nghiệm gây sự cố phải được làm trên cluster thử nghiệm riêng.

### Bước 6. Đối chiếu cùng document ở các nguồn đọc

Nếu được phép, so sánh kết quả với cùng filter, cùng BSON type:

~~~javascript
db.orders.findOne({
  _id: "O-240-001"
});
~~~

Trên một kết nối primary và một kết nối secondary được cấu hình riêng biệt. Nếu primary thấy version 12 còn secondary chỉ thấy version 11, đó là chỉ báo hữu ích về độ trễ hoặc node/snapshot, nhưng cần xác minh read preference thực sự và điều kiện thời gian.

Nếu cả primary và secondary đều thấy version 12 nhưng API vẫn trả 11, ưu tiên điều tra **cache hoặc read model ngoài MongoDB**.

### Bước 7. Chọn phương án khắc phục theo nguyên nhân

| Quan sát | Hướng xử lý |
|---|---|
Read từ secondary lag, không có causal session | Dùng primary cho đường đọc nhạy cảm hoặc cấu hình causal majority session |
Read majority nhưng không thấy ghi từ request trước | Kiểm tra causal metadata và session boundary |
Write w:1 bị rollback sau election | Xem lại majority write concern và chiến lược retry/idempotency |
Write bị timeout, kết quả không rõ | Đối soát qua business key, không tạo id mới vô điều kiện |
Client gọi GET trước khi future ghi hoàn tất | Đảm bảo await/order trong code |
Transaction chưa commit | Chỉ đọc ngoài transaction sau khi commit được xác nhận |
Cache trả document cũ | Invalidation, version, bypass hoặc sửa chiến lược cache |
Query sai kiểu/filter/collection | Sửa truy vấn/mapping, không tăng concern vô ích |
Secondary cần lâu để bắt kịp | Thiết lập timeout, backoff, metrics, cân nhắc read primary |
Phiên bản document bị thay bởi client khác | Dùng optimistic concurrency/version hoặc transaction |

### Bước 8. Theo dõi sau thay đổi

Đừng chỉ kiểm tra một request thành công. Theo dõi:

- **Tỷ lệ GET không tìm thấy record ngay sau POST đã ACK**.
- **Tỷ lệ response version nhỏ hơn version client yêu cầu**.
- **Replication lag** và số lần causal read phải chờ/timeout.
- **Độ trễ p95/p99** của request sau thay đổi read preference.
- **Thời gian failover/server selection** và lỗi liên quan.
- **Tỷ lệ cache hit trả bản cũ** hoặc số lần bypass cache.
- **Số request UNKNOWN/đối soát** do lỗi ghi.

Những metric này phải được thiết kế/ghi nhận trong hệ thống quan sát tương ứng; chúng không tự xuất hiện dưới đúng tên trong MongoDB.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Insert có ACK thì mọi secondary thấy ngay” | Secondary replication bất đồng bộ | Cần mốc causal hoặc đọc primary |
| “w:majority nghĩa là tất cả node đều có dữ liệu” | Majority không phải toàn bộ thành viên | Secondary ngoài đa số xác nhận vẫn có thể lag |
| “ReadConcern majority luôn trả phiên bản mới nhất” | Majority snapshot không nhất thiết là thời điểm ghi vừa xong | Cần causal ordering/afterClusterTime nếu đọc secondary |
| “Chỉ bật causalConsistency là đủ” | Bảo đảm causal của MongoDB đòi hỏi concern và thứ tự phù hợp | Majority writes + majority reads + cùng causal session tuần tự |
| “Cùng MongoClient là cùng session” | Client có thể tạo nhiều session độc lập | Truyền cùng ClientSession rõ ràng |
| “Cùng user nhưng hai HTTP request chắc chắn cùng causal session” | Request có thể đi đến service/thread khác | Cần lựa chọn thiết kế xuyên request rõ ràng |
| “ReadPreference secondaryPreferred luôn đọc secondary” | Có thể fallback primary | Quan sát node thực tế nếu cần |
| “ReadPreference nearest nghĩa là mới nhất” | Nearest là chính sách latency/topology | Không bảo đảm nhân quả |
| “maxStalenessSeconds thay afterClusterTime” | Max staleness chỉ lọc node tương đối chậm | Không thay causal session |
| “Read concern linearizable áp dụng cho mọi aggregation” | Có phạm vi hỗ trợ riêng | Dùng đúng thao tác, primary, majority write |
| “ReadConcern snapshot luôn đọc dữ liệu mới nhất ngoài transaction” | Snapshot được giữ theo mốc đọc | Dùng transaction/snapshot đúng mục đích |
| “Find trong transaction thấy ghi thì client khác cũng thấy” | Ghi chưa commit chưa visible bên ngoài | Phải commit, đọc ngoài theo concern phù hợp |
| “w:1 trên primary đủ bền vững sau failover” | Ghi chưa majority có thể rollback | Dùng majority theo yêu cầu bền vững |
| “Timeout nghĩa là insert chưa xảy ra” | Có thể ghi xong rồi mất phản hồi | Đối soát/retry idempotent |
| “Mọi write đã majority thì GET không bao giờ timeout” | Secondary chờ bắt kịp, election/network vẫn có thể lỗi | Có timeout/backoff và error handling |
| “Read đã thấy X thì lần sau phải đúng y nguyên X” | Client khác có thể cập nhật document sau đó | RYW bảo vệ quan hệ nhân quả, không khóa dữ liệu vĩnh viễn |
| “Thấy dữ liệu cũ là lỗi replication” | Có thể do cache, mapping hoặc filter sai | Xác định nguồn đọc thực tế |
| “Có version trong response là tự được RYW” | Version chỉ giúp phát hiện bản cũ | Cần chờ/route đúng nguồn hoặc causal read |
| “Causal session ngăn hai client update lost update” | RYW không phải atomic conflict prevention | Dùng compare-and-set, unique index, transaction |
| “Bật majority ở mọi API không có chi phí” | Có thể ảnh hưởng latency/availability | Chọn theo mức nhất quán cần thiết |

## 20. Một kịch bản ứng dụng hoàn chỉnh

Giả sử hệ thống tạo order, sau đó màn hình người dùng gọi GET order. Yêu cầu nghiệp vụ:

> Khi API xác nhận đơn đã tạo bền vững, lần đọc kế tiếp của người dùng không được báo “đơn không tồn tại” chỉ vì secondary chậm.

Một cách triển khai thực dụng:

### 20.1. Ghi với business key ổn định

Client tạo **clientRequestId** một lần cho một ý định đặt hàng, backend có unique index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, clientRequestId: 1 },
  { unique: true }
);
~~~

Backend insert order với write concern majority và trả **orderId**, **version** sau khi có xác nhận.

### 20.2. Chọn đường đọc có yêu cầu RYW

Nếu GET được thực hiện từ service khác và không truyền causal session:

- Cấu hình **đọc primary** cho endpoint order detail cần tính mới.
- Hoặc thiết kế truyền causal metadata và cấu hình majority read/write phù hợp nếu phải đọc secondary.
- Hoặc trả lại order đã tạo từ POST và chỉ GET sau khi có tín hiệu read model bắt kịp, nếu hợp đồng cho phép.

Không coi một GET qua secondaryPreferred không có session là chắc chắn thấy order ngay.

### 20.3. Nếu chỉ có eventual read model

Một API có thể trả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "orderId": "O-900",
  "state": "INDEXING",
  "message": "Order created; read model is synchronizing"
}
~~~

Đây là lựa chọn **chấp nhận consistency trễ và làm rõ cho client**, không phải bảo đảm RYW của MongoDB read model. Phải có nguồn sự thật và cơ chế đối soát khi đồng bộ quá lâu.

### 20.4. Mục tiêu cuối cùng: API nhất quán theo hợp đồng

Sự đúng đắn không chỉ nằm ở một lần findOne thành công. Hệ thống cần:

- **Bản ghi order không bị tạo trùng** khi request retry.
- **Thông tin ghi được xác nhận** theo mức bền vững đã cam kết.
- **Đường đọc GET** không vô tình đổi sang node/cache stale nếu API hứa trả ngay.
- **Client nhìn thấy version phù hợp**, hoặc nhận trạng thái “đang đồng bộ” rõ ràng.
- **Lỗi mạng/failover được xử lý có kiểm soát**, không âm thầm tạo đơn thứ hai.

## 21. Bài tập thực hành và tình huống

Các bài tập sử dụng database **ryw_lab** và collection **orders/profiles** đã giới thiệu. Nếu cần kiểm tra secondary, causal session hoặc failover, hãy dùng **replica set thử nghiệm**; với standalone MongoDB chỉ nên làm phần CRUD và phân tích logic. Không thực hiện thao tác gây lag, xóa dữ liệu, tắt node hoặc điều chỉnh concern của cluster production khi chưa có phê duyệt vận hành.

### Bài 1. Ghi xong rồi đọc từ cùng primary

Giả sử mongosh kết nối primary và collection **orders** chưa có _id O-EX-1:

~~~javascript
db.orders.insertOne(
  { _id: "O-EX-1", state: "CREATED" },
  { writeConcern: { w: 1 } }
);

db.orders.findOne({ _id: "O-EX-1" });
~~~

**Câu hỏi:** Trong điều kiện primary không đổi, không có ghi cạnh tranh và insert ACK thành công, lần đọc thường trả gì? Có thể kết luận ghi chắc chắn không rollback sau mọi failover không?

**Định hướng:** Lần đọc từ cùng primary thường thấy document. Nhưng ACK w:1 không đồng nghĩa đạt majority replication; một lần đọc thấy thành công không chứng minh khả năng sống qua mọi failover.

### Bài 2. Majority write nhưng đọc secondary không có session

Replica set gồm P, S1 và S2. Lệnh insert X nhận xác nhận majority sau khi P và S1 có X, còn S2 chưa áp dụng X.

**Câu hỏi:**

1. Lần đọc ngay từ S2 có chắc thấy X không?
2. Nếu đặt read concern majority tại S2 mà không có causal session, đã đủ chưa?
3. Khi nào có thể kỳ vọng đọc được X từ S2?

**Định hướng:** Chưa chắc; S2 có thể chưa bắt kịp. Read concern majority không tự mang mốc causal từ ghi. Khi S2 đã áp dụng và có snapshot majority phù hợp, nó có thể đọc được X; muốn ràng buộc thứ tự ghi–đọc, dùng causal session và concern đúng.

### Bài 3. Chọn đúng các thành phần của causal RYW

Một developer nói:

> Chỉ cần cấu hình secondaryPreferred và causalConsistency=true, mặc định mọi lần đọc sẽ thấy lần ghi trước.

Hãy bổ sung các điều kiện còn thiếu.

**Đáp án định hướng:**

- Dùng **cùng causal session** hoặc chuyển causal metadata hợp lệ.
- **Lệnh ghi majority-acknowledged**, lệnh đọc read concern majority.
- Ghi phải hoàn tất trước khi đọc bắt đầu.
- Các thao tác trên session chạy tuần tự.
- Deployment/driver hỗ trợ session.
- Nếu secondary đang lag, read có thể chờ hoặc timeout.

SecondaryPreferred chỉ là chính sách chọn node, không thay các điều kiện này.

### Bài 4. Thí nghiệm một session trong mongosh

Dùng một requestId chưa tồn tại, tạo session:

~~~javascript
const session = db.getMongo().startSession({
  causalConsistency: true
});

const sdb = session.getDatabase("ryw_lab");

try {
  printjson(sdb.runCommand({
    insert: "orders",
    documents: [
      {
        _id: "O-EX-SESSION-1",
        requestId: "R-EX-SESSION-1",
        state: "CREATED"
      }
    ],
    writeConcern: { w: "majority", wtimeout: 10000 }
  }));

  printjson(sdb.runCommand({
    find: "orders",
    filter: { _id: "O-EX-SESSION-1" },
    readConcern: { level: "majority" }
  }));
} finally {
  session.endSession();
}
~~~

**Câu hỏi:** Code có những yếu tố nào quan trọng cho quan hệ nhân quả? Có thể khẳng định read trong bài này đã chạy từ secondary chỉ vì readConcern = majority không?

**Định hướng:** Cùng session, ghi majority, đọc majority và thứ tự tuần tự. Không, read concern không phải read preference; cần cấu hình chọn secondary riêng nếu muốn kiểm tra node đó.

### Bài 5. Session mới trong HTTP request thứ hai

POST được service A xử lý với session S1; GET được service B xử lý với S2 và secondary read. Không có metadata nhân quả được chuyển qua.

**Câu hỏi:** Điều gì có thể xảy ra khi GET đến ngay sau POST? Đề xuất hai lựa chọn khắc phục.

**Định hướng:** S2 không biết mốc nhân quả từ S1, secondary có thể stale. Có thể route GET sang primary theo hợp đồng hoặc thiết kế cơ chế chuyển causal token/giữ một luồng session khi phù hợp. Trả order từ POST rồi đồng bộ giao diện cũng là phương án cho một số sản phẩm.

### Bài 6. Mất phản hồi ghi và nguy cơ duplicate

Client gửi một yêu cầu tạo order, MongoDB có thể đã ghi thành công nhưng backend gặp timeout trước khi nhận phản hồi. Client retry bằng một orderId mới.

**Câu hỏi:** Có nguy cơ gì? Cơ chế nào bổ sung cho RYW?

**Định hướng:** Có thể tạo order trùng. Cần requestId/idempotency key ổn định, unique constraint phù hợp, đọc đối soát trạng thái và retry có giới hạn. Causal consistency không tự nhận biết hai yêu cầu nghiệp vụ khác nhau là một hành động.

### Bài 7. Transaction trước và sau commit

Transaction T:

~~~text
T: insert document X
T: find X -> thấy X
T: chưa commit
Client khác: find X -> ?
T: commit
Client khác: read secondary -> ?
~~~

**Câu hỏi:** Client khác có được nhìn thấy X trước commit không? Sau commit có chắc secondary bất kỳ thấy ngay X không?

**Định hướng:** Không nhìn thấy ghi chưa commit. Sau commit, secondary có thể cần thời gian áp dụng; nếu cần causal RYW, phải có quan hệ mốc nhân quả và concern đúng, hoặc đọc primary.

### Bài 8. Linearizable và snapshot

Hãy chọn giữa hai nhu cầu:

1. Đọc một document trạng thái khóa với yêu cầu nhận biết các ghi majority đã hoàn tất trước khi read bắt đầu theo thứ tự thời gian thực.
2. Đọc thống nhất số dư và nhiều document giao dịch tại một snapshot phù hợp.

**Định hướng:** (1) xem read concern linearizable trên primary với điều kiện áp dụng; (2) xem transaction/snapshot theo tính năng hỗ trợ. Không dùng linearizable như công tắc thay mọi transaction nhiều document.

### Bài 9. Cùng write majority nhưng GET vẫn trả bản cũ

API POST cập nhật displayName từ A sang B, MongoDB primary xác nhận majority. GET trả A. Log cho thấy GET là cache hit từ Redis.

**Câu hỏi:** Có nên tăng read concern của MongoDB từ local lên linearizable là giải pháp đầu tiên không?

**Định hướng:** Không. GET không đọc MongoDB nên đổi concern không sửa bản cũ ở Redis. Cần điều tra cache invalidation/version hoặc bypass theo hợp đồng API.

### Bài 10. maxStalenessSeconds

Một service dùng **readPreference secondaryPreferred** và giới hạn maxStalenessSeconds = 120 trong cấu hình được hỗ trợ.

**Câu hỏi:** Có thể bảo đảm mọi GET trong vòng 100 ms sau POST sẽ thấy document không?

**Đáp án:** Không. Chọn secondary không quá lạc hậu theo ngưỡng chỉ là tiêu chí chọn node, không có nghĩa node đã áp dụng lệnh ghi vừa xảy ra. Causal session hoặc primary read có thể cần thiết cho RYW.

### Bài 11. Optimistic concurrency và version

Document đang có:

~~~javascript
{
  _id: "PROFILE-EX",
  displayName: "A",
  version: 7
}
~~~

Hai client cùng đọc version 7 rồi muốn cập nhật. Hãy viết update cho client A:

~~~javascript
db.profiles.updateOne(
  {
    _id: "PROFILE-EX",
    version: 7
  },
  {
    $set: { displayName: "B" },
    $inc: { version: 1 }
  }
);
~~~

**Câu hỏi:** Nếu A cập nhật thành công, B thực hiện cùng filter version 7 còn matchedCount = bao nhiêu? Điều này liên quan thế nào đến RYW?

**Định hướng:** Với document đã chuyển version 8 và không có cập nhật ngược, B không còn khớp, matchedCount = 0. Đây là **chống lost update/đồng thời**; nó bổ sung nhưng không thay read-your-writes khi lần đọc được route sang secondary.

### Bài 12. Đọc từ primary nhưng query trả null

Insert:

~~~javascript
db.orders.insertOne({
  _id: "O-EX-12",
  state: "CREATED",
  tenantId: "T-A"
});
~~~

Đọc:

~~~javascript
db.orders.findOne({
  _id: "O-EX-12",
  state: "PAID",
  tenantId: "T-A"
});
~~~

**Câu hỏi:** Việc null có chứng minh primary chưa đồng bộ không?

**Đáp án:** Không. Filter yêu cầu PAID trong khi document có CREATED. Cần kiểm tra điều kiện truy vấn, BSON type, tenant, projection và collection trước khi suy luận về consistency.

### Bài 13. Tư duy thiết kế cho hai workload

Hãy đề xuất cấu hình/kiến trúc phù hợp cho:

- **Luồng A:** vừa lưu địa chỉ mới, người dùng phải thấy địa chỉ mới trong lần GET kế tiếp.
- **Luồng B:** dashboard thống kê số lượng đơn, cập nhật theo chu kỳ một phút và chấp nhận lag vài giây.

**Định hướng:** Luồng A cần RYW — có thể đọc primary hoặc dùng causal majority session nếu cần đọc secondary. Luồng B có thể dùng secondary/read model bất đồng bộ với metric replication/pipeline lag và thông tin độ mới. Không cần buộc hai luồng cùng mức consistency nếu nghiệp vụ khác nhau.

### Bài 14. Khi secondary chưa bắt kịp

Java Sync Driver dùng một causal session, ghi w:majority và đọc secondary read concern majority. Node secondary đang chậm hơn mốc ghi, còn operation có giới hạn thời gian.

**Câu hỏi:** Một lần đọc trả lỗi timeout có nghĩa cơ chế RYW “trả dữ liệu sai” không? Nên làm gì?

**Định hướng:** Không. Read không trả kết quả sai cũ; nó không thể phục vụ tại mốc nhất quán được yêu cầu trong giới hạn thời gian. Ứng dụng cần backoff/retry có giới hạn, chuyển sang primary nếu hợp đồng cho phép, hoặc trả lỗi rõ ràng. Không fallback sang dữ liệu cũ mà vẫn tuyên bố đã đáp ứng RYW.

## 22. Bảng tự đối chiếu khi xây dựng một API đọc sau ghi

Trước khi triển khai, hãy ghi rõ các quyết định của hệ thống:

| Câu hỏi | Ví dụ câu trả lời cần có |
|---|---|
Ghi được coi là thành công ở mức nào? | w:majority hay w:1 theo yêu cầu bền vững |
Lần đọc kế tiếp đi đến đâu? | primary/secondary/nearest/cache |
Có cần read-your-writes không? | Có với order detail, có thể không với analytics |
Lệnh ghi và đọc có dùng chung causal session không? | Có/không; nếu không, định tuyến đọc thế nào? |
Đọc dùng read concern gì? | local, majority, snapshot hoặc linearizable theo mục đích |
Ghi được xác nhận rồi mới đọc chứ? | Có await/sequence rõ ràng |
Nếu secondary chậm, ứng dụng làm gì? | Chờ, retry, primary fallback hoặc lỗi theo hợp đồng |
Nếu mất phản hồi ghi thì sao? | Đối soát bằng requestId, retry idempotent |
GET có cache không? | Có invalidation/version/bypass theo yêu cầu |
Nếu client khác cập nhật cùng document? | Version/CAS hoặc transaction theo nghiệp vụ |
Nếu failover giữa các bước? | Chiến lược timeout/retry và không khẳng định sai về rollback |
Mức latency chấp nhận được? | Mục tiêu p95/p99, quan sát replication lag |

Khi trả lời rõ những câu hỏi này, việc chọn concern và session trở thành một quyết định kỹ thuật có thể giải thích, thay vì một chuỗi cấu hình được sao chép từ ví dụ khác.

## 23. Tóm tắt nguyên lý

~~~text
                     WRITE X
                        |
                  Write concern
                        |
           +------------+-------------+
           |                          |
         w:1                      w:majority
           |                          |
     Primary ACK                Majority ACK
           |                          |
           v                          v
   Đọc primary thường thấy X    Cần đọc sau ghi?
   nhưng rollback vẫn có thể       /          \
   xảy ra qua failover            Có          Không
                                 |             |
                          Đọc primary hoặc    Chọn eventual
                          causal session      theo workload
                                 |
                        +--------+---------+
                        |                  |
                 Primary read       Secondary read
                        |                  |
                 concern phù hợp    majority read
                                     + causal token
                                     + cùng session
                                     + thứ tự tuần tự
                        |                  |
                        +--------+---------+
                                 |
                                 v
                       Read thành công tại
                       mốc đúng yêu cầu
                       hoặc chờ/lỗi rõ ràng
~~~

**Những điểm cần nhớ:**

1. **Đọc từ cùng primary sau khi ghi thành công** là trường hợp đơn giản thường thấy hiệu ứng ghi, nhưng **w:1 không bảo đảm bền vững qua failover**.
2. **w:majority không làm mọi secondary cập nhật tức thì**. Một secondary đọc majority mà không biết mốc ghi trước vẫn có thể chưa bắt kịp.
3. Muốn bảo đảm **read-your-writes trên secondary trong causal session**, cần **majority write, majority read, session causal và thao tác tuần tự**.
4. **Causal read có thể chờ hoặc lỗi**, thay vì trả một snapshot quá cũ. Consistency không phải cam kết luôn có kết quả ngay.
5. **Transaction read-your-own-writes** và **đọc sau commit từ một session khác** là hai bài toán khác nhau.
6. **Linearizable read** phục vụ mức real-time mạnh hơn trong phạm vi hỗ trợ; **snapshot** phục vụ ảnh chụp nhất quán, không nên dùng thay nhau.
7. **Timeout, cache và truy vấn sai filter** cũng có thể tạo biểu hiện “không thấy dữ liệu vừa ghi”. Cần điều tra đường đi end-to-end, không chỉ chỉnh một read concern.
8. **RYW không thay idempotency, unique constraints hay atomic updates**. Những cơ chế đó vẫn cần khi nhiều client/worker có thể tạo thao tác trùng hoặc cạnh tranh.

## 24. Kết luận

MongoDB không có một công tắc duy nhất bảo đảm “mọi nơi đọc lại ngay lập tức thấy dữ liệu vừa ghi” bất kể node, session, concern và sự cố. Một thiết kế đúng cần bắt đầu từ **phạm vi quan hệ nhân quả**, lựa chọn **mức bền vững của ghi**, **node phục vụ đọc**, **read concern**, và phương án xử lý khi node chưa bắt kịp.

Với các luồng CRUD đơn giản, đọc từ **primary sau khi ghi được xác nhận** thường đáp ứng nhu cầu hiển thị ngay; với yêu cầu bền vững nên dùng mức write concern phù hợp, thường là majority. Với luồng **ghi rồi đọc từ secondary**, một **causally consistent session kết hợp majority write + majority read** là cơ chế MongoDB quan trọng để bảo vệ read-your-writes. Với dữ liệu nhiều document hoặc yêu cầu real-time mạnh hơn, cần cân nhắc transaction/snapshot hay linearizable read đúng phạm vi.

Quan trọng hơn, hãy xem cả hệ thống: **requestId, retry, failover, cache, version và logic nghiệp vụ**. Khi những thành phần đó được thiết kế đồng bộ, ứng dụng có thể đưa ra một lời hứa rõ ràng và thực thi được: sau khi ghi thành công theo hợp đồng, những lần đọc có liên quan sẽ không âm thầm quay về dữ liệu cũ, hoặc sẽ báo rõ rằng hiện chưa thể phục vụ ở mức nhất quán được yêu cầu.

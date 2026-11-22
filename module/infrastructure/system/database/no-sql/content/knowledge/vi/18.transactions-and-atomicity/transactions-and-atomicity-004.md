# Phân biệt batch tối ưu truyền dữ liệu với batch có bảo đảm nguyên tử

## 1. Một request chứa nhiều thao tác có phải một giao dịch không?

Giả sử một ứng dụng bán hàng muốn ghi 100 dòng chi tiết đơn hàng. Thay vì gửi 100 request riêng tới cơ sở dữ liệu, ứng dụng gom chúng thành một lời gọi **batch**. Việc này thường giúp giảm chi phí mạng và tăng thông lượng.

Nhưng nếu thao tác thứ 61 thất bại, chuyện gì xảy ra với 60 thao tác trước?

- Có thể 60 thao tác đầu đã thành công và 40 thao tác còn lại chưa thực hiện.
- Có thể một số thao tác được thực hiện không theo thứ tự gửi.
- Có thể các thao tác thành công/thất bại được trả về riêng trong một kết quả batch.
- Có thể cơ sở dữ liệu cung cấp một cơ chế **transaction** bảo đảm toàn bộ nhóm thay đổi hoặc không thay đổi gì.
- Có thể một hệ gọi tính năng là **atomic batch**, nhưng phạm vi atomicity chỉ áp dụng tại một partition, không có isolation tổng quát khi đọc nhiều partition.

Những khả năng này không thể suy ra chỉ từ tên phương thức có chữ Batch, Bulk hoặc Pipeline.

**Câu hỏi cốt lõi của bài học:** Khi gom nhiều thao tác vào một lần gọi, ta đang **tối ưu truyền dữ liệu** hay đang yêu cầu **một đơn vị thay đổi nguyên tử**?

Đây là bài thuộc chương **Giao dịch và nguyên tử** của module **Database No SQL**. Các ví dụ xét MongoDB, DynamoDB, Redis, Cassandra/ScyllaDB và Elasticsearch/OpenSearch; đồng thời dùng tình huống nghiệp vụ thanh toán, tồn kho, đơn hàng và nhật ký hoạt động để chỉ ra cách thiết kế an toàn.

Sau khi học, bạn sẽ có thể:

1. Phân biệt batch, pipeline, bulk API, transaction và phạm vi atomicity.
2. Đọc đúng bảo đảm của một API thay vì đoán theo tên.
3. Phân tích lỗi một phần, timeout và retry sau batch.
4. Chọn batch hiệu năng hoặc transaction theo invariant nghiệp vụ.
5. Thiết kế idempotency, điều kiện ghi, outbox, saga hoặc reconciliation khi transaction không đủ phạm vi.
6. Đo latency, throughput và write amplification mà không đánh đồng tốc độ với tính đúng đắn.

## 2. Hai nghĩa hoàn toàn khác nhau của “batch”

### 2.1. Batch để tối ưu truyền dữ liệu

**Transport/performance batch** gom nhiều thao tác thành một request hoặc một luồng truyền:

~~~text
Không batch:
Client -> PUT A -> ACK
Client -> PUT B -> ACK
Client -> PUT C -> ACK

Có batch:
Client -> [PUT A, PUT B, PUT C] -> Kết quả
~~~

Mục tiêu chính:

- Giảm số vòng đi–về mạng (round trips).
- Giảm overhead thiết lập request, xử lý protocol và xác thực theo lần gọi.
- Tăng số thao tác được gửi mỗi đơn vị thời gian.
- Có thể cho driver/server gom công việc thành nhóm hiệu quả hơn.

**Không có bảo đảm nguyên tử mặc định:** Nếu A và B thành công nhưng C thất bại, hệ có thể giữ A/B.

### 2.2. Batch có bảo đảm nguyên tử

**Atomic batch/transactional group** có một hợp đồng về việc nhóm thay đổi được áp dụng như một đơn vị:

~~~text
Transaction [PUT A, PUT B, PUT C]
  -> COMMIT: cả nhóm cùng có hiệu lực theo phạm vi bảo đảm.
  -> ABORT: không thao tác nào của nhóm được commit.
~~~

Mục tiêu chính là **giữ invariant nghiệp vụ** giữa nhiều thao tác. Ví dụ một chuyển khoản cần cả ghi giảm và ghi tăng số dư theo nguyên tắc đã định, thay vì để lại trạng thái chỉ giảm tiền một phía.

Tuy nhiên, **atomicity không đồng nghĩa toàn bộ ACID**. Một nhóm được gọi là atomic có thể không cung cấp snapshot isolation, serializability hoặc transaction xuyên nhiều dịch vụ. Phải đọc cả phạm vi và mức isolation.

### 2.3. Hai loại batch có thể kết hợp

Một transaction có thể chứa nhiều thao tác và được truyền hiệu quả qua một lời gọi; nhưng đó là hai thuộc tính độc lập:

~~~text
Thuộc tính 1: Có gom request để giảm RTT không?
Thuộc tính 2: Có bảo đảm nguyên tử cho nhóm thao tác không?
~~~

Ta có bốn tình huống:

| | Không bảo đảm nguyên tử cả nhóm | Có bảo đảm nguyên tử cả nhóm |
|---|---|---|
| Nhiều request | Các lệnh độc lập thông thường | Transaction trải nhiều request trong phạm vi phiên giao dịch |
| Một request/batch | Bulk write, pipeline, batch API tối ưu thông lượng | Transaction API nhận một danh sách hành động |

**Một request không phải bằng chứng có transaction. Nhiều request cũng không có nghĩa chắc chắn không có transaction**, nếu cơ sở dữ liệu hỗ trợ một phiên giao dịch được mở, rồi commit sau.

## 3. Atomicity là gì? Không nên nhầm với các bảo đảm khác

### 3.1. Atomicity

Trong một transaction có bảo đảm nguyên tử đúng nghĩa, nhóm thay đổi được xem là **một đơn vị commit hoặc abort** theo phạm vi được định nghĩa.

Một transaction dự định:

~~~text
Giảm balance của ví A: 100.000
Tăng balance của ví B: 100.000
~~~

Nếu transaction abort, không được để lại trạng thái giảm tiền A nhưng B chưa nhận tiền.

Trong thực tế, cần phân biệt trạng thái **đang xử lý**, **đã commit**, **đã rollback/abort** và **không rõ kết quả do timeout**. Ngay cả khi server có transaction nguyên tử, client có thể không nhận được phản hồi commit.

### 3.2. Isolation

**Isolation** mô tả cách các transaction hoặc thao tác khác quan sát sự thay đổi trong khi nhóm đang thực thi.

Giả sử A và B đang được cập nhật:

~~~text
T1: cập nhật A
T1: cập nhật B

T2: đọc A, đọc B
~~~

Nếu cơ chế chỉ bảo đảm một dạng atomicity cuối cùng mà **không có isolation xuyên nhiều item**, T2 có thể tạm thời nhìn thấy A mới và B cũ, tùy hệ.

Một transaction ACID với mức isolation phù hợp có thể ngăn những hiện tượng nhất định, nhưng **không phải mọi transaction NoSQL đều serializable trong mọi loại read hoặc xuyên mọi Region**.

### 3.3. Consistency

**Consistency** có ít nhất hai cách dùng dễ nhầm:

- **Transaction consistency:** Invariant nghiệp vụ được giữ qua các thao tác, ví dụ số dư không âm, đơn hàng có trạng thái hợp lệ.
- **Replica/read consistency:** Dữ liệu đọc có mới nhất không, replica có hội tụ chưa, đọc strong hay eventual?

Một transaction ghi thành công ở bảng nguồn không có nghĩa mọi **GSI, cache và search index** đã cập nhật tức thì.

### 3.4. Durability

**Durability** nói về việc dữ liệu commit còn được bảo toàn qua những sự cố trong phạm vi hệ hứa hẹn. Durability không được suy chỉ từ việc gửi một request bulk.

Ví dụ một batch không nguyên tử có thể chứa các ghi riêng lẻ bền vững: A đã commit và sống sót sau crash, còn B thất bại. Nó có durability cho A nhưng không có atomicity cho cả nhóm.

### 3.5. Bảng phân biệt ngắn

| Thuộc tính | Câu hỏi |
|---|---|
| Batching | Có gom nhiều thao tác để giảm overhead không? |
| Atomicity | Nhóm thay đổi có commit/abort như một đơn vị không? |
| Isolation | Transaction khác có thể thấy trạng thái trung gian nào? |
| Consistency nghiệp vụ | Các invariant có được bảo vệ không? |
| Read consistency | Reader có thể thấy bản sao cũ không? |
| Durability | Mutation đã commit có được giữ theo mức cam kết khi lỗi không? |
| Idempotency | Gửi lại cùng yêu cầu có gây tác dụng phụ lặp không? |

Thiết kế đúng cần trả lời **từng câu**, không chỉ ghi chú “batch = true”.

## 4. Đường truyền được tối ưu ra sao?

### 4.1. Chi phí round trip

Giả sử mỗi request có thời gian chờ mạng \(L\), còn xử lý một thao tác mất \(s\). Với \(n\) request gửi tuần tự, một mô hình rất đơn giản:

\[
T_{\text{sequential}} \approx n(L+s).
\]

Nếu gom n thao tác trong một request và server xử lý tương tự:

\[
T_{\text{batch}} \approx L + ns + T_{\text{serialize}} + T_{\text{response}}.
\]

Ví dụ minh họa:

~~~text
n = 100 thao tác
RTT L = 8 ms
Server xử lý s = 0,5 ms/thao tác

100 request tuần tự:
  100 x (8 + 0,5) = 850 ms

1 batch, chưa tính serialization:
  8 + 100 x 0,5 = 58 ms
~~~

Đây chỉ là **mô hình lý tưởng hóa**, không phải benchmark của một database cụ thể. Client đồng thời, connection pooling, server parallelism, payload lớn, rate limit, replica ACK và transaction coordination sẽ thay đổi kết quả.

### 4.2. Pipelining khác batching

**Pipelining** cho phép gửi nhiều lệnh mà không phải đợi response từng lệnh:

~~~text
Client: CMD A -> CMD B -> CMD C
Server:          ACK A -> ACK B -> ACK C
~~~

Các lệnh vẫn có thể là **những lệnh độc lập**, được xử lý lần lượt theo ngữ nghĩa của hệ.

**Batch request** là một lời gọi chứa danh sách thao tác. Cả hai đều giúp giảm round trips, nhưng không tự tạo transaction.

### 4.3. Gửi đồng thời cũng không phải transaction

Client có thể gửi 100 PutItem bất đồng bộ cùng lúc để giảm thời gian tổng. Không có nghĩa 100 PutItem sẽ cùng thành công hoặc cùng thất bại.

Vì thế phải phân biệt:

- Sequential execution.
- Concurrent execution.
- Pipelined execution.
- Bulk/batch API.
- Transactional execution.

Chúng là các **cách tổ chức việc thực thi**, còn atomicity là **hợp đồng tính đúng đắn**.

### 4.4. Batch quá lớn có thể phản tác dụng

Một batch khổng lồ có thể:

- Vượt giới hạn request hoặc số hành động.
- Tăng thời gian serialize và bộ nhớ tạm.
- Bị timeout hoặc throttling.
- Làm retry tốn kém.
- Gây hot partition hoặc tranh chấp lock.
- Làm khó xác định item nào đã thành công.
- Kéo dài giao dịch và tăng xung đột nếu dùng transaction.

Vì vậy **batch size có giá trị tối ưu theo workload**, không phải “càng lớn càng nhanh”.

## 5. Một tình huống lỗi một phần

Ứng dụng ghi ba item:

~~~text
1. PUT order O1001
2. PUT audit event E1001
3. PUT notification N1001
~~~

Giả sử item notification không hợp lệ hoặc vùng lưu của nó tạm thời quá tải.

Với **batch tối ưu truyền dữ liệu**:

~~~text
O1001: SUCCESS
E1001: SUCCESS
N1001: FAILED
~~~

Tập dữ liệu có thể ở trạng thái một phần. Ứng dụng phải xác định retry N1001, đưa vào hàng chờ, hoặc xử lý theo một quy trình khác.

Với **transaction nguyên tử trong cùng phạm vi hỗ trợ**:

~~~text
COMMIT cả ba
hoặc
ABORT cả ba
~~~

Nhưng ngay cả transaction đó cũng **không bao phủ** việc gửi email ra ngoài hoặc đẩy webhook tới dịch vụ khác chỉ vì các lệnh ấy nằm trong một function của ứng dụng.

**Quy tắc:** Trước khi chọn API batch, hãy hỏi “Nếu thao tác giữa nhóm thất bại, trạng thái được phép còn lại là gì?”

## 6. Xác định invariant nghiệp vụ trước khi chọn API

### 6.1. Invariant cần nguyên tử

Ví dụ hệ đặt vé có:

~~~text
Seat S101:
  status = AVAILABLE

Booking B1001:
  status = CONFIRMED
~~~

Một quy tắc:

> Không được có booking CONFIRMED cho ghế S101 nếu ghế vẫn được phép bán đồng thời cho booking khác.

Ứng dụng có thể cần conditional write hoặc transaction để đảm bảo chỉ một booking giành được ghế. Nếu chỉ gửi hai Put/Update trong batch không nguyên tử, có thể tạo booking nhưng chưa đánh dấu ghế, hoặc ngược lại.

### 6.2. Invariant không đòi mọi bản sao tức thời

Ví dụ sau khi tạo đơn hàng, ứng dụng muốn cập nhật một bảng analytics:

~~~text
Order O1001 -> đã commit ở nguồn.
DailySalesSummary -> có thể cập nhật trễ vài giây.
~~~

Không nhất thiết cần transaction đồng bộ giữa source và analytics. Một event/outbox rồi projection bất đồng bộ có thể đáp ứng tốt hơn, miễn có retry và reconciliation.

### 6.3. Sự khác nhau về mục tiêu

| Tình huống | Nhu cầu thường gặp |
|---|---|
Nạp 100.000 log độc lập | Throughput, xử lý lỗi từng phần |
| Tạo nhiều sản phẩm độc lập | Bulk API với idempotent keys và retry |
| Chuyển tiền giữa hai tài khoản | Atomicity/isolation phù hợp và kiểm soát số dư |
| Trừ tồn kho và xác nhận đơn | Conditional write/transaction theo phạm vi dữ liệu |
| Cập nhật search sau khi tạo sản phẩm | Eventual projection có thể chấp nhận |
| Tăng số lượt xem | Batching/aggregation, cân nhắc sai số và retry |
| Ghi nguồn và outbox event | Cần cùng commit nếu dùng outbox truyền thống |

Không có một API tốt nhất cho mọi hàng trong bảng.

## 7. MongoDB: insertMany và bulkWrite không tự tạo multi-document transaction

### 7.1. insertMany

Ví dụ trong MongoDB shell:

~~~javascript
db.products.insertMany(
  [
    { _id: "P101", name: "Bút", stock: 50 },
    { _id: "P102", name: "Vở", stock: 80 },
    { _id: "P103", name: "Thước", stock: 20 }
  ],
  { ordered: true }
);
~~~

Một lời gọi chứa ba thao tác insert. Điều này có thể giảm overhead so với gọi insertOne ba lần.

**Không có multi-document atomicity tự động:** Nếu document P102 vi phạm unique index, những insert trước lỗi có thể đã thành công. Khi ordered=true, driver/server xử lý theo ngữ nghĩa ordered và dừng các thao tác tiếp theo sau lỗi; nó **không rollback** những document đã được ghi trước đó.

### 7.2. ordered khác atomic

Hai tùy chọn thường thấy:

- **ordered: true:** Các thao tác có thứ tự yêu cầu; khi gặp lỗi, nhóm dừng theo hợp đồng ordered.
- **ordered: false:** Những thao tác có thể được thực thi không theo thứ tự ban đầu và việc xử lý lỗi của một item không nhất thiết chặn các item khác.

**Cả ordered lẫn unordered đều không tự biến bulk thành transaction nguyên tử.**

Ví dụ:

~~~text
ordered=true:
  A SUCCESS
  B FAILED
  C NOT ATTEMPTED

ordered=false:
  A SUCCESS
  B FAILED
  C SUCCESS
~~~

Đây là tình huống minh họa; kết quả cụ thể phụ thuộc lỗi, batch, sharding và hành vi driver.

### 7.3. bulkWrite kết hợp nhiều loại thao tác

~~~javascript
db.products.bulkWrite(
  [
    {
      updateOne: {
        filter: { _id: "P101" },
        update: { $set: { stock: 49 } }
      }
    },
    {
      insertOne: {
        document: {
          _id: "P104",
          name: "Tẩy",
          stock: 30
        }
      }
    },
    {
      deleteOne: {
        filter: { _id: "P103" }
      }
    }
  ],
  { ordered: false }
);
~~~

BulkWrite có thể tối ưu nhiều thao tác ghi trong một lời gọi. Nhưng một số thao tác thành công không tạo ra **cơ chế undo cho các thao tác khác**.

### 7.4. Atomicity ở mức một document

MongoDB cung cấp tính nguyên tử cho thao tác ghi trên **một document** theo ngữ nghĩa tương ứng. Ví dụ:

~~~javascript
db.orders.updateOne(
  { _id: "O1001", version: 5 },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 }
  }
);
~~~

Điều kiện version và cập nhật hai field của document là một thao tác nguyên tử ở phạm vi document. Điều đó khác với mong muốn cập nhật ba document Orders, Stock, Audit cùng nguyên tử.

### 7.5. Dùng transaction khi cần nhiều document cùng commit

Ví dụ khái niệm với MongoDB Node.js driver:

~~~javascript
const session = client.startSession();

try {
  await session.withTransaction(async () => {
    const seatResult = await db.collection("seats").updateOne(
      { _id: "S101", status: "AVAILABLE" },
      { $set: { status: "RESERVED", bookingId: "B1001" } },
      { session }
    );

    if (seatResult.matchedCount !== 1) {
      throw new Error("Seat already reserved");
    }

    await db.collection("bookings").insertOne(
      {
        _id: "B1001",
        seatId: "S101",
        status: "CONFIRMED"
      },
      { session }
    );
  });
} finally {
  await session.endSession();
}
~~~

Ví dụ yêu cầu môi trường MongoDB hỗ trợ transaction và cấu hình session phù hợp. Khi transaction commit, các thay đổi trong phạm vi transaction có tính nguyên tử theo bảo đảm của MongoDB.

**Lưu ý:** Callback của withTransaction có thể được driver retry trong một số tình huống. Không đưa side effect bên ngoài như gửi email, trừ tiền qua API khác hoặc phát message không idempotent vào callback rồi giả định nó chỉ chạy một lần.

### 7.6. Transaction có giá

Multi-document transaction có thể tăng:

- Thời gian giữ tài nguyên và xung đột.
- Độ trễ commit.
- Tải oplog/journal và replication.
- Nguy cơ retry/abort khi nhiều client tranh chấp.
- Phức tạp khi transaction dài hoặc nhóm quá nhiều thao tác.

Vì vậy nếu có thể tổ chức một invariant trong **một document**, thao tác đơn có thể đơn giản hơn một transaction nhiều document. Nhưng không nên ép toàn bộ dữ liệu vào một document khổng lồ chỉ để né transaction.

## 8. DynamoDB BatchWriteItem: tối ưu nhiều Put/Delete, có thể thành công một phần

### 8.1. Chức năng chính

**BatchWriteItem** cho phép gửi nhiều yêu cầu Put hoặc Delete trong một lời gọi. API này được thiết kế để thao tác hàng loạt hiệu quả, chẳng hạn nạp hoặc xóa nhiều item độc lập.

Giới hạn được biết phổ biến:

- Tối đa **25 Put/Delete requests** trong một lời gọi BatchWriteItem.
- Tổng kích thước request tối đa theo giới hạn API, thường được nêu là **16 MB**.
- Mỗi item phải tuân theo giới hạn item của DynamoDB, điển hình **400 KB**.
- **Không hỗ trợ UpdateItem hoặc ConditionExpression** trong những Put/Delete thuộc BatchWriteItem.

Các ngưỡng cần được đối chiếu với tài liệu dịch vụ/SDK đang dùng vì giới hạn API có thể thay đổi theo thời gian.

### 8.2. Không phải một transaction toàn nhóm

Giả sử gửi:

~~~text
BatchWriteItem:
  Put P101
  Put P102
  Put P103
  Delete P090
~~~

Nếu một phần bị throttling hoặc không xử lý được, những phần khác có thể đã thành công. DynamoDB trả về danh sách **UnprocessedItems** đối với các yêu cầu chưa xử lý trong kết quả thành công ở mức request.

Không thể hiểu **HTTP success** cho BatchWriteItem là “mọi item đều đã được ghi”.

### 8.3. Ví dụ AWS SDK JavaScript v3

~~~javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  BatchWriteCommand
} from "@aws-sdk/lib-dynamodb";

const docClient = DynamoDBDocumentClient.from(
  new DynamoDBClient({ region: "ap-southeast-1" })
);

let pending = {
  Products: [
    {
      PutRequest: {
        Item: { PK: "PRODUCT#P101", SK: "META", stock: 50 }
      }
    },
    {
      PutRequest: {
        Item: { PK: "PRODUCT#P102", SK: "META", stock: 80 }
      }
    }
  ]
};

const response = await docClient.send(new BatchWriteCommand({
  RequestItems: pending
}));

pending = response.UnprocessedItems ?? {};
// Nếu pending còn yêu cầu, ứng dụng phải retry có backoff/jitter.
~~~

Đây là ví dụ minh họa cách đọc UnprocessedItems, chưa phải một hàm retry production. BatchWriteItem có thể trả lỗi ở mức toàn lời gọi trong những trường hợp khác; ứng dụng phải phân biệt **request-level error** và **item-level unprocessed**.

### 8.4. Retry UnprocessedItems

Một vòng lặp khái niệm:

~~~text
pending = originalBatch
attempt = 0

while pending not empty:
    response = BatchWriteItem(pending)
    pending = response.UnprocessedItems

    if pending empty:
        break

    attempt += 1
    if attempt > maxRetries:
        storeFailureForReconciliation(pending)
        break

    sleep(exponentialBackoffWithJitter(attempt))
~~~

Đừng retry vòng lặp nóng không có delay: nó có thể tăng throttling và gây tải thêm. Đồng thời cần đặt giới hạn tổng thời gian, metric, dead-letter queue hoặc bảng job để biết các item chưa được xử lý.

### 8.5. BatchWriteItem có thể thay thế item hiện có

Một PutRequest trong BatchWriteItem không hỗ trợ điều kiện “chỉ tạo nếu chưa tồn tại”. Vì vậy nếu cùng PK/SK đã có item, thao tác Put có thể ghi đè theo semantics PutItem.

Nếu cần **create-if-absent**, **compare-and-set** hoặc **version check**, phải dùng API ghi có điều kiện phù hợp, không chỉ BatchWriteItem.

### 8.6. Đừng suy tính nguyên tử từ cấu trúc JSON

RequestItems là một JSON object chứa nhiều request, nhưng đó là **định dạng trao đổi dữ liệu**, không phải lời hứa rollback nếu một item thất bại.

## 9. DynamoDB TransactWriteItems: transaction nhiều item trong phạm vi hỗ trợ

### 9.1. Mục tiêu khác BatchWriteItem

**TransactWriteItems** được thiết kế cho nhóm thao tác cần tính nguyên tử trong phạm vi transaction mà DynamoDB hỗ trợ. Nó có thể gồm:

- Put.
- Update.
- Delete.
- ConditionCheck.

Trong một transaction, các điều kiện được đánh giá theo hợp đồng và nhóm ghi có thể commit/abort như một đơn vị.

Giới hạn phổ biến cần nhớ là **tối đa 100 hành động cho tối đa 100 item khác nhau** và tổng kích thước item trong transaction giới hạn theo API, thường nêu là **4 MB**. Không được dùng hai hành động nhắm cùng một item trong một TransactWriteItems. Cần xác minh tài liệu cho phiên bản dịch vụ hiện hành.

### 9.2. Ví dụ đặt ghế và tạo booking

~~~javascript
import {
  DynamoDBDocumentClient,
  TransactWriteCommand
} from "@aws-sdk/lib-dynamodb";

await docClient.send(new TransactWriteCommand({
  TransactItems: [
    {
      Update: {
        TableName: "Tickets",
        Key: {
          PK: "SEAT#S101",
          SK: "META"
        },
        UpdateExpression: "SET #status = :reserved, bookingId = :bid",
        ConditionExpression: "#status = :available",
        ExpressionAttributeNames: {
          "#status": "status"
        },
        ExpressionAttributeValues: {
          ":reserved": "RESERVED",
          ":available": "AVAILABLE",
          ":bid": "B1001"
        }
      }
    },
    {
      Put: {
        TableName: "Tickets",
        Item: {
          PK: "BOOKING#B1001",
          SK: "META",
          seatId: "S101",
          status: "CONFIRMED"
        },
        ConditionExpression: "attribute_not_exists(PK)"
      }
    }
  ],
  ClientRequestToken: "booking-B1001-attempt-1"
}));
~~~

Giả định seat item đã có status AVAILABLE và booking chưa tồn tại. Nếu điều kiện giữ ghế hoặc tạo booking thất bại, transaction không commit chỉ một nửa của hai thay đổi.

ClientRequestToken hỗ trợ tính idempotent theo phạm vi, thời gian và điều kiện mà DynamoDB định nghĩa; nó **không là khóa idempotency vô hạn** cho mọi hệ thống. Ứng dụng vẫn nên có bookingId duy nhất và trạng thái nghiệp vụ rõ ràng.

### 9.3. So sánh trực tiếp

| Thuộc tính | BatchWriteItem | TransactWriteItems |
|---|---|---|
| Mục tiêu | Throughput, gom Put/Delete | Bảo đảm nguyên tử nhiều hành động |
| Put/Delete | Có | Có |
| Update/ConditionCheck | Không | Có |
| Điều kiện trên từng item | Không qua BatchWriteItem | Có |
| Kết quả thành công một phần | Có thể có UnprocessedItems | Transaction commit/abort theo phạm vi |
| Giới hạn phổ biến | 25 yêu cầu, request cỡ tối đa 16 MB | 100 hành động/100 item, khoảng 4 MB tổng |
| Chi phí | Phù hợp dữ liệu độc lập | Coordination/transaction capacity và xung đột |
| Đường retry | Retry phần chưa xử lý và phân biệt lỗi request | Retry theo trạng thái transaction và idempotency |

### 9.4. Mức nguyên tử không mở rộng qua mọi dịch vụ/Region

TransactWriteItems chỉ có phạm vi transaction được DynamoDB hỗ trợ trong tài khoản/Region tương ứng. Nó không đồng thời commit một lệnh gửi email, thanh toán qua cổng bên ngoài hoặc ghi Redis cache trên máy khác.

Với Global Tables và sao chép đa Region, phải xem riêng mức consistency và cách các bản sao hội tụ. Không tự suy rằng transaction ở Region A xuất hiện như một snapshot nguyên tử trên tất cả Region ngay sau commit.

### 9.5. Transaction không tự giúp retry dễ hơn

Client có thể timeout sau khi server commit nhưng trước khi nhận response. Ứng dụng phải giải quyết **kết quả không rõ** và tránh tạo booking hai lần bằng ID/idempotency phù hợp.

## 10. Redis pipelining: giảm RTT nhưng không phải transaction

### 10.1. Pipeline các lệnh độc lập

Ví dụ muốn cập nhật ba bộ đếm:

~~~redis
INCR views:article:101
INCR views:article:102
INCR views:article:103
~~~

Client có thể gửi lệnh theo pipeline mà không đợi từng response. Điều này giảm network latency khi có nhiều round trip.

**Không có atomicity toàn pipeline mặc định.** Một client khác có thể gửi lệnh xen kẽ giữa các lệnh trong pipeline theo lịch thực thi của server, và lỗi của một lệnh không tự rollback những lệnh khác.

### 10.2. Lỗi một phần

Giả sử:

~~~text
INCR keyA -> 11
INCR keyB -> WRONGTYPE
INCR keyC -> 7
~~~

Các lệnh hợp lệ có thể thành công dù một lệnh bị lỗi kiểu dữ liệu. Ứng dụng phải xem từng response.

Không nên lấy việc Redis pipeline có một lời gọi flush phía client để kết luận ba INCR đã trở thành một giao dịch.

## 11. Redis MULTI/EXEC và Lua: gần hơn với atomic execution nhưng vẫn có giới hạn

### 11.1. MULTI/EXEC

Ví dụ:

~~~redis
MULTI
INCR counter:A
INCR counter:B
EXEC
~~~

Trong Redis trên một instance phù hợp, MULTI/EXEC cho phép nhóm lệnh được thực thi tuần tự như một đơn vị, không bị lệnh của client khác chen vào giữa lúc server thực hiện nhóm.

Tuy nhiên, **Redis transaction không cung cấp rollback tổng quát nếu một lệnh trong EXEC gặp lỗi runtime**.

Ví dụ:

~~~text
MULTI
SET keyA "done"
INCR keyB     # keyB hiện là chuỗi không thể tăng số
SET keyC "done"
EXEC
~~~

Nếu INCR keyB lỗi kiểu dữ liệu lúc thực thi, những lệnh khác có thể đã được áp dụng. Vì vậy không nên nhầm MULTI/EXEC với SQL transaction có rollback tất cả runtime errors.

Các lỗi khi xếp hàng lệnh trước EXEC và lỗi tại thời điểm EXEC có hành vi khác nhau; cần xử lý kết quả trả về của từng lệnh.

### 11.2. WATCH và optimistic locking

Redis WATCH có thể dùng để phát hiện key đã thay đổi trước EXEC, hỗ trợ kiểu giao dịch lạc quan:

~~~text
WATCH balance:A
GET balance:A
... kiểm tra số dư ở client ...
MULTI
DECRBY balance:A 100
INCRBY balance:B 100
EXEC
~~~

Nếu key được WATCH thay đổi theo điều kiện Redis kiểm tra, EXEC có thể bị hủy, ứng dụng phải đọc lại và retry. Nhưng việc kiểm tra mọi điều kiện và hành vi khi lỗi runtime vẫn cần thiết kế đúng; không thể chỉ thêm WATCH rồi coi là transaction tiền tệ hoàn chỉnh trong mọi topology.

### 11.3. Lua hoặc Redis Functions

Một script xử lý nhiều lệnh trên Redis server có thể thực thi mà không bị interleaving từ script/lệnh khác trong phạm vi instance, cho phép kiểm tra và cập nhật gần nhau:

~~~lua
local available = tonumber(redis.call("GET", KEYS[1]) or "0")
local amount = tonumber(ARGV[1])

if available < amount then
  return {err = "INSUFFICIENT_STOCK"}
end

redis.call("DECRBY", KEYS[1], amount)
redis.call("SET", KEYS[2], ARGV[2])
return "OK"
~~~

**Lưu ý:** Script có thể gây lỗi sau khi đã tạo side effect; Redis không tự rollback mọi thay đổi trước lỗi. Cần kiểm tra toàn bộ điều kiện và kiểu dữ liệu trước phần ghi có rủi ro, hoặc thiết kế lại thao tác.

Script dài cũng có thể chặn Redis event loop; không thích hợp để xử lý batch khổng lồ không kiểm soát.

### 11.4. Redis Cluster và hash slot

Trong Redis Cluster, thao tác đa key bằng transaction/script phải tuân thủ giới hạn phân vùng khóa của cơ chế được hỗ trợ. Hai key thuộc hash slot khác nhau có thể không thực hiện được chung một đơn vị atomic như trên một node.

Ví dụ khóa có hash tag:

~~~text
stock:{order1001}:sku42
booking:{order1001}:meta
~~~

Chúng có thể được thiết kế để đồng vị trí bằng hash tag, nhưng việc đồng vị trí quá nhiều dữ liệu có thể tạo hot slot. Không dùng hash tag để biến mọi giao dịch đa tenant thành một partition khổng lồ.

## 12. Cassandra CQL BATCH: cái tên dễ gây hiểu lầm

### 12.1. BATCH không phải bulk-loader tối ưu mọi kiểu ghi

Cassandra hỗ trợ cú pháp:

~~~sql
BEGIN BATCH
  INSERT INTO activity_by_user (
      user_id, activity_day, event_id, event_type
  ) VALUES ('L001', '2026-11-14', 1001, 'START');

  INSERT INTO activity_by_user (
      user_id, activity_day, event_id, event_type
  ) VALUES ('L001', '2026-11-14', 1002, 'FINISH');
APPLY BATCH;
~~~

Ví dụ giả định bảng và các cột có kiểu phù hợp.

Không nên suy rằng gom **hàng nghìn INSERT ở nhiều partition** vào một BATCH sẽ nhanh hơn gửi các lệnh bất đồng bộ được driver điều phối đúng cách. Một BATCH đa partition có thể tăng coordination, batchlog và tạo hotspot.

### 12.2. LOGGED BATCH

Trong Cassandra, **logged batch** sử dụng cơ chế batchlog để giúp những mutation trong nhóm được áp dụng dù coordinator gặp lỗi; các bảo đảm và phạm vi atomicity phải đọc theo tài liệu đúng phiên bản.

Ý tưởng:

~~~text
BEGIN LOGGED BATCH
  mutation partition A
  mutation partition B
APPLY BATCH
~~~

Batchlog phục vụ **khả năng các mutation của batch cuối cùng được áp dụng**, không phải SQL transaction có snapshot isolation giữa nhiều partition.

Nếu một replica/partition được áp dụng trước phần khác, reader có thể quan sát **trạng thái trung gian** trong lúc batch đang lan truyền, tùy consistency và thời điểm đọc.

### 12.3. UNLOGGED BATCH

~~~sql
BEGIN UNLOGGED BATCH
  UPDATE counters_demo SET value = 10 WHERE id = 'A';
  UPDATE counters_demo SET value = 20 WHERE id = 'B';
APPLY BATCH;
~~~

Ví dụ chỉ minh họa cấu trúc, giả định đây là bảng có value thuộc kiểu có thể SET thường, **không phải counter column đặc biệt của Cassandra**.

UNLOGGED BATCH bỏ bước batchlog của logged batch. Với mutation trải nhiều partition, không được coi nó có bảo đảm atomicity toàn nhóm như logged batch.

Khi mọi thao tác cùng một partition, Cassandra có những tối ưu và bảo đảm ở cấp partition phù hợp; vẫn phải xem điều kiện, consistency và isolation của đúng API thay vì gọi bất cứ BATCH nào là ACID tổng quát.

### 12.4. Vì sao logged BATCH vẫn không phải giao dịch chuyển tiền SQL?

Các vấn đề:

- Không có mức isolation đa partition tổng quát tương đương serializable transaction.
- Một reader có thể thấy trạng thái trung gian khi mutation chưa hội tụ.
- BATCH không tự kiểm tra invariant số dư không âm trên hai tài khoản cùng lúc.
- Không có phép rollback nghiệp vụ tổng quát khi đã phát mutation ra nhiều partition.
- Coordination và batchlog tạo chi phí, đặc biệt với batch lớn.

**Atomicity của logged batch ở cấp cơ chế phát/áp dụng mutation không nên được diễn giải thành một ACID transaction với isolation tức thời trên tất cả partition.**

### 12.5. Batch cùng partition so với nhiều partition

| Trường hợp | Hướng tư duy |
|---|---|
| Nhiều mutation liên quan cùng partition | Có thể tận dụng BATCH/đảm bảo cấp partition của Cassandra theo trường hợp |
| Nhiều mutation khác partition, cần cùng được áp dụng | Đánh giá logged batch và giới hạn consistency/visibility |
| Nạp hàng triệu item độc lập ở nhiều partition | Dùng prepared statements/async writes theo driver và kiểm soát concurrency; không mặc định giant BATCH |
| Cần điều kiện ghi trên một partition | Đánh giá lightweight transaction/IF và phạm vi hỗ trợ |
| Cần ACID serializable giữa nhiều partition | Không nên giả định CQL BATCH là giải pháp; xem lại mô hình hoặc một nguồn giao dịch phù hợp |

### 12.6. COUNTER BATCH không cùng nghĩa với mọi BATCH khác

Cassandra có những quy tắc và cú pháp riêng cho counter updates. Không thể trộn mọi loại mutation trong cùng batch tùy ý rồi mong đạt bảo đảm nguyên tử như transaction thông thường.

Cần kiểm tra loại cột, phiên bản CQL, sự kết hợp statement và giới hạn thực thi trước khi dùng.

### 12.7. ScyllaDB

ScyllaDB tương thích nhiều khái niệm CQL và batch của Cassandra nhưng có các tối ưu và giới hạn riêng theo phiên bản/kiến trúc. Không suy từ cùng cú pháp BATCH rằng chi phí hoặc hành vi timeout/throttling giống hệt Cassandra trong mọi deployment.

## 13. Elasticsearch/OpenSearch Bulk API: nhiều item, nhiều kết quả

### 13.1. Bulk request

Một Bulk API có thể index, update hoặc delete nhiều document trong một request, thường theo định dạng **newline-delimited JSON (NDJSON)**:

~~~text
POST /_bulk
{"index":{"_index":"products","_id":"P101"}}
{"name":"Bút","stock":50}
{"index":{"_index":"products","_id":"P102"}}
{"name":"Vở","stock":80}
{"delete":{"_index":"products","_id":"P090"}}
~~~

Trong request thực, NDJSON cần đúng định dạng dòng và newline kết thúc theo API. Ví dụ trình bày các dòng lệnh và payload để nhận diện cấu trúc.

### 13.2. HTTP success vẫn có thể chứa item failures

Kết quả có thể có:

~~~json
{
  "errors": true,
  "items": [
    {"index": {"_id": "P101", "status": 201}},
    {"index": {"_id": "P102", "status": 429}},
    {"delete": {"_id": "P090", "status": 200}}
  ]
}
~~~

Đây là **kết quả minh họa**, không đại diện toàn bộ response thật. Việc Bulk API trả HTTP 200 không chứng minh mọi document thành công; phải xem trường errors và trạng thái từng item.

### 13.3. Không có atomicity cả bulk

Item P101 có thể đã được index dù P102 lỗi 429. Retry nên nhắm vào các item chưa thành công và tuân thủ backoff; không blind-retry toàn bộ nếu các thao tác như UPDATE script tăng bộ đếm có thể bị lặp.

### 13.4. Refresh không phải commit transaction

Một document có thể được ghi nhận thành công ở write path nhưng search query chưa nhìn thấy ngay do cơ chế refresh. Chọn refresh behavior giúp điều khiển khả năng thấy thay đổi theo ngữ nghĩa engine, **không biến bulk thành transaction nguyên tử**.

### 13.5. Search index không phải nguồn cuối cho bất biến giao dịch

Nếu cần bảo đảm “chỉ bán tối đa 1 ghế”, không nên chỉ dùng hai bulk index actions vào search engine để quyết định. Search là read model phù hợp cho tìm kiếm; invariant cần được bảo vệ tại nguồn có thẩm quyền.

## 14. Ma trận so sánh các API NoSQL

| Sản phẩm/API | Mục tiêu chính | Nguyên tử cả nhóm? | Lỗi một phần | Chú ý |
|---|---|---|---|---|
| MongoDB insertMany/bulkWrite | Gom nhiều ghi | Không mặc định | Có | Ordered không phải rollback |
| MongoDB multi-document transaction | Nhiều ghi cùng commit | Có trong phạm vi transaction | Abort/commit theo ngữ nghĩa | Session, retry, contention |
| DynamoDB BatchWriteItem | Nạp/xóa hàng loạt | Không | UnprocessedItems | Không condition/update |
| DynamoDB TransactWriteItems | Invariant nhiều item | Có trong phạm vi hỗ trợ | Transaction fail/abort | Giới hạn action/item/Region |
| Redis pipeline | Giảm RTT | Không | Từng lệnh | Không ngăn interleaving |
| Redis MULTI/EXEC | Nhóm lệnh trên instance | Không interleave khi EXEC; không rollback runtime errors | Runtime errors có thể còn side effects khác | Không tương đương SQL ACID |
| Redis Lua/Functions | Thao tác server-side có kiểm soát | Atomic execution theo phạm vi engine, không tự rollback lỗi script | Có thể có partial side effects khi script error | Giới hạn Cluster, thời gian chạy |
| Cassandra LOGGED BATCH | Ghi nhóm mutation với batchlog | Bảo đảm atomicity kiểu Cassandra, không phải isolation đa partition SQL | Có thể tạm thời thấy một phần; eventual apply | Batchlog/coordination |
| Cassandra UNLOGGED BATCH | Gom thao tác, hữu ích trong một số trường hợp cùng partition | Không mặc định toàn nhóm đa partition | Có thể | Không phải bulk-loader tối ưu mọi workload |
| Elasticsearch/OpenSearch Bulk | Index/delete/update nhiều doc | Không | Item-level status | Refresh và search visibility riêng |

Từ “nguyên tử” trong bảng phải luôn được đọc cùng **phạm vi, điều kiện lỗi và mức isolation**. Mục tiêu không phải xếp hạng một sản phẩm “mạnh” hay “yếu”, mà là chọn đúng công cụ cho một invariant cụ thể.

## 15. Batch đa partition có thể gặp những điểm nghẽn nào?

### 15.1. Một request nhưng nhiều node

Giả sử 100 item có partition key khác nhau:

~~~text
Batch request 100 items
     |
     v
Coordinator / Gateway
     |----> Node A (30 items)
     |----> Node B (20 items)
     |----> Node C (50 items)
~~~

Về mạng client→server, có thể chỉ một request. Nhưng nội bộ hệ vẫn phải điều phối nhiều shard/partition/nút.

### 15.2. Thông lượng không chỉ phụ thuộc số request

Một batch có thể chậm vì:

- Một partition nóng chiếm phần lớn item.
- WCU/RCU hoặc capacity của index thiếu.
- Disk I/O hay compaction backlog.
- Lock/transaction conflict.
- Replica bị lag.
- Quota request size hoặc số thao tác.
- Coordinator phải chờ shard chậm nhất.

Giảm số request client không làm biến mất những chi phí này.

### 15.3. Batch lớn và backpressure

Gửi liên tục các batch 25 hoặc 100 item có thể vẫn vượt capacity. Cần giới hạn concurrency, xử lý throttling/backoff và không cho queue tăng vô hạn.

Một pipeline ingestion tốt đo:

- Items/giây thành công.
- Số items thất bại/chưa xử lý.
- Retry ratio và retry age.
- Latency p50/p95/p99.
- Request size.
- Hot partition/key.
- CPU, disk I/O, capacity utilization.

## 16. Retry: bài toán khó hơn khi kết quả không rõ

### 16.1. Lỗi trước khi server xử lý

Client không thể kết nối, server chưa nhận request: retry thường đơn giản hơn, nhưng chỉ khi thật sự xác định không có side effect nào.

### 16.2. Lỗi sau khi một phần đã xử lý

Batch không nguyên tử:

~~~text
PUT A -> SUCCESS
PUT B -> SUCCESS
PUT C -> TIMEOUT hoặc FAILED
~~~

Retry toàn nhóm có thể:

- Ghi đè A/B nếu dùng Put không điều kiện.
- Tạo duplicate nếu ID được tạo mới ở mỗi lần gửi.
- Tăng counter thêm lần nữa.
- Gửi notification/email lặp.

Phải biết item nào đã thành công, hoặc làm mọi thao tác **lặp an toàn** theo idempotency key.

### 16.3. Transaction commit nhưng response thất lạc

~~~text
Client gửi COMMIT
Server COMMIT thành công
Response mất trên mạng
Client thấy timeout
~~~

Lúc này client không thể suy “transaction đã rollback”. Cần cách phân biệt **committed, aborted và unknown**, dùng idempotency token, truy vấn trạng thái nghiệp vụ hoặc retry theo contract của API.

### 16.4. PUT, DELETE, INCREMENT có khác nhau

~~~text
PUT key=K value=V       -> thường có thể lặp mà kết quả cùng giá trị,
                          nhưng phải xét version và ghi đồng thời.

DELETE key=K            -> lặp lại thường có thể cho trạng thái vắng mặt,
                          nhưng nguy hiểm nếu K đã được tái sử dụng.

INCREMENT counter      -> gửi lại có thể tăng hai lần.

APPEND event không ID  -> gửi lại có thể tạo trùng.
~~~

Do đó **idempotency phụ thuộc ngữ nghĩa của thao tác**, không phụ thuộc chữ Batch.

## 17. Idempotency: thiết kế xử lý lại mà không nhân đôi tác dụng

### 17.1. Định danh nghiệp vụ ổn định

Thay vì tạo orderId mới mỗi lần retry:

~~~text
Yêu cầu đầu:
  clientRequestId = REQ-778
  orderId = O1001

Yêu cầu retry:
  clientRequestId = REQ-778
  orderId = O1001
~~~

Server có thể dùng unique key hoặc conditional insert để nhận diện một ý định đã xử lý.

### 17.2. Bảng kết quả idempotency

Ví dụ schema khái niệm:

~~~text
IdempotencyRecord:
  tenantId
  requestId
  payloadHash
  status = PROCESSING | COMMITTED | FAILED
  resultReference
  createdAt
~~~

Khi request trùng:

1. Nếu requestId chưa có, tạo record theo điều kiện nguyên tử.
2. Nếu đã có với cùng payloadHash và COMMITTED, trả kết quả trước.
3. Nếu cùng requestId nhưng payload khác, trả conflict.
4. Nếu PROCESSING quá lâu, dùng quy trình phục hồi trạng thái không rõ.

**Chỉ lưu requestId trong JSON không tự tạo idempotency**; phải kiểm tra và ràng buộc nó ở điểm ghi có thẩm quyền.

### 17.3. Idempotency và deduplication không giống transaction

Idempotency ngăn một tác dụng bị lặp khi retry; transaction bảo vệ một nhóm tác dụng khỏi trạng thái commit một phần. Một hệ có thể cần **cả hai**.

Ví dụ transaction đặt ghế có thể atomic giữa Seat và Booking; idempotency bảo vệ client gửi lại cùng booking request sau timeout.

### 17.4. Version/CAS

Với cập nhật có điều kiện:

~~~text
UPDATE item
WHERE item.version = 7
SET value=..., version=8
~~~

Nếu retry khi item đã version=8, điều kiện thất bại; ứng dụng cần xác định đây là “chính mình đã ghi thành công” hay “client khác đã cập nhật”.

Một version check đơn thuần **không luôn đủ** để phân biệt các trường hợp đó; có thể cần operationId hoặc transaction log.

## 18. Atomicity của một item và của nhiều item

### 18.1. Đơn vị nguyên tử nhỏ nhất của hệ

Nhiều NoSQL cung cấp bảo đảm mạnh cho một document/item/row theo ngữ nghĩa riêng, ví dụ:

- MongoDB: một thao tác ghi trên một document có tính nguyên tử.
- DynamoDB: conditional write trên một item được đánh giá cùng thao tác ghi.
- Redis: một lệnh trên instance xử lý được thực thi nguyên tử theo mô hình event loop.
- Cassandra: có bảo đảm ở mức mutation/row/partition tùy thao tác và consistency.

Điều đó không tự kéo dài sang nhiều document, nhiều key, nhiều partition hoặc nhiều hệ.

### 18.2. Gom invariant vào một item khi hợp lý

Ví dụ một Order có các line item nhỏ được nhúng trong cùng document và cập nhật như một đơn vị. Nếu số line có giới hạn, việc giữ chúng trong một document có thể đơn giản hóa atomicity.

Tuy nhiên, nếu order có 100.000 line item, nhúng tất cả có thể vượt giới hạn kích thước và tạo hot document. Không nên hy sinh mô hình dữ liệu chỉ để né một transaction.

### 18.3. Trường hợp hai item

~~~text
Inventory[SKU-42].available -= 1
Order[O1001].status = CONFIRMED
~~~

Nếu hai item thuộc một transaction được hỗ trợ, chọn transaction hoặc conditional write phù hợp. Nếu không có transaction chung, cần thay đổi workflow:

- Giữ chỗ tồn kho với reservation ID.
- Ghi trạng thái đơn PENDING.
- Xác nhận khi reservation hợp lệ.
- Có cơ chế hủy giữ chỗ khi thất bại.

Không nên gọi hai UpdateItem trong batch không nguyên tử rồi tuyên bố hệ bảo đảm không oversell.

## 19. Transaction nhiều item vẫn không bao phủ side effects bên ngoài

### 19.1. Ví dụ tạo đơn và gửi email

~~~text
Transaction database:
  INSERT Order
  UPDATE Inventory
COMMIT

External:
  Send email confirmation
~~~

Nếu email gửi trước khi transaction commit, giao dịch abort nhưng người dùng đã nhận xác nhận sai. Nếu email gửi sau commit nhưng service chết, đơn đã tạo mà email chưa gửi.

Không thể giải quyết bằng cách thêm sendEmail() vào callback transaction và coi đó là một phần ACID.

### 19.2. Transactional outbox

Một thiết kế:

~~~text
BEGIN TRANSACTION
  INSERT Order(O1001, CONFIRMED)
  UPDATE Inventory(SKU-42)
  INSERT OutboxEvent(ORDER_CONFIRMED, O1001, EVT-101)
COMMIT
~~~

Sau commit, worker đọc outbox rồi gửi email, cập nhật search và publish event.

Outbox giúp tránh khoảng trống “database commit nhưng không còn bằng chứng để phát sự kiện”; song consumer vẫn có thể nhận event trùng, nên cần **idempotent processing**.

### 19.3. Saga khi không có transaction chung

Một quy trình đặt vé qua nhiều dịch vụ:

~~~text
1. Reserve seat
2. Authorize payment
3. Confirm booking
~~~

Nếu thanh toán thất bại, ứng dụng cần **compensating action**:

~~~text
Release seat reservation
~~~

Đây là mô hình **saga**, không phải transaction nguyên tử toàn cục. Các bước trung gian có thể quan sát được, hành động bù trừ cũng có thể thất bại và cần retry. “Bù trừ” không phải phép rollback thời gian: email đã gửi hoặc hàng đã giao có thể không đảo ngược hoàn toàn.

### 19.4. Không nhầm saga với batch

Saga có quy trình trạng thái, timeout, bù trừ và khả năng phục hồi giữa các dịch vụ. Một HTTP batch gửi ba lệnh độc lập **không tự trở thành saga** nếu không có các cơ chế đó.

## 20. Phân biệt visibility, atomic commit và eventual replication

### 20.1. Có thể commit nguyên tử tại nguồn nhưng đọc từ bản sao cũ

Giả sử transaction ở nguồn cập nhật:

~~~text
Order.status = PAID
Payment.status = CAPTURED
~~~

Transaction commit thành công. Một bảng search hoặc dashboard được cập nhật bất đồng bộ vẫn có thể hiển thị Order.status=PENDING trong vài giây.

Không có mâu thuẫn với atomicity của transaction **trong phạm vi nguồn**: read model không thuộc transaction đó.

### 20.2. GSI và projection

DynamoDB GSI có consistency eventual; không thể bật strong read trên GSI. Một transaction ghi bảng chính không bắt GSI xuất hiện như một snapshot nguyên tử ngay lập tức.

Với MongoDB change stream hoặc search projection, consumer cần áp dụng event theo version và có phương án rebuild.

### 20.3. Read-your-writes

Nếu ứng dụng yêu cầu người dùng vừa bấm “Đặt vé” phải thấy chính xác booking mới, có thể đọc từ nguồn theo consistency phù hợp sau commit thay vì ngay lập tức chỉ Query một projection eventual.

**Đừng cố chữa vấn đề eventual replication bằng cách tăng kích thước batch ở nguồn.**

## 21. Ordered, unordered, atomic, isolated: một ma trận tình huống

### 21.1. Ordered bulk

~~~text
A thành công
B thất bại
C không chạy
~~~

Giữ thứ tự thao tác ở mức API nhưng không rollback A.

### 21.2. Unordered bulk

~~~text
A thành công
B thất bại
C thành công
~~~

Cho phép xử lý các item độc lập hiệu quả hơn trong một số tình huống, nhưng khó suy kết quả từ thứ tự danh sách.

### 21.3. Atomic transaction với isolation phù hợp

~~~text
COMMIT: A, B, C cùng là trạng thái được commit.
ABORT: không commit nhóm thay đổi.
~~~

Đường đọc có thể được bảo vệ khỏi một số trạng thái trung gian tùy mức isolation. Không suy isolation cao nhất nếu API không công bố.

### 21.4. Cassandra logged batch

~~~text
Các mutation của batch được bảo vệ bằng batchlog
để hướng tới áp dụng đầy đủ theo bảo đảm Cassandra.

Reader trên nhiều partition có thể thấy các mutation
ở những thời điểm khác nhau trong khi lan truyền.
~~~

Đây là ví dụ vì sao không thể lấy từ **atomic** rồi mặc định tất cả tính chất SQL ACID.

### 21.5. Redis MULTI/EXEC

~~~text
Lệnh trong EXEC không bị client khác chen vào giữa,
nhưng lỗi runtime của một lệnh không tự rollback mọi lệnh khác.
~~~

Không thể coi mọi tập lệnh MULTI/EXEC là “cả nhóm thành công hoặc không gì thay đổi” trong mọi trường hợp lỗi.

## 22. Batch size và thiết kế backpressure

### 22.1. Đường cong thông lượng

Một mô hình thực tế thường gặp:

~~~text
Batch size nhỏ:
  Nhiều request, RTT overhead cao.

Batch size vừa:
  Ít request hơn, amortize overhead tốt.

Batch size rất lớn:
  Payload, parse, memory, throttling và retry cost tăng.
~~~

Do đó thông lượng có thể cải thiện tới một mức rồi bão hòa hoặc suy giảm.

### 22.2. Adaptive batching

Một batcher có thể xả khi đạt một trong hai điều kiện:

~~~text
maxItemsPerBatch = 25
maxWaitTime = 20ms
~~~

Nếu có đủ 25 item trước 20 ms thì gửi ngay; nếu đến 20 ms vẫn chỉ có 7 item thì gửi 7 item để không tăng latency vô hạn.

Hai con số trên chỉ là **ví dụ chính sách ứng dụng**, không phải khuyến nghị mặc định cho mọi API. Cần tôn trọng giới hạn dịch vụ và đo p95/p99 end-to-end.

### 22.3. Retry queue có giới hạn

Khi DB trả throttling hoặc UnprocessedItems, không nên retry đồng thời không giới hạn:

~~~text
Producer
   |
   v
Bounded queue
   |
   v
Batcher với concurrency limit
   |
   v
Database
   |
   +--> Success metrics
   +--> Retry queue có backoff
   +--> Dead-letter/failure ledger sau ngưỡng
~~~

Hệ thống cần chặn hoặc giảm tốc producer khi lỗi kéo dài để không biến một lỗi DB tạm thời thành mất RAM/khối lượng công việc khổng lồ.

### 22.4. Transaction size cũng cần giới hạn

Transaction lớn có thể giữ tài nguyên lâu, tranh chấp nhiều item và tăng retry cost. Chỉ vì API cho phép tối đa X hành động không có nghĩa nên dùng đủ X trong mọi giao dịch.

Chọn **phạm vi atomicity nhỏ nhất nhưng đủ giữ invariant** thường dễ vận hành hơn một transaction gom nhiều công việc không liên quan.

## 23. Thiết kế kết quả batch minh bạch

### 23.1. Không chỉ trả một boolean success

Với batch không nguyên tử, response nên giúp caller biết trạng thái từng item:

~~~json
{
  "batchId": "BATCH-1001",
  "status": "PARTIAL",
  "items": [
    {
      "operationId": "OP-1",
      "status": "SUCCEEDED"
    },
    {
      "operationId": "OP-2",
      "status": "FAILED",
      "errorCode": "VALIDATION_ERROR"
    },
    {
      "operationId": "OP-3",
      "status": "RETRYABLE",
      "errorCode": "THROTTLED"
    }
  ]
}
~~~

Đây là mô hình API ứng dụng, không phải JSON trả về chuẩn của DynamoDB hay MongoDB.

### 23.2. Phân biệt permanent và transient errors

**Permanent:** Sai schema, vi phạm điều kiện nghiệp vụ, permission, ID không hợp lệ. Retry vô hạn không sửa được lỗi.

**Transient:** Throttling, kết nối ngắt, tài nguyên tạm thiếu. Có thể retry với backoff, nhưng trạng thái không rõ sau timeout cần idempotency.

Một số lỗi có thể đổi nhóm tùy context; ví dụ conditional check failure có thể là xung đột cần người dùng giải quyết hoặc là bằng chứng request đã được xử lý thành công trước đó.

### 23.3. Failure ledger

Với pipeline ghi lớn, nên lưu:

~~~text
batchId
operationId
targetKey
payloadHash
attemptCount
lastError
nextRetryAt
finalStatus
~~~

Ledger giúp điều tra những item bỏ sót và tránh “batch trả thành công nhưng thiếu 3 item” tồn tại âm thầm nhiều ngày.

## 24. Kiểm thử tình huống lỗi trước khi dùng production

### 24.1. Test lỗi một item giữa batch

Cho một item cố tình vi phạm unique index hoặc schema:

~~~text
A hợp lệ
B lỗi
C hợp lệ
~~~

Quan sát:

- A có được commit không?
- C có chạy không?
- Response có chỉ ra B lỗi không?
- Với retry, A/C có bị nhân đôi không?

Test cho cả ordered và unordered nếu API hỗ trợ.

### 24.2. Test throttling

Làm việc trong môi trường test có giới hạn tải và tạo điều kiện một phần item bị throttling. Kiểm tra:

- API trả lỗi toàn request hay UnprocessedItems?
- Worker retry đúng phần nào?
- Có exponential backoff/jitter không?
- Có dừng sau maxRetries và ghi failure ledger không?

### 24.3. Test timeout sau commit

Giả lập response commit bị mất. Client retry:

- Có tạo booking thứ hai không?
- Có tăng bộ đếm hai lần không?
- Có gửi email hai lần không?
- Có đọc được trạng thái nghiệp vụ cuối cùng theo requestId không?

### 24.4. Test transaction conflict

Hai client đồng thời đặt cùng ghế:

~~~text
Client A: Reserve S101 for B1001
Client B: Reserve S101 for B1002
~~~

Kết quả mong muốn là **tối đa một booking được xác nhận** theo invariant. Test chỉ gửi từng request tuần tự không phát hiện được race.

### 24.5. Test khi worker hoặc node chết

Giả lập worker chết sau khi xử lý nửa batch không nguyên tử. Khởi động lại từ checkpoint/failure ledger và kiểm tra không mất item hoặc nhân đôi side effect.

Với Cassandra logged batch, cần test theo phạm vi mà tài liệu hệ hỗ trợ và quan sát consistency/visibility; không suy ra khả năng rollback SQL chỉ vì một lần test không thấy dữ liệu trung gian.

## 25. Ví dụ kiến trúc: ghi log nhiều nhưng cần đơn hàng nguyên tử

Giả sử ứng dụng có hai luồng:

**Luồng A: Telemetry**

~~~text
500.000 event độc lập/phút
Không có invariant xuyên các event
Chấp nhận retry và dedup theo eventId
~~~

Có thể dùng API batch/pipeline để tăng throughput, với batcher, idempotent event IDs và DLQ. Transaction nhiều event không liên quan thường không mang lại giá trị tương xứng.

**Luồng B: Checkout**

~~~text
1. Đặt chỗ tồn kho.
2. Tạo đơn hàng CONFIRMED.
3. Ghi outbox event ORDER_CONFIRMED.
~~~

Đây là nhóm thay đổi có invariant. Có thể cần transaction trong một datastore, hoặc reservation/saga nếu các thành phần nằm ở nhiều hệ.

Sau commit:

~~~text
Outbox worker
  -> Gửi email (idempotent)
  -> Cập nhật search index
  -> Cập nhật analytics
~~~

Những bản chiếu này có thể xử lý bằng batch hiệu năng độc lập mà **không mở rộng transaction checkout tới toàn bộ hệ thống**.

**Bài học kiến trúc:** Trong cùng một ứng dụng, batch và transaction thường cùng tồn tại nhưng phục vụ những tầng trách nhiệm khác nhau.

## 26. Gợi ý lựa chọn theo câu hỏi quyết định

### 26.1. Checklist

| Câu hỏi | Nếu câu trả lời là “có” |
|---|---|
| Mỗi item độc lập và có thể retry riêng? | Cân nhắc batch/pipeline |
| Có invariant giữa nhiều item? | Cân nhắc transaction/conditional write |
| Bắt buộc không có trạng thái commit một phần? | Không dùng bulk không nguyên tử như cơ chế bảo vệ duy nhất |
| Các item nằm ở nhiều partition/nút? | Kiểm tra phạm vi transaction và chi phí coordination |
| Liên quan email, thanh toán, webhook bên ngoài? | Cần outbox/saga/idempotency; không suy giao dịch chung |
| Có thể đọc projection trễ không? | Cân nhắc eventual read model |
| Có thể retry request sau timeout? | Cần operationId, kết quả không rõ và dedup |
| Batch có item bị throttle? | Retry phần chưa xử lý với backoff |
| Hệ có giới hạn 25/100 hành động hoặc kích thước? | Chia nhóm theo giới hạn API, không tự mở rộng atomicity |
| Chi phí ghi cao hay tranh chấp lớn? | Giảm phạm vi transaction và đo tải |

### 26.2. Quy tắc chọn ngắn gọn

1. **Batch chỉ để nhanh hơn khi các thao tác có thể tồn tại độc lập.**
2. **Transaction để bảo vệ nhóm thay đổi không được phép tồn tại một phần.**
3. **Đọc chính xác hợp đồng atomicity/isolation của API trước khi gọi nó là transaction.**
4. **Đừng kéo transaction xuyên các hệ không hỗ trợ; dùng workflow và phục hồi trạng thái.**
5. **Dù có transaction, vẫn phải xử lý timeout, retry và event bên ngoài.**

## 27. Các hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Một HTTP request chứa 100 thao tác thì nguyên tử | Batch transport không hứa rollback |
| ordered=true nghĩa all-or-nothing | Ordered chỉ liên quan trình tự/dừng sau lỗi |
| HTTP 200 của bulk nghĩa mọi item thành công | Bulk có thể trả trạng thái lỗi ở từng item |
| BatchWriteItem giống TransactWriteItems | Hai API có mục tiêu và bảo đảm khác nhau |
| UnprocessedItems là lỗi đã rollback cả batch | Các item khác có thể đã được ghi |
| Filter/condition tự có ở mọi batch | DynamoDB BatchWriteItem không hỗ trợ điều kiện trên item |
| Redis pipeline giống MULTI/EXEC | Pipeline chỉ tối ưu mạng |
| Redis MULTI có rollback runtime errors như SQL | Những lệnh khác có thể đã có side effects |
| Lua script tự rollback khi error | Script error không tự đảo mọi thay đổi trước đó |
| Cassandra BATCH là bulk loader tối ưu | Batch đa partition có thể thêm coordination/batchlog |
| Cassandra logged batch cung cấp serializable isolation | Không phải transaction SQL tổng quát xuyên partition |
| Transaction thành công nghĩa email cũng đã gửi | Side effect bên ngoài không thuộc DB transaction |
| Timeout nghĩa transaction chắc chắn thất bại | Có thể commit nhưng response mất |
| Retry toàn batch luôn an toàn | Counter/append có thể bị lặp, Put có thể ghi đè |
| Transaction nguồn làm GSI/search mới ngay | Projection eventual có thể trễ |
| Batch lớn nhất luôn throughput cao nhất | Payload, throttling và retry cost có thể tăng |
| Chỉ cần test happy path | Race và partial failure mới phân biệt đúng bảo đảm |

## 28. Bài tập thực hành

### Bài 1. Phân loại API

Cho những thao tác:

1. MongoDB bulkWrite ordered=false.
2. DynamoDB BatchWriteItem.
3. DynamoDB TransactWriteItems.
4. Redis pipeline.
5. Redis MULTI/EXEC.
6. Cassandra LOGGED BATCH.
7. Elasticsearch Bulk API.

Với mỗi thao tác, trả lời:

- Mục tiêu chính là throughput hay atomicity?
- Có thể thấy kết quả một phần không?
- Có rollback toàn nhóm khi một lệnh runtime lỗi không?
- Phạm vi consistency/isolation cần đọc lại là gì?
- Cơ chế retry phù hợp ra sao?

**Gợi ý:** Redis MULTI/EXEC và Cassandra logged batch không nên được mô tả bằng một chữ “ACID” không kèm điều kiện.

### Bài 2. Đọc kết quả BatchWriteItem

Ứng dụng gửi 25 PutRequest. Response có 4 item trong UnprocessedItems.

1. Có thể coi cả 25 item đều đã ghi thành công không?
2. Có thể mặc định 21 item còn lại đã rollback không?
3. Ứng dụng nên retry những item nào?
4. Vì sao phải có exponential backoff/jitter?
5. Nếu PutRequest có cùng key item đã tồn tại, rủi ro gì?

**Gợi ý:** UnprocessedItems là phần chưa xử lý, còn BatchWriteItem không có nguyên tử cả nhóm.

### Bài 3. MongoDB ordered không phải transaction

Batch:

~~~javascript
db.products.insertMany(
  [
    { _id: "P1" },
    { _id: "P2" },
    { _id: "P3" }
  ],
  { ordered: true }
);
~~~

Giả sử P2 đã tồn tại và vi phạm unique index.

1. P1 có thể đã được ghi chưa?
2. P3 có được thử chạy không theo ordered semantics?
3. Có rollback P1 không?
4. Nếu nghiệp vụ yêu cầu cả ba cùng có hoặc cùng không, chọn cơ chế gì?

### Bài 4. DynamoDB đặt ghế

Một ứng dụng có hai item:

~~~text
SEAT#S101 status=AVAILABLE
BOOKING#B1001 chưa tồn tại
~~~

Khi khách đặt ghế, cần đổi SEAT thành RESERVED và tạo BOOKING CONFIRMED.

Hãy:

1. Giải thích vì sao hai Put/Update trong BatchWriteItem không phù hợp.
2. Đề xuất TransactWriteItems với điều kiện giữ ghế.
3. Xử lý hai client đặt S101 đồng thời.
4. Thiết kế requestId và cách trả lời sau timeout không rõ kết quả.
5. Nếu thanh toán nằm ở bên thứ ba, transaction DynamoDB bảo vệ được phần nào?

### Bài 5. Redis pipeline, MULTI và lỗi runtime

Giả sử:

~~~text
keyA = "0"
keyB = "hello"
keyC = "0"
~~~

Client gửi:

~~~redis
MULTI
INCR keyA
INCR keyB
INCR keyC
EXEC
~~~

Hãy xác định vấn đề của INCR keyB, giải thích vì sao keyA/keyC có thể vẫn tăng và nêu cách thiết kế lại để không có trạng thái sai nghiệp vụ.

### Bài 6. Cassandra cùng partition và nhiều partition

Một ứng dụng lưu hành vi của người dùng theo (userId, day). Nó cần ghi hai sự kiện trong một ngày, rồi có luồng khác ghi 10.000 sự kiện của 10.000 người dùng.

1. Trường hợp nào có thể xem xét BATCH cùng partition?
2. Vì sao không nên tự đưa 10.000 event đa partition vào một LOGGED BATCH khổng lồ?
3. Nếu có yêu cầu giao dịch ngân hàng đa tài khoản, tại sao BATCH CQL không tự tạo serializable transaction?
4. Phương án load/async writes có thể tối ưu throughput ra sao?

### Bài 7. Search bulk có lỗi một phần

Bulk response:

~~~json
{
  "errors": true,
  "items": [
    {"index": {"_id": "P1", "status": 201}},
    {"index": {"_id": "P2", "status": 429}},
    {"index": {"_id": "P3", "status": 201}}
  ]
}
~~~

Hãy:

1. Xác định item cần retry.
2. Phân biệt retry một phép index theo ID với retry script tăng số lượt xem.
3. Giải thích vì sao HTTP 200 hoặc request đã hoàn thành không đủ để kết luận tất cả item thành công.
4. Trình bày vai trò của refresh đối với search visibility.

### Bài 8. Tính tiết kiệm round trip

Một client thực hiện 200 thao tác. Giả sử RTT 6 ms và xử lý mỗi thao tác 0,3 ms, bỏ qua các overhead khác.

1. Ước lượng thời gian khi gửi 200 request tuần tự.
2. Ước lượng khi gộp một batch lý tưởng.
3. Tại sao kết quả lý thuyết này không chứng minh batch nguyên tử?
4. Nếu một request tối đa 25 item, cần chia thành bao nhiêu batch?
5. Vì sao 8 batch có thể vẫn được gửi đồng thời có giới hạn thay vì tuần tự, và ảnh hưởng backpressure?

**Gợi ý:**

\[
T_{\text{sequential}}=200(6+0,3)=1260\text{ ms}.
\]

\[
T_{\text{ideal batch}}=6+200(0,3)=66\text{ ms}.
\]

Đây là mô hình minh họa, không bao gồm server coordination và serialization.

### Bài 9. Idempotency khi ghi hàng loạt

Ứng dụng gửi batch chứa:

~~~text
PUT order O1001
INCREMENT salesCounter
APPEND audit event với ID ngẫu nhiên mới mỗi lần retry
~~~

Request timeout sau khi server có thể đã xử lý một phần.

1. Thao tác nào có nguy cơ bị lặp tác dụng?
2. Vì sao retry toàn batch là nguy hiểm?
3. Thiết kế operationId/eventId ổn định và điều kiện ghi.
4. Khi nào cần transaction nguồn + outbox?

### Bài 10. Thiết kế benchmark và fault injection

Hãy lập kế hoạch kiểm thử hai pipeline:

**Pipeline A:** Nạp 100.000 telemetry events độc lập bằng batch.

**Pipeline B:** Tạo 1.000 booking, mỗi booking cần giữ ghế và tạo record nguyên tử.

Đo:

- Throughput thành công.
- Latency p50/p95/p99.
- Số item failed/unprocessed.
- Thời gian backoff và retry count.
- Số transaction conflict/abort.
- Mức tiêu thụ capacity và hot key.
- Tính đúng đắn sau timeout, worker crash và retry.

Giải thích vì sao tiêu chí nghiệm thu của hai pipeline phải khác nhau: A ưu tiên xử lý đủ mọi event với dedup; B ưu tiên invariant không bán trùng ghế.

## 29. Tổng kết

**Batch tối ưu truyền dữ liệu** và **batch có bảo đảm nguyên tử** giải quyết hai vấn đề khác nhau:

- Batch/pipeline/bulk giúp gửi nhiều thao tác với ít round trips hơn và có thể tăng throughput. Nó **không tự hứa all-or-nothing**.
- Atomic transaction bảo vệ một nhóm thay đổi khỏi commit một phần **trong phạm vi và điều kiện mà API công bố**. Nó có chi phí phối hợp, giới hạn và những mức isolation riêng.

Các điểm phải nhớ:

1. **Một request không đồng nghĩa một transaction.** Ordered cũng không đồng nghĩa rollback.
2. **Phân biệt kết quả của cả request với từng item.** BatchWriteItem có UnprocessedItems; Bulk search có item statuses; MongoDB bulk có các quy tắc dừng và lỗi.
3. **Không gán toàn bộ ACID cho mọi API có chữ atomic.** Redis MULTI/EXEC không rollback runtime errors như SQL; Cassandra BATCH không phải serializable multi-partition transaction.
4. **Chọn theo invariant nghiệp vụ.** Ghi log độc lập khác hẳn giữ ghế, cập nhật tồn kho hoặc chuyển tiền.
5. **Retry phải idempotent.** Timeout không chứng minh thất bại; increment, append và side effect bên ngoài có thể bị lặp.
6. **Transaction không bao phủ dịch vụ bên ngoài.** Outbox, saga và compensation cần được thiết kế khi luồng vượt ranh giới datastore.
7. **Hiệu quả cần đo, không suy đoán.** Batch size lớn có thể làm tăng throttling, bộ nhớ, hot partition và chi phí retry.
8. **Xác định visibility/consistency của bản sao.** GSI, search và cache có thể trễ dù transaction nguồn đã commit.

Trước khi viết một batch, hãy tự trả lời câu quyết định: **“Tôi muốn giảm số lần trao đổi mạng, hay tôi cần bảo đảm rằng các thay đổi này không bao giờ được commit riêng lẻ?”** Nếu là ý thứ hai, chỉ sử dụng một cơ chế có **atomicity, isolation và phạm vi lỗi** thực sự phù hợp với invariant cần bảo vệ.

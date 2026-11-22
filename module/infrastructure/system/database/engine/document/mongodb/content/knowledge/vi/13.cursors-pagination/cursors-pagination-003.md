# Đọc tuần tự, đóng cursor và xử lý cursor hết hạn trong MongoDB

Khi một truy vấn MongoDB khớp hàng nghìn hoặc hàng triệu document, ứng dụng không nên tải toàn bộ kết quả vào bộ nhớ chỉ để xử lý từng bản ghi. MongoDB dùng **cursor** để cho phép client lần lượt nhận và duyệt các document, thường thông qua những **batch** được chuyển giữa server và driver. Cách duyệt tuần tự này phù hợp cho báo cáo, xử lý dữ liệu theo luồng, xuất dữ liệu và nhiều công việc đọc có khối lượng lớn.

Tuy nhiên, cursor là một tài nguyên có vòng đời. Nếu chương trình dừng đọc giữa chừng mà không đóng cursor, server có thể phải giữ trạng thái của truy vấn cho đến khi tài nguyên được giải phóng hoặc hết hạn. Nếu chương trình chờ quá lâu giữa các lượt đọc, cursor có thể hết hạn và một lệnh lấy batch tiếp theo có thể thất bại. Vì thế, cần hiểu cả ba việc: **đọc tuần tự**, **đóng cursor đúng lúc** và **khôi phục an toàn khi cursor không còn hợp lệ**.

Trong bài học, ta thực hành với **mongosh** và **MongoDB Java Sync Driver**, rồi áp dụng cơ chế kiểm tra điểm tiếp tục (checkpoint) để xử lý dữ liệu lâu dài. Đây là nội dung về **cursor thông thường**; tailable cursor, Change Streams và các hình thức phân trang khác có một số quy tắc riêng sẽ được phân biệt khi cần thiết.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích cách một truy vấn MongoDB tạo cursor, trả batch đầu và sử dụng lệnh **getMore** để tải thêm dữ liệu.
- Duyệt cursor bằng **hasNext()**, **next()**, vòng lặp, **forEach()**; hiểu vì sao **toArray()** không thích hợp với tập kết quả quá lớn.
- Phân biệt **batchSize**, **limit**, **sort** và **skip**; biết batchSize chỉ kiểm soát cách truyền kết quả theo lô.
- Chủ động **close()** trong mongosh và **try-with-resources** trong Java để tránh giữ tài nguyên không cần thiết.
- Nhận diện cursor hết hạn do không hoạt động, bị đóng, bị kill, session hết hạn hoặc kết nối gián đoạn.
- Thiết kế cách đọc lại sau lỗi bằng một mốc đã xử lý (checkpoint), với thứ tự ổn định và nguyên tắc xử lý trùng lặp.

## 2. Cursor là gì và vì sao cần nó?

Giả sử collection **orders** có một triệu document. Một câu truy vấn:

~~~javascript
db.orders.find({ status: "PAID" })
~~~

không có nghĩa toàn bộ document phù hợp luôn được gửi về cho client trong một lần. MongoDB có thể trả về một **batch đầu tiên** cùng một định danh cursor do server quản lý. Khi client duyệt hết batch hiện có, driver có thể phát lệnh **getMore** để nhận batch tiếp theo. Quá trình tiếp tục cho đến khi kết quả đã được đọc hết, cursor bị đóng hoặc xảy ra lỗi.

~~~text
Ứng dụng / mongosh                   MongoDB server
       |                                   |
       |-------- find(query) ------------->|
       |<------- firstBatch + cursorId ----|
       |                                   |
       |   Đọc document trong firstBatch   |
       |                                   |
       |-------- getMore(cursorId) ------->|
       |<------- nextBatch + cursorId -----|
       |                                   |
       |   Đọc document trong nextBatch    |
       |                                   |
       |-------- getMore(cursorId) ------->|
       |<------- batch cuối / id = 0 ------|
       |                                   |
       |   Cursor đã được duyệt hết        |
       |                                   |
~~~

**firstBatch**, **nextBatch** và **cursorId** là các thành phần thường thấy trong phản hồi của các lệnh ở cấp giao thức. Thư viện Java thường che phần điều khiển getMore và cung cấp một API duyệt quen thuộc, chẳng hạn **MongoCursor.next()**.

### 2.1. Cursor là con trỏ duyệt, không phải danh sách đã tải sẵn

Ví dụ mongosh:

~~~javascript
const cursor = db.orders.find({ status: "PAID" });
~~~

Biến **cursor** là đối tượng giúp duyệt kết quả. Tùy driver và thao tác, việc gửi truy vấn đến server có thể diễn ra khi client bắt đầu lấy kết quả, thay vì tại thời điểm xây dựng đối tượng filter. Không nên đồng nhất việc giữ đối tượng cursor với việc đã có toàn bộ document trong bộ nhớ.

### 2.2. Cursor cần tài nguyên ở client và có thể cần trạng thái ở server

Server có thể giữ thông tin liên quan đến kết quả, vị trí duyệt và kế hoạch truy vấn của cursor đang mở. Client cũng quản lý batch nhận được, đối tượng cursor, trạng thái giải mã BSON và những tài nguyên liên quan. Khi một cursor không còn cần thiết, đóng nó giúp giảm tài nguyên được giữ ở cả hai phía.

Điều này quan trọng khi ứng dụng có nhiều request đồng thời. Một cursor bị bỏ quên ở mỗi request có thể tích lũy thành nhiều cursor chờ hết hạn.

### 2.3. Không phải mọi truy vấn đều giữ cursor phía server lâu dài

Nếu một truy vấn có ít kết quả và toàn bộ kết quả đã được trả trong batch đầu, cursor phía server có thể **đã hoàn tất ngay**. Trái lại, truy vấn có nhiều kết quả hoặc chỉ đọc một phần sẽ có khả năng để lại cursor đang mở. Vì thế, chương trình nên đóng cursor sau khi sử dụng dù tập dữ liệu khi chạy thử đôi khi rất nhỏ.

## 3. Chuẩn bị dữ liệu thực hành

Các ví dụ dưới đây chạy trong **mongosh** kết nối với MongoDB đang hoạt động. Hãy dùng database học tập riêng:

~~~javascript
use cursor_lab
~~~

Nếu collection chưa tồn tại, tạo 24 document có trường **seq** duy nhất, tăng dần:

~~~javascript
const docs = Array.from({ length: 24 }, (_, i) => {
  const n = i + 1;
  return {
    _id: "EVT-" + String(n).padStart(4, "0"),
    seq: n,
    category: n % 2 === 0 ? "SYSTEM" : "USER",
    message: "Event " + n,
    processed: false
  };
});

db.events.insertMany(docs);
~~~

Tạo index để phục vụ việc đọc có thứ tự và các câu truy vấn theo điểm tiếp tục:

~~~javascript
db.events.createIndex({ seq: 1 }, { unique: true });
~~~

Nếu chạy lại **insertMany** trên dữ liệu đã tạo, thao tác có thể báo trùng _id; đó là hành vi bình thường. Trong bài thực hành, hãy chạy lệnh tạo dữ liệu một lần trên collection mới hoặc dùng database test khác.

Thử kiểm tra:

~~~javascript
db.events.countDocuments({});
db.events.find(
  {},
  { _id: 1, seq: 1, category: 1 }
).sort({ seq: 1 }).limit(5);
~~~

Kết quả kỳ vọng có 24 document. Năm document đầu sau khi sort có **seq từ 1 đến 5**. Đây là dữ liệu để theo dõi từng lượt duyệt mà không phải đọc một tập kết quả lớn.

## 4. Đọc tuần tự bằng cursor trong mongosh

### 4.1. hasNext() và next()

Một vòng lặp duyệt thông thường:

~~~javascript
const cursor = db.events
  .find({}, { _id: 1, seq: 1, message: 1 })
  .sort({ seq: 1 })
  .batchSize(5);

try {
  while (cursor.hasNext()) {
    const doc = cursor.next();
    print(doc.seq + " - " + doc.message);
  }
} finally {
  cursor.close();
}
~~~

Ở đây:

1. **find()** xác định bộ lọc và projection.
2. **sort({seq: 1})** yêu cầu duyệt tăng dần theo seq.
3. **batchSize(5)** đề nghị lấy kết quả theo những batch có số document tối đa phù hợp, ngoài các giới hạn khác của server.
4. **hasNext()** kiểm tra còn document để đọc hay không; khi cần có thể khiến client yêu cầu batch tiếp theo.
5. **next()** lấy document kế tiếp.
6. **finally** bảo đảm gọi **close()** cả khi việc xử lý document ném lỗi.

Đây là ví dụ **đọc tuần tự**: chương trình xử lý từng document, không cần lưu một array 24 document do ứng dụng tự tạo từ kết quả.

### 4.2. Không gọi next() vô điều kiện

Trong mô hình thông thường, khi cursor đã hết kết quả, gọi next() tiếp có thể gây lỗi vì không còn document. Dùng hasNext() để kiểm tra và chỉ gọi next() khi có giá trị. Đối với một số API iterator, phương thức hasNext() cũng có thể chờ server trả batch kế tiếp, vì vậy đừng cho rằng hasNext() luôn là phép kiểm tra cục bộ không tốn thời gian.

### 4.3. forEach() giúp xử lý từng document

Một cách gọn:

~~~javascript
const cursor = db.events
  .find({ category: "SYSTEM" })
  .sort({ seq: 1 })
  .batchSize(4);

try {
  cursor.forEach(doc => {
    print("SYSTEM event: " + doc.seq);
  });
} finally {
  cursor.close();
}
~~~

Đoạn trên chỉ đọc event có **seq chẵn** trong dữ liệu mẫu, tức 12 document. Đây là kiểu duyệt thuận tiện cho tác vụ đơn giản; nếu muốn chủ động dừng theo điều kiện, ghi checkpoint hoặc xử lý lỗi riêng từng document, vòng **while + hasNext/next** có thể rõ ràng hơn.

### 4.4. toArray() khác với duyệt tuần tự

~~~javascript
const allEvents = db.events.find().toArray();
~~~

Lệnh trên đưa toàn bộ kết quả vào **một array trong bộ nhớ client**. Với 24 document thử nghiệm thì tiện, nhưng với hàng triệu document hoặc payload lớn, có thể tiêu tốn nhiều bộ nhớ và gây áp lực lên ứng dụng.

| Cách đọc | Đặc điểm | Phù hợp |
|---|---|---|
| while + next() | Xử lý từng document | Tập lớn, streaming nghiệp vụ |
| forEach() | Callback cho từng document | Duyệt và xử lý đơn giản |
| toArray() | Gom toàn bộ kết quả | Tập nhỏ, biết trước kích thước |
| findOne() | Lấy một document phù hợp | Chỉ cần một record |
| find().limit(N) | Giới hạn tối đa N document trả về | Xem trước hoặc xử lý một phần |

Việc server gửi kết quả theo batch **không bảo vệ ứng dụng khỏi tràn bộ nhớ** nếu sau đó chính code lại đưa mọi document vào một list/array vô hạn.

## 5. batchSize, limit, sort và skip khác nhau ra sao?

### 5.1. batchSize điều khiển cách truyền theo lô

~~~javascript
db.events.find().sort({ seq: 1 }).batchSize(5);
~~~

Với 24 document, server/driver có thể cần nhiều lượt lấy batch để trả đủ dữ liệu. **batchSize(5) không có nghĩa chỉ trả 5 document tổng cộng**. Số document thực tế trong mỗi batch còn chịu giới hạn phản hồi và cách server xử lý; không nên kỳ vọng mọi batch đều có đúng 5 document.

Giảm batchSize có thể làm tăng số lượt trao đổi mạng. Tăng batchSize có thể giảm số round-trip nhưng cần thêm bộ nhớ đệm trong client. Hãy chọn theo kích thước document, tốc độ xử lý và độ trễ mạng.

### 5.2. limit giới hạn tổng số document

~~~javascript
db.events
  .find()
  .sort({ seq: 1 })
  .limit(5);
~~~

Truy vấn trên chỉ yêu cầu tối đa **5 document** trong kết quả. Trong khi đó, **batchSize(5)** vẫn cho phép đọc lần lượt cả 24 document khi tiếp tục duyệt.

Trong giao tiếp trực tiếp với server, limit và batchSize có các quy tắc phối hợp khi tạo/getMore cursor; ý nghĩa quan trọng ở cấp ứng dụng là **limit kiểm soát tổng số record muốn lấy, còn batchSize kiểm soát việc phân lô**.

### 5.3. sort quyết định thứ tự, không phải batchSize

~~~javascript
db.events
  .find({ category: "USER" })
  .sort({ seq: 1 })
  .batchSize(3);
~~~

Batch có thể được chia thành nhiều phần, nhưng thứ tự kết quả vẫn theo điều kiện **sort({seq: 1})** của truy vấn. **batchSize không tạo thứ tự**, còn thứ tự không được chỉ định có thể thay đổi theo kế hoạch truy vấn và trạng thái dữ liệu.

### 5.4. skip không phải cơ chế tiếp tục mạnh cho tập lớn

~~~javascript
db.events
  .find()
  .sort({ seq: 1 })
  .skip(10)
  .limit(5);
~~~

Trên tập dữ liệu mẫu bất biến, câu này lấy các document có seq 11–15. Nhưng nếu tập dữ liệu thay đổi trong lúc phân trang, các vị trí skip có thể dịch chuyển khiến ứng dụng thấy trùng hoặc bỏ sót record. Với offset lớn, server còn phải đi qua nhiều kết quả trước vị trí cần lấy, dẫn đến chi phí tăng.

Khi muốn tiếp tục đọc bền vững sau lỗi, nên cân nhắc **keyset pagination** theo một khóa có thứ tự ổn định như seq hoặc cặp (createdAt, _id); phần sau sẽ minh họa chi tiết.

## 6. Đóng cursor chủ động

Cursor có thể được tự giải phóng khi đã duyệt hết kết quả, nhưng điều đó không có nghĩa chương trình có thể bỏ qua việc quản lý tài nguyên.

### 6.1. Đóng khi chỉ cần một phần kết quả

Giả sử ứng dụng chỉ cần quan sát ba event đầu rồi dừng:

~~~javascript
const cursor = db.events
  .find({}, { seq: 1, message: 1 })
  .sort({ seq: 1 })
  .batchSize(5);

try {
  let count = 0;
  while (count < 3 && cursor.hasNext()) {
    printjson(cursor.next());
    count++;
  }
} finally {
  cursor.close();
}
~~~

Ở đây có thể vẫn còn kết quả chưa được đọc. **close()** báo rằng chương trình không cần cursor nữa. Khi còn cursor phía server, driver có thể gửi yêu cầu **killCursors** để giải phóng tài nguyên liên quan. Việc đóng có ý nghĩa ngay cả khi bạn không có ý định đọc tiếp.

### 6.2. Vì sao nên dùng finally?

Nếu chương trình xử lý document gặp lỗi giữa chừng:

~~~javascript
function processEvent(doc) {
  if (doc.seq === 3) {
    throw new Error("Giả lập lỗi xử lý");
  }
  print(doc.seq);
}
~~~

thì vòng lặp có thể kết thúc trước khi đọc hết cursor. Đặt close() trong finally giúp nó vẫn được gọi:

~~~javascript
const cursor = db.events.find().sort({ seq: 1 });

try {
  while (cursor.hasNext()) {
    processEvent(cursor.next());
  }
} finally {
  cursor.close();
}
~~~

**Không nên chỉ đóng trong nhánh xử lý thành công**, vì lỗi mạng, lỗi logic hoặc người dùng hủy tác vụ đều có thể làm vòng lặp kết thúc sớm.

### 6.3. Đóng cursor khác đóng kết nối

Đóng **cursor** giải phóng tài nguyên của một truy vấn. Đóng **MongoClient** chấm dứt việc sử dụng tài nguyên client, bao gồm connection pool và các tác vụ liên quan. Trong ứng dụng server Java, thông thường cần **tái sử dụng MongoClient** cho nhiều request và **đóng từng MongoCursor** sau mỗi lần đọc.

Không tạo MongoClient mới cho mọi document chỉ để tránh quản lý cursor; cách đó làm tăng chi phí kết nối và khó vận hành.

## 7. Duyệt và đóng cursor trong MongoDB Java Sync Driver

Trong Java, MongoDB Sync Driver cung cấp **MongoCollection**, **FindIterable** và **MongoCursor**. Một đối tượng **FindIterable** mô tả cách lấy kết quả, còn **MongoCursor** được dùng để duyệt tuần tự. **MongoCursor** triển khai cơ chế đóng tài nguyên, vì vậy có thể dùng **try-with-resources**.

Ví dụ cần project có dependency **org.mongodb:mongodb-driver-sync** phù hợp và có biến môi trường **MONGODB_URI** trỏ tới MongoDB.

### 7.1. Ví dụ hoàn chỉnh: đọc theo thứ tự và đóng tự động

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class SequentialCursorReader {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("cursor_lab")
                    .getCollection("events");

            try (MongoCursor<Document> cursor = events.find()
                    .projection(Projections.include("seq", "message"))
                    .sort(Sorts.ascending("seq"))
                    .batchSize(5)
                    .iterator()) {

                while (cursor.hasNext()) {
                    Document doc = cursor.next();
                    int seq = doc.getInteger("seq");
                    String message = doc.getString("message");
                    System.out.println(seq + " - " + message);
                }
            }
        }
    }
}
~~~

Trong chương trình:

1. **MongoClient** tạo và quản lý kết nối theo cấu hình driver.
2. **events.find()** xây dựng truy vấn.
3. **sort()** yêu cầu thứ tự kết quả.
4. **batchSize(5)** đặt kích thước batch mong muốn.
5. **iterator()** trả về MongoCursor để duyệt.
6. **try-with-resources** gọi close() khi ra khỏi phạm vi, kể cả khi hasNext(), next() hoặc phần xử lý document xảy ra ngoại lệ.

Mã ví dụ đóng MongoClient khi chương trình dòng lệnh kết thúc. Trong ứng dụng web/Spring Boot chạy lâu dài, MongoClient thông thường được quản lý ở cấp ứng dụng hoặc dependency injection; **không đóng client sau mỗi query**. Bạn vẫn cần đóng cursor ở phạm vi từng lần đọc.

### 7.2. Dừng sớm nhưng vẫn giải phóng cursor

~~~java
try (MongoCursor<Document> cursor = events.find()
        .sort(Sorts.ascending("seq"))
        .batchSize(10)
        .iterator()) {

    int processed = 0;
    while (cursor.hasNext() && processed < 3) {
        Document event = cursor.next();
        System.out.println(event.getInteger("seq"));
        processed++;
    }
}
~~~

Vòng lặp chỉ lấy tối đa ba document. Khi thoát khối try, driver đóng cursor. Đây là trường hợp đặc biệt quan trọng vì server có thể còn nhiều document chưa gửi về.

### 7.3. Tránh dùng into(new ArrayList<>()) với dữ liệu không giới hạn

~~~java
// Chỉ phù hợp khi biết trước số lượng dữ liệu đủ nhỏ.
List<Document> allEvents = events.find()
        .into(new ArrayList<>());
~~~

Hàm **into()** gom tất cả document trả về vào collection bên Java. Driver có thể tải kết quả theo batch ở tầng giao tiếp, nhưng List cuối cùng vẫn có thể lớn đến mức gây thiếu bộ nhớ.

Nếu công việc là đọc hàng triệu document rồi xử lý từng record, dùng **MongoCursor trong try-with-resources** hoặc dùng API reactive phù hợp với kiến trúc ứng dụng, kèm kiểm soát backpressure.

## 8. Cursor hết hạn là gì?

Một cursor đang mở không được bảo đảm tồn tại vĩnh viễn. MongoDB có cơ chế giải phóng cursor không còn hoạt động để tránh rò rỉ tài nguyên.

### 8.1. Thời gian không hoạt động của cursor

Trong cấu hình thông dụng, MongoDB có thể đóng **cursor không còn hoạt động khoảng 10 phút** (mặc định đối với idle cursor thuộc phạm vi quản lý timeout). Nếu chương trình lấy một batch rồi dừng rất lâu trước khi yêu cầu batch tiếp theo, server có thể coi cursor là bỏ quên và đóng nó.

Ví dụ tình huống:

~~~text
T0      Client nhận 1 batch, vẫn còn cursor phía server
T1      Client xử lý batch rất chậm hoặc không làm gì
T2      Thời gian idle vượt ngưỡng của server
T3      Server đóng cursor theo chính sách timeout
T4      Client cố getMore bằng cursorId cũ -> lỗi
~~~

Ngưỡng, cách dọn dẹp và hành vi chính xác còn phụ thuộc cấu hình MongoDB, phiên bản và kiểu cursor. Con số **10 phút** là mặc định thường gặp để hiểu cơ chế, không phải hợp đồng rằng mọi cursor sẽ bị đóng đúng tại giây thứ 600.

**Quan trọng:** quá trình xử lý dữ liệu lâu trong code client không đồng nghĩa cursor đang giao tiếp với server. Nếu client không gửi thao tác làm mới phiên/cursor trong lúc xử lý, server có thể xem cursor hoặc session là idle.

### 8.2. Session timeout có thể làm cursor bị đóng

MongoDB dùng **logical session** để theo dõi nhiều hoạt động của client. Mặc định thường gặp, một session không hoạt động khoảng **30 phút** có thể hết hạn. Khi session bị hết hạn, server có thể đóng những cursor được gắn với session đó.

Vì vậy, cần phân biệt:

| Nguyên nhân | Khái niệm | Hệ quả |
|---|---|---|
| Cursor idle timeout | Cursor không được sử dụng trong khoảng thời gian theo chính sách | Server có thể đóng cursor |
| Logical session timeout | Session của client không có hoạt động làm mới đủ lâu | Cursor thuộc session có thể bị đóng |
| Client chủ động close() | Ứng dụng đã đọc đủ hoặc hủy thao tác | Cursor được giải phóng |
| Server killCursors | Quản trị hoặc xử lý hủy cursor | getMore tiếp theo không thể dùng cursor cũ |
| Lỗi mạng/đổi kết nối/failover | Client không còn truy cập được kết quả như trước | Cursor có thể không tiếp tục được, phụ thuộc loại lỗi |
| Duyệt hết kết quả | Cursor đã hết document cần trả | Cursor hoàn tất bình thường |

Một cursor được đóng khi đã hết kết quả **không phải lỗi**. Ngược lại, một lỗi trong lúc vẫn còn dữ liệu cần đọc có thể làm tiến trình dở dang. Ứng dụng cần phân biệt hai trường hợp.

### 8.3. noCursorTimeout không làm cursor sống mãi

MongoDB hỗ trợ tùy chọn **noCursorTimeout** để tránh cơ chế idle timeout thông thường dành cho cursor. Trong mongosh, có thể dùng:

~~~javascript
const cursor = db.events
  .find()
  .sort({ seq: 1 })
  .noCursorTimeout();

try {
  while (cursor.hasNext()) {
    printjson(cursor.next());
  }
} finally {
  cursor.close();
}
~~~

Trong Java Sync Driver, FindIterable có thể được cấu hình:

~~~java
try (MongoCursor<Document> cursor = events.find()
        .sort(Sorts.ascending("seq"))
        .noCursorTimeout(true)
        .iterator()) {

    while (cursor.hasNext()) {
        processEvent(cursor.next());
    }
}
~~~

Hàm **processEvent** ở đây đại diện cho logic xử lý do ứng dụng định nghĩa.

**Cần nhớ:** noCursorTimeout **không miễn trừ cơ chế hết hạn logical session**. Nếu session bị coi là không hoạt động quá lâu, cursor vẫn có thể bị đóng. Ngoài ra, server restart, killCursors, lỗi mạng và các vấn đề khác vẫn có thể làm cursor mất hiệu lực.

Do đó, noCursorTimeout không phải chiến lược chính để bảo đảm một batch job kéo dài nhiều giờ không mất tiến độ. Nếu thực sự cần đọc lâu, hãy chia công việc thành các đoạn có điểm tiếp tục, quản lý session theo cơ chế driver/triển khai phù hợp, và bảo đảm đóng tài nguyên.

### 8.4. Khi nào nên tránh noCursorTimeout?

Nếu ứng dụng có bug làm bỏ quên cursor, noCursorTimeout khiến cursor có nguy cơ giữ tài nguyên lâu hơn chính sách thông thường. Trong ứng dụng web có nhiều request hoặc batch job thường xuyên bị hủy, điều đó làm tăng nguy cơ tồn đọng cursor.

Trước khi bật tùy chọn này, nên hiểu rõ thời gian xử lý mỗi batch, thời gian idle thực sự, timeout của session và cơ chế đóng cursor. Nhiều tác vụ có thể được cải thiện bằng cách **giảm công việc giữa các lần getMore**, **xử lý thành các trang độc lập** hoặc **ghi checkpoint**.

## 9. Nhận biết lỗi cursor bị đóng hoặc không còn tồn tại

Giả sử client có cursorId nhưng server đã dọn dẹp cursor. Khi driver cần yêu cầu thêm dữ liệu, lệnh **getMore** có thể trả lỗi như **CursorNotFound** (mã lỗi MongoDB thường gặp là **43**). MongoDB driver có thể biểu diễn lỗi bằng một ngoại lệ liên quan đến cursor hoặc MongoException, tùy phiên bản thư viện và tình huống.

Các dấu hiệu đáng chú ý:

- Ứng dụng đọc được vài batch rồi lỗi ở **hasNext()** hoặc **next()**, dù cùng filter trước đó chạy tốt.
- Log/exception cho thấy **cursor id không còn tồn tại**, cursor bị kill hoặc operation gián đoạn.
- Tác vụ đọc từng batch xử lý quá lâu giữa các lượt getMore.
- Client đã đóng cursor hoặc session đã kết thúc nhưng code vẫn cố đọc tiếp.
- Kết nối mạng bị ngắt, server restart hoặc topology thay đổi khiến cursor không thể tiếp tục.

Không phải mọi lỗi đọc cursor đều là timeout. Ví dụ lỗi quyền truy cập, lỗi giải mã BSON, máy chủ không sẵn sàng hoặc điều kiện truy vấn không hợp lệ cũng có thể xuất hiện. Khi xử lý, cần xem **loại ngoại lệ, mã lỗi và ngữ cảnh vận hành**, thay vì retry tất cả lỗi theo một cách.

### 9.1. Không đọc tiếp một cursor đã mất hiệu lực

Khi server không còn giữ cursorId, client không thể mặc nhiên nối lại **chính cursorId đó**. Một hành động phù hợp thường là:

1. Ghi nhận vị trí đã xử lý thành công.
2. Đóng cursor cũ ở phía client.
3. Đánh giá lỗi có thể thử lại hay không.
4. Tạo **truy vấn mới** bắt đầu từ sau vị trí đã xử lý.
5. Tiếp tục với cơ chế chống xử lý trùng khi cần.

Việc tạo lại cursor bằng cùng filter ban đầu mà không giới hạn điểm tiếp tục có thể làm đọc lại tất cả document từ đầu. Nếu một số document đã được gửi email, ghi file hoặc cập nhật hệ thống khác, hậu quả có thể là hành động bị lặp.

### 9.2. Không đồng nhất mọi lỗi với CursorNotFound

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Cursor đã được đọc hết bình thường | Hoàn thành tác vụ, đóng tài nguyên |
| CursorNotFound sau thời gian idle | Đánh giá tạo truy vấn mới từ checkpoint |
| Client chủ động close, sau đó code gọi next | Sửa vòng đời đối tượng; không retry vô hạn |
| Lỗi mạng tạm thời | Retry có giới hạn, kiểm tra idempotency và điểm tiếp tục |
| Filter sai hoặc BSON decode lỗi | Sửa dữ liệu/code; retry y nguyên có thể lặp lỗi |
| Server bị quá tải | Theo dõi, giảm tốc, backoff và đo vận hành |
| Thiếu quyền hoặc cấu hình sai | Khắc phục quyền/cấu hình trước khi chạy lại |

Trường hợp **lỗi không có tiến độ hay điểm checkpoint** cần được thiết kế riêng; không tự khẳng định có thể tiếp tục chính xác từ vị trí cũ.

## 10. Khôi phục sau khi cursor hết hạn bằng checkpoint

**Checkpoint** là thông tin cho biết phần dữ liệu nào đã được xử lý thành công. Nếu không thể tiếp tục cursor cũ, ứng dụng dùng checkpoint để dựng **truy vấn mới** chỉ lấy những document sau vị trí đã ghi nhận.

Với bộ dữ liệu của bài, trường **seq** là số tăng dần và có **unique index**. Đây là một khóa thuận tiện để thử nghiệm phương pháp đọc tiếp:

~~~text
Cursor đầu tiên:  seq = 1, 2, 3, 4, 5, 6, ...
                                  |
                         Đã xử lý đến seq=4
                                  |
                     Lỗi timeout / network
                                  |
                                  v
                     Checkpoint lastSeq=4
                                  |
                                  v
Cursor mới:       find({ seq: { $gt: 4 } }).sort({ seq: 1 })
                                  |
                                  v
                     seq = 5, 6, 7, 8, ...
~~~

Điều kiện **$gt: lastSeq** bỏ qua bản ghi đã xử lý đến mốc lastSeq, còn **sort({seq: 1})** giúp kết quả có thứ tự rõ ràng.

### 10.1. Duyệt theo nhiều trang độc lập trong mongosh

Ví dụ đọc những trang có nhiều nhất năm document:

~~~javascript
let lastSeq = 0;
const pageSize = 5;

while (true) {
  const page = db.events
    .find(
      { seq: { $gt: lastSeq } },
      { _id: 1, seq: 1, message: 1 }
    )
    .sort({ seq: 1 })
    .limit(pageSize)
    .toArray();

  if (page.length === 0) {
    break;
  }

  for (const event of page) {
    print("Processed " + event.seq);
    lastSeq = event.seq;
  }
}
~~~

Trong ví dụ này, **toArray() chỉ gom một trang tối đa năm document**, không gom toàn bộ collection. Mỗi vòng tạo một truy vấn có giới hạn và một điểm tiếp tục, nên không có nhu cầu giữ một cursor dài suốt toàn bộ batch job.

Đây là ví dụ ở mức **cơ chế**. Biến lastSeq nằm trong bộ nhớ mongosh; nếu tiến trình bị tắt, biến sẽ mất. Đối với công việc cần phục hồi thực sự, phải ghi checkpoint vào nơi bền vững sau khi hoàn thành công việc với document tương ứng.

### 10.2. Khi nào được nâng checkpoint?

Giả sử xử lý event bao gồm ghi dữ liệu sang hệ thống khác. Quy tắc cốt lõi:

> Chỉ ghi nhận một document là đã xử lý khi các tác vụ bắt buộc cho document đó đã thành công theo hợp đồng nghiệp vụ.

Nếu nâng lastSeq **trước** khi ghi kết quả thành công, rồi chương trình gặp lỗi, lần chạy sau sẽ bỏ qua document chưa được xử lý hoàn chỉnh. Ngược lại, nếu ghi kết quả xong nhưng chết trước khi lưu checkpoint, lần chạy sau có thể xử lý lại document.

Do đó, checkpoint giúp **tiếp tục tiến độ**, nhưng không tự cung cấp exactly-once processing. Các tác vụ có side effect cần tính **idempotency**, khóa xử lý duy nhất, transaction phù hợp hoặc cơ chế outbox/inbox theo kiến trúc hệ thống.

### 10.3. Dùng hai khóa khi trường sort không duy nhất

Trong thực tế, nhiều document có thể có cùng **createdAt**. Nếu chỉ lưu checkpoint bằng thời điểm và dùng:

~~~javascript
{ createdAt: { $gt: lastCreatedAt } }
~~~

thì các document **cùng createdAt** chưa kịp xử lý có thể bị bỏ qua. Cần một khóa phụ tạo thứ tự ổn định, ví dụ **(createdAt, _id)**:

~~~javascript
const lastCreatedAt = ISODate("2026-11-14T09:00:00Z");
const lastId = ObjectId("66f1c2a4b1d2e3f405162738");

db.auditEvents.find({
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
})
  .sort({ createdAt: 1, _id: 1 })
  .limit(100);
~~~

Đây là ví dụ khái niệm với collection **auditEvents**, giả định _id là ObjectId và cả hai trường có kiểu BSON nhất quán. Query nên được hỗ trợ bằng index thích hợp, chẳng hạn **{createdAt: 1, _id: 1}**.

Để dùng làm checkpoint, thứ tự phải **xác định rõ ràng và ổn định**, đặc biệt không được thay đổi tùy tiện giá trị khóa của record đã xử lý. Nếu giá trị sort có thể bị chỉnh sửa, một document có thể nhảy từ phía sau lên phía trước checkpoint hoặc ngược lại.

### 10.4. Dùng _id có bảo đảm thứ tự chèn tuyệt đối không?

ObjectId có một thành phần thời gian, nhưng không nên coi việc sort theo ObjectId là bằng chứng chắc chắn về thứ tự chèn tuyệt đối giữa nhiều client, nhất là khi client tạo ObjectId độc lập, đồng hồ khác nhau hoặc có ghi đến trễ. Trong ví dụ thực hành, **seq được thiết kế chủ động là duy nhất và tăng dần**, nên mới phù hợp làm điểm tiếp tục.

Trong hệ thống nghiệp vụ, hãy xác định rõ khóa thứ tự, thời điểm tạo khóa, tính duy nhất, khả năng cập nhật và các bản ghi đến muộn. Nếu cần một snapshot đầy đủ bất biến của một tập dữ liệu tại thời điểm xác định, chỉ checkpoint trên một collection đang thay đổi có thể không đủ để bảo đảm ngữ nghĩa đó.

## 11. Java: xử lý theo trang nhỏ để có thể tiếp tục

Đối với batch job có nguy cơ xử lý một record rất lâu, thay vì giữ một cursor liên tục trong nhiều giờ, có thể chọn kiến trúc **đọc từng trang ngắn, xử lý xong, lưu checkpoint và mở trang tiếp theo**.

Ví dụ Java Sync Driver bên dưới diễn tả cách đọc các trang theo seq. Mã này in log để minh họa; để phục hồi qua lần chạy khác, ứng dụng thực tế cần nạp và lưu checkpoint từ database hoặc kho trạng thái của job.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class PagedCursorReader {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        int pageSize = 5;
        int lastSeq = 0; // Trong ứng dụng thật: đọc từ checkpoint đã lưu.

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("cursor_lab")
                    .getCollection("events");

            while (true) {
                List<Document> page = events
                        .find(Filters.gt("seq", lastSeq))
                        .sort(Sorts.ascending("seq"))
                        .limit(pageSize)
                        .into(new ArrayList<>());

                if (page.isEmpty()) {
                    break;
                }

                for (Document event : page) {
                    int seq = event.getInteger("seq");
                    // Ở đây thay bằng logic xử lý thực tế.
                    System.out.println("Processed event " + seq);

                    // Chỉ nâng mốc sau khi xử lý đã thành công.
                    lastSeq = seq;
                    // Trong ứng dụng thật: lưu checkpoint bền vững ở đây.
                }
            }
        }
    }
}
~~~

Mỗi trang chỉ chứa tối đa năm document, nên **into(new ArrayList<>())** ở đây có giới hạn rõ ràng. Truy vấn trang vẫn có cursor bên trong driver, nhưng ứng dụng không giữ một MongoCursor sống lâu qua toàn bộ vòng xử lý. 

### 11.1. Nếu trang đang xử lý bị lỗi thì sao?

Giả sử trang có seq 11–15, ứng dụng xử lý xong 11, 12 rồi lỗi ở 13:

- Nếu checkpoint đã lưu bền vững là **12**, lần sau truy vấn **seq > 12**.
- Nếu checkpoint mới chỉ lưu đến **10**, có thể phải xử lý lại 11, 12; logic cần chịu được việc lặp.
- Nếu checkpoint đã bị nâng lên **15** khi mới tải trang nhưng chưa xử lý xong, lần sau sẽ bỏ sót công việc từ 13 đến 15.

Vì vậy, **đọc xong một trang không đồng nghĩa xử lý xong trang**. Thời điểm ghi checkpoint phải tương ứng với thành công nghiệp vụ.

### 11.2. Khi nào nên giữ một cursor dài?

Một cursor duyệt liên tục có thể vẫn phù hợp khi:

- Ứng dụng có thể xử lý từng document nhanh.
- Mỗi batch được tiêu thụ đều đặn.
- Không cần dừng và khôi phục ở một checkpoint nghiệp vụ.
- Tập kết quả và thời gian đọc nằm trong các giới hạn vận hành đã dự tính.

Ngược lại, nếu mỗi document có tác vụ mạng kéo dài, gọi dịch vụ ngoài hoặc nhiều bước không thể hoàn tất nhanh, **chia trang và checkpoint** thường giúp giảm sự phụ thuộc vào thời gian sống của một cursor.

## 12. Lỗi xảy ra trong lúc duyệt Java: đặt phạm vi retry hợp lý

Trong MongoDB Java Sync Driver, lỗi có thể xuất hiện khi truy vấn ban đầu, khi driver gọi getMore, hoặc khi mã ứng dụng xử lý từng document. Có thể phân biệt ở mức ngoại lệ:

~~~java
import com.mongodb.MongoException;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

try (MongoCursor<Document> cursor = events.find()
        .sort(new Document("seq", 1))
        .iterator()) {

    while (cursor.hasNext()) {
        Document event = cursor.next();
        System.out.println(event.getInteger("seq"));
    }
} catch (MongoException ex) {
    System.err.println(
            "MongoDB read failed; errorCode=" + ex.getCode()
    );
    throw ex;
}
~~~

Đây là đoạn minh họa đặt trong phương thức đã có biến **events**. Khối try-with-resources tự đóng cursor cả khi ngoại lệ được ném ra.

Trong MongoDB, **CursorNotFound** thường tương ứng mã lỗi **43**, nhưng các sự cố liên quan cursor còn có thể có loại ngoại lệ hoặc mã khác. Không nên chỉ kiểm tra một con số rồi tự coi mọi sự cố còn lại đều có thể tiếp tục.

### 12.1. Một chiến lược retry có kiểm soát

Với tác vụ có checkpoint:

~~~text
Đọc checkpoint từ nơi bền vững
              |
              v
     Mở truy vấn từ sau checkpoint
              |
              v
        Nhận document / trang
              |
              v
       Xử lý nghiệp vụ thành công?
          /                \
        Có                 Không
        |                    |
   Lưu checkpoint      Phân loại lỗi
        |                    |
      Tiếp tục       Lỗi tạm thời?
                          /     \
                        Có     Không
                         |        |
                 Backoff giới hạn Báo lỗi / dừng job
                         |
                Mở truy vấn mới từ checkpoint
~~~

Nên giới hạn số lượt retry, áp dụng **backoff** phù hợp với hạ tầng và có khả năng hủy job. Không retry vô hạn lỗi dữ liệu hoặc lỗi quyền truy cập. Và **không cố tiếp tục sử dụng một MongoCursor đã hỏng**; tạo truy vấn mới với checkpoint rõ ràng.

### 12.2. Có nên tự catch rồi lặp lại toàn bộ query?

Nếu tất cả thao tác chỉ **đọc và in màn hình**, lặp lại kết quả có thể chấp nhận được. Nhưng nếu mỗi document kích hoạt tạo hóa đơn, gửi email hoặc cập nhật hệ thống khác, retry nguyên truy vấn có thể lặp side effect.

Hệ thống cần kết hợp checkpoint với thiết kế idempotency, chẳng hạn lưu mã sự kiện đã xử lý hoặc dùng phép ghi có khóa duy nhất. Một số trường hợp cần transaction, outbox hoặc cơ chế bảo đảm nhất quán xuyên dịch vụ; cursor tự nó không giải quyết được những yêu cầu đó.

## 13. Truy vấn đang chạy không đồng nghĩa với cursor luôn giữ snapshot cố định

Một cursor thông thường không tự tạo ra một bản sao bất biến của toàn bộ collection ở thời điểm mở truy vấn. Nếu có tiến trình khác đang insert, update hoặc delete document trong lúc bạn duyệt nhiều batch, tập dữ liệu được quan sát có thể chịu ảnh hưởng từ concurrency và các quy tắc read concern/transaction cụ thể.

Ví dụ:

~~~text
Job đọc theo seq 1 ... 1000
             |
             +--- Một service khác sửa seq, xóa record hoặc thêm record
             |
             +--- Job tiếp tục đọc hoặc mở trang mới
~~~

Nếu **seq là khóa ổn định**, các trang theo seq thường dễ tiếp tục hơn offset skip. Tuy nhiên, ngay cả keyset pagination cũng không tự bảo đảm đọc tất cả thay đổi trong một snapshot nếu document bị xóa, khóa bị cập nhật hoặc dữ liệu mới được chèn vào vị trí đã đi qua.

### 13.1. Xác định ranh giới tập dữ liệu cần xử lý

Đối với batch job quét tập dữ liệu đã tồn tại trước khi job bắt đầu, có thể ghi lại một **high-water mark**, ví dụ giá trị seq lớn nhất tại thời điểm bắt đầu:

~~~javascript
const newest = db.events
  .find({}, { seq: 1 })
  .sort({ seq: -1 })
  .limit(1)
  .toArray();

const maxSeqAtStart = newest.length > 0 ? newest[0].seq : 0;
~~~

Sau đó xử lý:

~~~javascript
db.events.find({
  seq: {
    $gt: lastSeq,
    $lte: maxSeqAtStart
  }
}).sort({ seq: 1 }).limit(100);
~~~

**maxSeqAtStart** hạn chế việc job chạy mãi khi các bản ghi mới có seq lớn hơn liên tục được ghi thêm. Đây là một ranh giới theo khóa được chọn, **không thay thế snapshot isolation**: document cũ vẫn có thể bị sửa/xóa trong khi job chạy.

### 13.2. Khi yêu cầu nhất quán mạnh

Nếu nghiệp vụ yêu cầu một tập kết quả nhất quán theo một thời điểm xác định, cần xem xét **read concern**, transaction có hỗ trợ snapshot, hoặc kiến trúc xuất dữ liệu/chụp ảnh dữ liệu phù hợp với deployment MongoDB. Những cách đó có chi phí và giới hạn vận hành riêng. Không nên mặc định chỉ việc gọi find().sort() đã tạo snapshot có thể giữ nhiều giờ.

Việc chọn mô hình đúng phụ thuộc: job có được phép bỏ qua document bị xóa không, có cần bắt mọi lần cập nhật không, có thể chấp nhận record mới xuất hiện trong lúc chạy không và cần mức đảm bảo nào khi hệ thống xảy ra failover.

## 14. Phân biệt cursor timeout với timeout của một thao tác truy vấn

Có nhiều loại timeout trong ứng dụng MongoDB. Chúng ảnh hưởng đến những giai đoạn khác nhau:

| Cơ chế | Điều gì bị giới hạn? | Có thay thế cơ chế đóng cursor không? |
|---|---|---|
| Cursor idle timeout | Thời gian cursor không được sử dụng theo chính sách server | Không |
| Logical session timeout | Thời gian session không hoạt động theo chính sách | Không |
| maxTimeMS / maxTime trong API tương ứng | Thời gian được phép thực thi thao tác server trong phạm vi áp dụng | Không |
| Socket/read timeout ở driver | Thời gian chờ giao tiếp mạng theo cấu hình client | Không |
| Thời hạn job do ứng dụng đặt | Thời gian cho phép toàn bộ tác vụ xử lý | Không |

Một query **chạy quá lâu** và một cursor **đang idle quá lâu** là hai tình huống khác nhau. Không nên tùy tiện tăng maxTimeMS rồi coi như đã giải quyết được cursor bị hết hạn do ngừng getMore.

### 14.1. maxTimeMS không có nghĩa “cursor sống trong N mili giây”

Ví dụ truy vấn:

~~~javascript
db.events
  .find({ category: "SYSTEM" })
  .maxTimeMS(10000);
~~~

Tùy loại thao tác, cấu hình và phiên bản, maxTimeMS giới hạn thời gian thực thi mà server cho phép. Nó **không phải số mili giây mà server sẽ giữ cursor đang idle sau khi gửi một batch**. Không sử dụng maxTimeMS thay thế cho close(), noCursorTimeout hoặc chiến lược checkpoint.

### 14.2. Batch lớn hay nhỏ ảnh hưởng đến nguy cơ idle

Giả sử mỗi document mất 30 giây để xử lý nghiệp vụ và ứng dụng chỉ yêu cầu batch mới sau khi xử lý xong batch trước:

| batchSize | Thời gian xử lý lý thuyết của một batch đầy |
|---|---|
| 5 | 2,5 phút |
| 20 | 10 phút |
| 100 | 50 phút |

Đây chỉ là ước lượng theo bài toán giả định; số document thực tế từng batch có thể khác cấu hình và thời gian xử lý thực tế biến động. Nhưng nó minh họa vấn đề: **batch quá lớn cộng với xử lý chậm có thể tạo quãng thời gian không gọi getMore đủ dài để gặp cursor/session timeout**.

Một cách giảm rủi ro là xử lý nhanh trong vòng duyệt, tách tác vụ nặng sang hàng đợi khác, giới hạn batch hợp lý, hoặc dùng phân trang có checkpoint khi cần xử lý lâu.

### 14.3. noCursorTimeout và việc làm mới session

**noCursorTimeout** có ích khi đã hiểu rõ yêu cầu giữ cursor, nhưng các session vẫn có chính sách hết hạn riêng. Với job đặc biệt dài, một số thiết kế sử dụng session tường minh và cơ chế **refreshSessions** định kỳ theo hướng dẫn phù hợp với phiên bản server và driver. Đây là một nhiệm vụ quản lý vòng đời bổ sung; tự thực hiện refresh không bảo vệ trước mọi nguyên nhân mất cursor.

Với phần lớn tác vụ nghiệp vụ cần phục hồi, kiến trúc **checkpoint + truy vấn mới** thường dễ kiểm soát hơn việc cố giữ một cursor duy nhất qua mọi lần gián đoạn.

## 15. Quan sát và giám sát cursor khi vận hành

Một hệ thống có nhiều cursor mở nhưng không được đóng có thể tích lũy tài nguyên, đặc biệt nếu ứng dụng thường xuyên dừng duyệt giữa chừng hoặc có luồng xử lý lỗi không đi qua finally.

### 15.1. Xem thông tin tổng quan từ serverStatus

Với tài khoản có quyền phù hợp, có thể dùng:

~~~javascript
db.serverStatus().metrics.cursor;
~~~

Các chỉ số có thể bao gồm thông tin về số cursor đang mở và số cursor đã hết hạn, ví dụ những trường theo cấu trúc như **open.total** và **timedOut**. Tên trường/nhóm thống kê có thể khác nhau giữa các phiên bản MongoDB, vì vậy cần kiểm tra output thực tế của server.

Chỉ số tổng hợp hữu ích để quan sát xu hướng:

- **Số cursor mở** tăng liên tục dù request hoàn tất có thể gợi ý rò rỉ hoặc workload mới.
- **Số cursor timeout** tăng nhanh có thể cho thấy ứng dụng ngừng đọc lâu hoặc bỏ quên cursor.
- **Thời gian job** và **số document xử lý mỗi giây** giúp xác định batch đang xử lý chậm.
- **Số lần retry từ checkpoint** giúp thấy hệ thống có thường xuyên mất cursor trong lúc làm việc không.

Một chỉ số server tự nó không chứng minh ứng dụng nào làm rò rỉ cursor. Cần đối chiếu log, tracing, đặc điểm workload và các phiên bản triển khai.

### 15.2. Log tiến độ batch job

Một log phù hợp có thể chứa:

~~~text
jobId=export-2026-11-14
checkpoint.seq=12500
processedCount=12500
batchSize=200
durationSeconds=180
retryCount=1
status=RUNNING
~~~

Tác dụng của log:

1. Biết job đang xử lý tới đâu.
2. Có thể xác định bước nào xảy ra lỗi.
3. So sánh tốc độ thực tế với thời gian sống của cursor.
4. Hỗ trợ khôi phục từ checkpoint phù hợp.

Không ghi trực tiếp mật khẩu kết nối, token hay toàn bộ document nhạy cảm vào log tiến độ.

### 15.3. Tránh tự kill cursor của workload khác

MongoDB có lệnh quản trị **killCursors** và những công cụ để quan sát hoạt động đang chạy. Các thao tác này có thể ảnh hưởng tới truy vấn của ứng dụng khác. Trong bài thực hành, hãy chủ động **close()** cursor do chính chương trình tạo; nếu cần điều tra sự cố production, xác định chính xác client, session và cursor trước khi thực hiện thao tác quản trị.

## 16. Cursor thông thường, tailable cursor và Change Streams

Khái niệm “đọc liên tục” có thể gây nhầm: đọc hết một tập kết quả bằng cursor thông thường khác với **theo dõi document mới** hoặc **theo dõi thay đổi database**.

| Cơ chế | Mục đích | Khi không còn dữ liệu hiện tại |
|---|---|---|
| Cursor thông thường | Duyệt kết quả của một truy vấn | Duyệt hết rồi kết thúc |
| Tailable cursor | Đọc tiếp document được nối vào capped collection | Có thể tiếp tục chờ document mới khi cursor còn hợp lệ |
| Change Streams | Theo dõi sự kiện thay đổi qua MongoDB change stream API | Có thể chờ sự kiện mới và dùng resume token khi điều kiện hỗ trợ |

### 16.1. Tại sao find() thông thường không phải lệnh “theo dõi mãi”?

~~~javascript
db.events.find({ category: "SYSTEM" });
~~~

Khi cursor thông thường đã hết kết quả, nó được hoàn tất. Nếu sau đó có document mới đáp ứng bộ lọc, cursor đã hoàn tất **không tự biến thành một luồng theo dõi vô hạn**.

Để theo dõi các thay đổi liên tục, hãy xem xét **Change Streams** khi deployment hỗ trợ, hoặc **tailable cursor** dành cho capped collection khi phù hợp. Những cơ chế này có thêm quy tắc về chờ dữ liệu, timeout, resume và bảo đảm tiêu thụ; chúng không thể tự thay thế cho nhau.

### 16.2. Tailable cursor có thể mất document cũ

Tailable cursor trên capped collection phụ thuộc vùng đệm còn giữ dữ liệu. Nếu producer ghi nhanh khiến các document cũ bị loại trước khi consumer đọc, consumer có thể bỏ lỡ dữ liệu. Do đó, không nên coi tailable cursor là hàng đợi bảo đảm giao mọi sự kiện.

### 16.3. Change Streams có resume token riêng

Change Streams có cơ chế **resume token** để giúp tiếp tục sau một số gián đoạn, nhưng khả năng tiếp tục còn phụ thuộc lịch sử thay đổi/oplog còn sẵn và điều kiện hỗ trợ. Không nên lấy checkpoint seq của cursor thông thường áp dụng trực tiếp cho Change Streams, hoặc mặc định mọi cursor đều có resume token tự động.

## 17. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| Java batch job giữ nhiều MongoCursor mở | Không đóng ở nhánh lỗi/dừng sớm | Dùng try-with-resources ở phạm vi mỗi cursor |
| mongosh dừng xử lý sau vài document, server vẫn giữ cursor | Không gọi close() khi break hoặc exception | Dùng try/finally và cursor.close() |
| CursorNotFound sau khi xử lý batch rất lâu | Cursor/session có thể hết hạn trong khoảng không có getMore | Giảm thời gian xử lý giữa các batch, chia trang, dùng checkpoint |
| Đã đặt noCursorTimeout nhưng vẫn mất cursor | Session hết hạn hoặc có nguyên nhân khác | Xem session, server, mạng và thiết kế phục hồi |
| Chạy lại query sau lỗi làm xử lý trùng | Không lưu checkpoint hoặc side effect không idempotent | Persist checkpoint đúng lúc, xử lý trùng có kiểm soát |
| Ghi checkpoint khi vừa tải trang rồi bị mất một số record | Chưa xử lý thành công các document cuối trang | Chỉ nâng checkpoint sau thành công nghiệp vụ |
| find().toArray() gây thiếu bộ nhớ | Gom tập dữ liệu lớn vào List/Array | Duyệt từng document hoặc trang có limit |
| Tăng batchSize để “đọc nhanh” nhưng lỗi idle nhiều hơn | Batch lớn mất nhiều thời gian xử lý trước getMore | Đo tốc độ xử lý và điều chỉnh batchSize |
| skip/limit bị trùng hoặc mất record trong lúc có ghi mới | Offset thay đổi khi dữ liệu được insert/delete | Keyset pagination trên khóa thứ tự ổn định |
| Sort theo createdAt nhưng bỏ sót record cùng thời điểm | Checkpoint thiếu khóa phụ | Dùng cặp (createdAt, _id) hoặc khóa duy nhất khác |
| Dùng _id ObjectId như đồng hồ tuyệt đối | ObjectId có thể được tạo từ nhiều client, thứ tự không tuyệt đối | Xác định khóa tiến độ theo thiết kế nghiệp vụ |
| Bật maxTimeMS để ngăn cursor idle timeout | Hai cơ chế giới hạn khác nhau | Phân biệt operation timeout với idle/session timeout |
| Query đọc hết nhưng tưởng cursor bị lỗi | Cursor hoàn tất bình thường sau kết quả cuối | Phân biệt hết dữ liệu với ngoại lệ getMore |
| MongoClient bị tạo/đóng sau mỗi document | Nhầm vòng đời client và cursor | Tái sử dụng MongoClient, đóng MongoCursor từng query |

## 18. Bài tập thực hành

Thực hiện các bài tập trên database **cursor_lab** đã tạo ở phần 3. Những bài có cập nhật dữ liệu nên làm trên dữ liệu thử nghiệm, tránh ảnh hưởng đến hệ thống thật.

### Bài 1. Đọc tuần tự và đóng cursor

Yêu cầu: in ra seq và message của tất cả document theo thứ tự seq tăng dần, batchSize bằng 4, bảo đảm cursor được đóng khi kết thúc.

**Đáp án tham khảo:**

~~~javascript
const cursor = db.events.find(
  {},
  { seq: 1, message: 1 }
).sort({ seq: 1 }).batchSize(4);

try {
  while (cursor.hasNext()) {
    const doc = cursor.next();
    print(doc.seq + ": " + doc.message);
  }
} finally {
  cursor.close();
}
~~~

Với dữ liệu mẫu chưa thay đổi, bạn sẽ đọc **24 document**, từ seq 1 đến seq 24. Việc dùng batchSize(4) không giới hạn tổng số document ở 4.

### Bài 2. Dừng sớm

Yêu cầu: chỉ đọc ba document đầu nhưng vẫn đóng cursor.

**Đáp án tham khảo:**

~~~javascript
const cursor = db.events.find().sort({ seq: 1 });

try {
  for (let i = 0; i < 3 && cursor.hasNext(); i++) {
    printjson(cursor.next());
  }
} finally {
  cursor.close();
}
~~~

Giải thích vì sao thao tác close() vẫn có ý nghĩa khi truy vấn có thể còn 21 document chưa đọc.

### Bài 3. So sánh batchSize và limit

Dự đoán số document tối đa mà mỗi truy vấn có thể trả:

~~~javascript
db.events.find().batchSize(3)
db.events.find().limit(3)
db.events.find().batchSize(3).limit(8)
~~~

**Định hướng:** Truy vấn thứ nhất vẫn có thể duyệt toàn bộ 24 document; truy vấn thứ hai chỉ lấy tối đa 3; truy vấn thứ ba lấy tối đa 8, có thể phân thành nhiều batch khi cần.

### Bài 4. Xử lý sự cố sau checkpoint

Giả sử job đã xử lý thành công và lưu checkpoint **lastSeq = 12** rồi xảy ra lỗi CursorNotFound. Viết câu truy vấn tiếp tục từ record kế tiếp:

~~~javascript
const lastSeq = 12;

db.events
  .find({ seq: { $gt: lastSeq } })
  .sort({ seq: 1 })
  .limit(5);
~~~

Kết quả trang tiếp theo là **seq 13–17** nếu dữ liệu mẫu còn nguyên. Vì sao phải dùng $gt thay vì $gte trong điều kiện tiếp tục? Vì seq 12 đã được xác nhận xử lý xong.

### Bài 5. Checkpoint sai thời điểm

Một job đã xử lý thành công seq 1–7, đang xử lý seq 8 thì gặp lỗi, nhưng checkpoint đã được ghi bằng 10 ngay khi tải trang.

Hãy giải thích:

1. Điều gì xảy ra nếu lần sau truy vấn seq > 10?
2. Checkpoint nên lưu ở mốc nào?
3. Nếu tác vụ xử lý seq 7 xong nhưng chết trước khi ghi checkpoint 7, cần cơ chế gì để chịu được xử lý lại?

**Gợi ý:** seq 8–10 có thể bị bỏ qua; checkpoint an toàn sau thành công mới là 7; cần cơ chế idempotent hoặc ghi trạng thái nghiệp vụ và checkpoint nhất quán.

### Bài 6. Phân trang với trường không duy nhất

Giả sử nhiều event có cùng **createdAt**. Một job chỉ lưu lastCreatedAt và truy vấn createdAt > lastCreatedAt. Vì sao job có nguy cơ bỏ sót document? Hãy viết điều kiện dùng cả createdAt và _id làm cặp thứ tự, kèm sort({createdAt:1,_id:1}).

**Định hướng:** một số document có createdAt bằng mốc cuối nhưng _id lớn hơn có thể chưa được xử lý. Cần điều kiện **createdAt lớn hơn mốc hoặc createdAt bằng mốc và _id lớn hơn lastId**.

### Bài 7. Phân tích thời gian idle

Giả sử mỗi document cần xử lý 20 giây ở phía ứng dụng. So sánh việc đọc batch 5, 20 và 100 document trước khi yêu cầu batch kế tiếp.

Hãy tính thời gian xử lý lý thuyết của từng batch, xác định tình huống có nguy cơ vượt khoảng idle thường gặp và đề xuất thay đổi kiến trúc. 

**Gợi ý:** thời gian lần lượt khoảng **100 giây**, **400 giây**, **2.000 giây**. Cần xem timeout của cursor và session; một trang đọc ngắn, checkpoint và tác vụ xử lý riêng có thể giúp tránh phụ thuộc vào cursor sống lâu.

### Bài 8. Dự đoán hành vi khi hết cursor

Với một ứng dụng Java đã gọi cursor.close(), code vẫn gọi cursor.next(). Điều đó có nghĩa nên bật noCursorTimeout để tiếp tục được không?

**Định hướng:** không. Cursor bị đóng **chủ động** có vòng đời đã kết thúc; noCursorTimeout chỉ liên quan cơ chế timeout của server, không làm đối tượng đã close có thể được đọc tiếp. Cần sửa phạm vi sử dụng cursor hoặc tạo truy vấn mới theo yêu cầu.

## 19. Nguyên tắc triển khai trong ứng dụng thực tế

Khi thiết kế một công việc đọc MongoDB, nên trả lời các câu hỏi:

1. **Có cần lấy tất cả document cùng lúc không?** Nếu không, duyệt từng document bằng cursor, hoặc chia thành những trang có giới hạn.
2. **Có cần sort ổn định không?** Nếu cần resume hoặc phân trang, chọn khóa sắp xếp nhất quán và cân nhắc tính duy nhất, cùng index phù hợp.
3. **Mỗi document xử lý bao lâu?** Nếu xử lý có thể lâu, tránh giữ cursor idle quá dài; cân nhắc checkpoint.
4. **Ai đóng cursor?** Trong mongosh, dùng try/finally; trong Java Sync Driver, dùng try-with-resources.
5. **Nếu server đóng cursor, chương trình làm gì?** Phân loại lỗi, đóng tài nguyên, tạo truy vấn mới từ checkpoint khi điều kiện cho phép.
6. **Nếu một document bị xử lý lại, có gây hậu quả không?** Thiết kế xử lý idempotent hoặc cơ chế nhất quán phù hợp.
7. **Có yêu cầu snapshot hoặc dữ liệu thay đổi liên tục không?** Xác định read concern/transaction hoặc kiến trúc đồng bộ thích hợp thay vì giả định cursor thường tự đáp ứng.

Cursor giúp MongoDB truyền và xử lý tập kết quả lớn một cách tuần tự. Để dùng an toàn, cần **duyệt theo batch hợp lý**, **đóng tài nguyên kể cả khi gặp lỗi** và **không phụ thuộc vào việc một cursor sẽ sống mãi**. Khi tác vụ cần chạy lâu hoặc có thể gián đoạn, một thứ tự dữ liệu ổn định cùng checkpoint bền vững là nền tảng để tiếp tục công việc mà không âm thầm bỏ sót hoặc xử lý trùng bản ghi.

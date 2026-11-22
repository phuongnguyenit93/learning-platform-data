# Xử lý va chạm, kiểm tra duy nhất và rủi ro kiểm tra rồi mới ghi

## 1. Vì sao khóa và định danh cần được bảo vệ ở thời điểm ghi?

Trong cơ sở dữ liệu NoSQL, **khóa** giúp xác định và truy cập bản ghi; **định danh** giúp hệ thống và nghiệp vụ biết hai dữ liệu có đại diện cho cùng một đối tượng hay không. Một lỗi nhỏ khi sinh khóa, chuẩn hóa định danh hoặc ghi dữ liệu đồng thời có thể gây hậu quả lớn: tạo hai tài khoản dùng cùng tên đăng nhập, ghi đè dữ liệu người khác, xử lý trùng đơn hàng hoặc phân bổ hai lần một tài nguyên chỉ còn một suất.

Xét một ứng dụng bán vé. Chỉ còn một ghế trống. Hai khách cùng nhìn thấy trạng thái “còn ghế”, rồi cùng gửi yêu cầu đặt chỗ. Nếu chương trình thực hiện theo cách “kiểm tra còn ghế → tạo đặt chỗ”, cả hai yêu cầu có thể đều vượt qua bước kiểm tra trước khi một trong hai được ghi. Kết quả có thể là **bán trùng ghế**.

Vấn đề này không chỉ xảy ra ở dữ liệu NoSQL. Tuy nhiên, các hệ NoSQL có sự khác biệt lớn về khóa chính, điều kiện ghi, giao dịch, chỉ mục duy nhất và mức nhất quán, nên **phải thiết kế đúng cơ chế bảo đảm ở tầng lưu trữ được chọn**.

Bài học tập trung vào ba năng lực:

1. **Nhận diện và xử lý va chạm:** Phân biệt va chạm khóa, trùng định danh nghiệp vụ và va chạm hàm băm.
2. **Kiểm tra tính duy nhất đúng cách:** Xác định phạm vi duy nhất và áp dụng ràng buộc hoặc thao tác ghi nguyên tử.
3. **Tránh rủi ro “kiểm tra rồi mới ghi”:** Hiểu lỗi đua tranh do nhiều yêu cầu chạy đồng thời và dùng thao tác điều kiện, giao dịch hoặc cơ chế phối hợp thích hợp.

Một nguyên tắc xuyên suốt: **kết quả của một lần đọc trước đó không thể tự trở thành bảo đảm cho lần ghi sau đó** nếu có các tác nhân khác cũng được quyền ghi.

## 2. Phân biệt các loại khóa và tính duy nhất

### 2.1. Khóa vật lý, định danh nghiệp vụ và khóa truy cập

Các khái niệm thường gặp:

| Khái niệm | Ý nghĩa | Ví dụ | Rủi ro cần quản lý |
|---|---|---|---|
| Khóa chính / document ID | Định danh bản ghi trong một phạm vi lưu trữ | orderId, document _id | Ghi trùng hoặc ghi đè khi dùng cùng khóa |
| Định danh nghiệp vụ | Giá trị thể hiện sự duy nhất theo quy tắc của tổ chức | Email đăng nhập, mã số thuế, mã giao dịch ngoài | Hai bản ghi khác khóa chính nhưng cùng một định danh nghiệp vụ |
| Khóa phân vùng (partition key) | Quyết định cách dữ liệu được phân phối hoặc truy cập | tenantId, accountId | Tải lệch trên một phân vùng; không tự bảo đảm mọi điều kiện duy nhất |
| Khóa tổng hợp (composite key) | Nhiều thành phần cùng định danh một bản ghi | tenantId + username | Có thể trùng username ở tenant khác nếu phạm vi cho phép |
| Khóa idempotency | Nhận diện cùng một **ý định thao tác** khi yêu cầu bị gửi lại | requestId hoặc idempotencyKey | Tạo lại đơn, thanh toán hai lần do retry |
| Giá trị băm (hash) | Dấu vân tay được tính từ dữ liệu đầu vào | hash(content), hash(email) | Hai đầu vào khác nhau có thể cho cùng kết quả băm |

**Khóa chính duy nhất không đồng nghĩa mọi trường khác cũng duy nhất.** Hai tài liệu có thể có document ID khác nhau nhưng cùng normalizedUsername. Ngược lại, một giá trị username có thể được phép xuất hiện ở nhiều tenant nếu điều kiện duy nhất là tổ hợp (tenantId, normalizedUsername).

### 2.2. Phạm vi duy nhất phải được phát biểu rõ

Trước khi thiết kế, luôn trả lời:

- Một giá trị phải duy nhất **toàn hệ thống**, **trong một tenant**, **trong một nhóm**, hay **theo một khoảng thời gian**?
- Có phân biệt chữ hoa, chữ thường, khoảng trắng hoặc các dạng Unicode tương đương không?
- Giá trị trống hoặc thiếu trường có được phép xuất hiện nhiều lần không?
- Quy tắc chỉ áp dụng với bản ghi **đang hoạt động** hay cả bản ghi đã xóa mềm?
- Nếu đổi tên, định danh cũ có được cấp lại ngay hay phải giữ trong một khoảng thời gian?
- Dữ liệu được ghi ở **một vùng** hay ở nhiều vùng hoạt động đồng thời?

Ví dụ quy tắc chính xác hơn “Username không được trùng” là:

> Trong cùng một tenant, hai tài khoản đang hoạt động không được có cùng normalizedUsername. Username được so sánh theo chính sách chuẩn hóa đã thống nhất, và thao tác tạo hoặc đổi username phải được kiểm tra tại thời điểm ghi.

Quy tắc này có thể được biểu diễn như khóa duy nhất **(tenantId, normalizedUsername)** trên tập bản ghi đủ điều kiện. Nếu nghiệp vụ cần giữ tên của tài khoản đã xóa một thời gian, phải bổ sung trạng thái giữ chỗ hoặc quy tắc riêng.

### 2.3. Chuẩn hóa định danh là một phần của tính duy nhất

Giả sử người dùng nhập:

~~~text
" Alice "
"alice"
"ALICE"
~~~

Nếu quy tắc nghiệp vụ coi ba giá trị là cùng một username, hệ thống nên lưu:

~~~json
{
  "displayUsername": "Alice",
  "normalizedUsername": "alice"
}
~~~

**displayUsername** dùng cho giao diện; **normalizedUsername** dùng cho so sánh duy nhất. Có thể cần chuẩn hóa Unicode, loại khoảng trắng thừa hoặc xử lý phân biệt hoa–thường theo quy tắc sản phẩm.

Không nên áp dụng các quy tắc chuẩn hóa tùy tiện cho mọi loại định danh. Chẳng hạn, ý nghĩa chữ hoa–thường ở phần local của email và cách xử lý dấu chấm/dấu cộng phụ thuộc quy tắc địa chỉ và nhà cung cấp. Việc gộp email theo mẹo riêng của một dịch vụ có thể khiến hai địa chỉ hợp lệ bị coi nhầm là một. Chính sách chuẩn hóa phải được thiết kế và thống nhất với nghiệp vụ.

## 3. Va chạm là gì? Ba tình huống khác nhau

Từ “va chạm” thường được dùng cho nhiều vấn đề. Nếu không phân biệt, dễ chọn nhầm cách xử lý.

### 3.1. Trùng khóa do bộ sinh ID hoặc nhập dữ liệu

Hai thao tác cố tạo hai thực thể khác nhau với cùng một ID:

~~~text
Request A: tạo orderId = ORD-1008 cho khách X
Request B: tạo orderId = ORD-1008 cho khách Y
~~~

Nếu cơ sở dữ liệu có thao tác **chèn khi khóa chưa tồn tại**, một yêu cầu sẽ thành công và yêu cầu còn lại bị từ chối. Nếu ứng dụng dùng thao tác **upsert hoặc ghi đè vô điều kiện**, yêu cầu đến sau có thể thay thế nội dung của yêu cầu trước, tùy cách hệ quản trị xử lý thao tác.

Vì vậy, với ý nghĩa “tạo mới”, cần phân biệt rõ:

- **Insert/create có kiểm tra tồn tại:** Chỉ cho phép bản ghi mới.
- **Upsert:** Nếu chưa có thì tạo, nếu đã có thì cập nhật; không phù hợp cho mọi thao tác “tạo mới”.
- **Update có điều kiện:** Chỉ cập nhật nếu bản ghi và trạng thái/phiên bản thỏa điều kiện.
- **Replace vô điều kiện:** Có thể ghi đè dữ liệu nếu khóa đã tồn tại.

Không nên xử lý trùng khóa bằng cách **tự động sửa hoặc thêm hậu tố vào khóa nghiệp vụ** mà không có quy tắc sản phẩm, vì làm vậy có thể đổi ý nghĩa định danh hoặc phá liên kết từ hệ thống khác.

### 3.2. Va chạm của hàm băm

Hàm băm biến dữ liệu đầu vào thành giá trị trong một không gian hữu hạn:

~~~text
hash("input-A") -> 8432
hash("input-B") -> 8432
~~~

Hai đầu vào khác nhau nhưng cùng kết quả là **hash collision**. Đó là tính chất toán học không thể loại bỏ tuyệt đối nếu số đầu vào khả dĩ lớn hơn số giá trị băm.

Phân biệt:

1. **Va chạm bucket trong cấu trúc hash table:** Nhiều khóa có thể rơi vào cùng một bucket. Cấu trúc dữ liệu xử lý bằng so sánh khóa thật và phương pháp phân giải va chạm, như chaining hoặc probing.
2. **Va chạm khi dùng hash làm định danh:** Nếu chỉ lưu hash rút gọn rồi coi nó là định danh tuyệt đối, hai đối tượng khác nhau có thể bị gộp nhầm.
3. **Trùng dữ liệu có chủ đích:** Hai bản ghi có cùng nội dung sinh ra cùng một hash; đây không phải va chạm giữa hai nội dung khác nhau. Với lưu trữ theo nội dung, đây có thể là tín hiệu khử trùng lặp, nhưng vẫn cần chính sách xác minh.

Ví dụ một dịch vụ lưu ảnh dùng 32 bit băm làm ID duy nhất. Hai ảnh khác nhau có thể chung ID và ảnh sau ghi đè ảnh trước. Cách giảm rủi ro là dùng không gian băm đủ lớn, **so sánh dữ liệu hoặc dấu vân tay tin cậy khi cần chứng minh trùng nội dung**, và xử lý trường hợp khóa đã tồn tại thay vì mặc định “hash giống nhau = cùng vật”.

Hash có phân phối tốt giúp giảm tải lệch do va chạm bucket nhưng **không phải ràng buộc duy nhất** ở cấp nghiệp vụ. Ngược lại, mật mã băm cũng không tự giải quyết việc hai yêu cầu cùng chọn một username có chủ đích.

### 3.3. Trùng định danh nghiệp vụ dù ID kỹ thuật khác nhau

~~~json
{"_id":"user-17","tenantId":"T1","normalizedUsername":"alice"}
{"_id":"user-93","tenantId":"T1","normalizedUsername":"alice"}
~~~

Hai tài liệu có khóa chính khác nhau, nên có thể hợp lệ với ràng buộc trên _id. Nhưng chúng **vi phạm quy tắc username duy nhất trong tenant T1**. Cơ chế sinh UUID cho _id không giúp ngăn lỗi này.

Cần định nghĩa ràng buộc trên đúng **khóa nghiệp vụ** hoặc thực hiện thao tác ghi nguyên tử mà **mọi yêu cầu cùng cạnh tranh một địa chỉ khóa**.

## 4. Xác suất va chạm khi sinh ID ngẫu nhiên

Không gian định danh càng lớn và phân phối càng đồng đều, xác suất hai lần sinh ngẫu nhiên độc lập gặp cùng ID càng nhỏ. Tuy nhiên, “xác suất rất nhỏ” khác với “không thể xảy ra”.

Nếu có **M** giá trị ID khả dĩ và sinh độc lập **n** lần với phân phối đều, xác suất có ít nhất một cặp trùng được xấp xỉ bằng công thức bài toán ngày sinh:

\[
P(\text{collision}) \approx 1 - \exp\left(-\frac{n(n-1)}{2M}\right).
\]

Khi \(\frac{n(n-1)}{2M}\) rất nhỏ, có thể xấp xỉ tiếp:

\[
P(\text{collision}) \approx \frac{n(n-1)}{2M}.
\]

Với UUID phiên bản 4 được sinh ngẫu nhiên đúng chuẩn, có **122 bit ngẫu nhiên**, tức khoảng \(2^{122}\) giá trị khả dĩ. Đây là không gian rất lớn cho nhiều ứng dụng. Dù vậy, hệ thống vẫn cần bảo vệ tại thời điểm chèn để xử lý trường hợp trùng do lỗi bộ sinh, nhập dữ liệu, cấu hình hoặc sự kiện hiếm.

Không phải mọi loại ID đều dùng cơ chế ngẫu nhiên hoàn toàn:

| Cách sinh ID | Ưu điểm | Rủi ro hoặc điều cần lưu ý |
|---|---|---|
| UUIDv4 ngẫu nhiên | Không cần bộ cấp phát tập trung | Phụ thuộc nguồn ngẫu nhiên; có xác suất trùng cực nhỏ |
| UUID có phần thời gian (ví dụ UUIDv7) | Hỗ trợ sắp xếp gần theo thời gian trong nhiều trường hợp | Không mặc định bảo đảm thứ tự tuyệt đối hoặc tính duy nhất nếu bộ sinh lỗi |
| Số thứ tự tập trung | Dễ hiểu, kiểm soát cấp phát tại một nơi | Phụ thuộc bộ cấp phát; có thể là điểm nghẽn |
| ID có thời gian + mã node + sequence | Có thể cấp phát phân tán, tương đối có thứ tự | Mã node trùng, đồng hồ lùi hoặc sequence tràn có thể làm phát sinh lỗi |
| Khóa nghiệp vụ tự nhiên | Dễ tra cứu từ nghiệp vụ | Giá trị có thể thay đổi, bị tái sử dụng hoặc có nhiều quy tắc so sánh |
| Hash nội dung | Hữu ích cho xác định nội dung tương đồng hoặc khử trùng lặp | Không phải bằng chứng tuyệt đối về cùng nội dung; cần xử lý collision |

Một thiết kế thực tế thường kết hợp **bộ sinh ID có xác suất va chạm thấp** với **lệnh tạo mới từ chối khóa trùng**. Bộ sinh giảm khả năng gặp lỗi; ràng buộc tại kho dữ liệu bảo vệ khi lỗi xảy ra.

## 5. Kiểm tra duy nhất bằng cách nào?

Có nhiều cơ chế, nhưng mức bảo đảm phụ thuộc trực tiếp vào **phạm vi ràng buộc** và **mô hình nhất quán** của hệ quản trị NoSQL.

### 5.1. Ràng buộc hoặc chỉ mục duy nhất (unique index/constraint)

Một số hệ quản trị cho phép khai báo khóa duy nhất trên một hoặc nhiều trường. Khi thao tác ghi làm vi phạm, cơ sở dữ liệu từ chối thao tác thay vì để ứng dụng tự phát hiện sau.

Ví dụ dạng tư duy:

~~~text
UNIQUE (tenantId, normalizedUsername)
~~~

Điều này diễn đạt: với cùng tenantId, hai bản ghi không thể có cùng normalizedUsername trong phạm vi mà ràng buộc áp dụng.

Với **MongoDB**, một ví dụ tạo unique compound index:

~~~javascript
db.users.createIndex(
  { tenantId: 1, normalizedUsername: 1 },
  { unique: true, name: "uq_tenant_username" }
);
~~~

Khi hai tác nhân đồng thời chèn cùng cặp giá trị, **chỉ mục duy nhất** sẽ bảo vệ quy tắc trong phạm vi được hệ thống hỗ trợ. Một thao tác chèn có thể nhận lỗi duplicate key, thường có mã lỗi 11000; ứng dụng cần bắt lỗi đó và phản hồi có ý nghĩa.

Ví dụ:

~~~javascript
try {
  await db.collection("users").insertOne({
    _id: "user-100",
    tenantId: "T1",
    normalizedUsername: "alice",
    displayUsername: "Alice"
  });
} catch (err) {
  if (err.code === 11000) {
    // Phản hồi: tên đăng nhập đã được sử dụng trong tenant này.
  } else {
    throw err;
  }
}
~~~

Trong ứng dụng thực, giá trị _id phải là ID mới hợp lệ cho từng yêu cầu; nếu xảy ra duplicate key, cần xác định **trường hoặc chỉ mục nào trùng** trước khi trả thông báo, bởi lỗi cũng có thể đến từ khóa khác như _id.

**Các điểm cần làm rõ với unique index:**

- Chỉ mục unique có thể **không tạo được** khi dữ liệu hiện tại đã có bản ghi vi phạm; cần xử lý dữ liệu cũ trước.
- Với giá trị null hoặc thiếu thuộc tính, cách cơ sở dữ liệu và loại chỉ mục xử lý có thể khác mong đợi; cần định nghĩa chính sách trường tùy chọn.
- Quy tắc so sánh chuỗi có thể phụ thuộc collation và cách chuẩn hóa; unique index không tự biết “ALICE” tương đương “alice” theo nghiệp vụ.
- Đối với dữ liệu phân mảnh (sharded), khả năng áp dụng ràng buộc unique trên các trường không chứa khóa phân mảnh có giới hạn tùy hệ thống và cấu hình. Không mặc định một unique index trên một shard tương đương duy nhất toàn cụm.
- Nếu nghiệp vụ chỉ yêu cầu duy nhất ở một phần bản ghi (ví dụ user đang hoạt động), cân nhắc **partial unique index** khi hệ quản trị hỗ trợ; phải xác định chính xác điều kiện bao phủ.

Ví dụ minh họa **một lựa chọn riêng** với MongoDB, khi chỉ những username dạng chuỗi mới phải duy nhất:

~~~javascript
db.users.createIndex(
  { tenantId: 1, normalizedUsername: 1 },
  {
    unique: true,
    partialFilterExpression: {
      normalizedUsername: { $type: "string" }
    }
  }
);
~~~

Ví dụ partial index không phải sự thay thế tự động cho unique index thông thường. Nó áp dụng ràng buộc **chỉ với tài liệu thỏa điều kiện lọc**, nên phải đối chiếu với yêu cầu nghiệp vụ trước khi dùng.

### 5.2. Ghi có điều kiện (conditional write / compare-and-set)

Một số kho NoSQL kiểm soát tính duy nhất bằng thao tác “**chỉ tạo bản ghi nếu khóa chưa tồn tại**”, trong đó kiểm tra điều kiện và ghi là **một thao tác nguyên tử tại phạm vi được hỗ trợ**.

Ví dụ tư duy:

~~~text
CREATE key = "username#T1#alice"
ONLY IF key DOES NOT EXIST
~~~

Nếu hai yêu cầu cùng cố ghi đúng khóa, một yêu cầu có thể thắng, yêu cầu khác nhận lỗi điều kiện không thỏa. Bảo đảm này khác hẳn với việc ứng dụng gọi GET rồi tự quyết định PUT.

Với **Amazon DynamoDB**, ví dụ đơn giản dùng PutItem và điều kiện trên khóa phân vùng:

~~~javascript
// Ví dụ với AWS SDK for JavaScript v3
import { DynamoDBClient, PutItemCommand } from "@aws-sdk/client-dynamodb";

const client = new DynamoDBClient({});

await client.send(new PutItemCommand({
  TableName: "UniqueUsernameReservations",
  Item: {
    pk: { S: "USERNAME#T1#alice" },
    userId: { S: "user-100" }
  },
  ConditionExpression: "attribute_not_exists(pk)"
}));
~~~

Ở đây, **pk** là khóa chính duy nhất của bảng minh họa. Điều kiện kiểm tra rằng **mục ở chính địa chỉ khóa được ghi** chưa tồn tại. Nếu điều kiện sai, DynamoDB trả lỗi kiểm tra điều kiện; ứng dụng cần xử lý như một trường hợp tranh chấp hợp lệ.

Nếu bảng dùng **khóa phân vùng và khóa sắp xếp**, tính duy nhất mặc định là theo **toàn bộ khóa chính**, không phải mọi giá trị partition key. Quy tắc username duy nhất phải được mô hình hóa sao cho mọi yêu cầu cùng username cạnh tranh cùng **một mục dành riêng**, hoặc thông qua cơ chế giao dịch phù hợp.

Với **Apache Cassandra**, phép chèn có điều kiện có thể viết:

~~~sql
INSERT INTO usernames_by_key (username_key, user_id)
VALUES ('T1#alice', 100)
IF NOT EXISTS;
~~~

Cú pháp này sử dụng cơ chế **lightweight transaction (LWT)** cho điều kiện ghi tại khóa được thiết kế, theo khả năng và yêu cầu consistency của Cassandra. Nó có chi phí cao hơn ghi thông thường, nên cần cân nhắc trên đường ghi nhiều tải. Không nên suy ra rằng một câu IF NOT EXISTS tự bảo đảm tính duy nhất trên một **trường không phải khóa** ở mọi phân vùng.

### 5.3. Giao dịch khi quy tắc liên quan nhiều mục

Giả sử ứng dụng lưu:

- **Một mục đặt chỗ username:** Khóa USERNAME#T1#alice.
- **Một hồ sơ người dùng:** Khóa USER#user-100.

Nếu đặt chỗ username thành công nhưng tạo hồ sơ thất bại, một username có thể bị giữ mà không có tài khoản hợp lệ. Nếu tạo hồ sơ trước rồi đặt chỗ thất bại, có thể xuất hiện hồ sơ chưa có định danh nghiệp vụ hợp lệ.

Khi nghiệp vụ yêu cầu **cả hai thành công hoặc cùng không được áp dụng**, dùng **giao dịch nhiều mục** nếu hệ quản trị hỗ trợ, với điều kiện “username chưa được đặt” trong chính giao dịch.

Ví dụ dạng giả mã:

~~~text
transaction:
  put usernameReservation(
    key = "USERNAME#T1#alice",
    owner = "user-100"
  )
    IF_NOT_EXISTS

  put userProfile(
    key = "USER#user-100",
    username = "alice"
  )
    IF_NOT_EXISTS

commit atomically
~~~

Giao dịch giúp duy trì bất biến qua hai bản ghi khi cơ sở dữ liệu bảo đảm atomicity tương ứng. Phải kiểm tra giới hạn giao dịch, số mục, tính nhất quán liên vùng, thông lượng và lỗi trả về của sản phẩm đang dùng.

Nếu kho dữ liệu không hỗ trợ giao dịch phù hợp, có thể cần thay đổi mô hình lưu để bất biến tập trung ở **một khóa**, hoặc dùng quy trình dự phòng/đối soát có trạng thái. Không thể tự biến hai thao tác ghi độc lập thành atomic chỉ bằng cách đặt chúng liên tiếp trong một hàm.

## 6. Rủi ro “kiểm tra rồi mới ghi” (check-then-write / TOCTOU)

### 6.1. Lỗi đến từ khoảng trống giữa hai bước

**Time-of-check to time-of-use (TOCTOU)** là loại lỗi khi điều kiện đúng tại thời điểm kiểm tra nhưng có thể không còn đúng lúc hành động được thực hiện.

Giả sử username "alice" chưa có:

| Thời điểm | Yêu cầu A | Yêu cầu B |
|---|---|---|
| t1 | Đọc: username “alice” chưa tồn tại | |
| t2 | | Đọc: username “alice” chưa tồn tại |
| t3 | Tạo user-100 / username “alice” | |
| t4 | | Tạo user-200 / username “alice” |
| Kết quả | Cả hai từng thấy “chưa tồn tại” | Có nguy cơ hai user cùng tên |

Mẫu code có vấn đề:

~~~javascript
async function registerUser(username) {
  const normalized = normalizeUsername(username);

  const existing = await users.findOne({
    normalizedUsername: normalized
  });

  if (existing) {
    throw new Error("Username already exists");
  }

  // Giữa findOne và insertOne, yêu cầu khác có thể đã chèn username.
  return users.insertOne({
    userId: makeUserId(),
    normalizedUsername: normalized
  });
}
~~~

Kể cả nếu bước đọc dùng strong consistency, hai yêu cầu vẫn có thể cùng đọc **trước khi bất kỳ yêu cầu nào ghi**. Strong read giúp đọc dữ liệu mới hơn hoặc nhất quán theo bảo đảm sản phẩm; **nó không khóa tương lai** và không tự ngăn một tác nhân khác ghi sau lần đọc.

### 6.2. Minh họa tuần tự theo hai luồng

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Yêu cầu A
    participant DB as CSDL
    participant B as Yêu cầu B
    A->>DB: Tìm username "alice"
    DB-->>A: Chưa tồn tại
    B->>DB: Tìm username "alice"
    DB-->>B: Chưa tồn tại
    A->>DB: Chèn user A, username "alice"
    DB-->>A: Thành công
    B->>DB: Chèn user B, username "alice"
    DB-->>B: Thành công nếu không có bảo vệ duy nhất
~~~

Biểu đồ mô tả lỗi trong trường hợp hai thao tác chèn không bị ràng buộc thích hợp. Nếu có unique index hoặc điều kiện ghi nguyên tử đúng khóa, một thao tác sẽ bị từ chối và bất biến được giữ.

### 6.3. Vì sao kiểm tra ở tầng ứng dụng là chưa đủ?

Các cách sau **không tạo bảo đảm duy nhất** khi có nhiều tiến trình:

- Ẩn nút đăng ký sau khi người dùng bấm.
- Disable form trên trình duyệt.
- Kiểm tra trước bằng API validate username.
- Đọc nhiều lần để chắc chắn username “vẫn trống”.
- Dùng mutex trong bộ nhớ của **một instance** khi hệ thống có nhiều instance hoặc worker.
- Dùng cache xác nhận “chưa tồn tại”.
- Thêm một khoảng thời gian chờ rồi mới ghi.

Những biện pháp đó có thể hữu ích cho trải nghiệm người dùng hoặc giảm số yêu cầu, nhưng **tính đúng đắn phải dựa trên nơi kiểm soát cạnh tranh ở phạm vi của toàn bộ thao tác liên quan**.

### 6.4. Mẫu sửa đúng: cố ghi rồi xử lý xung đột

Nếu đã có unique index trên cặp (tenantId, normalizedUsername):

~~~javascript
async function registerUser(db, tenantId, username) {
  const normalizedUsername = normalizeUsername(username);

  try {
    const result = await db.collection("users").insertOne({
      tenantId,
      normalizedUsername,
      displayUsername: username,
      createdAt: new Date()
    });

    return { userId: result.insertedId, created: true };
  } catch (error) {
    if (error.code === 11000) {
      // Với nhiều unique index, kiểm tra nguyên nhân trùng trước khi
      // ánh xạ thành thông báo username đã tồn tại.
      throw new UsernameAlreadyTakenError();
    }
    throw error;
  }
}
~~~

Trong ví dụ này, tính duy nhất của username được bảo vệ bởi **chỉ mục tại CSDL**. Việc có thể hiển thị “Username khả dụng” trước khi submit chỉ là **dự báo**, không phải lời hứa chắc chắn cho lần chèn sau.

Đối với kho không hỗ trợ unique index phù hợp, hãy đưa cùng định danh vào cùng **khóa ghi có điều kiện** hoặc dùng cơ chế giao dịch tương ứng.

## 7. Các vấn đề đồng thời liên quan nhưng khác lỗi tạo trùng

### 7.1. Lost update: hai yêu cầu cùng sửa một bản ghi

Tồn kho hiện tại là 5. Hai tác nhân cùng đọc số lượng 5:

~~~text
A đọc 5, bán 1 -> định ghi 4
B đọc 5, bán 1 -> định ghi 4
Sau hai lần ghi, số lượng là 4 thay vì 3.
~~~

Đây là **lost update**, không phải trường hợp hai ID trùng. Với các kho có hỗ trợ, hãy dùng lệnh giảm nguyên tử hoặc điều kiện trên phiên bản/số lượng.

Ví dụ tư duy:

~~~text
UPDATE stock
SET available = available - 1
ONLY IF available >= 1
~~~

Kiểm tra và cập nhật phải xảy ra trong **cùng một thao tác bảo đảm nguyên tử** ở đúng phạm vi. Cú pháp khác nhau theo sản phẩm. Nếu đơn hàng và kho nằm ở nhiều bản ghi/hệ thống, phải giải quyết thêm việc hai cập nhật cùng thành công hoặc được phục hồi theo quy tắc nghiệp vụ.

### 7.2. Optimistic concurrency: so sánh phiên bản

Mỗi bản ghi có một trường **version**:

~~~json
{
  "orderId": "ORD-1008",
  "status": "PENDING",
  "version": 7
}
~~~

Yêu cầu cập nhật gửi kèm version đã đọc. Chỉ ghi nếu version vẫn là 7, đồng thời tăng lên 8:

~~~text
UPDATE order SET status = "PAID", version = 8
WHERE orderId = "ORD-1008" AND version = 7
~~~

Nếu yêu cầu khác đã cập nhật lên version 8, thao tác điều kiện thất bại và ứng dụng cần đọc lại trạng thái, quyết định thử lại hoặc báo xung đột.

**Compare-and-set (CAS)** giúp ngăn ghi đè dữ liệu cũ mà không biết; nó khác với ràng buộc tên đăng nhập duy nhất. Trong cả hai trường hợp, điểm chung là **điều kiện được kiểm tra ngay trong thao tác ghi**.

### 7.3. Write skew và bất biến trải trên nhiều bản ghi

Giả sử quy tắc “mỗi ca trực luôn có ít nhất một nhân viên trực”. A và B cùng kiểm tra thấy người kia đang trực; A và B lần lượt tự nghỉ. Mỗi người chỉ cập nhật **bản ghi của mình**, nên một CAS trên từng bản ghi vẫn có thể thành công và để lại ca trực không có ai.

Đây là dạng xung đột trên **bất biến nhiều bản ghi**. Cần cơ chế giao dịch có mức isolation thích hợp, hoặc thiết kế lại bất biến để được kiểm tra nguyên tử tại một điểm phối hợp. **Atomicity của một bản ghi không bảo đảm mọi quy tắc trên nhiều bản ghi**.

## 8. Thiết kế khóa duy nhất trong NoSQL phân tán

### 8.1. “Duy nhất” ở phạm vi nào?

Mỗi sản phẩm có phạm vi nguyên tử và nhất quán khác nhau:

| Phạm vi | Ví dụ | Câu hỏi cần hỏi |
|---|---|---|
| Một tài liệu/mục | Tạo mục theo khóa chưa tồn tại | Có conditional create nguyên tử không? |
| Một phân vùng | Ghi theo cùng partition key | Điều kiện có được phối hợp tại phân vùng đó không? |
| Nhiều mục cùng kho | Tạo hồ sơ và chỗ giữ username | Có giao dịch nhiều mục không? |
| Nhiều phân vùng/shard | Unique username toàn tenant | Ràng buộc có bao phủ mọi shard không? |
| Nhiều vùng hoạt động | Cùng username được đăng ký ở hai khu vực | Hệ thống có phối hợp đồng bộ toàn cầu không? |
| Nhiều dịch vụ | Tạo user ở Identity và Profile | Ai sở hữu bất biến, cách rollback hoặc đối soát? |

**Không được suy từ “cơ sở dữ liệu hỗ trợ transaction” thành “mọi ghi đa vùng đều tuần tự toàn cục”**. Cần đọc rõ phạm vi giao dịch, replication, conflict resolution và độ trễ của công nghệ thực tế.

### 8.2. Mẫu reservation key cho unique username

Nếu kho hỗ trợ conditional put theo khóa nhưng không có unique index tùy ý, ta có thể biến bài toán duy nhất thành một khóa đặc biệt:

~~~text
PK = USERNAME#<tenantId>#<normalizedUsername>
value = { ownerUserId: <userId>, status: "RESERVED" }
~~~

Ví dụ:

~~~text
USERNAME#T1#alice -> ownerUserId = U100
USERNAME#T2#alice -> ownerUserId = U777
~~~

Hai tenant được dùng cùng username vì chúng là hai khóa khác nhau. Nhưng hai yêu cầu của T1 cho "alice" cạnh tranh **đúng một khóa**.

Mẫu này chỉ bảo đảm giữ username nếu **việc tạo reservation là nguyên tử và mọi đường ghi bắt buộc đi qua nó**. Nếu ứng dụng khác có thể tạo hồ sơ tùy ý mà không đặt chỗ, bất biến vẫn bị phá.

Nếu reservation và user profile được lưu riêng, cần giải quyết tính nguyên tử qua giao dịch hoặc quy trình có trạng thái (ví dụ RESERVED → ACTIVE; có thời hạn, xử lý lỗi và đối soát). Không được tự giả định hai lần ghi luôn cùng thành công.

### 8.3. Multi-region và eventual consistency

Giả sử vùng A và vùng B có thể ghi độc lập, dữ liệu đồng bộ bất đồng bộ:

~~~text
Vùng A: chưa thấy username "alice" -> tạo user A
Vùng B: chưa thấy username "alice" -> tạo user B
Sau đồng bộ: xuất hiện xung đột nghiệp vụ.
~~~

Nếu hệ thống chỉ áp dụng unique condition **cục bộ từng vùng** mà không phối hợp toàn cục, hai vùng có thể đều chấp nhận cùng một định danh trước khi đồng bộ. Một số kho hỗ trợ các cấu hình mạnh hơn; số khác áp dụng giải quyết xung đột cuối cùng và có thể làm mất hoặc ghi đè một phiên bản.

Các hướng thiết kế có thể là:

- **Một vùng chủ cho định danh cần duy nhất toàn cục:** Mọi thao tác cấp phát đi qua cùng nơi; đổi lại có độ trễ và bài toán sẵn sàng.
- **Dịch vụ cấp phát/đăng ký tên có cơ chế đồng thuận phù hợp:** Bảo đảm mạnh hơn nhưng thêm thành phần phối hợp.
- **Phân chia không gian định danh:** Ví dụ username chỉ duy nhất trong tenant, và mỗi tenant được ghi qua một chủ sở hữu rõ ràng.
- **Chấp nhận xung đột và có quy trình hòa giải:** Chỉ phù hợp khi nghiệp vụ có thể xử lý việc hai định danh được tạo đồng thời; thường không phù hợp cho những trường hợp cấm trùng nghiêm ngặt.

Đây là quyết định sản phẩm và kiến trúc, cần xác định từ yêu cầu sẵn sàng, độ trễ, tính nhất quán và khả năng chấp nhận xung đột.

## 9. Idempotency: xử lý yêu cầu gửi lại mà không tạo thêm tác dụng

Không phải mọi “trùng lặp” là hai người cùng chọn một username. Trong hệ thống phân tán, **cùng một yêu cầu hợp lệ** có thể được gửi nhiều lần vì mất kết nối, timeout, retry tự động hoặc sự kiện được chuyển lại.

### 9.1. Timeout không có nghĩa thao tác thất bại

~~~text
Client -> Server: Tạo đơn hàng
Server -> Database: Tạo ORD-1008 thành công
Server -> Client: Phản hồi bị mất trên mạng
Client: Timeout, không biết đã tạo hay chưa
Client -> Server: Gửi lại yêu cầu
~~~

Nếu server tạo một đơn mới ở lần retry, khách có thể bị tính tiền hoặc xử lý đơn hai lần. Cần **idempotency key** do phía gọi cung cấp hoặc cơ chế nhận diện yêu cầu đã xử lý.

### 9.2. Định danh thao tác và định danh bản ghi

Phân biệt:

- **orderId:** Định danh đơn đã được tạo.
- **idempotencyKey:** Định danh *ý định tạo đơn* được gửi lại.
- **request fingerprint:** Dấu vân tay của nội dung quan trọng để phát hiện cùng idempotencyKey nhưng payload khác.

Ví dụ giao diện:

~~~http
POST /orders
Idempotency-Key: req-9f8c
Content-Type: application/json

{"customerId":"C17","items":[{"sku":"P10","quantity":1}]}
~~~

Server có thể lưu một bản ghi:

~~~json
{
  "idempotencyKey": "req-9f8c",
  "customerId": "C17",
  "requestFingerprint": "hash-canonical-request",
  "status": "COMPLETED",
  "resultOrderId": "ORD-1008"
}
~~~

**Cách xử lý mong muốn:**

1. Yêu cầu đầu tiên chiếm quyền xử lý key bằng một thao tác ghi nguyên tử.
2. Các yêu cầu khác dùng cùng key và nội dung tương đương nhận cùng kết quả đã lưu hoặc trạng thái đang xử lý theo chính sách.
3. Nếu cùng key nhưng payload khác, hệ thống phản hồi lỗi xung đột, không âm thầm áp dụng một tác vụ khác.
4. Có cơ chế phục hồi trường hợp key được giữ nhưng tác vụ phía sau chưa hoàn tất.
5. Thời hạn lưu idempotency key được định nghĩa theo nghiệp vụ; sau thời hạn, hệ thống phải có chính sách rõ với retry đến muộn.

Trong một kho có transaction, có thể ghi bản ghi idempotency và tạo đơn trong cùng giao dịch. Nếu hành động liên quan dịch vụ ngoài như cổng thanh toán, một transaction của cơ sở dữ liệu **không bao trùm tự động** yêu cầu mạng tới dịch vụ đó. Cần idempotency ở phía cổng, trạng thái tác vụ, outbox/inbox hoặc quy trình đối soát tương ứng.

### 9.3. Tại sao “đọc idempotency key trước” vẫn chưa đủ?

Mẫu sai:

~~~text
IF idempotencyKey not found:
  chargeCard()
  save(idempotencyKey)
~~~

Hai worker có thể cùng thấy key chưa tồn tại và cùng chargeCard. Cần **claim key nguyên tử trước khi thực thi hành động** và phối hợp trạng thái của thao tác. Đây là chính cùng một lỗi check-then-write dưới dạng khác.

### 9.4. Delivery “at least once” và hiệu ứng “đúng một lần”

Một hệ thống gửi sự kiện **at least once** có thể giao cùng event nhiều lần. Consumer nên sử dụng **eventId ổn định**, deduplication và ghi có điều kiện hoặc transaction để tránh áp dụng lại tác dụng nghiệp vụ.

**Exactly-once delivery** (nếu một công nghệ quảng bá hỗ trợ trong phạm vi nào đó) không tự đồng nghĩa mọi side effect bên ngoài được thực hiện đúng một lần. Giới hạn giao dịch, phạm vi kho dữ liệu và thao tác mạng ngoài hệ thống vẫn cần xử lý riêng.

## 10. Va chạm do cập nhật hoặc tái sử dụng định danh

### 10.1. Đổi username

Đổi từ "alice" sang "alice2026" là **thao tác thay đổi một khóa nghiệp vụ**, không chỉ sửa trường displayName:

1. Bảo đảm normalizedUsername mới chưa bị người khác giữ.
2. Cập nhật chủ sở hữu username một cách nguyên tử hoặc theo quy trình có trạng thái.
3. Giải phóng hoặc giữ lại username cũ theo chính sách.
4. Xử lý phiên đăng nhập, đường dẫn công khai và các hệ thống tìm kiếm/cache liên quan.

Nếu giữ username cũ để redirect hoặc ngăn mạo danh, nó vẫn là một dạng reservation. Nếu giải phóng, có thể có người khác chiếm ngay khi đồng thời với các yêu cầu còn sử dụng tên cũ.

### 10.2. Xóa mềm và “unique trong bản ghi đang hoạt động”

Giả sử user A bị xóa mềm:

~~~json
{"tenantId":"T1","normalizedUsername":"alice","deletedAt":"2026-11-01T10:00:00Z"}
~~~

Nếu muốn cho user B đăng ký "alice" sau đó, chỉ mục unique bao phủ **mọi** bản ghi có thể ngăn hành động này. Cần quyết định:

- Giữ unique trên mọi bản ghi để không tái sử dụng username.
- Chỉ ràng buộc unique với tài khoản hoạt động qua cơ chế **partial index** hoặc reservation phù hợp.
- Chuyển username cũ sang lịch sử/định danh đã thu hồi trong quy trình rõ ràng.

Việc cho tái sử dụng email/username có thể ảnh hưởng kiểm toán và quy trình khôi phục tài khoản. Do đó chính sách tái sử dụng là yêu cầu nghiệp vụ, không chỉ lựa chọn tối ưu kỹ thuật.

### 10.3. Nạp dữ liệu cũ và hợp nhất bản ghi

Một hệ thống nhập 1.000.000 tài khoản từ nguồn cũ có thể phát hiện:

- Hai user cùng username do trước đây không có unique constraint.
- Chữ hoa/chữ thường chưa chuẩn hóa.
- Cùng người xuất hiện ở nhiều nguồn với các ID khác nhau.
- ID nguồn bị tái sử dụng, hoặc khóa tổng hợp không chứa tenantId.

Không được tự động hợp nhất chỉ vì hai bản ghi có cùng tên hoặc hash. Cần quy tắc nhận diện, ưu tiên nguồn, lịch sử và quyết định cho các trường hợp mơ hồ.

Trong quá trình di trú, có thể tạo bảng ánh xạ:

| Source | Source ID | Canonical ID | Trạng thái |
|---|---|---|---|
| CRM | 41 | U100 | Đã đối chiếu |
| OldApp | A-77 | U100 | Đã xác minh là cùng người |
| OldApp | A-78 | Chưa xác định | Cần xử lý xung đột |

Chỉ sau khi dữ liệu đáp ứng ràng buộc mới bật unique index hoặc cho hệ thống mới nhận ghi theo chính sách thống nhất.

## 11. Những ví dụ thiết kế theo cơ sở dữ liệu NoSQL

Các ví dụ dưới đây nhằm minh họa **nguyên tắc**. Cú pháp và khả năng cụ thể có thể thay đổi theo phiên bản, chế độ triển khai và cấu hình.

### 11.1. MongoDB: unique index thay cho check-then-insert

Một hệ thống nhiều tenant cho phép username trùng ở hai tenant khác nhau nhưng không trùng trong cùng tenant:

~~~javascript
db.users.createIndex(
  { tenantId: 1, normalizedUsername: 1 },
  { unique: true }
);
~~~

Ứng dụng có thể kiểm tra khả dụng để thông báo sớm, nhưng **kết quả cuối cùng** dựa trên kết quả insert/update. Nếu cần thao tác trên nhiều collection để duy trì bất biến, cân nhắc transaction phù hợp với triển khai đang dùng.

Với ứng dụng phân mảnh, cần xem kỹ **những unique index được phép và phạm vi bảo đảm** trong cách cấu hình shard key. Không coi chỉ mục thử nghiệm ở môi trường không sharding là bằng chứng cho bảo đảm toàn cục ở cấu hình phân mảnh khác.

### 11.2. DynamoDB: conditional put và sentinel item

Nếu bảng khóa chính là pk và muốn bảo vệ username, dùng mục đặt chỗ:

~~~text
pk = USERNAME#T1#alice
ownerId = U100
~~~

Lệnh PutItem với điều kiện **attribute_not_exists(pk)** thực thi tạo mới có điều kiện. Mọi yêu cầu cạnh tranh cùng username phải truy cập cùng pk. Nếu còn cần ghi hồ sơ USER#U100, xem xét **TransactWriteItems** để bảo vệ bất biến qua các mục liên quan trong phạm vi DynamoDB hỗ trợ.

Đặt username trong một thuộc tính không phải khóa trên nhiều mục USER#... rồi chỉ kiểm tra bằng Query trước khi ghi sẽ không đủ để bảo đảm duy nhất khi có cạnh tranh.

### 11.3. Cassandra: thiết kế unique key và lightweight transaction

Cassandra tổ chức dữ liệu theo khóa phân vùng và clustering keys. Quy tắc duy nhất trên một **username toàn hệ thống** thường cần một bảng truy cập theo chính username:

~~~sql
CREATE TABLE username_registry (
    username_key text PRIMARY KEY,
    user_id uuid
);
~~~

Thao tác:

~~~sql
INSERT INTO username_registry (username_key, user_id)
VALUES ('T1#alice', 00000000-0000-0000-0000-000000000100)
IF NOT EXISTS;
~~~

Nếu câu lệnh trả về không áp dụng được điều kiện, username đã được giữ. Cần kiểm tra kết quả applied trong client. Với hồ sơ user lưu ở bảng khác, giải quyết thêm khả năng một bước thành công và bước kia thất bại. Không mặc định LWT một partition trở thành giao dịch đa bảng nhiều partition.

### 11.4. Redis: SET NX và giới hạn phạm vi

Trong Redis, lệnh:

~~~text
SET username:T1:alice U100 NX
~~~

chỉ đặt giá trị nếu khóa chưa tồn tại ở thời điểm lệnh được xử lý. Đây là một thao tác nguyên tử đối với khóa tại instance thực thi. Nhưng nếu hồ sơ user nằm ở một cơ sở dữ liệu khác, hai bước **SET NX** và **ghi hồ sơ** không tự là giao dịch chung.

Nếu dùng **TTL** cho reservation, khóa có thể hết hạn rồi được cấp lại. Điều này có thể phù hợp cho “giữ tên trong lúc hoàn tất đăng ký”, nhưng không đủ cho yêu cầu duy nhất lâu dài nếu TTL hết trong lúc tài khoản đang tồn tại. Ngoài ra, tính bền vững và failover của dữ liệu Redis phải được đánh giá theo cấu hình; không mặc định một cache tạm thời là nguồn thẩm quyền về định danh.

## 12. Luồng đăng ký an toàn từ góc nhìn nghiệp vụ

Một API đăng ký username có thể được chia thành:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu tạo tài khoản"] --> B["Chuẩn hóa và kiểm tra định dạng username"]
    B --> C["Tạo ID tài khoản và idempotency key nếu cần"]
    C --> D["Thử ghi nguyên tử với ràng buộc duy nhất"]
    D --> E{"Ghi thành công?"}
    E -->|Có| F["Trả về ID và kết quả tạo tài khoản"]
    E -->|Trùng định danh| G["Trả về xung đột phù hợp"]
    E -->|Lỗi tạm thời| H["Xử lý retry an toàn và đối soát kết quả"]
~~~

Về mặt trải nghiệm, API có thể gọi “kiểm tra username còn trống?” để hiển thị gợi ý sớm. Nhưng ở đường ghi cuối cùng, **không bỏ bước bảo vệ nguyên tử** ngay cả khi người dùng vừa được thông báo tên khả dụng.

Một quy trình đáng tin cậy cần xác định thêm:

- Yêu cầu tạo tài khoản có thể được gửi lại với cùng idempotency key không?
- Nếu client timeout sau khi server ghi thành công, làm sao trả lại đúng tài khoản cũ?
- Nếu ràng buộc trùng do _id hay username, cách phân biệt phản hồi thế nào?
- Có cần transaction giữa reservation và hồ sơ không?
- Các lỗi tạm thời có được retry với backoff không, và retry có vô tình gây tác dụng phụ không?
- Khi nhiều vùng cùng xử lý, cơ chế nào thật sự kiểm soát một định danh duy nhất?

## 13. Xử lý lỗi xung đột và retry

### 13.1. Xung đột là kết quả nghiệp vụ có thể dự đoán

Nếu hai người cùng đăng ký một username, một người không thể thành công khi quy tắc cấm trùng. Trường hợp thất bại nên được xem là **xung đột bình thường**, không phải lúc nào cũng là lỗi hệ thống.

Ví dụ phân loại:

| Tình huống | Cách xử lý ứng dụng |
|---|---|
| Username đã có người giữ | Thông báo tên đã dùng, đề nghị tên khác; phản hồi xung đột phù hợp |
| ID kỹ thuật ngẫu nhiên trùng | Không ghi đè; có thể sinh ID mới và thử lại trong giới hạn rõ |
| Conditional write thất bại vì version đã đổi | Đọc trạng thái hiện tại, quyết định cập nhật lại hoặc báo xung đột |
| Client timeout, chưa rõ ghi đã thành công chưa | Dùng idempotency key hoặc truy vấn theo ID ổn định để xác minh |
| Dịch vụ dữ liệu tạm thời lỗi | Retry có giới hạn, backoff và phân biệt lỗi có thể retry |
| Trùng event đã xử lý | Không áp dụng lại side effect; trả trạng thái đã xử lý |

Không nên retry vô hạn một lỗi unique violation do username thực sự đã được người khác sử dụng. Retry cũng không nên đổi sang ID mới tùy tiện nếu mục đích là **gửi lại cùng thao tác đã thành công**: điều đó dễ tạo bản ghi trùng.

### 13.2. Không biết kết quả ghi: trạng thái “unknown outcome”

Trong hệ thống phân tán, một timeout có thể xảy ra:

1. Trước khi request tới database.
2. Trong khi database đang xử lý.
3. Sau khi database commit nhưng trước khi response về client.

Do đó, **timeout không đủ để kết luận “chưa ghi”**. Với thao tác có tác dụng quan trọng, cần khả năng tìm lại kết quả theo ID ổn định hoặc idempotency key.

Một API tốt có thể trả về cùng kết quả khi khách hàng retry cùng thao tác, hoặc trạng thái “đang xử lý” để client tiếp tục theo dõi. Không nên tạo thêm đối tượng mới mỗi khi người dùng nhấn lại.

### 13.3. Tránh công bố thông tin nhạy cảm từ lỗi duy nhất

Một API đăng ký có thể vô tình làm lộ việc một email cụ thể đã đăng ký hay chưa. Phản hồi xung đột cần cân nhắc chính sách bảo mật, khả năng liệt kê tài khoản và trải nghiệm người dùng. Không trả nguyên văn lỗi cơ sở dữ liệu có thể chứa thông tin nội bộ, cấu trúc chỉ mục hoặc định danh không cần thiết.

## 14. Mô hình suy luận để chọn giải pháp

Khi nhận một yêu cầu như “Không được tạo trùng”, hãy đi qua các câu hỏi:

**Bước 1 – Định nghĩa bất biến.** Cái gì phải duy nhất? ID đơn hàng, username trong tenant, mã thanh toán ngoài hay một ghế trong suất chiếu?

**Bước 2 – Xác định nơi phát sinh cạnh tranh.** Có bao nhiêu instance, worker, vùng và nguồn ghi? Có ai ghi trực tiếp bỏ qua ứng dụng chính không?

**Bước 3 – Đưa điều kiện vào điểm ghi.** Dùng unique index, conditional put, CAS hoặc transaction đúng phạm vi. Nếu không có thao tác nguyên tử thích hợp, xem xét thay đổi khóa/mô hình dữ liệu.

**Bước 4 – Xử lý bất biến nhiều bản ghi.** Nếu tạo một tài khoản đòi hỏi ghi hồ sơ và giữ username cùng thành công, chọn giao dịch hoặc quy trình bù trừ, đối soát có trạng thái rõ ràng.

**Bước 5 – Bảo vệ retry.** Một yêu cầu có thể được lặp lại do timeout; cần idempotency và phân biệt cùng một ý định với một ý định mới.

**Bước 6 – Xử lý xung đột một cách có nghĩa.** Báo trùng tên khi tên đã được dùng, đọc lại khi version đổi, chỉ retry lỗi tạm thời.

**Bước 7 – Kiểm tra phạm vi phân tán.** Tính duy nhất có thật sự bao phủ các shard/vùng/đường ghi mà nghiệp vụ yêu cầu không?

## 15. Bài tập thực hành

### Bài 1. Tìm lỗi đua tranh ở đăng ký tài khoản

Cho đoạn mã giả:

~~~text
if not exists(username):
    userId = generateRandomId()
    insertUser(userId, username)
    return success
else:
    return duplicate
~~~

Giả sử hai request đồng thời đăng ký "minh" trong cùng tenant.

1. Hãy mô tả lịch thực thi khiến cả hai cùng trả success.
2. Vì sao ID ngẫu nhiên khác nhau không loại bỏ lỗi trùng username?
3. Đề xuất cách bảo vệ bằng unique compound index hoặc khóa reservation nguyên tử.
4. Khi lỗi trùng xảy ra, ứng dụng cần phản hồi thế nào?

**Gợi ý:** Hai request cùng chạy exists trước khi request nào insert. Cần đưa ràng buộc (tenantId, normalizedUsername) vào một cơ chế thực thi nguyên tử ở điểm ghi. Với index duy nhất, một lệnh ghi được chấp nhận và lệnh kia bị từ chối.

### Bài 2. Phân biệt collision và retry

Một API tạo đơn có tình huống:

~~~text
Client gửi requestId = X, server tạo ORD-21 rồi phản hồi bị mất.
Client gửi lại requestId = X.
~~~

Câu hỏi:

1. Đây có nhất thiết là va chạm ID ngẫu nhiên không?
2. Nếu server tự sinh orderId mới khi nhận request thứ hai, có rủi ro gì?
3. Đề xuất schema cho bản ghi idempotency và quy tắc xử lý khi payload thay đổi nhưng requestId giữ nguyên.

**Gợi ý:** Đây là tình huống cùng một ý định được gửi lại. Có thể dùng bản ghi theo requestId lưu fingerprint, trạng thái và orderId kết quả; việc claim requestId phải nguyên tử.

### Bài 3. Ghế cuối cùng trong một suất chiếu

Một suất chiếu S1 có ghế A10. Hai người cùng chọn ghế này.

1. Thiết kế khóa duy nhất để không bán trùng: ví dụ SHOW#S1#SEAT#A10.
2. Viết thao tác giả mã đặt chỗ nguyên tử theo khóa.
3. Nếu hệ thống có bước thanh toán ngoài, cần xử lý đặt chỗ chưa thanh toán, hết hạn và thanh toán thành công đến muộn thế nào?

**Gợi ý:**

~~~text
CONDITIONAL_PUT(
  key = "SHOW#S1#SEAT#A10",
  state = "HELD",
  owner = requestId,
  expiresAt = holdDeadline,
  condition = "seat is available according to validated state"
)
~~~

Đây là mô hình ý tưởng, không phải lệnh có cú pháp chung cho mọi NoSQL. Nếu một khóa giữ chỗ đã tồn tại ở trạng thái hết hạn, cần thao tác điều kiện dựa trên **trạng thái hiện tại** để chuyển chủ sở hữu an toàn; không dùng GET rồi DELETE/PUT vô điều kiện.

Đối với thanh toán ngoài, cần liên kết kết quả thanh toán với đúng lượt giữ chỗ, dùng idempotency và quy tắc hoàn tiền/đối soát khi trạng thái đến muộn. **TTL tự xóa một khóa** không giải quyết đầy đủ tình huống thanh toán đang xử lý.

### Bài 4. Va chạm hash

Một nhóm phát triển lưu tài liệu bằng khóa 6 ký tự hex đầu của SHA-256 nội dung:

~~~text
docKey = sha256(content).substring(0, 6)
~~~

1. Không gian khóa có bao nhiêu giá trị khả dĩ?
2. Rủi ro tăng ra sao khi số lượng tài liệu tăng?
3. Vì sao phải kiểm tra nội dung hoặc dùng cơ chế mạnh hơn khi khóa đã tồn tại?

**Gợi ý:** Sáu ký tự hex biểu diễn \(16^6 = 2^{24}\) giá trị. Không gian này quá nhỏ để xem va chạm là bất khả thi trong kho lớn. Khi hai nội dung khác nhau chia sẻ cùng khóa rút gọn, phải phát hiện xung đột và xử lý, thay vì coi chúng là cùng tài liệu.

### Bài 5. Thiết kế lại khóa theo tenant

Một ứng dụng lưu mọi user theo khóa username và đặt điều kiện không tồn tại. Sau khi triển khai SaaS, hai tenant T1 và T2 đều muốn có user "admin".

1. Quy tắc duy nhất cần thay đổi thế nào?
2. Khóa vật lý nên thay đổi ra sao nếu mỗi tenant được dùng username giống nhau?
3. Những đường truy vấn nào phải cập nhật để tránh lấy nhầm dữ liệu tenant khác?

**Gợi ý:** Bất biến là duy nhất theo **(tenantId, normalizedUsername)**. Cần đặt tenantId vào khóa hoặc cơ chế ràng buộc, đồng thời bảo đảm mọi thao tác đọc, cập nhật và kiểm tra quyền đều gắn đúng tenant.

## 16. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng UUID và cho rằng username tự duy nhất | Hai user ID khác nhau có cùng username | Bảo vệ thêm định danh nghiệp vụ |
| Check exists rồi insert | Hai request có thể cùng vượt qua kiểm tra | Unique index hoặc conditional insert nguyên tử |
| Upsert vô điều kiện cho thao tác tạo mới | Bản ghi cũ có thể bị ghi đè | Dùng insert-if-absent hoặc điều kiện đúng mục đích |
| Chỉ kiểm tra duy nhất trong frontend hoặc cache | Dữ liệu đồng thời vượt qua kiểm tra | Kiểm soát bất biến tại điểm ghi có thẩm quyền |
| Tự chọn một hash ngắn làm ID tuyệt đối | Nội dung khác nhau có thể bị gộp | Không gian khóa đủ lớn, kiểm tra va chạm và phương án giải quyết |
| Quên phạm vi tenant | Từ chối username hợp lệ hoặc rò dữ liệu | Khóa và truy vấn có tenantId |
| Coi strong read là khóa độc quyền | Vẫn có race giữa đọc và ghi | Điều kiện nằm trong thao tác ghi |
| Dùng khóa Redis có TTL để giữ username vĩnh viễn | Tên có thể được cấp lại khi hết hạn | Chính sách reservation và nguồn thẩm quyền bền vững |
| Dùng CAS một mục để bảo vệ quy tắc nhiều mục | Write skew hoặc trạng thái lệch | Giao dịch, điểm phối hợp hoặc thiết kế lại bất biến |
| Retry mọi lỗi trùng bằng ID mới | Gây trùng nghiệp vụ, khó đối soát | Phân biệt lỗi xung đột với retry cùng ý định |
| Dựa vào unique cục bộ để hứa duy nhất đa vùng | Xung đột sau replication | Kiểm tra bảo đảm toàn vùng, chọn điểm cấp phát phù hợp |
| Xóa reservation khi client mất kết nối mà không xét giao dịch đã hoàn tất | Tái cấp định danh, mất trạng thái | Idempotency, trạng thái có vòng đời và đối soát |

## 17. Kết luận

Trong thiết kế khóa và định danh cho NoSQL, **chống trùng dữ liệu** là vấn đề kết hợp giữa **ngữ nghĩa nghiệp vụ**, **phạm vi khóa**, **cơ chế ghi nguyên tử** và **đồng thời phân tán**.

- **Va chạm ID/hash** cần được phát hiện bằng cơ chế tạo mới từ chối trùng và phương án xử lý phù hợp; không nên mặc định va chạm là bất khả thi.
- **Tính duy nhất nghiệp vụ** phải được định nghĩa cụ thể về phạm vi, chuẩn hóa, trạng thái và khả năng tái sử dụng.
- **Check-then-write** có lỗ hổng đua tranh; một lần đọc “chưa có” không bảo vệ tương lai. Dùng unique constraint, conditional create hoặc transaction tại đúng phạm vi.
- **Nhiều bản ghi và nhiều vùng** đòi hỏi kiểm tra rõ phạm vi bảo đảm, có thể cần điểm điều phối hoặc quy trình có trạng thái.
- **Retry và sự kiện gửi lại** phải được nhận diện bằng idempotency key, kết quả lưu bền vững và xử lý unknown outcome.

Khi mọi tác nhân đều tuân theo cùng một cơ chế kiểm soát ở thời điểm ghi, hệ thống mới có cơ sở bảo đảm rằng “một định danh chỉ thuộc về một chủ thể” theo đúng phạm vi nghiệp vụ đã đặt ra.

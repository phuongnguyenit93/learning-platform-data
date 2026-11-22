# Giá trị dạng byte, chuỗi hoặc cấu trúc dữ liệu theo khả năng của từng hệ

Mô hình **khóa–giá trị (key–value)** thường được giới thiệu bằng một phép ánh xạ đơn giản: cung cấp **key**, hệ thống trả về **value**. Tuy nhiên, chữ *value* không có cùng ý nghĩa ở mọi cơ sở dữ liệu NoSQL. Có hệ chỉ lưu **một dãy byte** mà không hiểu nội dung; có hệ cung cấp kiểu **chuỗi văn bản**; có hệ cho phép lưu và thao tác trực tiếp với **hash, list, set, sorted set, map, number, binary** và những cấu trúc khác.

Khác biệt này quyết định cách ứng dụng mã hóa dữ liệu, cập nhật một thuộc tính, xử lý truy cập đồng thời, thiết kế key, sử dụng bộ nhớ và xây dựng truy vấn. Chẳng hạn, một giỏ hàng được lưu thành chuỗi JSON và một giỏ hàng được lưu thành Redis Hash có thể hiển thị giống nhau trên giao diện, nhưng cách cập nhật số lượng từng mặt hàng, cách kiểm soát ghi đè và số thao tác gửi đến database lại khác.

Bài học tập trung vào cách đọc đúng khả năng của **từng hệ key–value** trước khi chọn kiểu giá trị. Các ví dụ minh họa chủ yếu dùng Redis, sau đó đối chiếu với Memcached, etcd, RocksDB và DynamoDB. Mục tiêu là hiểu nguyên tắc thiết kế; các đoạn lệnh chỉ mang ý nghĩa minh họa, không giả định mọi sản phẩm đều hỗ trợ cùng một API.

## 1. Key–value mô tả cách truy cập, chưa định nghĩa kiểu của value

Ở mức khái niệm, một kho khóa–giá trị cung cấp phép ánh xạ:

\[
\text{Key} \longrightarrow \text{Value}
\]

Ví dụ:

| Key | Value nhìn từ nghiệp vụ | Mục đích |
|---|---|---|
| **session:1001** | Thông tin phiên đăng nhập | Xác thực nhanh |
| **cart:1001** | Các mặt hàng và số lượng | Cập nhật giỏ hàng |
| **counter:visits:2026-11-14** | Số lượt truy cập | Đếm sự kiện |
| **cache:product:42** | Dữ liệu sản phẩm đã dựng sẵn | Trả kết quả đọc nhanh |
| **avatar:1001** | Dữ liệu ảnh hoặc tham chiếu đến tệp ảnh | Tra cứu tài nguyên |

Nhìn vào bảng chưa thể biết hệ thống có hiểu **cart** là một tập các trường hay chỉ là một khối byte. Sự khác biệt nằm ở API và cơ chế lưu trữ mà hệ đó cung cấp.

~~~mermaid
flowchart TD
    A["Ứng dụng: cần lưu giỏ hàng"] --> B["Chọn key: cart:1001"]
    B --> C{"Hệ thống hỗ trợ value nào?"}
    C --> D["Dãy byte / opaque blob"]
    C --> E["String"]
    C --> F["Cấu trúc native: Hash, List, Set..."]
    D --> G["Ứng dụng tự encode/decode"]
    E --> H["Đọc/ghi chuỗi; có thể chứa JSON"]
    F --> I["Lệnh cập nhật phần tử/trường"]
    G --> J["Cân nhắc đồng thời, schema, TTL và chi phí"]
    H --> J
    I --> J
~~~

Cần tách ba khái niệm:

1. **Kiểu dữ liệu nghiệp vụ:** giỏ hàng là danh sách mặt hàng, tổng tiền là số, ảnh là dữ liệu nhị phân.
2. **Biểu diễn lưu trữ:** JSON UTF-8, byte array, MessagePack, Protobuf hoặc cấu trúc do database quản lý.
3. **Khả năng thao tác phía database:** đọc/ghi toàn value, tăng số nguyên, sửa một field, thêm phần tử vào set, lấy một khoảng theo điểm số.

Một hệ hỗ trợ lưu JSON dưới dạng chuỗi **không có nghĩa** nó mặc nhiên hỗ trợ truy vấn một thuộc tính JSON hoặc cập nhật riêng thuộc tính đó. Muốn làm vậy có thể cần mô-đun, API chuyên biệt hoặc đổi cách biểu diễn.

## 2. Ba cách nhìn phổ biến về giá trị

### 2.1. Value là dãy byte không có ngữ nghĩa (opaque bytes)

Ở mô hình này, database coi value là một dãy byte:

~~~text
Key                  Value thực sự lưu
--------------------------------------------------------
user:1001:profile    7B 22 6E 61 6D 65 22 3A ... 
avatar:1001          89 50 4E 47 0D 0A 1A 0A ...
counter:demo         00 00 00 00 00 00 00 2A
~~~

Các dãy byte có thể lần lượt biểu diễn JSON, dữ liệu ảnh PNG và số nguyên 64-bit kiểu big-endian. Nếu database chỉ hiểu value là byte, **nó không thể tự suy ra** byte nào là tên, giá hay số lượng. Ứng dụng và thư viện mã hóa phải thống nhất quy tắc diễn giải.

Ưu điểm:

- Có thể lưu nhiều định dạng: văn bản, dữ liệu nhị phân, cấu trúc đã serialize.
- Thao tác đọc/ghi theo key đơn giản.
- Không phụ thuộc cấu trúc nội bộ của value ở phía engine.

Hạn chế:

- Muốn sửa một trường thường phải đọc, giải mã, sửa, mã hóa và ghi lại toàn bộ value.
- Khi có hai client cùng sửa, dễ xảy ra **lost update** nếu thiếu version, CAS hoặc transaction phù hợp.
- Không thể giả định có lệnh tìm tất cả value chứa một thuộc tính nghiệp vụ.
- Khi đổi định dạng, các phiên bản ứng dụng phải tương thích với dữ liệu đã lưu.

Kiểu này phổ biến ở các engine key–value ở tầng thấp như RocksDB, ở thao tác giá trị của etcd và trong nhiều cách sử dụng Memcached. Mỗi hệ vẫn có những khả năng bổ sung riêng; “opaque bytes” mô tả **cách engine hiểu nội dung**, không phải toàn bộ tính năng của sản phẩm.

### 2.2. Value là chuỗi (string)

Chuỗi dễ đọc, dễ kiểm tra và thường phù hợp với:

- Cờ trạng thái: **enabled**, **disabled**.
- Mã hoặc token đã được quản lý an toàn.
- Giá trị cấu hình ngắn.
- Số biểu diễn dạng chữ khi hệ thống có lệnh tăng/giảm tương thích.
- JSON hoặc XML do ứng dụng serialize.

Ví dụ với Redis CLI:

~~~redis
SET demo:welcome "Xin chào"
GET demo:welcome
TYPE demo:welcome
~~~

Kết quả **GET** là chuỗi **Xin chào**, còn **TYPE** trả **string**.

Tuy vậy, Redis String là **binary-safe**: giá trị có thể chứa byte không phải UTF-8 hợp lệ. Tên gọi *String* trong Redis là **kiểu dữ liệu API của Redis**, không phải lời cam kết rằng nội dung luôn là văn bản Unicode.

Với một value dạng JSON:

~~~redis
SET demo:profile:1001 "{\"name\":\"An\",\"level\":3}"
GET demo:profile:1001
TYPE demo:profile:1001
~~~

Redis vẫn báo **string**, vì JSON ở đây chỉ là **nội dung của chuỗi**. Database không tự biến trường **level** thành một trường độc lập có thể thao tác bằng lệnh Hash.

### 2.3. Value là cấu trúc có API riêng của database

Một số hệ cung cấp nhiều kiểu dữ liệu native. Redis là ví dụ điển hình: một key có thể gắn với String, Hash, List, Set, Sorted Set, Stream và những cấu trúc hoặc chức năng chuyên biệt khác.

~~~text
cart:1001           -> Hash       {sku:pen -> 2, sku:book -> 1}
queue:emails        -> List       [job-1, job-2, job-3]
tags:product:42     -> Set        {java, nosql, backend}
leaderboard:daily   -> Sorted Set {(user:7, 98), (user:9, 135)}
events:orders       -> Stream     [event-1, event-2, ...]
~~~

Ứng dụng có thể dùng lệnh thao tác ở mức field hoặc phần tử, ví dụ **HINCRBY** để tăng số lượng một mặt hàng trong Hash, **SADD** để thêm phần tử vào Set, hoặc **ZREVRANGE**/**ZRANGE** để đọc bảng xếp hạng theo điểm số và thứ tự tùy lựa chọn.

Cần nhớ rằng **cấu trúc native có quy tắc riêng**. Redis Hash lưu field–value với các giá trị trường được diễn giải là chuỗi byte; nó không tự chuyển thành một cây object có trường lồng nhau như JSON. Một key thuộc loại Hash cũng không thể đọc bằng **GET** dành cho String; thông thường database trả lỗi **WRONGTYPE**.

## 3. Cùng tên key–value, các hệ có khả năng khác nhau

| Hệ thống | Biểu diễn value tiêu biểu | Thao tác đặc trưng | Điều cần lưu ý |
|---|---|---|---|
| **Redis** | String binary-safe; Hash, List, Set, Sorted Set, Stream và kiểu khác | **GET/SET**, **HSET**, **HINCRBY**, **SADD**, **ZADD**, thao tác theo key | Mỗi key có kiểu Redis; lệnh phải đúng kiểu; JSON dạng object có thể cần mô-đun hoặc biểu diễn khác |
| **Memcached** | Payload byte cùng metadata như flags do client sử dụng | Get/set, add/replace, CAS, tăng/giảm các giá trị số phù hợp | Engine không hiểu trường nằm trong JSON; client quyết định serialize |
| **etcd v3** | Key/value dạng byte; có revision, lease, watch | Get/put, transaction so sánh điều kiện, watch thay đổi | Thường dùng cho cấu hình/phối hợp dịch vụ; không phải engine cho mọi workload dữ liệu lớn |
| **RocksDB** | Key và value dạng byte theo giao diện key–value có thứ tự | Get/put/delete; iteration theo thứ tự key, batch, snapshot | Là engine nhúng vào ứng dụng; schema và serialization thường do ứng dụng thiết kế |
| **DynamoDB** | Item gồm attributes có kiểu như String, Number, Binary, Map, List, Set | GetItem/PutItem/UpdateItem, điều kiện cập nhật, query theo key/index | Là cơ sở dữ liệu key–value **và** document; không chỉ là một blob cho mỗi key |

Không nên lấy khả năng của một hệ để suy ra khả năng của hệ khác. Chẳng hạn:

- Redis có **Hash** không có nghĩa Memcached cũng có lệnh cập nhật một field.
- RocksDB trả về byte không có nghĩa DynamoDB chỉ lưu byte; DynamoDB hiểu kiểu attribute.
- etcd có watch và revision không có nghĩa một Redis String đã có cùng mô hình phiên bản.
- Redis có thao tác Set/Sorted Set không có nghĩa mọi hệ NoSQL đều hỗ trợ truy vấn thành viên hoặc xếp hạng.

Điều cần đọc trong tài liệu kỹ thuật của hệ cụ thể là **API value**, **kiểu key**, **kiểu thao tác nguyên tử**, **giới hạn kích thước**, **TTL**, **index**, **transaction** và **quy tắc nhất quán**.

## 4. Dãy byte và chuỗi: ứng dụng phải thống nhất cách mã hóa

Một byte không phải một ký tự. Trong Unicode UTF-8, một ký tự có thể chiếm nhiều byte; vì thế **độ dài chuỗi Java** và **số byte gửi tới database** không nhất thiết giống nhau.

Ví dụ Java:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class ValueEncodingExample {
    public static void main(String[] args) {
        String text = "Xin chào";

        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(encoded, StandardCharsets.UTF_8);

        System.out.println("UTF-16 code units: " + text.length());
        System.out.println("UTF-8 bytes: " + encoded.length);
        System.out.println("Bytes: " + Arrays.toString(encoded));
        System.out.println("Decoded: " + decoded);
    }
}
~~~

Các điểm cần hiểu:

1. **getBytes(StandardCharsets.UTF_8)** biến chuỗi thành dãy byte có quy ước rõ ràng.
2. **new String(..., UTF_8)** giải mã theo cùng quy ước.
3. **String.length()** của Java đếm số đơn vị mã UTF-16, không phải số byte UTF-8.
4. Dữ liệu nhị phân tùy ý, ví dụ ảnh hoặc bản nén, **không nên** tự chuyển thành String rồi ghi lại bằng UTF-8; quy trình đó có thể làm sai byte ban đầu.

Với số nguyên, cũng cần có quy tắc encoding. Hai client không thể chỉ đồng ý rằng “đây là 42” mà bỏ qua độ rộng số và thứ tự byte:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class BinaryNumberExample {
    public static void main(String[] args) {
        byte[] bytes = ByteBuffer.allocate(Long.BYTES)
                .order(ByteOrder.BIG_ENDIAN)
                .putLong(42L)
                .array();

        long restored = ByteBuffer.wrap(bytes)
                .order(ByteOrder.BIG_ENDIAN)
                .getLong();

        System.out.println(restored); // 42
    }
}
~~~

Nếu một client ghi big-endian còn client đọc little-endian, cùng dãy byte cho kết quả khác. Vì vậy, định dạng byte nên quy định tối thiểu:

- Charset với văn bản, ví dụ **UTF-8**.
- Kiểu và độ rộng số, quy tắc xử lý số âm, số thập phân, thứ tự byte.
- Cách biểu diễn **null**, giá trị rỗng và trường không tồn tại.
- Múi giờ và định dạng thời gian, thường chuẩn hóa UTC ở mức lưu trữ.
- Phiên bản schema/payload để có thể đọc dữ liệu do phiên bản phần mềm cũ ghi.

Không nên dùng cơ chế tuần tự hóa phụ thuộc nội bộ runtime làm định dạng lưu dài hạn khi nhiều ngôn ngữ, phiên bản ứng dụng hoặc công cụ khác cần đọc. Nếu dùng định dạng nhị phân, hãy chọn schema và quy tắc tương thích rõ ràng.

## 5. Chọn định dạng serialize cho value dạng blob

Khi database không hiểu cấu trúc bên trong value, ứng dụng có thể serialize một object:

~~~json
{
  "schemaVersion": 2,
  "userId": "1001",
  "displayName": "An",
  "preferences": {
    "language": "vi",
    "notifications": true
  },
  "updatedAt": "2026-11-14T09:00:00Z"
}
~~~

Các biểu diễn thường gặp:

| Biểu diễn | Đặc điểm | Tình huống phù hợp |
|---|---|---|
| **UTF-8 text** | Dễ đọc, dễ kiểm tra, không tự mô tả nhiều trường | Token, mã trạng thái, cấu hình ngắn |
| **JSON UTF-8** | Có object/array, phổ biến với API, tương đối dễ debug | Profile, cache response, preferences |
| **MessagePack/CBOR** | Biểu diễn dữ liệu có cấu trúc ở dạng nhị phân, thường gọn hơn JSON trong một số trường hợp | Payload muốn giảm byte nhưng vẫn cần cấu trúc động |
| **Protocol Buffers** | Schema có khai báo rõ, nhị phân, khả năng tương thích theo quy tắc field | Hợp đồng giữa dịch vụ nhiều phiên bản |
| **Binary định dạng riêng** | Tối ưu cho trường hợp cụ thể nếu thiết kế cẩn thận | Giá trị chuyên dụng có yêu cầu bộ nhớ/CPU đặc biệt |

Không có định dạng luôn tốt nhất: kích thước sau nén, CPU encode/decode, khả năng kiểm tra, quản lý phiên bản và tương thích giữa dịch vụ đều ảnh hưởng lựa chọn.

Với JSON blob, việc sửa một trường có thể diễn ra như sau:

~~~text
GET profile:1001
    -> decode JSON
    -> đổi preferences.language = "en"
    -> encode JSON
SET profile:1001 <toàn bộ JSON mới>
~~~

Đây là đường thao tác theo **toàn value**, dù nghiệp vụ chỉ đổi một field. Nếu hai yêu cầu đồng thời đọc cùng giá trị cũ rồi ghi toàn blob mới, thay đổi của một yêu cầu có thể bị ghi đè bởi yêu cầu còn lại. Cần version/CAS/transaction hoặc một representation có lệnh cập nhật phần tử phù hợp.

Trường **schemaVersion** giúp ứng dụng quyết định cách đọc dữ liệu cũ. Nó không tự động thực hiện migration; ứng dụng phải định nghĩa quá trình đọc tương thích, chuyển đổi và ghi lại khi cần.

## 6. Redis String: văn bản, byte và số cùng nằm dưới một kiểu API

Redis String cho phép lưu chuỗi ngắn hoặc dữ liệu nhị phân. Trong Redis CLI, ví dụ sau dùng tiền tố **demo:** để tránh lẫn với key nghiệp vụ:

~~~redis
SET demo:status "active"
GET demo:status
TYPE demo:status

SET demo:counter "41"
INCR demo:counter
GET demo:counter
~~~

Sau **INCR**, **demo:counter** có giá trị **42**. Redis có thể tăng số vì nội dung value phù hợp với yêu cầu lệnh **INCR**, dù **TYPE** vẫn là **string**.

Nếu thay bằng JSON:

~~~redis
SET demo:counter "{\"count\":41}"
INCR demo:counter
~~~

Lệnh **INCR** sẽ báo lỗi vì giá trị String này không thể được diễn giải thành số nguyên mà lệnh yêu cầu. Không thể suy ra kiểu nghiệp vụ từ **TYPE string**:

| Nội dung của Redis String | **TYPE** | **INCR** |
|---|---|---|
| **41** | string | Có thể tăng thành 42 nếu giá trị trong miền hợp lệ |
| **active** | string | Báo lỗi |
| **{"count":41}** | string | Báo lỗi |
| Một dãy byte ảnh | string | Không phải bộ đếm số phù hợp |

Đối với phiên có TTL, một lệnh có thể tạo giá trị và gắn hạn:

~~~redis
SET demo:session:1001 "{\"userId\":\"1001\",\"role\":\"member\"}" EX 1800
TTL demo:session:1001
~~~

**EX 1800** đặt hạn 1.800 giây cho key. TTL giúp quản lý tuổi dữ liệu; nhưng việc hết hạn phiên về mặt nghiệp vụ còn cần kiểm tra ở đường xác thực và cách xử lý thu hồi token phù hợp.

Không nên lưu blob nhị phân lớn chỉ vì Redis String chấp nhận byte. Cần cân nhắc giới hạn value, RAM, chi phí replication, persistence, mạng và tần suất đọc/ghi. Với ảnh/video lớn, một giải pháp thường hợp lý là lưu nội dung trong object storage và dùng KV để tra metadata hoặc tham chiếu, nếu yêu cầu hệ thống cho phép.

## 7. Redis Hash: cập nhật field mà không thay toàn bộ JSON

Giả sử giỏ hàng của user **1001** có hai sản phẩm:

~~~text
cart:1001
  sku:pen   -> 2
  sku:book  -> 1
~~~

Với Redis Hash:

~~~redis
HSET demo:cart:1001 sku:pen 2 sku:book 1
TYPE demo:cart:1001
HGET demo:cart:1001 sku:pen
HGETALL demo:cart:1001

HINCRBY demo:cart:1001 sku:pen 1
HGET demo:cart:1001 sku:pen
~~~

Kết quả của **HINCRBY** là số lượng bút tăng từ **2 lên 3**; không cần đưa toàn bộ giỏ hàng về ứng dụng để sửa một trường. Với dữ liệu này, Hash phù hợp vì mỗi SKU là một field và số lượng mỗi SKU là một giá trị được tăng/giảm độc lập.

Tuy vậy, khả năng thao tác field **không tự bảo đảm mọi bất biến nghiệp vụ**:

- HINCRBY là thao tác tăng/giảm ở field tương ứng, nhưng nếu ứng dụng yêu cầu số lượng luôn lớn hơn 0 thì phải có cách kiểm tra và cập nhật nguyên tử đúng quy tắc.
- Nếu giỏ hàng có tổng tiền, khuyến mãi và tồn kho liên quan, cập nhật một field không tự khiến mọi dữ liệu khác đồng bộ.
- Redis Hash không tự cung cấp cây object lồng nhau nhiều cấp như JSON document.
- TTL ở ví dụ này gắn cho **key giỏ hàng**; việc hỗ trợ TTL mức field phụ thuộc tính năng và phiên bản hệ thống, không được mặc định có mặt.

Ví dụ đặt hạn cho cả giỏ:

~~~redis
EXPIRE demo:cart:1001 3600
TTL demo:cart:1001
~~~

Khi muốn thời hạn tính từ lần hoạt động cuối, ứng dụng phải có quy tắc cập nhật TTL theo sự kiện hoạt động thực sự. Không phải bất kỳ lệnh **HSET** nào cũng tự kéo dài TTL.

Nếu cần lưu một object có cấu trúc lồng nhau sâu và cập nhật theo đường dẫn JSON, có thể dùng khả năng JSON của hệ đang triển khai, nếu được hỗ trợ và cấu hình. Với Redis, các lệnh JSON như **JSON.SET** thuộc tính năng RedisJSON/Redis Stack hoặc phân phối hỗ trợ tương ứng; không nên giả định luôn tồn tại trong mọi Redis server.

## 8. Redis List, Set, Sorted Set, Stream: cấu trúc biểu diễn thao tác

Câu hỏi hữu ích không chỉ là “đối tượng này là danh sách hay tập hợp trong Java?”, mà còn là **ứng dụng muốn làm thao tác gì phía database**.

| Cấu trúc | Tính chất | Thao tác phù hợp | Ví dụ |
|---|---|---|---|
| **List** | Các phần tử theo thứ tự, có thể trùng | Đẩy/lấy đầu hoặc cuối, đọc theo khoảng | Danh sách công việc đơn giản |
| **Set** | Thành viên duy nhất, không cam kết thứ tự hiển thị | Thêm/bỏ, kiểm tra thành viên, phép tập hợp | Tập tag, user đã tham gia |
| **Sorted Set** | Thành viên duy nhất có score, đọc theo thứ tự score | Bảng xếp hạng, top N, ngưỡng điểm | Leaderboard |
| **Stream** | Chuỗi entry có ID, hỗ trợ mô hình đọc tiêu thụ sự kiện | Ghi event, đọc theo ID, consumer group | Dòng sự kiện cần xử lý |
| **Hash** | Nhiều field–value thuộc cùng key | Đọc/cập nhật field, tăng số ở field | Giỏ hàng, bộ thuộc tính phẳng |

### List

~~~redis
LPUSH demo:queue:email "job-1"
LPUSH demo:queue:email "job-2"
LRANGE demo:queue:email 0 -1
RPOP demo:queue:email
~~~

**LPUSH** thêm vào đầu, **RPOP** lấy ở cuối; với ví dụ này, phần tử được đưa vào trước (**job-1**) sẽ được lấy ra trước. Tuy nhiên, dùng List làm hàng đợi sản xuất còn cần xử lý acknowledgment, retry, crash của consumer và các đảm bảo xử lý phù hợp; thao tác pop trực tiếp có thể làm mất job nếu consumer chết sau khi lấy.

### Set

~~~redis
SADD demo:tags:product:42 "java" "nosql" "backend"
SADD demo:tags:product:42 "java"
SISMEMBER demo:tags:product:42 "java"
SMEMBERS demo:tags:product:42
~~~

Thêm **java** lần hai không tạo hai thành viên giống nhau. **SMEMBERS** không có cam kết trả về theo thứ tự chèn; nếu giao diện cần thứ tự cố định thì phải có quy tắc sắp xếp khác.

### Sorted Set

~~~redis
ZADD demo:leaderboard 98 "user:7" 135 "user:9" 102 "user:3"
ZREVRANGE demo:leaderboard 0 2 WITHSCORES
ZINCRBY demo:leaderboard 10 "user:7"
~~~

Thành viên có score cao đứng đầu khi dùng thứ tự giảm. Đây là thao tác native thuận lợi cho bảng xếp hạng; nếu chỉ lưu toàn bộ leaderboard thành JSON String, mỗi lần thay điểm sẽ phải giải quyết đọc/ghi lại blob hoặc xây thêm cơ chế khác.

### Stream

~~~redis
XADD demo:orders:events * type "ORDER_PAID" orderId "o-101"
XRANGE demo:orders:events - +
~~~

Mỗi entry trong Redis Stream có ID và các field. Stream hữu ích cho luồng sự kiện, nhưng không đồng nghĩa với một nền tảng hàng đợi bền vững đầy đủ trong mọi cấu hình. Việc giữ lịch sử, xử lý lại, giới hạn stream, persistence và consumer group vẫn cần thiết kế riêng.

## 9. DynamoDB: key–value cũng có thể có Map, List, Number và Binary

DynamoDB là một ví dụ quan trọng vì nó hỗ trợ cả **key–value** và **document data model**. Mỗi item được xác định bằng primary key; khóa có thể gồm **partition key** hoặc **partition key + sort key**. Những attribute còn lại mang kiểu dữ liệu và có thể bao gồm Map hoặc List.

Ví dụ item theo dạng biểu diễn JSON kiểu DynamoDB API:

~~~json
{
  "PK": { "S": "USER#1001" },
  "SK": { "S": "CART" },
  "items": {
    "M": {
      "sku:pen": { "N": "2" },
      "sku:book": { "N": "1" }
    }
  },
  "active": { "BOOL": true },
  "notes": { "NULL": true },
  "updatedAt": { "S": "2026-11-14T09:00:00Z" }
}
~~~

Ở đây:

- **S** là String.
- **N** là Number; API mã hóa giá trị số dưới dạng chuỗi ký tự thập phân, nhưng ngữ nghĩa của attribute vẫn là số.
- **M** là Map, có thể chứa các attribute con.
- **L** là List.
- **B** là Binary.
- Ngoài ra còn có các kiểu khác như **BOOL**, **NULL** và các set có kiểu tương ứng.

Khác với Redis String chứa JSON nguyên khối, DynamoDB **hiểu kiểu các attribute** và cung cấp những thao tác đọc/cập nhật ở mức attribute thông qua API tương ứng. Tuy nhiên, không được coi item là document tự do có thể tìm mọi field với hiệu năng ngang nhau. Việc truy vấn hiệu quả vẫn phụ thuộc vào **primary key**, **sort key**, **secondary index**, điều kiện truy cập và mô hình phân vùng.

Nếu cần cập nhật số lượng một SKU, DynamoDB có thể dùng thao tác cập nhật attribute với biểu thức và điều kiện phù hợp; cách viết khác Redis HINCRBY. Không nên cố dùng cùng một chuỗi lệnh cho hai database chỉ vì cùng lưu giỏ hàng.

## 10. Memcached, etcd, RocksDB: khi cấu trúc nằm chủ yếu ở phía ứng dụng

### Memcached

Memcached thường được dùng làm cache theo key. Nó lưu payload cùng thông tin quản lý, nhưng không tự hiểu JSON như cấu trúc field–value. Một value có thể là chuỗi hoặc bytes đã được client serialize; client quyết định cách giải mã.

Với key **cache:product:42**, ứng dụng có thể lưu JSON đầy đủ để lấy lại qua một phép GET. Nếu chỉ đổi **price**, cách phổ biến là tạo lại payload và ghi giá trị mới. Các thao tác tăng/giảm số và **CAS** (compare-and-swap) tồn tại, nhưng chúng không biến Memcached thành một document database có truy vấn theo trường.

Memcached là cache, nên phải thiết kế cách xử lý **cache miss**, hết hạn, eviction và làm mới từ nguồn dữ liệu chính. Nếu một key bị đẩy khỏi cache để giải phóng bộ nhớ, ứng dụng không nên mất dữ liệu nghiệp vụ mà chỉ còn được giữ ở cache.

### etcd

etcd v3 cung cấp key/value dạng byte và các khái niệm revision, lease, watch. Giá trị có thể chứa nội dung cấu hình JSON hoặc text, nhưng một thao tác cập nhật có điều kiện dựa trên revision không có nghĩa etcd hiểu cấu trúc JSON bên trong.

Ví dụ dịch vụ có key **/config/payment/timeout-ms** lưu nội dung **5000**. Ứng dụng có thể watch để nhận thay đổi và dùng transaction có điều kiện để tránh ghi đè cấu hình cũ. Đối với cấu hình/phối hợp dịch vụ, khả năng **watch và phiên bản** thường quan trọng hơn việc engine hỗ trợ List hoặc Sorted Set.

### RocksDB

RocksDB là một engine key–value nhúng. Ứng dụng lưu key và value dạng byte, đọc theo key hoặc duyệt key trong thứ tự của comparator. Nếu muốn lưu đơn hàng có nhiều mặt hàng, ứng dụng phải quyết định:

- Ghi cả đơn trong một value đã serialize.
- Ghi nhiều key như **order:101:header**, **order:101:item:1**, **order:101:item:2**.
- Chọn quy tắc encode key sao cho quét theo prefix có thứ tự đúng.
- Xác định dùng batch/transaction/locking nào khi cần cập nhật nhiều key.

Vì đây là engine nhúng, không nên mặc định RocksDB có các đặc tính của một dịch vụ database phân tán như tự quản lý shard, replica hay endpoint mạng. Những khả năng đó cần đến tầng hệ thống triển khai xung quanh nó.

## 11. Chọn biểu diễn từ thao tác cần thực hiện

Xét bốn yêu cầu nghiệp vụ. Mỗi yêu cầu dẫn đến một quyết định khác về value.

| Yêu cầu | Biểu diễn ứng viên | Vì sao |
|---|---|---|
| Đọc toàn bộ cấu hình theo một key, thay đổi rất ít | String JSON hoặc serialized bytes | Một lần đọc đơn giản, dễ cache, cập nhật nguyên khối chấp nhận được |
| Tăng số lượt xem liên tục | Giá trị số mà hệ hỗ trợ tăng nguyên tử | Tránh vòng GET rồi SET gây mất cập nhật |
| Thay đổi số lượng từng SKU trong giỏ | Redis Hash hoặc attributes có thao tác cập nhật tương đương | Thay một phần nhỏ mà không ghi lại toàn value |
| Trả top 10 người có điểm cao | Redis Sorted Set hoặc read model/index tương ứng | Hệ có thể duy trì thứ tự theo score |

### Ví dụ: cùng một giỏ hàng, hai cách lưu

**Cách A — một Redis String JSON:**

~~~redis
SET demo:cart:json:1001 "{\"sku:pen\":2,\"sku:book\":1}"
GET demo:cart:json:1001
~~~

Ứng dụng có thể deserialize thành Map và thao tác dễ dàng trong bộ nhớ. Nhưng hai luồng cùng đọc giỏ rồi sửa SKU khác nhau có thể ghi đè thay đổi của nhau nếu chỉ dùng **GET → sửa local → SET**.

**Cách B — một Redis Hash:**

~~~redis
HSET demo:cart:hash:1001 sku:pen 2 sku:book 1
HINCRBY demo:cart:hash:1001 sku:pen 1
HGET demo:cart:hash:1001 sku:book
~~~

Tăng số lượng **sku:pen** không cần đọc lại và ghi cả **sku:book**. Tuy nhiên, mô hình này cần thêm quy tắc xử lý xóa SKU khi số lượng về 0, ngăn số lượng âm, áp dụng giá và khuyến mãi, thời hạn hết hiệu lực, và đồng bộ với dữ liệu đơn hàng đã chốt.

Không có kết luận “Hash luôn tốt hơn JSON”. Nếu màn hình luôn đọc toàn bộ giỏ và thường thay tất cả các trường cùng lúc, một value serialize vẫn có thể phù hợp. Nếu cần sửa từng field với tần suất lớn và concurrent updates, cấu trúc native thường đáng cân nhắc hơn.

## 12. Giá trị có cấu trúc không tự giải quyết tính nhất quán

Giả sử hai yêu cầu cùng tăng số lượng mặt hàng. Với đường:

~~~text
Client A: GET -> thấy 2
Client B: GET -> thấy 2
Client A: SET 3
Client B: SET 3

Mong muốn: 4
Thực tế với vòng đọc–ghi thiếu bảo vệ: 3
~~~

Kết quả sai đến từ **read–modify–write không có bảo vệ đồng thời**, không phải vì số nguyên được lưu dưới dạng ký tự.

Nếu hệ có lệnh tăng nguyên tử ở đúng phạm vi:

~~~redis
SET demo:counter:atomic 2
INCR demo:counter:atomic
INCR demo:counter:atomic
GET demo:counter:atomic
~~~

Giá trị cuối là **4** khi hai lệnh tăng đã được thực thi thành công theo mô hình Redis tương ứng. Điều đó không có nghĩa mọi thay đổi trải qua nhiều key cũng tự động nguyên tử. Ví dụ “trừ tồn kho và tăng số lượng giỏ” cần xác định ranh giới transaction hoặc quy trình nhất quán riêng.

Các cơ chế cần tìm hiểu theo sản phẩm:

- **Redis:** lệnh nguyên tử trên cấu trúc phù hợp, transaction với **MULTI/EXEC**, optimistic locking với **WATCH**, script/Function khi cần kiểm tra và cập nhật theo một đơn vị xử lý.
- **Memcached:** **CAS** để phát hiện value đã thay đổi trước khi ghi lại.
- **etcd:** transaction có điều kiện dựa trên revision/version.
- **DynamoDB:** conditional write, update expression và transaction khi cần nhiều item trong phạm vi được hỗ trợ.
- **RocksDB:** batch và các cơ chế transaction/locking theo cách tích hợp của ứng dụng, không tự suy ra tính nguyên tử nhiều thao tác độc lập.

Mỗi giải pháp có phạm vi và giới hạn riêng. Khi thiết kế, nên viết rõ **bất biến** cần bảo vệ, ví dụ “số lượng không âm”, “chỉ chủ sở hữu sửa giỏ”, “hai lần retry không tính tiền hai lần”, rồi chọn API đủ để thực thi bất biến đó.

## 13. Key được đặt thế nào cũng ảnh hưởng đến value

Một mô hình key–value tốt phải mô tả được **đường truy cập từ đầu vào đến key**:

~~~text
session:{sessionId}
cart:{userId}
product-cache:{productId}
rate-limit:{tenantId}:{windowId}
leaderboard:{date}
~~~

Những quy tắc quan trọng:

1. **Key cần xác định được từ đầu vào của thao tác.** Nếu API yêu cầu tìm tất cả giỏ hàng theo thành phố nhưng key chỉ chứa userId, phải có index/read model hoặc một cơ chế khác; GET theo key không giải quyết truy vấn đó.
2. **Namespace ngăn va chạm kiểu.** Dùng **cart:1001** cho Hash và **session:1001** cho String rõ ràng hơn việc dùng chung một key cho các thực thể khác nhau.
3. **Không nhét dữ liệu nhạy cảm trực tiếp vào tên key** khi có thể dùng định danh nội bộ; key thường xuất hiện trong log, metrics, snapshot hoặc công cụ chẩn đoán.
4. **Kiểm soát key quá lớn hoặc quá nhiều key.** Tên key dài, số lượng key khổng lồ hoặc value vượt mục tiêu kích thước đều tăng chi phí bộ nhớ/lưu trữ.
5. **Chú ý hot key.** Một bảng xếp hạng toàn hệ thống hoặc bộ đếm tập trung có thể nhận phần lớn truy cập vào một key, tạo điểm nghẽn dù cluster còn tài nguyên.
6. **Thiết kế cho phân vùng.** Với hệ phân tán, cách bố trí partition key/shard key có thể quyết định nơi dữ liệu được lưu và hiệu quả của truy vấn nhiều key.

Cấu trúc value và sơ đồ key phải được chọn cùng nhau. Tách một giỏ thành nhiều key **cart:1001:sku:pen**, **cart:1001:sku:book** giúp cập nhật từng SKU, nhưng đặt ra câu hỏi cách liệt kê tất cả SKU của giỏ, xóa toàn bộ giỏ và bảo đảm các thao tác nhiều key nhất quán. Một Hash duy nhất giúp liệt kê field nhưng cũng có giới hạn riêng khi giá trị tăng rất lớn.

## 14. TTL, xóa và giới hạn kích thước thay đổi theo kiểu value

Một value có thể phù hợp về mặt dữ liệu nhưng không phù hợp về vòng đời:

| Dữ liệu | Kiểu đề xuất ban đầu | Câu hỏi vòng đời |
|---|---|---|
| Session đăng nhập | String JSON hoặc Hash | Hết hạn theo thời gian nào? Có thu hồi ngay khi logout không? |
| Cache kết quả truy vấn | String/bytes | TTL bao lâu? Có nguồn chính để dựng lại không? |
| Giỏ hàng | Hash hoặc document | Có xóa sau thời gian không hoạt động? Có cần bảo toàn khi người dùng đổi thiết bị không? |
| Leaderboard theo ngày | Sorted Set | Ngày cũ được archive hay xóa? |
| Event stream | Stream | Giới hạn giữ entry, xử lý consumer chậm và retry thế nào? |

Redis có thể gắn TTL cho key thuộc nhiều loại, nhưng **không nên mặc định mọi hệ đều có TTL cùng độ chính xác hoặc cùng ngữ nghĩa**. DynamoDB TTL dọn item không đồng bộ; etcd có lease; Memcached có cơ chế expiration; engine nhúng có thể yêu cầu ứng dụng tự quản lý vòng đời. TTL không thay thế yêu cầu xóa ở cache, backup, kho dữ liệu thứ cấp hoặc dữ liệu đã xuất.

Cũng cần đánh giá kích thước value:

- **Một JSON blob lớn:** mỗi lần cập nhật có thể phải truyền và ghi lại nhiều byte.
- **Một Hash rất nhiều field:** thao tác đơn lẻ tiện nhưng một key có thể trở thành vùng dữ liệu hoặc hotspot quá lớn.
- **Một List/Stream tăng liên tục:** phải có chính sách giới hạn, dọn dữ liệu cũ và bảo vệ consumer chậm.
- **Một tập ảnh/byte lớn:** cần đánh giá chi phí RAM, disk, replication và network trước khi dùng KV làm kho nội dung chính.

Chọn native type không miễn trừ bài toán retention, access control, backup và quan sát thực tế.

## 15. Nhận diện các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Key–value chỉ lưu string.” | Có hệ lưu opaque bytes, có hệ cung cấp String binary-safe hoặc nhiều cấu trúc native. |
| “Tôi lưu JSON nên database hiểu các field.” | JSON có thể chỉ là payload string/bytes; cần API hỗ trợ cấu trúc mới thao tác được từng field. |
| “Redis String là văn bản UTF-8.” | Redis String binary-safe; cách decode phụ thuộc ứng dụng. |
| “Số 42 trong chuỗi là kiểu Number.” | Ngữ nghĩa phụ thuộc hệ và API; Redis String có thể được lệnh INCR diễn giải như số nguyên, còn DynamoDB có kiểu Number riêng. |
| “Hash luôn tốt hơn JSON.” | Hash thuận lợi cho nhiều cập nhật field độc lập; JSON blob có thể đơn giản hơn khi đọc/ghi nguyên đối tượng. |
| “Dùng native List là đủ làm hàng đợi tin cậy.” | Còn cần thiết kế retry, acknowledgment, persistence và xử lý consumer lỗi. |
| “Tất cả value đều cập nhật nguyên tử theo cùng cách.” | Tính nguyên tử phụ thuộc loại thao tác và phạm vi mỗi database bảo đảm. |
| “GET theo key đủ để phục vụ mọi màn hình.” | Truy vấn theo thuộc tính, theo thời gian hoặc xếp hạng cần key design, index hoặc read model phù hợp. |
| “TTL xóa đúng tức thì và xóa mọi bản sao.” | TTL và phạm vi xóa thay đổi theo hệ; backup, dữ liệu dẫn xuất và xóa vật lý cần xử lý riêng. |

## 16. Quy trình lựa chọn giá trị cho một yêu cầu mới

Khi thiết kế một tính năng key–value, hãy đi từ hành vi thực tế của ứng dụng:

**Bước 1 — Xác định dữ liệu và key.** Ví dụ “đọc giỏ hàng của user 1001” cho phép suy ra **cart:1001** từ userId; “tìm 10 sản phẩm bán chạy nhất tháng này” cần đường truy cập khác.

**Bước 2 — Liệt kê thao tác.** Đọc nguyên value, đọc một field, tăng số, thêm phần tử không trùng, lấy top N, ghi sự kiện hay quét theo prefix?

**Bước 3 — Đối chiếu API database.** Hệ cho phép blob bytes, String, Map/Hash, List, Set, Sorted Set, Stream hay typed attributes? Lệnh nào thực hiện thao tác ngay tại database?

**Bước 4 — Chọn serialization nếu cần.** Chốt charset/format/schemaVersion, phương án decode dữ liệu cũ và cách xử lý byte không hợp lệ.

**Bước 5 — Chốt bất biến đồng thời.** Một giá trị được cập nhật bởi bao nhiêu client? Có cần CAS, lệnh tăng nguyên tử, transaction hoặc retry idempotent không?

**Bước 6 — Đánh giá tải và vòng đời.** Kích thước value, tốc độ ghi, hot key, TTL, eviction, persistence, giới hạn lưu trữ và đường khôi phục.

**Bước 7 — Xác định bằng chứng quan sát.** Đọc lại đúng type/value, đo lượng byte, số lần gọi, độ trễ, xung đột khi cập nhật và kết quả khi key hết hạn.

~~~text
Yêu cầu nghiệp vụ
      |
      v
Cần thao tác gì với value?
      |
      +--> Đọc/ghi toàn object ----------> JSON/Protobuf/bytes/String
      |
      +--> Tăng một số ------------------> Counter/Number phù hợp
      |
      +--> Sửa field độc lập ------------> Hash/Map/Update attribute
      |
      +--> Thành viên duy nhất ----------> Set
      |
      +--> Xếp hạng theo điểm -----------> Sorted Set hoặc index/read model
      |
      +--> Dòng sự kiện theo ID ---------> Stream/log phù hợp
      |
      v
Kiểm tra database hỗ trợ thực tế
      |
      v
Chốt key, encoding, đồng thời, TTL và quan sát
~~~

## 17. Thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Phân biệt String với số

Cho Redis String có nội dung **"15"**, **"15.5"** và **"{\"count\":15}"** ở ba key riêng biệt. Với mỗi key, hãy dự đoán kết quả của **TYPE** và điều gì xảy ra nếu dùng **INCR**. Giải thích vì sao cùng một kiểu Redis nhưng lệnh tăng lại cho kết quả khác.

### Bài tập 2 — Chọn kiểu cho giỏ hàng

Một giỏ hàng trung bình có 20 SKU. Hệ thống thường xuyên tăng/giảm số lượng riêng từng SKU từ nhiều thiết bị, đôi khi cần trả toàn bộ giỏ. Hãy so sánh Redis String JSON và Redis Hash theo số thao tác, lượng dữ liệu truyền, nguy cơ lost update, điều kiện số lượng không âm và TTL.

### Bài tập 3 — Byte không phải text

Một dịch vụ lưu ảnh PNG dưới dạng byte rồi cố giải mã thành UTF-8 String, sau đó encode lại và lưu. Hãy chỉ ra vì sao thao tác này có thể làm sai ảnh, và đề xuất cách truyền/giữ binary nguyên vẹn.

### Bài tập 4 — Chọn đúng hệ

Một ứng dụng cần: (a) lưu cờ cấu hình có watch/revision; (b) cache response có thể mất; (c) cập nhật bảng xếp hạng; (d) lưu local key–value trên máy của ứng dụng. Hãy giải thích trường hợp nào phù hợp với khả năng điển hình của etcd, Memcached, Redis Sorted Set và RocksDB. Đừng chỉ chọn theo tên sản phẩm; phải viện dẫn loại value và thao tác cần.

### Bài tập 5 — Schema và triển khai nhiều phiên bản

Ứng dụng cũ ghi JSON **{"name":"An"}**. Phiên bản mới cần thêm **schemaVersion** và **preferences**; trong thời gian triển khai, client cũ và mới cùng hoạt động. Hãy đề xuất quy tắc đọc ngược, ghi dữ liệu mới và tránh làm mất trường mà client cũ không hiểu.

### Bài tập 6 — Quan sát kết quả

Tạo một key String JSON và một key Hash chứa dữ liệu tương đương. Dùng **TYPE**, **GET**, **HGETALL**, một lệnh cập nhật số và TTL để quan sát cách database phản hồi. Ghi lại trường hợp lệnh sai kiểu gây lỗi, và giải thích lỗi đó chứng minh điều gì về API value.

Điểm cần nắm sau bài là: **key–value mô tả cách định vị dữ liệu, còn khả năng của value là hợp đồng cụ thể do từng database cung cấp**. Quyết định lưu byte, chuỗi hay cấu trúc native phải được nối trực tiếp với thao tác nghiệp vụ, định dạng dữ liệu, tính nhất quán, quy mô và hành vi có thể kiểm chứng của hệ thống.

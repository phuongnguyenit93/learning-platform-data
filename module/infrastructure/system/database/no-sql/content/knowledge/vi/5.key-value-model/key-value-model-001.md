# Cấu trúc khóa và giá trị, không gian tên và thao tác cơ bản

Trong **mô hình khóa–giá trị** (*key–value*), một mục dữ liệu được định danh bằng **khóa** (*key*) và gắn với một **giá trị** (*value*). Ý tưởng gần với cấu trúc `Map<K, V>` trong lập trình: khi đã biết khóa, ứng dụng có thể tìm, ghi hoặc xóa dữ liệu tương ứng.

Mô hình đơn giản không có nghĩa thiết kế cũng đơn giản. Chọn khóa thế nào để tránh trùng và dễ mở rộng? Một giá trị nên là chuỗi, JSON hay cấu trúc chuyên biệt? Có thể dùng tiền tố khóa để tạo “thư mục” không? Hai yêu cầu cùng sửa một giá trị có gây mất cập nhật không? Dữ liệu tạm hết hạn ra sao?

Bài học đi từ cách biểu diễn đến cách sử dụng, minh họa phần lớn bằng **Redis**. Redis là một DBMS thường được xếp vào nhóm key–value và cung cấp nhiều cấu trúc dữ liệu cùng lệnh đặc thù. **Mô hình key–value không đồng nghĩa với Redis**: các sản phẩm khác như Amazon DynamoDB, Aerospike hay kho key–value nhúng có API, giới hạn, bảo đảm nhất quán và khả năng truy vấn khác nhau. Khi dùng lệnh Redis, cần hiểu đó là ví dụ triển khai của mô hình.

## 1. Cấu trúc cơ bản của một mục dữ liệu

Ở mức khái niệm:

~~~text
Key                               Value
------------------------------------------------------------------
shop:prod:product:P1001           {"name":"Bút mực","priceVnd":25000}
shop:prod:cart:C42                {"items":[{"sku":"P1001","qty":2}]}
shop:prod:stock:P1001             125
shop:prod:session:S9A3            {"userId":"U42"}
~~~

Mỗi khóa trỏ đến tối đa một giá trị **hiện hành** trong phạm vi không gian khóa mà hệ quản trị quy định. Nhiều khóa có thể chứa những giá trị giống nhau. Một khóa có thể không tồn tại, có thể được tạo, thay đổi hoặc xóa; trong một số hệ nó có thể tự hết hạn.

Sơ đồ truy cập:

~~~text
        Ứng dụng có định danh "cart:C42"
                         │
                         ▼
                   GET(key)
                         │
                         ▼
             Kho dữ liệu key–value
                         │
                    ┌────┴────┐
                    ▼         ▼
                Tìm thấy   Không có
                    │         │
                    ▼         ▼
                 Value     Không có value
~~~

Điểm mạnh quan trọng là **đọc theo khóa đã biết**. Nhưng câu hỏi “tìm tất cả giỏ hàng có số lượng hơn 10 sản phẩm” không có một khóa cụ thể; không thể mặc định kho key–value sẽ tự hỗ trợ bộ lọc theo mọi trường nằm trong value.

### Key và value có vai trò khác nhau

| Thành phần | Vai trò | Điều cần quyết định |
| --- | --- | --- |
| **Key** | Định danh mục dữ liệu, làm điểm vào chính để truy cập | Duy nhất trong phạm vi nào? Có ổn định không? Được mã hóa ra sao? |
| **Value** | Chứa dữ liệu hoặc cấu trúc cần lưu | Kiểu nào? Đọc/ghi toàn bộ hay từng phần? Cần version/schema không? |
| **Metadata** nếu DBMS hỗ trợ | Thời gian sống, phiên bản, thời điểm cập nhật, v.v. | TTL, bảo đảm, cách quản lý và đọc metadata như thế nào? |

Ví dụ hai khóa `user:42` và `user:042` có thể đại diện cho hai mục khác nhau, mặc dù nghiệp vụ có thể xem `42` và `042` là cùng một ID. Tính nhất quán của **quy tắc tạo khóa** vì vậy ảnh hưởng trực tiếp đến tính đúng đắn của dữ liệu.

## 2. Thiết kế khóa: từ định danh đến mẫu truy cập

Một quy tắc đặt tên phổ biến là ghép các thành phần bằng dấu phân tách, chẳng hạn dấu hai chấm:

~~~text
<app>:<environment>:<entity-type>:<entity-id>[:<sub-resource>]

shop:prod:user:U42:profile
shop:prod:user:U42:preferences
shop:prod:order:O1008
shop:prod:stock:P1001
shop:staging:user:U42:profile
~~~

Mẫu trên chỉ là **quy ước của ứng dụng**, không phải cú pháp bắt buộc của key–value DBMS. Trong Redis, dấu `:` không tạo bảng, thư mục hoặc database con; toàn bộ chuỗi vẫn là tên của một key.

### Chọn thành phần của khóa

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Ứng dụng/dịch vụ | Phân biệt các thành phần sử dụng cùng kho | `shop`, `billing` |
| Môi trường | Hạn chế va chạm giữa test, staging, production khi cùng kho | `dev`, `staging`, `prod` |
| Loại đối tượng | Nhìn được nhóm dữ liệu | `user`, `cart`, `stock` |
| Định danh ổn định | Tìm một đối tượng cụ thể | `U42`, `O1008` |
| Phần dữ liệu con | Tách dữ liệu có vòng đời hoặc cách truy cập khác nhau | `profile`, `settings`, `counter` |
| Tenant (nếu cần) | Phân biệt dữ liệu tổ chức/khách hàng | `tenant:T17` |
| Phiên bản định dạng (nếu cần) | Hỗ trợ quá trình đổi cách lưu | `v2` |

Giả sử hệ thống nhiều tenant có hai tổ chức cùng mã liên hệ `C102`:

~~~text
crm:prod:tenant:T17:contact:C102
crm:prod:tenant:T24:contact:C102
~~~

Hai khóa sẽ khác nhau do tenant khác nhau. Tuy nhiên, **đặt tenant vào key không phải là bảo mật**: ứng dụng và DBMS vẫn cần xác thực, kiểm soát quyền truy cập và ngăn client tự chọn tenant không thuộc quyền của họ.

### Tiêu chí của một key tốt

1. **Định danh duy nhất và ổn định.** Mã ID nên có định dạng chuẩn; tránh dùng thuộc tính dễ thay đổi, như tên hiển thị hoặc email, làm khóa chính nếu không có quy trình thay khóa.
2. **Không nhập nhằng.** Phải thống nhất chữ hoa/thường, số 0 đầu, Unicode, khoảng trắng và cách mã hóa dấu phân tách. Nếu ID có thể chứa `:`, cần encoding hoặc quy tắc escape nhất quán.
3. **Dễ truy cập theo nhu cầu chính.** Nếu ứng dụng chủ yếu đọc giỏ hàng bằng `cartId`, khóa có ID giỏ hàng sẽ dễ truy cập trực tiếp.
4. **Không quá dài.** Mỗi ký tự khóa đều tốn dung lượng; hàng triệu khóa có tiền tố quá dài có thể làm tăng đáng kể chi phí bộ nhớ hoặc lưu trữ.
5. **Không chứa bí mật không cần thiết.** Tên khóa có thể xuất hiện trong công cụ quản trị, chỉ số quan sát hay log; tránh nhúng token, mật khẩu, dữ liệu nhạy cảm.
6. **Có hợp đồng sở hữu.** Dịch vụ nào được tạo, cập nhật, xóa và ai được đọc nhóm khóa này?

Ví dụ:

~~~text
Nên cân nhắc:
user:U42:profile

Khó duy trì khi email thay đổi:
user:an.nguyen@example.com
~~~

Email có thể được sử dụng để **tra cứu thứ cấp**, nhưng không nhất thiết phải là định danh chính. Tương tự, việc đặt trạng thái thường thay đổi vào key, như `order:PAID:O1008`, có thể gây rắc rối khi đơn hàng chuyển sang `REFUNDED`: ứng dụng phải đổi khóa và sửa các tham chiếu/chỉ mục liên quan.

### Key ghép không đồng nghĩa với truy vấn nhiều thuộc tính

Tên `order:customer:U42:2026-10-12:O1008` chứa nhiều thông tin, nhưng kho key–value không nhất thiết có khả năng “lọc tất cả order theo ngày” chỉ bằng việc tên khóa có ngày. Một số hệ có API đọc theo tiền tố hoặc sort key; một số khác chỉ có tra cứu chính xác, scan hay cấu trúc phụ.

Do đó, cần tách bạch **đặt tên dễ hiểu**, **định danh**, **khóa phân vùng** và **đường truy cập hỗ trợ truy vấn**. Đây có thể là bốn vấn đề khác nhau dù cùng được thể hiện trong một chuỗi key.

## 3. Không gian tên (*namespace*) là gì?

**Namespace** giúp tổ chức hoặc phân tách các tập khóa. Trên thực tế có nhiều cấp độ:

| Cấp độ | Ví dụ | Phạm vi thực tế |
| --- | --- | --- |
| Tiền tố ở ứng dụng | `shop:prod:*`, `billing:prod:*` | Quy ước tổ chức tên khóa; không tự tạo cách ly bảo mật |
| Không gian logic do DBMS hỗ trợ | Database, bucket, table hoặc tên miền quản lý dữ liệu tùy sản phẩm | Có cấu trúc, giới hạn và quyền do DBMS quyết định |
| Cụm/instance/triển khai riêng | Redis test riêng với Redis production | Tách hạ tầng rõ ràng hơn, vẫn cần quản lý quyền và cấu hình |

Ví dụ hai dịch vụ có thể vô tình va chạm:

~~~text
Service A: SET user:42 '{"name":"An"}'
Service B: SET user:42 '{"roles":["editor"]}'
~~~

Nếu hai service cùng ghi khóa `user:42`, dữ liệu ghi sau có thể thay thế dữ liệu ghi trước. Quy ước tách nhóm:

~~~text
profile:prod:user:42
authorization:prod:user:42
~~~

### Namespace trong Redis

Tiền tố như `shop:prod:cart:*` là quy ước ứng dụng. Redis độc lập có các logical database chọn bằng `SELECT`, nhưng đó không phải là ranh giới bảo mật tương đương triển khai riêng. Redis Cluster chỉ dùng database số `0`; không thể dựa vào các logical database giống cách dùng trên instance đơn lẻ.

Nếu yêu cầu quan trọng là **cô lập sự cố, tài nguyên hoặc môi trường production**, namespace bằng tiền tố chưa đủ. Cần cân nhắc hạ tầng riêng hoặc các cơ chế quyền/hạn ngạch/giới hạn do nền tảng hỗ trợ.

### Quét khóa theo tiền tố có phải truy vấn theo namespace không?

Trong Redis, `SCAN` cho phép duyệt dần keyspace, có thể lọc theo mẫu:

~~~redis
SCAN 0 MATCH shop:prod:cart:* COUNT 100
~~~

Kết quả trả về cursor cho lượt tiếp theo và danh sách khóa tìm được. Để duyệt trọn, cần lặp với cursor mới cho đến khi nhận `0`. `COUNT` là gợi ý mức độ công việc, không phải số phần tử bảo đảm trả về. Trong lúc khóa thêm, xóa hay hết hạn, kết quả quét có thể lặp hoặc khác nhau giữa các lượt; client cần xử lý hợp lý.

`SCAN` hữu ích cho công việc quản trị hoặc duyệt từng phần, nhưng **không thay cho một index được thiết kế phục vụ truy vấn nghiệp vụ**. Lệnh `KEYS` quét toàn bộ keyspace trong một lần và có thể chặn hoạt động trong Redis khi số lượng khóa lớn; tránh dùng nó trên hệ thống production nhiều dữ liệu.

## 4. Thiết kế value: chuỗi, JSON, bytes hay cấu trúc chuyên biệt?

Trong mô hình key–value thuần túy, value có thể được xem như một chuỗi bytes mà ứng dụng tự giải mã. Tuy nhiên, một DBMS key–value có thể hiểu thêm các kiểu dữ liệu và cho phép thao tác từng phần.

Ví dụ value dạng JSON:

~~~json
{
  "schemaVersion": 1,
  "userId": "U42",
  "displayName": "An",
  "preferences": {
    "language": "vi",
    "theme": "dark"
  }
}
~~~

Nếu lưu JSON trong **Redis string**, lệnh `GET` trả về chuỗi đã lưu; Redis không mặc định phân tích cấu trúc đó để cho truy vấn tùy ý theo `preferences.language`. Khi muốn cập nhật một trường, ứng dụng có thể phải đọc, parse, sửa, serialize và ghi lại cả chuỗi, trừ khi dùng kiểu dữ liệu/khả năng mở rộng phù hợp.

| Cách lưu value | Phù hợp khi | Đánh đổi |
| --- | --- | --- |
| String hoặc số dạng chuỗi | Giá trị đơn, mã trạng thái, bộ đếm | Cần thống nhất encoding và kiểu; không có nhiều trường |
| JSON serialize | Đọc trọn đối tượng, cấu trúc lồng nhau | Cập nhật một trường có thể phải ghi lại cả chuỗi |
| Binary, Protobuf, MessagePack | Tối ưu kích thước hoặc hợp đồng định dạng | Cần codec và chiến lược tương thích phiên bản |
| Hash của Redis | Trường đơn giản, cập nhật từng trường | Khác JSON lồng nhau; cú pháp và giới hạn do Redis quy định |
| List, set, sorted set, stream trong Redis | Danh sách, tập, thứ tự, log/sự kiện | Không phải mọi kho key–value đều có |

### Một khóa lớn hay nhiều khóa nhỏ?

Giả sử hồ sơ người dùng gồm tên, thành phố và lượt đăng nhập:

~~~text
Phương án A — một value:
user:U42 → {"name":"An","city":"Da Nang","loginCount":17}

Phương án B — ba khóa:
user:U42:name       → "An"
user:U42:city       → "Da Nang"
user:U42:loginCount → "17"
~~~

Phương án A đọc toàn bộ hồ sơ đơn giản hơn. Phương án B cho phép truy cập từng giá trị nhưng tạo nhiều khóa, tăng số lần gọi và có thể dẫn đến dữ liệu không đồng bộ nếu phải cập nhật nhiều khóa cùng lúc.

Trong Redis có thể dùng **hash** như một lựa chọn khác:

~~~redis
HSET shop:prod:user:U42:profile name "An" city "Da Nang" loginCount 17
HGET shop:prod:user:U42:profile city
HINCRBY shop:prod:user:U42:profile loginCount 1
HGETALL shop:prod:user:U42:profile
~~~

Các lệnh Redis hash thao tác trên từng trường trong một key. Mỗi lựa chọn tổ chức value nên được đánh giá theo **đơn vị đọc, đơn vị ghi, mức cạnh tranh khi cập nhật và dung lượng**.

### Schema của value vẫn quan trọng

Một kho key–value không nhất thiết áp đặt cấu trúc value, nhưng ứng dụng vẫn phải quy định:

- Những trường nào bắt buộc, kiểu dữ liệu và giá trị hợp lệ.
- Cách phân biệt giá trị bị thiếu, `null`, rỗng hoặc sai định dạng.
- Phiên bản payload và cách client cũ xử lý payload mới.
- Dữ liệu nào là nguồn chính, dữ liệu nào có thể dựng lại.
- Quy tắc mã hóa và giải mã; không giả định bytes có thể luôn được đọc như UTF-8.

Ví dụ `schemaVersion` trong JSON giúp ứng dụng nhận biết cách diễn giải, nhưng **chỉ thêm trường version không tự động thực hiện migration**. Mỗi consumer vẫn phải hiểu phiên bản nó có thể đọc.

## 5. Các phép toán cơ bản: tạo, đọc, sửa, xóa

Các thao tác khái niệm thường gồm:

| Phép toán | Ý nghĩa | Lệnh Redis minh họa |
| --- | --- | --- |
| `put(key, value)` | Tạo hoặc ghi giá trị, tùy API có thể ghi đè | `SET key value` |
| `get(key)` | Đọc theo key | `GET key` |
| `exists(key)` | Kiểm tra key có tồn tại | `EXISTS key` |
| `delete(key)` | Xóa mục dữ liệu | `DEL key` |
| `putIfAbsent` | Tạo khi key chưa có | `SET key value NX` |
| `putIfPresent` | Ghi khi key có sẵn | `SET key value XX` |
| `expire` | Đặt thời gian sống | `EXPIRE key seconds` |
| `ttl` | Đọc thời gian sống còn lại | `TTL key` |
| `increment` | Tăng bộ đếm nguyên tử theo khả năng DBMS | `INCR key` |

Đây là bảng đối chiếu khái niệm với **Redis**, không khẳng định mọi hệ key–value đều hỗ trợ TTL, bộ đếm, thao tác điều kiện hoặc cùng một loại transaction.

### 5.1. CRUD trong Redis

~~~redis
SET demo:prod:product:P1001 "But muc"
GET demo:prod:product:P1001
EXISTS demo:prod:product:P1001

SET demo:prod:product:P1001 "But bi"
GET demo:prod:product:P1001

DEL demo:prod:product:P1001
GET demo:prod:product:P1001
~~~

Trong ví dụ:

1. `SET` tạo giá trị dưới khóa `demo:prod:product:P1001`.
2. `GET` đọc giá trị theo key; `EXISTS` với một key trả về `1` nếu tồn tại, `0` nếu không.
3. Lệnh `SET` thứ hai **ghi đè** giá trị cũ.
4. `DEL` xóa khóa; sau đó `GET` nhận kết quả không tồn tại, thường hiển thị là `(nil)` trong Redis CLI.

Ghi đè có thể phù hợp cho cache, nhưng với dữ liệu đơn hàng hoặc trạng thái chịu ràng buộc, ứng dụng thường cần logic kiểm tra trước khi cho phép thay đổi.

### 5.2. Tạo và ghi có điều kiện

~~~redis
# Chỉ tạo giỏ nếu khóa chưa tồn tại.
SET demo:prod:cart:C42 '{"items":[]}' NX

# Chỉ sửa giỏ nếu khóa đã tồn tại.
SET demo:prod:cart:C42 '{"items":[{"sku":"P1001","qty":2}]}' XX
~~~

- **NX:** chỉ ghi khi key chưa có.
- **XX:** chỉ ghi khi key đã có.

Hai tùy chọn này tránh một số cuộc đua kiểu “kiểm tra key rồi ghi”, vì điều kiện được kiểm tra ngay khi thực hiện lệnh. Tuy nhiên, `XX` **không phải** compare-and-set theo phiên bản: hai client cùng đọc một value cũ rồi `SET ... XX` vẫn có thể ghi đè lẫn nhau. Khi cần chống mất cập nhật, phải dùng thao tác nguyên tử thích hợp, điều kiện theo phiên bản hoặc transaction/script của DBMS.

### 5.3. Thời gian sống và hết hạn — TTL

Một số dữ liệu như cache, phiên đăng nhập, mã tạm, quota theo cửa sổ không cần tồn tại mãi. Redis cho phép đặt TTL:

~~~redis
# Tạo phiên có thời gian sống 30 phút.
SET demo:prod:session:S9A3 '{"userId":"U42"}' EX 1800

# Xem số giây còn lại.
TTL demo:prod:session:S9A3

# Đổi thời hạn thành 10 phút tính từ hiện tại.
EXPIRE demo:prod:session:S9A3 600
TTL demo:prod:session:S9A3

# Xóa phiên ngay khi logout.
DEL demo:prod:session:S9A3
~~~

Đối với `TTL key` trong Redis:

| Giá trị trả về | Diễn giải |
| --- | --- |
| Số nguyên không âm | Số giây còn lại tại thời điểm gọi |
| `-1` | Khóa có tồn tại nhưng không có thời hạn hết hạn |
| `-2` | Khóa không tồn tại |

**Chi tiết dễ sai:** trong Redis, `SET` ghi đè một khóa có TTL thường **xóa TTL cũ**, trừ khi sử dụng tùy chọn phù hợp như `KEEPTTL`. Nếu ứng dụng làm mới giá trị session và quên thời hạn, session có thể tồn tại lâu hơn dự kiến. Khi muốn *sliding expiration*, cần xác định thế nào là “hoạt động” và gia hạn TTL tương ứng; chỉ đặt TTL khi tạo biểu diễn *hết hạn tính từ lúc tạo*.

Không nên đặt TTL cho dữ liệu là **nguồn có thẩm quyền** của nghiệp vụ nếu việc tự hết hạn là không hợp lệ. TTL là một cơ chế vòng đời, không phải giải pháp thay thế chính sách lưu giữ/backup/khôi phục.

### 5.4. Bộ đếm nguyên tử và vấn đề đọc–ghi

~~~redis
SET demo:prod:views:P1001 0
INCR demo:prod:views:P1001
INCRBY demo:prod:views:P1001 5
GET demo:prod:views:P1001
~~~

Trong Redis, `INCR`/`INCRBY` thao tác nguyên tử lên giá trị số nguyên của một key, tránh trường hợp:

~~~text
Client A: GET counter -> 10
Client B: GET counter -> 10
Client A: SET counter 11
Client B: SET counter 11

Kết quả: mất một lần tăng.
~~~

Một lệnh tăng nguyên tử theo key giúp xử lý bộ đếm đơn giản. Nhưng **không tự giải quyết giao dịch nhiều khóa**, không bảo đảm request không bị xử lý hai lần và không mặc định đặt TTL. Đối với số liệu tài chính hay tài nguyên chịu ràng buộc nghiêm ngặt, phải xem phạm vi bảo đảm nhất quán, độ bền và logic nghiệp vụ.

### 5.5. Đọc/ghi nhiều khóa

Redis có `MGET` và `MSET`:

~~~redis
MGET demo:prod:stock:P1001 demo:prod:stock:P1002
MSET demo:prod:stock:P1001 125 demo:prod:stock:P1002 40
~~~

Nhóm thao tác có thể giảm số lượt gọi mạng. Tuy nhiên, API nhiều khóa không phải đặc tính đồng nhất của mọi DBMS. Trong **Redis Cluster**, nhiều lệnh nhiều khóa chịu giới hạn cùng hash slot; không thể mặc định mọi tập khóa tùy ý đều xử lý như instance Redis độc lập. Ngoài ra, lệnh nhiều khóa không thay thế việc đánh giá đúng đơn vị dữ liệu cần ghi và các điều kiện nghiệp vụ.

## 6. Những kiểu value và thao tác khác trong Redis

Redis cho phép nhiều cấu trúc dữ liệu được truy cập theo key:

| Kiểu | Lệnh ví dụ | Trường hợp sử dụng |
| --- | --- | --- |
| **String** | `SET`, `GET`, `INCR` | Chuỗi, bytes, số đếm, JSON serialize |
| **Hash** | `HSET`, `HGET`, `HGETALL` | Hồ sơ nhiều trường |
| **List** | `LPUSH`, `LRANGE` | Danh sách theo thứ tự vị trí |
| **Set** | `SADD`, `SISMEMBER`, `SMEMBERS` | Tập phần tử không trùng |
| **Sorted set** | `ZADD`, `ZRANGE` | Phần tử có score và thứ tự |
| **Stream** | `XADD`, `XREAD` | Dòng bản ghi/sự kiện có ID |

Ví dụ các thao tác:

~~~redis
# Hash: một số trường hồ sơ.
HSET demo:prod:user:U42:profile name "An" city "Da Nang"
HGET demo:prod:user:U42:profile city

# Set: danh sách ID duy nhất.
SADD demo:prod:members:premium U42 U77
SISMEMBER demo:prod:members:premium U42

# Sorted set: bảng điểm.
ZADD demo:prod:leaderboard 120 U42 95 U77
ZRANGE demo:prod:leaderboard 0 -1 WITHSCORES

# List: mã công việc theo thứ tự.
LPUSH demo:prod:tasks:pending T101 T102
LRANGE demo:prod:tasks:pending 0 -1
~~~

Một key chứa hash không thể được đọc bằng `GET` như string; Redis sẽ báo lỗi kiểu khi lệnh không tương thích. Có thể dùng `TYPE key` để biết kiểu đang gắn với một khóa. Các khả năng này là của **Redis**, không phải các thao tác bắt buộc của mọi kho key–value.

## 7. Tìm theo value: cần đường truy cập bổ sung

Giả sử hồ sơ được lưu:

~~~text
demo:prod:user:U42 -> {"name":"An","city":"Da Nang"}
demo:prod:user:U77 -> {"name":"Binh","city":"Ha Noi"}
demo:prod:user:U81 -> {"name":"Chi","city":"Da Nang"}
~~~

Tìm `U42` rất dễ vì biết key. Nhưng yêu cầu “tìm tất cả user ở Đà Nẵng” là **truy vấn theo thuộc tính value**, không có key chính xác. Những hướng thường gặp:

1. **Quét rồi lọc:** dễ viết cho dữ liệu nhỏ hoặc tác vụ quản trị, tốn kém khi số bản ghi lớn.
2. **Duy trì chỉ mục tra cứu ngược:** ví dụ ánh xạ thành phố đến tập ID người dùng.
3. **Chọn DBMS hoặc dịch vụ tìm kiếm hỗ trợ secondary index:** tùy dạng truy vấn, quy mô và giới hạn hệ thống.

Một chỉ mục tra cứu ngược trong Redis có thể là:

~~~text
demo:prod:user-by-city:da-nang -> {U42, U81}
demo:prod:user-by-city:ha-noi  -> {U77}
~~~

Các lệnh:

~~~redis
SADD demo:prod:user-by-city:da-nang U42 U81
SMEMBERS demo:prod:user-by-city:da-nang
~~~

Với kết quả ID, ứng dụng đọc những user tương ứng. Nhưng **chỉ mục phụ là dữ liệu phải duy trì**. Nếu U42 chuyển từ Đà Nẵng đến Hà Nội, cần cập nhật hồ sơ, xóa U42 khỏi tập cũ và thêm vào tập mới. Nếu một thao tác thất bại, chỉ mục có thể sai. Cần cơ chế cập nhật nhất quán, xử lý lỗi, đối soát hoặc tái xây dựng phù hợp.

Tương tự, xóa user hay để user hết hạn không nhất thiết tự xóa ID của người đó khỏi chỉ mục phụ do ứng dụng tạo. Các cấu trúc key–value thường **không có cascade delete theo quan hệ nghiệp vụ** chỉ dựa trên tiền tố hoặc việc một key bị xóa.

## 8. Không gian tên và vòng đời khi nhiều dịch vụ cùng sử dụng

Trong một môi trường dùng chung, nên có hợp đồng cho mỗi nhóm khóa:

~~~text
catalog:prod:product:P1001
checkout:prod:cart:C42
identity:prod:session:S9A3
analytics:prod:views:P1001
~~~

Hợp đồng cần trả lời:

- Dịch vụ nào **sở hữu** dữ liệu và dịch vụ nào được phép ghi/xóa?
- Kiểu value là gì? Có thay từ string thành hash mà client cũ chưa nâng cấp không?
- Mỗi nhóm khóa có TTL bao lâu, và khi nào hết hạn?
- Dữ liệu nào có thể lấy lại từ nguồn chính, dữ liệu nào cần bền vững?
- Ai có thể truy cập namespace? Phân quyền được thực hiện tại đâu?
- Khi xóa một entity, những index, cache và khóa tham chiếu nào cần dọn?

### Phân biệt key, partition key và hash slot

Với một hệ thống phân tán, key ở API có thể ảnh hưởng vị trí lưu dữ liệu, nhưng các cơ chế rất khác nhau:

- Một DBMS có thể hash toàn bộ key để chọn shard.
- Một DBMS có thể phân biệt **partition key** và **sort key**.
- Một DBMS có thể hỗ trợ cơ chế để các key liên quan nằm cùng nơi, phục vụ thao tác nhiều khóa.

Redis Cluster chia không gian khóa thành **hash slot**. Cú pháp hash tag trong cặp ngoặc nhọn có thể tác động cách chọn slot cho những key cần phối hợp. Nhưng gom quá nhiều khóa vào một slot có thể tạo mất cân bằng tải. Vì vậy, tiền tố đẹp mắt không phải bằng chứng rằng dữ liệu phân tán đều hoặc các thao tác nhiều key đều hợp lệ.

### Hot key và key quá lớn

Nếu tất cả request truy cập `demo:prod:views:P1001` với tần suất rất cao, key đó có thể thành điểm nóng. Trong vài trường hợp, có thể phân tán số đếm thành nhiều bucket rồi tổng hợp; đổi lại, việc đọc tổng và bảo đảm chính xác tức thời phức tạp hơn.

Nếu một key chứa JSON nhiều megabyte nhưng client chỉ cần một trường nhỏ, mỗi lượt đọc/ghi toàn bộ value cũng có thể gây lãng phí mạng, bộ nhớ và CPU. Khi đó có thể cân nhắc tách cấu trúc, dùng hash, định nghĩa đơn vị cập nhật nhỏ hơn hoặc chuyển mô hình dữ liệu.

## 9. Ví dụ đầy đủ: quản lý giỏ hàng tạm thời

Yêu cầu:

- Mỗi giỏ hàng có `cartId` duy nhất.
- Thêm mặt hàng, đổi số lượng, xóa mặt hàng.
- Đọc toàn bộ giỏ theo ID.
- Nếu không hoạt động trong một giờ, giỏ hàng có thể hết hạn.

Nếu chỉ lưu `SKU → quantity`, một **Redis hash** có thể phù hợp:

~~~text
Key: demo:prod:cart:C42
Type: hash
Fields:
    P1001 -> 2
    P1002 -> 1
TTL: 3600 seconds
~~~

Thao tác:

~~~redis
# Tạo/cập nhật dữ liệu giỏ.
HSET demo:prod:cart:C42 P1001 2 P1002 1

# Lấy toàn bộ giỏ.
HGETALL demo:prod:cart:C42

# Tăng số lượng P1001 thêm 1.
HINCRBY demo:prod:cart:C42 P1001 1

# Xóa một mặt hàng.
HDEL demo:prod:cart:C42 P1002

# Đặt hoặc gia hạn TTL một giờ.
EXPIRE demo:prod:cart:C42 3600

# Xem TTL còn lại.
TTL demo:prod:cart:C42

# Xóa giỏ sau checkout hoặc hủy.
DEL demo:prod:cart:C42
~~~

**Giới hạn:** `HINCRBY` chỉ thực hiện thao tác số học trên một trường, không tự đảm bảo số lượng dương, không vượt tồn kho hoặc còn hiệu lực theo giá. Quy tắc nghiệp vụ cần được xác thực và cập nhật bằng cơ chế phù hợp. Hơn nữa, `HSET` rồi `EXPIRE` là hai lệnh: nếu ứng dụng lỗi giữa chúng, key có thể tồn tại chưa có TTL. Hệ thống yêu cầu TTL nghiêm ngặt cần dùng giải pháp phối hợp ghi và đặt hạn phù hợp với nền tảng.

Nếu mỗi dòng hàng cần cả giá, khuyến mãi, lựa chọn màu/kích thước và metadata lồng nhau, hash `SKU → quantity` có thể không đủ. Có thể cân nhắc JSON toàn giỏ hoặc một cấu trúc khác, rồi đánh giá lại cách chống cập nhật ghi đè.

### Một lựa chọn JSON

~~~json
{
  "schemaVersion": 1,
  "items": [
    {"sku": "P1001", "quantity": 2, "unitPriceVnd": 25000},
    {"sku": "P1002", "quantity": 1, "unitPriceVnd": 70000}
  ],
  "currency": "VND"
}
~~~

Đọc toàn bộ giỏ thuận tiện, nhưng hai request cùng sửa từng phần của JSON dễ gặp **lost update** nếu cả hai đọc một value cũ rồi cùng ghi đè. Một thao tác ghi có điều kiện theo phiên bản hoặc transaction/script là lựa chọn cần đánh giá khi concurrency có ý nghĩa.

## 10. Những lỗi dễ mắc

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng tên hiển thị hoặc email thay đổi làm khóa chính | Đổi thông tin phải đổi key và tham chiếu | Dùng định danh ổn định |
| Không thống nhất quy tắc tạo key | Trùng, phân mảnh hoặc hai key cho cùng một entity | Chuẩn hóa ID, encoding, tiền tố |
| Coi tiền tố tenant là quyền truy cập | Truy cập chéo dữ liệu khi ứng dụng không kiểm quyền | Áp dụng xác thực, phân quyền và cách ly phù hợp |
| Chứa bí mật trong key | Lộ thông tin qua công cụ, log, giám sát | Dùng ID không nhạy cảm, quản lý secrets riêng |
| Quét toàn bộ keyspace để lọc theo nội dung value | Độ trễ và tải tăng theo kích thước dữ liệu | Thiết kế chỉ mục hoặc kho dữ liệu phù hợp |
| Lưu JSON lớn và ghi đè từ nhiều client | Mất cập nhật và tốn truyền dữ liệu | Chọn giá trị/cấu trúc và cơ chế cập nhật thích hợp |
| Dùng `GET` rồi `SET` cho bộ đếm | Mất lượt tăng khi hai request đồng thời | Dùng phép tăng nguyên tử |
| Không đặt TTL cho dữ liệu tạm | Dữ liệu rác tích lũy | Chính sách hết hạn hoặc dọn định kỳ |
| Đặt TTL cho dữ liệu không được phép mất | Mất bản ghi nghiệp vụ | Phân biệt source of truth với cache |
| Đổi value từ string sang hash mà không quản lý schema | Client cũ gọi sai lệnh hoặc đọc sai | Hợp đồng version/migration |
| Tự tạo chỉ mục phụ nhưng bỏ qua thao tác đổi/xóa | Kết quả tìm kiếm không còn khớp nguồn | Đồng bộ, đối soát, xử lý lỗi |

## 11. Bài tập tự luyện

### Bài 1 — Đặt key có namespace

Một ứng dụng quản lý học viên có `studentId = S102`, ba môi trường `dev`, `staging`, `prod` và hai loại dữ liệu `profile`, `progress`. Hãy đề xuất bốn khóa đại diện cho hai loại dữ liệu của hai môi trường bất kỳ. Sau đó giải thích vì sao tiền tố môi trường chỉ là một phần của cách tổ chức, không đảm bảo cô lập bảo mật.

**Gợi ý:** `school:prod:student:S102:profile` và `school:prod:student:S102:progress` là hai khóa khác nhau của cùng học viên; đổi `prod` thành `dev` tạo tên khác nhưng không tự thay đổi quyền truy cập.

### Bài 2 — Giá trị JSON hay bộ đếm riêng?

Hệ thống thường xuyên tăng số lượt xem sản phẩm và chỉ đôi khi đọc tên/mô tả sản phẩm. Lưu lượt xem trong JSON sản phẩm hay trong một khóa số đếm riêng có thể phù hợp hơn?

**Gợi ý:** một khóa đếm riêng cho phép dùng phép tăng nguyên tử, nhưng cần xác định số đếm có phải dữ liệu gốc, có thể mất không, và khi nào phải tổng hợp vào báo cáo.

### Bài 3 — Dấu phân tách và định danh

Hệ thống cho phép mã tenant chứa dấu hai chấm. Nếu ghép trực tiếp `tenant:contact:123`, ứng dụng có thể phân tách nhầm các phần. Hãy đề xuất cách mã hóa ID hoặc một cấu trúc quy ước đảm bảo có thể giải mã không nhập nhằng.

**Gợi ý:** phải có định dạng chuẩn/escape hoặc encode thành phần, được thực hiện thống nhất ở chỗ tạo key và chỗ đọc key.

### Bài 4 — So sánh NX, XX với chống lost update

Hai request cùng đọc một giỏ hàng đã có, mỗi request thêm một SKU khác và dùng `SET ... XX` để ghi. Điều gì có thể xảy ra?

**Gợi ý:** `XX` chỉ kiểm tra key tồn tại; request ghi sau vẫn có thể làm mất thay đổi của request ghi trước. Cần cơ chế cập nhật từng trường hoặc kiểm tra phiên bản.

### Bài 5 — Thiết kế TTL

Session ban đầu có TTL 30 phút. Ứng dụng dùng `SET` để ghi lại giá trị khi người dùng đổi tùy chọn hiển thị. TTL cũ trong Redis có luôn được giữ không?

**Gợi ý:** `SET` mặc định có thể xóa TTL cũ. Nếu cần giữ hoặc gia hạn, phải chỉ rõ chính sách và dùng lệnh/tùy chọn thích hợp.

## 12. Mẫu đặc tả một nhóm khóa

Trong một hệ thống nhiều người phát triển, nên viết hợp đồng cho nhóm dữ liệu thay vì chỉ ghi lại vài lệnh:

~~~yaml
logicalName: Shopping cart
keyPattern: "shop:<environment>:cart:<cartId>"
owner: Checkout Service
valueType: Redis hash
fieldRule: "SKU -> integer quantity"
primaryReads:
  - "Get cart by cartId"
primaryWrites:
  - "Set quantity of SKU"
  - "Increment quantity of SKU"
  - "Remove SKU"
ttlPolicy: "3600 seconds after the last qualifying activity"
requiredSemantics:
  - "Avoid lost updates"
  - "Reject invalid quantities"
cleanup: "Expire or delete after successful checkout"
~~~

Đây là ví dụ **tài liệu đặc tả ứng dụng**, không phải một cấu hình Redis tự thực thi. Chính sách “sau hoạt động cuối” chỉ đúng nếu ứng dụng **thực sự gia hạn TTL** theo định nghĩa hoạt động; đặt `EXPIRE` một lần ở đầu chỉ mang nghĩa hết hạn sau khi tạo.

Ngoài những trường trên, hệ thống thực tế nên bổ sung dự kiến số lượng khóa, kích thước value, tần suất đọc/ghi, quyền truy cập, backup/khôi phục, mức độ bền vững, cơ chế chuyển schema và cách quan sát hot key.

## 13. Ghi nhớ

Khi thiết kế một nhóm dữ liệu theo mô hình key–value, hãy trả lời các câu hỏi theo thứ tự:

1. **Ứng dụng có biết key khi đọc không?** Nếu thường xuyên lọc theo thuộc tính bên trong value, cần thêm chỉ mục hoặc mô hình dữ liệu phù hợp.
2. **Key có duy nhất, ổn định và được chuẩn hóa không?** Đảm bảo cùng một định danh nghiệp vụ luôn tạo ra cùng một key.
3. **Namespace được tổ chức và bảo vệ thế nào?** Tiền tố có ích cho tên gọi nhưng không tự thay thế cơ chế phân quyền.
4. **Value cần đọc/ghi với đơn vị nào?** Chọn string, JSON, hash hoặc cấu trúc khác dựa trên thao tác thường gặp.
5. **Các phép ghi có cần điều kiện hay tính nguyên tử không?** Tránh mất cập nhật khi nhiều client cùng sửa dữ liệu.
6. **Dữ liệu có thời hạn không?** Xác định TTL, vòng đời và cách dọn chỉ mục phụ hoặc khóa tham chiếu.
7. **DBMS cụ thể bảo đảm điều gì?** Đối chiếu API, cách phân vùng, giới hạn nhiều khóa, bảo đảm lưu trữ và khả năng truy vấn trước khi triển khai.

Ưu thế của key–value là **truy cập trực tiếp, thao tác đơn giản khi biết khóa và dễ thiết kế hiệu quả cho mẫu truy cập rõ ràng**. Chất lượng thiết kế đến từ việc tổ chức đúng khóa, giá trị, namespace và các thao tác theo yêu cầu thực tế của ứng dụng.

# tuple, UDT, frozen và ngữ nghĩa lưu trữ trong Apache Cassandra

Khi mô hình hóa dữ liệu **wide-column** trong Apache Cassandra, không phải mọi nhóm giá trị đều nên trở thành một bảng riêng, nhưng cũng không nên gộp mọi thứ vào một “object” lớn. CQL cung cấp **`tuple`** để lưu một nhóm phần tử **có vị trí và kiểu cố định**, **UDT** (*user-defined type*) để lưu một nhóm trường **có tên và kiểu dữ liệu rõ ràng**, và từ khóa **`frozen<...>`** để yêu cầu Cassandra xử lý toàn bộ giá trị phức hợp **như một đơn vị** thay vì các trường/phần tử cập nhật riêng.

Bài thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Mục tiêu của module là hiểu kiến trúc phân tán và mô hình wide-column của Apache Cassandra, chọn partition key, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, thực hành CQL, replication, compaction, repair, xử lý lỗi và kết nối Java. Trong bối cảnh ấy, **tuple/UDT/frozen là lựa chọn ngữ nghĩa và đơn vị cập nhật**, còn **partition key và clustering columns** vẫn phải được thiết kế theo truy vấn.

## 1. Bảng định hướng lựa chọn

| Cấu trúc | Các thành phần | Cách khai báo CQL | Có cập nhật từng thành phần? | Tình huống phù hợp |
|---|---|---|---|---|
| **Tuple** | Có vị trí, có kiểu, **không có tên trường** | `tuple<double, double>` | **Không**: tuple luôn được xử lý như frozen | Một cặp tọa độ, cặp giá trị nhỏ có nghĩa vị trí rõ ràng |
| **UDT không frozen** | Có **tên trường**, có kiểu | `postal_address` | **Có**, với UDT và thao tác CQL được phiên bản hỗ trợ | Địa chỉ hiện tại cần sửa một trường độc lập |
| **UDT frozen** | Có tên trường, có kiểu | `frozen<postal_address>` | **Không**: thay cả giá trị | Bản chụp địa chỉ giao hàng gắn với đơn hàng |
| **Collection không frozen** | List/set/map cùng kiểu phần tử tương ứng | `set<text>`, `map<text,text>` | Có một số phép cập nhật theo phần tử | Nhóm phần tử nhỏ, có giới hạn |
| **Collection frozen** | List/set/map được gói một giá trị | `frozen<map<text,text>>` | **Không**: thay cả giá trị | Cấu hình nhỏ được version hóa theo snapshot |
| **Bảng nhiều hàng** | Mỗi thực thể có primary key riêng | `CREATE TABLE ... PRIMARY KEY (...)` | Có thể cập nhật/truy vấn theo từng hàng | Dữ liệu lớn, tăng theo thời gian, cần phân trang/tra cứu riêng |

**Đừng hiểu “frozen” là không thể cập nhật dữ liệu.** Một cột `frozen<postal_address>` **vẫn có thể bị thay bằng giá trị mới**. Điều bị hạn chế là **cập nhật riêng một trường bên trong** giá trị frozen. Tên `frozen` mô tả **cách Cassandra xem một giá trị là nguyên khối**, không phải một ràng buộc “immutable” tuyệt đối ở cấp ứng dụng.

## 2. Tuple: cấu trúc cố định theo thứ tự vị trí

### 2.1. Tuple là gì?

`tuple<T1, T2, ...>` biểu diễn một nhóm trường **theo vị trí**. Mỗi vị trí có một kiểu CQL đã định nghĩa; các kiểu **có thể khác nhau**.

~~~cql
CREATE TABLE geo_samples_by_id (
    sample_id uuid PRIMARY KEY,
    coordinates tuple<double, double>,
    quality tuple<int, text>
);

INSERT INTO geo_samples_by_id (
    sample_id, coordinates, quality
) VALUES (
    11111111-1111-4111-8111-111111111111,
    (10.7769, 106.7009),
    (95, 'GPS')
);

SELECT coordinates, quality
FROM geo_samples_by_id
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Ở đây:

- `coordinates` có phần tử **vị trí 0 là vĩ độ**, **vị trí 1 là kinh độ** theo **quy ước của ứng dụng**. Cassandra chỉ biết đây là hai giá trị `double`; nó không tự biết hệ tọa độ hay vị trí nào là latitude.
- `quality` có **vị trí 0 là điểm số int**, **vị trí 1 là mã nguồn text**.
- Tuple literal dùng **dấu ngoặc tròn**: `(10.7769, 106.7009)`.
- Tuple là **cấu trúc có arity cố định**: nếu schema là `tuple<int,text>`, literal cần biểu diễn hai vị trí. Một vị trí có thể là `null` khi phù hợp, nhưng không tự bỏ vị trí mà vẫn giữ đúng nghĩa.

Vì tuple **không có tên trường**, thứ tự là một phần của hợp đồng dữ liệu. Nếu client A hiểu `(lat, lon)` còn client B hiểu `(lon, lat)`, dữ liệu có thể vẫn đúng kiểu CQL nhưng **sai về nghiệp vụ**.

### 2.2. Tuple luôn frozen

Trong Cassandra, một tuple **luôn được coi như frozen** dù không ghi từ khóa `frozen` trong khai báo. Vì vậy:

~~~cql
-- Đúng: thay toàn bộ tuple.
UPDATE geo_samples_by_id
SET coordinates = (10.7800, 106.7050)
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Không được mong có phép cập nhật riêng `coordinates[0]` theo cách cập nhật `list` không frozen; tuple **không phải list**. Nếu chỉ thay vĩ độ, client phải tạo **tuple mới có cả hai giá trị hợp lệ** rồi ghi thay toàn bộ.

Tác động quan trọng:

- **Atomicity ở cấp giá trị:** việc thay tuple là một mutation của giá trị nguyên khối; một nửa tuple mới không được merge độc lập với nửa tuple cũ như UDT không frozen.
- **Đồng thời:** hai client cùng đọc tuple rồi sửa hai vị trí khác nhau có thể ghi đè kết quả của nhau nếu mỗi client thay toàn bộ tuple.
- **Chi phí:** trường hợp rất nhỏ như cặp tọa độ là hợp lý; với nhiều phần tử lớn phải truyền lại toàn bộ giá trị khi chỉ có một chỗ thay đổi.
- **Tra cứu:** Cassandra không tạo đường truy vấn “mọi hàng có tuple phần tử 0 trong khoảng X” chỉ vì cột đó là tuple.

### 2.3. Khi nào tuple kém UDT?

Tuple có thể phù hợp với dữ liệu cố định, **đơn giản và được biểu diễn bằng vị trí một cách hiển nhiên**, ví dụ cặp số tọa độ trong một hệ thống đã quy định rõ.

Nhưng khi biểu diễn `(street, ward, city, postalCode, countryCode)`, việc dùng `tuple<text,text,text,text,ascii>` tạo ra các vị trí khó nhớ, dễ nhầm khi thêm trường và khó đọc trên cả Java lẫn CQL. Khi đó **UDT có tên trường** phù hợp hơn.

**Thực hành:** nếu một tuple có trên 2–3 phần tử hoặc cần bình luận “phần tử thứ 3 thực sự là gì”, hãy cân nhắc UDT hoặc các cột CQL riêng trước khi chốt thiết kế.

## 3. UDT: nhóm trường có tên và kiểu rõ ràng

### 3.1. CREATE TYPE trong keyspace

Một **user-defined type (UDT)** là cấu trúc có tên, chứa một danh sách có thứ tự các trường **đặt tên và định kiểu**. UDT được định nghĩa **trong một keyspace** rồi được các bảng của keyspace đó sử dụng.

~~~cql
-- Giả sử đã chọn keyspace ứng dụng bằng USE hoặc cấu hình client.
CREATE TYPE postal_address (
    street text,
    ward text,
    city text,
    postal_code text,
    country_code ascii
);
~~~

Các trường được định nghĩa **theo thứ tự**. Thứ tự này quan trọng với codec/serialization và schema evolution dù ứng dụng chủ yếu truy cập theo **tên trường**. Đừng cho rằng UDT đơn giản là một `map<text,text>`: UDT có **schema cố định và kiểu riêng** cho mỗi trường; map có tập key động và các value cùng một kiểu.

UDT literal trong CQL dùng tên trường **không phải chuỗi key**:

~~~cql
{
    street: '42 Nguyen Hue',
    ward: 'Ben Nghe',
    city: 'Ho Chi Minh City',
    postal_code: '700000',
    country_code: 'VN'
}
~~~

Khác với literal `map<text,text>` thường dùng `{'theme': 'dark'}`, các identifier `street`, `city` trong UDT literal là **tên trường được định nghĩa trong type**.

Một literal UDT có thể **bỏ qua vài trường**; các trường đó được xem là `null` trong giá trị UDT tương ứng. Điều này khác với việc có hay không cả cột UDT trong một row.

### 3.2. Vì sao UDT được tái sử dụng?

Nếu `postal_address` xuất hiện ở nhiều bảng, định nghĩa type một lần giúp cùng schema trường được sử dụng trong những ngữ cảnh khác:

- `current_address postal_address`: địa chỉ hiện tại có thể thay đổi ở hồ sơ khách hàng.
- `shipping_address frozen<postal_address>`: **bản chụp tại thời điểm đặt hàng**.
- `billing_address frozen<postal_address>`: địa chỉ xuất hóa đơn có thể cần giữ nguyên theo chứng từ.

Tái sử dụng **định nghĩa kiểu** không có nghĩa các cột tự đồng bộ giá trị. Cập nhật `current_address` không tự thay đổi snapshot `shipping_address` ở các đơn hàng cũ, và đó thường chính là ý định nghiệp vụ.

### 3.3. UDT có giới hạn

UDT hữu ích khi một nhóm field là một **giá trị gắn với row**. Nó không tạo:

- **Quan hệ khóa ngoại** tới row khác;
- **Index mặc định** trên từng field;
- **Validation nghiệp vụ** (mã quốc gia hợp lệ, mã bưu điện theo quốc gia);
- **Transaction ACID đa bảng** khi nhiều row cùng chứa type đó;
- **Tính duy nhất toàn cluster** của một trường bên trong UDT.

Nếu thường xuyên truy vấn riêng `postal_address.city` để tìm **mọi khách hàng ở một thành phố**, cần thiết kế đường truy cập theo thành phố, không chỉ đưa `city` vào UDT.

## 4. Frozen UDT: snapshot nguyên khối

Một trường `frozen<postal_address>` được Cassandra xử lý **như một giá trị hoàn chỉnh trong một cell**. Khi cập nhật, ứng dụng thay **toàn bộ địa chỉ** thay vì sửa từng field trên server.

Ví dụ một bảng theo yêu cầu “xem lịch sử đơn hàng của khách hàng theo tháng”:

~~~cql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    order_month text,
    ordered_at timestamp,
    order_id uuid,
    shipping_address frozen<postal_address>,
    dropoff_point tuple<double, double>,
    total_minor bigint,
    currency_code ascii,
    PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
~~~

Ở đây:

- **`(customer_id, order_month)`** là partition key, ví dụ `order_month = '2026-11'` theo UTC hoặc một lịch nghiệp vụ đã thống nhất.
- **`ordered_at, order_id`** là clustering columns, giúp đọc đơn theo thời điểm và phân biệt hai đơn cùng mili giây.
- **`shipping_address frozen<postal_address>`** lưu **địa chỉ snapshot**; bản cập nhật địa chỉ khách hàng sau này không thay dữ liệu lịch sử đơn.
- **`dropoff_point tuple<double,double>`** lưu một cặp vĩ độ/kinh độ theo quy ước ứng dụng; tuple vốn đã frozen.
- **`total_minor bigint`** và `currency_code ascii` minh họa việc giữ tiền bằng đơn vị nhỏ nhất và mã tiền tệ riêng; không dùng `double` để đối soát tiền.

~~~cql
INSERT INTO orders_by_customer_month (
    customer_id, order_month, ordered_at, order_id,
    shipping_address, dropoff_point, total_minor, currency_code
) VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11',
    '2026-11-21T04:00:00Z',
    33333333-3333-4333-8333-333333333333,
    {
        street: '42 Nguyen Hue',
        ward: 'Ben Nghe',
        city: 'Ho Chi Minh City',
        postal_code: '700000',
        country_code: 'VN'
    },
    (10.7769, 106.7009),
    199000,
    'VND'
);
~~~

Truy vấn theo đúng khóa được thiết kế:

~~~cql
SELECT ordered_at, order_id, shipping_address,
       dropoff_point, total_minor, currency_code
FROM orders_by_customer_month
WHERE customer_id = 22222222-2222-4222-8222-222222222222
  AND order_month = '2026-11'
LIMIT 50;
~~~

`frozen` không tạo ra một bản snapshot **bất biến về mặt lịch sử**: lệnh `UPDATE` vẫn có thể thay hoặc xóa cột frozen. Khái niệm snapshot bất biến phải được ứng dụng bảo vệ bằng quy tắc ghi, quyền truy cập và quy trình audit.

### 4.1. Thay cả giá trị, không cập nhật trường

~~~cql
-- Hợp lệ: thay toàn bộ frozen UDT bằng một giá trị mới.
UPDATE orders_by_customer_month
SET shipping_address = {
    street: '10 Le Loi',
    ward: 'Ben Nghe',
    city: 'Ho Chi Minh City',
    postal_code: '700000',
    country_code: 'VN'
}
WHERE customer_id = 22222222-2222-4222-8222-222222222222
  AND order_month = '2026-11'
  AND ordered_at = '2026-11-21T04:00:00Z'
  AND order_id = 33333333-3333-4333-8333-333333333333;
~~~

Không có cú pháp tương đương “`SET shipping_address.city = ...`” **áp dụng cho frozen UDT**. Muốn đổi thành phố trong frozen UDT, cần biết và ghi lại các trường còn lại hoặc dùng một nguồn giá trị đầy đủ đáng tin.

Đối với hai client cập nhật đồng thời:

~~~text
Trạng thái ban đầu:
{street: '42 Nguyen Hue', city: 'Ho Chi Minh City'}

Client A đọc rồi sửa street
Client B đọc rồi sửa city

A ghi cả frozen value với street mới, city cũ
B ghi cả frozen value với street cũ, city mới

Kết quả có thể mất một trong hai chỉnh sửa,
tùy xung đột và metadata write timestamp.
~~~

Không có phép merge tự động theo ý định từng field đối với frozen. Nếu nghiệp vụ yêu cầu cùng lúc sửa nhiều trường bởi các writer độc lập, cân nhắc **UDT không frozen** hoặc các cột riêng, kèm chính sách concurrency.

## 5. UDT không frozen: cập nhật trường riêng lẻ

Trong Cassandra có hỗ trợ **UDT không frozen** (từ dòng CQL của Cassandra 3.6 và các bản sau hỗ trợ tính năng), các trường có thể được cập nhật/xóa độc lập khi schema phù hợp. Trước khi sử dụng, cần **xác nhận phiên bản Cassandra/biến thể đang triển khai**; một số hạn chế với nested type/collection có thể khác nhau giữa các phiên bản.

Ví dụ hồ sơ khách hàng có địa chỉ hiện tại:

~~~cql
CREATE TABLE customer_profiles_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    current_address postal_address,
    updated_at timestamp
);

INSERT INTO customer_profiles_by_id (
    customer_id, display_name, current_address, updated_at
) VALUES (
    22222222-2222-4222-8222-222222222222,
    'Nguyen Ha',
    {
        street: '42 Nguyen Hue',
        ward: 'Ben Nghe',
        city: 'Ho Chi Minh City',
        postal_code: '700000',
        country_code: 'VN'
    },
    '2026-11-21T04:10:00Z'
);
~~~

Thay riêng tên thành phố mà không yêu cầu ứng dụng tái tạo cả địa chỉ:

~~~cql
UPDATE customer_profiles_by_id
SET current_address.city = 'Ha Noi',
    updated_at = '2026-11-21T04:15:00Z'
WHERE customer_id = 22222222-2222-4222-8222-222222222222;
~~~

Cú pháp `current_address.city` dùng được khi **cột UDT không frozen**. Những field khác như `street` và `postal_code` không phải bị ghi lại chỉ vì trường `city` thay đổi.

Muốn xóa một field của UDT không frozen:

~~~cql
DELETE current_address.postal_code
FROM customer_profiles_by_id
WHERE customer_id = 22222222-2222-4222-8222-222222222222;
~~~

Phép xóa tạo thông tin **tombstone** cho field tương ứng. UDT không frozen được lưu theo các thành phần có thể cập nhật riêng; vì vậy cần quan sát chi phí ghi/tombstone, và đừng mặc định nó là một “object đồng nhất” có version chung cho mọi field.

### 5.1. Tại sao non-frozen không đồng nghĩa không cần xử lý cạnh tranh?

Hai client cập nhật **hai field khác nhau** có thể ít va chạm hơn việc thay toàn bộ frozen UDT, nhưng điều đó không có nghĩa:

- Việc thay `city` và `postal_code` qua hai lệnh độc lập sẽ luôn được quan sát như một transaction nghiệp vụ hoàn chỉnh.
- Cassandra tự đảm bảo một bộ quy tắc địa chỉ nhất quán xuyên tất cả field.
- Các field có cùng TTL hoặc write timestamp nếu chúng được cập nhật ở các thời điểm khác nhau.
- Một ứng dụng thay **toàn bộ UDT** sẽ không làm ảnh hưởng các field mà client khác vừa sửa.

Nếu cần “đổi cả địa chỉ phải là một quyết định nguyên tử theo version”, hãy cân nhắc **frozen snapshot + phiên bản/LWT**, hoặc thiết kế row/đơn vị cập nhật phù hợp. Nếu cần nhiều cập nhật độc lập, UDT không frozen có thể hiệu quả hơn, nhưng vẫn phải kiểm tra retry và xung đột.

### 5.2. Khi nào dùng cột riêng thay vì UDT?

Không bắt buộc dùng UDT chỉ vì các cột có liên quan ngữ nghĩa. Ví dụ:

~~~cql
CREATE TABLE customer_contact_by_id (
    customer_id uuid PRIMARY KEY,
    street text,
    ward text,
    city text,
    country_code ascii,
    phone text
);
~~~

Các cột độc lập giúp truy vấn chọn các trường cần thiết và cập nhật rõ ràng. UDT phù hợp hơn khi bạn muốn **tái sử dụng một mô hình giá trị chung** ở nhiều bảng hoặc xem nhóm field là một đơn vị domain có tên.

Giữa hai cách, cần cân nhắc mức độ tái sử dụng schema, tính ổn định của field, mẫu truy vấn, concurrency, migration và API Java. **Đừng chọn UDT chỉ để tạo nhiều tầng nesting**, vì nó không thay đổi bản chất bảng wide-column.

## 6. frozen và ngữ nghĩa lưu trữ thực sự

### 6.1. Một cell so với nhiều cell

Một cách hình dung đơn giản:

~~~text
Row của customer_id = C

Cột frozen<postal_address>:
  shipping_address -> [serialized address: street, ward, city, ...]
  (một giá trị/cell ở cấp Cassandra)

Cột postal_address không frozen:
  current_address.street       -> "42 Nguyen Hue"
  current_address.ward         -> "Ben Nghe"
  current_address.city         -> "Ho Chi Minh City"
  current_address.postal_code  -> "700000"
  current_address.country_code -> "VN"
  (các field có thể là cell/giá trị được cập nhật riêng)
~~~

Sơ đồ thể hiện **đơn vị mutation logic**, không phải bố cục file SSTable byte-for-byte cho mọi phiên bản. Điểm quan trọng cho ứng dụng:

- **Frozen:** replace/DELETE toàn giá trị; không mutate riêng nested field.
- **Non-frozen:** có thể mutate/delete field riêng theo cú pháp CQL hỗ trợ.
- **Tuple:** luôn frozen, dù không viết `frozen<tuple<...>>`.
- **Nested UDT/collections:** có quy tắc về việc cần frozen ở mức lồng nhau; phải xác nhận phiên bản và lược đồ thay vì giả định mọi tổ hợp đều hợp lệ.

### 6.2. Tính nguyên tử có giới hạn

Khi Cassandra nhận một mutation ghi giá trị frozen, giá trị đó được xử lý như một **đơn vị**, không áp dụng một field mới từ writer A và một field mới từ writer B thành một object lai theo semantics non-frozen.

Tuy nhiên, “một giá trị” **không** có nghĩa:

- Một chuỗi ghi nhiều bảng/partition trở thành transaction ACID.
- Mọi người đọc luôn có consistency tuyến tính (linearizable) mà không cần thiết kế điều kiện ghi/đọc.
- Ghi snapshot frozen tự tạo khóa định danh duy nhất toàn hệ thống.
- Cassandra tự chống lost update khi hai writer cùng thay cả value.

Cassandra cho phép chọn consistency level và hỗ trợ thao tác có điều kiện trong những trường hợp nhất định; **quy tắc version và idempotency vẫn phải thiết kế theo nghiệp vụ**.

### 6.3. TTL, NULL, UNSET và tombstone

Một **frozen UDT** là một cột giá trị; TTL/NULL/xóa thường tác động ở mức cột giá trị đó. Một **UDT không frozen** có thể được cập nhật/xóa field riêng, vì vậy những field có thể có **write timestamp/TTL khác nhau** tùy cách mutation đã áp dụng.

Bảng tóm tắt:

| Tình huống | Frozen UDT / tuple | Non-frozen UDT |
|---|---|---|
| Không gửi cột trong INSERT thường | Không thay cột cũ | Không thay UDT cũ nếu cột không tham gia mutation |
| Bind **UNSET** cho cả cột | Bỏ qua cả value | Bỏ qua cả UDT nếu thao tác phù hợp |
| Ghi **NULL** cho cả cột | Xóa value, tạo tombstone theo quy tắc | Xóa cả UDT/field theo mutation được hỗ trợ |
| Đổi một field | Thay toàn bộ value | `SET address.field = ...` |
| Xóa một field | Không hỗ trợ xóa riêng field | `DELETE address.field ...` |
| Có thể khác TTL giữa các field | Không trên một giá trị frozen trong cùng cell | Có thể khi field được ghi riêng |

**Lưu ý với UDT literal thiếu field:** khi tạo **toàn bộ frozen value**, các field bỏ trống trong literal có thể trở thành **NULL bên trong UDT mới**. Không coi một literal chỉ gồm `{city: 'Ha Noi'}` là “patch city, giữ mọi field còn lại” cho một frozen address: nó là **một giá trị mới** và các field không được cung cấp không tự lấy từ phiên bản cũ.

Nếu API PATCH phân biệt **không gửi**, **explicit null** và **giá trị mới**, hãy ánh xạ đúng `UNSET`, `NULL` hoặc mutation field. Không cố tránh tombstone bằng UNSET khi nghiệp vụ thật sự yêu cầu xóa; điều đó sẽ để dữ liệu cũ tồn tại.

### 6.4. Kích thước một giá trị

Một UDT frozen lớn buộc client đọc/ghi cả giá trị khi thay một trường. Một UDT không frozen với rất nhiều field hoặc field là collection lớn cũng chưa chắc hợp lý: dữ liệu tăng vô giới hạn nên được tách thành các hàng có khóa riêng.

Với payload/file lớn, dùng object storage và lưu URI/metadata khi phù hợp. Với hàng triệu địa chỉ/giao dịch, không đặt tất cả trong một collection hoặc một UDT của một row; hãy thiết kế phân vùng để Cassandra có thể page và phân phối tải.

## 7. Tuple/UDT và PRIMARY KEY: vì sao nên ưu tiên khóa ổn định?

Một partition key trong Cassandra được **mã hóa rồi băm** để xác định token/replica. Clustering columns được **so sánh có thứ tự** bên trong một partition. Vì vậy, khóa cần ổn định, rõ nghĩa và hỗ trợ đường truy vấn.

Về mặt khả năng kiểu, một số kiểu phức hợp **frozen** có thể được dùng ở vị trí khóa khi phiên bản CQL hỗ trợ, nhưng điều đó không làm chúng trở thành lựa chọn mặc định tốt. Đặt toàn bộ một địa chỉ làm primary key thường có các vấn đề:

1. **Bất kỳ thay đổi field nào cũng thay giá trị khóa.** Địa chỉ sửa một dấu câu có thể chuyển row sang partition khác.
2. **Canonicalization** (viết hoa, dấu tiếng Việt, mã quốc gia, định dạng mã bưu điện) trở thành một phần khó kiểm soát của định danh.
3. **Tính duy nhất nghiệp vụ** của địa chỉ thường không rõ: hai khách hàng có thể cùng địa chỉ.
4. **Truy vấn theo một field** như city không tự được Cassandra tối ưu chỉ vì field nằm trong key phức hợp.
5. Bản encoded frozen value thay đổi theo schema/version cần được quản trị cẩn thận.

Vì thế, trong ví dụ `orders_by_customer_month`, khóa là **`customer_id`, `order_month`, `ordered_at`, `order_id`**, còn `shipping_address frozen<postal_address>` chỉ là **cột dữ liệu**. Thiết kế tách rõ **ID/đường truy vấn** khỏi **snapshot domain**.

Nếu cần tra cứu đơn hàng chính xác chỉ theo `order_id`, có thể phải có thêm bảng `orders_by_id` hoặc mapping ID → khóa partition; Cassandra không tự tra hiệu quả theo `order_id` nếu thiếu các thành phần khóa của bảng hiện tại.

## 8. Java Driver 4.x: TupleValue và UdtValue

Trong Java Driver 4.x, hai kiểu CQL được biểu diễn qua các type/value đối tượng, không ánh xạ trực tiếp sang `List<Object>` hay POJO mặc định:

| CQL | Type metadata trong Java | Giá trị Java | API đọc/ghi |
|---|---|---|---|
| `tuple<double,double>` | `TupleType` | `TupleValue` | `getTupleValue`, `setTupleValue` |
| `postal_address` hoặc `frozen<postal_address>` | `UserDefinedType` | `UdtValue` | `getUdtValue`, `setUdtValue` |
| Field `text` trong UDT | Metadata field type | `String` | `udtValue.getString("city")`, `setString("city", ...) ` |

Lưu ý: Java Driver không mặc định suy rằng một POJO Java bất kỳ có thể bind vào cột UDT; cần dùng `UdtValue` hoặc **Mapper/codec** đã được cấu hình chính xác. UDT có định nghĩa riêng trong keyspace và field order, nên lấy **type metadata từ schema/statement** thường an toàn hơn tự tạo một type thủ công.

### 8.1. Lấy type từ prepared statement, tạo value và bind

Ví dụ ghi đơn vào `orders_by_customer_month`. Giả sử `session` là `CqlSession` đã kết nối vào keyspace chứa `postal_address`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.data.TupleValue;
import com.datastax.oss.driver.api.core.data.UdtValue;
import com.datastax.oss.driver.api.core.type.TupleType;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

import java.time.Instant;
import java.util.UUID;

// CqlSession session = ...; // Quản lý kết nối ngoài ví dụ.

PreparedStatement insertOrder = session.prepare(
    "INSERT INTO orders_by_customer_month "
  + "(customer_id, order_month, ordered_at, order_id, "
  + " shipping_address, dropoff_point, total_minor, currency_code) "
  + "VALUES (:customer_id, :order_month, :ordered_at, :order_id, "
  + " :shipping_address, :dropoff_point, :total_minor, :currency_code)");

// Driver biết kiểu đúng của biến bind theo schema server.
UserDefinedType addressType = (UserDefinedType)
    insertOrder.getVariableDefinitions()
        .get("shipping_address").getType();

TupleType pointType = (TupleType)
    insertOrder.getVariableDefinitions()
        .get("dropoff_point").getType();

UdtValue address = addressType.newValue()
    .setString("street", "42 Nguyen Hue")
    .setString("ward", "Ben Nghe")
    .setString("city", "Ho Chi Minh City")
    .setString("postal_code", "700000")
    .setString("country_code", "VN");

TupleValue point = pointType.newValue()
    .setDouble(0, 10.7769)   // Latitude theo hợp đồng.
    .setDouble(1, 106.7009); // Longitude theo hợp đồng.

UUID customerId =
    UUID.fromString("22222222-2222-4222-8222-222222222222");
UUID orderId =
    UUID.fromString("33333333-3333-4333-8333-333333333333");

BoundStatement bound = insertOrder.boundStatementBuilder()
    .setUuid("customer_id", customerId)
    .setString("order_month", "2026-11")
    .setInstant("ordered_at", Instant.parse("2026-11-21T04:00:00Z"))
    .setUuid("order_id", orderId)
    .setUdtValue("shipping_address", address)
    .setTupleValue("dropoff_point", point)
    .setLong("total_minor", 199000L)
    .setString("currency_code", "VND")
    .build();

session.execute(bound);
~~~

Giải thích:

- `getVariableDefinitions().get("shipping_address").getType()` nhận metadata của bind variable theo đúng UDT đã triển khai.
- `addressType.newValue()` tạo `UdtValue` với các field có tên.
- `pointType.newValue()` tạo `TupleValue` với các vị trí 0 và 1.
- `setUdtValue` và `setTupleValue` bind giá trị đúng codec.
- UUID được sinh/lấy **một lần** và **tái sử dụng khi retry**. Không sinh order ID mới sau timeout, nếu không có thể tạo nhiều hàng cho cùng một đơn.

**Lưu ý về tính mutable:** `UdtValue` và `TupleValue` từ driver thường là **mutable value objects**, trong khi `BoundStatement` là **immutable**. Nếu các thread cùng chia sẻ và sửa một `UdtValue` đã bind cho thao tác async, có thể gặp race hoặc dữ liệu không như dự định. Tạo instance riêng/snapshot theo yêu cầu trước khi submit.

### 8.2. Đọc lại từ Row

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.TupleValue;
import com.datastax.oss.driver.api.core.data.UdtValue;

PreparedStatement findOrders = session.prepare(
    "SELECT ordered_at, order_id, shipping_address, dropoff_point "
  + "FROM orders_by_customer_month "
  + "WHERE customer_id = ? AND order_month = ? LIMIT 50");

for (Row row : session.execute(
        findOrders.bind(customerId, "2026-11"))) {

    UdtValue shipping = row.getUdtValue("shipping_address");
    if (shipping != null) {
        String city = shipping.getString("city");
        String street = shipping.getString("street");
    }

    TupleValue location = row.getTupleValue("dropoff_point");
    if (location != null &&
        !location.isNull(0) &&
        !location.isNull(1)) {

        double latitude = location.getDouble(0);
        double longitude = location.getDouble(1);
    }
}
~~~

Một **cột UDT có thể null**. Một **UDT không null vẫn có field null** nếu literal/nguồn không cung cấp field đó. Tương tự, tuple có thể chứa phần tử null, nên với getter primitive (`getDouble`) cần kiểm tra `isNull(index)` khi nghiệp vụ cho phép giá trị thiếu.

### 8.3. Cập nhật UDT không frozen bằng Java

Để thay thành phố của `customer_profiles_by_id.current_address`, không cần tạo `UdtValue` cho toàn bộ address:

~~~java
PreparedStatement updateCity = session.prepare(
    "UPDATE customer_profiles_by_id "
  + "SET current_address.city = ?, updated_at = ? "
  + "WHERE customer_id = ?");

session.execute(
    updateCity.boundStatementBuilder()
        .setString(0, "Ha Noi")
        .setInstant(1, Instant.parse("2026-11-21T04:15:00Z"))
        .setUuid(2, customerId)
        .build()
);
~~~

Đây là ưu điểm của **non-frozen UDT** khi sửa field cụ thể. Nếu `current_address` được khai báo **frozen**, câu lệnh trên sẽ không hợp lệ; phải tạo `UdtValue` mới với toàn bộ field rồi bind như một giá trị hoàn chỉnh.

### 8.4. Lấy UserDefinedType từ schema metadata

Ngoài prepared statement, có thể lấy type từ metadata của keyspace:

~~~java
import com.datastax.oss.driver.api.core.type.UserDefinedType;

// Với keyspace ví dụ là "shop_ks".
UserDefinedType addressType = session.getMetadata()
    .getKeyspace("shop_ks")
    .flatMap(ks -> ks.getUserDefinedType("postal_address"))
    .orElseThrow(() -> new IllegalStateException("UDT chưa có trong schema"));
~~~

Sau lệnh `CREATE TYPE`/`ALTER TYPE`, client cần nhìn thấy schema mới. Trong hệ phân tán, phải chờ **schema agreement** phù hợp và đảm bảo session/driver đã refresh metadata trước khi tạo/bind `UdtValue` theo type mới. Tránh tự dựng type bằng API nội bộ có field order không khớp, vì dữ liệu có thể bị mã hóa sai hoặc không thể đọc lại đúng.

## 9. Nested type và collection: khi nào cần frozen?

Một yêu cầu phổ biến là “mỗi người dùng có nhiều địa chỉ theo nhãn home/work”. Với số lượng địa chỉ **nhỏ và có giới hạn**, có thể lưu một map của các **frozen UDT**:

~~~cql
CREATE TABLE address_book_by_user (
    user_id uuid PRIMARY KEY,
    addresses map<text, frozen<postal_address>>
);
~~~

Ví dụ:

~~~cql
INSERT INTO address_book_by_user (user_id, addresses)
VALUES (
    44444444-4444-4444-8444-444444444444,
    {
        'home': {
            street: '42 Nguyen Hue',
            ward: 'Ben Nghe',
            city: 'Ho Chi Minh City',
            postal_code: '700000',
            country_code: 'VN'
        },
        'work': {
            street: '10 Le Loi',
            ward: 'Ben Nghe',
            city: 'Ho Chi Minh City',
            postal_code: '700000',
            country_code: 'VN'
        }
    }
);
~~~

Trong `map<text, frozen<postal_address>>`:

- Map **có thể** được cập nhật từng entry, ví dụ `addresses['home']`.
- **Giá trị của entry** là frozen UDT, vì vậy khi sửa thành phố của địa chỉ `home`, phải **thay toàn bộ giá trị địa chỉ home**, không có mutation nested field tự do.
- Map vẫn có giới hạn thiết kế: chỉ hợp nếu số key “home/work/...” nhỏ; nếu hàng nghìn địa chỉ có truy vấn/vòng đời riêng, hãy dùng **một row mỗi địa chỉ**.
- Các lồng ghép phức tạp có hạn chế cú pháp tùy phiên bản CQL. Xem tài liệu phiên bản đang chạy trước khi chọn nested non-frozen types.

Ví dụ thay toàn bộ entry `home`:

~~~cql
UPDATE address_book_by_user
SET addresses['home'] = {
    street: '99 Dong Khoi',
    ward: 'Ben Nghe',
    city: 'Ho Chi Minh City',
    postal_code: '700000',
    country_code: 'VN'
}
WHERE user_id = 44444444-4444-4444-8444-444444444444;
~~~

**Không xem map của frozen UDT là một bảng địa chỉ thu nhỏ có thể phân trang tùy ý.** Đọc/ghi/truy cập từng entry và cách tổ chức tombstone không thay thế clustering columns, pagination và phân phối partition. Để tìm tất cả địa chỉ của mọi người dùng ở một thành phố, cần thiết kế truy vấn khác.

## 10. UDT schema evolution: thêm trường, sửa hợp đồng và migration

UDT có schema nằm trong keyspace. Ví dụ, ứng dụng muốn bổ sung quận/huyện vào địa chỉ:

~~~cql
ALTER TYPE postal_address ADD district text;
~~~

Theo semantics CQL, **giá trị UDT được tạo trước khi thêm trường** không có giá trị cho `district`; trường mới được đọc như **NULL** cho đến khi dữ liệu được bổ sung. Đây không phải một migration backfill tự động.

Những quy tắc nên tuân thủ:

1. **Bắt đầu bằng thay đổi tương thích**, ví dụ thêm field optional; cho phép các client cũ chưa biết field mới trong giai đoạn chuyển đổi.
2. **Chờ schema agreement** trên cluster và kiểm tra driver metadata/codec; đặc biệt với `frozen<UDT>` việc giải mã phụ thuộc đúng định nghĩa trường và thứ tự.
3. **Đừng đổi nghĩa field đang có** chỉ bằng cách giữ tên nhưng thay đơn vị/format. Ví dụ `postal_code` từ text sang số sẽ mất số 0 đầu và có thể không phù hợp quốc tế.
4. **Versioning dữ liệu khi cần:** với đơn hàng được chốt, thay đổi schema địa chỉ hoặc rule hiển thị cần phân biệt bản chụp lịch sử với địa chỉ hiện tại.
5. **Backfill có kiểm soát** nếu field mới bắt buộc về nghiệp vụ; thống kê số row chưa có field, retry theo ID ổn định và đối soát.
6. **Không tùy tiện DROP TYPE** còn được bảng/UDT/hàm khác sử dụng. CQL thường từ chối drop type đang được tham chiếu.

Một lệnh `ALTER TYPE ... RENAME` có thể được hỗ trợ ở phiên bản CQL cụ thể, nhưng đổi tên field là thay đổi hợp đồng với code, prepared statements, mapper, API và schema metadata. Đừng coi đó là thao tác vô hại chỉ vì dữ liệu lưu trữ có thể vẫn diễn giải được.

### 10.1. Tuple khó tiến hóa schema theo field

Tuple **không có tên trường**, nên một client đọc tuple theo **index**. Nếu một nhóm dùng `tuple<text,int>` nhưng nhóm khác đổi vị trí thành `tuple<int,text>`, dữ liệu không còn cùng hợp đồng kiểu.

Ngay cả khi thêm thành phần ở cuối, thay đổi định nghĩa kiểu cột và codec không nên được xem như migration tự động tương thích. Với cấu trúc domain dự kiến thêm/đổi field, **UDT có tên trường** hoặc **cột riêng** thường dễ duy trì hơn.

### 10.2. Frozen không phải cách tự động nâng cấp mọi dữ liệu cũ

Một `frozen<postal_address>` được ghi trước thời điểm thêm `district` không tự có `district` thực. Nếu nghiệp vụ yêu cầu hiển thị lại địa chỉ lịch sử, có thể phải lấy thông tin gốc/sự kiện nguồn, không thể suy quận từ schema mới.

Một `UPDATE` thay frozen value ở đơn hàng cũ cũng có thể làm mất ý nghĩa snapshot. Hãy phân biệt **schema evolution** (các trường có thể đọc/ghi) với **business migration** (giá trị đúng của bản ghi cũ).

## 11. Retry, consistency và cập nhật một giá trị phức hợp

### 11.1. Retry sau timeout và lost update

Trong Cassandra, lệnh ghi có thể đã thành công ở vài replica nhưng client nhận timeout. Vì vậy:

- Với **frozen UDT/tuple**, retry cùng **primary key và cùng value** cho cùng một yêu cầu thường dễ suy luận hơn retry với value mới được tính lại từ dữ liệu đã thay đổi; nhưng phải xem write timestamp và concurrency.
- Với **non-frozen UDT**, retry cập nhật cùng field với cùng giá trị không tự tạo nhiều field trùng nhau; tuy nhiên xung đột với writer khác vẫn chịu metadata ghi và cách ứng dụng điều phối.
- Với **sự kiện nghiệp vụ**, hãy sinh `order_id` **một lần** rồi tái sử dụng ở mọi lần thử. Không cho retry tạo đơn thứ hai.
- Nếu một thao tác cần cập nhật hồ sơ và nhiều bảng lịch sử, không mặc định nhiều câu CQL độc lập thành một transaction ACID đa partition.

**Consistency level** như `LOCAL_QUORUM` điều chỉnh số replica xác nhận; nó không quyết định “client nào mới nhất về mặt thời gian thực” cho hai object frozen được ghi đồng thời.

### 11.2. Điều kiện ghi

Nếu domain yêu cầu “chỉ thay địa chỉ nếu phiên bản vẫn là 5”, có thể lưu `version int` và sử dụng **lightweight transaction (LWT)** với điều kiện đã hỗ trợ trong CQL/phiên bản triển khai:

~~~cql
-- Minh họa cơ chế optimistic concurrency trên một row.
-- Giả sử bảng có cột version int cùng customer_id.
UPDATE customer_profiles_versioned
SET version = 6
WHERE customer_id = 22222222-2222-4222-8222-222222222222
IF version = 5;
~~~

Đây là ví dụ **điều kiện cập nhật phiên bản**, không phải định nghĩa một bảng mới; khi triển khai thực tế, cần đưa cả các field địa chỉ cần đổi vào **cùng câu UPDATE có điều kiện** để việc xác nhận version gắn với mutation. LWT có chi phí Paxos đáng kể hơn ghi thường; không dùng như mặc định cho mọi cột chỉ để che một thiết kế đồng thời chưa rõ.

Nếu hệ thống có sự kiện phải chống trùng, bản ghi audit hoặc bảng định danh riêng có thể thích hợp hơn chỉ dùng một version field.

## 12. Replication, compaction, repair và độ lớn dữ liệu

### 12.1. Replication và repair

Cassandra sao chép **các mutation/cell** dựa trên partition key và replication strategy. Khi dữ liệu dùng `frozen<UDT>`, replica xử lý **giá trị đóng gói**; với non-frozen UDT, các field có thể có metadata cập nhật riêng. **Repair** giúp trạng thái replica hội tụ theo cơ chế Cassandra, nhưng không sửa được lỗi logic như đảo `latitude` với `longitude` trong tuple.

### 12.2. Compaction và tombstone

Khi xóa hoặc ghi đè giá trị, Cassandra có thể ghi dấu xóa/tombstone để ngăn giá trị cũ tái xuất hiện trên replica. Cập nhật/xóa field của non-frozen UDT tạo mutation ở mức field; xóa hoặc thay cả frozen value được xử lý ở cấp giá trị. **Compaction** gộp SSTable và dọn tombstone khi đủ điều kiện; không làm một UDT lớn trở thành cấu trúc nhiều row có thể phân trang.

Nếu thường xuyên chỉnh một trường của object rất lớn, cần xem xét **đơn vị cập nhật** và việc thay toàn bộ frozen value có tạo tải mạng/GC không cần thiết hay không.

### 12.3. Kích thước partition

Một bảng `orders_by_customer_month` giới hạn partition theo customer và tháng, nhưng **không đảm bảo partition nhỏ** nếu một khách hàng tạo lượng đơn cực lớn. Phải đo số row/partition, kích thước address UDT, tổng byte, tombstone, p95/p99 đọc/ghi, và cân nhắc bucket nhỏ hơn hoặc shard nếu cần.

**Không đưa hàng nghìn địa chỉ** vào `map<text,frozen<postal_address>>` trong một row chỉ vì CQL cho phép. Với nhu cầu tìm kiếm, phân trang, chỉnh sửa hoặc xóa độc lập, một bảng với `PRIMARY KEY ((customer_id, bucket), address_id)` hoặc khóa phù hợp với truy vấn thường dễ vận hành hơn.

### 12.4. Bảo vệ dữ liệu cá nhân

Địa chỉ và tọa độ có thể là dữ liệu nhạy cảm. Một UDT gói các field lại **không tự mã hóa hay kiểm soát quyền truy cập từng field**. Cần áp dụng kiểm soát truy cập, masking/logging, retention/TTL và quy trình xóa theo yêu cầu. Không log `UdtValue.getFormattedContents()` vô điều kiện vì có thể đưa toàn bộ nội dung địa chỉ vào log.

## 13. Lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
|---|---|---|
| Dùng tuple dài để lưu địa chỉ | Dễ nhầm index, khó mở rộng schema | Dùng UDT có tên trường hoặc cột riêng |
| Đảo `latitude` và `longitude` trong tuple | Dữ liệu sai nhưng codec vẫn hợp lệ | Quy định thứ tự, validation miền và test biên |
| Nghĩ tuple có thể cập nhật `coordinates[0]` | Tuple luôn frozen; không có mutation index như list | Tạo tuple mới rồi thay cả giá trị |
| Dùng `frozen<UDT>` nhưng kỳ vọng `address.city = ...` | CQL không hỗ trợ update field frozen | Dùng non-frozen UDT hoặc thay cả value |
| Cho rằng frozen đồng nghĩa không thể cập nhật | Vẫn có thể ghi đè toàn bộ | Bảo vệ snapshot bằng chính sách nghiệp vụ |
| Patch frozen UDT bằng literal chỉ có `city` | Các field khác trong value mới có thể là null | Ghi toàn bộ giá trị đã được xác thực |
| Ghi nguyên non-frozen UDT từ hai client read-modify-write | Có thể mất cập nhật hoặc vi phạm invariant | Update field riêng, version/LWT khi cần |
| Coi UDT là index trên `city` | Không tự hỗ trợ tìm kiếm theo field toàn cluster | Bảng theo city/index phù hợp workload |
| Dùng địa chỉ frozen làm khóa định danh | Khóa đổi khi sửa địa chỉ; khó canonicalization | Khóa `uuid`/text bền vững, address làm value |
| Coi non-frozen là transaction nghiệp vụ nhiều field | Các bước độc lập vẫn có rủi ro race/partial workflow | Thiết kế mutation/điều kiện đúng đơn vị |
| Thay UDT type mà không refresh metadata Java Driver | Codec không khớp định nghĩa schema mới | Schema agreement, metadata refresh, test migration |
| Dùng một map/UDT lớn tăng vô hạn | Row/partition nặng, khó page | Bảng nhiều row với khóa truy vấn |
| Coi repair tự sửa lỗi nhầm field/đảo index | Replica chỉ hội tụ dữ liệu đã ghi | Validation/QA ở ứng dụng và backfill có kiểm soát |
| Log toàn bộ UDT chứa địa chỉ cá nhân | Lộ dữ liệu nhạy cảm | Redaction và kiểm soát quyền logging |

## 14. Bài tập tình huống

### Bài 1 — Chọn kiểu

Một ứng dụng cần lưu:

1. Hai số `latitude, longitude` gắn liền một snapshot.
2. Địa chỉ nhận hàng khi đơn được chốt; không được đổi theo địa chỉ hồ sơ sau này.
3. Địa chỉ hiện tại để user sửa riêng `ward`/`city`/`postal_code`.
4. Mọi địa chỉ user từng dùng, có hàng triệu bản ghi và cần phân trang.

**Gợi ý:** (1) `tuple<double,double>` nếu quy ước thứ tự rõ; (2) `frozen<postal_address>`; (3) `postal_address` không frozen (khi phiên bản hỗ trợ) hoặc các cột riêng; (4) **bảng nhiều row** với address ID/bucket và clustering phù hợp.

### Bài 2 — Frozen có thật sự immutable?

Một `orders_by_customer_month.shipping_address` khai báo `frozen<postal_address>`. Client gửi `UPDATE SET shipping_address = { ... }` với địa chỉ mới và đúng primary key.

**Đáp án:** Cassandra **có thể cập nhật** cả frozen value. Frozen chỉ ngăn update field riêng, không bảo vệ snapshot khỏi bị ghi đè; tính immutable của lịch sử phải do quy tắc nghiệp vụ áp dụng.

### Bài 3 — Tranh chấp cập nhật

Ban đầu `address = \{street: 'A', city: 'X'\}`. Client 1 thay street thành B, client 2 thay city thành Y; cả hai đọc snapshot cũ rồi ghi nguyên `frozen<address>`.

**Câu hỏi:** Có chắc cuối cùng là `{street: 'B', city: 'Y'}`?

**Đáp án:** không. Hai lần thay nguyên value có thể ghi đè một thay đổi. Cân nhắc non-frozen field-level mutations, hoặc version/điều kiện ghi nếu nghiệp vụ muốn toàn bộ address là một phiên bản thống nhất.

### Bài 4 — UDT literal thiếu trường

~~~cql
-- Cột shipping_address là frozen<postal_address>.
UPDATE orders_by_customer_month
SET shipping_address = {city: 'Ha Noi'}
WHERE customer_id = 22222222-2222-4222-8222-222222222222
  AND order_month = '2026-11'
  AND ordered_at = '2026-11-21T04:00:00Z'
  AND order_id = 33333333-3333-4333-8333-333333333333;
~~~

**Câu hỏi:** Cột `street` có được giữ lại không?

**Đáp án:** không được giả định giữ lại. Lệnh này thay **toàn bộ frozen value**, và trường không cung cấp trong literal có thể trở thành **null** của giá trị mới. Với PATCH field, phải dùng UDT không frozen hoặc xây một frozen value hoàn chỉnh sau khi có kiểm soát concurrency.

### Bài 5 — Java Driver

Một prepared statement có biến `shipping_address frozen<postal_address>` và `dropoff_point tuple<double,double>`. Bạn muốn bind cả hai qua Java.

**Gợi ý:** lấy `UserDefinedType`/`TupleType` từ `prepared.getVariableDefinitions().get("...").getType()`, gọi `newValue()`, set field theo tên với `UdtValue`, set phần tử theo index với `TupleValue`, rồi `setUdtValue`/`setTupleValue`. Không tự serialize JSON hoặc dùng `List<Object>` rồi mong driver tự suy schema.

### Bài 6 — Truy vấn theo địa chỉ

Bảng đơn được partition bởi `(customer_id, order_month)`, có `shipping_address frozen<postal_address>`. Sản phẩm yêu cầu “tìm mọi đơn giao tới Hà Nội trong 7 ngày”.

**Đáp án:** cột UDT không tự cung cấp đường truy cập theo field `city` trên toàn cluster. Thiết kế bảng theo thành phố/ngày với bucket và ID, hoặc một cơ chế index/search đã được đánh giá theo phiên bản và tải; phải quản lý đồng bộ khi địa chỉ đơn bị điều chỉnh.

## 15. Checklist trước khi dùng tuple, UDT và frozen

- [ ] Cấu trúc cần **vị trí cố định** (tuple) hay **tên trường rõ ràng** (UDT)?
- [ ] Tuple có thứ tự field được tài liệu hóa và kiểm thử để tránh đảo vị trí?
- [ ] UDT được định nghĩa trong đúng keyspace và các field có kiểu/ngữ nghĩa ổn định?
- [ ] Cột cần **thay toàn bộ snapshot** (frozen) hay **chỉnh từng field** (non-frozen)?
- [ ] Đã hiểu **tuple luôn frozen**, không cập nhật riêng phần tử?
- [ ] Với frozen value, mọi PATCH có xây **giá trị đầy đủ** thay vì chỉ cung cấp một field và làm null field khác?
- [ ] Nếu UDT không frozen, phiên bản Cassandra và quy tắc nested type có hỗ trợ schema này?
- [ ] Đã cân nhắc concurrency, TTL, tombstone và versioning cho đơn vị cập nhật?
- [ ] Có phân biệt **NULL/UNSET** ở cấp cột với field NULL bên trong UDT?
- [ ] Truy vấn đã có **partition key/clustering columns** phù hợp, không dựa vào UDT để tự tạo index field?
- [ ] Java Driver dùng đúng `UdtValue`/`TupleValue`, lấy metadata từ schema hoặc statement?
- [ ] Sau `ALTER TYPE`, các client đã refresh type metadata, kiểm thử tương thích đọc/ghi và backfill nếu cần?
- [ ] Số field, kích thước frozen value và partition có được giới hạn/quan sát trong vận hành?
- [ ] Retry giữ primary key, loại trừ tạo đơn hàng trùng sau timeout?
- [ ] Đã tính tới replication/consistency/compaction/repair, chính sách bảo mật dữ liệu và audit?

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Types: UDT và Tuple](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html).
- [Apache Cassandra — Data Manipulation (cập nhật field UDT không frozen)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
- [Apache Cassandra — CREATE TABLE và frozen UDT](https://cassandra.apache.org/doc/stable/cassandra/reference/cql-commands/create-table.html).
- [Apache Cassandra Java Driver 4.x — UDTs](https://apache.github.io/cassandra-java-driver/4.19.0/core/udts/).
- [Apache Cassandra Java Driver 4.x — Tuples](https://apache.github.io/cassandra-java-driver/4.19.0/core/tuples/).

**Ghi nhớ:** **`tuple`** mô hình hóa nhóm phần tử **theo vị trí** và **luôn frozen**; **UDT** mô hình hóa nhóm field **có tên** và có thể frozen hoặc không frozen khi schema/phiên bản hỗ trợ. **Frozen = thay cả giá trị**, không có cập nhật độc lập từng field. Trong Cassandra, lựa chọn này quyết định đơn vị mutation, concurrency, tombstone và codec Java; còn khóa phân vùng, clustering, replication và thiết kế theo truy vấn quyết định dữ liệu được truy xuất hiệu quả như thế nào.


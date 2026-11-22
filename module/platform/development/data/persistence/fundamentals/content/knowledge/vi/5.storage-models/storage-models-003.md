# Mô hình khóa–giá trị và truy cập theo khóa

Trong nhiều ứng dụng Java, câu hỏi phổ biến nhất khi đọc dữ liệu là: “Với mã định danh này, bản ghi tương ứng đang ở đâu?”. Ví dụ, hệ thống thương mại điện tử cần lấy giỏ hàng theo mã giỏ; dịch vụ đăng nhập cần tìm phiên theo session ID; bộ xử lý sự kiện cần biết một message ID đã được xử lý hay chưa. Khi đường truy cập chính đã xác định rõ **một khóa**, mô hình lưu trữ **khóa–giá trị (key–value)** thường là lựa chọn đơn giản và hiệu quả.

Bài học thuộc chương **Mô hình lưu trữ** của **DATA_PERSISTENCE_FUNDAMENTALS**. Trọng tâm là biểu diễn dữ liệu thành cặp khóa–giá trị, thiết kế đường truy cập theo khóa và triển khai ranh giới persistence trong Java. Các quyết định về giao dịch, tính nhất quán, bảo mật, tiến hóa schema, sao lưu và hiệu năng sẽ được xem xét từ chính mô hình này.

## 1. Khái niệm và điều kiện áp dụng

Một kho khóa–giá trị duy trì ánh xạ:

~~~text
key  ->  value
"cart:v1:t42:c901"  ->  {"schemaVersion":1,"version":4,"items":[...]}
"session:v1:s80"    ->  {"userId":"u17","expiresAt":"..."}
~~~

- **Key** là định danh duy nhất trong phạm vi không gian khóa. Hai lần ghi vào cùng một khóa thường cùng tác động đến một mục dữ liệu, theo chính sách ghi của hệ thống.
- **Value** là nội dung gắn với khóa. Nó có thể là chuỗi, số, JSON, byte array hoặc một cấu trúc do hệ quản trị hỗ trợ. Với kho khóa–giá trị thuần túy, hệ thống lưu trữ có thể coi value là khối byte không cần hiểu cấu trúc bên trong.
- **Namespace** là quy ước phân nhóm khóa ở tầng ứng dụng, chẳng hạn tiền tố **cart:** hoặc **session:**. Nó giúp quản lý nhưng không tự tạo ranh giới bảo mật.
- **Truy cập theo khóa (point lookup)** là cung cấp đầy đủ khóa để lấy một giá trị: tìm **cart:v1:t42:c901** thay vì hỏi “mọi giỏ hàng có tổng tiền lớn hơn một triệu”.

Đặc tính quan trọng là **ứng dụng biết khóa trước khi đọc**. Nếu yêu cầu nghiệp vụ thường xuyên tìm bằng nhiều thuộc tính, lọc hoặc kết hợp nhiều tập dữ liệu, chỉ có ánh xạ key–value sẽ không đủ tiện lợi; cần thiết kế chỉ mục phụ, mô hình dữ liệu khác hoặc kết hợp nhiều loại kho lưu trữ.

**Key–value là mô hình dữ liệu, không đồng nghĩa với cache.** Một cơ sở dữ liệu key–value có thể lưu bền vững; một cache key–value lại có thể chấp nhận mất dữ liệu. Sự khác nhau nằm ở cấu hình, cơ chế lưu trữ và cam kết của hệ thống cụ thể.

## 2. Các thao tác cơ bản và đường truy cập

| Thao tác logic | Ý nghĩa | Điểm cần xác định trong thiết kế |
|---|---|---|
| **GET(key)** | Đọc value của khóa | Khóa không tồn tại được biểu diễn ra sao; đọc từ bản sao nào |
| **PUT(key, value)** | Tạo hoặc thay thế value | Ghi đè có điều kiện hay vô điều kiện; ghi đã bền vững chưa |
| **DELETE(key)** | Xóa khóa | Xóa tức thời hay đánh dấu xóa; tác động lên bản sao |
| **PUT_IF_ABSENT(key, value)** | Chỉ tạo khi khóa chưa có | Phải được thực hiện nguyên tử nếu dùng để chống trùng |
| **COMPARE_AND_SET(key, old, new)** | Chỉ thay đổi khi giá trị/phiên bản còn khớp | Có được hệ lưu trữ hỗ trợ nguyên tử hay không |
| **EXPIRE(key, ttl)** | Đặt thời gian sống nếu hệ thống hỗ trợ | Hết hạn là quy tắc truy cập, không phải bảo đảm thời điểm thu hồi vật lý |
| **BATCH/MULTI_GET** | Đọc/ghi nhiều khóa | Có giảm lượt mạng không; có bảo đảm nguyên tử cả nhóm không |

Một đường đọc điển hình có thể hình dung như sau:

~~~mermaid
flowchart LR
    A["Ứng dụng Java"] --> B["Tạo key chính xác"]
    B --> C["Client / connection pool"]
    C --> D["Node hoặc phân vùng giữ key"]
    D --> E["Tra chỉ mục và đọc value"]
    E --> F["Giải mã về đối tượng"]
~~~

Sơ đồ là **luồng khái niệm**, không phải cấu trúc bắt buộc của mọi sản phẩm. Một kho nhúng có thể không có mạng; một hệ phân tán có thể định tuyến khóa tới partition và đọc từ bản sao. Chỉ mục bên dưới có thể dùng bảng băm, B-tree, LSM-tree hoặc cấu trúc khác. Vì vậy, không nên khẳng định mọi lần GET đều có độ phức tạp O(1): độ trễ thực tế còn phụ thuộc I/O, cache, kích thước value, tải hệ thống, phân vùng và mạng.

### Vì sao truy cập bằng khóa thường nhanh?

Khi đã biết khóa, hệ thống không cần xét lần lượt mọi value để kiểm tra điều kiện nghiệp vụ. Nó định vị trực tiếp mục tương ứng qua cấu trúc chỉ mục. Với bảng băm trong bộ nhớ, tra cứu trung bình có thể gần O(1); với chỉ mục trên đĩa, số lượt truy cập và bố cục dữ liệu quyết định chi phí. Trong môi trường dịch vụ, một chuyến đi qua mạng đôi khi tốn nhiều thời gian hơn thao tác tìm khóa, nên cần đo độ trễ đầu cuối thay vì chỉ nói đến độ phức tạp thuật toán.

## 3. Thiết kế khóa để sử dụng lâu dài

Hãy xét giỏ hàng của tenant **t42**, có cart ID **c901**. Một quy ước có thể là:

~~~text
cart:v1:t42:c901
│    │  │   └── mã giỏ
│    │  └────── mã tenant
│    └───────── phiên bản quy ước đặt key
└────────────── loại thực thể
~~~

Khóa tốt thường đáp ứng các tiêu chí:

1. **Duy nhất và ổn định:** cùng một thực thể luôn tạo ra cùng một khóa. Không dùng thuộc tính dễ thay đổi, như tên hiển thị, làm định danh chính.
2. **Có phạm vi rõ ràng:** thêm tenant ID khi hệ thống nhiều tenant; tránh va chạm giữa môi trường, loại dữ liệu và phiên bản.
3. **Có quy tắc mã hóa:** chỉ cho phép tập ký tự đã quy định hoặc mã hóa các thành phần có dấu phân cách; tránh trường hợp hai bộ thành phần tạo ra cùng một chuỗi khóa.
4. **Giữ kích thước hợp lý:** khóa dài tiêu tốn bộ nhớ, mạng và dung lượng chỉ mục; value quá lớn cũng tăng thời gian truyền và chi phí cập nhật.
5. **Không lộ dữ liệu nhạy cảm:** không đưa mật khẩu, token bí mật, số căn cước hoặc thông tin cá nhân trực tiếp vào tên khóa; key có thể xuất hiện trong log và công cụ quản trị.
6. **Chú ý phân phối tải:** key nóng, mọi yêu cầu đổ vào một khóa hoặc một partition, có thể trở thành nút nghẽn dù tổng dung lượng vẫn nhỏ.

Tiền tố **v1** giúp thay đổi quy ước key về sau, nhưng không thay thế trường **schemaVersion** bên trong value. Hai loại phiên bản giải quyết hai việc khác nhau: tìm đúng địa chỉ và hiểu đúng dữ liệu.

**Ví dụ sai:** dùng email làm khóa hồ sơ người dùng, sau đó đổi email khiến hệ thống không tìm được hồ sơ cũ. **Cách tốt hơn:** lưu hồ sơ bằng user ID bất biến; nếu cần tìm bằng email, xây dựng một đường tra cứu hoặc chỉ mục email → user ID có quy tắc đồng bộ rõ ràng.

## 4. Biểu diễn value và tiến hóa schema

Đối với value phức tạp, ứng dụng cần định nghĩa cách mã hóa và giải mã. JSON dễ kiểm tra thủ công; một định dạng nhị phân như Protocol Buffers có thể giảm kích thước hoặc bổ sung quy tắc tương thích. Không có định dạng nào tự xử lý được mọi vấn đề tiến hóa schema.

Ví dụ một value giỏ hàng:

~~~json
{
  "schemaVersion": 2,
  "version": 4,
  "currency": "VND",
  "items": [
    {"sku": "BOOK-17", "quantity": 2},
    {"sku": "PEN-03", "quantity": 1}
  ]
}
~~~

Ở đây **schemaVersion** giúp bộ giải mã chọn cách đọc định dạng, còn **version** là phiên bản thay đổi của chính giỏ hàng, có thể dùng trong kiểm soát đồng thời. Khi nâng schema, bộ đọc nên có chiến lược đối với value đời cũ và trường mới: cung cấp giá trị mặc định hợp lệ, chuyển đổi khi đọc hoặc thực hiện migration có kiểm soát. Việc thêm trường bắt buộc mà không xử lý value cũ dễ gây lỗi khi triển khai phiên bản ứng dụng mới.

Nên quyết định rõ:

- **Null và missing:** không tìm thấy key khác với value hợp lệ nhưng rỗng; không tự diễn giải dữ liệu lỗi thành “không tồn tại”.
- **Tương thích phiên bản:** ứng dụng mới có đọc được value cũ không; ứng dụng cũ có cần đọc value mới trong giai đoạn rolling deployment không.
- **Xử lý hỏng dữ liệu:** ghi log đủ để chẩn đoán nhưng không in toàn bộ value nhạy cảm; phân biệt lỗi giải mã với lỗi kết nối.
- **Giới hạn kích thước:** không gom danh sách tăng vô hạn vào một value; một thay đổi nhỏ có thể buộc ghi lại toàn bộ tài liệu.

## 5. Xây ranh giới persistence trong Java

Không nên để controller hoặc nghiệp vụ tự ghép lệnh của một sản phẩm lưu trữ ở mọi nơi. Một cổng truy cập nhỏ giúp mã nghiệp vụ diễn tả **đọc theo khóa**, **ghi theo khóa** và **quy tắc TTL**. Ví dụ Java 17 dưới đây minh họa giao diện và một repository; lớp hiện thực **KeyValueStore** và bộ mã hóa **Codec** sẽ phụ thuộc công nghệ sử dụng.

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

interface KeyValueStore {
    Optional<String> get(String key);
    void put(String key, String value, Duration ttl);
    boolean putIfAbsent(String key, String value, Duration ttl);
    boolean delete(String key);
}

interface Codec<T> {
    String encode(T value);
    T decode(String encoded);
}

record Cart(long version, Map<String, Integer> quantityBySku) {}

final class CartRepository {
    private final KeyValueStore store;
    private final Codec<Cart> codec;
    private static final Duration CART_TTL = Duration.ofMinutes(30);

    CartRepository(KeyValueStore store, Codec<Cart> codec) {
        this.store = store;
        this.codec = codec;
    }

    Optional<Cart> find(String tenantId, UUID cartId) {
        return store.get(key(tenantId, cartId)).map(codec::decode);
    }

    void save(String tenantId, UUID cartId, Cart cart) {
        store.put(key(tenantId, cartId), codec.encode(cart), CART_TTL);
    }

    boolean remove(String tenantId, UUID cartId) {
        return store.delete(key(tenantId, cartId));
    }

    private static String key(String tenantId, UUID cartId) {
        if (tenantId == null || !tenantId.matches("[a-z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        return "cart:v1:" + tenantId + ":" + cartId;
    }
}
~~~

Đoạn mã cho thấy cách tạo key nhất quán, đọc qua **Optional** và giữ logic lưu trữ tại một điểm. Đây là **hợp đồng ứng dụng**, chưa phải chương trình tự chạy: cần adapter cho kho lưu trữ thật và codec tương thích schema. Trong adapter, việc đặt value và TTL nên là một thao tác nguyên tử nếu backend hỗ trợ. Cần quy định thời hạn ghi và cách ánh xạ lỗi kết nối, timeout, thiếu quyền hoặc value không giải mã được sang lỗi thích hợp của tầng ứng dụng.

**Lưu ý đồng thời:** **save** ở trên là ghi đè vô điều kiện. Nếu hai yêu cầu cập nhật cùng một cart, giá trị ghi sau có thể làm mất thay đổi trước. Repository production có luồng cập nhật cạnh tranh cần bổ sung phiên bản và cơ chế ghi có điều kiện; chỉ có trường **version** trong JSON là chưa đủ.

### Minh họa với Redis

Redis là một hệ thống hỗ trợ truy cập bằng key và nhiều kiểu dữ liệu. Các lệnh sau mô tả một vòng đời **key → value**; có thể thực hành trong môi trường thử nghiệm:

~~~redis
SET cart:v1:t42:c901 '{"schemaVersion":2,"version":4,"items":[]}' EX 1800
GET cart:v1:t42:c901
TTL cart:v1:t42:c901
DEL cart:v1:t42:c901
~~~

- **SET ... EX 1800** ghi chuỗi và TTL 1.800 giây trong cùng lệnh.
- **GET** trả về chuỗi hoặc giá trị “không có” khi key vắng mặt.
- **TTL** kiểm tra thời gian sống còn lại theo quy tắc của Redis.
- **DEL** xóa key; nếu xóa một key không tồn tại, kết quả khác với xóa thành công.

Có thể đặt dấu giữ chỗ chống hai tiến trình đồng thời “nhận” cùng một yêu cầu bằng thao tác tạo có điều kiện:

~~~redis
SET request:v1:t42:r501 processing NX EX 120
~~~

**NX** nghĩa là chỉ ghi nếu key chưa tồn tại. Đây là bước claim nguyên tử, **chưa phải toàn bộ giải pháp idempotency**: ứng dụng còn phải lưu trạng thái hoàn tất, kết quả xử lý, quy tắc retry khi tiến trình chết và trường hợp TTL hết trước khi nghiệp vụ kết thúc. Không sử dụng một key có TTL như bằng chứng tuyệt đối rằng giao dịch bên ngoài chỉ thực hiện một lần.

Các cú pháp trên là ví dụ của Redis; không phải mọi kho key–value đều có cùng lệnh hoặc cùng cam kết về TTL, replication và durability.

## 6. TTL, cache và lưu trữ bền vững

**TTL (time to live)** quy định thời gian một mục dữ liệu được xem là hợp lệ. Nó phù hợp với session tạm thời, giỏ hàng bỏ quên, cache và tín hiệu chống trùng có giới hạn thời gian. Tuy nhiên, TTL **không tự biến dữ liệu thành an toàn để mất**.

Cần phân biệt ba chính sách:

| Chính sách | Ý nghĩa | Câu hỏi cần kiểm chứng |
|---|---|---|
| **Expiration / TTL** | Giá trị quá hạn không còn được phục vụ theo quy tắc của store | Key hết hạn có thể còn chiếm chỗ đến khi được dọn không? |
| **Eviction** | Hệ thống chủ động loại dữ liệu khi thiếu tài nguyên, tùy cấu hình | Có chấp nhận mất key trước TTL không? |
| **Durability** | Giá trị đã ghi có khả năng tồn tại sau lỗi tiến trình hoặc máy | Dữ liệu được đồng bộ xuống lưu trữ bền vững ở bước nào? |

Một ứng dụng có thể dùng key–value theo hai vai trò:

- **Cache:** cơ sở dữ liệu chính giữ nguồn dữ liệu đáng tin; cache giữ bản sao có TTL. Khi cache miss, ứng dụng đọc nguồn chính và nạp lại. Cần đề phòng cache stampede khi nhiều yêu cầu cùng miss.
- **Nguồn dữ liệu chính:** backend key–value chịu trách nhiệm lưu dữ liệu lâu dài. Lúc này phải lựa chọn cam kết ghi, bản sao, sao lưu, phục hồi và thử nghiệm mất máy theo khả năng của sản phẩm.

Ví dụ, Redis có các cơ chế persistence như snapshot RDB và append-only file (AOF), nhưng mức độ bền vững khi mất điện phụ thuộc cấu hình và thời điểm đồng bộ; replication đơn thuần không có nghĩa một ghi đã an toàn tuyệt đối. Một kho nhúng trên đĩa có thể dùng write-ahead log hoặc cấu trúc LSM-tree. Hãy đọc cam kết **acknowledgement → durability** của backend đang sử dụng, thay vì suy ra chỉ từ tên “database”.

Nếu dữ liệu là đơn hàng đã thanh toán, việc để key hết hạn sau 30 phút hoặc cho phép eviction là lựa chọn không phù hợp. Nếu dữ liệu là phiên xác thực, TTL và việc thu hồi sớm lại là yêu cầu nghiệp vụ cần thiết.

## 7. Tính nhất quán và cập nhật đồng thời

Xét hai request cùng tăng số lượng sản phẩm từ 1:

~~~text
Thời điểm    Request A                 Request B
t1           GET cart -> quantity 1
t2                                     GET cart -> quantity 1
t3           PUT cart -> quantity 2
t4                                     PUT cart -> quantity 2

Mong muốn: quantity 3. Kết quả có thể là 2 (lost update).
~~~

**Atomic GET** và **atomic PUT** riêng lẻ không tự khiến chuỗi **GET → sửa → PUT** trở thành một giao dịch. Khi có cập nhật cạnh tranh, chọn một trong các cơ chế phù hợp:

1. **Thao tác nguyên tử theo key:** dùng tăng số, thao tác trên cấu trúc hoặc script/transaction do backend bảo đảm; phù hợp khi thay đổi có thể diễn đạt thành một phép cập nhật tại server.
2. **Optimistic concurrency / compare-and-set:** đọc kèm version, ghi chỉ khi version hiện tại vẫn khớp; nếu thất bại thì đọc lại và quyết định retry. Điều kiện kiểm tra và ghi phải nguyên tử tại nơi lưu trữ.
3. **Transaction hoặc khóa phù hợp:** nếu cần cập nhật đồng thời nhiều key, phải xác minh backend có bảo đảm atomicity trong phạm vi đó hay không; phân vùng khác nhau có thể làm điều kiện thay đổi.

Trong hệ phân tán, còn có câu hỏi **đọc từ bản sao nào**. Một backend replication bất đồng bộ có thể trả về dữ liệu cũ từ replica sau khi writer đã nhận xác nhận. Nếu nghiệp vụ cần “ghi xong đọc thấy ngay”, phải chọn đường đọc và mức consistency đáp ứng điều kiện đó.

### Nhiều key và chỉ mục phụ

Giả sử lưu đơn hàng theo:

~~~text
order:v1:t42:o101   -> {"customerId":"u7","total":...}
order:v1:t42:o102   -> {"customerId":"u7","total":...}
~~~

Đọc theo order ID rất thuận tiện. Nhưng yêu cầu “liệt kê đơn của khách hàng u7 trong tháng này” **không thể được giải quyết hiệu quả chỉ bằng GET(orderId)**, vì ứng dụng chưa biết danh sách order ID cần đọc.

Có thể duy trì một chỉ mục phụ, ví dụ ánh xạ **orders-by-user:t42:u7 → tập order ID**, rồi GET từng đơn. Cách này đổi chi phí truy vấn lấy chi phí cập nhật: tạo, xóa, hoàn trả và chuyển trạng thái đơn có thể phải cập nhật nhiều key. Nếu một bước thành công và bước còn lại thất bại, chỉ mục sẽ lệch dữ liệu gốc. Cần giao dịch được hỗ trợ, cơ chế xử lý sự kiện có phục hồi, hoặc định kỳ đối soát tùy yêu cầu nhất quán. Trường hợp cần lọc, phân trang, sắp xếp và join phong phú có thể phù hợp hơn với cơ sở dữ liệu quan hệ hay kho tài liệu được lập chỉ mục.

**Phân biệt:** một số engine key–value duy trì khóa theo thứ tự, cho phép range scan hoặc prefix scan; một số khác thiên về hash lookup. Không nên giả định mọi backend đều hỗ trợ hoặc đều không hỗ trợ duyệt theo tiền tố.

## 8. Lỗi kết nối, retry và xử lý vận hành

Trong Java, gọi GET/PUT qua mạng không chỉ có hai kết quả “thành công” và “không tìm thấy”. Cần phân biệt:

- **Key vắng mặt:** kết quả nghiệp vụ bình thường của GET, thường được biểu diễn bằng Optional.empty().
- **Timeout hoặc mất kết nối:** không biết yêu cầu đã tới server hay chưa. Với PUT, có thể giá trị đã được ghi dù client chưa nhận phản hồi.
- **Conflict:** ghi có điều kiện thất bại vì version thay đổi; đây là trạng thái cạnh tranh, không đồng nghĩa backend hỏng.
- **Decode error:** key tồn tại nhưng payload sai định dạng; cần phân loại và xử lý thay vì coi như cache miss.
- **Unavailable / resource limit:** store hết bộ nhớ, quá nhiều kết nối, partition lỗi hoặc tạm thời không phục vụ.

Chỉ retry khi thao tác và chính sách nghiệp vụ cho phép. GET thường dễ retry hơn; PUT cùng value vào cùng key có thể idempotent trong một số điều kiện; thao tác tăng số hoặc tạo đơn hàng có tác dụng bên ngoài thì không tự an toàn khi retry. Dùng backoff có giới hạn, deadline và mã yêu cầu nhất quán. Ứng dụng nên đóng hoặc tái sử dụng kết nối bằng client/pool đúng cách; cấu hình timeout và connection pool theo lưu lượng thực.

Với dữ liệu quan trọng, các việc cần thử nghiệm bao gồm: khởi động lại node, lỗi mạng giữa lúc ghi, mất replica, khôi phục từ bản sao lưu và kiểm tra tính toàn vẹn của value sau phục hồi. **Backup** khác với **replica**: lỗi logic hoặc xóa nhầm có thể được sao chép sang các replica, trong khi bản sao lưu theo thời điểm giúp khôi phục về trạng thái trước đó.

## 9. Bảo mật và cô lập tenant

Key có chứa tenant ID chỉ là **quy ước địa chỉ**. Người dùng thuộc tenant t42 không được tự chọn tenant t43 rồi đọc key tương ứng. Tầng ứng dụng cần lấy tenant identity từ ngữ cảnh xác thực đáng tin cậy, kiểm tra quyền đối với bản ghi và giới hạn chức năng đọc/ghi. Khi backend hỗ trợ, bổ sung quyền truy cập theo phạm vi và tách môi trường sản xuất với thử nghiệm.

Sử dụng TLS khi có kết nối mạng, xác thực kết nối và quản lý secret ngoài mã nguồn. Mã hóa dữ liệu khi lưu theo yêu cầu tổ chức; tránh ghi toàn bộ key/value nhạy cảm vào log. Đối với dữ liệu có hạn lưu trữ pháp lý, TTL tại một kho chưa chắc giải quyết hết nghĩa vụ xóa tại backup, bản sao hoặc hệ thống downstream.

## 10. Hiệu năng, phân vùng và quan sát

Các thông số đáng đo bao gồm **p50/p95/p99 latency** cho GET và PUT, lưu lượng request/giây, tỷ lệ hit/miss, số timeout, conflict, kích thước value, memory/disk usage, độ trễ replication và lượng key bị eviction. Chỉ nhìn mức trung bình có thể bỏ sót một nhóm yêu cầu chậm bất thường.

Một số hướng tối ưu phải xuất phát từ đường truy cập thật:

| Triệu chứng | Nguyên nhân cần điều tra | Hướng cải thiện có điều kiện |
|---|---|---|
| Nhiều GET nhỏ nhưng chậm | Quá nhiều round trip hoặc pool thiếu kết nối | Multi-get, batching hoặc pipelining nếu backend hỗ trợ; đo lại độ trễ |
| Một key chịu tải rất cao | Hot key, tranh chấp ghi, một partition quá tải | Phân tán tải đọc, điều chỉnh dữ liệu hoặc cơ chế gom cập nhật |
| Value ngày càng lớn | Nhồi nhiều thực thể vào một blob | Tách key theo đơn vị truy cập và cập nhật |
| Cache miss tăng đột ngột | TTL đồng loạt, eviction, lỗi backend | TTL lệch pha, giới hạn tải nạp lại, kiểm tra capacity |
| Truy vấn theo thuộc tính quá chậm | Phải scan nhiều key/value | Tạo chỉ mục thích hợp hoặc chọn kho dữ liệu hỗ trợ truy vấn đó |
| Ghi tăng tải không đều | Phân phối khóa lệch hoặc partition nóng | Kiểm tra chiến lược partitioning và khóa sinh tải cao |

**Sharding / partitioning** thường dùng hàm ánh xạ từ key đến vùng lưu trữ. Vì thế việc chọn key ảnh hưởng đến cân bằng tải và khả năng truy cập liên quan nhiều key. Phân tán giá trị sang nhiều shard có thể cải thiện throughput, nhưng làm các giao dịch nhiều key phức tạp hơn. Không tự thiết kế lại key chỉ để có chuỗi “ngẫu nhiên” mà chưa kiểm tra chính sách phân vùng của backend.

## 11. Khi nào chọn mô hình khóa–giá trị?

| Bài toán | Độ phù hợp | Lý do và điều kiện |
|---|---|---|
| Session theo session ID | **Cao** | Lookup trực tiếp, TTL rõ ràng; cần chính sách thu hồi và bảo vệ token |
| Giỏ hàng theo cart ID | **Cao đến trung bình** | Đọc/ghi theo khóa thuận tiện; phải giải quyết lost update và chọn độ bền vững |
| Trạng thái idempotency theo request ID | **Cao khi thiết kế đúng** | Cần thao tác điều kiện nguyên tử và vòng đời trạng thái hoàn chỉnh |
| Hồ sơ người dùng chỉ tìm theo user ID | **Cao** | Đường đọc cố định, value thường được lấy nguyên cụm |
| Danh sách đơn hàng có lọc nhiều điều kiện | **Thấp nếu chỉ có GET(key)** | Cần chỉ mục phụ, sắp xếp, phân trang và nhất quán khi cập nhật |
| Kế toán, chuyển tiền giữa nhiều tài khoản | **Phụ thuộc backend, thường cần mô hình giao dịch mạnh hơn** | Nhiều bản ghi phải giữ bất biến cùng lúc và có yêu cầu kiểm toán |

Chọn mô hình dựa trên **câu hỏi mà ứng dụng thực sự cần trả lời** và **điều kiện dữ liệu phải giữ đúng**. Một API GET rất nhanh không bù được việc không truy vấn được theo yêu cầu nghiệp vụ hoặc không bảo vệ được cập nhật đồng thời.

## 12. Bài thực hành: thiết kế persistence cho giỏ hàng

Một dịch vụ Java phục vụ nhiều cửa hàng. Mỗi giỏ được xác định bởi **tenantId + cartId**, có danh sách SKU và số lượng, hết hạn sau 30 phút không hoạt động. Hai thiết bị của cùng người dùng có thể cập nhật giỏ đồng thời. Khách hàng không được đọc giỏ của tenant khác.

**Yêu cầu thiết kế:**

1. Đề xuất mẫu key có thể tạo lại chính xác và giải thích cách kiểm tra từng thành phần.
2. Đề xuất payload có **schemaVersion** và **version**, giải thích khi nào tăng mỗi trường.
3. Mô tả GET và PUT với TTL; nêu điều gì xảy ra nếu backend không còn key, lỗi kết nối hoặc không giải mã được value.
4. Chọn cơ chế chống lost update khi hai thiết bị sửa giỏ cùng lúc. Trình bày một tình huống cần retry vì conflict.
5. Quyết định giỏ là dữ liệu chính hay cache có thể dựng lại; từ đó xác định durability, eviction, backup và cách khôi phục.
6. Nêu cách đo hiệu năng dưới tải, bao gồm ít nhất p95 cho GET/PUT và các lỗi timeout/conflict.

**Một hướng giải quyết:** dùng key **cart:v1:{tenantId}:{cartId}** với các thành phần đã kiểm tra, value gồm **schemaVersion**, **version** và items, TTL được gia hạn khi lưu thành công. Ghi bằng compare-and-set theo version tại server; nếu thất bại, đọc lại để hợp nhất thay đổi theo luật nghiệp vụ trước khi thử lại có giới hạn. Lấy tenant từ phiên đã xác thực. Nếu giỏ là nguồn dữ liệu chính, chọn backend và cấu hình lưu bền vững tương ứng, không cho eviction tùy ý. Cách giải quyết này vẫn cần kiểm thử race condition, timeout sau ghi, TTL và phục hồi dữ liệu.

### Tự kiểm tra kiến thức

- Vì sao biết **customerId** chưa đủ để GET trực tiếp đơn hàng nếu key của đơn được đặt theo **orderId**?
- Tại sao hai thao tác GET và PUT riêng lẻ thành công vẫn có thể gây mất cập nhật?
- TTL, eviction và durability khác nhau ở điểm nào?
- Nếu client timeout khi PUT, vì sao không thể mặc định kết luận rằng server chưa ghi?
- Khi thêm trường mới vào JSON value, cần làm gì để ứng dụng vẫn đọc được dữ liệu cũ?

Sau bài học, người học cần có khả năng thiết kế key ổn định, mô tả đường truy cập trực tiếp, triển khai cổng persistence trong Java và chỉ ra lúc nào mô hình khóa–giá trị đủ dùng hoặc cần một mô hình/chỉ mục khác.

# Khóa nghiệp vụ, khóa kỹ thuật và phạm vi duy nhất

Trong cơ sở dữ liệu NoSQL, câu hỏi “dùng trường nào làm khóa?” thường phức tạp hơn việc chọn một `_id` hoặc một UUID. Một bản ghi có thể có **mã nghiệp vụ người dùng nhận ra**, **định danh kỹ thuật ổn định để hệ thống tham chiếu**, **khóa phân vùng để phân phối dữ liệu**, và **ràng buộc duy nhất chỉ đúng trong một phạm vi cụ thể**.

Ví dụ, hai cửa hàng độc lập có thể cùng bán sản phẩm mã `SP-001`. Mã ấy có thể duy nhất **trong từng cửa hàng**, nhưng không duy nhất **trên toàn nền tảng**. Một sản phẩm cũng có thể đổi mã bán hàng mà vẫn là sản phẩm cũ. Nếu dùng trực tiếp mã sản phẩm làm định danh bất biến của mọi liên kết, lần đổi mã đó có thể kéo theo hàng loạt cập nhật và làm hỏng các bản ghi lịch sử.

Tư duy thiết kế tốt bắt đầu bằng ba câu hỏi:

1. **Khóa nào biểu diễn danh tính nghiệp vụ?** Người dùng và quy trình đang nhận diện “cùng một đối tượng” bằng quy tắc nào?
2. **Khóa nào ổn định để lưu trữ, tham chiếu và tích hợp?** Giá trị đó có còn hợp lệ khi tên, mã hiển thị hoặc cấu trúc nghiệp vụ thay đổi không?
3. **Duy nhất trong phạm vi nào và tại thời điểm nào?** Toàn hệ thống, một tenant, một cửa hàng, một chiến dịch hay chỉ giữa các bản ghi đang hoạt động?

Bài học sử dụng ví dụ từ document database và các hệ NoSQL phân tán. Khả năng áp đặt uniqueness, transaction và partition của từng hệ quản trị khác nhau; các ví dụ MongoDB là minh họa cụ thể, không phải cú pháp áp dụng cho mọi NoSQL.

## 1. Trước hết, “khóa” có thể chỉ những vai trò khác nhau

| Khái niệm | Mục đích chính | Ví dụ | Câu hỏi phải hỏi |
|---|---|---|---|
| **Khóa nghiệp vụ (business key)** | Định danh theo quy tắc của tổ chức hoặc thế giới thực | SKU, mã nhân viên, mã hợp đồng, mã đơn hàng bên ngoài | Ai cấp mã, mã có đổi được, có tái sử dụng không? |
| **Khóa kỹ thuật (surrogate/technical key)** | Tạo định danh ổn định cho hệ thống lưu trữ, API và tham chiếu | ObjectId, UUID, ULID, số ID được cấp tập trung | ID có ổn định, đủ duy nhất và không phụ thuộc thuộc tính nghiệp vụ không? |
| **Khóa chính / định danh mục (primary/item key)** | Định vị hoặc nhận diện một mục theo mô hình của DB | MongoDB `_id`; DynamoDB partition key + sort key | DB đảm bảo gì với khóa này, trong phạm vi nào? |
| **Partition/shard key** | Quyết định cách dữ liệu phân tán | `tenantId`, `deviceId`, khóa tổng hợp | Có phân phối được cả dung lượng và truy cập không? |
| **Khóa tổng hợp (composite key)** | Phối hợp nhiều trường để xác định một mục hoặc phạm vi | `(tenantId, skuKey)` | Thứ tự, kiểu và cách chuẩn hóa từng thành phần là gì? |
| **Khóa tham chiếu (reference key)** | Nối quan hệ logic giữa các document/thực thể | `productId` trong dòng đơn hàng | Khi dữ liệu đích đổi tên hoặc bị xóa thì xử lý ra sao? |
| **Idempotency key** | Nhận biết một thao tác gửi lặp lại | `(tenantId, requestId)` | Trùng request phải trả lại kết quả trước hay từ chối? |

**Một trường có thể đảm nhiệm nhiều vai trò**, nhưng các vai trò không tự động đồng nhất. Ví dụ `_id` là định danh tài liệu trong MongoDB, nhưng không nhất thiết là mã đơn hàng gửi cho khách. Tương tự, một trường được dùng làm shard key chưa chắc là business key duy nhất.

Cần phân biệt **identity** và **equality**:

- Hai document có cùng tên hiển thị không có nghĩa chúng là cùng một thực thể.
- Hai document có cùng mã nghiệp vụ trong hai tenant khác nhau có thể đều hợp lệ.
- Một document đổi mã nghiệp vụ vẫn có thể giữ nguyên danh tính.
- Hai lần nhận cùng một sự kiện không nhất thiết tạo hai bản ghi nghiệp vụ.

## 2. Khóa nghiệp vụ: có ý nghĩa nhưng không mặc nhiên bất biến

Khóa nghiệp vụ thường do tổ chức, đối tác hoặc quy trình cấp. Một số ví dụ:

- `sku`: mã quản lý hàng hóa của một nhà bán.
- `employeeCode`: mã nhân viên theo quy định công ty.
- `invoiceNumber`: số hóa đơn thuộc một đơn vị phát hành và chuỗi đánh số.
- `externalOrderId`: mã đơn hàng tại hệ thống đối tác.
- `username`: tên đăng nhập theo chính sách của một dịch vụ.
- `email` hoặc `phone`: thông tin liên lạc, đôi khi được dùng để đăng nhập.

Khóa nghiệp vụ có điểm mạnh: dễ nhận diện, dùng được trong trao đổi nghiệp vụ, kiểm tra trùng, tìm kiếm, đối soát và tích hợp. Nhưng cần hỏi rõ các tính chất sau.

### 2.1. Ai tạo khóa và ai được sửa?

Mã SKU có thể do nhà bán tự nhập, hệ thống sinh theo dãy số hoặc được import từ phần mềm kho. Nếu người bán được đổi SKU, hệ thống phải quyết định việc đổi mã có giữ nguyên `productId` hay tạo sản phẩm mới. Thông thường, đổi mã chỉ là đổi thuộc tính của cùng một thực thể, không phải thay danh tính kỹ thuật.

Mã từ đối tác cũng có thể đổi khi đối tác di chuyển hệ thống, gộp dữ liệu hoặc sửa lỗi. Khi đó, khóa liên kết bên ngoài cần gắn kèm **nguồn cấp** và chính sách cập nhật.

### 2.2. Khóa có thực sự duy nhất?

“Email duy nhất” nghe có vẻ rõ, nhưng thực tế cần xác định:

- Có cho phép một email gắn với nhiều tài khoản phụ hoặc nhiều tenant không?
- Có coi chữ hoa và chữ thường là tương đương không?
- Có xử lý Unicode trong domain và phần local-part theo chính sách nào?
- Khi xóa tài khoản, email được dùng lại ngay hay phải giữ trong thời gian chờ?
- Một người có thể thay email không? Nếu thay, lịch sử giao dịch tham chiếu thế nào?

Không nên tự cho rằng email, số điện thoại hoặc tên thật là danh tính bất biến của con người. Những thuộc tính này có thể đổi, được chia sẻ, bị thu hồi hoặc được cấp lại. Nếu dùng chúng để đăng nhập hay đối soát, cần định nghĩa quy tắc chứng minh quyền sở hữu, chuẩn hóa và tái sử dụng.

### 2.3. Khóa có ý nghĩa theo thời gian không?

Một mã hợp đồng được cấp cho từng năm có thể chỉ duy nhất theo `(organizationId, year, contractNo)`. Mã `001` trong năm 2025 và mã `001` trong năm 2026 có thể là hai hợp đồng hợp lệ.

Nếu bỏ năm khỏi định nghĩa khóa chỉ vì nghĩ “contractNo phải unique”, hệ thống sẽ chặn những bản ghi hợp lệ. Ngược lại, nếu quy định pháp lý hay nghiệp vụ yêu cầu mã không được tái sử dụng, việc cho phép trùng sau khi xóa là sai.

## 3. Khóa kỹ thuật: giữ danh tính ổn định

Khóa kỹ thuật thường không có ý nghĩa nghiệp vụ trực tiếp. Ví dụ:

~~~json
{
  "_id": "db-internal-opaque-id",
  "productId": "01992bd3-1e4d-7f0c-9c17-6c17d0a42210",
  "tenantId": "shop-17",
  "sku": "SP-001",
  "name": "Bàn phím cơ"
}
~~~

Trong document minh họa này:

- `_id` là định danh document theo cách tổ chức lưu trữ đã chọn.
- `productId` là ID kỹ thuật dùng ổn định ở các API và trong tham chiếu. Nó có thể trùng với `_id` nếu không cần hai lớp ID.
- `tenantId` xác định tổ chức sở hữu và phạm vi của nhiều quy tắc.
- `sku` là khóa nghiệp vụ; có thể đổi theo quy trình.
- `name` chỉ là thuộc tính mô tả, không phù hợp làm danh tính.

Việc có cả `_id` và `productId` **không phải yêu cầu bắt buộc**. Nếu có hai định danh, phải nêu lý do cụ thể: chẳng hạn ID lưu trữ nội bộ độc lập với định dạng public API, hoặc cần migration giữa kho dữ liệu mà không thay đổi ID công khai. Mỗi ID bổ sung kéo theo index, quy tắc mapping và nguy cơ lệch dữ liệu.

### 3.1. Một khóa kỹ thuật tốt thường cần gì?

- **Ổn định:** không đổi khi tên, SKU hoặc nơi lưu trữ thay đổi.
- **Đủ duy nhất trong phạm vi mục tiêu:** tránh va chạm khi nhiều producer tạo đồng thời.
- **Có thể truyền, lưu và đối chiếu nhất quán:** kiểu dữ liệu và định dạng thống nhất giữa các dịch vụ.
- **Không đưa thông tin nhạy cảm vào ID nếu không cần:** ID công khai không nên tiết lộ số giấy tờ, email hoặc mô hình kinh doanh.
- **Có kế hoạch cho scale và nhập dữ liệu:** ID tạo phân tán có cần bộ cấp số tập trung không; có an toàn khi merge dữ liệu không?
- **Tương thích với truy vấn:** kiểu ID ảnh hưởng index, độ dài key và thứ tự lưu trữ tùy engine.

### 3.2. Chọn định dạng định danh kỹ thuật

| Cách tạo ID | Điểm mạnh | Cân nhắc |
|---|---|---|
| **UUID v4** | Sinh phân tán, khó đoán từ trình tự cấp số | Kích thước tương đối lớn; tính ngẫu nhiên có thể ảnh hưởng locality của một số index |
| **UUID v7** | Chứa thành phần thời gian, có tính sắp xếp gần thời gian | Vẫn phải hiểu cơ chế sinh và va chạm; có thể lộ thứ tự/thời điểm gần đúng |
| **ULID** | Dạng chuỗi có thể sắp xếp theo thời gian khi dùng đúng đặc tả | Cần thống nhất encoding, tính đơn điệu trong cùng mili giây và xử lý clock |
| **MongoDB ObjectId** | Phù hợp hệ sinh thái MongoDB; tạo phân tán trong driver | Không đại diện cho thời gian chính xác tuyệt đối hay danh tính nghiệp vụ; không là secret |
| **Số tăng dần** | Ngắn, dễ đọc và có locality tốt ở một số hệ | Cần thiết kế cấp số khi phân tán; dễ đoán và có thể tạo điểm nghẽn |
| **ID tự thiết kế có prefix** | Dễ nhận loại thực thể, ví dụ `prod_...` | Cần bảo đảm phần sinh ID đủ duy nhất, format và validator đồng nhất |

Không có định dạng nào tự quyết định toàn bộ tính đúng đắn. Một UUID có xác suất va chạm rất thấp vẫn nên kết hợp với ràng buộc khóa thích hợp tại nơi lưu, xử lý lỗi va chạm và cơ chế nhận biết request lặp.

**ID không phải mật khẩu hay quyền truy cập.** Dù ID ngẫu nhiên, service vẫn phải kiểm tra người gọi có quyền đọc hoặc sửa tài nguyên đó.

## 4. Phạm vi duy nhất: viết thành một câu đầy đủ

Phát biểu “SKU unique” chưa đủ để viết index. Cần nói rõ: **unique theo những thành phần nào, trong tập bản ghi nào, tại thời điểm nào, với chuẩn so sánh nào**.

Các dạng thường gặp:

| Yêu cầu nghiệp vụ | Phạm vi duy nhất | Ví dụ hai giá trị giống nhau có hợp lệ? |
|---|---|---|
| Mã khách hàng do toàn nền tảng cấp | Toàn tập khách hàng | Không, nếu chính sách cấm tái sử dụng |
| SKU của từng cửa hàng | `(tenantId, skuKey)` | Có, khi thuộc hai tenant khác nhau |
| Mã nhân viên trong chi nhánh | `(companyId, branchId, employeeCodeKey)` | Có, nếu ở chi nhánh khác và công ty cho phép |
| Số dòng trong một đơn hàng | `(orderId, lineNumber)` | Có, cùng lineNumber trong đơn khác |
| Mã đơn hàng đối tác | `(providerId, externalOrderId)` | Có, giữa hai đối tác độc lập |
| Mã giảm giá theo chiến dịch | `(campaignId, couponCodeKey)` | Có, nếu chiến dịch khác nhau |
| SKU chỉ unique giữa sản phẩm ACTIVE | `(tenantId, skuKey)` trên tập `status = ACTIVE` | Có thể, giữa các bản ghi không ACTIVE theo chính sách |
| Chỗ đặt trong một suất chiếu | `(showtimeId, seatId)` trên tập chỗ đã giữ/đặt | Không, với hai đặt chỗ hiệu lực cho cùng ghế |

Một số trường hợp phải tính cả **thời gian hiệu lực**. Ví dụ phòng họp không thể có hai lịch đặt chồng lấn trong cùng khoảng thời gian. Unique index trên `(roomId, startAt)` chỉ ngăn hai lịch có cùng giờ bắt đầu, **không chặn** lịch 09:00–10:00 và lịch 09:30–10:30. Quy tắc không chồng lấn cần mô hình dữ liệu và cơ chế đồng thời riêng.

### Mô hình hóa uniqueness theo tập hợp

Với mỗi sản phẩm `p` có `tenantId` và `skuKey`, quy tắc “SKU duy nhất trong tenant giữa các sản phẩm đang hoạt động” được diễn đạt:

\[
\forall p \ne q,\ 
(p.status = ACTIVE \land q.status = ACTIVE \land p.tenantId=q.tenantId)
\Rightarrow p.skuKey \ne q.skuKey
\]

Đọc bằng lời: với hai sản phẩm **đang ACTIVE** khác nhau nhưng thuộc **cùng tenant**, khóa SKU đã chuẩn hóa phải khác nhau.

Phát biểu này giúp tránh ba nhầm lẫn: không cấm các tenant khác nhau dùng cùng SKU; không lấy SKU thô chưa chuẩn hóa; và chỉ áp dụng cho trạng thái ACTIVE. Nếu nghiệp vụ đòi mã không bao giờ tái sử dụng, bỏ điều kiện ACTIVE và giữ mã đã dùng trong một registry có vòng đời rõ ràng.

## 5. Ví dụ xuyên suốt: sản phẩm thuộc nhiều tenant

Xét nền tảng quản lý kho cho nhiều cửa hàng. Một sản phẩm có:

~~~json
{
  "_id": "opaque-document-id",
  "productId": "p-8472",
  "tenantId": "shop-17",
  "sku": " Sp-001 ",
  "skuKey": "SP-001",
  "name": "Bàn phím cơ",
  "status": "ACTIVE"
}
~~~

Ở đây `sku` có thể giữ nguyên cách người dùng nhập để hiển thị. `skuKey` là giá trị **chuẩn hóa nhất quán** dùng để kiểm tra trùng, tìm kiếm bằng mã và tạo unique index. Hệ thống phải định nghĩa các bước chuẩn hóa trước khi ghi; ví dụ minh họa có thể là trim khoảng trắng ở hai đầu và chuyển chữ Latin thành in hoa theo quy tắc cố định.

**Bất biến cần giữ:**

1. `productId` là định danh kỹ thuật, không đổi trong suốt đời sản phẩm.
2. `tenantId` là phạm vi sở hữu, không lấy từ request nếu người gọi không được quyền chọn tenant.
3. Hai sản phẩm ACTIVE cùng tenant không được có cùng `skuKey`.
4. Hai tenant khác nhau được phép dùng cùng `skuKey`.
5. Đổi `sku` không làm đổi `productId`, nhưng phải kiểm tra mã mới và xử lý tham chiếu/đồng bộ nghiệp vụ.
6. Nếu sản phẩm không ACTIVE có thể trùng SKU, phải có quy tắc khi phục hồi trạng thái ACTIVE.

Một khóa tổng hợp thường hợp lý hơn giả định SKU tự nó là toàn cục. Quan trọng hơn, cần nắm rõ **phạm vi duy nhất và phạm vi truy cập là hai vấn đề riêng**: index `(tenantId, skuKey)` không thay thế kiểm tra phân quyền tenant.

## 6. Chuẩn hóa khóa nghiệp vụ trước khi xét duy nhất

Hai chuỗi nhìn gần giống nhau có thể được lưu thành các byte khác nhau:

~~~text
"SP-001"
"sp-001"
" SP-001 "
"SP-００１"   # chữ số full-width Unicode
"SP-001 "     # khoảng trắng cuối
~~~

Nếu nghiệp vụ xem chúng là cùng một mã, unique index trên chuỗi thô có thể không bảo vệ được quy tắc mong muốn.

### 6.1. Chính sách chuẩn hóa cần được công bố

Một chính sách đơn giản cho SKU chỉ gồm ký tự ASCII có thể là:

1. Trim khoảng trắng ở đầu/cuối.
2. Chỉ cho phép `A-Z`, `0-9` và dấu gạch nối.
3. Chuyển chữ cái ASCII thành in hoa.
4. Giới hạn độ dài và cấm chuỗi rỗng.
5. Lưu riêng `sku` hiển thị và `skuKey` dùng kiểm tra duy nhất nếu cần.

~~~java
import java.util.Locale;
import java.util.regex.Pattern;

public final class SkuKey {
    private static final Pattern ALLOWED =
        Pattern.compile("[A-Z0-9-]{1,40}");

    private SkuKey() {}

    public static String from(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("SKU is required");
        }

        String normalized = raw.trim().toUpperCase(Locale.ROOT);

        if (!ALLOWED.matcher(normalized).matches()) {
            throw new IllegalArgumentException("Invalid SKU format");
        }

        return normalized;
    }
}
~~~

Đây là chính sách **minh họa dành cho SKU ASCII**, không phải giải pháp đúng cho mọi ngôn ngữ hay mọi mã định danh. Nếu cho phép Unicode, cần xác định Unicode normalization (NFC hay NFKC), case folding, xử lý ký tự trông giống nhau, khoảng trắng và chính sách locale. Không tùy tiện loại dấu tiếng Việt hoặc gộp ký tự khác nhau nếu nghiệp vụ không cho phép.

### 6.2. Phân biệt chuẩn hóa và biến đổi ý nghĩa

- Chuyển `"sp-001"` thành `"SP-001"` có thể hợp lệ khi chính sách quy định SKU không phân biệt hoa/thường.
- Chuyển mọi dấu gạch nối thành chuỗi rỗng sẽ làm `"AB-12"` và `"A-B12"` thành cùng mã; đây là quyết định nghiệp vụ, không phải thao tác kỹ thuật vô hại.
- Chuẩn hóa số điện thoại theo định dạng quốc tế cần thư viện/phân tích số phù hợp với vùng; chỉ xóa tất cả ký tự không phải số chưa đủ để hiểu đúng số.
- Email có các chi tiết phức tạp về domain, local-part và chính sách nhà cung cấp. Không tự áp dụng quy tắc dấu chấm hay dấu cộng của một nhà cung cấp cho mọi địa chỉ.

**Cùng một phiên bản chuẩn hóa phải được dùng trong tất cả đường ghi**: API, import, message consumer, migration và công cụ quản trị. Nếu cập nhật chính sách chuẩn hóa, phải dự đoán khả năng hai mã trước đây khác nhau trở thành trùng nhau sau chuẩn hóa.

## 7. Áp đặt uniqueness trong MongoDB

Với một collection chưa sharding, MongoDB có unique index bảo vệ tính duy nhất của các giá trị index trong collection. Ví dụ yêu cầu hai sản phẩm ACTIVE cùng tenant không trùng mã SKU:

~~~javascript
db.products.createIndex(
  { tenantId: 1, skuKey: 1 },
  {
    name: "uq_active_sku_per_tenant",
    unique: true,
    partialFilterExpression: { status: "ACTIVE" }
  }
);
~~~

Ý nghĩa:

- Tổ hợp `(tenantId, skuKey)` quyết định khóa so sánh.
- Chỉ document có `status: "ACTIVE"` nằm trong phạm vi unique index này.
- Một SKU có thể xuất hiện ở nhiều tenant khác nhau.
- Bản ghi không ACTIVE có thể trùng nhau theo điều kiện index, nhưng việc chuyển chúng trở lại ACTIVE sẽ bị kiểm tra.
- Index không thay thế validation: mọi bản ghi ACTIVE cần có `tenantId` và `skuKey` hợp lệ, đúng kiểu và đã chuẩn hóa.

Ví dụ dữ liệu:

~~~javascript
db.products.insertMany([
  {
    _id: "doc-101",
    productId: "p-101",
    tenantId: "shop-17",
    sku: "SP-001",
    skuKey: "SP-001",
    name: "Bàn phím cơ",
    status: "ACTIVE"
  },
  {
    _id: "doc-102",
    productId: "p-102",
    tenantId: "shop-42",
    sku: "sp-001",
    skuKey: "SP-001",
    name: "Bàn phím mỏng",
    status: "ACTIVE"
  }
]);
~~~

Cả hai document hợp lệ vì thuộc **hai tenant khác nhau**. Nếu tiếp tục tạo một document ACTIVE với `tenantId = "shop-17"` và `skuKey = "SP-001"`, thao tác sẽ bị unique index từ chối khi collection có index hoạt động đúng như đã khai báo.

Trong hệ thống thật, cần thêm ràng buộc cho `productId` theo phạm vi lựa chọn. Ví dụ nếu `productId` phải duy nhất toàn collection:

~~~javascript
db.products.createIndex(
  { productId: 1 },
  { name: "uq_product_id", unique: true }
);
~~~

Nếu `productId` chỉ duy nhất trong tenant, thay bằng index tổng hợp phù hợp và để API/quan hệ tham chiếu mang đủ `tenantId`. Đừng để “ID có vẻ ngẫu nhiên” thay thế ràng buộc uniqueness được yêu cầu.

### 7.1. Trường thiếu, `null` và partial index

Không thể bỏ qua dữ liệu thiếu chỉ vì index có `unique: true`. Với unique index một trường trong MongoDB, trường thiếu và giá trị `null` ảnh hưởng đến key được index; không mặc nhiên có thể lưu vô số document thiếu trường. Với compound index, các tổ hợp giá trị và trường thiếu cũng có hành vi riêng.

Có ba quyết định khác nhau:

- **Bắt buộc có khóa:** dùng schema validation và kiểm tra đầu vào để mọi document cần ràng buộc đều có giá trị hợp lệ.
- **Chỉ áp dụng unique cho tập con:** dùng partial index với điều kiện có nghĩa nghiệp vụ, chẳng hạn `status = ACTIVE`.
- **Cho phép giá trị tùy chọn thật sự:** xác định rõ `missing`, `null`, chuỗi rỗng và giá trị mặc định là giống hay khác nhau.

Partial index trong ví dụ dựa vào `status`, **không tự đảm bảo** rằng document ACTIVE luôn có `skuKey`. Một hệ thống sai dữ liệu có thể vẫn gặp xung đột ở những document thiếu trường. Chính sách validation phải được thiết kế cùng index.

### 7.2. Soft delete và tái kích hoạt

Giả sử sản phẩm `p-101` có SKU `SP-001` được đánh dấu `DELETED`. Theo partial unique index, hệ thống có thể tạo sản phẩm mới `p-999` ACTIVE với cùng SKU. Sau đó muốn phục hồi `p-101` thành ACTIVE sẽ gặp xung đột.

Do đó phải chọn rõ:

- Có cho phép tái sử dụng SKU sau xóa không?
- Có thời gian giữ mã hay không?
- Khi restore gặp mã đã được sử dụng, cần đổi mã, hủy thao tác hay hợp nhất dữ liệu?
- Lịch sử đơn hàng vẫn tham chiếu sản phẩm nào?

Nếu một SKU **không được tái sử dụng vĩnh viễn** dù sản phẩm đã bị xóa, partial unique index chỉ trên ACTIVE **không đáp ứng yêu cầu**. Khi ấy cần giữ ràng buộc trên toàn bộ bản ghi hoặc có registry/tombstone lưu mã đã cấp.

### 7.3. Unique index và sharding

Khi collection được sharding, quy tắc unique index của MongoDB bị giới hạn bởi cách chọn shard key. Không được suy ra rằng một unique index tùy ý có thể bảo đảm uniqueness toàn cluster. Với nhiều cấu hình, unique index cần có **shard key làm tiền tố**, và cơ chế áp đặt unique cho `_id` có điểm cần chú ý khi `_id` không phải shard key.

Ví dụ, nếu chọn shard key bắt đầu bằng `tenantId`, cần kiểm tra xem index `(tenantId, skuKey)` có thỏa các giới hạn của phiên bản MongoDB và kiểu sharding được dùng hay không. Nếu shard key là một tổ hợp khác hoặc dùng hashed sharding, lựa chọn index uniqueness có thể bị hạn chế.

Vì vậy, **thiết kế phạm vi duy nhất và chọn shard key phải đi cùng nhau**. Nếu cần uniqueness toàn cục theo một khóa không thể áp đặt bằng index hiện có, phải thiết kế thêm cơ chế cấp phát/claim khóa nhất quán, mô hình phân vùng khác hoặc thay đổi kiến trúc. Không nên hứa “unique toàn hệ thống” chỉ vì chạy lệnh tạo index thành công trong môi trường không sharding.

## 8. Kiểm tra trùng trong service chưa đủ khi có đồng thời

Một cách triển khai dễ gặp:

~~~text
1. SELECT xem SKU đã tồn tại chưa
2. Nếu chưa tồn tại thì INSERT sản phẩm
~~~

Hai request đến gần như đồng thời có thể cùng thấy “chưa có” rồi cùng ghi. Đây là trường hợp **check-then-act race**.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: Tìm SKU SP-001 (chưa có)
    B->>DB: Tìm SKU SP-001 (chưa có)
    DB-->>A: Không tìm thấy
    DB-->>B: Không tìm thấy
    A->>DB: Insert SP-001
    B->>DB: Insert SP-001
    DB-->>A: Thành công
    DB-->>B: Duplicate key (unique index)
~~~

Nếu **không có cơ chế áp đặt uniqueness thực sự** ở lớp ghi, cả hai insert có thể thành công. Bước truy vấn trước giúp trả thông báo thân thiện nhưng **không là hàng rào cuối cùng**.

Cách xử lý đúng với MongoDB khi ràng buộc phù hợp:

1. Chuẩn hóa SKU trong service.
2. Xác định tenant từ ngữ cảnh đã được xác thực.
3. Ghi document.
4. Unique index chặn xung đột đồng thời.
5. Service bắt lỗi duplicate-key và ánh xạ thành lỗi nghiệp vụ có ý nghĩa, chẳng hạn HTTP `409 Conflict`.
6. Nếu request có thể được gửi lại, cân nhắc idempotency key để phân biệt yêu cầu lặp với hai yêu cầu tạo khác nhau.

Ví dụ pseudo-code Java/Spring:

~~~java
public Product createProduct(CreateProductRequest request, TenantContext tenant) {
    String skuKey = SkuKey.from(request.sku());

    Product product = new Product(
        createTechnicalId(),
        tenant.id(),
        request.sku(),
        skuKey,
        request.name(),
        "ACTIVE"
    );

    try {
        return productRepository.insert(product);
    } catch (DuplicateKeyException exception) {
        throw new BusinessConflictException(
            "SKU đã được sử dụng trong cửa hàng này"
        );
    }
}
~~~

Đây là **mã minh họa luồng xử lý**, các class `Product`, `TenantContext` và exception nghiệp vụ phải được định nghĩa trong dự án thật. Nếu có nhiều unique index, nên phân biệt index nào gây lỗi để không trả sai thông báo (ví dụ trùng `productId` không nên luôn được diễn giải là trùng SKU). Không dựa vào chuỗi thông điệp lỗi database không ổn định làm hợp đồng nghiệp vụ.

## 9. Khóa phân vùng khác với khóa duy nhất

Nhiều hệ NoSQL phân tán dùng partition/shard key nhằm phân bố dữ liệu và điều phối truy vấn. Ràng buộc duy nhất là một bài toán khác.

Một partition key tốt cần cân nhắc:

- Số lượng giá trị khóa đang hoạt động có đủ lớn không?
- Ghi và đọc có phân bố đều theo khóa không?
- Có tenant hoặc sản phẩm cực lớn làm hot partition không?
- Những query quan trọng có thể định vị partition hiệu quả không?
- Key có đổi thường xuyên không?
- Tạo index, transaction và unique constraint có bị ràng buộc bởi cách phân vùng không?

Ví dụ dùng `tenantId` làm partition key giúp truy vấn dữ liệu theo tenant thuận tiện trong một số mô hình, nhưng một tenant lớn có thể gây tải lệch. Dùng `productId` có tính phân tán hơn đối với nhiều sản phẩm nhưng truy vấn tổng hợp theo tenant có thể phải tìm trên nhiều partition.

**Đừng chọn shard key chỉ vì nó unique.** Một khóa rất duy nhất vẫn có thể tạo bất lợi cho các truy vấn quan trọng; một khóa thuận truy vấn có thể khiến tải dồn một nơi.

### 9.1. Cần phân biệt giới hạn của từng hệ quản trị

| Hệ / mô hình | Định danh và uniqueness thường được đảm bảo ở đâu? | Điều cần kiểm tra trước khi thiết kế |
|---|---|---|
| **MongoDB** | `_id`, unique index; với sharding có hạn chế theo shard key | Chế độ sharding, tiền tố shard key, partial index, phạm vi `_id` |
| **Amazon DynamoDB** | Khóa chính của item: partition key hoặc cặp partition key + sort key | Uniqueness của thuộc tính khác không tự có nhờ GSI; cần conditional write hoặc mô hình claim/transaction |
| **Apache Cassandra** | Primary key gồm partition key và clustering columns, xác định hàng | Ghi cùng primary key có thể cập nhật/ghi đè; xét `IF NOT EXISTS` và chi phí lightweight transaction khi cần tạo duy nhất |
| **Redis** | Phụ thuộc kiểu dữ liệu và lệnh điều kiện như `SET NX` | Một khóa Redis/lock không tự trở thành nguồn sự thật bền vững cho invariant nghiệp vụ của DB khác |
| **Graph DB** | Phụ thuộc engine, constraint cho thuộc tính node/edge | Tên loại node, phạm vi label và semantics của unique constraint |

Đặc biệt trong DynamoDB, một bảng có `PK = tenantId` và `SK = productId` chỉ áp đặt duy nhất cho **cặp** `(tenantId, productId)` của item đó. Nó không tự ngăn hai item cùng tenant có chung trường `skuKey`. Nếu SKU cần duy nhất, có thể thiết kế item claim theo `(tenantId, skuKey)` và thực hiện ghi điều kiện/transaction phù hợp, hoặc thay đổi cách tạo primary key. Global secondary index không tự trở thành unique constraint trên giá trị index.

### 9.2. Ví dụ thiết kế khóa dạng composite trong DynamoDB

Một ứng dụng có thể lưu item với:

~~~text
PK = TENANT#shop-17
SK = PRODUCT#p-101
skuKey = SP-001
~~~

Cặp `(PK, SK)` xác định duy nhất item, nhưng sản phẩm `p-102` với `SK = PRODUCT#p-102` và cùng `skuKey = SP-001` vẫn có thể được tạo nếu ứng dụng không thêm cơ chế chặn.

Một mẫu khác có thể dùng item dành riêng cho claim:

~~~text
PK = TENANT#shop-17
SK = SKU#SP-001
ownerProductId = p-101
~~~

Ứng dụng dùng **conditional create** để chỉ một request giành được claim này, đồng thời dùng transaction để phối hợp tạo sản phẩm và claim nếu yêu cầu nguyên tử. Phải thiết kế cả đường **đổi SKU, xóa/khôi phục, retry và lỗi giữa các bước**; một item claim không được cập nhật đồng bộ sẽ làm hệ thống báo mã đã có dù chủ sở hữu tương ứng không còn hợp lệ.

Đây là **mẫu mô hình hóa**, không phải lệnh DynamoDB hoàn chỉnh. Điều kiện, transaction limit và khả năng nhất quán đọc/ghi phải tham chiếu tài liệu phiên bản dịch vụ thực tế.

## 10. Định danh trong mô hình quan hệ giữa các document

Trong NoSQL, tham chiếu không mặc nhiên có foreign key như cơ sở dữ liệu quan hệ. Vì vậy, lựa chọn khóa tham chiếu rất quan trọng.

Giả sử đơn hàng lưu:

~~~json
{
  "orderId": "ord-7008",
  "tenantId": "shop-17",
  "lines": [
    {
      "productId": "p-101",
      "skuAtPurchase": "SP-001",
      "nameAtPurchase": "Bàn phím cơ",
      "quantity": 2,
      "unitPriceMinor": 450000
    }
  ]
}
~~~

Trong ví dụ:

- `productId` dùng để nhận diện sản phẩm tương ứng theo danh tính ổn định.
- `skuAtPurchase`, `nameAtPurchase` và `unitPriceMinor` lưu **ảnh chụp dữ liệu giao dịch**, bởi các thuộc tính hiện tại của sản phẩm có thể thay đổi.
- `tenantId` gắn với đơn hàng giúp thể hiện phạm vi sở hữu; nếu `productId` chỉ unique theo tenant thì truy vấn tham chiếu phải dùng đủ `(tenantId, productId)`.

Nếu dùng trực tiếp SKU làm reference duy nhất, việc đổi SKU có thể khiến order cũ không tìm được sản phẩm, hoặc tệ hơn, trỏ nhầm sang sản phẩm khác khi mã được tái sử dụng.

### Khi xóa dữ liệu đích

Thiết kế cần quy định:

- Có cho phép xóa cứng bản ghi đang được tham chiếu không?
- Đơn hàng cũ còn cần hiển thị sản phẩm đã mua không?
- Có dùng soft delete, tombstone hoặc dữ liệu snapshot không?
- Làm sao xử lý tham chiếu mồ côi?
- Có cần transaction/điều kiện khi cập nhật nhiều document không?

Đừng nghĩ khóa kỹ thuật tự bảo đảm toàn vẹn tham chiếu. Nó là **cơ sở để nhận diện ổn định**; chính sách tồn tại và nhất quán vẫn là trách nhiệm thiết kế ứng dụng và database.

## 11. Đổi khóa nghiệp vụ mà vẫn giữ đúng danh tính

Giả sử cửa hàng đổi SKU của sản phẩm `p-101` từ `SP-001` sang `KB-001`. Luồng hợp lý:

~~~text
productId = p-101             (giữ nguyên)
tenantId  = shop-17           (giữ nguyên)
sku       = SP-001 -> KB-001  (thay đổi)
skuKey    = SP-001 -> KB-001  (chuẩn hóa và kiểm tra unique)
~~~

Các bước cần xem xét:

1. Xác định người thực hiện có quyền đổi mã trong đúng tenant.
2. Chuẩn hóa mã mới bằng cùng chính sách tạo mới.
3. Kiểm tra các quy tắc nghiệp vụ liên quan, ví dụ SKU đã được dùng cho đơn hàng đang xử lý.
4. Dùng thao tác cập nhật được cơ chế unique của database bảo vệ trước concurrent updates.
5. Nếu có đồng bộ đến hệ khác, phát sự kiện mang `productId` ổn định và thông tin mã cũ/mới theo hợp đồng.
6. Giữ lịch sử thay đổi hoặc alias khi các hệ thống ngoài có thể còn tham chiếu mã cũ.

Ví dụ cập nhật trong MongoDB:

~~~javascript
db.products.updateOne(
  { tenantId: "shop-17", productId: "p-101", status: "ACTIVE" },
  {
    $set: {
      sku: "KB-001",
      skuKey: "KB-001"
    }
  }
);
~~~

Lệnh là ví dụ cho **chuyển giá trị**; ứng dụng cần xác định trường hợp `matchedCount = 0`, lỗi unique, quyền người dùng và xung đột đồng thời. Nếu nhiều writer có thể thay đổi bản ghi, thêm cơ chế version/optimistic concurrency để tránh một thao tác cũ ghi đè thao tác mới.

### Alias và tái sử dụng mã cũ

Nếu hệ ngoài vẫn gửi `SP-001` trong vài tháng, có thể lưu một bảng/collection alias:

~~~json
{
  "tenantId": "shop-17",
  "aliasKey": "SP-001",
  "productId": "p-101",
  "validFrom": "2026-10-01T00:00:00Z",
  "validTo": null
}
~~~

Nhưng hệ thống phải có quy tắc rõ ràng nếu sau này một sản phẩm khác muốn dùng lại `SP-001`: mã cũ còn là alias hay đã được giải phóng? Trùng giữa **alias** và **mã hiện tại** có được phép không? Nếu không, cần chung một không gian uniqueness hoặc cơ chế claim có thể kiểm tra cả hai loại, không chỉ unique index riêng cho từng collection.

## 12. Khóa nghiệp vụ từ hệ thống bên ngoài

Khi nhận sự kiện hoặc import từ đối tác, một `externalId` thường không đủ để tạo định danh duy nhất:

~~~json
{
  "provider": "marketplace-A",
  "externalOrderId": "12345",
  "tenantId": "shop-17",
  "orderId": "ord-7008"
}
~~~

Cần xác định thực thể externalOrderId thuộc phạm vi nào:

- Chỉ duy nhất trong một `provider`?
- Được cấp lại cho mỗi seller/account bên đối tác?
- Có giữ nguyên qua môi trường test và production không?
- Có thể được đối tác tái sử dụng hoặc đổi không?
- Có cùng mã khi event được gửi lặp lại không?

Định nghĩa có thể cần là `(provider, providerAccountId, externalOrderId)` thay vì `externalOrderId` độc lập.

### Bản ghi mapping là một tài sản nghiệp vụ

Một mô hình tích hợp có thể giữ:

~~~json
{
  "sourceSystem": "marketplace-A",
  "sourceAccount": "seller-17",
  "sourceId": "12345",
  "internalOrderId": "ord-7008"
}
~~~

Tập mapping phải có unique constraint theo phạm vi nguồn đã xác định. `internalOrderId` giữ danh tính hệ thống nội bộ, cho phép đối tác đổi format mã hoặc hệ thống tích hợp được nâng cấp mà không phải thay mọi reference.

Khi hai event cùng nói về một đơn hàng, ứng dụng cần biết đó là **cùng thực thể** hay hai thực thể khác nhau trùng mã do sai phạm vi. Đây là quyết định từ hợp đồng tích hợp, không thể giải quyết bằng sinh UUID mới cho mỗi event.

## 13. Idempotency key không thay cho business key

Một yêu cầu tạo đơn có thể thành công ở server nhưng client mất kết nối trước khi nhận phản hồi. Client gửi lại cùng request. Nếu server sinh `orderId` mới và ghi tiếp, hệ thống có thể tạo hai đơn dù người dùng chỉ muốn tạo một.

**Idempotency key** nhận diện việc thực hiện lại **cùng một thao tác logic**:

~~~http
POST /orders
Idempotency-Key: req-8da3e77a
Content-Type: application/json

{"cartId":"cart-451"}
~~~

Hệ thống cần xác định **phạm vi key** như `(tenantId, clientId, idempotencyKey)`, thời gian giữ kết quả, tham số nào thuộc request ban đầu, và cách xử lý khi cùng key được dùng với payload khác.

Một cách nhìn:

| Loại khóa | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `orderId` | “Đây là đơn hàng nào?” | `ord-7008` |
| `externalOrderId` | “Đối tác gọi đơn này là gì?” | `12345` trong đúng source/account |
| `idempotencyKey` | “Đây có phải cùng yêu cầu tạo đơn được gửi lại?” | `req-8da3e77a` |
| `tenantId` | “Thao tác thuộc phạm vi tổ chức nào?” | `shop-17` |

Với request idempotent, server có thể lưu trạng thái `IN_PROGRESS / COMPLETED` cùng response hoặc kết quả đã xác định; các lần retry cần được đồng bộ để không cùng tiến hành tạo mới. Idempotency key không nên được xem là business key vĩnh viễn nếu chỉ có thời hạn giữ, và không thay thế unique constraint cho mã đơn hàng thật.

## 14. Khóa kỹ thuật, phân quyền và tính riêng tư

Một lỗi bảo mật phổ biến là truy vấn tài nguyên theo public ID nhưng không giới hạn theo tenant:

~~~javascript
// Thiếu phạm vi tenant trong một API đa tenant.
db.products.findOne({ productId: "p-101" });
~~~

Một truy vấn phù hợp hơn với mô hình tenant-scoped có thể là:

~~~javascript
db.products.findOne({
  tenantId: authenticatedTenantId,
  productId: "p-101"
});
~~~

`authenticatedTenantId` phải đến từ ngữ cảnh đã được xác thực và ủy quyền, không được tin trực tiếp từ tham số do client tự đặt nếu không có bước kiểm tra. ID ngẫu nhiên khó đoán **không đủ** để ngăn lỗi lộ dữ liệu giữa tenant.

Ngoài ra:

- Không nhúng thông tin cá nhân nhạy cảm vào ID công khai nếu không cần.
- Không dựa vào “UUID không ai đoán được” để cấp quyền.
- Không sử dụng một business key dễ đổi như email làm khóa tham chiếu toàn hệ thống khi có lựa chọn ổn định hơn.
- Cân nhắc log/audit khi trả về khóa nghiệp vụ có dữ liệu nhạy cảm.
- Nếu định danh chứa timestamp hoặc số tuần tự, quyết định có chấp nhận tiết lộ quy mô hoạt động gần đúng hay không.

Index giúp tìm dữ liệu nhanh và ngăn một số va chạm, nhưng **không tự thi hành chính sách truy cập**.

## 15. Những bất biến nào không thể bảo vệ bằng unique index đơn giản?

### 15.1. Không được đặt trùng khoảng thời gian

Hai booking cho cùng phòng phải không chồng lấn:

~~~text
Booking A: phòng 7, 09:00–10:00
Booking B: phòng 7, 09:30–10:30
~~~

Dù hai booking có `bookingId` khác nhau và `startAt` khác nhau, chúng vẫn xung đột. Unique index trên `(roomId, startAt)` sẽ không ngăn.

Giải pháp tùy mô hình: chia thành slot có khóa duy nhất, conditional reservation, khóa logic hoặc transaction/constraint do DB hỗ trợ. Cần xét cả concurrent requests và quy tắc hủy/giải phóng chỗ.

### 15.2. Một người chỉ có một tài khoản hoạt động theo danh tính đã xác thực

Một rule như “mỗi người chỉ có một tài khoản” không thể suy ra từ email vì một người có nhiều email và nhiều người có thể dùng chung địa chỉ liên lạc. Cần định nghĩa danh tính theo chính sách xác thực và luật áp dụng; unique index chỉ bảo vệ được một thuộc tính **đã được quyết định là khóa**.

### 15.3. Số thứ tự liên tục không có khoảng trống

Yêu cầu “mã số tăng dần và không có lỗ hổng” khác với “mã số duy nhất”. Trong hệ phân tán, cấp số tuần tự có thể tạo điểm nóng, rollback và retry có thể tạo khoảng trống; unique constraint không tự bảo đảm dãy liên tiếp. Nếu số hóa đơn chịu quy định riêng, cần thiết kế quy trình cấp số, chốt sổ và xử lý hủy riêng thay vì dùng UUID hoặc auto-increment mà giả định đủ.

### 15.4. Bản ghi chỉ được tạo một lần trong cả vòng đời

Nếu xóa cứng document rồi tạo lại cùng business key, unique index của collection không còn nhìn thấy bản ghi cũ. Muốn cấm tái sử dụng vĩnh viễn, cần giữ lịch sử hoặc tombstone/registry đủ lâu theo yêu cầu.

## 16. Chuyển từ khóa tự nhiên sang khóa kỹ thuật khi hệ thống đã có dữ liệu

Một hệ thống ban đầu có thể dùng `sku` làm `_id`:

~~~json
{
  "_id": "SP-001",
  "name": "Bàn phím cơ"
}
~~~

Sau khi triển khai multi-tenant và cho phép đổi SKU, mô hình này gây xung đột:

- Hai tenant cùng dùng `SP-001`.
- Sửa SKU là thay danh tính lưu trữ, ảnh hưởng tham chiếu.
- Các event hoặc URL cũ tiếp tục dùng `SP-001` không còn rõ đang chỉ sản phẩm nào.
- Khả năng phân bố tải có thể không phù hợp nếu định danh gắn với quy tắc nghiệp vụ.

Một kế hoạch chuyển đổi có thể gồm:

1. **Định nghĩa mô hình đích:** `productId` bất biến, `tenantId` rõ ràng, `skuKey` và phạm vi uniqueness cụ thể.
2. **Kiểm kê dữ liệu hiện có:** tìm SKU trùng, thiếu, sai kiểu, mã trùng sau chuẩn hóa hoặc bản ghi không xác định tenant.
3. **Tạo định danh kỹ thuật cho từng thực thể:** đảm bảo không đổi qua các lần retry migration; ghi mapping `oldKey -> newId`.
4. **Cập nhật reader và API:** hỗ trợ định danh mới, có cơ chế tương thích tạm thời cho mã cũ nếu cần.
5. **Chuyển writer:** tất cả đường ghi mới dùng mô hình mới, quy tắc chuẩn hóa và uniqueness đúng phạm vi.
6. **Chuyển reference:** sửa hoặc bổ sung khóa tham chiếu trong order, event, cache và hệ tích hợp theo kế hoạch.
7. **Tạo index/validator phù hợp:** chỉ siết khi dữ liệu và đường ghi đã đáp ứng các điều kiện, kiểm tra hạn chế khi sharding.
8. **Quan sát và ngừng khóa cũ:** theo dõi consumer cũ, lỗi tra cứu, trùng mã và xung đột; gỡ đường tương thích khi không còn phụ thuộc.

Trong MongoDB, `_id` của document là trường bất biến sau khi đã tạo. Nếu muốn thay `_id`, không thể xem đó là update đơn giản; có thể phải tạo document mới, cập nhật reference và chuyển lưu trữ có kiểm soát. Vì vậy quyết định dùng business key làm `_id` có hậu quả lâu dài.

### Điểm thường bị bỏ sót trong migration

Nếu trước đây cho phép `"SP-001"` và `"sp-001"` cùng tồn tại, đến khi triển khai `skuKey` in hoa, cả hai thành `SP-001`. Tạo unique index sẽ thất bại hoặc làm luồng ghi mới bị chặn. Cần có chính sách giải quyết xung đột thực tế: hợp nhất, đổi mã, tách tenant hay phân loại bản ghi lỗi. Không tự xóa dữ liệu trùng khi chưa biết chúng là cùng một thực thể.

## 17. Thiết kế API khi có cả khóa nghiệp vụ và khóa kỹ thuật

Một API thường nên dùng ID kỹ thuật cho thao tác trực tiếp lên thực thể:

~~~http
GET /tenants/shop-17/products/p-101
PATCH /tenants/shop-17/products/p-101
~~~

Còn tìm kiếm bằng SKU là khả năng tra cứu:

~~~http
GET /tenants/shop-17/products?sku=SP-001
~~~

Phân biệt này đem lại vài lợi ích:

- URL định danh bằng `productId` không phải đổi khi SKU đổi.
- Có thể tìm sản phẩm bằng SKU quen thuộc với nghiệp vụ.
- Khi SKU được tái sử dụng theo chính sách, những đường dẫn lịch sử dùng `productId` vẫn trỏ đúng thực thể.
- Hệ thống dễ phân biệt trường hợp **không tìm thấy ID** với **không tìm thấy mã**.

Tuy nhiên, nếu kiến trúc dùng tenant-scoped ID, route và mọi truy vấn phải mang tenant đúng. Không được giả định productId tự động toàn cục nếu chính sách chỉ cấp ID trong tenant.

**Mã lỗi gợi ý:**

- `400 Bad Request`: mã không thỏa định dạng đầu vào.
- `404 Not Found`: không tồn tại tài nguyên trong phạm vi người gọi được phép truy cập; chính sách bảo mật có thể che khác biệt quyền truy cập.
- `409 Conflict`: mã nghiệp vụ mới xung đột với ràng buộc duy nhất.
- `422 Unprocessable Content`: hợp đồng API có thể dùng cho điều kiện nghiệp vụ có cú pháp đúng nhưng không thỏa ngữ nghĩa, tùy quy ước hệ thống.

Các mã chỉ là đề xuất thiết kế API; cần thống nhất với chuẩn lỗi chung của sản phẩm.

## 18. Lỗi thiết kế thường gặp

**“Có `_id` là khỏi cần nghĩ đến khóa nghiệp vụ.”** `_id` giúp nhận diện document nhưng không tự cấm hai sản phẩm trong cùng tenant có cùng SKU. Bất biến về SKU cần ràng buộc riêng.

**“SKU unique trên toàn collection chắc chắn đúng.”** Với multi-tenant, mỗi tenant có thể được phép dùng chung mã. Cần ghi đúng phạm vi `(tenantId, skuKey)`.

**“Tôi đã kiểm tra trùng bằng query trước insert.”** Hai request đồng thời có thể cùng vượt qua. Ràng buộc tại nơi ghi và xử lý lỗi đồng thời mới là bảo vệ thiết yếu.

**“UUID là khóa chính nên mọi index khác không cần.”** UUID giúp định danh, nhưng query theo mã nghiệp vụ và ràng buộc uniqueness của mã đó vẫn cần được thiết kế.

**“Dùng hash key là tự có unique toàn cluster.”** Hash hỗ trợ ánh xạ khóa vào partition; uniqueness còn tùy khóa chính, index, điều kiện ghi và quy định của engine.

**“Email luôn là định danh người dùng bất biến.”** Email có thể đổi, được chia sẻ và có chính sách so sánh khác nhau. Dùng userId ổn định để tham chiếu thường ít rủi ro hơn.

**“Xóa mềm thì mã cũ được tái sử dụng an toàn.”** Khả năng tái sử dụng phụ thuộc quy trình restore, alias, tham chiếu lịch sử và quy tắc vòng đời.

**“Chỉ cần thêm `tenantId` vào document là dữ liệu được cô lập.”** Các đường đọc, ghi, tìm kiếm, cache và quyền truy cập phải luôn dùng đúng tenant. Một index không phải authorization.

**“Mỗi lần import cứ cấp ID mới.”** Hai lần import cùng một thực thể có thể tạo hai bản ghi. Cần mapping theo khóa nguồn đúng phạm vi hoặc cơ chế idempotency phù hợp.

**“Đổi business key chỉ là update một trường.”** Mã có thể được dùng trong integration, event, dữ liệu lịch sử, cache hoặc URL cũ. Cần xem xét toàn bộ hợp đồng tham chiếu.

## 19. Bài tập áp dụng

### Bài tập A — Mã nhân viên giữa nhiều công ty

Hệ thống HR SaaS có hai doanh nghiệp A và B. Cả hai đều có nhân viên mã `NV-100`.

**Câu hỏi:** Dùng `employeeCode` làm `_id` toàn collection có phù hợp không? Ràng buộc duy nhất nên theo phạm vi nào?

**Hướng suy luận:** nếu mã chỉ do từng doanh nghiệp cấp, `employeeCode` không duy nhất toàn hệ thống. Nên có `employeeId` kỹ thuật ổn định và uniqueness theo `(companyId, employeeCodeKey)`. Quy tắc đổi mã và tái sử dụng khi nhân viên nghỉ việc phải được xác định riêng.

### Bài tập B — Hai request đăng ký cùng username

Hai request gần đồng thời đăng ký tên `"Minh"` và `"minh"`. Chính sách yêu cầu username không phân biệt hoa/thường trên toàn ứng dụng.

**Câu hỏi:** Hệ thống cần bảo vệ điều gì?

**Hướng suy luận:** cùng chuẩn hóa cả hai thành `usernameKey` theo chính sách đã công bố; dùng unique constraint phù hợp với phạm vi toàn hệ thống. Kiểm tra trong service có thể đưa ra thông báo sớm nhưng chưa đủ; phải xử lý duplicate-key khi cạnh tranh ghi. Đừng tự suy rộng chính sách username sang email hoặc tên thật.

### Bài tập C — Mã giảm giá theo chiến dịch

Marketing có hai chiến dịch `SUMMER` và `WINTER`, cả hai muốn có mã `WELCOME`.

**Câu hỏi:** Unique index nào mô tả đúng yêu cầu?

**Hướng suy luận:** nếu mã được nhập trong ngữ cảnh đã chọn chiến dịch thì `(campaignId, couponCodeKey)` có thể là phạm vi đúng. Nếu người dùng nhập mã trên một ô checkout chung mà không chọn chiến dịch, hai mã cùng tên có thể gây mơ hồ; có thể cần unique toàn bộ các chiến dịch đang hiệu lực hoặc quy tắc phân giải rõ ràng.

### Bài tập D — Mã sản phẩm được phép đổi

Một sản phẩm đã xuất hiện trong 5.000 dòng đơn hàng. Người bán đổi SKU.

**Câu hỏi:** Nếu order line tham chiếu SKU, chuyện gì có thể xảy ra? Nên giữ gì trong order line?

**Hướng suy luận:** SKU cũ có thể không tra được hoặc được tái sử dụng cho sản phẩm khác. Nên dùng định danh sản phẩm ổn định (và tenant nếu cần) cùng snapshot mã/tên/giá tại thời điểm mua để giữ lịch sử giao dịch có nghĩa.

### Bài tập E — Nhập dữ liệu từ hai đối tác

Hai marketplace cùng phát sự kiện đơn hàng có `externalOrderId = "123"`. Một marketplace còn có nhiều seller account.

**Câu hỏi:** Khóa mapping nào ngăn nhập lặp mà không gộp nhầm?

**Hướng suy luận:** phải xác định nguồn cấp và phạm vi thật: ít nhất `(provider, externalOrderId)` hoặc `(provider, providerAccountId, externalOrderId)`. `internalOrderId` kỹ thuật dùng làm danh tính ổn định nội bộ. Event retry có thể dùng cùng mapping kết hợp idempotency thích hợp.

## 20. Một quy trình ra quyết định khi thiết kế khóa NoSQL

Khi tạo thực thể hoặc collection mới, có thể đi theo thứ tự sau:

1. **Định nghĩa danh tính thực thể:** điều gì khiến hai bản ghi là cùng một đối tượng qua thời gian?
2. **Liệt kê các khóa nghiệp vụ:** ai cấp, ai dùng, có thể đổi, tái sử dụng hoặc trùng ở đâu?
3. **Viết rõ phạm vi duy nhất:** toàn cục, theo tenant, theo nhánh tổ chức, theo chiến dịch, theo trạng thái hoặc khoảng thời gian.
4. **Định nghĩa chuẩn so sánh:** hoa/thường, Unicode, khoảng trắng, dấu, định dạng và xử lý giá trị thiếu.
5. **Chọn định danh kỹ thuật ổn định:** cân nhắc cách sinh, định dạng API, tính riêng tư và khả năng migration.
6. **Chọn partition/shard key theo access pattern:** đồng thời kiểm tra giới hạn uniqueness và cơ chế transaction của engine.
7. **Đặt ràng buộc ở nơi ghi:** unique index, conditional write, claim/transaction hoặc cơ chế khác phù hợp, có tính đến concurrent requests.
8. **Thiết kế tham chiếu và lịch sử:** lựa chọn reference ID, snapshot, alias, soft delete và chính sách restore.
9. **Thiết kế import và tích hợp:** scope của external ID, xử lý duplicate và idempotency.
10. **Kiểm tra các trường hợp khó:** hai request đồng thời, đổi mã, nhập lặp, tái sử dụng sau xóa, sharding và thay đổi chính sách chuẩn hóa.

Có thể ghi lại quyết định khóa bằng một hợp đồng ngắn:

~~~yaml
entity: Product
technicalIdentity:
  field: productId
  stability: immutable
businessIdentity:
  displayField: sku
  normalizedField: skuKey
  scope: [tenantId]
  appliesWhen: "status == ACTIVE"
  reuseAfterDelete: "allowed only after explicit business review"
storageIdentity:
  mongoIdField: _id
references:
  orderLine: [tenantId, productId]
concurrency:
  enforcement: "unique index or equivalent mechanism supported by topology"
  conflictResponse: "409 for duplicate active SKU"
normalization:
  policy: "trim + uppercase ASCII; validate format"
lifecycle:
  skuCanChange: true
  productIdCanChange: false
~~~

Đây là **mẫu diễn đạt hợp đồng**, không phải YAML cấu hình được MongoDB hay một framework tự động thực thi. Các thành phần phải được chuyển thành code, index, validator và quy trình vận hành nhất quán.

Tư duy cốt lõi của bài học là **khóa nghiệp vụ thể hiện quy tắc nhận diện của tổ chức, khóa kỹ thuật giữ danh tính ổn định, còn phạm vi duy nhất nói chính xác những bản ghi nào không được cùng mang một giá trị**. Trong NoSQL, điều này càng cần được thiết kế tường minh vì cách phân vùng dữ liệu và khả năng bảo đảm uniqueness rất khác nhau giữa các hệ quản trị. Chọn đúng khóa giúp dữ liệu còn nhất quán khi hệ thống có nhiều tenant, nhiều luồng ghi đồng thời, nhiều nhà cung cấp và nhiều lần thay đổi quy trình nghiệp vụ.

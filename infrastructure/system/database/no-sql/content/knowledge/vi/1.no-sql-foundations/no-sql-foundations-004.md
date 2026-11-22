# Bản đồ thuật ngữ NoSQL: khóa, bản ghi, tài liệu, phân vùng, bản sao và cụm

Khi làm việc với NoSQL, cùng một dữ liệu có thể được nhìn ở nhiều cấp độ: ứng dụng nhận diện một đối tượng bằng **khóa**, lưu nội dung đối tượng dưới dạng **bản ghi** hoặc **tài liệu**, hệ thống đặt dữ liệu vào **phân vùng**, tạo **bản sao** để tăng khả năng chịu lỗi và vận hành các nút trong một **cụm**. Sáu khái niệm này liên quan chặt chẽ nhưng trả lời sáu câu hỏi khác nhau.

Sau bài học, bạn có thể đọc một mô tả kiến trúc NoSQL và xác định: đối tượng nào đang được lưu, khóa nào dùng để nhận diện hay định tuyến, dữ liệu nằm ở đâu, được sao chép ra sao và những máy nào cùng vận hành cơ sở dữ liệu.

## 1. Nhìn toàn cảnh trước khi đi vào từng từ

Giả sử một ứng dụng bán hàng lưu đơn hàng có mã **order-1001**, thuộc khách hàng **customer-07**. Ở góc nhìn logic, đó là một đơn hàng. Ở góc nhìn hệ thống phân tán, đơn hàng này phải được định tuyến tới nơi lưu trữ, rồi có thể được sao chép sang các nút khác.

~~~text
Ứng dụng
  |
  | Ghi đơn hàng: orderId = order-1001, customerId = customer-07
  v
Khóa nhận diện bản ghi: orderId
  |
  v
Bản ghi / tài liệu: nội dung của đơn hàng
  |
  | Dùng khóa phân vùng: customerId
  v
Phân vùng P1: nhóm dữ liệu mà hệ thống định tuyến tới
  |
  +--> Bản sao P1 trên nút B
  |
  +--> Bản sao P1 trên nút C

           CỤM = các nút và cơ chế phối hợp để vận hành dữ liệu
~~~

Sơ đồ là một cách triển khai **minh họa**, không phải kiến trúc bắt buộc của mọi NoSQL. Một hệ thống có thể lưu toàn bộ dữ liệu trên một máy, có thể chia dữ liệu theo cách khác và có thể không dùng mô hình nút chính/nút phụ.

| Thuật ngữ | Câu hỏi mà thuật ngữ trả lời | Cấp độ tư duy |
| --- | --- | --- |
| **Khóa (key)** | Làm thế nào nhận diện hoặc tìm đúng dữ liệu? | Định danh và truy cập |
| **Bản ghi (record)** | Một đơn vị dữ liệu logic chứa thông tin gì? | Mô hình dữ liệu |
| **Tài liệu (document)** | Bản ghi được biểu diễn thành cấu trúc trường, đối tượng lồng nhau và mảng thế nào? | Mô hình tài liệu |
| **Phân vùng (partition/shard)** | Dữ liệu được chia thành những phần nào, và yêu cầu được chuyển tới phần nào? | Phân phối dữ liệu |
| **Bản sao (replica)** | Có những bản lưu bổ sung nào của cùng dữ liệu để phục vụ đọc và chịu lỗi? | Sao chép dữ liệu |
| **Cụm (cluster)** | Các nút nào phối hợp để cung cấp một hệ cơ sở dữ liệu? | Triển khai và vận hành |

Một nguyên tắc hữu ích: **khóa và bản ghi** mô tả cách ứng dụng nhìn dữ liệu; **phân vùng, bản sao và cụm** chủ yếu mô tả cách hệ thống tổ chức và vận hành dữ liệu. **Tài liệu** là một dạng biểu diễn bản ghi phổ biến trong NoSQL.

## 2. Khóa (key): nhận diện khác với định tuyến

Từ *key* xuất hiện ở nhiều vị trí. Không phải khóa nào cũng thực hiện cùng một nhiệm vụ.

### 2.1. Khóa nhận diện và khóa chính

**Khóa nhận diện** là giá trị được dùng để tìm một đối tượng, ví dụ mã đơn hàng **order-1001**. Trong mô hình key–value, hệ thống ánh xạ một key sang một value; trong document database, mỗi tài liệu thường có một trường định danh.

~~~text
Key:   order:1001
Value: { customerId: "customer-07", total: 350000, status: "PAID" }
~~~

**Khóa chính (primary key)** là tập trường được hệ quản trị dùng làm định danh duy nhất trong một phạm vi xác định. Phạm vi đó có thể là collection, bảng, partition hoặc phạm vi khác tùy sản phẩm và cách khai báo. Khóa chính đôi khi là một trường, đôi khi là **khóa ghép** gồm nhiều trường.

Ví dụ về khóa ghép:

~~~text
Khóa chính của một dòng đơn hàng = (orderId, lineNumber)

(order-1001, 1) -> sản phẩm A
(order-1001, 2) -> sản phẩm B
~~~

Ở đây **orderId** lặp lại được vì cặp **(orderId, lineNumber)** mới là định danh đầy đủ.

### 2.2. Khóa phân vùng và khóa sắp xếp

**Khóa phân vùng (partition key)** được dùng để xác định dữ liệu thuộc phần phân phối nào. Ví dụ, hệ thống có thể dùng **customerId** để các đơn hàng cùng khách hàng được định tuyến vào cùng một phân vùng trong mô hình minh họa này. Khóa phân vùng **không mặc nhiên là định danh duy nhất**: một khách hàng có thể có nhiều đơn hàng.

**Khóa sắp xếp (sort key hoặc clustering key/column, tùy hệ)** giúp phân biệt hoặc tổ chức thứ tự các mục *bên trong* cùng một nhóm khóa phân vùng. Ví dụ, nhóm theo **customerId** và sắp xếp theo **createdAt** để lấy đơn hàng gần đây. Tên gọi và quy tắc duy nhất của các cặp khóa phụ thuộc từng hệ quản trị.

| Vai trò khóa | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Khóa định danh đơn hàng | **orderId = order-1001** | Chỉ ra đơn hàng ứng dụng muốn xử lý |
| Khóa chính đơn trường | **orderId** | Có thể đảm bảo định danh duy nhất trong phạm vi được cấu hình |
| Khóa chính ghép | **(orderId, lineNumber)** | Phân biệt từng dòng sản phẩm của một đơn hàng |
| Khóa phân vùng | **customerId = customer-07** | Quyết định nhóm dữ liệu/đích định tuyến |
| Khóa sắp xếp | **createdAt** | Phục vụ thứ tự hoặc truy vấn trong nhóm, nếu hệ hỗ trợ |
| Trường được lập chỉ mục phụ | **status** | Hỗ trợ tra cứu theo một thuộc tính; không mặc nhiên là khóa chính hoặc khóa phân vùng |

**Chỉ mục (index) không đồng nghĩa với khóa.** Chỉ mục là cấu trúc hỗ trợ truy vấn. Một trường có thể được lập chỉ mục nhưng không tham gia định danh hay phân vùng. Ngược lại, một hệ có thể tự tạo chỉ mục cho khóa chính. Cần xem cơ chế cụ thể của sản phẩm.

### 2.3. Chọn khóa phải dựa vào thao tác truy vấn

Giả sử hai thao tác phổ biến là:

1. Lấy chi tiết một đơn hàng theo **orderId**.
2. Liệt kê các đơn hàng của một khách hàng theo **customerId** và thời gian.

Thiết kế cần hỗ trợ cả tính duy nhất của đơn hàng lẫn đường đi hiệu quả cho truy vấn theo khách hàng. Chỉ dùng **orderId** làm khóa phân vùng có thể phân tán tốt nhưng không tự động giúp liệt kê tất cả đơn của một khách hàng. Chỉ dùng **customerId** có thể nhóm đơn hàng thuận lợi nhưng một khách hàng quá lớn có nguy cơ tạo **phân vùng nóng (hot partition)**. Đôi khi cần chỉ mục phụ, bảng/tài liệu biểu diễn riêng cho kiểu truy vấn, hoặc cách phân nhóm tinh hơn.

Không nên mặc định rằng cứ có trường tên **id** thì hệ thống phân tán dựa trên trường đó để chia dữ liệu.

## 3. Bản ghi (record): một đơn vị dữ liệu logic

**Bản ghi** là cách gọi tổng quát cho một đơn vị thông tin mà ứng dụng lưu và xử lý. Ví dụ, một bản ghi đơn hàng chứa mã đơn, người mua, trạng thái, danh sách mặt hàng và tổng tiền. Nó là khái niệm logic; việc nằm trên máy nào là vấn đề khác.

Trong các họ cơ sở dữ liệu, đơn vị tương tự có tên và hình dạng khác nhau:

| Họ mô hình dữ liệu | Đơn vị thường gặp | Hình dung |
| --- | --- | --- |
| Key–value | Cặp **key → value** | Khóa giỏ hàng trỏ tới nội dung giỏ |
| Document | **Document** | Một đối tượng đơn hàng có trường và mảng lồng nhau |
| Wide-column | **Row**, **partition** và các ô/cột liên quan | Dữ liệu được tổ chức theo khóa phân vùng và khóa cụm |
| Graph | **Node**, **edge** cùng thuộc tính | Khách hàng liên kết với đơn hàng hoặc sản phẩm |

Không phải mọi hệ NoSQL đều gọi đơn vị dữ liệu là **record**. Ta dùng từ này để trao đổi ở mức khái niệm, sau đó dùng đúng thuật ngữ khi đọc tài liệu sản phẩm.

**Một bản ghi không nhất thiết tương ứng với một tệp, một trang đĩa, một phân vùng hoặc một nút máy.** Nhiều bản ghi thường cùng nằm trong một phân vùng, còn một phân vùng có thể nằm trên nhiều nút vì được sao chép.

## 4. Tài liệu (document): bản ghi có cấu trúc linh hoạt

Trong **document database**, đơn vị lưu trữ trung tâm là **tài liệu**. Tài liệu thường biểu diễn dưới dạng cấu trúc gần JSON: các cặp tên trường–giá trị, đối tượng lồng nhau và mảng. Một số hệ lưu bằng dạng nhị phân riêng như BSON; JSON ở đây dùng để dễ học.

~~~json
{
  "_id": "order-1001",
  "customerId": "customer-07",
  "createdAt": "2026-11-14T08:00:00Z",
  "status": "PAID",
  "shippingAddress": {
    "city": "Da Nang",
    "country": "VN"
  },
  "items": [
    { "sku": "book-01", "quantity": 2, "unitPrice": 100000 },
    { "sku": "pen-02", "quantity": 3, "unitPrice": 50000 }
  ],
  "total": 350000
}
~~~

Trong ví dụ, cả thông tin giao hàng và các mặt hàng được biểu diễn trong **một tài liệu đơn hàng**. Điều này thuận lợi nếu màn hình chủ yếu tải toàn bộ chi tiết đơn hàng cùng lúc.

Tài liệu có vài đặc điểm đáng nhớ:

- **Tổ chức theo đối tượng:** các trường liên quan có thể nằm gần nhau, kể cả mảng và đối tượng lồng nhau.
- **Cấu trúc có thể khác giữa tài liệu:** một đơn hàng khác có thể có thêm trường **discountCode**, nhưng ứng dụng vẫn phải có hợp đồng dữ liệu, kiểm tra kiểu và quy tắc tương thích phiên bản.
- **Có định danh:** trường **_id** ở ví dụ là khóa nhận diện tài liệu; tên trường và phạm vi duy nhất phụ thuộc sản phẩm.
- **Có giới hạn thiết kế:** tài liệu quá lớn hoặc mảng tăng không giới hạn có thể làm thao tác đọc/ghi tốn kém; nhúng mọi thứ vào một tài liệu không phải lúc nào cũng tốt.

**Quan hệ giữa record và document:** một document là một dạng bản ghi trong mô hình tài liệu. Chiều ngược lại không đúng: record trong key–value, wide-column hoặc graph không nhất thiết là document.

### Khi nào nhúng và khi nào tham chiếu?

Để học đúng nghĩa từ *document*, cần phân biệt **cấu trúc tài liệu** với **quan hệ giữa tài liệu**.

| Cách biểu diễn | Ví dụ | Phù hợp khi |
| --- | --- | --- |
| **Nhúng (embed)** | Mảng **items** ngay trong đơn hàng | Các thành phần thường được đọc cùng nhau, kích thước có thể kiểm soát |
| **Tham chiếu (reference)** | **customerId** trỏ tới tài liệu khách hàng | Đối tượng được dùng lại hoặc cập nhật độc lập |

Đây là quyết định mô hình dữ liệu, không phải quyết định về phân vùng hay nhân bản. Một tài liệu nhúng vẫn có thể nằm trong một phân vùng được sao chép nhiều lần.

## 5. Phân vùng (partition/shard): chia dữ liệu để phân phối

Khi dữ liệu tăng, hệ thống có thể chia tập dữ liệu thành các **phân vùng** để đặt, quản lý hoặc xử lý trên nhiều tài nguyên. Trong ngữ cảnh phân tán, **sharding** thường chỉ việc chia dữ liệu theo các phần để phân phối lên các nút; **shard** là một phần dữ liệu như vậy. Từ **partition** có thể được dùng ở mức logic hoặc vật lý tùy hệ.

Ví dụ giả định định tuyến theo **customerId**:

~~~text
customer-01, customer-05, customer-09  -> P0
customer-02, customer-07, customer-11  -> P1
customer-03, customer-08, customer-12  -> P2
~~~

Các mã trong sơ đồ chỉ để minh họa kết quả định tuyến. Trong thực tế, thuật toán và số lượng phân vùng do hệ quản trị quyết định.

### Hai chiến lược phổ biến

| Chiến lược | Ý tưởng | Thuận lợi | Điều cần chú ý |
| --- | --- | --- | --- |
| **Theo hàm băm (hash-based)** | Tính giá trị băm từ khóa phân vùng, rồi ánh xạ tới phân vùng | Có thể phân tán khóa tương đối đều nếu phân bố đầu vào phù hợp | Truy vấn phạm vi theo khóa có thể phải đi tới nhiều phân vùng |
| **Theo khoảng giá trị (range-based)** | Chia dữ liệu thành các khoảng khóa liên tiếp | Truy vấn theo phạm vi có thể hiệu quả | Ghi liên tục vào đầu/cuối dải khóa có thể tạo điểm nóng |

Một sản phẩm có thể dùng cách khác hoặc kết hợp nhiều cơ chế. Ví dụ **hash(key) mod N** chỉ giúp hiểu nguyên lý định tuyến; không nên xem đó là công thức triển khai chung vì việc thay đổi **N** sẽ ảnh hưởng ánh xạ dữ liệu. Các hệ thực tế có thể dùng định tuyến động, virtual nodes, tách/gộp phân vùng hoặc cơ chế cân bằng khác.

### Ba điều rất dễ nhầm

1. **Một giá trị khóa phân vùng không tương đương một phân vùng vật lý.** Nhiều giá trị khóa có thể cùng được đặt trong một phân vùng.
2. **Một phân vùng không tương đương một nút.** Một nút có thể giữ nhiều phân vùng; một phân vùng có thể được sao chép sang nhiều nút.
3. **Phân vùng khác bản sao.** Chia dữ liệu tạo các phần có nội dung khác nhau; nhân bản tạo thêm bản lưu của cùng một phần dữ liệu.

Phân vùng cải thiện khả năng mở rộng khi tải được phân phối phù hợp. Đổi lại, truy vấn hoặc giao dịch liên quan nhiều phân vùng có thể phải phối hợp qua mạng. Cơ chế giao dịch, chỉ mục và truy vấn xuyên phân vùng khác nhau đáng kể giữa các hệ NoSQL.

### Phân vùng nóng (hot partition)

Nếu **customer-07** tạo ra phần lớn yêu cầu, định tuyến tất cả dữ liệu theo **customerId** có thể dồn tải vào một chỗ, dù cụm còn nhiều nút rảnh. Đây là **lệch tải**, không nhất thiết do thiếu nút.

Các hướng xử lý tùy mục đích gồm chọn lại khóa phân vùng, thêm thành phần thời gian hoặc bucket vào khóa, điều chỉnh mô hình truy vấn, hoặc tận dụng khả năng chia/cân bằng phân vùng của sản phẩm. Mỗi cách có chi phí: chẳng hạn thêm bucket có thể buộc truy vấn một khách hàng phải tổng hợp nhiều nơi.

## 6. Bản sao (replica): nhiều bản lưu của cùng dữ liệu

**Replica** là bản lưu dữ liệu được duy trì để phục vụ tính sẵn sàng, khả năng chịu lỗi hoặc tải đọc. Nếu phân vùng **P1** được sao chép lên hai nút, cả hai chứa dữ liệu thuộc **P1** theo chính sách sao chép của hệ thống.

~~~text
Phân vùng logic P1
  |
  +--> Nút B: bản sao của P1
  |
  +--> Nút C: bản sao của P1
~~~

**Replication factor (RF)** thường chỉ số bản sao dữ liệu mong muốn theo đơn vị và cách tính của sản phẩm. Trong sơ đồ trên, nếu mỗi bản lưu được tính một lần, **RF = 2**. RF không phải số lượng phân vùng, và không tự động bằng số lượng nút của cả cụm.

### Các mô hình sao chép thường gặp

- **Leader-based:** một bản sao đang giữ vai trò leader/primary nhận ghi hoặc điều phối ghi; follower/secondary nhận thay đổi từ leader. Một số hệ cho phép đọc tại follower tùy cấu hình.
- **Leaderless hoặc phối hợp nhiều bản sao:** yêu cầu có thể đi tới nhiều replica; hệ dùng cơ chế chọn phiên bản, xác nhận ghi, đọc sửa lỗi hoặc đồng thuận khác nhau tùy thiết kế.
- **Đồng bộ và bất đồng bộ:** hệ có thể chờ một số bản sao xác nhận trước khi báo ghi thành công, hoặc xác nhận trước rồi truyền thay đổi sau. Chính sách này ảnh hưởng độ trễ, tính nhất quán và rủi ro mất thay đổi khi có lỗi.

Không thể suy ra **đọc luôn thấy giá trị mới nhất** chỉ vì có nhiều replica. Cần biết mô hình nhất quán và mức xác nhận mà hệ cung cấp, cùng cấu hình đọc/ghi đang dùng.

### Replica khác backup như thế nào?

| Replica | Backup |
| --- | --- |
| Bản dữ liệu hoạt động, thường được cập nhật liên tục hoặc gần thời gian thực | Ảnh chụp hoặc bản lưu theo một mốc thời gian/chính sách lưu trữ |
| Chủ yếu phục vụ sẵn sàng, chịu lỗi và đôi khi tăng tải đọc | Chủ yếu phục vụ khôi phục dữ liệu khi xóa nhầm, hỏng dữ liệu hoặc sự cố diện rộng |
| Lệnh xóa nhầm có thể lan sang các replica | Có thể khôi phục phiên bản cũ nếu backup còn hiệu lực và dùng được |
| Không thay thế chiến lược khôi phục | Không mặc nhiên là bản sao có thể nhận truy vấn trực tiếp |

Một hệ có **RF = 3** vẫn cần backup, phương án khôi phục và kiểm tra khôi phục. Ba bản sao đặt cùng nơi có thể cùng bị ảnh hưởng khi nơi đó mất điện; cần xét **miền lỗi (failure domain)**, ví dụ máy, rack hoặc vùng khả dụng.

## 7. Cụm (cluster): các nút cùng vận hành một hệ dữ liệu

**Cụm** là tập các **nút (node)** phối hợp để cung cấp một hệ cơ sở dữ liệu theo cơ chế quản trị chung. Nút có thể là máy vật lý, máy ảo hoặc tiến trình/instance phù hợp kiến trúc sản phẩm. Cụm có thể đảm nhiệm định tuyến, lưu trữ, sao chép, bầu leader, phát hiện lỗi và cân bằng tải; không phải sản phẩm nào cũng tổ chức các vai trò này giống nhau.

Trong ví dụ đơn giản, cụm có ba nút dữ liệu **A**, **B**, **C**. Mỗi nút giữ các phân vùng khác nhau và có thể đồng thời giữ bản sao của phân vùng do nút khác làm leader.

~~~text
                      CỤM ĐƠN HÀNG
  +----------------+ +----------------+ +----------------+
  | Nút A          | | Nút B          | | Nút C          |
  | P0: leader     | | P1: leader     | | P2: leader     |
  | P2: follower   | | P0: follower   | | P1: follower   |
  +----------------+ +----------------+ +----------------+

  P0: A + B          P1: B + C          P2: C + A
  Mỗi phân vùng có hai bản sao (mô hình minh họa RF = 2).
~~~

Trong sơ đồ giả định leader-based này:

- **Ba phân vùng logic P0, P1, P2** chia tập dữ liệu thành các phần khác nhau.
- **Mỗi phân vùng có hai bản sao** đặt trên hai nút.
- **Mỗi nút giữ hai phần dữ liệu:** một phân vùng ở vai trò leader và một phân vùng ở vai trò follower.
- **Cụm có ba nút** nhưng không có nghĩa RF phải là 3.

Nếu nút **B** ngừng hoạt động, các bản sao của **P0** tại **A** và **P1** tại **C** vẫn tồn tại. Tuy nhiên, việc tiếp tục phục vụ đọc/ghi phụ thuộc cơ chế chuyển vai trò, quorum/đồng thuận, mức cập nhật replica và chính sách của hệ. Không nên hứa rằng mọi lần lỗi nút đều không gián đoạn hoặc không mất dữ liệu.

**Mở rộng ngang (scale out)** là thêm nút rồi phân phối lại tải/dữ liệu phù hợp. Thêm nút không tự động tăng tốc mọi truy vấn: một truy vấn dồn vào một khóa nóng hoặc phải gom dữ liệu từ nhiều phân vùng vẫn có thể là điểm nghẽn.

## 8. Theo chân một đơn hàng qua đủ sáu khái niệm

Xét hệ thống tài liệu đơn hàng dưới đây. Đây là thiết kế để học cách nối thuật ngữ với nhau, không phải cấu hình sản xuất cho một hệ quản trị cụ thể.

**Dữ liệu đầu vào:**

~~~json
[
  { "_id": "order-1001", "customerId": "customer-07", "status": "PAID", "total": 350000 },
  { "_id": "order-1002", "customerId": "customer-07", "status": "NEW",  "total": 120000 },
  { "_id": "order-1003", "customerId": "customer-08", "status": "PAID", "total": 98000 }
]
~~~

**Quy ước thiết kế:**

- Một **document** biểu diễn một đơn hàng; ở mức ứng dụng, mỗi document cũng là một **record**.
- **_id** chứa mã đơn hàng, được ứng dụng thiết kế để duy nhất trong tập đơn hàng.
- **customerId** là **partition key**, không phải định danh duy nhất của đơn hàng.
- Giả sử bộ định tuyến ánh xạ **customer-07 → P1** và **customer-08 → P2**.
- Cụm dùng đúng sơ đồ ba nút, ba phân vùng và hai replica cho mỗi phân vùng ở phần trước.

Khi ghi **order-1001**, đường đi ở mức khái niệm là:

1. Ứng dụng tạo **bản ghi** đơn hàng và biểu diễn nó thành **tài liệu**.
2. Hệ nhận **khóa định danh _id = order-1001** để phân biệt đơn này với đơn khác.
3. Hệ đọc **khóa phân vùng customerId = customer-07**, từ đó định tuyến tới **P1**.
4. Theo sơ đồ giả định, **B** giữ bản sao leader của **P1**, **C** giữ bản sao follower; hệ thực hiện ghi và sao chép theo chính sách xác nhận đã cấu hình.
5. Các nút **A, B, C** thuộc cùng một **cụm** và phối hợp để phục vụ dữ liệu.

**order-1002** có khóa định danh khác nhưng cùng khóa phân vùng **customer-07**, nên trong mô hình này cũng đi tới **P1**. **order-1003** có khóa phân vùng khác và được ánh xạ tới **P2**. Từ đó thấy rõ: **hai bản ghi khác nhau có thể cùng phân vùng**, còn **một phân vùng có thể có nhiều bản sao**.

### Truy vấn nào thuận đường đi dữ liệu?

~~~text
Yêu cầu A: Liệt kê đơn hàng của customer-07
  -> Biết partition key customerId
  -> Bộ định tuyến có thể nhắm tới P1 trong ví dụ

Yêu cầu B: Tìm tất cả đơn hàng status = PAID
  -> Không có partition key trong điều kiện
  -> Có thể cần chỉ mục hỗ trợ, mô hình dữ liệu riêng
     hoặc truy vấn nhiều phân vùng, tùy sản phẩm

Yêu cầu C: Lấy order-1003 theo _id
  -> Có khóa định danh, nhưng chưa chắc đã có partition key
  -> Đường đi tùy cách hệ đánh chỉ mục và định tuyến
~~~

Ví dụ cho thấy **định danh được một tài liệu** và **biết ngay nơi chứa tài liệu** là hai khả năng khác nhau. Ở một số hệ, truy vấn theo khóa chính đủ để tìm đúng phân vùng vì khóa chính chứa khóa phân vùng; ở hệ khác, định danh và shard key là hai trường tách biệt.

## 9. Đặt các thuật ngữ lên từng họ NoSQL

NoSQL là tên gọi chung của nhiều kiểu hệ quản trị; không có một từ điển triển khai áp dụng nguyên xi cho mọi sản phẩm. Bảng sau chỉ dùng để **định vị khái niệm** khi đọc tài liệu.

| Mô hình / hệ ví dụ | Khái niệm khóa và bản ghi | Khái niệm phân phối |
| --- | --- | --- |
| **Key–value**, ví dụ Redis | **Key** ánh xạ tới **value**; giá trị có thể thuộc nhiều kiểu dữ liệu | Việc phân chia key giữa các nút và có replica tùy chế độ triển khai |
| **Document**, ví dụ MongoDB | **Document** có định danh **_id**; dữ liệu có thể chứa trường lồng nhau | **Shard key** dùng cho phân mảnh nếu bật sharding; bản sao và tập nút có cơ chế riêng |
| **Key–value/document managed**, ví dụ DynamoDB | Đơn vị là **item**; khóa chính có **partition key**, có thể thêm **sort key** | Hệ quản lý các phân vùng vật lý và bản sao ở phía dịch vụ |
| **Wide-column**, ví dụ Cassandra | **Partition key** xác định partition; **clustering columns** giúp tổ chức các row trong partition | Các node trong **cluster** lưu những vùng dữ liệu được phân phối và nhân bản |
| **Graph database** | **Node/vertex**, **edge/relation** và thuộc tính là trọng tâm | Cách chia đồ thị và sao chép phụ thuộc hệ cụ thể; không thể suy từ mô hình document |

Khi xem một hệ mới, nên mở tài liệu chính thức để kiểm tra ba điểm: phạm vi duy nhất của khóa, đơn vị dùng cho partition/shard và chính sách replication/consistency. Đừng lấy hành vi của một sản phẩm rồi coi là định nghĩa chung cho NoSQL.

## 10. Các nhầm lẫn thường gặp

| Nhận định dễ nhầm | Cách hiểu đúng |
| --- | --- |
| “Primary key lúc nào cũng là partition key.” | Có hệ kết hợp chúng, có hệ tách biệt; phải xem mô hình khóa cụ thể. |
| “Giá trị partition key nào cũng có một máy riêng.” | Nhiều giá trị khóa có thể cùng một phân vùng; một nút có thể giữ nhiều phân vùng. |
| “Một record bằng một document ở mọi NoSQL.” | Document là dạng bản ghi của mô hình tài liệu; các mô hình khác dùng đơn vị khác. |
| “Shard là bản sao.” | Sharding **chia dữ liệu khác nhau**; replication **sao chép cùng dữ liệu**. |
| “Ba node nghĩa là ba bản sao của mỗi record.” | Số node, số phân vùng và replication factor là ba đại lượng độc lập về khái niệm. |
| “Có replica nghĩa là đã có backup.” | Lỗi/xóa nhầm có thể được sao chép; backup phục vụ khôi phục về mốc trước. |
| “Có replica thì mọi lần đọc đều thấy ghi mới nhất.” | Mức nhất quán phụ thuộc cơ chế replication và chính sách đọc/ghi. |
| “NoSQL đồng nghĩa không có cấu trúc hoặc không có schema.” | Nhiều hệ có schema, ràng buộc hay kiểm tra dữ liệu; linh hoạt không có nghĩa tùy tiện. |
| “Thêm node chắc chắn chữa được truy vấn chậm.” | Điểm nóng, chỉ mục, truy vấn xuyên partition và thiết kế khóa vẫn có thể giới hạn hiệu năng. |

### Ba câu hỏi để đọc bất kỳ sơ đồ NoSQL nào

1. **Dữ liệu logic:** mỗi đối tượng là key–value, document, row hay node/edge? Khóa nào xác định đối tượng?
2. **Định tuyến:** dùng trường nào để chọn partition? Một truy vấn biết trường đó không, và điều kiện lọc có phải đi qua nhiều partition không?
3. **Khả dụng:** mỗi partition có bao nhiêu replica, nằm trên node/miền lỗi nào, và hệ xác nhận đọc/ghi cùng chuyển vai trò ra sao?

Ba câu hỏi giúp không nhầm vấn đề **mô hình dữ liệu** với vấn đề **phân phối** hoặc **khả năng chịu lỗi**.

## 11. Tự kiểm tra cách dùng thuật ngữ

**Tình huống 1.** Một cửa hàng có 10.000 đơn hàng, trong đó 200 đơn của cùng một khách. Hệ dùng **customerId** làm partition key và **orderId** làm định danh duy nhất. Có phải 200 đơn này là một record không?

**Trả lời:** Không. Chúng là **200 record/document riêng**, mỗi record có một **orderId**. Trong mô hình định tuyến minh họa theo customerId, chúng có thể đi vào cùng một partition. Một partition chứa được nhiều record.

**Tình huống 2.** Một partition có hai replica nằm trên hai nút. Một người vô tình xóa tài liệu và thao tác xóa được sao chép sang cả hai nút. Có thể gọi replica thứ hai là bản backup khôi phục tài liệu trước khi xóa không?

**Trả lời:** Không. Replica đang theo trạng thái hiện tại và có thể nhận cả lệnh xóa. Muốn phục hồi trạng thái cũ cần cơ chế backup, snapshot, lịch sử phiên bản hoặc khôi phục tại thời điểm, nếu hệ hỗ trợ và đã cấu hình.

**Tình huống 3.** Cụm có sáu nút và mười hai phân vùng, mỗi phân vùng có ba bản sao. Có mâu thuẫn vì số phân vùng lớn hơn số nút không?

**Trả lời:** Không. Một nút có thể chứa nhiều phân vùng. Với giả định ba bản sao cho mỗi phân vùng, ta có **12 × 3 = 36 vị trí lưu bản sao phân vùng** được phân bổ trên sáu nút. Đó là số vị trí logic trong ví dụ, không cho biết kích thước hay cách phân bố thực tế và không đảm bảo mọi yêu cầu chịu lỗi đều được thỏa mãn.

**Tình huống 4.** Một API truy vấn theo **status = PAID** chậm dù cụm đã thêm nút. Nên chỉ tăng replication factor không?

**Trả lời:** Chưa đủ cơ sở. Cần xem điều kiện **status** có chỉ mục hay mô hình truy vấn phù hợp, truy vấn phải quét bao nhiêu partition, có bị dồn tải vào khóa nóng không và replicas có tham gia phục vụ đọc được không. Tăng replication factor không tự tạo đường truy vấn hiệu quả.

## 12. Ghi nhớ bằng một chuỗi sáu câu

**Khóa** giúp nhận diện hoặc định tuyến dữ liệu. **Bản ghi** là một đơn vị thông tin logic. **Tài liệu** là một dạng bản ghi có cấu trúc trường và đối tượng lồng nhau. **Phân vùng** là cách chia dữ liệu để phân phối. **Bản sao** là bản lưu thêm của cùng dữ liệu theo cơ chế replication. **Cụm** là tập các nút phối hợp để lưu, định tuyến và phục vụ dữ liệu.

Khi thiết kế NoSQL, hãy xuất phát từ dữ liệu và những truy vấn ứng dụng thực sự cần, rồi mới xác định khóa, phân vùng, số bản sao và cấu trúc cụm. Thứ tự suy nghĩ này giúp tránh trộn lẫn câu hỏi “**lưu cái gì?**”, “**tìm bằng gì?**”, “**đặt ở đâu?**” và “**duy trì hoạt động khi có sự cố thế nào?**”.

# Mảng lồng nhau, tăng trưởng không giới hạn và giới hạn kích thước tài liệu

Trong mô hình tài liệu (*document model*) của NoSQL, một document có thể chứa object, trường đơn và các **mảng lồng nhau**. Cách tổ chức này tự nhiên khi dữ liệu có quan hệ thuộc về nhau: đơn hàng chứa dòng hàng, bài viết chứa danh sách thẻ, hồ sơ người dùng chứa một số địa chỉ liên hệ. Khi ứng dụng đọc toàn bộ thực thể, việc lấy một document thường đơn giản hơn nhiều lần truy vấn để ghép các phần nhỏ.

Nhưng ưu điểm ấy không có nghĩa **mọi quan hệ một-nhiều đều nên được nhúng thành một mảng**. Nếu số phần tử tiếp tục tăng mà không có giới hạn nghiệp vụ, document có thể chạm giới hạn kích thước của cơ sở dữ liệu. Trước khi chạm giới hạn, hệ thống đã có thể gặp độ trễ ghi/đọc tăng, index phình to, tranh chấp cập nhật, tốn băng thông và khó phân trang.

Bài học này giúp trả lời ba câu hỏi thiết kế:

1. **Khi nào một mảng lồng nhau là lựa chọn phù hợp?**
2. **Điều gì xảy ra khi mảng tăng trưởng không giới hạn?**
3. **Nên chuyển sang tài liệu tham chiếu, bucket hay dữ liệu tổng hợp như thế nào để giữ truy vấn nhanh và vận hành ổn định?**

## 1. Mảng lồng nhau trong document thực chất là gì?

Xét document đơn hàng:

~~~json
{
  "orderId": "O-1042",
  "customerId": "C-21",
  "createdAt": "2026-11-14T08:00:00Z",
  "items": [
    {
      "sku": "SKU-A",
      "quantity": 2,
      "unitPrice": 150000
    },
    {
      "sku": "SKU-B",
      "quantity": 1,
      "unitPrice": 230000
    }
  ],
  "total": 530000
}
~~~

Trường **items** là một mảng các object được nhúng (*embedded documents*). Các dòng hàng có ý nghĩa chủ yếu trong ngữ cảnh đơn hàng: cùng được tạo khi đặt hàng, cùng được đọc khi xem đơn, và thường không cần xuất hiện như thực thể độc lập để hàng nghìn ứng dụng khác cập nhật.

Nhúng đem lại những lợi ích tiềm năng:

- **Đọc theo aggregate:** có thể lấy đơn hàng và dòng hàng trong một thao tác tìm theo khóa.
- **Tính cục bộ:** những trường thường dùng cùng nhau nằm trong một đơn vị lưu trữ logic.
- **Cập nhật nhất quán trong một document:** nhiều hệ document hỗ trợ atomic update của một document, nhưng cú pháp và bảo đảm cụ thể phụ thuộc sản phẩm.
- **Dễ diễn đạt dữ liệu phân cấp:** cấu trúc JSON/BSON gần với payload API.
- **Giảm join ở ứng dụng:** với dữ liệu nhỏ, ổn định, không cần fetch từng dòng để lắp thành kết quả.

Tuy nhiên, một document không phải là một không gian lưu trữ vô hạn. Sản phẩm có thể áp dụng **giới hạn kích thước trên từng document**, giới hạn độ sâu lồng nhau, giới hạn request, và giới hạn khác cho index hoặc transaction. Ngoài giới hạn cứng, một document rất lớn còn có thể gây chi phí vận hành đáng kể.

### 1.1. Phân biệt mảng có giới hạn với mảng không giới hạn

| Mảng có giới hạn hợp lý | Mảng có khả năng tăng không giới hạn |
|---|---|
| Các dòng hàng trong một đơn, nếu nghiệp vụ có ngưỡng số dòng | Mọi đơn hàng từng tạo của một khách hàng |
| Một số ảnh đại diện sản phẩm, có giới hạn số ảnh | Mọi lượt xem sản phẩm trong nhiều năm |
| Danh sách tối đa 5 địa chỉ nhận hàng | Toàn bộ bình luận của một bài viết |
| 10 thông báo mới nhất dùng để hiển thị nhanh | Toàn bộ thông báo từng phát tới tài khoản |
| Một tập trạng thái hoặc thuộc tính nhỏ, biết trước biên trên | Mọi tin nhắn của một phòng chat |

Đặc điểm quyết định không phải là **mảng hiện tại có nhỏ hay không**, mà là **số phần tử tối đa trong tương lai có được khống chế bằng quy tắc nghiệp vụ hoặc giới hạn hệ thống đáng tin cậy hay không**.

Mảng chỉ có 10 phần tử hôm nay vẫn là unbounded array nếu ứng dụng không đặt giới hạn và mỗi ngày có thể thêm hàng nghìn phần tử mới.

### 1.2. Một quan hệ một-nhiều chưa nói lên cách lưu

Giả sử ứng dụng có:

~~~text
BlogPost 1 ---- N Comment
User     1 ---- N Order
Room     1 ---- N Message
Order    1 ---- N OrderItem
~~~

Tất cả đều là quan hệ một-nhiều, nhưng **N** có ý nghĩa hoàn toàn khác nhau:

- N của **OrderItem** có thể bị chặn bởi giới hạn giỏ hàng.
- N của **Comment** có thể lên tới hàng triệu.
- N của **Message** tăng liên tục theo tuổi phòng chat.
- N của **Order** tăng theo vòng đời khách hàng; ngay cả khách hàng phổ thông cũng có thể tích lũy dữ liệu trong nhiều năm.

Vì thế, không thể quyết định nhúng chỉ từ sơ đồ quan hệ. Phải xét **cardinality**, tốc độ tăng, vòng đời, truy vấn, cách cập nhật và kích thước của mỗi phần tử.

## 2. Vì sao một mảng lớn là rủi ro, ngay cả trước giới hạn cứng?

Hãy tưởng tượng mỗi bài viết được lưu thành một document:

~~~json
{
  "postId": "P-100",
  "title": "Một bài viết phổ biến",
  "comments": [
    {
      "commentId": "C-1",
      "authorId": "U-1",
      "createdAt": "2026-11-14T08:05:00Z",
      "text": "Ví dụ bình luận đầu tiên"
    }
  ]
}
~~~

Lúc đầu, cấu trúc này hợp lý: đọc một bài viết có thể lấy luôn bình luận. Nhưng nếu ứng dụng liên tục nối thêm phần tử vào **comments**, cấu trúc này dần xuất hiện nhiều vấn đề.

### 2.1. Giới hạn kích thước document là một ranh giới kỹ thuật

Nhiều cơ sở dữ liệu document có giới hạn số byte được lưu trong **một document**. Chẳng hạn, MongoDB có giới hạn BSON document 16 MiB trong các phiên bản phổ biến; những hệ khác có giới hạn, ngoại lệ và cách đếm kích thước riêng. Khi triển khai cần tra tài liệu chính thức đúng phiên bản, dịch vụ và phương thức lưu trữ đang dùng.

Một document chứa mảng sẽ tăng khi thêm:

- Nội dung của phần tử mới.
- Tên trường, kiểu dữ liệu, chỉ số/vị trí hoặc metadata của định dạng lưu trữ.
- Các trường khác được cập nhật cùng document.
- Các trường mới bổ sung khi schema phát triển.

**Giới hạn là trên toàn document, không phải chỉ tính riêng mảng.** Dữ liệu lồng nhau, trường gốc, phần tử lớn bất thường và overhead đều dùng chung ngân sách kích thước.

Việc nén hoặc chỉ chiếu vài trường khi trả kết quả không mặc nhiên xóa bỏ giới hạn kích thước của bản ghi đã lưu. Cơ chế nén, định dạng trong bộ nhớ và cách tính giới hạn phụ thuộc từng hệ quản trị.

### 2.2. Đọc ít dữ liệu nhưng giữ document quá lớn

Màn hình chỉ cần “20 bình luận mới nhất”. Nếu mọi bình luận nằm trong một document khổng lồ:

~~~text
GET /posts/P-100/comments?limit=20
~~~

thì database phải truy cập cấu trúc lưu trữ chứa mảng lớn để lấy phần được yêu cầu. Một số hệ có projection hoặc toán tử slice, giúp giảm dữ liệu trả về qua mạng; tuy nhiên không nên suy luận rằng phần còn lại của document hoàn toàn không gây chi phí đọc, giải mã, index hoặc I/O. Hành vi cụ thể cần đo ở sản phẩm thực tế.

Trường hợp người dùng chỉ đọc metadata bài viết cũng tương tự: nếu bản ghi luôn phát triển theo bình luận, read path, cache behavior, document movement và chi phí truy xuất có thể bị ảnh hưởng tùy engine. Một mảng thường xuyên tăng có thể làm **aggregate đọc cùng nhau** trở thành **aggregate quá lớn so với phần cần đọc**.

### 2.3. Cập nhật một phần tử cũng có thể trở nên đắt

Những thao tác tưởng nhỏ như:

~~~text
append comment
edit comment C-927
delete comment C-404
mark one message as read
~~~

có thể phải định vị và cập nhật phần tử trong mảng lớn. Tùy storage engine, cấu trúc lưu trữ, index và kích thước, thao tác có thể làm tăng công việc ghi, di chuyển hoặc tái tổ chức dữ liệu, replication log và áp lực I/O. **Không nên khẳng định mọi cơ sở dữ liệu đều ghi lại toàn bộ document ở mỗi lần thêm phần tử**; cách tối ưu cập nhật khác nhau. Tuy nhiên, chi phí thường trở nên khó dự đoán hơn khi document quá lớn và nhiều writer tranh chấp.

Với mảng có một triệu phần tử, một API muốn sửa một bình luận bất kỳ cũng cần một đường truy cập hợp lý tới bình luận đó. Truy vấn và chỉ mục ở cấp phần tử mảng có thể có giới hạn, còn thao tác xóa một phần tử có thể gây thay đổi cấu trúc mảng.

### 2.4. Một document nóng tạo tranh chấp ghi

Nếu tất cả bình luận của bài P-100 được nhúng vào document P-100, hàng nghìn người cùng bình luận đều ghi vào **cùng một document**.

Điều này có thể gây:

- Cạnh tranh cập nhật vào cùng mục dữ liệu.
- Retry hoặc xung đột khi dùng version/optimistic concurrency.
- Hàng đợi ghi hoặc giới hạn throughput tại khóa nóng.
- Khó phân tán tải ghi bằng cách tăng số node, vì toàn bộ thao tác vẫn quy về một khóa logic.

**Một document lớn và một document nóng là hai vấn đề khác nhau**, nhưng unbounded array có thể gây cả hai: phần tử tăng làm document lớn, người dùng cùng thêm phần tử làm khóa ghi nóng.

### 2.5. Index trên mảng có thể tăng nhanh

Một số hệ hỗ trợ **multikey index**, index nested fields hoặc cấu trúc tương đương. Nếu index từng giá trị trong array, số index entries có thể tăng theo số phần tử và số trường index.

Ví dụ:

~~~json
{
  "postId": "P-100",
  "comments": [
    {"authorId": "U-1", "text": "A"},
    {"authorId": "U-2", "text": "B"},
    {"authorId": "U-3", "text": "C"}
  ]
}
~~~

Index theo **comments.authorId** có thể phải duy trì thông tin cho nhiều tác giả từ cùng document. Khi mảng tăng, dung lượng index, chi phí thêm/xóa phần tử và độ phức tạp truy vấn có thể tăng. Mô hình và giới hạn của index mảng khác nhau theo hệ sản phẩm; không nên giả định một index trên mảng giống hệt index từng document con độc lập.

### 2.6. Replication, backup và migration phức tạp hơn

Document lớn tác động đến nhiều công việc ngoài API:

- Đồng bộ và khôi phục dữ liệu theo cơ chế replication của sản phẩm.
- Sao lưu và restore một tập document có biến động lớn.
- Chạy backfill để thay đổi schema của phần tử lồng nhau.
- Xuất, nhập, xử lý sự cố của một document gần ngưỡng kích thước.
- Tính lại index sau migration hoặc restore.

Một dữ liệu lớn được nhét vào một document khiến khả năng chia nhỏ công việc theo từng phần tử bị hạn chế. Khi tách thành các document độc lập, có thể dùng batch, cursor và công cụ xử lý song song linh hoạt hơn, đổi lại phải quản lý quan hệ và tính nhất quán giữa các bản ghi.

## 3. Ước tính tăng trưởng trước khi chọn nhúng

Không nên chờ hệ thống báo lỗi “document too large” rồi mới điều chỉnh. Ngay lúc thiết kế có thể tính kích thước dự kiến theo thời gian.

### 3.1. Công thức ước tính

Ký hiệu:

- **S_base:** kích thước các trường ngoài mảng.
- **N(t):** số phần tử tại thời điểm t.
- **S_item_avg:** kích thước trung bình mỗi phần tử khi được lưu.
- **H(N):** overhead định dạng và cấu trúc mảng tại số phần tử N.

Ta có:

~~~text
S_doc(t) ≈ S_base + N(t) × S_item_avg + H(N(t))
~~~

Nếu số phần tử tăng trung bình **r phần tử/ngày**:

~~~text
N(t) ≈ N_0 + r × t
~~~

với **t** là số ngày kể từ khi đo; thực tế cần dùng cả kịch bản cao điểm và phần tử lớn bất thường.

Ví dụ đơn giản:

- Một bài viết có 2.000 bình luận ở thời điểm hiện tại.
- Trung bình thêm 1.000 bình luận/ngày.
- Mỗi bình luận có kích thước lưu trữ trung bình giả định 300 byte.
- Chưa tính metadata, tăng trưởng trường khác và overhead.

Sau 100 ngày:

~~~text
N(100) = 2.000 + 1.000 × 100 = 102.000 bình luận

Dung lượng riêng phần nội dung bình luận xấp xỉ:
102.000 × 300 byte = 30.600.000 byte ≈ 30,6 MB (thập phân)
~~~

Đây **chỉ là ước lượng phần payload**, không phải BSON size hay dung lượng vật lý chính xác. Nó cho thấy một document có thể vượt các giới hạn vài đến vài chục MiB dù ban đầu chỉ có vài nghìn phần tử.

### 3.2. Cần đo phân vị và mức cực đại, không chỉ trung bình

Kích thước trung bình 300 byte không nói hết rủi ro:

- 90% bình luận có thể ngắn, 1% có thể chứa văn bản dài.
- Một số bài có rất ít bình luận, bài nổi tiếng có hàng triệu bình luận.
- Một người dùng có thể nhập liên tục hoặc bot tạo đột biến.
- Schema mới có thể thêm trường phụ làm mỗi phần tử lớn hơn.

Vì vậy cần thu thập:

| Đại lượng | Mục đích |
|---|---|
| Phân bố số phần tử theo document: p50, p95, p99, max | Phát hiện bản ghi quá nhiều phần tử |
| Kích thước từng phần tử: p50, p95, p99, max | Dự đoán phần tử lớn bất thường |
| Kích thước toàn document và tốc độ tăng | Xác định headroom tới giới hạn |
| Tần suất ghi theo khóa cha | Phát hiện hot document |
| Số phần tử thực sự trả về trên mỗi request | Nhận diện đọc quá nhiều so với nhu cầu |
| Chi phí/index entries theo mảng | Ước lượng write amplification |

Nếu sản phẩm có một giới hạn cứng **L**, cần đặt **ngưỡng thiết kế thấp hơn L đủ nhiều** để chứa dữ liệu tăng trưởng, metadata và trường hợp bất thường. Không nên đặt mục tiêu vận hành mỗi document sát giới hạn, vì chỉ một phần tử lớn hoặc một thay đổi schema cũng có thể làm cập nhật thất bại.

### 3.3. “Không giới hạn” cần được định nghĩa theo nghiệp vụ

Không phải mọi mảng lớn đều thực sự không giới hạn. Ví dụ:

- Mảng **availableLanguages** có tập giá trị hữu hạn theo sản phẩm.
- Mảng **invoiceLines** có thể được giới hạn tối đa ở API, nhưng phải bảo đảm mọi đường ghi đều thực thi quy tắc đó.
- Mảng **recentEvents** có thể được cắt về 50 phần tử sau mỗi lần thêm, nếu bộ phận sản phẩm chỉ cần 50 sự kiện mới nhất và lịch sử đầy đủ đã lưu nơi khác.

Ngược lại, mảng **allOrders**, **allMessages**, **allEvents**, **allComments**, **allFollowers** và **allNotifications** về bản chất thường tăng theo thời gian. Không nên coi “hôm nay mới có vài phần tử” là biên trên.

## 4. Những mẫu mô hình thay thế mảng tăng vô hạn

Có nhiều giải pháp, tùy theo cách đọc/ghi. Chúng không loại trừ nhau: hệ thống có thể vừa tách collection, vừa lưu một mảng preview có giới hạn, vừa duy trì dữ liệu tổng hợp.

### 4.1. Pattern A — Giữ mảng nhúng có giới hạn (*bounded embedding*)

Với phần tử nhỏ và có biên trên, nhúng vẫn là lựa chọn tốt:

~~~json
{
  "productId": "P-501",
  "name": "Bình nước",
  "featuredImages": [
    {"url": "https://example.test/a.jpg", "position": 1},
    {"url": "https://example.test/b.jpg", "position": 2}
  ],
  "maxFeaturedImages": 8
}
~~~

Ở đây **featuredImages** tối đa 8 ảnh là quy tắc nghiệp vụ; cần kiểm tra ở write API và thao tác nền. Với dữ liệu có thể sửa đồng thời, điều kiện giới hạn phải được áp dụng an toàn theo cơ chế của database, thay vì hai request cùng đọc “còn 7 ảnh” rồi cùng thêm khiến số lượng vượt 8.

**Nên dùng khi** dữ liệu có vòng đời gắn với cha, số lượng có giới hạn chắc chắn, thường đọc cùng cha và cần cập nhật nguyên tử trong cùng document.

**Không nên dùng khi** giới hạn chỉ là kỳ vọng không có biện pháp thực thi, hoặc mỗi phần tử có thể tự lớn bất thường.

### 4.2. Pattern B — Tách phần tử thành document riêng (*referencing / one-to-many*)

Thay vì lưu mọi bình luận trong document bài viết:

~~~json
{
  "postId": "P-100",
  "title": "Một bài viết phổ biến",
  "commentCount": 120000,
  "lastCommentAt": "2026-11-14T08:30:00Z"
}
~~~

Lưu từng bình luận trong collection riêng:

~~~json
{
  "commentId": "C-100820",
  "postId": "P-100",
  "authorId": "U-91",
  "createdAt": "2026-11-14T08:30:00Z",
  "text": "Nội dung bình luận"
}
~~~

Đường truy cập dự kiến:

~~~text
PostById:
  key = postId

CommentsByPost:
  partition / filter = postId
  order = (createdAt DESC, commentId DESC)
  result = 20 bình luận mới nhất
~~~

**Ưu điểm:**

- Document bài viết không tăng theo số bình luận.
- Có thể phân trang, lọc, sửa và xóa bình luận độc lập.
- Không phải cập nhật một mảng cha rất lớn mỗi lần thêm bình luận.
- Dễ định nghĩa index cho từng document bình luận.
- Có thể áp dụng TTL, archive, phân vùng và xử lý hàng loạt cho bình luận nếu chính sách cho phép.

**Đánh đổi:**

- Đọc bài viết và bình luận có thể cần hai truy vấn hoặc read model.
- Trường tổng hợp **commentCount** có thể không đồng bộ với bình luận gốc nếu cập nhật riêng.
- Xóa bài viết cần chính sách xóa hoặc vô hiệu hóa bình luận liên quan.
- Truy vấn theo **postId** có thể vẫn tạo partition nóng nếu một bài được bình luận quá nhiều; tách document không tự loại bỏ mọi điểm nóng.

### 4.3. Pattern C — Dữ liệu con riêng + preview được giới hạn

Nhiều trang chỉ cần hiển thị **vài bình luận gần nhất** trong màn hình bài viết, còn danh sách đầy đủ có API riêng. Có thể kết hợp:

~~~json
{
  "postId": "P-100",
  "title": "Một bài viết phổ biến",
  "commentCount": 120000,
  "recentCommentsPreview": [
    {"commentId": "C-100820", "text": "Bình luận mới"},
    {"commentId": "C-100819", "text": "Bình luận trước"}
  ]
}
~~~

Quy tắc:

~~~text
recentCommentsPreview chỉ giữ tối đa K phần tử.
Danh sách đầy đủ thuộc CommentsByPost.
Nguồn dữ liệu có thẩm quyền cho mỗi bình luận là CommentsByPost.
~~~

**Ưu điểm:** đọc trang tổng quan nhanh, không phải ghép nhiều truy vấn nếu preview đủ.

**Đánh đổi:** tăng chi phí cập nhật và duy trì bản sao; preview có thể trễ hoặc sai nếu pipeline cập nhật lỗi. Cần có thể dựng lại preview từ nguồn.

Một lưu ý quan trọng: nếu nhiều người liên tục thêm bình luận vào cùng bài, cập nhật preview trực tiếp trên document cha ở mỗi bình luận **vẫn có thể tạo hot document**. Khi tải cao, nên cân nhắc preview riêng, cache cập nhật theo lô hoặc chấp nhận độ trễ hiển thị có kiểm soát.

### 4.4. Pattern D — Chia thành bucket theo thời gian hoặc số phần tử

Khi cần lưu các phần tử gần nhau để đọc theo lô nhưng không muốn một document tăng mãi, dùng **bucket pattern**: mỗi document đại diện cho một khoảng thời gian hoặc một nhóm tối đa N phần tử.

Ví dụ chuỗi sự kiện cảm biến:

~~~json
{
  "deviceId": "D-9",
  "bucketDate": "2026-11-14",
  "bucketNo": 3,
  "minTimestamp": "2026-11-14T10:00:00Z",
  "maxTimestamp": "2026-11-14T10:02:00Z",
  "sampleCount": 3,
  "samples": [
    {"at": "2026-11-14T10:00:00Z", "temperature": 24.1},
    {"at": "2026-11-14T10:01:00Z", "temperature": 24.3},
    {"at": "2026-11-14T10:02:00Z", "temperature": 24.2}
  ]
}
~~~

Mẫu khóa logic:

~~~text
partition key = (deviceId, bucketDate)
sort key      = bucketNo

hoặc:

document key = (deviceId, bucketStartTime, bucketNo)
~~~

Quy tắc mở bucket mới có thể dựa trên:

- Thời gian: mỗi giờ hoặc mỗi ngày.
- Số phần tử: tối đa 100, 500 hoặc một ngưỡng xác định qua thử nghiệm.
- Dung lượng byte: ngừng thêm khi gần ngân sách kích thước an toàn.
- Kết hợp: bucket đóng khi đạt bất kỳ ngưỡng nào trước.

**Không được giả định một bucket mỗi ngày luôn có kích thước an toàn.** Nếu một thiết bị phát hàng triệu sự kiện trong ngày, bucket vẫn có thể vượt giới hạn. Cần thêm giới hạn số phần tử/byte hoặc chia theo shard.

Với nhiều writer, cơ chế “đọc count rồi chọn bucket chưa đầy” có thể bị race condition. Có thể dùng atomic conditional append, version check, khóa phối hợp phù hợp hoặc thuật toán cấp bucket khác, tùy khả năng DB. Nếu retry thêm phần tử, phải ngăn trùng bằng eventId và cách ghi idempotent.

**Bucket có ích khi** truy vấn thường đọc các phần tử gần nhau theo thời gian hoặc nhóm, số phần tử mỗi bucket có thể kiểm soát, và việc giải nén/đọc cả bucket phù hợp với access pattern.

**Bucket có thể không phù hợp khi** ứng dụng thường sửa/xóa riêng từng phần tử bằng ID, có nhiều writer tranh chấp cùng bucket hoặc thời hạn giữ khác nhau tới mức xóa từng phần tử trở nên phức tạp.

### 4.5. Pattern E — Tổng hợp và retention thay cho lưu tất cả ở cùng chỗ

Giả sử hệ thống cần thống kê lượt xem sản phẩm theo ngày. API thông thường không cần tải một mảng hàng triệu lượt xem. Có thể giữ:

~~~json
{
  "productId": "P-501",
  "day": "2026-11-14",
  "viewCount": 25742,
  "uniqueViewersEstimate": 19380
}
~~~

Trong khi sự kiện gốc được gửi vào luồng ingest hoặc kho sự kiện riêng, có thời gian giữ phù hợp. Cần làm rõ **viewCount** là giá trị chính xác hay kết quả cập nhật bất đồng bộ; **uniqueViewersEstimate** là ước lượng từ thuật toán nào và sai số chấp nhận được.

Một số use case chỉ cần bản tổng hợp theo giờ/ngày hoặc dữ liệu gần đây. Khi đó có thể áp dụng:

- Retention / TTL cho sự kiện gốc nếu được phép.
- Downsampling dữ liệu time-series.
- Kho lạnh hoặc hệ phân tích cho lịch sử dài hạn.
- Read model phục vụ dashboard.

Không được xóa dữ liệu gốc trước khi xác định yêu cầu nghiệp vụ, đối soát, pháp lý và khả năng tái tính toán.

### 4.6. Bảng chọn nhanh giữa các phương án

| Tiêu chí | Mảng nhúng giới hạn | Document con riêng | Bucket có giới hạn | Chỉ giữ tổng hợp |
|---|---|---|---|---|
| Số phần tử | Nhỏ, có biên trên | Có thể rất lớn | Lớn tổng thể, mỗi bucket giới hạn | Không cần giữ chi tiết tại đây |
| Đọc cùng parent | Rất thuận tiện | Có thể cần truy vấn thứ hai | Thường cần truy vấn bucket | Chỉ đọc summary |
| Phân trang chi tiết | Khó nếu mảng quá lớn | Tự nhiên với index phù hợp | Theo bucket, cần xử lý cursor | Không áp dụng |
| Sửa/xóa từng phần tử | Thuận tiện nếu nhỏ | Thuận tiện | Có thể phức tạp hơn | Phải đi vào nguồn khác |
| Ghi đồng thời | Chung một document | Phân tán theo document con | Có tranh chấp trong bucket | Phụ thuộc pipeline |
| Truy vấn theo thời gian | Giới hạn bởi kích thước | Index theo thời gian | Phù hợp nếu bucket theo thời gian | Phù hợp báo cáo định kỳ |
| Độ chính xác dữ liệu chi tiết | Trực tiếp trong document | Bản ghi con có thẩm quyền | Theo bucket có thẩm quyền | Tùy luồng tổng hợp |

## 5. Truy vấn và phân trang khi tách mảng

Một trong những lợi ích quan trọng nhất của việc tách bình luận, tin nhắn hoặc lịch sử giao dịch thành document riêng là **phân trang hiệu quả**. Nhưng muốn có lợi ích này phải thiết kế key và index đúng.

### 5.1. Tránh tải cả mảng rồi cắt ở ứng dụng

Ví dụ cách làm không phù hợp khi dữ liệu quá lớn:

~~~javascript
// Mã giả minh họa anti-pattern
const post = await posts.findById(postId);
const page = post.comments.slice(offset, offset + 20);
return page;
~~~

Ứng dụng có thể nhận cả mảng rồi chỉ giữ 20 phần tử. Độ trễ và băng thông tăng theo toàn bộ dữ liệu không cần thiết. Nếu database có toán tử lấy một phần array, điều đó có thể giảm lượng trả về, nhưng **không biến mảng không giới hạn thành mô hình có thể mở rộng vô thời hạn**.

### 5.2. Dùng truy vấn theo khóa và thứ tự có index

Document con:

~~~json
{
  "tenantId": "T-1",
  "postId": "P-100",
  "commentId": "C-100820",
  "createdAt": "2026-11-14T08:30:00Z",
  "authorId": "U-91",
  "text": "Nội dung bình luận"
}
~~~

Truy vấn:

~~~text
WHERE tenantId = "T-1" AND postId = "P-100"
ORDER BY createdAt DESC, commentId DESC
LIMIT 20
~~~

Đường index logic:

~~~text
(tenantId, postId, createdAt DESC, commentId DESC)
~~~

Đây là mô hình truy cập minh họa, không phải cú pháp chung cho mọi NoSQL. Một số hệ yêu cầu partition key rõ ràng; một số hỗ trợ compound index; một số cần một bảng/read model riêng để lấy dữ liệu có thứ tự.

### 5.3. Keyset pagination thay cho offset tăng mãi

Nếu dùng offset:

~~~text
Page 1: skip 0, take 20
Page 1000: skip 19980, take 20
~~~

một số cơ sở dữ liệu phải duyệt nhiều mục bị bỏ qua, nên trang rất sâu có thể chậm. Trong danh sách lớn có thứ tự ổn định, **keyset/cursor pagination** thường tốt hơn.

Giả sử phần tử cuối của trang trước là:

~~~json
{
  "createdAt": "2026-11-14T07:59:00Z",
  "commentId": "C-099"
}
~~~

Trang kế tiếp đọc những phần tử nhỏ hơn tuple:

~~~text
WHERE (createdAt, commentId) < (lastCreatedAt, lastCommentId)
ORDER BY createdAt DESC, commentId DESC
LIMIT 20
~~~

Dấu so sánh tuple chỉ là cách viết logic. Tùy hệ, cần triển khai điều kiện tương đương với index phù hợp. **commentId** làm tie-breaker vì nhiều bình luận có thể cùng timestamp; timestamp một mình không bảo đảm thứ tự duy nhất.

Cursor nên chứa đủ thông tin về **tenantId, postId, thứ tự và vị trí cuối**; API cần xác thực nó thuộc phạm vi truy vấn và có thể ký/mã hóa cursor nếu không muốn client chỉnh tùy ý. Khi dữ liệu đang được thêm/xóa, keyset pagination thường ổn định hơn offset, nhưng vẫn cần xác định semantics: lấy snapshot tại một thời điểm hay duyệt luồng đang thay đổi.

### 5.4. Một bài viết rất nóng vẫn có thể tạo hot partition

Tách mỗi comment thành document riêng giúp tránh hot document, nhưng nếu mọi bình luận thuộc **postId = P-100** vẫn được nhóm vào một partition vật lý hoặc logic đơn, nó có thể là điểm nóng.

Với workload đặc biệt cao, cân nhắc:

~~~text
partition key = (tenantId, postId, timeBucket, shardNo)
sort key      = (createdAt, commentId)
~~~

Việc thêm **timeBucket/shardNo** giúp phân tán ghi tùy đặc tính hệ, nhưng đọc 20 bình luận mới nhất có thể phải hợp nhất nhiều shard. Cần thiết kế cursor và thứ tự toàn cục, tránh nhân bản và mất mục khi dữ liệu tới muộn.

Một phương án khác là **fan-out write** hoặc **read model** tổng hợp gần đây theo bài viết. Chọn phương án dựa trên mức skew thực tế, tần suất đọc/ghi và khả năng của database.

## 6. Cập nhật đồng thời và tính đúng đắn khi đổi mô hình

Tách mảng giải quyết kích thước document, nhưng có thể tách một thao tác nguyên tử thành nhiều bước. Đây là đánh đổi cần chủ động xử lý.

### 6.1. Trước khi tách: một aggregate có thể cập nhật nguyên tử

Với document:

~~~json
{
  "postId": "P-100",
  "commentCount": 2,
  "comments": [
    {"commentId": "C-1", "text": "A"},
    {"commentId": "C-2", "text": "B"}
  ]
}
~~~

Nếu database hỗ trợ cập nhật nguyên tử **commentCount** cùng mảng trong một document, ứng dụng có thể giữ chúng khớp trong một thao tác. Nhưng cách này chỉ phù hợp khi mảng đủ nhỏ và tải tranh chấp chấp nhận được.

### 6.2. Sau khi tách: nguồn dữ liệu và projection phải rõ ràng

Nếu bình luận trở thành document riêng và bài viết giữ **commentCount**, một request có thể phải:

1. Tạo document bình luận.
2. Tăng **commentCount** trong bài viết.
3. Cập nhật **recentCommentsPreview**.

Ba bước này **không mặc định là một transaction nguyên tử** nếu nằm ở các document hoặc phân vùng khác nhau. Có thể một bước thành công, bước khác thất bại.

Cần chọn cách bảo đảm:

- **Transaction nhiều document** nếu sản phẩm hỗ trợ với phạm vi, isolation và chi phí chấp nhận được.
- **Sự kiện có thể xử lý lại** để xây count/preview bất đồng bộ từ comment gốc.
- **Outbox hoặc cơ chế phát thay đổi bền vững** gắn với thao tác tạo comment, kết hợp consumer idempotent.
- **Đối soát và rebuild** các trường tổng hợp từ dữ liệu nguồn khi sai lệch.

Một mô hình hợp lý:

~~~mermaid
flowchart TD
    API["POST /posts/{id}/comments"] --> V["Kiểm tra quyền và idempotency key"]
    V --> C[("Comments: nguồn dữ liệu gốc")]
    C --> E["Sự kiện bình luận được lưu/phát bền vững"]
    E --> COUNT[("CommentCount projection")]
    E --> PREVIEW[("RecentComments preview")]
    COUNT --> UI["Trang bài viết"]
    PREVIEW --> UI
~~~

Sơ đồ diễn tả luồng logic. Việc bảo đảm **ghi comment và ghi nhận sự kiện cùng nhau** cần cơ chế cụ thể; không nên coi một lệnh insert và một lệnh publish độc lập là tự động đáng tin cậy.

### 6.3. Idempotency chống bình luận trùng khi retry

Giả sử client gửi bình luận rồi timeout, nhưng server đã lưu thành công. Client gửi lại request; nếu không có khóa idempotency, ứng dụng có thể tạo bình luận thứ hai và tăng count hai lần.

Một thiết kế có thể nhận **clientRequestId** hoặc **commentId** duy nhất theo phạm vi tenant/bài viết và dùng thao tác tạo có điều kiện:

~~~text
createComment(postId, commentId, content):
    nếu (postId, commentId) đã tồn tại:
        trả lại kết quả đã ghi
    nếu chưa:
        tạo comment theo khóa duy nhất
        ghi nhận sự kiện để cập nhật projection
~~~

Điều kiện uniqueness/idempotency phải được thực thi bởi cơ chế đáng tin cậy của storage hoặc transaction, thay vì kiểm tra tồn tại rồi insert tách rời trong môi trường có concurrency. Consumer cập nhật count cũng phải chống xử lý một sự kiện nhiều lần.

### 6.4. Thứ tự của phần tử trong array và trong collection riêng

Một mảng trong document có thứ tự phần tử rõ ràng. Khi tách thành các document riêng, thứ tự phải được biểu diễn:

- **createdAt** cho thứ tự theo thời gian.
- **sequenceNumber** khi nghiệp vụ yêu cầu thứ tự tuyệt đối do hệ thống cấp.
- **position** nếu cho phép người dùng sắp xếp lại thủ công.
- **id tiebreaker** nếu timestamp trùng.

Đồng hồ ở nhiều thiết bị có thể lệch. Nếu chat yêu cầu thứ tự gửi tin nhắn thống nhất trong từng phòng, cần xác định nơi cấp thứ tự có thẩm quyền hoặc chấp nhận thứ tự theo thời gian nhận của máy chủ. Chỉ sắp xếp bằng timestamp do client gửi có thể gây thứ tự bất ngờ.

### 6.5. Xóa parent và dữ liệu con

Khi một bài viết bị xóa nhưng bình luận nằm ở collection riêng, có nhiều chiến lược:

- Xóa mềm parent trước để ngăn đọc/ghi mới; công việc nền xóa comments theo batch.
- Dùng trạng thái **DELETING** rồi hoàn tất cleanup trước khi đánh dấu **DELETED**.
- Giữ dữ liệu con theo chính sách retention nếu nghiệp vụ cho phép; phải kiểm soát quyền và trạng thái hiển thị.

Transaction xóa hàng triệu bình luận cùng lúc thường không phải hướng tối ưu hoặc có thể vượt giới hạn sản phẩm. Batch job cần khả năng tiếp tục sau lỗi, idempotency, theo dõi tiến độ và đối soát. Chính sách quyền riêng tư và retention có thể yêu cầu xóa ở cache, index, backup và các bản sao phát sinh.

## 7. Bucket pattern: thiết kế chi tiết và các bẫy cần tránh

Bucket là một giải pháp trung gian giữa “mọi phần tử chung một document” và “mỗi phần tử một document”. Nó giảm số document hoặc chi phí index trong một số workload, nhưng làm cho cập nhật và truy vấn phức tạp hơn.

### 7.1. Chọn ranh giới bucket từ access pattern

Giả sử một cảm biến gửi 60 mẫu/phút và người dùng thường xem biểu đồ 15 phút gần nhất.

Các phương án:

| Cách chia | Lợi ích | Rủi ro |
|---|---|---|
| 1 bucket/ngày | Ít bucket, thuận tiện báo cáo ngày | Khoảng 86.400 mẫu/ngày; rất dễ lớn nếu phần tử nhiều trường |
| 1 bucket/giờ | 3.600 mẫu/giờ; phù hợp một số truy vấn giờ | Mỗi bucket có thể vẫn lớn; update tập trung |
| 1 bucket/5 phút | 300 mẫu/5 phút; đọc biểu đồ 15 phút qua vài bucket | Số bucket tăng; phải ghép khi đọc |
| Bucket tối đa N mẫu/byte | Kích thước được kiểm soát | Phải cấp bucket mới an toàn khi concurrency |
| Mỗi mẫu một document | Truy cập/sửa từng mẫu độc lập | Nhiều record/index entry, có thể cần tối ưu ingest |

Không có con số bucket tối ưu phổ quát. Một phần tử có 20 byte khác rất nhiều một phần tử có 20 KB. Bucket nên được thiết kế theo **dung lượng byte**, **số phần tử**, **mật độ ghi**, **kích thước truy vấn** và giới hạn sản phẩm.

### 7.2. Tránh kiểm tra giới hạn kiểu đọc rồi ghi

Mã giả dễ sai:

~~~text
bucket = getOpenBucket(deviceId)
if bucket.sampleCount < MAX:
    append(bucket, sample)
~~~

Hai writer có thể cùng đọc **sampleCount = MAX - 1**, cùng thấy “còn chỗ”, rồi ghi làm vượt giới hạn. Cần dùng cơ chế có kiểm tra điều kiện và cập nhật nguyên tử ở phạm vi bucket, optimistic locking hoặc phương án cấp phát bucket phù hợp.

Một cách diễn đạt mục tiêu:

~~~text
appendSample(bucketId, sample):
    chỉ append khi:
        sampleCount < maxCount
        AND estimatedSizeAfterAppend <= safeByteBudget
        AND sampleId chưa được ghi vào bucket
    cập nhật sampleCount/version cùng thao tác
~~~

Đây là **mã giả**, không bảo đảm mọi hệ hỗ trợ điều kiện kích thước/duy nhất như vậy trong một lệnh. Phần kiểm tra duplicate có thể đòi hỏi thiết kế khóa hoặc tập dedupe riêng. Cần dựa trên khả năng thực tế của hệ quản trị.

### 7.3. Bucket theo thời gian không giải quyết mọi vấn đề hotspot

Nếu mọi cảm biến gửi cùng một mẫu/giây, mỗi cảm biến có bucket riêng thì tải trải theo **deviceId**. Nếu một thiết bị phát 100.000 mẫu/giây, bucket hiện tại của chính thiết bị đó có thể vẫn nóng. Có thể kết hợp:

~~~text
(deviceId, fiveMinuteBucket, shardNo)
~~~

và dùng một số shard để phân phối ghi. Khi đọc 5 phút gần nhất, hệ thống phải truy vấn nhiều shard và hợp nhất. Cần cân nhắc tính chính xác của thứ tự và chi phí fan-out.

### 7.4. TTL/retention của bucket cần có quy tắc

Nếu bucket chứa sự kiện từ 23:55 hôm trước đến 00:05 hôm sau, xóa theo ngày bắt đầu có thể khiến một số mẫu chưa hết hạn bị xóa sớm. Nếu bucket chỉ xóa khi tất cả mẫu đều quá hạn, một số mẫu sẽ được giữ lâu hơn yêu cầu.

Nên chọn ranh giới bucket phù hợp thời gian giữ, hoặc chấp nhận/thiết kế rõ phần sai lệch. Khi dữ liệu có retention khác nhau theo loại hoặc theo tenant, cần tránh gom các mục có chính sách xóa xung đột vào cùng bucket.

### 7.5. Index và thống kê metadata của bucket

Metadata như **minTimestamp, maxTimestamp, count, minValue, maxValue** có thể giúp bỏ qua bucket không liên quan khi truy vấn:

~~~json
{
  "deviceId": "D-9",
  "bucketStart": "2026-11-14T10:00:00Z",
  "bucketEnd": "2026-11-14T10:05:00Z",
  "count": 300,
  "minTemperature": 23.9,
  "maxTemperature": 24.6,
  "samples": ["..."]
}
~~~

Metadata phải được cập nhật đúng khi thêm/xóa phần tử; nếu bất đồng bộ thì truy vấn không được coi nó là chứng cứ tuyệt đối để bỏ qua dữ liệu trừ khi thiết kế bảo đảm an toàn. Kích thước và độ phức tạp của bucket cần được cân bằng với lợi ích skip scan.

## 8. Case study: mô hình tin nhắn phòng chat

Một phòng chat có thể tồn tại nhiều năm và nhận hàng triệu tin nhắn. Đây là ví dụ rõ nhất cho unbounded array.

### 8.1. Thiết kế ban đầu

~~~json
{
  "roomId": "R-100",
  "name": "Nhóm dự án",
  "messages": [
    {"id": "M-1", "senderId": "U-1", "text": "Chào"},
    {"id": "M-2", "senderId": "U-2", "text": "Chào bạn"}
  ]
}
~~~

Tại bản demo, lấy tất cả message bằng một lần đọc rất tiện. Nhưng theo thời gian:

- **messages** tăng mãi, nguy cơ vượt giới hạn document.
- Mỗi tin nhắn mới chạm vào cùng document **R-100**.
- Phân trang 50 tin nhắn cũ không hiệu quả khi cần đi sâu.
- Xóa một tin nhắn hoặc cập nhật trạng thái riêng có thể ảnh hưởng mảng lớn.
- Những phòng chat có lưu lượng cao trở thành hot document.

### 8.2. Thiết kế tách theo trách nhiệm

**Room** lưu metadata có kích thước nhỏ:

~~~json
{
  "roomId": "R-100",
  "name": "Nhóm dự án",
  "lastMessageId": "M-200",
  "lastActivityAt": "2026-11-14T08:40:00Z"
}
~~~

**Message** lưu riêng:

~~~json
{
  "roomId": "R-100",
  "messageId": "M-200",
  "senderId": "U-1",
  "sentAt": "2026-11-14T08:40:00Z",
  "text": "Kế hoạch đã cập nhật",
  "status": "VISIBLE"
}
~~~

Đường truy cập:

~~~text
RoomById(roomId)

MessagesByRoom:
    filter/partition = roomId
    sort = (sentAt DESC, messageId DESC)
    limit = 50
    cursor = (lastSentAt, lastMessageId)
~~~

Nếu một phòng quá nóng, có thể cần chia theo thời gian/shard hoặc dùng cơ chế ingest/phân phối riêng. Nếu ứng dụng cần bảo đảm thứ tự tin nhắn nghiêm ngặt trong phòng, phải xác định cách cấp thứ tự hoặc sequencer thay vì chỉ dựa vào đồng hồ client.

### 8.3. Trạng thái đọc chưa chắc thuộc Message

Giả sử 10.000 thành viên có trạng thái “đã đọc đến tin nhắn nào”. Nếu nhúng trạng thái đọc của mọi thành viên vào **mỗi message**, số phần tử có thể tăng cùng số người tham gia và tạo lượng ghi lớn.

Một mô hình có thể dùng **ReadCursor(roomId, userId, lastReadMessageId)**. Khi người dùng đọc, cập nhật cursor riêng của họ. Tính số chưa đọc có thể dùng thứ tự tin nhắn và projection phù hợp, không nhất thiết ghi trạng thái riêng cho mỗi người trên từng tin nhắn.

Đây là ví dụ về việc **mô hình dữ liệu phụ thuộc thao tác cần hỗ trợ**: chức năng “đã đọc” có thể được biểu diễn bằng cursor theo user, thay vì mảng thành viên lồng trong từng message.

### 8.4. Trường lastMessage vẫn có thể nóng

Mặc dù chuyển message thành document riêng, mỗi tin mới vẫn có thể cập nhật **Room.lastMessageId**. Trong phòng cực lớn, metadata Room trở thành điểm ghi nóng.

Có thể điều chỉnh bằng:

- Cập nhật last-message projection bất đồng bộ với độ trễ chấp nhận được.
- Duy trì một bản tóm tắt riêng được cập nhật theo lô.
- Truy vấn index tin nhắn để tìm tin mới nhất nếu độ trễ đạt SLO.

Giảm kích thước document **không tự động giải quyết mọi write contention**; phải xem mọi trường tổng hợp và hotspot còn tồn tại.

## 9. Case study: lịch sử đơn hàng của khách

Một lỗi tương tự là lưu toàn bộ đơn của khách trong document khách hàng:

~~~json
{
  "customerId": "C-42",
  "name": "Lan",
  "orders": [
    {"orderId": "O-1", "total": 200000},
    {"orderId": "O-2", "total": 500000}
  ]
}
~~~

Nếu hệ thống hoạt động nhiều năm, **orders** có thể trở thành unbounded array. Hơn nữa:

- Đơn hàng là thực thể độc lập với quy trình trạng thái và giao dịch riêng.
- Nhiều dịch vụ có thể cập nhật trạng thái giao hàng, thanh toán, hoàn tiền.
- Lịch sử thường cần phân trang, lọc thời gian hoặc trạng thái.
- Một khách hàng lớn có thể tạo nhiều đơn; document khách hàng trở thành điểm nóng.

Một lựa chọn:

~~~text
CustomerById:
    key = (tenantId, customerId)

OrderById:
    key = (tenantId, orderId)

OrdersByCustomer:
    filter/partition = (tenantId, customerId)
    sort = (createdAt DESC, orderId DESC)
~~~

**OrdersByCustomer** có thể là index của dữ liệu đơn gốc hoặc read model riêng. Tùy khả năng hệ quản trị, có thể dùng index bao phủ một số trường để trả danh sách, rồi chỉ truy vấn đơn gốc khi người dùng mở chi tiết.

Nếu UI cần “3 đơn gần nhất” ngay tại profile, có thể nhúng một **recentOrdersPreview tối đa 3 phần tử**, có cơ chế đồng bộ/rebuild. Vấn đề không phải nhúng bị cấm, mà là **nhúng phần dữ liệu có giới hạn và thường được đọc cùng nhau**.

## 10. Những câu hỏi thiết kế cần trả lời trước khi nhúng array

Trước khi thêm một trường **comments: []**, **messages: []**, **history: []** hoặc tương tự, nên trả lời:

1. **Số phần tử tối đa là bao nhiêu?** Giới hạn theo nghiệp vụ, API, storage hay chỉ là ước đoán?
2. **Kích thước từng phần tử lớn đến đâu?** Có chứa text dài, metadata mở rộng, ảnh/file hoặc dữ liệu có thể thay đổi?
3. **Mảng tăng với tốc độ nào?** Theo ngày, theo tenant, theo bài phổ biến, theo thời điểm cao điểm?
4. **Ứng dụng cần đọc bao nhiêu phần tử?** Toàn bộ một lần hay chỉ 20 gần nhất/phân trang?
5. **Cần sửa/xóa từng phần tử hay không?** Nếu có, truy vấn định vị phần tử được index thế nào?
6. **Bao nhiêu writer cùng cập nhật document cha?** Có nguy cơ tranh chấp và hot key?
7. **Mảng có cần atomicity cùng trường cha?** Nếu tách, tính đúng đắn thay đổi thế nào?
8. **Index trên array có chi phí và giới hạn gì?** Có cần filter/sort trên các trường con?
9. **Khi gần chạm kích thước tối đa, hệ thống sẽ làm gì?** Chặn thêm, tạo bucket, chuyển mô hình hay archive?
10. **Dữ liệu có yêu cầu retention, xóa, export hoặc phân vùng theo thời gian không?**

Nếu câu trả lời cho số phần tử tối đa là **“không biết, có thể tăng mãi”**, việc nhúng tất cả vào một document thường cần được xem xét lại.

### 10.1. Bảng quyết định dựa trên workload

| Workload | Thiết kế có thể phù hợp | Vì sao |
|---|---|---|
| Đơn hàng chứa tối đa vài chục dòng | Nhúng **items** | Đọc cùng nhau, cập nhật một aggregate |
| Bài viết có hàng triệu bình luận | **Comments** tách riêng, có index theo post + thời gian | Giới hạn kích thước, phân trang, sửa/xóa độc lập |
| Trang bài viết cần 5 bình luận mới nhất | Preview nhúng có giới hạn + nguồn comment riêng | Đọc nhanh mà không chứa toàn lịch sử |
| Dữ liệu cảm biến đọc theo khoảng thời gian | Document riêng hoặc bucket có giới hạn | Kiểm soát số phần tử, retention và đọc theo lô |
| Phòng chat có tin nhắn liên tục | Message document riêng, cursor phân trang | Tránh hot document và unbounded array |
| Hồ sơ cần 3 địa chỉ giao mặc định | Mảng nhúng có giới hạn | Nhỏ, thuộc cùng vòng đời với profile |
| Hàng triệu lượt xem dùng cho báo cáo | Event store/analytics + aggregates | Không cần trả toàn bộ sự kiện qua API giao dịch |

## 11. Di chuyển một mảng đang tăng trưởng sang mô hình mới

Đổi cấu trúc từ một document cha có mảng lớn sang collection con không chỉ là thao tác tách JSON. Hệ thống đang có người dùng và ghi mới cần tránh mất phần tử, trùng lặp hoặc chênh số liệu.

Một kế hoạch migration hợp lý:

### Giai đoạn 1: Xác định nguồn và schema mới

Với mỗi phần tử cũ, xác định khóa duy nhất ổn định:

~~~text
old:
  Post(postId, comments[])

new:
  Post(postId, metadata, commentCount)
  Comment(postId, commentId, createdAt, authorId, text)
~~~

Nếu phần tử cũ không có **commentId**, cần quy tắc tạo ID ổn định để chạy lại migration không tạo trùng. Đánh dấu **version/schemaVersion** ở mức cần thiết giúp biết record đã di chuyển hay chưa.

### Giai đoạn 2: Chuẩn bị đường đọc/ghi tương thích

Ứng dụng có thể tạm hỗ trợ cả schema cũ và mới. Cần xác định **một nơi có thẩm quyền cho ghi mới** tại mỗi giai đoạn và cách đồng bộ thay đổi. Dual-write vào hai nơi mà không có transaction hoặc cơ chế sự kiện bền vững có thể tạo sai lệch nếu một lần ghi thành công và lần còn lại thất bại.

Nếu cần duy trì dữ liệu cũ trong thời gian chuyển đổi, có thể dùng outbox/CDC, log nghiệp vụ hoặc tạm dừng ghi theo cửa sổ bảo trì phù hợp.

### Giai đoạn 3: Backfill theo lô, có thể chạy lại

Chạy đọc document cha, tách từng phần tử và tạo document con theo khóa duy nhất. Chia batch để tránh một job chiếm quá nhiều tài nguyên. Ghi lại mốc tiến độ, version hoặc cursor.

~~~text
for each parent document:
    for each child in parent.children:
        upsert child by stableChildId
    mark backfill progress
~~~

Mã giả nhấn mạnh **idempotent upsert** và kiểm soát tiến độ. Nếu dữ liệu nguồn vẫn thay đổi, snapshot backfill phải được phối hợp với cơ chế bắt thay đổi hoặc giai đoạn cutover để không bỏ sót phần tử phát sinh trong lúc job chạy.

### Giai đoạn 4: Đối soát trước khi cutover

Đối soát:

- Số phần tử của từng parent và số document con.
- ID duy nhất, không trùng lặp.
- Giá trị quan trọng như text, authorId, createdAt.
- Kết quả truy vấn 20 mới nhất trước/sau.
- Các bản ghi thêm, sửa, xóa trong thời gian backfill.

Nếu có trường **commentCount** hoặc preview, nên xác định cách tái tạo từ nguồn thay vì dựa vào giá trị sai lệch được mang sang.

### Giai đoạn 5: Chuyển đường đọc, ngừng ghi schema cũ

Thay API đọc comment từ collection con, theo dõi p95/p99 latency, lỗi phân trang, missing/duplicate và consistency. Chỉ loại bỏ mảng cũ khi chắc chắn không còn đường ghi/đọc phụ thuộc, đã có backup/rollback phù hợp và chính sách xóa cho phép.

### Giai đoạn 6: Dọn dữ liệu và đánh giá lại chỉ mục

Xóa mảng cũ khỏi document cha có thể giảm kích thước rất nhiều, nhưng thao tác trên record gần giới hạn cần được thử với cơ chế update của hệ. Sau migration cần điều chỉnh index, backup, retention và dashboard giám sát. Có thể còn bản sao trong backup và hệ phân tích; các bản sao này phải được quản lý theo chính sách vòng đời dữ liệu.

## 12. Giám sát: phát hiện rủi ro trước khi production lỗi

Một thiết kế dùng mảng nhúng nên được quan sát bằng chỉ số tương quan với tăng trưởng:

| Chỉ số | Ý nghĩa |
|---|---|
| Kích thước document p50/p95/p99/max | Nhìn thấy tăng trưởng và bản ghi sát ngưỡng |
| Độ dài mảng p50/p95/p99/max | Phát hiện bất thường của một số thực thể |
| Tăng trưởng byte/ngày theo nhóm record | Ước lượng thời gian hết headroom |
| Append/update latency p95/p99 | Phát hiện chi phí ghi tăng |
| Document/partition hot keys | Phát hiện tranh chấp và throttling |
| Index size / entries / write amplification | Nhìn chi phí index của mảng |
| Read bytes so với bytes trả về hữu ích | Phát hiện đọc thừa khi chỉ cần vài phần tử |
| Lỗi document-too-large / validation | Tín hiệu giới hạn kỹ thuật đã bị chạm |
| Retry/conflict rate | Phát hiện cạnh tranh ghi vào parent hoặc bucket |
| Projection lag / reconciliation mismatch | Phát hiện dữ liệu nhân bản chậm hoặc thiếu |

Đối với một mảng được chủ đích giới hạn, nên có metric theo dõi **số lần đạt ngưỡng**, số lần từ chối thêm và các bản ghi có kích thước bất thường. Nếu hệ thống chỉ theo dõi giá trị trung bình, một bài viết nổi tiếng hoặc một phòng chat nóng có thể vượt giới hạn dù trung bình toàn collection còn thấp.

### 12.1. Giới hạn bảo vệ ở tầng ứng dụng và tầng dữ liệu

Một hệ thống nên có các lớp bảo vệ thích hợp:

- **Giới hạn nội dung phần tử:** ví dụ độ dài bình luận, kích thước payload, số trường mở rộng.
- **Giới hạn số phần tử trong mảng nhúng:** thực thi an toàn khi có concurrent writes.
- **Ngân sách kích thước:** đặt thấp hơn giới hạn cứng theo kết quả đo.
- **Cơ chế rollover:** tạo bucket mới hoặc chuyển sang collection con khi gần ngưỡng.
- **Chính sách từ chối có thể hiểu được:** nếu không thể ghi, API thông báo đúng nguyên nhân và bảo đảm request không tạo tác dụng phụ mơ hồ.
- **Alert tăng trưởng và hot key:** phát hiện xu hướng trước khi ảnh hưởng người dùng.

Giới hạn ở API đơn lẻ có thể không đủ nếu có import, background job hoặc nhiều dịch vụ ghi trực tiếp. Những đường ghi này cần dùng cùng quy tắc hoặc được bảo vệ ở tầng storage.

## 13. Những ngộ nhận thường gặp

### “NoSQL document linh hoạt nên có thể chứa bất kỳ số lượng phần tử nào”

Linh hoạt về schema không có nghĩa không có giới hạn kích thước, index và hiệu năng. Mảng có thể tăng cho đến khi một ghi hợp lệ về nghiệp vụ bị database từ chối.

### “Mỗi phần tử nhỏ nên một triệu phần tử vẫn an toàn”

Kích thước tổng bằng tổng phần tử, metadata và phần document còn lại. Ngay cả phần tử vài trăm byte cũng có thể đưa document tới hàng chục hoặc hàng trăm MB khi số lượng đủ lớn.

### “Dùng projection hoặc slice là đã giải quyết mảng lớn”

Projection có thể giảm dữ liệu trả về, nhưng không thay đổi số phần tử được lưu trong document, rủi ro tăng trưởng, tranh chấp ghi và chi phí index. Nên đánh giá cả đường ghi và giới hạn lưu trữ.

### “Atomic update trên document cho phép mọi người cùng append không giới hạn”

Atomicity bảo vệ một thao tác trong phạm vi của nó; nó không làm document vô hạn hoặc loại bỏ hot-key contention. Nhiều writer vẫn tranh chấp cùng bản ghi.

### “Tách phần tử thành collection riêng thì không cần nghĩ về consistency”

Khi parent giữ count, preview, lastActivity hoặc thống kê, dữ liệu bị nhân bản giữa các document. Cần transaction phù hợp hoặc cập nhật bất đồng bộ có idempotency và đối soát.

### “Chia bucket theo ngày sẽ bảo đảm mỗi bucket nhỏ”

Một ngày có thể chứa một triệu sự kiện ở tenant hoặc thiết bị nóng. Bucket nên giới hạn theo byte hoặc số phần tử, kết hợp thời gian nếu cần.

### “Lưu mỗi tin nhắn thành document riêng thì hotspot biến mất”

Nếu toàn bộ message vẫn dùng một partition key có giới hạn tải, hoặc mỗi message đều cập nhật Room.lastMessageId, hệ thống vẫn có hot partition/document. Cần đo và điều chỉnh cả các đường ghi phụ.

### “Muốn hiển thị tổng số bình luận thì phải ghi chính xác trong cùng document với mỗi bình luận”

Không nhất thiết. Count có thể là projection được duy trì từ nguồn có thẩm quyền, có SLA về độ trễ và cơ chế đối soát. Nếu nghiệp vụ yêu cầu count chính xác ngay trong mọi trường hợp, phải xác định cơ chế ghi/transaction đáp ứng ràng buộc đó.

## 14. Quy trình quyết định và thực hành

Khi định lưu một mảng lồng nhau trong document, hãy thực hiện:

1. **Viết access pattern:** màn hình nào đọc parent, có đọc tất cả child không, có phân trang/lọc/sắp xếp không?
2. **Xác định cardinality:** số child tối đa, trung bình, p99; tốc độ tăng và đỉnh của một parent phổ biến.
3. **Ước tính dung lượng:** byte mỗi child, overhead, tốc độ tăng, ngân sách an toàn dưới giới hạn sản phẩm.
4. **Kiểm tra write pattern:** bao nhiêu writer cập nhật cùng document, cần sửa/xóa riêng child không?
5. **Xác định ranh giới atomicity:** child có phải cập nhật cùng parent không, count/preview có thể trễ không?
6. **So sánh mô hình:** nhúng có giới hạn, child collection, bucket, preview, summary; tính cả read/write amplification.
7. **Thiết kế khóa/index/cursor:** đặc biệt cho danh sách có thứ tự và các parent có tải lớn.
8. **Kiểm tra đặc tính sản phẩm:** giới hạn document, nested depth, index mảng, atomic update, transaction, replication.
9. **Thử tải có skew:** tạo bài viết/phòng chat/tenant cực nóng, document gần ngưỡng, nhiều writer và pagination sâu.
10. **Chuẩn bị migration/monitoring:** biết khi nào phải tách mô hình và cách đối soát trước/sau.

Một bản ghi quyết định kỹ thuật có thể theo mẫu:

~~~text
Entity: BlogPost
Nested array: recentCommentsPreview
Hard business cap: 5 comments
Source of truth: Comments collection
Read path: PostById for page preview; CommentsByPost for full list
Write path: Insert comment then update preview asynchronously
Consistency: Preview may lag by a documented short interval
Index: (tenantId, postId, createdAt DESC, commentId DESC)
Hot key handling: Keep preview updates out of the critical write path
Monitoring: Post size, comment write p99, projection lag, mismatches
~~~

Mẫu trên chỉ minh họa tư duy. Mức trễ chấp nhận được, giới hạn, chỉ mục và giải pháp hot key phải được chọn từ workload thực tế, không sao chép nguyên dạng cho mọi dự án.

## 15. Bài tập áp dụng

### Bài 1 — Mảng đánh giá sản phẩm

Một document sản phẩm chứa trường **reviews**; mỗi ngày sản phẩm bán chạy có 2.000 đánh giá mới, mỗi đánh giá lưu trung bình 400 byte. Trang sản phẩm chỉ hiện 10 đánh giá mới nhất, người dùng có thể lọc theo số sao.

Yêu cầu:

1. Ước tính phần payload mảng sau 30 và 365 ngày, bỏ qua overhead.
2. Giải thích vì sao dữ liệu tăng trưởng gây rủi ro ngay khi chưa chạm giới hạn cứng.
3. Thiết kế collection đánh giá riêng và đường index để lấy 10 đánh giá mới nhất hoặc theo số sao.
4. Đề xuất **ratingSummary** và cách giữ số sao trung bình đúng khi một đánh giá bị sửa hoặc xóa.

### Bài 2 — Dữ liệu cảm biến

Một cảm biến gửi 120 mẫu/phút. Hệ thống muốn nhúng tất cả mẫu mỗi ngày vào một document. Mỗi mẫu lưu trung bình 160 byte.

Yêu cầu:

1. Tính số mẫu/ngày và phần payload/ngày.
2. Phân tích bucket 5 phút, bucket 1 giờ và bucket tối đa 500 mẫu.
3. Xác định cách xử lý khi nhiều worker ghi cùng bucket.
4. Thiết kế retention 90 ngày và việc xóa bucket có ảnh hưởng tới mẫu sát ranh giới thời gian không.

### Bài 3 — Phòng chat đông người

Một phòng chat có 50.000 thành viên, 100 tin/giây. Nhóm muốn lưu **messages[]** và **readByUsers[]** trong document Room.

Yêu cầu:

1. Phân tích hai mảng tăng trưởng theo những chiều khác nhau ra sao.
2. Đề xuất Message collection và ReadCursor theo user.
3. Thiết kế API phân trang 50 tin cũ bằng cursor ổn định.
4. Giải thích vì sao chỉ tách Message mà vẫn cập nhật Room mỗi tin có thể còn hotspot.

### Bài 4 — Chuyển đổi dữ liệu khi đang có traffic

Hệ thống đã có hàng triệu Post document chứa **comments[]**. Mỗi ngày vẫn phát sinh bình luận mới. Cần chuyển sang collection Comments mà không mất hoặc nhân đôi bình luận.

Yêu cầu:

1. Đề xuất khóa comment ổn định để chạy backfill nhiều lần.
2. Lập kế hoạch đồng bộ các bình luận mới trong lúc migration.
3. Mô tả cách đối soát count, ID và thứ tự trước cutover.
4. Nêu rủi ro khi dual-write trực tiếp hai collection mà không có bảo đảm transaction hoặc outbox.

### Bài 5 — Lựa chọn nhúng hay tách

Cho bốn quan hệ:

- Customer → 3 địa chỉ mặc định.
- Order → 15 dòng hàng.
- Article → 2 triệu bình luận.
- User → lịch sử đăng nhập 5 năm.

Hãy chọn nhúng, tách, bucket hoặc summary cho từng quan hệ; giải thích theo **giới hạn số phần tử, truy vấn, cập nhật đồng thời, retention và chi phí vận hành**.

---

**Kết luận:** Mảng lồng nhau là một công cụ mạnh khi dữ liệu con **nhỏ, có biên trên và thường được đọc/cập nhật cùng document cha**. Khi phần tử tăng không giới hạn, mô hình đó có thể gặp giới hạn kích thước, đọc/ghi tốn kém, index phình to và tranh chấp trên một bản ghi nóng. Giải pháp không nhất thiết là bỏ nhúng hoàn toàn: hãy giữ phần **có giới hạn** trong document, tách lịch sử lớn thành document con hoặc bucket được khống chế kích thước, và chỉ nhân bản preview/tổng hợp khi có cách kiểm soát nhất quán. Quyết định cuối cùng phải dựa trên workload, kích thước đo được, ranh giới atomicity và giới hạn của hệ quản trị đang dùng.

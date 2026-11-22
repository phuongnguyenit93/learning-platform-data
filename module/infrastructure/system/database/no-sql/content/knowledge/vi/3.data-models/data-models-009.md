# Khả năng hỗ trợ nhiều mô hình trong cùng một hệ quản trị

## 1. Vì sao một hệ quản trị cơ sở dữ liệu lại hỗ trợ nhiều mô hình?

Trong các hệ thống thực tế, dữ liệu thường không có cùng hình dạng và không được truy cập theo cùng một cách. Chẳng hạn, một nền tảng học tập có thể cần:

- Lưu hồ sơ học viên với nhiều thuộc tính tùy chọn: tên, ngôn ngữ, kỹ năng và tùy chọn cá nhân.
- Lấy nhanh phiên đăng nhập hoặc tiến độ học của một học viên theo mã định danh.
- Tìm các khóa học có liên quan thông qua mối quan hệ giữa học viên, chủ đề và bài học.
- Tìm kiếm nội dung bài học theo từ khóa, bộ lọc và mức độ liên quan.
- Phân tích lượt tương tác theo khoảng thời gian.

Một cách tiếp cận là dùng nhiều loại cơ sở dữ liệu khác nhau. Một cách khác là chọn **hệ quản trị đa mô hình (multi-model database management system)**, tức hệ có khả năng biểu diễn và truy vấn **nhiều mô hình dữ liệu** trong phạm vi một sản phẩm, một dịch vụ hoặc một động cơ cơ sở dữ liệu.

Ý tưởng cốt lõi: **giữ được cách biểu diễn phù hợp cho từng loại dữ liệu mà không bắt buộc phải vận hành một hệ quản trị độc lập cho mỗi mô hình**. Tuy vậy, mức tích hợp của các mô hình có thể rất khác nhau giữa các sản phẩm. “Có nhiều API” không tự động đồng nghĩa “mọi mô hình cùng sử dụng một kho lưu trữ và một giao dịch”.

### Mục tiêu của bài

Sau bài học, người đọc có thể:

1. Phân biệt **multi-model database** với **polyglot persistence** (dùng nhiều hệ quản trị chuyên biệt).
2. Nhận diện các mô hình document, key–value, graph và các khả năng bổ sung thường gặp.
3. Hiểu sự khác nhau giữa hỗ trợ đa mô hình **tự nhiên**, thông qua **phần mở rộng**, hoặc qua **nhiều API/dịch vụ**.
4. Thiết kế một ví dụ kết hợp document và graph trong cùng hệ quản trị.
5. Đánh giá lợi ích và đánh đổi về truy vấn, giao dịch, chỉ mục, mở rộng, vận hành và ràng buộc nhà cung cấp.

## 2. Làm rõ ba khái niệm thường bị nhầm lẫn

| Khái niệm | Bản chất | Ví dụ minh họa |
|---|---|---|
| **Mô hình dữ liệu (data model)** | Cách biểu diễn thực thể và quan hệ: tài liệu, cặp khóa–giá trị, đỉnh/cạnh, bảng, chuỗi thời gian... | Hồ sơ người dùng là document; quan hệ theo dõi là cạnh graph |
| **Giao diện truy cập (API/query language)** | Cách ứng dụng đọc, ghi và truy vấn dữ liệu | Truy vấn theo khóa, truy vấn graph traversal hoặc một ngôn ngữ truy vấn thống nhất |
| **Động cơ lưu trữ (storage engine)** | Thành phần tổ chức dữ liệu trên đĩa/bộ nhớ và xử lý chỉ mục, transaction, replication | Một động cơ chung có thể phục vụ nhiều mô hình, hoặc mỗi mô hình dùng một động cơ khác nhau |

Ba lớp này liên quan nhưng không đồng nhất. Chẳng hạn:

- Một hệ document cho phép tra cứu tài liệu bằng khóa chính. Nó có **kiểu truy cập key–value**, nhưng không nhất thiết cung cấp mọi tính năng của một hệ key–value chuyên dụng.
- Một hệ document lưu danh sách mã bạn bè trong mảng. Nó có thể **biểu diễn quan hệ**, nhưng chưa chắc hỗ trợ duyệt graph nhiều bước hiệu quả.
- Một nền tảng cung cấp API tương thích với document và graph có thể triển khai trên **những dịch vụ hoặc kiểu tài khoản tách biệt**, với giới hạn dữ liệu và giao dịch riêng.

Vì vậy, khi nghe “hỗ trợ nhiều mô hình”, cần hỏi: **nhiều cấu trúc dữ liệu, nhiều cách truy vấn, hay thực sự cùng một nền tảng giao dịch/lưu trữ?**

## 3. Các mô hình dữ liệu có thể cùng tồn tại

### 3.1. Document: lưu thực thể có cấu trúc linh hoạt

Document thường dùng đối tượng JSON hoặc dạng nhị phân tương đương, có thuộc tính lồng nhau và mảng.

~~~json
{
  "_key": "student-101",
  "displayName": "Minh",
  "city": "Da Nang",
  "skills": ["Java", "NoSQL"],
  "preferences": {
    "language": "vi",
    "theme": "dark"
  }
}
~~~

Mô hình này phù hợp khi ứng dụng thường tải toàn bộ một thực thể, khi các thuộc tính thay đổi theo loại đối tượng, hoặc khi dữ liệu con có cùng vòng đời với dữ liệu cha.

**Lưu ý:** document không có nghĩa là không cần schema. Ứng dụng vẫn phải quy định trường bắt buộc, kiểu dữ liệu, phiên bản cấu trúc, validation và cách xử lý tài liệu cũ.

### 3.2. Key–value: tìm nhanh theo định danh

Với key–value, mỗi khóa xác định một giá trị. Cách truy cập điển hình là `GET(key)`, `PUT(key, value)` hoặc `DELETE(key)`.

~~~text
student:101:progress  -> { course: "nosql", lesson: 8 }
session:abc-123       -> { studentId: "student-101", expiresAt: "..." }
~~~

Nhiều hệ document hỗ trợ lấy tài liệu theo khóa chính rất hiệu quả, nên có thể phục vụ **một phần nhu cầu key–value** ngay trong cơ sở dữ liệu document. Nhưng các tính năng như TTL tự động, toán tử tăng đếm nguyên tử, cấu trúc dữ liệu trong bộ nhớ hoặc độ trễ đặc thù của một kho key–value chuyên dụng cần được xác minh theo sản phẩm.

### 3.3. Graph: mô hình hóa và duyệt quan hệ

Graph biểu diễn đối tượng thành **đỉnh (vertex)** và quan hệ thành **cạnh (edge)**. Cạnh có thể có hướng và mang thuộc tính.

~~~text
[Học viên Minh] -- THEO_DÕI --> [Học viên Lan]
       |                             |
       +-- HOÀN_THÀNH --> [Bài NoSQL] <-- ĐĂNG_KÝ --+
~~~

Những bài toán phù hợp gồm đường đi ngắn, quan hệ bạn bè nhiều cấp, phụ thuộc giữa các dịch vụ, mạng tri thức hoặc đề xuất dựa trên liên kết.

Khác với việc chỉ lưu mảng ID trong JSON, hệ có **hỗ trợ graph thực sự** thường cung cấp mô hình cạnh, chỉ mục cho quan hệ và phép duyệt theo số bước/chiều đi, giúp diễn đạt truy vấn một cách tự nhiên hơn.

### 3.4. Các mô hình và khả năng khác

Một số hệ đa mô hình còn hỗ trợ bảng/quan hệ, dữ liệu cột, time series, geospatial, vector hoặc tìm kiếm toàn văn. **Không có tập khả năng bắt buộc chung cho mọi multi-model DBMS.** Đặc biệt, cần phân biệt **một mô hình dữ liệu được quản lý trực tiếp** với **một loại chỉ mục hoặc toán tử truy vấn**. Ví dụ, chỉ mục full-text có thể được xây trên document; điều đó không nhất thiết biến cơ sở dữ liệu thành một công cụ tìm kiếm chuyên dụng.

## 4. Những mức độ hỗ trợ đa mô hình

Có thể phân loại khả năng đa mô hình theo cách tích hợp, thay vì chỉ đếm tên các mô hình trên trang giới thiệu sản phẩm.

| Kiểu hỗ trợ | Cách hoạt động | Lợi ích chính | Điều cần kiểm tra |
|---|---|---|---|
| **Native / unified multi-model** | Một động cơ hỗ trợ trực tiếp nhiều cách biểu diễn và truy vấn; dữ liệu có thể dùng chung định danh, bảo mật và công cụ vận hành | Có thể kết hợp truy vấn các mô hình và giảm sao chép giữa những kho riêng | Mức nguyên tử của transaction, giới hạn cross-shard, công cụ chỉ mục, hiệu năng từng mô hình |
| **Mô hình chính + tính năng bổ sung** | Một cơ sở dữ liệu chủ yếu theo document hoặc quan hệ, nhưng thêm JSON, truy vấn đệ quy, key lookup, graph extension... | Tái sử dụng công nghệ quen thuộc, tránh chuyển toàn bộ nền tảng | Tính năng có thực sự tương đương hệ chuyên dụng không? Phần mở rộng có được duy trì và hỗ trợ không? |
| **Nhiều API trong một dịch vụ/nền tảng** | Một nhà cung cấp cho truy cập qua các API hoặc kiểu tài khoản dành cho những mô hình khác nhau | Có thể dùng giao diện phù hợp với client hiện tại | Các API có dùng cùng dữ liệu, truy vấn xuyên API, giao dịch, backup và quota không? |
| **Một ứng dụng dùng nhiều DBMS (polyglot persistence)** | Chọn các cơ sở dữ liệu khác nhau cho các nghiệp vụ khác nhau | Tối ưu sâu cho từng bài toán | Đồng bộ dữ liệu, transaction liên hệ thống, monitoring, vận hành, chi phí và độ phức tạp |

**Ví dụ định hướng:** ArangoDB là một hệ thường được giới thiệu như cơ sở dữ liệu đa mô hình document/graph/key–value với ngôn ngữ truy vấn AQL; các thao tác cụ thể còn phụ thuộc phiên bản và cấu hình. PostgreSQL là hệ quan hệ có JSON/JSONB và khả năng truy vấn phong phú, có thể đáp ứng một số nhu cầu đa mô hình mà không chuyển sang một DBMS mới. Các nền tảng cloud có nhiều API cần được xem xét ở mức cấu hình tài khoản và tính năng cụ thể; **không nên mặc định nhiều API luôn thao tác trên cùng một tập dữ liệu**.

### Phân biệt với polyglot persistence

~~~mermaid
flowchart LR
  subgraph A["Phương án đa mô hình trong một hệ quản trị"]
    App1["Ứng dụng"] --> Unified["Hệ quản trị đa mô hình"]
    Unified --> Doc["Document"]
    Unified --> Key["Key lookup"]
    Unified --> Graph["Graph"]
  end
  subgraph B["Phương án nhiều hệ quản trị"]
    App2["Ứng dụng"] --> Db1["Document DB"]
    App2 --> Db2["Key–value DB"]
    App2 --> Db3["Graph DB"]
    Db1 -. "Sự kiện / ETL" .-> Db3
  end
~~~

Sơ đồ bên trái mang tính **logic**: một sản phẩm đa mô hình vẫn có thể chạy trên nhiều nút, nhiều shard và nhiều lớp lưu trữ ở bên trong. Sơ đồ bên phải cho thấy ứng dụng hoặc tầng tích hợp phải phối hợp các kho riêng.

## 5. Ví dụ xuyên suốt: nền tảng học tập dùng document và graph

Giả sử cần xây dựng tính năng “học viên mà bạn theo dõi và bài học họ đã viết”. Hệ thống có ba loại dữ liệu:

1. **Học viên:** hồ sơ, ngôn ngữ, kỹ năng và trạng thái hoạt động — phù hợp với document.
2. **Bài viết học tập:** tiêu đề, nội dung, thẻ — phù hợp với document.
3. **Quan hệ:** học viên A theo dõi B, học viên B viết bài X — phù hợp với graph.

Nếu dùng một hệ có document và graph, một tài liệu học viên có thể **đồng thời là đỉnh** của graph. Cạnh tham chiếu tài liệu theo định danh. Không cần tạo thêm một bản sao hồ sơ trong một graph database riêng chỉ để duyệt quan hệ.

### 5.1. Dữ liệu mẫu

Hình dung các collection:

- `users`: các document học viên; mỗi document có khóa riêng.
- `posts`: các document bài viết.
- `follows`: các cạnh “theo dõi”, hướng từ người theo dõi đến người được theo dõi.
- `writes`: các cạnh “viết”, hướng từ học viên đến bài viết.

~~~json
{
  "_id": "users/u101",
  "_key": "u101",
  "displayName": "Minh",
  "skills": ["Java", "NoSQL"],
  "active": true
}
~~~

~~~json
{
  "_id": "users/u102",
  "_key": "u102",
  "displayName": "Lan",
  "skills": ["MongoDB", "Graph"],
  "active": true
}
~~~

~~~json
{
  "_id": "posts/p201",
  "_key": "p201",
  "title": "Tìm hiểu mô hình document",
  "tags": ["database", "nosql"]
}
~~~

Quan hệ được biểu diễn bằng edge document:

~~~json
{
  "_from": "users/u101",
  "_to": "users/u102",
  "since": "2026-01-15"
}
~~~

~~~json
{
  "_from": "users/u102",
  "_to": "posts/p201",
  "role": "author"
}
~~~

Trong ví dụ này, các trường `_id`, `_key`, `_from` và `_to` dùng theo cách biểu diễn đặc trưng của ArangoDB. Hệ khác có thể dùng định dạng đỉnh/cạnh khác. Với ArangoDB, `follows` và `writes` cần được tạo ở dạng **edge collection** trước khi ghi cạnh; `users` và `posts` là **document collection**.

### 5.2. Truy vấn document theo thuộc tính

Ví dụ bằng AQL, lấy những học viên đang hoạt động và có kỹ năng NoSQL:

~~~aql
FOR u IN users
  FILTER u.active == true
  FILTER "NoSQL" IN u.skills
  SORT u.displayName ASC
  RETURN {
    id: u._id,
    name: u.displayName,
    skills: u.skills
  }
~~~

Đây là truy vấn trên **thuộc tính document**. Nếu tập dữ liệu lớn, cần xét chỉ mục và kế hoạch truy vấn của chính hệ quản trị; không nên giả định mọi bộ lọc trên mảng đều nhanh.

### 5.3. Truy vấn theo khóa

Lấy đúng học viên có định danh đã biết:

~~~aql
RETURN DOCUMENT("users/u101")
~~~

Cách này thể hiện nhu cầu **key lookup** ngay trên một collection document. Khả năng truy xuất theo khóa chính không đồng nghĩa toàn bộ sản phẩm là key–value engine chuyên dụng.

### 5.4. Truy vấn graph một bước

Lấy những học viên mà Minh đang theo dõi:

~~~aql
FOR v, e IN 1..1 OUTBOUND "users/u101" follows
  FILTER v.active == true
  RETURN {
    id: v._id,
    name: v.displayName,
    since: e.since
  }
~~~

Ý nghĩa từng thành phần:

- `1..1`: chỉ duyệt đúng **một cạnh**.
- `OUTBOUND`: đi theo hướng từ `_from` sang `_to`.
- `"users/u101"`: đỉnh xuất phát.
- `follows`: edge collection được dùng để duyệt.
- `v` và `e`: lần lượt là đỉnh và cạnh được gặp trong quá trình duyệt.

Truy vấn này kết hợp **quan hệ graph** (ai theo dõi ai) với **thuộc tính document** (học viên còn hoạt động hay không) mà không cần truy vấn một hệ graph riêng rồi gọi tiếp sang một hệ document để lấy hồ sơ.

### 5.5. Kết hợp hai loại quan hệ

Từ học viên `u101`, tìm những bài viết của người mà họ đang theo dõi:

~~~aql
FOR followed IN 1..1 OUTBOUND "users/u101" follows
  FILTER followed.active == true
  FOR post IN 1..1 OUTBOUND followed writes
    FILTER "nosql" IN post.tags
    RETURN DISTINCT {
      author: followed.displayName,
      postId: post._id,
      title: post.title
    }
~~~

Đây là ví dụ **kết hợp mô hình trong một truy vấn**:

- Document chứa hồ sơ và nội dung.
- Graph xác định hướng và chuỗi quan hệ.
- Bộ lọc document giới hạn kết quả.
- Ngôn ngữ truy vấn giúp biểu đạt cả hai cách truy cập.

Trong dữ liệu mẫu, thẻ `"database"` và `"nosql"` phải khớp chính xác giá trị dùng để lọc; hệ thống cần thống nhất quy tắc chuẩn hóa chữ hoa/chữ thường nếu nghiệp vụ có nhu cầu tìm kiếm không phân biệt hoa thường.

~~~mermaid
flowchart LR
  U1["users/u101: Minh"] -->|follows| U2["users/u102: Lan"]
  U2 -->|writes| P1["posts/p201: Bài document"]
  U1 --- D1["Document: hồ sơ"]
  P1 --- D2["Document: nội dung"]
~~~

**Điểm quan trọng:** hệ đa mô hình không tự hiểu mọi quan hệ được giấu trong một chuỗi ID hoặc một mảng. Muốn duyệt bằng graph, vẫn cần thiết kế đỉnh, cạnh, chiều liên kết, chỉ mục và giới hạn đường đi phù hợp.

## 6. Lợi ích khi nhiều mô hình được hỗ trợ trong một DBMS

### 6.1. Một thực thể có thể phục vụ nhiều cách truy cập

Hồ sơ học viên được đọc như document theo khóa, lọc theo thuộc tính và dùng làm đỉnh khi duyệt graph. Nếu hệ thống hỗ trợ dùng chung dữ liệu thực sự, ứng dụng không cần duy trì nhiều bản sao của cùng một hồ sơ ở các hệ độc lập.

Giảm số bản sao thường giúp giảm nguy cơ một trường đã được cập nhật ở kho chính nhưng bản chiếu trong kho graph còn cũ. Tuy nhiên, nếu ứng dụng tự tạo tài liệu trùng trong nhiều collection hoặc nhiều vùng dữ liệu, vấn đề đồng bộ vẫn tồn tại.

### 6.2. Truy vấn phối hợp dễ diễn đạt hơn

Ví dụ “tìm bài về NoSQL do bạn của bạn viết, lọc theo kỹ năng của tác giả” cần cả lọc thuộc tính và duyệt quan hệ. Một ngôn ngữ truy vấn hỗ trợ cả document và graph có thể giúp diễn đạt thao tác trong một câu truy vấn, thay vì thực hiện nhiều vòng trao đổi từ ứng dụng tới các hệ riêng.

Điều này **không bảo đảm một truy vấn luôn nhanh hơn**. Độ trễ vẫn phụ thuộc phân vùng, chỉ mục, số cạnh được duyệt, độ chọn lọc của bộ lọc và khả năng tối ưu của động cơ.

### 6.3. Đơn giản hóa một phần vận hành

Khi nhiều mô hình dùng chung một cơ sở dữ liệu hoặc một cụm, đội ngũ có thể giảm số công nghệ phải cài đặt, giám sát, cập nhật, sao lưu, bảo mật và tích hợp. Một chính sách quản lý định danh hoặc một quy trình sao lưu có thể bao phủ nhiều loại dữ liệu nếu sản phẩm thực sự hỗ trợ.

Nhưng **một hệ quản trị không có nghĩa là không còn công việc vận hành**. Cụm đa mô hình có thể cần phân mảnh riêng cho từng collection, theo dõi tải graph, tinh chỉnh cache và chỉ mục, cũng như quản lý sự cố ảnh hưởng đến nhiều loại chức năng cùng lúc.

### 6.4. Phát triển tính năng mới linh hoạt hơn

Nếu sản phẩm bắt đầu bằng document nhưng về sau cần “người dùng tương tự” hoặc “đường liên hệ”, việc bổ sung một số edge collection có thể thuận tiện hơn việc dựng thêm toàn bộ nền tảng graph, xây pipeline đồng bộ và thay đổi các đường truy cập.

Lợi ích cao nhất xuất hiện khi **các mô hình thường xuyên tham chiếu chung các thực thể** và cần kết hợp trong truy vấn.

## 7. Các giới hạn và đánh đổi cần đánh giá

### 7.1. “Một DBMS” không bảo đảm mọi thao tác có cùng transaction

Hãy xét yêu cầu “tạo bài viết và tạo cạnh tác giả viết bài”. Có hai thao tác ghi:

~~~text
1. Tạo posts/p201
2. Tạo writes: users/u102 -> posts/p201
~~~

Nếu thao tác 1 thành công nhưng thao tác 2 thất bại, ứng dụng có thể thấy bài chưa có tác giả. Để tránh trạng thái trung gian, cần xem DBMS có hỗ trợ **transaction nguyên tử qua các collection liên quan** hay không, bao gồm giới hạn khi dữ liệu trải trên nhiều shard hoặc nhiều vùng.

Cần xác định rõ:

- **Atomicity:** tất cả thao tác cùng thành công hay cùng được hoàn tác?
- **Isolation:** truy vấn đồng thời có nhìn thấy dữ liệu trung gian không?
- **Durability:** khi đã xác nhận ghi, điều gì xảy ra nếu nút gặp sự cố?
- **Consistency model:** đọc sau ghi hoặc đọc từ replica được bảo đảm thế nào?

Không thể suy ra các bảo đảm này chỉ từ nhãn multi-model. Nếu dùng nhiều hệ quản trị độc lập, ứng dụng thường cần cơ chế đồng bộ sự kiện, outbox, xử lý lặp, retry hoặc quy trình bù trừ thay cho một transaction toàn cục.

### 7.2. Tối ưu một mô hình có thể làm mô hình khác bị chậm

Một số mẫu truy cập đối lập nhau:

| Tác vụ | Tối ưu thường cần | Nguy cơ |
|---|---|---|
| Đọc document bằng ID | Chỉ mục khóa chính, dữ liệu cục bộ | Tập document quá lớn hoặc nút nóng |
| Tìm document theo thuộc tính | Chỉ mục phù hợp bộ lọc và sắp xếp | Chi phí lưu trữ chỉ mục và cập nhật ghi |
| Duyệt graph nhiều cấp | Chỉ mục cạnh, giới hạn số bước, lọc sớm | Số đường đi tăng đột biến khi có đỉnh bậc cao |
| Phân tích lịch sử dài | Bố cục tối ưu quét và tổng hợp | Gây tranh tài nguyên với truy vấn giao dịch |
| Tìm kiếm toàn văn | Chỉ mục tìm kiếm chuyên biệt, ranking | Độ trễ cập nhật chỉ mục hoặc chi phí lưu trữ |

Một hệ đa mô hình tốt cần cho phép quan sát kế hoạch thực thi và tài nguyên theo loại truy vấn. Hệ thống phải có giới hạn độ sâu graph, kích thước kết quả, timeout và cơ chế phân trang để tránh truy vấn gây cạn tài nguyên.

### 7.3. Phân mảnh và quan hệ xuyên nút

Mở rộng ngang bằng sharding có thể phù hợp với document được truy cập theo `userId`. Nhưng graph traversal từ người dùng A có thể phải đi qua hàng nghìn cạnh nối sang nhiều shard.

Khi thiết kế cần xem:

- Khóa phân vùng có giúp các dữ liệu thường được truy cập cùng nhau nằm gần nhau không?
- Các cạnh có thường nối giữa các partition hoặc shard không?
- Có nút đặc biệt với hàng triệu cạnh (*supernode*) tạo tải tập trung không?
- Hệ thống có cách tối ưu hoặc giới hạn truy vấn xuyên shard không?
- Mức nhất quán khi truy vấn qua nhiều replica/shard là gì?

Một sản phẩm hỗ trợ cả document và graph vẫn có thể không thích hợp cho workload graph cực lớn hoặc traversals sâu trên hệ thống phân tán.

### 7.4. Một cụm tập trung cũng là một miền lỗi chung

Đặt hồ sơ, phiên truy cập và quan hệ trong cùng một hệ thống có thể giảm số dịch vụ phụ thuộc, nhưng sự cố cụm có thể đồng thời ảnh hưởng nhiều tính năng. Phải thiết kế replica, vùng lỗi độc lập, backup, khôi phục và cơ chế failover tương ứng với mục tiêu sẵn sàng.

### 7.5. Phụ thuộc vào tính năng riêng của nhà cung cấp

Ngôn ngữ truy vấn, cách tạo cạnh, ngữ nghĩa giao dịch và mô hình chỉ mục có thể rất khác nhau. Nếu ứng dụng dùng sâu một ngôn ngữ graph độc quyền, việc di chuyển sang DBMS khác có thể khó hơn so với mô hình tài liệu đơn giản.

Đó là đánh đổi giữa **tận dụng tính năng tích hợp** và **tính di động**. Không nên né mọi tính năng đặc thù bằng mọi giá, nhưng cần biết tính năng nào tạo ràng buộc dài hạn.

## 8. Khi nào nên dùng một DBMS đa mô hình?

Multi-model thường đáng cân nhắc khi:

- Cùng một tập thực thể được dùng trong nhiều dạng truy vấn: đọc document, lọc thuộc tính và duyệt quan hệ.
- Nghiệp vụ thay đổi, có khả năng bổ sung loại quan hệ hoặc cấu trúc document mới.
- Đội ngũ muốn giảm số hệ lưu trữ cần vận hành và có thể chấp nhận giới hạn của sản phẩm.
- Workload của các mô hình nằm trong mức hiệu năng, chi phí và transaction mà sản phẩm chứng minh được.
- Việc giảm sao chép dữ liệu có giá trị thực tế vì các bản sao giữa những hệ độc lập thường dễ bị lệch.

Nên cân nhắc một hệ chuyên dụng hoặc polyglot persistence nếu:

- Mỗi workload có yêu cầu rất khác nhau, chẳng hạn cache siêu thấp độ trễ, tìm kiếm toàn văn quy mô lớn và đồ thị cực sâu.
- Cần các tính năng đặc thù mà engine đa mô hình không cung cấp hoặc cung cấp chưa đủ.
- Dữ liệu cần các chính sách lưu giữ, phân quyền, môi trường và tần suất mở rộng hoàn toàn riêng biệt.
- Năng lực đội ngũ, hệ sinh thái và giới hạn chi phí ủng hộ việc sử dụng cơ sở dữ liệu quan hệ hoặc document hiện có.

Không có quy tắc “hơn hai mô hình thì phải dùng multi-model”. **Chọn theo truy vấn, tính đúng đắn, tải, vận hành và khả năng kiểm chứng**, không theo số lượng nhãn mô hình trên danh sách tính năng.

## 9. So sánh một phương án đa mô hình với nhiều DBMS

Ví dụ một nền tảng thương mại có sản phẩm dạng document, quan hệ mua kèm dạng graph và giỏ hàng dạng key–value.

| Tiêu chí | Một DBMS đa mô hình | Nhiều DBMS chuyên biệt |
|---|---|---|
| Số công nghệ cần vận hành | Có thể ít hơn | Thường nhiều hơn |
| Liên kết dữ liệu giữa các mô hình | Có thể trực tiếp nếu các mô hình dùng chung định danh/kho dữ liệu | Thường cần đồng bộ hoặc truy vấn qua nhiều dịch vụ |
| Transaction nhiều loại dữ liệu | Phụ thuộc transaction của chính DBMS, phạm vi collection/shard | Thường phức tạp hơn khi qua nhiều DBMS |
| Tối ưu từng workload | Có thể chấp nhận đánh đổi để tích hợp | Có nhiều lựa chọn engine chuyên dụng |
| Khả năng mở rộng độc lập | Có thể bị ràng buộc bởi cụm chung; tùy sản phẩm | Có thể mở rộng từng DBMS theo nhu cầu |
| Chi phí hệ thống | Ít thành phần nhưng chưa chắc rẻ hơn | Tốn thêm vận hành/tích hợp, có thể tối ưu tài nguyên từng workload |
| Khả năng chịu lỗi | Cần bảo vệ miền lỗi chung | Các hệ có thể độc lập hơn nhưng tăng điểm tích hợp dễ lỗi |
| Độ linh hoạt công nghệ | Tận dụng một stack, có nguy cơ phụ thuộc nhà cung cấp | Tự do chọn engine nhưng tăng phức tạp và hợp đồng dữ liệu |

**Không nên đánh giá chỉ theo số máy chủ hoặc số dịch vụ.** Chi phí thực bao gồm kỹ thuật triển khai, khả năng khôi phục, kỹ năng nhân sự, bản quyền/cloud, độ phức tạp ứng dụng và hậu quả khi dữ liệu sai lệch.

## 10. Cách đánh giá một sản phẩm có thực sự phù hợp

### Bước 1: Liệt kê truy vấn quan trọng nhất

Ví dụ:

~~~text
Q1. Lấy hồ sơ học viên theo ID                     -> key lookup
Q2. Lọc học viên theo kỹ năng và trạng thái         -> document query
Q3. Tìm người được theo dõi trong hai cấp          -> graph traversal
Q4. Lấy bài học của người được theo dõi             -> document + graph
Q5. Tìm bài học có nội dung gần với từ khóa         -> search (nếu cần)
~~~

Với từng truy vấn, ghi rõ số yêu cầu/giây, p95/p99 mong muốn, tập dữ liệu, số cạnh điển hình và độ tươi dữ liệu cần thiết.

### Bước 2: Xác minh khả năng đa mô hình ở mức kỹ thuật

Đừng dừng ở câu “hỗ trợ document và graph”. Cần xác minh:

1. Document và graph có tham chiếu **cùng một thực thể** hay phải nhân bản?
2. Có thể viết **một truy vấn** lọc document và duyệt cạnh không?
3. Phạm vi giao dịch qua nhiều collection, shard hoặc mô hình đến đâu?
4. Chỉ mục khóa, thuộc tính và cạnh được quản lý như thế nào?
5. Backup/restore, phân quyền và replication có đồng nhất giữa các mô hình không?
6. Có driver, công cụ migration, monitoring và giải thích kế hoạch truy vấn không?
7. Dữ liệu có thể xuất/nhập ở định dạng nào, chi phí di chuyển sang sản phẩm khác ra sao?

### Bước 3: Thiết kế khóa, cạnh và vòng đời dữ liệu

Với graph, cần quyết định **chiều cạnh**, ngữ nghĩa và tính duy nhất của quan hệ. Ví dụ cạnh “theo dõi” có hướng; cạnh “cùng học một lớp” có thể được mô hình hóa khác.

Với document, cần quyết định **nhúng hay tham chiếu**, trường bắt buộc, phiên bản schema và chỉ mục. Với dữ liệu tạm, xác định thời hạn lưu, cơ chế xóa và hậu quả nếu mất.

### Bước 4: Chạy thử workload kết hợp

Tạo dữ liệu giống phân bố thực tế: số học viên, số bài học, số cạnh bình quân và số cạnh cực đại. Đo:

- Thời gian đọc document theo khóa và bộ lọc.
- Độ trễ graph traversal một bước, hai bước và các nút có bậc lớn.
- Tác động của thao tác ghi nhiều cạnh lên truy vấn đọc.
- Thời gian khi mất một nút và khả năng phục hồi sau lỗi.
- Dung lượng chỉ mục và chi phí theo quy mô.
- Hành vi khi cần cập nhật document và cạnh trong cùng nghiệp vụ.

Không cần xây thử toàn bộ ứng dụng mới có số liệu; một tập truy vấn đại diện và dữ liệu có phân bố thực là nền tảng để so sánh công bằng.

### Bước 5: Chọn kiến trúc theo rủi ro thực tế

Nếu phần lớn tính năng chỉ cần document và key lookup, một DBMS document hoặc quan hệ có hỗ trợ JSON đã đủ có thể là lựa chọn đơn giản. Nếu nhiều truy vấn graph phức tạp và thường kết hợp trực tiếp với thuộc tính document, ưu điểm của hệ multi-model native trở nên rõ hơn. Nếu mỗi workload đòi hỏi engine chuyên biệt, có thể cần nhiều DBMS cùng cơ chế đồng bộ rõ ràng.

## 11. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Cùng sản phẩm nghĩa là một kho dữ liệu chung.” | Có sản phẩm đa mô hình thống nhất, cũng có nền tảng chỉ cung cấp nhiều API hoặc dịch vụ độc lập. |
| “Có JSON và khóa chính thì đã là hệ document, key–value và graph đầy đủ.” | Biểu diễn dữ liệu khác với khả năng truy vấn, chỉ mục và thao tác nguyên tử của từng mô hình. |
| “Đã dùng một DBMS thì không còn vấn đề đồng bộ.” | Vẫn có transaction nhiều collection, replica, cache, chỉ mục tìm kiếm hoặc bản chiếu dữ liệu cần xem xét. |
| “Graph truy vấn được nhiều cấp thì lúc nào cũng nhanh.” | Chi phí phụ thuộc số cạnh, số bước, shard, bộ lọc và phân bố đỉnh; traversals có thể bùng nổ. |
| “Multi-model làm mất hoàn toàn nhu cầu SQL.” | Hệ quan hệ vẫn phù hợp nhiều nghiệp vụ; không ít hệ quan hệ đã hỗ trợ JSON và truy vấn phức tạp. |
| “Một DBMS luôn dễ mở rộng hơn ba DBMS.” | Có thể giảm thành phần vận hành nhưng gặp giới hạn tăng tải độc lập và miền lỗi chung. |
| “Schema linh hoạt nên không cần xác thực dữ liệu.” | Mỗi mô hình vẫn cần validation, ràng buộc và quản trị phiên bản. |
| “Multi-model đồng nghĩa transaction ACID cho mọi thao tác.” | Mỗi sản phẩm có giới hạn transaction và consistency riêng, nhất là khi dữ liệu phân tán. |

## 12. Tình huống thực hành

Một ứng dụng quản lý sự kiện có:

- Thông tin sự kiện: thời gian, địa điểm, nội dung và thông số tùy loại sự kiện.
- Quan hệ: người tham gia theo dõi người tổ chức; sự kiện liên quan đến các nhóm sở thích.
- Vé đã bán: không được bán vượt quá sức chứa.
- Màn hình gợi ý: ưu tiên sự kiện của các tổ chức mà người dùng đang theo dõi.
- Bộ lọc: tìm sự kiện theo vị trí, ngày, danh mục và giá.

Hãy thử lập một phương án thiết kế:

1. Mô hình nào thích hợp để biểu diễn **thông tin sự kiện**?
2. Có nên tạo **cạnh graph** cho quan hệ theo dõi và tham dự? Nếu có, chiều cạnh và khóa là gì?
3. Truy vấn **gợi ý sự kiện của người tổ chức đã theo dõi** cần phối hợp những mô hình nào?
4. Việc **bán vé không vượt sức chứa** có ràng buộc transaction nào phải bảo đảm?
5. Cần đo những chỉ số nào để quyết định dùng một DBMS đa mô hình hay chia thành nhiều kho?

**Hướng tiếp cận:** Có thể dùng document cho sự kiện, graph cho quan hệ theo dõi, truy vấn kết hợp hai loại để gợi ý. Nhưng số vé còn lại cần một cơ chế kiểm soát đồng thời hoặc transaction được xác minh ở mức lưu trữ; riêng khả năng duyệt graph không giải quyết được bất biến này. Bộ lọc địa lý và ngày tháng còn đòi hỏi khả năng đánh chỉ mục thích hợp.

## 13. Tổng kết

Hệ quản trị đa mô hình cho phép nhiều cách biểu diễn và truy vấn dữ liệu cùng tồn tại trong một sản phẩm hoặc một động cơ, thường để giảm chi phí phối hợp các hệ lưu trữ riêng và giúp các thực thể được sử dụng qua nhiều kiểu truy cập.

Điều cần hiểu là **khả năng hỗ trợ nhiều mô hình có nhiều mức độ**. Một hệ có thể cung cấp document và key lookup, một hệ khác cho phép document tham gia trực tiếp vào graph traversal, còn một nền tảng có thể chỉ cung cấp nhiều API được triển khai tách biệt. Vì vậy, khi lựa chọn phải kiểm chứng **chia sẻ dữ liệu, cú pháp truy vấn, phạm vi transaction, chỉ mục, consistency, mở rộng và vận hành**.

Mô hình phù hợp xuất phát từ truy vấn và ràng buộc nghiệp vụ. Multi-model là một công cụ thiết kế hữu ích khi nhiều cách truy cập cần phối hợp trên cùng dữ liệu; nó không thay thế việc mô hình hóa chính xác, đo hiệu năng và kiểm tra khả năng phục hồi.

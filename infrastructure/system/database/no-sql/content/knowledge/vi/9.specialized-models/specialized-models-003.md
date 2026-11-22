# Tìm kiếm văn bản: tài liệu, token, chỉ mục đảo và độ liên quan

## 1. Từ tìm chuỗi ký tự đến tìm kiếm theo ý nghĩa

Giả sử một nền tảng học tập có hàng chục nghìn bài viết. Người học gõ:

> cách đánh chỉ mục để tìm văn bản nhanh

Hệ thống cần tìm bài **“Chỉ mục đảo trong công cụ tìm kiếm”**, ngay cả khi tiêu đề không chứa nguyên văn câu người dùng nhập. Nó cũng nên đưa bài chuyên sâu về chỉ mục đảo lên trước một trang chỉ tình cờ nhắc cụm “tìm văn bản” ở cuối.

Đây là bài toán **tìm kiếm toàn văn (full-text search)**: biến văn bản thành những đơn vị có thể tra cứu, tạo cấu trúc chỉ mục cho các đơn vị ấy, truy xuất tập tài liệu phù hợp và **xếp hạng mức độ liên quan (relevance)**.

Khác với tra cứu một bản ghi bằng khóa chính, tìm kiếm văn bản phải đối mặt với các đặc điểm:

- Một khái niệm có nhiều cách viết: “cơ sở dữ liệu”, “CSDL”, “database”.
- Người dùng có thể viết không dấu, gõ sai một ký tự hoặc đảo thứ tự từ.
- Một từ xuất hiện trong nhiều tài liệu nhưng có giá trị phân biệt rất khác nhau.
- Các trường **tiêu đề**, **mô tả**, **nội dung** và **thẻ** có mức quan trọng khác nhau.
- Người dùng muốn kết quả tốt nhất ở đầu danh sách, thường chỉ xem 10–20 kết quả.
- Tài liệu có thể bị cập nhật, xóa, chuyển quyền xem hoặc thay đổi trạng thái xuất bản.

Trong họ NoSQL, **search engine/search database** là một dạng hệ lưu trữ và truy vấn chuyên biệt. Elasticsearch, OpenSearch, Solr và Lucene (thư viện tìm kiếm được nhiều hệ thống dùng bên trong) thường được nhắc tới khi giải quyết nhu cầu này. Tuy nhiên, tìm kiếm toàn văn cũng có thể được cung cấp bởi RDBMS hoặc dịch vụ quản lý khác; không bắt buộc xây một hệ NoSQL riêng nếu công cụ hiện tại đã đáp ứng yêu cầu.

Trọng tâm của bài là chuỗi khái niệm:

~~~text
Tài liệu gốc
    ↓
Phân tích văn bản thành token
    ↓
Chỉ mục đảo (token → các tài liệu chứa token)
    ↓
Truy xuất tập ứng viên
    ↓
Tính điểm độ liên quan và áp dụng điều kiện lọc
    ↓
Sắp xếp, phân trang, hiển thị kết quả
~~~

## 2. Tài liệu (document): đơn vị tìm kiếm cơ bản

### 2.1. Document không nhất thiết là file

Trong search engine, **document** là đơn vị dữ liệu được đưa vào chỉ mục và có thể xuất hiện như một kết quả tìm kiếm. Nó có thể đại diện:

- Một bài học hoặc bài báo.
- Một sản phẩm trong danh mục.
- Một tin tuyển dụng hoặc hồ sơ.
- Một ticket hỗ trợ khách hàng.
- Một trang tài liệu kỹ thuật.
- Một bản ghi sự kiện cần tìm trong log.

Ví dụ document được lập chỉ mục cho nền tảng bài học:

~~~json
{
  "id": "lesson-104",
  "tenantId": "academy-a",
  "title": "Chỉ mục đảo trong tìm kiếm toàn văn",
  "description": "Giải thích token, posting list và cách xếp hạng kết quả.",
  "content": "Công cụ tìm kiếm thường phân tích văn bản...",
  "tags": ["nosql", "search", "indexing"],
  "language": "vi",
  "status": "PUBLISHED",
  "publishedAt": "2026-10-01T08:00:00Z",
  "popularity": 128
}
~~~

Một document chứa nhiều **field**, mỗi field có thể được xử lý khác nhau:

| Field | Kiểu xử lý phù hợp | Lý do |
| --- | --- | --- |
| id | Giá trị chính xác (keyword/ID) | Tìm, cập nhật và xóa đúng tài liệu |
| tenantId | Giá trị chính xác | Giới hạn dữ liệu theo đơn vị sở hữu |
| title | Văn bản được phân tích (text) | Tìm theo từ, cụm từ và tính điểm |
| description | Văn bản được phân tích | Bổ sung ngữ cảnh liên quan |
| content | Văn bản được phân tích | Tìm trong thân bài |
| tags | Thường tìm/chọn chính xác | Lọc theo thẻ đã chuẩn hóa |
| status | Giá trị chính xác | Chỉ hiển thị bài đã xuất bản |
| publishedAt | Ngày/giờ | Lọc khoảng thời gian, sắp theo độ mới |
| popularity | Số | Là tín hiệu xếp hạng nghiệp vụ nếu cần |

**Document là đơn vị tìm kiếm, không nhất thiết là nguồn dữ liệu gốc.** Một cơ sở dữ liệu giao dịch có thể lưu bài viết chính thức; hệ tìm kiếm giữ bản chiếu tối ưu để đọc. Khi đó cần quy tắc đồng bộ giữa hai nơi.

### 2.2. Phân biệt dữ liệu nguồn, dữ liệu chỉ mục và dữ liệu trả về

Ba biểu diễn có thể khác nhau:

1. **Source document:** Nội dung và metadata mà hệ thống quản lý.
2. **Indexed representation:** Token, vị trí, thống kê và cấu trúc để tìm nhanh.
3. **Stored/projected fields:** Các trường cần trả về hoặc làm highlight trong kết quả.

Không phải search engine nào cũng lưu nguyên toàn bộ document theo cùng cách, và không phải mọi field đều cần đưa vào inverted index. Một thiết kế tốt chỉ lập chỉ mục những trường phục vụ truy vấn; giữ các trường dùng để lọc, sắp xếp hoặc hiển thị theo cơ chế phù hợp.

### 2.3. Chọn ranh giới document

Nếu bài học có nhiều chương, có thể lập chỉ mục:

- **Một document cho cả bài học:** Trả một kết quả cho mỗi bài, nhưng tài liệu dài khiến kết quả khó chỉ rõ đoạn phù hợp.
- **Một document cho mỗi đoạn/chương:** Tìm chính xác vùng nội dung hơn, nhưng có thể trả nhiều kết quả trùng bài và cần gộp ở tầng ứng dụng.
- **Một document cho từng thực thể liên quan:** Ví dụ sản phẩm, danh mục và đánh giá, khi chúng có vòng đời và cách tìm riêng.

Ranh giới document ảnh hưởng độ dài, điểm relevance, highlight, cập nhật và phân trang. Không nên tách/ghép chỉ vì cấu trúc JSON thuận tiện; cần dựa vào **đơn vị mà người dùng muốn nhận như một kết quả**.

## 3. Token: từ chuỗi văn bản đến các đơn vị có thể tìm

Máy tìm kiếm không nhất thiết so sánh toàn bộ đoạn chữ như một chuỗi duy nhất. Nó dùng một **analyzer** để biến văn bản đầu vào thành một dòng token.

Ví dụ đơn giản:

~~~text
Văn bản:  "Tìm kiếm văn bản với chỉ mục đảo!"

Chuẩn hóa chữ thường và dấu câu:
          "tìm kiếm văn bản với chỉ mục đảo"

Token minh họa:
          [tìm, kiếm, văn, bản, với, chỉ, mục, đảo]
~~~

Ví dụ này cố tình tách theo các tiếng để dễ nhìn quá trình. **Tiếng Việt không thể luôn phân tách từ đúng chỉ bằng dấu cách**: “cơ sở dữ liệu” hoặc “học máy” gồm nhiều tiếng tạo thành cụm từ có ý nghĩa. Analyzer thực tế có thể cần công cụ tách từ/segmenter phù hợp và xử lý Unicode, dấu tiếng Việt.

### 3.1. Các bước thường gặp trong analyzer

~~~mermaid
flowchart LR
    A["Văn bản gốc"] --> B["Char filters<br/>Chuẩn hóa ký tự"]
    B --> C["Tokenizer<br/>Tách đơn vị"]
    C --> D["Token filters<br/>Biến đổi hoặc loại token"]
    D --> E["Token stream<br/>term + vị trí"]
~~~

**Character filters** có thể sửa dạng ký tự trước khi tách, ví dụ chuẩn hóa khoảng trắng hoặc xử lý các dạng ký tự tương đương. Cần cẩn thận với thay đổi làm mất dấu hoặc làm biến đổi ý nghĩa.

**Tokenizer** quyết định ranh giới token. Có tokenizer phân tách theo từ, theo ký tự hoặc n-gram. Lựa chọn này quyết định loại truy vấn nào sẽ phù hợp.

**Token filters** có thể:

- Chuyển về chữ thường.
- Loại stop words nếu có lý do rõ ràng.
- Chuẩn hóa dấu hoặc chính tả theo quy tắc.
- Biến đổi từ về gốc/stem đối với ngôn ngữ được hỗ trợ.
- Thêm từ đồng nghĩa vào dòng token.
- Tạo các biến thể cho autocomplete nếu thiết kế yêu cầu.

Một analyzer không nhất thiết chứa tất cả những bước trên. Mỗi bước có lợi ích và khả năng làm mất phân biệt giữa các từ.

### 3.2. Một token có thông tin gì?

Token thường không chỉ gồm nội dung chữ. Các thông tin có thể bao gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| term | Giá trị token đã phân tích, ví dụ “search” |
| position | Vị trí tương đối trong dòng token, phục vụ phrase query |
| startOffset/endOffset | Vị trí ký tự trong văn bản gốc, phục vụ highlight |
| positionIncrement | Khoảng cách vị trí giữa các token |
| token type/payload | Thông tin bổ sung tùy tokenizer và engine |

Không phải mọi hệ thống đều giữ mọi trường này trong inverted index; cấu hình **positions, offsets, term vectors** quyết định các kiểu truy vấn/highlight có thể thực hiện và chi phí lưu trữ.

### 3.3. Ví dụ token position

Văn bản:

~~~text
"chỉ mục đảo giúp tìm kiếm nhanh"
~~~

Một analyzer minh họa có thể sinh:

| Token | Position |
| --- | ---: |
| chỉ | 0 |
| mục | 1 |
| đảo | 2 |
| giúp | 3 |
| tìm | 4 |
| kiếm | 5 |
| nhanh | 6 |

Để kiểm tra cụm từ **“chỉ mục đảo”**, engine không chỉ cần biết tài liệu có ba token **chỉ**, **mục**, **đảo**; nó còn cần biết chúng xuất hiện liên tiếp, theo đúng thứ tự. Thông tin vị trí giúp phân biệt:

~~~text
"chỉ mục đảo"           -> khớp cụm từ
"đảo thứ tự chỉ mục"    -> có các tiếng nhưng không khớp cụm từ đó
~~~

### 3.4. Analyzer lúc lập chỉ mục và lúc truy vấn

Cùng một cụm người dùng nhập phải được biến đổi thành token tương thích với những token đã lập chỉ mục:

~~~text
Index time:
    "Tìm Kiếm" -> [tìm, kiếm]

Search time:
    "tìm kiếm" -> [tìm, kiếm]
~~~

Nếu index chuẩn hóa bỏ dấu còn query vẫn giữ dấu (hoặc ngược lại), kết quả có thể bị thiếu. Ngược lại, nếu xóa mọi dấu ở cả hai phía thì **“ma”**, **“má”**, **“mã”** có thể bị xem là giống nhau, gây false positive.

Với tiếng Việt, một thiết kế có thể duy trì **trường tìm kiếm có dấu** và **trường hỗ trợ không dấu**, rồi ưu tiên điểm cao hơn cho kết quả khớp có dấu. Cách làm cụ thể phụ thuộc analyzer và hành vi người dùng. Không nên mặc định rằng analyzer tên “standard” có khả năng tách từ tiếng Việt đúng cho mọi loại nội dung.

## 4. Chỉ mục đảo (inverted index): cấu trúc cốt lõi

### 4.1. Chỉ mục thuận và chỉ mục đảo

Nếu lưu dữ liệu theo document thông thường:

~~~text
Doc 1 -> [tìm, kiếm, văn, bản, chỉ, mục, đảo]
Doc 2 -> [chỉ, mục, đảo, tìm, kiếm]
Doc 3 -> [cơ, sở, dữ, liệu, truy, vấn]
~~~

Muốn tìm từ **“đảo”**, phương án đơn giản nhất là đọc mọi document và tìm bên trong từng văn bản. Khi số document tăng, cách quét toàn bộ trở nên tốn kém.

**Chỉ mục đảo** đảo chiều tra cứu:

~~~text
term -> danh sách document có chứa term
~~~

Ví dụ:

| Term | Posting list (doc IDs) |
| --- | --- |
| tìm | [1, 2] |
| kiếm | [1, 2] |
| chỉ | [1, 2] |
| mục | [1, 2] |
| đảo | [1, 2] |
| văn | [1] |
| bản | [1] |
| cơ | [3] |
| sở | [3] |
| dữ | [3] |
| liệu | [3] |

Khi người dùng hỏi **“chỉ mục đảo”**, engine tra các posting list của ba term và kết hợp chúng theo quy tắc truy vấn, thay vì duyệt từng văn bản đầy đủ.

### 4.2. Một posting chứa những gì?

Trong chỉ mục đảo thực tế, một posting có thể giữ:

~~~text
term = "đảo"
    docId=1, frequency=1, positions=[7]
    docId=2, frequency=1, positions=[2]
~~~

Các trường quan trọng:

- **document ID:** tài liệu có chứa token.
- **term frequency (tf):** số lần token xuất hiện trong tài liệu hoặc field.
- **positions:** vị trí các lần xuất hiện, để hỗ trợ phrase/proximity.
- **offsets:** tùy cơ chế lưu trữ, giúp liên kết token về đoạn ký tự gốc.
- **field context/norms:** thống kê chiều dài hoặc thông tin riêng theo trường, phục vụ chấm điểm.

Posting list thường được lưu theo thứ tự thích hợp để giao/cộng/duyệt hiệu quả và được nén để giảm dung lượng. Tên và cấu trúc file vật lý phụ thuộc engine; đây là cách hình dung **logic**, không phải định dạng file chung.

### 4.3. Truy vấn AND, OR trên posting list

Giả sử:

~~~text
chỉ    -> [D1, D2, D7, D9]
mục    -> [D1, D2, D8, D9]
đảo    -> [D1, D2, D9]
~~~

Truy vấn yêu cầu có đủ cả ba term dùng **giao (intersection)**:

~~~text
[D1, D2, D7, D9]
∩ [D1, D2, D8, D9]
∩ [D1, D2, D9]
= [D1, D2, D9]
~~~

Truy vấn chấp nhận chứa ít nhất một term dùng **hợp (union)**:

~~~text
[D1, D2, D7, D8, D9]
~~~

Kết quả AND thường hẹp hơn OR nhưng có thể bỏ qua bài liên quan dùng từ đồng nghĩa. Kết quả OR thường bao phủ hơn nhưng cần **xếp hạng** để đẩy tài liệu khớp nhiều từ, nhiều trường quan trọng lên trước.

**Lưu ý:** AND của token chỉ chứng minh chúng cùng có mặt, không chứng minh chúng đứng sát nhau. Phrase query phải kiểm tra positions.

### 4.4. Vì sao chỉ mục đảo nhanh?

Tra cứu từ khóa diễn ra trên cấu trúc dữ liệu đã được chuẩn bị:

1. Xác định term ID hoặc đường dẫn tới posting list.
2. Đọc danh sách tài liệu ứng viên tương ứng.
3. Kết hợp posting lists theo Boolean query hoặc thuật toán tối ưu.
4. Chấm điểm những tài liệu ứng viên phù hợp.
5. Trả top-K và metadata cần hiển thị.

Engine có thể dùng dictionary cấu trúc trie/FST hoặc cấu trúc khác, nén posting, skipping và các thuật toán top-K để tránh xử lý toàn bộ ứng viên khi không cần. Vì vậy, công cụ tìm kiếm có thể trả ít kết quả liên quan từ một tập văn bản rất lớn.

Tuy nhiên, tìm một term quá phổ biến, truy vấn không đủ chọn lọc hoặc phép wildcard rộng vẫn có thể tốn CPU, bộ nhớ và I/O. **Có inverted index không có nghĩa mọi truy vấn văn bản đều rẻ.**

## 5. Xây chỉ mục từ một tập văn bản nhỏ

Cho ba bài:

~~~text
D1: "Tìm kiếm văn bản với chỉ mục đảo"
D2: "Chỉ mục đảo tăng tốc tìm kiếm"
D3: "Cơ sở dữ liệu hỗ trợ truy vấn"
~~~

Để minh họa dễ tính, ta chuyển chữ thường và tách các tiếng bằng khoảng trắng; chưa áp dụng tách từ tiếng Việt chuyên dụng, stop words hoặc từ đồng nghĩa.

### 5.1. Gắn vị trí token

~~~text
D1:
  tìm(0), kiếm(1), văn(2), bản(3),
  với(4), chỉ(5), mục(6), đảo(7)

D2:
  chỉ(0), mục(1), đảo(2), tăng(3),
  tốc(4), tìm(5), kiếm(6)

D3:
  cơ(0), sở(1), dữ(2), liệu(3),
  hỗ(4), trợ(5), truy(6), vấn(7)
~~~

### 5.2. Tạo posting lists

~~~text
"tìm"  -> (D1, tf=1, pos=[0]), (D2, tf=1, pos=[5])
"kiếm" -> (D1, tf=1, pos=[1]), (D2, tf=1, pos=[6])
"chỉ"  -> (D1, tf=1, pos=[5]), (D2, tf=1, pos=[0])
"mục"  -> (D1, tf=1, pos=[6]), (D2, tf=1, pos=[1])
"đảo"  -> (D1, tf=1, pos=[7]), (D2, tf=1, pos=[2])
"cơ"   -> (D3, tf=1, pos=[0])
~~~

### 5.3. Xử lý một truy vấn

Truy vấn **“chỉ mục đảo”**:

1. Analyzer truy vấn sinh **[chỉ, mục, đảo]**.
2. Posting list của từng term đều có **D1** và **D2**.
3. Nếu là truy vấn AND, cả D1 và D2 đều là ứng viên.
4. Nếu là phrase query, positions cho thấy:
   - D1 chứa **chỉ(5) mục(6) đảo(7)**.
   - D2 chứa **chỉ(0) mục(1) đảo(2)**.
5. Cả hai khớp phrase; cần các tín hiệu khác để quyết định bài nào đứng đầu, ví dụ field match, độ dài field, độ phổ biến hoặc thời gian xuất bản.

Nếu truy vấn **“cơ sở dữ liệu”**, chỉ D3 có đủ những token tương ứng trong ví dụ. Hệ thống có thể trả D3 nhanh mà không cần dò chữ của D1 và D2.

### 5.4. Chỉ mục được cập nhật ra sao?

Khi thêm D4, các posting list của term mới hoặc term đã có cần được cập nhật. Các engine dựa trên Lucene thường tổ chức dữ liệu theo **segment**: document mới được thêm vào các segment, các segment nhỏ có thể được hợp nhất theo thời gian. Xóa và cập nhật có thể được xử lý bằng đánh dấu document cũ và thêm document mới, sau đó quá trình merge thu hồi dữ liệu không còn hiệu lực.

Điều này dẫn tới những đánh đổi vận hành:

- Nhiều cập nhật/xóa gây thêm công việc lập chỉ mục và merge.
- Refresh để tài liệu mới có thể tìm thấy không nhất thiết đồng nghĩa đã hoàn tất flush/sync và mọi bảo đảm durability.
- Tài liệu vừa ghi có thể chưa xuất hiện ngay trong kết quả tùy mô hình **near real-time** của hệ.
- Chỉ mục có thể lớn hơn văn bản nguồn vì giữ posting, positions, norms và metadata.

## 6. Query syntax: truy vấn chuỗi không chỉ là so sánh bằng

Một công cụ tìm kiếm thường có nhiều kiểu truy vấn:

| Loại | Ví dụ | Ý định |
| --- | --- | --- |
| Exact term | status = PUBLISHED | Lọc giá trị đã chuẩn hóa |
| Full-text match | “tìm kiếm văn bản” | Tìm token liên quan |
| AND | “chỉ” AND “mục” | Bắt buộc có đủ term |
| OR | “chỉ” OR “mục” | Có ít nhất một term |
| Phrase | “chỉ mục đảo” | Các token gần/đúng vị trí và thứ tự |
| Prefix | “tim*” | Mở rộng theo tiền tố token |
| Fuzzy | “databse” gần “database” | Cho phép sai khác ký tự có kiểm soát |
| Range/filter | publishedAt từ ngày A đến B | Thu hẹp theo metadata |
| Fielded search | title chứa “NoSQL” | Ưu tiên/tìm trong trường cụ thể |
| Boolean combination | status bắt buộc + text liên quan | Kết hợp điều kiện lọc và tìm văn bản |

Các kiểu truy vấn là **ý tưởng chung**; cú pháp, mức hỗ trợ và thuật toán cụ thể phụ thuộc search engine.

### 6.1. Match khác exact term như thế nào?

Giả sử field title được phân tích:

~~~text
title gốc: "Tìm kiếm văn bản"
tokens:   [tìm, kiếm, văn, bản]
~~~

Truy vấn **match “tìm kiếm”** cũng được analyzer xử lý thành token rồi tìm theo semantics phù hợp. Ngược lại, truy vấn **term** tìm đúng một giá trị trong cấu trúc chỉ mục. Nếu dùng term query trực tiếp trên field đã phân tích nhưng đưa nguyên chuỗi “Tìm kiếm”, có thể không có term nào đúng nguyên chuỗi đó.

Vì vậy, thường thiết kế:

~~~text
title          -> text, phục vụ full-text search
title.keyword  -> keyword, phục vụ exact match / sort / aggregation khi cần
~~~

Đây là mô hình kiểu **multi-field** của một số engine; không phải tên trường mặc định bắt buộc. Exact match với mã, trạng thái, tag và tenant nên dùng field không bị tokenization theo văn bản tự nhiên.

### 6.2. Phrase query và khoảng cách

Phrase query kiểm tra các token có nằm ở vị trí phù hợp hay không:

~~~text
Truy vấn: "tìm kiếm"

Tài liệu A: "công cụ tìm kiếm"          -> gần nhau, đúng thứ tự
Tài liệu B: "tìm cách tối ưu phép kiếm" -> không phải cụm liên tiếp
~~~

Một số hệ cho phép **slop**: khoảng cách hoặc mức dịch chuyển chấp nhận được giữa các token. Slop lớn làm tăng recall nhưng cũng có thể đưa vào kết quả kém chính xác.

Với tiếng Việt, nếu analyzer tách cụm từ thành token ghép, semantics của phrase sẽ phụ thuộc token stream và positions sinh ra. Vì vậy phải kiểm tra kết quả analyzer trước khi dựa vào phrase query cho tên tổ chức, sản phẩm hay thuật ngữ chuyên ngành.

### 6.3. Prefix, wildcard, fuzzy và autocomplete

Người dùng gõ “elas” và muốn gợi ý “Elasticsearch”, hoặc gõ “databse” và muốn kết quả “database”. Có thể dùng prefix query, fuzzy matching, n-gram/edge n-gram, completion suggester hoặc một chỉ mục gợi ý chuyên dụng.

Không nên coi chúng là một thao tác:

- **Prefix** tìm token bắt đầu bằng tiền tố đã cho.
- **Wildcard** khớp mẫu ký tự, đôi khi rất tốn kém nếu mẫu rộng hoặc bắt đầu bằng dấu bất kỳ.
- **Fuzzy** dùng khoảng cách chỉnh sửa hoặc thuật toán gần đúng để chịu lỗi gõ.
- **Edge n-gram** tạo các tiền tố tại index time cho search-as-you-type; tăng kích thước index.
- **Completion suggester** thường tối ưu cho trả gợi ý đầu vào ngắn, không phải thay toàn bộ truy vấn tìm kiếm.

Đối với autocomplete, thường nên có field/chỉ mục riêng và giới hạn độ dài đầu vào, số gợi ý, số lần gọi để bảo vệ tài nguyên.

## 7. Độ liên quan (relevance): vì sao cùng khớp token nhưng thứ hạng khác nhau?

Inverted index giúp biết **tài liệu nào có khả năng phù hợp**. Nhưng người dùng cần kết quả **liên quan nhất** ở phía trên. Search engine thường tính một **relevance score** cho từng document ứng viên.

Ví dụ:

~~~text
Query: "chỉ mục đảo"

Doc A:
  title = "Chỉ mục đảo"
  content = "Giải thích cách tạo inverted index..."

Doc B:
  title = "Tổng quan NoSQL"
  content = "... một số hệ có chỉ mục đảo ..."
~~~

Cả A và B đều chứa các term cần tìm. Nhưng nhiều ứng dụng muốn A ở trước B vì:

- Khớp trực tiếp trong **title**.
- Cụm từ xuất hiện chính xác và nổi bật.
- Nội dung của A tập trung hơn vào chủ đề.
- Các tín hiệu chất lượng khác có thể ủng hộ A.

Không có điểm relevance “đúng tuyệt đối” cho mọi sản phẩm. Nó là một **hàm đánh giá** được thiết kế để phù hợp với hành vi người dùng và mục tiêu tìm kiếm.

## 8. TF, DF, IDF: ba thống kê nền tảng

### 8.1. Term frequency (TF)

**TF(t, d)** là tần suất term **t** xuất hiện trong document **d** hoặc trong một field đang xét.

Ví dụ:

~~~text
Doc A: "NoSQL và tìm kiếm trong NoSQL"
TF("NoSQL", A) = 2
~~~

Một term xuất hiện nhiều lần có thể thể hiện mức tập trung vào chủ đề. Nhưng lặp từ 1.000 lần không nên tự động khiến tài liệu vượt trội; các hàm ranking thực tế thường dùng **saturation** để hạn chế lợi ích tăng thêm của TF.

### 8.2. Document frequency (DF)

**DF(t)** là số document có chứa term **t**. Nếu 9.900 trong 10.000 tài liệu đều chứa “bài”, từ này kém hữu ích trong việc phân biệt kết quả. Nếu chỉ 30 bài có “inverted”, đây có thể là term phân biệt mạnh hơn.

Ví dụ:

| Term | N = 10.000 tài liệu | DF | Khả năng phân biệt (trực giác) |
| --- | ---: | ---: | --- |
| bài | 10.000 | 9.900 | Thấp |
| dữ liệu | 10.000 | 6.500 | Vừa hoặc thấp |
| chỉ mục đảo | 10.000 | 120 | Cao hơn |
| Lucene | 10.000 | 80 | Cao hơn |

Các con số chỉ minh họa; DF của một phrase không nhất thiết được xử lý giống DF của một term.

### 8.3. Inverse document frequency (IDF)

**IDF** tăng trọng số cho term hiếm hơn trong tập tài liệu. Một dạng ý tưởng đơn giản:

\[
\operatorname{IDF}(t) \approx \log \frac{N}{DF(t)}
\]

Trong đó **N** là số document và **DF(t)** là số document chứa term. Các thuật toán thực tế dùng công thức làm mượt, điều chỉnh cho trường hợp DF nhỏ/lớn và đặc điểm triển khai.

Ý nghĩa cần nhớ:

- Term có mặt ở gần như mọi tài liệu thường đóng góp ít điểm phân biệt.
- Term hiếm nhưng phù hợp có thể giúp nhận diện tài liệu đúng chủ đề.
- TF và IDF không đủ để đánh giá toàn diện; độ dài trường, vị trí/phrase và tín hiệu nghiệp vụ cũng quan trọng.

**IDF không phải đánh giá ngữ nghĩa thực sự.** Một mã ngẫu nhiên cực hiếm có thể có IDF cao nhưng không phải nội dung có giá trị với người dùng.

## 9. BM25: mô hình xếp hạng văn bản phổ biến

Nhiều hệ tìm kiếm dựa trên Lucene sử dụng các biến thể của **BM25 (Best Matching 25)** để xếp hạng truy vấn văn bản. BM25 kết hợp độ hiếm của term, tần suất xuất hiện và độ dài tài liệu.

Một dạng công thức thường dùng:

\[
\operatorname{BM25}(q,d)=
\sum_{t\in q}
\operatorname{IDF}(t)
\cdot
\frac{TF(t,d)(k_1+1)}
{TF(t,d)+k_1\left(1-b+b\frac{|d|}{\mathrm{avgdl}}\right)}
\]

Với:

- **q:** truy vấn; **d:** document đang chấm điểm.
- **TF(t, d):** số lần token t xuất hiện trong d.
- **IDF(t):** mức hiếm của t trong tập document.
- **|d|:** độ dài của d theo cách engine định nghĩa.
- **avgdl:** độ dài trung bình của document/field trong tập được xét.
- **k₁:** tham số ảnh hưởng mức bão hòa của TF.
- **b:** tham số điều chỉnh mức chuẩn hóa theo độ dài, thường nằm trong khoảng 0–1.

Một dạng IDF làm mượt được dùng trong nhiều tài liệu BM25:

\[
\operatorname{IDF}(t)=
\ln\left(1+
\frac{N-DF(t)+0.5}{DF(t)+0.5}
\right)
\]

Các hệ quản trị hoặc phiên bản có thể khác nhau về công thức, tham số mặc định, field norms, thống kê trên shard/segment và cách kết hợp nhiều trường. Công thức trên nhằm giải thích cơ chế, **không nên dùng để khẳng định điểm số chính xác của một engine cụ thể**.

### 9.1. TF tăng nhưng lợi ích giảm dần

Một bài nhắc “chỉ mục” ba lần thường có thể liên quan hơn bài nhắc một lần. Nhưng một bài lặp cụm từ 300 lần không nên nhận điểm gấp 100 lần. Phần phân số trong BM25 giúp giới hạn lợi ích tăng thêm của TF.

### 9.2. Độ dài document ảnh hưởng điểm

Nếu hai document đều chứa “inverted index” một lần:

- Document ngắn, phần lớn bàn về inverted index.
- Document dài 20.000 từ, chỉ nhắc cụm này trong một câu.

BM25 thường có xu hướng đánh giá mức tập trung của document ngắn cao hơn, thông qua **length normalization**, nếu các yếu tố khác tương đương. Tác động phụ thuộc tham số **b** và field được chấm điểm.

### 9.3. Điểm BM25 không phải xác suất

Điểm **12,4** không có nghĩa “tài liệu đúng 12,4%” hay “độ tin cậy 12,4/100”. Score thường là **giá trị tương đối trong bối cảnh một truy vấn, một tập chỉ mục và cấu hình ranking**. Không nên so điểm thô của hai truy vấn hoặc hai chỉ mục khác nhau như cùng thang đo nếu chưa có bước chuẩn hóa thích hợp.

## 10. Field boosting và các tín hiệu xếp hạng khác

Trong bài viết, từ khóa xuất hiện trong **title** thường mang ý nghĩa mạnh hơn xuất hiện ở một dòng không quan trọng của body.

Một công thức khái niệm:

~~~text
textScore =
    3.0 × relevance(title)
  + 1.5 × relevance(description)
  + 1.0 × relevance(content)
~~~

**Boost** thể hiện ưu tiên của sản phẩm, không có một bộ trọng số cố định phù hợp mọi loại dữ liệu. Có thể kết hợp thêm:

- **Phrase match:** ưu tiên cụm từ đúng.
- **Freshness:** tài liệu mới hơn, nếu độ mới liên quan đến ý định tìm kiếm.
- **Popularity/engagement:** lượt xem, lượt chọn hữu ích, tỷ lệ click; phải phòng tín hiệu bị thao túng.
- **Quality/authority:** trạng thái kiểm duyệt, độ tin cậy của nguồn.
- **Business rules:** ưu tiên tài liệu ngôn ngữ hoặc bộ sưu tập người dùng đang xem.
- **Semantic similarity:** kết hợp truy xuất theo embedding khi cần xử lý ý nghĩa khác mặt chữ.

Ví dụ xếp hạng:

~~~text
finalScore =
    textScore
  + boundedFreshnessBoost
  + boundedQualityBoost
~~~

Hàm trên chỉ là minh họa. Nếu cộng trực tiếp các thành phần có thang đo chênh lệch, một tín hiệu có thể lấn át hoàn toàn các tín hiệu còn lại. Các hệ search thường có cơ chế function score, rescore hoặc pipeline ranking riêng để kiểm soát cách kết hợp.

### 10.1. Độ mới không phải lúc nào cũng tốt

Với truy vấn **“API phiên bản mới nhất”**, bài mới có thể quan trọng. Nhưng với truy vấn **“định nghĩa chỉ mục đảo”**, bài cũ vẫn có thể chính xác và tốt hơn bài mới. Boost độ mới không điều kiện có thể khiến nội dung ít liên quan đứng đầu.

### 10.2. Tìm bằng từ khóa và tìm theo ngữ nghĩa

**Lexical search** dựa trên token và inverted index; phù hợp với mã sản phẩm, tên riêng, ký hiệu kỹ thuật và cụm từ chính xác. **Semantic/vector search** dựa trên biểu diễn embedding; có thể tìm tài liệu cùng ý dù khác từ. Hai cách có thể bổ trợ nhau trong **hybrid search**.

Ví dụ:

~~~text
Query: "đừng để dữ liệu đã ghi bị mất khi máy hỏng"

Lexical:
  tìm những tài liệu chứa token gần giống câu hỏi

Semantic:
  có thể tìm bài về "durability" và "write-ahead log"
  dù nội dung không lặp đúng các từ trong query
~~~

Vector search không thay thế hoàn toàn inverted index: nó có thể bỏ sót mã định danh chính xác, gặp vấn đề với số liệu hiếm hoặc đưa kết quả cùng chủ đề nhưng không đáp ứng điều kiện. Kết hợp phải có kiểm thử relevance và lớp lọc quyền phù hợp.

## 11. Ví dụ truy vấn kết hợp tìm kiếm, lọc và tăng trọng số

Giả sử hệ thống bài học lưu:

~~~json
{
  "id": "lesson-104",
  "tenantId": "academy-a",
  "title": "Chỉ mục đảo trong tìm kiếm",
  "description": "Tìm hiểu cách token dẫn tới posting list.",
  "status": "PUBLISHED",
  "language": "vi"
}
~~~

Yêu cầu:

> Tìm các bài xuất bản của academy-a nói về “chỉ mục đảo”, ưu tiên title so với description.

Ví dụ dưới đây dùng DSL theo phong cách **Elasticsearch/OpenSearch** để minh họa ý tưởng; tên field, analyzer và mapping phải được cấu hình tương ứng trong hệ thực tế.

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "academy-a" } },
        { "term": { "status": "PUBLISHED" } }
      ],
      "should": [
        {
          "match": {
            "title": {
              "query": "chỉ mục đảo",
              "boost": 3
            }
          }
        },
        {
          "match": {
            "description": {
              "query": "chỉ mục đảo",
              "boost": 1
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  },
  "size": 20
}
~~~

Giải thích:

1. **filter** yêu cầu đúng tenant và trạng thái, thường không đóng góp vào text relevance score.
2. **should** đưa hai nguồn liên quan là title và description.
3. **boost = 3** làm match trong title có ảnh hưởng lớn hơn trong description theo cách engine kết hợp điểm.
4. **minimum_should_match = 1** yêu cầu ít nhất một nhánh tìm kiếm văn bản phù hợp.
5. **size = 20** giới hạn số kết quả trả về.

Trong thực tế, thường thêm field nội dung, phrase boost, ngôn ngữ, sắp xếp ổn định, highlight và cơ chế phân trang. Quan trọng hơn, **tenant/permission filter phải có trong đường truy vấn server-side**, không chỉ lọc sau khi engine đã trả kết quả cho client.

### 11.1. Vì sao filter khác score?

Trạng thái **PUBLISHED** là một điều kiện **được phép hiển thị hay không**, chứ không phải dấu hiệu tài liệu nói nhiều hơn về “chỉ mục đảo”. Nếu cố đưa trạng thái vào ranking thay vì filter, bài ở trạng thái DRAFT vẫn có thể xuất hiện trong kết quả.

Tương tự:

- **Bộ lọc quyền/tenant**: điều kiện bắt buộc.
- **Bộ lọc ngày, loại tài liệu**: tùy yêu cầu có thể là điều kiện bắt buộc.
- **Tiêu đề khớp từ khóa**: tín hiệu relevance.
- **Độ mới/popularity**: tín hiệu phụ để xếp hạng nếu phù hợp.

Phân tách rõ giúp vừa đúng nghiệp vụ vừa dễ giải thích kết quả.

### 11.2. Kiểm tra query bằng ví dụ có đối chứng

Chuẩn bị các document:

~~~text
Doc A: title = "Chỉ mục đảo", status = PUBLISHED, tenant = academy-a
Doc B: title = "NoSQL tổng quan", description = "Có nói về chỉ mục đảo",
       status = PUBLISHED, tenant = academy-a
Doc C: title = "Chỉ mục đảo", status = DRAFT, tenant = academy-a
Doc D: title = "Chỉ mục đảo", status = PUBLISHED, tenant = academy-b
~~~

Với truy vấn của người dùng thuộc **academy-a**, kết quả hợp lệ chỉ gồm A và B. A có thể được xếp trước B nhờ title boost. C bị loại vì trạng thái, D bị loại vì tenant. Một công cụ tìm kiếm tốt cần đúng **cả logic lọc lẫn thứ tự liên quan**.

## 12. Tìm kiếm tiếng Việt: những chi tiết cần thiết kế

Tiếng Việt là ngôn ngữ có dấu thanh và từ nhiều tiếng viết cách nhau bằng khoảng trắng. Analyzer chỉ lowercase rồi split theo dấu cách có thể thiếu chính xác về ngữ nghĩa.

### 12.1. Tách tiếng khác tách từ

~~~text
Văn bản: "cơ sở dữ liệu quan hệ"

Tách theo khoảng trắng:
  [cơ, sở, dữ, liệu, quan, hệ]

Tách theo từ/cụm từ trong một thiết kế có segmenter:
  [cơ_sở_dữ_liệu, quan_hệ]
~~~

Dạng token thực tế phụ thuộc thuật toán tách từ. Với chủ đề chuyên ngành, cần xem khả năng nhận diện cụm **“học máy”**, **“khóa chính”**, **“chỉ mục đảo”**, **“sơ đồ đồ thị”** và tên sản phẩm.

Một số hệ hỗ trợ n-gram, từ điển riêng hoặc plugin tokenizer cho ngôn ngữ; phải kiểm tra khả năng hỗ trợ thực tế và chi phí bảo trì khi nâng cấp engine.

### 12.2. Tìm có dấu và không dấu

~~~text
Query A: "cơ sở dữ liệu"
Query B: "co so du lieu"
~~~

Người dùng thường mong cả hai truy vấn tìm thấy bài liên quan. Nhưng chuẩn hóa bỏ dấu có thể tạo mơ hồ:

~~~text
ma, má, mà, mã, mạ -> ma
~~~

Một hướng là lưu hai đường tìm:

~~~text
title.vi_exact  -> giữ dấu, analyzer tiếng Việt
title.vi_folded -> chuẩn hóa dấu có kiểm soát
~~~

Khi query có dấu, ưu tiên match trên **vi_exact**; dùng **vi_folded** để tăng recall. Khi query không dấu, có thể tăng trọng số dựa vào các tín hiệu khác như phrase, danh mục hoặc tương tác tìm kiếm. Không được đánh đồng tìm không dấu với “tìm đúng tuyệt đối”.

### 12.3. Từ đồng nghĩa và thuật ngữ chuyên ngành

Ví dụ:

~~~text
CSDL ↔ cơ sở dữ liệu
full-text search ↔ tìm kiếm toàn văn
inverted index ↔ chỉ mục đảo
~~~

Từ đồng nghĩa có thể được mở rộng khi lập chỉ mục, khi truy vấn hoặc kết hợp. Mỗi cách có đánh đổi:

- Mở rộng lúc index có thể yêu cầu reindex khi đổi từ điển.
- Mở rộng lúc query cho phép thay đổi từ điển linh hoạt hơn nhưng có thể tăng nhánh truy vấn.
- Mở rộng sai gây false positive: “Java” không luôn đồng nghĩa “JavaScript”, “graph” không luôn đồng nghĩa “biểu đồ”.

Từ điển nên theo **ngữ cảnh sản phẩm, ngành và ngôn ngữ**; tránh danh sách đồng nghĩa chung thiếu kiểm soát.

### 12.4. Stop words

Một số hệ loại các từ thông dụng để giảm nhiễu. Nhưng xóa stop words có thể đổi nghĩa của truy vấn:

~~~text
"có quyền"  và  "không có quyền"
~~~

Nếu bỏ “không” như từ dừng, kết quả sẽ rất nguy hiểm với câu hỏi về quyền hoặc chính sách. Hãy phân tích từ điển stop words theo trường/ngôn ngữ, đặc biệt khi hỗ trợ phrase search và truy vấn chứa phủ định.

### 12.5. Chuẩn Unicode và dữ liệu nhập liệu

Đầu vào có thể dùng các cách biểu diễn Unicode khác nhau nhưng nhìn giống nhau, ký tự khoảng trắng đặc biệt hoặc dấu câu khác nhau. Có thể cần chuẩn hóa Unicode (chẳng hạn NFC theo quy ước), whitespace và encoding trước khi index/search.

Việc chuẩn hóa phải đồng nhất giữa ghi và truy vấn, và cần giữ **nội dung gốc** để hiển thị đúng cho người dùng. Không nên tự động sửa hoặc mất thông tin trong source document chỉ vì một trường search được chuẩn hóa.

## 13. Highlight: vì sao kết quả có thể tô đậm đoạn khớp?

Một trang kết quả tìm kiếm thường hiển thị:

> **Chỉ mục đảo** trong hệ tìm kiếm  
> Mỗi **token** ánh xạ tới danh sách tài liệu để truy xuất nhanh...

Highlight giúp người dùng hiểu **vì sao** một kết quả được trả về. Nó có thể dựa vào:

- Tài liệu gốc được lưu.
- Offsets/positions đã lập chỉ mục.
- Thuật toán phân đoạn văn bản thành snippet.
- Match của truy vấn sau khi phân tích từ đồng nghĩa/phrase.

Nếu không bảo quản offsets hoặc phải highlight trên văn bản đã bị thay đổi, đoạn tô đậm có thể không trùng vị trí. Với tiếng Việt, sự khác nhau giữa token có dấu, không dấu và token ghép càng làm lựa chọn highlighter quan trọng.

Highlight là tính năng hiển thị và giải thích; **nó không chứng minh kết quả có độ liên quan cao nhất**. Một engine vẫn có thể highlight một cụm xuất hiện tình cờ ở cuối tài liệu.

## 14. Tìm kiếm theo nội dung và nguồn dữ liệu chính

Không phải lúc nào search index cũng nên là **system of record**.

Ví dụ, nền tảng thương mại cần:

- Quản lý sản phẩm, giá và tồn kho.
- Đặt hàng có giao dịch.
- Tìm kiếm sản phẩm theo tên, thuộc tính và nội dung mô tả.

Một kiến trúc điển hình:

~~~mermaid
flowchart LR
    A["API quản trị"] --> B[("DB nghiệp vụ")]
    B --> C["Outbox / CDC / event"]
    C --> D["Indexer"]
    D --> E[("Search index")]
    F["API tìm kiếm"] --> E
    F --> G["Kết quả + kiểm tra quyền/giá trị cần thiết"]
~~~

**DB nghiệp vụ** nắm các ràng buộc như tồn kho, thanh toán và giá bán. **Search index** là bản chiếu được tối ưu cho việc tìm và xếp hạng. Nếu chỉ mục bị hỏng, hệ thống có thể rebuild từ nguồn chính và log sự kiện đủ tin cậy.

### 14.1. Những trạng thái nhất quán có thể xuất hiện

~~~text
10:00:00  Giá sản phẩm trong DB đổi từ 500.000 thành 450.000
10:00:01  API quản trị xác nhận cập nhật thành công
10:00:02  Event đến bộ lập chỉ mục
10:00:03  Search index mới phản ánh giá 450.000
~~~

Trong khoảng 10:00:01–10:00:03, kết quả tìm kiếm có thể vẫn hiển thị giá cũ. Đây là hệ quả của **eventual consistency** của bản chiếu cập nhật bất đồng bộ, nếu kiến trúc chọn cách này.

Với dữ liệu nhạy cảm về tính đúng đắn, ứng dụng phải quyết định:

- Dữ liệu nào có thể hiển thị hơi cũ?
- Dữ liệu nào phải xác minh lại từ nguồn gốc trước khi thực hiện giao dịch?
- Khi xóa quyền truy cập hoặc thu hồi nội dung, độ trễ cập nhật search có chấp nhận được không?

Đặc biệt, **thu hồi quyền và xóa dữ liệu nhạy cảm** không nên dựa duy nhất vào hy vọng chỉ mục sẽ đồng bộ sớm; cần kiểm tra quyền ở điểm thực thi truy vấn/kết quả phù hợp với mô hình bảo mật.

### 14.2. Ghi trực tiếp hai hệ có thể gây lệch

Nếu một request tự ghi DB rồi ghi search index:

~~~text
UPDATE database ...     -> thành công
INDEX search document   -> timeout
~~~

Hai nơi tạm thời không đồng bộ. Đảo thứ tự cũng có thể gây tình huống search trả nội dung mà DB chưa commit.

Một cách tổ chức thường dùng là **transactional outbox** trong DB nguồn:

1. Ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng một transaction.
2. Worker hoặc CDC đọc outbox và cập nhật search index.
3. Xử lý retry với thao tác idempotent theo document ID/version.
4. Theo dõi lag, bản ghi lỗi và khả năng phát lại.

Outbox giúp tránh một số dạng mất sự kiện giữa DB và broker, nhưng không tự đem lại “exactly once” trên toàn pipeline. Bộ indexer nên xử lý trùng lặp, đảo thứ tự và sự kiện đến muộn theo version/sequence thích hợp.

### 14.3. Xóa và cập nhật

Khi bài viết bị xóa hoặc đổi từ PUBLISHED sang PRIVATE, indexer phải:

- Xóa/tombstone document trong search hoặc cập nhật trạng thái và quyền.
- Tránh một sự kiện cũ “hồi sinh” document đã xóa.
- Bảo đảm mọi alias/chỉ mục phiên bản mới đều có trạng thái đúng.
- Cân nhắc cache trang kết quả, gợi ý tìm kiếm và highlight có thể giữ thông tin cũ.

Vì vậy, **reindex** không đơn thuần là “chạy lại tất cả INSERT”; cần có quy tắc ghi phiên bản, cutover và xử lý xóa.

## 15. Reindex, alias và thay đổi analyzer

Thay đổi quy tắc analyzer có thể làm **tập token của cùng một document khác đi**. Ví dụ chuyển từ tách tiếng sang tách từ tiếng Việt, hoặc thêm từ đồng nghĩa lúc index, thường không thể chỉ sửa cấu hình rồi kỳ vọng các posting cũ tự được tạo lại.

Quy trình khái niệm:

~~~text
Index hiện tại: lessons_v1
  ↓
Tạo lessons_v2 với analyzer/mapping mới
  ↓
Đọc dữ liệu nguồn và lập chỉ mục vào v2
  ↓
Kiểm tra số lượng, truy vấn mẫu, quyền và dữ liệu xóa
  ↓
Chuyển alias "lessons_search" sang v2
  ↓
Theo dõi, giữ đường rollback có kiểm soát
~~~

Các công cụ alias, cách chuyển atomic và cách bắt kịp thay đổi trong lúc reindex phụ thuộc engine. Có thể cần snapshot/change log, chạy song song và replay sự kiện đến đúng version trước khi cutover.

Các lỗi thường gặp:

- Reindex chỉ dữ liệu hiện còn mà quên các bản ghi vừa bị xóa.
- Truy vấn lẫn mapping cũ/mới trong quá trình chuyển.
- Sự kiện cũ ghi đè dữ liệu mới.
- Không đánh giá dung lượng tạm thời khi hai index cùng tồn tại.
- Đổi analyzer nhưng không kiểm tra phần search-as-you-type và synonym.

## 16. Hiệu năng và chi phí: inverted index không miễn phí

Các hệ tìm kiếm cần tài nguyên cho **ghi chỉ mục**, **đọc posting**, **chấm điểm** và **lưu dữ liệu/replica**.

### 16.1. Những yếu tố làm index lớn

- Số document và số field được lập chỉ mục.
- Số token duy nhất và tổng số lần xuất hiện.
- Positions, offsets, term vectors và metadata dùng cho ranking.
- N-gram/edge n-gram, synonyms mở rộng lúc index.
- Số bản sao, dữ liệu hiển thị được lưu, doc values.
- Tần suất update/delete và các segment chưa được merge.

Một thiết kế lập chỉ mục cả nội dung dài, mọi thuộc tính JSON và nhiều n-gram field có thể tốn đáng kể dung lượng và thời gian rebuild.

### 16.2. Những truy vấn thường tốn tài nguyên

- Wildcard quá rộng, nhất là ở đầu từ.
- Regex/phép mở rộng sinh rất nhiều term.
- Fuzzy query với giới hạn chỉnh sửa cao trên từ quá ngắn.
- Truy vấn OR với nhiều term phổ biến.
- Phrase/proximity trên dữ liệu lớn với posting positions dày.
- Sort/aggregation trên field chưa có cấu trúc tối ưu.
- Phân trang sâu bằng offset lớn.
- Truy vấn trên nhiều shard/tenant rồi chỉ lọc sau cùng.

### 16.3. Phân trang và tổng số kết quả

Với trang 1, hệ có thể chấm điểm ứng viên và lấy top 20. Nhưng khi người dùng yêu cầu trang thứ 10.000, kiểu **from + size/offset** có thể khiến engine phải giữ hoặc xét rất nhiều kết quả trước đó.

Các hệ thường cung cấp cơ chế như **search_after**, cursor, point-in-time snapshot hoặc cách phân trang riêng. Muốn phân trang ổn định, cần một tiêu chí **tie-breaker** nhất quán và hiểu cách dữ liệu cập nhật trong lúc người dùng chuyển trang.

Tổng số hit chính xác cũng có thể tốn tài nguyên ở quy mô lớn. Nếu giao diện chỉ cần “có nhiều kết quả”, có thể dùng đếm xấp xỉ hoặc giới hạn theo khả năng engine, thay vì luôn đòi số lượng tuyệt đối.

### 16.4. Tối ưu bắt đầu bằng dữ liệu đại diện

Benchmark nên có:

| Yếu tố | Cần mô phỏng |
| --- | --- |
| Corpus | Số lượng document, độ dài, trường và ngôn ngữ thực tế |
| Query mix | Truy vấn một từ, nhiều từ, phrase, typo, filter, autocomplete |
| Field distribution | Title ngắn, body dài, tags, metadata |
| Update mix | Thêm mới, sửa, xóa, đổi quyền, reindex |
| Tenant skew | Tenant rất lớn và tenant nhỏ |
| Latency | p50, p95, p99, không chỉ giá trị trung bình |
| Resource | CPU, RAM, disk, I/O, size, merge/refresh backlog |
| Search quality | Recall/precision và mức hài lòng của kết quả top-K |

Không có một chỉ số “truy vấn mất 20 ms” có giá trị chung cho mọi corpus hay hạ tầng. Quan trọng là đo đúng workload, đúng quy mô và mức chất lượng kết quả kỳ vọng.

## 17. Đánh giá chất lượng tìm kiếm bằng tập truy vấn mẫu

Tối ưu relevance không thể chỉ xem truy vấn có chạy nhanh hay không.

Giả sử cần tìm tài liệu về **chỉ mục đảo**. Tạo một tập kiểm thử thủ công:

| Query | Kết quả mong muốn | Điểm cần kiểm tra |
| --- | --- | --- |
| chỉ mục đảo | Bài chính về inverted index đứng đầu | Phrase/title relevance |
| chi muc dao | Vẫn thấy bài liên quan | Tìm không dấu |
| inverted index | Tìm bài tiếng Việt có thuật ngữ tương đương | Từ đồng nghĩa/chuyên ngành |
| chỉ múc đảo | Có thể sửa lỗi nhẹ | Fuzzy/typo tolerance |
| tìm kiếm văn bản | Bài tổng quan và bài chuyên sâu có thứ hạng hợp lý | Relevance nhiều ý |
| lesson-104 | Trả đúng ID nếu đây là tìm theo mã | Exact lookup |
| "không có quyền" | Không bỏ mất phủ định | Stopword/phrase semantics |

Có thể dùng một nhóm người đánh giá thủ công mức liên quan theo thang:

~~~text
0 = không liên quan
1 = hơi liên quan
2 = liên quan
3 = rất liên quan
~~~

Sau đó đo **Precision@K**, **Recall@K**, **MRR** hoặc **NDCG@K** tùy mục tiêu. Đây là các chỉ số khác nhau:

- **Precision@K:** Tỷ lệ kết quả liên quan trong K vị trí đầu.
- **Recall@K:** Phần tài liệu liên quan đã tìm được trong K vị trí đầu so với tập tài liệu liên quan.
- **MRR (Mean Reciprocal Rank):** Nhấn mạnh vị trí xuất hiện đầu tiên của câu trả lời phù hợp.
- **NDCG@K:** Đánh giá chất lượng thứ hạng khi có nhiều mức độ liên quan.

Một search engine có thể tăng Recall bằng mở rộng nhiều synonym, nhưng Precision lại giảm vì nhiều bài không đúng chủ đề xuất hiện. Lựa chọn phụ thuộc bối cảnh: tìm tài liệu pháp lý cần bao phủ tốt, còn autocomplete cần kết quả cực nhanh và chính xác ở đầu danh sách.

### 17.1. Ví dụ Precision@3

Query có ba kết quả đầu:

~~~text
1. Bài về chỉ mục đảo        -> liên quan
2. Bài về full-text search  -> liên quan
3. Bài về cache             -> không liên quan
~~~

**Precision@3 = 2/3** nếu định nghĩa liên quan là nhãn nhị phân. Con số này không nói bài tốt nhất đã đứng vị trí 1 hay chưa; để đánh giá thứ tự chi tiết có thể dùng NDCG hoặc chỉ số ranking phù hợp.

### 17.2. Kết quả có thể khác vì ngôn ngữ và nhóm người dùng

Query “index” trong hệ tài chính, cơ sở dữ liệu và tìm kiếm tài liệu có thể ám chỉ những khái niệm khác nhau. Một bộ synonym chung cho mọi tenant hoặc ngành có thể làm kết quả sai. Nếu cá nhân hóa, cần tránh dùng dữ liệu hành vi một cách không được kiểm soát và phải đo sự công bằng/chất lượng theo nhóm người dùng có nhu cầu khác nhau.

## 18. Quyền truy cập và an toàn dữ liệu trong search

Search index có thể chứa đoạn nội dung chưa công khai, tên người dùng, token nhạy cảm hoặc thông tin cá nhân. Một lỗ hổng quyền trong truy vấn tìm kiếm có thể lộ dữ liệu dù trang chi tiết đã có kiểm tra quyền.

### 18.1. Bảo vệ theo tenant và ACL

Ví dụ mỗi tài liệu có:

~~~json
{
  "id": "doc-12",
  "tenantId": "academy-a",
  "visibility": "PRIVATE",
  "allowedUserIds": ["U01", "U02"]
}
~~~

API tìm kiếm phải xác định tenant và danh tính người dùng từ thông tin xác thực **được kiểm tra ở server**, rồi áp dụng điều kiện quyền trước khi trả kết quả. Không tin tenantId do client tự nhập nếu không có bước ủy quyền.

Lưu ý:

- Snippet và highlight có thể lộ nội dung ngay trên trang kết quả.
- Autocomplete có thể lộ tiêu đề tài liệu chưa công khai.
- Facet count có thể cho biết sự tồn tại của tài liệu bí mật.
- Cache kết quả cần có phạm vi khóa theo quyền/tenant.
- Index cập nhật bất đồng bộ có thể giữ quyền cũ một thời gian sau khi tài liệu bị thu hồi.

Nếu quyền rất nhạy cảm và hay thay đổi, có thể cần kiểm tra quyền lúc trả kết quả từ hệ nguồn/authorization service, kết hợp với bộ lọc sớm để tránh rò rỉ dữ liệu. Cách làm cụ thể phụ thuộc khả năng truy vấn và mức rủi ro được chấp nhận.

### 18.2. Giới hạn truy vấn từ người dùng

Không chuyển tùy ý chuỗi người dùng thành query DSL có quyền thực thi mọi loại truy vấn. Nên xây một API giới hạn:

~~~text
POST /search
{
  "query": "chỉ mục đảo",
  "language": "vi",
  "pageSize": 20
}
~~~

Ở server:

1. Kiểm tra độ dài chuỗi, bộ lọc và giới hạn pageSize.
2. Chọn tập field/analyzer được phép.
3. Tự thêm filter tenant, trạng thái và quyền.
4. Hạn chế wildcard/regex/fuzzy tốn tài nguyên.
5. Ghi log truy vấn phù hợp với chính sách bảo vệ dữ liệu.

Một query parser cho phép người dùng nhập cú pháp chuyên biệt có thể rất hữu ích cho người dùng chuyên môn, nhưng phải tách rõ **ý định tìm kiếm** với **quyền truy cập và giới hạn tài nguyên**.

## 19. Chọn search engine riêng hay dùng tính năng của database hiện có?

Khi nhu cầu chỉ là tìm theo vài trường ngắn trong hệ thống nhỏ, có thể sử dụng chỉ mục phù hợp hoặc full-text search của database đang có. Khi nhu cầu tăng về relevance, autocomplete, typo tolerance, nhiều ngôn ngữ, highlight và lưu lượng truy vấn lớn, một search engine chuyên dụng có thể đáng cân nhắc.

| Tiêu chí | Search tích hợp trong DB nguồn | Search engine chuyên dụng |
| --- | --- | --- |
| Tổ chức vận hành | Thường ít thành phần hơn | Thêm cluster/dịch vụ và pipeline dữ liệu |
| Tính nhất quán với bản ghi gốc | Có thể gần giao dịch hơn tùy tính năng | Thường là bản chiếu bất đồng bộ nếu kiến trúc tách riêng |
| Xếp hạng và analyzer | Tùy DB, có thể đáp ứng tốt nhu cầu cơ bản | Thường nhiều lựa chọn cho relevance/analyzer |
| Autocomplete/fuzzy/highlight | Tùy sản phẩm và extension | Thường có công cụ chuyên biệt |
| Mở rộng tải tìm kiếm độc lập | Có thể bị giới hạn bởi DB nguồn | Có thể tách quy mô và tài nguyên tìm kiếm |
| Chi phí đồng bộ | Ít hơn nếu cùng DB | Cần CDC/outbox, reindex, giám sát lag |
| Phù hợp giao dịch | DB nguồn thường được chọn vì bất biến nghiệp vụ | Search index thường không là nguồn chính cho giao dịch nhiều thực thể |

Không nên coi bảng này là khẳng định “SQL yếu về search” hoặc “NoSQL luôn mạnh về search”. PostgreSQL có full-text search, trigram extension và nhiều kiểu chỉ mục; một số document database có tính năng search riêng hoặc tích hợp dịch vụ tìm kiếm. Chọn dựa trên truy vấn, chất lượng cần đạt, chi phí và năng lực vận hành.

### 19.1. Ba tình huống định hướng

**Tình huống A — Trang quản trị có vài nghìn sản phẩm.** Cần tìm chính xác theo mã, lọc theo danh mục và tìm tên cơ bản. DB nguồn với index/full-text extension phù hợp có thể đủ, giảm nhu cầu vận hành hai hệ.

**Tình huống B — Kho bài học nhiều ngôn ngữ.** Cần truy vấn chủ đề, sửa lỗi gõ, tìm không dấu, synonym chuyên ngành, highlight, boost tiêu đề, cập nhật liên tục. Một search engine chuyên dụng có thể tạo giá trị rõ ràng nếu được đo bằng truy vấn thật.

**Tình huống C — Hệ quản lý đơn và thanh toán.** Tìm đơn theo mã/trạng thái/khách hàng và bảo vệ giao dịch quan trọng. RDBMS hoặc hệ giao dịch chính vẫn phù hợp để nắm dữ liệu gốc; search index chỉ nên bổ sung nếu yêu cầu tìm kiếm nâng cao thực sự cần.

## 20. Các hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu chính xác hơn |
| --- | --- |
| “Full-text search chỉ cần LIKE %từ khóa%.” | LIKE là tìm mẫu chuỗi, không tự cung cấp tokenization, posting lists, ranking và phrase semantics đầy đủ. |
| “Một document là một file Word/PDF.” | Document là đơn vị lập chỉ mục logic, có thể là sản phẩm, bài học hoặc một đoạn. |
| “Tách theo dấu cách luôn đủ.” | Tiếng Việt có từ nhiều tiếng, tên riêng và cách viết phức tạp cần analyzer phù hợp. |
| “Có inverted index là mọi truy vấn nhanh.” | Wildcard rộng, fuzzy nhiều nhánh, query rất phổ biến và phân trang sâu có thể tốn tài nguyên. |
| “AND các từ đồng nghĩa với phrase match.” | AND chỉ yêu cầu cùng có mặt; phrase còn xét vị trí/thứ tự. |
| “Term query tương đương full-text match.” | Term tìm giá trị đã lập chỉ mục; match thường phân tích văn bản truy vấn. |
| “Độ liên quan là xác suất đúng.” | Search score thường là điểm tương đối, phụ thuộc công thức, field và corpus. |
| “Từ xuất hiện càng nhiều thì điểm tăng không giới hạn.” | BM25 thường có saturation và chuẩn hóa theo độ dài. |
| “Mọi bài mới nên được xếp trước.” | Freshness hữu ích tùy mục tiêu truy vấn, có thể gây nhiễu nội dung kiến thức nền. |
| “Lưu ba replica là đủ cho dữ liệu nguồn.” | Replication không thay backup, transaction hay chính sách xóa/khôi phục. |
| “Search index luôn thấy ghi mới ngay.” | Nhiều hệ có refresh/near-real-time, độ trễ đồng bộ và semantics riêng. |
| “Lọc quyền ở giao diện là đủ.” | Phải kiểm tra quyền ở server/truy vấn; snippet và gợi ý cũng có thể làm lộ dữ liệu. |

## 21. Quy trình xây một tính năng tìm kiếm toàn văn

### Bước 1 — Xác định tập tài liệu và đơn vị kết quả

Liệt kê loại document, ID ổn định, nguồn dữ liệu gốc, trường hiển thị, trường được index, ngôn ngữ và vòng đời. Quyết định trả theo bài, theo đoạn hay theo thực thể.

### Bước 2 — Thu thập mẫu truy vấn thực tế

Nhóm truy vấn theo nhu cầu:

~~~text
Tra mã chính xác       -> lesson-104
Tìm chủ đề             -> chỉ mục đảo
Tìm không dấu          -> chi muc dao
Tìm cụm từ             -> "tìm kiếm toàn văn"
Tìm sai chính tả       -> databse
Autocomplete           -> elas...
Lọc                    -> khóa học NoSQL đã xuất bản
~~~

Xác định mức ưu tiên và những truy vấn bắt buộc phải trả đúng để tránh tạo analyzer/index tùy tiện.

### Bước 3 — Thiết kế mapping và analyzer theo field

Tách field exact/keyword khỏi field text. Đối với tiếng Việt, thử tokenizer phù hợp, quy tắc giữ/bỏ dấu, synonym, stopword và phrase. Kiểm tra token stream bằng những chuỗi có nhiều từ ghép và tên riêng.

### Bước 4 — Xây inverted index và nhập dữ liệu mẫu

Lập chỉ mục vài document đã biết trước kết quả đúng. Kiểm tra:

- Truy vấn một term.
- Truy vấn nhiều term AND/OR.
- Phrase query theo positions.
- Exact filter status/tenant.
- Title boost so với body.
- Highlight và khả năng trả về nguồn gốc.

### Bước 5 — Đặt quyền và điều kiện nghiệp vụ vào API

Tạo hợp đồng tìm kiếm cố định, xác thực người dùng và áp bộ lọc tenant/ACL, visibility, trạng thái xuất bản. Bảo vệ autocomplete, counts và snippets.

### Bước 6 — Thiết kế đồng bộ và rebuild

Nếu có DB nguồn, tạo đường đồng bộ đáng tin cậy, thường thông qua outbox/CDC hoặc một pipeline có khả năng phát lại. Dùng ID/version ổn định, xử lý xóa, retry và dữ liệu đến muộn. Chuẩn bị cách reindex khi analyzer/mapping thay đổi.

### Bước 7 — Đo relevance và hiệu năng

Dùng query set đã có nhãn, đo Precision@K/Recall@K/NDCG nếu phù hợp, so sánh thay đổi trước/sau. Đồng thời đo latency, mức dùng tài nguyên, tốc độ index, backlog, thời gian refresh và khối lượng dữ liệu.

### Bước 8 — Theo dõi tìm kiếm trong vận hành

Các tín hiệu nên quan sát:

| Nhóm | Ví dụ tín hiệu |
| --- | --- |
| Search latency | p50/p95/p99, timeout, slow queries |
| Chất lượng | Truy vấn không có kết quả, click-through, reformulation, phản hồi |
| Index health | Số document, dung lượng, shard/segment, lỗi indexing |
| Pipeline | Độ trễ từ source đến search, retry, dead-letter events |
| Query safety | Wildcard/regex nặng, tài nguyên quá ngưỡng, request bị giới hạn |
| Bảo mật | Kết quả bị loại bởi ACL, phát hiện dữ liệu lộ trong snippet |
| Vòng đời | Reindex thành công, xóa/tombstone, thời gian rebuild |

Giám sát phải gắn với mục tiêu cụ thể. Ví dụ “zero results” có thể nghĩa analyzer thiếu synonym, nhưng cũng có thể đơn giản là người dùng tìm một nội dung chưa tồn tại.

## 22. Bài tập thực hành

### Bài 1: Tự dựng inverted index

Cho ba document sau, dùng lowercase và tách theo khoảng trắng, không loại token:

~~~text
D1: "search index nhanh"
D2: "index giúp search"
D3: "database lưu dữ liệu"
~~~

**Yêu cầu:** Lập posting list cho các token **search**, **index**, **database**. Truy vấn AND **search AND index** trả document nào?

**Gợi ý:**

~~~text
search   -> [D1, D2]
index    -> [D1, D2]
database -> [D3]

search AND index -> [D1, D2]
~~~

### Bài 2: Phân biệt AND với phrase

Cho:

~~~text
D1: "chỉ mục đảo"
D2: "đảo thứ tự của chỉ mục"
~~~

**Yêu cầu:** Truy vấn AND ba token **chỉ**, **mục**, **đảo** và truy vấn phrase **“chỉ mục đảo”** có kết quả giống nhau không?

**Gợi ý:** Cả D1 và D2 chứa các token theo ví dụ tách tiếng; chỉ D1 có ba token liền nhau đúng thứ tự. Phải có thông tin positions để kiểm tra phrase.

### Bài 3: Chọn field type

Ứng dụng có các field **productId**, **title**, **description**, **status**, **tenantId** và **createdAt**.

**Yêu cầu:** Field nào nên ưu tiên exact/keyword, field nào text, field nào date?

**Gợi ý:** productId/status/tenantId thường cần exact; title/description cần text analyzer; createdAt cần date/range. Có thể thêm multi-field nếu title còn phải sort hoặc match nguyên chuỗi.

### Bài 4: Vì sao tài liệu ngắn có thể được xếp trên?

Hai bài đều có một lần term **“BM25”**. Bài A có 200 token, bài B có 20.000 token; các yếu tố khác tương đương.

**Yêu cầu:** Giải thích vai trò length normalization.

**Gợi ý:** BM25 thường có xu hướng ưu tiên bài ngắn hơn vì term chiếm tỷ lệ tập trung cao hơn, với tác động phụ thuộc tham số b và field. Điểm này không phải đánh giá chất lượng nội dung độc lập.

### Bài 5: Tìm kiếm tiếng Việt không dấu

Người dùng nhập **“co so du lieu”**. Hệ chỉ index dạng có dấu **“cơ sở dữ liệu”** nhưng chưa có quy tắc chuẩn hóa tương thích.

**Yêu cầu:** Nêu hai phương án để tăng recall và rủi ro.

**Gợi ý:** Dùng trường folded không dấu, analyzer có tách từ/chuẩn hóa phù hợp hoặc bổ sung synonym theo trường hợp. Rủi ro là đồng nhất những từ khác nghĩa khi mất dấu và làm tăng số kết quả nhiễu.

### Bài 6: Tìm kiếm đa tenant

Document D1 và D2 đều có title **“Chỉ mục đảo”**, nhưng D1 thuộc tenant A và D2 thuộc tenant B. Người dùng tenant A gửi query “chỉ mục đảo”.

**Yêu cầu:** Thiết kế điều kiện truy vấn bảo đảm không trả D2.

**Gợi ý:** Xác định tenant từ phiên xác thực ở server, áp filter tenantId = A và các điều kiện quyền cùng với full-text query. Không trả kết quả tất cả tenant về client rồi mới lọc.

### Bài 7: Đồng bộ search index

Ứng dụng đổi một bài từ **PUBLISHED** sang **PRIVATE** trong DB nguồn, nhưng cập nhật search index bị lỗi mạng. Bài vẫn hiện trong tìm kiếm vài giây.

**Yêu cầu:** Phân tích rủi ro và đề xuất đường khắc phục.

**Gợi ý:** Phải xử lý quyền ở API, có pipeline retry/idempotent, theo dõi lag, khả năng phát lại/rebuild và ưu tiên đồng bộ thao tác thu hồi. Không chỉ dựa vào trạng thái search index để quyết định tiết lộ nội dung.

### Bài 8: Đánh giá relevance

Top 5 kết quả của một truy vấn được gán nhãn nhị phân:

~~~text
relevant = [1, 0, 1, 1, 0]
~~~

**Yêu cầu:** Tính Precision@5 và nêu giới hạn của chỉ số.

**Gợi ý:** Có 3 kết quả liên quan trong 5 vị trí đầu, nên **Precision@5 = 3/5 = 0,6**. Chỉ số không phân biệt việc một tài liệu liên quan xuất hiện ở vị trí 1 hay 4; nếu cần đánh giá thứ hạng có thể dùng NDCG@K.

## 23. Kết luận

Tìm kiếm toàn văn bắt đầu bằng **document**, nhưng sức mạnh đến từ cách biến các trường văn bản thành **token** và xây **inverted index** ánh xạ từ term sang các tài liệu cùng vị trí xuất hiện. Chỉ mục đảo giúp thu hẹp nhanh tập ứng viên; các truy vấn Boolean, phrase, prefix và fuzzy quyết định thế nào là “khớp”.

**Relevance** giải quyết bước tiếp theo: kết quả nào nên xuất hiện trước. TF, DF, IDF và BM25 cung cấp nền tảng xếp hạng dựa trên từ khóa, trong khi field boosting, phrase match, freshness, chất lượng và những tín hiệu khác giúp điều chỉnh theo mục tiêu sản phẩm.

Khi triển khai thực tế, chất lượng phụ thuộc mạnh vào **analyzer phù hợp ngôn ngữ**, ranh giới document, thiết kế quyền, cách đồng bộ với dữ liệu nguồn và khả năng đánh giá bằng truy vấn mẫu. Search engine chuyên biệt rất hữu ích cho bài toán văn bản phức tạp, nhưng nó cần được lựa chọn và vận hành như một thành phần có mục đích rõ ràng, với tiêu chí chất lượng, độ trễ và nhất quán được đo kiểm.

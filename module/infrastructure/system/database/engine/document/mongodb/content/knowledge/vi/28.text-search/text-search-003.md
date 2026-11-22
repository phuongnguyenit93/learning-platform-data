# Text index, $text, điểm textScore và ngôn ngữ hỗ trợ trong MongoDB

## 1. Bài toán và mục tiêu học tập

Một ứng dụng lưu bài viết, sản phẩm hoặc tài liệu kỹ thuật thường cần tìm những document có từ liên quan trong `title`, `description`, `body` hoặc `tags`. Nếu chỉ dùng một điều kiện equality:

~~~javascript
db.articles.find({ title: "MongoDB text search basics" });
~~~

ứng dụng chỉ tìm được những bản ghi có giá trị title đúng theo điều kiện. Nhưng người dùng có thể gõ một vài từ như `mongo search`, tìm một cụm từ trong nội dung, hoặc yêu cầu xếp những kết quả có tiêu đề phù hợp lên trước.

MongoDB có khả năng **text search truyền thống** gồm:

- **Text index:** lập chỉ mục các từ/token trong field kiểu string.
- **`$text` query operator:** thực hiện tìm kiếm theo text index.
- **`$meta:"textScore"`:** truy cập điểm liên quan và dùng để sắp xếp.
- **Ngôn ngữ:** ảnh hưởng tokenization, stop words và stemming.

Bài học thuộc chương **Tìm kiếm văn bản** của module **Database Engine Document MongoDB**, có đề bài **Text index, $text, điểm textScore và ngôn ngữ hỗ trợ**.

Sau bài, bạn có thể:

1. Tạo single-field và multi-field text index, xác minh bằng `getIndexes()`.
2. Phân biệt `$text` với equality, `$regex` và MongoDB Search.
3. Dùng `$search` để tìm từ, nhiều từ, cụm chính xác và loại trừ.
4. Hiểu kết hợp token/OR, stem, stop words và giới hạn substring matching.
5. Dùng `textScore` trong projection, sort và aggregation.
6. Ưu tiên các field bằng `weights` mà không coi score là xác suất.
7. Thiết lập `default_language` và `language_override`, xử lý tài liệu đa ngôn ngữ.
8. Hiểu rõ các ngôn ngữ `$text` hỗ trợ, đặc biệt giới hạn với tiếng Việt.
9. Thiết kế compound text index có equality prefix trong hệ thống nhiều tenant.
10. Biết các giới hạn: chỉ một text index/collection, không dùng `hint()` với `$text`, điều kiện aggregation và collation.
11. Triển khai bằng mongosh/Java Sync Driver, xử lý lỗi và lựa chọn công cụ phù hợp khi yêu cầu nâng cao.

**Thông điệp chính:** Text index là cơ chế **tìm kiếm theo token/ngôn ngữ**, không phải “LIKE bất kỳ chuỗi con nào”. `textScore` là điểm liên quan được tính cho **truy vấn hiện tại**, không tự thể hiện phần trăm đúng và không tự quyết định thứ tự nếu không yêu cầu sort.

## 2. Phân biệt bốn cách tìm kiếm

Xét document:

~~~javascript
{
  _id: 1,
  title: "Wireless mouse for laptop",
  description: "Comfortable Bluetooth mouse for daily work"
}
~~~

| Phương pháp | Ví dụ | Ý nghĩa |
|---|---|---|
| Equality | `{title:"Wireless mouse for laptop"}` | Giá trị field khớp điều kiện |
| Regex | `{title:/mouse/i}` | Khớp biểu thức chính quy trên chuỗi |
| Native text search | `{$text:{$search:"wireless mouse"}}` | Tìm các token đã lập text index theo quy tắc ngôn ngữ |
| MongoDB Search | `$search` aggregation stage | Tìm kiếm chuyên dụng, analyzer, autocomplete/fuzzy, facets… theo deployment hỗ trợ |

### 2.1. Text search khác regex

`$regex` hữu ích cho pattern matching, nhưng không cung cấp stemming/stop words/điểm liên quan như `$text`.

Ngược lại, text index không thay thế được mọi regex. Nếu muốn tìm phần giữa của một mã SKU như `"ABC-123"` bằng substring, text index có thể không đáp ứng vì index được xây theo token, không phải mọi chuỗi con.

### 2.2. Text search khác MongoDB Search

Tên dễ gây nhầm:

~~~javascript
// Native text query: $text chứa tham số $search.
{ $text: { $search: "wireless mouse" } }
~~~

và:

~~~javascript
// MongoDB Search: aggregation stage $search.
{
  $search: {
    index: "product_search",
    text: {
      query: "wireless mouse",
      path: ["title", "description"]
    }
  }
}
~~~

Đây là **hai cơ chế khác nhau**, sử dụng **hai kiểu index khác nhau**. Ví dụ `$search` stage chỉ chạy khi môi trường MongoDB có triển khai MongoDB Search và đã tạo search index tương ứng.

Tài liệu MongoDB hiện khuyến nghị MongoDB Search cho nhu cầu full-text mới và nâng cao; native `$text` vẫn có thể phù hợp bài toán từ khóa đơn giản hoặc môi trường chưa triển khai search index chuyên dụng.

## 3. Tạo bộ dữ liệu thực hành có thể tự chạy

Dùng database riêng trong `mongosh`:

~~~javascript
use text_search_lab
~~~

Các ví dụ giả định collection mới, chưa có dữ liệu. Nếu collection đã tồn tại, kiểm tra trước khi insert/index; không drop production chỉ để làm bài học.

Nạp tài liệu bằng IDs cố định:

~~~javascript
const articles = [
  {
    _id: 1,
    tenantId: "tenant-A",
    status: "published",
    lang: "english",
    title: "MongoDB text search basics",
    body: "Learn to build a text index and search document content.",
    tags: ["database", "tutorial"],
    publishedAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: 2,
    tenantId: "tenant-A",
    status: "published",
    lang: "english",
    title: "Text indexing and relevance",
    body: "Search engines rank articles using text relevance scores.",
    tags: ["search", "database"],
    publishedAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: 3,
    tenantId: "tenant-A",
    status: "published",
    lang: "english",
    title: "Wireless mouse buying guide",
    body: "Choose a comfortable mouse and compare wireless models.",
    tags: ["hardware", "guide"],
    publishedAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: 4,
    tenantId: "tenant-A",
    status: "draft",
    lang: "english",
    title: "MongoDB performance checklist",
    body: "Tune database indexes, projections, and query plans.",
    tags: ["database", "performance"],
    publishedAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: 5,
    tenantId: "tenant-B",
    status: "published",
    lang: "english",
    title: "Database indexing for beginners",
    body: "Database indexes help queries find documents efficiently.",
    tags: ["database", "beginner"],
    publishedAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: 6,
    tenantId: "tenant-A",
    status: "published",
    lang: "none",
    title: "Hướng dẫn tìm kiếm văn bản MongoDB",
    body: "Ví dụ tìm kiếm tiếng Việt có dấu trong dữ liệu.",
    tags: ["mongo", "tìm kiếm"],
    publishedAt: ISODate("2026-10-06T08:00:00Z")
  },
  {
    _id: 7,
    tenantId: "tenant-A",
    status: "published",
    lang: "english",
    title: "MongoDB text search practice",
    body: "Practice keyword searches and matching exact phrases.",
    tags: ["tutorial", "search"],
    publishedAt: ISODate("2026-10-07T08:00:00Z")
  },
  {
    _id: 8,
    tenantId: "tenant-B",
    status: "archived",
    lang: "english",
    title: "Search index migration",
    body: "Plan index rebuilds and application rollouts.",
    tags: ["search", "migration"],
    publishedAt: ISODate("2026-10-08T08:00:00Z")
  }
];

db.articles.insertMany(articles);
~~~

Khi collection thực sự rỗng ban đầu:

- Có **8** articles.
- Tenant-A có 6 articles, tenant-B có 2.
- Tenant-A có 5 published và 1 draft.
- Tenant-A chứa 1 document tiếng Việt được đánh dấu `lang:"none"`.
- Các trường `title`/`body` là String, `tags` là mảng String.

Kiểm tra:

~~~javascript
db.articles.countDocuments({});
db.articles.find(
  {},
  { _id: 1, tenantId: 1, lang: 1, title: 1 }
).sort({ _id: 1 });
~~~

**Lưu ý:** Chạy `insertMany(articles)` lần thứ hai sẽ gặp duplicate `_id` trên collection thường vì ID đã tồn tại. Điều này **không liên quan** text index.

## 4. Tạo một text index trên một field

Một index đơn giản:

~~~javascript
db.articles.createIndex(
  { title: "text" },
  { name: "idx_title_text" }
);
~~~

Sau đó tìm:

~~~javascript
db.articles.find({
  $text: { $search: "MongoDB" }
});
~~~

`$text` chỉ tìm trên những fields có trong text index. Nếu index chỉ có `title`, các từ chỉ xuất hiện trong `body` không được lập chỉ mục cho text query đó.

### 4.1. Kiểm tra text index

~~~javascript
db.articles.getIndexes();
~~~

Có thể thấy index có tên `idx_title_text` và key metadata đặc biệt liên quan text index. Output có thể chứa `weights`, `default_language`, `language_override` và `textIndexVersion` tùy version.

Không suy luận từ tên index rằng index tìm mọi field: hãy xem đúng `weights`/definition.

### 4.2. Tối đa một text index trên mỗi collection

MongoDB cho phép **tối đa một text index** trên mỗi collection. Vì vậy **không** tiếp tục tạo text index thứ hai trên `body` trong collection đã có `idx_title_text`:

~~~javascript
// Không tạo thêm text index độc lập trong cùng collection.
db.articles.createIndex({ body: "text" });
~~~

Nếu cần tìm cả title, body và tags, phải dùng **một text index nhiều field**.

### 4.3. Đổi từ index đơn thành nhiều field

Trong môi trường lab, sau khi đã chạy ví dụ single-field, có thể xóa đúng index lab:

~~~javascript
db.articles.dropIndex("idx_title_text");
~~~

Sau đó tạo index mới ở mục tiếp theo. Đây là thao tác DDL nhạy cảm: không drop text index của ứng dụng production khi chưa có kế hoạch downtime hoặc rollout index thay thế.

## 5. Một text index nhiều field và weights

Ví dụ duy nhất của collection `articles` dùng cho phần lớn bài:

~~~javascript
db.articles.createIndex(
  {
    title: "text",
    body: "text",
    tags: "text"
  },
  {
    name: "idx_article_search",
    default_language: "english",
    language_override: "lang",
    weights: {
      title: 10,
      tags: 4,
      body: 1
    }
  }
);
~~~

Ở đây:

- `title`, `body`, `tags` cùng thuộc **một index**.
- `title` có trọng số 10.
- `tags` có trọng số 4.
- `body` có trọng số 1.
- `default_language:"english"` áp dụng khi document không cung cấp ngôn ngữ override.
- `language_override:"lang"` nghĩa là MongoDB đọc field `lang` trong mỗi document để biết dùng quy tắc ngôn ngữ nào.
- Document `lang:"none"` dùng chế độ không stemming/stop words.

### 5.1. Ý nghĩa của weight

Giả sử từ `MongoDB` xuất hiện ở title của article A, nhưng chỉ xuất hiện ở body của article B. Khi các yếu tố khác tương đương, A có thể được đánh điểm cao hơn vì title được gán weight lớn hơn.

**Weights không có nghĩa title phải khớp mới được tìm thấy.** Body vẫn được lập chỉ mục và vẫn có thể làm document match.

### 5.2. Weights không phải phép nhân điểm cố định dễ dự đoán

Không công bố công thức đơn giản kiểu:

~~~text
score = 10 * số từ khớp ở title
      + 4 * số từ khớp ở tags
      + 1 * số từ khớp ở body
~~~

như một bảo đảm của MongoDB. Server có tính toán relevance riêng, chịu ảnh hưởng tần suất/mức độ khớp và phiên bản. Weights là **tín hiệu tương đối** về tầm quan trọng của field, không phải hợp đồng điểm số chính xác.

### 5.3. Khoảng weight

MongoDB hỗ trợ integer weights từ **1 tới 99.999**. Mặc định nếu không chỉ định weight cho indexed field là 1.

Đừng đặt title weight cực lớn chỉ để “chắc chắn luôn đứng đầu” mà chưa đánh giá kết quả thật. Nếu muốn ưu tiên bắt buộc theo quy tắc kinh doanh, thiết kế một business ranking hoặc query pipeline riêng.

### 5.4. Một mảng String cũng có thể tham gia text index

`tags` trong bộ mẫu là array of Strings:

~~~javascript
tags: ["database", "tutorial"]
~~~

Text index có thể lập chỉ mục các string bên trong mảng. Nhưng nó không tự biến mọi field object/array phức tạp thành text có chất lượng tốt như analyzer chuyên dụng.

## 6. $text: cú pháp cơ bản và điều kiện cần

Text query:

~~~javascript
db.articles.find({
  $text: {
    $search: "database"
  }
});
~~~

Điều kiện:

1. Collection phải có text index hợp lệ.
2. `$search` phải là String.
3. Có thể cấu hình `$language`, `$caseSensitive`, `$diacriticSensitive` theo hỗ trợ.
4. Một query chỉ có **một biểu thức `$text`**.

Cấu trúc đầy đủ:

~~~javascript
db.articles.find({
  $text: {
    $search: "text search",
    $language: "english",
    $caseSensitive: false,
    $diacriticSensitive: false
  }
});
~~~

### 6.1. Không chỉ định field bên trong $text

Không viết:

~~~javascript
// Sai cú pháp/ý nghĩa:
db.articles.find({
  $text: {
    field: "title",
    $search: "MongoDB"
  }
});
~~~

Fields tham gia tìm kiếm được **định nghĩa trong text index**. Muốn chỉ tìm title, cần dùng một collection/index cấu hình tương ứng, hoặc một công cụ search hỗ trợ path-level filtering linh hoạt.

### 6.2. Kết hợp filter thông thường

~~~javascript
db.articles.find({
  tenantId: "tenant-A",
  status: "published",
  $text: { $search: "database" }
});
~~~

Điều kiện tenant/status lọc kết quả của text query. Trong hệ thống đa tenant, backend phải gắn tenant từ session người dùng, không tin vào tenantId tùy ý từ client.

### 6.3. Có thể tìm từ trong những field không được index không?

Giả sử một document có `internalNote:"database migration"` nhưng text index chỉ gồm title/body/tags. `$text` không tìm thông qua internalNote, trừ khi từ cũng xuất hiện trong indexed fields.

## 7. Nhiều từ: mặc định là OR

Một text query:

~~~javascript
db.articles.find({
  $text: {
    $search: "database wireless"
  }
});
~~~

về cơ bản tìm document chứa **một hoặc nhiều** search terms theo quy tắc tokenization/ngôn ngữ. Không hiểu rằng cả hai từ đều bắt buộc có mặt.

Ví dụ với bộ mẫu:

- Articles về database có thể match nhờ `database`.
- Article về wireless mouse có thể match nhờ `wireless`.
- Không cần document nào phải chứa cả hai.

### 7.1. Vì sao không coi dấu cách là AND?

Với native `$text`, một chuỗi gồm các từ không có dấu ngoặc kép không có nghĩa “tất cả các từ”. MongoDB dùng logical **OR** cho các terms trong cách tìm mặc định.

Nếu một màn hình tìm kiếm cần **all terms must match**, không thể mặc nhiên dùng:

~~~javascript
$search: "word1 word2"
~~~

rồi tuyên bố kết quả đã thực hiện AND. Cần thiết kế cụ thể theo ngữ nghĩa MongoDB hoặc chuyển sang MongoDB Search hỗ trợ boolean search rõ ràng hơn.

### 7.2. Stemming làm các từ biến đổi

Với English analyzer, các từ có chung stem có thể được coi liên quan. Ví dụ `index` và `indexing` có thể được ánh xạ theo stemmer; tác động chính xác cần kiểm tra trên dữ liệu thực.

### 7.3. Text search không phải prefix match

Nếu index có từ `blueberry`, tìm `blue` không mặc nhiên match. Text search xử lý từ/token và stem, không lập chỉ mục mọi prefix.

Điều này quan trọng với autocomplete, tên riêng và mã SKU.

## 8. Tìm cụm từ nguyên văn bằng dấu ngoặc kép

Nếu muốn tìm một cụm gồm nhiều từ đúng thứ tự:

~~~javascript
db.articles.find({
  $text: {
    $search: "\"text search\""
  }
});
~~~

Trong JavaScript, chuỗi `"\"text search\""` chứa dấu ngoặc kép bên trong giá trị `$search`.

Ví dụ:

~~~javascript
const phrase = '"text search"';

db.articles.find({
  $text: { $search: phrase }
});
~~~

### 8.1. Khác biệt giữa term OR và phrase

| Search string | Ý nghĩa chính |
|---|---|
| `text search` | Match document có ít nhất một trong các terms |
| `"text search"` | Tìm cụm từ theo thứ tự/phrase semantics |
| `"wireless mouse"` | Tìm cụm wireless mouse |
| `"database index"` | Tìm cụm database index |

Stemming và stop-word rules vẫn có thể tác động tùy ngôn ngữ và version. “Exact phrase” trong `$text` không có nghĩa binary byte-for-byte substring matching như một phép so sánh chuỗi thô.

### 8.2. Trộn phrase và các term riêng lẻ

~~~javascript
db.articles.find({
  $text: {
    $search: "\"wireless mouse\" guide"
  }
});
~~~

Theo tài liệu, khi có quoted multi-word string cùng những terms khác, document cần có **multi-word phrase** để được match. Đừng diễn giải chuỗi này đơn giản thành OR giữa “wireless mouse” và “guide” theo cách bỏ qua phrase.

### 8.3. Quoted phrase không tự bảo đảm đúng field title

Text index trên title/body/tags có thể match cụm từ trong bất kỳ field nào được index theo khả năng query. Muốn khoanh vùng một field riêng biệt với ngôn ngữ query linh hoạt, cân nhắc search stage có `path`.

## 9. Loại trừ bằng dấu trừ

Native text search cho phép phủ định term bằng dấu `-`.

~~~javascript
db.articles.find({
  $text: {
    $search: "mongodb -performance"
  }
});
~~~

Ý tưởng: tìm document chứa từ MongoDB nhưng loại document chứa term performance trong indexed text.

### 9.1. Có ít nhất một term khẳng định

~~~javascript
// Chỉ có phủ định: không match document nào.
db.articles.find({
  $text: {
    $search: "-performance"
  }
});
~~~

Theo MongoDB Manual, một search string chỉ có các negated terms sẽ không match documents.

### 9.2. Negation kết hợp AND

Nếu search là:

~~~text
database -beginner -migration
~~~

những negated terms loại các documents chứa chúng. Đây không phải cú pháp SQL `NOT LIKE` và không giống một boolean parser đầy đủ.

### 9.3. Dấu gạch nối trong từ ghép

Search:

~~~text
pre-market
~~~

không nhất thiết có nghĩa phủ định `market`. MongoDB phân biệt hyphenated words với dấu minus dùng cho negation theo cú pháp/position.

Ví dụ phủ định rõ:

~~~text
pre -market
~~~

Trong ứng dụng, nếu người dùng có thể nhập dấu trừ như một phần của tên sản phẩm, cần xác định UI có muốn nó trở thành toán tử phủ định không.

## 10. textScore: điểm liên quan là gì?

Khi chạy `$text`, MongoDB có thể gán metadata **textScore** cho documents match. Đây là chỉ số liên quan giữa document và search query dựa trên index và các rules.

Không nên hiểu:

~~~text
score = 0.87 => 87% xác suất document đúng
~~~

Không có bảo đảm như vậy. Score dùng để **so sánh mức liên quan trong cùng bối cảnh tìm kiếm**.

### 10.1. Mặc định kết quả không được sắp theo score

~~~javascript
db.articles.find({
  $text: { $search: "mongodb" }
});
~~~

Không được giả định document đầu tiên là phù hợp nhất. Muốn thứ tự relevance, cần sort tường minh.

### 10.2. Project score ra kết quả

~~~javascript
db.articles.find(
  {
    $text: { $search: "mongodb" }
  },
  {
    title: 1,
    tenantId: 1,
    score: { $meta: "textScore" }
  }
);
~~~

Field `score` là giá trị được lấy từ metadata của query, không phải field lưu sẵn trong document.

### 10.3. Sắp xếp theo score

~~~javascript
db.articles.find(
  {
    $text: { $search: "mongodb" }
  },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
});
~~~

MongoDB sắp theo relevance **giảm dần** khi sort bằng textScore metadata.

### 10.4. Thêm tie-breaker

~~~javascript
db.articles.find(
  {
    tenantId: "tenant-A",
    status: "published",
    $text: { $search: "mongodb" }
  },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" },
  _id: 1
});
~~~

`_id` là tie-breaker cho những documents có score ngang nhau, giúp kết quả ổn định hơn khi phân trang và so sánh. Khi dữ liệu/index thay đổi, score và vị trí vẫn có thể thay đổi.

### 10.5. Score có so sánh xuyên query được không?

Không nên dùng score của query `"mongodb"` để so với score của query `"wireless"` như cùng một thang đo chuẩn hóa.

Score có ý nghĩa trong một query/index/dataset cụ thể. Việc thêm tài liệu, đổi weights hoặc đổi index có thể làm ranking thay đổi.

## 11. textScore trong aggregation pipeline

`$text` có thể nằm trong `$match` của aggregation. Nhưng `$match` chứa `$text` phải là **stage đầu tiên** của pipeline.

Ví dụ:

~~~javascript
db.articles.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "published",
      $text: { $search: "mongodb" }
    }
  },
  {
    $addFields: {
      relevance: { $meta: "textScore" }
    }
  },
  {
    $sort: {
      relevance: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      tenantId: 1,
      relevance: 1
    }
  },
  { $limit: 10 }
]);
~~~

`$addFields` đọc metadata sau `$match` đầu tiên, giúp đưa score thành một field trong pipeline.

### 11.1. Sort trực tiếp bằng $meta trong aggregation

Có thể dùng:

~~~javascript
db.articles.aggregate([
  {
    $match: {
      $text: { $search: "search" }
    }
  },
  {
    $sort: {
      score: { $meta: "textScore" }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "textScore" }
    }
  }
]);
~~~

### 11.2. Ví dụ sai: match text ở stage sau

~~~javascript
// Không hợp lệ cho aggregation $text:
db.articles.aggregate([
  { $project: { title: 1, body: 1 } },
  { $match: { $text: { $search: "mongodb" } } }
]);
~~~

`$match` chứa `$text` phải đứng đầu, trước những stage khác.

### 11.3. Không dùng $or hoặc $not bao quanh $text trong pipeline

Ví dụ không hợp lệ:

~~~javascript
db.articles.aggregate([
  {
    $match: {
      $or: [
        { $text: { $search: "mongodb" } },
        { status: "published" }
      ]
    }
  }
]);
~~~

Trong aggregation, text expression không được xuất hiện trong `$or` hoặc `$not`. Thay vào đó, kết hợp những predicates được hỗ trợ với text expression ở cấp thích hợp, hoặc dùng một cơ chế search khác.

### 11.4. Metadata chỉ xuất hiện khi có text query

Không thể lấy `{$meta:"textScore"}` của một document trong pipeline thông thường không có `$text` matching context, rồi kỳ vọng MongoDB tự tính “độ hay” của bài viết.

## 12. Stop words và stemming

Một text index không đơn thuần tách chuỗi bằng dấu cách rồi lưu nguyên tất cả từ.

### 12.1. Stop words

English có những từ phổ biến như:

~~~text
the
and
a
an
~~~

Các từ này có thể bị loại khỏi text index vì ít giúp phân biệt nội dung.

Ví dụ:

~~~javascript
db.englishNotes.insertMany([
  { _id: 1, text: "the cat and the dog" },
  { _id: 2, text: "a blue cat" }
]);

db.englishNotes.createIndex(
  { text: "text" },
  { default_language: "english" }
);
~~~

Tìm riêng `the` có thể không trả kết quả vì đó là stop word theo bộ xử lý English.

### 12.2. Stemming

Một số biến thể hình thái có chung gốc được stemmer xử lý như liên quan. Ví dụ English có thể liên hệ `blueberry` và `blueberries` dựa trên stem.

Nhưng `blue` không phải prefix search tự động của `blueberry`; nó không mặc nhiên match vì chứa một phần từ.

### 12.3. Stop words phụ thuộc ngôn ngữ

Từ `hay` trong Spanish có thể là stop word. Một document Spanish và document English được xử lý theo language-specific rules khác nhau.

Vì vậy, `default_language` và `language_override` không chỉ là trường mô tả UI; chúng thay đổi **những token được lập index**.

### 12.4. Tách từ không phải NLP đa ngôn ngữ tổng quát

Text index không cung cấp mặc định synonym dictionary, lỗi chính tả fuzzy, ngắt từ tiếng Việt tối ưu, autocomplete phức tạp hoặc ranking AI. Nếu ứng dụng cần những khả năng này, cân nhắc MongoDB Search.

## 13. Danh sách ngôn ngữ được $text hỗ trợ

MongoDB Manual liệt kê **15 ngôn ngữ** có quy tắc hỗ trợ cho native `$text`:

| Tên language | Mã | Ghi chú |
|---|---|---|
| `danish` | `da` | Tiếng Đan Mạch |
| `dutch` | `nl` | Tiếng Hà Lan |
| `english` | `en` | Tiếng Anh |
| `finnish` | `fi` | Tiếng Phần Lan |
| `french` | `fr` | Tiếng Pháp |
| `german` | `de` | Tiếng Đức |
| `hungarian` | `hu` | Tiếng Hungary |
| `italian` | `it` | Tiếng Ý |
| `norwegian` | `nb` | Tiếng Na Uy |
| `portuguese` | `pt` | Tiếng Bồ Đào Nha |
| `romanian` | `ro` | Tiếng Romania |
| `russian` | `ru` | Tiếng Nga |
| `spanish` | `es` | Tiếng Tây Ban Nha |
| `swedish` | `sv` | Tiếng Thụy Điển |
| `turkish` | `tr` | Tiếng Thổ Nhĩ Kỳ |

Có thể dùng tên đầy đủ hoặc mã ngôn ngữ được hỗ trợ. Ví dụ:

~~~javascript
db.articles.find({
  $text: {
    $search: "database",
    $language: "english"
  }
});
~~~

hoặc:

~~~javascript
db.articles.find({
  $text: {
    $search: "database",
    $language: "en"
  }
});
~~~

### 13.1. Tiếng Việt không nằm trong 15 ngôn ngữ native này

**Không** viết:

~~~javascript
// Không phải language được native $text hỗ trợ.
db.articles.find({
  $text: {
    $search: "tìm kiếm",
    $language: "vietnamese"
  }
});
~~~

Tương tự, `$language:"vi"` không phải mã ngôn ngữ trong danh sách của native text search này.

### 13.2. Vietnamese text có tìm được bằng $text không?

Có thể sử dụng **`default_language:"none"`** hoặc per-document override `"none"` để lập chỉ mục các token mà không dùng English stemming/stop words.

Ví dụ trong dataset:

~~~javascript
{
  _id: 6,
  lang: "none",
  title: "Hướng dẫn tìm kiếm văn bản MongoDB"
}
~~~

Điều đó **không** có nghĩa MongoDB đã có bộ analyzer hiểu cấu trúc từ ghép tiếng Việt.

Ví dụ `"tìm kiếm"` chứa hai âm tiết tách bằng khoảng trắng nhưng có thể là một đơn vị từ vựng trong tiếng Việt. Native tokenizer không tự thực hiện phân đoạn từ tiếng Việt như một bộ NLP chuyên dụng.

### 13.3. Dấu tiếng Việt và textIndexVersion

Text index version 3 thông thường **không phân biệt dấu** theo cơ chế diacritic-insensitive mặc định. Nhưng không nên diễn giải như “hỗ trợ ngôn ngữ tiếng Việt đầy đủ”.

Case/diacritic normalization và **phân tích ngôn ngữ** là hai vấn đề khác nhau. Bỏ dấu có thể khiến các từ tiếng Việt khác nghĩa trở thành gần nhau.

## 14. default_language khi tạo index

Nếu không khai báo gì, `default_language` của text index là `"english"`.

~~~javascript
db.englishNotes.createIndex(
  { text: "text" }
);
~~~

Có ý nghĩa tương tự chỉ định English default cho documents không có override.

Để lập Spanish index:

~~~javascript
db.spanishNotes.insertMany([
  { _id: 1, text: "La suerte protege a los audaces." },
  { _id: 2, text: "Nada hay más surrealista que la realidad." }
]);

db.spanishNotes.createIndex(
  { text: "text" },
  {
    default_language: "spanish",
    name: "idx_spanish_text"
  }
);
~~~

Một số Spanish stop words và stem rules sẽ được áp dụng. Chẳng hạn từ `hay` có thể bị bỏ qua, trong khi từ mang dấu có thể match tìm kiếm không dấu do diacritic-insensitive semantics của text index version 3.

### 14.1. Khi nên đổi default_language

- Phần lớn documents có cùng một ngôn ngữ hỗ trợ.
- Bạn muốn stemming/stop words đúng ngôn ngữ đó.
- Các documents không có field language override sẽ dùng default này.

### 14.2. Nguy cơ dùng English default cho tiếng Việt

Nếu dữ liệu hoàn toàn là tiếng Việt, English stop words/stemming không phản ánh chính xác tiếng Việt. `none` có thể phù hợp hơn cho tìm kiếm token đơn giản; MongoDB Search với analyzer phù hợp thường tốt hơn cho sản phẩm tìm kiếm tiếng Việt phức tạp.

### 14.3. Đổi index language không giống update metadata

Để thay đổi `default_language` hoặc weights của text index đang có, thường phải lập kế hoạch **drop/recreate text index** phù hợp. Không chỉ update một field cấu hình rồi kỳ vọng index tokens cũ được tự xử lý lại theo ngôn ngữ mới.

## 15. language_override: tài liệu đa ngôn ngữ

Một collection có thể chứa English, Spanish, French và nội dung không muốn stemming.

Ví dụ:

~~~javascript
db.multilingualDocs.insertMany([
  {
    _id: 1,
    lang: "english",
    text: "Blueberries and apples"
  },
  {
    _id: 2,
    lang: "spanish",
    text: "La realidad y la suerte"
  },
  {
    _id: 3,
    lang: "none",
    text: "Tìm kiếm tài liệu tiếng Việt"
  }
]);
~~~

Index:

~~~javascript
db.multilingualDocs.createIndex(
  { text: "text" },
  {
    name: "idx_multilingual_text",
    default_language: "english",
    language_override: "lang"
  }
);
~~~

Với cấu hình trên:

- Document 1 được xử lý với English.
- Document 2 được xử lý với Spanish.
- Document 3 được xử lý với `none`.
- Document thiếu `lang` sẽ dùng English default.

### 15.1. language_override là tên field, không phải giá trị ngôn ngữ

~~~javascript
language_override: "lang"
~~~

nghĩa là tìm field `lang` trong document. Không có nghĩa dùng language có tên `lang`.

### 15.2. Nếu không đặt language_override

Tên field override mặc định là `language`.

Một document:

~~~javascript
{
  title: "Example",
  language: "spanish"
}
~~~

có thể được text index xử lý theo Spanish dù bạn không khai báo `language_override`, nếu text index sử dụng default field này.

### 15.3. Tránh vô tình dùng field language cho mục đích khác

Nếu business document có `language:"unknown"` hay giá trị không phải ngôn ngữ hợp lệ, text index có thể gặp lỗi khi lập index.

Cách an toàn là dùng field riêng `textLanguage`/`lang` chứa những giá trị được kiểm soát, và đặt `language_override` tương ứng.

### 15.4. Query $language và index-time language có liên quan nhưng khác vai trò

- **Index time:** quy tắc ngôn ngữ xác định những tokens được lập chỉ mục của mỗi document.
- **Query time:** `$language` xác định cách phân tích search terms của query.

Đổi `$language` ở query **không** viết lại index data đã được xây với một ngôn ngữ khác. Để có kết quả đáng tin cậy, phải thiết kế index-time/document language đúng ngay từ đầu.

## 16. Chế độ language none

`none` là một giá trị đặc biệt:

~~~javascript
db.plainTokens.insertMany([
  { _id: 1, text: "the blue berries" },
  { _id: 2, text: "and blueberry" }
]);

db.plainTokens.createIndex(
  { text: "text" },
  {
    name: "idx_plain_tokens",
    default_language: "none"
  }
);
~~~

Đặc điểm:

- Không dùng stemmer theo language-specific rules.
- Không loại stop words theo language-specific list.
- Vẫn token hóa chuỗi, không biến text index thành một exact-substring index.
- Không tự có Unicode word segmentation tiếng Việt nâng cao.

### 16.1. Một ví dụ dễ nhận biết

Với English default, `the` có thể bị bỏ khỏi index; với `none`, nó vẫn được index như một token.

~~~javascript
db.plainTokens.find({
  $text: {
    $search: "the",
    $language: "none"
  }
});
~~~

### 16.2. none không có nghĩa caseSensitive/diacriticSensitive được bật

`none` kiểm soát stemming/stop words. Sensitivity có những tùy chọn riêng trong `$text`, và behavior còn phụ thuộc text index version.

Không suy luận rằng `default_language:"none"` buộc tiếng Việt phải khớp đúng mọi dấu/chữ hoa.

### 16.3. Khi nào none phù hợp?

- Các mã định danh dạng từ ngắn mà không muốn English stemming.
- Nội dung thuộc ngôn ngữ không có native stemmer.
- Các bài toán keyword đơn giản coi mỗi token là đơn vị có ý nghĩa.
- Dữ liệu trộn nhiều ngôn ngữ mà không thể chọn analyzer phù hợp, khi hiểu rõ giới hạn.

## 17. Case sensitivity

Text index version 3 mặc định case-insensitive.

Ví dụ:

~~~javascript
db.articles.find({
  $text: {
    $search: "MongoDB"
  }
});
~~~

Có thể match token có cách viết hoa/thường khác nhau theo index semantics.

Bật case sensitivity:

~~~javascript
db.articles.find({
  $text: {
    $search: "MongoDB",
    $caseSensitive: true
  }
});
~~~

### 17.1. Tác động hiệu năng

Khi index vốn case-insensitive, MongoDB có thể cần dùng index lấy candidate matches rồi lọc lại theo case. Vì vậy bật `$caseSensitive:true` có thể tăng chi phí xử lý.

### 17.2. Case sensitivity không phải fuzzy matching

`$caseSensitive:true` không cung cấp typo correction, synonyms hoặc autocomplete. Nó chỉ kiểm soát một khía cạnh của so khớp.

### 17.3. Không nhầm với collation

Text index chỉ hỗ trợ simple/binary collation đối với index configuration, nhưng text search dùng case/diacritic handling riêng của text index version. Đó không phải hai phát biểu mâu thuẫn.

## 18. Diacritic sensitivity và văn bản có dấu

Text index version 3 mặc định diacritic-insensitive. Ví dụ các ký tự `é`, `ê` và `e` có thể được xử lý không phân biệt dấu ở mức index.

Để yêu cầu phân biệt dấu:

~~~javascript
db.articles.find({
  $text: {
    $search: "café",
    $diacriticSensitive: true
  }
});
~~~

### 18.1. Tại sao cần cân nhắc với tiếng Việt?

Tiếng Việt có các từ khác nghĩa khi thay dấu, chẳng hạn một chuỗi không dấu có thể khớp nhiều khả năng. Tìm kiếm bỏ dấu có thể tăng recall nhưng làm giảm precision.

Nếu ứng dụng cần matching chính xác theo dấu, có thể sử dụng `$diacriticSensitive:true` với text index version 3. Nhưng điều đó vẫn không sửa được hạn chế tokenizer/stemming dành cho tiếng Việt.

### 18.2. Version cũ khác thế nào?

Text index version 3 mặc định diacritic-insensitive, trong khi các phiên bản text index cũ có behavior khác (các phiên bản trước nhạy dấu).

Không lấy kết quả kiểm thử trên collection cũ với `textIndexVersion:2` làm chuẩn cho text index version 3 mới.

### 18.3. Có thể tốn thêm chi phí

Tương tự case-sensitive search, yêu cầu diacritic-sensitive khi index vốn insensitive có thể cần lọc bổ sung và làm query chậm hơn.

## 19. textIndexVersion và khả năng tương thích

MongoDB từng có nhiều text index versions:

| Version | Bối cảnh lịch sử |
|---|---|
| v1 | Giới thiệu trong MongoDB 2.4 |
| v2 | Giới thiệu trong MongoDB 2.6 |
| v3 | Giới thiệu trong MongoDB 3.2, là default trên những phiên bản hiện đại |

Tài liệu MongoDB khuyến nghị dùng default text index version nếu không có lý do tương thích rõ ràng.

Ví dụ không nên tùy tiện làm:

~~~javascript
db.articles.createIndex(
  { title: "text" },
  { textIndexVersion: 1 }
);
~~~

trên deployment hiện đại.

### 19.1. Vì sao version có ý nghĩa?

Version có thể ảnh hưởng token normalization, case/diacritic handling và cách index hoạt động. Khi nâng server, không tự mặc định một index được tạo từ nhiều năm trước có hoàn toàn giống index mới trong mọi khía cạnh.

### 19.2. Kiểm tra

~~~javascript
db.articles.getIndexes();
~~~

Tìm `textIndexVersion` ở index definition và đối chiếu MongoDB Manual đúng version server.

## 20. Compound text index: kết hợp equality filter với text

Một collection lớn có nhiều tenants và trạng thái published/draft. Nếu phần lớn query đều theo `tenantId` và `status`, có thể cân nhắc compound text index với equality prefix.

**Quan trọng:** Collection `articles` đã có text index. Không tạo **text index thứ hai** trên chính nó. Ta dùng collection lab khác:

~~~javascript
use text_search_lab

db.createCollection("tenantDocs");

db.tenantDocs.insertMany([
  {
    _id: 1,
    tenantId: "tenant-A",
    status: "published",
    title: "MongoDB index design",
    body: "Create efficient search indexes"
  },
  {
    _id: 2,
    tenantId: "tenant-A",
    status: "draft",
    title: "MongoDB text search draft",
    body: "Draft documentation"
  },
  {
    _id: 3,
    tenantId: "tenant-B",
    status: "published",
    title: "Search engines overview",
    body: "Compare text search strategies"
  }
]);
~~~

Tạo **một** compound text index:

~~~javascript
db.tenantDocs.createIndex(
  {
    tenantId: 1,
    status: 1,
    title: "text",
    body: "text"
  },
  {
    name: "idx_tenant_status_text",
    default_language: "english"
  }
);
~~~

### 20.1. Bắt buộc equality trên prefix đứng trước text fields

Query:

~~~javascript
db.tenantDocs.find({
  tenantId: "tenant-A",
  status: "published",
  $text: {
    $search: "mongodb"
  }
});
~~~

có equality cho cả `tenantId` và `status` đứng trước các text keys trong compound index.

Nếu thiếu `status`:

~~~javascript
// Có thể không thể sử dụng compound text index đúng yêu cầu.
db.tenantDocs.find({
  tenantId: "tenant-A",
  $text: { $search: "mongodb" }
});
~~~

theo restriction của MongoDB: `$text` query phải có **equality conditions cho mọi index keys đứng trước text key**.

### 20.2. Tại sao compound text index hữu ích?

Ví dụ 20 triệu documents thuộc nhiều tenants. Nếu business query luôn giới hạn tenant và trạng thái trước khi tìm text, equality prefix giúp giảm lượng text index entries phải xét.

### 20.3. Hạn chế thiết kế prefix

Nếu một ứng dụng còn nhiều màn hình muốn tìm ở **mọi status** hoặc **mọi tenant**, index có `tenantId,status` ở trước text có thể không đáp ứng những query đó.

Đừng chọn compound prefix chỉ dựa theo một endpoint mà quên các endpoints khác. Một collection chỉ có một text index nên đây là quyết định thiết kế quan trọng.

### 20.4. Các text keys phải liền nhau

Khi tạo compound index nhiều text fields, những text keys phải đặt **liền nhau** trong index definition.

Ví dụ nên:

~~~javascript
{
  tenantId: 1,
  title: "text",
  body: "text",
  publishedAt: -1
}
~~~

Không chèn key thường vào giữa hai text fields:

~~~javascript
// Không hợp lệ vì hai text keys không liền nhau.
{
  tenantId: 1,
  title: "text",
  publishedAt: -1,
  body: "text"
}
~~~

### 20.5. Không phối hợp tùy ý với special index khác

Compound text index không được ghép tùy ý với special types như geospatial hoặc multikey index fields khác theo MongoDB restrictions.

Nếu bạn cần query kết hợp geospatial + full-text nâng cao, cân nhắc MongoDB Search hoặc thiết kế query riêng, không cố nhét tất cả vào một compound native text index.

## 21. Text index có hỗ trợ sort như B-tree thông thường không?

**Không.** MongoDB Manual nêu text indexes không cải thiện hiệu suất sort, kể cả compound text indexes.

Điều đó không có nghĩa bạn không thể gọi `sort()`:

~~~javascript
db.articles.find({
  $text: { $search: "database" }
}).sort({ publishedAt: -1 });
~~~

Nhưng không nên giả định text index sẽ cung cấp sẵn thứ tự `publishedAt` để query không cần sort work.

### 21.1. Sort textScore là relevance sort

~~~javascript
db.articles.find(
  { $text: { $search: "database" } },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({ score: { $meta: "textScore" } });
~~~

### 21.2. Sort field thường là nghiệp vụ khác

Một ứng dụng có thể cung cấp hai chế độ:

- **Relevance:** sort theo textScore.
- **Latest:** sort theo publishedAt.

Không xem hai chế độ có cùng query plan hoặc cùng chi phí. Kết hợp relevance và recency cần có định nghĩa ranking rõ.

### 21.3. Dùng explain

~~~javascript
db.articles.find({
  $text: {
    $search: "database"
  }
}).sort({
  publishedAt: -1
}).explain("executionStats");
~~~

Theo phiên bản MongoDB, plan có thể có những stages liên quan text index và sort; đừng giả định mọi kết quả được xuất ra theo index order.

## 22. Wildcard text index khác wildcard index thường

MongoDB có thể tạo wildcard **text** index:

~~~javascript
db.anyFieldDocs.insertMany([
  { _id: 1, title: "Database guide", details: "Index tuning" },
  { _id: 2, summary: "Wireless mouse", notes: "Bluetooth accessories" }
]);

db.anyFieldDocs.createIndex(
  { "$**": "text" },
  {
    name: "idx_all_strings_text",
    default_language: "english"
  }
);
~~~

Index này hướng tới string fields có trong documents, theo cơ chế wildcard text index.

**Phân biệt:**

~~~javascript
{ "$**": "text" }  // Wildcard TEXT index.
{ "$**": 1 }       // Wildcard index kiểu thường.
~~~

Index `{"$**":1}` không tự hỗ trợ `$text`.

### 22.1. Rủi ro khi text index mọi string fields

- Index có thể lớn.
- Index hóa những fields không liên quan như status, codes hoặc nội dung ít giá trị.
- Có thể làm lộ dữ liệu nội bộ trong kết quả nếu không kiểm soát projection/quyền.
- Khó đặt weights hợp lý cho field schema linh hoạt.
- Tăng chi phí ghi khi document thay đổi.

Chỉ chọn wildcard text index khi có lý do rõ ràng và đã đo workload. Với schema ổn định, text index đích danh fields thường dễ kiểm soát hơn.

### 22.2. Vẫn chỉ một text index trên collection

Wildcard text index cũng chiếm quota **một text index per collection**. Không thể thêm một text index độc lập trên title sau đó.

## 23. Những giới hạn quan trọng của $text

| Giới hạn | Ý nghĩa thực tế |
|---|---|
| Một text index/collection | Muốn tìm nhiều fields phải gộp trong một index |
| Một biểu thức `$text`/query | Không đặt hai text predicates độc lập |
| `$text` không trong `$nor` | Không hỗ trợ loại boolean này |
| `$text` không trong `$elemMatch` | Không tìm riêng phần tử mảng theo cách đó |
| `$text` + `hint()` | Không được chỉ định hint cho text query |
| `$text` + `$natural` sort | Không được dùng |
| Các `$or` clauses | Phải thỏa điều kiện index được MongoDB quy định |
| `$text` + toán tử cần special index khác | Không tùy ý dùng với `$near` |
| Views | Không hỗ trợ `$text` |
| Aggregation | `$match` chứa `$text` phải đầu tiên |
| Aggregation `$or`/`$not` | Không bao text expression trong những cấu trúc đó |
| Text index sort | Không tối ưu sort thường |
| Compound prefix | Bắt buộc equality trên keys đứng trước text |
| Collation | Text index yêu cầu simple/binary collation |

### 23.1. Ví dụ không dùng hint

~~~javascript
// Không dùng hint() với $text.
db.articles.find({
  $text: { $search: "mongodb" }
}).hint("idx_article_search");
~~~

Khi cần tối ưu, đánh giá index design và query shape thay vì cố ép hint cho text query.

### 23.2. Một $text expression không có nghĩa một từ

Bạn có thể tìm nhiều terms trong một `$text`:

~~~javascript
db.articles.find({
  $text: { $search: "database mongodb" }
});
~~~

Nhưng không đặt hai `$text` expressions độc lập:

~~~javascript
// Sai mô hình:
{
  $and: [
    { $text: { $search: "database" } },
    { $text: { $search: "mongodb" } }
  ]
}
~~~

### 23.3. $text không phải giải pháp chung cho text + location

Không kết hợp tùy tiện `$text` với `$near` yêu cầu geospatial special index. Một tính năng “cửa hàng gần tôi có tên liên quan…” cần xem lựa chọn search/geospatial thích hợp.

### 23.4. Collation và text case-insensitive không giống nhau

Text indexes dùng simple collation trong cấu hình index. Nhưng `$text` có case/diacritic-insensitive behavior theo text index version. Không tự kết luận rằng index simple collation nghĩa text search luôn phân biệt chữ hoa.

## 24. Collation của text index

Nếu collection được tạo với một non-simple collation:

~~~javascript
db.createCollection("localeDocs", {
  collation: { locale: "en" }
});
~~~

khi tạo text index cần chỉ rõ simple collation:

~~~javascript
db.localeDocs.createIndex(
  { title: "text" },
  {
    name: "idx_locale_title_text",
    collation: { locale: "simple" }
  }
);
~~~

### 24.1. Vì sao?

Text indexes không hỗ trợ collation kiểu locale-based như một B-tree string index thông thường. Chúng dùng text tokenization/normalization semantics riêng.

### 24.2. Có thể search tiếng Việt với collation vi không?

Không thể dùng `collation:{locale:"vi"}` trên text index để bật một Vietnamese stemmer đầy đủ.

Nếu cần NLP cho tiếng Việt, cân nhắc search analyzer/collection thiết kế riêng, có test thực tế về tokenization và dấu.

## 25. Text index không phải unique constraint

~~~javascript
db.articles.createIndex(
  { title: "text" }
);
~~~

không có ý nghĩa `title` duy nhất.

Nếu hai documents có cùng title, chúng vẫn có thể cùng tồn tại. Nếu nghiệp vụ yêu cầu slug hoặc document code unique, dùng unique index B-tree riêng phù hợp:

~~~javascript
db.articles.createIndex(
  { tenantId: 1, slug: 1 },
  { unique: true }
);
~~~

Đây là một index **khác loại**; nó không chiếm quota text index, và bảo đảm uniqueness theo cặp tenantId/slug.

### 25.1. Text search không thay data validation

Các document có field body là Number/Date thay vì String không tự được biến thành nội dung searchable như String. Nên kiểm soát schema và kiểu dữ liệu khi ingest.

### 25.2. Text search không thay authorization

Nếu một document là draft hoặc thuộc tenant khác, nó vẫn có thể match text index. Backend phải filter theo quyền:

~~~javascript
db.articles.find({
  tenantId: authenticatedTenantId,
  status: "published",
  $text: { $search: queryFromUser }
});
~~~

Ở đây `authenticatedTenantId` và `queryFromUser` là các biến của ứng dụng, không phải giá trị lấy trực tiếp từ một request thiếu xác thực.

## 26. Phân trang kết quả tìm kiếm

Một API:

~~~text
GET /articles?q=mongodb&page=1&pageSize=10
~~~

có thể dùng:

~~~javascript
const page = 1;
const pageSize = 10;

db.articles.find(
  {
    tenantId: "tenant-A",
    status: "published",
    $text: { $search: "mongodb" }
  },
  {
    title: 1,
    publishedAt: 1,
    score: { $meta: "textScore" }
  }
)
.sort({
  score: { $meta: "textScore" },
  _id: 1
})
.skip((page - 1) * pageSize)
.limit(pageSize);
~~~

### 26.1. Score tie-breaker

Khi nhiều documents có cùng relevance score, thêm `_id` giúp thứ tự ổn định hơn trong cùng trạng thái dữ liệu.

### 26.2. Kết quả vẫn có thể thay đổi giữa requests

Nếu dữ liệu hoặc text index thay đổi, score có thể thay đổi. Hai HTTP requests chạy lần lượt không tự chia sẻ snapshot.

Không hứa infinite-scroll luôn nhìn một tập kết quả bất biến chỉ nhờ sort textScore.

### 26.3. Skip ở trang sâu có chi phí

Truy vấn `skip(100000)` vẫn có thể cần bỏ qua rất nhiều kết quả. Nếu ứng dụng search lớn, đánh giá pagination strategy, query limits và MongoDB Search capabilities phù hợp.

### 26.4. Giới hạn đầu vào search

Cần hạn chế `q` quá dài, số lượng terms bất thường, độ sâu pagination và thời gian query. Trả kết quả rỗng khác lỗi timeout; không biến lỗi server thành “không tìm thấy”.

## 27. Java Sync Driver: tạo text index

MongoDB Java Sync Driver hỗ trợ `Indexes.text()` và `IndexOptions`.

Ví dụ giả định `client` là `MongoClient` đã kết nối:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

MongoDatabase database =
    client.getDatabase("text_search_lab");

MongoCollection<Document> articles =
    database.getCollection("articles");

// Tạo index chỉ nếu collection CHƯA có text index khác.
String indexName = articles.createIndex(
    Indexes.compoundIndex(
        Indexes.text("title"),
        Indexes.text("body"),
        Indexes.text("tags")
    ),
    new IndexOptions()
        .name("idx_article_search")
        .defaultLanguage("english")
        .languageOverride("lang")
        .weights(
            new Document("title", 10)
                .append("tags", 4)
                .append("body", 1)
        )
);

System.out.println(indexName);
~~~

**Quan trọng:** Bài mongosh mục 5 đã tạo `idx_article_search`. Nếu cùng collection đã có index tương ứng, bạn không cần tạo lại. Nếu có text index khác không cùng options, MongoDB có thể trả `IndexOptionsConflict` hoặc lỗi tương đương.

### 27.1. Chỉ một text index

Không làm:

~~~java
articles.createIndex(Indexes.text("title"));
articles.createIndex(Indexes.text("body"));
~~~

như thể hai index riêng biệt sẽ cùng tồn tại.

Dùng một compound text index có các fields cần tìm.

### 27.2. Java index options là cấu hình server

Driver gửi index definition tới MongoDB. Quy tắc một text index, ngôn ngữ hỗ trợ, collation và weights do server thực thi, không phải driver tự bỏ qua khi không hợp lệ.

## 28. Java Sync Driver: tìm kiếm và lấy textScore

Tạo filter text bằng `Filters.text`:

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

Bson filter = Filters.and(
    Filters.eq("tenantId", "tenant-A"),
    Filters.eq("status", "published"),
    Filters.text("mongodb")
);

Bson projection = Projections.fields(
    Projections.include("title", "tenantId"),
    Projections.metaTextScore("score")
);

Bson relevanceSort = Sorts.metaTextScore("score");

for (Document doc : articles.find(filter)
        .projection(projection)
        .sort(relevanceSort)
        .limit(10)) {
    System.out.println(doc.toJson());
}
~~~

Đây là cách Java Driver thực hiện:

- `$text:{$search:"mongodb"}`.
- Projection `score:{$meta:"textScore"}`.
- Sort theo relevance metadata.

### 28.1. Search nhiều từ

~~~java
Bson searchAnyTerm = Filters.text("mongodb database");
~~~

Mặc định là OR trên các terms, không phải “phải có cả hai”.

### 28.2. Search phrase

~~~java
Bson phrase = Filters.text("\"text search\"");
~~~

### 28.3. Search phủ định

~~~java
Bson notPerformance = Filters.text("mongodb -performance");
~~~

### 28.4. Chỉ định language/case/diacritics

~~~java
import com.mongodb.client.model.TextSearchOptions;

TextSearchOptions options = new TextSearchOptions()
    .language("english")
    .caseSensitive(false)
    .diacriticSensitive(false);

Bson filter = Filters.text("database", options);
~~~

Không dùng `language("vietnamese")` nếu server native `$text` không hỗ trợ.

### 28.5. Java sort tie-breaker

Nếu cần thứ tự ổn định:

~~~java
Bson sort = Sorts.orderBy(
    Sorts.metaTextScore("score"),
    Sorts.ascending("_id")
);
~~~

Lưu ý trong Java Driver/MongoDB 4.4+, tên field truyền vào `Sorts.metaTextScore("score")` trong sort có thể bị MongoDB bỏ qua ở việc diễn giải sort metadata; đây là API builder cho `$meta`, không phải yêu cầu sort theo field stored `score`.

## 29. Java aggregation với textScore

Nếu cần pipeline:

~~~java
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import java.util.List;

List<Bson> pipeline = List.of(
    Aggregates.match(
        Filters.and(
            Filters.eq("tenantId", "tenant-A"),
            Filters.text("mongodb")
        )
    ),
    new Document("$addFields",
        new Document("relevance",
            new Document("$meta", "textScore")
        )
    ),
    Aggregates.sort(
        Sorts.orderBy(
            Sorts.descending("relevance"),
            Sorts.ascending("_id")
        )
    ),
    Aggregates.project(
        Projections.fields(
            Projections.include("title", "relevance")
        )
    ),
    Aggregates.limit(10)
);

articles.aggregate(pipeline)
    .forEach(doc -> System.out.println(doc.toJson()));
~~~

`Aggregates.match(...)` chứa text query là **đầu pipeline**, đáp ứng hạn chế MongoDB.

**Không dùng `$text` như một stage aggregation riêng.** Nó là **query operator bên trong `$match`**.

## 30. Theo dõi performance bằng explain

Trên collection có nhiều dữ liệu:

~~~javascript
db.articles.find({
  tenantId: "tenant-A",
  status: "published",
  $text: { $search: "database" }
})
.explain("executionStats");
~~~

Tùy phiên bản/query engine, plan có thể hiển thị stages như text matching, index scans, filtering và sorting.

### 30.1. Những metrics nên xem

- `nReturned`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- `executionTimeMillis` (đặt trong bối cảnh môi trường).
- Có blocking sort hay không.
- Số documents bị filter vì tenant/status sau text match.
- Query có compound equality prefix phù hợp không.

### 30.2. Một từ quá phổ biến có thể tốn kém

Search term xuất hiện trong hàng triệu documents có thể tạo nhiều candidate matches. Giới hạn `limit` chỉ giới hạn số kết quả trả về, không nhất thiết tránh mọi công việc chọn/ranking candidates.

### 30.3. Text index có chi phí bảo trì

Mỗi lần insert/update field indexed, text index có thể cần cập nhật tokens. Index lớn làm tăng storage và chi phí write, đặc biệt khi body rất dài.

### 30.4. Thay weights là thay ranking

Nếu A/B test đổi weight title từ 10 lên 20, thứ tự kết quả có thể thay đổi. Không kết luận query “nhanh hơn” chỉ dựa vào score cao hơn; đo execution performance riêng.

### 30.5. Memory và phiên bản mới

Một số phiên bản MongoDB mới (ví dụ thay đổi từ 8.3) có giới hạn bộ nhớ cho stage `TextOr`, với hành vi `allowDiskUse` khi vượt ngưỡng. Nếu deployment gặp lỗi memory khi sort/rank nhiều kết quả, hãy đối chiếu tài liệu **đúng phiên bản**, không chỉ tăng RAM tùy ý.

## 31. Tìm kiếm tiếng Việt trong sản phẩm thực tế

Tiếng Việt có những yêu cầu đặc thù:

- Một từ vựng có thể gồm nhiều âm tiết ngăn bởi khoảng trắng, ví dụ `"tìm kiếm"`.
- Có nhiều thanh điệu và nguyên âm có dấu.
- Người dùng có thể gõ không dấu.
- Có tên riêng, địa danh, cách viết tắt, mã sản phẩm và từ mượn.
- Có nhu cầu sửa lỗi chính tả, prefix/autocomplete và synonyms.

Native `$text` không có Vietnamese language analyzer trong danh sách hỗ trợ. Dùng `none` có thể phù hợp **keyword search đơn giản**, nhưng không tương đương hệ thống tìm kiếm tiếng Việt chuyên dụng.

### 31.1. Một ví dụ chỉ để tìm token

~~~javascript
db.articles.find({
  tenantId: "tenant-A",
  $text: {
    $search: "MongoDB",
    $language: "none"
  }
});
~~~

Tìm một token như MongoDB dễ diễn giải hơn tìm từ ghép có phân đoạn tiếng Việt.

### 31.2. Đừng xem bỏ dấu là đủ

Từ không dấu có thể tương ứng nhiều từ có nghĩa khác nhau. Nếu không có analyzer phù hợp, độ chính xác và độ bao phủ dễ giảm.

### 31.3. Khi dùng MongoDB Search

Nếu ứng dụng cần:

- Analyzer/custom tokenizer được cấu hình rõ.
- Fuzzy search.
- Autocomplete.
- Synonym maps.
- Highlighting.
- Facet và scoring/ranking nâng cao.
- Hybrid keyword/semantic search.

hãy đánh giá MongoDB Search (aggregation `$search`) trên deployment hỗ trợ. Nó là công cụ khác native text index và cần cấu hình search index riêng.

### 31.4. Có phải MongoDB Search tự hiểu tiếng Việt hoàn hảo?

Không mặc định. Cần xem những analyzers/token filters được hỗ trợ, cấu hình và test tiếng Việt thật, đặc biệt với dấu, từ ghép và tên riêng. Một công cụ search nâng cao không thay thế việc đánh giá chất lượng kết quả bằng dữ liệu người dùng.

## 32. Bảo mật và chất lượng dữ liệu tìm kiếm

### 32.1. Không cho user chọn tenant tùy ý

Query đúng:

~~~javascript
db.articles.find({
  tenantId: tenantFromAuthenticatedSession,
  status: "published",
  $text: { $search: textFromUser }
});
~~~

Tầng ứng dụng phải lấy `tenantFromAuthenticatedSession` từ xác thực, không từ query string user tự chọn.

### 32.2. Search string có syntax riêng

Người dùng gõ:

~~~text
performance -mongodb
~~~

thì dấu trừ có thể bị phân tích thành negation. Nếu UI chỉ muốn tìm literal string, cần xử lý/giải thích syntax, không dùng trực tiếp mọi ký tự theo cách làm thay đổi ý định.

### 32.3. Giới hạn request

- Maximum search length.
- Page size và số trang hợp lý.
- Query deadlines/`maxTimeMS`.
- Rate limiting theo user/tenant.
- Projection tránh trả fields nhạy cảm.
- Log tìm kiếm theo chính sách dữ liệu cá nhân.

### 32.4. Chất lượng nội dung

Nếu documents chứa HTML, markup, text bị lỗi encoding hoặc token spam, text index có thể lập chỉ mục nhiều từ không có giá trị. Nên chuẩn hóa nội dung trước khi ghi, tách title/body/tags và kiểm soát spam theo business rules.

## 33. MongoDB Compass: quan sát text index và score

Compass có thể tạo indexes và chạy queries/aggregations theo khả năng từng version. Quy trình thực hành:

1. Kết nối tới database lab.
2. Mở collection `articles`.
3. Xem tab **Indexes**; tìm `idx_article_search`.
4. Kiểm tra title/body/tags có phải text fields.
5. Trong query filter, nhập `{$text:{$search:"mongodb"}}`.
6. Dùng projection `{title:1,score:{$meta:"textScore"}}` nếu UI hỗ trợ.
7. Dùng sort `{score:{$meta:"textScore"}}`.
8. Thử aggregation với `$match` text đứng đầu.
9. So sánh search `"mongodb database"` với `"text search"` có dấu quote.
10. Nếu UI không expose đầy đủ options, dùng mongosh để kiểm chứng command.

**Không** kết luận rằng Compass đã sắp theo relevance chỉ vì danh sách documents nhìn có vẻ hợp lý; xác minh sort specification.

## 34. Lỗi và hiểu nhầm thường gặp

| Triệu chứng/nhận định | Nguyên nhân | Cách khắc phục |
|---|---|---|
| “Không tạo được text index thứ hai” | Một text index/collection | Gộp các fields vào một index |
| “$text không tìm được từ trong body” | Body không có trong text index | Chọn fields indexed |
| “Gõ hai từ phải có cả hai” | `$search` terms mặc định OR | Dùng semantics khác theo yêu cầu |
| “Tìm blue khớp blueberry” | Không phải prefix search | Dùng full term hoặc autocomplete search |
| “Không có score trong kết quả” | Chưa project metadata | `{$meta:"textScore"}` |
| “Kết quả chưa được xếp theo score” | `$text` không tự sort | Sort `$meta:"textScore"` |
| “Score 0.75 nghĩa 75% đúng” | Không phải xác suất | Chỉ so sánh relevance tương đối |
| “Điểm giữa hai query so trực tiếp được” | Không có chuẩn hóa toàn cục | So trong cùng query/index |
| “Weights 10 thì score luôn gấp 10” | Score có thuật toán riêng | Đo ranking trên corpus thực |
| “the không tìm thấy trong English index” | Stop word | Test `none` nếu cần token ấy |
| “$language vi được hỗ trợ” | Native danh sách không có Vietnamese | `none` hoặc MongoDB Search |
| “none là Vietnamese analyzer” | Không stemming/stop words, không NLP | Dùng analyzer phù hợp |
| “Tôi đổi $language query mà index tự đổi token” | Index-time analyzer đã được áp | Rebuild index khi cần |
| “Tìm có dấu phải khớp chính xác theo dấu” | v3 insensitive mặc định | `$diacriticSensitive:true` nếu phù hợp |
| “Case-sensitive search không tốn thêm phí” | Có thể thêm filter | Đo query latency |
| “Regex và $text là một” | Khác semantics và loại index | Chọn công cụ theo use case |
| “$text trong aggregation đứng sau project” | Text match phải đầu pipeline | Đưa `$match` text lên đầu |
| “$text dùng chung với hint” | Bị hạn chế | Bỏ hint, tối ưu index design |
| “Compound text index không cần equality prefix” | Keys trước text phải có equality | Bổ sung predicates hoặc đổi index |
| “Text index tự tối ưu sort mới nhất” | Text indexes không tối ưu sort | Đo sort plan, chọn architecture |
| “Text index tìm được mọi field” | Chỉ fields được index | Kiểm tra index definition |
| “Wildcard index $**:1 hỗ trợ $text” | Khác wildcard text | Dùng `{"$**":"text"}` nếu phù hợp |
| “Text search giữ quyền tenant” | Không tự làm authorization | Filter tenant đúng quyền |
| “Một $text index đủ cho fuzzy/autocomplete” | Native text có giới hạn | MongoDB Search |
| “Đổi weights không cần rebuild” | Là index options | Lập kế hoạch tái tạo index |
| “Có thể dùng textScore khi không có $text” | Không có text metadata | Chỉ dùng trong text query context |

## 35. Bài tập thực hành

Các bài sử dụng database `text_search_lab`. Bài thay đổi index cần chạy trên collection lab riêng hoặc thực hiện theo thứ tự trong bài, tránh xóa index production.

### Bài 1 — Tạo text index đơn

Tạo text index chỉ cho `title` trên collection mới. Truy vấn `$text` tìm `"MongoDB"`.

**Hỏi:** Vì sao một từ chỉ xuất hiện trong body không match qua index title?

### Bài 2 — Một text index nhiều field

Tạo duy nhất một text index gồm `title`, `body`, `tags`. Vì sao không nên tạo ba text indexes độc lập?

### Bài 3 — OR terms

~~~javascript
{ $text: { $search: "database wireless" } }
~~~

**Hỏi:** Điều kiện match mặc định là OR hay AND? Giải thích dựa trên bộ dữ liệu.

### Bài 4 — Phrase

Viết query tìm cụm `"text search"`. So sánh với tìm hai terms không có dấu quote.

### Bài 5 — Negation

~~~javascript
{ $text: { $search: "mongodb -performance" } }
~~~

Kỳ vọng loại loại document nào? Vì sao `"-performance"` đơn độc không trả kết quả?

### Bài 6 — Project score

Viết find projection gồm `title` và `score:{$meta:"textScore"}`. Giải thích score không phải field persisted.

### Bài 7 — Relevance sort

Viết `sort({score:{$meta:"textScore"},_id:1})`. Vì sao phải yêu cầu sort tường minh?

### Bài 8 — Weights

Tạo weights `title:10,body:1,tags:4`. Giải thích tại sao hai document cùng chứa term nhưng score có thể khác nhau.

### Bài 9 — Không dự đoán score bằng công thức thô

Một document có title match một lần, document khác body match ba lần. Có thể kết luận document đầu luôn score =10, document sau score =3 không?

**Đáp án:** Không. Weights là tham số cho scoring algorithm; kết quả cần kiểm thử.

### Bài 10 — English stop words

Trong English index, thử tìm `the`. Giải thích nguyên nhân query có thể không match dù text gốc chứa từ này.

### Bài 11 — none

Tạo collection mới với `default_language:"none"` và tìm từ `the`. Chỉ ra khác biệt về stop words/stemming, không nhầm với full Vietnamese NLP.

### Bài 12 — Vietnamese language

Vì sao `$language:"vi"` không hợp lệ với native `$text`? Nếu phải tìm tiếng Việt có dấu, đề xuất hai mức giải pháp: keyword đơn giản bằng none và search analyzer nâng cao.

### Bài 13 — Per-document language override

Tạo một English doc, một Spanish doc, một `lang:"none"` doc; tạo index với `language_override:"lang"`. Quy tắc nào áp dụng cho từng document?

### Bài 14 — Case sensitivity

So sánh `$caseSensitive:false` với `true`. Vì sao true có thể tốn thêm thời gian?

### Bài 15 — Diacritic sensitivity

Tìm `"cafe"` và `"café"` trong corpus có dấu. Giải thích hành vi v3 và tác động của `$diacriticSensitive:true`.

### Bài 16 — Text index version

So sánh tính nhạy dấu của text index v2 và v3. Vì sao không nên tùy tiện set `textIndexVersion:1` trên server mới?

### Bài 17 — Compound prefix

Collection `tenantDocs` có index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  title: "text",
  body: "text"
}
~~~

Viết query có equality cho cả tenantId và status. Điều gì xảy ra nếu bỏ status?

### Bài 18 — Không sắp text keys rời nhau

Phân tích index:

~~~javascript
{
  tenantId: 1,
  title: "text",
  publishedAt: -1,
  body: "text"
}
~~~

**Hỏi:** Vì sao không hợp lệ theo quy tắc adjacent text keys?

### Bài 19 — Aggregation text first

Viết pipeline `$match` chứa `$text` ở stage đầu, sau đó `$project` textScore, `$sort` score và `$limit`.

### Bài 20 — $text và hint

Giải thích vì sao query `$text` không cho `hint("idx_article_search")`. Cần dùng gì để quan sát plan?

### Bài 21 — Wildcard text vs wildcard index

Phân biệt:

~~~javascript
{ "$**": "text" }
{ "$**": 1 }
~~~

Index nào hỗ trợ `$text`? Khi nào không nên index tất cả string fields?

### Bài 22 — Tenant security

Thiết kế API tìm kiếm chỉ các bài đã published của tenant hiện tại. Cần những filters nào ngoài `$text`?

### Bài 23 — Java Driver

Sử dụng `Filters.text("mongodb")`, `Projections.metaTextScore("score")` và `Sorts.metaTextScore("score")` để lấy kết quả theo relevance.

### Bài 24 — Search user experience

Ứng dụng cần autocomplete từng ký tự, fuzzy typo và synonym. Native `$text` đủ không? Phân biệt với MongoDB Search stage `$search`.

### Bài 25 — Production diagnostics

Một text query trả chậm khi search từ quá phổ biến. Lập kế hoạch kiểm tra index definition, explain, total docs/keys examined, sort work, compound equality prefix, search length, timeout và pagination.

## 36. Quy trình thiết kế text search cho ứng dụng thật

### Bước 1 — Xác định kỳ vọng người dùng

Người dùng muốn keyword OR, phrase, all-terms, autocomplete, fuzzy, synonyms, hay semantic search? Không đặt tên tính năng “full-text search” rồi bỏ qua yêu cầu cụ thể.

### Bước 2 — Xác định trường searchable

Chỉ title, body, tags hay mọi string field? Mọi field thêm vào text index đều tăng chi phí và có thể thay đổi relevance.

### Bước 3 — Xác định ngôn ngữ corpus

Nếu English/Spanish/French, dùng các analyzers native được hỗ trợ với language override đúng. Nếu Vietnamese, biết giới hạn và đánh giá none hoặc search engine nâng cao.

### Bước 4 — Chọn weight

Title thường ưu tiên hơn body, tags có mức riêng. Thử ranking bằng bộ query đại diện; không đặt weight quá cực đoan mà không đo.

### Bước 5 — Thiết kế phạm vi access

Filter tenantId/status/visibility theo quyền. Nếu mọi query có equality tenant/status, cân nhắc compound prefix — nhưng nhớ chỉ có một text index/collection.

### Bước 6 — Chọn kiểu ranking và pagination

Relevance hay latest? Có tie-breaker không? Có yêu cầu kết quả ổn định giữa requests không? Đặt giới hạn offset/pageSize.

### Bước 7 — Đo trên dữ liệu thật

Dùng explain, index stats, query p95/p99, tần suất terms, số documents. Các bài ví dụ 8 documents không chứng minh hiệu năng production.

### Bước 8 — Lập kế hoạch thay đổi index

Thay fields, language hay weights của text index thường cần rebuild. Có staging/rollout và kế hoạch khi query không tìm được index trong thời gian chuyển đổi.

### Bước 9 — Kiểm tra quality

Tạo tập các query với kết quả mong đợi, gồm tiếng Việt có dấu/không dấu, stop words, stemming, cụm từ, phủ định và ngôn ngữ trộn.

### Bước 10 — Quyết định có cần MongoDB Search không

Nếu native text index không đáp ứng chất lượng, đừng cố dùng quá nhiều regex/logic thủ công để giả lập search engine. Đánh giá MongoDB Search và deployment/index cost cụ thể.

## 37. Checklist trước khi triển khai

### Text index và query

- [ ] Collection chỉ có một text index.
- [ ] Tất cả fields cần tìm đều được lập chỉ mục trong text index đó.
- [ ] Không dùng text index như unique index.
- [ ] Hiểu `$text.$search` terms mặc định OR.
- [ ] Có test quoted phrases và negation.
- [ ] Không nhầm text token search với substring/prefix search.
- [ ] Không giả định `$text` tự sort theo relevance.
- [ ] Có `$meta:"textScore"` khi cần score.
- [ ] Score không được diễn giải như xác suất hoặc so xuyên các queries.
- [ ] Weights được kiểm tra bằng ranking test.
- [ ] Compound text index có equality prefix đầy đủ.
- [ ] Không dùng `hint()` với text query.
- [ ] Aggregation text `$match` đặt đầu pipeline.
- [ ] Text index chỉ có simple collation.

### Ngôn ngữ và dữ liệu

- [ ] Biết `default_language` mặc định English.
- [ ] Có `language_override` khi corpus đa ngôn ngữ.
- [ ] Field override chứa ngôn ngữ hợp lệ hoặc none.
- [ ] Biết Vietnamese không nằm trong 15 ngôn ngữ native `$text`.
- [ ] `none` không đồng nghĩa NLP tiếng Việt.
- [ ] Có test case-sensitive và diacritic-sensitive semantics.
- [ ] Không tự giả định tokenization/stemming đúng với mọi ký tự đặc biệt.
- [ ] Tránh lập chỉ mục strings chứa dữ liệu nhạy cảm không cần thiết.

### Vận hành và sản phẩm

- [ ] Query luôn gắn tenant/visibility từ quyền người dùng.
- [ ] Có giới hạn độ dài search string, page size và timeout.
- [ ] Có index/read performance benchmark trên corpus thực.
- [ ] Có kế hoạch rebuild khi đổi weights/language/fields.
- [ ] Có monitoring lỗi index conflicts và query timeouts.
- [ ] Có query relevance test set và cơ chế phản hồi chất lượng.
- [ ] Đã đánh giá MongoDB Search nếu cần fuzzy/autocomplete/synonyms/facets.
- [ ] Không tự hứa tính năng tìm kiếm vượt khả năng native text index.

## 38. Tổng kết

MongoDB text search truyền thống gồm ba mảnh ghép chính:

1. **Text index** xác định những fields được token hóa, language rules và weights. Mỗi collection chỉ có **một text index**, dù index đó có thể chứa nhiều text fields.
2. **`$text`** tìm trên index; chuỗi nhiều terms mặc định OR, quoted phrases yêu cầu match cụm, dấu trừ loại trừ terms. Đây không phải regex, substring hay autocomplete.
3. **`$meta:"textScore"`** giúp lấy và sắp theo relevance, nhưng không tự xuất hiện/sort khi bạn chỉ dùng `$text`. Score là tín hiệu tương đối của query, không phải xác suất chính xác.

Ngôn ngữ quyết định stemming/stop words. Native `$text` hỗ trợ 15 ngôn ngữ được liệt kê trong MongoDB Manual, **không có Vietnamese**. `default_language:"none"` phù hợp keyword search không dùng stemming/stop words, nhưng không phải bộ phân tích tiếng Việt chuyên dụng.

Đối với những hệ thống cần tìm kiếm nâng cao, MongoDB hiện khuyến nghị MongoDB Search với search indexes và aggregation `$search` stage. Chọn native text index hay MongoDB Search nên dựa trên **ngữ nghĩa tìm kiếm, ngôn ngữ, chất lượng kết quả, độ trễ và chi phí vận hành** thực tế.

## Tài liệu tham khảo chính thức

- [MongoDB Manual — $text query predicate](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
- [MongoDB Manual — Text Search](https://www.mongodb.com/docs/manual/text-search/)
- [MongoDB Manual — Text Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/)
- [MongoDB Manual — Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/)
- [MongoDB Manual — Text Search Languages](https://www.mongodb.com/docs/manual/reference/text-search-languages/)
- [MongoDB Manual — Specify Text Index Language](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/specify-text-index-language/)
- [MongoDB Manual — Language Override](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/specify-language-text-index/use-any-field-to-specify-language/)
- [MongoDB Manual — Text Index Versions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-versions/)
- [MongoDB Manual — Text Search in Aggregation](https://www.mongodb.com/docs/manual/tutorial/text-search-in-aggregation/)
- [MongoDB Manual — Limit Text Index Entries Scanned](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/limit-number-of-items-scanned-for-text-search/)
- [MongoDB Java Sync Driver — Query Text](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/text/)
- [MongoDB Java Sync Driver — Sort Text Results](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/sort/)
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)

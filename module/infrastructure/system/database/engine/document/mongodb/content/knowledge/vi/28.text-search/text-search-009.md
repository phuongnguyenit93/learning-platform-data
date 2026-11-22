# Độ trễ cập nhật search index, giám sát và đánh giá chất lượng kết quả trong MongoDB

## 1. Tình huống mở đầu: đã sửa sản phẩm nhưng tìm kiếm chưa thấy

Một ứng dụng thương mại điện tử lưu sản phẩm trong MongoDB. Nhân viên sửa tên một sản phẩm:

```javascript
db.products.updateOne(
  { _id: productId },
  {
    $set: {
      title: "Tai nghe Bluetooth chống ồn",
      status: "ACTIVE",
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
```

API cập nhật trả về thành công. Khi nhân viên mở trang chi tiết bằng `findOne({_id: productId})` trên primary, tên mới đã xuất hiện. Nhưng tìm từ khóa **“chống ồn”** qua MongoDB Search `$search` vẫn chưa ra sản phẩm. Vài giây sau, không cần sửa gì thêm, sản phẩm mới xuất hiện trong kết quả.

Điều này có thể là biểu hiện của **độ trễ cập nhật search index** (*search indexing lag*). Đặc biệt với **MongoDB Search** (trước đây thường gọi là *Atlas Search*), việc ghi dữ liệu vào MongoDB và việc một thay đổi trở nên có thể tìm thấy trong chỉ mục tìm kiếm là **hai mốc khác nhau**.

Một luồng khái niệm:

```text
Ứng dụng ghi sản phẩm
          |
          v
MongoDB collection
   đã nhận ghi
          |
          | thay đổi được đồng bộ tới dịch vụ search
          v
Search index ingestion
          |
          | phân tích token, cập nhật cấu trúc tìm kiếm,
          | refresh trạng thái có thể truy vấn
          v
Search index mới nhìn thấy dữ liệu
          |
          v
API $search trả kết quả liên quan
```

Giữa thời điểm **write acknowledgment** và thời điểm **search visibility** có thể tồn tại khoảng trễ. Khi lượng ghi tăng, thay đổi analyzer/index definition hoặc một thành phần search thiếu tài nguyên, khoảng trễ này có thể tăng.

Bài học **“Độ trễ cập nhật search index, giám sát và đánh giá chất lượng kết quả”** thuộc chương **Tìm kiếm văn bản** của MongoDB. Sau bài, bạn sẽ:

1. Phân biệt **MongoDB Search index** với **text index truyền thống** của MongoDB.
2. Hiểu những giai đoạn tạo ra indexing lag và vì sao ghi majority không đồng nghĩa tìm kiếm thấy ngay.
3. Thiết kế phép đo **freshness** bằng các document thử nghiệm có mã định danh ổn định.
4. Giám sát trạng thái index, độ trễ đồng bộ, truy vấn, mức tải và tỷ lệ lỗi.
5. Phân biệt lỗi **không tìm thấy do index chưa cập nhật** với lỗi analyzer, mapping, query hoặc phân quyền.
6. Đánh giá độ phù hợp của kết quả bằng tập truy vấn có nhãn, Precision@K, Recall@K, MRR và nDCG.
7. Đánh giá tiếng Việt, dấu, từ ghép, đồng nghĩa, autocomplete và các tình huống từ khóa thực tế.
8. Thử nghiệm cải tiến ranking bằng phương pháp offline, canary và A/B test.
9. Triển khai search index mới an toàn, có quan sát và kế hoạch quay lại.
10. Thực hành MongoDB Search trên môi trường thử nghiệm được cấp quyền.

## 2. Trước tiên phải phân biệt hai loại “text search index”

MongoDB có nhiều cơ chế tìm kiếm văn bản. Khi nói “search index”, cần nêu rõ công nghệ đang dùng.

### 2.1. Native MongoDB text index và toán tử `$text`

MongoDB hỗ trợ **text index** tích hợp với cơ chế index thông thường của database:

```javascript
db.products.createIndex({
  title: "text",
  description: "text"
});

db.products.find({
  $text: {
    $search: "tai nghe"
  }
});
```

Đây là **native text search** với toán tử `$text`. Index là một phần của cơ chế database/index trên các thành viên MongoDB. Ghi dữ liệu và cập nhật index ở node thực hiện ghi tuân theo cơ chế quản lý index của MongoDB; nếu đọc từ secondary, vẫn phải xét **replication lag** của secondary đó.

Với `$text`, các câu hỏi về tính mới thường tập trung vào:

- Ghi đã thành công và query đọc đúng node/cluster chưa?
- Secondary có đang trễ không?
- Text index đã được tạo và có đúng field không?
- Ngôn ngữ, stemming, stop words và tokenizer của text index có phù hợp không?
- Query có dùng đúng `$text` syntax và projection `textScore` không?

Không nên áp mô hình “MongoDB Search service refresh bất đồng bộ” lên mọi query `$text`.

### 2.2. MongoDB Search index và stage `$search`

**MongoDB Search** cung cấp tìm kiếm full-text nâng cao dựa trên hạ tầng chỉ mục tìm kiếm riêng, với khả năng như:

- phân tích từ/token theo analyzer;
- relevance score;
- compound queries và các operator chuyên cho search;
- synonyms, fuzzy search hoặc autocomplete khi cấu hình phù hợp;
- highlighting, facets và những chức năng khác theo phiên bản/tính năng;
- kết hợp tìm kiếm với aggregation pipeline.

Ví dụ:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      text: {
        query: "tai nghe chống ồn",
        path: ["title", "description"]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

MongoDB Search sử dụng cơ chế đồng bộ và lập chỉ mục tìm kiếm **bất đồng bộ** so với thao tác ghi vào collection. Vì vậy **write acknowledged** không mặc định đảm bảo ngay lúc đó `$search` đã thấy nội dung mới.

### 2.3. So sánh hai cơ chế

| Khía cạnh | Native `$text` + text index | MongoDB Search `$search` |
| --- | --- | --- |
| Cấu trúc | Index thuộc cơ chế database | Search index được quản lý riêng |
| Cú pháp truy vấn | `find({$text: ...})` | Aggregation stage `$search` |
| Cập nhật index khi ghi | Theo cơ chế index của database node | Đồng bộ/lập chỉ mục search bất đồng bộ |
| Độ trễ cần quan sát | Write acknowledgment, secondary replication, query | Tất cả yếu tố liên quan và **search index visibility** |
| Analyzer và ranking | Chức năng text search truyền thống | Nhiều tùy chọn analyzer, scoring, facets, autocomplete |
| Điểm relevance | `{$meta:"textScore"}` | `{$meta:"searchScore"}` |
| Quản trị chỉ mục | `createIndex()` / `getIndexes()` | `createSearchIndex()` / `getSearchIndexes()` hoặc quản lý tương ứng |
| Điều kiện triển khai | MongoDB text index được hỗ trợ trong deployment thích hợp | Cần deployment có tính năng MongoDB Search được hỗ trợ |

Hai cơ chế có thể cùng tồn tại trên một collection, nhưng **không dùng chung định nghĩa index**. Tạo `createIndex({title:"text"})` **không tạo** MongoDB Search index cho `$search`.

### 2.4. Không nhầm MongoDB Search với MongoDB Vector Search

MongoDB còn có chức năng tìm kiếm vector/ngữ nghĩa. Vector search có thể cần embedding model, vector index và cơ chế đồng bộ riêng. Phép đo freshness/ranking ở mức tổng thể tương tự, nhưng các chỉ số **recall của approximate nearest neighbor**, embedding drift và evaluation ngữ nghĩa là một bài toán bổ sung.

Bài này tập trung vào **tìm kiếm văn bản**, MongoDB Search và tình huống native `$text` khi cần đối chiếu; không mặc định mọi search index đều là vector index.

## 3. Search indexing lag thực chất là khoảng trễ nào?

### 3.1. Các mốc thời gian trong một thao tác cập nhật

Một update có thể đi qua nhiều bước:

```text
T0: Client gửi update sản phẩm
T1: MongoDB xác nhận ghi theo write concern đã chọn
T2: Thành phần Search nhận/thấy thay đổi cần lập chỉ mục
T3: Thay đổi đã được xử lý trong cấu trúc search index
T4: Query $search mới trả đúng membership/ranking theo thay đổi
T5: UI hoặc cache của ứng dụng hiển thị kết quả mới
```

Không phải mọi hệ thống monitoring đều trực tiếp cung cấp được tất cả mốc `T2`, `T3` hoặc `T4`. Cần phân biệt **thứ muốn đo** và **thứ thực sự đo được**.

Các độ trễ:

\[
\text{Write latency} = T_1 - T_0
\]

\[
\text{Search visibility lag} \approx T_4 - T_1
\]

\[
\text{User-observed freshness lag} \approx T_5 - T_1
\]

Nếu giao diện có cache 30 giây, `T5 - T1` có thể lớn dù search index đã cập nhật từ lâu. Không quy tất cả độ trễ người dùng quan sát được cho MongoDB Search.

### 3.2. Vì sao search index cập nhật bất đồng bộ?

Một hệ thống tìm kiếm thường cần:

1. Nhận biết document mới, document bị sửa hoặc xóa.
2. Đọc nội dung các field được mapping.
3. Chuẩn hóa chuỗi, tokenization, áp analyzer/stemming/synonyms.
4. Cập nhật các cấu trúc tìm kiếm (ví dụ inverted index).
5. Quản lý các segment/bộ nhớ và làm thay đổi khả dụng cho truy vấn.
6. Duy trì sự đồng bộ theo cấu hình tìm kiếm, lưu lượng ghi và topology.

Những công việc này không nhất thiết kết thúc trước khi driver nhận acknowledgment từ lệnh ghi MongoDB. Đó là một **đánh đổi kiến trúc** cho chức năng tìm kiếm phong phú, không tự chứng minh database bị sai.

### 3.3. Ba tình huống trễ khác nhau

**Trễ insert:** document mới tồn tại trong MongoDB nhưng `$search` chưa trả nó cho từ khóa phù hợp.

**Trễ update:** document đổi từ “Tai nghe có dây” sang “Tai nghe Bluetooth”, nhưng index chưa cập nhật token. Query từ khóa mới có thể chưa thấy document; query từ khóa cũ có thể vẫn chọn nó trong thời gian ngắn.

**Trễ delete hoặc unpublish:** document đã bị xóa hoặc đổi `status` sang `INACTIVE`, nhưng index chưa phản ánh hoàn toàn thay đổi; kết quả tìm kiếm và nội dung lấy từ collection có thể khác nhau tùy cơ chế trả kết quả.

Tình huống thứ ba đặc biệt quan trọng: nếu **quyền truy cập, thu hồi sản phẩm hoặc trạng thái nhạy cảm** phụ thuộc vào dữ liệu mới nhất, không dùng chỉ một search index cập nhật bất đồng bộ làm cơ chế bảo vệ cuối cùng.

### 3.4. “Stale membership” và “stale document” không hoàn toàn giống nhau

Giả sử một document:

```javascript
{
  _id: "P-10",
  title: "Tai nghe có dây",
  version: 3
}
```

được đổi thành:

```javascript
{
  _id: "P-10",
  title: "Tai nghe Bluetooth",
  version: 4
}
```

Trước khi search index đồng bộ:

- Query `"Bluetooth"` có thể **chưa chọn** document này.
- Query `"có dây"` có thể **vẫn chọn** nó.
- Trong một số cấu hình thực thi `$search`, kết quả được truy xuất từ collection MongoDB có thể phản ánh field mới hơn so với bộ token/search score đã chọn document. Khi đó kết quả có thể **match theo nội dung cũ nhưng hiển thị field mới**.

Do vậy khi kiểm tra freshness phải xét **membership/score** của search index, không chỉ so `fullDocument.title` trong response.

### 3.5. Index đã “READY” không có nghĩa lag bằng 0

Trạng thái search index như **building/ready/queryable** cho biết các bước xây dựng và khả năng phục vụ query theo giao diện quản trị của phiên bản. Một search index có thể ở trạng thái sử dụng được trong khi **những ghi mới vẫn đang chờ trở nên visible**.

Kết luận sai:

> “Search index status = READY, vậy mọi document vừa ghi chắc chắn tìm thấy ngay.”

Kết luận đúng hơn:

> “Index được báo đủ điều kiện phục vụ truy vấn; vẫn cần theo dõi freshness của dữ liệu đang thay đổi.”

## 4. Khi nào độ trễ index tăng?

### 4.1. Ghi nhiều hoặc cập nhật nhiều field được index

Một chương trình nhập hàng loạt 2 triệu sản phẩm có thể tạo khối lượng thay đổi mà hệ thống search cần xử lý:

```text
MongoDB write throughput
          |
          v
Search indexing workload
          |
          +-- tokenization
          +-- index segment updates
          +-- delete/update bookkeeping
          +-- refresh/query workload
```

Nếu tốc độ thay đổi kéo dài lớn hơn khả năng lập chỉ mục, backlog và search visibility lag có thể tăng. Một khoảng trễ nhỏ khi tải đột biến là khác với **backlog tăng liên tục**.

### 4.2. Mapping/analyzer phức tạp

Các field động nhiều kiểu, nhiều analyzer, autocomplete/ngram, synonym mapping lớn hoặc index quá nhiều field có thể khiến xây dựng và cập nhật search index tốn tài nguyên hơn.

Không phải “nhiều field hơn” lúc nào cũng khiến query tốt hơn. Mapping động toàn bộ document đôi khi làm index lớn, tăng chi phí và đưa vào search những field không cần thiết.

### 4.3. Rebuild hoặc thay search index definition

Khi tạo index mới hay cập nhật định nghĩa index, MongoDB Search có thể cần xây dựng lại cấu trúc phục vụ tìm kiếm. Trong giai đoạn này:

- Index mới có thể chưa phục vụ query.
- Resource usage tăng.
- Trạng thái/tiến độ xây dựng thay đổi.
- Nếu đổi analyzer, kết quả ranking có thể khác dù dữ liệu không đổi.

Đừng xem một đợt index build là bằng chứng Search index cũ đang hỏng; cần nhận biết hoạt động triển khai đang diễn ra.

### 4.4. Search nodes thiếu tài nguyên

Khi deployment hỗ trợ hạ tầng Search chuyên biệt, các yếu tố cần xem:

- CPU bận.
- Bộ nhớ hoặc cache áp lực.
- Disk capacity, IOPS và read/write latency.
- Search index size, segment/merge workload.
- Network giữa thành phần database và Search.
- Số lượng truy vấn search đồng thời.

Các metric và tên gọi cụ thể phụ thuộc Atlas/MongoDB Search deployment, phiên bản, tier và dashboard. Không tự bịa một field `replicationLagMs` và khẳng định mọi cluster đều có sẵn.

### 4.5. Nhiều query đắt đỏ có thể cạnh tranh tài nguyên

Search query dùng fuzzy quá rộng, wildcard, autocomplete trên nhiều field, filter ít chọn lọc hoặc request `$searchMeta` tính count trên tập rất lớn có thể làm tăng chi phí truy vấn.

Tùy kiến trúc, indexing và querying có thể cạnh tranh tài nguyên; cần theo dõi **cả indexing freshness và query latency**. Chỉ nhìn số request/giây không đủ kết luận năng lực còn dư.

### 4.6. Lỗi cấu hình hoặc mất khả năng đồng bộ

Nếu một document không xuất hiện suốt nhiều phút, nguyên nhân không nhất thiết là “lag bình thường”:

- Field không được mapping.
- Dữ liệu có kiểu BSON không đúng với mapping.
- Search index chưa queryable hoặc build thất bại.
- Query dùng sai tên index.
- Analyzer loại bỏ/chuyển token khác kỳ vọng.
- Điều kiện filter (tenant/status) loại bỏ document.
- Dữ liệu đã được ghi vào nhầm database/collection.
- Query đang dùng cache hoặc environment khác.
- Lỗi đồng bộ hay giới hạn hạ tầng làm Search không thể bắt kịp.

Vì thế cần thiết kế một quy trình **phân loại** trước khi tăng capacity.

## 5. Tính mới của kết quả và tính nhất quán đọc–ghi

### 5.1. Write acknowledgment không phải Search acknowledgment

Ví dụ:

```javascript
const result = db.products.updateOne(
  { _id: productId },
  { $set: { title: "Máy pha cà phê mini" } },
  { writeConcern: { w: "majority" } }
);
```

Nếu ghi thành công theo `w:"majority"`, thao tác đã đạt mức xác nhận replica set yêu cầu. Nhưng **không có nghĩa MongoDB Search index đã lập chỉ mục xong**.

Tách hai hợp đồng:

- **Database durability/commit:** ghi đã được MongoDB xác nhận như thế nào?
- **Search freshness:** thay đổi đã có thể được tìm qua `$search` hay chưa?

Đây là hai yếu tố khác nhau. Thay write concern không biến Search thành synchronous indexing.

### 5.2. “Read-your-writes” trên API search

Người dùng vừa tạo sản phẩm rồi muốn tìm nó ngay. Có ba cách thiết kế tùy mức bảo đảm:

**Phương án A — Điều hướng bằng ID tới database:** sau khi tạo, trả `productId` và đọc chi tiết bằng `findOne` trên nguồn phù hợp. Search page có thể thông báo cần một khoảng thời gian để index cập nhật.

**Phương án B — Chờ kết quả search có giới hạn:** sau khi ghi, ứng dụng kiểm tra query được định nghĩa rõ với **deadline/backoff**, đến khi thấy document hoặc trả trạng thái “đang lập chỉ mục”. Đây là phép đợi tại ứng dụng, không tạo bảo đảm instant visibility.

**Phương án C — Kết hợp kết quả:** UI dùng bản ghi vừa tạo từ response/database để hiển thị mục mới, song song với danh sách search; cần loại duplicate và giữ thứ tự minh bạch. Tránh tự đưa vào danh sách “đã được tìm thấy theo relevance” khi chưa đo score.

### 5.3. Những nghiệp vụ không được phụ thuộc chỉ vào search freshness

Không dựa duy nhất vào `$search` để:

- kiểm tra quyền truy cập mới nhất;
- bảo đảm mã sản phẩm/username là duy nhất;
- quyết định trừ tồn kho hoặc hạn mức;
- xác nhận thanh toán;
- thực hiện thao tác xóa dữ liệu nhạy cảm;
- xác định trạng thái “đã khóa” ngay sau khi thu hồi quyền.

Với những bất biến đó, dùng **MongoDB query/atomic update/unique index/transaction** và kiểm soát authorization ở dữ liệu nguồn.

Search nên dùng để **tìm ứng viên và xếp hạng**, không làm hệ thống giao dịch cuối cùng cho các quyết định yêu cầu nhất quán mạnh.

### 5.4. Khi search index còn stale, filter phân quyền phải được kiểm tra lại

Giả sử một document đổi từ `visibility:"PUBLIC"` sang `"PRIVATE"`. Trong một khoảng trễ, Search có thể chưa phản ánh điều kiện mới.

Nếu chỉ dùng:

```javascript
$search: {
  compound: {
    filter: [
      { equals: { path: "visibility", value: "PUBLIC" } }
    ]
  }
}
```

rồi trả toàn bộ dữ liệu không kiểm tra gì khác, ứng dụng có thể dựa trên **trạng thái index chưa cập nhật**.

Với thông tin nhạy cảm:

1. Dùng search filter để giảm ứng viên.
2. Khi lấy kết quả, kiểm tra quyền truy cập theo trạng thái **authoritative** của nguồn MongoDB với consistency phù hợp.
3. Chỉ trả tài liệu người dùng thật sự được phép xem.
4. Đảm bảo không đưa nội dung nhạy cảm vào search highlights/facets/snippets hoặc log **trước khi được kiểm tra quyền**.

Đây là vấn đề **bảo mật**, không chỉ UX lag.

## 6. Thiết kế search index rõ ràng và dễ quan sát

### 6.1. Một định nghĩa index mẫu

Một MongoDB Search index có tên `products_text_v1`:

```javascript
{
  mappings: {
    dynamic: false,
    fields: {
      title: {
        type: "string",
        analyzer: "lucene.standard"
      },
      description: {
        type: "string",
        analyzer: "lucene.standard"
      },
      tenantId: {
        type: "token"
      },
      status: {
        type: "token"
      }
    }
  }
}
```

Trong ví dụ:

- `title` và `description` hỗ trợ truy vấn `text`.
- `tenantId` và `status` dùng kiểu mapping phù hợp với tìm kiếm **bằng giá trị chính xác** qua operator như `equals` trong các phiên bản MongoDB Search hỗ trợ.
- `dynamic:false` khiến index chỉ lập chỉ mục những field khai báo; giảm nguy cơ index mọi field không cần thiết.

Các mapping types/analyzer/operator có thể thay đổi theo release. Với phiên bản cũ chưa hỗ trợ `token` theo cách trên, phải tham khảo mapping/operator tương thích **trước khi triển khai**, không tự đổi `token` sang `string` rồi kỳ vọng semantics `equals` hoàn toàn giống nhau.

### 6.2. Query dùng đúng index và filter

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      compound: {
        must: [
          {
            text: {
              query: "tai nghe bluetooth",
              path: ["title", "description"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "tenantId",
              value: "TENANT-A"
            }
          },
          {
            equals: {
              path: "status",
              value: "ACTIVE"
            }
          }
        ]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 1,
      title: 1,
      status: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

`compound.filter` giảm ứng viên theo điều kiện không cần cộng vào relevance score; `compound.must` mô tả tiêu chí search quan trọng. Tùy mục tiêu, có thể dùng `should` và `minimumShouldMatch` để mở rộng matching.

**Không** lấy `tenantId` từ một input tùy ý chưa xác thực. Ví dụ trên minh họa cú pháp, không thay thế authorization.

### 6.3. Trạng thái index trong `mongosh`

Trên deployment hỗ trợ MongoDB Search:

```javascript
const products = db.getSiblingDB("shop").getCollection("products");

printjson(products.getSearchIndexes());
```

Khi đã đặt tên index:

```javascript
printjson(
  products.getSearchIndexes("products_text_v1")
);
```

Các trường thường hữu ích:

- tên index và loại;
- định nghĩa/mapping đang áp dụng;
- trạng thái xây dựng/indexing được báo cáo;
- khả năng queryable hoặc trạng thái tương đương;
- lỗi xây index/định nghĩa nếu có;
- thông tin version của index definition ở bản phát hành hỗ trợ.

**Không tự giả định tên trường response giống nhau ở mọi phiên bản Atlas/MongoDB Search.** Và như đã lưu ý, trạng thái READY/queryable không thay thế phép đo độ mới của mỗi update.

### 6.4. Tạo và thay index trong môi trường phù hợp

Một API `mongosh` cho deployment hỗ trợ là:

```javascript
db.products.createSearchIndex(
  "products_text_v1",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" },
        description: { type: "string" }
      }
    }
  }
);
```

Lệnh tạo index có thể trả về trước khi toàn bộ index mới trở nên queryable; cần giám sát trạng thái, không lập tức chuyển traffic.

Trong production:

- Không thử `createSearchIndex()` trên môi trường không hỗ trợ.
- Không ghi đè tên index đang được API sử dụng nếu chưa có kế hoạch.
- Không `dropSearchIndex()` index cũ trước khi kiểm chứng index mới.
- Dùng tên có phiên bản (`v1`, `v2`) để so sánh/rollback khi hạ tầng cho phép.
- Cân nhắc chi phí lưu song song hai index trong giai đoạn chuyển đổi.

## 7. Đo “search index đã thấy ghi mới chưa?” bằng probe

### 7.1. Định nghĩa phép đo trước khi viết script

Một phép đo hữu ích cần ghi:

- `writeId` hoặc `probeId` ổn định.
- `documentId` và `version` mong đợi.
- Thời điểm ứng dụng nhận **write acknowledgment**.
- Query có khả năng chọn chính document đó khi index đã cập nhật.
- Lần quan sát đầu tiên query trả đúng điều kiện.
- Khoảng polling, timeout và các lỗi xen giữa.

Khi đó:

\[
\text{Observed visibility lag}
=
\text{First observed visible time}
-
\text{Write acknowledged time}
\]

Đây là **độ trễ quan sát được theo cách poll**. Nó có thể **lớn hơn** thời điểm thực sự dữ liệu trở nên visible, tối đa theo khoảng polling và chi phí mạng/query; không phải timestamp nội bộ chính xác của Search engine.

### 7.2. Không chỉ đo bằng query quá chung

Nếu tạo sản phẩm tên `"iPhone"` rồi search `"iPhone"`, kết quả có thể đã có hàng nghìn sản phẩm trước đó. Việc query trả ít nhất một hit **không chứng minh sản phẩm mới đã được lập chỉ mục**.

Cần một **marker có tính duy nhất** và một điều kiện xác định đúng document:

```javascript
{
  _id: probeId,
  runId: "row308-unique-run",
  probeToken: "probe-unique-identifier",
  title: "Kiểm tra độ mới của Search",
  version: 1
}
```

Chỉ khi query search trả đúng `probeId`/token mới xem là **insert đã visible theo index**. Tránh dựa vào một số hit tổng quát hoặc thứ hạng bất kỳ.

### 7.3. Đo ba loại thay đổi

Một probe đầy đủ nên đo:

**Insert visibility:** thêm document chứa token duy nhất, poll đến khi Search trả nó.

**Update visibility:** đổi token từ `probe-old-XYZ` sang `probe-new-XYZ`, poll đến khi query mới match; đồng thời có thể đo khi nào query cũ không còn match.

**Delete visibility:** xóa document, poll đến khi search không còn trả nó. Cần phân biệt **index membership** với việc MongoDB fetch document sau khi đã xóa; một query không trả document ở giai đoạn sớm chưa đủ khẳng định index đã loại toàn bộ posting cũ nếu không có phép đo phù hợp.

Nhờ đo cả ba, ta có thể phát hiện pipeline update/delete có hành vi khác insert, thay vì chỉ dùng một sentinel insert.

### 7.4. Phải đo một “freshness SLO” theo thời gian

Ví dụ SLO nội bộ **chỉ để minh họa**:

```text
99% thay đổi sản phẩm ACTIVE
phải có thể tìm được trong vòng 15 giây
sau majority write acknowledgment,
đo từ probe có ID duy nhất trên cùng luồng index.
```

Từ đó định nghĩa:

- `p50_visibility_lag_seconds`.
- `p95_visibility_lag_seconds`.
- `p99_visibility_lag_seconds`.
- tỷ lệ probe chưa visible sau deadline.
- lag theo loại insert/update/delete.
- lag theo region, collection, index version hoặc nhóm sản phẩm.

**Ngưỡng 15 giây là ví dụ hợp đồng sản phẩm, không phải cam kết mặc định của MongoDB.** Đội vận hành phải chọn mục tiêu dựa trên tính năng, traffic và kết quả đo thật.

### 7.5. Phải tính đến probe bị mất kết quả do lỗi khác

Một probe thất bại có thể do:

- Index chưa xây xong.
- Query mapping sai.
- Broker/logging/probe process lỗi.
- Thời gian write acknowledgment chưa được ghi.
- MongoDB Search timeout.
- Khả năng tìm không khớp do analyzer/token.
- Token chưa được index.

Không được chỉ báo “lag > deadline” khi thực tế probe query không hợp lệ. Phân loại **failed query**, **mapping mismatch**, **index unavailable** và **valid query with document not yet visible**.

## 8. Giám sát search index: những trục quan trọng

### 8.1. Index lifecycle và sức khỏe

Theo dõi:

- Index đang xây, queryable, gặp lỗi hay bị xóa.
- Định nghĩa index đang active có đúng version triển khai không.
- Thời lượng build/rebuild.
- Số lỗi tạo/cập nhật index.
- Search service/node availability theo dashboard được hỗ trợ.
- Storage và tài nguyên cho dữ liệu index.

Index có thể READY nhưng chỉ trả chất lượng kém do analyzer mới; vì vậy cần giám sát cả **định nghĩa index + chất lượng query**, không chỉ tình trạng dịch vụ.

### 8.2. Freshness

Theo dõi:

- thời gian write → search visibility;
- tỉ lệ insert/update/delete vượt deadline;
- tốc độ ghi vào collection và tốc độ search bắt kịp nếu metric được cung cấp;
- backlog/lag của Search theo chỉ số Atlas/deployment có sẵn;
- số lần probe hết timeout;
- index build/rebuild cùng lúc lag tăng;
- chênh lệch giữa nguồn MongoDB và số document có thể tìm kiếm.

Khi các công cụ cung cấp một metric có tên “indexing lag” hay “replication lag”, phải đọc **định nghĩa chính xác**: có thể là lag giữa MongoDB và Search, hoặc replication lag giữa replica set members — hai thứ không đồng nghĩa.

### 8.3. Query latency và throughput

Theo dõi:

- QPS theo query type.
- p50/p95/p99 query latency.
- tỷ lệ timeout và lỗi của `$search`.
- tỷ lệ no-results.
- kết quả/truy vấn trung bình.
- số request dùng fuzzy, autocomplete hoặc index version khác.
- latency phía API gồm network, authorization, cache và query.

Một số kết quả tìm được nhanh nhưng sai ngữ nghĩa vẫn là trải nghiệm kém. Ngược lại, ranking tốt nhưng p99 quá cao cũng có thể không đạt SLO người dùng.

### 8.4. Chi phí và tài nguyên

Quan sát cùng thời điểm với freshness/latency:

| Trục | Dấu hiệu cần xem | Câu hỏi điều tra |
| --- | --- | --- |
| CPU/search node | CPU bận kéo dài | Query complexity hay indexing burst? |
| Memory/cache | Áp lực bộ nhớ, eviction hoặc giới hạn tài nguyên | Index quá lớn hoặc workload bất thường? |
| Disk/storage | Tăng size, I/O latency | Mapping quá rộng, rebuild hoặc index growth? |
| Network | RTT, bandwidth, errors | Dữ liệu đồng bộ tới Search có bị nghẽn? |
| Index build | Thời gian xây mới, trạng thái | Có đang triển khai index khác? |
| Database writes | Tốc độ insert/update/delete | Batch import làm queue index tăng? |
| API caching | Hit rate, cache age | UI cũ do cache hay search index? |

Không tự khẳng định một metric có sẵn ở mọi MongoDB plan. Với deployment managed, dùng **Atlas metrics/logs** được cấp; với self-managed Search khi được hỗ trợ, dùng telemetry tương ứng.

### 8.5. Custom metrics hữu ích

Một service có thể tự xuất:

```text
search_probe_visibility_seconds
search_probe_timeout_total
search_probe_query_error_total
search_queries_total
search_query_latency_seconds
search_no_results_total
search_index_version_traffic_total
search_relevance_feedback_total
search_result_clicks_total
search_sessions_success_total
```

Đây là **tên đề xuất tự đặt**, không phải danh sách field mặc định do MongoDB tạo sẵn. Khi xuất metric, gắn label có cardinality được kiểm soát như `index_version`, `query_class`, `region`, không gắn từng raw user query hoặc productId thành Prometheus label gây bùng nổ time series.

## 9. Thiết kế dashboard và cảnh báo vận hành

### 9.1. Một dashboard có ý nghĩa

Nên đặt các biểu đồ cạnh nhau:

```text
+-----------------------+-----------------------+
| Search freshness p95  | Search freshness p99  |
+-----------------------+-----------------------+
| Search query QPS      | Search latency p95    |
+-----------------------+-----------------------+
| Index status/build    | Query error rate      |
+-----------------------+-----------------------+
| No-results rate       | Search success rate   |
+-----------------------+-----------------------+
| CPU / Disk / Memory   | DB write throughput   |
+-----------------------+-----------------------+
```

Khi p95 freshness tăng cùng thời điểm write throughput tăng mạnh, nghi vấn indexing backlog. Khi query latency tăng nhưng freshness bình thường, tập trung vào query complexity, cache và hạ tầng truy vấn.

### 9.2. Alert theo triệu chứng, không chỉ index READY

Một bảng cảnh báo mẫu:

| Điều kiện minh họa | Độ ưu tiên phụ thuộc nghiệp vụ | Hướng phản ứng |
| --- | --- | --- |
| Search index không queryable | Cao nếu phục vụ traffic chính | Kiểm tra build/error, fallback |
| p95 visibility vượt freshness SLO | Cảnh báo chất lượng cập nhật | Triage workload và indexing |
| p99 query latency vượt API SLO | Cảnh báo trải nghiệm | Xem query shape/capacity |
| No-results tăng đột biến sau deploy analyzer | Nguy cơ relevance regression | So index versions, query replay |
| Query errors/timeout tăng | Có thể mất tính sẵn sàng | Triage Search nodes, command errors |
| Probe không tạo dữ liệu nhiều chu kỳ | Monitoring không còn đáng tin | Sửa probe, không coi chỉ số cũ là bình thường |
| Điểm relevance offline giảm vượt ngưỡng | Rủi ro chất lượng | Giữ/rollback index version |

Alert cần **khoảng quan sát**, số lượng mẫu và phân nhóm hợp lý để tránh báo động từ một probe mạng lỗi ngẫu nhiên.

### 9.3. Chỉ số composite và scorecard

Để trình bày với đội sản phẩm, có thể xây scorecard:

| Nhóm | Chỉ số | Câu hỏi |
| --- | --- | --- |
| Freshness | p95/p99 indexing visibility | Sản phẩm vừa cập nhật được tìm thấy nhanh không? |
| Availability | Query success rate | Search có hoạt động ổn định? |
| Latency | p95 API search duration | Người dùng có phải chờ? |
| Retrieval quality | Recall@K, no-results | Có bỏ sót sản phẩm phù hợp? |
| Ranking quality | MRR, nDCG@K | Kết quả tốt nằm gần đầu? |
| Product outcome | Click success, conversion, reformulation | Người dùng có tìm được điều họ muốn? |
| Cost | Resources per QPS/index size | Hiệu quả chi phí có chấp nhận? |

Không gom các chỉ số thành một “search health score” thiếu giải thích khiến một cải tiến latency che lấp việc kết quả liên quan giảm mạnh.

## 10. Quy trình điều tra khi tìm kiếm chưa thấy document mới

### 10.1. Bước 1 — Xác nhận dữ liệu nguồn

Đầu tiên, đọc document bằng ID từ collection MongoDB phù hợp:

```javascript
db.products.findOne(
  { _id: productId },
  { title: 1, status: 1, tenantId: 1, version: 1, updatedAt: 1 }
);
```

Hỏi:

1. Ghi có thành công thật không?
2. `matchedCount`/`modifiedCount`/`upsertedId` cho thấy gì?
3. Document đang ở database/collection đúng không?
4. `status`/tenant/scope có làm query loại document?
5. Có worker khác ghi đè sau khi cập nhật không?

Nếu nguồn MongoDB chưa có tên mới, không thể kết luận Search bị lag.

### 10.2. Bước 2 — Xác nhận tên index và mapping

```javascript
printjson(
  db.products.getSearchIndexes()
);
```

Xem index mà API thực sự dùng, field được mapping và trạng thái. Một source field `productName` nhưng Search chỉ mapping `title` sẽ không tự được tìm theo `title` khi `dynamic:false`.

Nếu vừa đổi analyzer/index definition, cần xem traffic có đang trỏ tới version cũ hay version mới.

### 10.3. Bước 3 — Tối giản query

Thay một query phức tạp bằng query text rõ ràng:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      text: {
        query: "bluetooth",
        path: "title"
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

Sau khi xác nhận index hoạt động, thêm dần:

- tenant filter;
- status filter;
- các field search khác;
- fuzzy/synonyms;
- custom score;
- projection và pagination.

Nếu query tối giản trả document nhưng query đầy đủ không trả, nguyên nhân có thể là **mapping/filter/ranking logic**, không phải lag.

### 10.4. Bước 4 — Xem thời điểm và tiến độ

So:

```text
Write acknowledgment:  10:00:00.000
Probe first visible:   10:00:03.500
Observed lag:           3.5 giây
```

Đây chỉ là dữ liệu minh họa. Với lỗi thực tế, cần có:

- ID và version của document.
- Tên index.
- Query được dùng (đã loại dữ liệu nhạy cảm).
- Timestamp được ghi ở tầng server/ứng dụng.
- Tiến độ index và tình trạng queryable.
- Probe result từ nhiều lần lấy mẫu.

Nếu không có một phép đo đích danh document, một dấu hiệu “người dùng bảo chưa thấy” khó phân biệt lag với analyzer không match.

### 10.5. Bước 5 — Phân biệt với cache/UI

Kiểm tra:

- CDN hoặc HTTP response caching.
- Redis/application cache.
- Browser cache hoặc state phía frontend.
- Pagination/trang đầu có giới hạn và ranking score thay đổi.
- Các query params khác nhau giữa trang admin và trang người dùng.
- Timezone/filter status/ngày hiệu lực.

Nếu `$search` qua `mongosh` đã trả document nhưng UI vẫn chưa, hãy điều tra tầng sau Search.

### 10.6. Bảng triage

| Quan sát | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `findOne` không thấy cập nhật | Write chưa thực hiện/đọc nhầm nguồn | Kiểm tra write result, namespace, node |
| `findOne` thấy, `$search` chưa thấy ngay rồi tự xuất hiện | Search indexing lag | Đo visibility và backlog |
| `$search` không bao giờ thấy một field | Field chưa mapping, dữ liệu sai kiểu, analyzer | Kiểm definition/schema |
| Query tối giản thấy, query có filter không thấy | Filter/tenant/status sai hoặc dữ liệu stale | So semantics filter và nguồn authoritative |
| Index không queryable | Build/error/triển khai | Kiểm trạng thái và runbook |
| Search thấy bằng mongosh, UI không thấy | Cache, pagination, API mapping | Tracing end-to-end |
| Query từ cũ còn match nhưng tiêu đề hiển thị mới | Index membership stale, document fetch mới hơn | Kiểm probe update và version |
| Không thấy từ tiếng Việt có dấu | Analyzer, Unicode/tokenization | Test normalizations và query pairs |
| Ranking đổi sau deploy | Definition/analyzer/boost thay đổi | So offline judgments/traffic canary |
| Tất cả query chậm nhưng freshness bình thường | Index/query/capacity pressure | Xem explain, QPS, resources |

## 11. Chất lượng kết quả: “Search tốt” là gì?

### 11.1. Không có một chỉ số duy nhất

Một hệ thống có thể:

- tìm rất nhanh nhưng trả tài liệu không liên quan;
- trả đúng các tài liệu nhưng xếp chúng ở trang 5;
- cho kết quả tốt khi gõ đúng chính tả nhưng thất bại với lỗi gõ;
- thành công với tiếng Anh nhưng kém với từ ghép tiếng Việt;
- có relevance tốt nhưng bỏ sót document mới vài chục giây;
- có CTR cao vì người dùng luôn click vị trí đầu tiên, không phải vì kết quả đúng.

Vì vậy đánh giá search thường chia thành:

1. **Retrieval:** hệ thống tìm được các kết quả phù hợp hay không.
2. **Ranking:** các kết quả phù hợp có nằm ở vị trí cao không.
3. **Freshness:** kết quả phản ánh dữ liệu mới đến đâu.
4. **Reliability/latency:** truy vấn có phục vụ đúng hạn không.
5. **Business outcome:** người dùng có hoàn thành mục tiêu không.

### 11.2. Relevance là một nhãn có ngữ cảnh

Query `"tai nghe"`:

- với người mua hàng: sản phẩm tai nghe phù hợp là relevant;
- với đội hỗ trợ: bài hướng dẫn bảo hành tai nghe có thể relevant;
- với kho vận: SKU/hàng tồn trong kho là relevant.

Một tập đánh giá phải xác định:

- ý định người dùng;
- ngôn ngữ và vùng;
- loại document;
- filter business (stock/active/tenant);
- mức liên quan được kỳ vọng;
- thời điểm dữ liệu;
- loại query: chính xác, mơ hồ, dài, sai chính tả, synonym.

Không có “relevance score đúng tuyệt đối” nếu chưa định nghĩa nhiệm vụ.

### 11.3. Nhãn nhị phân và nhãn nhiều mức

**Nhãn nhị phân**:

```text
0 = không liên quan
1 = có liên quan
```

**Nhãn phân cấp**:

```text
0 = sai hoàn toàn
1 = liên quan yếu
2 = khá phù hợp
3 = phù hợp rất cao / đúng ý định
```

Nhãn phân cấp hữu ích cho các metric ranking như **nDCG**, vì nó phân biệt kết quả chính xác với kết quả chỉ tương đối liên quan.

Nên có guideline cho người gắn nhãn, audit bất đồng giữa annotators, và tách những query nhạy cảm để chuyên gia nghiệp vụ đánh giá khi cần.

## 12. Xây bộ kiểm thử relevance offline

### 12.1. Tập truy vấn đại diện

Một bộ query nên chứa nhiều nhóm:

| Nhóm | Ví dụ | Khả năng cần kiểm tra |
| --- | --- | --- |
| Exact name | `"tai nghe bluetooth"` | Matching đúng tên |
| Nhiều từ | `"tai nghe bluetooth chống ồn"` | Đồng hiện diện các token và ranking |
| Synonym | `"headphone không dây"` | Từ đồng nghĩa/ngôn ngữ pha trộn |
| Typo | `"bluetooh"` | Fuzzy matching với giới hạn |
| Có/không dấu | `"may loc khong khi"` / `"máy lọc không khí"` | Unicode/analyzer |
| Mã sản phẩm | `"WH-1000XM"` | Exact/keyword matching |
| Từ hiếm | `"màng lọc HEPA H13"` | Phân biệt từ kỹ thuật |
| Query quá rộng | `"máy"` | Relevance, facets, pagination |
| Query không có kết quả | `"sản phẩm không tồn tại 308XYZ"` | No-results và gợi ý |
| Multi-tenant | cùng từ khóa trong 2 tenant | Isolation/authorization |
| Sản phẩm mới | query chứa unique token vừa ghi | Freshness |
| Sản phẩm ngừng bán | query từng match nhưng nay INACTIVE | Index lag và filter correctness |

Không tạo bộ query chỉ từ 10 từ khóa phổ biến nhất. **Long-tail queries**, truy vấn sai chính tả và query có ý định cụ thể thường phơi bày nhiều lỗi hơn.

### 12.2. Golden dataset

Một tập đánh giá có thể lưu:

```json
{
  "queryId": "Q-001",
  "query": "tai nghe bluetooth",
  "tenantContext": "TENANT-TEST",
  "locale": "vi-VN",
  "intent": "find_product",
  "judgments": [
    { "documentId": "P-001", "relevance": 3 },
    { "documentId": "P-002", "relevance": 2 },
    { "documentId": "P-003", "relevance": 0 }
  ]
}
```

Khi dùng tập này:

- Cố định hoặc ghi lại snapshot dữ liệu test.
- Lưu index version, query version và analyzer version.
- Xác định tình trạng ACTIVE/in-stock tại thời điểm gắn nhãn.
- Phân biệt một document **chưa được đánh giá** với document **được đánh giá là không liên quan**.
- Tránh sử dụng dữ liệu cá nhân/khách hàng thật trong artifact có thể chia sẻ.

Nếu dữ liệu test thay đổi liên tục, so sánh ranking giữa hai index có thể bị nhiễu bởi **freshness hoặc dữ liệu nguồn khác nhau**, không chỉ do thuật toán.

### 12.3. Tập đánh giá nên có độ khó tăng dần

Gợi ý cấu trúc:

1. **Smoke set:** ít query nhưng rất dễ xác định expected result, dùng sau deploy.
2. **Regression set:** các query từng gây lỗi hoặc bị khiếu nại.
3. **Representative set:** lấy mẫu theo lượng truy vấn và phân khúc người dùng.
4. **Stress/edge set:** nhiều token, tên có dấu, typo, mã SKU, query no-result.
5. **Freshness set:** những thay đổi mới insert/update/delete có expected visibility.
6. **Safety/authorization set:** kết quả không được rò rỉ dữ liệu ngoài quyền.

Không bắt buộc mọi loại metric có cùng trọng số; cần phản ánh rủi ro sản phẩm.

## 13. Precision@K, Recall@K và Hit Rate

### 13.1. Precision@K

**Precision@K** là tỷ lệ kết quả liên quan trong **K kết quả đầu tiên**:

\[
\operatorname{Precision@K}
=
\frac{\text{số kết quả liên quan trong top K}}{K}
\]

Ví dụ top 5 có nhãn:

```text
Rank      1   2   3   4   5
Relevant  1   0   1   0   1
```

Có 3 kết quả liên quan trong top 5:

\[
\operatorname{P@5}=3/5=0.60
\]

Điểm 0,60 nói rằng 60% vị trí top 5 là kết quả relevant theo nhãn. Nó **không nói** những tài liệu liên quan khác bị bỏ sót bao nhiêu.

### 13.2. Recall@K

**Recall@K** đo tỷ lệ kết quả liên quan thực tế được lấy vào top K:

\[
\operatorname{Recall@K}
=
\frac{\text{số kết quả liên quan trong top K}}
{\text{tổng số kết quả liên quan trong tập xét}}
\]

Giả sử tập nhãn xác định có tổng cộng **4 document liên quan**, top 5 tìm được 3:

\[
\operatorname{Recall@5}=3/4=0.75
\]

Muốn tính Recall có ý nghĩa, cần biết hoặc ước lượng đủ tốt **tập tài liệu liên quan**. Nếu chỉ gắn nhãn top 5 hiện tại rồi coi tất cả document khác đều không liên quan, recall sẽ bị sai lệch nghiêm trọng.

### 13.3. Hit Rate@K / Success@K

Với query mà người dùng chỉ cần **một kết quả đúng**, một chỉ số đơn giản:

```text
Hit@K(query) = 1 nếu top K có ít nhất một kết quả liên quan,
               0 nếu không có.
```

Trung bình Hit@K qua nhiều query cho biết khả năng có **ít nhất một kết quả đúng** trong K vị trí đầu.

Metric này dễ giải thích nhưng không phân biệt “một kết quả đúng ở rank 1” với “một kết quả đúng ở rank K”. Vì vậy nên dùng thêm MRR/nDCG.

### 13.4. Lưu ý với query không có kết quả hợp lệ

Nếu query thực sự không có bất kỳ document relevant nào:

- Recall có mẫu số 0, phải quy định rõ cách xử lý trong đánh giá.
- No-results có thể là kết quả **đúng**.
- Một search engine luôn trả ít nhất 10 document kể cả sai hoàn toàn không phải tốt hơn engine trả mảng rỗng khi không có match.

Với query “không có hàng”, hãy đo **no-result correctness** và chất lượng gợi ý thay vì cố tối ưu recall bằng cách trả kết quả không liên quan.

## 14. MRR và nDCG: đo thứ tự xếp hạng

### 14.1. MRR — Mean Reciprocal Rank

MRR ưu tiên hệ thống đưa **kết quả relevant đầu tiên** lên cao.

Với một query:

\[
\operatorname{RR}(q)
=
\frac{1}{\text{rank của kết quả relevant đầu tiên}}
\]

Nếu relevant đầu tiên ở rank 2:

\[
\operatorname{RR}(q)=1/2=0.5
\]

Qua `N` query:

\[
\operatorname{MRR}
=
\frac{1}{N}
\sum_{q=1}^{N}\operatorname{RR}(q)
\]

Nếu không có kết quả relevant trong phạm vi đánh giá, quy ước thường dùng là `RR=0`.

MRR rất phù hợp với **navigational search** hoặc trường hợp người dùng cần một kết quả đúng, như tìm sản phẩm theo mã hoặc trang hỗ trợ cụ thể. Nó ít phản ánh chất lượng toàn bộ top 10 nếu kết quả đầu tiên đã đúng.

### 14.2. DCG và nDCG — đánh giá nhiều mức relevance

Khi mỗi document có nhãn relevance từ 0 đến 3, **Discounted Cumulative Gain**:

\[
\operatorname{DCG@K}
=
\sum_{i=1}^{K}
\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

Trong đó `rel_i` là nhãn relevance của kết quả ở vị trí thứ `i`. Thành phần `log₂(i+1)` làm giảm trọng số kết quả nằm thấp hơn.

`nDCG` chuẩn hóa DCG theo thứ tự lý tưởng:

\[
\operatorname{nDCG@K}
=
\frac{\operatorname{DCG@K}}
{\operatorname{IDCG@K}}
\]

Trong đó `IDCG@K` là DCG của thứ tự tốt nhất theo nhãn đã biết. Với tập nhãn nonempty và định nghĩa chuẩn, nDCG thường nằm trong khoảng 0 đến 1.

Ví dụ:

```text
Rank:       1   2   3   4   5
Relevance:  3   1   0   2   0
```

Một ranking tốt hơn có thể là:

```text
Rank:       1   2   3   4   5
Relevance:  3   2   1   0   0
```

Thứ tự thứ hai đưa relevance 2 lên trước relevance 1 nên **DCG và nDCG cao hơn**, dù cùng có số document relevant như nhau.

Với query không có nhãn relevance dương, `IDCG@K=0`; evaluator phải có quy tắc riêng, không chia cho 0.

### 14.3. Chọn metric theo tác vụ

| Tác vụ | Metric hữu ích | Cảnh báo |
| --- | --- | --- |
| Tìm trang theo tên/mã chính xác | MRR@K, Hit@1 | MRR bỏ qua chất lượng sau kết quả relevant đầu tiên |
| Tìm nhiều sản phẩm để so sánh | nDCG@10, P@10 | Cần nhãn nhiều mức đáng tin |
| Thu thập tài liệu đầy đủ | Recall@K, coverage | Cần biết tập liên quan |
| Autocomplete | MRR@5, chọn gợi ý thành công | Prefix ngắn dễ gây nhiều match |
| Search trả rỗng đúng lúc | No-result correctness | Đừng ép mọi query phải có hit |
| Search tài liệu hỗ trợ | nDCG@5, task success | Click không đồng nghĩa giải quyết được vấn đề |
| Search thay đổi mới | Freshness/visibility latency | Relevance cao trên dữ liệu cũ chưa đủ |

Một đội sản phẩm nên có **bộ metric theo mục tiêu**, không chọn nDCG vì nó nghe “khoa học” mà không có nhãn tốt.

## 15. Chất lượng tìm kiếm tiếng Việt và dữ liệu đa ngôn ngữ

### 15.1. Dấu tiếng Việt và Unicode

Các cặp:

```text
"máy lọc không khí"  /  "may loc khong khi"
"điện thoại"        /  "dien thoai"
"cà phê"           /  "ca phe"
```

có thể cần hành vi tìm kiếm tương đương trong ứng dụng Việt Nam. Nhưng việc “bỏ dấu” không nên làm tùy tiện:

- Có thể làm tăng recall với query không dấu.
- Có thể làm tăng false positives, ảnh hưởng precision.
- Có thể khiến hai từ khác nghĩa sau chuẩn hóa trùng token.
- Có thể ảnh hưởng highlight, exact matching và các tên riêng.

Đánh giá bằng **query pairs** có dấu/không dấu, kết hợp analyzer phù hợp và dữ liệu thực tế. Nếu dùng custom analyzer/token filter như Unicode folding, phải thiết lập đúng trong Search index definition và kiểm chứng bằng test; không suy luận rằng `lucene.standard` mặc định giải quyết mọi vấn đề tiếng Việt.

### 15.2. Unicode normalization

Một chuỗi có dấu có thể tồn tại dưới nhiều cách biểu diễn Unicode (ký tự ghép sẵn hoặc ký tự cơ sở + combining mark). Dữ liệu copy từ nhiều hệ thống có thể khác normalization.

Nếu không có chính sách:

```text
Client A gửi "café" (ký tự ghép sẵn)
Client B gửi "café" (e + dấu kết hợp)
```

hai chuỗi có thể trông giống nhau nhưng khác sequence code points. Đặt chính sách **Unicode normalization** tại ingestion hoặc analyzer khi phù hợp; so sánh test theo byte/code point nếu nghi ngờ.

### 15.3. Từ ghép, tên riêng và mã SKU

Tiếng Việt có nhiều từ ghép được viết bằng khoảng trắng:

```text
"máy lọc không khí"
"tai nghe chống ồn"
"điện thoại thông minh"
```

Việc một analyzer tách từng tiếng không có nghĩa phrase matching sẽ tự hiểu đúng mọi ngữ nghĩa. Cần kiểm tra:

- phrase query;
- multi-word synonyms;
- tokenization/position;
- boost cho title so với description;
- exact match cho mã sản phẩm;
- khả năng match theo tiền tố ở autocomplete.

Mã SKU như `"AB-1200-X"` có thể bị analyzer tách thành nhiều token. Đôi khi cần field riêng dùng exact/token mapping song song với field full-text; không bắt buộc chọn một analyzer duy nhất cho mọi field.

### 15.4. Synonyms cần version và test

Ví dụ:

```text
"tai nghe" ~ "headphone"
"điện thoại" ~ "smartphone"
"máy tính xách tay" ~ "laptop"
```

Synonyms có thể mở recall nhưng cũng làm giảm precision nếu các từ chỉ gần nghĩa trong một số ngữ cảnh.

Quy trình:

1. Ghi rõ synonym set version.
2. Thử query có/không có synonym.
3. So P@K, Recall@K, MRR/nDCG.
4. Kiểm tra tác động đến latency và số kết quả.
5. Canary trước khi áp dụng cho toàn bộ traffic.

Không thêm hàng nghìn synonym chỉ vì mong muốn search “thông minh hơn” mà không kiểm chứng.

### 15.5. Fuzzy matching và lỗi gõ

Fuzzy query có thể giúp:

```text
"bluetooh"  -> "bluetooth"
"samssung"  -> "samsung"
```

Nhưng nếu cho phép edit distance quá lớn trên query ngắn, kết quả có thể rất nhiễu. Các lựa chọn như maxEdits, prefixLength và maxExpansions chịu giới hạn theo Search operator và phiên bản.

Nên đo:

- typo recovery rate;
- false positive rate;
- query latency;
- tác động lên top 5/ranking;
- sự khác nhau giữa code sản phẩm và từ thường.

Mã SKU/ID thường cần **exact match hoặc prefix chính xác** hơn là fuzzy mạnh.

### 15.6. Autocomplete không phải full-text query bình thường

Autocomplete phục vụ khi người dùng đang gõ:

```text
"tai" -> "tai nghe bluetooth", "tai nghe chụp tai", ...
```

Có thể cần mapping `autocomplete` và operator `autocomplete` tương ứng, chứ không đơn thuần dùng `text` query như trường hợp search hoàn chỉnh.

Đánh giá riêng:

- chất lượng gợi ý ở 2, 3, 4 ký tự;
- latency khi keypress liên tục;
- typo và dấu tiếng Việt;
- session success;
- giới hạn request/debounce/rate.

Một autocomplete index nhiều n-gram có thể tăng kích thước và chi phí cập nhật. Đừng áp cùng các ngưỡng freshness/ranking của search đầy đủ mà không xác định hành vi sản phẩm.

## 16. Truy vấn và xem relevance score để chẩn đoán

### 16.1. `searchScore` là score tương đối, không phải xác suất

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      text: {
        query: "máy lọc không khí",
        path: ["title", "description"]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

`score` thường phục vụ **xếp hạng tương đối trong một query/cấu hình**. Không diễn giải `score=7.3` thành “73% xác suất đây là sản phẩm đúng”.

So score giữa các query khác nhau, index definitions khác nhau hoặc data corpus khác nhau có thể không có cùng thang ý nghĩa. Khi đánh giá ranking, ưu tiên **thứ tự + nhãn relevance** thay vì chỉ nhìn score tuyệt đối.

### 16.2. Boost field có thể tăng chất lượng hoặc gây regression

Ví dụ query ưu tiên title:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      compound: {
        should: [
          {
            text: {
              query: "tai nghe bluetooth",
              path: "title",
              score: { boost: { value: 3 } }
            }
          },
          {
            text: {
              query: "tai nghe bluetooth",
              path: "description"
            }
          }
        ],
        minimumShouldMatch: 1
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

Boost title có thể giúp sản phẩm tên khớp từ khóa lên trên sản phẩm chỉ nhắc từ khóa ở description. Nhưng `boost=3` là **giá trị minh họa**, không phải thông số tối ưu mặc định. Cần đánh giá theo golden queries, đặc biệt khi title ngắn hoặc chứa quảng cáo lặp từ khóa.

### 16.3. Search score details/explain

Trong các phiên bản/cấu hình hỗ trợ, MongoDB Search có khả năng giải thích scoring (ví dụ sử dụng tùy chọn `scoreDetails` và metadata tương ứng), giúp điều tra:

- trường nào match;
- điều kiện nào góp vào score;
- boost/synonyms ảnh hưởng ra sao;
- tại sao một document được xếp trên document khác.

Với production, scoring details/explain có thể tạo output lớn và chi phí thêm. Chỉ bật cho query chẩn đoán có phạm vi nhỏ, không log raw tài liệu nhạy cảm.

### 16.4. `$searchMeta` và số lượng kết quả

Đôi khi cần biết **ước lượng hoặc tổng số kết quả match**:

```javascript
db.products.aggregate([
  {
    $searchMeta: {
      index: "products_text_v1",
      text: {
        query: "tai nghe",
        path: ["title", "description"]
      },
      count: {
        type: "total"
      }
    }
  }
]);
```

MongoDB Search hỗ trợ các loại count như `total` và `lowerBound` theo operator/phiên bản. `total` có thể đắt hơn trong một số workload; `lowerBound` không phải một con số chính xác tuyệt đối cho pagination.

Đừng lấy count của `$searchMeta` làm bằng chứng mọi thay đổi vừa ghi đã visible. Count dựa trên **trạng thái search index có thể truy vấn tại thời điểm đó**.

### 16.5. `$search` và thứ tự aggregation pipeline

`$search` phải là stage đầu tiên trong pipeline mà nó thuộc về (với các bối cảnh nested pipeline được hỗ trợ theo phiên bản). Không viết:

```javascript
// Không đúng cách để "lọc trước" $search.
db.products.aggregate([
  { $match: { status: "ACTIVE" } },
  { $search: { index: "products_text_v1", text: {
    query: "tai nghe", path: "title"
  } } }
]);
```

Thay vào đó:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      compound: {
        must: [
          { text: { query: "tai nghe", path: "title" } }
        ],
        filter: [
          { equals: { path: "status", value: "ACTIVE" } }
        ]
      }
    }
  },
  { $limit: 10 }
]);
```

Điều kiện filter bên trong `$search` cần field mapping/operator phù hợp. Nếu filter đặt sau `$limit`, có thể không lấy được top K hợp lệ mà nghiệp vụ mong muốn.

## 17. Đánh giá online: CTR, conversion và A/B test

### 17.1. Chỉ số offline không phải kết quả cuối

Một index mới có thể tăng nDCG trên bộ query có nhãn nhưng khiến người dùng:

- không hiểu cách sắp xếp;
- không thấy kết quả quen thuộc;
- click nhiều hơn vì title hấp dẫn nhưng không phù hợp;
- phải reformulate query nhiều lần;
- gặp latency cao hơn;
- thấy sản phẩm đã ngừng bán do freshness kém.

Vì vậy sau offline evaluation cần kiểm tra **online user outcomes** với guardrails.

### 17.2. Những metric online thường dùng

| Metric | Mô tả | Cần thận trọng |
| --- | --- | --- |
| CTR@K | Tỷ lệ click kết quả trong top K | Bị position bias, không phải nhãn relevance trực tiếp |
| Search success rate | Tỷ lệ session hoàn thành mục tiêu định nghĩa | Phải xác định thế nào là thành công |
| Query reformulation rate | Tỷ lệ người dùng sửa query ngay | Có thể tăng vì exploratory search hợp lệ |
| No-results rate | Query trả 0 hit | Zero đúng với query không có dữ liệu |
| Add-to-cart/conversion | Hành động nghiệp vụ sau search | Bị ảnh hưởng giá, tồn kho, UX và chiến dịch |
| Abandonment rate | Rời bỏ luồng search | Có thể do đã đọc đủ thông tin không cần click |
| p95/p99 latency | Hiệu năng | Không phản ánh độ đúng ranking |
| Freshness probe rate | Tỷ lệ thay đổi visible đúng SLO | Đo với sentinel/expected membership |

Không dùng **CTR đơn độc** để khẳng định ranking mới tốt: người dùng có xu hướng click vị trí đầu, và việc tăng click có thể đến từ một thay đổi giao diện.

### 17.3. A/B test công bằng

So hai index:

```text
Control: index products_text_v1
Treatment: index products_text_v2
```

Quy trình:

1. Đảm bảo hai index queryable và dữ liệu/mốc thời gian so sánh hợp lý.
2. Chia traffic theo session/user bằng cách ổn định, tránh người dùng bị đổi phiên bản liên tục.
3. Giữ UI, bộ lọc và định nghĩa success nhất quán giữa hai nhóm.
4. Ghi index/query version cùng các sự kiện impression/click.
5. Theo dõi freshness và latency guardrails.
6. Đánh giá theo phân khúc query (head/long-tail, tiếng Việt có dấu, SKU).
7. Xác định tiêu chí kết thúc và mức tin cậy/thống kê phù hợp.

Nếu treatment có dữ liệu lập chỉ mục **chưa xây xong** hoặc freshness kém hơn, số liệu conversion không phản ánh riêng chất lượng analyzer.

### 17.4. Logging có bảo vệ riêng tư

Một record quan sát có thể gồm:

```json
{
  "requestId": "req-308-example",
  "indexVersion": "products_text_v2",
  "queryCategory": "generic-product",
  "latencyMs": 47,
  "returnedCount": 10,
  "topDocumentIds": ["P-1", "P-2"],
  "hadClick": true,
  "hadConversion": false
}
```

Trong hệ thống thật, query text có thể chứa PII, số điện thoại, địa chỉ, bí mật hoặc bệnh lý. Hãy:

- giới hạn lưu query raw;
- mask/tokenize phù hợp;
- dùng retention và RBAC;
- không đưa thông tin cá nhân vào metric labels;
- bảo đảm phân quyền khi chia sẻ search relevance judgments.

## 18. Triển khai index/analyzer mới an toàn

### 18.1. Không sửa production index rồi hy vọng

Ví dụ cần thay analyzer cho tiếng Việt hoặc thêm field `keywords`. Một cách triển khai dễ kiểm soát hơn:

```text
products_text_v1  <-- đang phục vụ 100% traffic
      |
      | tạo song song
      v
products_text_v2  <-- building / indexing
      |
      | queryable + smoke tests + quality/freshness checks
      v
canary 1% -> 10% -> 50% -> 100%
      |
      v
giữ v1 trong cửa sổ rollback rồi mới cleanup
```

Các tỷ lệ là ví dụ; kế hoạch triển khai thực tùy tải, SLO, chi phí và khả năng routing hai index.

### 18.2. Checkpoint trước cutover

Trước khi chuyển traffic:

- `v2` đã queryable.
- Khảo sát index build errors/mapping warnings.
- Smoke queries trả đúng document theo ID/search term.
- Tập golden queries đạt ngưỡng relevance đặt trước.
- Freshness probe đạt SLO minh họa hoặc mục tiêu thực.
- Query latency và resource usage đủ an toàn.
- Ứng dụng có thể chọn tên index theo config/feature flag.
- Quy trình quay lại `v1` đã được thử trên staging.

“Index ready” là **điều kiện cần**, không phải điều kiện đủ.

### 18.3. Rollback phải quay cả query version

Đổi analyzer/index mapping đôi khi đi kèm đổi query shape:

```text
v1: text title + description
v2: autocomplete title + synonyms + boosted title
```

Nếu chỉ đổi tên index về v1 nhưng vẫn chạy operator `autocomplete` trên field không được mapping tương ứng, rollback có thể thất bại.

Do đó cần quản lý **cặp version**:

```text
searchConfigVersion = {
  indexName,
  queryTemplateVersion,
  analyzerContractVersion,
  scoreSettings
}
```

Chuyển lại một cấu hình nhất quán, không chỉ đổi một string.

### 18.4. Chi phí giữ hai index

Trong giai đoạn chuyển đổi, cả v1 và v2 có thể cùng sử dụng:

- dung lượng index;
- CPU để xử lý cập nhật;
- memory/cache và I/O;
- độ trễ index visibility;
- chi phí dịch vụ managed.

Nếu cluster đang tải cao, việc xây v2 có thể khiến freshness v1 bị ảnh hưởng. Phải có capacity headroom, theo dõi và thời điểm triển khai phù hợp.

### 18.5. Dừng/rollback khi metrics xấu

Một số điều kiện rollback có thể được đặt trước:

- search errors tăng vượt guardrail;
- freshness p95 vượt mục tiêu trong khoảng đáng kể;
- no-results rate tăng bất thường trên query phổ biến;
- nDCG/MRR regression vượt ngưỡng;
- p99 latency ảnh hưởng API SLA;
- tài nguyên Search cạn.

Không đợi tới khi conversion giảm mạnh trong nhiều ngày mới quay lại nếu đã có **tín hiệu lỗi rõ ràng** và xác minh được.

## 19. Bài thực hành `mongosh`: tạo probe và đo search visibility

### 19.1. Điều kiện

**Phải có deployment hỗ trợ MongoDB Search**, ví dụ một cụm Atlas test đã bật tính năng tương ứng. Một `mongod` standalone cục bộ thông thường **không tự hỗ trợ `$search` và Search indexes** chỉ vì có MongoDB server.

Ví dụ dưới đây:

- dùng database lab;
- tạo **collection có tên riêng cho mỗi lượt**;
- tạo một Search index có tên riêng;
- chỉ ghi dữ liệu giả lập;
- dùng `_id` và `runId` để truy vấn/dọn an toàn;
- không tác động production search indexes.

Nếu không có môi trường MongoDB Search test, bạn có thể đọc cú pháp và nguyên lý mà **không chạy DDL**; không tự bật dịch vụ/tạo resources trên tài khoản tính phí nếu chưa được cấp quyền.

### 19.2. Kết nối đúng cluster và tạo namespace duy nhất

URI minh họa:

```bash
mongosh "mongodb+srv://<test-cluster-host>/" 
```

Trong shell đã xác thực:

```javascript
const lab = db.getSiblingDB("mongo_search_row308_lab");
const runId = "row308-" + new ObjectId().toHexString();
const collectionName = "products_" + runId.replaceAll("-", "_");

if (lab.getCollectionNames().includes(collectionName)) {
  throw new Error("Namespace đã tồn tại; không ghi đè.");
}

lab.createCollection(collectionName);
const products = lab.getCollection(collectionName);
const searchIndexName = "row308_text_v1";

print("database=" + lab.getName());
print("collection=" + products.getName());
print("runId=" + runId);
```

Nếu phiên bản `mongosh`/runtime không hỗ trợ `replaceAll`, có thể dùng `runId.replace(/-/g, "_")`. Mục đích là tạo collection riêng và tránh thay đổi collection có trước.

### 19.3. Tạo Search index dành riêng cho lab

```javascript
products.createSearchIndex(
  searchIndexName,
  {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" },
        description: { type: "string" },
        tenantId: { type: "token" },
        status: { type: "token" },
        probeToken: { type: "token" }
      }
    }
  }
);
```

Ở MongoDB Search phiên bản phù hợp, mapping `token` được dùng cho `equals` trên chuỗi đơn. Nếu môi trường của bạn có giới hạn operator/mapping khác, cần điều chỉnh theo tài liệu **trước khi chạy**, không biến thử nghiệm thành thay đổi production.

Trạng thái xây dựng index:

```javascript
printjson(
  products.getSearchIndexes(searchIndexName)
);
```

**Không chạy ngay `$search` rồi kết luận lỗi** nếu index chưa queryable. Kiểm tra kết quả trạng thái được server trả về. Việc index ban đầu cần thời gian là một phần của vận hành, khác với độ trễ đồng bộ những ghi phát sinh sau khi index đã sẵn sàng.

### 19.4. Ghi một document có marker duy nhất

Sau khi index đã đủ điều kiện truy vấn:

```javascript
const probeId = new ObjectId();
const probeToken = "probe-" + probeId.toHexString();
const testTenantId = runId;

const writeStart = new Date();
const writeResult = products.insertOne(
  {
    _id: probeId,
    runId,
    tenantId: testTenantId,
    status: "ACTIVE",
    probeToken,
    title: "Tai nghe thử nghiệm Search",
    description: "Document dùng để đo độ mới của chỉ mục",
    version: 1,
    createdAt: new Date(),
    updatedAt: new Date()
  },
  {
    writeConcern: { w: "majority", wtimeout: 10000 }
  }
);
const writeAcknowledgedAt = new Date();

printjson({
  writeResult,
  writeStart,
  writeAcknowledgedAt,
  probeId,
  probeToken
});
```

`writeAcknowledgedAt` được ghi ở client sau khi có phản hồi. Đây là phép đo **trên phía client**, bao gồm network latency; không phải timestamp nội bộ chính xác của MongoDB Search.

Nếu nhận write concern timeout, **không tự coi insert chắc chắn thất bại**. Dùng `_id`/`runId` để đối soát trước khi thử lại với ID khác.

### 19.5. Đọc nguồn MongoDB bằng ID

```javascript
printjson(
  products.findOne({
    _id: probeId,
    runId
  })
);
```

Khi câu lệnh này thấy document, biết rằng dữ liệu nguồn tồn tại theo lựa chọn đọc đang dùng. Nhưng vẫn chưa chứng minh Search index có thể tìm nó.

### 19.6. Truy vấn Search bằng token chính xác

```javascript
function findProbeInSearch() {
  return products.aggregate([
    {
      $search: {
        index: searchIndexName,
        compound: {
          filter: [
            {
              equals: {
                path: "probeToken",
                value: probeToken
              }
            },
            {
              equals: {
                path: "tenantId",
                value: testTenantId
              }
            }
          ]
        }
      }
    },
    { $limit: 5 },
    {
      $project: {
        _id: 1,
        probeToken: 1,
        title: 1,
        version: 1
      }
    }
  ]).toArray();
}

printjson(findProbeInSearch());
```

Nếu mảng rỗng ngay sau insert, có thể index chưa visible hoặc mapping/query đang lỗi. Hãy kiểm tra index readiness và query configuration trước khi diễn giải là lag.

### 19.7. Poll có giới hạn để đo thời gian nhìn thấy

Chỉ trong cluster test đã được phép, một đoạn poll **có thời hạn**:

```javascript
let firstObservedAt = null;
let lastProbeError = null;
const maxAttempts = 30;
const pollIntervalMillis = 500;

for (let attempt = 0; attempt < maxAttempts; attempt++) {
  try {
    const hits = findProbeInSearch();
    const found = hits.some(
      (doc) => doc._id.toHexString() === probeId.toHexString()
    );
    if (found) {
      firstObservedAt = new Date();
      break;
    }
  } catch (error) {
    lastProbeError = {
      name: error.name,
      message: error.message
    };
    break;
  }

  sleep(pollIntervalMillis);
}

printjson({
  firstObservedAt,
  observedVisibilityLagMs:
    firstObservedAt
      ? firstObservedAt.getTime() -
        writeAcknowledgedAt.getTime()
      : null,
  pollIntervalMillis,
  lastProbeError,
  timedOutWithoutVisibility:
    !firstObservedAt && !lastProbeError
});
```

Giải thích:

- Vòng lặp dừng sớm khi thấy đúng document.
- Tối đa 30 lần với khoảng nghỉ 500 ms là **một phép thử ngắn**, không phải mục tiêu SLO mặc định.
- Nếu timeout, kết quả là **“chưa quan sát thấy trong cửa sổ thử”**, không tự động là “Search đã mất dữ liệu”.
- Nếu query lỗi, ghi nhận error riêng; không trộn vào histogram visibility lag như thể có một thời gian hợp lệ.
- Polling có thể bỏ qua mốc index thật sự trở nên visible ở giữa hai lần kiểm tra.
- Không chạy hàng nghìn probe đồng thời khiến chính hệ thống Search bị thêm tải.

### 19.8. Đo update freshness tách khỏi insert

Một thử nghiệm update:

```javascript
const newTitle = "Máy chiếu bỏ túi đặc biệt row308";

const updated = products.updateOne(
  { _id: probeId, runId, version: 1 },
  {
    $set: {
      title: newTitle,
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);

printjson(updated);
```

Để quan sát index đã cập nhật title, chạy query `text` có điều kiện tên mới và **giới hạn đúng probe**:

```javascript
const updatedHits = products.aggregate([
  {
    $search: {
      index: searchIndexName,
      compound: {
        must: [
          {
            text: {
              query: "máy chiếu bỏ túi",
              path: "title"
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "probeToken",
              value: probeToken
            }
          }
        ]
      }
    }
  },
  { $limit: 5 },
  { $project: { title: 1, version: 1 } }
]).toArray();

printjson(updatedHits);
```

Nếu document nguồn đã là version 2 mà `updatedHits` còn rỗng, có thể Search chưa cập nhật token mới. Khi Search tìm được đúng token/title mới, điều đó là một **tín hiệu update visibility**.

Muốn đo chính xác độ trễ update, lưu `updatedAcknowledgedAt` ngay khi update thành công rồi dùng một vòng polling giống phần insert, nhưng điều kiện match phải phản ánh **từ khóa mới**; không chỉ đọc field `version:2` vì document fetch có thể mới trong khi index membership vẫn cũ.

### 19.9. Dọn đúng dữ liệu thử nghiệm

Trước khi xóa:

```javascript
print("database=" + lab.getName());
print("collection=" + products.getName());
print("runId=" + runId);

printjson(
  products.findOne(
    { _id: probeId, runId },
    { title: 1, probeToken: 1, runId: 1 }
  )
);
```

Nếu đúng document bạn tạo:

```javascript
const removed = products.deleteOne({
  _id: probeId,
  runId
});

printjson(removed);
print(
  "remaining=" +
    products.countDocuments({ _id: probeId, runId })
);
```

Việc xóa document cũng cần được đồng bộ tới Search index, nên một search query ngay sau delete **không tự chứng minh index đã cập nhật**. Đừng tự xóa index hoặc drop database khi có khả năng namespace được chia sẻ.

Collection và Search index của lab có thể còn tồn tại sau khi dọn document. Với hạ tầng có tính phí, người được giao quản trị cần **thu hồi tài nguyên lab theo quy trình riêng**, chỉ sau khi xác nhận tên namespace/index và quyền sở hữu. Không chạy `dropSearchIndex()` hoặc `dropDatabase()` trên môi trường dùng chung chỉ để “dọn bài học”.

## 20. Thử nghiệm native `$text` để phân biệt với MongoDB Search

Trong một collection **khác** trên MongoDB test (không trùng index/namespace của lab Search), tạo:

```javascript
const nativeDb = db.getSiblingDB("mongo_search_row308_lab");
const nativeColl = nativeDb.getCollection(
  "native_text_" + new ObjectId().toHexString()
);

nativeDb.createCollection(nativeColl.getName());

nativeColl.createIndex({
  title: "text",
  description: "text"
});

const nativeId = new ObjectId();

nativeColl.insertOne({
  _id: nativeId,
  title: "Tai nghe Bluetooth",
  description: "Sản phẩm mô phỏng cho native text search"
});

printjson(
  nativeColl.find(
    { $text: { $search: "Bluetooth" } },
    {
      title: 1,
      textScore: { $meta: "textScore" }
    }
  ).sort({
    textScore: { $meta: "textScore" }
  }).toArray()
);
```

Điểm khác:

- Đã dùng `createIndex({title:"text"})`, **không phải `createSearchIndex()`**.
- Query dùng `$text`, không dùng `$search`.
- Score đọc qua `textScore`, không phải `searchScore`.
- Độ mới khi đọc từ primary theo cơ chế database index, không có vòng đồng bộ Search service riêng giống MongoDB Search.
- Nếu query được điều hướng tới secondary, cần xét replication lag và read preference.

Chỉ dọn đúng record thử:

```javascript
nativeColl.deleteOne({ _id: nativeId });
```

Không drop một collection bất kỳ vì tên giống ví dụ. Namespace tạo riêng có thể được thu hồi theo quy trình lab sau khi kết thúc và xác minh quyền sở hữu.

## 21. Kết hợp relevance evaluation vào CI/CD và quy trình vận hành

### 21.1. Trước khi deploy index mới

Một pipeline kỹ thuật có thể:

1. Chạy query templates trên staging index với dữ liệu ổn định.
2. Lấy top K document IDs và search scores.
3. So với golden judgments.
4. Tính P@K, MRR@K, nDCG@K, Hit@K theo loại query.
5. Chạy freshness probes insert/update/delete.
6. Đo query p95/p99 trên workload đại diện.
7. Xác nhận không có regression về tenant isolation và kết quả inactive.
8. Xuất báo cáo so sánh **v1 vs v2**.

Đừng cho script test sửa index production khi chạy CI; cần môi trường và quyền tách biệt.

### 21.2. Một báo cáo so sánh minh họa

| Chỉ số | v1 | v2 | Đánh giá cần làm |
| --- | ---: | ---: | --- |
| nDCG@10 (offline) | 0,72 | 0,79 | Có thể cải thiện ranking |
| MRR@5 (SKU queries) | 0,94 | 0,88 | Regression ở query chính xác |
| Recall@10 (synonym queries) | 0,61 | 0,78 | Có thể tăng recall |
| No-results rate | 8,0% | 6,2% | Cần xác định ít kết quả rỗng có thực sự tốt |
| Search p95 latency | 75 ms | 105 ms | Query chậm hơn |
| Visibility p95 | 4 s | 9 s | Freshness kém đi |
| Index storage | 18 GiB | 29 GiB | Chi phí tăng |

Các số chỉ là **ví dụ giả định**. Tình huống này **không tự động có nghĩa v2 tốt hơn**, dù nDCG và Recall tăng. Nếu API yêu cầu SKU exact matching và sản phẩm vừa tạo phải tìm được trong 5 giây, các regression về MRR SKU/freshness có thể là blocker.

### 21.3. Không tính toán từ tập dữ liệu không tương đương

Nếu v1 chạy trên snapshot sáng thứ Hai, v2 chạy trên dữ liệu sáng thứ Ba có thêm 10% sản phẩm, metric ranking không thể so sánh trực tiếp mà không điều chỉnh.

Để so:

- cùng query set;
- cùng relevancy judgments;
- cùng phiên bản dữ liệu hoặc phương án đối chiếu;
- cùng filter business;
- cùng cutoff K và quy tắc metric;
- cùng điều kiện latency load test hoặc ghi nhận khác biệt.

Khi dữ liệu thực luôn thay đổi, cần một **offline corpus ổn định** cộng thêm **online evaluation** để tránh kết luận dựa trên dữ liệu lệch.

### 21.4. Post-deploy verification

Sau khi chuyển traffic, cần:

```text
Index queryable?
       |
       v
Smoke queries correct?
       |
       v
Freshness probes within SLO?
       |
       v
Latency and errors within guardrails?
       |
       v
Offline + online quality acceptable?
       |
       v
Continue rollout / keep observing
```

Nếu một bước thất bại, xem nguyên nhân và **rollback canary** khi cần; không tiếp tục tăng traffic chỉ vì index status báo READY.

## 22. Runbook khi Search chậm cập nhật hoặc kết quả giảm chất lượng

### 22.1. Trường hợp A — Freshness tăng chậm nhưng query vẫn nhanh

Giả sử:

```text
Search query p95: 55 ms
Insert visibility p95: 45 giây
Previous visibility p95: 4 giây
MongoDB write QPS: tăng gấp 5
```

Hướng điều tra:

1. Xác nhận probe query hợp lệ và có đủ số mẫu.
2. Xem write rate, loại updates và tài nguyên search nodes.
3. Kiểm tra có index rebuild/migration không.
4. Kiểm tra trạng thái index, indexing error hoặc backlog nếu metric có sẵn.
5. Giảm tốc **batch không cấp thiết** khi được phép.
6. Cân nhắc capacity/mapping index theo dữ liệu đo được.
7. Không tăng polling QPS vô hạn vì sẽ làm search thêm tải.

### 22.2. Trường hợp B — Query latency tăng nhưng freshness bình thường

```text
Query p95: tăng từ 80 ms lên 400 ms
Visibility p95: giữ ở 3 giây
```

Hướng điều tra:

- Query pattern mới dùng fuzzy quá rộng?
- Có `$searchMeta` total count đắt đỏ không?
- Có `$limit` quá lớn hoặc pagination quá sâu?
- Có query đang quét/return nhiều field?
- Search QPS/CPU/cache/network tăng?
- API có gọi thêm service khác/caches bị miss?

Không đổi cấu hình indexing chỉ vì latency query cao nếu nguyên nhân là truy vấn mới hoặc tầng API.

### 22.3. Trường hợp C — No-results tăng sau thay analyzer

```text
Index v1: query "dien thoai" trả kết quả tốt
Index v2: query đó trả rỗng
```

Hướng điều tra:

1. Xác minh v2 đã queryable và đủ freshness.
2. So field mapping và analyzer.
3. So query template/operator giữa hai version.
4. Kiểm tra Unicode/diacritics normalization.
5. So golden queries có dấu/không dấu.
6. Đánh giá rollback v1 nếu có regression rõ.

Đừng khắc phục bằng cách tự động bỏ mọi dấu trên mọi field khi chưa đánh giá false positives.

### 22.4. Trường hợp D — Search trả tài liệu không còn được phép hiển thị

Ưu tiên:

1. Ngăn rò rỉ bằng **authorization/filter authoritative** trước khi trả response.
2. Xác nhận document nguồn và quyền hiện hành.
3. Kiểm tra trạng thái search index và độ trễ update/delete.
4. Kiểm tra cache phía API/UI.
5. Xem liệu cần purge cache hoặc tạm vô hiệu hóa một loại search result.
6. Ghi nhận sự cố bảo mật theo quy trình tổ chức.

Không xem đây chỉ là “relevance hơi kém”; có thể là vấn đề quyền riêng tư.

### 22.5. Trường hợp E — Build index mới thất bại

Các câu hỏi:

- Definition có field mapping/analyzer không hợp lệ không?
- Có tài nguyên CPU/memory/storage cần thiết không?
- Namespace/index name đúng không?
- Deployment/tier/server version có hỗ trợ operator đang dùng?
- Có đang chạy một DDL/index change khác không?
- Có dữ liệu BSON bất thường làm mapper lỗi không?

Không drop index cũ đang phục vụ chỉ vì index mới build failed. Sửa index mới trên staging, sau đó chạy lại theo rollout plan.

## 23. Những sai lầm thường gặp

| Sai lầm | Thực tế và cách khắc phục |
| --- | --- |
| “Write majority thành công thì `$search` phải thấy ngay” | MongoDB Search index cập nhật bất đồng bộ; cần đo visibility riêng |
| “Native `$text` và MongoDB Search là một loại index” | Hai cơ chế và cú pháp khác nhau |
| “Index READY nghĩa mọi ghi mới đã được lập chỉ mục” | READY/queryable không chứng minh lag bằng 0 |
| “`findOne` thấy tên mới thì Search index đã cập nhật” | Document nguồn có thể mới hơn token/search membership |
| “Search không thấy thì dữ liệu chắc chắn mất” | Có thể do lag, analyzer, mapping, filter, tenant hoặc cache |
| “Search thấy tên mới thì search membership đã mới” | Field trả về có thể được fetch từ collection trong khi index match theo nội dung cũ |
| “Cứ poll mỗi 1 ms để giảm lag” | Polling không làm index cập nhật nhanh hơn; chỉ tăng tải |
| “Lag đo bằng timestamp document updatedAt là chính xác” | Client clock, ghi retry, polling interval và network gây sai lệch |
| “Chỉ đo insert là đủ cho freshness” | Update/delete có hành vi và rủi ro khác |
| “Chỉ đo search p95 latency là biết search khỏe” | Relevance và freshness có thể kém dù query nhanh |
| “No-results rate càng thấp càng tốt” | Query không có tài liệu relevant cần trả rỗng đúng |
| “CTR tăng chắc chắn relevance tăng” | Position bias, UI và giá cả ảnh hưởng CTR |
| “Recall@K tính bằng top K đã tự gắn nhãn” | Cần biết/ước lượng đủ tốt tập relevant; tránh tự cho document chưa đánh giá là không relevant |
| “searchScore là xác suất sản phẩm đúng” | Score phục vụ ranking, không phải xác suất được hiệu chỉnh |
| “Boost lớn luôn tăng chất lượng” | Có thể đẩy kết quả không phù hợp lên đầu |
| “Bỏ dấu tiếng Việt luôn tốt” | Có thể tăng false positives; phải đo precision/recall |
| “Fuzzy càng rộng càng tốt” | Query ngắn có thể trở nên rất nhiễu và chậm |
| “Tạo v2 xong chuyển traffic ngay” | Phải đợi queryable, kiểm freshness/quality/latency |
| “Rollback chỉ cần sửa indexName” | Query template/operator/analyzer cũng phải tương thích v1 |
| “Search filter đủ làm hàng rào phân quyền” | Index có thể stale; xác minh lại quyền từ nguồn authoritative |
| “Search là nơi cưỡng chế uniqueness/tồn kho” | Dùng unique index, atomic writes/transactions ở MongoDB |
| “Một SLO 5 giây là bảo đảm của MongoDB” | SLO là hợp đồng do ứng dụng và vận hành xác lập |
| “Giữ hai index không tốn tài nguyên” | Dual indexing có thể tăng storage, CPU, write/update load |
| “Mọi metric dashboard Atlas có tên giống nhau” | Phải kiểm tra deployment, version, tier và định nghĩa metric |

## 24. Bài tập vận dụng

### Bài A — Phân biệt text index và Search index

Cho:

```javascript
db.products.createIndex({ title: "text" });
db.products.find({ $text: { $search: "bluetooth" } });
```

1. Đây là native text search hay MongoDB Search?
2. Query nào dùng `$search`?
3. Nếu đọc từ secondary, hiện tượng gì có thể ảnh hưởng tính mới?
4. Có thể dùng `getSearchIndexes()` để mô tả index trên không?

### Bài B — Tính visibility lag

Một probe nhận acknowledgment lúc `10:00:00.000`. Poll mỗi 500 ms, lần đầu thấy đúng document lúc `10:00:04.500`.

1. Observed visibility lag là bao nhiêu?
2. Mốc index thực sự cập nhật có chắc bằng `10:00:04.500` không?
3. Vì sao phải gắn một token duy nhất?
4. Nếu query báo lỗi mapping, có nên ghi sample 4,5 giây vào histogram lag không?

### Bài C — Search thấy nội dung “mâu thuẫn”

Document đổi title từ `"Giày chạy bộ"` sang `"Giày đi bộ"`. Query từ `"chạy bộ"` vẫn trả document, nhưng `title` trong output đã là `"Giày đi bộ"`.

1. Tại sao hiện tượng này có thể xảy ra?
2. Vì sao không chỉ đọc `title` để đo index freshness?
3. Nên dùng điều kiện probe nào để xác định token mới đã được search index nhận?

### Bài D — Thiết kế dashboard

Chỉ số:

```text
Query p95 latency:       50 ms (ổn định)
Write throughput:        tăng 6 lần
Search visibility p95:   từ 3 s lên 40 s
Index status:            READY
```

1. Vì sao không thể kết luận Search hoàn toàn khỏe?
2. Cần xem những metric tài nguyên nào?
3. Tại sao index READY không chứng minh dữ liệu mới đã visible?
4. Có nên tăng số probe lên hàng nghìn query/s ngay lúc này không?

### Bài E — Precision và Recall

Top 5 relevance nhị phân:

```text
Rank:      1  2  3  4  5
Relevant:  1  0  1  0  1
```

Toàn bộ tập xét có **4** tài liệu relevant.

1. Tính Precision@5.
2. Tính Recall@5.
3. Vì sao hai số đo khác nhau?
4. Nếu một document chưa được gắn nhãn, có nên tự gán 0 không?

### Bài F — MRR và nDCG

Một query có các nhãn relevance:

```text
Ranking A: 3, 1, 0, 2, 0
Ranking B: 3, 2, 1, 0, 0
```

1. MRR của hai ranking khác nhau không nếu relevant đầu tiên đều ở rank 1?
2. Vì sao nDCG có thể đánh giá B tốt hơn A?
3. Nếu mục tiêu chỉ là tìm một mã sản phẩm đúng, metric nào có thể quan trọng hơn?

### Bài G — Tiếng Việt có và không dấu

Tạo tập query pairs:

```text
"điện thoại" / "dien thoai"
"máy lọc không khí" / "may loc khong khi"
"cà phê" / "ca phe"
```

Hãy đề xuất quy trình đo Recall@10, P@10 và no-results trước/sau thay analyzer. Vì sao chỉ đo “số hit tăng” không đủ chứng minh cải tiến?

### Bài H — Thay index v1 sang v2

Index v2 cải thiện nDCG@10 từ 0,72 lên 0,79 nhưng query p95 tăng từ 75 ms lên 105 ms và visibility p95 từ 4 s lên 9 s.

1. Có nên chuyển ngay 100% traffic không?
2. Cần xem SLO nào?
3. Hãy thiết kế rollout canary và điều kiện rollback.
4. Vì sao phải version cả query template?

### Bài I — Quyền truy cập và index stale

Một document chứa thông tin nội bộ vừa đổi `visibility:"PUBLIC"` sang `"PRIVATE"`. `$search` vẫn trả nó với filter PUBLIC trong vài giây.

1. Đây có thể là lỗi freshness hay relevance?
2. Vì sao không được gửi snippet/highlight trước khi kiểm tra quyền?
3. Nguồn nào phải là authoritative để quyết định có trả document?
4. Cần ghi nhận metric và loại sự cố gì?

### Bài J — Tách search lag khỏi cache lag

`findOne` thấy bản mới; `$search` trong `mongosh` cũng thấy bản mới; API web vẫn hiển thị bản cũ 30 giây.

1. Khả năng nguyên nhân nằm ở đâu?
2. Metric nào giúp phân biệt?
3. Có nên tăng CPU Search nodes ngay không?
4. Làm thế nào để đo thời gian từ **Search visible** đến **UI visible**?

## 25. Tài liệu tham khảo chính thức

Các chi tiết phụ thuộc **MongoDB server/Atlas Search version, index mappings, loại deployment và driver**. Tham khảo tài liệu của đúng phiên bản đang chạy:

- [MongoDB Search Overview](https://www.mongodb.com/docs/atlas/atlas-search/) — kiến trúc và khả năng tìm kiếm văn bản.
- [Create a MongoDB Search Index](https://www.mongodb.com/docs/atlas/atlas-search/create-index/) — định nghĩa, tạo và quản lý index.
- [MongoDB Search Index Field Types](https://www.mongodb.com/docs/atlas/atlas-search/field-types/) — mapping field và lựa chọn kiểu.
- [`$search` Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/search/) — cú pháp query và các operator.
- [`$searchMeta` Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/searchMeta/) — metadata/count/facets theo khả năng hỗ trợ.
- [MongoDB Search Score](https://www.mongodb.com/docs/atlas/atlas-search/scoring/) — relevance scoring và tùy chọn boost.
- [MongoDB Search Analyzers](https://www.mongodb.com/docs/atlas/atlas-search/analyzers/) — analyzer/tokenization.
- [MongoDB Search Synonyms](https://www.mongodb.com/docs/atlas/atlas-search/synonyms/) — quản lý từ đồng nghĩa.
- [`db.collection.getSearchIndexes()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.getSearchIndexes/) — xem Search indexes theo phiên bản.
- [`db.collection.createSearchIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createSearchIndex/) — tạo Search index nơi được hỗ trợ.
- [Text Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/) — native MongoDB text index.
- [`$text` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/) — truy vấn native text search.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — phân biệt write acknowledgment với search visibility.

Tên sản phẩm, trang tài liệu và trường metrics có thể được tổ chức lại giữa các release; khi xây runbook sản xuất phải xác minh **semantics cụ thể của phiên bản và dịch vụ** thay vì coi mọi ví dụ ở đây là hợp đồng API bất biến.

## 26. Kết luận

**MongoDB Search index** phục vụ tìm kiếm toàn văn với analyzer, relevance và các chức năng chuyên dụng, nhưng dữ liệu trong search index có thể **chậm hơn** dữ liệu vừa được ghi vào MongoDB. **Write acknowledgment**, **index queryable status**, **search visibility** và **UI freshness** là những khái niệm khác nhau. Một write majority thành công không tự buộc `$search` phải thấy ngay document mới.

Để vận hành có trách nhiệm, hãy đo **insert/update/delete visibility lag** bằng marker duy nhất và polling có deadline, giám sát đồng thời index lifecycle, độ trễ truy vấn, tài nguyên, lỗi và cache. Khi kết quả bất thường, xác minh dữ liệu nguồn, mapping, analyzer, query filter và index version trước khi kết luận Search bị chậm cập nhật.

Chất lượng tìm kiếm không chỉ là có hit hay không. Một hệ thống tốt phải vừa **tìm được kết quả liên quan**, vừa **xếp các kết quả quan trọng lên cao**, **cập nhật đủ mới** và **phục vụ đúng hạn**. Dùng Precision@K, Recall@K, MRR, nDCG, golden query sets và chỉ số online để đo thay đổi; đặc biệt kiểm tra từ khóa tiếng Việt, dấu, synonyms, typo và mã sản phẩm. Triển khai index mới bằng quy trình versioning, canary và rollback, không chỉ bằng một lần tạo index rồi chuyển toàn bộ traffic.

**Thông điệp cốt lõi:** “Search index đã sẵn sàng” không đồng nghĩa “mọi dữ liệu vừa ghi đã tìm thấy”, và “query nhanh” không đồng nghĩa “kết quả tốt”. Search đáng tin cậy cần đo **freshness, relevance, latency và tính đúng đắn nghiệp vụ** cùng lúc.

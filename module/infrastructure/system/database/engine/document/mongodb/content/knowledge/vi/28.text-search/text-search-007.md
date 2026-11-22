# Truy vấn tìm kiếm, lọc, fuzzy, autocomplete và xếp hạng trong MongoDB

## 1. Bài toán tìm kiếm văn bản trong ứng dụng

Một cửa hàng lưu sản phẩm:

~~~javascript
{
  _id: "P-100",
  tenantId: "store-a",
  title: "Chuột không dây M100",
  description: "Chuột Bluetooth nhỏ gọn, kết nối ổn định",
  category: "mouse",
  priceCents: 250000,
  active: true
}
~~~

Người dùng có thể muốn tìm kiếm theo nhiều cách:

- Nhập **"chuột không dây"** để tìm tiêu đề và mô tả.
- Gõ sai **"bluetooh"** nhưng vẫn mong thấy sản phẩm Bluetooth.
- Nhập **"chu"** và muốn nhận gợi ý ngay khi đang gõ.
- Chọn danh mục, giới hạn khoảng giá, chỉ xem hàng đang bán.
- Xếp kết quả khớp tiêu đề lên trên kết quả chỉ xuất hiện trong mô tả.
- Phân trang, tô sáng đoạn văn khớp, xem bộ lọc danh mục có bao nhiêu sản phẩm.
- Bảo đảm user thuộc **store-a** không thấy sản phẩm riêng của **store-b**.

Một lệnh find chính xác không đáp ứng tất cả những yêu cầu đó. MongoDB cung cấp hai hướng cần phân biệt:

1. **Text index truyền thống với $text**, hỗ trợ tìm từ khóa và textScore ở mức cơ bản.
2. **MongoDB Search** (còn được biết dưới tên Atlas Search trong nhiều tài liệu): Search indexes và các aggregation stages **$search**/**$searchMeta**, có relevance scoring, compound queries, fuzzy, autocomplete, highlight và facets.

Bài này tập trung vào cách tạo trải nghiệm tìm kiếm với **MongoDB Search**, đồng thời so sánh với find, regex và $text. Các tính năng MongoDB Search yêu cầu **deployment hỗ trợ Search**, không phải mọi mongod standalone chỉ vì đã tạo text index.

### Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt tìm chính xác, regex, full-text và fuzzy matching.
2. Thiết kế Search index cho full-text, autocomplete và các filters.
3. Kết hợp **text, phrase, compound.must/should/filter/mustNot**.
4. Tùy chỉnh fuzzy, autocomplete và điểm relevance.
5. Xây phân trang, highlights, facets và thứ tự kết quả.
6. Áp dụng filter theo tenant và phân quyền an toàn.
7. Viết ví dụ mongosh, Java Sync Driver và Spring Data MongoDB.
8. Đo chất lượng tìm kiếm, latency và vận hành index trong production.

## 2. Exact match, regex, $text và $search

### 2.1. Exact match

~~~javascript
db.products.find({
  tenantId: "store-a",
  title: "Chuột không dây M100"
});
~~~

Đây là phép so sánh giá trị, có thể tận dụng index thông thường. Nó không tự hiểu từ đồng nghĩa, lỗi gõ hay relevance. Collation có thể thay đổi quy tắc so sánh chuỗi nhưng không biến exact match thành full-text search.

### 2.2. Regex

~~~javascript
db.products.find({
  title: {
    $regex: "^Chuột",
    $options: "i"
  }
});
~~~

Regex hữu ích cho patterns đơn giản, nhưng không cung cấp tokenization/word relevance/BM25/autocomplete chuyên dụng. Unanchored và case-insensitive regex có thể tốn tài nguyên; không nên cho user điều khiển regex tùy ý.

### 2.3. $text truyền thống

~~~javascript
db.products.createIndex(
  {
    title: "text",
    description: "text"
  },
  {
    weights: {
      title: 10,
      description: 2
    }
  }
);

db.products.find(
  {
    tenantId: "store-a",
    $text: {
      $search: "wireless bluetooth"
    }
  },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
});
~~~

Đây là **MongoDB text index**, được tạo bằng createIndex, khác hoàn toàn với **MongoDB Search index** dành cho $search stage. $text có thể đủ cho tìm kiếm đơn giản, nhưng không thay thế được đầy đủ fuzzy, autocomplete, facets, highlights và ranking controls của MongoDB Search.

### 2.4. $search

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "chuột không dây",
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
~~~

Trong aggregation pipeline thông thường, **$search phải là stage đầu tiên**. Không đặt $match trước $search để kỳ vọng nó chạy Search trên dữ liệu đã lọc. Muốn lọc sớm trong Search engine, hãy dùng **compound.filter**.

### 2.5. Bảng so sánh

| Nhu cầu | find / regex | $text | MongoDB Search |
|---|---|---|---|
| Exact ID/status/range | Rất phù hợp. | Kết hợp find. | Filter khi có search. |
| Text relevance | Hạn chế. | Cơ bản. | **Nhiều toán tử và scoring.** |
| Fuzzy typo tolerance | Không sẵn có. | Không phải chức năng chính. | **text/autocomplete fuzzy**. |
| Autocomplete khi gõ | Prefix regex có giới hạn. | Không chuyên dụng. | **autocomplete operator/index**. |
| Highlights | Tự xử lý. | Tự xử lý. | **highlight**. |
| Facets và counts | Aggregation riêng. | Aggregation riêng. | **$searchMeta**. |
| Weighted ranking | Tự viết. | Text weights. | **boost/score functions/compound**. |

## 3. Bộ dữ liệu mẫu cho các truy vấn

Dùng database **mongo_search_lab** trên deployment hỗ trợ MongoDB Search. Những giá trị trong ví dụ là dữ liệu thử nghiệm, không phải sản phẩm thực tế.

~~~javascript
use mongo_search_lab

db.products.insertMany([
  {
    _id: "P-100",
    tenantId: "store-a",
    title: "Chuột không dây M100",
    titleSuggest: "Chuột không dây M100",
    description: "Chuột Bluetooth nhỏ gọn, kết nối ổn định",
    category: "mouse",
    tags: ["bluetooth", "wireless"],
    priceCents: 250000,
    active: true,
    stock: 15,
    popularity: 80,
    publishedAt: ISODate("2026-05-10T08:00:00Z")
  },
  {
    _id: "P-101",
    tenantId: "store-a",
    title: "Chuột gaming RGB G1",
    titleSuggest: "Chuột gaming RGB G1",
    description: "Chuột chơi game có dây, cảm biến chính xác",
    category: "mouse",
    tags: ["gaming", "rgb"],
    priceCents: 390000,
    active: true,
    stock: 6,
    popularity: 92,
    publishedAt: ISODate("2026-05-11T08:00:00Z")
  },
  {
    _id: "P-102",
    tenantId: "store-a",
    title: "Bàn phím cơ K2",
    titleSuggest: "Bàn phím cơ K2",
    description: "Bàn phím cơ nhỏ gọn, kết nối Bluetooth",
    category: "keyboard",
    tags: ["mechanical", "bluetooth"],
    priceCents: 850000,
    active: true,
    stock: 8,
    popularity: 75,
    publishedAt: ISODate("2026-05-09T08:00:00Z")
  },
  {
    _id: "P-103",
    tenantId: "store-a",
    title: "Tai nghe không dây Air 200",
    titleSuggest: "Tai nghe không dây Air 200",
    description: "Tai nghe Bluetooth với thời lượng pin tốt",
    category: "headphone",
    tags: ["wireless", "audio"],
    priceCents: 620000,
    active: true,
    stock: 0,
    popularity: 88,
    publishedAt: ISODate("2026-05-08T08:00:00Z")
  },
  {
    _id: "P-104",
    tenantId: "store-a",
    title: "Chuột Bluetooth M2",
    titleSuggest: "Chuột Bluetooth M2",
    description: "Chuột không dây êm và nhẹ cho văn phòng",
    category: "mouse",
    tags: ["wireless", "office"],
    priceCents: 320000,
    active: true,
    stock: 22,
    popularity: 67,
    publishedAt: ISODate("2026-05-12T08:00:00Z")
  },
  {
    _id: "P-105",
    tenantId: "store-a",
    title: "Chuột không dây đời cũ",
    titleSuggest: "Chuột không dây đời cũ",
    description: "Sản phẩm đã ngừng kinh doanh",
    category: "mouse",
    tags: ["wireless"],
    priceCents: 180000,
    active: false,
    stock: 0,
    popularity: 30,
    publishedAt: ISODate("2025-12-20T08:00:00Z")
  },
  {
    _id: "P-900",
    tenantId: "store-b",
    title: "Chuột không dây B-Pro",
    titleSuggest: "Chuột không dây B-Pro",
    description: "Mẫu riêng của cửa hàng B",
    category: "mouse",
    tags: ["wireless"],
    priceCents: 280000,
    active: true,
    stock: 12,
    popularity: 100,
    publishedAt: ISODate("2026-05-13T08:00:00Z")
  }
]);
~~~

**Chạy seed một lần trên collection mới.** Chạy lại khi _id đã tồn tại sẽ báo duplicate key. Thứ tự Search results/điểm relevance cụ thể có thể khác theo analyzer, index, corpus và phiên bản công cụ tìm kiếm.

### 3.1. Vì sao có titleSuggest?

Để ví dụ rõ ràng, dữ liệu lưu hai field:

- **title**: mapping full-text **string**.
- **titleSuggest**: mapping **autocomplete** cho cùng nội dung tiêu đề.

Một số cấu hình Search hỗ trợ khai báo **nhiều mapping types trên cùng field** để tránh nhân bản title; ở đây tách field nhằm đơn giản hóa index definition. Khi title thay đổi, ứng dụng phải cập nhật titleSuggest nhất quán.

### 3.2. Quy ước dữ liệu

**tenantId** và **category** là chuỗi định danh chuẩn hóa cho exact filters; **active** là boolean; **priceCents/stock/popularity** là số; **publishedAt** là BSON Date.

Không để client gửi tenantId tùy ý để tự xác nhận phạm vi tìm kiếm. Tenant được lấy từ user identity đã được server xác thực.

## 4. Tạo MongoDB Search index

MongoDB Search dùng **Search index** khác với B-tree index hoặc text index tạo bằng createIndex. Cách quản lý tùy môi trường: MongoDB Atlas UI/API, mongosh hoặc deployment hỗ trợ Search.

### 4.1. Index mapping minh họa

~~~javascript
db.products.createSearchIndex(
  "products_search",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: {
          type: "string",
          analyzer: "lucene.standard"
        },
        titleSuggest: {
          type: "autocomplete",
          tokenization: "edgeGram",
          minGrams: 2,
          maxGrams: 15,
          foldDiacritics: true
        },
        description: {
          type: "string",
          analyzer: "lucene.standard"
        },
        tags: {
          type: "string",
          analyzer: "lucene.standard"
        },
        tenantId: {
          type: "token"
        },
        category: {
          type: "token"
        },
        active: {
          type: "boolean"
        },
        stock: {
          type: "number"
        },
        priceCents: {
          type: "number"
        },
        popularity: {
          type: "number"
        },
        publishedAt: {
          type: "date"
        }
      }
    }
  }
);
~~~

**Lưu ý:** cú pháp createSearchIndex và các mapping options phải được deployment/server version hỗ trợ. Với hệ thống không có MongoDB Search, không thể chỉ thêm index thường rồi chạy $search.

### 4.2. Ý nghĩa mapping

| Field | Mapping | Mục đích |
|---|---|---|
| title | **string** | Full-text ranking, phrase matching. |
| titleSuggest | **autocomplete** | Prefix matching khi user đang gõ. |
| description, tags | **string** | Full-text recall. |
| tenantId, category | **token** | Exact string equality, category facets. |
| active | **boolean** | Chỉ sản phẩm đang bán. |
| stock, priceCents | **number** | Range/equality filters. |
| popularity | **number** | Có thể dùng làm ranking signal. |
| publishedAt | **date** | Filter hoặc boost theo độ mới. |

**dynamic:false** chỉ lập chỉ mục các fields đã khai báo. Cách này giúp kiểm soát Search index size và tránh indexing dữ liệu nhạy cảm ngoài ý muốn.

### 4.3. Token khác analyzed string

**string** thường được tokenizer/analyzer phân tích thành terms, phù hợp với tìm kiếm từ khóa.

**token** dùng cho nguyên giá trị chuỗi như **tenantId = store-a** hoặc **category = mouse**. Nếu dùng analyzer full-text cho tenantId, điều kiện có thể không còn mang ý nghĩa so sánh nguyên giá trị.

Đối với fields tenant, có thể bổ sung normalizer theo quy tắc dữ liệu. Nếu index giữ nguyên hoa/thường, cần nhất quán cách ghi và cách lọc tenantId.

### 4.4. Analyzer cho tiếng Việt

Analyzer quyết định cách:

- Tách chuỗi thành terms.
- Chuẩn hóa chữ hoa/thường và dấu.
- Xử lý Unicode, từ dừng và stemming khi có.
- Đồng bộ quy tắc index time và query time.

**lucene.standard** không có nghĩa tự tách từ tiếng Việt chính xác trong mọi trường hợp. Những chuỗi như **chuột, chuot, điện thoại, dien thoai** phải được test trên corpus thật. Nếu cần tìm không dấu, synonyms hoặc phân tách từ nâng cao, hãy thiết kế analyzer/field chuẩn hóa và bộ đánh giá chất lượng phù hợp.

Fuzzy theo edit distance **không thay thế một bộ xử lý ngôn ngữ tiếng Việt**.

### 4.5. Chờ Search index sẵn sàng

Lập Search index có thể diễn ra **bất đồng bộ**. Trong mongosh có thể kiểm tra:

~~~javascript
db.products.getSearchIndexes();
~~~

Chờ trạng thái Search index có thể phục vụ truy vấn trước khi đánh giá kết quả. Khi index còn build, kết quả truy vấn hoặc thông báo lỗi chưa phản ánh hiệu quả chính thức.

### 4.6. Không nhầm các tên index

~~~text
createIndex({title:"text"})     -> MongoDB text index
createSearchIndex("products_search", definition)
                               -> MongoDB Search index
~~~

Trong $search phải chọn đúng **index:"products_search"**. Index của $text không thay thế index này.

## 5. Truy vấn toàn văn với text operator

### 5.1. Search theo một field

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "Bluetooth",
        path: "title"
      }
    }
  },
  {
    $project: {
      title: 1,
      category: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]);
~~~

MongoDB Search phân tích query bằng analyzer/searchAnalyzer liên quan và đánh giá những documents có terms phù hợp trong title. Không phải toán tử so khớp chuỗi nguyên bản.

### 5.2. Search đồng thời nhiều fields

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "Bluetooth",
        path: [
          "title",
          "description",
          "tags"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

Một sản phẩm chứa Bluetooth trong description hoặc tags có thể khớp dù title không có từ đó. Nếu cần ưu tiên title so với description, dùng **compound.should** với boost khác nhau thay vì coi các fields có trọng số bằng nhau.

### 5.3. Query nhiều từ

~~~javascript
{
  $search: {
    index: "products_search",
    text: {
      query: "chuột không dây",
      path: ["title", "description"]
    }
  }
}
~~~

Các terms được tách theo analyzer, không tự đảm bảo phải nằm cạnh nhau hoặc đúng thứ tự như một cụm từ. Nếu business yêu cầu khớp cụm **"không dây"**, dùng **phrase operator** hoặc compound clauses phù hợp.

### 5.4. text query array

Search text operator có thể nhận danh sách các truy vấn văn bản:

~~~javascript
{
  $search: {
    index: "products_search",
    text: {
      query: ["bluetooth", "wireless"],
      path: ["description", "tags"]
    }
  }
}
~~~

Cần hiểu semantics của text operator và analyzer: một text query array **không tự có nghĩa cả hai cụm phải cùng xuất hiện**. Nếu bắt buộc nhiều điều kiện, hãy tạo các clauses trong **compound.must**.

## 6. Tìm nguyên cụm với phrase

**phrase** phù hợp khi thứ tự và khoảng cách giữa các terms quan trọng.

### 6.1. Cụm chính xác

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      phrase: {
        query: "không dây",
        path: "title",
        slop: 0
      }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
~~~

Với **slop:0**, các terms trong phrase phải liền kề theo tokens được analyzer tạo ra. Dấu câu, stop words và quá trình phân tích có thể ảnh hưởng điều kiện liền kề; vì vậy kiểm thử trên dữ liệu và analyzer thực tế.

### 6.2. Cho phép khoảng cách

~~~javascript
{
  $search: {
    index: "products_search",
    phrase: {
      query: "chuột M100",
      path: "title",
      slop: 2
    }
  }
}
~~~

**slop** cho phép độ lệch vị trí terms nhất định, không phải khoảng cách ký tự hay fuzzy edit distance.

### 6.3. text và phrase có thể phối hợp

Ví dụ user nhập “chuột không dây”: ta có thể bắt các products có terms phù hợp, rồi **boost** những products khớp chính xác phrase. Đây là một vấn đề scoring, không cần loại bỏ mọi kết quả thiếu exact phrase.

## 7. Các toán tử Search khác nên nhận biết

| Toán tử | Mục tiêu | Ví dụ use case |
|---|---|---|
| **text** | Tìm terms qua analyzer. | Tìm sản phẩm theo từ khóa. |
| **phrase** | Tìm chuỗi terms gần/đúng thứ tự. | “không dây”, mã cụm có nghĩa. |
| **autocomplete** | Gợi ý khi đang nhập tiền tố. | Người dùng gõ “chu”. |
| **equals** | So sánh bằng trên field đã index đúng type. | tenantId, active, category. |
| **range** | Khoảng số/ngày. | Giá 200.000–500.000. |
| **in** | Giá trị thuộc danh sách. | Nhiều categories cho phép. |
| **exists** | Field tồn tại theo Search mapping. | Có description đã index. |
| **wildcard** | Tìm pattern term với ký tự đại diện. | Một số truy vấn pattern đặc biệt. |
| **regex** | Tìm pattern theo cú pháp Lucene regex Search. | Mã sản phẩm có format. |
| **near** | Đánh giá độ gần với số/ngày/điểm. | Boost sản phẩm được đăng gần đây. |

**Không đánh đồng MongoDB Search regex với MongoDB $regex** trong find. Cú pháp, cách analyzer xử lý và khả năng index của chúng không giống nhau.

Search wildcard/regex trên những fields hoặc patterns quá rộng có thể tốn tài nguyên. Khi có nhu cầu prefix search UI, **autocomplete thường phù hợp hơn** tự dựng wildcard toàn bộ corpus.

## 8. compound: kết hợp tìm kiếm và lọc

Đối với API thực tế, phải kết hợp relevance với các ràng buộc:

- Đúng tenant đang đăng nhập.
- Sản phẩm có active=true.
- Giá trong khoảng cho phép.
- Có hoặc không thuộc danh mục nhất định.
- Có nhiều text signals mang trọng số khác nhau.

MongoDB Search hỗ trợ **compound** với bốn nhóm:

| Clause | Ý nghĩa | Đóng góp điểm relevance? |
|---|---|---|
| **must** | Mọi mệnh đề phải khớp. | Có, theo các child scores. |
| **should** | Khớp giúp tăng điểm; có thể yêu cầu tối thiểu một số mệnh đề. | Có. |
| **filter** | Mọi điều kiện phải thỏa. | **Không** đóng góp score. |
| **mustNot** | Loại những documents khớp điều kiện. | Không. |

### 8.1. Bắt buộc keyword, lọc tenant và active

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "chuột",
              path: ["title", "description"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "tenantId",
              value: "store-a"
            }
          },
          {
            equals: {
              path: "active",
              value: true
            }
          }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      tenantId: 1,
      active: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]);
~~~

**P-900 của store-b phải bị loại**, dù nó có title khớp và popularity rất cao. P-105 active=false cũng bị loại.

### 8.2. Filter theo giá và tồn kho

~~~javascript
{
  $search: {
    index: "products_search",
    compound: {
      must: [
        {
          text: {
            query: "chuột",
            path: ["title", "description"]
          }
        }
      ],
      filter: [
        {
          equals: {
            path: "tenantId",
            value: "store-a"
          }
        },
        {
          equals: {
            path: "active",
            value: true
          }
        },
        {
          range: {
            path: "priceCents",
            gte: 200000,
            lte: 500000
          }
        },
        {
          range: {
            path: "stock",
            gt: 0
          }
        }
      ]
    }
  }
}
~~~

Lọc price theo **số**, không phải so sánh chuỗi kiểu "500000" với "90000". Với giá tiền có thể thay đổi thường xuyên, cần hiểu độ trễ đồng bộ Search index nếu đây là thông tin quan trọng cho việc chốt đơn; giá cuối cùng vẫn phải được xác nhận ở write/checkout path.

### 8.3. mustNot

Loại một danh mục:

~~~javascript
{
  compound: {
    must: [
      {
        text: {
          query: "không dây",
          path: ["title", "description"]
        }
      }
    ],
    filter: [
      {
        equals: {
          path: "tenantId",
          value: "store-a"
        }
      }
    ],
    mustNot: [
      {
        equals: {
          path: "category",
          value: "headphone"
        }
      }
    ]
  }
}
~~~

Điều kiện mustNot loại kết quả chứ không tạo điểm âm cho những documents còn lại.

### 8.4. should và minimumShouldMatch

~~~javascript
{
  compound: {
    should: [
      {
        text: {
          query: "chuột",
          path: "title"
        }
      },
      {
        text: {
          query: "chuột",
          path: "description"
        }
      }
    ],
    minimumShouldMatch: 1,
    filter: [
      {
        equals: {
          path: "tenantId",
          value: "store-a"
        }
      }
    ]
  }
}
~~~

**minimumShouldMatch:1** bảo đảm ít nhất một should clause khớp. Nếu compound có cả filter/must và should, không đặt minimumShouldMatch có thể khiến should chỉ mang vai trò tăng score, làm xuất hiện documents không có keyword nếu các filter match.

### 8.5. AND giữa các từ khóa

Nếu business yêu cầu vừa có từ **chuột** vừa có từ **bluetooth**:

~~~javascript
{
  compound: {
    must: [
      {
        text: {
          query: "chuột",
          path: ["title", "description"]
        }
      },
      {
        text: {
          query: "bluetooth",
          path: ["title", "description", "tags"]
        }
      }
    ]
  }
}
~~~

Mỗi must clause được đánh giá độc lập theo Search analyzer và phải thỏa. Kết quả vẫn phụ thuộc stemming/tokenization của từng clause.

### 8.6. Tại sao nên filter bên trong $search?

Đối chiếu hai cách:

~~~javascript
// Lọc sớm trong Search engine.
{
  $search: {
    index: "products_search",
    compound: {
      must: [{ text: { query: "chuột", path: "title" } }],
      filter: [{ equals: { path: "tenantId", value: "store-a" } }]
    }
  }
}
~~~

~~~javascript
// Search trước rồi mới lọc bằng aggregation $match.
{
  $search: {
    index: "products_search",
    text: {
      query: "chuột",
      path: "title"
    }
  }
},
{
  $match: {
    tenantId: "store-a"
  }
}
~~~

Cách thứ hai có thể khiến Search engine xét nhiều candidates hơn cần thiết và sai phân trang/count nếu limit được áp dụng trước filter. Với điều kiện được Search index hỗ trợ, **compound.filter** thường phù hợp hơn. Backend vẫn phải bảo vệ authorization ở tầng API, không chỉ tin vào input tenant từ client.

## 9. Fuzzy search: chấp nhận lỗi gõ có kiểm soát

Người dùng có thể nhập **"bluetooh"** thay vì **"bluetooth"**. Fuzzy text matching mở rộng term matching dựa trên **edit distance**, ví dụ thêm, xóa hoặc thay ký tự.

### 9.1. text.fuzzy

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "bluetooh",
              path: ["title", "description", "tags"],
              fuzzy: {
                maxEdits: 1,
                prefixLength: 2,
                maxExpansions: 50
              }
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]);
~~~

Với maxEdits=1, typo thiếu một ký tự có thể được xét là term gần đúng. Kết quả thực tế phụ thuộc analyzer và dữ liệu đã index.

### 9.2. Ý nghĩa ba tham số

| Tham số | Ý nghĩa | Đánh đổi |
|---|---|---|
| **maxEdits** | Số thao tác chỉnh sửa tối đa (thường 1 hoặc 2). | Cao tăng recall nhưng dễ false positives/tăng chi phí. |
| **prefixLength** | Số ký tự đầu term cần khớp chính xác. | Cao tăng precision nhưng bỏ lỡ lỗi ở đầu từ. |
| **maxExpansions** | Giới hạn số biến thể term xem xét trong fuzzy expansion. | Cao tăng chi phí truy vấn. |

Fuzzy edit distance **không hiểu ngữ nghĩa**. Hai từ chỉ khác một ký tự có thể là hai mã sản phẩm hoàn toàn khác nhau. Với SKU hay mã giao dịch, hãy cân nhắc exact matching trước khi fuzzy.

### 9.3. maxEdits theo độ dài query

Một heuristic phía ứng dụng có thể là:

~~~text
query length < 3  -> không fuzzy, gợi ý prefix hoặc yêu cầu nhập thêm.
3–5 ký tự        -> thử maxEdits=1.
query dài hơn    -> có thể thử maxEdits=1/2, tùy corpus và SLA.
~~~

Đây không phải quy tắc mặc định của MongoDB. Cần benchmark precision/recall và độ trễ, nhất là với từ ngắn.

### 9.4. Ưu tiên exact matches rồi mới fuzzy

~~~javascript
{
  $search: {
    index: "products_search",
    compound: {
      should: [
        {
          text: {
            query: "bluetooh",
            path: ["title", "description"],
            score: { boost: { value: 5 } }
          }
        },
        {
          text: {
            query: "bluetooh",
            path: ["title", "description"],
            fuzzy: {
              maxEdits: 1,
              prefixLength: 2
            },
            score: { boost: { value: 1 } }
          }
        }
      ],
      minimumShouldMatch: 1,
      filter: [
        { equals: { path: "tenantId", value: "store-a" } }
      ]
    }
  }
}
~~~

Khi user nhập chính tả đúng, exact clause có thể cho điểm cao hơn; khi nhập sai, fuzzy clause bổ sung recall. Điểm cuối phụ thuộc các clauses, term statistics và score combination, không phải chỉ một con số boost.

### 9.5. Giới hạn của fuzzy với tiếng Việt

Fuzzy không tự chuyển mọi chuỗi không dấu sang có dấu. Những từ như **"chuột"** và **"chuot"** phụ thuộc Unicode normalization, analyzer và mapping. Nếu muốn tìm không dấu, nên dùng analyzer/field chuẩn hóa và bộ test tiếng Việt, không chỉ tăng maxEdits.

### 9.6. Fuzzy và synonyms

MongoDB Search hỗ trợ synonyms qua cấu hình index tương ứng, nhưng **text.fuzzy và synonyms trong cùng clause có ràng buộc sử dụng**. Khi cần cả synonym expansion và typo tolerance, thiết kế các clauses riêng và xem tài liệu API/version cụ thể; không tự bật cả hai trên một toán tử rồi kỳ vọng luôn hợp lệ.

## 10. Autocomplete: gợi ý trong khi đang gõ

Fuzzy và autocomplete giải quyết hai mục tiêu khác nhau:

~~~text
Fuzzy:
  "bluetooh" -> có thể tìm "Bluetooth".

Autocomplete:
  "Chu" -> gợi ý "Chuột không dây M100".
~~~

Autocomplete yêu cầu field được index với mapping **type:"autocomplete"**. Ví dụ dùng **titleSuggest**.

### 10.1. Truy vấn tiền tố

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            autocomplete: {
              query: "Chu",
              path: "titleSuggest",
              tokenOrder: "sequential"
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 8 }
]);
~~~

Autocomplete nên giới hạn số results, tránh trả cả catalog khi user gõ ký tự đầu.

### 10.2. Các kiểu tokenization

| Kiểu | Ý nghĩa | Use case |
|---|---|---|
| **edgeGram** | Index tiền tố từ đầu token. | Gõ đầu từ hoặc tên. |
| **rightEdgeGram** | Index hậu tố từ cuối token. | Nhu cầu suffix search. |
| **nGram** | Index các đoạn ký tự ở nhiều vị trí. | Infix matching, đổi lấy index lớn hơn. |

Với token **bluetooth**, edgeGram (minGrams=2) có thể tạo những tiền tố như **bl, blu, blue, bluet** cho tới maxGrams. **minGrams/maxGrams** là index configuration; đổi chúng thường đòi cập nhật/rebuild Search index.

### 10.3. tokenOrder

~~~javascript
{
  autocomplete: {
    query: "chuột không",
    path: "titleSuggest",
    tokenOrder: "sequential"
  }
}
~~~

**sequential** yêu cầu các query tokens theo thứ tự; **any** linh hoạt hơn về vị trí/thứ tự. Trải nghiệm tốt nhất phụ thuộc corpus nên cần test cả hai.

### 10.4. Autocomplete với fuzzy

~~~javascript
{
  autocomplete: {
    query: "bluetoh",
    path: "titleSuggest",
    tokenOrder: "sequential",
    fuzzy: {
      maxEdits: 1,
      prefixLength: 2,
      maxExpansions: 50
    }
  }
}
~~~

Fuzzy autocomplete giúp gợi ý khi một token đang được nhập có lỗi. Nhưng query rất ngắn cộng maxEdits cao có thể làm nhiều kết quả không liên quan xuất hiện. Cần minimum query length, debounce và đo chất lượng.

### 10.5. Autocomplete không đồng nghĩa full-word relevance

Một title khớp nguyên cụm chưa chắc luôn đứng trên mọi title khớp prefix nếu chỉ dùng autocomplete score. Nếu cần ưu tiên exact/full-word:

- Kết hợp **text/phrase** và **autocomplete** trong compound.should.
- Boost matches ở title hoặc phrase.
- Dùng signals như popularity/recency một cách có kiểm soát.
- Re-rank shortlist theo quy tắc sản phẩm khi phù hợp.

### 10.6. Debounce phía frontend

~~~text
User nhập "c":    chưa cần query.
User nhập "ch":   đợi một khoảng ngắn.
User nhập "chu":  gọi API suggest.
User tiếp tục gõ: cancel hoặc bỏ qua response cũ.
~~~

Khoảng debounce do UX và traffic quyết định, thường vài trăm milliseconds. **Debounce là logic ứng dụng**, không phải một tùy chọn của $search.

### 10.7. Autocomplete không tự tạo một danh sách gợi ý unique

Một query có thể trả nhiều documents có tên giống nhau. Muốn mỗi tên xuất hiện một lần, cần dedupe output hoặc suggestion model phù hợp; không phải chỉ bật operator autocomplete là có unique suggestions.

**Bảo mật:** autocomplete endpoint cũng phải filter tenant, active và quyền hiển thị. Nó có thể trở thành kênh làm lộ tên sản phẩm của tenant khác nếu thiếu scope.

## 11. Xếp hạng kết quả bằng searchScore

Trong full-text search, không chỉ cần biết document **có khớp hay không**, mà còn cần đánh giá **mức độ phù hợp**.

MongoDB Search gán **relevance score** cho những documents khớp query. Với full-text, Search thường dùng cơ chế đánh giá dựa trên thống kê terms như BM25, kết hợp theo operators/analyzers và score settings.

### 11.1. Lấy điểm ra kết quả

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "chuột",
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

**searchScore là một chỉ số xếp hạng tương đối trong ngữ cảnh query/index**, không phải phần trăm độ đúng hay một xác suất được chuẩn hóa. Không đặt nhãn UI “phù hợp 87%” chỉ vì score = 8.7.

### 11.2. Vì sao score có thể khác?

Các yếu tố có thể ảnh hưởng:

- Term khớp ở field nào.
- Term hiếm hay phổ biến trong corpus.
- Số lần xuất hiện và độ dài field theo cơ chế scoring.
- Analyzer, tokenization và synonyms.
- Fuzzy/phrase match và scoring operator.
- Search index configuration, score boosts/functions.
- Thay đổi corpus và version của Search index.

Vì vậy **không so searchScore giữa hai truy vấn khác nhau như một đại lượng tuyệt đối** và không tạo ngưỡng cố định mà thiếu đánh giá chất lượng thực tế.

### 11.3. Boost title cao hơn description

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        should: [
          {
            text: {
              query: "chuột",
              path: "title",
              score: {
                boost: { value: 5 }
              }
            }
          },
          {
            text: {
              query: "chuột",
              path: "description",
              score: {
                boost: { value: 1 }
              }
            }
          }
        ],
        minimumShouldMatch: 1,
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]);
~~~

**boost không khiến query tự match**. Nó thay đổi điểm của một clause khi clause đó match. Nếu chỉ tồn tại một sản phẩm khớp description, boost title không biến sản phẩm không khớp title thành một kết quả title match.

### 11.4. Ưu tiên khớp cụm chính xác

~~~javascript
{
  $search: {
    index: "products_search",
    compound: {
      should: [
        {
          phrase: {
            query: "không dây",
            path: "title",
            slop: 0,
            score: { boost: { value: 6 } }
          }
        },
        {
          text: {
            query: "không dây",
            path: "title",
            score: { boost: { value: 3 } }
          }
        },
        {
          text: {
            query: "không dây",
            path: "description",
            score: { boost: { value: 1 } }
          }
        }
      ],
      minimumShouldMatch: 1,
      filter: [
        { equals: { path: "tenantId", value: "store-a" } }
      ]
    }
  }
}
~~~

Một product khớp phrase có thể nhận thêm contribution từ các clauses khác. Tương tác giữa multiple matches quyết định score tổng; đừng tự suy nó luôn đúng bằng 6+3+1.

### 11.5. Constant score và score functions

MongoDB Search cung cấp các cách điều chỉnh score khác, chẳng hạn:

~~~javascript
score: {
  constant: {
    value: 5
  }
}
~~~

**constant** thay điểm tính bằng một giá trị hằng cho clause tương ứng, khác với **boost** nhân điểm relevance.

Search còn hỗ trợ **function scoring** để kết hợp điểm relevance với giá trị field, độ mới hoặc các phép toán tương ứng. Tuy nhiên cần:

1. Chuẩn hóa các signals (không cho popularity 0–1.000.000 áp đảo hoàn toàn relevance 1–10).
2. Không boost một sản phẩm đã inactive/ngoài tenant lên thành kết quả hợp lệ; điều kiện đó phải nằm trong filter.
3. Test ảnh hưởng của các signals trên tập query thực tế.
4. Hạn chế business rules nhạy cảm phụ thuộc vào một score formula thiếu versioning.

### 11.6. Recency và popularity

Trong product search, độ mới và mức quan tâm có thể là secondary signals:

~~~text
Final ranking considerations:

Primary: text relevance / exact phrase / title match.
Secondary: popularity, publishedAt, in-stock.
Hard constraints: tenantId, active, authorized categories.
~~~

Nếu sản phẩm mới không chứa query keyword, boost độ mới **không nên khiến nó được đưa vào kết quả** trừ khi hệ thống cố ý thiết kế discovery mode.

### 11.7. Filter không tạo score

Một document thỏa **tenantId="store-a"** và **active=true** không nên được tăng relevance chỉ vì nó hợp lệ. Đó là lý do dùng **compound.filter** cho các ràng buộc bắt buộc.

Không dùng must text về từ "active" hay tenant ID để mô phỏng bảo mật hoặc lọc trạng thái.

### 11.8. Xem chi tiết score khi phân tích

Một số phiên bản MongoDB Search hỗ trợ **scoreDetails** để trả giải thích đóng góp score:

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "chuột",
        path: "title"
      },
      scoreDetails: true
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" },
      scoreDetails: { $meta: "searchScoreDetails" }
    }
  }
]);
~~~

**scoreDetails dùng để debug/tuning**, có thể tạo overhead. Không trả thông tin scoring nội bộ cho mọi client ở production.

### 11.9. Sắp xếp score và ổn định thứ tự

~~~javascript
{ $sort: { score: -1, _id: 1 } }
~~~

Sắp điểm giảm dần, dùng _id làm tie-breaker. Tuy nhiên kết quả có thể thay đổi khi Search index nhận updates và terms statistics thay đổi. **Stable sort trên một snapshot bất biến khác với ổn định pagination khi catalog đang liên tục được cập nhật**.

## 12. Highlight: làm nổi bật vị trí match

Search results thường cần hiển thị:

~~~text
Chuột Bluetooth M2
Mô tả: Chuột không dây êm và nhẹ cho văn phòng
        ^^^^^^^^^^^^^^^
~~~

MongoDB Search hỗ trợ **highlight** để trả những đoạn văn và token matches liên quan.

### 12.1. Yêu cầu highlights

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "bluetooth",
        path: ["title", "description"]
      },
      highlight: {
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" },
      highlights: { $meta: "searchHighlights" }
    }
  },
  { $limit: 10 }
]);
~~~

Kết quả highlights chứa thông tin về path, đoạn text và loại phần tử khớp/không khớp theo schema Search. Đây **không phải** một chuỗi HTML chứa thẻ mark tự sinh.

### 12.2. Render an toàn ở frontend

Không tự lấy text từ database rồi đưa thẳng vào innerHTML mà không escape. Trong web app, hãy:

- Render từng segment bằng text node.
- Gán style cho segment có match.
- Escape/encode nội dung user-generated.
- Kiểm tra tenant và field visibility trước khi trả metadata.

Highlight giúp UX; nó không thay thế bảo vệ XSS và authorization.

### 12.3. Highlight không phải lời giải cho mọi fuzzy match

Fuzzy/analyzer có thể biến đổi terms, vì thế vị trí highlight và khái niệm “khớp đúng toàn query” cần xem theo Search semantics. Không dùng highlight để chứng minh một tài liệu “đúng tuyệt đối”.

### 12.4. Khi nào không cần highlights?

Autocomplete gợi ý 5 tên sản phẩm có thể chỉ cần tên, ảnh và category. Không nhất thiết bật highlight phức tạp làm tăng payload khi UI không hiển thị.

## 13. Counts và faceted search bằng $searchMeta

Một trang tìm kiếm thường có hai khu vực:

~~~text
Kết quả "bluetooth": 27 sản phẩm

Danh mục:
  Chuột (12)
  Bàn phím (7)
  Tai nghe (8)

Giá:
  Dưới 200.000
  200.000–500.000
  Trên 500.000
~~~

**$searchMeta** trả Search metadata như counts và facets, thay vì trả toàn bộ result documents.

### 13.1. Đếm số kết quả

~~~javascript
db.products.aggregate([
  {
    $searchMeta: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "bluetooth",
              path: ["title", "description", "tags"]
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      },
      count: {
        type: "total"
      }
    }
  }
]);
~~~

**total** hướng tới count chính xác theo query semantics; những lựa chọn count như **lowerBound** có thể phù hợp khi ưu tiên latency, với ý nghĩa kết quả khác exact total.

Không đếm toàn bộ tenant rồi hiển thị như count của kết quả đang lọc. Count query phải có cùng điều kiện business.

### 13.2. Category và price facets

~~~javascript
db.products.aggregate([
  {
    $searchMeta: {
      index: "products_search",
      facet: {
        operator: {
          compound: {
            must: [
              {
                text: {
                  query: "bluetooth",
                  path: ["title", "description", "tags"]
                }
              }
            ],
            filter: [
              { equals: { path: "tenantId", value: "store-a" } },
              { equals: { path: "active", value: true } }
            ]
          }
        },
        facets: {
          categories: {
            type: "string",
            path: "category",
            numBuckets: 10
          },
          priceBands: {
            type: "number",
            path: "priceCents",
            boundaries: [
              0,
              200000,
              500000,
              1000000
            ],
            default: "other"
          }
        }
      }
    }
  }
]);
~~~

Index field phải có mapping phù hợp cho facet. Với category, **token** mapping thường phù hợp với exact string faceting trong các phiên bản Search hỗ trợ. Với priceBands, số phải được index dạng number.

### 13.3. Facet counts phụ thuộc filter

Nếu user đã chọn **category=mouse** và facet query cũng filter category=mouse, categories facet có thể chỉ còn mouse, khiến UI không hiển thị các danh mục thay thế.

Tùy UX, có thể dùng chiến lược **disjunctive faceting**: khi tính facet cho category, giữ những filter khác như tenant, active, text và giá, nhưng bỏ filter category đang chọn. Việc này có thể cần nhiều metadata queries hoặc một thiết kế facet phù hợp; hãy làm rõ semantics với product team.

### 13.4. Count/facet và Search index freshness

Search index đồng bộ từ MongoDB không phải một transactionally consistent read của tất cả dữ liệu nghiệp vụ tại chính mili giây người dùng click. Counts và facets có thể thay đổi khi index updates; cần biết tính **near-real-time** của hệ thống Search.

Đối với tính tiền/tồn kho, không dùng facet count hoặc Search index result làm kiểm tra cuối cùng trước khi ghi đơn hàng.

## 14. Phân trang Search results

Một endpoint search không nên trả hàng nghìn documents trong một response. Thường chỉ cần 10–30 kết quả/trang, cùng thông tin tổng số hoặc khả năng sang trang tiếp.

### 14.1. Skip/limit cho các trang nhỏ

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "chuột",
              path: ["title", "description"]
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      category: 1,
      priceCents: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $skip: 0 },
  { $limit: 10 }
]);
~~~

Trang thứ hai có thể đặt skip=10. Tuy nhiên, **deep pagination** (skip rất lớn) buộc hệ thống xử lý nhiều kết quả bị bỏ đi và có thể tăng latency/memory. Ngoài ra khi Search index nhận updates, documents có thể chuyển thứ tự giữa các requests.

### 14.2. Search after / sequence token

MongoDB Search hỗ trợ phân trang dựa trên **searchSequenceToken** trong những phiên bản/triển khai phù hợp. Một request có thể lấy token cho mỗi hit:

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "chuột",
              path: "title"
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } }
        ]
      },
      sort: {
        score: { $meta: "searchScore" },
        publishedAt: -1
      }
    }
  },
  {
    $project: {
      title: 1,
      publishedAt: 1,
      score: { $meta: "searchScore" },
      pageToken: { $meta: "searchSequenceToken" }
    }
  },
  { $limit: 10 }
]);
~~~

Request trang kế tiếp truyền **searchAfter** với token thực của item cuối trang trước, và phải dùng **cùng query, filters và sort**:

~~~javascript
{
  $search: {
    index: "products_search",
    text: {
      query: "chuột",
      path: "title"
    },
    sort: {
      score: { $meta: "searchScore" },
      publishedAt: -1
    },
    searchAfter: savedSearchSequenceToken
  }
}
~~~

Đoạn thứ hai minh họa cấu trúc searchAfter. Trong ứng dụng thật, **savedSearchSequenceToken** phải là token hợp lệ do Search trả ra và **query/filters phải giống trang trước**, không được bỏ điều kiện tenant khi lấy trang tiếp.

### 14.3. Search pagination token không phải MongoDB Change Stream resume token

~~~text
MongoDB Search searchSequenceToken:
  -> Vị trí phân trang kết quả Search.

MongoDB Change Stream resume token:
  -> Vị trí trong luồng các thay đổi đã commit.
~~~

Hai loại token khác mục đích và không thay thế nhau.

### 14.4. Sắp xếp ổn định và tie-break

Khi nhiều documents cùng score hoặc publishedAt, muốn thứ tự hoàn toàn ổn định cần cân nhắc **secondary unique tie-break field được index hỗ trợ sort**. Một token chỉ có thể được dùng theo semantics của query/search sort tương ứng.

Đừng kỳ vọng phân trang không drift tuyệt đối khi catalog hoặc Search index thay đổi ngay giữa các requests. Nếu yêu cầu snapshot pagination bất biến, cần thiết kế stateful result set hoặc cơ chế snapshot/retention ngoài Search pagination thông thường.

### 14.5. Bảo mật page token

Không coi token là thông tin cho phép vượt phân quyền. API phải kiểm tra tenant và quyền **ở mọi trang**. Có thể ký/mã hóa token ở tầng API nếu cần chống client thay nội dung hoặc giấu thông tin nội bộ; đừng tin một token do client gửi là chứng minh quyền truy cập.

## 15. Một pipeline tìm kiếm sản phẩm tương đối đầy đủ

Giả sử user nhập:

~~~text
q = "chuột không dây"
category = mouse
price = 200.000–500.000 VND
inStock = true
tenant = store-a (xác thực bởi backend)
~~~

Mục tiêu:

1. Tìm toàn văn ở title/description.
2. Boost phrase đúng thứ tự trên title.
3. Lọc đúng tenant, active, category, price và stock.
4. Trả title, price, score, highlights.
5. Chỉ trả 10 kết quả đầu.

~~~javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        must: [
          {
            text: {
              query: "chuột không dây",
              path: ["title", "description"]
            }
          }
        ],
        should: [
          {
            phrase: {
              query: "chuột không dây",
              path: "title",
              slop: 0,
              score: {
                boost: { value: 6 }
              }
            }
          },
          {
            text: {
              query: "chuột không dây",
              path: "title",
              score: {
                boost: { value: 3 }
              }
            }
          }
        ],
        filter: [
          { equals: { path: "tenantId", value: "store-a" } },
          { equals: { path: "active", value: true } },
          { equals: { path: "category", value: "mouse" } },
          {
            range: {
              path: "priceCents",
              gte: 200000,
              lte: 500000
            }
          },
          { range: { path: "stock", gt: 0 } }
        ]
      },
      highlight: {
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      description: 1,
      category: 1,
      priceCents: 1,
      stock: 1,
      score: { $meta: "searchScore" },
      highlights: { $meta: "searchHighlights" }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

### 15.1. Các clauses có vai trò khác nhau

| Clause | Vai trò |
|---|---|
| must text | Bắt buộc khớp query text theo analyzer. |
| should phrase | Thưởng điểm cho khớp nguyên cụm ở title. |
| should text title | Thưởng điểm cho tiêu đề liên quan. |
| filter tenantId | Bảo vệ scope cửa hàng. |
| filter active | Ẩn sản phẩm ngừng bán. |
| filter category | Chỉ lấy danh mục user đã chọn. |
| filter priceCents | Giới hạn giá. |
| filter stock | Yêu cầu còn tồn theo Search index. |
| highlight | Trả đoạn text làm nổi bật keyword. |
| sort/limit | Trả shortlist theo score. |

### 15.2. Vì sao nên chia tìm kiếm thành hai chế độ?

Một ứng dụng thường tách:

**Search results mode**: user đã nhập đủ query, có filters, phân trang, highlights.

**Suggest mode**: user đang gõ, query có thể ngắn, dùng autocomplete, trả 5–8 gợi ý và response nhỏ.

Nếu dùng fuzzy + phrase + highlight + facet + long pagination trên **mỗi keypress**, chi phí và độ trễ có thể tăng mạnh mà UX không cải thiện.

### 15.3. Những điều query này chưa đảm bảo

- Không xác nhận giá/tồn kho nguyên tử ở thời điểm checkout.
- Không đồng bộ Search index tức thì sau mỗi write.
- Không tự tạo transactional snapshot của mọi dữ liệu MongoDB.
- Không phòng chống event duplication nếu backend kết hợp tìm kiếm với outbox/CDC.
- Không tự xử lý tiếng Việt không dấu/synonyms nếu index analyzer chưa cấu hình.
- Không tự biến score thành xác suất liên quan.

## 16. Xây API tìm kiếm an toàn

### 16.1. Không nhận pipeline từ client

Sai về mặt thiết kế:

~~~text
POST /search
body = { "aggregationPipeline": [ ...user-controlled... ] }
~~~

Việc cho client gửi tùy ý Search operators hoặc raw aggregation stages có thể gây lọc sai tenant, khai thác tính năng không mong muốn và truy vấn tốn tài nguyên.

API nên nhận **tham số đã định nghĩa**:

~~~json
{
  "query": "chuột",
  "category": "mouse",
  "minPriceCents": 200000,
  "maxPriceCents": 500000,
  "inStock": true,
  "limit": 10
}
~~~

Backend **tự lắp Search DSL có allowlist**, không truyền JSON client thành pipeline.

### 16.2. Pseudocode dựng compound.filter

~~~javascript
function buildProductSearchStages(request, authenticatedTenantId) {
  const q = String(request.query || "").trim();
  if (q.length < 2 || q.length > 100) {
    throw new Error("Query length is outside allowed range");
  }

  const limit = Math.min(
    30,
    Math.max(1, Number(request.limit || 10))
  );

  if (!Number.isSafeInteger(limit)) {
    throw new Error("Invalid limit");
  }

  const filters = [
    {
      equals: {
        path: "tenantId",
        value: authenticatedTenantId
      }
    },
    {
      equals: {
        path: "active",
        value: true
      }
    }
  ];

  const allowedCategories = new Set([
    "mouse",
    "keyboard",
    "headphone"
  ]);

  if (request.category != null) {
    if (!allowedCategories.has(request.category)) {
      throw new Error("Invalid category");
    }
    filters.push({
      equals: {
        path: "category",
        value: request.category
      }
    });
  }

  if (request.inStock === true) {
    filters.push({
      range: {
        path: "stock",
        gt: 0
      }
    });
  }

  const min = request.minPriceCents;
  const max = request.maxPriceCents;

  if (min != null || max != null) {
    if (
      (min != null && (!Number.isSafeInteger(min) || min < 0)) ||
      (max != null && (!Number.isSafeInteger(max) || max < 0)) ||
      (min != null && max != null && min > max)
    ) {
      throw new Error("Invalid price range");
    }

    const priceRange = { path: "priceCents" };
    if (min != null) priceRange.gte = min;
    if (max != null) priceRange.lte = max;
    filters.push({ range: priceRange });
  }

  return [
    {
      $search: {
        index: "products_search",
        compound: {
          must: [
            {
              text: {
                query: q,
                path: ["title", "description"]
              }
            }
          ],
          filter: filters
        }
      }
    },
    {
      $project: {
        title: 1,
        priceCents: 1,
        category: 1,
        score: { $meta: "searchScore" }
      }
    },
    { $sort: { score: -1, _id: 1 } },
    { $limit: limit }
  ];
}
~~~

Đây là code minh họa builder, **không phải router/authentication middleware hoàn chỉnh**. Nó chỉ cho phép các filters/path cố định, và tenantId là tham số server đã xác minh.

### 16.3. Không nhận score boost tùy ý

Nếu client gửi:

~~~json
{
  "boost": 1000000
}
~~~

và backend đưa thẳng vào score function, kết quả có thể thiếu ổn định và query tốn chi phí. Chỉ dùng **ranking profiles** được allowlist, có version và thử nghiệm.

### 16.4. Giới hạn dữ liệu trả về

Response chỉ cần các fields phục vụ UI: ID, title, giá, ảnh, category và score/highlight khi cần. Tránh trả toàn bộ document có wholesalePrice, internalNotes, email hoặc các fields không được phép hiển thị.

### 16.5. Không dùng Search để quyết định nghiệp vụ quan trọng

Ví dụ user tìm thấy sản phẩm với stock=1. Trong vài giây trước checkout, một request khác có thể mua hết hàng và Search index có thể chưa đồng bộ.

**Checkout phải kiểm tra stock và giá hiện tại với lệnh ghi có điều kiện/transaction phù hợp trên MongoDB source of truth**. Search chỉ phục vụ discovery và trải nghiệm duyệt.

## 17. Java Sync Driver: thực hiện Search aggregation

MongoDB Java Sync Driver có thể chạy **$search** dưới dạng các **Bson** stages. Nếu builder chuyên dụng chưa hỗ trợ một Search operator của phiên bản đang sử dụng, có thể xây stage bằng **org.bson.Document**.

### 17.1. Ví dụ tìm sản phẩm có điều kiện

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;
import java.util.concurrent.TimeUnit;

public final class ProductSearchDemo {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI is required"
            );
        }

        // Tenant ID phải do backend đã xác thực cung cấp.
        String tenantId = "store-a";
        String query = "chuột";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(
                    "mongo_search_lab"
            );
            MongoCollection<Document> products =
                    database.getCollection("products");

            Document search = new Document(
                    "$search",
                    new Document("index", "products_search")
                            .append(
                                    "compound",
                                    new Document(
                                            "must",
                                            List.of(
                                                    new Document(
                                                            "text",
                                                            new Document("query", query)
                                                                    .append(
                                                                            "path",
                                                                            List.of(
                                                                                    "title",
                                                                                    "description"
                                                                            )
                                                                    )
                                                    )
                                            )
                                    ).append(
                                            "filter",
                                            List.of(
                                                    new Document(
                                                            "equals",
                                                            new Document(
                                                                    "path",
                                                                    "tenantId"
                                                            ).append(
                                                                    "value",
                                                                    tenantId
                                                            )
                                                    ),
                                                    new Document(
                                                            "equals",
                                                            new Document(
                                                                    "path",
                                                                    "active"
                                                            ).append(
                                                                    "value",
                                                                    true
                                                            )
                                                    )
                                            )
                                    )
                            )
            );

            Bson project = new Document(
                    "$project",
                    new Document("title", 1)
                            .append("category", 1)
                            .append("priceCents", 1)
                            .append(
                                    "score",
                                    new Document("$meta", "searchScore")
                            )
            );

            Bson sort = new Document(
                    "$sort",
                    new Document("score", -1)
                            .append("_id", 1)
            );

            List<Bson> pipeline = List.of(
                    search,
                    project,
                    sort,
                    new Document("$limit", 10)
            );

            products.aggregate(pipeline)
                    .maxTime(5, TimeUnit.SECONDS)
                    .forEach(System.out::println);
        }
    }
}
~~~

Giải thích:

- **search** là một Bson stage, phải đứng đầu pipeline.
- **must.text** quy định text terms cần tìm.
- **filter.equals** hạn chế tenant và active mà không tăng score.
- **$project** lấy **searchScore** qua $meta.
- **$sort** theo score giảm dần và _id.
- **$limit** tránh trả quá nhiều results.
- **maxTime** đặt giới hạn thời gian phía server cho aggregation; timeout cần được xử lý như lỗi, không phải một danh sách kết quả rỗng.

### 17.2. Fuzzy trong Java

Khi cần fuzzy text, có thể thay text clause bằng:

~~~java
Document fuzzyText = new Document(
        "text",
        new Document("query", "bluetooh")
                .append(
                        "path",
                        List.of("title", "description", "tags")
                )
                .append(
                        "fuzzy",
                        new Document("maxEdits", 1)
                                .append("prefixLength", 2)
                                .append("maxExpansions", 50)
                )
);
~~~

Sau đó đưa **fuzzyText** vào **compound.must** hoặc **compound.should** theo behavior cần thiết.

### 17.3. Autocomplete trong Java

~~~java
Document autocomplete = new Document(
        "autocomplete",
        new Document("query", "Chu")
                .append("path", "titleSuggest")
                .append("tokenOrder", "sequential")
);
~~~

Nên có một API gợi ý riêng với giới hạn query length và 5–10 results. Không để user tự chọn mọi Search field/path hoặc số lượng trả về không giới hạn.

### 17.4. Java dùng cùng Search DSL nhưng không cần nhúng JSON string

Các Document builders cho phép tạo BSON query tree có type số/boolean đúng, thay vì nối chuỗi:

~~~java
// Không làm:
String json = "{ tenantId: '" + userInput + "' }";
~~~

Nối raw JSON từ user input dễ tạo lỗi escape/injection ở tầng truy vấn. Hãy tạo Bson Document với **đường dẫn field có allowlist** và giá trị có kiểu rõ ràng.

### 17.5. Validation và exceptions

Ở service thật cần:

- Validate q length, giá trị min/max price và limit.
- Filter tenant từ security context.
- Xử lý timeouts và lỗi Search index unavailable.
- Không log query có PII nếu không thật sự cần.
- Expose metrics latency theo query type thay vì raw user text.
- Return DTO chỉ chứa fields cho phép.

## 18. Spring Data MongoDB: dùng AggregationOperation

Spring Data MongoDB hỗ trợ **MongoTemplate.aggregate()**. Với $search, có thể dùng **AggregationOperation** trả một raw stage Document, tránh phụ thuộc vào việc version Spring Data đã có builder chuyên biệt hay chưa.

### 18.1. Service mẫu

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class CatalogSearchService {

    private final MongoTemplate mongoTemplate;

    public CatalogSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> search(
            String tenantId,
            String query) {

        if (query == null
                || query.isBlank()
                || query.length() > 100) {
            throw new IllegalArgumentException("Invalid query");
        }

        Document text = new Document(
                "text",
                new Document("query", query.trim())
                        .append(
                                "path",
                                List.of("title", "description")
                        )
        );

        Document byTenant = new Document(
                "equals",
                new Document("path", "tenantId")
                        .append("value", tenantId)
        );

        Document activeOnly = new Document(
                "equals",
                new Document("path", "active")
                        .append("value", true)
        );

        Document compound = new Document(
                "must",
                List.of(text)
        ).append(
                "filter",
                List.of(byTenant, activeOnly)
        );

        AggregationOperation searchStage =
                context -> new Document(
                        "$search",
                        new Document("index", "products_search")
                                .append("compound", compound)
                );

        AggregationOperation projectStage =
                context -> new Document(
                        "$project",
                        new Document("title", 1)
                                .append("priceCents", 1)
                                .append(
                                        "score",
                                        new Document("$meta", "searchScore")
                                )
                );

        AggregationOperation sortStage =
                context -> new Document(
                        "$sort",
                        new Document("score", -1)
                                .append("_id", 1)
                );

        AggregationOperation limitStage =
                context -> new Document("$limit", 10);

        Aggregation pipeline = Aggregation.newAggregation(
                searchStage,
                projectStage,
                sortStage,
                limitStage
        );

        return mongoTemplate.aggregate(
                pipeline,
                "products",
                Document.class
        ).getMappedResults();
    }
}
~~~

Trong ứng dụng thật, **tenantId phải lấy từ security context**, không nhận tùy ý từ form. Cần mapping DTO, timeout và xử lý exception chuyên biệt.

### 18.2. Tại sao Search stage phải là đầu?

~~~text
Đúng:
  $search -> $project -> $sort -> $limit

Không đúng trong pipeline thông thường:
  $match -> $search -> $project
~~~

Nếu code Spring Data tự thêm $match/$project trước Search stage, MongoDB có thể từ chối pipeline. Đảm bảo **Aggregation.newAggregation(searchStage, ...)** giữ Search ở vị trí đầu.

### 18.3. Lưu ý Spring Data mapping

Khi dùng raw Document stages, bạn đang viết **tên field thực tế trong MongoDB**. Nếu Java entity dùng **@Field("product_title")** nhưng code vẫn truy vấn "title", pipeline có thể không match như mong muốn.

Với typed builders, Spring Data có cơ chế mapping field names; với raw stages cần hiểu rõ context và document schema.

### 18.4. ReactiveMongoTemplate

Ở reactive stack, có thể dùng **ReactiveMongoTemplate.aggregate(...)** để trả **Flux** results; Search computation vẫn chạy ở MongoDB Search và có cùng yêu cầu index/latency. Không gọi blocking Java Sync Driver trên reactive event loop.

### 18.5. Spring Data repository không tự biến derived query thành $search

Method như:

~~~java
List<Product> findByTitleContainingIgnoreCase(String title);
~~~

thường biểu diễn query theo cơ chế Spring Data thông thường, không đồng nghĩa nó đang dùng **MongoDB Search fuzzy/autocomplete/ranking**. Muốn Search features, cần aggregation stage/driver hoặc integration được framework hỗ trợ rõ ràng.

## 19. Tìm kiếm và sự nhất quán dữ liệu

### 19.1. Search index không phải source of truth

Luồng dữ liệu thường:

~~~text
Application write
       |
       v
MongoDB collection
       |
       v
Search index đồng bộ bất đồng bộ
       |
       v
Search query
~~~

Một document vừa insert/update có thể cần thời gian trước khi xuất hiện hoặc phản ánh state mới trên Search index. **Độ trễ này thường được gọi là near-real-time/index freshness lag**.

Do đó:

- Không giả định user vừa Save xong sẽ lập tức tìm thấy kết quả mới trong cùng mili giây.
- Không dùng Search score/price/stock để kiểm tra invariant tại checkout.
- Nếu cần read-your-writes của một document, có thể lấy document theo _id từ MongoDB source và hiển thị confirmation, còn Search index đồng bộ dần.

### 19.2. Phân quyền không được dựa vào độ mới Search index

Giả sử sản phẩm vừa chuyển từ tenant A sang B hoặc quyền truy cập thay đổi. Khi Search index chưa đồng bộ, một kết quả cũ có thể vẫn match filter tenant A.

Với dữ liệu nhạy cảm, kiến trúc phải bảo đảm **authorization ở tầng đọc source-of-truth/response** hoặc cơ chế invalidation/consistency phù hợp. Search filter là quan trọng nhưng **không đủ làm rào bảo vệ duy nhất** cho các chuyển quyền cần hiệu lực ngay.

### 19.3. Search sau transaction

Một transaction MongoDB có thể commit các thay đổi catalog, nhưng Search index cập nhật không nhất thiết cùng transaction commit. Không dùng Search aggregation trong transaction như một snapshot transactional của Search indexes; hãy kiểm tra hạn chế của $search trong transaction ở server version hiện hành.

### 19.4. Reindex và thay analyzer

Khi thay Search index analyzer, tokenizer, minGrams hoặc fields, thường cần tạo/cập nhật index và xây lại dữ liệu tìm kiếm.

Một rollout an toàn:

1. Tạo **products_search_v2**.
2. Chờ index sẵn sàng.
3. Chạy bộ query đánh giá chất lượng/latency.
4. Chuyển một phần traffic qua v2.
5. Migrate dần traffic, giữ khả năng rollback sang v1.
6. Xóa v1 khi đã ổn định và không còn phụ thuộc.

Không thay index trong production mà không có canary/safe rollout khi đây là tính năng critical.

## 20. Tối ưu hiệu năng của MongoDB Search

### 20.1. Chọn phạm vi index vừa đủ

Với **dynamic:false**, chỉ index các fields cần dùng cho Search. Nếu một collection có hàng trăm fields nhưng API chỉ tìm title, description, tags và filter vài field, không cần index mọi field.

Index quá rộng có thể:

- Tăng chi phí bộ nhớ/ổ đĩa Search.
- Tăng công việc đồng bộ khi document thay đổi.
- Gây lộ dữ liệu vào Search index ngoài ý định.
- Làm khó kiểm soát analyzer và relevance.

Nên định nghĩa Search index theo use case thay vì “index everything”.

### 20.2. Autocomplete nGram có chi phí index

Một term dài có thể sinh nhiều n-grams hơn một term ngắn. Các phương án **nGram**, minGrams quá nhỏ hoặc maxGrams quá lớn có thể tăng index size và số candidates.

Nếu user thường gõ từ đầu của tên sản phẩm, **edgeGram** là một điểm khởi đầu hợp lý. Chỉ chọn nGram khi thật sự cần match ở giữa từ và có benchmark.

### 20.3. Giới hạn fuzzy expansions

Fuzzy với **maxEdits=2**, **prefixLength=0** và **maxExpansions** rất lớn có thể tạo nhiều matches sai và chi phí cao.

Một chiến lược:

1. Thử exact text/phrase trước.
2. Dùng fuzzy ở một số trường hợp query đủ dài.
3. Không fuzzy trên mã SKU/tenant ID nếu business cần exact.
4. Giới hạn maxExpansions và result count.
5. Theo dõi p95/p99 latency và zero-hit rate.

### 20.4. Filter early bằng compound.filter

Lọc tenant/active/category/price **trong $search** có thể giảm số candidates cần score và trả về. Đưa các điều kiện cứng vào **filter** thay vì hậu xử lý sau Search khi có toán tử Search phù hợp.

Hãy kiểm tra index mapping: **equals với tenantId kiểu token** và **range với priceCents kiểu number** không giống một điều kiện trên field string không được index đúng type.

### 20.5. Giới hạn output và payload

- Chỉ trả top N results.
- Chỉ project fields cần cho UI.
- Không trả scoreDetails/highlights trong những endpoints không cần.
- Hạn chế requests autocomplete trên mỗi phím bằng debounce/cancel.
- Không dùng skip hàng trăm nghìn nếu có thể dùng searchAfter.
- Cân nhắc caching các query phổ biến khi authorization/freshness cho phép.

### 20.6. Giảm chi phí faceting

Facets thường tốn thêm công việc tính toán. Không cần tính mọi facet của catalog khi người dùng chỉ mở menu gợi ý.

Có thể tách hai endpoints:

~~~text
GET /search/suggest?q=chu
  -> autocomplete, top 8, không facets.

GET /search/products?q=chuot&category=mouse
  -> text/compound, pagination, facets khi cần.
~~~

Chỉ yêu cầu exact total count khi UX thật sự cần. Lower-bound counts hoặc “còn kết quả tiếp” có thể phù hợp khi ưu tiên latency.

### 20.7. Phân tích query plan

Trên phiên bản/triển khai có hỗ trợ explain cho Search, có thể dùng công cụ **Search Query Analyzer/explain** để đánh giá stages, số candidates và latency.

Đừng suy kết quả từ B-tree index explain của find là đã đo được toàn bộ chi phí MongoDB Search. Search có cơ chế index/scoring riêng.

### 20.8. Theo dõi index freshness

Nếu cập nhật sản phẩm từ backend nhưng Search results chậm đổi, cần quan sát:

- Search index build/sync status.
- Write throughput và indexing backlog.
- Search node CPU/memory/storage.
- Query latency khi index đang cập nhật.
- Các lỗi trong Search service hoặc network.

Index freshness là một phần của **SLO tìm kiếm** và có thể cần thông báo cho UI/admin khi chậm.

## 21. Đánh giá chất lượng kết quả, không chỉ độ trễ

Một Search query trả response trong 20 ms vẫn có thể là **kết quả tệ** nếu user không tìm thấy sản phẩm cần mua.

### 21.1. Precision và recall

Giả sử query **"chuột Bluetooth"** có 10 sản phẩm thật sự liên quan.

Search trả top 5, trong đó 4 liên quan:

~~~text
precision@5 = 4 / 5 = 0.8
recall@5    = 4 / 10 = 0.4
~~~

Fuzzy thường làm tăng recall nhưng có thể làm giảm precision. Tăng boost title có thể cải thiện top-positions nhưng cũng có thể bỏ sót những descriptions hữu ích.

### 21.2. Ranking metrics

Những chỉ số phổ biến:

| Metric | Ý nghĩa |
|---|---|
| **Precision@K** | Tỷ lệ kết quả liên quan trong top K. |
| **Recall@K** | Tỷ lệ những kết quả liên quan đã được tìm thấy trong top K. |
| **MRR** | Vị trí nghịch đảo của kết quả đúng đầu tiên, trung bình theo queries. |
| **NDCG@K** | Đánh giá thứ tự top K khi có nhiều mức relevance. |
| **Zero-result rate** | Tỷ lệ queries không tìm được gì. |
| **CTR / conversion** | Hành vi người dùng sau khi thấy kết quả, cần cân nhắc bias. |
| **Latency p50/p95/p99** | Độ trễ của search và suggest endpoints. |

Không chỉ tối ưu cho CTR vì click có thể bị ảnh hưởng bởi vị trí, ảnh, giá, khuyến mãi và UX.

### 21.3. Tạo tập query đánh giá

Một bộ test nên có:

| Query | Mục tiêu |
|---|---|
| chuột | Tìm các sản phẩm chuột trong tenant. |
| chuột không dây | Ưu tiên title và phrase liên quan. |
| bluetooh | Có kết quả Bluetooth khi fuzzy được bật. |
| chuo | Xử lý không dấu/typo tùy analyzer được thiết kế. |
| chu | Autocomplete trả các title phù hợp. |
| M100 | Tìm mã sản phẩm chính xác. |
| tai nghe không dây | Không bị ranking lẫn với chuột. |
| từ khóa không tồn tại | Trả empty state hợp lý, không truy vấn vô hạn. |

Thêm các queries từ search logs đã được làm sạch/anonymized, tránh đưa PII vào dataset đánh giá.

### 21.4. A/B test ranking

Một thay đổi như tăng title boost từ 3 lên 8 có thể:

- Nâng các products khớp tiêu đề lên.
- Đẩy products có description rất liên quan xuống thấp.
- Làm một số query dài có quality tốt hơn, các query ngắn lại tệ đi.

Vì vậy nên có **ranking profile version**, chạy offline evaluation và canary traffic trước khi thay đổi toàn bộ production.

### 21.5. Đừng hardcode kết quả theo một score cố định

Không viết test kiểu:

~~~text
P-100 phải luôn có searchScore == 3.147
~~~

Scores có thể thay đổi vì corpus, analyzer hoặc engine version. Nên kiểm tra **tính đúng của filter**, những kết quả relevance chủ chốt và **thứ tự tương đối** trong phạm vi được kiểm soát.

## 22. Những lỗi thường gặp

### 22.1. Dùng index text truyền thống cho $search

~~~javascript
db.products.createIndex({ title: "text" });
~~~

Lệnh này **không tạo** MongoDB Search index. Muốn dùng $search, phải tạo Search index tương ứng trên deployment hỗ trợ.

### 22.2. Đặt $match trước $search

~~~javascript
[
  { $match: { tenantId: "store-a" } },
  { $search: { /* ... */ } }
]
~~~

Trong aggregation pipeline thông thường, **$search phải ở đầu**. Dùng compound.filter để áp điều kiện sớm ở Search engine.

### 22.3. Quên filter tenant trong autocomplete

Autocomplete vẫn có thể trả tên sản phẩm của tenant khác. Phải kiểm tra tenant ở cả endpoints search và suggest.

### 22.4. Định nghĩa category là string full-text rồi dùng equals

Nếu cần **equals trên string nguyên giá trị**, index mapping phải tương ứng, thường là **token**. Full-text string analyzer có semantics khác.

### 22.5. Fuzzy trên query ngắn

Một ký tự sai trong từ 2–3 ký tự có thể làm matches rất rộng. Dùng minimum input length, prefixLength, maxEdits phù hợp và đo false positives.

### 22.6. Coi autocomplete là search full-text cuối cùng

Autocomplete được tối ưu cho prefix. Nó không nhất thiết xếp exact/full-word matches tốt nhất cho mọi query. Kết hợp text/phrase và boost khi cần.

### 22.7. Coi searchScore là xác suất

Score 7.5 không có nghĩa “phù hợp 75%”. Dùng nó cho thứ tự, không cho xác suất nếu chưa xây mô hình hiệu chỉnh riêng.

### 22.8. Không đặt minimumShouldMatch

Một compound có should và filter có thể trả documents chỉ thỏa filter mà không match keyword nếu should không bắt buộc. Đặt **minimumShouldMatch:1** khi đó là yêu cầu.

### 22.9. Dùng regex để mô phỏng fuzzy

Regex không tự tính edit distance hay BM25. Nó không phải giải pháp thay thế fuzzy Search index.

### 22.10. Đưa mọi thông tin vào Search index

Index cả fields nhạy cảm, internalNotes hoặc credentials không cần thiết làm tăng nguy cơ lộ dữ liệu và chi phí. Dùng mapping rõ ràng, nguyên tắc tối thiểu.

### 22.11. Trả kết quả stale như dữ liệu authoritative

Search index cập nhật bất đồng bộ; giá và tồn kho tại checkout phải được kiểm tra lại trong MongoDB source.

### 22.12. Facet counts không cùng scope với results

Results lọc tenant A, nhưng metadata query đếm cả tenant B sẽ gây lộ thống kê và sai UI. Dùng cùng authorized scope ở mọi Search/searchMeta query.

### 22.13. Deep pagination bằng skip lớn

Skip hàng trăm nghìn tăng chi phí. Cân nhắc searchAfter và stable sort theo API/driver hỗ trợ.

### 22.14. Không kiểm tra sự thay đổi analyzer

Tối ưu analyzer cho tiếng Việt có thể thay đổi tokenization và relevance của mọi query. Cần test corpus, mapping versions và rollout.

### 22.15. Tin rằng Search index có consistency như transaction

Search index có latency đồng bộ. Không dùng Search query để chứng minh một write mới nhất đã xuất hiện hay một quyền truy cập vừa đổi đã được áp dụng ngay trong index.

### 22.16. Lỗi lộ dữ liệu qua highlight

Highlight có thể chứa snippets từ fields nhạy cảm được index. Không index/highlight fields mà người dùng không được phép xem; frontend phải escape nội dung.

### 22.17. Không validate giá trị filter và limit

Giá âm, min > max, limit cực lớn hoặc categories không hợp lệ có thể làm query sai hoặc tốn tài nguyên. Validate types và ranges trước khi dựng DSL.

## 23. Checklist triển khai Search trong production

### 23.1. Dữ liệu và index

1. Xác định fields search vs fields exact filter.
2. Thiết kế analyzer cho ngôn ngữ thực tế.
3. Chọn string/token/autocomplete/number/date mappings đúng chức năng.
4. Giới hạn dynamic index và tránh fields nhạy cảm.
5. Giữ dữ liệu chuẩn hóa cho tenant/category/price.
6. Có phiên bản Search index và kế hoạch rollout/rebuild.

### 23.2. Query và ranking

1. Bắt đầu với text/phrase query đơn giản.
2. Đưa constraints vào compound.filter.
3. Dùng fuzzy khi đủ độ dài và business chấp nhận false positives.
4. Tách suggest autocomplete khỏi search results.
5. Đặt boosts title/description/phrase có chủ đích.
6. Dùng scoreDetails/explain khi tuning, không bật cho mọi user.
7. Project fields tối thiểu và giới hạn số kết quả.
8. Có plan cho counts/facets/pagination.

### 23.3. Bảo mật và correctness

1. Không cho client chọn tenantId trong security filter.
2. Không nhận raw aggregation/search DSL từ client.
3. Không tin Search index là authoritative đối với checkout/permissions.
4. Escape highlights.
5. Không log raw user PII/search terms nếu chưa có chính sách.
6. Áp dụng rate limiting/debounce/timeouts.
7. Không để fallback broad search làm lộ dữ liệu.

### 23.4. Monitoring và đánh giá

1. Query latency p50/p95/p99 theo endpoint.
2. Search index freshness/build status.
3. Throughput, error/timeout rate.
4. Zero-result rate và empty suggestions.
5. Chất lượng precision@K/NDCG trên tập query chuẩn.
6. Index size và Search resource utilization.
7. A/B test ranking changes trước rollout.

## 24. Bài thực hành

### Bài 1 — So sánh exact, regex và Search

Với title **"Chuột không dây M100"**, hãy giải thích sự khác nhau giữa:

~~~javascript
db.products.find({ title: "Chuột không dây M100" });

db.products.find({ title: /^Chuột/i });

db.products.aggregate([
  {
    $search: {
      index: "products_search",
      text: {
        query: "chuột",
        path: "title"
      }
    }
  }
]);
~~~

Trường hợp nào phù hợp khi user muốn sửa lỗi gõ?

### Bài 2 — Text index truyền thống

Tạo text index trên title/description với weights title=10, description=2. Chạy $text và project textScore. Vì sao không thể dùng index đó làm Search autocomplete index?

### Bài 3 — Search index mappings

Từ schema products, chọn mapping cho:

~~~text
title
titleSuggest
tenantId
category
priceCents
active
publishedAt
~~~

Giải thích vì sao tenantId không nên dùng analyzer full-text.

### Bài 4 — Search một field

Viết $search.text tìm **"Bluetooth"** chỉ trong description. Project title, description, searchScore rồi sort giảm dần.

### Bài 5 — Search nhiều fields

Mở rộng bài 4 tìm đồng thời title, description, tags. Tại sao một document chỉ có Bluetooth trong tags vẫn có thể khớp?

### Bài 6 — Phrase và text

Viết hai truy vấn:

1. text query **"không dây"** trên title.
2. phrase query **"không dây"**, slop=0.

Mô tả khác biệt về yêu cầu thứ tự/khoảng cách terms.

### Bài 7 — compound.must

Tìm documents có cả terms **"chuột"** và **"bluetooth"** trong title/description/tags. Viết hai must clauses thay vì một text query array.

### Bài 8 — Tenant và active filters

Tìm chuột cho **store-a** nhưng không trả P-900 của store-b hoặc P-105 inactive. Viết compound.filter và giải thích vì sao filter không đóng góp score.

### Bài 9 — Lọc range

Thêm priceCents trong khoảng **200000–500000**, stock > 0. Giải thích vì sao cần mapping number cho cả hai fields.

### Bài 10 — mustNot

Tìm **"không dây"** nhưng loại category **headphone**, vẫn chỉ lấy store-a. Viết compound.mustNot và filter.

### Bài 11 — minimumShouldMatch

Thiết kế compound có hai should clauses, một match title và một match description, cùng filter active=true. Tại sao nên đặt minimumShouldMatch:1?

### Bài 12 — Fuzzy typo

User nhập **"bluetooh"**. Viết text.fuzzy với maxEdits=1, prefixLength=2, maxExpansions=50. Liệt kê ít nhất hai rủi ro nếu tăng maxEdits quá lớn.

### Bài 13 — Exact match được boost

Viết compound.should gồm:

- text match bình thường, boost=5.
- text fuzzy maxEdits=1, boost=1.

Giải thích tại sao khi user nhập đúng chính tả, exact clause thường có lợi thế.

### Bài 14 — Tiếng Việt có dấu và không dấu

Với queries **"chuột"**, **"chuot"**, **"điện thoại"** và **"dien thoai"**, thiết kế một test corpus để đánh giá analyzer/search normalization. Vì sao không đủ chỉ bật fuzzy?

### Bài 15 — Autocomplete khi nhập

Tạo query autocomplete trên titleSuggest với query **"Chu"**, tokenOrder:"sequential". Giới hạn 8 hits và filter store-a/active=true.

### Bài 16 — edgeGram và nGram

Nêu khác biệt giữa edgeGram và nGram. Nếu nhu cầu chỉ là gõ đầu từ, cách nào thường là điểm khởi đầu gọn hơn?

### Bài 17 — Fuzzy autocomplete

Viết autocomplete với query **"bluetoh"**, maxEdits=1. Tại sao nên có ngưỡng độ dài query và debounce?

### Bài 18 — Xếp hạng title vs description

Viết compound.should với title boost=5, description boost=1, minimumShouldMatch=1. Tại sao boost không được dùng để thay tenant filter?

### Bài 19 — Boost phrase

Tìm **"chuột không dây"**, boost phrase title slop=0 cao hơn text description. Mô tả khi nào một title match exact phrase có thể được ưu tiên.

### Bài 20 — Hiển thị searchScore

Thêm $project với score {$meta:"searchScore"} và $sort giảm dần. Giải thích vì sao score=8 không có nghĩa 80% xác suất đúng.

### Bài 21 — Highlight

Tìm **"bluetooth"**, yêu cầu highlight title và description. Nêu cách render segments an toàn để tránh XSS.

### Bài 22 — Count và facets

Tạo $searchMeta đếm kết quả Bluetooth trong store-a và facets cho category cùng price bands. Vì sao phải dùng cùng điều kiện tenant ở cả results và metadata query?

### Bài 23 — Disjunctive faceting

User đã chọn category=mouse. Thiết kế facet category để UI vẫn nhìn thấy số sản phẩm của các categories khác. Cần xử lý filter category như thế nào khi tính facet?

### Bài 24 — Pagination

Tạo $skip/$limit cho trang 2. Sau đó mô tả cách dùng searchSequenceToken/searchAfter cho các trang sâu và lý do không thể dùng Change Stream resume token thay thế.

### Bài 25 — API security

Một client gửi:

~~~json
{
  "query": "chuột",
  "tenantId": "store-b",
  "limit": 1000000
}
~~~

Backend đã xác thực user thuộc store-a. API phải xử lý tenantId và limit thế nào? Vì sao không được cho client gửi raw $search DSL?

### Bài 26 — Checkout consistency

Một kết quả Search trả stock=1, nhưng hai người dùng đặt hàng cùng lúc. Tại sao không thể trừ stock chỉ dựa trên Search result? Đề xuất conditional write/transaction trên source collection.

### Bài 27 — Java Sync Driver

Viết Java aggregation dùng org.bson.Document với $search đứng đầu, compound.must text, compound.filter tenantId và active, project searchScore, sort và limit.

### Bài 28 — Spring Data

Viết MongoTemplate.aggregate() với AggregationOperation tạo $search raw Document. Giải thích lỗi nếu một Aggregation.match() được đặt trước Search stage.

### Bài 29 — Relevance evaluation

Tạo bộ 10 queries có nhãn sản phẩm đúng/sai, tính precision@5 và đo latency p95. Nếu fuzzy giúp nhiều queries có kết quả hơn nhưng precision@5 giảm, nhóm sẽ quyết định thế nào?

### Bài 30 — Index rollout

Bạn muốn đổi analyzer để hỗ trợ tiếng Việt không dấu. Mô tả kế hoạch index v2, build, offline relevance tests, canary và rollback mà không làm hỏng endpoint production.

## 25. Câu hỏi ôn tập

1. MongoDB text index khác MongoDB Search index ra sao?
2. Tại sao $search không đặt sau $match trong pipeline thông thường?
3. Search analyzer ảnh hưởng query kết quả bằng những cách nào?
4. Khi nào dùng mapping string và khi nào dùng token?
5. Vì sao autocomplete cần mapping autocomplete riêng?
6. text khác phrase như thế nào?
7. must và should khác nhau ra sao?
8. Khi nào minimumShouldMatch bắt buộc đối với business query?
9. Vì sao compound.filter không làm tăng điểm relevance?
10. Tại sao cần filter tenant ở chính Search query?
11. Fuzzy edit distance giải quyết gì và không giải quyết gì?
12. maxEdits, prefixLength, maxExpansions có ý nghĩa thế nào?
13. Vì sao fuzzy trên từ ngắn dễ có false positives?
14. Autocomplete tokenOrder:"sequential" khác "any" thế nào?
15. edgeGram, rightEdgeGram và nGram khác nhau ra sao?
16. Vì sao debounce là quyết định UX/backend chứ không phải Search index setting?
17. searchScore có phải xác suất user sẽ click hay kết quả chính xác không?
18. Boost và constant score có khác nhau không?
19. Vì sao title match thường được boost hơn description match?
20. Highlight trả metadata nào và frontend cần bảo vệ gì?
21. $searchMeta phù hợp với counts/facets như thế nào?
22. Category facet có thể bị ảnh hưởng ra sao bởi filter category đang chọn?
23. Tại sao skip rất lớn có thể gây độ trễ?
24. Search pagination token khác Change Stream resume token ra sao?
25. Nếu Search index vừa được cập nhật, phân trang có thể thay đổi như thế nào?
26. Search index có luôn phản ánh ngay những writes vừa commit không?
27. Vì sao giá/stock ở checkout phải được xác nhận từ source of truth?
28. Java Driver dùng org.bson.Document để tạo $search stage như thế nào?
29. Spring Data derived query có tự dùng fuzzy MongoDB Search không?
30. Cần những chỉ số nào để đánh giá cả độ trễ lẫn chất lượng relevance?

## 26. Tổng kết

Xây tìm kiếm văn bản hiệu quả trong MongoDB cần xem **truy vấn, lọc, fuzzy, autocomplete và xếp hạng** là các phần của cùng một trải nghiệm người dùng:

~~~text
User query
   |
   +-- Đang gõ tiền tố?
   |       |
   |       v
   |   autocomplete + prefix index
   |
   +-- Đã nhập đủ từ khóa?
           |
           v
       text / phrase
           |
           +-- Cần chấp nhận typo?
           |       |
           |       v
           |     fuzzy
           |
           v
       compound.filter
         tenant, active, category, price, stock
           |
           v
       relevance score + boosts
           |
           v
       ranking / pagination
           |
           v
       highlights, facets, result DTO
           |
           v
       UI và downstream actions
~~~

Các nguyên tắc quan trọng nhất:

1. **MongoDB Search $search/$searchMeta khác $text truyền thống**; cần Search index/triển khai hỗ trợ.
2. **Mapping phải phù hợp kiểu truy vấn**: string cho analyzed text, token cho exact string filters, autocomplete cho suggestions, number/date cho ranges.
3. **compound.filter là nơi đặt ràng buộc cứng** như tenant/active/price; không dùng ranking boost để mô phỏng authorization.
4. **Fuzzy cải thiện recall nhưng có nguy cơ false positives**; kiểm soát maxEdits, prefixLength, maxExpansions và query length.
5. **Autocomplete dành cho prefix khi gõ**, nên dùng request nhỏ, debounce và filter cùng phạm vi truy cập.
6. **searchScore dùng cho xếp hạng tương đối**, không phải một xác suất chuẩn hóa; boost nên được đánh giá trên tập query thực tế.
7. **Highlight, facets, count và pagination** có yêu cầu về metadata, index mapping và consistency với query filters.
8. **Search index đồng bộ bất đồng bộ**, không thay source-of-truth trong authorization cấp cuối hoặc checkout.
9. **Java Sync Driver/Spring Data** có thể truyền Search stages bằng BSON/Document với $search ở đầu pipeline.
10. **Chất lượng tìm kiếm** được đo bằng precision/recall, NDCG, zero-hit rate và business outcomes, không chỉ latency.

### Tài liệu tham khảo chính thức

- [MongoDB Search — tổng quan](https://www.mongodb.com/docs/atlas/atlas-search/) — khả năng full-text Search và index.
- [MongoDB Search Index Definitions](https://www.mongodb.com/docs/atlas/atlas-search/define-field-mappings/) — string, token, autocomplete, numbers và mapping.
- [$search Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/search/) — cú pháp $search và các tùy chọn.
- [$searchMeta Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/searchMeta/) — count/facet metadata.
- [text Operator](https://www.mongodb.com/docs/atlas/atlas-search/text/) — full-text match và fuzzy.
- [phrase Operator](https://www.mongodb.com/docs/atlas/atlas-search/phrase/) — phrase, slop.
- [autocomplete Operator](https://www.mongodb.com/docs/atlas/atlas-search/autocomplete/) — gợi ý tiền tố và typo tolerance.
- [compound Operator](https://www.mongodb.com/docs/atlas/atlas-search/compound/) — must, should, filter, mustNot.
- [equals Operator](https://www.mongodb.com/docs/atlas/atlas-search/equals/) — exact field matching.
- [range Operator](https://www.mongodb.com/docs/atlas/atlas-search/range/) — numeric/date range filters.
- [Score Results](https://www.mongodb.com/docs/atlas/atlas-search/scoring/) — searchScore và các cách điều chỉnh.
- [Highlight Search Terms](https://www.mongodb.com/docs/atlas/atlas-search/highlighting/) — searchHighlights.
- [Facet Search Results](https://www.mongodb.com/docs/atlas/atlas-search/facet/) — facets và counts.
- [Paginate Search Results](https://www.mongodb.com/docs/atlas/atlas-search/paginate-results/) — searchSequenceToken/searchAfter.
- [MongoDB $text Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/) — text index truyền thống.
- [MongoDB Java Sync Driver Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — aggregate với BSON stages.
- [Spring Data MongoDB Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — MongoTemplate và AggregationOperation.

Khi thiết kế Search API, hãy bắt đầu bằng câu hỏi **“người dùng đang muốn tìm gì và kết quả nào thực sự phù hợp?”**. Sau đó mới xác định analyzer, full-text clause, các bộ lọc bắt buộc, fuzzy/autocomplete và ranking signals. Một Search index tốt không chỉ đưa ra kết quả nhanh; nó còn phải **trả đúng dữ liệu người dùng được phép xem, chịu được lỗi gõ, có thứ tự hợp lý và vận hành an toàn khi catalog thay đổi**.









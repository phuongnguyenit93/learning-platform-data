# Chi phí script, an toàn đầu vào và kiểm thử trường hợp biên

Painless script cho phép cập nhật document và tính toán dữ liệu ngay trong Elasticsearch. Script hữu ích khi một thao tác cần đọc nhiều field, áp dụng điều kiện hoặc biến đổi dữ liệu theo từng document. Tuy nhiên, script có chi phí CPU, có thể tạo tải ghi lớn và trở thành rủi ro nếu ứng dụng ghép đầu vào không tin cậy trực tiếp vào mã script.

Khi dùng script trong Spring Data Elasticsearch, cần kiểm soát ba khía cạnh:

- **Chi phí:** phân biệt chi phí biên dịch script với chi phí thực thi trên từng document; ước lượng số document bị cập nhật và lượng dữ liệu phải ghi lại.
- **An toàn đầu vào:** giữ mã script cố định, truyền dữ liệu qua `params`, kiểm tra kiểu và miền giá trị ở tầng ứng dụng.
- **Trường hợp biên:** xác định hành vi khi field thiếu, null, sai kiểu, collection rỗng, giá trị vượt giới hạn, request lặp lại hoặc có cập nhật đồng thời.

Script không nên là lựa chọn mặc định cho mọi thao tác. Nếu một thao tác có thể thực hiện bằng update một field, ingest pipeline hoặc xử lý ở ứng dụng mà không cần đọc trạng thái document trên Elasticsearch, hãy cân nhắc giải pháp đơn giản hơn.

## 1. Script trong Elasticsearch làm việc như thế nào?

Elasticsearch hỗ trợ Painless, một ngôn ngữ script được thiết kế cho các thao tác trên dữ liệu Elasticsearch. Script có thể chạy trong nhiều context, chẳng hạn:

- Update context: thay đổi `_source` của document.
- Update by query context: cập nhật nhiều document thỏa query.
- Ingest context: biến đổi document trong ingest pipeline.
- Score context: tính điểm relevance.
- Sort hoặc aggregation context: dùng biểu thức trong một số truy vấn và aggregation.

Mỗi context có các biến và API được phép khác nhau. Ví dụ, update script thường đọc và ghi qua `ctx._source`, trong khi script score có thể truy cập field thông qua `doc`. Không nên lấy ví dụ của context này áp dụng nguyên xi cho context khác.

Ví dụ update một document:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = params.stock",
    "params": {
      "stock": 25
    }
  }
}
~~~

Elasticsearch nhận mã Painless, biên dịch nếu cần, rồi thực thi trong update context trên document được chỉ định. Script gán field stock thành giá trị trong `params`.

Với update script, `ctx._source` là map biểu diễn nội dung `_source` của document. `params` là map chứa dữ liệu đầu vào mà ứng dụng truyền vào request. Dùng `params` giúp giữ mã script ổn định và tách logic khỏi dữ liệu.

## 2. Hai loại chi phí: biên dịch và thực thi

Khi đánh giá hiệu năng script, cần tách hai công đoạn:

1. **Compilation:** Elasticsearch biên dịch mã Painless thành dạng có thể thực thi.
2. **Execution:** Elasticsearch chạy script trong context của document hoặc truy vấn.

Chi phí biên dịch thường được giảm bằng script compilation cache. Chi phí thực thi vẫn phát sinh mỗi lần script được chạy.

### 2.1. Chi phí biên dịch

Nếu mỗi request gửi một chuỗi script khác nhau, Elasticsearch có thể phải biên dịch nhiều phiên bản script. Việc tạo quá nhiều script source duy nhất trong thời gian ngắn có thể làm tăng compilation, gây cache churn và chạm giới hạn tốc độ biên dịch.

Ví dụ không nên làm:

~~~java
String source = "ctx._source.stock = " + userProvidedStock;
~~~

Mỗi giá trị đầu vào tạo ra source khác nhau. Cách này còn trộn dữ liệu với mã chương trình, khiến việc kiểm soát an toàn khó hơn.

Nên giữ source cố định và truyền giá trị qua params:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = params.stock",
    "params": {
      "stock": 25
    }
  }
}
~~~

Khi source, ngôn ngữ và context giống nhau, Elasticsearch có thể tái sử dụng script đã biên dịch từ cache. Thay đổi giá trị params không cần tạo một source mới.

### 2.2. Chi phí thực thi

Cache không làm cho script chạy miễn phí. Mỗi document được xử lý vẫn cần thực thi biểu thức, đọc field, kiểm tra điều kiện và có thể sửa `_source`.

Chi phí thực thi tăng theo:

- Số document được xử lý.
- Độ phức tạp của biểu thức và số vòng lặp.
- Số field hoặc phần tử collection được đọc.
- Kích thước `_source` phải tải và ghi lại.
- Số shard tham gia và mức độ song song.
- Tốc độ ghi, refresh và merge của index.
- Thời gian xử lý ở hệ thống đích nếu tác vụ kết hợp với export hoặc đồng bộ.

Một script ngắn chạy trên hàng triệu document vẫn có thể tốn tài nguyên đáng kể. Ngược lại, một script phức tạp chạy trên một document có thể không đáng kể. Luôn đánh giá cả chi phí trên mỗi document lẫn số document bị tác động.

### 2.3. Compilation cache và giới hạn

Elasticsearch có script cache và các thiết lập giới hạn tốc độ biên dịch. Tên cấu hình và giá trị mặc định có thể thay đổi theo phiên bản. Các thiết lập thường gặp gồm:

- `script.cache.max_size`: số script đã biên dịch có thể giữ trong cache.
- `script.cache.expire`: thời gian hết hạn của mục cache nếu cấu hình được bật.
- `script.max_compilations_rate`: giới hạn tốc độ biên dịch script.
- `script.allowed_types`: loại script được phép, ví dụ inline hoặc stored.
- `script.allowed_contexts`: context script được phép chạy.

Không nên thay đổi giới hạn chỉ để che việc tạo source động. Trước tiên hãy dùng source cố định, params và stored script khi phù hợp. Nếu cần điều chỉnh cấu hình cluster, đo compilation rate và cache eviction trên tải thực tế, rồi thay đổi theo chính sách vận hành của hệ thống.

## 3. Script source cố định và params

Một nguyên tắc quan trọng là không ghép dữ liệu đầu vào vào chuỗi mã script. Giữ source cố định, truyền giá trị qua `params`.

Ví dụ tăng tồn kho theo số lượng nhận vào:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = (ctx._source.stock == null ? 0 : ctx._source.stock) + params.delta",
    "params": {
      "delta": 5
    }
  }
}
~~~

Mã script không thay đổi theo delta. Ứng dụng chỉ gửi giá trị mới trong params.

Lợi ích:

- Giảm số source script cần biên dịch.
- Không biến đầu vào thành một phần cú pháp chương trình.
- Dễ đọc, kiểm thử và tái sử dụng script.
- Dễ kiểm soát kiểu dữ liệu và miền giá trị.
- Cho phép chuyển từ inline script sang stored script mà không thay logic nghiệp vụ.

### 3.1. Không cho người dùng gửi script tùy ý

Không tạo API nhận nội dung script do client tự gửi rồi thực thi trực tiếp. Người dùng API chỉ nên chọn một thao tác nghiệp vụ đã được ứng dụng định nghĩa, ví dụ `increaseStock`, `setStatus` hoặc `appendTag`. Server ánh xạ thao tác đó sang source script đã được kiểm soát và chỉ truyền các tham số hợp lệ.

Nếu cần chọn field động, dùng allowlist ở tầng ứng dụng:

~~~java
Set<String> allowedFields =
        Set.of("viewCount", "downloadCount", "favoriteCount");

if (!allowedFields.contains(request.field())) {
    throw new IllegalArgumentException("Unsupported counter field");
}
~~~

Không nối trực tiếp tên field không tin cậy vào source script. Với những field có thể chọn, hãy kiểm tra tên theo allowlist hoặc ánh xạ từ enum sang tên field cố định.

### 3.2. Params không thay thế validation

Truyền dữ liệu qua params giúp tách dữ liệu khỏi mã, nhưng không tự bảo đảm dữ liệu hợp lệ. Ví dụ delta có thể âm, null, quá lớn hoặc không đúng kiểu mà nghiệp vụ cho phép.

Ứng dụng nên validate trước khi gửi request:

- Kiểu dữ liệu đúng.
- Giá trị nằm trong miền cho phép.
- Kích thước chuỗi và collection có giới hạn.
- Enum hoặc trạng thái thuộc danh sách hợp lệ.
- Các giá trị liên quan có quan hệ nhất quán.

Script cũng có thể kiểm tra các bất biến cần được bảo vệ ngay tại nơi cập nhật, nhưng validation ở API vẫn cần thiết để trả lỗi sớm và rõ ràng.

## 4. Painless và giới hạn an toàn

Painless được thiết kế với cơ chế sandbox và allowlist API. Script không phải một chương trình Java tùy ý có toàn quyền truy cập JVM, hệ thống file hoặc mạng. Khả năng sử dụng class và API phụ thuộc context và allowlist của Elasticsearch.

Tuy nhiên, sandbox không có nghĩa mọi script đều an toàn về tài nguyên hoặc logic. Một script có vòng lặp lớn, thao tác trên collection khổng lồ hoặc được chạy trên quá nhiều document vẫn có thể gây tải CPU và bộ nhớ.

Các nguyên tắc:

- Chỉ dùng script source do ứng dụng hoặc đội vận hành kiểm soát.
- Không thực thi source do người dùng cuối gửi lên.
- Truyền dữ liệu qua params.
- Giới hạn kích thước chuỗi, collection và số phần tử xử lý.
- Tránh vòng lặp không có giới hạn rõ ràng.
- Không đọc hoặc ghi field ngoài phạm vi nghiệp vụ.
- Giới hạn số document trong update-by-query bằng query cụ thể.
- Đặt timeout và cơ chế hủy cho tác vụ dài theo khả năng API.
- Phân quyền truy cập endpoint script và index phù hợp.

### 4.1. Kiểm soát loại script và context

Cluster có thể giới hạn loại script được phép và context được phép chạy. Ví dụ, một môi trường chỉ cho phép stored script hoặc chỉ cho phép một số context nhất định. Cấu hình này là biện pháp phòng thủ ở cấp cluster.

Không nên bật mọi loại script và mọi context nếu ứng dụng chỉ cần update script. Ngược lại, không tự ý tắt context mà ứng dụng đang phụ thuộc. Hãy kiểm kê các use case script trước khi thay đổi cấu hình, thử trên môi trường staging và kiểm tra log lỗi compilation hoặc context bị từ chối.

### 4.2. Stored script

Nếu cùng một script được dùng ở nhiều nơi, có thể lưu script trên cluster và gọi bằng ID:

~~~http
PUT /_scripts/increment-stock
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = (ctx._source.stock == null ? 0 : ctx._source.stock) + params.delta"
  }
}
~~~

Sử dụng:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "id": "increment-stock",
    "params": {
      "delta": 5
    }
  }
}
~~~

Stored script giúp quản lý source tập trung và tránh gửi source dài trong từng request. Nó không làm giảm chi phí thực thi trên từng document. Việc cập nhật stored script cần quy trình versioning, review và triển khai có kiểm soát vì nhiều service có thể đang dùng cùng ID.

## 5. Chi phí của update và update-by-query

### 5.1. Update một document

Update API lấy document hiện tại, chạy script hoặc merge partial document, rồi ghi lại phiên bản document mới. Elasticsearch không sửa một vài byte tại chỗ trong Lucene segment. Một lần update tạo phiên bản mới và document cũ được đánh dấu đã xóa để xử lý về sau qua merge.

Vì vậy, script update có chi phí đọc, thực thi và ghi. Nếu document lớn, thay đổi một field nhỏ vẫn có thể cần xử lý và ghi lại document theo cơ chế của Elasticsearch.

Ví dụ:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "ACTIVE"
    }
  }
}
~~~

Đây là một thao tác cho một document. Nếu ứng dụng đã biết giá trị cần đặt và không cần logic dựa trên trạng thái hiện tại, partial document update có thể đơn giản hơn script:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

Chọn script khi cần điều kiện hoặc tính toán dựa trên document hiện tại. Chọn partial update khi chỉ cần gán một số field đã biết.

### 5.2. Update by query

`_update_by_query` tìm các document khớp query rồi chạy script trên từng document:

~~~http
POST /products/_update_by_query
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "LEGACY"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "ARCHIVED"
    }
  }
}
~~~

Tác vụ có thể chạm hàng nghìn hoặc hàng triệu document. Chi phí gồm tìm kiếm document, tải nội dung cần xử lý, thực thi script và ghi lại document đã cập nhật. Số shard, số document khớp, kích thước `_source`, tốc độ ghi và refresh đều ảnh hưởng thời gian hoàn thành.

Trước khi chạy trên production:

1. Chạy query riêng để ước lượng số document khớp.
2. Kiểm tra một mẫu document và kết quả dự kiến của script.
3. Ước lượng dung lượng và tải ghi.
4. Thử trên staging hoặc một phạm vi nhỏ.
5. Đặt giới hạn tốc độ và theo dõi task.
6. Chuẩn bị cách xử lý version conflict và lỗi từng batch.

### 5.3. Throttle, slice và tác vụ bất đồng bộ

Update-by-query hỗ trợ các cơ chế điều tiết và theo dõi tác vụ:

- `requests_per_second` giới hạn tốc độ batch theo cấu hình request.
- `wait_for_completion=false` cho phép chạy bất đồng bộ và nhận task ID.
- `slices` chia công việc thành các phần chạy song song.
- Task API cho phép theo dõi tiến độ, lỗi và trạng thái.
- Có thể dùng task cancellation nếu tác vụ cần dừng và API/phiên bản hỗ trợ.

Tăng số slice có thể tăng thông lượng nhưng cũng tăng áp lực lên CPU, heap và I/O. Không nên đặt song song tối đa theo cảm tính. Hãy điều chỉnh dựa trên tải cluster và mức độ ưu tiên của truy vấn người dùng.

Ví dụ chạy bất đồng bộ có throttle:

~~~http
POST /products/_update_by_query?wait_for_completion=false&requests_per_second=200
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "LEGACY"
    }
  },
  "script": {
    "source": "ctx._source.status = 'ARCHIVED'"
  }
}
~~~

Response trả task ID để theo dõi qua Tasks API. Tốc độ 200 request mỗi giây chỉ là ví dụ cấu hình; phải chọn theo tải thực tế và semantics của throttle đối với batch.

### 5.4. Version conflict và retry

Trong khi update-by-query chạy, một document có thể bị ứng dụng khác cập nhật. Khi đó tác vụ có thể gặp version conflict. Tùy yêu cầu, có thể để tác vụ dừng khi gặp conflict hoặc tiếp tục các document còn lại với `conflicts=proceed`.

~~~http
POST /products/_update_by_query?conflicts=proceed
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "LEGACY"
    }
  },
  "script": {
    "source": "ctx._source.status = 'ARCHIVED'"
  }
}
~~~

`conflicts=proceed` không giải quyết conflict bằng cách ghi đè dữ liệu mới hơn. Nó cho phép tác vụ tiếp tục và báo số conflict trong response. Ứng dụng cần quyết định có retry các document bị conflict hay không, và phải tránh retry mù quáng với script không idempotent.

## 6. Idempotency và cập nhật lặp lại

Một script idempotent cho cùng kết quả khi chạy lại với cùng đầu vào và trạng thái mục tiêu. Tính chất này quan trọng vì request có thể được retry sau timeout, tác vụ có thể chạy lại hoặc một batch có thể được gửi nhiều lần.

Ví dụ gán trạng thái:

~~~json
{
  "script": {
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "ARCHIVED"
    }
  }
}
~~~

Chạy nhiều lần vẫn đặt status thành ARCHIVED. Đây là thao tác idempotent theo field status.

Ngược lại, tăng counter:

~~~json
{
  "script": {
    "source": "ctx._source.viewCount += params.delta",
    "params": {
      "delta": 1
    }
  }
}
~~~

Chạy hai lần sẽ tăng hai lần. Nếu request đầu đã được Elasticsearch xử lý nhưng response bị mất, client retry có thể làm counter tăng thêm ngoài ý muốn.

### 6.1. Cách xử lý thao tác không idempotent

Một số lựa chọn:

- Dùng event ID duy nhất và lưu dấu đã xử lý để chống áp dụng lại.
- Thiết kế update dựa trên giá trị đích thay vì delta nếu nghiệp vụ cho phép.
- Dùng optimistic concurrency để phát hiện cập nhật dựa trên phiên bản cũ.
- Đưa sự kiện qua hệ thống có cơ chế deduplication.
- Ghi nhận kết quả từng item khi dùng Bulk API.

Không có một cơ chế retry chung phù hợp cho mọi script. Phải xác định trước thao tác có được phép áp dụng nhiều lần hay không.

## 7. An toàn kiểu dữ liệu và field thiếu

Painless làm việc với dữ liệu JSON đã được chuyển thành kiểu runtime. Một field có thể không tồn tại, có giá trị null, có kiểu khác dự kiến hoặc chứa array thay vì scalar.

Script cần xác định rõ hành vi cho từng trường hợp. Không giả định rằng mọi document đều có đủ field hoặc dữ liệu lịch sử luôn tuân theo schema hiện tại.

### 7.1. Phân biệt field thiếu và null

Trong update context, có thể kiểm tra key trong `_source`:

~~~painless
if (!ctx._source.containsKey('stock')) {
    ctx._source.stock = 0;
} else if (ctx._source.stock == null) {
    ctx._source.stock = 0;
}
~~~

Ví dụ trên gán mặc định 0 trong cả hai trường hợp thiếu key và key có giá trị null. Nếu nghiệp vụ cần phân biệt chúng, giữ hai nhánh riêng và định nghĩa kết quả riêng.

Không nên truy cập field lồng nhau mà không kiểm tra các object trung gian. Ví dụ `ctx._source.address.city` có thể lỗi nếu address chưa tồn tại hoặc null. Kiểm tra từng cấp trước khi đọc.

### 7.2. Giá trị sai kiểu

Document cũ có thể chứa:

- `stock` là chuỗi `"10"` thay vì số.
- `price` là null.
- `tags` là chuỗi thay vì mảng.
- `createdAt` có format không thống nhất.

Không nên ép kiểu tùy tiện rồi tiếp tục nếu dữ liệu không đúng hợp đồng. Có thể bỏ qua document, đánh dấu lỗi hoặc dừng tác vụ tùy mức độ quan trọng.

Ví dụ kiểm tra collection trước khi thêm phần tử:

~~~painless
if (!ctx._source.containsKey('tags') || ctx._source.tags == null) {
    ctx._source.tags = [];
}

if (!(ctx._source.tags instanceof List)) {
    throw new IllegalArgumentException('tags must be a list');
}

if (!ctx._source.tags.contains(params.tag)) {
    ctx._source.tags.add(params.tag);
}
~~~

Script trên khởi tạo danh sách khi field thiếu hoặc null, từ chối dữ liệu sai kiểu và chỉ thêm tag nếu chưa tồn tại. Tùy phiên bản Painless và kiểu collection, cú pháp khởi tạo hoặc kiểm tra kiểu cần được xác nhận trên cluster mục tiêu.

### 7.3. Collection rỗng và phần tử trùng

Với mảng, hãy xác định:

- Mảng thiếu có tương đương mảng rỗng không?
- Giá trị null có được phép không?
- Có cho phép phần tử trùng không?
- Có giới hạn số phần tử tối đa không?
- Thứ tự phần tử có mang ý nghĩa không?

Một script append đơn giản có thể làm mảng tăng không giới hạn hoặc tạo phần tử trùng khi retry. Nếu dữ liệu là tập hợp, kiểm tra trùng trước khi thêm. Nếu collection có thể rất lớn, cân nhắc mô hình lưu riêng hoặc thiết kế giới hạn.

## 8. Kiểm soát số học và giá trị biên

Script số học cần xử lý rõ:

- Giá trị âm.
- Số 0.
- Giá trị cực đại hoặc cực tiểu.
- Tràn số nguyên.
- Chia cho 0.
- Số thực NaN hoặc Infinity từ dữ liệu/biểu thức không hợp lệ.
- Ép kiểu giữa integer, long, double và decimal.

Ví dụ tăng stock cần xác định delta có được âm không:

~~~painless
if (params.delta == null) {
    throw new IllegalArgumentException('delta is required');
}

if (params.delta < 0) {
    throw new IllegalArgumentException('delta must not be negative');
}

def current = ctx._source.stock == null ? 0 : ctx._source.stock;

if (!(current instanceof Number)) {
    throw new IllegalArgumentException('stock must be numeric');
}

ctx._source.stock = current.longValue() + params.delta;
~~~

Đây là ví dụ minh họa kiểm tra dữ liệu. Trong code thực tế, nên validate delta ở tầng ứng dụng trước khi gửi script, và kiểm tra miền kết quả để tránh tràn số. Nếu stock có giới hạn nghiệp vụ, kiểm tra current + delta không vượt giới hạn đó.

### 8.1. Chia cho 0

Ví dụ tính giá trung bình:

~~~painless
if (params.count == null || params.count <= 0) {
    throw new IllegalArgumentException('count must be greater than zero');
}

ctx._source.average = params.total / params.count;
~~~

Nếu count có thể bằng 0, cần quyết định hành vi nghiệp vụ: từ chối cập nhật, giữ giá trị cũ, đặt null hay đặt một giá trị mặc định. Không để phép chia lỗi trở thành cách xử lý ngầm.

### 8.2. Làm tròn và tiền tệ

Không nên dùng phép toán floating-point tùy tiện cho tiền tệ nếu nghiệp vụ yêu cầu chính xác đến đơn vị nhỏ nhất. Xác định đơn vị lưu trữ, ví dụ lưu số nguyên theo cents hoặc đơn vị tiền nhỏ nhất, và quy tắc làm tròn ở tầng nghiệp vụ.

Với `scaled_float`, Elasticsearch lưu giá trị theo scaling factor; ứng dụng vẫn cần thống nhất cách chuyển đổi và làm tròn. Đừng cộng một giá trị tiền dạng chuỗi vào số hoặc dựa vào biểu diễn double để đảm bảo chính xác tài chính.

## 9. Kiểm soát kích thước và độ phức tạp đầu vào

Ngay cả khi params không thể biến thành mã script, một đầu vào quá lớn vẫn có thể làm script tốn CPU hoặc bộ nhớ.

Giới hạn các đầu vào:

- Chuỗi có độ dài tối đa.
- Danh sách có số phần tử tối đa.
- Map có số key tối đa và key hợp lệ.
- Số vòng lặp tối đa.
- Khoảng thời gian hoặc khoảng giá nằm trong giới hạn.
- Số document bị tác động bởi update-by-query.

Ví dụ không nên duyệt một collection do client gửi lên mà không giới hạn số phần tử. Nếu client gửi hàng trăm nghìn tag, script sẽ tiêu tốn tài nguyên tương ứng và có thể làm request kéo dài.

Đối với update-by-query, query xác định phạm vi document và script chạy trên từng document trong phạm vi đó. Một query thiếu filter hoặc filter sai có thể làm tác động đến toàn bộ index. Hãy kiểm tra query và ước lượng số hit trước khi thực thi.

## 10. Tránh no-op update và ghi lại không cần thiết

Nếu script không thay đổi document, có thể đặt `ctx.op = 'noop'` để báo Elasticsearch bỏ qua cập nhật:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "source": """
      if (ctx._source.status == params.status) {
        ctx.op = 'noop';
      } else {
        ctx._source.status = params.status;
      }
    """,
    "params": {
      "status": "ACTIVE"
    }
  }
}
~~~

No-op hữu ích khi nhiều request có thể đặt lại cùng một giá trị. Nó tránh tạo phiên bản document mới khi không có thay đổi cần lưu.

Trong update-by-query, có thể dùng `ctx.op = 'noop'` để bỏ qua document không cần sửa sau khi script kiểm tra trạng thái. Không nên dùng no-op để che việc query quá rộng hoặc logic script không rõ ràng; hãy làm cho điều kiện query và điều kiện script dễ hiểu.

## 11. Cập nhật field, xóa field và thao tác document

Trong update context, script có thể thay đổi `_source` hoặc điều khiển operation:

- Gán field mới hoặc cập nhật field hiện có.
- Xóa key khỏi map `_source`.
- Đặt `ctx.op = 'noop'` để bỏ qua cập nhật.
- Đặt `ctx.op = 'delete'` để xóa document khi nghiệp vụ yêu cầu.

Ví dụ xóa field cũ:

~~~json
{
  "script": {
    "source": "ctx._source.remove(params.field)",
    "params": {
      "field": "legacyCode"
    }
  }
}
~~~

Nếu field được chọn từ request, `params.field` vẫn cần được kiểm tra bằng allowlist. Không cho phép client tùy ý xóa field hệ thống, field phân quyền hoặc field dùng làm khóa nghiệp vụ.

Ví dụ bỏ qua document nếu không đủ điều kiện:

~~~painless
if (ctx._source.status != 'PENDING') {
    ctx.op = 'noop';
} else {
    ctx._source.status = 'PROCESSING';
}
~~~

Nếu muốn xóa document có điều kiện, cần kiểm tra chặt chẽ:

~~~painless
if (ctx._source.expired == true) {
    ctx.op = 'delete';
}
~~~

Xóa là thao tác có tác động lớn. Chỉ dùng khi điều kiện nghiệp vụ được xác định rõ, query giới hạn đúng tập document và có cơ chế audit hoặc khôi phục phù hợp.

## 12. Cập nhật đồng thời và optimistic concurrency

Hai request có thể cùng đọc một phiên bản document rồi cố cập nhật. Elasticsearch dùng cơ chế versioning nội bộ để bảo vệ thao tác update. Update API có tùy chọn `retry_on_conflict` để thử lại khi xảy ra version conflict:

~~~http
POST /products/_update/42?retry_on_conflict=3
Content-Type: application/json

{
  "script": {
    "source": "ctx._source.stock = (ctx._source.stock == null ? 0 : ctx._source.stock) + params.delta",
    "params": {
      "delta": 1
    }
  }
}
~~~

Khi retry, Elasticsearch có thể chạy script trên phiên bản document mới hơn. Điều này hữu ích cho phép cộng dồn, nhưng ứng dụng vẫn phải hiểu semantics của thao tác và bảo đảm request không bị gửi lặp từ phía client.

### 12.1. Dùng if_seq_no và if_primary_term

Nếu ứng dụng đọc document, tính toán ở phía client rồi muốn chỉ cập nhật khi document vẫn là phiên bản đã đọc, có thể dùng optimistic concurrency với sequence number và primary term:

~~~http
POST /products/_update/42?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "price": 199.99
  }
}
~~~

Nếu document đã thay đổi kể từ khi đọc, Elasticsearch trả version conflict thay vì ghi đè âm thầm. Ứng dụng có thể đọc lại, tính toán lại hoặc trả lỗi conflict cho caller.

`retry_on_conflict` và `if_seq_no`/`if_primary_term` phục vụ các chiến lược khác nhau:

- `retry_on_conflict`: cho phép Elasticsearch thử lại update dựa trên phiên bản mới hơn.
- `if_seq_no` và `if_primary_term`: yêu cầu cập nhật đúng phiên bản đã quan sát.

Chọn theo yêu cầu nhất quán của nghiệp vụ; không bật retry vô điều kiện nếu script không an toàn khi chạy lại.

## 13. Script trong Bulk API

Khi cần cập nhật nhiều document có ID đã biết, Bulk API giảm số round-trip bằng cách gửi nhiều action trong một request:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"update":{"_index":"products","_id":"42"}}
{"script":{"source":"ctx._source.stock += params.delta","params":{"delta":2}}}
{"update":{"_index":"products","_id":"43"}}
{"script":{"source":"ctx._source.stock += params.delta","params":{"delta":3}}}
~~~

Mỗi update action có thể dùng cùng script source nhưng params khác nhau. Hãy đọc từng item trong bulk response: request bulk có thể trả HTTP thành công nhưng một số item riêng lẻ vẫn thất bại.

Bulk không biến việc cập nhật thành thao tác miễn phí. Nó giảm overhead request, nhưng mỗi document vẫn cần xử lý và ghi. Chọn batch size phù hợp, tránh request quá lớn và có chính sách retry theo từng item.

## 14. Khi nào nên dùng script, khi nào không?

| Nhu cầu | Cách tiếp cận nên cân nhắc |
|---|---|
| Gán một vài field đã biết | Partial document update |
| Tăng counter dựa trên giá trị hiện tại | Update script |
| Chỉ sửa document thỏa điều kiện | Update script có điều kiện hoặc update-by-query |
| Biến đổi dữ liệu khi index | Ingest pipeline |
| Tính toán ở query mà không cần lưu lại | Query/aggregation hoặc script phù hợp context |
| Cập nhật hàng loạt theo ID đã biết | Bulk update |
| Tính toán phức tạp cần thư viện nghiệp vụ hoặc nhiều nguồn dữ liệu | Xử lý ở ứng dụng rồi ghi kết quả |
| Chuyển đổi schema lớn | Reindex hoặc migration có kiểm soát |

Không dùng script chỉ vì nó có thể làm được. Script chạy trong cluster Elasticsearch và tiêu thụ tài nguyên của cluster. Nếu logic cần gọi dịch vụ ngoài, truy cập cơ sở dữ liệu khác hoặc dùng thư viện không được Painless hỗ trợ, hãy thực hiện ở ứng dụng hoặc pipeline phù hợp.

## 15. Kiểm thử script theo lớp

Một script nên được kiểm tra ở nhiều cấp:

1. Unit test logic nghiệp vụ ở tầng ứng dụng: validation, miền giá trị, mapping params.
2. Integration test script trên phiên bản Elasticsearch tương thích.
3. Kiểm thử hiệu năng với số document và kích thước `_source` gần production.
4. Kiểm thử concurrency và retry nếu thao tác có cập nhật đồng thời.

Mock request có thể xác nhận ứng dụng gửi đúng source và params, nhưng không chứng minh Painless script biên dịch và chạy đúng trên Elasticsearch. Cần integration test cho các script quan trọng.

### 15.1. Ma trận trường hợp biên

Với một script cập nhật stock, có thể lập bảng:

| Trường hợp | Đầu vào / trạng thái | Hành vi mong muốn |
|---|---|---|
| Field bình thường | stock=10, delta=2 | stock=12 |
| Field thiếu | không có stock, delta=2 | Khởi tạo theo quy tắc đã chọn |
| Field null | stock=null | Khởi tạo hoặc từ chối theo hợp đồng |
| Delta bằng 0 | delta=0 | No-op hoặc giữ nguyên |
| Delta âm | delta=-1 | Từ chối nếu nghiệp vụ chỉ cho tăng |
| Sai kiểu | stock="ten" | Báo lỗi dữ liệu hoặc đưa vào xử lý riêng |
| Giá trị cực đại | stock gần giới hạn, delta lớn | Từ chối nếu vượt giới hạn |
| Document không tồn tại | ID không có | Xử lý not found hoặc upsert theo yêu cầu |
| Request gửi lại | Cùng event được gửi hai lần | Không tăng lặp nếu yêu cầu dedup |
| Hai update đồng thời | Hai delta cùng cập nhật | Kết quả đúng theo chính sách concurrency |

Ma trận này buộc ứng dụng xác định rõ hành vi thay vì để kiểu dữ liệu hoặc exception quyết định ngẫu nhiên.

### 15.2. Kiểm thử field thiếu, null và sai kiểu

Chuẩn bị document riêng cho từng trạng thái:

~~~json
{"name": "A", "stock": 10}
~~~

~~~json
{"name": "B"}
~~~

~~~json
{"name": "C", "stock": null}
~~~

~~~json
{"name": "D", "stock": "10"}
~~~

Chạy script trên từng document và xác nhận:

- Document hợp lệ được cập nhật đúng.
- Field thiếu/null được xử lý đúng quy tắc.
- Sai kiểu được từ chối hoặc ghi nhận có chủ đích.
- Không có document khác bị thay đổi.

### 15.3. Kiểm thử idempotency

Chạy cùng một request hai lần:

- Với script gán status, giá trị cuối phải giống nhau.
- Với script tăng counter, giá trị sẽ tăng hai lần nếu không có deduplication.
- Với script append tag, kiểm tra có tạo phần tử trùng hay không.
- Với script xóa field, lần thứ hai nên có hành vi được xác định rõ.

Không chỉ test một lần chạy thành công. Retry là một phần thực tế của hệ thống phân tán.

### 15.4. Kiểm thử concurrency

Tạo nhiều request cập nhật cùng một document và kiểm tra:

- Có version conflict hay không.
- `retry_on_conflict` có tạo kết quả đúng không.
- Có mất cập nhật không.
- Event lặp có làm thay đổi dữ liệu hai lần không.
- Ứng dụng xử lý conflict và retry như thế nào.

Với counter, cần phân biệt hai request hợp lệ cùng tăng với một request bị gửi lại do timeout. Hai trường hợp có ý nghĩa nghiệp vụ khác nhau.

## 16. Đo hiệu năng và theo dõi script

Để đánh giá script:

- Đo thời gian phản hồi update một document.
- Đo throughput và latency của bulk update.
- Theo dõi số document khớp update-by-query.
- Theo dõi task progress, version conflicts và failures.
- Theo dõi CPU, heap, indexing pressure, merge và refresh.
- Theo dõi compilation rate và script cache eviction khi nghi ngờ source động.
- So sánh với partial update hoặc ingest pipeline nếu có thể.

Thử nghiệm trên dữ liệu có kích thước `_source`, số shard và concurrency gần môi trường thực. Benchmark một document nhỏ trên máy local không dự báo đáng tin cậy chi phí update-by-query hàng triệu document trên cluster.

### 16.1. Chạy thử theo phạm vi nhỏ

Với migration hoặc update-by-query lớn, có thể bắt đầu bằng một phạm vi hẹp:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "LEGACY"
          }
        },
        {
          "term": {
            "tenantId": "tenant-test"
          }
        }
      ]
    }
  }
}
~~~

Ước lượng số document khớp bằng `_count` hoặc search với size nhỏ trước khi chạy script. Khi kết quả đúng, mở rộng phạm vi theo batch hoặc theo tenant.

### 16.2. Theo dõi task update-by-query

Khi chạy bất đồng bộ, lưu task ID và theo dõi trạng thái:

~~~http
GET /_tasks/<task_id>
~~~

Response có thể chứa số document đã xử lý, số update, số no-op, version conflicts và lỗi theo batch. Dùng thông tin này để quyết định tác vụ đã hoàn tất hay cần điều tra.

Không coi task đã được nhận là task đã hoàn thành. Ứng dụng điều phối cần lưu trạng thái và báo cáo kết quả cuối cùng.

## 17. Ví dụ hoàn chỉnh: cập nhật counter có kiểm soát

Ví dụ dưới đây minh họa cách tách validation ở service và script source cố định.

~~~java
public void increaseViewCount(String productId, long delta) {
    if (productId == null || productId.isBlank()) {
        throw new IllegalArgumentException("productId is required");
    }

    if (delta <= 0 || delta > 10_000) {
        throw new IllegalArgumentException("delta is outside the allowed range");
    }

    UpdateQuery updateQuery = UpdateQuery.builder(productId)
            .withScript("""
                if (ctx._source.viewCount == null) {
                    ctx._source.viewCount = 0L;
                }
                ctx._source.viewCount += params.delta;
                """)
            .withParams(Map.of("delta", delta))
            .build();

    operations.update(updateQuery, IndexCoordinates.of("products"));
}
~~~

Đây là ví dụ định hướng; các builder method và kiểu `UpdateQuery` thay đổi theo release train Spring Data Elasticsearch. Trong dự án, dùng API đúng phiên bản hoặc tạo update request qua Elasticsearch Java Client tương ứng.

Các điểm cần giữ:

- Product ID được kiểm tra trước khi tạo request.
- Delta có giới hạn nghiệp vụ.
- Script source cố định.
- Delta được truyền qua params.
- Field thiếu được khởi tạo theo quy tắc đã định.
- Hệ thống cần chính sách retry/dedup nếu request có thể được gửi lại.

Nếu counter phải tăng chính xác một lần cho mỗi event, chỉ validate delta là chưa đủ. Cần một event ID hoặc cơ chế deduplication để không áp dụng cùng sự kiện nhiều lần.

## 18. Checklist trước khi đưa script lên production

- [ ] Script source được kiểm soát trong code hoặc stored script đã review.
- [ ] Đầu vào được truyền qua params, không ghép vào source.
- [ ] Tên field hoặc thao tác động được giới hạn bằng allowlist.
- [ ] Kiểu dữ liệu, null và field thiếu có hành vi xác định.
- [ ] Chuỗi, collection, vòng lặp và số document bị tác động có giới hạn.
- [ ] Logic xử lý số 0, số âm, tràn số và chia cho 0.
- [ ] Xác định script có idempotent hay không.
- [ ] Có chính sách version conflict, retry và deduplication.
- [ ] Query update-by-query được kiểm tra phạm vi trước khi chạy.
- [ ] Có throttle, task monitoring và cách dừng tác vụ dài.
- [ ] Có integration test trên Elasticsearch tương thích.
- [ ] Có benchmark và theo dõi CPU, heap, cache, indexing pressure.
- [ ] Đã cân nhắc partial update, bulk, ingest pipeline hoặc reindex.

## 19. Kết luận

Script trong Elasticsearch có hai loại chi phí chính: biên dịch và thực thi. Compilation cache giúp tái sử dụng script có source ổn định, còn params cho phép thay đổi dữ liệu đầu vào mà không tạo source mới. Tuy nhiên, mỗi document vẫn phải thực thi script và có thể phải ghi lại toàn bộ document, vì vậy update-by-query trên tập dữ liệu lớn cần được ước lượng, throttle và theo dõi.

An toàn đầu vào bắt đầu từ việc không thực thi script do client tùy ý gửi, không nối dữ liệu vào source, validate kiểu và miền giá trị, giới hạn kích thước collection và phạm vi document. Painless sandbox giảm khả năng truy cập nguy hiểm nhưng không loại bỏ rủi ro CPU, bộ nhớ hoặc logic sai.

Kiểm thử cần bao gồm field thiếu, null, sai kiểu, collection rỗng, số 0, số âm, giới hạn số học, request lặp, version conflict và cập nhật đồng thời. Với tác vụ quan trọng, hãy integration test script trên Elasticsearch thật tương thích và đo hiệu năng với dữ liệu gần production. Chỉ dùng script khi logic thực sự cần chạy dựa trên trạng thái document; partial update, bulk, ingest pipeline hoặc xử lý ở ứng dụng có thể là lựa chọn đơn giản hơn.

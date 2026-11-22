# Delete by query, xung đột và kết quả từng tác vụ

Elasticsearch hỗ trợ xóa nhiều document cùng lúc bằng `_delete_by_query`. Ứng dụng gửi một query để xác định tập document cần xóa; Elasticsearch lấy một snapshot của dữ liệu phù hợp rồi thực hiện thao tác xóa theo từng batch. API này hữu ích khi dọn dữ liệu hết hạn, xóa document theo trạng thái, loại bỏ dữ liệu của một tenant hoặc chạy tác vụ bảo trì theo lịch.

Vì quá trình xóa diễn ra theo batch trên một tập dữ liệu có thể đồng thời được cập nhật, kết quả không đơn giản chỉ là “thành công” hoặc “thất bại”. Có thể xảy ra version conflict, shard failure, timeout hoặc task bị hủy sau khi một phần document đã bị xóa. Cần đọc response và trạng thái task để biết chính xác số document đã xóa, số conflict, batch đã chạy, retry và lỗi từng phần.

Trong Spring Data Elasticsearch, có thể gọi thao tác delete theo query qua `ElasticsearchOperations.delete(...)` và nhận `ByQueryResponse`. Với công việc dài, cần cân nhắc chạy bất đồng bộ ở tầng Elasticsearch, theo dõi task ID, kiểm soát tốc độ và thiết kế cách chạy lại an toàn.

## 1. Delete by query là gì?

`_delete_by_query` xóa các document khớp với một Query DSL. Khác với delete-by-ID, ứng dụng không cần biết ID của từng document trước khi gọi; chỉ cần xác định điều kiện tìm kiếm.

Ví dụ xóa các session đã hết hạn:

```http
POST /sessions/_delete_by_query
Content-Type: application/json

{
  "query": {
    "range": {
      "expiresAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
```

Elasticsearch tìm các document có `expiresAt` nhỏ hơn mốc thời gian rồi xóa chúng. Request có thể xử lý nhiều document hơn giới hạn phân trang thông thường vì server tự chia công việc thành các batch.

### So sánh các cách xóa

| Cách xóa | Khi nào dùng | Đặc điểm |
|---|---|---|
| Delete by ID | Đã biết `_id` của một document | Xóa trực tiếp một document, có thể kèm routing và version điều kiện |
| Delete by query | Cần xóa mọi document thỏa điều kiện | Server tìm và xóa theo batch; có thể phát sinh conflict và partial result |
| Bulk delete | Ứng dụng đã có danh sách ID cần xóa | Gửi nhiều delete action trong một bulk request; phải kiểm tra kết quả từng item |
| Xóa index | Muốn loại bỏ toàn bộ dữ liệu của một index | Thao tác ở cấp index; ảnh hưởng toàn bộ document và mapping trong index |

Delete by query không phải transaction nguyên tử. Nếu một batch đã xóa thành công rồi batch sau gặp lỗi, các document đã xóa không được khôi phục tự động.

## 2. Cách Delete by query hoạt động

Ở mức khái quát, Elasticsearch thực hiện các bước:

```text
Ứng dụng gửi query
       |
       v
Elasticsearch tạo snapshot/search context
       |
       v
Tìm các document khớp query
       |
       v
Chia kết quả thành các batch
       |
       v
Gửi delete action cho từng batch
       |
       +----> Thành công: tăng deleted
       |
       +----> Version conflict: ghi nhận conflict
       |
       +----> Lỗi khác: ghi nhận failure
       |
       v
Trả response hoặc hoàn tất task
```

Delete by query dùng một snapshot của dữ liệu tại thời điểm bắt đầu tìm kiếm. Document được thêm sau khi snapshot được tạo không tự động nằm trong tập cần xóa của lượt chạy đó.

Khi xóa từng document, Elasticsearch sử dụng thông tin version nội bộ từ snapshot. Nếu document đã bị thay đổi sau khi snapshot được tạo, thao tác xóa có thể gặp version conflict. Cơ chế này ngăn một job xóa dựa trên dữ liệu cũ vô tình xóa phiên bản mới hơn của document.

### Không có rollback tự động

Nếu task xóa được 10.000 document rồi gặp lỗi ở batch tiếp theo, 10.000 document đã xóa vẫn bị xóa. Delete by query không gom toàn bộ batch thành một transaction. Khi cần khả năng khôi phục, phải có snapshot/backup hoặc một thiết kế lưu trữ cho phép phục hồi dữ liệu.

## 3. Viết query có phạm vi rõ ràng

Ví dụ xóa các sản phẩm đã bị archive trước một ngày:

```http
POST /products/_delete_by_query
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "ARCHIVED"
          }
        },
        {
          "range": {
            "archivedAt": {
              "lt": "2026-01-01T00:00:00Z"
            }
          }
        }
      ]
    }
  }
}
```

`filter` phù hợp cho điều kiện nghiệp vụ không cần relevance score. Hãy xác định rõ:

- Index hoặc alias đích.
- Tenant, loại document hoặc trạng thái cần xóa.
- Mốc thời gian và timezone.
- Field có mapping đúng kiểu không.
- Query có vô tình khớp document mới hoặc document đang hoạt động không.

### Kiểm tra trước khi xóa

Trước khi gọi delete by query, nên chạy chính query đó bằng `_count` hoặc `_search` để xác nhận phạm vi:

```http
POST /products/_count
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ARCHIVED" } },
        {
          "range": {
            "archivedAt": {
              "lt": "2026-01-01T00:00:00Z"
            }
          }
        }
      ]
    }
  }
}
```

Nếu cần xem mẫu document, dùng `_search` với `size` nhỏ và chỉ lấy các field cần thiết. Count là ước lượng phạm vi theo thời điểm kiểm tra; dữ liệu vẫn có thể thay đổi trước khi delete by query bắt đầu.

## 4. Response đồng bộ và các trường quan trọng

Khi chạy đồng bộ, Elasticsearch trả kết quả sau khi thao tác kết thúc hoặc bị dừng do lỗi. Response rút gọn có thể như sau:

```json
{
  "took": 147,
  "timed_out": false,
  "total": 1200,
  "deleted": 1198,
  "batches": 3,
  "version_conflicts": 2,
  "noops": 0,
  "retries": {
    "bulk": 0,
    "search": 1
  },
  "throttled_millis": 0,
  "requests_per_second": -1.0,
  "failures": []
}
```

Ý nghĩa các trường:

| Trường | Ý nghĩa |
|---|---|
| `took` | Thời gian thực thi, tính bằng mili giây |
| `timed_out` | Search phase có bị timeout hay không |
| `total` | Số document được tìm thấy trong snapshot để xử lý |
| `deleted` | Số document đã xóa thành công |
| `batches` | Số batch bulk delete đã gửi |
| `version_conflicts` | Số document gặp xung đột version |
| `noops` | Số thao tác không tạo thay đổi (thường bằng 0 với delete by query) |
| `retries.bulk` | Số lần retry do lỗi ở bulk phase |
| `retries.search` | Số lần retry do lỗi ở search phase |
| `throttled_millis` | Tổng thời gian bị throttling |
| `requests_per_second` | Tốc độ được cấu hình; `-1` thường biểu thị không giới hạn |
| `failures` | Danh sách lỗi được ghi nhận trong quá trình xử lý |

Không nên chỉ kiểm tra HTTP status 200. Hãy đọc `deleted`, `version_conflicts`, `timed_out` và `failures` để xác định task có đạt mục tiêu nghiệp vụ hay không.

### `total` không đồng nghĩa với `deleted`

Hai số có thể khác nhau. Ví dụ `total = 1200`, `deleted = 1198`, `version_conflicts = 2` nghĩa là 1.200 document thuộc tập snapshot, nhưng chỉ 1.198 document được xóa. Hai document còn lại đã thay đổi sau snapshot hoặc gặp conflict.

## 5. Version conflict phát sinh khi nào?

Giả sử delete-by-query bắt đầu và tìm thấy document `p-100` với version hiện tại là 7. Trước khi delete action được gửi, một tiến trình khác cập nhật document thành version 8.

```text
Thời điểm T1: Delete by query tạo snapshot
              p-100, version 7

Thời điểm T2: Ứng dụng cập nhật p-100
              p-100, version 8

Thời điểm T3: Delete by query gửi delete
              dựa trên version 7

Kết quả: version conflict
         document version 8 không bị xóa bởi thao tác cũ
```

Đây là bảo vệ cần thiết để tránh xóa nhầm document vừa được cập nhật. Conflict không nhất thiết là lỗi mapping hoặc lỗi cú pháp query; nó có thể là hệ quả bình thường của hệ thống có nhiều writer.

### Những nguyên nhân thường gặp

- Người dùng cập nhật document trong lúc job dọn dữ liệu chạy.
- Một consumer khác thay đổi trạng thái document.
- Một job đồng bộ khác ghi lại document cùng ID.
- Nhiều tác vụ delete/update chạy đồng thời trên cùng tập dữ liệu.
- Alias trỏ tới index đang nhận ghi liên tục.

## 6. `conflicts=abort` và `conflicts=proceed`

Tham số `conflicts` quyết định hành vi khi gặp version conflict.

### Mặc định: abort

```http
POST /products/_delete_by_query?conflicts=abort
```

Đây là hành vi mặc định. Khi gặp version conflict, task dừng và trả kết quả có conflict/failure tương ứng. Những document đã xóa ở các batch trước vẫn không được phục hồi.

### Tiếp tục: proceed

```http
POST /products/_delete_by_query?conflicts=proceed
```

Với `proceed`, Elasticsearch bỏ qua các document gặp version conflict và tiếp tục xử lý những document còn lại. Response ghi nhận số conflict trong `version_conflicts`.

`proceed` không có nghĩa là Elasticsearch tự thử xóa lại document đã conflict bằng version mới. Nó có nghĩa là bỏ qua conflict đó để task tiếp tục. Nếu nghiệp vụ vẫn muốn xóa document đó, ứng dụng có thể cần kiểm tra lại bằng query mới và quyết định có chạy lượt tiếp theo hay không.

### Chọn chính sách nào?

| Tình huống | Chính sách có thể phù hợp |
|---|---|
| Dọn dữ liệu ít thay đổi, muốn dừng khi có bất thường | `abort` |
| Dọn dữ liệu lớn, chấp nhận một số document thay đổi trong lúc chạy | `proceed` |
| Dữ liệu có yêu cầu audit chặt chẽ | Dùng `abort` hoặc `proceed` kèm báo cáo và xử lý conflict riêng |
| Xóa theo trạng thái có thể đổi liên tục | Thiết kế query/version/watermark rõ ràng; không chỉ dựa vào `proceed` |

Không chọn `proceed` chỉ để response trông thành công. Số conflict vẫn phải được giám sát và xử lý theo yêu cầu nghiệp vụ.

## 7. Phân biệt version conflict với các failure khác

Version conflict là một nhóm vấn đề cụ thể. `failures` có thể chứa các lỗi khác như shard unavailable, mapping/operation failure hoặc lỗi bulk item.

| Dấu hiệu | Cách hiểu | Hướng xử lý |
|---|---|---|
| `version_conflicts > 0` | Document thay đổi giữa snapshot và delete | Chọn abort/proceed và đánh giá có cần chạy lại |
| `timed_out: true` | Search phase bị timeout | Kiểm tra tải cluster, query, scroll/timeout và shard |
| `failures` không rỗng | Có lỗi cụ thể trong search hoặc bulk phase | Đọc từng failure, xác định shard/document và nguyên nhân |
| `retries.search > 0` | Search phase đã phải retry | Theo dõi shard availability và tải cluster |
| `retries.bulk > 0` | Bulk delete phase đã phải retry | Kiểm tra áp lực indexing, thread pool và throttling |

Nếu `failures` có phần tử, hãy lưu thông tin cần thiết để điều tra. Không nên chỉ log một thông báo chung như “delete failed” mà bỏ qua index, shard, status và nguyên nhân trả về.

## 8. Chạy Delete by query bất đồng bộ

Một tác vụ xóa lớn có thể chạy lâu. Thay vì giữ kết nối HTTP chờ đến khi xong, có thể dùng `wait_for_completion=false`:

```http
POST /events/_delete_by_query?wait_for_completion=false&conflicts=proceed
Content-Type: application/json

{
  "query": {
    "range": {
      "expiresAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
```

Response trả task ID thay vì chờ toàn bộ kết quả:

```json
{
  "task": "node-1:123456"
}
```

Ứng dụng lưu task ID và dùng Tasks API để theo dõi. Task bất đồng bộ vẫn chạy trên Elasticsearch sau khi request HTTP ban đầu đã trả về.

### Vì sao dùng async?

- Không giữ request thread của ứng dụng trong thời gian dài.
- Có thể theo dõi tiến độ định kỳ.
- Có thể chủ động hủy task nếu cần.
- Có thể điều chỉnh tốc độ khi task đang chạy.
- Dễ tích hợp vào scheduler hoặc job orchestration.

Async không làm thao tác xóa trở thành transaction và không bảo đảm task sẽ hoàn tất nếu cluster gặp sự cố. Ứng dụng vẫn cần quản lý trạng thái, timeout, retry và kết quả cuối.

## 9. Theo dõi task bằng Tasks API

Sau khi nhận task ID, lấy trạng thái:

```http
GET /_tasks/node-1:123456
```

Khi task chưa hoàn tất, response có thể chứa `completed: false` cùng thông tin task/status:

```json
{
  "completed": false,
  "task": {
    "node": "node-1",
    "id": 123456,
    "action": "indices:data/write/delete/byquery",
    "status": {
      "total": 100000,
      "deleted": 45000,
      "batches": 45,
      "version_conflicts": 3,
      "noops": 0,
      "retries": {
        "bulk": 0,
        "search": 1
      },
      "requests_per_second": 500.0,
      "throttled_millis": 1200
    }
  }
}
```

Khi hoàn tất, response có `completed: true` và phần `response` chứa kết quả cuối cùng:

```json
{
  "completed": true,
  "response": {
    "took": 12000,
    "timed_out": false,
    "total": 100000,
    "deleted": 99997,
    "batches": 100,
    "version_conflicts": 3,
    "failures": []
  }
}
```

Các trường status trong lúc chạy là số liệu tiến độ tại thời điểm poll, không phải kết quả cuối cùng. Chỉ kết luận task hoàn tất khi `completed` là `true` và đã đọc `response` hoặc `error` tương ứng.

### Polling hợp lý

Không nên gọi Tasks API liên tục với chu kỳ vài mili giây. Poll theo khoảng thời gian phù hợp với thời lượng job, ví dụ vài giây hoặc lâu hơn, và tăng khoảng cách khi task chạy dài. Với nhiều task, tránh đồng bộ tất cả client polling cùng một thời điểm.

## 10. Hủy task đang chạy

Có thể gửi yêu cầu hủy:

```http
POST /_tasks/node-1:123456/_cancel
```

Hủy task là yêu cầu dừng công việc, không phải rollback. Những document đã xóa trước khi task dừng vẫn đã bị xóa. Task có thể cần một khoảng thời gian để dừng tại ranh giới xử lý phù hợp.

Sau khi gửi cancel, tiếp tục kiểm tra Tasks API để xác nhận trạng thái cuối cùng. Không đánh dấu job là “đã rollback” hoặc “không có dữ liệu bị xóa” chỉ vì endpoint cancel trả về thành công.

### Khi nào hủy?

- Phát hiện query phạm vi rộng hơn dự kiến.
- Tải cluster vượt ngưỡng vận hành.
- Task đang xóa nhầm tenant hoặc loại dữ liệu.
- Cần dừng để xử lý một sự cố hoặc bảo trì.

Nếu query sai phạm vi và một phần dữ liệu đã bị xóa, cần quy trình phục hồi từ backup hoặc nguồn dữ liệu gốc; cancel không thể khôi phục document.

## 11. Throttling với `requests_per_second`

Delete by query có thể tạo tải lớn lên search và bulk indexing thread pool. Tham số `requests_per_second` giúp giới hạn tốc độ xử lý.

Ví dụ giới hạn khoảng 500 request đơn vị xử lý mỗi giây theo cơ chế throttling của API:

```http
POST /events/_delete_by_query?requests_per_second=500
Content-Type: application/json

{
  "query": {
    "range": {
      "expiresAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
```

Giá trị `-1` biểu thị không throttling. Tốc độ này được thực thi thông qua thời gian chờ giữa các batch; nó không phải cam kết chính xác về số document xóa mỗi giây trong mọi workload.

### Điều chỉnh tốc độ khi task đang chạy

Với task bất đồng bộ, có thể re-throttle:

```http
POST /_delete_by_query/node-1:123456/_rethrottle?requests_per_second=100
```

Có thể giảm tốc độ khi cluster đang chịu tải hoặc tăng lại khi hệ thống ổn định. Re-throttle không thay đổi query và không xử lý lại conflict đã xảy ra.

## 12. Chia task bằng `slices`

`slices` cho phép Elasticsearch chia một delete-by-query thành các sub-task chạy song song trên các phần dữ liệu khác nhau.

Ví dụ:

```http
POST /events/_delete_by_query?slices=auto&wait_for_completion=false
Content-Type: application/json

{
  "query": {
    "range": {
      "expiresAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
```

`slices=auto` để Elasticsearch chọn số slice dựa trên shard. Có thể đặt số nguyên cụ thể nếu đã đo workload.

### Lợi ích và trade-off

- Tăng mức song song và có thể rút ngắn thời gian xử lý.
- Mỗi slice có thể tạo search context và batch riêng.
- Nhiều slice làm tăng tài nguyên đồng thời.
- Tổng số task con có thể làm tăng tải search/bulk và áp lực heap.
- Tổng kết quả và `max_docs` có thể không chia đều tuyệt đối giữa các slice.

Không tăng slice chỉ để làm task chạy nhanh hơn. Hãy theo dõi CPU, heap, indexing pressure, search thread pool, số shard và thời gian batch.

## 13. Các tham số vận hành quan trọng

Delete by query có nhiều tham số điều khiển. Những tham số thường gặp:

| Tham số | Mục đích | Lưu ý |
|---|---|---|
| `conflicts` | Chọn `abort` hoặc `proceed` | `proceed` bỏ qua version conflict, không retry document đó |
| `wait_for_completion` | Chạy đồng bộ hay bất đồng bộ | Async trả task ID để poll |
| `requests_per_second` | Giới hạn tốc độ batch | `-1` thường là không giới hạn |
| `slices` | Chia task thành các phần song song | Tăng tải tài nguyên khi quá lớn |
| `scroll_size` | Số document mỗi batch tìm kiếm | Batch lớn tăng payload và bộ nhớ |
| `scroll` | Thời gian giữ scroll context nội bộ | Cần đủ thời gian giữa các batch |
| `max_docs` | Giới hạn số document xử lý | Không dùng như cơ chế chọn ngẫu nhiên hoặc top N nếu không có sort/logic phù hợp |
| `refresh` | Refresh shard sau khi xóa | Có chi phí; chỉ bật khi cần kết quả search thấy thay đổi ngay |
| `routing` | Giới hạn thao tác theo routing value | Chỉ dùng khi biết routing phù hợp |
| `timeout` | Thời gian chờ các thao tác liên quan | Không thay thế xử lý task dài bằng async |

### `max_docs`

Ví dụ giới hạn tối đa 10.000 document:

```http
POST /logs/_delete_by_query?max_docs=10000
```

`max_docs` giới hạn số document được xử lý, không phải cơ chế đảm bảo chọn đúng 10.000 document mới nhất/cũ nhất. Nếu cần xóa theo thứ tự nghiệp vụ, hãy xác định query và cách chọn tập dữ liệu trước; delete by query không nên được dùng như một truy vấn phân trang có sort tùy ý.

Khi kết hợp `max_docs` với slicing, số document thực tế có thể không đúng tuyệt đối với con số giới hạn do cách phân phối và xử lý song song. Nếu cần giới hạn chính xác, cần thiết kế lựa chọn ID/tập dữ liệu riêng rồi xóa theo danh sách hoặc chia partition có kiểm soát.

### `refresh`

`refresh=true` yêu cầu refresh các shard liên quan sau khi thao tác hoàn tất để các thay đổi hiển thị ngay với search. Refresh có chi phí và không cần thiết nếu ứng dụng chấp nhận đợi refresh interval bình thường.

## 14. Routing và phạm vi shard

Nếu biết routing value, có thể giới hạn delete by query vào shard liên quan:

```http
POST /tenant-data/_delete_by_query?routing=tenant-42
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "EXPIRED"
    }
  }
}
```

Routing chỉ giới hạn shard được truy vấn. Nó không thay thế điều kiện tenant trong Query DSL. Với dữ liệu đa tenant, nên giữ điều kiện `tenantId` trong query để thể hiện phạm vi nghiệp vụ rõ ràng, đồng thời dùng routing nếu kiến trúc index hỗ trợ.

Đặc biệt với parent-child, routing phải nhất quán với cách document được index. Xóa theo query cần nhắm đúng index, query và routing để tránh bỏ sót hoặc tác động ngoài phạm vi dự kiến.

## 15. Kết quả từng tác vụ trong hệ thống ứng dụng

Nếu ứng dụng chạy nhiều job delete by query, không nên chỉ ghi một biến `success = true/false`. Mỗi tác vụ nên có bản ghi trạng thái riêng để theo dõi vòng đời và kết quả.

Một mô hình trạng thái có thể gồm:

```text
CREATED
   |
   v
SUBMITTED
   |
   v
RUNNING ---------> CANCELLING
   |                   |
   v                   v
COMPLETED           CANCELLED
   |
   +----> COMPLETED_WITH_CONFLICTS
   |
   +----> COMPLETED_WITH_FAILURES

RUNNING / SUBMITTED ----> FAILED
```

Đây là trạng thái nghiệp vụ do ứng dụng định nghĩa. Nó không phải tên trạng thái chính thức của Elasticsearch Tasks API.

### Thông tin nên lưu cho mỗi job

| Trường | Mục đích |
|---|---|
| `jobId` | ID nghiệp vụ ổn định của job |
| `taskId` | ID do Elasticsearch trả về khi chạy async |
| `indexOrAlias` | Index/alias được nhắm tới |
| `queryDescription` hoặc query hash | Nhận diện điều kiện xóa đã gửi |
| `submittedAt`, `startedAt`, `finishedAt` | Theo dõi thời gian |
| `status` | Trạng thái nghiệp vụ của job |
| `total` | Số document được tìm thấy |
| `deleted` | Số document đã xóa |
| `versionConflicts` | Số conflict |
| `batches` | Số batch đã chạy |
| `retries` | Số lần retry search/bulk |
| `timedOut` | Có timeout hay không |
| `failures` | Tóm tắt lỗi và thông tin tham chiếu để điều tra |
| `cancelRequested` | Có yêu cầu hủy hay không |

Không nhất thiết lưu toàn bộ response raw nếu nó có thể lớn hoặc chứa thông tin nhạy cảm. Hãy lưu các trường cần audit và tham chiếu tới log/trace có kiểm soát.

## 16. Đánh giá kết quả task

Một task chỉ nên được xem là hoàn tất đúng yêu cầu khi ứng dụng đánh giá đủ các chỉ số, không chỉ dựa trên việc task đã dừng.

Ví dụ:

| Kết quả | Cách diễn giải |
|---|---|
| `completed=true`, `deleted=total`, `failures=[]`, `timed_out=false` | Task đã xóa hết tập document tìm thấy trong snapshot |
| `deleted < total`, `version_conflicts > 0`, không có failure khác | Một số document thay đổi và bị bỏ qua hoặc task dừng theo conflict policy |
| `failures` không rỗng | Có lỗi cần điều tra; không đánh dấu thành công hoàn toàn |
| Task bị cancel | Một phần có thể đã xóa; cần đọc kết quả cuối và xử lý phần còn lại |
| Task không còn tìm thấy | Có thể task đã hoàn tất và kết quả không còn truy cập được, task/node đã mất hoặc ID sai; cần đối chiếu job record và log |

### Completed không đồng nghĩa với fully successful

Tasks API có thể báo task đã hoàn tất, nhưng response vẫn chứa version conflict hoặc failures. Trạng thái `completed` mô tả vòng đời task, còn thành công nghiệp vụ phải dựa trên nội dung response.

## 17. Chạy lại sau conflict hoặc failure

Nếu task kết thúc với version conflict, có thể cân nhắc chạy lại query để xử lý những document vẫn còn khớp. Tuy nhiên, trước khi chạy lại cần xác định:

- Những document conflict có còn thỏa điều kiện xóa không?
- Chúng có được cập nhật sang trạng thái cần giữ lại không?
- Query có thể xóa nhầm phiên bản mới nếu chạy lại không?
- Có document mới được thêm vào trong lúc chạy không?
- Job có thể chạy lặp an toàn không?

Ví dụ, nếu query xóa session có `expiresAt < now`, một session được gia hạn trong lúc job chạy có thể gặp conflict. Chạy lại cùng query sau đó sẽ không xóa session nếu `expiresAt` đã được cập nhật sang tương lai. Đây là hành vi phù hợp.

Ngược lại, nếu query chỉ dựa trên một cờ `cleanup=true` và tiến trình khác cập nhật nội dung nhưng vẫn giữ cờ đó, chạy lại có thể tiếp tục xóa document. Vì vậy, retry phải dựa trên quy tắc nghiệp vụ, không chỉ dựa trên số conflict.

### Không retry mù quáng toàn bộ task

Retry một query lớn có thể xóa thêm document được tạo sau lần chạy đầu nếu chúng cũng khớp điều kiện. Nếu yêu cầu chỉ xử lý tập dữ liệu tại một thời điểm, hãy cố định phạm vi bằng watermark hoặc partition và dùng snapshot/backup phù hợp.

## 18. Delete by query trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp thao tác delete theo `Query` thông qua `ElasticsearchOperations`. Với API có hỗ trợ, phương thức trả về `ByQueryResponse`, chứa các thông tin kết quả của delete-by-query.

Ví dụ xóa các event hết hạn:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.ByQueryResponse;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class EventCleanupService {

    private final ElasticsearchOperations operations;

    public EventCleanupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ByQueryResponse deleteExpiredEvents(String cutoff) {
        Query query = NativeQuery.builder()
            .withQuery(q -> q.range(r -> r
                .field("expiresAt")
                .lt(co.elastic.clients.json.JsonData.of(cutoff))
            ))
            .build();

        return operations.delete(query, EventDocument.class);
    }
}
```

`EventDocument.class` giúp Spring Data xác định index mapping. Nếu cần chỉ định alias/index cụ thể, dùng overload nhận `IndexCoordinates` nếu phiên bản Spring Data đang dùng hỗ trợ.

### Đọc `ByQueryResponse`

```java
ByQueryResponse response = deleteExpiredEvents(cutoff);

long total = response.getTotal();
long deleted = response.getDeleted();
long conflicts = response.getVersionConflicts();
long batches = response.getBatches();
boolean timedOut = response.isTimedOut();
var failures = response.getFailures();
```

Các accessor và package của `ByQueryResponse` có thể thay đổi theo version Spring Data Elasticsearch. Hãy đối chiếu Javadoc của dependency trong dự án. Quan trọng là ứng dụng phải kiểm tra deleted, conflict, timeout và failures trước khi kết luận job thành công.

### Lưu ý về đồng bộ và bất đồng bộ

`ElasticsearchOperations.delete(query, clazz)` thường là abstraction cho thao tác delete-by-query và trả kết quả khi lời gọi hoàn tất theo API của phiên bản đang dùng. Nếu cần kiểm soát `wait_for_completion=false`, theo dõi task ID, re-throttle hoặc cancel, hãy kiểm tra khả năng của client/API tương ứng; có thể cần dùng Elasticsearch Java API Client trực tiếp thay vì abstraction cấp cao.

## 19. Ví dụ kiểm tra kết quả trong service

Không nên trả response thành công chỉ vì không có exception. Hãy chuyển kết quả sang một mô hình nghiệp vụ rõ ràng:

```java
public record CleanupResult(
        long total,
        long deleted,
        long versionConflicts,
        long batches,
        boolean timedOut,
        boolean hasFailures) {

    public boolean completedWithoutIssues() {
        return !timedOut
            && !hasFailures
            && versionConflicts == 0
            && deleted == total;
    }
}
```

Chuyển từ `ByQueryResponse`:

```java
public CleanupResult toResult(ByQueryResponse response) {
    return new CleanupResult(
        response.getTotal(),
        response.getDeleted(),
        response.getVersionConflicts(),
        response.getBatches(),
        response.isTimedOut(),
        !response.getFailures().isEmpty()
    );
}
```

`completedWithoutIssues()` chỉ là một quy tắc ví dụ. Với job dùng `conflicts=proceed`, có thể chấp nhận conflict trong một số trường hợp, nhưng vẫn phải lưu số conflict và quyết định có cần xử lý lại hay không.

## 20. Tách phạm vi query và chính sách xóa khỏi service

Với tác vụ xóa quan trọng, nên tạo query từ một tiêu chí nghiệp vụ rõ ràng thay vì nối chuỗi JSON hoặc nhận raw Query DSL từ client.

Ví dụ DTO nội bộ:

```java
import java.time.Instant;

public record ExpiredEventCriteria(
        String tenantId,
        Instant expiresBefore) {
}
```

Xây query:

```java
public Query buildDeleteQuery(ExpiredEventCriteria criteria) {
    return NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
            .filter(f -> f.term(t -> t
                .field("tenantId")
                .value(criteria.tenantId())
            ))
            .filter(f -> f.range(r -> r
                .field("expiresAt")
                .lt(co.elastic.clients.json.JsonData.of(criteria.expiresBefore().toString()))
            ))
        ))
        .build();
}
```

Trước khi chạy, validate `tenantId` không rỗng và `expiresBefore` hợp lệ. Nếu job chỉ được phép xóa dữ liệu của một tenant, không cho phép caller bỏ qua tenant filter.

## 21. Xử lý bất đồng bộ ở tầng ứng dụng

Một job runner có thể lưu bản ghi job trước khi submit, sau đó cập nhật task ID và poll kết quả:

```text
Scheduler / API nội bộ
        |
        v
Tạo cleanup job record
        |
        v
Submit delete-by-query (async)
        |
        v
Lưu Elasticsearch task ID
        |
        v
Worker poll Tasks API
        |
        +----> completed=false: cập nhật progress, poll sau
        |
        +----> completed=true: đọc response/error
                         |
                         v
                 Đánh giá conflict/failures
                         |
                         v
                 Cập nhật trạng thái nghiệp vụ
```

Các điểm cần thiết kế:

- Không submit cùng một job nhiều lần chỉ vì client không nhận được response đầu tiên.
- Dùng job ID idempotent ở tầng ứng dụng.
- Nếu submit bị timeout, kiểm tra xem task có được tạo hay không trước khi gửi lại.
- Lưu task ID ngay sau khi nhận được.
- Poll có backoff và giới hạn thời gian.
- Xử lý task bị mất hoặc node restart.
- Khi cancel, tiếp tục chờ trạng thái cuối và ghi nhận số document đã xóa.

## 22. Kiểm soát tác vụ đồng thời

Nhiều delete-by-query lớn chạy cùng lúc có thể gây áp lực lên cluster. Nên có giới hạn số job đồng thời theo index hoặc theo loại workload.

Ví dụ chính sách:

- Chỉ chạy một cleanup lớn trên cùng index trong một thời điểm.
- Các job nhỏ có thể chạy song song nếu tài nguyên đủ.
- Tác vụ production có `requests_per_second` giới hạn.
- Job có `slices` được cấu hình theo số shard và năng lực cluster.
- Có hàng đợi để tránh scheduler khởi chạy nhiều lần cùng một lịch.
- Có cơ chế cancel/disable khi cluster vượt ngưỡng tải.

Không nên dùng một con số concurrency cố định cho mọi cluster. Hãy đo search/bulk thread pool, CPU, heap, disk I/O, indexing pressure và latency của ứng dụng chính.

## 23. Refresh và khả năng nhìn thấy document đã xóa

Delete by query không nhất thiết làm document biến mất khỏi search ngay lập tức nếu shard chưa refresh. Tham số `refresh=true` yêu cầu refresh sau khi thao tác hoàn tất.

Ví dụ:

```http
POST /sessions/_delete_by_query?refresh=true
```

Refresh ảnh hưởng khả năng nhìn thấy thay đổi qua search, không phải cơ chế xác nhận backup hay rollback. Nếu ứng dụng có thể chờ refresh interval bình thường, không cần bật refresh cho mọi cleanup.

## 24. Xử lý alias và rollover index

Nếu delete by query chạy trên alias trỏ tới nhiều index, cần xác định alias có write index hoặc filter/routing riêng hay không. Delete by query có thể tác động tới các index mà alias đại diện theo phạm vi request.

Với dữ liệu time-series hoặc index rollover:

- Nếu index cũ đã hết vòng đời, xóa toàn bộ index bằng lifecycle policy hoặc delete index có thể hiệu quả hơn delete từng document.
- Nếu chỉ một phần dữ liệu trong index cần xóa, delete by query có thể phù hợp.
- Nếu alias trỏ tới nhiều thế hệ index, xác nhận phạm vi alias trước khi chạy.
- Nếu job cần xóa theo tenant, luôn có filter tenant và routing phù hợp.

Không dùng alias rộng cho cleanup nếu chưa kiểm tra chính xác danh sách index mà alias trỏ tới.

## 25. Bảo vệ tác vụ xóa nguy hiểm

Delete by query có thể xóa lượng lớn dữ liệu. Một số biện pháp vận hành hữu ích:

1. Chạy `_count` trước và ghi nhận số document dự kiến.
2. Dùng filter bắt buộc như tenant, status hoặc time range.
3. Xác nhận index/alias và môi trường trước khi submit.
4. Giới hạn `max_docs` nếu nghiệp vụ cho phép giới hạn số lượng.
5. Chạy async để có task ID và khả năng theo dõi/cancel.
6. Dùng throttling và giới hạn concurrency.
7. Lưu kết quả từng task để audit.
8. Bảo đảm có snapshot/backup nếu dữ liệu cần khả năng phục hồi.

Không nên nhận nguyên Query DSL tùy ý từ một API public rồi gửi thẳng vào `_delete_by_query`. Hãy kiểm soát index, filter bắt buộc và quyền của caller ở tầng ứng dụng.

## 26. Kiểm thử Delete by query

Integration test nên chạy với Elasticsearch tương thích và dữ liệu fixture được kiểm soát. Mock `ElasticsearchOperations` có thể kiểm tra service gọi đúng phương thức, nhưng không kiểm tra hành vi Query DSL, version conflict hoặc kết quả xóa thực tế.

Các trường hợp cần kiểm thử:

- Chỉ document khớp query bị xóa.
- Document không khớp vẫn còn.
- Query có filter tenant không xóa dữ liệu tenant khác.
- Range date đúng biên và timezone.
- `deleted` khớp số document kỳ vọng khi không có concurrent update.
- Version conflict được xử lý theo `abort` hoặc `proceed`.
- Response có failures được phản ánh vào trạng thái job.
- Async task được poll đến khi hoàn tất.
- Cancel không được diễn giải thành rollback.
- Throttling và slicing không làm sai phạm vi dữ liệu.
- Chạy lại job không gây hậu quả ngoài ý muốn.

Để tái hiện conflict, một integration test có thể đồng thời cập nhật document đã nằm trong snapshot trong lúc delete-by-query đang chạy. Do timing khó kiểm soát, test này cần dữ liệu đủ lớn hoặc cơ chế đồng bộ test phù hợp; không nên dựa vào một `sleep` ngắn để khẳng định conflict sẽ xảy ra.

## 27. Các lỗi thường gặp

### Chỉ kiểm tra HTTP status

HTTP thành công không đồng nghĩa mọi document đã xóa. Đọc `deleted`, `version_conflicts`, `timed_out` và `failures`.

### Nghĩ `conflicts=proceed` sẽ retry document conflict

`proceed` bỏ qua document conflict và tiếp tục. Nếu cần xử lý lại, ứng dụng phải đánh giá và chạy query phù hợp ở lượt sau.

### Nghĩ cancel sẽ hoàn tác dữ liệu

Cancel chỉ yêu cầu dừng task. Document đã xóa vẫn mất; cần backup/restore nếu muốn phục hồi.

### Retry toàn bộ query mà không kiểm tra phạm vi

Query chạy lại có thể khớp document mới hoặc document vừa thay đổi. Dùng watermark/partition và quy tắc nghiệp vụ rõ ràng.

### Không đọc `failures`

Task có thể hoàn tất nhưng vẫn có failure. Lưu chi tiết lỗi và xác định có cần retry hay báo lỗi nghiệp vụ.

### Đặt batch/slices quá lớn

Tăng song song không phải lúc nào cũng nhanh hơn. Theo dõi heap, CPU, search/bulk thread pool và indexing pressure.

### Bỏ qua routing

Với index dùng custom routing hoặc parent-child, thiếu routing có thể làm thao tác quét rộng hơn hoặc không nhắm đúng shard dự kiến. Xác nhận routing theo mapping và dữ liệu thực tế.

### Xóa trên alias quá rộng

Alias có thể đại diện nhiều index. Kiểm tra alias và phạm vi trước khi chạy.

## 28. Quy trình triển khai một cleanup job

Một cleanup job có thể được thiết kế theo trình tự:

1. Nhận tiêu chí nghiệp vụ đã validate, không nhận query tùy ý từ client.
2. Xác định index/alias, tenant và khoảng thời gian.
3. Chạy `_count` hoặc search mẫu để xác nhận phạm vi.
4. Tạo query bằng `NativeQuery` hoặc Query API.
5. Chọn `conflicts=abort` hay `proceed` theo yêu cầu.
6. Chọn đồng bộ hay bất đồng bộ; với tác vụ dài, ưu tiên async và lưu task ID.
7. Chọn batch size, keep-alive, `requests_per_second` và `slices` theo tải cluster.
8. Theo dõi task qua Tasks API.
9. Khi task hoàn tất, đọc toàn bộ response và phân loại conflict/failure/timeout.
10. Ghi kết quả vào job record và audit log.
11. Nếu cần retry, xác định lại tập document và bảo đảm thao tác chạy lại an toàn.
12. Chỉ đánh dấu job thành công khi kết quả đáp ứng điều kiện nghiệp vụ.

## 29. Kết luận

Delete by query xóa document theo Query DSL bằng cách tạo snapshot, tìm document phù hợp rồi gửi delete theo từng batch. Vì dữ liệu có thể bị cập nhật đồng thời, version conflict là tình huống cần xử lý có chủ đích. `conflicts=abort` dừng khi gặp conflict; `conflicts=proceed` bỏ qua document conflict và tiếp tục, nhưng không tự retry document đó. Response cần được đánh giá qua `total`, `deleted`, `batches`, `version_conflicts`, `timed_out`, `retries` và `failures`.

Với tác vụ dài, dùng `wait_for_completion=false` để nhận task ID, theo dõi bằng Tasks API, điều chỉnh tốc độ bằng re-throttle và hủy bằng cancel khi cần. Hủy task không rollback các document đã xóa. Trong Spring Data Elasticsearch, `ElasticsearchOperations.delete(query, entityClass)` cung cấp abstraction và `ByQueryResponse` cho kết quả; nếu cần quản lý async task chi tiết, có thể phải dùng Elasticsearch Java API Client trực tiếp. Thiết kế query hẹp, kiểm tra count trước, giới hạn tải, lưu kết quả từng job và làm cho retry an toàn là các phần quan trọng của một quy trình xóa dữ liệu đáng tin cậy.

## Tài liệu tham khảo

- [Elasticsearch – Delete by query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query)
- [Elasticsearch – Tasks API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-tasks-get)
- [Elasticsearch – Cancel tasks API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-tasks-cancel)
- [Elasticsearch – Rethrottle delete by query](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query-rethrottle)
- [Elasticsearch – Query DSL](https://www.elastic.co/docs/reference/query-languages/query-dsl)
- [Spring Data Elasticsearch – Operations and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – `ByQueryResponse` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/ByQueryResponse.html)

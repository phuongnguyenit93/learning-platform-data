# Heap, bộ nhớ ngoài heap, đĩa và chi phí index lớn

Khi một index Elasticsearch lớn dần, hiệu năng không chỉ phụ thuộc vào dung lượng heap của JVM. Elasticsearch chạy trên Lucene, sử dụng đồng thời heap, bộ nhớ native/off-heap, filesystem page cache và đĩa. Mỗi lớp có vai trò khác nhau: heap giữ nhiều cấu trúc runtime và dữ liệu tạm; page cache giúp đọc segment nhanh; off-heap chứa một số buffer và cấu trúc native; đĩa lưu segment, translog và bản sao shard.

Một node có thể còn nhiều heap trống nhưng search vẫn chậm vì page cache thiếu, disk latency cao hoặc shard quá lớn. Ngược lại, node có heap tương đối thấp nhưng filesystem cache tốt vẫn có thể phục vụ search ổn định. Chỉ nhìn heap usage không đủ để kết luận node còn dư tài nguyên.

Với Spring Data Elasticsearch, chi phí còn xuất hiện ở phía ứng dụng: entity mapping, JSON serialization, bulk request buffers, connection pool và việc gom quá nhiều kết quả vào collection. Khi index lớn, cần đo cả Elasticsearch node lẫn JVM của ứng dụng Spring.

Bài học này giải thích cách các lớp bộ nhớ và storage phối hợp, vì sao index lớn làm tăng chi phí, cách theo dõi và cách thiết kế mapping, shard, bulk, refresh cùng workload để giữ hiệu năng ổn định.

## 1. Bản đồ tài nguyên của một Elasticsearch node

Một node Elasticsearch có thể được hình dung qua các lớp:

    Spring Boot application
      - Entity objects
      - Query and bulk request buffers
      - HTTP client connections
      - JSON serialization
                 |
                 v
          Network / HTTP
                 |
                 v
    Elasticsearch JVM process
      - Java heap
      - Thread stacks
      - Direct/native buffers
      - JVM metadata and runtime
      - Elasticsearch data structures
                 |
                 v
          Lucene / filesystem
      - Inverted index
      - Stored fields and _source
      - Doc values
      - Segment files
      - Translog
                 |
                 v
       Operating system page cache
                 |
                 v
              Disk

Các lớp này không độc lập hoàn toàn. Lucene đọc segment từ filesystem; hệ điều hành có thể giữ các block vừa đọc trong page cache. Elasticsearch quản lý metadata và một số cấu trúc trên heap. JVM dùng native memory cho runtime, thread stack và direct buffer. Ứng dụng Spring tạo object và buffer riêng trước khi gửi request.

Khi điều tra hiệu năng, cần xác định bottleneck nằm ở đâu:

- Heap hoặc garbage collection.
- Native memory hoặc direct buffer.
- Filesystem page cache.
- Disk throughput, IOPS hoặc latency.
- CPU và thread pool.
- Network hoặc connection pool.
- Chi phí mapping/serialization ở ứng dụng.

## 2. Heap JVM là gì?

Heap là vùng bộ nhớ JVM dùng để cấp phát các Java object. Elasticsearch sử dụng heap cho nhiều cấu trúc runtime, chẳng hạn:

- Cluster state và metadata index/shard.
- Một số metadata của Lucene và segment reader.
- Query execution structures.
- Aggregation state và bucket structures.
- Fielddata.
- Filter/query cache metadata.
- Indexing buffers và các cấu trúc liên quan đến ingest.
- Request state, coordination và các object tạm thời.

Heap được garbage collector quản lý. Object không còn được tham chiếu có thể được thu hồi, nhưng GC cần CPU và có thể tạo pause. Khi heap chịu áp lực cao, request latency có thể tăng, allocation thất bại hoặc node có thể gặp lỗi bộ nhớ.

Heap usage cần được quan sát theo thời gian. Một lần chụp heap thấp ngay sau GC không nói lên mức sử dụng trong peak workload. Cần xem cả:

- Heap used.
- Heap committed và maximum.
- Old generation occupancy.
- GC count và GC pause duration.
- Allocation rate.
- Số lần GC liên tục.

## 3. Không phải toàn bộ dữ liệu index nằm trên heap

Một quan niệm sai phổ biến là index lớn thì cần heap lớn tương ứng với toàn bộ dung lượng index. Lucene lưu phần lớn dữ liệu index dưới dạng file segment trên filesystem. Elasticsearch và Lucene sử dụng page cache của hệ điều hành để tăng tốc truy cập những file đó.

Ví dụ, một node có index vài trăm GB không có nghĩa JVM heap phải bằng vài trăm GB. Heap giữ metadata, cache và cấu trúc runtime cần thiết; các file segment nằm trên disk và có thể được cache trong RAM bởi hệ điều hành.

Điều này giải thích vì sao việc cấp toàn bộ RAM cho heap thường là quyết định không tốt. Node cần RAM cho filesystem cache để Lucene đọc postings, doc values và stored fields hiệu quả.

Khi heap quá lớn:

- Phần RAM còn lại cho page cache giảm.
- GC có thể mất nhiều thời gian hơn.
- Object graph lớn làm tăng chi phí quản lý.
- Có thể vượt ngưỡng compressed ordinary object pointers tùy JVM/platform, làm object reference lớn hơn.
- Search phải đọc nhiều hơn từ disk nếu dữ liệu không còn trong cache.

Không nên chọn heap chỉ theo tổng kích thước index. Hãy dựa vào heap pressure thực tế, query mix, shard count, aggregation, indexing rate và dung lượng RAM cần giữ cho OS cache.

## 4. Bộ nhớ ngoài heap và native memory

Ngoài heap, một JVM process còn sử dụng native memory. Những vùng này không được tính đầy đủ trong chỉ số heap used.

Ví dụ:

- Thread stack cho từng thread.
- Direct ByteBuffer.
- Native library và runtime allocation.
- JIT compiler code cache.
- Metaspace chứa class metadata.
- TLS/network buffers.
- Memory-mapped file mappings.
- Các cấu trúc native của thư viện và hệ điều hành.

Tổng RSS của process vì thế có thể lớn hơn nhiều so với heap used.

Một node báo heap 55% nhưng process RSS gần chạm memory limit vẫn có thể bị container OOM kill. Đừng chỉ nhìn heap chart để quyết định node còn bao nhiêu RAM.

### Heap và off-heap khác nhau

| Đặc điểm | Heap | Off-heap/native |
|---|---|---|
| Quản lý | JVM garbage collector | JVM/native library/OS |
| Đo lường | Heap metrics | Process RSS, native memory, OS metrics |
| Vòng đời | Theo reachability và GC | Theo API/library/OS lifecycle |
| Áp lực | GC, allocation, heap exhaustion | Native memory exhaustion, direct buffer pressure |
| Ví dụ | Java object, aggregation state | Direct buffer, thread stack, mmap |

Không phải mọi memory-mapped file đều tương đương với một vùng RAM resident cố định. Mapping có thể chiếm virtual address space; các trang thực sự resident được quản lý bởi OS page cache và memory manager.

## 5. Filesystem page cache

Filesystem page cache là RAM do hệ điều hành dùng để cache nội dung file. Lucene segment được lưu trên disk, và những block đã đọc có thể được giữ trong page cache để lần đọc sau nhanh hơn.

Page cache đặc biệt quan trọng với search vì query thường truy cập:

- Inverted index postings.
- Term dictionary.
- Norms.
- Doc values.
- Stored fields và _source.
- Segment metadata.

Nếu dữ liệu nóng nằm trong page cache, nhiều thao tác đọc có thể được phục vụ từ RAM. Nếu cache không đủ hoặc workload truy cập dữ liệu phân tán, hệ điều hành phải đọc disk nhiều hơn.

Điều đó có nghĩa:

- Heap trống không đảm bảo search nhanh.
- Disk nhanh vẫn không thay thế hoàn toàn page cache.
- Index lớn hơn RAM không nhất thiết là vấn đề nếu working set nhỏ và ổn định.
- Query ngẫu nhiên trên working set rất lớn có thể tạo nhiều cache miss.

Khi benchmark, cần ghi cả memory của process và memory/page cache của node. Không nên chỉ nhìn JVM heap.

## 6. Disk là nơi lưu segment và translog

Elasticsearch sử dụng Lucene để lưu index. Các file segment là cấu trúc nền tảng của index. Một số thành phần dữ liệu phổ biến:

- Inverted index để tìm term trong text/keyword.
- Doc values để sort, aggregation và truy cập giá trị theo document.
- Stored fields và _source để trả lại nội dung document.
- Norms và metadata phục vụ scoring.
- Segment metadata và cấu trúc hỗ trợ đọc.
- Translog để bảo vệ thao tác ghi trước khi segment được flush/commit theo cơ chế của Elasticsearch.

Disk còn phải chứa:

- Primary shard data.
- Replica shard data.
- Translog.
- File tạm trong quá trình merge/recovery.
- Snapshot cache hoặc file liên quan tùy hạ tầng.
- Index khác trên cùng node.
- Log và các file hệ thống nếu cùng filesystem.

Dung lượng index hiển thị trong một API không nhất thiết bao gồm mọi chi phí tạm thời hoặc mọi file ở cấp node. Khi sizing disk, cần xem cả store size, translog, replica, merge headroom, recovery và growth.

## 7. Inverted index và chi phí lưu trữ

Với field text, Elasticsearch phân tích nội dung thành token rồi xây inverted index. Cấu trúc này cho phép tìm kiếm term nhanh, nhưng dung lượng phụ thuộc:

- Số document.
- Số token trên mỗi document.
- Cardinality của term.
- Độ dài token.
- Analyzer và normalizer.
- Số lượng field text.
- Term frequency và positions nếu lưu.

Một description dài với analyzer lưu positions có thể tốn nhiều storage hơn một keyword field đơn giản. Nếu cùng một nội dung được index vào nhiều field hoặc nhiều subfield, chi phí tăng thêm.

Không cần biến mọi field thành text. Field dùng để filter, sort hoặc aggregation thường phù hợp với keyword/numeric/date và doc values. Mapping nên phản ánh đúng truy vấn cần hỗ trợ.

## 8. Doc values: chi phí disk đổi lấy khả năng truy cập theo document

Doc values là cấu trúc column-oriented được lưu trên disk và dùng cho sort, aggregation, scripting hoặc truy cập field theo document. Với phần lớn field phù hợp, doc values được bật mặc định.

Doc values không phải heap cache. Lucene có thể đọc chúng qua filesystem và page cache. Một query aggregation vẫn có thể tạo state trên heap, dù giá trị gốc của field nằm trong doc values trên disk.

Ví dụ:

    "properties": {
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }

Các field này thường phù hợp cho filter, sort và aggregation. Khi mapping, cân nhắc:

- Field nào cần search text?
- Field nào cần exact match?
- Field nào cần sort/aggregation?
- Field nào chỉ cần hiển thị trong source?
- Field nào không cần được index?

Tắt doc values có thể giảm một phần storage nhưng làm mất hoặc hạn chế sort/aggregation và một số cách truy cập. Không tắt chỉ vì muốn giảm disk nếu workload còn cần các thao tác đó.

## 9. Stored fields và _source

_source thường giữ JSON document gốc dưới dạng lưu trữ được nén. Khi trả search result, Elasticsearch có thể phải đọc và giải nén source cho từng hit.

Nếu API chỉ cần ID, name và status, việc trả toàn bộ source lớn có thể tăng:

- Disk read.
- CPU giải nén.
- Network bytes.
- Heap allocation ở Elasticsearch và ứng dụng.
- JSON mapping/serialization cost.

Source filtering có thể giảm lượng source được trả về, nhưng không xóa dữ liệu đã lưu và không phải cơ chế authorization. Stored fields là một cơ chế riêng, chỉ áp dụng cho field được cấu hình store.

Trong Spring Data, nếu endpoint chỉ cần một phần dữ liệu, cân nhắc source filtering và DTO projection. Tuy nhiên, không dùng entity partial để save lại toàn document vì field không được tải có thể bị ghi đè hoặc mất.

## 10. Segment là gì?

Lucene index được tổ chức thành các segment bất biến. Khi dữ liệu được refresh, các thao tác ghi mới có thể được tạo thành segment mới để search nhìn thấy. Segment sau khi tạo không được sửa trực tiếp theo kiểu update một dòng trong relational database.

Update document thường được thực hiện về mặt logic bằng cách đánh dấu phiên bản cũ đã xóa và index phiên bản mới. Delete cũng đánh dấu document là deleted; dữ liệu vật lý được loại bỏ khi segment merge.

Vì vậy, index có nhiều update/delete có thể chứa:

- Nhiều segment.
- Deleted documents chưa được merge loại bỏ.
- File cũ còn tồn tại cho đến khi merge.
- Nhiều cấu trúc cần được mở và quản lý.

Số segment và mức độ phân mảnh ảnh hưởng đến search, memory, file descriptors và merge work.

## 11. Refresh tạo segment mới và ảnh hưởng workload

Refresh làm các thao tác ghi gần đây có thể được search nhìn thấy. Refresh không giống flush và không phải commit database transaction.

Nếu refresh quá thường xuyên:

- Nhiều segment nhỏ được tạo.
- Mỗi search có thể phải truy cập nhiều segment hơn.
- Segment metadata và reader overhead tăng.
- Merge phải xử lý nhiều segment nhỏ.

Nếu refresh quá thưa:

- Search visibility bị trễ.
- Người dùng có thể chưa thấy document vừa ghi.

Với workload indexing lớn, có thể cân nhắc refresh interval dài hơn hoặc refresh NONE trong bulk import, sau đó refresh khi cần. Lựa chọn phải theo yêu cầu search freshness.

Trong Spring Data Elasticsearch, RefreshPolicy có thể được cấu hình cho một số thao tác. Không dùng IMMEDIATE cho mọi document nếu không cần read-after-write ngay lập tức.

## 12. Segment merge và chi phí đĩa

Lucene merge nhiều segment nhỏ thành segment lớn hơn để cải thiện cấu trúc index và loại bỏ document đã bị đánh dấu deleted.

Merge cần:

- Đọc segment đầu vào.
- Ghi segment đầu ra mới.
- CPU để xử lý postings, doc values và stored fields.
- Disk bandwidth và IOPS.
- Dung lượng tạm thời trong lúc segment cũ và mới cùng tồn tại.

Trong lúc merge, dung lượng đĩa có thể tăng tạm thời. Disk sizing chỉ dựa trên kích thước index ổn định sẽ thiếu headroom cho merge, recovery và reindex.

Merge có thể bị throttle khi disk hoặc indexing load cao. Điều này giúp bảo vệ cluster nhưng cũng có thể làm merge backlog tăng.

Theo dõi merge time, merge throttling, segment count và disk utilization. Không force merge thường xuyên trên index đang tiếp tục ghi vì thao tác này tốn tài nguyên và có thể tạo thêm write amplification.

## 13. Update và delete làm tăng write amplification

Elasticsearch không cập nhật một field tại chỗ trong file segment như một số người hình dung về database row. Một update thường tạo phiên bản document mới và đánh dấu bản cũ đã xóa. Merge sau đó mới loại bỏ dữ liệu cũ về mặt vật lý.

Nếu cùng document được update nhiều lần:

- Segment chứa phiên bản cũ vẫn chiếm dung lượng trước khi merge.
- Translog và indexing work tăng.
- Merge phải xử lý nhiều deleted documents.
- Disk write amplification tăng.

Với document rất lớn và chỉ cập nhật một field nhỏ, việc index lại source có thể tốn đáng kể. Hãy cân nhắc document modeling và tách dữ liệu có tần suất update rất khác nhau nếu phù hợp với use case.

## 14. Translog và durability

Translog ghi nhận thao tác để Elasticsearch có thể phục hồi các write đã được acknowledge theo durability semantics. Translog được quản lý riêng với Lucene segment files.

Các khái niệm cần phân biệt:

- Index request được xử lý.
- Translog được ghi và đảm bảo theo durability configuration.
- Refresh làm document searchable.
- Flush tạo Lucene commit và làm sạch translog theo cơ chế tương ứng.

Translog có thể chiếm thêm disk. Khi write rate cao hoặc flush bị trì hoãn, dung lượng translog có thể tăng.

Không dùng refresh để thay thế durability. Cũng không tùy tiện tắt translog durability chỉ để tăng benchmark mà không hiểu rủi ro mất dữ liệu khi node/process gặp sự cố.

## 15. Chi phí replica

Mỗi primary shard có thể có một hoặc nhiều replica shard. Replica cung cấp khả năng chịu lỗi và tăng năng lực phục vụ search, nhưng chúng cần storage và tài nguyên indexing.

Nếu primary store size là P và có R replica, dung lượng dữ liệu shard ở trạng thái ổn định có thể xấp xỉ:

    total shard copies ~= P * (1 + R)

Đây là ước lượng cho dữ liệu shard, chưa bao gồm translog, merge headroom, recovery, overhead filesystem và các index khác.

Replica cũng làm tăng:

- Disk usage.
- Network replication traffic.
- CPU và disk write.
- Recovery time khi node rời cluster.

Replica có thể giúp search throughput vì query có thể được phân phối giữa các shard copies. Nhưng tăng replica không phải cách miễn phí để tăng tốc; phải benchmark cả read lẫn write.

## 16. Shard có chi phí bộ nhớ và metadata

Mỗi shard là một đơn vị Lucene index riêng. Một shard có thể có nhiều segment, reader, file handle, metadata và hoạt động background.

Quá nhiều shard nhỏ tạo overhead:

- Cluster state lớn hơn.
- Nhiều shard allocation và recovery tasks.
- Nhiều segment readers.
- Nhiều file descriptors.
- Nhiều request fan-out.
- Tốn heap và native resources.
- Merge và refresh overhead phân tán trên nhiều shard.

Quá ít shard hoặc shard quá lớn cũng có tradeoff:

- Một shard có thể trở thành hotspot.
- Recovery một shard lớn lâu hơn.
- Khó phân phối tải đều.
- Parallelism bị giới hạn.

Chọn shard count dựa trên data size, write rate, query fan-out, recovery objectives và kích thước shard mục tiêu. Không tạo một shard cho mỗi tenant nếu số tenant rất lớn và mỗi tenant có ít dữ liệu.

## 17. Chi phí index lớn không chỉ là dung lượng store

Một index lớn tạo chi phí ở nhiều lớp:

| Thành phần | Chi phí chính |
|---|---|
| Inverted index | Disk, page cache, CPU khi query |
| Doc values | Disk, page cache, aggregation/sort |
| _source/stored fields | Disk, giải nén, network và mapping |
| Segment metadata | Heap/native memory, file descriptors |
| Deleted docs | Storage và merge work trước khi được loại bỏ |
| Translog | Disk và recovery work |
| Replicas | Disk, network và indexing CPU |
| Shard metadata | Heap, cluster state và coordination |
| Aggregation state | Heap và CPU |
| Fielddata | Heap có thể tăng mạnh |
| Cache | Heap/native hoặc page cache tùy loại |

Một index có dung lượng nhỏ hơn nhưng high-cardinality aggregation có thể tạo áp lực heap lớn hơn index lớn được query bằng filter đơn giản.

## 18. Fielddata có thể gây áp lực heap

Fielddata là cấu trúc heap được dùng để truy cập giá trị field theo document cho một số loại field, đặc biệt là text khi cần aggregation hoặc sort.

Aggregation trên text field có thể khiến Elasticsearch phải xây fielddata. Với cardinality cao, fielddata có thể tiêu thụ nhiều heap.

Ví dụ mapping không phù hợp:

    "customerName": {
      "type": "text",
      "fielddata": true
    }

Nếu cần exact match, sort hoặc terms aggregation, thường nên dùng keyword subfield:

    "customerName": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }

Sau đó aggregate trên customerName.keyword thay vì bật fielddata cho text.

Fielddata có thể được cache trên heap và tạo memory pressure. Chỉ bật khi thực sự cần và hiểu cardinality.

## 19. Doc values không loại bỏ mọi chi phí aggregation

Keyword/numeric/date fields thường dùng doc values trên disk. Điều này giảm nhu cầu giữ toàn bộ giá trị field trong heap như fielddata của text.

Tuy nhiên, aggregation vẫn cần cấu trúc runtime:

- Bucket maps.
- Counts và metrics.
- Parent/child aggregation state.
- Pipeline aggregation data.
- Response serialization.

Terms aggregation high-cardinality có thể tạo nhiều bucket và tiêu thụ heap dù field dùng doc values. Giới hạn size, dùng composite aggregation khi cần duyệt nhiều bucket và tránh yêu cầu bucket không cần thiết.

## 20. Query cache và request cache

Elasticsearch có các cache với semantics khác nhau. Query cache có thể giữ kết quả filter bitset ở cấp shard cho những query phù hợp. Shard request cache có thể cache kết quả một số request, thường hữu ích với aggregation trên dữ liệu ít thay đổi.

Cache giúp giảm CPU và disk work, nhưng chiếm memory và phụ thuộc workload:

- Query lặp lại có thể được cache.
- Query thay đổi liên tục có thể ít cache hit.
- Segment thay đổi có thể ảnh hưởng cache entries.
- Request cache không có nghĩa mọi search response đều được cache.

Không nên tăng cache size chỉ vì thấy heap còn trống. Theo dõi hit/miss, eviction và memory. Một cache không phù hợp có thể chiếm heap nhưng ít giảm latency.

## 21. Aggregation có thể tiêu thụ heap lớn

Aggregation giữ trạng thái trong lúc query chạy. Chi phí phụ thuộc:

- Số document được xét.
- Cardinality field.
- Số bucket.
- Độ sâu aggregation lồng nhau.
- Nested/parent-child structure.
- Pipeline aggregation.
- Số shard tham gia.

Ví dụ terms aggregation theo productId trên hàng triệu giá trị khác nhau có thể tạo rất nhiều bucket:

    {
      "size": 0,
      "aggs": {
        "by_product": {
          "terms": {
            "field": "productId",
            "size": 100000
          }
        }
      }
    }

Không yêu cầu số bucket lớn nếu giao diện chỉ cần top 10. Nếu cần duyệt toàn bộ bucket, cân nhắc composite aggregation và phân trang bucket.

Circuit breaker có thể từ chối request dự kiến vượt ngưỡng memory. Đây là cơ chế bảo vệ node, không phải lỗi nên xử lý bằng cách tăng limit vô hạn.

## 22. Circuit breaker

Elasticsearch sử dụng circuit breakers để hạn chế các thao tác có nguy cơ tiêu thụ quá nhiều memory. Có breaker cho request, fielddata, in-flight requests và một số vùng khác tùy phiên bản.

Khi breaker kích hoạt:

- Request có thể bị từ chối.
- Client nhận exception.
- Search hoặc aggregation có thể thất bại dù query syntax hợp lệ.

Điều tra:

- Breaker nào kích hoạt?
- Query hoặc aggregation nào tạo memory estimate lớn?
- Cardinality và bucket count ra sao?
- Có nhiều request nặng chạy đồng thời không?
- Heap và GC đang ở trạng thái nào?

Không nên chỉ tăng breaker limit. Nếu request thực sự cần memory lớn hơn heap còn lại, tăng limit có thể chuyển lỗi có kiểm soát thành node OOM.

## 23. Indexing buffer

Elasticsearch dùng indexing buffer để gom dữ liệu trong quá trình indexing trước khi flush thành segment. Buffer được quản lý theo node và chia sẻ giữa các shard đang ghi.

Nếu write rate cao:

- Buffer được sử dụng nhanh.
- Segment mới được tạo thường xuyên hơn.
- Merge load tăng.
- CPU và disk throughput tăng.

Tăng indexing buffer không tự động cải thiện throughput nếu bottleneck là disk, CPU, merge hoặc network. Cần theo dõi indexing pressure, refresh, merge và disk utilization.

Với bulk indexing, batch size và concurrency của client phải phù hợp với khả năng ingest của node. Gửi quá nhiều request đồng thời có thể làm queue và indexing pressure tăng.

## 24. Indexing pressure

Elasticsearch có cơ chế indexing pressure để giới hạn memory liên quan đến các indexing request đang được xử lý ở coordinating, primary và replica stages. Cơ chế và metric cụ thể phụ thuộc phiên bản.

Khi indexing pressure cao:

- Request bulk có thể bị reject.
- 429 có thể tăng.
- Queue và retry ở client có thể tăng.
- Heap/native memory pressure có thể tăng.

Điều chỉnh client:

- Giảm concurrency.
- Chọn bulk size vừa phải.
- Dùng backoff và jitter khi retry 429.
- Tách item thất bại khỏi batch thành công nếu API cho phép.
- Theo dõi thời gian queue và indexing latency.

Không giải quyết overload bằng cách tăng worker vô hạn. Hệ thống cần backpressure để tốc độ gửi gần với tốc độ cluster có thể xử lý.

## 25. Disk watermark và cluster allocation

Elasticsearch theo dõi dung lượng disk và sử dụng watermarks để bảo vệ node khỏi hết dung lượng. Khi node vượt ngưỡng, cluster có thể hạn chế allocation hoặc chuyển shard tùy cấu hình/version.

Hậu quả của disk pressure:

- Shard không thể được allocate.
- Replica có thể unassigned.
- Cluster health chuyển yellow hoặc red.
- Merge/recovery có thể thiếu không gian.
- Write có thể bị chặn khi vượt flood-stage watermark.

Watermark cụ thể và cách áp dụng phụ thuộc Elasticsearch version/configuration. Không nên đặt watermark quá cao chỉ để trì hoãn cảnh báo; node cần đủ không gian để merge, recover và tiếp tục ingest.

Theo dõi disk free theo từng node, không chỉ tổng dung lượng cluster. Một node có thể đầy dù cluster còn nhiều disk trống do shard distribution lệch.

## 26. Ước lượng dung lượng disk

Một cách ước lượng sơ bộ:

    primary data size
      = document count * average primary bytes per document

    steady shard-copy storage
      ~= primary data size * (1 + replica count)

    required disk
      = steady shard-copy storage
        + translog allowance
        + merge/recovery headroom
        + growth allowance
        + other index/system overhead

Đây là mô hình lập kế hoạch, không phải công thức sizing chính xác. Average document bytes phải được đo sau khi index với mapping/analyzer thực tế, không dùng JSON payload size làm thay thế trực tiếp.

Khi tính capacity:

- Đo store size sau ingest và merge ổn định.
- Tính cả replica.
- Dành chỗ cho segment merge.
- Dành chỗ cho shard relocation/recovery.
- Dự báo tăng trưởng.
- Giữ disk free theo watermarks và operational policy.
- Kiểm tra mỗi node có đủ chỗ theo shard allocation thực tế.

## 27. Reindex và merge cần headroom

Reindex từ index cũ sang index mới có thể tạm thời cần dung lượng cho cả hai index:

    old index
    + new index under construction
    + replicas
    + translog
    + merge headroom
    + recovery headroom

Nếu chỉ có đủ disk cho index cuối cùng, reindex có thể thất bại giữa chừng vì old và new index cùng tồn tại.

Khi triển khai index version mới:

1. Ước lượng dung lượng index đích.
2. Kiểm tra dung lượng trên từng node.
3. Tính replica và merge headroom.
4. Tạo index mới.
5. Reindex theo batch có kiểm soát.
6. Theo dõi disk, merge và indexing pressure.
7. Đối soát dữ liệu.
8. Chuyển alias.
9. Chỉ xóa index cũ sau khi có quyết định rõ ràng.

## 28. Shard size và số lượng shard

Shard quá nhỏ làm tăng overhead quản lý. Shard quá lớn làm recovery lâu, khó phân phối tải và có thể tạo hotspot.

Không có một shard size tối ưu cho mọi workload. Kích thước phù hợp phụ thuộc:

- Số document.
- Mapping và field count.
- Write rate.
- Query fan-out.
- Recovery time objective.
- Disk type.
- Node count và RAM.
- Số segment và mức update/delete.

Hãy đo kích thước shard thực tế bằng cat shards hoặc index stats. Theo dõi phân phối giữa các node và số shard mỗi node.

Không đặt shard count theo một công thức cố định từ blog mà không benchmark workload và recovery.

## 29. Data stream, rollover và index lifecycle

Với dữ liệu append-only theo thời gian, data stream và rollover có thể giúp chia dữ liệu thành backing indices theo kích thước hoặc tuổi.

Lợi ích:

- Quản lý retention theo thời gian.
- Giới hạn kích thước từng backing index.
- Tách dữ liệu nóng và cũ.
- Dễ xóa index cũ theo lifecycle policy.

Chi phí:

- Nhiều backing index/shard nếu rollover quá thường xuyên.
- Alias/data stream metadata.
- Reindex hoặc force merge khi thay đổi policy.
- Query có thể fan-out qua nhiều backing index.

Chọn rollover theo kích thước và thời gian phù hợp. Rollover quá sớm tạo nhiều index nhỏ; quá muộn tạo shard lớn và recovery lâu.

## 30. Index lifecycle và tiered storage

Dữ liệu có thể được phân tầng theo mức độ truy cập:

- Hot: dữ liệu mới, cần search/write thường xuyên, storage nhanh.
- Warm: dữ liệu ít thay đổi, vẫn cần search.
- Cold/frozen: dữ liệu hiếm truy cập, tối ưu chi phí storage.

Tiered architecture có thể giảm chi phí tổng thể nhưng tăng độ phức tạp:

- Allocation và migration.
- Snapshot/cache behavior.
- Search latency khác nhau theo tier.
- Replica và recovery policy.
- Query fan-out qua nhiều tier.

Không đánh giá toàn bộ index chỉ bằng latency trên hot tier nếu production query cả dữ liệu cold. Workload cần mô phỏng tỷ lệ truy cập theo tuổi dữ liệu.

## 31. Heap sizing và nguyên tắc để RAM cho page cache

Heap phải đủ cho cluster metadata, query/aggregation state, fielddata, cache và indexing workload. Nhưng không nên chiếm hết RAM node.

Nguyên tắc vận hành phổ biến là để một phần đáng kể RAM cho filesystem cache. Elasticsearch thường tự cấu hình heap khi dùng các cách triển khai được hỗ trợ; nếu đặt thủ công, cần theo dõi hướng dẫn đúng phiên bản.

Không sao chép một heap size cố định giữa các node khác nhau. Heap phù hợp phụ thuộc:

- RAM node.
- Shard count và segment count.
- Aggregation workload.
- Fielddata.
- Indexing rate.
- Cluster state size.
- Query concurrency.
- JVM version và compressed references behavior.

Tránh tăng heap chỉ vì process RSS cao. RSS có thể bao gồm page cache hoặc native memory. Xác định phần nào đang tăng trước khi thay đổi.

## 32. Heap lớn có thể làm GC đắt hơn

Heap lớn không tự động xấu, nhưng object graph lớn làm GC phải quản lý nhiều memory hơn. Một số collector có thể xử lý heap lớn tốt, song pause, concurrent CPU và allocation pressure vẫn cần được theo dõi.

Dấu hiệu:

- Old generation thường xuyên gần đầy.
- GC pause dài.
- Allocation rate cao.
- Request latency tăng trùng thời điểm GC.
- Circuit breaker hoặc memory pressure xuất hiện.

Không tối ưu bằng cách giảm heap ngay nếu heap thực sự cần cho workload. Trước tiên kiểm tra query/aggregation gây allocation, fielddata, cache, shard count và ứng dụng gửi quá nhiều request đồng thời.

## 33. Native memory và container limit

Trong container, memory limit áp dụng cho process/container theo cơ chế cgroup. Heap maximum không đại diện cho tổng memory tiêu thụ.

Tổng memory có thể gồm:

    JVM heap
    + metaspace
    + code cache
    + thread stacks
    + direct buffers
    + native libraries
    + memory mappings / resident pages
    + other process memory

Nếu container limit quá sát heap maximum, process có thể bị OOM kill dù heap chưa đạt maximum.

Khi chạy Elasticsearch hoặc Spring Boot trong Kubernetes:

- Đặt memory request/limit có headroom.
- Kiểm tra JVM container awareness.
- Theo dõi RSS và cgroup memory.
- Theo dõi CPU throttling.
- Giới hạn thread/concurrency hợp lý.
- Tránh đặt heap bằng toàn bộ container limit.

Không chỉ xem Kubernetes pod restart count; xem OOMKilled reason và memory usage trước thời điểm chết.

## 34. Spring Data Elasticsearch cũng tiêu thụ memory

Phía ứng dụng có thể tạo áp lực memory đáng kể khi đọc hoặc ghi dữ liệu lớn:

- Mỗi document được chuyển thành Java object.
- Serializer tạo byte buffers.
- Bulk request giữ nhiều IndexQuery hoặc request item.
- Search result mapping tạo entity và nested collection.
- collectList giữ toàn bộ hit cho đến khi stream kết thúc.
- DTO mapping tạo object mới.
- Web layer serialize response JSON.

Ví dụ nguy hiểm:

    List<Product> all =
        repository.findAll();

    List<ProductResponse> responses =
        all.stream()
            .map(ProductResponse::from)
            .toList();

Với hàng triệu document, cả entity list và response list có thể cùng tồn tại trong heap. Điều này tạo allocation lớn và có thể gây OutOfMemoryError ở Spring application, dù Elasticsearch node vẫn khỏe.

Hãy dùng pagination, stream hoặc batch processing với giới hạn rõ ràng. Không gom toàn bộ index vào một collection chỉ để export.

## 35. Bulk request trong Spring Data

Bulk indexing giảm network overhead nhưng batch quá lớn có thể giữ nhiều object và serialized bytes trong memory.

Ví dụ batch:

    List<IndexQuery> batch = products.stream()
        .map(product -> IndexQuery.builder()
            .withId(product.getId())
            .withObject(product)
            .build())
        .toList();

    operations.bulkIndex(
        batch,
        BulkOptions.builder()
            .withRefreshPolicy(RefreshPolicy.NONE)
            .build(),
        IndexCoordinates.of("products")
    );

Sau khi bulk hoàn tất, giải phóng reference đến batch trước khi nạp batch kế tiếp. Trong pipeline dài, tránh giữ mọi batch trong một list lớn.

Batch size nên được cân bằng theo số document và tổng bytes. 1.000 document nhỏ khác rất nhiều 1.000 document có source vài trăm KB.

Theo dõi:

- Heap application.
- Bulk request bytes.
- Bulk latency.
- 429 và partial failures.
- Elasticsearch indexing pressure.
- Merge và disk throughput.

## 36. Reactive không có nghĩa memory vô hạn

Reactive Streams và backpressure giúp kiểm soát lượng dữ liệu downstream yêu cầu. Nhưng nếu ứng dụng dùng collectList, buffer không giới hạn hoặc flatMap concurrency quá cao, memory vẫn có thể tăng mạnh.

Ví dụ:

    Flux<SearchHit<Product>> hits = ...;

    Mono<List<Product>> products =
        hits.map(SearchHit::getContent)
            .collectList();

collectList giữ tất cả Product cho đến khi stream hoàn tất. Nếu có hàng trăm nghìn hit, heap ứng dụng có thể tăng mạnh.

Với dữ liệu lớn:

- Xử lý từng batch.
- Giới hạn flatMap concurrency.
- Dùng backpressure.
- Ghi kết quả theo stream.
- Dùng PIT/search_after hoặc scroll theo API phù hợp.
- Tránh giữ entity và DTO của toàn bộ index cùng lúc.

Backpressure ở client không tự giảm heap của Elasticsearch nếu query aggregation phía server đã tạo bucket lớn.

## 37. Source filtering giảm chi phí truyền và mapping

Nếu endpoint chỉ cần một vài field, source filtering có thể giảm bytes từ Elasticsearch về ứng dụng và giảm số field phải convert.

Ví dụ:

    Query query = NativeQuery.builder()
        .withQuery(q -> q.matchAll(m -> m))
        .withSourceFilter(
            new FetchSourceFilter(
                new String[] {"name", "price", "category"},
                null
            )
        )
        .build();

Tuy nhiên, source filtering không xóa field khỏi index và không phải authorization. Nó cũng không làm giảm mọi chi phí query engine nếu query vẫn cần đọc field khác để filter, sort hoặc aggregation.

Nếu source filter tạo entity partial, không dùng entity đó để save toàn document mà không khôi phục field bị thiếu. Map sang DTO read-only.

## 38. Query response size và heap

Một search trả nhiều hit có thể làm tăng:

- Elasticsearch fetch phase.
- Source decompression.
- Network bytes.
- Client JSON parsing.
- Entity mapping.
- Application heap.
- HTTP response serialization.

Giảm page size, chọn source fields cần thiết và trả DTO gọn có thể giảm chi phí. Nhưng không nên giảm size tùy tiện nếu API cần pagination semantics rõ ràng.

Với export lớn, stream theo trang và checkpoint thay vì trả một response JSON chứa hàng triệu document.

## 39. Mapping quá rộng làm index lớn

Dynamic mapping có thể tạo nhiều field khi document chứa object động hoặc key thay đổi theo dữ liệu. Mapping quá rộng làm tăng:

- Cluster state metadata.
- Field lookup overhead.
- Mapping serialization và propagation.
- Segment metadata và query planning complexity.
- Khả năng chạm giới hạn số field.

Ví dụ một document chứa map với key là user-generated values có thể tạo hàng nghìn field mapping nếu dynamic mapping được bật.

Hãy dùng kiểu field **flattened**, object model phù hợp hoặc tắt dynamic mapping cho phần không cần query theo từng key, tùy use case và phiên bản.

Không index mọi thuộc tính chỉ vì source có field đó. Chọn field dựa trên search/filter/sort/aggregation thực tế.

## 40. Multi-fields làm tăng index size

Một field text có nhiều subfield:

    "name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        },
        "english": {
          "type": "text",
          "analyzer": "english"
        }
      }
    }

Mỗi subfield có thể tạo thêm cấu trúc index và storage. Multi-fields hữu ích khi cùng một dữ liệu cần nhiều cách truy vấn, nhưng không nên tạo hàng loạt analyzer/subfield không được dùng.

Kiểm tra mapping và query usage trước khi thêm field. Một field không được truy vấn có thể chỉ làm index lớn hơn và tăng indexing CPU.

## 41. Nested data làm tăng số Lucene documents

Nested objects được biểu diễn bằng các Lucene documents nội bộ liên quan đến parent. Một source document có nhiều nested children có thể tạo nhiều Lucene documents hơn số source documents.

Nếu mỗi product có trung bình 20 offers, số Lucene documents có thể cao hơn đáng kể số product source records.

Điều này ảnh hưởng:

- Index size.
- Indexing throughput.
- Query cost.
- Nested aggregation.
- Segment count và merge.

Benchmark nested mapping cần dùng phân phối child count gần production, đặc biệt là p95/p99 số nested objects mỗi parent.

## 42. Routing và phân phối shard

Custom routing có thể giảm shard fan-out cho query theo tenant, nhưng cũng có thể dồn dữ liệu vào một số shard.

Ví dụ nếu tenant lớn nhất chiếm 40% dữ liệu và tất cả document của tenant đó cùng routing key, shard tương ứng có thể nóng hơn nhiều shard khác.

Theo dõi:

- Store size từng shard.
- Document count từng shard.
- Indexing rate theo shard nếu metric có.
- Search request distribution.
- CPU/disk per node.

Không chỉ xem tổng cluster resources. Một node hoặc shard hotspot có thể giới hạn toàn bộ workload dù các node khác còn dư tài nguyên.

## 43. Snapshot không giống bản sao shard đang chạy

Snapshot lưu backup ở repository ngoài cluster. Nó không nên được tính như một replica shard đang phục vụ search, và dung lượng snapshot có thể có sharing/deduplication tùy repository và cách snapshot được tạo.

Khi lập capacity:

- Disk của active index.
- Replica.
- Merge/recovery headroom.
- Snapshot repository capacity.
- Retention của snapshot.
- Tốc độ snapshot/restore.

Không để snapshot repository dùng chung disk data path của node nếu điều đó tạo cạnh tranh I/O hoặc làm cạn dung lượng.

## 44. Recovery và relocation cũng tiêu thụ tài nguyên

Khi node rời cluster hoặc shard được di chuyển, Elasticsearch phải copy dữ liệu shard và phục hồi trạng thái.

Recovery có thể dùng:

- Disk read/write.
- Network bandwidth.
- CPU.
- Heap/native buffers.
- File descriptors.

Trong lúc recovery, search/index latency có thể tăng. Một cluster chỉ benchmark ở trạng thái ổn định sẽ không cho biết khả năng phục hồi sau node failure.

Nếu availability và recovery time quan trọng, hãy benchmark hoặc kiểm thử recovery riêng trong môi trường an toàn. Không tạo node failure trên production tùy tiện.

## 45. Theo dõi heap và JVM

Có thể xem JVM stats qua Node Stats:

    GET _nodes/stats/jvm

Các trường quan tâm:

- Heap used/committed/max.
- Memory pools.
- GC collectors.
- GC collection count/time.
- JVM uptime.

Theo dõi theo node và theo thời gian. Một node có heap pressure cao hơn nhiều node khác có thể đang giữ shard nóng, fielddata lớn hoặc nhận query không đều.

Không kết luận chỉ từ một snapshot. Xem xu hướng, peak và tương quan với request latency.

## 46. Theo dõi process và native memory

Node Stats process có thể cung cấp thông tin process memory và CPU:

    GET _nodes/stats/process

Kết hợp với OS/container metrics:

- RSS.
- Virtual memory.
- Cgroup memory usage.
- OOM events.
- Thread count.
- CPU utilization.
- CPU throttling.

Nếu heap ổn nhưng RSS tăng liên tục, điều tra direct buffers, native allocations, thread count, memory mappings và OS cache. Phân biệt process RSS với page cache toàn node tùy cách hệ điều hành/container báo cáo.

## 47. Theo dõi filesystem và disk

Node stats filesystem:

    GET _nodes/stats/fs

Index stats:

    GET products/_stats/store,segments,translog,merge,refresh,flush

Cat APIs hữu ích để quan sát:

    GET _cat/indices?v&h=index,pri,rep,docs.count,store.size,pri.store.size

    GET _cat/shards/products?v

Theo dõi:

- Disk free trên từng node.
- Store size primary và tổng.
- Translog size.
- Segment count.
- Merge current/total/time.
- Merge throttling.
- IOPS và disk latency.
- Read/write throughput.
- Shard allocation và recovery.

Store size không phải toàn bộ disk headroom cần thiết. Luôn đối chiếu với filesystem free và growth/merge/recovery plan.

## 48. Theo dõi indexing, search và breaker

Index stats có thể cung cấp counter cho indexing/search/merge/refresh:

    GET products/_stats/indexing,search,merge,refresh,flush,fielddata,query_cache,request_cache

Node stats có thể quan sát breaker và thread pool:

    GET _nodes/stats/breaker,thread_pool,indices

Theo dõi:

- Indexing total/current time.
- Search query/fetch count và time.
- Rejected requests.
- Fielddata memory.
- Query/request cache hit/miss.
- Breaker estimated/limit/tripped.
- Thread pool queue và rejected count.
- Indexing pressure nếu phiên bản expose.

Counter thường là tích lũy từ lúc node khởi động. Để tính rate, lấy chênh lệch theo thời gian và xử lý node restart/reset.

## 49. Theo dõi cluster và shard allocation

Các API:

    GET _cluster/health

    GET _cluster/stats

    GET _cat/nodes?v

    GET _cat/allocation?v

Chúng giúp xem:

- Cluster health.
- Node count.
- Shard count.
- Unassigned shard.
- Disk allocation.
- Index/store totals.
- Node roles.

Cluster green không có nghĩa mọi node đều cân bằng hoặc workload có latency tốt. Một cluster có thể green nhưng một shard nóng, heap cao hoặc disk latency lớn.

## 50. Spring Boot Actuator và Micrometer

Ở phía ứng dụng, Spring Boot Actuator và Micrometer có thể thu thập:

- JVM memory và GC.
- Process CPU.
- HTTP server request duration.
- Connection pool metrics nếu client integration expose.
- Thread pool và executor metrics.
- Custom timer cho ElasticsearchOperations.
- Bulk failure và retry counters.

Ví dụ đo thời gian thao tác search imperative:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;
        private final MeterRegistry registry;

        public ProductSearchService(
                ElasticsearchOperations operations,
                MeterRegistry registry) {
            this.operations = operations;
            this.registry = registry;
        }

        public SearchHits<Product> search(Query query) {
            Timer timer = registry.timer(
                "product.search.duration",
                "operation",
                "search"
            );

            return timer.record(() ->
                operations.search(query, Product.class)
            );
        }
    }

Timer này đo thời gian service call, không chỉ thời gian query engine. Nó có thể gồm network, conversion và các bước trong client path.

Không thêm raw query text, document ID hoặc tenant ID cardinality cao vào metric tags. Dùng query family và operation name có số lượng giá trị giới hạn.

## 51. Đo reactive operation đúng cách

Reactive publisher thường lazy. Nếu chỉ đo thời gian tạo Mono, bạn không đo thời gian request thực thi.

Ví dụ:

    Mono<ReactiveSearchHits<Product>> result =
        reactiveOperations.search(query, Product.class);

Đo thời gian cần bao quanh subscription và terminal signal, hoặc dùng Micrometer Observation/Reactor instrumentation đã được cấu hình.

Không gọi block chỉ để lấy Timer.record. Có thể dùng Mono.defer để bắt đầu timer khi subscription bắt đầu, sau đó dừng timer ở doFinally hoặc dùng cơ chế instrumentation chuyên dụng.

Với reactive stream dài, cần phân biệt:

- Thời gian nhận response metadata.
- Thời gian phát hit đầu tiên.
- Thời gian phát hit cuối cùng.
- Thời gian downstream xử lý hoàn tất.

Một Flux có thể giữ resource và subscription trong thời gian dài; đo một duration tổng duy nhất có thể không đủ để tìm bottleneck.

## 52. Heap pressure trong Spring application

Ứng dụng Spring có thể tăng heap do:

- Search page size quá lớn.
- collectList trên Flux lớn.
- Bulk batch giữ nhiều object.
- DTO mapping tạo object mới.
- JSON serialization buffer.
- Retry queue trong memory.
- Cache ứng dụng không có giới hạn.
- Async executor queue lớn.

Ví dụ:

    Flux<SearchHit<Product>> hits = ...;

    Mono<List<Product>> products =
        hits.map(SearchHit::getContent)
            .collectList();

collectList giữ tất cả Product cho đến khi stream hoàn tất. Nếu có hàng trăm nghìn hit, heap ứng dụng có thể tăng mạnh.

Dùng batch processing, bounded concurrency và streaming response. Đặt giới hạn rõ cho page size và queue.

## 53. Phân biệt heap của Spring Boot và heap Elasticsearch

Ứng dụng Spring Boot và Elasticsearch thường là hai process riêng. Chúng có JVM heap, GC, native memory và container limits riêng.

Một dashboard chỉ hiển thị Elasticsearch heap không cho biết Spring application có bị OutOfMemoryError khi mapping response hay không.

Theo dõi riêng:

| Thành phần | Cần đo |
|---|---|
| Spring Boot JVM | Heap, GC, RSS, allocation, thread pool |
| Elasticsearch JVM | Heap, GC, breaker, indexing/search state |
| OS/node | Page cache, free memory, disk I/O, CPU |
| Network | Bytes, latency, retransmission, connection |
| Storage | Free space, IOPS, latency, throughput |

Nếu hai process cùng chạy trên một host, chúng cạnh tranh RAM, CPU và disk. Cần tính tổng memory limit và không để một process chiếm hết page cache hoặc native memory của process còn lại.

## 54. Tối ưu mapping để giảm index footprint

Mapping tốt có thể giảm storage và indexing work:

- Dùng keyword cho exact match, không dùng text nếu không cần full-text.
- Không tạo multi-field nếu không có query use case.
- Dùng numeric/date type phù hợp.
- Tắt index cho field chỉ cần trả source và không cần query.
- Cân nhắc doc_values theo nhu cầu sort/aggregation.
- Giới hạn dynamic fields.
- Dùng nested chỉ khi cần semantics nested.
- Không index secret hoặc dữ liệu không cần search.
- Tránh duplicate cùng một payload vào nhiều field.

Mọi thay đổi mapping cần đánh giá cả query semantics và khả năng reindex. Giảm storage bằng cách tắt tính năng mà ứng dụng đang cần sẽ tạo lỗi chức năng.

## 55. Giảm fielddata và aggregation pressure

Nếu fielddata tăng:

1. Xác định field nào đang giữ fielddata.
2. Kiểm tra query/aggregation dùng field đó.
3. Nếu field là text nhưng cần exact bucket, thêm keyword subfield trong index mới.
4. Chuyển aggregation sang keyword field.
5. Reindex dữ liệu nếu mapping thay đổi yêu cầu.
6. Theo dõi heap và breaker sau thay đổi.

Không xóa fielddata cache liên tục như giải pháp lâu dài. Cache sẽ được xây lại và gây thêm CPU/latency.

## 56. Giảm segment và merge pressure

Để kiểm soát segment:

- Chọn refresh interval theo yêu cầu freshness.
- Tránh refresh IMMEDIATE trên mọi document.
- Dùng bulk indexing thay cho request nhỏ lặp lại.
- Không force merge index đang ghi liên tục.
- Theo dõi merge backlog và throttling.
- Chọn shard count phù hợp.
- Hạn chế update/delete không cần thiết.

Với index gần như immutable, force merge có thể hữu ích trong quy trình lifecycle được kiểm soát. Với index đang nhận update liên tục, force merge có thể tạo write amplification và cạnh tranh I/O.

## 57. Giảm chi phí _source và fetch

Nếu search chỉ cần một vài field:

- Dùng source filtering.
- Giảm page size.
- Dùng DTO thay vì trả entity đầy đủ.
- Tránh lấy highlight/inner_hits nếu không cần.
- Tránh trả nested payload rất lớn.

Nếu source filtering tạo entity partial, không dùng entity đó để ghi đè toàn document. Tách read model và write model.

Source filtering giảm response payload, không xóa field khỏi index và không phải cơ chế bảo mật. Nếu cần field-level authorization, dùng security policy tương ứng.

## 58. Tối ưu bulk và refresh trong Spring Data

Một bulk job có thể dùng batch hữu hạn:

    for (List<Product> batch : batches) {
        List<IndexQuery> queries = batch.stream()
            .map(product -> IndexQuery.builder()
                .withId(product.getId())
                .withObject(product)
                .build())
            .toList();

        operations.bulkIndex(
            queries,
            BulkOptions.builder()
                .withRefreshPolicy(RefreshPolicy.NONE)
                .build(),
            IndexCoordinates.of("products")
        );
    }

Đây là ví dụ imperative. Cần chọn batch size theo bytes và cluster capacity. Sau import, refresh một lần nếu cần search visibility ngay.

Đừng giữ toàn bộ source list, toàn bộ IndexQuery list và response list cùng lúc nếu dataset lớn. Đọc nguồn theo batch, ghi batch, giải phóng reference và tiếp tục.

## 59. Tối ưu query concurrency

Nhiều query nặng đồng thời có thể tiêu thụ heap và CPU vượt khả năng node. Một query aggregation high-cardinality có thể không gây vấn đề khi chạy riêng nhưng gây breaker khi 50 request chạy cùng lúc.

Ở ứng dụng:

- Giới hạn concurrency theo endpoint.
- Dùng rate limit cho truy vấn nặng.
- Đặt timeout hợp lý.
- Dùng pagination và bucket limit.
- Tránh retry storm.
- Có circuit breaker ở tầng ứng dụng nếu phù hợp.

Ở Elasticsearch:

- Theo dõi thread pool và breaker.
- Theo dõi search queue/rejections.
- Kiểm tra shard fan-out.
- Tối ưu query/mapping.

Không tăng thread pool hoặc queue tùy tiện; nhiều request đồng thời có thể làm heap pressure tăng.

## 60. Khi nào cần thêm node hoặc tăng tài nguyên?

Trước khi scale, xác định tài nguyên nào thực sự bão hòa:

- CPU cao liên tục.
- Heap pressure/GC cao.
- Page cache không đủ cho working set.
- Disk latency hoặc throughput đạt giới hạn.
- Network bão hòa.
- Shard hotspot.
- Query fan-out quá lớn.
- Indexing pressure hoặc merge backlog.

Scale up (thêm CPU/RAM/disk nhanh hơn) và scale out (thêm node) giải quyết các vấn đề khác nhau. Thêm node không tự động phân phối shard ngay lập tức nếu allocation/routing không phù hợp. Tăng RAM nhưng dồn hết vào heap có thể làm page cache giảm.

Sau khi thay đổi tài nguyên, chạy lại cùng workload để đo lợi ích thực tế và chi phí.

## 61. Capacity planning theo growth

Lập kế hoạch cần dự báo:

- Document mới mỗi ngày.
- Tăng trưởng source size.
- Số field và mapping evolution.
- Update/delete rate.
- Replica count.
- Retention period.
- Rollover frequency.
- Snapshot retention.
- Reindex windows.
- Growth headroom.

Ví dụ mô hình:

    daily_primary_growth = new_docs_per_day
                          * measured_primary_bytes_per_doc

    retained_primary_size = daily_primary_growth
                            * retention_days

    steady_shard_data = retained_primary_size
                        * (1 + replicas)

Sau đó cộng translog, merge/recovery headroom, index overhead và các index khác. Mô hình phải được hiệu chỉnh bằng store size thực tế sau khi ingest.

Không dùng kích thước JSON input làm primary bytes per document vì analyzer, postings, doc values, source compression và mapping ảnh hưởng đáng kể.

## 62. Index lớn và reindex strategy

Khi mapping hoặc analyzer thay đổi, có thể cần tạo index mới và reindex. Index lớn khiến quá trình này tiêu thụ:

- Disk cho index cũ và mới.
- CPU và disk read/write.
- Network giữa nodes.
- Heap/native buffers.
- Merge resources.
- Thời gian để catch up thay đổi mới.

Thiết kế alias versioned:

    products-v1
    products-v2
          |
          v
      products alias

Reindex vào v2, đối soát dữ liệu, rồi atomically switch alias. Giữ v1 đủ lâu cho rollback theo policy.

Không bắt đầu reindex nếu disk headroom không đủ. Không xóa index cũ trước khi xác nhận alias và dữ liệu mới hoạt động đúng.

## 63. Kiểm thử memory và disk dưới tải

Một kế hoạch kiểm thử nên có:

- Indexing bulk đến quy mô dự kiến.
- Search-only trên index ổn định.
- Mixed search/write.
- Aggregation high-cardinality.
- Update/delete workload.
- Reindex.
- Node restart/recovery.
- Soak test đủ lâu để quan sát merge và cache behavior.

Thu thập:

- Heap peak và GC pause.
- RSS và cgroup memory.
- Page cache/available memory.
- Disk free và disk latency.
- Store size/translog.
- Segment count và merge.
- Indexing pressure.
- Breaker trips.
- Search p95/p99.
- Bulk throughput và failures.

Một bài test ngắn có thể không thấy merge backlog hoặc memory leak. Chạy đủ lâu để workload đạt trạng thái ổn định.

## 64. Những lỗi thường gặp

### Nghĩ index lớn phải có heap bằng kích thước index

Phần lớn Lucene segment nằm trên disk và được hỗ trợ bởi filesystem cache. Heap giữ cấu trúc runtime, cache và query state.

### Dành toàn bộ RAM cho heap

Page cache giảm và GC có thể đắt hơn. Cần để RAM cho OS và native memory.

### Chỉ xem heap used

RSS, direct buffer, thread stack, page cache và cgroup limit cũng quan trọng.

### Nghĩ doc values không dùng memory

Doc values nằm trên disk nhưng được truy cập qua page cache; aggregation vẫn cần runtime state.

### Bật fielddata trên text để làm aggregation

Có thể tạo heap pressure lớn. Dùng keyword subfield khi semantics phù hợp.

### Aggregation high-cardinality không giới hạn

Bucket state có thể tiêu thụ heap và kích hoạt breaker. Giới hạn size hoặc dùng composite pagination.

### Refresh quá thường xuyên

Tạo nhiều segment nhỏ và tăng merge overhead. Chọn freshness policy phù hợp.

### Force merge thường xuyên

Tốn disk/CPU và không phù hợp với index đang ghi liên tục.

### Tạo quá nhiều shard nhỏ

Tăng cluster state, reader, file handle và coordination overhead.

### Chỉ tính primary store khi sizing disk

Bỏ sót replica, translog, merge headroom, recovery và growth.

### Bulk batch quá lớn

Ứng dụng và cluster giữ nhiều memory, latency tăng và retry tốn kém. Giới hạn theo bytes và concurrency.

### Dùng collectList cho index lớn

Giữ toàn bộ entity trong heap ứng dụng. Stream hoặc batch processing.

### Tăng concurrency khi đã có 429

Có thể làm overload nặng hơn. Giảm tốc, backoff và điều chỉnh batch.

### Không đo page cache/disk

Heap chart có thể ổn trong khi search bị giới hạn bởi disk I/O.

### Reindex không có disk headroom

Index cũ và mới cùng tồn tại, merge và recovery có thể làm node hết disk.

### Scale node mà không xem shard distribution

Hot shard vẫn có thể giới hạn throughput. Kiểm tra allocation và routing.

## 65. Quy trình điều tra node chậm hoặc index quá lớn

Khi search/indexing suy giảm:

1. Xác định node và shard chịu tải cao.
2. Kiểm tra cluster health, allocation và disk free.
3. Xem heap, GC và breaker.
4. Xem RSS, native memory và container limit.
5. Xem page cache, disk latency và throughput.
6. Kiểm tra segment count, merge và translog.
7. Kiểm tra indexing pressure và thread pool queue/rejections.
8. Kiểm tra fielddata, query cache và request cache.
9. Xem query mix, aggregation cardinality và shard fan-out.
10. Kiểm tra application heap, bulk batch và response size.
11. Dùng slow logs/Profile API để điều tra query cụ thể.
12. Thay đổi một yếu tố, chạy lại workload và so p95/p99 cùng tài nguyên.

Không bắt đầu bằng việc tăng heap hoặc tăng node count nếu chưa xác định bottleneck. Một thay đổi tài nguyên sai có thể làm tình hình tệ hơn hoặc chỉ che dấu nguyên nhân.

## 66. Checklist thiết kế index lớn

- Mapping chỉ index field cần query.
- Field text có keyword subfield khi cần exact match/aggregation.
- Không bật fielddata tùy tiện.
- Cardinality aggregation được kiểm soát.
- Source payload không chứa dữ liệu không cần thiết.
- Dynamic mapping được kiểm soát.
- Nested object count có giới hạn hợp lý.
- Shard count phù hợp với kích thước và workload.
- Replica được tính vào disk và write capacity.
- Refresh interval phù hợp freshness.
- Bulk batch và concurrency được giới hạn.
- Disk có merge/recovery headroom.
- Heap để đủ chỗ cho page cache và native memory.
- JVM heap/GC được theo dõi theo thời gian.
- RSS và cgroup limit được giám sát.
- Snapshot và reindex capacity được tính riêng.
- Spring Data không gom toàn bộ dataset vào memory.
- Query response size và source filtering được đánh giá.
- Monitoring có alert cho breaker, 429, disk watermark và merge backlog.

## Kết luận

Hiệu năng của index lớn phụ thuộc vào sự cân bằng giữa JVM heap, native/off-heap memory, filesystem page cache và disk. Heap giữ metadata, cache và query/aggregation state; Lucene segment, inverted index, doc values, stored fields và translog chủ yếu được lưu trên disk, trong khi page cache giúp đọc file nhanh. Heap quá lớn có thể làm thiếu RAM cho page cache, còn heap nhỏ hoặc aggregation/fielddata quá nặng có thể gây GC pressure và circuit breaker. RSS cũng có thể vượt heap do native memory, thread stack và memory mapping.

Index lớn làm tăng chi phí segment, merge, update/delete, replica, shard metadata, recovery và reindex. Khi sizing disk, phải tính primary data, replica, translog, merge/recovery headroom và growth; khi sizing shard, phải cân bằng shard size với fan-out, allocation và recovery time. Trong Spring Data Elasticsearch, bulk batch, entity mapping, response size và collectList có thể tạo áp lực heap riêng ở application. Theo dõi JVM, process RSS, page cache, disk I/O, segment/merge, indexing pressure, breaker và thread pool cùng lúc. Tối ưu mapping, refresh, bulk concurrency và shard layout dựa trên workload đo được, không dựa vào một chỉ số heap hoặc một con số dung lượng index đơn lẻ.

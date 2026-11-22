# Chính sách lưu giữ, snapshot và phục hồi dữ liệu tìm kiếm

Một hệ thống tìm kiếm cần kế hoạch cho toàn bộ vòng đời dữ liệu: dữ liệu được ghi vào index nào, giữ trong bao lâu, khi nào chuyển sang tầng lưu trữ khác, lúc nào xóa và làm sao khôi phục khi xảy ra sự cố. Trong Elasticsearch, alias giúp ứng dụng làm việc với tên logic ổn định; Index Lifecycle Management (ILM) hoặc cơ chế lifecycle phù hợp giúp tự động quản lý index; snapshot repository và Snapshot Lifecycle Management (SLM) hỗ trợ sao lưu và quản lý thời hạn lưu bản sao.

Ba trách nhiệm cần được phân biệt:

- **Retention của index:** quyết định dữ liệu tìm kiếm trực tuyến được giữ bao lâu và khi nào index bị xóa.
- **Snapshot:** tạo bản sao lưu có thể dùng để phục hồi index hoặc dữ liệu cluster trong phạm vi snapshot đã chọn.
- **Retention của snapshot:** quyết định bản sao lưu được giữ bao lâu và khi nào có thể xóa snapshot cũ.

Snapshot không thay thế retention của index. Ngược lại, ILM xóa index không đồng nghĩa snapshot tương ứng cũng bị xóa. Một chính sách hoàn chỉnh phải quản lý cả dữ liệu đang phục vụ truy vấn lẫn các bản sao lưu.

## 1. Vì sao cần chính sách vòng đời dữ liệu?

Dữ liệu tìm kiếm thường tăng liên tục. Log, audit event, telemetry, lịch sử giao dịch và nội dung nghiệp vụ có tốc độ ghi, thời hạn sử dụng và yêu cầu phục hồi khác nhau.

Nếu không có chính sách vòng đời:

- Index cũ tiếp tục chiếm dung lượng dù không còn giá trị truy vấn.
- Shard tăng kích thước và làm tăng chi phí lưu trữ, phục hồi, quản lý.
- Dữ liệu quan trọng có thể bị xóa nhầm hoặc không có bản sao lưu.
- Snapshot cũ tích tụ và chiếm dung lượng repository.
- Khi cluster hỏng, đội ngũ không biết bản sao nào có thể phục hồi và mất bao lâu.

Retention phải bắt đầu từ yêu cầu nghiệp vụ. Ví dụ, log vận hành có thể chỉ cần truy vấn trực tuyến trong 30 ngày; audit record có thể phải giữ lâu hơn theo chính sách tổ chức; dữ liệu cá nhân có thể phải xóa theo yêu cầu pháp lý. Không nên chọn thời hạn chỉ vì một con số mặc định trong cấu hình.

### 1.1. Xác định yêu cầu trước khi cấu hình

Với mỗi nhóm dữ liệu, hãy xác định:

| Yêu cầu | Câu hỏi |
|---|---|
| Thời hạn trực tuyến | Người dùng cần tìm kiếm dữ liệu trong bao lâu? |
| Thời hạn lưu trữ tổng thể | Dữ liệu phải tồn tại bao lâu theo nghiệp vụ hoặc quy định? |
| Tần suất truy vấn | Dữ liệu mới và dữ liệu cũ được truy vấn thường xuyên đến mức nào? |
| RPO | Có thể chấp nhận mất tối đa bao nhiêu dữ liệu khi phục hồi? |
| RTO | Hệ thống cần hoạt động trở lại trong bao lâu? |
| Dung lượng | Tốc độ ghi và dung lượng tăng mỗi ngày là bao nhiêu? |
| Phạm vi phục hồi | Cần phục hồi một index, một nhóm index hay cả cluster? |
| Quyền riêng tư | Có yêu cầu xóa dữ liệu khỏi index, snapshot và các bản sao lưu không? |

RPO (Recovery Point Objective) mô tả mức mất dữ liệu tối đa có thể chấp nhận, thường quy đổi thành khoảng thời gian. RTO (Recovery Time Objective) mô tả thời gian mục tiêu để khôi phục dịch vụ. Lịch snapshot, tốc độ ghi và thời gian phục hồi cần được thiết kế theo hai chỉ số này.

## 2. Alias là lớp tên logic cho index

Ứng dụng không nhất thiết phải truy cập trực tiếp index vật lý. Alias là tên logic có thể trỏ đến một hoặc nhiều index, đồng thời có thể được dùng làm điểm đọc hoặc ghi.

Ví dụ:

~~~text
Ứng dụng
   |
   +---- đọc ----> logs-read
   |                  |
   |                  +----> logs-000041
   |                  +----> logs-000042
   |
   +---- ghi ----> logs-write
                      |
                      +----> logs-000042 (write index)
~~~

Khi rollover tạo index mới, alias ghi có thể được chuyển sang index mới mà ứng dụng vẫn tiếp tục ghi vào cùng tên logs-write. Alias đọc có thể trỏ đến tất cả index còn trong thời hạn tìm kiếm.

Alias không tự xóa dữ liệu và không phải bản sao lưu. Nó là lớp định tuyến giúp tách tên ứng dụng khỏi tên index vật lý. Cần biết alias đang trỏ đến index nào trước khi thực hiện restore, xóa hoặc thay đổi lifecycle.

Có thể đọc alias bằng:

~~~http
GET /_alias/logs-read,logs-write
~~~

Hoặc dùng CAT API để quan sát dạng bảng:

~~~http
GET /_cat/aliases?v
~~~

## 3. Retention và ILM

Index Lifecycle Management (ILM) cho phép định nghĩa các phase và action để Elasticsearch quản lý index theo tuổi đời hoặc điều kiện vòng đời. Một policy có thể rollover index, chuyển dữ liệu sang tầng phù hợp, tối ưu index hoặc xóa index khi hết thời hạn.

Các phase thường gặp:

| Phase | Vai trò thường dùng |
|---|---|
| Hot | Nhận ghi và phục vụ truy vấn thường xuyên |
| Warm | Dữ liệu ít thay đổi, có thể tối ưu để giảm chi phí |
| Cold | Dữ liệu ít được truy cập, ưu tiên tiết kiệm tài nguyên |
| Frozen | Dữ liệu rất ít truy cập, có thể dùng searchable snapshots tùy kiến trúc |
| Delete | Xóa index khi đã hết thời hạn lưu giữ |

Không phải index nào cũng cần đi qua tất cả phase. Một hệ thống nhỏ có thể chỉ cần hot và delete. Tầng lưu trữ và action khả dụng phụ thuộc phiên bản Elasticsearch, license, loại index và cấu hình cluster.

### 3.1. Rollover tạo index mới

Rollover đóng luồng ghi vào index hiện tại và chuyển write alias sang index mới khi đạt một điều kiện, ví dụ:

- Index đạt tuổi tối đa.
- Primary shard đạt kích thước mục tiêu.
- Index đạt số lượng document mục tiêu.

Ví dụ policy có thể rollover khi index đã một ngày tuổi hoặc primary shard lớn hơn 50 GB:

~~~http
PUT /_ilm/policy/logs-retention-policy
Content-Type: application/json

{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_age": "1d",
            "max_primary_shard_size": "50gb"
          }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "forcemerge": {
            "max_num_segments": 1
          }
        }
      },
      "delete": {
        "min_age": "90d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
~~~

Đây là ví dụ minh họa, không phải con số phù hợp cho mọi hệ thống. Cần chọn kích thước shard và thời điểm rollover theo tốc độ ingest, dung lượng node, thời gian truy vấn và yêu cầu vận hành. Việc force merge có thể tiêu tốn tài nguyên I/O và cần được tính đến trong tải cluster.

### 3.2. Gắn ILM policy qua index template

Với mô hình index theo alias, index template có thể khai báo policy và rollover alias cho các index mới:

~~~http
PUT /_index_template/logs-template
Content-Type: application/json

{
  "index_patterns": ["logs-*"],
  "template": {
    "settings": {
      "index.lifecycle.name": "logs-retention-policy",
      "index.lifecycle.rollover_alias": "logs-write"
    },
    "mappings": {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "message": {
          "type": "text"
        },
        "level": {
          "type": "keyword"
        }
      }
    },
    "aliases": {
      "logs-read": {}
    }
  }
}
~~~

Sau đó tạo index khởi đầu và gắn write alias:

~~~http
PUT /logs-000001
Content-Type: application/json

{
  "aliases": {
    "logs-write": {
      "is_write_index": true
    }
  }
}
~~~

Các lần ghi tiếp theo có thể gửi đến logs-write. Khi điều kiện rollover đạt ngưỡng, ILM tạo index kế tiếp và cập nhật write alias. logs-read tiếp tục cung cấp điểm đọc trên các index phù hợp.

Index template chủ yếu áp dụng khi tạo index. Thay đổi template không tự động sửa settings hoặc mapping của index đã tồn tại. Cần kiểm tra index hiện tại bằng API và có migration riêng nếu cần thay đổi.

### 3.3. Xem trạng thái ILM

Có thể xem policy:

~~~http
GET /_ilm/policy/logs-retention-policy
~~~

Kiểm tra trạng thái lifecycle của các index:

~~~http
GET /logs-*/_ilm/explain
~~~

Kết quả explain giúp xác định index đang ở phase nào, action nào đang chạy, lần chạy tiếp theo và lỗi nếu lifecycle bị dừng. Khi một index không được xóa đúng hạn, cần xem trạng thái ILM thay vì xóa thủ công ngay lập tức.

### 3.4. Retention theo data stream

Với dữ liệu append-only như log và event, data stream có thể phù hợp hơn mô hình index và alias tự quản lý. Data stream tổ chức dữ liệu thành các backing index, cho phép ghi vào luồng logic và rollover khi cần.

Có thể quản lý vòng đời backing index bằng ILM thông qua index template. Một số phiên bản Elasticsearch còn cung cấp Data Stream Lifecycle với cách cấu hình retention đơn giản hơn cho data stream. Hãy chọn một cơ chế lifecycle phù hợp với phiên bản và mô hình dữ liệu, kiểm tra tài liệu tương ứng và tránh để nhiều chính sách xung đột cùng quản lý một backing index.

## 4. Retention của index khác retention của snapshot

Hai thời hạn này phục vụ hai mục đích khác nhau:

~~~text
Dữ liệu ứng dụng
      |
      v
Index đang hoạt động
      |
      | ILM: rollover / chuyển phase / delete
      v
Index hết hạn được xóa khỏi cluster

Snapshot repository
      ^
      | snapshot định kỳ
      |
Index và metadata tại thời điểm sao lưu
      |
      | SLM: lịch tạo snapshot / retention
      v
Snapshot cũ được giữ hoặc xóa theo policy riêng
~~~

Ví dụ, index log được giữ trực tuyến 90 ngày nhưng snapshot được giữ 30 ngày. Khi ILM xóa index sau 90 ngày, snapshot cũ hơn 30 ngày cũng có thể đã hết hạn. Nếu yêu cầu khôi phục log trong vòng một năm, lịch và retention snapshot phải được thiết kế để đáp ứng yêu cầu đó.

Ngược lại, giữ snapshot trong một năm không làm cho dữ liệu tự xuất hiện trong tìm kiếm trực tuyến. Muốn truy vấn lại, cần restore snapshot thành index hoặc data stream trên cluster phù hợp.

## 5. Snapshot là gì?

Snapshot là bản sao lưu của một hoặc nhiều index, data stream và có thể bao gồm một phần cluster state hoặc feature state tùy lựa chọn. Snapshot được lưu trong snapshot repository được Elasticsearch hỗ trợ.

Snapshot có một số đặc điểm:

- Snapshot là cơ chế backup chính thức của Elasticsearch.
- Snapshot được tạo theo cách incremental: các segment đã có trong repository có thể được tái sử dụng, chỉ dữ liệu mới hoặc thay đổi cần bổ sung.
- Nhiều snapshot có thể chia sẻ dữ liệu segment trong repository.
- Snapshot lưu metadata cần thiết để phục hồi index, bao gồm mapping và settings của index được sao lưu.
- Cluster state toàn cục có thể được đưa vào hoặc loại ra theo tùy chọn.

Snapshot không phải bản sao byte-for-byte của thư mục dữ liệu đang chạy. Không được tự sao chép, sửa hoặc xóa các file nội bộ trong repository bằng công cụ filesystem hay object storage. Hãy dùng API snapshot để quản lý repository và snapshot.

### 5.1. Snapshot khác replica như thế nào?

| Tiêu chí | Replica shard | Snapshot |
|---|---|---|
| Mục đích | Tăng tính sẵn sàng và năng lực đọc trong cluster | Sao lưu để phục hồi sau mất dữ liệu hoặc sự cố |
| Vị trí | Nằm trong cùng Elasticsearch cluster | Nằm trong repository độc lập |
| Khi xóa nhầm index | Không bảo đảm khôi phục được | Có thể restore nếu snapshot còn |
| Khi mất toàn cluster | Có thể mất cả primary và replica | Có thể phục hồi trên cluster khác tương thích |
| Lịch sử | Phản ánh dữ liệu hiện tại của shard | Lưu các trạng thái được snapshot theo thời điểm |

Replica không phải backup. Nếu ứng dụng xóa nhầm document hoặc một thao tác phá hủy lan ra cluster, replica sẽ đồng bộ trạng thái đó. Snapshot tạo ra điểm phục hồi độc lập hơn.

## 6. Snapshot repository

Snapshot repository là nơi Elasticsearch lưu dữ liệu snapshot. Các loại repository thường dùng gồm:

- Shared filesystem (fs).
- Amazon S3.
- Azure Blob Storage.
- Google Cloud Storage.
- Các repository hoặc plugin được hỗ trợ bởi phiên bản và nền tảng đang triển khai.

Repository nên nằm ngoài vòng đời của node dữ liệu. Nếu snapshot chỉ được lưu trên cùng ổ đĩa hoặc cùng máy với cluster, một sự cố vật lý có thể làm mất cả dữ liệu lẫn bản sao lưu.

### 6.1. Ví dụ đăng ký repository filesystem

Với repository loại fs, cần cấu hình path.repo trong elasticsearch.yml trên các node liên quan và bảo đảm đường dẫn được mount, có quyền truy cập nhất quán trên cluster. Sau khi cấu hình và restart node theo yêu cầu, đăng ký repository:

~~~yaml
path.repo: ["/mnt/es-backups"]
~~~

~~~http
PUT /_snapshot/prod-backup
Content-Type: application/json

{
  "type": "fs",
  "settings": {
    "location": "/mnt/es-backups",
    "compress": true
  }
}
~~~

Đường dẫn trong ví dụ phải nằm trong path.repo đã cho phép và phải có thể truy cập từ các node cần thiết. Không dùng một thư mục cục bộ chỉ tồn tại trên một node trong cluster nhiều node.

Với repository cloud, cần cài plugin phù hợp và cấu hình thông tin xác thực qua cơ chế bảo mật được hỗ trợ. Không ghi access key hoặc secret trực tiếp vào source code, file cấu hình được commit hoặc nội dung bài log.

### 6.2. Kiểm tra repository

Sau khi đăng ký, có thể xác minh repository:

~~~http
POST /_snapshot/prod-backup/_verify
~~~

Đọc danh sách repository:

~~~http
GET /_snapshot
~~~

Chỉ nên đưa repository vào lịch backup sau khi xác nhận cluster có thể ghi và đọc repository thành công. Trong môi trường nhiều cluster, cần tuân thủ quy tắc repository: không để nhiều cluster cùng ghi vào một repository. Cluster thứ hai có thể đăng ký repository ở chế độ chỉ đọc nếu cần phục hồi hoặc kiểm tra snapshot.

## 7. Tạo snapshot thủ công

Ví dụ tạo snapshot cho các index log:

~~~http
PUT /_snapshot/prod-backup/logs-snapshot-2025-04-18?wait_for_completion=true
Content-Type: application/json

{
  "indices": "logs-*",
  "ignore_unavailable": true,
  "include_global_state": false,
  "partial": false
}
~~~

Các tùy chọn đáng chú ý:

- indices: chỉ định index hoặc data stream cần sao lưu.
- ignore_unavailable: quyết định có bỏ qua index không tồn tại hoặc không sẵn sàng hay không.
- include_global_state: có đưa global cluster state vào snapshot hay không.
- partial: quyết định có chấp nhận snapshot chỉ chứa một phần shard hay không; với backup thông thường nên tránh chấp nhận snapshot partial nếu mục tiêu là phục hồi đầy đủ.
- wait_for_completion: nếu bật, request chờ đến khi snapshot hoàn tất; với snapshot lớn, có thể tạo bất đồng bộ rồi kiểm tra trạng thái sau.

Snapshot không nên được coi là thành công chỉ vì request đã được gửi. Cần kiểm tra trạng thái cuối cùng và số shard thành công/thất bại.

### 7.1. Kiểm tra trạng thái snapshot

Đọc một snapshot cụ thể:

~~~http
GET /_snapshot/prod-backup/logs-snapshot-2025-04-18
~~~

Xem trạng thái:

~~~http
GET /_snapshot/prod-backup/logs-snapshot-2025-04-18/_status
~~~

Kết quả cần được kiểm tra để bảo đảm snapshot đã hoàn thành, không có shard thất bại ngoài dự kiến và các index cần thiết đều nằm trong snapshot.

## 8. Tự động hóa snapshot bằng Snapshot Lifecycle Management

Snapshot Lifecycle Management (SLM) cho phép định nghĩa lịch tạo snapshot và chính sách dọn snapshot cũ. SLM quản lý vòng đời của snapshot trong repository, còn ILM quản lý vòng đời index trong cluster.

Ví dụ policy tạo snapshot mỗi ngày lúc 01:30 và giữ snapshot theo thời hạn:

~~~http
PUT /_slm/policy/daily-logs-backup
Content-Type: application/json

{
  "schedule": "0 30 1 * * ?",
  "name": "<daily-logs-{now/d}>",
  "repository": "prod-backup",
  "config": {
    "indices": ["logs-*"],
    "ignore_unavailable": true,
    "include_global_state": false,
    "partial": false
  },
  "retention": {
    "expire_after": "30d",
    "min_count": 7,
    "max_count": 50
  }
}
~~~

Ý nghĩa:

- schedule: lịch chạy theo biểu thức cron mà SLM hỗ trợ.
- name: mẫu tên snapshot; phần ngày được tạo theo date math.
- repository: repository đích.
- config.indices: phạm vi dữ liệu được sao lưu.
- retention.expire_after: tuổi tối đa trước khi snapshot đủ điều kiện hết hạn.
- min_count: số snapshot tối thiểu muốn giữ nếu có thể.
- max_count: giới hạn số snapshot cần quản lý.

Retention của SLM có thể cân nhắc cả tuổi snapshot và số lượng tối thiểu/tối đa. Cần thiết kế các giá trị sao cho không xóa mất điểm phục hồi mà tổ chức cần. Một policy không bảo đảm backup thành công chỉ vì đã được khai báo; phải giám sát kết quả từng lần chạy và lỗi repository.

### 8.1. Theo dõi SLM

Đọc policy:

~~~http
GET /_slm/policy/daily-logs-backup
~~~

Kiểm tra trạng thái và thống kê:

~~~http
GET /_slm/status
~~~

Xem lịch sử thực thi:

~~~http
GET /_slm/stats
~~~

Có thể kiểm tra snapshot gần đây trong repository và đối chiếu với lịch dự kiến. Nếu một lần backup thất bại, cần cảnh báo trước khi vượt quá RPO mà hệ thống đã cam kết.

## 9. Restore snapshot

Restore tạo lại index hoặc data stream từ snapshot. Có thể phục hồi về cluster ban đầu sau sự cố hoặc phục hồi sang cluster khác để kiểm thử, điều tra dữ liệu hay chuyển môi trường.

Trước khi restore:

1. Xác nhận repository có thể truy cập và snapshot còn tồn tại.
2. Kiểm tra phiên bản Elasticsearch tạo snapshot và phiên bản cluster đích.
3. Xác định index hoặc data stream cần phục hồi.
4. Kiểm tra tên index đích có đang tồn tại hoặc xung đột alias không.
5. Quyết định có cần khôi phục global state và feature state không.
6. Đánh giá dung lượng, thời gian và tải của cluster đích.

### 9.1. Xem snapshot có những index nào

Liệt kê snapshot:

~~~http
GET /_snapshot/prod-backup/_all
~~~

Có thể xem chi tiết một snapshot để xác định index, trạng thái và metadata được lưu. Chọn đúng snapshot theo thời điểm cần phục hồi; tên snapshot không thay thế việc kiểm tra trạng thái hoàn tất.

### 9.2. Restore một index

Ví dụ restore index log từ snapshot:

~~~http
POST /_snapshot/prod-backup/logs-snapshot-2025-04-18/_restore
Content-Type: application/json

{
  "indices": "logs-000042",
  "ignore_unavailable": true,
  "include_global_state": false,
  "include_aliases": false,
  "rename_pattern": "logs-(.+)",
  "rename_replacement": "restore-logs-$1"
}
~~~

Ví dụ trên đổi tên index được phục hồi thành restore-logs-000042 để tránh ghi đè hoặc xung đột với index hiện tại. Khi dùng rename pattern, hãy bảo đảm tên mới hợp lệ và không trùng index đang tồn tại.

include_aliases false giúp tránh tự động phục hồi alias từ snapshot trong trường hợp alias hiện tại đang được cluster quản lý riêng. Sau khi xác minh index được phục hồi, có thể gắn alias theo kế hoạch. Nếu cần phục hồi alias, hãy kiểm tra trước các xung đột và tác động đến luồng đọc/ghi.

### 9.3. Restore nhiều index hoặc data stream

Trường indices có thể chỉ định nhiều index hoặc pattern. Khi phục hồi data stream, snapshot phải bao gồm data stream và dữ liệu backing index cần thiết; quy trình restore phải tuân theo hướng dẫn của phiên bản Elasticsearch tương ứng.

Không nên restore toàn bộ cluster state một cách máy móc vào cluster đang phục vụ production. Global state có thể chứa metadata như persistent settings, templates, policies và các cấu hình cluster khác. Phục hồi toàn bộ có thể làm thay đổi cấu hình hiện hành. Với tình huống chỉ cần khôi phục dữ liệu index, thường nên loại global state rồi xử lý alias/template/policy riêng.

### 9.4. Theo dõi quá trình restore

Sau khi gửi restore request, theo dõi recovery:

~~~http
GET /_cat/recovery/restore-logs-*?v
~~~

Kiểm tra trạng thái shard:

~~~http
GET /_cluster/health/restore-logs-*
~~~

Có thể đọc mapping và settings của index đã phục hồi:

~~~http
GET /restore-logs-*/_mapping
~~~

~~~http
GET /restore-logs-*/_settings
~~~

Chỉ chuyển alias đọc/ghi sau khi index phục hồi hoàn tất và dữ liệu được xác nhận phù hợp.

## 10. Tương thích phiên bản khi phục hồi

Snapshot gắn với phiên bản Elasticsearch đã tạo nó. Việc restore cần tuân theo quy tắc tương thích phiên bản của Elasticsearch. Nói chung, không thể restore snapshot được tạo bởi phiên bản mới hơn vào cluster cũ hơn; việc phục hồi qua các phiên bản lớn còn có giới hạn và yêu cầu nâng cấp theo lộ trình được hỗ trợ.

Trước khi thực hiện:

- Ghi nhận phiên bản nguồn và đích.
- Kiểm tra hướng dẫn snapshot/restore của đúng phiên bản.
- Xác nhận plugin, analyzer và các tính năng được dùng ở cluster nguồn có sẵn ở cluster đích.
- Thử restore trên môi trường staging hoặc cluster tạm nếu dữ liệu quan trọng.

Không nên giả định snapshot là định dạng trao đổi bất kỳ giữa mọi phiên bản. Với mục tiêu chuyển dữ liệu sang phiên bản không tương thích, có thể cần nâng cấp theo từng bước được hỗ trợ, dùng reindex-from-remote hoặc một quy trình chuyển đổi dữ liệu khác.

## 11. Kiểm thử phục hồi và xác nhận dữ liệu

Một backup chỉ có giá trị khi có thể phục hồi trong thời gian mục tiêu. Vì vậy cần diễn tập restore định kỳ.

Sau khi restore, xác nhận:

1. Snapshot đã hoàn tất và không có shard lỗi ngoài dự kiến.
2. Các index hoặc data stream mong muốn đã xuất hiện.
3. Cluster health và shard allocation đạt trạng thái chấp nhận được.
4. Mapping và settings khớp yêu cầu ứng dụng.
5. Số lượng document và mốc thời gian dữ liệu phù hợp với snapshot.
6. Alias đọc/ghi được gắn đúng index.
7. Các truy vấn nghiệp vụ quan trọng chạy được.
8. Ứng dụng Spring Data Elasticsearch có thể đọc và ghi theo cấu hình dự kiến.
9. Thời gian thực tế để phục hồi đáp ứng RTO.

Nên lưu lại thời điểm snapshot, thời gian restore, dung lượng, số index, số shard và kết quả kiểm tra. Kết quả diễn tập giúp điều chỉnh lịch backup, tài nguyên repository và mục tiêu RTO/RPO.

## 12. Quyền truy cập và bảo vệ bản sao lưu

Snapshot repository thường chứa dữ liệu có giá trị tương đương dữ liệu production. Cần bảo vệ cả đường truy cập lẫn nơi lưu trữ:

- Chỉ cấp quyền tạo, đọc, xóa snapshot cho vai trò cần thiết.
- Bảo vệ repository bằng quyền truy cập ở filesystem hoặc cloud storage.
- Dùng mã hóa khi truyền và khi lưu trữ nếu nền tảng hỗ trợ.
- Quản lý credential qua secret store hoặc cơ chế bảo mật của cluster.
- Giới hạn cluster được phép ghi vào repository.
- Theo dõi dung lượng và lỗi ghi repository.
- Có kế hoạch giữ bản sao ở failure domain khác với cluster nguồn.

Nếu có yêu cầu xóa dữ liệu cá nhân, cần đánh giá cả index đang hoạt động, snapshot còn hiệu lực, bản sao lưu ngoài cluster và quy trình hết hạn. Xóa document khỏi index không tự loại bỏ document đó khỏi snapshot đã tạo trước đó. Không nên cam kết xóa hoàn toàn chỉ dựa trên một thao tác delete trong Elasticsearch.

## 13. Kết hợp lifecycle với ứng dụng Spring Data Elasticsearch

Spring Data Elasticsearch tập trung vào ánh xạ entity và thao tác document. Retention, rollover và snapshot thường thuộc lớp vận hành Elasticsearch, được quản lý bằng index template, ILM, SLM, data stream lifecycle hoặc API quản trị tương ứng.

Ứng dụng nên sử dụng alias hoặc data stream làm tên đích ổn định nếu kiến trúc yêu cầu rollover. Ví dụ:

~~~java
@Document(indexName = "logs-write", createIndex = false)
public class LogEvent {

    @Id
    private String id;

    @Field(name = "@timestamp", type = FieldType.Date)
    private Instant timestamp;

    @Field(type = FieldType.Keyword)
    private String level;

    @Field(type = FieldType.Text)
    private String message;

    // constructors, getters and setters
}
~~~

Ở đây logs-write là alias được tạo và quản lý bởi quy trình provisioning. createIndex = false tránh repository bootstrap tự tạo một index vật lý cùng tên alias nếu alias chưa tồn tại. ILM chịu trách nhiệm rollover và xóa index theo policy; SLM chịu trách nhiệm snapshot và retention của snapshot.

Không nên để từng instance Spring Boot tự tạo, xóa hoặc thay đổi policy lifecycle khi khởi động. Các thay đổi vận hành nên được quản lý tập trung qua pipeline triển khai hoặc công cụ quản trị có kiểm soát. Điều này tránh race condition và bảo đảm các môi trường áp dụng cùng cấu hình.

### 13.1. Ghi qua alias

Repository sử dụng entity metadata và alias làm đích:

~~~java
public interface LogEventRepository
        extends ElasticsearchRepository<LogEvent, String> {
}
~~~

Khi gọi save, Spring Data dùng indexName được khai báo trên @Document. Elasticsearch định tuyến request ghi qua write alias đến index hiện hành. Khi ILM rollover, alias được cập nhật và ứng dụng tiếp tục ghi theo cùng tên logic.

Với truy vấn đọc, hãy xác định alias hoặc index pattern bao phủ đúng thời hạn dữ liệu cần tìm. Một write alias thường chỉ trỏ đến write index; không nên giả định nó cũng là alias đọc toàn bộ lịch sử.

## 14. Thiết kế retention và backup cho từng loại dữ liệu

Không nên áp dụng một policy chung cho tất cả index. Một cách phân loại tham khảo:

| Loại dữ liệu | Retention trực tuyến | Snapshot/backup cần cân nhắc |
|---|---|---|
| Log vận hành | Ngắn đến trung hạn, theo nhu cầu điều tra | Snapshot định kỳ nếu cần điều tra sự cố hoặc tuân thủ |
| Audit event | Theo chính sách kiểm toán và pháp lý | Snapshot dài hạn, quyền truy cập nghiêm ngặt và kiểm thử phục hồi |
| Telemetry | Theo nhu cầu giám sát và phân tích xu hướng | Backup chọn lọc hoặc kho lưu trữ dài hạn |
| Nội dung tìm kiếm được tái tạo từ database | Có thể giữ theo nhu cầu tìm kiếm | Có thể tái lập index từ nguồn chính, nhưng vẫn cần đánh giá thời gian rebuild |
| Dữ liệu không thể tái tạo | Theo hợp đồng dữ liệu | Snapshot và diễn tập restore có ưu tiên cao |

Nếu Elasticsearch chỉ là read model có thể tái tạo từ cơ sở dữ liệu chính, snapshot có thể phục vụ phục hồi nhanh thay vì là nguồn lưu trữ duy nhất. Cần xác định thời gian tái lập index, khả năng phát lại event và mức mất dữ liệu có thể chấp nhận. Nếu dữ liệu chỉ tồn tại trong Elasticsearch, yêu cầu backup cần nghiêm ngặt hơn.

## 15. Những lỗi thường gặp

### 15.1. Coi replica là backup

Replica nằm trong cùng cluster và đồng bộ thay đổi với primary. Xóa nhầm hoặc lỗi logic có thể lan sang replica. Cần snapshot repository độc lập.

### 15.2. Chỉ cấu hình ILM mà quên snapshot

ILM có thể xóa index theo policy. Nếu dữ liệu cần phục hồi sau thời điểm xóa, phải có snapshot còn hiệu lực hoặc nguồn dữ liệu khác để tái tạo.

### 15.3. Chỉ tạo snapshot mà không kiểm tra kết quả

Request tạo snapshot không đồng nghĩa snapshot hoàn tất thành công. Cần kiểm tra trạng thái, shard failed và cảnh báo khi lịch chạy thất bại.

### 15.4. Không thử restore

Repository có thể mất quyền truy cập, snapshot có thể không tương thích phiên bản hoặc thời gian phục hồi có thể vượt RTO. Diễn tập restore là cách xác nhận backup có thể sử dụng.

### 15.5. Để repository cùng failure domain

Nếu repository nằm trên cùng ổ đĩa hoặc hạ tầng có thể hỏng cùng cluster, sự cố có thể phá hủy cả dữ liệu gốc và bản sao lưu. Nên dùng nơi lưu trữ độc lập và có chính sách bảo vệ riêng.

### 15.6. Xóa index thủ công trong khi ILM đang quản lý

Xóa index ngoài policy có thể làm alias, trạng thái lifecycle và kế hoạch phục hồi không nhất quán. Hãy xác định index thuộc policy nào và dùng thao tác có kiểm soát.

### 15.7. Restore đè lên index hoặc alias production

Restore có thể thất bại do tên đã tồn tại hoặc gây thay đổi luồng đọc/ghi nếu alias được phục hồi. Hãy restore sang tên tạm, xác minh rồi mới chuyển alias.

### 15.8. Giữ snapshot vô hạn

Snapshot incremental vẫn cần metadata và dung lượng segment. Giữ snapshot vô hạn có thể làm repository tăng liên tục. Cần SLM retention rõ ràng và theo dõi dung lượng.

## 16. Quy trình vận hành mẫu

Một quy trình có thể triển khai theo thứ tự:

1. Phân loại dữ liệu và xác định thời hạn retention trực tuyến.
2. Thiết kế index hoặc data stream, alias đọc/ghi và quy tắc rollover.
3. Tạo index template và ILM policy phù hợp.
4. Tạo snapshot repository độc lập, xác minh quyền truy cập.
5. Thiết lập SLM policy theo RPO và retention backup.
6. Giám sát trạng thái ILM, SLM, repository, dung lượng và lỗi snapshot.
7. Định kỳ restore sang môi trường kiểm thử hoặc index có tên tạm.
8. Kiểm tra mapping, settings, document count, truy vấn và alias sau restore.
9. Đo thời gian phục hồi và cập nhật RTO/RPO nếu thực tế khác mục tiêu.
10. Rà soát retention khi yêu cầu nghiệp vụ, pháp lý hoặc chi phí thay đổi.

Các lệnh kiểm tra thường dùng:

~~~http
GET /_ilm/policy
GET /logs-*/_ilm/explain
GET /_alias/logs-read,logs-write
GET /_snapshot
GET /_snapshot/prod-backup/_all
GET /_slm/policy
GET /_slm/status
GET /_slm/stats
~~~

Kết quả nên được giám sát bằng cảnh báo, không chỉ kiểm tra thủ công khi có sự cố.

## 17. Kết luận

Chính sách lưu giữ quyết định dữ liệu tìm kiếm được giữ trực tuyến bao lâu; ILM hoặc lifecycle phù hợp quản lý rollover, chuyển phase và xóa index. Snapshot tạo điểm phục hồi độc lập trong repository, còn SLM quản lý lịch tạo và retention của các bản sao lưu.

Alias giúp ứng dụng Spring Data Elasticsearch tiếp tục dùng tên logic ổn định khi index vật lý được rollover hoặc phục hồi. Ứng dụng nên tập trung vào đọc/ghi document; pipeline triển khai hoặc lớp vận hành quản lý index template, lifecycle policy và snapshot policy.

Một chiến lược backup chỉ hoàn chỉnh khi snapshot được kiểm tra và restore được diễn tập. Hãy thiết kế retention, lịch snapshot, repository độc lập, quyền truy cập và quy trình phục hồi theo RPO/RTO thực tế. Luôn xác minh index, mapping, settings và alias sau restore trước khi đưa dữ liệu trở lại phục vụ người dùng.

# Tạo event rules và lựa chọn event actions

Trong chương **API, sự kiện và tích hợp** của Oracle Cloud Infrastructure (OCI), event rule là cầu nối giữa một thay đổi trên tài nguyên và phản ứng tự động của hệ thống. Ví dụ, khi một tệp CSV xuất hiện trong Object Storage, bạn có thể thông báo cho nhóm vận hành, gọi một Function để kiểm tra dữ liệu hoặc đưa sự kiện vào Streaming để một ứng dụng xử lý sau.

Bài học tập trung vào cách xác định phạm vi rule, viết điều kiện khớp sự kiện và chọn action phù hợp. Các quyết định được đặt trong bối cảnh tenancy, compartment, IAM, giám sát, tính sẵn sàng và chi phí của hạ tầng OCI.

Sau bài học, bạn có thể:

- Chuyển một yêu cầu vận hành thành bộ ba: sự kiện nguồn, điều kiện lọc và đích nhận.
- Tạo rule bằng Console hoặc OCI CLI với phạm vi compartment rõ ràng.
- Phân biệt Notifications, Functions và Streaming khi chọn action.
- Kiểm tra riêng việc khớp rule, giao sự kiện và hoàn thành xử lý nghiệp vụ.
- Thiết kế phản ứng chịu được sự kiện trùng, lỗi ở đích và thay đổi cấu hình.

## 1. Hiểu đúng quan hệ giữa event, rule và action

Một **event** là thông điệp mô tả thay đổi do dịch vụ OCI phát ra. **Event type** cho biết loại thay đổi, chẳng hạn tạo object. **Rule** chứa điều kiện lọc và danh sách action. **Action** chỉ định tài nguyên đích nhận sự kiện khớp rule.

Events hỗ trợ ba loại đích trực tiếp: Notifications topic, Streaming stream và Function. Khi một sự kiện khớp, dịch vụ giao thông điệp cho các đích được cấu hình; công việc tiếp theo thuộc trách nhiệm của dịch vụ hoặc ứng dụng nhận. [Nguồn: Overview of Events](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm).

~~~mermaid
flowchart LR
    S["Tài nguyên phát sự kiện"] --> E["OCI Events"]
    E --> R{"Rule bật và condition khớp?"}
    R -->|Có| N["Notifications topic"]
    R -->|Có| F["Function"]
    R -->|Có| T["Streaming stream"]
    R -->|Không| X["Không chạy action của rule này"]
    N --> U["Người hoặc subscriber nhận tin"]
    F --> B["Xử lý nghiệp vụ"]
    T --> C["Consumer xử lý bất đồng bộ"]
~~~

Sơ đồ minh họa các lựa chọn. Một rule chỉ cần những action phục vụ yêu cầu thực tế, không cần cấu hình cả ba.

### 1.1. Phạm vi compartment quyết định rule nhìn thấy gì

Rule áp dụng cho sự kiện từ tài nguyên trong compartment chứa rule và các compartment con. Vì vậy:

- Rule đặt trong `EventLab` có thể theo dõi tài nguyên của `EventLab` và các nhánh con.
- Rule đặt trong một nhánh con không tự theo dõi tài nguyên của compartment cha hay nhánh anh em.
- Nếu chỉ muốn một compartment cụ thể, có thể thêm `data.compartmentId` vào condition để thu hẹp phạm vi.
- Đích action có thể nằm trong compartment khác với rule; quyền truy cập đích phải phù hợp.

Mỗi rule phải có ít nhất một action; tài liệu quản lý rule nêu tối đa 10 action trên một rule. Đây là giới hạn cấu hình, không phải lý do để thêm nhiều action khi chưa cần. [Nguồn: Managing Rules for Events](https://docs.oracle.com/en-us/iaas/Content/Events/Task/managingrules.htm).

Khi triển khai, ghi rõ cả **region** và compartment của nguồn, rule, đích. Bài thực hành sử dụng một region duy nhất để dễ kiểm tra. Không mặc định một rule đã tạo sẽ tự bao phủ các region khác.

### 1.2. Phân biệt ba kết quả thường bị đánh đồng

| Kết quả | Điều đã được chứng minh | Điều còn phải kiểm tra |
| --- | --- | --- |
| Rule được tạo thành công | Cấu hình được dịch vụ chấp nhận | Nguồn có phát event và condition có khớp hay không |
| Event được giao tới action | Đích nhận đã chấp nhận thông điệp theo cơ chế giao nhận | Subscriber, Function hoặc consumer có hoàn thành công việc hay không |
| Nghiệp vụ hoàn thành | Đầu ra mong muốn đã xuất hiện | Có bị xử lý trùng hoặc bỏ sót trong các tình huống lỗi hay không |

Một email đến nơi không chứng minh Function cùng rule đã thành công. Tương tự, giao thành công vào stream không chứng minh consumer đã cập nhật cơ sở dữ liệu.

## 2. Đọc thông điệp nguồn trước khi viết condition

Không nên bắt đầu bằng suy đoán tên field. Hãy xác định event type trong danh mục của dịch vụ nguồn và đọc payload mẫu tương ứng.

Dưới đây là thông điệp **minh họa** dựa trên cấu trúc sự kiện tạo object. Các định danh đã được thay bằng giá trị giả; đây không phải dữ liệu thu từ tenancy thật.

~~~json
{
  "cloudEventsVersion": "0.1",
  "eventID": "example-event-invoice-001",
  "eventType": "com.oraclecloud.objectstorage.createobject",
  "source": "objectstorage",
  "eventTypeVersion": "2.0",
  "eventTime": "2026-11-20T03:00:00Z",
  "contentType": "application/json",
  "extensions": {
    "compartmentId": "<SOURCE_COMPARTMENT_OCID>"
  },
  "data": {
    "compartmentId": "<SOURCE_COMPARTMENT_OCID>",
    "compartmentName": "EventLab",
    "resourceName": "incoming/invoice-001.csv",
    "resourceId": "",
    "availabilityDomain": "all",
    "additionalDetails": {
      "namespace": "training_namespace",
      "bucketName": "oci-event-lab-input",
      "bucketId": "<BUCKET_OCID>",
      "eTag": "example-etag-001"
    }
  }
}
~~~

Với object event, `data.resourceName` biểu diễn tên object; tên bucket nằm trong `data.additionalDetails.bucketName`. Không lấy cấu trúc của bucket event để suy ra cấu trúc của object event. Danh mục OCI cũng phân biệt `createobject`, `updateobject` và `deleteobject`. [Nguồn: Services that Produce Events, phần Object Storage](https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventsproducers.htm#ObjectStorage).

Các trường cần quan tâm trong bài:

| Field | Vai trò trong thiết kế |
| --- | --- |
| `eventID` | Tương quan log và hỗ trợ nhận diện sự kiện đã xử lý |
| `eventType` | Chọn đúng loại thay đổi cần phản ứng |
| `eventTime` | Thời điểm của sự kiện, hỗ trợ điều tra độ trễ |
| `data.compartmentId` | Khoanh phạm vi tài nguyên nguồn |
| `data.resourceName` | Lọc tài nguyên hoặc tên object theo yêu cầu |
| `data.additionalDetails` | Chứa thông tin riêng của dịch vụ nguồn |

Payload phụ thuộc dịch vụ và event type. Không giả định mọi event đều có `bucketName`, tag hay một `resourceId` không rỗng. Ví dụ trên giữ `resourceId` rỗng như một tình huống mà bộ xử lý cần chấp nhận, thay vì dùng field này làm khóa duy nhất cho mọi loại sự kiện. [Nguồn: Contents of an Event Message](https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventenvelopereference.htm).

`cloudEventsVersion` trong ví dụ phản ánh mẫu OCI đang dùng để minh họa; không tự đổi tên envelope sang schema khác trong khi viết rule. Luôn dựa vào message mà nguồn thực tế phát ra.

## 3. Chuyển yêu cầu thành điều kiện lọc

Giả sử yêu cầu là:

> Khi có object mới dưới tiền tố `incoming/`, đuôi `.csv`, trong bucket `oci-event-lab-input` thuộc compartment nguồn đã chọn, gửi thông báo cho nhóm vận hành.

Condition tương ứng:

~~~json
{
  "eventType": [
    "com.oraclecloud.objectstorage.createobject"
  ],
  "data": {
    "compartmentId": "<SOURCE_COMPARTMENT_OCID>",
    "resourceName": "incoming/*.csv",
    "additionalDetails": {
      "bucketName": "oci-event-lab-input"
    }
  }
}
~~~

Thay `<SOURCE_COMPARTMENT_OCID>` bằng OCID thực trước khi triển khai. Đây là **nội dung condition**, chưa phải toàn bộ đối tượng rule.

### 3.1. Quy tắc kết hợp điều kiện

Các field được khai báo phải cùng khớp; các giá trị trong một mảng là những lựa chọn thay thế. Field không xuất hiện trong condition không tham gia lọc. Cấu trúc lồng nhau phải giống thông điệp gốc.

Trong ví dụ, event phải đúng loại, compartment, tên object và bucket. OCI hỗ trợ wildcard `*`; nó không biến condition thành biểu thức chính quy. Một condition `{}` khớp mọi sự kiện trong phạm vi compartment của rule. [Nguồn: Matching Events with Filters](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/filterevents.htm).

Đọc condition trên thành câu giúp phát hiện sai yêu cầu: “Loại tạo object **và** đúng compartment **và** tên khớp `incoming/*.csv` **và** đúng bucket”.

Nếu nghiệp vụ chấp nhận cả tạo và cập nhật object, chỉ thay phần event type:

~~~json
{
  "eventType": [
    "com.oraclecloud.objectstorage.createobject",
    "com.oraclecloud.objectstorage.updateobject"
  ]
}
~~~

Đây là một mảnh condition để giải thích mảng, không phải cấu hình thay thế toàn bộ bộ lọc của bài thực hành. Khi áp dụng, giữ lại các ràng buộc compartment, bucket và tên object cần thiết.

Đối với thao tác ghi đè, sao chép hoặc multipart upload, hãy quan sát event thực tế của thao tác trước khi quyết định chọn loại nào. Tên thao tác trong ứng dụng không đủ để suy ra chắc chắn event type.

### 3.2. Những lỗi thiết kế dễ gặp

| Cách làm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt `bucketName` ngay dưới `data` | Không khớp cấu trúc object event | Đặt dưới `data.additionalDetails` |
| Dùng `resourceName` bằng tên bucket cho object event | Object hợp lệ bị loại | Dùng tên object tại field này |
| Đưa cú pháp `$.data.resourceName` vào tên field | Nhầm condition với JSONPath | Dùng JSON lồng nhau đúng schema |
| Dùng `incoming/.*\.csv` như regex | Pattern không có ý nghĩa regex mong muốn | Dùng wildcard được hỗ trợ và thử với mẫu |
| Lọc theo tag chưa có trong payload | Có thể không khớp dù tài nguyên được gắn tag ở nơi khác | Kiểm tra event nguồn thực sự chứa tag |
| Dùng tên compartment làm định danh lâu dài | Đổi tên có thể ảnh hưởng bộ lọc | Ưu tiên OCID khi cần định danh chính xác |
| Dùng `{}` ở phạm vi rộng để xử lý tự động | Nhiều sự kiện ngoài dự kiến đi tới đích | Bắt đầu bằng event type và phạm vi hẹp |

Đừng nhập các toán tử quen thuộc của công cụ khác như `$or`, `exists` hoặc biểu thức SQL nếu tài liệu OCI Events không quy định chúng. Nếu điều kiện nghiệp vụ cần đọc nội dung CSV, so sánh nhiều bản ghi hoặc gọi hệ thống khác, chuyển phần đó sang bộ xử lý.

### 3.3. Tag của rule và tag dùng để lọc nguồn

Tag gắn lên **rule** phục vụ tổ chức tài nguyên rule. Điều kiện như `data.definedTags` hoặc `data.freeFormTags` lại kiểm tra **thông điệp nguồn**.

Ví dụ, gắn tag `Environment=prod` cho rule không tự khiến rule chỉ nhận event từ tài nguyên production. Muốn có hành vi đó, condition phải tham chiếu đúng tag được nguồn phát ra. Thiết kế cần quy định ai được sửa tag nguồn, vì thay đổi tag có thể làm thay đổi phạm vi tự động hóa.

## 4. Chọn action theo người nhận và cách xử lý

Ba action có cùng điểm xuất phát là event khớp, nhưng phục vụ nhu cầu khác nhau.

| Tiêu chí | Notifications | Functions | Streaming |
| --- | --- | --- | --- |
| Nhu cầu điển hình | Thông báo cho người hoặc subscriber | Thực thi logic tùy chỉnh | Đưa thông điệp vào luồng cho consumer |
| Tài nguyên đích | Topic | Function đã triển khai | Stream |
| Thành phần phải chuẩn bị | Topic và subscription phù hợp | Function, cấu hình, quyền và kết nối cần thiết | Stream và ứng dụng consumer |
| Công việc tiếp theo | Subscriber nhận, diễn giải hoặc chuyển tiếp | Code kiểm tra, biến đổi hay gọi API | Consumer đọc, xử lý và theo dõi tiến độ |
| Điểm cần giám sát thêm | Trạng thái subscription và kết quả nhận | Log, lỗi, thời gian chạy, đầu ra | Độ trễ consumer, lỗi xử lý, khả năng đọc lại |
| Chi phí cần đánh giá | Kênh thông báo và lượng gửi | Lượt gọi, tài nguyên thực thi và dịch vụ được gọi | Dung lượng/thông lượng, lưu giữ và consumer |

Các nhận định lựa chọn dưới đây là khuyến nghị thiết kế cho tình huống bài học; chúng không bổ sung loại action mới cho dịch vụ Events.

### 4.1. Notifications: khi phản ứng chính là thông báo

Chọn Notifications nếu nhóm vận hành cần nhận tin về một thay đổi, ví dụ có tệp mới cần theo dõi hoặc một thao tác trên cơ sở dữ liệu vừa kết thúc.

Đích của rule là **topic**, không phải địa chỉ email. Với email subscription, cần hoàn tất xác nhận nhận qua email trước khi kỳ vọng nhận thông báo vận hành. [Nguồn: Getting Started with Events](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsgetstarted.htm).

Một email từ event tạo tệp chỉ chứng minh tệp đã được nguồn báo tạo. Nếu cần thông báo “dữ liệu đã kiểm tra hợp lệ”, hãy gửi thông báo sau bước kiểm tra nghiệp vụ.

Tránh dùng cùng một hộp thư cho toàn bộ event lưu lượng lớn. Chọn các thay đổi cần con người hành động và quy định người chịu trách nhiệm nhận.

### 4.2. Functions: khi cần thực thi logic

Chọn Functions khi cần đọc metadata, kiểm tra object, chuyển đổi thông điệp hoặc gọi API đích.

Ví dụ thiết kế:

1. Nhận event về object mới.
2. Kiểm tra `eventType` và bucket được phép.
3. Dùng danh tính của Function để đọc object.
4. Kiểm tra cấu trúc dữ liệu.
5. Ghi kết quả xử lý với khóa chống trùng.
6. Gửi thông báo kết quả hoặc gọi bước tiếp theo.

Đây là luồng nghiệp vụ do bạn xây dựng. Rule không tự cung cấp các bước đó.

Nếu Function chạy trong VCN, phải thiết kế đường mạng tới Object Storage, cơ sở dữ liệu hoặc API mà code sử dụng. Việc rule gọi được Function không chứng minh Function có quyền hay đường mạng để truy cập các tài nguyên tiếp theo.

Không nhúng mật khẩu cơ sở dữ liệu hoặc khóa truy cập trong condition và mô tả action. Dùng cơ chế danh tính và quản lý bí mật phù hợp với ứng dụng.

### 4.3. Streaming: khi cần tách thời điểm tiếp nhận và xử lý

Chọn Streaming nếu ứng dụng cần tiêu thụ sự kiện theo tốc độ riêng hoặc nhiều nhóm cần xử lý độc lập.

Ví dụ, một consumer cập nhật danh mục tệp, còn consumer khác tính số lượng tệp đã đến. Với thiết kế này, cần quy định thời gian lưu giữ phù hợp, cách quản lý tiến độ và cách phục hồi consumer.

Khả năng đọc lại từ stream phụ thuộc cấu hình lưu giữ và trạng thái dữ liệu của stream. Nó không có nghĩa Events tự lưu toàn bộ lịch sử để phát lại bất kỳ lúc nào.

Nếu nghiệp vụ yêu cầu thứ tự trên từng đối tượng, hãy thiết kế khóa, phân vùng và cơ chế kiểm tra phiên bản ở consumer. Không suy ra thứ tự toàn cục chỉ vì mọi event được đưa vào một stream.

### 4.4. Nhiều action là phân phối, không phải workflow tuần tự

Một rule có thể giao cùng sự kiện tới nhiều đích. Tuy nhiên, không nên diễn giải thứ tự các phần tử action thành “Function chạy xong rồi email mới được gửi”.

Nếu cấu hình đồng thời Function và Notifications, email nói về **event nguồn**. Muốn email phản ánh **kết quả Function**, để Function hoặc bước điều phối gửi sau khi công việc đạt trạng thái cần thông báo.

Cũng không giả định các action có một giao dịch chung: đích A có thể nhận trong lúc đích B gặp lỗi. Thiết kế xử lý lỗi và quan sát riêng từng nhánh.

API Gateway, cơ sở dữ liệu và một URL HTTP tùy ý không phải ba loại action trực tiếp nêu trên. Khi cần tích hợp các đích này, chọn thành phần trung gian phù hợp, chẳng hạn Function thực hiện lời gọi có xác thực.

## 5. Chuẩn bị IAM trước khi tạo rule

Cần phân biệt các lớp quyền:

| Chủ thể | Quyền cần xem xét |
| --- | --- |
| Người hoặc pipeline tạo rule | Quản lý rule trong compartment được giao |
| Người chọn đích action | Xem hoặc sử dụng topic, Function, stream tương ứng |
| Code chạy trong Function | Truy cập object, secret, cơ sở dữ liệu hoặc API theo nghiệp vụ |
| Consumer của stream | Đọc stream và ghi đầu ra được phép |

Ví dụ dưới đây giả sử nhóm `OciEventAuthors`, compartment `EventLab` và `IntegrationTargets` đã tồn tại:

~~~text
Allow group OciEventAuthors to manage cloudevents-rules in compartment EventLab
Allow group OciEventAuthors to use ons-topic in compartment IntegrationTargets
Allow group OciEventAuthors to inspect compartments in tenancy
~~~

Đây là ví dụ giới hạn phạm vi cho người quản lý rule dùng topic đã có. Nó không cấp đầy đủ quyền để tạo mọi tài nguyên của bài thực hành; quyền tạo bucket, topic, subscription, Function hoặc stream cần được xét riêng.

Trong tenancy dùng identity domain, tham chiếu nhóm phải tuân theo cú pháp domain/group của tenancy. Thay các tên mẫu bằng tên thực và đặt policy tại phạm vi có thẩm quyền với các compartment liên quan. [Nguồn: Events and IAM Policies](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventspolicy.htm).

Đối với rule, resource type IAM là `cloudevents-rules`. Quyền đọc và quyền quản lý khác nhau; không cần cấp `manage` cho người chỉ quan sát cấu hình. [Nguồn: Details for the Events Service](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/cloudeventspolicyreference.htm).

Nếu chọn Functions hoặc Streaming, tra quyền cho đúng loại đích thay vì tiếp tục dùng policy dành cho Notifications. Quyền quản lý rule không thay thế quyền nghiệp vụ của Function.

Bài này dùng cùng một tenancy. Giao sự kiện sang tenancy khác là bài toán phân quyền riêng, cần cấu hình hai phía theo tài liệu cross-tenancy; không thể giải quyết chỉ bằng đổi OCID của action.

## 6. Thực hành tạo rule bằng Console

### 6.1. Mô hình thực hành

| Thành phần | Giá trị minh họa |
| --- | --- |
| Region | `ap-singapore-1` |
| Compartment nguồn và rule | `EventLab` |
| Bucket nguồn | `oci-event-lab-input` |
| Object hợp lệ | `incoming/invoice-001.csv` |
| Đích đầu tiên | Notifications topic `event-lab-notifications` |
| Tên rule | `event-lab-csv-created-notify` |

Tên và region trên là lựa chọn cho lab. Nếu dùng region khác, áp dụng nhất quán trong Console và CLI. Tên bucket thực tế phải phù hợp namespace của bạn.

Bắt đầu với Notifications giúp quan sát đường đi của sự kiện mà chưa cần viết code xử lý. Sau khi đường đi hoạt động, có thể thay hoặc bổ sung action theo yêu cầu.

### 6.2. Chuẩn bị nguồn và đích

1. Chọn region thực hành.
2. Tạo hoặc xác định bucket nguồn trong `EventLab`.
3. Bật **Emit object events** cho bucket.
4. Chuẩn bị Notifications topic.
5. Tạo email subscription và hoàn tất xác nhận.
6. Kiểm tra quyền của người thực hành với rule và topic.

Object events không được phát mặc định. Nếu quên bật cấu hình trên bucket, một condition đúng vẫn không nhận được sự kiện tạo object. Có thể bật từ trang bucket hoặc bằng CLI. [Nguồn: Managing Emitting Events for Object State Changes](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingbuckets_topic-To_enable_or_disable_emitting_events_for_object_state_changes.htm).

### 6.3. Khai báo rule

Mở **Events Service → Rules**, chọn compartment chứa rule rồi tạo rule mới.

Điền tên, mô tả và điều kiện:

- Event type: Object Storage, loại tạo object.
- Thuộc tính compartment nguồn: OCID thực của `EventLab`.
- Tên object: `incoming/*.csv`.
- Tên bucket: `oci-event-lab-input`.

Dùng trình chỉnh sửa condition nếu cần để đối chiếu chính xác JSON ở mục 3. Với action, chọn **Notifications**, compartment chứa topic và topic đã chuẩn bị.

Console cũng cho phép chọn Streaming bằng stream đích hoặc Functions bằng application rồi Function đích. Các tài nguyên phải có sẵn để được chọn. [Nguồn: Creating an Events Rule](https://docs.oracle.com/en-us/iaas/Content/Events/Task/create-events-rule.htm).

Phần mô tả nên nêu rõ mục đích, chẳng hạn: “Thông báo khi có CSV mới dưới incoming trong bucket thực hành”. Tránh mô tả gây hiểu nhầm rằng dữ liệu đã được kiểm tra thành công.

### 6.4. Dùng mẫu để kiểm tra condition

Dùng chức năng kiểm tra sự kiện mẫu với rule, được tài liệu Console mô tả là **Check if Example Event Matches Rule** hoặc **Validate**.

Dán event minh họa ở mục 2 sau khi thay compartment bằng giá trị thực. Kiểm tra thêm các biến thể:

| Biến thể mẫu | Kết quả cần có |
| --- | --- |
| Đúng event type, compartment, bucket, tên CSV | Khớp |
| Tên là `incoming/readme.txt` | Không khớp |
| Tên là `processed/invoice-001.csv` | Không khớp |
| Bucket khác | Không khớp |
| Compartment khác | Không khớp |
| Event type là `deleteobject` | Không khớp |
| Không có `data.additionalDetails.bucketName` | Không khớp |

Nếu dùng rule ở compartment cha nhưng condition giới hạn compartment con A, event của compartment con B vẫn phải bị loại.

Kiểm tra bằng mẫu chỉ đánh giá điều kiện lọc. Nó không chứng minh nguồn đã bật event, quyền giao nhận phù hợp hoặc email đã đến. Sau khi tạo rule, kiểm tra trạng thái bật của cả rule lẫn action trước khi thử đầu cuối.

## 7. Thực hành tương đương bằng OCI CLI

Các lệnh trong mục này dùng **Bash trên OCI Cloud Shell**, không phải cú pháp PowerShell. Chúng là hướng dẫn để người học chạy trong tenancy thực hành; các OCID nằm trong dấu `<...>` phải được thay bằng giá trị thật.

Người học cần OCI CLI đã được xác thực, tài nguyên nguồn/đích và các quyền đã chuẩn bị. Không đưa khóa riêng hoặc token vào các file cấu hình minh họa.

### 7.1. Chuẩn bị condition và actions

Lưu condition ở mục 3 thành `condition.json`, thay OCID compartment. Không thêm lớp bao ngoài mang tên `condition` vào file này.

Tạo `actions.json` với một Notifications action:

~~~json
{
  "actions": [
    {
      "actionType": "ONS",
      "description": "Thong bao object CSV moi trong bucket thuc hanh",
      "isEnabled": true,
      "topicId": "<TOPIC_OCID>"
    }
  ]
}
~~~

Tên thuộc tính đầu vào sử dụng camelCase, chẳng hạn `actionType` và `topicId`. Không sao chép nguyên tên có dấu gạch nối từ JSON kết quả của CLI để làm đầu vào.

Khi cần loại đích khác, dùng thuộc tính tương ứng:

| Loại action trong đầu vào | Trường OCID đích | Dịch vụ |
| --- | --- | --- |
| `ONS` | `topicId` | Notifications |
| `FAAS` | `functionId` | Functions |
| `OSS` | `streamId` | Streaming |

`OSS` ở đây là mã action cho Streaming, không phải mã action Object Storage. Cấu trúc action được Oracle minh họa trong hướng dẫn khởi động Events. [Nguồn: Getting Started with Events, phần CLI](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsgetstarted.htm#usingcli).

Ví dụ một action Function để thay phần tử bên trong mảng `actions`:

~~~json
{
  "actionType": "FAAS",
  "description": "Kiem tra du lieu object moi",
  "isEnabled": true,
  "functionId": "<FUNCTION_OCID>"
}
~~~

Nếu bổ sung nhiều action, giữ chúng thành các phần tử của cùng mảng. Chỉ thêm đích đã triển khai, có người vận hành và có mục đích rõ ràng.

### 7.2. Tạo rule ở trạng thái tắt

Trong thư mục chứa hai file JSON:

~~~bash
REGION='ap-singapore-1'
RULE_COMPARTMENT_ID='<SOURCE_COMPARTMENT_OCID>'

RULE_ID=$(oci events rule create \
  --region "$REGION" \
  --compartment-id "$RULE_COMPARTMENT_ID" \
  --display-name 'event-lab-csv-created-notify' \
  --description 'Notify on incoming CSV object creation in the lab bucket' \
  --condition "$(cat condition.json)" \
  --actions file://actions.json \
  --is-enabled false \
  --wait-for-state ACTIVE \
  --query 'data.id' \
  --raw-output)

printf '%s\n' "$RULE_ID"
~~~

CLI nhận `--condition` dưới dạng chuỗi JSON và `--actions` dưới dạng đối tượng JSON phức hợp; `file://` dùng để đọc đầu vào action từ file. Lệnh sử dụng `cat` để truyền nội dung condition thành một đối số. [Nguồn: OCI CLI — events rule create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/events/rule/create.html).

Kiểm tra lệnh đã thành công và `RULE_ID` là OCID hợp lệ trước khi tiếp tục. Không chạy lại lệnh create một cách mù quáng sau lỗi mạng: kiểm tra danh sách rule trước để tránh tạo rule trùng.

Việc chờ lifecycle state `ACTIVE` không đồng nghĩa rule đã bật. Trong lệnh này, rule tồn tại ở trạng thái lifecycle hoạt động nhưng `isEnabled` vẫn là `false`.

### 7.3. Đọc lại cấu hình và bật rule

~~~bash
oci events rule get \
  --region "$REGION" \
  --rule-id "$RULE_ID"
~~~

Đối chiếu:

- Đúng compartment và tên rule.
- Condition chứa đúng event type, OCID compartment và bucket.
- Topic ID trỏ tới đích thực hành.
- Action đang bật.
- Rule đang tắt như dự kiến ở bước tạo.

Sau khi xác nhận cấu hình và kiểm tra condition bằng mẫu trong Console, bật rule:

~~~bash
oci events rule update \
  --region "$REGION" \
  --rule-id "$RULE_ID" \
  --is-enabled true \
  --wait-for-state ACTIVE
~~~

CLI cung cấp thao tác update để đổi trạng thái bật. Sau các thay đổi, đọc lại rule thay vì chỉ dựa vào việc câu lệnh không báo lỗi. [Nguồn: OCI CLI — events rule update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/events/rule/update.html).

Nếu sửa danh sách actions, kiểm tra ý nghĩa cập nhật của tham số và giữ đầy đủ các action còn cần dùng. Không giả định gửi một phần tử mới sẽ tự nối thêm mà giữ nguyên mọi phần tử cũ.

### 7.4. Bật nguồn phát và tạo sự kiện thật

Đặt namespace thực và bucket đã chuẩn bị:

~~~bash
NAMESPACE='<OBJECT_STORAGE_NAMESPACE>'
BUCKET='oci-event-lab-input'

oci os bucket update \
  --region "$REGION" \
  --namespace-name "$NAMESPACE" \
  --name "$BUCKET" \
  --object-events-enabled true
~~~

Tạo một tệp dữ liệu giả và tải lên bằng một **tên object mới**:

~~~bash
printf 'invoice_id,total\nINV-001,120000\n' > event-lab.csv

oci os object put \
  --region "$REGION" \
  --namespace-name "$NAMESPACE" \
  --bucket-name "$BUCKET" \
  --name 'incoming/invoice-001.csv' \
  --file ./event-lab.csv
~~~

Nếu object đó đã có, dùng tên mới, chẳng hạn `incoming/invoice-002.csv`, để phép thử tạo mới rõ ràng. Không chọn ghi đè rồi mặc định kết quả phải giống thao tác tạo lần đầu.

Sau đó thử một object không hợp lệ với condition:

~~~bash
oci os object put \
  --region "$REGION" \
  --namespace-name "$NAMESPACE" \
  --bucket-name "$BUCKET" \
  --name 'incoming/readme.txt' \
  --file ./event-lab.csv
~~~

Dù nội dung tệp vẫn là CSV, tên object kết thúc bằng `.txt` nên không khớp bộ lọc. Phép thử này cũng cho thấy rule đang lọc metadata, không đọc nội dung tệp.

Chờ tín hiệu giao nhận và kiểm tra metrics theo khoảng thời gian phù hợp. Không coi việc không nhận email ngay lập tức là bằng chứng đủ để kết luận rule sai.

## 8. Kiểm tra đầu cuối bằng bằng chứng

Một lần kiểm thử có giá trị cần nối được ba lớp bằng chứng:

1. Thao tác trên nguồn thành công và nguồn được cấu hình phát event.
2. Rule khớp và có kết quả giao tới action.
3. Đích tạo đầu ra mong đợi: email, log xử lý hoặc bản ghi do consumer ghi.

Trong ví dụ Notifications, nội dung nhận phải liên quan đúng object đã tải lên. Nếu chuyển sang Function, nên ghi log có cấu trúc gồm `eventID`, `eventType`, tên bucket, tên object và kết quả xử lý; tránh ghi nguyên dữ liệu nghiệp vụ nhạy cảm.

Với nhiều rule hoặc nhiều action, một thao tác nguồn có thể dẫn tới nhiều lần giao. Không dùng tiêu chí “chỉ đúng một email” để khẳng định toàn hệ thống xử lý chính xác nếu chưa xem các đường đi khác.

### 8.1. Metrics của Events

Namespace giám sát là `oci_cloudevents`.

| Metric | Câu hỏi được hỗ trợ |
| --- | --- |
| `PublishedEvents` | Có sự kiện được phát từ tài nguyên trong compartment không? |
| `MatchedEvents` | Rule có khớp sự kiện không? |
| `DeliverySucceedEvents` | Có giao thành công tới action không? |
| `DeliveryFailedEvents` | Có lần giao không thành công không? |

Đối chiếu đúng region, cửa sổ thời gian và dimension `resourceId` của rule khi metric áp dụng cho rule. `PublishedEvents` phản ánh phạm vi compartment; không diễn giải nó như bộ đếm riêng của một rule.

Các metric có thể có dimension khác nhau; không giả định luôn lọc được mọi metric theo từng action riêng lẻ. Dùng dimension được cung cấp, cấu hình action và bằng chứng từ đích để khoanh vùng. [Nguồn: Events Metrics](https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventsmetrics.htm).

Một cảnh báo về lỗi giao nhận giúp phát hiện vấn đề ở đường giao sự kiện. Muốn biết Function có cập nhật thành công cơ sở dữ liệu hay consumer có bị chậm, cần thêm log và metric của thành phần đó.

### 8.2. Khoanh vùng lỗi theo chặng

| Hiện tượng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Không thấy event nguồn | Region, compartment, Emit object events, loại thao tác | Tạo sự kiện mới sau khi bật phát |
| Có event nhưng không thấy rule khớp | Condition, cấu trúc field, event type, phạm vi rule | Thử payload thực với trình kiểm tra mẫu |
| Condition mẫu khớp nhưng không có action | Rule/action có bật không, đích đúng không | Đọc lại cấu hình đang triển khai |
| Có lỗi giao nhận | Đích còn tồn tại không, quyền, trạng thái dịch vụ | Khoanh đúng action và kiểm tra đích |
| Giao Notifications thành công nhưng không có email | Topic, subscription, xác nhận, hộp thư nhận | Xác nhận đúng đường subscription |
| Function được gọi nhưng không có kết quả | Log, quyền resource principal, kết nối tới phụ thuộc | Sửa lỗi ở code hoặc đường truy cập |
| Stream nhận sự kiện nhưng ứng dụng không cập nhật | Tiến độ consumer, lỗi giải mã, lỗi ghi đầu ra | Khắc phục consumer và xử lý lại theo thiết kế |
| Số lần xử lý tăng bất thường | Rule chồng phạm vi, event trùng, vòng lặp tự động hóa | Thu hẹp condition và kiểm tra chống trùng |

Nếu tạm tạo rule rộng để chẩn đoán, dùng đích quan sát an toàn và giới hạn compartment thực hành. Không nối bộ lọc rộng vào Function có quyền thay đổi tài nguyên production.

## 9. Thiết kế chịu lỗi và chống xử lý trùng

Không thiết kế bộ xử lý dựa trên giả định mỗi event luôn đến đúng một lần hoặc theo thứ tự phát. Tài liệu FAQ của Oracle mô tả khả năng giao trùng và khuyến nghị receiver có tính idempotent. [Nguồn: Events Service FAQ](https://www.oracle.com/webfolder/technetwork/tutorials/faqs/oci/events-faq.pdf).

**Idempotent** nghĩa là xử lý lặp cùng một tác động không tạo thêm kết quả sai. Ví dụ, nhận lại event tạo object không được tự tạo thêm một yêu cầu thanh toán.

### 9.1. Chọn khóa xử lý phù hợp

`eventID` hữu ích để nhận diện lại cùng thông điệp. Tuy nhiên, hai event khác ID vẫn có thể cùng liên quan một nghiệp vụ. Vì vậy, có thể cần thêm khóa nghiệp vụ gồm namespace, bucket, tên object và định danh phiên bản phù hợp.

Không mặc định `eTag` là mã băm nội dung hoặc luôn thay thế được định danh phiên bản. Khóa chống trùng phải dựa trên ý nghĩa dữ liệu và kiểu thao tác mà ứng dụng thực sự cần bảo vệ.

Một thiết kế gợi ý:

~~~text
receive(event)
validate_event_type_and_scope(event)

key = derive_processing_key(event)
claim = acquire_atomic_claim_with_lease(key)

if claim.already_completed:
    return success

if not claim.acquired:
    return retry_later

try:
    result = perform_idempotent_business_operation(key, event)
    save_result_and_mark_completed(key, result)
    return success
catch error:
    record_failure_for_retry(key, error)
    return retry_or_escalate
~~~

Đây là mã giả về thiết kế, không phải handler OCI Functions có thể triển khai nguyên trạng.

Thao tác chiếm quyền xử lý phải nguyên tử. Nếu chỉ “đọc xem có chưa rồi ghi”, hai worker có thể đồng thời cho rằng mình là worker đầu tiên. Lease hoặc cơ chế tương đương giúp phục hồi khi tiến trình chết giữa chừng.

Nếu hiệu ứng bên ngoài và bảng trạng thái không nằm trong cùng giao dịch, vẫn có cửa sổ lỗi: tác động đã xảy ra nhưng chưa đánh dấu hoàn tất. Khi đó cần idempotency key ở hệ thống nhận, unique constraint, cơ chế outbox hoặc đối soát phù hợp. Một bảng `processed_events` đơn giản không tự bảo đảm exactly-once.

### 9.2. Retry, lưu lỗi và đối soát

Phân loại lỗi để hành động có chủ đích:

- Lỗi tạm thời như timeout hoặc throttling: thử lại với độ trễ và giới hạn phù hợp.
- Lỗi dữ liệu không hợp lệ: ghi trạng thái từ chối, lý do và vị trí dữ liệu để xử lý.
- Lỗi quyền hoặc sai cấu hình: cảnh báo người vận hành, tránh vòng lặp thử vô hạn.
- Lỗi phụ thuộc kéo dài: lưu thông tin đủ để khôi phục và đối soát sau.

Không giả định rule tự tạo một hàng đợi lỗi vĩnh viễn. Nếu cần lưu các công việc chưa hoàn thành, thiết kế kho lỗi hoặc luồng xử lý riêng và kiểm tra khả năng của dịch vụ đích.

Cũng không coi việc thêm Streaming làm action thứ hai là một cơ chế dự phòng chắc chắn cho Function: stream nhận được event không chứng minh Function đã nhận hay đã xử lý. Mỗi nhánh cần được giám sát độc lập.

### 9.3. Tránh vòng lặp tự động hóa

Nếu Function xử lý `incoming/a.csv` rồi ghi một tệp mới cũng nằm dưới `incoming/`, nó có thể tạo thêm event khớp rule.

Một cách tổ chức là:

- Nguồn vào ở `incoming/`.
- Kết quả ở `processed/` hoặc một bucket riêng.
- Condition chỉ nhận đúng vùng nguồn.
- Bộ xử lý vẫn kiểm tra phạm vi và khóa chống trùng.

Với tự động hóa thay đổi tài nguyên Compute hoặc cơ sở dữ liệu, áp dụng cùng nguyên tắc: xác định event nào do chính hành động của bộ xử lý tạo ra và ngăn nó kích hoạt lặp ngoài ý muốn.

## 10. Kiểm soát chi phí và thay đổi vận hành

Chi phí thực tế phụ thuộc các đích và công việc được kích hoạt. Khi đánh giá, tính cả Function, stream, subscriber, log, lưu trữ và các API phía sau.

Để ước lượng ban đầu:

~~~text
Số lần giao dự kiến ≈ số event khớp × số action đang bật
~~~

Đây là mô hình thiết kế đơn giản, chưa gồm retry, giao trùng và nhiều rule cùng khớp. Ví dụ, 2.000 event khớp với hai action tạo khoảng 4.000 lần giao trong mô hình cơ sở; không suy ra đó là 4.000 tác vụ nghiệp vụ hoàn thành hoặc 4.000 đơn vị tính phí.

Các biện pháp thực tế:

- Lọc đúng loại thay đổi và đúng tài nguyên ngay tại rule.
- Chỉ gửi email cho những thay đổi có người cần xử lý.
- Giới hạn lượng công việc mà Function có thể khởi tạo.
- Theo dõi tăng đột biến số event, lượt gọi và độ trễ consumer.
- Xác định thời gian lưu log, dữ liệu stream và kết quả xử lý theo nhu cầu.
- Đối chiếu bảng giá, hạn mức và quota hiện hành của từng dịch vụ trước khi triển khai lớn.

### 10.1. Triển khai thay đổi có thể kiểm chứng

Một quy trình phù hợp cho rule quan trọng:

1. Lưu condition, cấu hình action và mô tả mục đích trong hệ thống quản lý thay đổi của dự án.
2. Thử bằng payload hợp lệ và các trường hợp phải bị loại.
3. Kiểm tra trong compartment thực hành với quyền giới hạn.
4. Đọc lại cấu hình sau triển khai.
5. Phát một sự kiện mới có kiểm soát và theo dõi toàn đường đi.
6. Theo dõi lỗi giao nhận và đầu ra nghiệp vụ sau khi bật.

Khi thay action đang hoạt động, tránh vô tình tạo hai đường cùng xử lý một công việc. Nếu cần chạy song song để chuyển đổi, bộ xử lý phải có cơ chế chống trùng thích hợp.

### 10.2. Dừng rule và dọn tài nguyên thực hành

Tắt rule bằng:

~~~bash
oci events rule update \
  --region "$REGION" \
  --rule-id "$RULE_ID" \
  --is-enabled false \
  --wait-for-state ACTIVE
~~~

Đọc lại rule để xác nhận `isEnabled` đã tắt. Những công việc đã giao hoặc đã bắt đầu ở đích vẫn cần được kiểm tra riêng; tắt rule không hoàn tác tác động đã xảy ra.

Sau khi xác minh, xóa object và tài nguyên chỉ dành cho lab nếu không còn sử dụng. Với topic, subscription, Function hoặc stream dùng chung, chỉ tháo cấu hình liên quan đến bài thực hành theo phạm vi được giao. Nếu bucket giữ lại và không cần object events nữa, tắt cấu hình phát object events của bucket.

## 11. Áp dụng cùng phương pháp cho Compute và cơ sở dữ liệu Oracle

Tình huống Object Storage giúp nhìn rõ đường đi, nhưng cách thiết kế áp dụng cho các dịch vụ OCI khác:

1. Chọn đúng event type trong danh mục dịch vụ nguồn.
2. Đọc payload và xác định field thực sự dùng được.
3. Khoanh compartment và nhóm tài nguyên cần phản ứng.
4. Chọn người hoặc hệ thống nhận cuối.
5. Gắn action phù hợp và kiểm tra đầu cuối.
6. Thiết kế quyền, chống trùng, lưu lỗi và đối soát.

Với một thao tác backup cơ sở dữ liệu, cần phân biệt thông báo thao tác kết thúc với kết luận backup thành công. Chỉ kết luận sau khi đối chiếu định nghĩa event, trường kết quả hoặc trạng thái tài nguyên có thẩm quyền. Không tự đặt tên event bằng cách ghép chuỗi giống ví dụ của dịch vụ khác.

Với phản ứng tự động trên Compute, nên bắt đầu bằng action thông báo hoặc kiểm tra trạng thái. Khi chuyển sang thao tác thay đổi hạ tầng, xác định rõ phạm vi tài nguyên, điều kiện thực thi và cách phục hồi nếu hành động bị lặp.

Một cấu hình hoàn thành cho bài học phải có condition giải thích được, đích được chọn có lý do, bằng chứng cả trường hợp khớp lẫn không khớp, và phương án vận hành khi đích lỗi. Chỉ thấy rule ở trạng thái `ACTIVE` chưa đáp ứng các tiêu chí đó.

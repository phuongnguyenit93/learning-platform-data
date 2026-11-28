# Đồng bộ danh mục với năng lực cấp phát thực tế của broker

Catalog là hợp đồng công khai cho biết service broker có thể cung cấp dịch vụ nào, theo plan nào và hỗ trợ những thao tác nào. Nếu catalog quảng bá một khả năng mà broker hoặc nhà cung cấp chưa thực hiện được, nền tảng có thể cho người dùng chọn một dịch vụ rồi gặp lỗi khi provision, bind hoặc update. Ngược lại, nếu catalog bỏ sót khả năng đã triển khai ổn định, người dùng và nền tảng sẽ không khai thác được dịch vụ đó.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, catalog cần được đồng bộ với năng lực thực tế của ứng dụng broker, adapter nhà cung cấp và hạ tầng đích. Spring Cloud Open Service Broker giúp triển khai hợp đồng OSB API trên nền Spring; phần quyết định một service hay plan có thể được cung cấp ra sao vẫn cần được thiết kế và duy trì trong ứng dụng.

Bài học này trình bày cách mô hình hóa catalog, ánh xạ năng lực provision và binding thành metadata phù hợp, kiểm tra yêu cầu ở thời điểm thực thi, xử lý thay đổi plan và tránh để catalog trở thành một danh sách quảng cáo không phản ánh hành vi thật.

## 1. Catalog là hợp đồng giữa nền tảng và broker

Nền tảng gọi endpoint catalog của broker để lấy danh sách dịch vụ và plan mà broker công bố. Từ dữ liệu này, nền tảng có thể hiển thị lựa chọn cho người dùng, kiểm tra một số khả năng và chuẩn bị request theo hợp đồng OSB API.

Một mục catalog thường mô tả:

- **Service**: loại dịch vụ được cung cấp, chẳng hạn PostgreSQL, Redis hoặc object storage.
- **Plan**: biến thể của dịch vụ, chẳng hạn dung lượng, hiệu năng, mức sẵn sàng hoặc chính sách backup.
- **Capability**: các thao tác mà broker hỗ trợ cho service, ví dụ có thể binding hoặc thay đổi plan.
- **Schema**: cấu trúc và giới hạn của tham số mà nền tảng có thể gửi khi provision, update hoặc bind.
- **Metadata**: thông tin mô tả, phân loại hoặc hiển thị phù hợp với hợp đồng.

Catalog vì vậy là một phần của API công khai. Khi broker khai báo service có thể bind, nền tảng có quyền kỳ vọng thao tác bind được hỗ trợ theo hợp đồng. Khi broker công bố plan có thể update, nền tảng có thể đưa ra luồng thay đổi plan. Mọi khai báo phải có phần xử lý tương ứng ở phía broker.

Catalog không phải bản sao tùy ý của danh sách sản phẩm trên trang marketing. Nó cần phản ánh những gì broker có thể cung cấp qua API, trong phạm vi nhà cung cấp, cấu hình và chính sách mà broker quản lý.

## 2. Phân biệt service, plan và năng lực thao tác

Service xác định một loại sản phẩm. Plan xác định một cấu hình hoặc mức dịch vụ của sản phẩm đó. Capability mô tả những thao tác được hỗ trợ đối với service hoặc instance.

Ví dụ, một broker có thể cung cấp dịch vụ PostgreSQL với ba plan:

| Service | Plan | Đặc điểm minh họa |
|---|---|---|
| PostgreSQL | small | Dung lượng và tài nguyên cơ bản |
| PostgreSQL | standard | Tài nguyên cao hơn, có backup định kỳ |
| PostgreSQL | high-availability | Có dự phòng và khả năng phục hồi cao hơn |

Ba plan có thể cùng hỗ trợ provision và bind nhưng khác nhau về dung lượng, giá, thời gian backup hoặc khả năng chuyển đổi. Việc một plan có thể được tạo không có nghĩa plan đó có thể nâng cấp hoặc hạ cấp sang plan khác.

Năng lực cần được đánh giá theo từng thao tác:

| Thao tác | Điều broker phải làm được |
|---|---|
| Provision | Tạo instance theo service, plan và parameters hợp lệ |
| Bind | Tạo thông tin kết nối hoặc quyền truy cập cho consumer |
| Unbind | Thu hồi binding và quyền tương ứng |
| Update | Thực hiện các thay đổi được công bố, chẳng hạn chuyển plan nếu hỗ trợ |
| Deprovision | Thu hồi instance theo chính sách và trạng thái thực tế |
| Retrieve instance/binding | Trả thông tin nếu broker công bố hỗ trợ khả năng truy xuất tương ứng |

Nên mô hình hóa năng lực một cách tường minh. Ví dụ, plan small có thể provision và bind nhưng không cho phép chuyển sang plan khác do giới hạn kỹ thuật. Plan standard có thể hỗ trợ update sang high-availability nếu nhà cung cấp có quy trình nâng cấp an toàn. Sự khác nhau này cần được phản ánh trong logic catalog và xử lý request.

## 3. Các trường catalog cần phản ánh đúng hành vi

OSB API định nghĩa cấu trúc service và plan cùng một số trường thể hiện khả năng. Các trường cụ thể cần được xác nhận theo phiên bản giao thức mà broker triển khai.

Một ví dụ catalog rút gọn:

~~~json
{
  "services": [
    {
      "id": "postgres-service",
      "name": "postgresql",
      "description": "Cơ sở dữ liệu PostgreSQL được quản lý",
      "bindable": true,
      "plan_updateable": false,
      "tags": ["database", "relational"],
      "plans": [
        {
          "id": "postgres-small-v1",
          "name": "small",
          "description": "Plan cơ bản cho môi trường phát triển",
          "free": false,
          "metadata": {
            "displayName": "PostgreSQL Small"
          },
          "schemas": {
            "service_instance": {
              "create": {
                "parameters": {
                  "type": "object",
                  "properties": {
                    "database_name": {
                      "type": "string",
                      "minLength": 1
                    },
                    "storage_gb": {
                      "type": "integer",
                      "minimum": 10,
                      "maximum": 100
                    }
                  },
                  "required": ["database_name"]
                }
              }
            }
          }
        }
      ]
    }
  ]
}
~~~

Ví dụ này chỉ minh họa cấu trúc và ý nghĩa. Một catalog thật cần tuân theo schema của phiên bản OSB API đang dùng và những trường bắt buộc của hợp đồng.

### Những trường quan trọng

**id** là định danh ổn định của service hoặc plan. Nền tảng dùng ID trong các thao tác vòng đời. Không nên tái sử dụng một ID cũ cho một sản phẩm có ngữ nghĩa khác, vì instance đã tồn tại có thể vẫn tham chiếu ID đó.

**name** và **description** giúp con người hiểu dịch vụ. Có thể thay đổi nội dung hiển thị có kiểm soát, nhưng cần giữ ổn định ý nghĩa và không dùng tên hiển thị thay cho định danh.

**bindable** cho biết service có hỗ trợ tạo binding hay không. Nếu broker không có quy trình tạo và thu hồi thông tin truy cập, không nên đặt trường này thành true.

**plan_updateable** cho biết service có hỗ trợ thay đổi plan theo hợp đồng hay không. Chỉ bật khi handler update và tích hợp nhà cung cấp thực sự hỗ trợ những chuyển đổi được cho phép. Việc có endpoint update trong giao thức không đồng nghĩa mọi service đều có thể update.

**plans** chứa những lựa chọn được cung cấp cho service. Mỗi plan cần có ID, tên, mô tả và các metadata hoặc schema phù hợp. Không đưa một plan vào catalog nếu broker không thể provision plan đó trong phạm vi đã cam kết.

**schemas** mô tả tham số mà broker chấp nhận. Schema giúp nền tảng xây dựng biểu mẫu hoặc kiểm tra dữ liệu, nhưng broker vẫn phải xác thực ở phía server. Request có thể đến từ client không dùng giao diện của nền tảng.

Tùy phiên bản OSB API, catalog còn có thể chứa các capability như truy xuất service instance, truy xuất binding hoặc cho phép cập nhật context. Chỉ khai báo những capability đã được triển khai và kiểm thử. Không tự thêm trường ngoài schema của phiên bản đang hỗ trợ.

## 4. Đồng bộ catalog với năng lực thực tế của nhà cung cấp

Năng lực của broker không chỉ phụ thuộc vào API của nhà cung cấp. Một tính năng chỉ được xem là khả dụng khi tất cả thành phần cần thiết đều thực hiện được nó:

1. Nhà cung cấp có API hoặc cơ chế vận hành hỗ trợ.
2. Adapter của broker gọi và diễn giải được API đó.
3. Ứng dụng broker có handler thực hiện đúng quy trình OSB.
4. Broker lưu và phục hồi được trạng thái cần thiết.
5. Broker có thể xử lý lỗi, retry, bảo mật và các trường hợp biên.
6. Nền tảng đích hiểu capability và request tương ứng.

Ví dụ, nhà cung cấp database có thể hỗ trợ tạo database và thay đổi dung lượng. Nhưng nếu broker chưa có handler update, chưa lưu operation hoặc chưa xử lý được trường hợp nhà cung cấp timeout, broker chưa nên công bố khả năng update plan.

Có thể mô hình hóa năng lực theo ma trận:

| Năng lực | Nhà cung cấp | Adapter broker | Handler broker | Có thể công bố? |
|---|---|---|---|---|
| Provision PostgreSQL | Có | Có | Có | Có, sau kiểm thử |
| Bind credentials | Có | Có | Có | Có, sau kiểm thử |
| Update plan | Có điều kiện | Chưa có | Chưa có | Không |
| Retrieve binding | Có API | Có | Có | Có nếu đúng hợp đồng |
| Backup theo lịch tùy chỉnh | Có | Có | Chưa xử lý tham số | Chưa |

Catalog phải dựa trên năng lực đầu cuối của broker, không chỉ dựa trên một API riêng lẻ mà nhà cung cấp quảng bá.

### Không đồng nhất khả năng kỹ thuật với quyền sử dụng

Một nhà cung cấp có thể hỗ trợ một loại instance nhưng tài khoản cloud hiện tại không có quyền tạo nó. Một region có thể không có đủ quota. Một plan có thể bị giới hạn theo hợp đồng hoặc chính sách của tổ chức.

Vì vậy, cần phân biệt:

- **Capability**: broker có triển khai thao tác đó hay không.
- **Eligibility**: tổ chức, region hoặc tenant cụ thể có đủ điều kiện sử dụng hay không.
- **Capacity**: tại thời điểm yêu cầu, nhà cung cấp còn tài nguyên hay không.

Catalog mô tả các dịch vụ broker cam kết cung cấp trong phạm vi xác định. Provision vẫn phải kiểm tra quyền, quota, region và capacity hiện tại. Không nên xem một mục catalog là bảo đảm tài nguyên luôn sẵn có ở mọi thời điểm.

Nếu dịch vụ chỉ có ở một số region hoặc nhóm tenant, broker cần thiết kế cách công bố rõ ràng theo khả năng của nền tảng. Có thể định nghĩa các service/plan có phạm vi cụ thể hoặc dùng context/parameters theo hợp đồng để xác định phạm vi cấp phát. Dù chọn cách nào, broker phải kiểm tra lại điều kiện thực tế khi nhận request.

## 5. Thiết kế catalog như một nguồn dữ liệu có kiểm soát

Trong ứng dụng Spring, nên tập trung định nghĩa catalog ở một nơi có thể kiểm tra và tái sử dụng. Cấu hình này có thể đến từ cấu hình ứng dụng, cơ sở dữ liệu quản trị hoặc một registry nội bộ. Tránh khai báo một bộ plan trong catalog, một bộ khác trong handler provision và một bộ thứ ba trong adapter nhà cung cấp.

Một mô hình nội bộ có thể gồm:

- **ServiceDefinition**: ID, tên, mô tả, metadata và danh sách plan.
- **PlanDefinition**: ID, giới hạn tài nguyên, giá hoặc chính sách, schema tham số.
- **CapabilitySet**: các thao tác đã được triển khai và kiểm thử.
- **ProviderProfile**: nhà cung cấp, region, loại tài nguyên và điều kiện hỗ trợ.
- **LifecyclePolicy**: quy tắc provision, update, bind, unbind và deprovision.

Từ mô hình này, ứng dụng xây dựng catalog response và dùng cùng định nghĩa để xác thực request. Framework Spring Cloud Open Service Broker cung cấp các điểm tích hợp để trả catalog và xử lý các thao tác OSB; chi tiết class và cấu hình phải theo đúng phiên bản thư viện mà dự án đang sử dụng.

Một luồng xây dựng catalog có thể mô tả như sau:

~~~mermaid
flowchart TD
    Config["Service/Plan definitions"] --> Capability["Đối chiếu capability broker"]
    Provider["Provider profiles"] --> Capability
    Capability --> Validate["Kiểm tra schema và tính nhất quán"]
    Validate --> Snapshot["Catalog snapshot đã xác thực"]
    Snapshot --> Endpoint["GET /v2/catalog"]
    Snapshot --> Provision["Provision handler"]
    Snapshot --> Update["Update handler"]
    Snapshot --> Binding["Binding handlers"]
~~~

Điểm quan trọng là catalog và handler phải dùng cùng một định nghĩa về service, plan và capability. Nếu catalog được xây dựng từ một nguồn nhưng handler đọc một nguồn khác, hai phía có thể lệch nhau sau một lần thay đổi cấu hình.

### Sinh catalog từ cấu hình

Ví dụ cấu hình khái niệm:

~~~yaml
broker:
  services:
    - id: postgres-service
      name: postgresql
      bindable: true
      plan-updateable: false
      plans:
        - id: postgres-small-v1
          name: small
          provider: managed-postgres
          min-storage-gb: 10
          max-storage-gb: 100
          supports-provision: true
          supports-bind: true
          supports-update: false
~~~

Đây là cấu hình minh họa cho mô hình nội bộ, không phải YAML schema chuẩn của OSB API hay cấu hình có thể sao chép trực tiếp vào mọi phiên bản Spring Cloud Open Service Broker.

Khi khởi động ứng dụng hoặc nạp lại cấu hình, broker có thể kiểm tra:

- ID service và plan không trùng nhau trong phạm vi yêu cầu.
- Mỗi plan tham chiếu đến provider profile tồn tại.
- bindable phù hợp với handler bind và unbind.
- plan_updateable chỉ bật khi có quy trình update hoàn chỉnh.
- Giới hạn trong schema phù hợp với giới hạn nhà cung cấp.
- Các trường bắt buộc của OSB API được tạo đầy đủ.
- Không có tham số bí mật trong catalog.

Nếu kiểm tra thất bại, ứng dụng nên từ chối nạp cấu hình không hợp lệ hoặc không công bố snapshot lỗi. Một catalog sai có thể ảnh hưởng đến mọi người dùng nền tảng.

## 6. Giữ catalog nhất quán khi năng lực thay đổi

Năng lực nhà cung cấp có thể thay đổi theo thời gian. Một API có thể ngừng hỗ trợ một loại tài nguyên, region có thể hết quota, plan có thể bị ngừng bán hoặc một phiên bản adapter có thể chưa xử lý được API mới.

Không phải mọi thay đổi đều yêu cầu cập nhật catalog ngay lập tức. Cần phân loại:

| Thay đổi | Cách xử lý phù hợp |
|---|---|
| Plan bị ngừng cung cấp cho yêu cầu mới | Ngừng công bố plan theo chính sách; vẫn xử lý vòng đời instance cũ |
| Nhà cung cấp tạm hết capacity | Giữ catalog nếu plan vẫn là sản phẩm hợp lệ; từ chối provision có kiểm soát hoặc thông báo trạng thái phù hợp |
| Broker mất khả năng bind sau một thay đổi triển khai | Tắt capability hoặc đưa service vào trạng thái không nhận yêu cầu mới cho đến khi khôi phục |
| Giới hạn dung lượng thay đổi | Cập nhật schema và kiểm tra ở handler đồng bộ với provider |
| Provider API đổi phiên bản | Kiểm tra adapter và hợp đồng trước khi công bố capability mới |
| Plan được thay thế bằng plan mới | Thêm ID mới; giữ xử lý tương thích với instance cũ |

Một nguyên tắc quan trọng là **ngừng bán không đồng nghĩa xóa bỏ lịch sử vòng đời**. Nếu plan cũ không còn xuất hiện cho yêu cầu mới, broker vẫn có thể cần nhận bind, unbind, update hoặc deprovision cho các instance đã tạo bằng plan đó. Cần lưu định nghĩa cũ hoặc dữ liệu tương đương đủ để xử lý tài nguyên hiện hữu.

### Catalog snapshot và cập nhật nguyên tử

Nếu catalog được tạo từ nhiều nguồn cấu hình, tránh cập nhật từng phần trong lúc request đang đọc. Một request có thể nhận service mới nhưng thiếu plan, hoặc thấy capability mới trong khi handler chưa được nạp.

Có thể dùng catalog snapshot bất biến:

1. Nạp cấu hình service, plan và provider.
2. Xây dựng snapshot mới.
3. Kiểm tra ID, schema, capability và quan hệ tham chiếu.
4. Chạy các kiểm tra nội bộ cần thiết.
5. Chuyển snapshot hiện hành sang snapshot mới một cách nguyên tử.
6. Ghi nhận phiên bản cấu hình và thời điểm áp dụng.

Các request đang xử lý có thể tiếp tục dùng snapshot đã bắt đầu; request mới đọc snapshot hiện hành. Với nhiều instance broker, cần có cơ chế phân phối cùng phiên bản cấu hình để tránh mỗi node trả một catalog khác nhau.

Không nên thay đổi catalog dựa trên một lỗi timeout đơn lẻ từ provider. Trạng thái lỗi tạm thời cần được phân biệt với việc plan thực sự bị thu hồi. Cần có chính sách retry, thời gian xác nhận và cơ chế quan sát trước khi thay đổi nội dung công bố.

## 7. Provision phải xác thực lại những gì catalog đã mô tả

Catalog giúp nền tảng hiểu lựa chọn hợp lệ, nhưng không thay thế xác thực ở endpoint provision. Client có thể gửi request trực tiếp, dùng catalog cũ hoặc chọn plan đã bị ngừng cung cấp.

Khi nhận provision, broker nên kiểm tra theo trình tự:

1. **Định danh**: service_id và plan_id có được broker nhận diện không?
2. **Trạng thái cung cấp**: plan còn cho phép tạo instance mới không?
3. **Phạm vi**: organization, space, region hoặc context có được phép sử dụng plan không?
4. **Parameters**: kiểu dữ liệu, trường bắt buộc, giới hạn và quan hệ giữa các trường có hợp lệ không?
5. **Provider**: tài khoản, quota, capacity và API nhà cung cấp có đáp ứng yêu cầu không?
6. **Idempotency**: request retry với instance_id hiện có phải trả kết quả nhất quán hay không?
7. **Operation**: nếu xử lý bất đồng bộ, broker phải lưu operation và cho nền tảng truy vấn tiến độ.

Ví dụ, catalog cho phép storage_gb trong khoảng 10 đến 100. Provision vẫn cần từ chối giá trị 500. Nếu catalog cho biết service bindable, broker vẫn cần kiểm tra instance đã provision thành công và binding request có hợp lệ trước khi cấp credentials.

Khi plan không còn nhận provision mới nhưng instance cũ vẫn tồn tại, broker phải phân biệt hai trạng thái này. Không nên dùng một cờ disabled duy nhất để chặn mọi thao tác, vì deprovision và thu hồi binding vẫn có thể cần thực hiện.

## 8. Đồng bộ binding và các capability liên quan

Binding là một phần quan trọng của hợp đồng dịch vụ. Một service chỉ nên được công bố là bindable khi broker có thể tạo thông tin truy cập hoặc cấu hình kết nối theo yêu cầu.

Khi tạo binding, broker cần xác thực:

- Instance tồn tại và ở trạng thái cho phép bind.
- Service và plan hỗ trợ binding theo catalog.
- Binding ID chưa được dùng cho một binding khác với dữ liệu không tương thích.
- Consumer context và parameters hợp lệ.
- Provider có thể tạo user, role, credential hoặc quyền truy cập tương ứng.
- Credentials được trả về đúng hợp đồng, được bảo vệ trong quá trình truyền và không xuất hiện trong log.

Khi unbind, broker phải thu hồi hoặc vô hiệu hóa quyền truy cập theo chính sách dịch vụ. Nếu provider chưa thể xác nhận thu hồi ngay, cần lưu trạng thái và xử lý theo mô hình phù hợp; không nên báo hoàn tất chỉ vì đã gửi lệnh thu hồi.

Một số capability truy xuất instance hoặc binding có thể được khai báo trong catalog tùy phiên bản OSB API. Nếu công bố, endpoint tương ứng phải trả dữ liệu đúng với trạng thái mà broker quản lý. Dữ liệu trả về không nên tiết lộ credentials hoặc thông tin nội bộ không cần thiết.

## 9. Ví dụ: catalog thay đổi khi một plan bị ngừng cung cấp

Giả sử broker đang công bố hai plan standard và premium. Nhà cung cấp thông báo plan standard sẽ ngừng cấp phát instance mới vào cuối tháng, nhưng các database hiện tại vẫn được duy trì và có thể deprovision bình thường.

Cách xử lý hợp lý:

- Đặt plan standard thành trạng thái không nhận provision mới trong nguồn cấu hình nội bộ.
- Từ thời điểm áp dụng, loại plan khỏi danh sách lựa chọn mới trong catalog theo chính sách công bố.
- Giữ ánh xạ ID và metadata cần thiết để nhận diện instance cũ.
- Cho phép các thao tác vòng đời cần thiết đối với instance đã tồn tại, đặc biệt là unbind và deprovision.
- Nếu có chính sách migrate sang premium, chỉ cho phép update khi provider và broker hỗ trợ chuyển đổi an toàn.
- Ghi nhận thời điểm ngừng bán, lý do và phiên bản catalog để có thể đối soát khi nền tảng gửi request dựa trên dữ liệu cũ.

Không nên xóa hoàn toàn định nghĩa standard khỏi kho dữ liệu nội bộ nếu các instance cũ vẫn tham chiếu nó. Catalog công khai và dữ liệu lịch sử phục vụ vòng đời là hai phạm vi khác nhau.

## 10. Kiểm thử tính nhất quán giữa catalog và handler

Kiểm thử catalog không chỉ xác nhận endpoint trả HTTP 200 hoặc JSON parse được. Cần kiểm tra nội dung catalog có khớp với hành vi của broker.

Một bộ kiểm tra hợp đồng có thể gồm:

| Kiểm tra | Điều kiện cần xác nhận |
|---|---|
| ID service/plan | Ổn định, duy nhất và được handler nhận diện |
| Bindable | true thì bind và unbind có luồng xử lý thực tế |
| Plan updateable | true thì update handler hỗ trợ các chuyển đổi được công bố |
| Schema parameters | Request hợp lệ được chấp nhận; request ngoài schema bị từ chối |
| Provider profile | Mỗi plan có adapter và cấu hình provider tương ứng |
| Plan ngừng bán | Không nhận provision mới nhưng vẫn xử lý instance cũ |
| Capability truy xuất | Endpoint được công bố trả dữ liệu nhất quán |
| Catalog snapshot | Các node broker trả cùng một phiên bản catalog đã phát hành |

Có thể bổ sung kiểm thử tích hợp với nền tảng để xác nhận nền tảng đọc catalog, hiển thị đúng plan, gửi đúng request và xử lý response đồng bộ hoặc bất đồng bộ. Khi nâng phiên bản Spring Cloud Open Service Broker hoặc OSB API, cần chạy lại các kiểm thử hợp đồng liên quan.

## 11. Những lỗi thường gặp

**Khai báo bindable chỉ vì service có URL.** Có endpoint kết nối không có nghĩa broker có khả năng tạo và thu hồi binding theo hợp đồng. Phải có luồng cấp quyền và thu hồi quyền thực tế.

**Đặt plan_updateable thành true vì provider có API update.** Broker còn phải có handler, xác thực chuyển đổi, quản lý operation, xử lý retry và bảo đảm trạng thái nhất quán. Chỉ một API của provider là chưa đủ.

**Để catalog và provision dùng hai bộ cấu hình khác nhau.** Người dùng có thể thấy một plan mà handler không nhận diện, hoặc schema cho phép giá trị mà provider từ chối. Hãy dùng chung nguồn định nghĩa và kiểm tra ở runtime.

**Xóa plan cũ khỏi toàn bộ dữ liệu khi ngừng bán.** Instance hiện hữu vẫn có thể tham chiếu plan đó. Cần duy trì thông tin lịch sử để xử lý các thao tác vòng đời còn lại.

**Coi catalog là bảo đảm capacity.** Catalog mô tả dịch vụ được cung cấp, còn quota và capacity có thể thay đổi. Provision phải xác thực điều kiện hiện tại.

**Công bố capability chưa được kiểm thử trên nền tảng đích.** Broker có thể trả catalog hợp lệ nhưng nền tảng không hiểu hoặc không sử dụng được capability. Cần kiểm thử tích hợp với phiên bản nền tảng thực tế.

## 12. Nguyên tắc triển khai trong Spring Cloud Service Broker

Trong ứng dụng Spring Cloud Open Service Broker, hãy tổ chức định nghĩa service, plan, schema và capability sao cho catalog endpoint và các handler dùng chung một nguồn dữ liệu. Mỗi thay đổi catalog nên đi cùng thay đổi ở handler, adapter nhà cung cấp, persistence, bảo mật và kiểm thử hợp đồng.

Catalog cần có ID ổn định, schema phản ánh giới hạn thực tế và capability chỉ được công bố khi broker hoàn thành toàn bộ quy trình. Với thay đổi nhà cung cấp, cần phân biệt khả năng kỹ thuật, quyền sử dụng và capacity tại thời điểm yêu cầu. Với plan ngừng bán, giữ dữ liệu lịch sử để phục vụ instance đã tồn tại. Với broker chạy nhiều instance, phân phối catalog snapshot nhất quán để các node không công bố những năng lực khác nhau.

Khi nền tảng gọi provision, update, bind hoặc deprovision, broker luôn xác thực lại yêu cầu và trạng thái tài nguyên. Catalog giúp nền tảng đưa ra lựa chọn chính xác; handler và adapter mới chịu trách nhiệm thực hiện lựa chọn đó một cách an toàn, có thể quan sát và nhất quán với nhà cung cấp.


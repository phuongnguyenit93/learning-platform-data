# Theo dõi thao tác, hủy liên kết và xóa dịch vụ bằng CF CLI

Cloud Foundry cung cấp các lệnh trong cf CLI để quản lý vòng đời service instance sau khi ứng dụng đã được triển khai. Người vận hành có thể liệt kê service, xem trạng thái operation gần nhất, chờ thao tác bất đồng bộ hoàn tất, hủy binding với ứng dụng hoặc route, rồi xóa service instance khi không còn consumer sử dụng.

Các lệnh này tác động đến Cloud Controller. Với managed service, Cloud Controller điều phối request đến service broker theo Open Service Broker API (OSB API); broker tiếp tục làm việc với provider để tạo hoặc thu hồi tài nguyên và credentials. Vì vậy, kết quả hiển thị trên CLI phản ánh trạng thái mà nền tảng nhận được từ broker, không phải một lệnh trực tiếp thao tác database hoặc cluster của provider.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, hiểu đúng luồng này giúp kiểm tra broker đang xử lý provision/deprovision ra sao, xác định binding nào còn hoạt động và tránh xóa service khi ứng dụng vẫn phụ thuộc vào credentials. Bài học này tập trung vào cf CLI, các bước vận hành an toàn, cách đọc lỗi và mối liên hệ giữa lệnh CLI với endpoint OSB API.

## 1. Vai trò của cf CLI, Cloud Controller và service broker

Khi người dùng chạy một lệnh như create-service, bind-service hoặc delete-service, cf CLI gửi request đến Cloud Controller của Cloud Foundry. Cloud Controller xác thực quyền, kiểm tra tài nguyên trong organization/space và điều phối thao tác service.

Với managed service instance, Cloud Controller gọi broker đã đăng ký. Broker xử lý request OSB API, gọi provider adapter và lưu trạng thái operation. Nếu thao tác được xử lý bất đồng bộ, broker trả kết quả tiếp nhận theo hợp đồng; Cloud Controller tiếp tục truy vấn trạng thái operation và cập nhật trạng thái cho người dùng.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant User as Operator
    participant CLI as cf CLI
    participant CC as Cloud Controller
    participant Broker as Service Broker
    participant Provider as Provider

    User->>CLI: cf service / unbind-service / delete-service
    CLI->>CC: Cloud Foundry API request
    CC->>Broker: OSB API request
    Broker->>Provider: Create, revoke or delete resource
    Provider-->>Broker: Result or provider operation
    Broker-->>CC: OSB response
    CC-->>CLI: Status and operation information
    CLI-->>User: Result
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| cf CLI | Gửi lệnh, hiển thị thông tin và chờ kết quả nếu có tùy chọn wait |
| Cloud Controller | Quản lý service instance/binding trong phạm vi platform và gọi broker |
| Service broker | Thực hiện hợp đồng OSB API, quản lý state, idempotency và provider adapter |
| Provider | Tạo, duy trì, revoke hoặc xóa tài nguyên thật |
| Ứng dụng consumer | Đọc credentials được platform cung cấp và kết nối đến service |

Lệnh CLI thành công ở bước tiếp nhận chưa chắc đồng nghĩa provider đã hoàn tất công việc. Cần đọc last operation hoặc dùng tùy chọn chờ hoàn tất trước khi kết luận.

## 2. Chuẩn bị phiên làm việc và chọn đúng organization/space

Trước khi thao tác, xác nhận API endpoint, user, organization và space đang được target. Service instance thường được hiển thị theo space hiện tại; chạy lệnh trong nhầm space có thể khiến operator không tìm thấy hoặc tác động nhầm tài nguyên.

Ví dụ:

~~~bash
cf api https://api.example.com
cf login
cf target -o commerce -s production
cf target
~~~

Lệnh target cuối cùng hiển thị context hiện tại. Có thể dùng:

~~~bash
cf orgs
cf spaces
cf apps
~~~

để kiểm tra organization, space và ứng dụng trước khi làm việc với service.

Trong môi trường automation, nên dùng service account có quyền tối thiểu cần thiết và cơ chế đăng nhập không tương tác phù hợp với nền tảng. Không ghi access token, mật khẩu hoặc nội dung credentials vào script, command history hay log CI.

## 3. Liệt kê service instance bằng cf services

Lệnh:

~~~bash
cf services
~~~

hiển thị service instance trong space đang target. Bảng kết quả thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| name | Tên service instance |
| service | Service offering |
| plan | Service plan đang sử dụng |
| bound apps | Các ứng dụng đang bind |
| last operation | Kết quả operation gần nhất |
| broker | Broker cung cấp service |
| upgrade available | Có bản nâng cấp plan/service hay không, nếu platform hỗ trợ |

Ví dụ:

~~~text
name       service   plan       bound apps   last operation       broker
orders-db  postgres  standard   orders-api   create succeeded     postgres-broker
reports-db postgres  small                   update in progress   postgres-broker
~~~

Bảng này giúp phát hiện nhanh service còn ứng dụng đang bind và operation nào đang chạy. Nếu space lớn, việc truy xuất thông tin bound apps có thể mất thời gian. Có thể bỏ phần đó khi chỉ cần danh sách:

~~~bash
cf services --no-apps
~~~

Không nên kết luận một service không còn consumer chỉ từ cột bound apps nếu service được chia sẻ sang space khác hoặc có service key dành cho consumer bên ngoài Cloud Foundry. Cần kiểm tra thêm trạng thái sharing và service keys khi phù hợp.

## 4. Xem chi tiết và last operation bằng cf service

Để xem một service instance:

~~~bash
cf service orders-db
~~~

Thông tin có thể bao gồm tên, GUID, loại service, offering, plan, broker, dashboard URL, trạng thái sharing và thông tin operation gần nhất.

Phần last operation thường hiển thị:

- status: trạng thái như create succeeded, update in progress hoặc delete failed.
- message: mô tả do broker cung cấp nếu có.
- started: thời điểm bắt đầu operation.
- updated: thời điểm Cloud Controller cập nhật trạng thái gần nhất.

Ví dụ:

~~~text
Showing status of last operation from service orders-db...

status:    create succeeded
message:
started:   2026-11-27T08:30:00Z
updated:   2026-11-27T08:31:12Z
~~~

Đây là nơi đầu tiên nên kiểm tra khi create-service, update-service hoặc delete-service báo thao tác chưa hoàn tất. Nếu status là failed, đọc message để biết hướng xử lý. Nếu message chung chung, dùng operation reference/correlation ID do broker cung cấp nếu có và tra cứu log nội bộ theo quy trình vận hành.

Không đưa credentials hoặc dữ liệu khách hàng vào message của last operation. Message nên mô tả kết quả có thể hành động mà không tiết lộ provider URL, password, SQL hoặc thông tin tenant khác.

## 5. Chờ các thao tác bất đồng bộ hoàn tất

Provision và một số thao tác service có thể mất thời gian vì broker cần gọi provider hoặc chờ provider operation. cf CLI hỗ trợ tùy chọn --wait cho nhiều lệnh service.

Ví dụ tạo service và chờ hoàn tất:

~~~bash
cf create-service postgres standard orders-db --wait
~~~

Với lệnh update:

~~~bash
cf update-service orders-db -p premium --wait
~~~

Với lệnh unbind:

~~~bash
cf unbind-service orders-api orders-db --wait
~~~

Với lệnh xóa:

~~~bash
cf delete-service orders-db --wait
~~~

Có thể yêu cầu cf services chờ các operation đang chạy trong space trước khi trả kết quả:

~~~bash
cf services --wait
~~~

Sự khác nhau cần nhớ:

- cf service NAME xem chi tiết một instance và trạng thái operation gần nhất.
- cf services liệt kê các instance trong space.
- cf services --wait chờ các operation bất đồng bộ đang được theo dõi trong danh sách trước khi kết thúc.
- --wait trên một lệnh cụ thể chờ operation do lệnh đó khởi tạo hoàn tất.

Không phải mọi service hoặc broker đều có thời gian hoàn tất giống nhau. Provider có thể cần thời gian để tạo database, cấp network hoặc xóa volume. Nếu operation vẫn in progress, tiếp tục theo dõi thay vì gửi nhiều lệnh create/delete khác nhau cho cùng tài nguyên.

## 6. Hiểu các trạng thái operation

Trong giao diện Cloud Foundry, trạng thái operation của managed service thường được hiển thị ở dạng:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| create in progress | Provision đang chạy | Chờ và theo dõi |
| create succeeded | Provision hoàn tất | Có thể kiểm tra binding hoặc sử dụng service |
| create failed | Provision thất bại | Đọc message, xử lý nguyên nhân và đối soát tài nguyên |
| update in progress | Update đang chạy | Tránh gửi update khác xung đột |
| update succeeded | Update hoàn tất | Kiểm tra plan/configuration mới |
| update failed | Update thất bại | Đọc message và kiểm tra trạng thái provider |
| delete in progress | Deprovision đang chạy | Chờ kết quả, không giả định resource đã bị xóa |
| delete succeeded | Deprovision hoàn tất | Xác minh instance đã biến mất khỏi danh sách |
| delete failed | Deprovision thất bại | Kiểm tra broker/provider và cleanup còn tồn đọng |

Cloud Controller lấy trạng thái last operation từ broker theo giao thức tương ứng. Với OSB API v2, khi broker trả HTTP 202 Accepted cho provision, update hoặc deprovision, platform có thể poll endpoint last_operation của service instance. cf CLI trình bày trạng thái đó qua lệnh service/services.

Một operation failed không nhất thiết chứng minh không có side effect ở provider. Nếu broker gặp timeout sau khi provider đã tạo hoặc xóa tài nguyên, cần reconciliation theo external resource ID hoặc operation reference. Operator không nên tự tạo một service instance mới chỉ vì lệnh trước báo timeout.

## 7. Kiểm tra binding trước khi hủy liên kết

Binding liên kết service instance với một ứng dụng hoặc consumer. Với application binding, Cloud Foundry thường đưa credentials vào VCAP_SERVICES hoặc cơ chế credential delivery được cấu hình.

Trước khi unbind, xem service:

~~~bash
cf service orders-db
cf apps
~~~

Đối chiếu cột bound apps trong cf services với các ứng dụng thực tế. Xác nhận ứng dụng nào còn cần database, queue hoặc dịch vụ đang được cấp.

Nếu service instance được share sang space khác, kiểm tra nơi sử dụng trước khi thay đổi sharing hoặc xóa instance. Service có thể có consumer ngoài space hiện tại.

Unbind có tác động đến khả năng kết nối của ứng dụng. Hãy chuẩn bị cấu hình thay thế hoặc lịch bảo trì nếu ứng dụng đang dùng credentials đó cho request đang chạy.

## 8. Hủy application binding bằng cf unbind-service

Cú pháp:

~~~bash
cf unbind-service APP-NAME SERVICE-INSTANCE-NAME
~~~

Ví dụ:

~~~bash
cf unbind-service orders-api orders-db --wait
~~~

Lệnh này hủy liên kết giữa ứng dụng orders-api và service instance orders-db. Cloud Foundry yêu cầu broker xử lý thao tác delete binding theo OSB API; broker thường revoke user, token hoặc quyền truy cập đã cấp cho binding tương ứng.

Unbind không deprovision service instance. Sau khi unbind, instance vẫn tồn tại và có thể được bind với ứng dụng khác nếu service hỗ trợ.

Cloud Foundry loại credentials của binding khỏi VCAP_SERVICES hoặc nơi credential delivery được cấu hình. Ứng dụng cần restart hoặc trong một số trường hợp re-push để nhận thay đổi trong môi trường runtime:

~~~bash
cf restart orders-api
~~~

Chỉ restart sau khi đã xác nhận ứng dụng có thể chạy mà không cần binding vừa gỡ hoặc đã có cấu hình thay thế. Nếu ứng dụng vẫn cố kết nối bằng credentials cũ, việc unbind có thể làm request lỗi.

### Xác nhận sau unbind

Chạy lại:

~~~bash
cf service orders-db
cf services
~~~

Kiểm tra orders-api không còn nằm trong danh sách bound apps. Nếu broker hỗ trợ operation bất đồng bộ cho binding theo phiên bản tích hợp, dùng --wait và theo dõi kết quả của lệnh.

## 9. Hủy route service binding

Một số service được bind vào route để xử lý request/response qua một route service, chẳng hạn proxy hoặc lớp kiểm tra bảo mật.

Cú pháp:

~~~bash
cf unbind-route-service DOMAIN --hostname APP-NAME SERVICE-INSTANCE-NAME
~~~

Ví dụ:

~~~bash
cf unbind-route-service apps.example.com --hostname orders-api edge-proxy
~~~

Lệnh này loại bỏ liên kết route giữa route của ứng dụng và service instance edge-proxy. Không cần restage ứng dụng chỉ để thay đổi route binding.

Cần xem xét tác động bảo mật trước khi unbind. Nếu route service cung cấp authentication, authorization, filtering hoặc kiểm tra request, việc gỡ nó có thể khiến ứng dụng không còn lớp bảo vệ đó. Xác nhận đã có cơ chế thay thế trước khi thực hiện.

Application binding và route service binding là hai loại liên kết khác nhau. Dùng đúng lệnh cho đúng loại; cf unbind-service không thay thế cf unbind-route-service.

## 10. Phân biệt application binding và service key

Service key là credentials được tạo cho consumer bên ngoài ứng dụng Cloud Foundry, chẳng hạn một công cụ quản trị hoặc hệ thống chạy ngoài platform. Service key không phải application binding.

Có thể xem danh sách key:

~~~bash
cf service-keys orders-db
~~~

Xem chi tiết một key:

~~~bash
cf service-key orders-db reporting-key
~~~

Xóa key:

~~~bash
cf delete-service-key orders-db reporting-key --wait
~~~

Khi chuẩn bị xóa service instance, kiểm tra cả application bindings và service keys. Một service key còn được hệ thống bên ngoài sử dụng có thể làm gián đoạn tích hợp nếu bị xóa mà không thông báo.

Không dùng cf unbind-service để xóa service key. Unbind xử lý binding giữa app và service instance; delete-service-key xử lý key riêng.

## 11. Xử lý service instance được share sang space khác

Một service instance có thể được share từ space nguồn sang một hoặc nhiều space khác. Việc xóa hoặc đổi tên instance có thể bị chặn khi nó vẫn được share.

Kiểm tra thông tin sharing qua:

~~~bash
cf service orders-db
~~~

Nếu cần unshare, dùng lệnh theo space đích:

~~~bash
cf unshare-service orders-db -s reporting
~~~

Nếu space đích thuộc organization khác, có thể cần chỉ rõ organization theo cú pháp CLI:

~~~bash
cf unshare-service orders-db -s reporting -o analytics
~~~

Unsharing có thể xóa các binding đến ứng dụng trong space được share. Điều này có thể làm ứng dụng ở space đó mất credentials hoặc mất kết nối. Trước khi unshare, kiểm tra bound apps và phối hợp với chủ sở hữu các consumer.

Không dùng unshare như một bước dọn dẹp tự động nếu chưa biết các ứng dụng nào phụ thuộc vào service instance.

## 12. Xóa service instance bằng cf delete-service

Khi không còn ứng dụng, route hoặc consumer nào cần service, có thể deprovision instance.

Cú pháp:

~~~bash
cf delete-service SERVICE-INSTANCE-NAME
~~~

Ví dụ chờ thao tác hoàn tất:

~~~bash
cf delete-service orders-db --wait
~~~

CLI có thể yêu cầu xác nhận trước khi xóa. Tùy chọn -f hoặc --force bỏ qua prompt xác nhận:

~~~bash
cf delete-service orders-db -f --wait
~~~

Tùy chọn force ở đây chỉ bỏ bước hỏi xác nhận của CLI. Nó không biến một provider error thành thành công, không bỏ qua policy của broker và không tương đương với thao tác purge metadata.

Xóa một managed service instance sẽ yêu cầu deprovision tài nguyên và xóa dữ liệu liên quan theo hợp đồng dịch vụ. Đây là thao tác có thể gây mất dữ liệu. Trước khi chạy, xác nhận backup/export đã hoàn tất nếu cần, kiểm tra retention policy, application bindings, route bindings, service keys và các space đang được share.

### Trình tự xóa có kiểm soát

Một quy trình thường dùng:

1. Xác định service instance và đúng organization/space.
2. Kiểm tra operation hiện tại đã hoàn tất.
3. Liệt kê bound apps và service keys.
4. Chuyển ứng dụng sang service thay thế hoặc dừng consumer theo kế hoạch.
5. Unbind từng app bằng cf unbind-service.
6. Unbind route service nếu có.
7. Xóa service keys không còn được sử dụng.
8. Unshare khỏi các space khác nếu instance đang được share và đã xử lý consumer ở đó.
9. Chạy cf delete-service với --wait.
10. Xác nhận service không còn trong cf services và kiểm tra trạng thái provider/broker nếu cần.

Cloud Controller có thể xử lý các binding liên quan trong quá trình xóa service instance theo phiên bản API và loại service. Thực hiện unbind có chủ đích trước đó giúp operator kiểm soát consumer, thời điểm ngừng kết nối và việc thu hồi credentials.

## 13. Kiểm tra kết quả sau khi xóa

Sau khi lệnh hoàn tất:

~~~bash
cf services
cf service orders-db
~~~

Nếu service đã bị xóa thành công, instance không còn xuất hiện trong danh sách của space. Lệnh cf service với tên đã xóa sẽ không tìm thấy instance.

Nếu delete-service trả về ngay nhưng operation chưa hoàn tất, dùng --wait hoặc xem lại trạng thái operation. Không suy luận provider resource đã bị xóa chỉ từ việc CLI đã gửi request.

Nếu service vẫn còn hoặc delete failed:

- Đọc last operation và message.
- Ghi nhận operation/correlation reference.
- Kiểm tra broker có nhận deprovision request hay không.
- Kiểm tra provider resource còn tồn tại hay đã chuyển sang trạng thái deleting.
- Kiểm tra binding hoặc service key nào đang ngăn xóa.
- Đối soát operation chưa rõ kết quả trước khi gửi lại lệnh.

Không tự xóa trực tiếp resource ở provider rồi để Cloud Controller giữ instance record cũ, trừ khi đang thực hiện quy trình recovery có kiểm soát.

## 14. Dọn binding mồ côi khi instance bị xóa ngoài Cloud Foundry

Binding có thể trở thành orphan nếu service instance bị xóa trực tiếp ngoài Cloud Foundry, ví dụ operator xóa tài nguyên qua broker hoặc hạ tầng trước khi Cloud Controller được cập nhật. Khi đó, Cloud Foundry có thể còn binding record không còn service instance tương ứng.

Cloud Foundry CLI có lệnh:

~~~bash
cf cleanup-outdated-service-bindings
~~~

Lệnh này tìm và loại bỏ binding cũ không còn service instance tương ứng. Theo tài liệu Cloud Foundry, lệnh này nhằm dọn binding mồ côi và không ảnh hưởng binding đang hoạt động. Lệnh được bổ sung trong cf CLI v8.18.0; kiểm tra phiên bản trước khi dùng.

Đây là công cụ dọn dữ liệu platform sau khi service instance đã bị xóa ngoài Cloud Foundry. Nó không thay thế quy trình unbind bình thường và không nên chạy để thay cho delete-service.

### Phân biệt với purge-service-instance

cf purge-service-instance là lệnh quản trị đặc biệt để xóa service instance và các child record khỏi database Cloud Controller mà không gọi service broker. Nó chỉ phù hợp với tình huống broker không còn khả dụng hoặc không thể phản hồi hợp lệ, và tài nguyên provider đã được xóa/đối soát theo quy trình recovery.

Purge không gọi deprovision đến broker. Nếu dùng khi provider resource vẫn tồn tại, Cloud Foundry có thể mất metadata trong khi tài nguyên thật vẫn chạy và tiếp tục phát sinh chi phí. Không dùng purge như cách thông thường để xóa service.

## 15. Ví dụ quy trình vận hành hoàn chỉnh

Giả sử team chuẩn bị loại bỏ PostgreSQL service instance orders-db khỏi ứng dụng orders-api.

### Bước 1: Target đúng space và kiểm tra service

~~~bash
cf target -o commerce -s production
cf services
cf service orders-db
~~~

Xác nhận offering, plan, broker, bound apps và last operation. Nếu create hoặc update vẫn in progress, chờ operation đó kết thúc trước khi bắt đầu deprovision.

### Bước 2: Kiểm tra consumer và kế hoạch dữ liệu

Xác nhận orders-api đã chuyển sang database mới hoặc đã dừng traffic. Kiểm tra service keys và các space được share. Nếu cần lưu dữ liệu, hoàn tất export/backup theo chính sách của service.

### Bước 3: Hủy binding

~~~bash
cf unbind-service orders-api orders-db --wait
cf restart orders-api
~~~

Sau khi ứng dụng nhận cấu hình mới, kiểm tra lại:

~~~bash
cf service orders-db
~~~

Xác nhận orders-api không còn nằm trong bound apps.

### Bước 4: Xóa service keys hoặc route binding còn lại

Nếu có service key không còn sử dụng:

~~~bash
cf delete-service-key orders-db reporting-key --wait
~~~

Nếu service được bind vào route, dùng cf unbind-route-service với domain, hostname và service instance tương ứng. Nếu instance được share, xử lý từng space nhận share trước khi xóa.

### Bước 5: Deprovision và chờ hoàn tất

~~~bash
cf delete-service orders-db --wait
~~~

Nếu không dùng --wait, có thể theo dõi sau đó bằng:

~~~bash
cf service orders-db
cf services
~~~

### Bước 6: Xác nhận

Kiểm tra instance đã biến mất khỏi Cloud Foundry và broker đã xác nhận deprovision. Nếu provider có tác vụ xóa bất đồng bộ, tiếp tục theo dõi đến trạng thái cuối cùng. Lưu operation reference và kết quả theo quy trình audit vận hành.

## 16. Ánh xạ lệnh CF CLI với thao tác OSB API

Bảng dưới đây giúp người học liên hệ lệnh CLI với trách nhiệm của broker:

| Lệnh CLI | Ý nghĩa với người dùng | Thao tác broker thường tương ứng |
|---|---|---|
| cf services | Liệt kê service instance | Cloud Controller đọc metadata và trạng thái operation |
| cf service NAME | Xem chi tiết và last operation | Cloud Controller truy vấn trạng thái instance/broker |
| cf create-service | Tạo service instance | OSB provision |
| cf update-service | Cập nhật instance | OSB update |
| cf bind-service | Cấp binding cho app | OSB create service binding |
| cf unbind-service | Thu hồi binding của app | OSB delete service binding |
| cf delete-service | Deprovision instance | OSB deprovision |
| cf service-keys | Liệt kê service keys | Cloud Controller quản lý các binding/key tương ứng |
| cf delete-service-key | Xóa service key | Thu hồi binding/key tương ứng qua platform và broker |

Tên endpoint cụ thể phụ thuộc OSB API version mà platform sử dụng. Với OSB API v2, các thao tác chính thường đi qua PUT/DELETE service instance và service binding endpoints. Với thao tác async được hỗ trợ, broker trả response theo contract và platform truy vấn last_operation.

cf CLI không gọi thẳng Java method trong Spring broker. Nó gọi Cloud Controller; Cloud Controller mới là thành phần giao tiếp với broker. Vì vậy, khi lệnh CLI báo lỗi, cần xác định lỗi phát sinh ở CLI, Cloud Controller, broker hay provider.

## 17. Xử lý các lỗi thường gặp

### Service đang có operation khác

Nếu cf service hiển thị create/update/delete in progress, chờ operation hoàn tất. Không gửi nhiều lệnh update hoặc delete cho cùng instance khi trạng thái chưa rõ.

~~~bash
cf service orders-db
cf services --wait
~~~

Nếu operation bị treo lâu, kiểm tra broker logs và provider operation bằng reference tương ứng. Không xóa instance record bằng tay để làm mất trạng thái đang chạy.

### Unbind thất bại

Kiểm tra:
- App và service instance có thuộc đúng space không.
- Caller có quyền thao tác không.
- Binding có tồn tại không.
- Provider có thể revoke credential không.
- Broker có đang gặp timeout hoặc rate limit không.

Nếu provider đã revoke nhưng broker chưa lưu được kết quả, broker cần reconciliation trước khi gửi lại side effect. Request unbind lặp phải được xử lý idempotent.

### Delete service thất bại

Kiểm tra bound apps, route bindings, service keys và sharing. Sau đó đọc last operation. Nếu broker báo lỗi provider, dùng operation reference để tra cứu provider; không chạy purge chỉ để làm biến mất dòng service khỏi cf services.

### CLI không tìm thấy service

Kiểm tra target organization/space, tên service và quyền truy cập. Nếu instance được share từ space khác, kiểm tra nguồn share và space đích.

### App vẫn dùng credentials cũ sau unbind

Restart hoặc re-push ứng dụng theo credential delivery method. Kiểm tra lại VCAP_SERVICES trong runtime theo cách không làm lộ secret. Không in toàn bộ environment hoặc credentials ra log/ticket.

## 18. Quyền truy cập và bảo mật khi vận hành

Các lệnh service cần role phù hợp trong organization/space. Không cấp quyền admin rộng chỉ để một ứng dụng hoặc người dùng có thể unbind service của chính họ.

Các nguyên tắc:

- Target đúng API, organization và space trước khi chạy lệnh.
- Kiểm tra consumer trước khi unbind hoặc delete.
- Không đưa credentials vào command arguments nếu CLI có thể lưu command history.
- Không chia sẻ output có credentials hoặc dashboard URL nhạy cảm.
- Không dùng force để bỏ qua bước kiểm tra nghiệp vụ.
- Không dùng purge nếu chưa xác minh broker/provider resource đã được xử lý.
- Ghi operation reference, thời điểm, actor và kết quả vào audit.
- Giới hạn quyền truy cập log broker/provider và che credentials.
- Kiểm tra backup/retention trước khi xóa service có dữ liệu quan trọng.

Nếu cần tự động hóa, script nên kiểm tra exit code của cf CLI và xác minh trạng thái sau lệnh. Không coi việc process kết thúc với exit code 0 là bằng chứng duy nhất rằng provider đã hoàn tất xóa nếu lệnh không dùng --wait.

## 19. Kiểm thử quy trình CF CLI với service broker

Trong môi trường test hoặc staging, cần xác nhận cả trạng thái Cloud Controller lẫn side effect provider.

| Kịch bản | Kết quả mong đợi |
|---|---|
| cf services khi instance đã provision | Hiển thị service và last operation succeeded |
| cf service NAME | Hiển thị đúng broker, plan, operation state và timestamps |
| Provision bất đồng bộ | CLI hiển thị in progress rồi succeeded/failed |
| cf services --wait | Chờ các operation đang chạy trong scope được liệt kê |
| cf unbind-service APP SERVICE | Binding bị xóa và app không còn binding metadata |
| Restart app sau unbind | Runtime nhận môi trường binding đã cập nhật |
| cf delete-service SERVICE --wait | Deprovision hoàn tất trước khi lệnh trả về |
| Delete khi còn binding | Hành vi theo Cloud Controller/API và policy của broker được xác nhận |
| Provider timeout trong deprovision | Broker giữ state và reconcile, không báo xóa thành công giả |
| Service key còn tồn tại | Operator nhận diện và xử lý key riêng |
| Route binding còn tồn tại | Operator dùng lệnh unbind route phù hợp |
| Instance được share | Không xóa khi sharing/consumer chưa được xử lý |
| Cleanup outdated bindings | Chỉ dọn binding mồ côi theo điều kiện hỗ trợ |
| Purge service instance | Không gọi broker; chỉ dùng trong quy trình recovery được kiểm soát |

Test nên kiểm tra provider principal, database/resource thực tế và broker state, không chỉ kiểm tra output text của CLI. Đặc biệt, sau unbind cần xác nhận đúng credential bị revoke và binding khác của cùng instance vẫn hoạt động.

## 20. Nguyên tắc vận hành trong Spring Cloud Service Broker

Khi Cloud Foundry gọi broker, các lệnh CLI là giao diện vận hành của platform. Broker cần xử lý đúng các request provision, bind, unbind và deprovision; lưu operation state bền vững; trả last operation chính xác; và bảo đảm retry không tạo hoặc xóa tài nguyên trùng.

Với thao tác dài, broker có thể xử lý bất đồng bộ theo OSB API. Cloud Controller theo dõi operation và cf CLI hiển thị trạng thái đó qua cf service hoặc cf services. Broker nên cung cấp mô tả operation ngắn, an toàn và có ích cho người vận hành; không đưa credentials hoặc dữ liệu khách hàng vào message.

Khi unbind, thu hồi đúng quyền của consumer và giữ service instance nếu các consumer khác còn sử dụng. Khi delete, kiểm tra binding, route, service key, sharing và chính sách dữ liệu trước khi deprovision. Sau khi lệnh hoàn tất, đối soát Cloud Controller với broker và provider. Quy trình này giúp operator quản lý service instance bằng CF CLI có kiểm soát, còn broker duy trì trạng thái nhất quán trong toàn bộ vòng đời tài nguyên.

## Tài liệu tham khảo

- [Cloud Foundry Documentation – Managing service instances with the cf CLI](https://docs.cloudfoundry.org/devguide/services/managing-services.html)
- [Cloud Foundry Documentation – Delivering service credentials to an app](https://docs.cloudfoundry.org/devguide/services/application-binding.html)
- [Cloud Foundry CLI v8 Reference – unbind-service](https://cli.cloudfoundry.org/en-US/v8/unbind-service.html)
- [Cloud Foundry CLI v8 Reference – delete-service](https://cli.cloudfoundry.org/en-US/v8/delete-service.html)
- [Cloud Foundry CLI v8 Reference](https://cli.cloudfoundry.org/en-US/v8/)


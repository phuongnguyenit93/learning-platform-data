# HTTP 422 cho AsyncRequired và các trường hợp không thể xử lý

Open Service Broker API (OSB API) dùng HTTP 422 Unprocessable Entity để biểu diễn một số yêu cầu có cấu trúc hợp lệ nhưng broker không thể xử lý theo điều kiện hoặc khả năng mà giao thức quy định. Trường hợp quan trọng nhất là **AsyncRequired**: broker chỉ có thể hoàn tất một thao tác bằng xử lý bất đồng bộ, trong khi nền tảng chưa cho phép cách xử lý đó.

Với service broker xây dựng bằng Spring Cloud Open Service Broker, chọn đúng HTTP status và mã lỗi OSB giúp nền tảng biết cần sửa request, chờ operation, thử lại hay xử lý sự cố phụ thuộc. Không nên gom mọi lỗi nghiệp vụ vào 422. Một request sai JSON, một operation đang chạy, một caller không có quyền và một backend đang unavailable có nguyên nhân cũng như cách phục hồi khác nhau.

## 1. Ý nghĩa của HTTP 422 trong OSB

HTTP 422 cho biết server hiểu nội dung request và cú pháp của request có thể hợp lệ, nhưng không thể thực hiện yêu cầu theo điều kiện hiện tại hoặc theo ràng buộc của hợp đồng. OSB bổ sung mã lỗi trong body để client nhận biết nguyên nhân cụ thể.

Response lỗi thường có cấu trúc:

~~~json
{
  "error": "AsyncRequired",
  "description": "Thao tác này cần xử lý bất đồng bộ. Hãy gửi lại với accepts_incomplete=true."
}
~~~

Trường **error** là mã lỗi máy có thể xử lý; **description** là thông tin ngắn giúp người vận hành hoặc client hiểu tình huống. Nội dung mô tả không nên chứa stack trace, SQL, token, credentials hoặc chi tiết hạ tầng nội bộ.

Không được suy ra rằng mọi lỗi “không hợp lệ về nghiệp vụ” đều phải trả 422. Cần dùng status và error code theo đúng trường hợp OSB định nghĩa và phiên bản giao thức mà broker hỗ trợ.

## 2. AsyncRequired là gì?

Một số thao tác service instance có thể hoàn tất ngay trong thời gian xử lý HTTP; một số thao tác cần nhiều thời gian vì phải tạo database, cấp volume, cấu hình network, di chuyển dữ liệu hoặc gọi nhiều API cloud. OSB cho phép nền tảng báo trước liệu nó có chấp nhận xử lý bất đồng bộ hay không bằng query parameter **accepts_incomplete**.

Ví dụ request provision không chấp nhận async:

~~~http
PUT /v2/service_instances/instance-123?accepts_incomplete=false
X-Broker-API-Version: 2.17
Content-Type: application/json

{
  "service_id": "postgres-service",
  "plan_id": "ha-plan",
  "parameters": {
    "storageGb": 1000,
    "replicas": 3
  }
}
~~~

Nếu broker biết thao tác này cần worker hoặc tiến trình kéo dài và không thể hoàn tất đồng bộ, nó phải từ chối bằng 422 với mã **AsyncRequired**. Nền tảng có thể gửi lại request với **accepts_incomplete=true** nếu hỗ trợ async.

**accepts_incomplete** không có nghĩa nền tảng bắt buộc broker phải chạy async. Nó chỉ cho phép broker trả kết quả accepted khi cần. Nếu thao tác vẫn có thể hoàn tất đồng bộ, broker có thể xử lý và trả kết quả đồng bộ.

## 3. Phân biệt 422 AsyncRequired với 202 Accepted

Hai status này biểu diễn hai thời điểm khác nhau:

| Response | Ý nghĩa | Operation đã được broker chấp nhận? |
|---|---|---:|
| 422 AsyncRequired | Broker cần async nhưng request không cho phép | Không |
| 202 Accepted | Broker đã nhận thao tác async và sẽ tiếp tục xử lý | Có |
| 200 OK | Thao tác đã hoàn tất đồng bộ | Có, và đã hoàn tất |

Khi trả 422, broker chưa nhận trách nhiệm chạy operation async theo request đó. Không nên trả một operation key trong body 422 như thể công việc đã được accepted. Nền tảng cần gửi lại request theo cách cho phép async.

Khi trả 202, broker phải lưu operation bền vững, ghi trạng thái instance phù hợp và bảo đảm worker/reconciler có thể tiếp tục sau khi process restart. Response thường chứa operation key để nền tảng polling endpoint last operation.

Một luồng đúng:

    Request accepts_incomplete=false
        -> Broker xác định cần async
        -> 422 AsyncRequired
        -> Platform gửi lại accepts_incomplete=true
        -> Broker lưu operation + outbox
        -> 202 Accepted + operation key
        -> Worker thực hiện công việc
        -> Platform polling last_operation
        -> succeeded hoặc failed

Không trả 202 chỉ vì backend chậm nếu broker chưa lưu operation và chưa có cơ chế tiếp tục. Không trả 422 sau khi đã tạo tài nguyên hoặc dispatch worker mà không có khả năng bù trừ; quyết định sync/async phải được đưa ra trước khi chấp nhận tác dụng phụ không thể đảo ngược.

## 4. Những thao tác có thể cần AsyncRequired

OSB dùng **accepts_incomplete** cho các thao tác vòng đời service instance có thể chạy bất đồng bộ, thường gồm:

- Provision service instance.
- Update service instance.
- Deprovision service instance.

Ví dụ:

| Thao tác | Công việc có thể kéo dài | Khi nào trả AsyncRequired |
|---|---|---|
| Provision | Tạo database, cluster, volume, replica và endpoint | Request không chấp nhận async nhưng broker không thể provision đồng bộ |
| Update | Resize storage, chuyển plan, migrate dữ liệu hoặc thay đổi topology | Update cần worker nhưng request không chấp nhận async |
| Deprovision | Backup cuối, revoke nhiều tài nguyên, xóa volume và network | Cleanup cần async nhưng request không chấp nhận async |

Binding và unbinding có hợp đồng riêng. Không tự mở rộng **accepts_incomplete** sang bind/unbind chỉ vì implementation dùng Reactor hoặc worker. Chỉ hỗ trợ async cho binding nếu phiên bản OSB, capability và Spring Cloud Open Service Broker đang dùng định nghĩa rõ hành vi đó.

## 5. Quyết định sync hay async trước khi tạo tác dụng phụ

Broker nên có policy xác định liệu request có thể hoàn tất đồng bộ:

1. Xác thực caller và parse request.
2. Đọc service/plan và kiểm tra capability.
3. Validate parameters, entitlement và state hiện tại.
4. Ước lượng hoặc xác định execution mode theo loại operation, plan, kích thước tài nguyên và khả năng backend.
5. Nếu cần async nhưng **accepts_incomplete** không true, trả **AsyncRequired**.
6. Nếu async được chấp nhận, ghi operation và outbox trong transaction rồi trả 202.
7. Nếu xử lý đồng bộ, thực hiện thao tác và trả response cuối khi đã xác nhận kết quả.

Không nên tạo resource rồi mới phát hiện request không chấp nhận async. Nếu cần reservation để đánh giá hoặc bảo vệ quota, reservation đó phải có thể rollback/giải phóng an toàn trước khi trả 422.

Ví dụ pseudocode:

~~~java
public Mono<CreateServiceInstanceResponse> provision(
        ProvisionRequest request) {

    return validator.validate(request)
            .then(executionPolicy.requiresAsync(request))
            .flatMap(asyncRequired -> {
                if (asyncRequired && !request.acceptsIncomplete()) {
                    return Mono.error(new AsyncRequiredException(
                            "Provisioning requires asynchronous processing"));
                }

                if (asyncRequired) {
                    return operationService.accept(request)
                            .map(responseMapper::toAcceptedResponse);
                }

                return provisionService.executeSynchronously(request)
                        .map(responseMapper::toCompletedResponse);
            });
}
~~~

Đây là pseudocode minh họa; **AsyncRequiredException**, request và response mapper có thể mang tên khác trong ứng dụng. Cần bảo đảm **executionPolicy** không tự tạo tác dụng phụ và **operationService.accept** lưu operation bền vững trước khi response accepted được gửi.

## 6. Xử lý khi accepts_incomplete bị thiếu hoặc false

Nếu query parameter bị bỏ qua, broker phải xử lý theo semantics của OSB: nền tảng chưa cho phép thao tác async. Không mặc định coi giá trị thiếu là true.

| Giá trị request | Ý nghĩa | Nếu broker cần async |
|---|---|---|
| Không truyền accepts_incomplete | Không chấp nhận async | Trả 422 AsyncRequired |
| accepts_incomplete=false | Không chấp nhận async | Trả 422 AsyncRequired |
| accepts_incomplete=true | Chấp nhận async | Có thể trả 202 nếu cần async |

Nếu request cho phép async nhưng broker hoàn tất nhanh, trả response thành công đồng bộ vẫn hợp lệ. Client cho phép async không bắt buộc broker phải tạo operation.

Không parse giá trị tùy ý như yes, 1 hoặc TRUE theo cách riêng nếu framework đã định nghĩa parser cho query parameter. Để framework xử lý contract và chỉ chuyển giá trị đã parse vào application service.

## 7. Các trường hợp 422 khác theo hợp đồng OSB

Ngoài **AsyncRequired**, OSB có thể dùng 422 cho một số điều kiện ngữ nghĩa được định nghĩa bằng error code riêng. Ví dụ phụ thuộc vào thao tác và phiên bản API:

| Error code | Tình huống điển hình | Ý nghĩa |
|---|---|---|
| RequiresApp | Service/binding yêu cầu thông tin ứng dụng nhưng request không cung cấp context cần thiết | Nền tảng cần gửi app context theo hợp đồng |
| RequiresRoute | Route service binding yêu cầu route nhưng request thiếu thông tin route | Request chưa đáp ứng điều kiện tạo route binding |
| ServiceInstanceSharingNotSupported | Nền tảng yêu cầu chia sẻ instance nhưng broker/service không hỗ trợ | Không thể thực hiện kiểu sử dụng instance được yêu cầu |
| MaintenanceInfoConflict | Thông tin maintenance trong request xung đột với version/policy mà broker chấp nhận | Nền tảng cần đồng bộ thông tin maintenance |

Chỉ dùng các mã lỗi này khi đúng điều kiện và phiên bản OSB hỗ trợ. Không tự tạo tên error code gần giống để biểu diễn lỗi nội bộ. Với các lỗi concurrency, duplicate resource hoặc operation đang chạy, cần kiểm tra status/error mapping cụ thể của OSB và framework; nhiều trường hợp thuộc HTTP 409 Conflict chứ không phải 422.

## 8. Phân biệt 422 với các HTTP status khác

Ánh xạ lỗi đúng giúp nền tảng chọn hành động phù hợp:

| HTTP status | Khi nào dùng | Hành động client thường thực hiện |
|---|---|---|
| 400 Bad Request | JSON sai, thiếu field bắt buộc về cú pháp hoặc request không parse được | Sửa request trước khi gửi lại |
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực | Xác thực lại |
| 403 Forbidden | Caller đã xác thực nhưng không có quyền | Không retry nếu quyền chưa thay đổi |
| 404 Not Found | Service/instance/binding không tồn tại trong ngữ cảnh thao tác | Kiểm tra định danh và trạng thái |
| 409 Conflict | Resource đã tồn tại, operation xung đột hoặc thay đổi không tương thích theo contract | Đọc lại trạng thái hoặc chờ operation hiện tại |
| 410 Gone | Instance/binding đã được thu hồi theo semantics OSB | Kết thúc tham chiếu đến resource đã mất |
| 422 Unprocessable Entity | Request hiểu được nhưng không thể xử lý theo điều kiện giao thức, ví dụ AsyncRequired | Sửa điều kiện request hoặc gửi lại với capability phù hợp |
| 429 Too Many Requests | Rate limit đang áp dụng | Retry theo policy/backoff nếu có |
| 500 Internal Server Error | Lỗi nội bộ không dự kiến | Báo lỗi; retry có kiểm soát tùy operation |
| 502/503/504 | Backend gateway, dependency unavailable hoặc timeout | Retry có backoff nếu thao tác an toàn |

Không trả 422 cho database timeout, Kubernetes API unavailable, secret manager outage hoặc network failure. Những tình huống đó là lỗi phụ thuộc/hạ tầng và cần được ánh xạ sang nhóm 5xx phù hợp. Không trả 422 cho JSON sai cú pháp; đó là lỗi 400.

## 9. Validation lỗi và điều kiện không thể xử lý

Một request có thể hợp lệ về JSON nhưng không hợp lệ về nghiệp vụ. Tuy nhiên, phải xác định lỗi thuộc nhóm nào:

- Sai kiểu parameter, giá trị ngoài schema hoặc thiếu trường bắt buộc: thường là lỗi invalid request/parameters theo mapping của OSB/framework.
- Không có quyền dùng service hoặc plan: authorization error.
- Instance đang có operation không tương thích: conflict theo semantics đã định nghĩa.
- Request cần async nhưng caller không cho phép: **AsyncRequired**.
- Backend tạm thời không thể xử lý: dependency/server error.
- Request yêu cầu capability mà broker không hỗ trợ: dùng error/status được OSB định nghĩa cho capability đó, không tự động chuyển thành AsyncRequired.

Không dùng 422 làm catch-all cho mọi exception nghiệp vụ. Một mã lỗi cụ thể giúp platform automation phân biệt trường hợp có thể sửa bằng cách thay request với trường hợp cần chờ hoặc liên hệ vận hành.

## 10. Error response phải ổn định và an toàn

OSB error response dùng mã lỗi và mô tả:

~~~json
{
  "error": "AsyncRequired",
  "description": "Broker cần xử lý thao tác này bất đồng bộ. Hãy gửi lại request với accepts_incomplete=true."
}
~~~

Các nguyên tắc:

- **error** dùng mã ổn định theo hợp đồng OSB.
- **description** ngắn, không thay đổi tùy stack trace hoặc tên lớp Java.
- Không trả operation ID nếu request chưa được accepted.
- Không trả password, token, private key, internal endpoint hoặc thông tin tenant khác.
- Không echo nguyên parameters do client gửi.
- Ghi correlation ID trong log nội bộ để support tra cứu.

Nếu framework tự ánh xạ exception sang OSB error body, hãy dùng extension point/exception tương ứng của phiên bản framework. Tránh tạo ResponseEntity riêng trong service implementation làm lệch contract chuẩn của Spring Cloud Open Service Broker.

## 11. Tích hợp AsyncRequired trong Spring Cloud Open Service Broker

Application service nên quyết định execution mode; OSB handler chỉ chuyển request và trả kết quả. Một mô hình phân lớp:

| Thành phần | Trách nhiệm |
|---|---|
| OSB handler | Nhận request, lấy accepts_incomplete đã parse và chuyển command |
| Execution policy | Xác định operation có cần async hay không |
| Validator | Kiểm tra parameters, plan, entitlement và state |
| Operation service | Lưu operation, instance transition và outbox |
| Worker | Thực hiện provision/update/deprovision dài |
| Error mapper | Ánh xạ AsyncRequired và các domain error sang OSB response |

Ví dụ handler:

~~~java
@Override
public Mono<CreateServiceInstanceResponse> createServiceInstance(
        CreateServiceInstanceRequest request) {

    ProvisionCommand command = requestMapper.toCommand(request);

    return provisionApplicationService.execute(
            command,
            request.isAcceptsIncomplete());
}
~~~

Đây là pseudocode. Tên getter và chữ ký method phụ thuộc phiên bản Spring Cloud Open Service Broker. Có thể framework biểu diễn AsyncRequired bằng exception chuyên biệt; nếu không, ứng dụng có thể dùng domain exception và cấu hình error mapping theo extension point được hỗ trợ. Không tự đoán tên class hoặc method nếu chưa đối chiếu dependency version.

Ví dụ application logic:

~~~java
public Mono<CreateServiceInstanceResponse> execute(
        ProvisionCommand command,
        boolean acceptsIncomplete) {

    return validationService.validate(command)
            .then(executionPolicy.requiresAsync(command))
            .flatMap(required -> {
                if (required && !acceptsIncomplete) {
                    return Mono.error(new AsyncRequiredException());
                }
                if (required) {
                    return operationService.accept(command)
                            .map(responseMapper::accepted);
                }
                return synchronousProvisioner.provision(command)
                        .map(responseMapper::completed);
            });
}
~~~

Validation và execution policy nên chạy trước khi tạo tác dụng phụ không thể đảo ngược. Nếu cần reserve quota trước, reservation phải có thể rollback an toàn khi trả AsyncRequired.

## 12. Operation state khi request được chấp nhận async

Khi **accepts_incomplete=true** và broker chọn xử lý async, cần ghi state trước khi trả 202:

1. Tạo operation ID.
2. Tạo operation record ở trạng thái PENDING.
3. Chuyển instance sang PROVISIONING, UPDATING hoặc DEPROVISIONING.
4. Ghi outbox event trong cùng transaction.
5. Commit transaction.
6. Trả 202 cùng operation key.
7. Worker nhận event, claim operation và thực hiện backend workflow.
8. Ghi terminal result để endpoint last operation trả succeeded hoặc failed.

Nếu ghi operation thất bại, không trả 202. Nếu outbox publisher chưa gửi được message, record outbox vẫn phải được giữ để retry. Nếu worker timeout sau khi backend có thể đã thực hiện tác dụng phụ, cần reconcile trước khi retry.

## 13. Khi request không cho phép async nhưng broker đã chuẩn bị công việc

Thiết kế tốt sẽ quyết định AsyncRequired trước khi dispatch worker. Tuy nhiên, một số hệ thống cần tạo reservation hoặc chuẩn bị metadata trước khi biết chắc thao tác có thể hoàn tất đồng bộ.

Nếu đã tạo reservation nhưng chưa chấp nhận operation:

- Giải phóng reservation hoặc rollback transaction trước khi trả 422.
- Không để instance ở trạng thái PROVISIONING/UPDATING nếu không có operation chịu trách nhiệm.
- Không để outbox event đã commit khiến worker chạy sau khi response 422 đã được gửi.
- Không xóa resource mà request khác có thể đã tạo hợp lệ; chỉ bù trừ phần thuộc request hiện tại.

Nếu backend đã nhận lệnh và có thể đã tạo tài nguyên, không thể đơn giản trả 422 rồi bỏ qua. Broker cần reconcile/compensate và có thể phải ghi nhận sự cố nội bộ. Vì vậy, execution mode và điểm bắt đầu side effect cần được thiết kế rõ.

## 14. Request lặp sau 422 và idempotency

422 AsyncRequired có nghĩa request chưa được chấp nhận để chạy async. Khi nền tảng gửi lại với accepts_incomplete=true, broker có thể tạo operation mới cho lần được chấp nhận đó.

Tuy nhiên, vẫn phải xử lý request retry an toàn:

- Nếu request 422 không tạo side effect, request gửi lại có thể đi qua validation và execution policy từ đầu.
- Nếu đã có reservation tạm, phải xác nhận reservation được rollback trước khi xử lý lại.
- Nếu một request tương đương đã được accepted từ một request khác, kiểm tra operation active và idempotency record để tránh tạo operation/resource trùng.
- Nếu cùng idempotency key nhưng payload khác, từ chối conflict thay vì replay kết quả không tương thích.

Không dùng 422 để che giấu một operation đã được accepted trước đó. Nếu operation đang chạy, trả response phù hợp với trạng thái operation hiện tại theo contract, thường là conflict hoặc thông tin operation đã tồn tại tùy endpoint và framework.

## 15. Kiểm thử AsyncRequired và các lỗi 422

Test cần xác minh status, error code và việc không có side effect ngoài ý muốn:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Provision cần async, accepts_incomplete thiếu | 422, error AsyncRequired, không tạo operation active |
| Provision cần async, accepts_incomplete=false | 422 AsyncRequired |
| Provision cần async, accepts_incomplete=true | 202 và operation được lưu bền vững |
| Provision hoàn tất sync, accepts_incomplete=false | Response thành công đồng bộ |
| Provision hoàn tất sync, accepts_incomplete=true | Có thể vẫn trả thành công đồng bộ |
| Update cần async nhưng caller không chấp nhận | 422, không thay đổi plan/current state |
| Deprovision cần async nhưng caller không chấp nhận | 422, không bắt đầu cleanup bất đồng bộ |
| Request thiếu app context cho service yêu cầu app | Mã lỗi RequiresApp theo contract hỗ trợ |
| Route binding thiếu route context | Mã lỗi RequiresRoute theo contract hỗ trợ |
| Yêu cầu share instance không được hỗ trợ | Mã lỗi sharing tương ứng theo contract |
| JSON sai cú pháp | 400, không phải 422 |
| Operation đang chạy và request mới xung đột | Conflict mapping phù hợp, không giả thành AsyncRequired |
| Backend unavailable | 5xx phù hợp, không phải 422 |
| Retry sau 422 | Không còn reservation hoặc operation mồ côi từ lần bị từ chối |

Contract test nên kiểm tra đúng JSON body:

~~~json
{
  "error": "AsyncRequired",
  "description": "..."
}
~~~

Integration test cần xác minh khi trả 422 thì không có active operation, outbox event chưa dispatch và instance state không bị kẹt ở trạng thái trung gian. Khi trả 202, operation phải đọc được ngay qua last operation endpoint.

## 16. Quan sát và vận hành

Nên theo dõi:

- Số response 422 theo error code và operation type.
- Tỷ lệ request bị từ chối vì AsyncRequired.
- Số request gửi lại với accepts_incomplete=true sau 422.
- Số operation accepted bằng 202 và thời gian hoàn tất.
- Số operation mồ côi, reservation chưa giải phóng và outbox event pending.
- Tỷ lệ lỗi 400, 409, 422 và 5xx theo endpoint.
- Số lần request bị conflict do operation khác đang chạy.

Log cần có correlation ID, instance ID, operation type, service ID/plan ID và error code đã chuẩn hóa. Không ghi credentials hoặc toàn bộ parameters. Metric label nên dùng tập giá trị giới hạn; không dùng instance ID hay tenant ID làm label có cardinality không giới hạn.

Nếu tỷ lệ AsyncRequired cao bất thường, có thể nền tảng thường xuyên gửi request không chấp nhận async trong khi service plan cần thao tác dài. Đây là tín hiệu để kiểm tra cấu hình platform integration, tài liệu service và thời gian xử lý của backend.

## 17. Những sai lầm thường gặp

- Trả 202 dù request không có accepts_incomplete=true.
- Trả 422 nhưng vẫn dispatch worker và để operation chạy ngầm.
- Coi accepts_incomplete=true là bắt buộc phải chạy async.
- Coi giá trị query parameter bị thiếu là true.
- Dùng 422 cho JSON sai, authorization failure hoặc backend timeout.
- Dùng AsyncRequired cho mọi lỗi không xử lý được.
- Trả operation key trong response 422 như thể request đã được accepted.
- Tạo reservation/resource trước khi xác định execution mode mà không có rollback.
- Trả 202 trước khi operation và outbox được lưu bền vững.
- Ánh xạ mọi exception thành cùng một error code.
- Dùng mã 422 riêng không nằm trong contract OSB hoặc không được platform hiểu.
- Đưa stack trace, credentials hoặc thông tin nội bộ vào description.

## Kết luận

HTTP 422 AsyncRequired là tín hiệu cho biết broker cần xử lý bất đồng bộ nhưng nền tảng chưa cho phép điều đó qua accepts_incomplete. Request bị từ chối chưa phải operation async đã được accepted; nền tảng cần gửi lại với giá trị true nếu hỗ trợ. Khi đã chấp nhận async, broker phải lưu operation và outbox trước khi trả 202. Các lỗi 422 khác chỉ nên dùng khi error code và điều kiện tương ứng được OSB định nghĩa; lỗi cú pháp, authorization, conflict và dependency outage phải giữ đúng status riêng. Tách execution policy, application service và error mapper trong Spring Cloud Open Service Broker giúp broker trả phản hồi nhất quán, tránh operation mồ côi và cho phép nền tảng tự động phục hồi đúng cách.

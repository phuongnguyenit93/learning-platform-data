# Thứ tự hủy binding, xóa instance và xử lý thao tác đồng thời

Một service instance có thể được nhiều ứng dụng sử dụng thông qua các service binding. Vì vậy, thu hồi instance không đơn giản là gọi lệnh xóa database hoặc volume. Broker phải bảo đảm mọi binding liên quan đã được thu hồi trước, credentials của từng consumer không còn hiệu lực và không có request bind mới chen vào trong lúc instance đang bị xóa.

Trong Open Service Broker API (OSB API), vòng đời này có thứ tự rõ ràng: nền tảng hủy từng binding bằng unbind, sau đó mới deprovision service instance. Broker vẫn phải tự bảo vệ thứ tự đó vì request có thể đến đồng thời, được retry hoặc đi qua nhiều replica của broker. Với module SPRING_CLOUD_SERVICE_BROKER, cần quản lý binding và instance như hai phần liên quan của cùng một vòng đời, dùng state store và cơ chế đồng bộ để tránh race condition.

## 1. Quan hệ giữa service instance và service binding

Service instance đại diện tài nguyên dịch vụ đã được cấp phát, ví dụ một database PostgreSQL. Service binding đại diện quyền truy cập của một consumer, thường là một ứng dụng, vào instance đó. Một instance có thể có nhiều binding:

    ServiceInstance: postgres-instance-123
      ├── Binding: orders-api
      ├── Binding: reporting-worker
      └── Binding: billing-service

Mỗi binding có thể sở hữu database user, token, secret hoặc policy riêng. Vì vậy, khi hủy một binding, broker chỉ thu hồi quyền của consumer đó. Khi hủy instance, broker mới thu hồi tài nguyên nền tảng mà tất cả binding cùng sử dụng.

| Đối tượng | Vòng đời | Tài nguyên điển hình |
|---|---|---|
| Service instance | Provision, update, deprovision | Database, cache, volume, cluster, endpoint |
| Service binding | Bind, unbind | Database user, access token, secret, role, grant |

Không nên nhầm việc xóa binding record với việc thu hồi quyền truy cập. Nếu broker xóa bản ghi nhưng database user hoặc token vẫn hoạt động, consumer vẫn có thể truy cập tài nguyên. Ngược lại, không nên xóa database khi vẫn còn consumer hợp lệ đang dùng nó.

## 2. Thứ tự vòng đời theo OSB

Luồng thu hồi bình thường gồm hai giai đoạn:

1. Nền tảng gọi unbind cho từng binding đang gắn với instance.
2. Sau khi tất cả binding đã được thu hồi, nền tảng gọi deprovision cho instance.

Request unbind thường có dạng:

    DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}
        ?service_id={service_id}&plan_id={plan_id}

Sau khi broker xác nhận binding đã được thu hồi, nền tảng có thể tiếp tục với binding khác. Khi không còn binding, nền tảng gửi:

    DELETE /v2/service_instances/{instance_id}
        ?service_id={service_id}&plan_id={plan_id}

Theo semantics deprovision của OSB, broker phải từ chối việc deprovision khi service instance vẫn còn binding, với phản hồi 422 Unprocessable Entity. Điều này bảo vệ consumer khỏi việc mất dịch vụ đột ngột khi nền tảng chưa thu hồi binding.

Trình tự tổng quát:

    Platform
      -> Broker: DELETE binding-A
      <- Broker: 200 OK
      -> Broker: DELETE binding-B
      <- Broker: 200 OK
      -> Broker: DELETE binding-C
      <- Broker: 200 OK
      -> Broker: DELETE service instance
      <- Broker: 200 OK hoặc 202 Accepted

Nếu nền tảng gọi deprovision khi còn binding, broker kiểm tra state store và trả lỗi phù hợp; không bắt đầu xóa instance. Sau khi các binding được unbind thành công, nền tảng có thể gửi lại deprovision.

## 3. Trạng thái binding và điều kiện được xóa instance

Broker nên biểu diễn rõ trạng thái binding thay vì chỉ có một cờ exists. Ví dụ:

| Trạng thái binding | Ý nghĩa | Có chặn deprovision không? |
|---|---|---:|
| CREATING | Đang tạo principal/credential | Có |
| BOUND | Binding hoạt động | Có |
| UNBINDING | Đang thu hồi quyền truy cập | Có |
| UNBIND_FAILED | Chưa xác nhận thu hồi hoàn toàn | Có |
| UNBOUND | Đã xác nhận quyền truy cập bị thu hồi | Không |
| FAILED_CLEANED | Tạo binding thất bại và tài nguyên tạm đã được dọn | Không |

Điều kiện quan trọng là binding chỉ được xem như đã kết thúc khi broker có bằng chứng cleanup hoàn tất. Nếu một thao tác unbind timeout, broker không được tự đánh dấu UNBOUND chỉ vì request đến backend đã hết thời gian chờ. Credential có thể vẫn còn hiệu lực.

Deprovision chỉ được bắt đầu khi không còn binding ở trạng thái CREATING, BOUND, UNBINDING hoặc UNBIND_FAILED. Tùy mô hình, broker có thể dùng một tập trạng thái terminal riêng để truy vấn số binding còn hiệu lực. Không chỉ đếm binding record chưa bị xóa vật lý, vì record UNBOUND có thể được giữ để audit hoặc xử lý request lặp.

## 4. State machine của service instance

Instance cũng cần trạng thái điều khiển vòng đời:

    ACTIVE
      -> DEPROVISION_REQUESTED
      -> DEPROVISIONING
      -> DEPROVISIONED

Khi deprovision bắt đầu, trạng thái không còn cho phép tạo binding mới. Nếu có binding đang tồn tại, request bị từ chối và instance giữ nguyên ACTIVE để nền tảng thực hiện unbind.

| Trạng thái instance | Cho phép bind mới? | Cho phép unbind? | Cho phép deprovision? |
|---|---:|---:|---:|
| PROVISIONING | Không | Không | Theo quy tắc operation/provision hiện tại |
| ACTIVE | Có | Có | Chỉ khi không còn binding |
| UPDATING | Theo policy; thường chặn thay đổi vòng đời cạnh tranh | Theo policy, phải bảo toàn an toàn | Không |
| DEPROVISION_REQUESTED | Không | Có, để hoàn tất các binding còn lại nếu policy cho phép | Đang chờ kiểm tra lại điều kiện |
| DEPROVISIONING | Không | Không nhận binding mới; xử lý binding còn sót phải theo recovery policy | Đã có operation deprovision |
| DEPROVISIONED | Không | Binding cũ đã phải terminal | Trả kết quả theo semantics instance đã mất |

Một cách đơn giản và an toàn là chỉ cho phép chuyển ACTIVE sang DEPROVISIONING khi transaction kiểm tra không còn binding active. Sau khi chuyển trạng thái thành công, mọi request bind mới phải bị từ chối. Nhờ vậy, broker không rơi vào tình huống vừa xóa instance vừa tạo thêm credential cho ứng dụng.

## 5. Race condition giữa bind và deprovision

Một tình huống nguy hiểm:

1. Request bind đọc instance đang ACTIVE.
2. Request deprovision cũng đọc instance đang ACTIVE và thấy chưa có binding.
3. Deprovision bắt đầu xóa database.
4. Bind tạo database user thành công và trả credentials.
5. Ứng dụng nhận credentials nhưng database đã bị xóa hoặc đang bị xóa.

Kiểm tra trạng thái bằng một câu SELECT thông thường không ngăn được race này. Cả bind và deprovision cần đồng bộ trên cùng bản ghi instance hoặc cùng một cơ chế khóa logic.

Quy tắc quyết định:

- Nếu bind giành quyền ghi trước, binding chuyển sang CREATING/BOUND và deprovision phải nhìn thấy binding đó rồi từ chối với 422.
- Nếu deprovision giành quyền chuyển instance sang DEPROVISIONING trước, bind phải nhìn thấy trạng thái mới và bị từ chối.
- Không có thứ tự nào cho phép cả hai thao tác cùng được chấp nhận như thể độc lập.

Sơ đồ cạnh tranh:

    Bind request                  Deprovision request
         |                                |
         v                                v
    Lock instance                  Lock instance
         |                                |
    Check ACTIVE                   Check ACTIVE
         |                                |
    Insert CREATING binding        Count active bindings
         |                                |
    Commit                         Nếu count > 0: reject 422
         |                                |
    Create credentials             Không xóa instance
         |
    Mark BOUND

Nếu deprovision lấy khóa trước và commit DEPROVISIONING, request bind sau đó sẽ không vượt qua kiểm tra trạng thái. Thứ tự thực tế phụ thuộc transaction nào lấy được khóa trước; điều kiện bắt buộc là cả hai luồng cùng tuân theo một giao thức đồng bộ.

## 6. Khóa và transaction ở cấp instance

Một phương án là khóa hàng instance trong database khi bắt đầu bind, unbind hoặc deprovision. Mọi thao tác vòng đời trước hết khóa cùng bản ghi cha, rồi mới đọc hoặc cập nhật binding con.

Ví dụ pseudocode:

    @Transactional
    public BindReservation reserveBinding(
            String instanceId,
            String bindingId) {

        ServiceInstance instance =
                instanceRepository.findByIdForUpdate(instanceId)
                        .orElseThrow(InstanceNotFoundException::new);

        if (instance.status() != InstanceStatus.ACTIVE) {
            throw new InstanceNotBindableException();
        }

        return bindingRepository.insertCreating(
                instanceId, bindingId);
    }

Phương thức deprovision cũng khóa cùng hàng instance:

    @Transactional
    public DeprovisionReservation reserveDeprovision(
            String instanceId) {

        ServiceInstance instance =
                instanceRepository.findByIdForUpdate(instanceId)
                        .orElseThrow(InstanceNotFoundException::new);

        if (instance.status() == InstanceStatus.DEPROVISIONING) {
            return operationRepository
                    .findActiveDeprovision(instanceId)
                    .map(DeprovisionReservation::existing)
                    .orElseThrow(OperationStateException::new);
        }

        if (instance.status() != InstanceStatus.ACTIVE) {
            throw new InvalidInstanceStateException();
        }

        if (bindingRepository.existsBlockingDeprovision(instanceId)) {
            throw new BindingsExistException();
        }

        instance.markDeprovisioning();
        DeprovisionOperation operation =
                operationRepository.create(instanceId);
        outboxRepository.append(operation.toEvent());

        return DeprovisionReservation.created(operation);
    }

Đây là pseudocode thể hiện ranh giới transaction. Các method repository và enum là mô hình minh họa do ứng dụng định nghĩa. Không giữ database transaction mở trong lúc gọi database server, Kubernetes API hoặc secret manager. Transaction chỉ nên khóa và ghi trạng thái bền vững; thao tác remote chạy sau commit.

Nếu dùng optimistic locking thay cho SELECT FOR UPDATE, cần cập nhật instance bằng điều kiện version, ví dụ UPDATE ... WHERE id = ? AND version = ?. Chỉ một transaction có thể tăng version thành công. Request thua cuộc phải đọc lại state và quyết định trả binding conflict, 422 do còn binding hoặc kết quả operation đã tồn tại.

## 7. Thứ tự xử lý unbind an toàn

Unbind thường phải hoàn tất đồng bộ theo hợp đồng binding của OSB; không giả định có thể dùng accepts_incomplete và last operation giống deprovision. Nếu backend cần thời gian dài, broker nên tối ưu quy trình revoke, áp dụng timeout có kiểm soát và trả lỗi phù hợp khi chưa thể xác nhận hoàn tất.

Một luồng unbind:

1. Xác thực caller và tra binding theo instance ID + binding ID.
2. Khóa instance theo giao thức khóa chung của các thao tác vòng đời.
3. Xác nhận instance/binding thuộc phạm vi caller và binding không xung đột.
4. Nếu binding đã UNBOUND, xử lý request lặp theo semantics của OSB.
5. Chuyển binding sang UNBINDING và commit trạng thái.
6. Revoke principal, token, grant hoặc credential ở backend.
7. Xóa hoặc đánh dấu secret reference đã thu hồi.
8. Cập nhật binding thành UNBOUND và ghi audit.

Trong khi binding ở UNBINDING, nó vẫn được tính là binding chặn deprovision. Chỉ sau khi backend xác nhận quyền đã bị thu hồi, broker mới chuyển sang UNBOUND. Nếu revoke thất bại hoặc timeout, giữ trạng thái chưa terminal để nền tảng có thể retry và deprovision tiếp tục bị chặn.

Không nên xóa binding record ngay khi nhận DELETE. Record cần tồn tại đủ lâu để xử lý retry, kiểm tra kết quả và ngăn một request bind mới dùng lại cùng binding ID theo cách gây nhầm lẫn.

## 8. Race condition giữa unbind và deprovision

Nền tảng thường tuần tự hóa unbind rồi deprovision, nhưng broker không nên phụ thuộc hoàn toàn vào thứ tự đó. Có thể hai request đến gần như cùng lúc hoặc request deprovision được gửi lại trước khi unbind hoàn tất.

Các trường hợp:

| Thứ tự transaction | Kết quả |
|---|---|
| Unbind chuyển binding sang UNBINDING trước | Deprovision nhìn thấy binding chưa terminal và trả 422 |
| Unbind hoàn tất, chuyển binding sang UNBOUND trước | Deprovision có thể tiếp tục nếu không còn binding khác |
| Deprovision kiểm tra trước khi unbind bắt đầu | Nếu binding còn BOUND, trả 422; unbind tiếp tục |
| Deprovision chuyển instance sang DEPROVISIONING trước | Unbind của binding còn tồn tại cần được xử lý theo recovery policy; không xóa instance cho đến khi binding đã revoke |

Thiết kế nên tránh trường hợp instance đã chuyển DEPROVISIONING nhưng vẫn còn binding active. Vì vậy, điều kiện “không còn binding” phải được kiểm tra trong cùng transaction với việc chuyển trạng thái instance, dưới cùng khóa instance.

Nếu deprovision bị từ chối vì còn binding, không cần giữ instance ở trạng thái DEPROVISION_REQUESTED lâu dài trừ khi sản phẩm có workflow riêng. Broker có thể trả 422 và để nền tảng điều phối unbind. Nếu có trạng thái yêu cầu thu hồi nội bộ, trạng thái đó vẫn phải cho phép unbind hoàn tất và không được ngăn nền tảng thực hiện bước cần thiết.

## 9. Deprovision bất đồng bộ sau khi binding đã hết

Deprovision có thể mất thời gian vì phải xóa database, volume, snapshot và network resource. Khi không còn binding, nếu request cho phép asynchronous operation, broker có thể:

1. Khóa instance và kiểm tra lại không còn binding blocking.
2. Chuyển instance sang DEPROVISIONING.
3. Tạo operation và outbox event trong cùng transaction.
4. Trả 202 Accepted cùng operation key theo OSB.
5. Worker thực hiện cleanup và cập nhật operation.
6. Khi cleanup hoàn tất, đánh dấu instance DEPROVISIONED và lưu tombstone.

Kể từ lúc instance chuyển DEPROVISIONING, bind mới phải bị từ chối. Nếu một request bind đã đặt reservation CREATING trước đó, reservation đó phải được tính là binding đang tồn tại và khiến deprovision bị từ chối. Nếu deprovision thắng khóa trước, bind sẽ không tạo được reservation.

Nếu nền tảng không chấp nhận async, broker cần hoàn tất đồng bộ hoặc trả lỗi theo quy tắc OSB/framework. Không trả 202 nếu chưa có operation bền vững và worker có khả năng tiếp tục sau restart.

## 10. Idempotency và request lặp ở từng thao tác

Bind, unbind và deprovision có các quy tắc lặp khác nhau:

| Thao tác | Request lặp | Hành vi mong muốn |
|---|---|---|
| Bind | Cùng instance ID và binding ID, cùng consumer | Không tạo principal/secret trùng; trả kết quả binding đã tồn tại theo hợp đồng |
| Bind | Binding ID đã thuộc instance hoặc consumer khác | Từ chối xung đột |
| Unbind | Binding đã UNBOUND hoặc không còn tồn tại | Trả kết quả phù hợp với semantics unbind, thường dùng 410 Gone khi binding không tồn tại |
| Deprovision | Instance còn binding | Từ chối 422, không bắt đầu xóa |
| Deprovision | Đã có operation đang chạy | Không tạo operation xóa song song; trả trạng thái operation hiện tại nếu phù hợp |
| Deprovision | Instance đã deprovision | Trả kết quả đã biến mất theo semantics OSB, thường là 410 Gone |

Idempotency cần được lưu bền vững. Không dùng một Set trong bộ nhớ của broker để ghi nhớ binding ID đã xử lý, vì nhiều replica hoặc restart sẽ làm mất thông tin. Dùng unique constraint, operation record, binding state và resource ownership metadata.

## 11. Trạng thái binding bị lỗi một phần

Một request bind có thể tạo database user thành công nhưng lỗi khi lưu secret hoặc response. Một request unbind có thể revoke token thành công nhưng timeout trước khi cập nhật binding record. Đây là các trạng thái không thể giải quyết bằng cách xóa record ngay.

Nên lưu checkpoint hoặc trạng thái đủ để reconcile:

| Tình huống | Trạng thái nên lưu | Cách phục hồi |
|---|---|---|
| Bind tạo principal thành công, chưa lưu secret reference | CREATING hoặc BIND_FAILED_NEEDS_RECONCILE | Tra cứu principal theo ownership metadata; hoàn tất lưu hoặc revoke phần tạo dở |
| Bind lỗi trước khi tạo tài nguyên | FAILED_CLEANED sau khi xác nhận không có tài nguyên | Cho phép retry theo policy |
| Unbind revoke thành công, chưa cập nhật DB | UNBINDING | Retry kiểm tra principal đã vắng mặt rồi chuyển UNBOUND |
| Unbind backend timeout | UNBINDING/UNBIND_RETRYABLE | Tra cứu backend trước khi gửi revoke lại |
| Deprovision thấy binding UNBINDING | Instance vẫn ACTIVE; deprovision trả 422 | Chờ unbind hoàn tất rồi thử lại |

Worker/reconciler cần sử dụng cùng idempotency key hoặc binding ownership ID để không tạo thêm principal khi phục hồi. Khi chưa xác định được credential đã bị revoke hay chưa, broker phải giữ trạng thái chặn deprovision.

## 12. Tránh deadlock và khóa kéo dài

Các thao tác vòng đời có thể cần khóa nhiều bản ghi. Nếu thứ tự khóa khác nhau giữa bind, unbind và deprovision, database có thể phát hiện deadlock.

Một quy ước hữu ích:

1. Khóa service instance trước.
2. Sau đó khóa binding theo thứ tự binding ID ổn định nếu cần nhiều binding.
3. Cuối cùng cập nhật operation/quota record theo thứ tự nhất quán đã định nghĩa.

Giữ transaction ngắn và không gọi API mạng khi đang giữ row lock. Nếu phải thực hiện nhiều bước remote, dùng trạng thái trung gian như CREATING, UNBINDING hoặc DEPROVISIONING cùng outbox/worker. Trạng thái trung gian vừa ngăn request cạnh tranh, vừa cho phép hệ thống phục hồi sau khi process dừng.

Nếu dùng distributed lock, cần lease/expiry và fencing token hoặc version để worker cũ không tiếp tục ghi state sau khi lock đã hết hạn và worker mới đã nhận việc. Lock hết hạn không chứng minh thao tác remote trước đó chưa xảy ra; worker mới vẫn phải reconcile backend.

## 13. Xử lý lỗi và ánh xạ response

Broker cần phân biệt lỗi do thứ tự vòng đời với lỗi phụ thuộc:

| Tình huống | Phản hồi/hướng xử lý |
|---|---|
| Deprovision khi còn binding | 422 Unprocessable Entity theo semantics OSB |
| Unbind thành công | 200 OK |
| Unbind binding đã biến mất | 410 Gone theo semantics unbind |
| Deprovision hoàn tất đồng bộ | 200 OK |
| Deprovision đã nhận và xử lý async | 202 Accepted nếu nền tảng cho phép |
| Instance đã deprovision | 410 Gone theo semantics deprovision |
| Database/secret manager tạm thời không truy cập được | Lỗi phụ thuộc phù hợp; không giả định đã thu hồi |
| Hai thao tác cạnh tranh làm version thay đổi | Đọc lại state và trả kết quả phù hợp, không ghi đè state mới |

Mã response cụ thể cần được kiểm tra với phiên bản OSB mà broker công bố. Không biến lỗi database thành 410 Gone; không trả 200 cho unbind khi credential vẫn còn hiệu lực; không trả 202 cho unbind nếu API/framework không hỗ trợ asynchronous binding operation.

## 14. Kiểm thử thứ tự và concurrency

Unit test cho policy là chưa đủ. Cần kiểm tra transaction, nhiều request đồng thời và kết quả backend:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Instance có một binding BOUND, nhận deprovision | Trả 422; instance không chuyển DEPROVISIONING |
| Unbind thành công rồi deprovision | Instance chỉ được xóa sau khi binding thành UNBOUND |
| Bind và deprovision đến đồng thời | Chỉ một bên thắng khóa; không có binding mới sau khi instance bắt đầu deprovision |
| Unbind và deprovision đến đồng thời | Deprovision bị chặn cho đến khi revoke hoàn tất |
| Binding ở CREATING | Deprovision xem như còn binding và từ chối |
| Binding ở UNBINDING hoặc UNBIND_FAILED | Deprovision tiếp tục bị chặn |
| Hai request deprovision đồng thời | Chỉ một operation hoạt động cho instance |
| Hai request bind cùng binding ID | Không tạo hai principal hoặc hai secret |
| Backend revoke thành công nhưng DB update lỗi | Retry/reconcile chuyển binding sang UNBOUND |
| Worker deprovision dừng giữa cleanup | Reconciler tiếp tục mà không bỏ qua binding còn hoạt động |
| Request đến từ tenant khác | Không tiết lộ binding hoặc instance và không gọi backend |
| Instance đã deprovision | Request lặp nhận response theo semantics đã định nghĩa |

Nên dùng integration test với database thật hoặc container test để xác minh SELECT FOR UPDATE, optimistic locking, unique constraint và transaction isolation. Test concurrency nên tạo nhiều request song song và kiểm tra invariant cuối cùng:

- Instance ở DEPROVISIONING/DEPROVISIONED thì không có binding active.
- Instance không bị deprovision nếu còn binding chưa terminal.
- Mỗi binding chỉ có một principal/credential đang được quản lý.
- Mỗi instance chỉ có một deprovision operation đang hoạt động.
- Quota và secret reference không bị giải phóng hoặc xóa nhiều lần ngoài ý muốn.

## 15. Những sai lầm thường gặp

- Xóa service instance trước khi unbind tất cả consumer.
- Chỉ đếm binding BOUND mà bỏ qua CREATING hoặc UNBINDING.
- Kiểm tra không có binding rồi chuyển trạng thái instance trong hai transaction tách rời.
- Cho phép bind mới sau khi deprovision đã bắt đầu.
- Giữ database transaction mở trong lúc gọi API backend.
- Xóa binding record trước khi revoke credential thực tế.
- Coi timeout là bằng chứng unbind đã thành công.
- Tạo operation deprovision mới cho mỗi request lặp.
- Dùng distributed lock không có fencing/version để chặn worker cũ.
- Trả 200 hoặc 202 khi chưa đạt điều kiện của hợp đồng OSB.

## Kết luận

Thứ tự an toàn là unbind mọi consumer trước, xác nhận không còn binding chưa terminal, rồi mới deprovision service instance. OSB yêu cầu broker từ chối deprovision khi instance còn binding bằng 422 Unprocessable Entity. Để bảo vệ thứ tự này khi request đến đồng thời, bind, unbind và deprovision phải cùng đồng bộ trên trạng thái instance; transaction cần bảo đảm việc kiểm tra binding và chuyển instance sang DEPROVISIONING là một quyết định nguyên tử. Kết hợp trạng thái trung gian, operation bền vững, idempotency, checkpoint và reconcile giúp broker Spring Cloud thu hồi credentials đúng lúc, không tạo binding mới trong lúc xóa instance và phục hồi an toàn sau timeout hoặc lỗi một phần.

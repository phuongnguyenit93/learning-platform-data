# Tránh duplicate flow name và rò rỉ registration

`IntegrationFlowContext` cho phép đăng ký và hủy các `IntegrationFlow` trong khi ứng dụng đang chạy. Khả năng này hữu ích khi topology phụ thuộc tenant, cấu hình runtime hoặc một nguồn tích hợp được bật/tắt theo yêu cầu. Tuy nhiên, mỗi lần đăng ký tạo ra các bean runtime như endpoint, channel và handler. Nếu hai flow dùng chung tên bean, việc đăng ký có thể thất bại; nếu flow đã hết nhu cầu nhưng registration vẫn còn trong context, endpoint và tài nguyên liên quan tiếp tục tồn tại.

Để quản lý flow động an toàn, cần có một quy tắc định danh duy nhất, một nơi chịu trách nhiệm đăng ký/hủy đăng ký, và một quy trình cleanup rõ ràng. `IntegrationFlowContext` quản lý các bean của flow; ứng dụng cần quản lý vòng đời nghiệp vụ của registration, bao gồm lúc nào được tạo, lúc nào dừng nhận message và khi nào phải hủy.

## 1. Registration gồm những gì?

Một bean `IntegrationFlow` mô tả topology: nguồn vào, các bước xử lý, channel và đích ra. Khi flow được đăng ký, Spring Integration tạo hoặc liên kết những thành phần runtime cần thiết để flow hoạt động. Tùy flow, các thành phần đó có thể gồm:

- Consumer endpoint kết nối channel với handler.
- Polling adapter và poller nếu flow đọc từ một `MessageSource`.
- Channel và các component được khai báo bên trong DSL.
- Transformer, router, filter, service activator hoặc aggregator.
- Adapter, listener, scheduler hoặc các thành phần có tài nguyên riêng.

`IntegrationFlowContext` cung cấp builder để đăng ký flow và trả về một `IntegrationFlowRegistration`:

```java
IntegrationFlowRegistration registration = flowContext
        .registration(tenantFlow)
        .id("tenant-orders-42")
        .useFlowIdAsPrefix()
        .register();
```

Registration là handle để ứng dụng truy cập và điều khiển flow đã đăng ký. Từ handle này, ứng dụng có thể lấy ID, truy cập input channel hoặc messaging template khi flow hỗ trợ, start/stop flow và destroy registration khi không còn sử dụng.

Một điểm cần nhớ: `IntegrationFlow` là định nghĩa topology; `IntegrationFlowRegistration` đại diện cho lần đăng ký topology đó trong một application context. Giữ tham chiếu registration giúp ứng dụng quản lý vòng đời một cách tường minh.

## 2. Hai loại xung đột tên cần phân biệt

Một lỗi thường gặp là chỉ kiểm tra ID của flow mà quên tên các component bên trong flow. Có hai lớp định danh khác nhau:

| Loại tên | Phạm vi | Ví dụ xung đột |
|---|---|---|
| Flow registration ID | Định danh một registration trong `IntegrationFlowContext` và context hiện tại | Hai yêu cầu cùng đăng ký ID `tenant-orders-42` |
| Bean/component name | Định danh bean runtime được tạo cho endpoint, channel hoặc component trong context | Hai flow cùng tạo component tên `transformer.handler` hoặc cùng khai báo một bean channel tường minh |

ID khác nhau chưa chắc loại bỏ mọi xung đột. Khi đăng ký nhiều flow có cấu trúc DSL tương tự, các component do DSL sinh ra có thể có tên mặc định giống nhau. `.useFlowIdAsPrefix()` yêu cầu Spring Integration dùng flow ID làm tiền tố cho tên bean được tạo trong flow, nhờ đó các component nội bộ của từng flow có namespace riêng.

Ví dụ, hai flow có thể cùng chứa một transformer được tạo theo cùng cấu trúc DSL. Khi bật prefix, tên bean sinh ra cho flow `tenant-orders-42` và `tenant-orders-84` sẽ được phân biệt bằng ID tương ứng.

Prefix không thay thế quy tắc đặt tên cho mọi bean trong ứng dụng. Với channel hoặc component được đặt tên tường minh, hãy xác định đó là tài nguyên riêng của flow hay tài nguyên dùng chung. Nếu riêng, tên cần chứa định danh flow; nếu dùng chung, hãy khai báo và quản lý bean dùng chung một lần ở context. Không tạo nhiều bean cùng tên chỉ vì mỗi flow có một registration ID khác nhau.

## 3. Thiết kế flow ID ổn định và duy nhất

Flow ID nên có các đặc điểm:

- Duy nhất trong phạm vi application context đang quản lý registration.
- Ổn định với cùng một đối tượng nghiệp vụ, để thao tác register/unregister tìm được cùng một ID.
- Dễ truy vết trong log, metrics và khi chẩn đoán lỗi.
- Không phụ thuộc vào dữ liệu đầu vào chưa được chuẩn hóa hoặc có thể thay đổi tùy request.
- Có quy tắc phân biệt môi trường, tenant, loại flow hoặc phiên bản khi những yếu tố đó tạo ra topology khác nhau.

Ví dụ, có thể tạo ID từ loại flow và tenant key đã chuẩn hóa:

```java
String flowIdFor(String tenantKey) {
    String stableKey = tenantKey.trim().toLowerCase(Locale.ROOT);
    String suffix = UUID.nameUUIDFromBytes(
            stableKey.getBytes(StandardCharsets.UTF_8)).toString();
    return "tenant-orders-" + suffix;
}
```

`UUID.nameUUIDFromBytes` tạo một UUID ổn định từ cùng một chuỗi đầu vào. Trong hệ thống thực tế, hãy chuẩn hóa tenant key theo quy tắc nghiệp vụ trước khi tạo ID. Nếu cùng tenant có nhiều phiên bản topology cùng tồn tại, thêm version hoặc loại flow vào phần định danh. Tránh chỉ dùng số ngẫu nhiên mỗi lần yêu cầu đăng ký: cách đó khiến cùng một tenant có thể tạo vô hạn registration mà ứng dụng không tìm lại được registration cũ.

Không dùng trực tiếp chuỗi tùy ý do client gửi làm tên bean. Hãy kiểm tra độ dài, chuẩn hóa ký tự và giới hạn miền giá trị. ID phải phản ánh danh tính của flow trong hệ thống, không phải toàn bộ nội dung request.

## 4. Đăng ký có kiểm soát và chống tạo trùng đồng thời

Nếu nhiều request cùng yêu cầu bật flow cho một tenant, hai luồng xử lý có thể cùng kiểm tra rằng flow chưa tồn tại rồi cùng gọi `register()`. Đây là race condition: cả hai đều thấy trạng thái ban đầu là chưa đăng ký.

Một registry ở cấp ứng dụng nên là nơi duy nhất sở hữu thao tác đăng ký. Registry chịu trách nhiệm:

1. Tạo flow ID từ khóa nghiệp vụ.
2. Kiểm tra registration hiện có theo chính sách idempotency.
3. Đăng ký flow đúng một lần.
4. Lưu handle `IntegrationFlowRegistration` sau khi đăng ký thành công.
5. Dùng cùng ID và cùng registry khi cần dừng hoặc hủy flow.

Ví dụ đơn giản dùng đồng bộ hóa để bảo đảm register và unregister của cùng registry không chạy chồng lên nhau:

```java
@Component
class TenantFlowRegistry {

    private final IntegrationFlowContext flowContext;
    private final OrderService orderService;
    private final Map<String, IntegrationFlowRegistration> registrations =
            new HashMap<>();

    TenantFlowRegistry(
            IntegrationFlowContext flowContext,
            OrderService orderService) {
        this.flowContext = flowContext;
        this.orderService = orderService;
    }

    public synchronized IntegrationFlowRegistration register(String tenantKey) {
        String flowId = flowIdFor(tenantKey);
        IntegrationFlowRegistration existing = registrations.get(flowId);
        if (existing != null) {
            return existing;
        }

        IntegrationFlow flow = buildFlow(tenantKey);
        IntegrationFlowRegistration registration = flowContext
                .registration(flow)
                .id(flowId)
                .useFlowIdAsPrefix()
                .register();

        registrations.put(flowId, registration);
        return registration;
    }

    public synchronized void unregister(String tenantKey) {
        String flowId = flowIdFor(tenantKey);
        IntegrationFlowRegistration registration = registrations.get(flowId);
        if (registration != null) {
            try {
                registration.stop();
            }
            finally {
                try {
                    registration.destroy();
                }
                finally {
                    registrations.remove(flowId, registration);
                }
            }
        }
    }

    private IntegrationFlow buildFlow(String tenantKey) {
        return IntegrationFlow
                .from(new DirectChannel())
                .handle((MessageHandler) message ->
                        orderService.accept(tenantKey, message.getPayload()))
                .get();
    }

    private String flowIdFor(String tenantKey) {
        String key = tenantKey.trim().toLowerCase(Locale.ROOT);
        return "tenant-orders-" + UUID.nameUUIDFromBytes(
                key.getBytes(StandardCharsets.UTF_8));
    }
}
```

Đây là ví dụ về một registry có một khóa đồng bộ chung, phù hợp khi số lần thay đổi topology thấp. Nếu hệ thống đăng ký nhiều tenant song song, có thể dùng lock theo flow ID hoặc một cơ chế đồng bộ theo khóa để các tenant khác nhau không chặn nhau. Dù chọn cách nào, thao tác kiểm tra, đăng ký và ghi nhận handle phải có tính nguyên tử đối với cùng một ID.

Chính sách khi flow đã tồn tại cần được quyết định rõ. Với thao tác “ensure active”, trả lại registration hiện có thường phù hợp. Với thao tác “replace topology”, cần dừng và hủy registration cũ theo trình tự rồi mới đăng ký phiên bản mới. Không nên vô tình xem một lần đăng ký trùng là yêu cầu thay thế flow.

## 5. `useFlowIdAsPrefix()` và tên component tường minh

`.useFlowIdAsPrefix()` hữu ích khi các flow được tạo từ cùng một hàm builder và chứa các component DSL sinh tên mặc định. Ví dụ, nhiều tenant có thể dùng cùng một pipeline gồm filter, transformer và service activator; prefix giúp tên bean nội bộ không va chạm.

Tuy vậy, cần kiểm tra những tên được khai báo trực tiếp trong topology. Ví dụ, flow có thể nhận một channel được tạo và đặt tên riêng ở cấp ứng dụng:

```java
MessageChannel tenantInputChannel = createTenantInputChannel(tenantKey);
IntegrationFlow flow = IntegrationFlow.from(tenantInputChannel)
        .handle(orderService, "accept")
        .get();
```

Nếu `tenantInputChannel` là một bean channel được đặt tên riêng, registry phải bảo đảm channel đó được tạo với tên duy nhất và có lifecycle rõ ràng; `createTenantInputChannel` trong ví dụ đại diện cho factory của ứng dụng. Nếu nhiều flow cùng tham chiếu một channel dùng chung, cần xác định việc gửi message vào channel sẽ phân phối tới một hay nhiều subscriber và liệu đó có đúng semantics mong muốn hay không.

Đối với component có ID được đặt tường minh, hãy xem ID đó là một phần của hợp đồng đặt tên. Prefix của flow không nên được dùng làm lý do để bỏ qua việc kiểm tra các tên tường minh, channel tham chiếu từ bên ngoài hoặc bean được chia sẻ giữa các flow.

## 6. Phân biệt stop, destroy và close context

Đăng ký flow tạo ra tài nguyên trong context. Khi tenant bị xóa hoặc topology không còn cần thiết, cần giải phóng registration tương ứng.

| Thao tác | Ý nghĩa | Khi dùng |
|---|---|---|
| `registration.stop()` | Dừng các thành phần lifecycle của flow | Ngừng nhận công việc mới trước khi drain hoặc thay topology |
| `registration.destroy()` | Hủy registration và các bean được tạo cho flow | Xóa flow khỏi runtime khi không còn sử dụng |
| `applicationContext.close()` | Đóng toàn bộ context và hủy các bean thuộc context | Khi ứng dụng hoặc context kết thúc |

`stop()` không xóa bean và không giải phóng toàn bộ registration. Một flow đã stop vẫn chiếm chỗ trong context và có thể được start lại. Vì vậy, nếu flow không còn được sử dụng, chỉ gọi `stop()` sẽ để lại registration và các bean runtime của nó.

`destroy()` là bước cần thiết để loại bỏ registration động. Khi cần shutdown có trật tự, hãy stop trước để ngừng nhận message, xử lý backlog theo chính sách của ứng dụng, rồi destroy. Nếu không có yêu cầu drain hoặc stop riêng, vẫn cần bảo đảm `destroy()` được gọi cho registration đã hết vòng đời.

Đóng application context sẽ kích hoạt lifecycle và destruction của các bean do context quản lý. Đây là cơ chế cleanup cuối cùng khi ứng dụng tắt; nó không thay thế việc hủy flow ngay khi tenant hoặc cấu hình đã bị loại bỏ trong lúc ứng dụng vẫn chạy.

## 7. Rò rỉ registration thường xuất hiện như thế nào?

Một registration bị bỏ quên có thể giữ lại nhiều thành phần hơn một object Java trong map:

| Dấu hiệu | Tài nguyên có thể còn tồn tại | Hậu quả |
|---|---|---|
| Tenant đã xóa nhưng flow vẫn chạy | Endpoint, subscriber và adapter | Message tiếp tục được nhận hoặc xử lý cho tenant không còn hoạt động |
| Mỗi lần cập nhật cấu hình lại tạo ID mới | Bean, channel và registration cũ | Số lượng component tăng theo thời gian |
| Chỉ gọi `stop()` | Bean definition và registration vẫn còn | Không thể đăng ký lại cùng ID hoặc tên component theo cách mong muốn |
| Giữ registration trong map không dọn | Handle và tham chiếu tới flow | Heap giữ object và làm sai trạng thái registry |
| Không dừng inbound adapter | Listener, poller hoặc consumer | Vẫn nhận message dù nghiệp vụ đã bị vô hiệu hóa |
| Tạo executor hoặc scheduler riêng nhưng không đóng | Thread và queue của task | Thread nền tồn tại, tài nguyên tăng và ứng dụng khó shutdown |

Rò rỉ có thể biểu hiện bằng số endpoint tăng, số thread tăng, queue backlog bất thường, message được xử lý lặp hoặc memory tăng theo số lần bật/tắt tenant. Không nên chỉ theo dõi số lượng registration trong map của ứng dụng; cần quan sát cả trạng thái endpoint và tài nguyên do flow sở hữu.

## 8. Quy trình unregister an toàn

Khi một flow không còn cần thiết, hãy thực hiện theo thứ tự:

1. Đánh dấu flow hoặc tenant đang chuyển sang trạng thái ngừng hoạt động để request mới không kích hoạt lại registration.
2. Ngừng nhận message mới bằng cách stop registration hoặc inbound endpoint thích hợp.
3. Chờ hoặc xử lý công việc đang chạy theo giới hạn shutdown đã định.
4. Destroy registration để loại bỏ các bean runtime do flow tạo ra.
5. Xóa handle khỏi registry của ứng dụng và giải phóng tham chiếu liên quan.
6. Đóng tài nguyên riêng mà ứng dụng tự tạo, nếu chúng không thuộc quyền sở hữu của Spring Integration registration.

Thứ tự xóa handle và destroy cần được bảo vệ bởi cùng cơ chế đồng bộ dùng cho register. Không cho phép một request khác đăng ký lại cùng ID trong khi registration cũ vẫn đang được destroy. Ví dụ registry đồng bộ ở phần trước giữ lock cho toàn bộ thao tác; registry có tải cao nên dùng lock theo ID hoặc state machine để bảo đảm cùng nguyên tắc.

Nếu `stop()` hoặc `destroy()` phát sinh lỗi, cần ghi log với flow ID và trạng thái hiện tại. Không âm thầm bỏ qua lỗi cleanup. Có thể giữ lại một trạng thái `CLEANUP_FAILED` để tác vụ quản trị thử cleanup lại, đồng thời ngăn tạo một registration mới cùng ID cho đến khi trạng thái cũ được giải quyết.

## 9. Tránh rò rỉ tài nguyên dùng chung

Không phải mọi bean được flow sử dụng đều thuộc sở hữu riêng của registration. Một flow có thể tham chiếu tới:

- Executor dùng chung cho nhiều flow.
- Task scheduler do application context quản lý.
- Connection factory hoặc client dùng chung.
- Channel được khai báo ở cấp ứng dụng.
- Service nghiệp vụ singleton.

Khi destroy một flow, chỉ tài nguyên thuộc flow đó mới nên được loại bỏ. Không đóng executor, connection factory hoặc channel dùng chung nếu flow khác vẫn cần chúng. Hãy phân biệt tài nguyên được registration tạo và quản lý với dependency được inject từ context.

Nếu adapter hoặc component tùy chỉnh tự tạo thread, listener hay connection, hãy gắn việc tạo và giải phóng chúng vào lifecycle của bean đó. Tránh mở tài nguyên trong mỗi lần xử lý message hoặc giữ static reference tới registration và context.

## 10. Quản lý lỗi trong lúc đăng ký và hủy flow

Đăng ký flow có thể thất bại do ID trùng, bean name trùng, dependency không tồn tại hoặc lỗi khi tạo endpoint. Registry chỉ nên ghi registration vào map sau khi `.register()` trả về thành công. Nếu việc xây dựng flow có tạo tài nguyên ngoài Spring trước khi register, cần có cleanup cho những tài nguyên đó khi register thất bại.

Khi thay topology, không nên destroy flow cũ trước khi xác minh cấu hình mới nếu hệ thống yêu cầu khả năng phục vụ liên tục. Có thể dùng versioned ID để tạo flow mới, kiểm tra hoạt động, chuyển traffic rồi mới stop/destroy flow cũ. Cách này cần một cơ chế chuyển hướng message rõ ràng và tránh để hai flow cùng tiêu thụ một input channel ngoài ý muốn.

Không dùng catch rộng rồi bỏ qua exception từ `register()` hoặc `destroy()`. Log nên bao gồm flow ID, tenant key đã được che hoặc chuẩn hóa, thao tác đang thực hiện và nguyên nhân gốc. Với thao tác retry cleanup, phải bảo đảm lệnh destroy có thể được gọi an toàn theo trạng thái thực tế của registration.

## 11. Kiểm thử duplicate và cleanup

Kiểm thử registry nên tập trung vào hành vi quan sát được:

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Đăng ký cùng tenant hai lần theo chính sách ensure | Chỉ có một registration; lần hai trả về handle hiện có |
| Hai tenant khác nhau | Hai flow ID khác nhau và component name không xung đột |
| Hai request đăng ký đồng thời cùng tenant | Chỉ một registration được tạo |
| Đăng ký thất bại | Registry không lưu một handle giả hoặc trạng thái active không có thật |
| Unregister tenant | Registration được stop/destroy và bị xóa khỏi registry |
| Unregister lặp lại | Thao tác có kết quả xác định, không tạo flow mới và không làm hỏng registry |
| Destroy một flow | Flow khác vẫn chạy nếu dùng chung context hoặc tài nguyên |
| Context đóng | Các registration còn lại và tài nguyên do context sở hữu được giải phóng |

Với integration test, có thể kiểm tra input channel hoặc handler của flow trước và sau unregister, đồng thời xác nhận endpoint không còn nhận message sau khi destroy. Nếu flow có listener hoặc executor riêng, kiểm tra trạng thái lifecycle và việc thread/tài nguyên được giải phóng.

## 12. Quan sát số lượng và trạng thái flow động

Một registry production nên cung cấp thông tin vận hành tối thiểu:

- Flow ID, loại flow và tenant key đã chuẩn hóa.
- Thời điểm đăng ký, thời điểm start/stop và thời điểm destroy.
- Trạng thái như `REGISTERING`, `ACTIVE`, `STOPPING`, `DESTROYED` hoặc `CLEANUP_FAILED`.
- Số lượng registration đang hoạt động và số lần đăng ký thất bại.
- Số lần cleanup thất bại và tuổi của registration lâu nhất.
- Số message hoặc task đang xử lý nếu endpoint cung cấp metric phù hợp.

Đặt giới hạn số flow động tối đa và chính sách khi vượt giới hạn. Nếu một tenant có thể tạo nhiều topology theo version, hãy đặt quota hoặc dọn các version cũ. Một registry không giới hạn có thể trở thành nguồn rò rỉ dù từng registration được đặt tên đúng.

Khi chẩn đoán, so sánh số flow mà nghiệp vụ mong đợi với số registration thực tế và số endpoint runtime. Kiểm tra các ID không còn tenant tương ứng, registration đã stop nhưng chưa destroy, component có tên trùng và các tài nguyên vẫn hoạt động sau unregister.

## 13. Nguyên tắc thiết kế

- **Một registry làm chủ registration:** không để nhiều service tự gọi `IntegrationFlowContext.register()` cho cùng loại flow mà không có phối hợp.
- **ID ổn định theo nghiệp vụ:** cùng tenant và cùng loại topology tạo ra cùng ID; topology khác phiên bản có ID phân biệt.
- **Bật prefix cho component DSL sinh tự động:** dùng `.useFlowIdAsPrefix()` khi đăng ký nhiều flow có cấu trúc tương tự.
- **Đặt tên tường minh có chủ đích:** channel và bean riêng phải có tên riêng; dependency dùng chung phải được khai báo và quản lý một lần.
- **Chống race condition:** thao tác kiểm tra, register và unregister phải được đồng bộ theo flow ID.
- **Phân biệt stop và destroy:** stop để tạm dừng; destroy để loại bỏ registration không còn dùng.
- **Dọn handle và tài nguyên:** xóa registry entry, đóng tài nguyên riêng và giữ nguyên tài nguyên dùng chung.
- **Theo dõi cleanup:** log, metrics và trạng thái lỗi giúp phát hiện flow mồ côi trước khi chúng tích tụ.

Trước khi tạo flow động, hãy xác định ai sở hữu registration, ID được tạo ra sao, component nào có tên tường minh, tài nguyên nào dùng chung và điều kiện nào kích hoạt destroy. Khi các quy tắc đó được thực hiện tập trung, `IntegrationFlowContext` có thể thay đổi topology trong runtime mà không tạo ra duplicate flow hoặc để lại endpoint và tài nguyên mồ côi.

# Sticky routing và session state

## 1. Giữ các RPC liên quan trên cùng backend

Trong **SPRING_GRPC**, một service có thể chạy trên nhiều instance và client dùng `ManagedChannel`, name resolver cùng load balancing policy để chọn backend. Với các luồng nghiệp vụ có session, đôi khi muốn những RPC liên quan đến cùng một người dùng, tenant hoặc job tiếp tục đến cùng instance. **Sticky routing** (session affinity) là cách duy trì sự gắn kết đó trong một khoảng thời gian hoặc theo một khóa định tuyến.

Ví dụ một người dùng bắt đầu quy trình xử lý đơn:

~~~text
Client gửi:
  StartCheckout(session = S-42)
  AddItem(session = S-42)
  GetCheckout(session = S-42)

Mong muốn khi dùng sticky routing:
  các RPC có session S-42 -> backend B
~~~

Sticky routing có ích khi backend giữ cache hoặc trạng thái phiên cục bộ, hoặc khi muốn tận dụng cache nóng. Tuy nhiên, **affinity không phải cơ chế lưu trữ session**. Nếu backend B bị restart, session chỉ nằm trong RAM của B sẽ mất. Hệ thống cần một chiến lược lưu và phục hồi state độc lập với việc chọn backend.

## 2. Phân biệt connection stickiness và RPC stickiness

gRPC dùng HTTP/2 và có thể multiplex nhiều RPC trên một kết nối. Vì vậy cần xác định lớp nào đang duy trì affinity:

| Cơ chế | Đơn vị được giữ gắn kết | Hệ quả |
|---|---|---|
| L4 load balancer / TCP proxy | Kết nối TCP | Nhiều RPC multiplex trên cùng HTTP/2 connection thường cùng đi đến một backend |
| gRPC client-side load balancing | Từng RPC mới qua subchannel được chọn | Các RPC trên cùng `ManagedChannel` có thể được phân phối đến backend khác nhau tùy policy |
| L7 proxy định tuyến theo HTTP/2 stream | Từng RPC/stream | Proxy có thể đọc metadata của RPC và chọn backend theo routing key nếu được cấu hình |
| Affinity theo session key | Các RPC mang cùng khóa | Chỉ hoạt động nếu lớp định tuyến hiểu khóa và dùng cùng thuật toán/nhóm backend |

Một TCP connection được giữ lâu không đồng nghĩa toàn bộ session nghiệp vụ được bảo đảm ở cùng instance trong mọi kiến trúc. Nếu client-side `round_robin` chọn các subchannel khác nhau cho RPC mới, một L4 proxy phía sau cũng không thể tự suy ra session key để giữ các RPC đó cùng backend.

Ngược lại, nếu một L4 proxy gắn một HTTP/2 connection vào một backend, mọi RPC multiplex trên connection đó có thể cùng đến backend đó, nhưng các client khác hoặc connection mới vẫn có thể được gắn vào instance khác. Đây là connection affinity, không phải định tuyến theo session nghiệp vụ.

## 3. Routing key phải ổn định và có phạm vi rõ

Sticky routing cần một **routing key** ổn định. Khóa có thể là session ID, job ID hoặc định danh tenant đã được xác thực. Các RPC thuộc cùng một phạm vi cần gửi cùng khóa:

~~~text
session S-42:
  StartCheckout  -> x-routing-key: S-42
  AddItem        -> x-routing-key: S-42
  GetCheckout    -> x-routing-key: S-42

session S-99:
  StartCheckout  -> x-routing-key: S-99
~~~

Routing key nên có các đặc điểm:

- Ổn định trong thời gian session hoặc workflow cần affinity.
- Có phạm vi duy nhất phù hợp, ví dụ kết hợp tenant và session nếu session ID chỉ duy nhất trong tenant.
- Không thay đổi theo từng RPC nếu muốn các RPC cùng phiên được định tuyến giống nhau.
- Không chứa dữ liệu cá nhân hoặc bí mật ở dạng rõ.
- Được tạo hoặc xác nhận từ danh tính đã xác thực, không tin một header tùy ý do caller tự khai báo.

Không nên dùng access token, email, số điện thoại hoặc dữ liệu nhạy cảm làm routing key. Có thể dùng một opaque identifier hoặc giá trị dẫn xuất có kiểm soát. Nếu cần kết hợp tenant và session, hãy mã hóa/canonicalize cặp khóa theo một quy ước nhất quán để tránh va chạm.

## 4. Các cách định tuyến theo khóa

Một load balancer hoặc proxy có thể dùng routing key theo nhiều cách:

| Cách chọn | Ý tưởng | Đặc điểm |
|---|---|---|
| Hash modulo số backend | `hash(key) % N` | Đơn giản; khi N thay đổi có thể remap nhiều key |
| Consistent hashing | Đặt backend và key trên vòng hash | Thường chỉ remap một phần key khi thêm/bớt backend |
| Ring hash / Maglev | Các thuật toán phân phối key ổn định trong proxy/control plane | Hữu ích cho affinity ở quy mô lớn; phụ thuộc implementation |
| Cookie hoặc header affinity | Proxy đọc cookie/header để chọn backend | Với gRPC thường dùng metadata/header; cần cấu hình proxy hiểu trường đó |
| Server-side session lookup | Backend được chọn tra session trong kho dùng chung | Có thể không cần affinity cứng; tăng phụ thuộc storage |

Các thuật toán hash không tự động có mặt chỉ vì client gửi một metadata key. Ví dụ `round_robin` chọn subchannel theo lượt, không hash theo `x-routing-key`. Muốn sticky routing, phải cấu hình policy/proxy hỗ trợ hash theo khóa, chẳng hạn ring-hash hoặc cơ chế định tuyến tương đương trong control plane.

Với xDS/service mesh, control plane có thể cung cấp endpoint và route/hash policy cho client hoặc proxy. Khả năng cụ thể phụ thuộc gRPC Java xDS integration, phiên bản, proxy và cấu hình triển khai. Không giả định một thuộc tính JSON bất kỳ sẽ được policy mặc định hiểu.

## 5. Gửi routing key trong gRPC metadata

gRPC metadata là nơi phù hợp để mang một routing hint không nhạy cảm theo từng RPC. Metadata được truyền cùng lời gọi và có thể được L7 proxy sử dụng nếu proxy được cấu hình hash theo header tương ứng.

Ví dụ client interceptor gắn khóa vào metadata:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class RoutingKeyClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> ROUTING_KEY =
            Metadata.Key.of(
                    "x-routing-key",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final String routingKey;

    public RoutingKeyClientInterceptor(String routingKey) {
        if (routingKey == null || routingKey.isBlank()) {
            throw new IllegalArgumentException("routingKey is required");
        }
        this.routingKey = routingKey;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                headers.put(ROUTING_KEY, routingKey);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

Có thể áp dụng interceptor cho stub/channel wrapper:

~~~java
import io.grpc.ClientInterceptors;

OrdersGrpc.OrdersBlockingStub sessionStub =
        OrdersGrpc.newBlockingStub(
                ClientInterceptors.intercept(
                        sharedOrdersChannel,
                        new RoutingKeyClientInterceptor(sessionKey)));
~~~

`sharedOrdersChannel` vẫn là channel dài hạn dùng chung; `ClientInterceptors.intercept` tạo lớp channel wrapper cho lời gọi, không tạo một kết nối transport mới. Nếu mỗi RPC có routing key khác nhau, tạo interceptor theo key của RPC đó hoặc dùng cơ chế truyền metadata theo request. Không lưu một routing key toàn cục trong singleton interceptor nếu nhiều session đồng thời dùng chung client service.

**Metadata chỉ mang khóa.** Nó không tự làm gRPC chọn backend theo khóa. L7 proxy, xDS policy hoặc custom load balancer phải được cấu hình đọc `x-routing-key` và áp dụng cùng thuật toán affinity. Nếu không có cấu hình đó, request vẫn được chọn theo policy hiện tại như `round_robin` hoặc `pick_first`.

## 6. Session state nên được lưu ở đâu?

Có ba mô hình thường gặp:

| Mô hình | State nằm ở đâu? | Khi backend restart hoặc đổi instance |
|---|---|---|
| Local session | RAM của một backend | State mất nếu không có snapshot/replication |
| Shared session store | Redis, database hoặc kho dùng chung | Backend khác có thể tải lại state |
| Stateless token | Client mang dữ liệu đã ký/mã hóa trong token | Không cần lookup cho state nhỏ; cần quản lý expiry, version và thu hồi |

**Local session + sticky routing** có thể giảm truy cập shared store và giữ cache nóng. Nhưng nó tạo phụ thuộc vào tuổi thọ instance, khiến scale-in, deploy và failover phức tạp hơn.

**Shared session store** thường bền vững hơn khi có nhiều replica. Mọi backend có quyền truy cập state theo session ID; sticky routing chỉ còn là tối ưu cache hoặc giảm contention.

**Stateless token** phù hợp khi state nhỏ, có thể xác minh độc lập và không cần cập nhật thường xuyên. Không đưa bí mật hoặc dữ liệu nhạy cảm vào token không mã hóa; chữ ký chỉ bảo vệ tính toàn vẹn, không che nội dung.

Trong thực tế có thể kết hợp: session chính lưu ở database/Redis, backend cache một phần, còn token chỉ mang định danh và version. Khi cache miss hoặc backend thay đổi, instance khác tải lại state từ nguồn dùng chung.

## 7. Nhất quán và cập nhật session

Sticky routing không bảo đảm hai RPC của cùng session chạy tuần tự. Client có thể gửi đồng thời `AddItem` và `ApplyCoupon`; cả hai đều được định tuyến đến cùng backend nhưng vẫn có thể chạy trên hai thread khác nhau hoặc hai connection khác nhau.

Nếu các thao tác cập nhật cùng state, cần cơ chế nhất quán:

- Optimistic locking bằng version hoặc compare-and-set.
- Transaction ở shared store.
- Idempotency key để xử lý request lặp.
- Serialize command theo session nếu thứ tự là yêu cầu nghiệp vụ.
- Đặt TTL/expiry và quy tắc cleanup cho session.

Ví dụ state có version:

~~~text
Session S-42, version 7
  RPC A đọc version 7
  RPC B đọc version 7
  RPC A ghi version 8 thành công
  RPC B ghi với expected version 7 -> conflict

Client/service đọc lại version 8 và quyết định xử lý tiếp
~~~

Không dùng affinity để thay thế khóa đồng thời hoặc transaction. Một session có thể được truy cập từ nhiều thiết bị, nhiều channel hoặc nhiều tiến trình client.

## 8. Khi backend bị lỗi hoặc topology thay đổi

Sticky routing không thể giữ một session mãi ở một instance. Backend có thể crash, bị ejection, scale-in hoặc bị gỡ khỏi service discovery. Khi tập backend thay đổi, thuật toán hash có thể ánh xạ một số key sang instance khác:

~~~text
Trước:
  key S-42 -> backend B

Backend B bị loại:
  key S-42 -> backend C

Backend C cần:
  tải session từ shared store
  hoặc khôi phục từ snapshot/replica
~~~

Với consistent hashing, thêm/bớt một backend thường giảm số key bị remap so với hash modulo đơn giản, nhưng không bảo đảm key luôn giữ nguyên backend. Nếu session chỉ tồn tại trong RAM, việc remap có thể làm mất phiên.

Khi backend sắp dừng:

1. Ngừng nhận session/RPC mới theo cơ chế drain.
2. Cho RPC đang chạy hoàn tất trong grace period.
3. Lưu hoặc đồng bộ state cần phục hồi.
4. Gỡ endpoint khỏi resolver/control plane.
5. Cho client reconnect và backend mới tải state theo session key.

Nếu cần duy trì session qua deploy, shared state hoặc cơ chế replication/snapshot phải là nền tảng chính. Sticky routing chỉ giảm số lần chuyển backend trong điều kiện bình thường.

## 9. Server streaming và affinity

Một server streaming RPC được gắn với backend đã nhận RPC khi nó bắt đầu. Routing key có thể giúp chọn đúng backend lúc mở stream, nhưng không chuyển stream sang backend khác khi kết nối bị ngắt.

~~~text
WatchSession(session = S-42, routing key = S-42)
  -> backend B
  <- event 1
  <- event 2
  <- event 3
  <- transport lỗi

Reconnect:
  WatchSession(after_sequence = 2, routing key = S-42)
  -> backend C sau khi topology thay đổi
  <- replay event 3, event 4, ...
~~~

Để resume:

- Event cần sequence hoặc cursor ổn định.
- Client lưu checkpoint sau khi áp dụng event bền vững.
- Backend mới đọc event từ nguồn dùng chung.
- Event replay cần idempotency/deduplication.

Không giữ nguồn event duy nhất trong RAM của backend được sticky routing chọn. Nếu instance mất, client không thể resume từ một nguồn đã biến mất.

## 10. Bảo mật và giới hạn của routing key

Routing key có thể ảnh hưởng backend nhận request, nên cần xem nó là dữ liệu đầu vào có tác động đến vận hành:

- Xác thực caller trước khi chấp nhận key có ý nghĩa định tuyến.
- Dẫn xuất key từ principal/tenant/session đã xác minh ở gateway hoặc service tin cậy.
- Không cho caller tự chọn key để né quota hoặc tập trung tải vào một backend.
- Không đưa token, email, số điện thoại hoặc dữ liệu nhạy cảm vào metadata.
- Giới hạn độ dài và định dạng key; tránh giá trị ngẫu nhiên quá nhiều làm tăng cardinality metric/cache.
- Không dùng routing key thay cho authorization; backend vẫn phải kiểm tra caller có quyền truy cập session đó.

Nếu nhiều tenant dùng chung một session ID, khóa phải bao gồm tenant scope hoặc một định danh toàn cục để tránh va chạm và rò rỉ dữ liệu chéo tenant.

## 11. Kiểm thử sticky routing và session recovery

Một test có một backend không chứng minh được affinity. Cần nhiều instance có thể nhận diện, một resolver/proxy hỗ trợ hash theo metadata và cách quan sát backend nhận từng RPC.

| Tình huống | Điều cần xác minh |
|---|---|
| Hai RPC cùng routing key | Được chọn cùng backend khi topology và policy không đổi |
| Hai session key khác nhau | Có thể được phân phối qua nhiều backend |
| Thiếu routing key | Dùng fallback policy hoặc từ chối theo hợp đồng đã chọn |
| Key do caller giả mạo | Gateway/service xác thực và chuẩn hóa key trước khi định tuyến |
| Backend chứa session local bị dừng | Session được phục hồi từ shared store hoặc trả lỗi rõ ràng |
| Thêm/bớt backend | Key có thể remap; state vẫn truy cập được |
| Hai RPC đồng thời cùng session | Không ghi đè state; version/transaction xử lý cạnh tranh |
| Stream bị ngắt | Client resume bằng cursor ở backend mới |
| Một session gửi quá nhiều request | Quota/rate limit vẫn áp dụng dù request cùng backend |
| Rolling upgrade | Session state và schema tương thích giữa phiên bản cũ/mới |

Test phải xác minh cả hai vế: routing key thật sự ảnh hưởng lựa chọn backend và state vẫn đúng khi affinity bị phá vỡ. Chỉ kiểm tra hai request đến cùng instance không chứng minh session có thể phục hồi sau failover.

## 12. Quan sát vận hành

Các chỉ số nên theo dõi:

- Tỷ lệ RPC theo backend và theo routing policy.
- Số key/session đang được cache tại mỗi instance.
- Cache hit/miss và số lần tải state từ shared store.
- Số session bị remap khi endpoint thay đổi.
- Số lần session recovery sau backend restart/ejection.
- Conflict/version retry và idempotency duplicate.
- Số stream reconnect/resume và khoảng sequence được replay.
- Phân bố tải theo tenant/backend để phát hiện key nóng.

Không xuất routing key thô vào metric label vì cardinality có thể tăng không giới hạn và có nguy cơ lộ dữ liệu. Có thể log một fingerprint đã băm theo cách có kiểm soát hoặc chỉ ghi instance ID, loại policy và kết quả remap.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ metadata tự tạo sticky routing | RPC vẫn được chọn theo policy hiện tại | Cấu hình proxy/xDS/custom policy đọc routing key |
| Dùng `round_robin` nhưng kỳ vọng cùng key về một backend | Các RPC cùng session có thể đi đến instance khác nhau | Dùng policy hash/affinity phù hợp |
| Chỉ lưu session trong RAM | Mất session khi backend restart hoặc remap | Shared store, snapshot hoặc token stateless |
| Coi sticky routing là authorization | Caller có thể giả mạo key để truy cập sai session | Xác thực và kiểm tra quyền ở backend |
| Dùng routing key chứa PII/token | Rò rỉ dữ liệu qua metadata/log | Dùng opaque key đã xác thực |
| Giả định cùng backend nghĩa là xử lý tuần tự | RPC đồng thời vẫn có race condition | Transaction, versioning hoặc serialization |
| Cho rằng stream tự chuyển backend | RPC hiện tại có thể lỗi giữa chừng | Reconnect/resume bằng cursor |
| Hash modulo backend count | Nhiều session bị remap khi topology đổi | Cân nhắc consistent hashing và shared state |

**Ghi nhớ:** Sticky routing giữ các RPC có cùng routing key trên cùng backend khi policy và topology cho phép; nó không phải nơi lưu session và không bảo đảm RPC chạy tuần tự. Với gRPC, cần phân biệt affinity theo TCP connection với affinity theo từng RPC, gửi routing key qua metadata và cấu hình L7 proxy/xDS/custom policy thực sự sử dụng khóa đó. Session quan trọng phải có shared state hoặc cơ chế phục hồi; backend đổi hoặc stream đứt vẫn cần recovery, idempotency và checkpoint.

# Cấu trúc LEASE: thời hạn hiệu lực, số yêu cầu và metadata

RSocket có cơ chế LEASE để một peer giới hạn số request mới mà peer còn lại được phép khởi tạo trong một khoảng thời gian. Cơ chế này hữu ích khi server cần bảo vệ tài nguyên, phân bổ quota theo tải hiện tại hoặc giới hạn tốc độ mở các interaction từ client.

Một frame `LEASE` mang ba phần thông tin cần hiểu rõ: thời hạn hiệu lực (TTL), số request được cấp và metadata tùy chọn. TTL quyết định quyền gửi tồn tại bao lâu; request count quyết định có thể khởi tạo bao nhiêu interaction; metadata bổ sung ngữ cảnh theo quy ước ứng dụng. Ba phần này có vai trò khác nhau và không thay thế backpressure của dữ liệu bên trong một stream.

## 1. LEASE nằm ở đâu trong vòng đời RSocket?

Khi mở kết nối, requester có thể bật cờ `L` trong frame `SETUP` để báo rằng nó sẽ tuân thủ cơ chế leasing do responder cấp. Khi đã chọn leasing, requester phải chờ một lease còn hiệu lực trước khi khởi tạo request. Responder có thể gửi các frame `LEASE` để cấp quyền theo từng khoảng thời gian.

```text
Requester / Client                         Responder / Server
       |                                           |
       |---------------- SETUP (L=1) ------------->|
       |                                           |
       |                  kiểm tra và chuẩn bị     |
       |                                           |
       |<--------------- LEASE --------------------|
       |             TTL, request count            |
       |                                           |
       |---- REQUEST_RESPONSE -------------------->|
       |---- REQUEST_FNF -------------------------->|
       |---- REQUEST_STREAM ---------------------->|
       |                                           |
       |       hết count hoặc hết TTL              |
       |                                           |
       |<--------------- LEASE mới ----------------|
       |---- REQUEST_CHANNEL --------------------->|
```

LEASE là frame cấp kết nối, có stream ID bằng `0`. Nó không phải một response của một request cụ thể và không mang ý nghĩa xác nhận xử lý nghiệp vụ. Nó cấp quyền để requester khởi tạo một số interaction mới trong thời hạn được nêu.

Nếu requester không bật leasing trong `SETUP`, requester không bị ràng buộc bởi quota LEASE theo cơ chế này và có thể khởi tạo request theo trạng thái kết nối cùng các giới hạn khác của hệ thống. Không nên bật cờ `L` rồi gửi request trước khi nhận lease: peer có thể từ chối request hoặc xử lý kết nối theo quy tắc vi phạm giao thức.

## 2. Cấu trúc frame LEASE

Frame `LEASE` có các trường chính:

| Trường | Ý nghĩa | Đơn vị / cách dùng |
| --- | --- | --- |
| Stream ID | Xác định đây là frame cấp kết nối | `0` |
| TTL | Thời gian lease còn hiệu lực | Millisecond (ms) |
| Request count | Số request mới tối đa được phép khởi tạo | Số lượng request |
| Metadata | Dữ liệu bổ sung tùy chọn do ứng dụng quy ước | Byte metadata |

Hai trường số TTL và request count là các giá trị unsigned 32-bit trong frame theo định dạng nhị phân của RSocket. TTL được tính bằng millisecond; request count là số interaction nguyên được cấp. Trước khi mã hóa, giá trị TTL sau khi đổi sang millisecond phải nằm trong miền unsigned 32-bit. Ở tầng ứng dụng, hãy dùng kiểu số đủ rộng để không làm sai giá trị khi chuyển đổi. Metadata là phần tùy chọn; nếu không cần ngữ cảnh bổ sung, frame có thể không mang metadata.

Ví dụ một grant minh họa:

```text
LEASE
  streamId     = 0
  ttl          = 5000 ms
  requestCount = 100
  metadata     = (optional) policy information
```

Trong ví dụ, requester có quyền khởi tạo tối đa 100 request trong vòng 5 giây của lease. Khi một trong hai điều kiện xảy ra — đã dùng hết 100 request hoặc TTL hết hạn — requester không được tiếp tục khởi tạo request bằng grant đó. Nó cần đợi lease mới.

TTL không phải timeout cho từng request. Một request đã được khởi tạo trong thời hạn lease có thể tiếp tục chạy sau khi TTL hết, theo timeout và vòng đời stream của chính request đó. TTL giới hạn thời điểm khởi tạo request mới.

## 3. TTL: thời hạn hiệu lực của quyền gửi

TTL (*Time To Live*) cho biết khoảng thời gian mà grant có hiệu lực. RSocket biểu diễn TTL bằng millisecond. Khi nhận lease, requester theo dõi thời điểm hết hạn và chỉ sử dụng quyền gửi trong khoảng thời gian còn hiệu lực.

Ví dụ:

| TTL được cấp | Request count | Ý nghĩa |
| --- | ---: | --- |
| 1.000 ms | 10 | Tối đa 10 request trong khoảng 1 giây |
| 5.000 ms | 100 | Tối đa 100 request trong khoảng 5 giây |
| 30.000 ms | 500 | Tối đa 500 request trong khoảng 30 giây |

Giả sử server cấp TTL 5 giây và 100 request:

- Client dùng hết 100 request sau 2 giây: client phải chờ lease tiếp theo dù TTL còn 3 giây.
- Client chỉ dùng 20 request trong 5 giây: 80 quyền chưa dùng cũng hết hạn khi TTL kết thúc.
- Client nhận lease mới sau khi grant cũ hết hạn: client sử dụng hạn mức theo grant mới.

Không nên dùng đồng hồ lịch của thiết bị để tự tính TTL vì đồng hồ có thể bị chỉnh giờ hoặc lệch giữa các máy. Runtime nên theo dõi thời lượng bằng clock đơn điệu (*monotonic clock*) theo cách thư viện RSocket triển khai. Ứng dụng không nên tự suy ra deadline bằng `LocalDateTime.now()`.

TTL bằng `0` hoặc giá trị không hợp lệ cần được xử lý theo quy tắc giao thức và implementation. Không tự diễn giải giá trị biên thành một lease vô hạn. Trong cấu hình ứng dụng, hãy dùng TTL dương và đủ dài cho round-trip mạng cùng thời gian xử lý dự kiến.

## 4. Request count: hạn mức tính theo interaction

Request count là số request mới requester được phép khởi tạo trong thời gian lease còn hiệu lực. Một request được tính khi mở interaction, bất kể interaction đó có trả về một hay nhiều payload.

Các interaction khởi tạo tiêu thụ hạn mức gồm:

- `REQUEST_RESPONSE`: một request-response tiêu thụ một quyền.
- `REQUEST_FNF`: một fire-and-forget tiêu thụ một quyền.
- `REQUEST_STREAM`: một request-stream tiêu thụ một quyền, dù responder phát nhiều payload.
- `REQUEST_CHANNEL`: một request-channel tiêu thụ một quyền, dù hai phía trao đổi nhiều payload trong channel.

Các frame tiếp tục một interaction đang tồn tại như `PAYLOAD`, `REQUEST_N`, `CANCEL` hoặc `COMPLETE` không phải là request mới và không tiêu thụ thêm request count của lease. Đây là khác biệt quan trọng giữa quota khởi tạo interaction và backpressure trong stream.

Ví dụ, một lease có request count bằng 3 có thể được dùng để mở:

```text
1. REQUEST_RESPONSE  -> còn 2 quyền
2. REQUEST_CHANNEL   -> còn 1 quyền
3. REQUEST_FNF       -> còn 0 quyền

PAYLOAD trong channel đang chạy không trừ thêm quota.
REQUEST_N để điều tiết demand cũng không trừ thêm quota.
```

Khi request count về 0, requester phải ngừng khởi tạo request mới cho tới khi nhận được lease tiếp theo. Các interaction đã mở vẫn tuân theo quy tắc stream, timeout và cancel của chúng.

## 5. TTL và request count phối hợp với nhau

Một lease có hai giới hạn độc lập:

- Giới hạn theo thời gian: grant không còn hiệu lực sau TTL.
- Giới hạn theo số lượng: grant không còn quyền khởi tạo request sau khi đã dùng hết request count.

Requester chỉ được mở request khi cả hai điều kiện đều đúng: lease chưa hết hạn và request count còn lớn hơn 0.

```text
                 Nhận LEASE
                      |
                      v
             +------------------+
             | TTL còn hiệu lực?|
             +------------------+
                | Có       | Không
                v          v
        +----------------+  Chờ LEASE mới
        | Count > 0 ?    |
        +----------------+
          | Có      | Không
          v         v
      Gửi request   Chờ LEASE mới
      trừ 1 count
          |
          +------ kiểm tra lại TTL và count
```

Ví dụ server cấp 50 request trong 10 giây. Nếu client phát 10 request mỗi giây, quota có thể hết sau 5 giây. Nếu client chỉ phát 2 request mỗi giây, TTL có thể hết trước khi dùng hết quota. Trong cả hai trường hợp, giới hạn nào đạt trước sẽ quyết định lúc client phải ngừng mở request mới.

## 6. Metadata trong frame LEASE

Metadata là phần tùy chọn để responder gửi thêm thông tin cùng grant. Nó được mã hóa theo quy ước metadata của kết nối RSocket; nếu kết nối dùng composite metadata, metadata có thể chứa nhiều entry có MIME type riêng.

Giao thức định nghĩa ý nghĩa của TTL và request count. Nội dung metadata bổ sung thường do ứng dụng tự quy ước. Ví dụ, metadata có thể mô tả:

- Tên chính sách quota mà server đang áp dụng, chẳng hạn `telemetry-standard`.
- Nhóm tài nguyên hoặc phạm vi dịch vụ mà grant hướng tới.
- Mức ưu tiên hoặc gợi ý để client điều chỉnh lịch gửi.
- Mã phiên bản của cấu trúc metadata ứng dụng.

Ví dụ minh họa metadata ở dạng dễ đọc:

```json
{
  "policy": "telemetry-standard",
  "scope": "device-group-7",
  "policyVersion": 2
}
```

Đây chỉ là ví dụ nội dung ứng dụng; frame thực tế chứa byte metadata và cách giải mã phụ thuộc metadata MIME type đã thống nhất. Metadata không thay đổi TTL hoặc request count đã được mã hóa trong các trường giao thức. Nếu metadata nói `policy=priority` nhưng request count chỉ là 10, client vẫn chỉ có 10 quyền theo grant đó.

Không xem metadata quota là bằng chứng xác thực hoặc quyền truy cập. Server vẫn phải xác thực requester và tự thực thi giới hạn ở phía server. Tránh đưa token, mật khẩu hoặc bí mật vào metadata LEASE vì metadata có thể xuất hiện trong log hoặc công cụ quan sát nếu không được bảo vệ cẩn thận.

## 7. Hướng cấp lease trong kết nối

Trong giao thức RSocket, responder gửi `LEASE` cho requester để giới hạn các request do requester khởi tạo trên kết nối đó. Với kết nối client-server thông thường, server là responder cấp grant và client là requester tiêu thụ quota.

- Server cấp lease cho client: client được phép mở request tới server theo TTL và request count.
- Client không gửi `LEASE` ngược lại để cấp quota cho server trên cùng kết nối theo cơ chế LEASE chuẩn.
- Nếu server chủ động mở request ngược về client, request đó không bị giới hạn bởi grant server đã cấp cho client. Muốn giới hạn chiều này, ứng dụng cần chính sách rate limit hoặc quota ở cấp nghiệp vụ phù hợp.

Cờ `L` trong `SETUP` báo requester sẽ tuân thủ LEASE từ responder. Khi bật cờ này, requester không gửi request trước khi nhận grant hợp lệ. Phía responder cấp lease cần chủ động phát `LEASE` theo chính sách tải và tài nguyên. Nếu ứng dụng không sử dụng leasing, không nên bật cờ này rồi giả định request vẫn được gửi tự do.

## 8. Lease không thay thế backpressure

Lease và backpressure kiểm soát hai vấn đề khác nhau:

| Cơ chế | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| LEASE | Số interaction mới được khởi tạo trong TTL | Tối đa 100 request trong 5 giây |
| Reactive Streams demand | Số payload được phát trong một stream theo nhu cầu subscriber | Subscriber yêu cầu thêm 20 phần tử |
| Rate limit ứng dụng | Tốc độ nghiệp vụ theo user, tenant hoặc thiết bị | Tối đa 10 lệnh điều khiển mỗi giây cho một thiết bị |
| Connection limit | Số kết nối hoặc channel đồng thời | Tối đa 500 channel hoạt động |

Ví dụ một client mở `REQUEST_STREAM` khi lease còn quyền. Request này tiêu thụ một request count. Sau đó server có thể phát hàng nghìn payload nếu subscriber tiếp tục yêu cầu và các giới hạn stream cho phép. Lease không giới hạn số payload bên trong stream đã mở.

Tương tự, một `REQUEST_CHANNEL` tiêu thụ một quyền khi mở channel. Các payload lệnh và kết quả trao đổi sau đó được điều tiết bằng demand hai chiều, không trừ thêm quota LEASE cho từng payload.

Do đó, server cần kết hợp quota khởi tạo interaction với backpressure, giới hạn channel, rate limit nghiệp vụ và giới hạn kích thước payload để bảo vệ toàn bộ tài nguyên.

## 9. Thiết kế chính sách quota ở server

Server có thể cấp lease dựa trên tải và mức dịch vụ. Một chính sách có thể xem xét:

- Số request đang hoạt động và số stream/channel đang mở.
- CPU, bộ nhớ, queue depth và độ trễ xử lý.
- Tenant, loại thiết bị hoặc mức dịch vụ của client.
- Tốc độ request gần đây và số lỗi do quá tải.
- Giới hạn tối đa cho mỗi kết nối và giới hạn tổng của toàn server.

Ví dụ chính sách minh họa:

| Trạng thái server | TTL | Request count | Ý định |
| --- | ---: | ---: | --- |
| Tải thấp | 5 giây | 100 | Cho phép client tạo nhiều interaction |
| Tải trung bình | 3 giây | 30 | Giảm số request mới |
| Gần ngưỡng quá tải | 1 giây | 5 | Hạn chế mạnh request mới |

Các con số trên chỉ là ví dụ để giải thích chính sách; hệ thống thực tế phải benchmark và điều chỉnh theo chi phí từng interaction. Một request-stream dài có thể tiêu tốn nhiều tài nguyên hơn một request-response ngắn, dù cả hai cùng trừ một đơn vị request count. Vì vậy request count không phải phép đo chính xác chi phí CPU hay bộ nhớ.

Server nên tránh cấp quota lớn hơn khả năng xử lý còn lại. Nếu cấp grant cho nhiều client, cần quản lý tổng ngân sách để tổng số quyền đã cấp không vượt quá mục tiêu bảo vệ tài nguyên. Cần tính đến quyền đã cấp nhưng chưa được sử dụng và thời gian grant còn hiệu lực.

## 10. Ví dụ cấu hình và vận hành với Java/Spring

Ở tầng ứng dụng, có thể mô hình hóa chính sách cấp lease bằng một cấu trúc chứa TTL, request count và metadata:

```java
public record LeasePolicy(
        Duration ttl,
        long requestCount,
        byte[] metadata
) {
    public LeasePolicy {
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        if (requestCount < 0 || requestCount > 0xFFFF_FFFFL) {
            throw new IllegalArgumentException("requestCount must fit an unsigned 32-bit field");
        }
    }
}
```

Ví dụ tạo chính sách:

```java
LeasePolicy policy = new LeasePolicy(
        Duration.ofSeconds(5),
        100,
        "policy=telemetry-standard".getBytes(StandardCharsets.UTF_8)
);
```

`LeasePolicy` là model nghiệp vụ minh họa, không phải class chuẩn của RSocket. Khi tích hợp, chuyển policy thành lease bằng API của phiên bản RSocket Java đang dùng và cấu hình phía connector/responder tương ứng. Trong Spring, có thể cung cấp `RSocketConnector` đã cấu hình cho `RSocketRequester` thông qua builder; phần phát lease cần được cấu hình ở responder/server. Tên method và API cụ thể có thể khác theo phiên bản thư viện.

Ví dụ phía client tạo requester với connector đã cấu hình:

```java
RSocketConnector connector = createConfiguredConnector();

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector)
        .tcp("localhost", 7000);
```

`createConfiguredConnector()` đại diện cho cấu hình connector theo phiên bản RSocket Java đang dùng, bao gồm bật hỗ trợ leasing nếu client cần tuân thủ lease. Đây là điểm tích hợp minh họa; hãy kiểm tra API phiên bản thực tế thay vì sao chép tên cấu hình giả định.

Ở phía client, ứng dụng thường không cần tự trừ quota song song với thư viện nếu RSocket requester đã quản lý lease. Nếu có tầng scheduler nghiệp vụ riêng, có thể quan sát trạng thái quota để điều phối công việc, nhưng quyết định cuối cùng vẫn phải tuân theo lease mà protocol runtime đang quản lý.

## 11. Kiểm thử TTL, request count và metadata

Kiểm thử leasing cần xác minh cả quyền gửi và thời điểm quyền hết hiệu lực.

| Trường hợp | Kết quả cần xác minh |
| --- | --- |
| Nhận lease hợp lệ | Requester có thể khởi tạo request |
| Chưa nhận lease khi `L=1` | Requester chưa gửi request mới |
| Dùng hết request count | Requester ngừng khởi tạo request dù TTL còn |
| TTL hết trước khi dùng hết count | Quyền còn lại hết hiệu lực |
| Nhận lease mới | Requester tiếp tục theo grant hợp lệ mới |
| Metadata có mặt | Metadata được giải mã theo MIME type đã thống nhất |
| Metadata không hợp lệ | Ứng dụng xử lý theo chính sách; không diễn giải sai TTL/count |
| Một request-stream dài | Chỉ interaction khởi tạo tiêu thụ quota; payload tiếp theo theo demand |
| Một request-channel dài | Channel mở tiêu thụ một quota; payload hai chiều không trừ request count mới |
| Server cấp lease cho client | Client tuân thủ grant khi khởi tạo request tới server; request ngược chiều do server khởi tạo cần chính sách giới hạn riêng |

Để kiểm thử TTL mà không làm test chậm, nên dùng clock có thể điều khiển nếu tầng chính sách ứng dụng hỗ trợ. Với integration test protocol, dùng thời gian ngắn nhưng đủ ổn định, chờ bằng tín hiệu hoặc deadline thay vì `Thread.sleep` tùy tiện.

Ngoài ra, cần kiểm thử server không cấp tổng quota vượt ngân sách, request bị từ chối khi hết quyền, và các interaction đang chạy vẫn hoàn tất theo chính sách khi lease hết hạn. Không nhầm việc hết lease với việc hủy các stream đã mở.

## 12. Các lỗi thiết kế thường gặp

**Nhầm TTL với timeout request.** TTL chỉ giới hạn lúc bắt đầu request mới. Timeout của một interaction đang chạy cần được cấu hình riêng.

**Nhầm request count với số payload.** Một request-stream hoặc request-channel chỉ tiêu thụ một quyền khi khởi tạo; các payload tiếp theo thuộc cùng stream.

**Chỉ giới hạn một chiều.** Lease được cấp theo hướng responder tới requester. Hệ thống hai chiều phải xác định chính sách cho từng hướng.

**Xem metadata là dữ liệu giao thức bắt buộc.** TTL và request count mới là hai trường quota chính. Metadata là tùy chọn và có ý nghĩa theo hợp đồng ứng dụng.

**Tự cộng quota không có cơ sở.** Ứng dụng nên để RSocket runtime quản lý vòng đời grant và chỉ dùng API được thư viện cung cấp. Không tự cộng request count giữa các frame nếu chưa hiểu rõ semantics của implementation.

**Cho rằng lease bảo vệ toàn bộ hệ thống.** Lease giới hạn số interaction mới, nhưng không thay thế backpressure, rate limit, giới hạn kết nối, giới hạn payload hoặc kiểm soát chi phí của stream dài.

## 13. Checklist triển khai

- [ ] Xác định requester nào sẽ tuân thủ leasing và bật cờ `L` trong `SETUP` phù hợp.
- [ ] Cấu hình responder cấp lease theo tải và ngân sách tài nguyên.
- [ ] Chọn TTL dương theo thời gian điều phối request dự kiến.
- [ ] Chọn request count dựa trên chi phí interaction và mức dịch vụ.
- [ ] Xác định metadata có cần thiết không, MIME type nào được dùng và schema/version của metadata.
- [ ] Không gửi request khi chưa có lease, lease hết TTL hoặc request count đã hết.
- [ ] Không trừ quota cho từng payload hoặc `REQUEST_N` trong stream đang chạy.
- [ ] Nhớ rằng LEASE chuẩn do responder cấp cho requester; giới hạn request ngược chiều cần chính sách ứng dụng riêng.
- [ ] Kết hợp lease với backpressure, rate limit, giới hạn channel và giám sát tải.
- [ ] Kiểm thử hết TTL, hết count, lease mới, metadata và stream dài.

LEASE là cơ chế cấp quyền khởi tạo request theo thời gian và số lượng. Khi hiểu đúng TTL, request count và metadata, ứng dụng có thể điều phối tải giữa nhiều client mà vẫn giữ được các stream đang chạy. Hãy xem quota là một phần của chính sách bảo vệ tài nguyên và kết hợp nó với backpressure cùng giới hạn nghiệp vụ để vận hành RSocket ổn định.

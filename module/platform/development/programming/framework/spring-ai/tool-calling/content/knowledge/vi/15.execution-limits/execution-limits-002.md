# Giới hạn lượt gọi của từng công cụ và toàn bộ một lượt hội thoại

Trong một vòng tool calling, mô hình có thể yêu cầu gọi cùng một công cụ nhiều lần, hoặc gọi nhiều công cụ khác nhau qua nhiều lượt trao đổi. Ví dụ, mô hình có thể phân trang kết quả tìm kiếm, tra cứu từng đơn hàng hoặc lặp lại một thao tác khi chưa đủ dữ liệu. Nếu không có giới hạn, một vòng lặp sai có thể tạo ra nhiều lời gọi dịch vụ, tăng độ trễ, chi phí và tải hệ thống.

Spring AI cung cấp hai giới hạn độc lập trong `DefaultToolCallingManager`:

- **Giới hạn theo từng công cụ:** một tên công cụ được gọi tối đa bao nhiêu lần trong một lượt hội thoại.
- **Giới hạn tổng:** tổng số lần gọi của tất cả công cụ trong cùng lượt hội thoại.

Trong Spring AI 2.1.0, mặc định là 40 lần cho mỗi công cụ và 150 lần tổng. Các giới hạn được tính theo lượt hiện tại, không phải toàn bộ lịch sử hội thoại. Bạn có thể điều chỉnh bằng Spring Boot properties hoặc builder của `ToolCallingManager`.

## Phân biệt một tool call, một vòng model và một lượt hội thoại

Các khái niệm này dễ bị nhầm khi cấu hình giới hạn:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Tool call | Một yêu cầu gọi một công cụ cụ thể. | Gọi `searchOrders` một lần với một trang kết quả. |
| Một vòng phản hồi của mô hình | Một lần mô hình trả về response; response có thể chứa không, một hoặc nhiều tool call. | Một response yêu cầu gọi `searchOrders` và `getCustomer`. |
| Một lượt hội thoại (turn) | Chuỗi xử lý bắt đầu từ một `UserMessage`, có thể gồm nhiều response của mô hình và nhiều tool result, cho đến khi kết thúc lượt. | Người dùng yêu cầu tìm đơn; mô hình gọi tìm kiếm ba lần, tra cứu chi tiết hai lần rồi trả lời. |
| Vòng lặp điều phối | Các lần gọi mô hình và công cụ lặp lại cho đến khi có câu trả lời cuối hoặc đạt điều kiện dừng. | Model → tool → model → tool → model. |

Một response của mô hình có thể chứa nhiều tool call. Một lượt hội thoại có thể chứa nhiều response như vậy. Giới hạn theo tool và giới hạn tổng của Spring AI đếm số tool call trong cả lượt, không chỉ đếm số lần gọi mô hình.

## Hai giới hạn mặc định của Spring AI

`DefaultToolCallingManager` áp dụng các giá trị mặc định sau ngay cả khi bạn không cấu hình builder:

| Giới hạn | Giá trị mặc định trong Spring AI 2.1.0 | Phạm vi |
|---|---:|---|
| `maxCallsPerTool` | 40 | Tối đa 40 lần cho mỗi tên công cụ trong một lượt. |
| `maxTotalToolCalls` | 150 | Tối đa 150 lần cộng tất cả công cụ trong một lượt. |
| `onLimitExceeded` | `THROW` | Ném lỗi khi chạm giới hạn. |

Ví dụ, trong một lượt:

- `searchOrders` được gọi 8 lần.
- `getOrderDetails` được gọi 4 lần.
- `getShipmentTracking` được gọi 3 lần.

Khi đó `searchOrders` dùng 8/40 lượt gọi của chính nó; tổng cộng cả ba công cụ dùng 15/150 lượt gọi. Chạm giới hạn riêng của một công cụ sẽ dừng công cụ đó ngay cả khi tổng vẫn còn nhiều. Chạm giới hạn tổng sẽ dừng thêm các công cụ khác dù từng công cụ chưa chạm giới hạn riêng.

Giới hạn theo từng công cụ giúp phát hiện một tool bị gọi lặp bất thường. Giới hạn tổng ngăn mô hình chia vòng lặp thành nhiều tên công cụ để né giới hạn riêng.

## Cấu hình bằng Spring Boot properties

Với ứng dụng Spring Boot dùng auto-configuration của Spring AI, có thể đặt giới hạn trong `application.yml`:

```yaml
spring:
  ai:
    tools:
      limits:
        max-calls-per-tool-default: 8
        max-calls-per-tool:
          searchOrders: 3
          getOrderDetails: 5
        excluded-tools:
          - emitProgress
        max-total-tool-calls: 12
        on-limit-exceeded: THROW
```

Trong ví dụ:

- Mỗi công cụ mặc định được gọi tối đa 8 lần trong một lượt.
- `searchOrders` có giới hạn riêng 3 lần.
- `getOrderDetails` có giới hạn riêng 5 lần.
- `emitProgress` được miễn giới hạn theo từng công cụ.
- Tổng số lần gọi của tất cả công cụ vẫn không vượt quá 12.
- Khi vượt giới hạn, manager dùng hành vi `THROW`.

Có thể cấu hình tương đương trong `application.properties`:

```properties
spring.ai.tools.limits.max-calls-per-tool-default=8
spring.ai.tools.limits.max-calls-per-tool.searchOrders=3
spring.ai.tools.limits.max-calls-per-tool.getOrderDetails=5
spring.ai.tools.limits.excluded-tools=emitProgress
spring.ai.tools.limits.max-total-tool-calls=12
spring.ai.tools.limits.on-limit-exceeded=THROW
```

Các property chính:

| Property | Ý nghĩa | Mặc định |
|---|---|---:|
| `spring.ai.tools.limits.max-calls-per-tool-default` | Giới hạn chung cho mỗi tool trong một lượt. | `40` |
| `spring.ai.tools.limits.max-calls-per-tool.<name>` | Ghi đè giới hạn cho một tên tool cụ thể. | Không có override |
| `spring.ai.tools.limits.excluded-tools` | Danh sách tên tool được miễn giới hạn riêng. | Rỗng |
| `spring.ai.tools.limits.max-total-tool-calls` | Giới hạn tổng số tool call trong một lượt. | `150` |
| `spring.ai.tools.limits.on-limit-exceeded` | Cách xử lý khi vượt giới hạn: `THROW` hoặc `RETURN_ERROR_RESPONSE`. | `THROW` |

Giá trị `-1` trong property giới hạn sẽ tắt giới hạn tương ứng. Hãy tránh tắt giới hạn tổng chỉ vì một công cụ cần nhiều lượt gọi; nên đặt override riêng cho công cụ đó và vẫn giữ giới hạn tổng.

## Ghi đè giới hạn bằng ToolCallingManager.Builder

Nếu ứng dụng tự tạo `ToolCallingManager`, có thể cấu hình giới hạn trực tiếp bằng builder:

```java
ToolCallingManager toolCallingManager = ToolCallingManager.builder()
        .maxCallsPerTool(8)
        .maxCallsPerTool("searchOrders", 3)
        .maxCallsPerTool("getOrderDetails", 5)
        .excludeToolFromLimit("emitProgress")
        .maxTotalToolCalls(12)
        .onLimitExceeded(ToolCallLimitBehavior.THROW)
        .build();
```

Các phương thức quan trọng:

| Builder method | Tác dụng |
|---|---|
| `maxCallsPerTool(int)` | Đặt giới hạn mặc định cho từng công cụ. |
| `maxCallsPerTool(String, int)` | Đặt giới hạn riêng cho một tên công cụ, ghi đè mức mặc định. |
| `excludeToolFromLimit(String)` | Miễn giới hạn theo tool cho tên được chỉ định. Công cụ vẫn tính vào giới hạn tổng. |
| `maxTotalToolCalls(int)` | Đặt giới hạn tổng cho mọi công cụ trong một lượt. |
| `onLimitExceeded(ToolCallLimitBehavior)` | Chọn `THROW` hoặc `RETURN_ERROR_RESPONSE`. |
| `unlimitedCallsPerTool()` | Tắt giới hạn mặc định theo từng công cụ. |
| `unlimitedTotalToolCalls()` | Tắt giới hạn tổng. |

`maxCallsPerTool("searchOrders", 3)` chỉ tác động đến công cụ có tên chính xác là `searchOrders`. Tên phải khớp với `ToolDefinition.name()` mà mô hình nhìn thấy; đổi tên tool cần rà lại cấu hình giới hạn.

Khi dùng builder thủ công, hãy cấu hình rõ các giới hạn mong muốn. Đừng mặc định rằng một manager được tạo bằng code sẽ nhận mọi property của Spring Boot giống bean auto-configured. Nếu muốn dùng cấu hình Boot, ưu tiên manager được auto-configure hoặc bind properties vào cấu hình builder của ứng dụng.

## Miễn giới hạn riêng không có nghĩa là không giới hạn

`excludeToolFromLimit("emitProgress")` chỉ miễn giới hạn số lần gọi riêng của `emitProgress`. Mọi lần gọi công cụ này vẫn được cộng vào `maxTotalToolCalls`.

Ví dụ, tổng giới hạn là 12 và `emitProgress` được miễn giới hạn riêng. Nếu mô hình gọi `emitProgress` 10 lần, sau đó gọi `searchOrders` 3 lần, tổng là 13. Lần gọi vượt giới hạn tổng vẫn bị chặn.

Chỉ miễn giới hạn riêng cho công cụ có đặc tính an toàn và chi phí thấp, ví dụ một callback phát tiến độ nội bộ không gọi dịch vụ tốn kém. Không miễn giới hạn cho công cụ ghi dữ liệu, gọi API tính phí hoặc truy vấn có thể trả khối lượng lớn chỉ để tránh lỗi giới hạn.

Hai builder `unlimitedCallsPerTool()` và `unlimitedTotalToolCalls()` tắt hai lớp bảo vệ tương ứng. Chỉ dùng khi ứng dụng có quota, timeout, rate limit và điều kiện dừng khác đủ mạnh; không dùng để xử lý một vòng lặp bất thường mà chưa tìm nguyên nhân.

## Cách đếm: giới hạn được tính trong lượt hiện tại

Spring AI không đếm toàn bộ lịch sử hội thoại mãi mãi. Manager xác định `UserMessage` cuối cùng trong prompt và chỉ đếm các `ToolResponseMessage` từ vị trí đó trở đi.

Ví dụ lịch sử:

```text
UserMessage: Hãy tìm đơn hàng của tôi.
AssistantMessage: yêu cầu gọi searchOrders
ToolResponseMessage: kết quả trang 1
AssistantMessage: yêu cầu gọi searchOrders
ToolResponseMessage: kết quả trang 2
AssistantMessage: câu trả lời cuối
UserMessage: Bây giờ hãy tra cứu trạng thái giao hàng.
AssistantMessage: yêu cầu gọi getShipmentTracking
ToolResponseMessage: trạng thái vận chuyển
```

Ở lượt thứ hai, bộ đếm bắt đầu từ `UserMessage` cuối cùng. Hai kết quả `searchOrders` của lượt trước không làm tăng bộ đếm của lượt mới.

Điều này cũng có ý nghĩa khi dùng `ChatMemory`: lịch sử cũ được nạp lại trước lượt hiện tại không làm tăng giới hạn, miễn là nó nằm trước `UserMessage` cuối cùng. Nếu advisor cắt bớt lịch sử nội bộ của vòng tool, manager vẫn dùng lịch sử đầy đủ của lượt hiện tại để đếm.

### Manager không giữ bộ đếm mutable dùng chung

`DefaultToolCallingManager` tính lại số lượng từ `prompt.getInstructions()` mỗi khi thực thi. Nó không lưu một bộ đếm toàn cục trên instance manager. Vì vậy, một manager có thể được chia sẻ giữa nhiều request đồng thời mà không làm bộ đếm của người dùng này cộng sang người dùng khác.

Điều này không có nghĩa toàn bộ callback đều tự động thread-safe. Các callback, service, client hoặc context mutable do ứng dụng tạo vẫn phải được thiết kế an toàn khi gọi đồng thời.

## Khi chạm giới hạn: THROW và RETURN_ERROR_RESPONSE

Spring AI hỗ trợ hai cách phản ứng:

| Hành vi | Kết quả | Khi phù hợp |
|---|---|---|
| `THROW` | `DefaultToolCallingManager` ném `ToolCallLimitExceededException`. | Muốn dừng lượt và để ứng dụng xử lý lỗi ở lớp gọi. |
| `RETURN_ERROR_RESPONSE` | Manager bỏ qua tool call vượt giới hạn và tạo `ToolResponse` báo lỗi để gửi lại mô hình. | Muốn mô hình biết đã chạm giới hạn và tiếp tục trả lời bằng dữ liệu đã có. |

### THROW

`ToolCallLimitExceededException` mang thông tin về tên công cụ bị giới hạn (giá trị `null` nếu vượt giới hạn tổng), mức giới hạn và `ToolExecutionResult` một phần đã hoàn thành trong batch hiện tại.

Khi chạy qua `ToolCallingAdvisor`, advisor bắt ngoại lệ và trả giới hạn như response cuối. Response có một `Generation` với finish reason riêng của `ToolCallLimitExceededException`; các tool call đã chạy thành công trước khi chạm giới hạn được giữ trong metadata partial responses.

Khi gọi `ToolCallingManager.executeToolCalls(...)` trực tiếp, ngoại lệ có thể đi lên caller. Ứng dụng cần bắt và chuyển thành lỗi API hoặc trạng thái workflow phù hợp.

Lưu ý: các tool call đã hoàn thành trước khi giới hạn bị chạm không tự động rollback. Nếu một batch có nhiều thao tác ghi, một phần có thể đã xảy ra trước khi phần còn lại bị chặn. Không coi giới hạn tool call là transaction bao trùm cả batch.

### RETURN_ERROR_RESPONSE

Khi chọn `RETURN_ERROR_RESPONSE`, manager không thực thi call vượt giới hạn. Nó tạo một tool response lỗi để mô hình biết rằng không thể gọi thêm công cụ theo policy hiện tại. Mô hình có thể tiếp tục hội thoại và đưa ra câu trả lời dựa trên kết quả đã có.

Đây thường là lựa chọn phù hợp khi ứng dụng gọi `ToolCallingManager.executeToolCalls(...)` trực tiếp và muốn giữ quyền điều phối. Hãy bảo đảm thông báo lỗi gửi mô hình không chứa thông tin nội bộ hoặc cấu hình giới hạn nhạy cảm.

## Cấu hình mẫu cho một ứng dụng hỗ trợ đơn hàng

Giả sử ứng dụng có các công cụ:

| Công cụ | Đặc điểm | Giới hạn gợi ý trong ví dụ |
|---|---|---:|
| `searchOrders` | Truy vấn phân trang, có thể cần vài lần gọi. | 4 lần |
| `getOrderDetails` | Đọc chi tiết một đơn cụ thể. | 5 lần |
| `getShipmentTracking` | Tra cứu trạng thái vận chuyển. | 3 lần |
| `emitProgress` | Phát tiến độ nội bộ, không gọi dịch vụ nghiệp vụ nặng. | Miễn giới hạn riêng |

Cấu hình:

```yaml
spring:
  ai:
    tools:
      limits:
        max-calls-per-tool-default: 5
        max-calls-per-tool:
          searchOrders: 4
          getOrderDetails: 5
          getShipmentTracking: 3
        excluded-tools:
          - emitProgress
        max-total-tool-calls: 10
        on-limit-exceeded: RETURN_ERROR_RESPONSE
```

Trong cấu hình này, `emitProgress` vẫn tiêu thụ một lượt trong tổng 10 lần. Nếu mô hình gọi `searchOrders` 4 lần, `getOrderDetails` 5 lần và `getShipmentTracking` 1 lần, tổng đã là 10. Một tool call tiếp theo bị chặn dù `getShipmentTracking` chưa chạm giới hạn riêng.

Giới hạn là ví dụ để minh họa. Hãy chọn số phù hợp với kích thước dữ liệu, số trang tối đa, SLA, chi phí và đặc tính của dịch vụ phía sau.

## Giới hạn tool call không thay thế các ngân sách khác

Hai giới hạn của `DefaultToolCallingManager` chỉ đếm số tool call trong một lượt. Chúng không giới hạn đầy đủ tài nguyên của một yêu cầu.

| Loại giới hạn | Câu hỏi | Nơi nên kiểm soát |
|---|---|---|
| Per-tool call limit | Một công cụ được gọi bao nhiêu lần trong một lượt? | `maxCallsPerTool`. |
| Total tool call limit | Tổng số lần gọi tất cả công cụ trong một lượt? | `maxTotalToolCalls`. |
| Model iteration limit | Mô hình được phép phản hồi/lặp tối đa bao nhiêu vòng? | Vòng điều phối hoặc advisor policy của ứng dụng. |
| Timeout | Một tool call hoặc toàn request được chạy tối đa bao lâu? | HTTP client, service timeout và deadline của request. |
| Rate limit | Một user/tenant được gửi bao nhiêu request trong một khoảng thời gian? | API gateway, bucket/token bucket hoặc quota service. |
| Concurrency limit | Bao nhiêu tool call được chạy đồng thời? | Executor, semaphore, bulkhead hoặc giới hạn pool. |
| Token/cost budget | Một lượt hội thoại được tiêu thụ bao nhiêu token hoặc chi phí? | Theo dõi usage qua các vòng model và áp ngân sách ở tầng ứng dụng. |
| Data/page limit | Một tool được phép trả bao nhiêu bản ghi hoặc byte? | Schema, validation và service nghiệp vụ. |

Ví dụ, một lượt có thể chỉ gọi `searchOrders` một lần nhưng truy vấn trả về một triệu bản ghi. Per-tool limit không ngăn được payload quá lớn. Cần giới hạn page size và kích thước kết quả ở service.

Tương tự, một công cụ gọi API ngoài có thể treo 60 giây. Giới hạn số lần gọi không thay thế timeout. Một user cũng có thể gửi hàng nghìn lượt riêng biệt; giới hạn theo turn không thay thế rate limit hoặc quota theo ngày.

## Phối hợp giới hạn với retry và thao tác ghi

Một số công cụ có lý do hợp lệ để được gọi nhiều lần, như phân trang, tìm kiếm theo nhiều bộ lọc hoặc tra cứu nhiều tài nguyên. Hãy thiết kế giới hạn dựa trên hành vi nghiệp vụ:

- Đặt giới hạn riêng cho công cụ có số lần gọi dự kiến cao.
- Đặt giới hạn tổng để ngăn mô hình phân tán lời gọi qua nhiều công cụ.
- Giới hạn `pageSize`, độ sâu phân trang và số phần tử trong arguments.
- Dùng cursor hoặc continuation token do ứng dụng cấp thay vì để mô hình tự tạo offset không giới hạn.
- Dùng idempotency key cho thao tác ghi để retry không tạo giao dịch trùng.
- Chỉ retry lỗi tạm thời và đặt retry budget nằm trong timeout tổng.
- Không tự động tăng giới hạn khi thấy lỗi; trước hết xác định mô hình đang lặp do thiếu dữ liệu, mô tả tool mơ hồ hay service trả kết quả không hữu ích.

Với thao tác ghi, số lần gọi nhỏ vẫn có thể gây hậu quả lớn. Authorization, xác nhận của người dùng, trạng thái nghiệp vụ và audit log vẫn phải được thực hiện ở service.

## Kiểm thử giới hạn thực thi

Hãy kiểm thử cả đường tự động qua `ToolCallingAdvisor` và đường gọi `ToolCallingManager` trực tiếp nếu ứng dụng dùng cả hai.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Một tool được gọi dưới giới hạn | Callback chạy và kết quả được thêm vào conversation history. |
| Một tool chạm giới hạn riêng | Lần gọi tiếp theo của tool đó bị xử lý theo `onLimitExceeded`. |
| Nhiều tool cùng được gọi | Tổng số lần gọi được cộng trên toàn bộ tên tool. |
| Một tool có override riêng | Override thắng giới hạn mặc định. |
| Một tool nằm trong `excluded-tools` | Không bị giới hạn riêng nhưng vẫn tính vào giới hạn tổng. |
| Tổng số call vượt giới hạn | Không có call vượt mức nào được thực thi. |
| `THROW` qua advisor | Response cuối biểu diễn limit breach và giữ metadata partial responses. |
| `THROW` qua manager trực tiếp | Caller nhận `ToolCallLimitExceededException` và xử lý phù hợp. |
| `RETURN_ERROR_RESPONSE` | Tool response lỗi được tạo và mô hình có thể tiếp tục với thông tin giới hạn. |
| Lịch sử có tool response từ turn cũ | Không làm tăng bộ đếm của turn hiện tại. |
| Memory advisor nạp lại lịch sử | Chỉ tool response sau `UserMessage` cuối cùng được tính. |
| Hai request đồng thời | Bộ đếm của các lượt độc lập không ảnh hưởng lẫn nhau. |
| Một batch có call thành công trước khi chạm limit | Partial result được giữ; không giả định các thao tác đã chạy được rollback. |
| Vượt timeout hoặc quota user | Lớp timeout/quota tương ứng hoạt động độc lập với tool call limit. |

Có thể dùng callback giả có bộ đếm để xác minh số lần thực thi. Dùng model giả lập để tạo chuỗi tool call xác định, tránh phụ thuộc việc model thật có lặp đúng số lần trong mỗi lần chạy hay không.

## Bài tập thực hành

Tạo một vòng tool calling cho hệ thống đơn hàng:

1. Đăng ký `searchOrders`, `getOrderDetails` và `getShipmentTracking`.
2. Cấu hình giới hạn mặc định 5, riêng `searchOrders` là 3 và tổng là 8.
3. Gọi `searchOrders` nhiều lần trong một lượt để kiểm tra giới hạn riêng.
4. Gọi xen kẽ ba công cụ để kiểm tra giới hạn tổng.
5. Miễn giới hạn riêng cho `emitProgress`, sau đó chứng minh nó vẫn tính vào tổng.
6. Chạy lại với `THROW`, kiểm tra `ToolCallLimitExceededException` và partial result.
7. Chạy với `RETURN_ERROR_RESPONSE`, xác nhận mô hình nhận thông báo giới hạn và có thể kết thúc câu trả lời.
8. Tạo một lượt `UserMessage` mới và chứng minh bộ đếm được đặt lại theo turn.
9. Bổ sung timeout, page-size limit và rate limit theo tenant để thấy sự khác biệt giữa các lớp bảo vệ.

Bạn hoàn thành khi có thể giải thích tại sao một tool call bị chặn, giới hạn nào đã chạm, các thao tác nào đã hoàn tất trước đó và cách ứng dụng xử lý phần kết quả còn lại.

## Danh sách kiểm tra trước khi triển khai

- [ ] Có giới hạn mặc định cho mỗi tool.
- [ ] Có giới hạn tổng cho toàn bộ tool call trong một lượt.
- [ ] Tool cần nhiều lần gọi có override riêng dựa trên nhu cầu nghiệp vụ.
- [ ] Tool được miễn giới hạn riêng vẫn bị tính vào giới hạn tổng.
- [ ] Không tắt cả hai giới hạn nếu chưa có cơ chế bảo vệ thay thế.
- [ ] `onLimitExceeded` được chọn rõ giữa `THROW` và `RETURN_ERROR_RESPONSE`.
- [ ] Caller xử lý `ToolCallLimitExceededException` và partial result đúng cách.
- [ ] Hiểu bộ đếm chỉ tính `ToolResponseMessage` từ `UserMessage` cuối cùng của turn hiện tại.
- [ ] Không nhầm tool call limit với model iteration, timeout, rate limit, concurrency hoặc token/cost budget.
- [ ] Service giới hạn page size, kích thước payload và số lượng kết quả.
- [ ] Tool ghi dữ liệu có authorization, confirmation và idempotency khi cần.
- [ ] Có kiểm thử giới hạn riêng, giới hạn tổng, excluded tool, hai hành vi khi vượt limit và request đồng thời.

Giới hạn theo từng công cụ ngăn một callback bị gọi lặp quá nhiều; giới hạn tổng ngăn mô hình chia số lần gọi qua nhiều công cụ. Hãy kết hợp hai giới hạn này với giới hạn vòng lặp, timeout, quota và validation nghiệp vụ để một lượt hội thoại luôn nằm trong ngân sách mà ứng dụng có thể kiểm soát.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 – DefaultToolCallingManager API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/DefaultToolCallingManager.html)
- [Spring AI 2.1.0 – ToolCallingProperties.Limits API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/autoconfigure/ToolCallingProperties.Limits.html)
- [Spring AI Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

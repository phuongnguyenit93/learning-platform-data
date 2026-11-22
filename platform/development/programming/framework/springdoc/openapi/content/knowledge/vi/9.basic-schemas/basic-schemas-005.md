# Ngày, giờ, thời lượng, UUID và các định dạng cần đối chiếu

API thường trao đổi các giá trị ngày sinh, ngày giao hàng, thời điểm tạo giao dịch, giờ mở cửa, thời lượng xử lý hoặc mã định danh duy nhất. Trong Java, những dữ liệu này có các kiểu chuyên biệt như **LocalDate**, **OffsetDateTime**, **Duration** và **UUID**. Trong JSON, chúng thường được truyền dưới dạng chuỗi. OpenAPI dùng **type: string** kết hợp **format** để mô tả cách diễn giải chuỗi đó, giúp người đọc, Swagger UI, validator và công cụ sinh client hiểu ý nghĩa của dữ liệu.

Khi dùng springdoc-openapi, schema có thể được suy ra từ kiểu Java và các annotation. Tuy nhiên, kiểu Java, cách Jackson tuần tự hóa JSON và **format** trong OpenAPI là ba lớp khác nhau. Một tài liệu có **format: date-time** không tự bảo đảm JSON thực tế có múi giờ; annotation **@Schema** cũng không tự thay đổi cách Jackson đọc hoặc ghi dữ liệu. Cần thiết kế hợp đồng trước, cấu hình chuyển đổi phù hợp và kiểm tra đặc tả cùng request/response thực tế.

## 1. format có ý nghĩa gì trong OpenAPI?

Schema OpenAPI mô tả kiểu dữ liệu JSON bằng các giá trị như **string**, **number**, **integer**, **boolean**, **object** và **array**. Thuộc tính **format** bổ sung một quy ước cụ thể cho kiểu dữ liệu, ví dụ:

~~~yaml
type: string
format: date
~~~

Schema trên cho biết giá trị là chuỗi biểu diễn một ngày theo định dạng **date**. Tương tự, **format: uuid** cho biết chuỗi có hình dạng mã UUID. **format** giúp công cụ tạo giao diện nhập liệu, kiểm tra dữ liệu hoặc sinh kiểu tương ứng cho ngôn ngữ lập trình.

Không nên xem **format** là cơ chế xác thực duy nhất. Theo OpenAPI 3.1, **format** mặc định được xử lý như annotation không bắt buộc validator phải kiểm tra. Khả năng hỗ trợ phụ thuộc vào từng công cụ; công cụ không nhận ra format có thể chỉ sử dụng **type: string**. Vì vậy, API vẫn cần parse và xác thực dữ liệu ở runtime, đồng thời kiểm thử schema bằng validator phù hợp.

OpenAPI 3.1 sử dụng hệ thống schema dựa trên JSON Schema 2020-12 và Format Registry của OpenAPI. Các format ngày, giờ, thời lượng và UUID được liệt kê trong registry gồm **date**, **date-time**, **time**, **duration** và **uuid**. Registry còn phân biệt **date-time-local** và **time-local** cho giá trị không chứa múi giờ hoặc offset. Công cụ không bắt buộc phải hỗ trợ mọi format trong registry, nên cần xác nhận khả năng tương thích của bộ công cụ đang sử dụng.

## 2. Chọn kiểu Java theo ý nghĩa thời gian

Trước khi chọn **format**, cần chọn đúng kiểu Java. Các kiểu trong **java.time** phân biệt ngày lịch, giờ trên đồng hồ, thời điểm tuyệt đối và thời lượng:

| Kiểu Java | Ý nghĩa | Ví dụ biểu diễn |
| --- | --- | --- |
| **LocalDate** | Ngày lịch, không có giờ và múi giờ | **2026-11-20** |
| **LocalTime** | Giờ trên đồng hồ, không có ngày hoặc múi giờ | **09:30:00** |
| **OffsetTime** | Giờ trên đồng hồ kèm offset UTC | **09:30:00+07:00** |
| **LocalDateTime** | Ngày và giờ địa phương, không có offset hoặc múi giờ | **2026-11-20T09:30:00** |
| **Instant** | Một thời điểm trên dòng thời gian, thường biểu diễn UTC | **2026-11-20T02:30:00Z** |
| **OffsetDateTime** | Ngày giờ kèm offset UTC | **2026-11-20T09:30:00+07:00** |
| **ZonedDateTime** | Ngày giờ gắn với múi giờ có quy tắc, ví dụ Asia/Ho_Chi_Minh | **2026-11-20T09:30:00+07:00[Asia/Ho_Chi_Minh]** |
| **Duration** | Khoảng thời gian tính theo giây và nano giây | **PT1H30M** |
| **Period** | Khoảng thời gian theo đơn vị lịch như năm, tháng, ngày | **P1Y2M3D** |
| **UUID** | Mã định danh 128-bit | **550e8400-e29b-41d4-a716-446655440000** |

**LocalDate** phù hợp với ngày sinh, ngày nghỉ hoặc ngày giao hàng. **LocalDateTime** phù hợp khi nghiệp vụ chỉ quan tâm giờ địa phương, ví dụ giờ hẹn tại một địa điểm đã biết. **Instant** hoặc **OffsetDateTime** phù hợp với thời điểm sự kiện cần so sánh nhất quán giữa các hệ thống.

**LocalDateTime** không chứa thông tin để xác định một thời điểm duy nhất trên toàn cầu. Ví dụ **2026-11-20T09:30:00** có thể chỉ 09:30 ở nhiều múi giờ khác nhau. Nếu API dùng giá trị đó để lên lịch gửi tiền, đặt vé hoặc xử lý sự kiện xuyên quốc gia, cần quy định múi giờ hoặc gửi thêm zone ID. Không tự gán UTC cho **LocalDateTime** nếu hợp đồng chưa quy định như vậy.

**OffsetDateTime** lưu offset, chẳng hạn **+07:00**, nhưng không lưu tên múi giờ như **Asia/Ho_Chi_Minh**. **ZonedDateTime** có thông tin vùng và quy tắc đổi giờ theo lịch. Nếu cần bảo toàn tên vùng múi giờ qua API, có thể công bố hai trường riêng, ví dụ **localDateTime** và **timeZone** (**Asia/Ho_Chi_Minh**), thay vì giả định mọi client đều hiểu phần **[Asia/Ho_Chi_Minh]** trong chuỗi Java.

## 3. Các format thường dùng

Bảng sau là quy ước schema hữu ích cho OpenAPI 3.1. Với các format mở rộng hoặc ít được công cụ hỗ trợ, hãy kiểm tra phiên bản OpenAPI và toolchain trước khi công bố:

| Ý nghĩa | Schema OpenAPI gợi ý | Ví dụ |
| --- | --- | --- |
| Ngày lịch | **type: string**, **format: date** | **2026-11-20** |
| Ngày giờ có offset hoặc UTC | **type: string**, **format: date-time** | **2026-11-20T09:30:00+07:00** |
| Ngày giờ không có múi giờ | **type: string**, **format: date-time-local** | **2026-11-20T09:30:00** |
| Giờ có offset | **type: string**, **format: time** | **09:30:00+07:00** |
| Giờ không có offset | **type: string**, **format: time-local** | **09:30:00** |
| Thời lượng | **type: string**, **format: duration** | **PT1H30M** |
| Mã UUID | **type: string**, **format: uuid** | **550e8400-e29b-41d4-a716-446655440000** |

**date** và **date-time** là các format quen thuộc từ OpenAPI 3.0. Trong OpenAPI 3.1, các format như **time**, **duration**, **uuid**, **date-time-local** và **time-local** được mô tả trong hệ sinh thái JSON Schema/OpenAPI Format Registry. Với tài liệu OpenAPI 3.0, một số công cụ vẫn hiểu **uuid** hoặc các format mở rộng theo quy ước riêng, nhưng không nên giả định mọi validator hoặc client generator xử lý chúng giống nhau.

Đối với **LocalDateTime** và **LocalTime**, không nên gắn **date-time** hoặc **time** chỉ vì tên kiểu Java có chữ Date hoặc Time. Các format **date-time** và **time** theo RFC 3339 có thành phần offset. Nếu chuỗi không có offset, hãy dùng format local tương ứng khi toolchain hỗ trợ, hoặc mô tả rõ pattern và ngữ nghĩa bằng **description** khi cần tương thích với công cụ cũ.

## 4. Mô tả schema trong OpenAPI YAML

Ví dụ dưới đây mô tả một sự kiện có ngày tổ chức, thời điểm bắt đầu, giờ mở cửa địa phương, thời lượng dự kiến và mã người phụ trách:

~~~yaml
components:
  schemas:
    Event:
      type: object
      required:
        - id
        - eventDate
        - startsAt
      properties:
        id:
          type: string
          format: uuid
          description: Mã định danh sự kiện
          example: 550e8400-e29b-41d4-a716-446655440000
        eventDate:
          type: string
          format: date
          description: Ngày diễn ra sự kiện theo lịch địa phương
          example: 2026-11-20
        startsAt:
          type: string
          format: date-time
          description: Thời điểm bắt đầu kèm offset UTC
          example: 2026-11-20T09:30:00+07:00
        doorsOpenAt:
          type: string
          format: time-local
          description: Giờ mở cửa theo đồng hồ địa phương của địa điểm
          example: 08:45:00
        expectedDuration:
          type: string
          format: duration
          description: Thời lượng dự kiến theo định dạng duration
          example: PT1H30M
~~~

Các thuộc tính **required**, **description** và **example** giúp schema dễ sử dụng hơn. **required** cho biết trường phải có mặt trong object; nó không đồng nghĩa với việc chuỗi phải khác rỗng hoặc đúng format. **example** minh họa giá trị, nhưng cũng không thay thế xác thực. Với OpenAPI 3.1, có thể bổ sung **minLength**, **maxLength** hoặc **pattern** nếu cần ràng buộc cấu trúc chuỗi cụ thể.

## 5. Khai báo kiểu dữ liệu Java và annotation springdoc

springdoc-openapi đọc kiểu Java và annotation OpenAPI để sinh schema. Ví dụ một DTO dùng Java record:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.UUID;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

public record CreateEventRequest(
    @NotNull
    @Schema(
        description = "Ngày diễn ra sự kiện",
        type = "string",
        format = "date",
        example = "2026-11-20"
    )
    LocalDate eventDate,

    @NotNull
    @Schema(
        description = "Thời điểm bắt đầu kèm offset",
        type = "string",
        format = "date-time",
        example = "2026-11-20T09:30:00+07:00"
    )
    OffsetDateTime startsAt,

    @Schema(
        description = "Thời điểm địa phương, không chứa offset",
        type = "string",
        format = "date-time-local",
        example = "2026-11-20T09:30:00"
    )
    LocalDateTime localReminderAt,

    @Schema(
        description = "Thời lượng dự kiến",
        type = "string",
        format = "duration",
        example = "PT1H30M"
    )
    Duration expectedDuration,

    @NotNull
    @Schema(
        description = "Mã người phụ trách",
        type = "string",
        format = "uuid",
        example = "550e8400-e29b-41d4-a716-446655440000"
    )
    UUID organizerId
) {
}
~~~

**@Schema** dùng để điều chỉnh mô tả OpenAPI. **type** và **format** ở đây giúp công bố hợp đồng rõ ràng khi kiểu Java hoặc phiên bản thư viện suy ra chưa đúng với ý nghĩa mong muốn. Chúng không thay đổi cách Jackson serialize/deserialize JSON, cũng không tự chuyển đổi request parameter.

Đối với nhiều kiểu **java.time**, swagger-core có các model converter để suy ra schema. Kết quả phụ thuộc phiên bản swagger-core mà springdoc đang sử dụng và phiên bản OpenAPI được cấu hình. Các bản swagger-core mới đã bổ sung ánh xạ Java time theo OpenAPI Format Registry; release notes của springdoc cũng ghi nhận thay đổi cho **Duration**, **LocalTime** và **OffsetTime**. Vì vậy, không nên giả định hai dự án dùng phiên bản springdoc khác nhau sẽ luôn sinh cùng một **format**. Hãy kiểm tra **/v3/api-docs** và dùng **@Schema(format = "...")** để ghi đè khi cần.

Một số release note của springdoc còn ghi nhận converter có thể sinh format **partial-time** cho kiểu giờ Java. Tên này không nằm trong nhóm format chuẩn thường dùng của OpenAPI Format Registry hiện tại. Nếu tài liệu của dự án xuất hiện **partial-time**, hãy kiểm tra khả năng hỗ trợ của validator và client generator; có thể ghi đè bằng **time-local** hoặc **time** khi ngữ nghĩa dữ liệu phù hợp, hoặc giữ **type: string** kèm mô tả pattern rõ ràng để ưu tiên tương thích.

## 6. Phân biệt chuyển đổi request với mô tả OpenAPI

Ba cơ chế thường bị nhầm lẫn:

| Cơ chế | Vai trò | Phạm vi |
| --- | --- | --- |
| **@DateTimeFormat** | Chỉ định cách Spring chuyển đổi giá trị chuỗi thành kiểu Java khi bind dữ liệu web | Query parameter, path variable, form field và data binding của Spring |
| **@JsonFormat** | Chỉ định hình dạng Jackson dùng khi đọc hoặc ghi JSON | JSON request body và response body |
| **@Schema** | Mô tả kiểu, format, ví dụ và ý nghĩa trong đặc tả OpenAPI | Tài liệu API và công cụ đọc OpenAPI |

Ví dụ với query parameter:

~~~java
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/events")
public List<EventResponse> findByDate(
        @RequestParam("date")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return eventService.findByDate(date);
}
~~~

Request:

~~~text
GET /api/events?date=2026-11-20
~~~

**@DateTimeFormat** hướng dẫn Spring parse query string thành **LocalDate**. Với JSON body, Jackson đảm nhiệm chuyển đổi. Nếu ứng dụng dùng pattern tùy chỉnh, cần cấu hình Jackson tương ứng, ví dụ qua **@JsonFormat** hoặc **ObjectMapper**:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.OffsetDateTime;

public record EventPayload(
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    OffsetDateTime startsAt
) {
}
~~~

Trong phần lớn API, nên ưu tiên định dạng ISO-8601/RFC 3339 thống nhất thay vì pattern riêng. Pattern tùy chỉnh chỉ nên dùng khi hợp đồng có yêu cầu cụ thể và cần được mô tả rõ trong OpenAPI. Nếu **@Schema** công bố **date-time** nhưng Jackson lại serialize thành mảng số hoặc chuỗi không có offset, tài liệu và dữ liệu thực tế sẽ không khớp.

## 7. Phân biệt Duration và Period

**Duration** và **Period** đều biểu diễn khoảng thời gian nhưng dùng cho các phép tính khác nhau:

- **Duration** biểu diễn lượng thời gian liên tục theo giây và nano giây. Ví dụ **Duration.ofHours(2)** có thể biểu diễn là **PT2H**; **Duration.ofDays(1)** tương đương đúng 24 giờ.
- **Period** biểu diễn đơn vị lịch như năm, tháng và ngày. Ví dụ **Period.ofMonths(1)** là một tháng lịch, không phải số giây cố định; tháng có thể có 28, 29, 30 hoặc 31 ngày.

Format **duration** phù hợp với chuỗi duration theo quy ước RFC 3339/ISO-8601 được công cụ hỗ trợ. Ví dụ:

| Giá trị | Ý nghĩa |
| --- | --- |
| **PT15M** | 15 phút |
| **PT1H30M** | 1 giờ 30 phút |
| **P2DT3H** | 2 ngày và 3 giờ theo biểu diễn duration |
| **P1Y2M3D** | 1 năm, 2 tháng và 3 ngày theo biểu diễn lịch |

Không dùng **Duration** để mô tả một tháng lịch hoặc một năm lịch. Nếu nghiệp vụ cần lịch gia hạn, kỳ thanh toán hoặc thời hạn theo tháng, cần chọn **Period** hoặc mô hình số tháng/ngày riêng và mô tả quy tắc tính toán. Nếu API muốn truyền số giây thay vì chuỗi ISO-8601, hãy công bố schema số, đơn vị và phạm vi rõ ràng, ví dụ **type: integer**, **format: int64**, **description: Thời lượng tính bằng giây**.

## 8. UUID và cách công bố mã định danh

Java có kiểu **java.util.UUID** để biểu diễn mã định danh 128-bit. Trong JSON, UUID thường được serialize thành chuỗi dạng canonical gồm 5 nhóm ký tự hexadecimal phân tách bằng dấu gạch ngang:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Schema OpenAPI:

~~~yaml
type: string
format: uuid
example: 550e8400-e29b-41d4-a716-446655440000
~~~

Với DTO dùng **UUID**, Jackson có thể đọc/ghi chuỗi UUID và springdoc thường suy ra schema dạng string. Nếu dùng **String** thay cho **UUID**, hãy khai báo **@Schema(type = "string", format = "uuid")** để công bố rõ ý nghĩa. Khi dùng **String**, ứng dụng cũng phải tự xác thực chuỗi bằng parser hoặc constraint thích hợp; **format: uuid** trong tài liệu không tự biến một chuỗi bất kỳ thành UUID.

Với path variable, Spring có thể bind trực tiếp:

~~~java
@GetMapping("/api/events/{id}")
public EventResponse getEvent(@PathVariable UUID id) {
    return eventService.getById(id);
}
~~~

Nếu client gửi giá trị không parse được thành UUID, request sẽ thất bại trong quá trình chuyển đổi trước khi vào logic nghiệp vụ. Hãy xác định response lỗi chuẩn cho trường hợp đó và mô tả mã trạng thái phù hợp trong OpenAPI.

## 9. Kiểm tra format trong tài liệu được sinh

Sau khi ứng dụng khởi động, mở endpoint mặc định **/v3/api-docs** hoặc endpoint đã tùy chỉnh. Tìm schema tương ứng trong **components.schemas** và kiểm tra:

1. **type** có đúng là **string** khi dữ liệu được truyền dưới dạng chuỗi hay không.
2. **format** có phù hợp với ngữ nghĩa: **date**, **date-time**, **date-time-local**, **time**, **time-local**, **duration** hoặc **uuid**.
3. **example** có đúng cú pháp và cùng kiểu dữ liệu với schema không.
4. Mô tả có nói rõ múi giờ, offset, đơn vị duration và cách dùng UUID không.
5. Các trường bắt buộc, nullable và validation có khớp với DTO không.
6. JSON thực tế được Jackson tạo ra có cùng hình dạng mà schema công bố hay không.

Có thể kiểm tra nhanh bằng cách tải đặc tả:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Sau đó kiểm tra response JSON thực tế của endpoint, đặc biệt với **LocalDateTime**, **ZonedDateTime** và **Duration**. Một số cấu hình Jackson có thể serialize giá trị thời gian thành chuỗi, số hoặc cấu trúc khác. Nếu dùng custom serializer/deserializer, schema phải mô tả đúng biểu diễn trên dây thay vì chỉ dựa vào kiểu Java.

## 10. Validation và các lỗi thường gặp

**format** giúp mô tả quy ước, còn validation runtime cần được thực hiện ở ứng dụng. Có thể kết hợp:

- **@NotNull** để yêu cầu trường phải có giá trị;
- **@Past**, **@PastOrPresent**, **@Future** hoặc **@FutureOrPresent** cho quy tắc thời gian phù hợp;
- **@Pattern** nếu API nhận chuỗi với pattern riêng;
- kiểu Java chuyên biệt như **LocalDate**, **OffsetDateTime**, **Duration** hoặc **UUID** để parser từ chối dữ liệu không hợp lệ;
- kiểm tra nghiệp vụ bổ sung khi cần ràng buộc múi giờ, khoảng thời gian hoặc quan hệ giữa nhiều trường.

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **LocalDateTime** được mô tả là **date-time** dù không có offset | Kiểu Java không chứa múi giờ nhưng schema dùng format có offset | Dùng **date-time-local** khi toolchain hỗ trợ, hoặc mô tả pattern và quy ước local rõ ràng |
| Thời điểm bị lệch khi client ở múi giờ khác | API nhận **LocalDateTime** nhưng các bên diễn giải theo zone khác nhau | Dùng **Instant**/**OffsetDateTime** hoặc truyền thêm zone ID theo hợp đồng |
| **ZonedDateTime** xuất ra chuỗi có phần **[Region/City]** nhưng validator mong RFC 3339 | Biểu diễn Java giữ tên vùng múi giờ ngoài định dạng date-time chuẩn | Dùng **OffsetDateTime**/**Instant** cho timestamp hoặc tách **zoneId** thành trường riêng |
| **Duration** xuất ra số thay vì chuỗi **PT...** | Jackson được cấu hình ghi duration dưới dạng số hoặc custom serializer | Đồng bộ JSON serializer và schema; công bố đơn vị nếu dùng số |
| Validator bỏ qua **format: uuid** hoặc **format: duration** | Công cụ không hỗ trợ format hoặc chỉ xem format là annotation | Kiểm tra khả năng validator và thực hiện validation ở server |
| Swagger UI hiển thị trường thời gian như chuỗi thường | UI không hỗ trợ format hoặc tài liệu không sinh format mong muốn | Kiểm tra **/v3/api-docs**, phiên bản swagger-core và annotation **@Schema** |
| Query parameter thời gian không parse được nhưng JSON body vẫn hoạt động | **@DateTimeFormat** và Jackson có cấu hình khác nhau | Cấu hình riêng cho Spring data binding và JSON serialization |
| UUID không hợp lệ chỉ bị phát hiện trong service | DTO dùng **String** nên không có bước parse sớm | Dùng **UUID** hoặc validation chuỗi trước khi xử lý nghiệp vụ |

Một điểm cần lưu ý là **@DateTimeFormat** có phạm vi của Spring data binding, còn **@JsonFormat** thuộc Jackson. Chỉnh một annotation không đảm bảo cả query parameter và JSON body thay đổi theo cùng cách. Hãy kiểm tra riêng từng nguồn request.

## 11. Nguyên tắc thiết kế

Chọn kiểu Java dựa trên ý nghĩa nghiệp vụ, sau đó chọn schema và format phản ánh đúng cách dữ liệu được truyền qua HTTP. Dùng **LocalDate** cho ngày lịch, **LocalTime** cho giờ địa phương, **Instant** hoặc **OffsetDateTime** cho thời điểm có thể so sánh giữa hệ thống, **Duration** cho thời lượng liên tục và **UUID** cho mã định danh. Chỉ dùng **LocalDateTime** khi múi giờ được hiểu từ ngữ cảnh nghiệp vụ hoặc được truyền riêng.

Giữ định dạng nhất quán giữa request, response, Jackson và OpenAPI. Khi nâng cấp springdoc hoặc swagger-core, hãy xem lại schema được sinh cho các kiểu thời gian vì converter có thể thay đổi cách gán **format**. Không dựa vào một ví dụ Swagger UI để kết luận dữ liệu đã được xác thực; hãy kiểm tra đặc tả, JSON thực tế và hành vi parse của ứng dụng.

## 12. Tài liệu tham khảo chính thức

- [OpenAPI Specification 3.1.2 — Data Type Formats](https://spec.openapis.org/oas/v3.1.2.html#data-type-format) — vai trò của **format** và tính tùy chọn của validation.
- [OpenAPI Formats Registry](https://spec.openapis.org/registry/format/) — các format **date**, **date-time**, **date-time-local**, **time**, **time-local**, **duration** và **uuid**.
- [Java SE — java.time](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html) — ý nghĩa các kiểu ngày giờ trong Java.
- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring/reference/core/validation/format.html) — **@DateTimeFormat**, **@DurationFormat** và chuyển đổi dữ liệu của Spring.
- [Spring Boot — JSON](https://docs.spring.io/spring-boot/reference/features/json.html) — cấu hình JSON mapper và serializer/deserializer.
- [Swagger Core Releases](https://github.com/swagger-api/swagger-core/releases) — thay đổi converter Java time và hỗ trợ OpenAPI Format Registry.
- [Springdoc OpenAPI Releases](https://github.com/springdoc/springdoc-openapi/releases) — thay đổi ánh xạ schema theo phiên bản springdoc.

Khi schema mô tả đúng ngày, giờ, thời lượng và UUID, client có thể tạo dữ liệu theo quy ước chung và công cụ có thể hỗ trợ kiểm tra tốt hơn. Điều quyết định vẫn là sự thống nhất giữa kiểu Java, JSON được serialize, định dạng OpenAPI và quy tắc validation thực thi trong ứng dụng Spring Boot.

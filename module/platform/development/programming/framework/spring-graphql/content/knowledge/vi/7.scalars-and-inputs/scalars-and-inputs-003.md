# Date và DateTime scalar

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt dữ liệu ngày lịch với thời điểm trên dòng thời gian.
- Giải thích vì sao GraphQL không có sẵn scalar Date và DateTime.
- Chọn kiểu Java phù hợp như `LocalDate`, `OffsetDateTime` và `Instant`.
- Đăng ký Date và DateTime scalar trong Spring for GraphQL.
- Mapping scalar vào argument, input object và kết quả trả về.
- Thiết kế quy tắc timezone, định dạng, nullability và kiểm thử dữ liệu thời gian.

## 1. Vì sao cần Date và DateTime scalar?

GraphQL định nghĩa năm scalar tích hợp sẵn: `Int`, `Float`, `String`, `Boolean` và `ID`. Không có scalar chuẩn tên `Date` hoặc `DateTime`.

Nếu một API dùng `String` cho mọi giá trị thời gian, schema sẽ không thể hiện rõ định dạng và ý nghĩa của dữ liệu. Ví dụ, hai giá trị sau đều là chuỗi nhưng biểu diễn hai khái niệm khác nhau:

- `2026-11-20`: một ngày lịch, không có giờ và múi giờ.
- `2026-11-20T09:30:00+07:00`: một thời điểm với giờ và độ lệch UTC.

Khi khai báo custom scalar, schema thể hiện ý nghĩa dữ liệu rõ hơn:

~~~graphql
scalar Date
scalar DateTime

type Appointment {
  serviceDate: Date!
  startsAt: DateTime!
}
~~~

Client biết `serviceDate` là ngày lịch và `startsAt` là thời điểm. Server cũng có thể kiểm tra định dạng đầu vào và chuyển đổi thành kiểu Java phù hợp.

Điểm quan trọng là tên scalar không tự định nghĩa định dạng. Ứng dụng phải chọn một quy ước thống nhất về cách parse input, cách serialize output, timezone và lỗi dữ liệu không hợp lệ.

## 2. Phân biệt Date và DateTime

`Date` và `DateTime` không nên được dùng thay thế cho nhau.

| Khái niệm | Ví dụ | Kiểu Java phù hợp | Có timezone? |
|---|---|---|---|
| Ngày lịch | `2026-11-20` | `LocalDate` | Không |
| Thời điểm kèm offset | `2026-11-20T09:30:00+07:00` | `OffsetDateTime` | Có độ lệch UTC |
| Thời điểm tuyệt đối | `2026-11-20T02:30:00Z` | `Instant` | UTC |
| Giờ địa phương không có ngày | `09:30:00` | `LocalTime` | Không |
| Ngày giờ địa phương chưa xác định múi giờ | `2026-11-20T09:30:00` | `LocalDateTime` | Không |

### Date: ngày lịch

Ngày lịch thường dùng cho ngày sinh, ngày phát hành hóa đơn, ngày nghỉ, ngày đặt lịch theo lịch địa phương hoặc ngày hết hạn được định nghĩa theo lịch.

Java `LocalDate` phù hợp vì chỉ chứa năm, tháng và ngày. Nó không mang giờ hoặc timezone. Một ngày lịch không nên bị tự động chuyển thành UTC hoặc cộng trừ offset.

Ví dụ:

~~~java
LocalDate serviceDate = LocalDate.of(2026, 11, 20);
~~~

### DateTime: thời điểm có offset

Một thời điểm cần được xác định rõ trên dòng thời gian. Giá trị có offset như `2026-11-20T09:30:00+07:00` cho biết giờ địa phương và độ lệch so với UTC.

Java `OffsetDateTime` phù hợp khi hợp đồng API cần mang theo offset. `Instant` phù hợp khi ứng dụng chỉ cần biểu diễn một thời điểm tuyệt đối theo UTC.

Ví dụ:

~~~java
OffsetDateTime localTime = OffsetDateTime.parse(
        "2026-11-20T09:30:00+07:00");

Instant instant = localTime.toInstant();
~~~

Hai giá trị này biểu diễn cùng một thời điểm. `OffsetDateTime` giữ offset đầu vào; `Instant` biểu diễn thời điểm đó trên trục UTC.

### Offset không giống timezone

Offset như `+07:00` chỉ cho biết độ lệch so với UTC tại thời điểm đó. Nó không lưu tên múi giờ và các quy tắc lịch sử hoặc daylight saving time.

Nếu nghiệp vụ cần biết người dùng đặt lịch theo múi giờ nào, chẳng hạn `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`, hãy lưu thêm Zone ID. Có thể truyền một field riêng:

~~~graphql
input AppointmentTimeInput {
  startsAt: DateTime!
  timeZone: String!
}
~~~

Server xác thực `timeZone` bằng `ZoneId.of(...)` và áp dụng quy tắc nghiệp vụ. Không nên giả định rằng một offset cố định luôn đại diện cho một timezone.

## 3. Quy ước định dạng nên thống nhất

Một API cần quy định rõ định dạng input và output. Một lựa chọn phổ biến là dùng biểu diễn ISO-8601:

- Date: `yyyy-MM-dd`, ví dụ `2026-11-20`.
- DateTime: dạng date-time có offset hoặc UTC, ví dụ `2026-11-20T09:30:00+07:00` hoặc `2026-11-20T02:30:00Z`.

Ví dụ GraphQL variables:

~~~json
{
  "date": "2026-11-20",
  "startsAt": "2026-11-20T09:30:00+07:00"
}
~~~

Các quy tắc nên thống nhất:

1. Date chỉ nhận ngày hợp lệ theo lịch Gregorian; không nhận giờ hoặc offset.
2. DateTime phải chứa offset hoặc ký hiệu UTC `Z`, nếu hợp đồng yêu cầu xác định thời điểm tuyệt đối.
3. Chọn độ chính xác phần giây, ví dụ giây hoặc mili giây, và giữ nhất quán.
4. Quy định cách chuẩn hóa output: giữ offset ban đầu hay chuyển tất cả về UTC.
5. Từ chối input sai định dạng hoặc ngày không tồn tại, chẳng hạn `2026-02-30`.

Không nên âm thầm diễn giải DateTime không có offset theo timezone mặc định của máy chủ. Kết quả khi đó có thể thay đổi giữa môi trường phát triển, staging và production.

## 4. Dùng Extended Scalars trong Spring for GraphQL

Bạn có thể tự viết custom scalar bằng GraphQL Java. Tuy nhiên, với các kiểu thời gian phổ biến, thư viện GraphQL Java Extended Scalars cung cấp sẵn những scalar đã triển khai quy tắc chuyển đổi.

Khai báo property phiên bản tương thích với GraphQL Java do Spring Boot quản lý, rồi thêm dependency Maven:

~~~xml
<dependency>
    <groupId>com.graphql-java</groupId>
    <artifactId>graphql-java-extended-scalars</artifactId>
    <version>${graphql-java-extended-scalars.version}</version>
</dependency>
~~~

Chọn phiên bản Extended Scalars tương thích với phiên bản GraphQL Java mà Spring Boot đang quản lý. Không nên nâng riêng GraphQL Java chỉ để thêm scalar nếu chưa kiểm tra ma trận tương thích.

Đăng ký scalar bằng `RuntimeWiringConfigurer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer dateScalars() {
        return wiringBuilder -> wiringBuilder
                .scalar(ExtendedScalars.Date)
                .scalar(ExtendedScalars.DateTime);
    }
}
~~~

Ở đây:

- `ExtendedScalars.Date` cung cấp scalar Date, thường ánh xạ sang `java.time.LocalDate`.
- `ExtendedScalars.DateTime` cung cấp scalar DateTime, ánh xạ sang `java.time.OffsetDateTime`.
- `RuntimeWiringConfigurer` được Spring Boot phát hiện và áp dụng khi xây dựng GraphQL runtime.

Tên scalar trong SDL phải trùng với tên scalar được đăng ký. Nếu schema khai báo `scalar DateTime` nhưng runtime không đăng ký scalar tương ứng, quá trình tạo schema hoặc thực thi coercion sẽ không hoạt động như mong đợi.

## 5. Khai báo Date và DateTime trong SDL

Ví dụ schema cho lịch hẹn:

~~~graphql
scalar Date
scalar DateTime

type Query {
  appointment(id: ID!): Appointment
}

type Mutation {
  reschedule(
    id: ID!
    serviceDate: Date!
    startsAt: DateTime!
  ): Appointment!
}

type Appointment {
  id: ID!
  serviceDate: Date!
  startsAt: DateTime!
}
~~~

Schema thể hiện rõ:

- `serviceDate` là ngày lịch và bắt buộc có giá trị.
- `startsAt` là thời điểm có offset và bắt buộc có giá trị.
- Mutation `reschedule` yêu cầu client gửi cả ngày lịch và thời điểm bắt đầu.
- Query trả về cùng kiểu scalar để client nhận định dạng nhất quán.

Nếu ngày hoặc thời điểm có thể chưa được xác định, hãy cân nhắc bỏ dấu `!` ở field tương ứng. Quyết định nullability phải phản ánh nghiệp vụ, không chỉ kiểu Java.

## 6. Mapping Date và DateTime sang Java

Dùng `LocalDate` cho Date và `OffsetDateTime` cho DateTime khi dùng Extended Scalars tương ứng.

Ví dụ DTO:

~~~java
import java.time.LocalDate;
import java.time.OffsetDateTime;

public record Appointment(
        String id,
        LocalDate serviceDate,
        OffsetDateTime startsAt) {
}
~~~

Controller:

~~~java
@Controller
public class AppointmentController {

    private final AppointmentService appointmentService;

    public AppointmentController(
            AppointmentService appointmentService) {
        this.appointmentService = appointmentService;
    }

    @QueryMapping
    public Appointment appointment(@Argument String id) {
        return appointmentService.findById(id);
    }

    @MutationMapping
    public Appointment reschedule(
            @Argument String id,
            @Argument LocalDate serviceDate,
            @Argument OffsetDateTime startsAt) {

        return appointmentService.reschedule(
                id, serviceDate, startsAt);
    }
}
~~~

GraphQL Java thực hiện scalar coercion khi nhận biến và serialize kết quả. Spring for GraphQL sau đó bind argument đã được chuyển đổi vào tham số Java.

Với input Date:

~~~graphql
mutation {
  reschedule(
    id: "apt-01"
    serviceDate: "2026-11-20"
    startsAt: "2026-11-20T09:30:00+07:00"
  ) {
    id
    serviceDate
    startsAt
  }
}
~~~

Kết quả Date được chuyển thành `LocalDate`, còn DateTime thành `OffsetDateTime`. Khi trả về response, scalar chuyển các kiểu Java đó thành chuỗi theo quy tắc serialize của scalar.

Nếu dùng input object, có thể gom các field thời gian vào DTO:

~~~graphql
input RescheduleInput {
  serviceDate: Date!
  startsAt: DateTime!
}
~~~

~~~java
public record RescheduleInput(
        LocalDate serviceDate,
        OffsetDateTime startsAt) {
}

@MutationMapping
public Appointment reschedule(
        @Argument String id,
        @Argument RescheduleInput input) {

    return appointmentService.reschedule(
            id, input.serviceDate(), input.startsAt());
}
~~~

Cấu trúc input object vẫn phải khai báo trong SDL và kiểu Java phải bind được các field tương ứng.

## 7. Khi nào nên dùng Instant thay cho OffsetDateTime?

Trong nhiều hệ thống, database lưu thời điểm theo UTC và Java domain model dùng `Instant`. Tuy nhiên, scalar DateTime phổ biến có thể trả về `OffsetDateTime`. Khi đó, có thể chuyển đổi ở ranh giới API.

Ví dụ:

~~~java
Instant storedAt = appointment.getStartsAt();

OffsetDateTime responseTime = storedAt.atOffset(ZoneOffset.UTC);
~~~

Khi nhận input:

~~~java
Instant normalized = startsAt.toInstant();
~~~

Cách này giữ một mô hình lưu trữ nhất quán theo UTC, trong khi API vẫn thể hiện rõ offset. Nếu cần hiển thị theo timezone người dùng, chuyển đổi ở tầng trình bày hoặc nghiệp vụ với Zone ID đã được xác thực.

Không nên lưu một thời điểm quan trọng dưới dạng chuỗi tùy ý trong database nếu hệ thống cần so sánh, sắp xếp hoặc tính toán thời gian. Hãy dùng kiểu temporal phù hợp của database và Java.

## 8. Tự triển khai custom scalar khi cần quy tắc riêng

Extended Scalars đáp ứng nhiều nhu cầu thông thường. Nếu API có định dạng đặc thù, cần kiểm soát chặt chẽ cách parse/serialize hoặc cần dùng kiểu Java khác, bạn có thể tự tạo scalar bằng GraphQL Java.

Một scalar cần định nghĩa ít nhất ba chiều chuyển đổi:

- **serialize:** chuyển giá trị Java thành giá trị JSON trả cho client.
- **parseValue:** chuyển biến đầu vào từ JSON thành kiểu Java.
- **parseLiteral:** chuyển literal trong GraphQL document thành kiểu Java.

Ví dụ khung triển khai Date với `LocalDate`:

~~~java
GraphQLScalarType dateScalar = GraphQLScalarType.newScalar()
        .name("Date")
        .description("Calendar date in ISO-8601 yyyy-MM-dd format")
        .coercing(new Coercing<LocalDate, String>() {

            @Override
            public String serialize(
                    Object input,
                    GraphQLContext context,
                    Locale locale) throws CoercingSerializeException {
                if (input instanceof LocalDate date) {
                    return date.toString();
                }
                throw new CoercingSerializeException(
                        "Date must be a LocalDate");
            }

            @Override
            public LocalDate parseValue(
                    Object input,
                    GraphQLContext context,
                    Locale locale) throws CoercingParseValueException {
                if (input instanceof String value) {
                    try {
                        return LocalDate.parse(value);
                    }
                    catch (DateTimeParseException ex) {
                        throw new CoercingParseValueException(
                                "Date must use yyyy-MM-dd format", ex);
                    }
                }
                throw new CoercingParseValueException(
                        "Date input must be a string");
            }

            @Override
            public LocalDate parseLiteral(
                    Value<?> input,
                    CoercedVariables variables,
                    GraphQLContext context,
                    Locale locale) throws CoercingParseLiteralException {
                if (input instanceof StringValue value) {
                    try {
                        return LocalDate.parse(value.getValue());
                    }
                    catch (DateTimeParseException ex) {
                        throw new CoercingParseLiteralException(
                                "Date literal must use yyyy-MM-dd format", ex);
                    }
                }
                throw new CoercingParseLiteralException(
                        "Date literal must be a string");
            }
        })
        .build();
~~~

Đây là mẫu theo chữ ký Coercing của các phiên bản GraphQL Java hiện đại. Nếu dự án dùng phiên bản cũ hơn, chữ ký phương thức có thể khác; hãy đối chiếu Javadoc đúng phiên bản được Spring Boot quản lý.

Đăng ký scalar vừa tạo:

~~~java
@Bean
RuntimeWiringConfigurer dateScalarConfigurer() {
    return wiringBuilder -> wiringBuilder.scalar(dateScalar);
}
~~~

Trong mã production, nên đặt scalar factory ở một lớp riêng, kiểm thử cả ba đường chuyển đổi và dùng exception chuyên biệt của GraphQL Java. Không trả về null khi input sai định dạng vì điều đó che giấu lỗi hợp đồng.

## 9. Xử lý timezone và các lỗi thường gặp

Thời gian là nguồn gây lỗi phổ biến vì cùng một chuỗi có thể được diễn giải khác nhau tùy timezone và quy tắc chuyển đổi.

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ngày bị lệch một ngày sau khi lưu | Chuyển LocalDate thành timestamp UTC không đúng ngữ nghĩa | Giữ LocalDate cho ngày lịch |
| Thời điểm khác nhau giữa các môi trường | Parse DateTime không có offset theo timezone mặc định | Yêu cầu offset hoặc Z |
| Mất timezone người dùng | Chỉ lưu offset như +07:00 | Lưu thêm Zone ID nếu nghiệp vụ cần |
| Input không hợp lệ | Chuỗi sai ISO-8601 hoặc ngày không tồn tại | Để scalar từ chối input và trả lỗi rõ ràng |
| Sai số thời gian | Cắt hoặc làm tròn phần giây không thống nhất | Quy định độ chính xác và chuẩn hóa ở một tầng |
| Thời gian bị đổi khi serialize | Chuyển OffsetDateTime sang UTC hoặc ngược lại ngoài ý muốn | Chọn chính sách giữ offset hay chuẩn hóa UTC |

Một số ví dụ nên được kiểm tra rõ:

- Date hợp lệ: `2026-11-20`.
- Date không hợp lệ: `2026-02-30`.
- DateTime có offset: `2026-11-20T09:30:00+07:00`.
- DateTime UTC: `2026-11-20T02:30:00Z`.
- DateTime thiếu offset: `2026-11-20T09:30:00` — từ chối nếu hợp đồng yêu cầu thời điểm tuyệt đối.

Không nên tự động thêm `Z` vào một giá trị không có offset. Việc đó thay đổi ý nghĩa thời gian và có thể tạo ra thời điểm khác với ý định của client.

## 10. Kiểm thử Date và DateTime scalar

Nên kiểm thử cả đường input và output. Với Spring for GraphQL, `GraphQlTester` cho phép gửi operation và xác minh response mà không phụ thuộc vào cách client thực tế gọi API.

Ví dụ test mutation:

~~~java
@Test
void rescheduleShouldPreserveDateAndOffset() {
    GraphQlTester.Response response = graphQlTester.document("""
            mutation Reschedule(
                $id: ID!,
                $serviceDate: Date!,
                $startsAt: DateTime!
            ) {
                reschedule(
                    id: $id,
                    serviceDate: $serviceDate,
                    startsAt: $startsAt
                ) {
                    serviceDate
                    startsAt
                }
            }
            """)
            .variable("id", "apt-01")
            .variable("serviceDate", "2026-11-20")
            .variable("startsAt", "2026-11-20T09:30:00+07:00")
            .execute();

    response.path("reschedule.serviceDate")
            .entity(String.class)
            .isEqualTo("2026-11-20");

    response.path("reschedule.startsAt")
            .entity(String.class)
            .isEqualTo("2026-11-20T09:30:00+07:00");
}
~~~

Có thể xác minh thêm `startsAt` để bảo đảm offset được serialize theo chính sách đã chọn. Nếu ứng dụng chuẩn hóa về UTC, kỳ vọng phải là `2026-11-20T02:30:00Z`.

Các trường hợp nên có trong bộ test:

1. Date hợp lệ và DateTime có offset hợp lệ.
2. Date không tồn tại theo lịch.
3. DateTime thiếu offset hoặc sai định dạng.
4. DateTime dùng UTC ký hiệu Z.
5. Giá trị có phần giây lẻ nếu API hỗ trợ.
6. Field nullable nhận null và field non-null từ chối null.
7. Input object chứa các field Date và DateTime.
8. Round-trip: parse input thành Java temporal type rồi serialize về response.

Với custom scalar tự viết, kiểm thử riêng `serialize`, `parseValue` và `parseLiteral`. Một scalar có thể hoạt động với variables nhưng thất bại khi client viết literal trực tiếp trong GraphQL document nếu chỉ triển khai một trong hai đường parse.

## 11. Nguyên tắc thiết kế API thời gian

Khi thiết kế Date và DateTime cho một GraphQL API, hãy thống nhất các nguyên tắc sau:

- Dùng Date cho ngày lịch, ánh xạ sang `LocalDate`.
- Dùng DateTime cho thời điểm có offset, ánh xạ sang `OffsetDateTime` nếu scalar hỗ trợ.
- Dùng `Instant` cho thời điểm tuyệt đối trong domain hoặc persistence và chuyển đổi rõ ràng ở ranh giới API.
- Lưu Zone ID riêng nếu nghiệp vụ phụ thuộc vào timezone có tên.
- Không dùng `java.util.Date` hoặc `LocalDateTime` như thể chúng tự mang timezone.
- Quy định định dạng, độ chính xác phần giây và chính sách chuẩn hóa output.
- Từ chối dữ liệu không hợp lệ thay vì tự sửa hoặc đoán timezone.
- Kiểm thử cả biến JSON, literal GraphQL và response serialization.

## Kết luận

Date và DateTime là custom scalar cần thiết khi GraphQL API làm việc với ngày lịch và thời điểm. Date phù hợp với `LocalDate`; DateTime có offset phù hợp với `OffsetDateTime`. Nếu hệ thống lưu thời điểm UTC, có thể dùng `Instant` trong domain và chuyển đổi rõ ràng ở lớp API.

Spring for GraphQL cho phép đăng ký scalar qua `RuntimeWiringConfigurer`. Thư viện GraphQL Java Extended Scalars cung cấp sẵn Date và DateTime cho nhiều trường hợp phổ biến. Khi quy định rõ định dạng, offset, timezone, nullability và kiểm thử coercion, API sẽ tránh được lỗi lệch ngày hoặc diễn giải sai thời điểm.

## Tài liệu tham khảo

- [Spring for GraphQL — Schema and Runtime Wiring](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java Extended Scalars](https://github.com/graphql-java/graphql-java-extended-scalars)
- [Java Date and Time API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html)
- [GraphQL Specification — Scalars](https://spec.graphql.org/October2021/#sec-Scalars)

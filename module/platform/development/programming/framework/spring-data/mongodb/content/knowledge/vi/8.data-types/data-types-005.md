# Instant, LocalDateTime, Date và quy ước UTC

> **Chương:** Kiểu dữ liệu  
> **Module:** `SPRING_DATA_MONGODB`

Thời gian là một nguồn lỗi khó phát hiện trong hệ thống dữ liệu: một sự kiện xảy ra lúc **09:00 tại Việt Nam** thực chất là **02:00 UTC**, trong khi một cuộc hẹn “09:00 ngày mai tại địa phương” có thể phải được hiểu theo múi giờ của người đặt hẹn. Nếu bỏ qua sự khác biệt này, ứng dụng có thể lưu, sắp xếp hoặc tổng hợp dữ liệu sai mà vẫn không phát sinh exception.

Trong Spring Data MongoDB, ba kiểu Java thường gặp là `java.time.Instant`, `java.time.LocalDateTime` và `java.util.Date`. Chúng không mang cùng ý nghĩa dù cuối cùng có thể được chuyển thành **BSON Date** trong MongoDB. Bài học xây dựng quy ước UTC rõ ràng để làm việc qua `MongoTemplate` hoặc repository, đồng thời chuẩn bị nền tảng cho truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng của module `SPRING_DATA_MONGODB`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **thời điểm tuyệt đối**, **giờ địa phương** và **múi giờ/offset**, giải thích cách BSON Date lưu thời gian.
2. Chọn đúng giữa `Instant`, `LocalDateTime` và `Date` trong model Java và API.
3. Chuyển thời gian địa phương sang `Instant` bằng `ZoneId` tường minh; tránh phụ thuộc `ZoneId.systemDefault()`.
4. Thiết kế document, truy vấn theo khoảng ngày địa phương và aggregation với quy ước UTC nhất quán.
5. Xử lý độ chính xác mili giây, daylight saving time (DST), dữ liệu lịch sử và lỗi chuyển đổi trong Spring Data MongoDB.

## 2. Ba khái niệm cần tách bạch

| Khái niệm | Ví dụ | Thông tin mang theo | Câu hỏi trả lời |
| --- | --- | --- | --- |
| **Thời điểm tuyệt đối** (*instant*) | `2026-11-20T02:00:00Z` | Một vị trí trên trục thời gian UTC | Sự kiện xảy ra **khi nào**? |
| **Thời gian trên đồng hồ địa phương** (*local date-time*) | `2026-11-20T09:00:00` | Ngày, giờ, phút, giây; **không** có múi giờ | Đồng hồ ở địa phương hiển thị **mấy giờ**? |
| **Múi giờ theo khu vực** | `Asia/Ho_Chi_Minh` | Tập quy tắc offset theo vùng và lịch sử | Diễn giải 09:00 ở **địa phương nào**? |
| **Độ lệch UTC** (*offset*) | `+07:00` | Chênh lệch với UTC tại một thời điểm | Giờ địa phương lệch UTC **bao nhiêu**? |

Một thời điểm có nhiều cách hiển thị, nhưng vẫn là **cùng một sự kiện**:

```text
2026-11-20 02:00:00 UTC
    = 2026-11-20 09:00:00 Asia/Ho_Chi_Minh (+07:00)
    = 2026-11-19 21:00:00 America/New_York (EST, -05:00)
```

Ngược lại, riêng chuỗi `2026-11-20 09:00:00` chưa xác định một instant: 09:00 ở Hà Nội và 09:00 ở New York là hai thời điểm khác nhau.

**Quy ước cốt lõi:** thời điểm phát sinh sự kiện (tạo đơn, nhận thanh toán, ghi log, gửi thông báo) nên được lưu và trao đổi như **instant**, còn múi giờ được dùng để **diễn giải giờ địa phương khi nhập liệu, hiển thị hoặc báo cáo theo lịch**.

## 3. BSON Date của MongoDB thực sự chứa gì?

MongoDB có kiểu BSON **Date**: một số nguyên **64 bit có dấu** biểu diễn **số mili giây từ Unix epoch** (`1970-01-01T00:00:00Z`). Giá trị âm biểu diễn thời điểm trước epoch. BSON Date không lưu tên múi giờ, offset, định dạng hiển thị hoặc đơn vị nanosecond.

Ví dụ trong `mongosh`:

```javascript
use shop

const moment = ISODate("2026-11-20T02:00:00.000Z");
moment.toISOString(); // "2026-11-20T02:00:00.000Z"
moment.getTime();      // mili giây kể từ Unix epoch

db.events.insertOne({
  name: "ORDER_PAID",
  occurredAt: moment
})

db.events.findOne({ name: "ORDER_PAID" })
```

`ISODate(...)` là cách biểu diễn/khởi tạo ngày trong `mongosh`; dữ liệu được lưu là **BSON Date**, không phải chuỗi literal `"ISODate(...)"`. Trong MongoDB Extended JSON, cùng ý nghĩa có thể xuất hiện như:

```json
{
  "occurredAt": {
    "$date": "2026-11-20T02:00:00Z"
  }
}
```

Đây là **Extended JSON** chứa kiểu Date; trường `occurredAt` không phải một object nghiệp vụ có field `$date`. Nếu lưu `"2026-11-20T02:00:00Z"` trực tiếp dưới dạng string, đó là **BSON String**, có ngữ nghĩa truy vấn và index khác.

### 3.1. UTC là cách xác định thời điểm, không phải múi giờ người dùng

Một BSON Date có cùng số mili giây dù được đọc ở server Việt Nam, Mỹ hay châu Âu. Công cụ hiển thị có thể format nó theo múi giờ khác nhau. Vì vậy không thể kết luận document bị “lưu sai 7 tiếng” chỉ vì `mongosh` cho thấy `02:00Z` còn giao diện hiển thị `09:00`.

Nếu người dùng chọn 09:00 ngày 20/11/2026 tại Việt Nam, giá trị chuẩn lưu vào MongoDB sẽ là:

```javascript
ISODate("2026-11-20T02:00:00.000Z")
```

**Sai lầm cần tránh:** thêm bảy giờ vào dữ liệu khi ghi và tiếp tục thêm bảy giờ khi đọc. Việc chuyển đổi phải có quy ước cố định ở **ranh giới** nhận/hiển thị dữ liệu.

### 3.2. Mili giây và độ chính xác bị mất

`Instant` có thể biểu diễn tới độ phân giải nanosecond, nhưng BSON Date chỉ lưu **mili giây**. Ví dụ:

```java
Instant precise = Instant.parse("2026-11-20T02:00:00.123456789Z");
Date legacy = Date.from(precise);

System.out.println(legacy.toInstant());
// 2026-11-20T02:00:00.123Z
```

Sáu chữ số nanosecond phía sau phần mili giây đã mất khi chuyển sang `Date`. Khi viết `Instant` vào BSON Date, cũng phải dự kiến độ chính xác chỉ còn mili giây; không nên yêu cầu so sánh round-trip với nanosecond ban đầu.

**Lưu ý phân biệt:** BSON `Timestamp` là kiểu khác dùng trong một số cơ chế nội bộ/replication của MongoDB; không dùng thay BSON Date để lưu thời điểm nghiệp vụ thông thường.

## 4. So sánh Instant, LocalDateTime và Date trong Java

| Kiểu | Có xác định instant không? | Có chứa múi giờ không? | Biến đổi được không? | Cách dùng gợi ý |
| --- | --- | --- | --- | --- |
| `Instant` | **Có** | Không mang tên vùng; được định vị trên trục UTC | Không (immutable) | `createdAt`, `updatedAt`, `paidAt`, `expiresAt` |
| `LocalDateTime` | **Không** | **Không** | Không (immutable) | Lịch địa phương như “09:00 thứ Hai”, trước khi xác định `ZoneId` |
| `java.util.Date` | **Có** (giữ epoch milliseconds) | Không lưu múi giờ | **Có** (mutable) | Tích hợp thư viện cũ/DTO legacy, cần chuyển sang `Instant` ở ranh giới |

Trong Java:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Date;

Instant instant = Instant.parse("2026-11-20T02:00:00Z");
LocalDateTime local = LocalDateTime.of(2026, 11, 20, 9, 0);
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

Instant fromLocal = local.atZone(vietnam).toInstant();
Date legacyDate = Date.from(instant);
Instant fromLegacy = legacyDate.toInstant();
ZonedDateTime display = instant.atZone(vietnam);

System.out.println(fromLocal.equals(instant)); // true
System.out.println(fromLegacy.equals(instant)); // true
System.out.println(display); // 2026-11-20T09:00+07:00[Asia/Ho_Chi_Minh]
```

### 4.1. Instant: lựa chọn mặc định cho thời điểm sự kiện

`Instant` mô tả **lúc nào**, không mô tả **ở đâu**. Nó thích hợp cho timestamp máy tạo: nhận yêu cầu, xác thực, tạo bản ghi, thanh toán, timeout, TTL và lịch sử audit. Khi so sánh hai instant, không cần tính lại múi giờ.

Tạo thời điểm hiện tại có thể dùng:

```java
Instant now = Instant.now();
```

Trong logic cần test lặp lại ổn định, nên inject `Clock` thay vì gọi `Instant.now()` trực tiếp ở khắp nơi.

### 4.2. LocalDateTime: giá trị lịch địa phương chưa đủ thông tin

`LocalDateTime.of(2026, 11, 20, 9, 0)` chỉ nói **09:00 ngày 20/11**, không có `+07:00` hoặc `Asia/Ho_Chi_Minh`. Không thể chuyển nó thành instant chính xác khi chưa biết **zone/offset**.

`LocalDateTime` phù hợp khi nghiệp vụ phải lưu **giờ trên đồng hồ**: lịch làm việc cửa hàng, thời gian mở quầy, hoặc lịch hẹn mà khu vực được lưu riêng. Khi cần đặt một tác vụ xảy ra đúng một thời điểm, phải ghép với zone và xử lý các trường hợp DST.

### 4.3. java.util.Date: kiểu cũ nhưng vẫn biểu diễn instant

Mặc dù có chữ “Date”, `java.util.Date` biểu diễn số mili giây từ epoch, không phải một “ngày chỉ có năm-tháng-ngày”. Nó **không giữ timezone**.

```java
Date date = Date.from(Instant.parse("2026-11-20T02:00:00Z"));
Instant instant = date.toInstant();

// Bản sao tránh truyền ra một đối tượng mutable từ API legacy.
Date defensiveCopy = new Date(date.getTime());
```

`Date.toString()` dùng múi giờ mặc định của tiến trình để **hiển thị** nên có thể tạo cảm giác dữ liệu thay đổi. Dùng `Date.toInstant()`, `Date.getTime()` hoặc formatter có zone tường minh khi cần so sánh thời điểm.

Không nhầm `java.util.Date` với `java.sql.Date` (mang ý nghĩa ngày trong JDBC) hoặc `LocalDate` (ngày lịch không có giờ).

## 5. Chuyển đổi giữa giờ địa phương và UTC

### 5.1. Chuyển đúng với ZoneId

Người dùng nhập `2026-11-20 09:30` và chọn múi giờ `Asia/Ho_Chi_Minh`:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime requested =
    LocalDateTime.of(2026, 11, 20, 9, 30);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant scheduledAt = requested.atZone(zone).toInstant();

System.out.println(scheduledAt);
// 2026-11-20T02:30:00Z
```

Khi hiển thị ở địa phương:

```java
LocalDateTime localAgain =
    LocalDateTime.ofInstant(scheduledAt, zone);

System.out.println(localAgain);
// 2026-11-20T09:30
```

Để biểu diễn một **thời điểm**, lưu `scheduledAt` vào BSON Date. Nếu nghiệp vụ cần giữ nguyên khu vực đặt lịch hoặc tái dựng quy tắc lịch địa phương khi múi giờ thay đổi, lưu thêm `zoneId` như một field riêng.

### 5.2. Vì sao không được gán UTC một cách tùy tiện?

```java
LocalDateTime local = LocalDateTime.of(2026, 11, 20, 9, 30);

// SAI về ngữ nghĩa nếu 09:30 là giờ Việt Nam.
Instant wrong = local.toInstant(java.time.ZoneOffset.UTC);
// 2026-11-20T09:30:00Z (lệch +7 giờ so với thời điểm dự kiến)

// ĐÚNG: biết giờ này thuộc Asia/Ho_Chi_Minh.
Instant correct = local
    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .toInstant();
// 2026-11-20T02:30:00Z
```

`ZoneOffset.UTC` chỉ đúng khi **giờ ban đầu thực sự là giờ UTC**, không phải cách “ép mọi LocalDateTime thành UTC”.

### 5.3. Offset cố định khác với vùng thời gian

`ZoneOffset.of("+07:00")` là độ lệch cố định. `ZoneId.of("Asia/Ho_Chi_Minh")` là tên vùng có quy tắc theo lịch sử. Một số khu vực thay offset trong năm do DST; dùng một offset cố định không thể mô tả quy tắc đó cho mọi ngày.

Với dữ liệu chỉ cần mô tả một instant và offset tại thời điểm nhập, `OffsetDateTime` có thể phù hợp ở tầng API. Với lịch hẹn hoặc giờ địa phương dài hạn, lưu `ZoneId` giúp diễn giải theo quy tắc khu vực.

## 6. Daylight saving time: giờ không tồn tại hoặc lặp lại

Một số khu vực thay đổi offset theo mùa. Ví dụ tại `America/New_York`:

- Lúc chuyển sang giờ mùa hè, một khoảng giờ địa phương bị **bỏ qua** (*gap*).
- Lúc quay về giờ tiêu chuẩn, một khoảng giờ địa phương xảy ra **hai lần** (*overlap*).

Vì vậy cùng chuỗi `2026-11-01T01:30` ở New York có thể tương ứng **hai instant** khác nhau. Gọi `atZone(...)` mà không xác định chính sách có thể tự chọn một offset trong trường hợp overlap hoặc tự dịch giờ trong gap.

Nếu hệ thống đặt lịch yêu cầu xác định chính xác một instant, có thể từ chối thời gian không duy nhất:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public static Instant resolveUnambiguous(
        LocalDateTime localTime, ZoneId zone) {
    List<ZoneOffset> validOffsets =
        zone.getRules().getValidOffsets(localTime);

    if (validOffsets.size() != 1) {
        throw new IllegalArgumentException(
            "Thời gian địa phương không tồn tại hoặc bị lặp: "
                + localTime + " tại " + zone);
    }

    return localTime.toInstant(validOffsets.get(0));
}
```

Đặt hàm này trong một class utility/service Java; đây là phương thức đầy đủ về logic. Nếu nghiệp vụ cho phép chọn một trong hai lần `01:30`, giao diện phải cho người dùng chọn offset hoặc cung cấp quy tắc rõ ràng rồi lưu instant đã giải quyết.

**Lưu ý:** Việt Nam hiện không dùng DST, nhưng dữ liệu đa quốc gia, múi giờ lịch sử và lịch hẹn tương lai vẫn cần xử lý theo `ZoneId` thích hợp.

## 7. Ánh xạ kiểu thời gian bằng Spring Data MongoDB

Với một ứng dụng quản lý đơn hàng, ta chọn:

- `createdAt`: thời điểm tạo đơn, dùng `Instant`.
- `paidAt`: thời điểm thanh toán, dùng `Instant` hoặc `null` khi chưa thanh toán.
- `importedLegacyAt`: trường tương thích hệ thống cũ dùng `Date`.
- `displayZoneId`: múi giờ dùng để hiển thị hoặc giải thích dữ liệu lịch địa phương.

File `OrderTimeline.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Date;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "order_timelines")
public record OrderTimeline(
    @Id String id,
    String orderId,
    @Field("created_at") Instant createdAt,
    @Field("paid_at") Instant paidAt,
    @Field("imported_legacy_at") Date importedLegacyAt,
    String displayZoneId
) {}
```

Trong cấu hình mapping thông thường, `Instant` và `Date` được chuyển sang BSON Date; `displayZoneId` là chuỗi tên vùng như `Asia/Ho_Chi_Minh`. Để giữ immutable toàn bộ domain model, có thể chuyển `importedLegacyAt` thành `Instant` ngay ở ranh giới import và bỏ `Date` khỏi entity.

Document minh họa:

```javascript
{
  _id: ObjectId("66a000000000000000000021"),
  orderId: "ORD-100",
  created_at: ISODate("2026-11-20T01:45:00.000Z"),
  paid_at: ISODate("2026-11-20T02:00:00.000Z"),
  imported_legacy_at: ISODate("2026-11-20T00:00:00.000Z"),
  displayZoneId: "Asia/Ho_Chi_Minh",
  _class: "com.example.shop.orders.OrderTimeline"
}
```

Field `_class` được minh họa vì mapping mặc định có thể ghi metadata kiểu Java; nó **không** làm thay đổi cách BSON Date lưu timestamp.

### 7.1. Lưu thời gian bằng Clock được inject

File `OrderTimelineService.java`:

```java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderTimelineService {
    private final MongoTemplate mongoTemplate;
    private final Clock clock;

    public OrderTimelineService(
            MongoTemplate mongoTemplate, Clock clock) {
        this.mongoTemplate = mongoTemplate;
        this.clock = clock;
    }

    public OrderTimeline create(String orderId) {
        OrderTimeline timeline = new OrderTimeline(
            null,
            orderId,
            Instant.now(clock),
            null,
            null,
            "Asia/Ho_Chi_Minh"
        );
        return mongoTemplate.insert(timeline);
    }
}
```

Đăng ký `Clock` như một Spring bean:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

`Clock.systemUTC()` làm rõ quy ước và cho phép thay bằng `Clock.fixed(...)` trong test. Lưu ý: đồng hồ hệ thống của nhiều máy vẫn có thể lệch nhau; nếu cần timestamp do database tự đặt trong thao tác update, xem xét operator `$currentDate` và quy ước đồng bộ thời gian hạ tầng.

### 7.2. Repository truy vấn theo Instant

File `OrderTimelineRepository.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderTimelineRepository
        extends MongoRepository<OrderTimeline, String> {

    List<OrderTimeline>
    findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        Instant fromInclusive, Instant toExclusive);
}
```

Derived query dựa trên **tên thuộc tính Java** `createdAt`; Spring Data mapping chuyển nó sang field BSON `created_at` nhờ `@Field`. Repository không tự biết “ngày theo Việt Nam” là khoảng UTC nào; caller phải cung cấp hai mốc thời gian đã được chuyển đổi.

### 7.3. LocalDateTime có thể mapping ra BSON Date, nhưng cần cẩn trọng

Spring Data MongoDB hỗ trợ các converter Java Time; **LocalDateTime không có timezone** nhưng một BSON Date bắt buộc đại diện một instant. Converter phải **lựa chọn một zone** để gán ý nghĩa cho giờ địa phương đó.

Theo tài liệu Spring Data, converter kiểu thời gian địa phương mặc định của Spring Data (`LocalDateTime` → `java.util.Date`) sử dụng **`ZoneId.systemDefault()`**. Một số cấu hình sử dụng codec Java Time của MongoDB Java Driver với **UTC**. Vì vậy cùng `LocalDateTime.of(2026, 11, 20, 9, 0)` có thể được lưu thành **instant khác nhau** nếu cấu hình conversion hoặc múi giờ tiến trình khác nhau.

| Nguồn chuyển đổi `LocalDateTime 09:00` | Zone dùng để hiểu 09:00 | BSON Date tương ứng |
| --- | --- | --- |
| Spring Data local-time converter, máy chạy theo Việt Nam | `Asia/Ho_Chi_Minh` | `2026-11-20T02:00:00Z` |
| Converter/codec dùng UTC | `UTC` | `2026-11-20T09:00:00Z` |
| Máy có default zone khác | Zone của máy đó | Có thể ra một instant khác |

Do đó **không nên dựa vào múi giờ của máy chạy** để xác định một thời điểm nghiệp vụ quan trọng. Cách an toàn là nhận `LocalDateTime + ZoneId`, giải quyết thành `Instant` ở tầng service, rồi lưu `Instant` trong entity.

Nếu nghiệp vụ thực sự cần lưu **giờ địa phương thuần túy** như “mỗi thứ Hai lúc 09:00”, hãy cân nhắc mô hình riêng gồm local date/time và `zoneId`, với biểu diễn lưu trữ đã quy định rõ (chẳng hạn chuỗi ISO-local-date-time hoặc các field số). Không mặc định rằng BSON Date lưu được ý nghĩa “09:00 ở mọi múi giờ”.

## 8. Quy ước API: nhập liệu, lưu trữ, hiển thị

### 8.1. API truyền thời điểm tuyệt đối

Ví dụ request/response sử dụng ISO 8601 với offset tường minh:

```json
{
  "orderId": "ORD-100",
  "paidAt": "2026-11-20T02:00:00Z"
}
```

Hoặc một giá trị có offset `+07:00`:

```json
{
  "orderId": "ORD-100",
  "paidAt": "2026-11-20T09:00:00+07:00"
}
```

Hai chuỗi mô tả cùng một instant. Với Jackson được cấu hình cho Java Time, có thể bind vào `OffsetDateTime` hoặc một kiểu thích hợp rồi chuyển về `Instant`. Tránh nhận một chuỗi thiếu zone như `"2026-11-20T09:00:00"` và tự suy đoán múi giờ máy chủ.

### 8.2. API truyền lịch hẹn địa phương

Nếu người dùng đặt lịch theo địa phương, API có thể nhận:

```json
{
  "appointmentLocal": "2026-11-20T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

Service kiểm tra `zoneId` và tính ra `scheduledAt: Instant`. Với DST gap/overlap, cần chính sách rõ ràng: yêu cầu nhập lại hoặc chọn offset hợp lệ. Nếu lịch là quy tắc lặp hằng tuần, không thể chỉ giữ một instant; phải lưu cả quy tắc lịch và vùng thời gian để tính từng lần thực thi.

### 8.3. Format để hiển thị

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

Instant paidAt = Instant.parse("2026-11-20T02:00:00Z");

String shown = DateTimeFormatter
    .ofPattern("dd/MM/yyyy HH:mm z")
    .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .format(paidAt);

System.out.println(shown);
// Ví dụ: 20/11/2026 09:00 ICT
```

Hiển thị theo locale/zone của người dùng, nhưng giữ `Instant` làm dữ liệu nguồn. **Định dạng chuỗi là chuyện trình bày**; không lưu thời điểm chỉ dưới dạng `dd/MM/yyyy HH:mm` nếu còn cần lọc, sắp xếp, tính hiệu thời gian và index kiểu ngày.

## 9. Truy vấn theo khoảng ngày địa phương đúng cách

Giả sử người dùng hỏi: “Tất cả đơn được tạo trong **ngày 20/11/2026 theo giờ Việt Nam**”. Ngày địa phương này bắt đầu và kết thúc ở UTC như sau:

```text
Ngày địa phương: 2026-11-20, Asia/Ho_Chi_Minh

start = 2026-11-20 00:00:00 +07:00
      = 2026-11-19T17:00:00Z

end   = 2026-11-21 00:00:00 +07:00
      = 2026-11-20T17:00:00Z

Khoảng truy vấn: [start, end)
```

Dùng **khoảng nửa mở** `[start, end)` giúp tránh rủi ro làm tròn ở `23:59:59.999` và tránh đếm trùng dữ liệu giữa hai ngày liên tiếp.

### 9.1. Tạo ranh giới bằng Java

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate day = LocalDate.of(2026, 11, 20);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

System.out.println(start); // 2026-11-19T17:00:00Z
System.out.println(end);   // 2026-11-20T17:00:00Z
```

**Không dùng** `start.plus(24, ChronoUnit.HOURS)` làm ranh giới của mọi ngày địa phương: ngày ở vùng có DST có thể dài 23 hoặc 25 giờ. Cần lấy **đầu ngày kế tiếp trong chính ZoneId**, rồi mới chuyển sang instant.

### 9.2. MongoTemplate

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<OrderTimeline> findByLocalDay(
        MongoTemplate mongoTemplate,
        LocalDate day,
        ZoneId zone) {

    Instant start = day.atStartOfDay(zone).toInstant();
    Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

    Query query = Query.query(
            Criteria.where("createdAt").gte(start).lt(end))
        .with(Sort.by(Sort.Direction.ASC, "createdAt"));

    return mongoTemplate.find(query, OrderTimeline.class);
}
```

Đặt phương thức này vào một service/class Java và inject `MongoTemplate` thực tế. Tiêu chí `createdAt` là **thuộc tính Java**; `MongoTemplate` dùng metadata `@Field("created_at")` để truy vấn field MongoDB phù hợp.

### 9.3. mongosh

```javascript
db.order_timelines
  .find({
    created_at: {
      $gte: ISODate("2026-11-19T17:00:00Z"),
      $lt: ISODate("2026-11-20T17:00:00Z")
    }
  })
  .sort({ created_at: 1 })
```

Tạo index cho truy vấn thời gian thường xuyên:

```javascript
db.order_timelines.createIndex({ created_at: 1 })
```

Nếu câu truy vấn thường lọc thêm `orderId` hoặc `storeId`, cân nhắc index ghép theo mẫu truy vấn, thay vì tạo index đơn lẻ cho mọi field. BSON Date giúp MongoDB lọc/sắp xếp theo thời điểm được lưu; MongoDB không cần biết vùng thời gian của người dùng khi đã có ranh giới UTC.

## 10. Aggregation theo ngày địa phương

Khi làm dashboard, “ngày” thường theo múi giờ kinh doanh, **không phải ngày UTC**. MongoDB aggregation có toán tử xử lý timezone, ví dụ `$dateTrunc` và `$dateToString`.

Giả sử collection `order_timelines` có `paid_at` là BSON Date, ta muốn đếm đơn theo ngày Việt Nam:

```javascript
db.order_timelines.aggregate([
  { $match: { paid_at: { $type: "date" } } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$paid_at",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      localDay: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$_id",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: 1
    }
  }
])
```

`$dateTrunc` theo `unit: "day"` với zone khu vực tạo các mốc đầu ngày theo quy tắc vùng đó; `$dateToString` định dạng nhãn ngày cho báo cáo. Ví dụ sử dụng `$dateTrunc` cần phiên bản MongoDB hỗ trợ toán tử (MongoDB 5.0 trở lên).

**Hai lỗi dễ mắc:**

1. Nhóm theo `$dateToString` không khai báo `timezone` rồi hiển thị nhãn tại Việt Nam: đơn gần nửa đêm địa phương có thể bị tính sang ngày khác.
2. Truy vấn theo ngày địa phương bằng ngày UTC `00:00Z`: sẽ thiếu đơn đầu ngày ở địa phương và lấy nhầm đơn của ngày kế tiếp.

Nếu cần thống kê theo tuần/tháng, cần thống nhất cách đánh số tuần, ngày bắt đầu tuần và timezone kinh doanh. Kết quả tính sẵn theo ngày cũng phải lưu rõ “ngày theo zone nào”.

## 11. Cấu hình chuyển đổi thời gian trong Spring Data

Thực tế có hai lớp chuyển đổi:

1. **Java domain → Spring Data mapping**: áp dụng metadata từ `@Document`, `@Field` và `MongoCustomConversions`.
2. **Giá trị tương ứng → BSON qua MongoDB driver**: lưu BSON Date, String, Number và các kiểu khác.

Với `Instant` và `Date` biểu diễn một thời điểm, đường ánh xạ sang BSON Date tương đối trực tiếp. Với `LocalDateTime`, quyết định về zone có thể khác nhau tùy converter/codec được chọn.

Theo API của Spring Data MongoDB, `MongoCustomConversions.MongoConverterConfigurationAdapter` có các lựa chọn dành cho Java Time:

- `useSpringDataJavaTimeCodecs()`: dùng converter Spring Data với `ZoneId.systemDefault()` cho kiểu local temporal.
- `useNativeDriverJavaTimeCodecs()`: dùng codec Java Time của driver với `ZoneOffset.UTC` cho kiểu local temporal.

Tên API và cấu hình khởi tạo `MongoCustomConversions` cần được kiểm tra theo phiên bản framework cụ thể của dự án; thay đổi lựa chọn này trên một database đã có dữ liệu `LocalDateTime` có thể khiến **cùng một BSON Date được diễn giải khác trước**.

**Quy ước nên chọn cho timestamp nghiệp vụ:** lưu `Instant`, chuyển đầu vào địa phương bằng `ZoneId` tường minh ở tầng service; xem `LocalDateTime` là một **giá trị lịch địa phương** chứ không tự động là timestamp. Quy ước này làm logic độc lập với timezone hệ điều hành.

Nếu dự án cần converter riêng, hãy đăng ký qua `MongoCustomConversions` với `@WritingConverter`/`@ReadingConverter` phù hợp, xác định rõ kiểu BSON đích và kiểm thử sau khi thay cấu hình. Chuyển đổi sai ở phạm vi toàn ứng dụng có thể làm thay đổi các field không liên quan.

## 12. Migration khi dữ liệu cũ lưu sai kiểu

Các hệ thống lâu năm thường có hỗn hợp:

```javascript
// A: đúng loại BSON Date
{ _id: "A", occurredAt: ISODate("2026-11-20T02:00:00Z") }

// B: string có offset tường minh
{ _id: "B", occurredAt: "2026-11-20T09:00:00+07:00" }

// C: string giờ địa phương, chưa có thông tin zone
{ _id: "C", occurredAt: "2026-11-20 09:00:00" }
```

Không thể sửa tất cả bằng một lệnh chuyển string sang Date mà bỏ qua ngữ nghĩa:

- **A** đã là BSON Date; không cần chuyển.
- **B** có offset; có thể parse ra cùng instant nếu định dạng hợp lệ.
- **C** thiếu zone; phải biết nguồn sinh dữ liệu dùng múi giờ nào, hoặc thừa nhận không thể khôi phục instant chính xác nếu thiếu ngữ cảnh.

### 12.1. Thống kê kiểu hiện có

```javascript
db.events.aggregate([
  {
    $group: {
      _id: { $type: "$occurredAt" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

Phép kiểm tra này giúp phát hiện những field là `date`, `string`, `null` hoặc bị thiếu; cần phân tích thêm định dạng và nguồn dữ liệu đối với các chuỗi.

### 12.2. Xem trước cách diễn giải giờ local

Giả sử **đã xác minh** rằng field `legacyLocalTime` của một tập dữ liệu cũ đều được nhập theo giờ Việt Nam ở định dạng `YYYY-MM-DD HH:mm:ss`. Có thể kiểm tra phép parse bằng một pipeline **chỉ đọc**:

```javascript
db.legacyEvents.aggregate([
  { $match: { legacyLocalTime: { $type: "string" } } },
  {
    $project: {
      legacyLocalTime: 1,
      convertedAt: {
        $dateFromString: {
          dateString: "$legacyLocalTime",
          format: "%Y-%m-%d %H:%M:%S",
          timezone: "Asia/Ho_Chi_Minh",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $limit: 20 }
])
```

Chỉ sau khi xác minh mẫu dữ liệu, timezone, cách xử lý lỗi và khả năng phục hồi mới nên lập lệnh ghi migration. Tránh chuyển một chuỗi đã có offset rồi tiếp tục áp timezone khác. Dữ liệu local rơi vào DST gap/overlap có thể cần quyết định thủ công hoặc dữ liệu bổ sung.

Với hệ thống đang chạy, nên cân nhắc giai đoạn reader hỗ trợ cả dữ liệu cũ và mới; ghi chuyển đổi theo lô có đối soát số lượng, thời điểm và số lỗi parse; có kế hoạch rollback. Chuyển BSON String thành BSON Date sẽ thay đổi cách sort, so sánh, index và aggregation hoạt động.

## 13. Kiểm thử đúng thời gian và kiểm tra hiệu năng

### 13.1. Kiểm thử Java không cần database

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class TimeRulesTest {
    @Test
    void vietnamLocalTimeMapsToExpectedInstant() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant instant = LocalDateTime.of(2026, 11, 20, 9, 0)
            .atZone(zone)
            .toInstant();

        assertEquals(
            Instant.parse("2026-11-20T02:00:00Z"),
            instant
        );
    }

    @Test
    void localDayProducesHalfOpenUtcBounds() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate date = LocalDate.of(2026, 11, 20);

        assertEquals(
            Instant.parse("2026-11-19T17:00:00Z"),
            date.atStartOfDay(zone).toInstant()
        );
        assertEquals(
            Instant.parse("2026-11-20T17:00:00Z"),
            date.plusDays(1).atStartOfDay(zone).toInstant()
        );
    }
}
```

### 13.2. Kiểm thử round-trip qua MongoDB

Với `MongoTemplate` hoặc repository, tạo entity có `Instant` chứa phần mili giây, lưu và đọc lại, rồi so sánh instant đã chuẩn hóa về mili giây:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant input = Instant.parse("2026-11-20T02:00:00.123456Z");
Instant expected = input.truncatedTo(ChronoUnit.MILLIS);

// Lưu input trong entity qua repository/MongoTemplate, rồi đọc lại.
// assertEquals(expected, reloaded.getCreatedAt());
```

Đây là đoạn minh họa **kỳ vọng kiểm thử**; thay `reloaded.getCreatedAt()` bằng accessor thực tế của entity. Nếu dùng `OrderTimeline` record ở trên, accessor là `reloaded.createdAt()`. Khi test mapping, cần kiểm tra BSON thực sự mang kiểu `date`, không phải string.

Các trường hợp tích hợp nên có:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Lưu và đọc `Instant` | Trả về cùng thời điểm ở độ phân giải mili giây |
| Lưu và đọc `java.util.Date` | Mili giây không đổi, không phụ thuộc timezone hiển thị |
| Dùng converter `LocalDateTime` ở các JVM timezone khác nhau | Phát hiện sai khác và khóa quy ước chuyển đổi |
| Truy vấn ngày Việt Nam | Dữ liệu đúng trong `[17:00Z hôm trước, 17:00Z hôm nay)` |
| Ngày qua DST ở New York | Hai ranh giới theo ngày địa phương đúng, có thể chênh 23/25 giờ |
| Timestamp có nanosecond | Không kỳ vọng phần nhỏ hơn mili giây sống sót qua BSON Date |
| Field bị thiếu/null hoặc string cũ | Xử lý theo chiến lược mapping/migration đã định |
| Dữ liệu tạo từ nhiều service | So sánh timestamp theo cùng hợp đồng UTC, kiểm tra lệch đồng hồ |

### 13.3. Chẩn đoán hiệu năng

Kiểm tra index và kế hoạch thực thi bằng `explain("executionStats")`:

```javascript
db.order_timelines
  .find({
    created_at: {
      $gte: ISODate("2026-11-19T17:00:00Z"),
      $lt: ISODate("2026-11-20T17:00:00Z")
    }
  })
  .sort({ created_at: 1 })
  .explain("executionStats")
```

Đo `totalDocsExamined`, `totalKeysExamined`, độ trễ và số document được trả về trên dữ liệu đại diện. Index BSON Date có thể phục vụ truy vấn range và sort theo thời gian; lưu thời điểm dưới dạng chuỗi hỗn hợp định dạng/offset khiến truy vấn khó đúng và khó tối ưu hơn.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Lưu `LocalDateTime` thành BSON Date mà không quyết định timezone | Giờ lưu khác nhau giữa máy/container | Chuyển `LocalDateTime + ZoneId` sang `Instant` trong service |
| Nghĩ `java.util.Date` giữ timezone | Log/hiển thị gây hiểu nhầm, dữ liệu bị cộng offset lần nữa | Xem `Date` như epoch milliseconds; định dạng bằng zone rõ ràng |
| Dùng `LocalDateTime.now()` làm timestamp hệ thống | Kết quả phụ thuộc timezone mặc định | Dùng `Instant.now(clock)` |
| Dùng `23:59:59.999` làm cuối ngày | Dễ sai khi độ phân giải thay đổi; biên không nhất quán | Dùng khoảng `[start, nextStart)` |
| Giả sử ngày nào cũng dài đúng 24 giờ | Sai ở vùng có DST | Tính đầu ngày kế tiếp từ `LocalDate.plusDays(1).atStartOfDay(zone)` |
| Dùng `ZoneOffset.UTC` để chuyển 09:00 ở Việt Nam | Lệch bảy giờ | Chọn đúng `ZoneId` của nguồn dữ liệu |
| So sánh instant nanosecond sau BSON Date round-trip | Kiểm thử thất bại do mất độ chính xác | Chuẩn hóa về mili giây khi cần |
| Lưu ngày dưới dạng chuỗi `dd/MM/yyyy HH:mm` | Khó lọc, sort và index đúng theo thời gian | Dùng BSON Date cho instant, format khi hiển thị |
| Tự parse string cũ thiếu zone theo timezone máy chạy | Dữ liệu bị diễn giải sai không thể phát hiện | Thống kê nguồn, xác minh zone và migration có đối soát |
| Nhóm báo cáo theo ngày UTC thay vì zone nghiệp vụ | Đơn gần nửa đêm bị tính sai ngày | Dùng timezone tường minh trong boundary hoặc aggregation |

## 15. Bài tập tình huống

Một cửa hàng tại TP. Hồ Chí Minh lưu `paidAt` cho đơn hàng. Khách đặt đơn lúc **23:50 ngày 20/11/2026 giờ Việt Nam**, nhưng dashboard được chạy từ server đặt tại UTC. Người quản lý muốn thống kê **doanh thu ngày 20/11 theo giờ Việt Nam**.

Hãy trả lời:

1. `paidAt` nên là `Instant`, `LocalDateTime` hay `Date` trong domain model mới? Vì sao?
2. Thời điểm `23:50` tại Việt Nam tương ứng với UTC nào?
3. Dashboard cần truy vấn `paidAt` trong khoảng UTC nào?
4. Nếu server chuyển từ UTC sang múi giờ khác, kết quả thống kê có được phép thay đổi không?
5. Nếu dùng MongoDB aggregation, cần khai báo timezone ở toán tử nào?

**Định hướng giải:**

- Chọn `Instant` vì thanh toán là sự kiện đã xảy ra tại một thời điểm xác định.
- `2026-11-20T23:50:00+07:00` tương ứng `2026-11-20T16:50:00Z`.
- Khoảng ngày Việt Nam là `[2026-11-19T17:00:00Z, 2026-11-20T17:00:00Z)`.
- Kết quả không được phụ thuộc timezone mặc định của server: chỉ vùng nghiệp vụ `Asia/Ho_Chi_Minh` mới quyết định ranh giới ngày.
- Với aggregation theo ngày, sử dụng `$dateTrunc`/`$dateToString` cùng tham số `timezone` phù hợp.

## 16. Tài liệu tham khảo

- MongoDB — [BSON Types: Date](https://www.mongodb.com/docs/manual/reference/bson-types/): định nghĩa Date, độ phân giải mili giây và epoch.
- MongoDB — [Date() and Datetime in mongosh](https://www.mongodb.com/docs/manual/reference/method/date/): `Date`, `new Date`, `ISODate` và cách hiển thị UTC.
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): ánh xạ `Instant` và các kiểu Java Time.
- Spring Data MongoDB — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): converter `LocalDateTime` và phụ thuộc timezone hệ thống.

## Ghi nhớ

**BSON Date** lưu mili giây của một thời điểm trên trục UTC và không mang thông tin múi giờ. **`Instant`** là lựa chọn mặc định cho timestamp nghiệp vụ; **`java.util.Date`** biểu diễn cùng ý nghĩa nhưng là API cũ, mutable và chỉ chính xác tới mili giây; **`LocalDateTime`** chỉ là giờ đồng hồ địa phương nên phải đi cùng `ZoneId` khi muốn xác định instant. Hãy chuyển đổi tại ranh giới API/service, lưu instant nhất quán, tính ranh giới báo cáo theo múi giờ nghiệp vụ và kiểm thử cả trường hợp thay timezone, DST và độ chính xác BSON.

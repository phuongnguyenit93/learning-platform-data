# Tránh gắn múi giờ mặc định ngầm vào dữ liệu trong Java

## 1. Vấn đề cốt lõi: một ngày giờ “trần” không xác định thời điểm tuyệt đối

Giả sử API nhận chuỗi `2024-05-01T09:00:00`. Nó có thể có nghĩa **09:00 tại Hà Nội**, **09:00 tại Paris**, **09:00 UTC**, hoặc chỉ là **giờ làm việc theo lịch** chưa gắn khu vực nào. Đây là bốn ý nghĩa khác nhau.

Nếu ứng dụng tự lấy `ZoneId.systemDefault()` để gắn vào chuỗi này, cùng một dữ liệu có thể trở thành **những `Instant` khác nhau** khi chạy trên máy phát triển, container production, máy chủ đặt ở quốc gia khác hoặc sau khi thay đổi cấu hình JVM.

Ví dụ với một giờ đồng hồ giống hệt nhau:

```text
LocalDateTime:       2024-05-01T09:00  (chưa có múi giờ)
Gắn Asia/Ho_Chi_Minh (+07:00) -> Instant: 2024-05-01T02:00:00Z
Gắn UTC (+00:00)              -> Instant: 2024-05-01T09:00:00Z

Hai kết quả cách nhau 7 giờ dù chuỗi đầu vào không đổi.
```

**Bài học:** Múi giờ/offset là thông tin **nghiệp vụ hoặc của giao thức**, không phải chi tiết nên tự suy từ môi trường chạy. Nếu đầu vào không có zone/offset, đừng giả vờ nó đã xác định duy nhất một thời điểm.

Chủ đề này thuộc `java.time` của Java 8 và vẫn còn nguyên giá trị trong các phiên bản Java hiện đại. Java hỗ trợ đầy đủ các kiểu dữ liệu cần thiết, nhưng chính ứng dụng phải quyết định cách biểu diễn và chuyển đổi.

### 1.1. Các lỗi sản xuất thường xuất hiện ra sao?

- Người dùng đặt hẹn `09:00`, ứng dụng chạy trên máy UTC, nên lịch được lưu lệch 7 giờ so với ý định tại Việt Nam.
- Một bản ghi chỉ có `2024-05-01T09:00` được parse thành `LocalDateTime`, sau đó tầng ORM/serialization hoặc đoạn code chuyển đổi tự lấy múi giờ hệ thống mà không ghi nhận giả định này.
- Một timestamp UTC được chuyển sang `LocalDateTime` rồi lưu mà **không giữ offset/zone**; khi đọc lại, ứng dụng tưởng giờ địa phương đó là UTC và thay đổi thời điểm.
- Một cuộc họp tại khu vực có chuyển giờ mùa hè được tạo đúng theo offset mùa đông hiện tại, nhưng cuộc họp tương lai xảy ra vào mùa hè: giờ trên đồng hồ bị lệch.
- Unit test chạy thành công trên laptop nhưng sai ở CI do `ZoneId.systemDefault()` khác.

Đây không phải lỗi của riêng `LocalDateTime`. Kiểu dữ liệu đó đúng cho “ngày và giờ nhìn trên đồng hồ”; lỗi nằm ở việc chuyển nó sang timeline **mà không có chính sách zone rõ ràng**.

## 2. Phân biệt chính xác các kiểu `java.time`

| Kiểu | Lưu cái gì? | Có xác định một `Instant` chưa? | Dùng khi nào? |
| --- | --- | --- | --- |
| `Instant` | Một điểm trên timeline UTC, tính theo epoch | **Có** | Audit timestamp, thời điểm phát sinh, thời điểm gửi lệnh |
| `LocalDateTime` | Năm–tháng–ngày–giờ, **không có** zone/offset | **Chưa** | Giờ hẹn theo lịch địa phương trước khi chọn khu vực |
| `OffsetDateTime` | Local date-time + `ZoneOffset`, ví dụ `+07:00` | **Có** | Payload có offset cụ thể, giao thức ISO offset |
| `ZonedDateTime` | Local date-time + `ZoneId` + offset đã được xác định | **Có** | Giờ địa phương gắn quy tắc khu vực |
| `ZoneOffset` | Độ lệch cố định so với UTC | Không phải ngày giờ | `Z`, `+07:00`, `-05:00` |
| `ZoneId` | Định danh múi giờ hoặc offset, ví dụ `Europe/Paris` | Không phải ngày giờ | Chọn quy tắc lịch sử và tương lai của một khu vực |
| `LocalDate` | Ngày trên lịch, không có giờ hoặc zone | **Chưa** | Ngày sinh, ngày nghỉ, ngày lập hóa đơn |
| `LocalTime` | Giờ–phút–giây, không có ngày/zone | **Chưa** | “Mở cửa lúc 09:00 hằng ngày” |
| `Clock` | Nguồn cung cấp thời gian kèm zone | Không phải sự kiện được lưu | Lấy “hiện tại” một cách kiểm soát được, đặc biệt trong test |

Các loại trên **không thể thay thế lẫn nhau** chỉ vì hiển thị gần giống. `LocalDateTime` thiếu offset nên không thể gọi `toInstant()` **không tham số**; để tạo `Instant`, phải có `ZoneOffset` hoặc `ZoneId` và quy tắc xử lý những thời điểm địa phương không rõ ràng.

### 2.1. `Instant` không “sống ở múi giờ UTC” theo nghĩa lịch hiển thị

`Instant` là thời điểm tuyệt đối trên timeline; định dạng `Z` thường được dùng để biểu diễn theo UTC. Một `Instant` có thể hiển thị tại nhiều khu vực:

```java
Instant event = Instant.parse("2024-05-01T02:00:00Z");
ZonedDateTime inVietnam =
    event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
// 2024-05-01T09:00+07:00[Asia/Ho_Chi_Minh]

ZonedDateTime inUtc = event.atZone(ZoneOffset.UTC);
// 2024-05-01T02:00Z
```

Hai biểu diễn có **cùng `toInstant()`**, dù giờ trên mặt đồng hồ khác nhau. `Instant` không tự ghi nhớ khu vực người dùng gốc: nếu ứng dụng cần hiển thị **chính theo múi giờ đã chọn lúc đặt hẹn**, phải lưu hoặc truy xuất `ZoneId` đó một cách có chủ đích.

### 2.2. `ZoneOffset` khác `ZoneId` của khu vực

`ZoneOffset.ofHours(7)` là một offset **cố định**: `+07:00`. `ZoneId.of("Asia/Ho_Chi_Minh")` là định danh **khu vực**, có bộ quy tắc múi giờ theo dữ liệu tzdb. Ở một thời điểm cụ thể, chúng có thể cùng offset `+07:00`, nhưng không phải vì thế chúng là cùng một khái niệm.

Đối với khu vực có daylight saving time (DST), `Europe/Paris` có thể dùng `+01:00` hoặc `+02:00` tùy ngày. Một offset `+01:00` được lưu ngày hôm nay không đủ để tính đúng cuộc họp `09:00 Paris` trong mọi ngày tương lai.

**Chọn `ZoneId`** cho quy tắc lịch địa phương dài hạn; chọn `ZoneOffset` nếu chính giao thức/nguồn dữ liệu chỉ xác định offset của một sự kiện cụ thể.

## 3. Các API vô tình lấy múi giờ mặc định

Những cách viết sau hợp lệ về mặt cú pháp nhưng có thể gây bất ngờ trong nghiệp vụ cần dữ liệu độc lập với môi trường:

```java
// Mỗi lời gọi có thể phụ thuộc múi giờ mặc định của JVM:
ZoneId defaultZone = ZoneId.systemDefault();
LocalDate today = LocalDate.now();
LocalDateTime nowLocal = LocalDateTime.now();
ZonedDateTime nowZoned = ZonedDateTime.now();
OffsetDateTime nowOffset = OffsetDateTime.now();

// Nếu đầu vào không có zone thì đoạn này đang tự thêm một giả định:
LocalDateTime input = LocalDateTime.parse("2024-05-01T09:00:00");
Instant guessed = input.atZone(ZoneId.systemDefault()).toInstant();
```

Các snippet sử dụng `import java.time.*;` và đặt trong một phương thức. **Không phải mọi lời gọi `now()` là sai**: vấn đề là không kiểm soát **múi giờ nào** quyết định lịch địa phương và không ghi rõ ý nghĩa của dữ liệu.

`ZoneId.systemDefault()` lấy cấu hình múi giờ của JVM/host. Cấu hình này có thể khác theo môi trường và **có thể thay đổi trong tiến trình**, vì vậy không thích hợp làm nguồn quyết định ngầm cho dữ liệu được trao đổi giữa các máy.

### 3.1. Không lẫn việc hỏi “hiện tại” với việc giải nghĩa một giờ trong quá khứ

Để biết **thời điểm hiện tại**, dùng:

```java
Instant currentInstant = Instant.now();
```

`Instant.now()` dùng đồng hồ hệ thống để lấy một instant, không cần áp đặt một múi giờ địa phương lên chuỗi đầu vào. Khi cần **ngày hiện tại của người dùng**, hãy dùng `LocalDate.now(userZone)` hoặc `LocalDate.now(clock)`. Ngược lại, nếu người dùng nhập một `LocalDateTime` quá khứ/tương lai, không thể lấy `Instant.now()` hoặc offset tại thời điểm hiện tại để đoán offset của dữ liệu đó.

### 3.2. Cách đúng là truyền zone như một phần của hợp đồng

```java
ZoneId venueZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime localAppointment =
    LocalDateTime.parse("2024-05-01T09:00:00");

Instant startsAt = localAppointment.atZone(venueZone).toInstant();
// 2024-05-01T02:00:00Z
```

`venueZone` có thể đến từ cấu hình nghiệp vụ, hồ sơ người dùng, địa điểm sự kiện hoặc tham số API **được yêu cầu rõ ràng**. Nếu chưa biết zone, **giữ `LocalDateTime` như dữ liệu chưa xác định instant**, hoặc trả lỗi yêu cầu cung cấp zone; đừng lấp bằng mặc định hệ thống.

## 4. Quy trình chuyển đổi có chủ đích

### 4.1. Từ `Instant` sang giờ hiển thị: có zone, không mơ hồ

```java
Instant event = Instant.parse("2024-10-27T00:30:00Z");
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime parisTime = event.atZone(paris);
ZonedDateTime vietnamTime = event.atZone(vietnam);
```

Với cùng instant này, Paris hiển thị `02:30+02:00` (trước khi chuyển DST mùa thu) và Việt Nam hiển thị `07:30+07:00`. Quy tắc ánh xạ **instant → local time trong một zone** cho một offset phù hợp tại thời điểm ấy; chiều ngược lại có thể mơ hồ.

### 4.2. Từ `LocalDateTime` sang `Instant`: phải thêm ngữ nghĩa

```java
LocalDateTime local = LocalDateTime.of(2024, 5, 1, 9, 0);

// Nếu dữ liệu là 09:00 ở Việt Nam:
Instant asVietnam = local
    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .toInstant();

// Nếu hợp đồng khẳng định đó là 09:00 UTC:
Instant asUtc = local.toInstant(ZoneOffset.UTC);
```

`asVietnam` là `2024-05-01T02:00:00Z`; `asUtc` là `2024-05-01T09:00:00Z`. `toInstant(ZoneOffset.UTC)` **không phải thao tác “thêm UTC miễn phí”**: nó khẳng định input vốn đã là giờ UTC.

Nếu dữ liệu có offset trong chuỗi, parse thẳng thành `OffsetDateTime` để giữ ý nghĩa:

```java
OffsetDateTime input = OffsetDateTime.parse(
    "2024-05-01T09:00:00+07:00");
Instant event = input.toInstant();
// 2024-05-01T02:00:00Z
```

Không parse chuỗi có offset rồi dùng `toLocalDateTime()`, bỏ phần `+07:00`, sau đó tự gắn zone mặc định để “khôi phục” instant; cách đó có thể làm lệch dữ liệu.

### 4.3. Chuyển zone: giữ **instant** hay giữ **giờ địa phương**?

`ZonedDateTime` phân biệt rõ hai phép:

```java
ZonedDateTime source = Instant.parse(
    "2024-10-27T00:30:00Z").atZone(
    ZoneId.of("Europe/Paris"));

ZonedDateTime sameInstant = source.withZoneSameInstant(
    ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime sameLocal = source.withZoneSameLocal(
    ZoneId.of("Asia/Ho_Chi_Minh"));
```

- `withZoneSameInstant`: chuyển biểu diễn sang khu vực mới nhưng **giữ nguyên thời điểm tuyệt đối**; giờ địa phương thường thay đổi.
- `withZoneSameLocal`: cố **giữ nguyên các trường giờ đồng hồ** và diễn giải chúng trong khu vực mới; **instant có thể thay đổi** và các quy tắc gap/overlap vẫn áp dụng.

Khi hiển thị timestamp của một sự kiện ở múi giờ khác, hầu như luôn muốn `withZoneSameInstant`. `withZoneSameLocal` thích hợp hơn với ý định **di chuyển một lịch hẹn “09:00 theo địa phương” sang nơi khác**, và phải được chọn có chủ đích.

`OffsetDateTime` cũng có cặp `withOffsetSameInstant` / `withOffsetSameLocal`. Không dùng chúng như các tên phương thức hoán đổi được.

## 5. DST: tại sao “LocalDateTime + ZoneId” có thể vẫn cần chính sách?

Một số khu vực có quy tắc đổi giờ mùa hè. Với một `LocalDateTime` trong một khu vực, có thể có:

1. **Một offset hợp lệ**: giờ địa phương xác định một instant.
2. **Không offset hợp lệ (gap)**: giờ bị “nhảy qua” khi đồng hồ tiến lên, nên thời điểm ấy không tồn tại.
3. **Hai offset hợp lệ (overlap)**: đồng hồ lùi lại, nên giờ địa phương ấy xảy ra **hai lần**.

`ZoneRules.getValidOffsets(LocalDateTime)` trả danh sách có kích thước **0, 1 hoặc 2**, giúp ứng dụng nhận diện trường hợp. Đây là công cụ phù hợp khi yêu cầu nghiệp vụ “không được tự điều chỉnh giờ đặt hẹn”.

### 5.1. Gap: 02:30 tại Paris ngày 31/03/2024 không tồn tại

`Europe/Paris` chuyển từ `+01:00` sang `+02:00` trong rạng sáng 31/03/2024. `2024-03-31T02:30` thuộc khoảng giờ **không tồn tại**. Theo hành vi chuẩn của `LocalDateTime.atZone(paris)`, giờ này được điều chỉnh **tiến tới 03:30+02:00**:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30);

int validOffsetCount = paris.getRules().getValidOffsets(gap).size();
// 0

ZonedDateTime adjusted = gap.atZone(paris);
// 2024-03-31T03:30+02:00[Europe/Paris]
```

Nếu người dùng đặt lịch đúng 02:30 và ứng dụng không được đổi giờ, hãy **từ chối** hoặc yêu cầu nhập lại; không dùng `atZone` rồi âm thầm chấp nhận 03:30.

### 5.2. Overlap: 02:30 tại Paris ngày 27/10/2024 xảy ra hai lần

Đầu giờ địa phương `2024-10-27T02:30` có hai offset:

```java
LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);
ZoneId paris = ZoneId.of("Europe/Paris");

List<ZoneOffset> options = paris.getRules().getValidOffsets(overlap);
// [+02:00, +01:00]

ZonedDateTime earlier = overlap.atZone(paris);
// 2024-10-27T02:30+02:00 -> 2024-10-27T00:30:00Z

ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
// 2024-10-27T02:30+01:00 -> 2024-10-27T01:30:00Z
```

Snippet cần `import java.util.List; import java.time.*;`. Hai bản ghi có cùng giờ đồng hồ nhưng **cách nhau một giờ tuyệt đối**. Mặc định, `LocalDateTime.atZone` chọn offset **sớm hơn** (thường tương ứng DST) trong overlap. Nếu đúng nghiệp vụ là lượt muộn hơn, dùng `withLaterOffsetAtOverlap()` hoặc yêu cầu người dùng chọn offset.

### 5.3. Từ chối gap/overlap thay vì “tự giải quyết”

Một hàm kiểm tra nghiêm ngặt có thể yêu cầu đúng **một offset hợp lệ**:

```java
static Instant requireUnambiguous(
        LocalDateTime input, ZoneId zone) {
    List<ZoneOffset> offsets = zone.getRules()
        .getValidOffsets(input);
    if (offsets.size() != 1) {
        throw new IllegalArgumentException(
            "Local time is missing or ambiguous");
    }
    return input.toInstant(offsets.get(0));
}
```

Đây là snippet của một **method tĩnh bên trong class**, cần import `java.time.*` và `java.util.List`. Nó từ chối cả 0 offset lẫn 2 offset. Ứng dụng khác có thể hợp lệ khi chọn offset sớm/muộn hoặc điều chỉnh gap; quan trọng là **chính sách phải rõ ràng, kiểm thử được và nhất quán**.

`ZonedDateTime.ofStrict(local, offset, zone)` là API khác để tạo một `ZonedDateTime` **chỉ khi offset được cung cấp là hợp lệ trong zone cho local time ấy**. Với overlap, cần **cung cấp offset mong muốn**; với gap, nó ném `DateTimeException`. Khi đã biết rõ offset từ input, `ofStrict` hữu ích hơn việc bỏ offset rồi để API tự chọn.

### 5.4. Quy tắc vùng có thể thay đổi theo cập nhật tzdb

`ZoneId` không phải một con số offset vĩnh viễn; nó tham chiếu tới quy tắc vùng. Quốc gia có thể thay đổi quy tắc giờ mùa hè hoặc thời điểm chuyển giờ, và JDK có thể cập nhật cơ sở dữ liệu múi giờ. Vì vậy với **lịch hẹn tương lai** phải xác định liệu hệ thống ưu tiên:

- Giữ **giờ địa phương** theo `ZoneId` khi luật vùng thay đổi, nên `Instant` có thể được tính lại.
- Giữ **Instant đã chốt** của sự kiện, nên giờ hiển thị có thể thay đổi sau cập nhật quy tắc.
- Lưu cả `Instant`, `ZoneId`, local date-time gốc và lựa chọn offset/phiên bản quy tắc khi domain yêu cầu kiểm toán chặt chẽ.

Không có một chính sách đúng cho mọi lĩnh vực. Điểm quan trọng là đừng thay thế `ZoneId` bằng offset “hiện tại” khi đang lên lịch cho tương lai.

## 6. Phân biệt so sánh “cùng instant” với so sánh “cùng trường ngày giờ”

Hai `OffsetDateTime` có thể đại diện **cùng một instant** nhưng không `equals` vì local time và offset khác nhau:

```java
OffsetDateTime hcm = OffsetDateTime.parse(
    "2024-01-15T10:00:00+07:00");

OffsetDateTime utc = OffsetDateTime.parse(
    "2024-01-15T03:00:00Z");

boolean sameObjectValue = hcm.equals(utc);   // false
boolean sameMoment = hcm.isEqual(utc);       // true
boolean sameInstant = hcm.toInstant().equals(utc.toInstant());
// true
```

**Chọn kiểu so sánh theo câu hỏi nghiệp vụ:**

- “Hai sự kiện cùng xảy ra lúc nào?” → so `Instant` hoặc `isEqual`.
- “Hai giá trị offset date-time có cùng các trường và offset?” → `equals`.
- “Hai cuộc hẹn có cùng ngày và giờ địa phương của một cơ sở?” → so local fields **sau khi đã xác định đúng cùng zone** và chính sách.
- “Ai đến trước ai?” → so `Instant` để so timeline; đừng so chuỗi ngày giờ địa phương ở các múi giờ khác nhau.

`OffsetDateTime`, `ZonedDateTime`, `Instant` là **value-based immutable classes**; so giá trị bằng `equals` khi cần đúng hợp đồng, không dùng `==` làm tiêu chí nghiệp vụ. Riêng so “cùng thời điểm” không phải lúc nào cũng trùng với `equals` của giá trị có offset/zone.

## 7. Parse và format: đừng vứt offset/zone khỏi payload

### 7.1. Ba định dạng diễn đạt ba hợp đồng khác nhau

```text
2024-05-01T09:00:00
    -> chỉ có local date-time, CHƯA có instant

2024-05-01T09:00:00+07:00
    -> có offset, xác định instant 2024-05-01T02:00:00Z

2024-05-01T09:00:00+07:00[Asia/Ho_Chi_Minh]
    -> có offset cùng region zone (cú pháp ISO_ZONED_DATE_TIME mở rộng của Java)
```

Các cách parse tương ứng:

```java
LocalDateTime local = LocalDateTime.parse(
    "2024-05-01T09:00:00");

OffsetDateTime withOffset = OffsetDateTime.parse(
    "2024-05-01T09:00:00+07:00");

ZonedDateTime withZone = ZonedDateTime.parse(
    "2024-05-01T09:00:00+07:00[Asia/Ho_Chi_Minh]");

Instant instant = Instant.parse("2024-05-01T02:00:00Z");
```

Không gọi `LocalDateTime.parse` trên payload có offset rồi **bỏ qua hậu tố**. Nếu input có offset, giữ nguyên bằng `OffsetDateTime` hoặc chuyển ngay thành `Instant` khi cần timeline.

### 7.2. Dùng formatter có hợp đồng rõ

`DateTimeFormatter.ISO_INSTANT` dành cho instant biểu diễn theo UTC. `ISO_OFFSET_DATE_TIME` dùng cho ngày-giờ có offset, `ISO_ZONED_DATE_TIME` cho ngày-giờ có offset kèm zone region khi có.

```java
Instant event = Instant.parse("2024-05-01T02:00:00Z");

String canonical = DateTimeFormatter.ISO_INSTANT.format(event);
// 2024-05-01T02:00:00Z

String displayed = event.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")).format(
    DateTimeFormatter.ISO_ZONED_DATE_TIME);
// 2024-05-01T09:00:00+07:00[Asia/Ho_Chi_Minh]
// Tùy formatter, các trường giây bằng 0 có thể bị lược bớt ở dạng in.
```

Cần phân biệt **định dạng đầu ra** và **ý nghĩa dữ liệu**. `DateTimeFormatter.withZone(zone)` có thể hữu ích khi format một `Instant`, nhưng nó **không thay thế** yêu cầu xác minh zone gốc của chuỗi local không có offset. Khi parse dữ liệu không có zone, chính sách zone vẫn cần xuất phát từ hợp đồng API.

### 7.3. Không dùng tên viết tắt mơ hồ làm khóa dữ liệu

`"CST"` có thể được dùng ở nhiều nơi với ý nghĩa khác nhau. Các tên `PST`, `IST`, `CST` hoặc ký hiệu hiển thị locale không phải lựa chọn tốt cho contract giao tiếp. Khi cần khu vực, ưu tiên **IANA zone ID** như `Europe/Paris`, `America/New_York`, `Asia/Ho_Chi_Minh`. Khi nguồn xác định offset, dùng `Z`, `+07:00` hoặc dạng offset chuẩn rõ ràng.

Khi cần bảo toàn chính sách địa phương tương lai, lưu region ID thay vì chỉ lưu abbreviation hoặc offset hiện tại.

## 8. Thiết kế API để không tạo giả định ngầm

### 8.1. API cho sự kiện đã xảy ra

Nếu API tiếp nhận thời điểm một giao dịch được ghi nhận, kiểu có ngữ nghĩa tự nhiên là:

```java
void recordPayment(Instant occurredAt);
```

Đây là **chữ ký minh họa**, không phải class hoàn chỉnh. Client có thể gửi timestamp với offset, server parse thành `OffsetDateTime` hoặc `Instant` rồi chuẩn hóa thành `Instant`. Khi hiển thị, yêu cầu `ZoneId` của người xem.

Không nên dùng:

```java
void recordPayment(LocalDateTime occurredAt);
```

nếu contract thật sự là **thời điểm tuyệt đối** và không có thông tin zone đi kèm: kiểu này cho phép dữ liệu mơ hồ.

### 8.2. API đặt lịch địa phương tương lai

Nếu lịch là “09:00 theo địa phương tại nơi tổ chức”, có thể thiết kế:

```java
void schedule(LocalDateTime localStart, ZoneId venueZone);
```

Hệ thống còn cần chính sách khi local time rơi vào DST gap/overlap. Nếu muốn người dùng quyết định lần 02:30 thứ nhất hay thứ hai trong ngày lùi giờ, payload phải truyền lựa chọn offset hoặc thông tin phân giải tương đương.

Một API chỉ nhận `LocalDateTime` rồi dùng `ZoneId.systemDefault()` đang **che giấu một phần contract quan trọng** trong cấu hình server. Cách xử lý phụ thuộc môi trường và khó kiểm thử.

### 8.3. API cho giờ lặp hằng ngày

“Gửi thông báo lúc 09:00 ở Paris mỗi ngày” thường cần:

- `LocalTime.of(9,0)`: giờ đồng hồ.
- `ZoneId.of("Europe/Paris")`: quy tắc địa phương.
- Ngày tiếp theo và **chính sách DST** khi ứng dụng tính một `Instant` thực thi cụ thể.

Đừng lấy `Instant.now().plus(Duration.ofDays(1))` như cách duy nhất để tạo lịch “09:00 hằng ngày”: trong những ngày chuyển giờ, **24 giờ trôi qua** không nhất thiết đưa về cùng giờ địa phương. Lịch theo ngày nên tính ngày địa phương tiếp theo bằng `LocalDate.plusDays(1)` rồi giải nghĩa với `ZoneId`, sau đó áp dụng quy tắc gap/overlap.

## 9. Lưu trữ và trao đổi dữ liệu: chốt mô hình trước công nghệ

### 9.1. Sự kiện đã xảy ra: lưu `Instant` và thêm zone nếu cần giải thích

Với audit log, thời điểm thanh toán, kết quả hoàn tất một tác vụ, giá trị trọng tâm thường là **một instant**. Có thể biểu diễn bằng ISO-8601 UTC như `2024-05-01T02:00:00Z` hoặc một kiểu dữ liệu lưu timeline được tài liệu hệ quản trị cơ sở dữ liệu xác nhận.

Nếu cần biết **người dùng đã nhìn thấy giờ nào khi nhập**, ngoài instant có thể lưu zone và/hoặc local date-time gốc. Đừng suy lại zone của người dùng từ instant: **rất nhiều khu vực có thể có cùng offset tại một thời điểm**.

### 9.2. Kế hoạch theo đồng hồ địa phương: lưu đủ `LocalDateTime + ZoneId`

Với chuyến bay, lịch làm việc, cuộc hẹn dự kiến, giờ đồng hồ và khu vực có thể là phần trọng tâm của domain. Khi đó lưu:

```text
local_start = 2024-10-27T02:30
zone_id     = Europe/Paris
dst_policy  = EARLIER_OFFSET hoặc LATER_OFFSET hoặc REJECT
```

Đây là **sơ đồ dữ liệu minh họa**, không phải một kiểu SQL tiêu chuẩn. Khi cần thực thi, tính instant từ local time + zone + policy. Nếu có yêu cầu kiểm toán hoặc đã xác nhận thời điểm, lưu thêm `Instant` và offset đã chọn.

Việc đặt `ZoneId` vào cấu hình toàn cục rồi chỉ lưu local time khiến bản ghi mất ngữ nghĩa sau khi cấu hình hoặc vùng triển khai thay đổi.

### 9.3. Kiểu timestamp trong database không giống nhau giữa các hệ

Tên cột `TIMESTAMP`, `DATETIME`, `TIMESTAMP WITH TIME ZONE` không cam kết cùng một cách lưu zone/offset ở mọi engine. Một số driver chuyển đổi theo timezone/session setting; một số hệ lưu instant đã chuẩn hóa và **không giữ zone ID gốc**. Vì thế cần **đọc hợp đồng của database/driver và kiểm thử round-trip**, không suy từ tên kiểu SQL rằng nó bảo toàn múi giờ.

Checklist thử round-trip:

1. Chọn instant chuẩn `2024-10-27T00:30:00Z`.
2. Ghi qua tầng JDBC/ORM theo kiểu Java đã chọn.
3. Đọc lại trong session/app có múi giờ **khác**.
4. So `Instant` đọc lại với instant ban đầu.
5. Nếu cần lưu zone gốc, kiểm tra riêng rằng `Europe/Paris` vẫn được giữ đúng.
6. Thử cả gap/overlap, nano/millisecond precision và giá trị trước epoch nếu domain cần.

Không dùng `LocalDateTime` làm kiểu lưu trữ cho một instant **chỉ vì nhìn giống timestamp**; nếu database thực tế không có offset/zone, phải quy định rõ quy ước UTC trong schema và conversion ở **mọi** điểm đọc/ghi.

### 9.4. JSON và contract cần rõ liệu offset là bắt buộc

Hai JSON sau không tương đương:

```json
{"occurredAt":"2024-05-01T09:00:00"}
```

```json
{"occurredAt":"2024-05-01T09:00:00+07:00"}
```

Chuỗi đầu không xác định instant; chuỗi sau xác định. Nếu API yêu cầu thời điểm tuyệt đối, validate payload phải có `Z` hoặc offset. Nếu API muốn lịch theo khu vực, sử dụng thêm một field `zoneId` và quy định cách giải nghĩa `localStart`.

Khi một thư viện serializer tự thêm `Z` hoặc offset vào `LocalDateTime`, điều đó là **một phép diễn giải dữ liệu** cần kiểm soát, không chỉ “thêm format cho đẹp”. Dùng test round-trip qua timezone khác để phát hiện biến đổi ngoài ý muốn.

## 10. Ranh giới ngày địa phương không luôn là 24 giờ

Một ngày trên lịch trong một `ZoneId` có thể dài **23, 24 hoặc 25 giờ**, và các trường hợp lịch sử đặc biệt còn có thể khác. Ví dụ ngày 27/10/2024 ở Paris có một khoảng giờ lặp nên dài **25 giờ thực**.

Tính ranh giới theo **ngày địa phương + ZoneId**, rồi chuyển sang instant:

```java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDate day = LocalDate.of(2024, 10, 27);

Instant startInclusive = day.atStartOfDay(zone).toInstant();
Instant endExclusive = day.plusDays(1)
    .atStartOfDay(zone).toInstant();

long hours = Duration.between(startInclusive, endExclusive).toHours();
// 25
```

Đây là đoạn minh họa trong method với import `java.time.*`.

**Tránh** tính `endExclusive = startInclusive.plus(Duration.ofDays(1))` rồi dùng nó để xác định “hết ngày địa phương” một cách phổ quát. `Duration.ofDays(1)` là **24 giờ**, trong khi `LocalDate.plusDays(1)` tăng **một ngày lịch**. Chúng có ý nghĩa khác nhau khi qua DST.

Mẫu lọc dữ liệu khuyến nghị là khoảng **nửa mở** `[startInclusive, endExclusive)`:

```text
eventInstant >= startInclusive
    AND eventInstant < endExclusive
```

Cách này tránh “cuối ngày 23:59:59.999...” vốn dễ bỏ sót độ chính xác nano hoặc giả định mọi ngày có cùng độ dài. Lưu ý `LocalDate.atStartOfDay(zone)` tạo **thời điểm hợp lệ sớm nhất**, không cam kết luôn đúng `00:00` nếu zone có chuyển giờ tại nửa đêm.

## 11. Test xác định với `Clock` thay vì phụ thuộc môi trường

Trong ứng dụng thực, `Instant.now()` là đúng khi cần biết hiện tại, nhưng **test** sẽ khó dự đoán nếu dùng đồng hồ thật. Hãy truyền `Clock` vào class thực hiện logic thời gian:

```java
final class ReportService {
    private final Clock clock;
    private final ZoneId businessZone;

    ReportService(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    LocalDate currentBusinessDate() {
        return LocalDate.now(clock.withZone(businessZone));
    }
}
```

Đây là **class snippet** cần import `java.time.Clock`, `LocalDate` và `ZoneId`. Trong test:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2024-05-01T23:30:00Z"),
    ZoneOffset.UTC
);

LocalDate utcDate = LocalDate.now(
    fixed.withZone(ZoneOffset.UTC)); // 2024-05-01

LocalDate vietnamDate = LocalDate.now(
    fixed.withZone(ZoneId.of("Asia/Ho_Chi_Minh")));
// 2024-05-02
```

Với cùng một instant, địa phương có thể đã sang **ngày khác**. Nếu yêu cầu báo cáo là “theo ngày của khách hàng”, phải dùng zone của khách hàng. Nếu muốn “theo ngày UTC”, ghi rõ UTC. Không dùng `LocalDate.now()` không tham số trong logic cần ổn định giữa server.

Trong cấu trúc ứng dụng lớn, `Clock` có thể được đưa qua dependency injection; kiểm thử bằng `Clock.fixed` làm dữ liệu dự đoán được mà không cần đổi zone toàn JVM hay chỉnh giờ hệ điều hành.

## 12. Chương trình Java chạy độc lập: đối chiếu các trường hợp rủi ro

Ví dụ sau dùng **API từ Java 8** nhưng chạy được trên JDK hiện đại. Nó kiểm tra:

1. Cùng `LocalDateTime` cho **hai `Instant`** khác nhau nếu áp dụng hai zone.
2. Cùng một `Instant` hiển thị khác nhau ở Paris và Việt Nam, nhưng giữ nguyên timeline.
3. `OffsetDateTime.equals` khác `isEqual` khi hai offset khác nhau.
4. DST gap và overlap, trong đó overlap có **hai instant** khác nhau; `ZonedDateTime.ofStrict` từ chối offset không hợp lệ.
5. `withZoneSameInstant` khác `withZoneSameLocal`.
6. `Clock.fixed` cho ngày địa phương ổn định, và ngày lịch có thể dài 25 giờ.

Tạo file **ExplicitTimeZoneDemo.java**:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class ExplicitTimeZoneDemo {
    static Instant requireUnambiguous(
            LocalDateTime local, ZoneId zone) {
        List<ZoneOffset> valid =
            zone.getRules().getValidOffsets(local);
        if (valid.size() != 1) {
            throw new IllegalArgumentException(
                "Missing or ambiguous local time");
        }
        return local.toInstant(valid.get(0));
    }

    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        LocalDateTime rawLocal = LocalDateTime.parse(
            "2024-05-01T09:00:00");

        Instant interpretVietnam = rawLocal.atZone(vietnam)
            .toInstant();
        Instant interpretUtc = rawLocal.toInstant(ZoneOffset.UTC);

        System.out.println("Vietnam 09:00 -> "
            + interpretVietnam);
        System.out.println("UTC 09:00 -> "
            + interpretUtc);
        System.out.println("Same local, same instant? "
            + interpretVietnam.equals(interpretUtc));

        Instant fixedEvent = Instant.parse(
            "2024-10-27T00:30:00Z");
        ZonedDateTime inParis = fixedEvent.atZone(paris);
        ZonedDateTime inVietnam = fixedEvent.atZone(vietnam);

        System.out.println("Paris local: "
            + inParis.toLocalDateTime()
            + ", offset=" + inParis.getOffset());
        System.out.println("Vietnam local: "
            + inVietnam.toLocalDateTime()
            + ", offset=" + inVietnam.getOffset());
        System.out.println("Same instant in two zones: "
            + inParis.toInstant().equals(inVietnam.toInstant()));

        OffsetDateTime withHcmOffset = OffsetDateTime.parse(
            "2024-01-15T10:00:00+07:00");
        OffsetDateTime withUtcOffset = OffsetDateTime.parse(
            "2024-01-15T03:00:00Z");
        System.out.println("OffsetDateTime equals: "
            + withHcmOffset.equals(withUtcOffset));
        System.out.println("OffsetDateTime isEqual: "
            + withHcmOffset.isEqual(withUtcOffset));

        LocalDateTime gap = LocalDateTime.of(
            2024, 3, 31, 2, 30);
        System.out.println("Gap valid offset count: "
            + paris.getRules().getValidOffsets(gap).size());
        ZonedDateTime adjusted = gap.atZone(paris);
        System.out.println("Gap adjusted: "
            + adjusted.toLocalDateTime()
            + ", offset=" + adjusted.getOffset());

        boolean strictGapRejected = false;
        try {
            ZonedDateTime.ofStrict(gap,
                ZoneOffset.ofHours(1), paris);
        } catch (DateTimeException expected) {
            strictGapRejected = true;
        }
        System.out.println("Strict gap rejected: "
            + strictGapRejected);

        LocalDateTime overlap = LocalDateTime.of(
            2024, 10, 27, 2, 30);
        System.out.println("Overlap offsets: "
            + paris.getRules().getValidOffsets(overlap));
        ZonedDateTime earlier = overlap.atZone(paris);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
        System.out.println("Overlap earlier: "
            + earlier.toInstant());
        System.out.println("Overlap later: "
            + later.toInstant());
        System.out.println("Overlap instant delta hours: "
            + Duration.between(earlier.toInstant(),
                later.toInstant()).toHours());

        boolean ambiguityRejected = false;
        try {
            requireUnambiguous(overlap, paris);
        } catch (IllegalArgumentException expected) {
            ambiguityRejected = true;
        }
        System.out.println("Ambiguous rejected: "
            + ambiguityRejected);

        ZonedDateTime sameInstant = inParis
            .withZoneSameInstant(vietnam);
        ZonedDateTime sameLocal = inParis
            .withZoneSameLocal(vietnam);
        System.out.println("withZoneSameInstant preserves instant: "
            + sameInstant.toInstant().equals(fixedEvent));
        System.out.println("withZoneSameLocal preserves instant: "
            + sameLocal.toInstant().equals(fixedEvent));

        Clock clock = Clock.fixed(
            Instant.parse("2024-05-01T23:30:00Z"),
            ZoneOffset.UTC
        );
        System.out.println("Fixed UTC date: "
            + LocalDate.now(clock.withZone(ZoneOffset.UTC)));
        System.out.println("Fixed Vietnam date: "
            + LocalDate.now(clock.withZone(vietnam)));

        LocalDate transitionDay = LocalDate.of(2024, 10, 27);
        Instant dayStart = transitionDay.atStartOfDay(paris)
            .toInstant();
        Instant nextDayStart = transitionDay.plusDays(1)
            .atStartOfDay(paris).toInstant();
        System.out.println("Paris calendar day duration hours: "
            + Duration.between(dayStart, nextDayStart).toHours());
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac -encoding UTF-8 ExplicitTimeZoneDemo.java
java ExplicitTimeZoneDemo
```

**Stdout dự kiến, không phụ thuộc múi giờ mặc định của JVM:**

```text
Vietnam 09:00 -> 2024-05-01T02:00:00Z
UTC 09:00 -> 2024-05-01T09:00:00Z
Same local, same instant? false
Paris local: 2024-10-27T02:30, offset=+02:00
Vietnam local: 2024-10-27T07:30, offset=+07:00
Same instant in two zones: true
OffsetDateTime equals: false
OffsetDateTime isEqual: true
Gap valid offset count: 0
Gap adjusted: 2024-03-31T03:30, offset=+02:00
Strict gap rejected: true
Overlap offsets: [+02:00, +01:00]
Overlap earlier: 2024-10-27T00:30:00Z
Overlap later: 2024-10-27T01:30:00Z
Overlap instant delta hours: 1
Ambiguous rejected: true
withZoneSameInstant preserves instant: true
withZoneSameLocal preserves instant: false
Fixed UTC date: 2024-05-01
Fixed Vietnam date: 2024-05-02
Paris calendar day duration hours: 25
```

**Giải thích kết quả:**

- Một `LocalDateTime` không có zone nên có thể ánh xạ ra nhiều instant; giá trị `09:00` tại Việt Nam khác `09:00` tại UTC đúng 7 giờ.
- Một `Instant` khi hiển thị ở Paris và Việt Nam có giờ đồng hồ khác nhau nhưng không thay đổi timeline.
- `OffsetDateTime.equals` so giá trị local date-time + offset; `isEqual` so underlying instant.
- `Europe/Paris` có DST gap lúc `02:30` ngày 31/03/2024; `atZone` mặc định điều chỉnh tới `03:30+02:00`, còn tạo strict với offset không hợp lệ bị từ chối.
- Trong DST overlap `02:30` ngày 27/10/2024, hai offset hợp lệ `+02:00` và `+01:00` cho hai thời điểm chênh một giờ. `requireUnambiguous` từ chối dữ liệu này nếu hệ thống yêu cầu một lựa chọn duy nhất.
- `withZoneSameInstant` giữ thời điểm; `withZoneSameLocal` giữ đồng hồ nên có thể thay đổi thời điểm.
- `Clock.fixed` cho cùng instant nhưng ngày khác nhau giữa UTC và Việt Nam. Ngày DST kết thúc ở Paris dài 25 giờ, nên không thể lấy 24 giờ làm định nghĩa của mọi ngày địa phương.

**Lưu ý kiểm thử:** Kết quả DST phụ thuộc bộ quy tắc múi giờ đã được cung cấp bởi JDK. Ví dụ dùng các chuyển đổi lịch sử năm 2024 của `Europe/Paris`; để có tính tái lập lâu dài, ghi nhận JDK/tzdb version trong môi trường test. Ứng dụng lịch tương lai cũng nên cập nhật tzdb theo chính sách vận hành.

## 13. Các tình huống ứng dụng và lựa chọn đúng

| Dữ liệu / yêu cầu | Kiểu và chính sách phù hợp | Vì sao |
| --- | --- | --- |
| Một thanh toán đã ghi nhận | `Instant occurredAt` | Đã có một thời điểm tuyệt đối. |
| Timestamp API có `Z` hoặc `+07:00` | Parse `Instant` hoặc `OffsetDateTime` | Offset có mặt, không cần đoán default zone. |
| Màn hình hiển thị lịch sử theo quốc gia người xem | `instant.atZone(viewerZone)` | Cùng sự kiện, cách hiển thị khác nhau. |
| Hẹn `09:00` tại Paris ngày tương lai | `LocalDateTime` + `ZoneId Europe/Paris` + DST policy | Offset có thể khác theo ngày. |
| Giờ mở cửa `09:00` hằng ngày | `LocalTime` + `ZoneId` | Đây là quy tắc lịch địa phương, không phải một instant bất biến. |
| Kiểm tra sự kiện xảy ra trước/sau | So `Instant` | Không nhầm giờ đồng hồ tại các zone khác nhau. |
| Người dùng nhập “2024-05-01T09:00” mà không có zone | Giữ local hoặc yêu cầu thêm zone | Không đủ dữ liệu tạo một instant duy nhất. |
| Payload có offset nhưng cần giữ zone kinh doanh | Lưu `Instant` **và** `ZoneId` nếu cần | Offset không đủ mô tả quy tắc khu vực về tương lai. |
| Báo cáo theo ngày địa phương | `LocalDate` + `ZoneId` → hai ranh giới instant | Một ngày không phải lúc nào cũng 24 giờ. |
| Unit test ngày giờ hiện tại | `Clock.fixed` + zone rõ ràng | Không phụ thuộc default zone hoặc thời gian chạy. |
| DB chỉ lưu local timestamp nhưng ứng dụng coi là UTC | Quy định rõ UTC ở mọi mapping đọc/ghi | Nếu không, round-trip qua zone khác có thể sai. |
| Hệ thống cần biết lần 02:30 nào trong DST overlap | Payload có offset hoặc chính sách chọn offset | `LocalDateTime + ZoneId` riêng lẻ vẫn còn hai lựa chọn. |

## 14. Những lỗi phổ biến và cách sửa

### 14.1. Cố định `UTC` bằng cách gắn `Z` vào chuỗi local

**Sai:** nhận `"2024-05-01T09:00:00"` rồi tự nối `"Z"` hoặc gọi `local.toInstant(ZoneOffset.UTC)` dù người dùng thực sự nhập 09:00 Việt Nam.

**Đúng:** giữ nguyên `LocalDateTime` cho đến khi nhận `ZoneId`, hoặc yêu cầu client gửi offset/instant nếu API đang trao đổi một thời điểm tuyệt đối.

### 14.2. Lấy `ZoneId.systemDefault()` làm default nghiệp vụ

**Sai:** vùng triển khai server quyết định địa phương của hóa đơn/cuộc hẹn. Một container ở UTC và một máy ở `Asia/Ho_Chi_Minh` sẽ hiểu input khác nhau.

**Đúng:** zone là tham số bắt buộc, cấu hình nghiệp vụ có tên rõ ràng hoặc dữ liệu của địa điểm/user. Không lặp `ZoneId.of("Asia/Ho_Chi_Minh")` khắp code nếu ứng dụng có nhiều tenant; truyền nó qua lớp domain/service thích hợp.

### 14.3. Dùng offset hiện tại cho lịch tương lai

**Sai:** lấy `ZonedDateTime.now(venueZone).getOffset()` rồi ghép offset đó vào tất cả lịch năm tới. Khu vực có DST hoặc thay đổi luật có thể có offset khác tại ngày sự kiện.

**Đúng:** giải nghĩa **local date-time của chính sự kiện** bằng `ZoneId` và `ZoneRules` tại ngày đó. Nếu cần xử lý chính sách gap/overlap, kiểm tra `getValidOffsets`.

### 14.4. Tưởng `atZone` sẽ ném lỗi với giờ không tồn tại

**Sai:** `LocalDateTime.atZone` thường **tự điều chỉnh** gap và chọn offset sớm trong overlap. Điều này có thể tạo “lịch hẹn lúc 03:30” dù người dùng nhập 02:30.

**Đúng:** xác định chính sách chấp nhận/từ chối bằng `getValidOffsets`; dùng `ZonedDateTime.ofStrict` khi đã có offset cụ thể và không được phép điều chỉnh âm thầm.

### 14.5. Lẫn `withZoneSameLocal` với `withZoneSameInstant`

**Sai:** thay region của một timestamp đã chốt bằng `withZoneSameLocal` rồi cho rằng vẫn là cùng sự kiện tuyệt đối.

**Đúng:** hiển thị cùng một sự kiện tại vùng khác bằng `withZoneSameInstant` hoặc `instant.atZone(zone)`.

### 14.6. Bỏ offset sau khi parse

**Sai:** `OffsetDateTime.parse(payload).toLocalDateTime()` rồi chỉ lưu kết quả làm timestamp event. Thông tin offset biến mất; không thể chắc chắn tái dựng instant ban đầu.

**Đúng:** lưu `toInstant()` cho sự kiện hoặc lưu cả biểu diễn offset nếu cần fidelity. Nếu một downstream chỉ nhận `LocalDateTime`, phải nói rõ nó mang **giờ địa phương** chứ không phải event instant.

### 14.7. Sử dụng `equals` khi nghiệp vụ hỏi “cùng thời điểm”

**Sai:** so hai `OffsetDateTime` khác offset qua `equals` rồi coi chúng là hai giao dịch xảy ra khác thời điểm.

**Đúng:** dùng `isEqual` hoặc so `toInstant` khi câu hỏi là trên timeline.

### 14.8. Dùng 24 giờ làm ranh giới mọi ngày

**Sai:** `startOfLocalDayInstant.plus(Duration.ofDays(1))` luôn là ngày hôm sau ở khu vực có DST.

**Đúng:** tính `day.plusDays(1).atStartOfDay(zone).toInstant()` riêng; dùng khoảng nửa mở.

### 14.9. Giả định kiểu SQL có chữ “time zone” tự lưu IANA `ZoneId`

**Sai:** tin rằng database tự bảo toàn `Europe/Paris` và offset đã chọn, dù schema/driver có thể chỉ lưu instant hoặc định dạng khác.

**Đúng:** xác minh contract của từng engine, driver, schema và phiên bản; lưu `ZoneId` riêng nếu miền nghiệp vụ cần.

### 14.10. Test theo đồng hồ/múi giờ thật

**Sai:** assert ngày hiện tại là một giá trị cố định nhưng gọi `LocalDate.now()` trong test; hoặc kiểm thử ý nghĩa một timestamp bằng zone của máy chạy.

**Đúng:** dùng `Clock.fixed`, `ZoneId` explicit và dữ liệu ngày cố định; thêm test đặc biệt cho các trường hợp DST gap/overlap.

## 15. Câu hỏi tự kiểm tra (có đáp án)

**1.** `LocalDateTime.of(2024,5,1,9,0)` có xác định một `Instant` duy nhất chưa?

**Đáp án:** chưa. Phải biết offset hoặc zone và quy tắc phân giải.

**2.** Nếu cùng local time 09:00 ngày 01/05/2024 ở UTC và `Asia/Ho_Chi_Minh`, hai instant lệch bao nhiêu?

**Đáp án:** 7 giờ, lần lượt `09:00Z` và `02:00Z`.

**3.** Một chuỗi `2024-05-01T09:00:00+07:00` nên parse thành gì nếu API nói đó là thời điểm tuyệt đối?

**Đáp án:** `OffsetDateTime.parse(...).toInstant()` hoặc quy trình parse có hợp đồng tương đương; không xóa offset rồi tự gắn default zone.

**4.** Tại sao dùng `+01:00` cố định không đủ thay cho `Europe/Paris` khi lên lịch hẹn tương lai?

**Đáp án:** `Europe/Paris` có quy tắc offset thay đổi theo ngày; `+01:00` là offset cố định, không mô tả DST.

**5.** `2024-03-31T02:30` ở Paris là trường hợp nào?

**Đáp án:** **gap**; không có offset hợp lệ. `atZone` điều chỉnh giờ, vì vậy chính sách nghiêm ngặt nên phát hiện và từ chối nếu người dùng không cho phép.

**6.** `2024-10-27T02:30` ở Paris có bao nhiêu instant khả dĩ?

**Đáp án:** hai: `00:30Z` với `+02:00` và `01:30Z` với `+01:00`.

**7.** Khi chuyển một cuộc gọi đã diễn ra ở Paris sang giờ Việt Nam, dùng `withZoneSameInstant` hay `withZoneSameLocal`?

**Đáp án:** `withZoneSameInstant`, để giữ đúng thời điểm sự kiện.

**8.** Vì sao `OffsetDateTime.equals` và `OffsetDateTime.isEqual` có thể khác nhau?

**Đáp án:** `equals` so cả local date-time/offset, trong khi `isEqual` so thời điểm tuyệt đối trên timeline.

**9.** Một ngày địa phương có thể dài 25 giờ không?

**Đáp án:** có; ngày 27/10/2024 ở Paris là ví dụ khi DST kết thúc và đồng hồ lùi một giờ.

**10.** Để tạo báo cáo “ngày hôm nay của khách hàng”, gọi `LocalDate.now()` không tham số có đủ an toàn không?

**Đáp án:** không nếu môi trường triển khai có zone khác của khách hàng. Nên gọi `LocalDate.now(customerZone)` hoặc dùng `Clock` được cấu hình rõ.

**11.** Khi đọc timestamp từ database, tên cột `TIMESTAMP WITH TIME ZONE` có cam kết giữ IANA zone ID nguyên bản không?

**Đáp án:** không nên giả định. Cần xem contract cụ thể của database/driver, kiểm thử round-trip và lưu zone riêng nếu cần.

**12.** Khi đổi từ `LocalDateTime` sang `Instant` mà thiếu cả offset lẫn zone của sự kiện, có cách nào suy ra luôn đúng không?

**Đáp án:** không. Đây là thiếu thông tin, không phải thiếu API. Phải yêu cầu bổ sung ngữ cảnh hoặc ghi rõ giả định theo chính sách nghiệp vụ.

## 16. Tài liệu API chính thức đang được duy trì

Các API nêu trong bài đều thuộc Java 8+ và tiếp tục được hỗ trợ; các nguồn chính thức dùng để kiểm tra ngữ nghĩa:

- [`Instant` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html): timeline tuyệt đối, parse ISO `Z`, `atZone`.
- [`LocalDateTime` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDateTime.html): giá trị không chứa zone; `atZone` và quy tắc xử lý DST gap/overlap.
- [`ZoneId` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html): region ID, `systemDefault` và quy tắc múi giờ.
- [`ZoneOffset` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneOffset.html): offset cố định và `UTC`.
- [`ZoneRules` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html): `getValidOffsets` để nhận diện gap/overlap.
- [`ZonedDateTime` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html): `ofStrict`, `withLaterOffsetAtOverlap`, `withZoneSameInstant`, `withZoneSameLocal`.
- [`OffsetDateTime` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/OffsetDateTime.html): timestamp có offset, `isEqual` và `toInstant`.
- [`Clock` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html): `fixed`, `withZone` cho logic/test độc lập hệ thống.
- [`DateTimeFormatter` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html): định dạng `ISO_INSTANT`, `ISO_OFFSET_DATE_TIME`, `ISO_ZONED_DATE_TIME`.

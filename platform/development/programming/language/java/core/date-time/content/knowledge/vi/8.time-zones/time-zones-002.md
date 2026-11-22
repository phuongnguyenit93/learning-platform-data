# ZoneOffset biểu diễn độ lệch cố định so với UTC

Trong Java, **`ZoneOffset` là một độ lệch thời gian cố định so với UTC**, ví dụ `+07:00` (nhanh hơn UTC 7 giờ), `-05:00` (chậm hơn UTC 5 giờ) hoặc `Z` (độ lệch bằng 0). `ZoneOffset` thuộc gói `java.time`, kế thừa `ZoneId` và là một dạng `ZoneId` có quy tắc offset **không thay đổi**.

Sự khác biệt quan trọng là **một độ lệch cố định không đồng nghĩa với một múi giờ địa lý**. `ZoneOffset.of("+07:00")` chỉ nói “cộng 7 giờ so với UTC”, còn `ZoneId.of("Asia/Ho_Chi_Minh")` nói đến quy tắc thời gian của một vùng cụ thể. Hai đối tượng có thể cho cùng offset ở một thời điểm, nhưng chỉ ID vùng mới mô tả cách tra cứu offset theo lịch sử hoặc thay đổi luật múi giờ.

Sau bài học này, bạn có thể đọc đúng dấu `+/-`, tạo và kiểm tra `ZoneOffset`, chuyển đổi `Instant` với giờ địa phương, và quyết định khi nào cần `ZoneId` có quy tắc vùng thay vì offset cố định.

## 1. UTC, offset và giờ địa phương

**UTC** (Coordinated Universal Time) là mốc tham chiếu. Một offset mô tả chênh lệch của giờ địa phương so với UTC theo đơn vị giờ, phút, có thể gồm giây:

```text
local date-time = UTC date-time + offset
UTC date-time   = local date-time - offset
```

Các ví dụ tại **cùng thời điểm** `2024-06-01T00:00:00Z`:

| Offset | Giờ địa phương của thời điểm trên | Ý nghĩa |
| --- | --- | --- |
| `Z` hay `+00:00` | `2024-06-01 00:00` | Trùng UTC |
| `+07:00` | `2024-06-01 07:00` | Nhanh hơn UTC 7 giờ |
| `+05:30` | `2024-06-01 05:30` | Nhanh hơn UTC 5 giờ 30 phút |
| `-05:00` | `2024-05-31 19:00` | Chậm hơn UTC 5 giờ; có thể thuộc ngày hôm trước |

**Quy tắc dấu:** `+07:00` nghĩa là giờ địa phương **bằng UTC cộng 7 giờ**; để tìm UTC từ giờ địa phương `09:00+07:00`, **trừ** 7 giờ, được `02:00Z`. Ngược lại, từ `09:00-05:00` phải **cộng** 5 giờ để được `14:00Z`. Sai dấu có thể làm sai thời điểm hàng giờ và thậm chí sai ngày.

Chữ `Z` là ký hiệu **zero offset** khi biểu diễn thời gian theo ISO-8601. Nó tương đương `+00:00` về giá trị offset. `ZoneOffset.UTC` và `ZoneOffset.of("Z")` cùng thể hiện offset 0.

## 2. ZoneOffset chứa thông tin nào?

`ZoneOffset` là một giá trị **bất biến** (*immutable*) và an toàn để dùng lại. Nó lưu offset dưới dạng **tổng số giây có dấu** so với UTC. Đây không phải timestamp và cũng không phải số giây từ đầu ngày:

```java
import java.time.ZoneOffset;

ZoneOffset vietnamOffset = ZoneOffset.of("+07:00");

System.out.println(vietnamOffset);                   // +07:00
System.out.println(vietnamOffset.getTotalSeconds());  // 25200
```

`7 × 3.600 = 25.200` giây, nên `getTotalSeconds()` trả số dương. Với `-05:00`, giá trị là `-18.000` giây. Offset bằng 0 trả `0`. Một `ZoneOffset` không chứa thông tin về **nước, thành phố, ngày lịch, DST, người dùng** hoặc giờ đồng hồ cụ thể.

`ZoneOffset` là lớp con của `ZoneId` và có thể được truyền vào những API nhận `ZoneId`:

```java
ZoneOffset fixed = ZoneOffset.ofHours(7);
ZoneId acceptedAsZone = fixed; // hợp lệ vì ZoneOffset extends ZoneId
```

Đoạn minh họa cần import `java.time.ZoneOffset` và `java.time.ZoneId`. Khi dùng một `ZoneOffset` làm zone, offset luôn cố định tại mọi thời điểm: nó **không tự đổi** khi đi qua mùa hè/mùa đông.

## 3. Tạo ZoneOffset bằng những API nào?

| API | Ví dụ | Kết quả/ý nghĩa |
| --- | --- | --- |
| `ZoneOffset.UTC` | Hằng có sẵn | `Z` |
| `ZoneOffset.of(String)` | `of("+07:00")` | Offset +7 giờ |
| `ZoneOffset.of(String)` | `of("-05:30")` | Offset âm 5 giờ 30 phút |
| `ZoneOffset.ofHours(int)` | `ofHours(7)` | `+07:00` |
| `ZoneOffset.ofHoursMinutes(int,int)` | `ofHoursMinutes(5,30)` | `+05:30` |
| `ZoneOffset.ofHoursMinutesSeconds(int,int,int)` | `ofHoursMinutesSeconds(5,30,15)` | `+05:30:15` |
| `ZoneOffset.ofTotalSeconds(int)` | `ofTotalSeconds(25200)` | `+07:00` |

Cách phổ biến nhất là đọc chuỗi offset ISO-8601:

```java
ZoneOffset plusSeven = ZoneOffset.of("+07:00");
ZoneOffset minusFive = ZoneOffset.of("-05:00");
ZoneOffset zero = ZoneOffset.of("Z");

System.out.println(plusSeven); // +07:00
System.out.println(minusFive); // -05:00
System.out.println(zero);      // Z
```

Đây là đoạn minh họa cần import `java.time.ZoneOffset`. Một số dạng khác được `ZoneOffset.of` hỗ trợ gồm `+07`, `+0700`, `+07:00` và dạng có giây như `+07:00:30`; tuy nhiên, với API tự thiết kế, nên thống nhất định dạng chuẩn `±HH:MM` (hoặc `Z`) để dễ đọc và giảm nhầm lẫn.

### Tạo từ giờ, phút, giây

```java
ZoneOffset a = ZoneOffset.ofHoursMinutes(5, 30);       // +05:30
ZoneOffset b = ZoneOffset.ofHoursMinutes(-5, -30);     // -05:30
ZoneOffset c = ZoneOffset.ofTotalSeconds(19_800);     // +05:30
```

Trong `ofHoursMinutes` và `ofHoursMinutesSeconds`, các thành phần có dấu phải **nhất quán** theo ràng buộc của API; không nên ghép giờ âm với phút dương theo suy diễn “-5 giờ + 30 phút”. Nếu nhận các trường từ biểu mẫu, hãy kiểm tra dấu đầu vào và tốt nhất biến đổi thành một **tổng số giây đã xác định rõ** trước khi dùng `ofTotalSeconds`.

Dùng `ZoneOffset.ofTotalSeconds(...)` nếu nguồn dữ liệu là offset tính bằng giây. Không chuyển nhầm **phút** sang **giây**: `+05:30` tương ứng `330` phút nhưng **19.800** giây, không phải `530` giây hoặc `5.30` giờ.

### Miền giá trị hợp lệ

Java giới hạn offset từ **-18:00 đến +18:00**, bao gồm hai đầu, tức tổng giây trong `[-64800, +64800]`. Khi thành phần giờ đạt `18`, phút và giây phải là `0`.

```java
ZoneOffset.of("+18:00"); // hợp lệ
ZoneOffset.of("-18:00"); // hợp lệ
ZoneOffset.of("+18:01"); // DateTimeException
ZoneOffset.of("+19:00"); // DateTimeException
```

Đoạn minh họa này có các lời gọi **cố ý lỗi** ở hai dòng cuối; chúng sẽ ném `java.time.DateTimeException` (hoặc một lớp con) và cần được bắt nếu chương trình phải chạy tiếp. Trong code production, ưu tiên để API xác thực miền và trả lỗi đầu vào rõ ràng, thay vì tự sửa offset không hợp lệ.

## 4. Chuyển Instant thành giờ với offset cố định

`Instant` là một **thời điểm tuyệt đối** trên trục UTC. Khi đã có `Instant` và `ZoneOffset`, bạn có thể lấy biểu diễn giờ địa phương dưới dạng `OffsetDateTime`:

```java
Instant event = Instant.parse("2024-06-01T00:00:00Z");
ZoneOffset plusSeven = ZoneOffset.of("+07:00");
ZoneOffset minusFive = ZoneOffset.of("-05:00");

OffsetDateTime vietnamLikeTime = event.atOffset(plusSeven);
OffsetDateTime minusFiveTime = event.atOffset(minusFive);

System.out.println(vietnamLikeTime); // 2024-06-01T07:00+07:00
System.out.println(minusFiveTime);   // 2024-05-31T19:00-05:00
```

Đây là đoạn minh họa cần import `java.time.*`. Hai `OffsetDateTime` khác nhau về **ngày/giờ hiển thị và offset** nhưng `toInstant()` của cả hai đều bằng `event`. Khi thay cách hiển thị một thời điểm, hãy giữ nguyên `Instant`; việc chọn offset khác chỉ thay cách đọc giờ trên đồng hồ.

`event.atZone(plusSeven)` cũng hợp lệ vì `ZoneOffset` là một `ZoneId` có quy tắc cố định; kết quả là `ZonedDateTime`. Khi muốn biểu diễn “ngày giờ kèm offset”, `OffsetDateTime` làm ý nghĩa dữ liệu rõ hơn.

## 5. Gắn offset cho một LocalDateTime

`LocalDateTime` chỉ mang **ngày và giờ trên đồng hồ**. Khi biết chắc offset của dữ liệu đó, có thể tạo `OffsetDateTime` và suy ra thời điểm:

```java
LocalDateTime local = LocalDateTime.of(2024, 6, 1, 9, 0);
ZoneOffset offset = ZoneOffset.of("+07:00");

OffsetDateTime withOffset = local.atOffset(offset);
Instant instant = withOffset.toInstant();

System.out.println(withOffset); // 2024-06-01T09:00+07:00
System.out.println(instant);    // 2024-06-01T02:00:00Z
```

Đoạn minh họa cần import `java.time.*`. `OffsetDateTime.of(local, offset)` tương đương về kết quả với `local.atOffset(offset)`. Việc gắn offset **đang đưa thêm giả định**: thời gian đầu vào thật sự thuộc offset đó. Java không tự suy ra offset đúng từ nơi ở hay địa điểm của người dùng.

Nếu nguồn nói rõ `2024-06-01T09:00+07:00`, parse thành `OffsetDateTime` để giữ offset đã công bố:

```java
OffsetDateTime parsed =
        OffsetDateTime.parse("2024-06-01T09:00:00+07:00");
Instant actualInstant = parsed.toInstant();
```

Không parse thành `LocalDateTime` rồi bỏ `+07:00` nếu cần giữ ý nghĩa thời điểm; một `LocalDateTime` không đủ để khôi phục chính xác `Instant` khi mất offset.

### Đổi offset: giữ thời điểm hay giữ giờ trên đồng hồ?

Hai phép chuyển của `OffsetDateTime` có tên gần nhau nhưng **ngữ nghĩa khác nhau**:

```java
OffsetDateTime original =
        OffsetDateTime.parse("2024-06-01T09:00:00+07:00");

OffsetDateTime sameInstant =
        original.withOffsetSameInstant(ZoneOffset.UTC);
// 2024-06-01T02:00Z: giữ nguyên thời điểm thực

OffsetDateTime sameLocal =
        original.withOffsetSameLocal(ZoneOffset.UTC);
// 2024-06-01T09:00Z: giữ nguyên chữ số ngày/giờ, đổi thời điểm thực
```

Đây là đoạn minh họa cần import `java.time.*`. Để **hiển thị cùng một sự kiện ở offset khác**, dùng `withOffsetSameInstant`. `withOffsetSameLocal` chỉ phù hợp khi nghiệp vụ cố ý **diễn giải lại giờ đồng hồ** dưới một offset khác; không được dùng nó để chuyển múi giờ cho sự kiện đã xảy ra.

## 6. Chương trình Java 17+ chạy hoàn chỉnh

Tạo tệp **`ZoneOffsetDemo.java`**:

```java
import java.time.*;

public class ZoneOffsetDemo {
    public static void main(String[] args) {
        ZoneOffset plusSeven = ZoneOffset.of("+07:00");
        ZoneOffset minusFive = ZoneOffset.ofHours(-5);
        Instant instant = Instant.parse("2024-06-01T00:00:00Z");

        System.out.println("Offset: " + plusSeven);
        System.out.println("Total seconds: " + plusSeven.getTotalSeconds());
        System.out.println("UTC: " + instant);
        System.out.println("At +07:00: " + instant.atOffset(plusSeven));
        System.out.println("At -05:00: " + instant.atOffset(minusFive));

        LocalDateTime local = LocalDateTime.of(2024, 6, 1, 9, 0);
        OffsetDateTime scheduled = OffsetDateTime.of(local, plusSeven);
        System.out.println("Local with offset: " + scheduled);
        System.out.println("Corresponding instant: " + scheduled.toInstant());
        System.out.println("From seconds: " + ZoneOffset.ofTotalSeconds(25_200));
        System.out.println("Z equals UTC: " + ZoneOffset.of("Z").equals(ZoneOffset.UTC));

        ZoneId paris = ZoneId.of("Europe/Paris");
        System.out.println("Paris January: " + paris.getRules()
                .getOffset(Instant.parse("2024-01-15T12:00:00Z")));
        System.out.println("Paris July: " + paris.getRules()
                .getOffset(Instant.parse("2024-07-15T12:00:00Z")));

        try {
            ZoneOffset.of("+19:00");
            System.out.println("Invalid offset: accepted");
        } catch (DateTimeException ex) {
            System.out.println("Invalid offset: rejected");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ZoneOffsetDemo.java
java ZoneOffsetDemo
```

**stdout chính xác** (mã đã được biên dịch với `javac --release 17` và chạy thành công):

```text
Offset: +07:00
Total seconds: 25200
UTC: 2024-06-01T00:00:00Z
At +07:00: 2024-06-01T07:00+07:00
At -05:00: 2024-05-31T19:00-05:00
Local with offset: 2024-06-01T09:00+07:00
Corresponding instant: 2024-06-01T02:00:00Z
From seconds: +07:00
Z equals UTC: true
Paris January: +01:00
Paris July: +02:00
Invalid offset: rejected
```

Đọc từng kết quả:

1. `ZoneOffset.of("+07:00")` có `getTotalSeconds() == 25200`, **không mang tên vùng địa lý**.
2. Cùng một `Instant` in ở `+07:00` và `-05:00` thành hai ngày/giờ đồng hồ khác nhau, nhưng vẫn chỉ là **một thời điểm thực**.
3. `OffsetDateTime.of(local, plusSeven).toInstant()` trừ 7 giờ để chuyển `09:00+07:00` thành `02:00Z`.
4. `ZoneOffset.ofTotalSeconds(25200)` khôi phục đúng offset `+07:00`.
5. Offset của `Europe/Paris` lần lượt `+01:00` (tháng 1) và `+02:00` (tháng 7) trong năm 2024; một `ZoneOffset` riêng lẻ không tự thay đổi theo mùa.
6. `+19:00` nằm ngoài phạm vi Java cho phép và bị từ chối.

## 7. ZoneOffset và ZoneId vùng: khác nhau ở quy tắc theo thời gian

Mặc dù `ZoneOffset` kế thừa `ZoneId`, **không phải mọi ZoneId đều là một ZoneOffset**. `ZoneId.of("Europe/Paris")` sử dụng bộ **zone rules** tra cứu offset phù hợp với từng thời điểm.

```java
ZoneId paris = ZoneId.of("Europe/Paris");

Instant winter = Instant.parse("2024-01-15T12:00:00Z");
Instant summer = Instant.parse("2024-07-15T12:00:00Z");

ZoneOffset winterOffset = paris.getRules().getOffset(winter); // +01:00
ZoneOffset summerOffset = paris.getRules().getOffset(summer); // +02:00
```

Đoạn minh họa cần import `java.time.*`. Nếu một cuộc họp được mô tả là **“09:00 giờ Paris vào mọi ngày làm việc”**, dùng `ZoneId.of("Europe/Paris")` cùng ngày/giờ địa phương khi tính từng cuộc họp. Dùng cố định `ZoneOffset.of("+01:00")` cho cả năm sẽ sai khi Paris vào giờ mùa hè.

Với một số địa phương hiện không đổi offset theo mùa, `ZoneId` vẫn đáng dùng khi nghiệp vụ được diễn đạt theo **địa điểm**: lịch sử từng vùng hoặc quy định pháp luật tương lai có thể làm offset thay đổi. Nếu dữ liệu chỉ nói “+07:00” thì `ZoneOffset` lại là biểu diễn trung thực nhất; **không tự suy đoán** đó là Việt Nam, Thái Lan hay một vùng cụ thể.

### Offset cố định và DST gap/overlap

`ZoneOffset.of("+01:00")` luôn có quy tắc `+01:00`, không có thay đổi DST. Trong khi đó, khi gắn `LocalDateTime` với một `ZoneId` như `Europe/Paris` hoặc `America/New_York`:

- Có những giờ địa phương **không tồn tại** khi đồng hồ tiến lên (*gap*).
- Có những giờ địa phương **xuất hiện hai lần** khi đồng hồ lùi (*overlap*).

Một `LocalDateTime` cộng với một `ZoneOffset` cụ thể đủ để xác định `Instant` theo offset đó, nhưng **không xác nhận** giờ ấy có hợp lệ trong một vùng IANA hay không. Nếu nguồn là lịch hẹn theo thành phố, phải tra cứu zone rules và có chính sách xử lý gap/overlap trước khi ấn định sự kiện.

## 8. Phân biệt ZoneOffset với các kiểu dữ liệu liên quan

| Kiểu | Mang gì? | Có mô tả thời điểm duy nhất? |
| --- | --- | --- |
| `ZoneOffset` | Số giây lệch UTC cố định | Không, vì chưa có ngày/giờ |
| `ZoneId` dạng vùng | ID vùng và cách tra cứu quy tắc | Không, vì chưa có ngày/giờ |
| `LocalDateTime` | Ngày + giờ địa phương | Không, vì thiếu offset/vùng |
| `OffsetDateTime` | Ngày + giờ + offset | Có; `toInstant()` xác định một thời điểm |
| `ZonedDateTime` | Ngày + giờ + ZoneId và offset đã phân giải | Có; `toInstant()` xác định một thời điểm |
| `Instant` | Thời điểm tuyệt đối | Có |

Nếu API trả `createdAt`, `sentAt` hoặc `paidAt`, hãy dùng một giá trị có nghĩa là **thời điểm thực**, chẳng hạn `Instant` hoặc `OffsetDateTime` theo hợp đồng. Nếu API trả “giờ mở cửa 09:00” thì `LocalTime` phù hợp hơn; việc gán cứng `+07:00` vào một giờ mở cửa mà không có ngày có thể làm mất quy tắc vùng khi chuyển sang lịch tương lai.

`ZoneOffset` **không phải** `Duration`: offset `+07:00` có thể quy đổi thành +25.200 giây để tính giờ, nhưng không mang nghĩa “sự kiện kéo dài 7 giờ”. Cũng không phải `Instant`: chỉ từ `+07:00` không thể suy ra sự kiện xảy ra lúc nào.

## 9. Parse, format và hợp đồng API

Khi truyền timestamp giữa hệ thống, nên sử dụng định dạng ISO-8601 có offset rõ ràng:

```text
2024-06-01T09:00:00+07:00
2024-06-01T02:00:00Z
```

Hai chuỗi trên biểu diễn **cùng một `Instant`**. Chuỗi `2024-06-01T09:00:00` thì thiếu offset nên **không nói lên cùng thời điểm**.

Parse theo kiểu phù hợp với dữ liệu:

```java
OffsetDateTime input =
        OffsetDateTime.parse("2024-06-01T09:00:00+07:00");

ZoneOffset suppliedOffset = input.getOffset(); // +07:00
Instant event = input.toInstant();              // 2024-06-01T02:00:00Z
```

Đây là đoạn minh họa cần import `java.time.*`. Nếu chỉ muốn parse văn bản offset độc lập, dùng `ZoneOffset.of("+07:00")`. Khi nhận tên vùng `Asia/Ho_Chi_Minh`, dùng `ZoneId.of(...)` thay vì `ZoneOffset.of(...)`.

Nếu hệ thống cần cả **thời điểm thực** và **vùng của lịch hẹn**, hãy biểu diễn chúng thành hai thuộc tính rõ ràng. Ví dụ một hợp đồng giao dịch đã có thời điểm:

```json
{
  "occurredAt": "2024-06-01T02:00:00Z",
  "displayZoneId": "Asia/Ho_Chi_Minh"
}
```

Còn khi nguồn chỉ cung cấp offset xác định:

```json
{
  "occurredAt": "2024-06-01T09:00:00+07:00"
}
```

Điều quan trọng là giữ offset/Instant nếu cần khôi phục thời điểm. Không bỏ `+07:00` rồi tiếp tục giả định mọi máy đọc chuỗi local date-time giống nhau.

## 10. Các lỗi thường gặp

1. **Đổi chiều dấu của offset.** `+07:00` là UTC + 7 giờ, nên `09:00+07:00` tương ứng `02:00Z`, không phải `16:00Z`.
2. **Coi offset là ID vùng địa lý.** `+07:00` không định danh duy nhất Việt Nam; nhiều vùng có thể cùng offset tại một thời điểm.
3. **Dùng offset hiện tại cho mọi ngày quá khứ hoặc tương lai của một vùng.** Vùng có thể thay đổi luật DST hoặc offset. Lấy `ZoneId` của vùng rồi tra quy tắc ở từng thời điểm.
4. **Cho rằng `ZoneOffset` tự đổi theo DST.** Nó bất biến và cố định. Chỉ `ZoneId` dạng vùng mới cung cấp các quy tắc thay đổi theo thời gian.
5. **Nhầm đơn vị của `getTotalSeconds()`.** `+05:30` trả **19.800 giây**, không phải 330 hay 5.30.
6. **Dùng offset ngoài phạm vi.** Java chỉ nhận từ `-18:00` đến `+18:00`; tại hai mốc ±18 giờ không được có phút/giây khác 0.
7. **Gắn một offset đoán trước cho `LocalDateTime`.** `atOffset` tạo một thời điểm dựa theo giả định đã chọn; nó không tự xác thực quy tắc địa lý.
8. **Đổi offset bằng `withOffsetSameLocal` khi muốn giữ thời điểm.** Hãy dùng `withOffsetSameInstant` để đổi cách hiển thị cùng sự kiện.
9. **Lưu timestamp không có offset/zone trong API đa vùng.** Mỗi client có thể diễn giải thành thời điểm khác. Dùng `Instant` hoặc `OffsetDateTime` theo hợp đồng.
10. **Sửa timezone mặc định toàn JVM để giải quyết một request.** Định tuyến phụ thuộc tường minh bằng `ZoneId` / `ZoneOffset`; tránh ảnh hưởng luồng khác.
11. **So sánh `LocalDateTime` từ hai hệ thống như thể là timestamp tuyệt đối.** Hai giờ địa phương phải được đưa về cùng `Instant` trước khi so sánh thời điểm thực.

## 11. Kiểm thử các ranh giới quan trọng

| Tình huống | Kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Offset 0 | `ZoneOffset.of("Z")` | Bằng `ZoneOffset.UTC` |
| Offset dương | `ZoneOffset.of("+07:00").getTotalSeconds()` | `25200` |
| Offset âm | `ZoneOffset.of("-05:00").getTotalSeconds()` | `-18000` |
| Offset có phút | `ZoneOffset.of("+05:30").getTotalSeconds()` | `19800` |
| Giá trị cận trên | `ZoneOffset.of("+18:00")` | Hợp lệ |
| Giá trị cận dưới | `ZoneOffset.of("-18:00")` | Hợp lệ |
| Vượt giới hạn | `ZoneOffset.of("+19:00")` | Ném `DateTimeException` |
| Cận 18 giờ có phút | `ZoneOffset.of("+18:01")` | Ném `DateTimeException` |
| Giữ thời điểm | `withOffsetSameInstant(UTC)` | `toInstant()` không đổi |
| Giữ giờ đồng hồ | `withOffsetSameLocal(UTC)` | `toLocalDateTime()` không đổi, `Instant` có thể đổi |
| Zone theo mùa | Paris 15/01 và 15/07/2024 | `+01:00` và `+02:00` |

Trong JUnit 5, có thể so sánh `assertEquals(25_200, ZoneOffset.of("+07:00").getTotalSeconds())`, dùng `assertThrows(DateTimeException.class, () -> ZoneOffset.of("+19:00"))`, và kiểm tra cùng `Instant` khi đổi offset bằng `withOffsetSameInstant`. Đoạn kiểm thử cần các import phù hợp và static import `org.junit.jupiter.api.Assertions.*`.

## 12. Cách chọn API phù hợp

| Bạn cần làm gì? | API |
| --- | --- |
| Tạo một độ lệch UTC cố định | `ZoneOffset.of("+07:00")` |
| Lấy số giây lệch UTC | `offset.getTotalSeconds()` |
| Tạo offset từ số giây | `ZoneOffset.ofTotalSeconds(seconds)` |
| Hiển thị một Instant ở offset cố định | `instant.atOffset(offset)` |
| Kết hợp ngày giờ địa phương với offset đã biết | `localDateTime.atOffset(offset)` |
| Tính Instant từ ngày giờ + offset | `offsetDateTime.toInstant()` |
| Giữ Instant khi đổi offset | `offsetDateTime.withOffsetSameInstant(newOffset)` |
| Biểu diễn lịch hẹn theo quy tắc thành phố | `ZoneId.of("Europe/Paris")` và zone rules |
| Lấy offset hợp lệ của một vùng tại thời điểm | `zone.getRules().getOffset(instant)` |
| Lưu thời điểm chính xác | `Instant` hoặc `OffsetDateTime` theo hợp đồng |

**Ghi nhớ:** `ZoneOffset` là **số giây có dấu cố định so với UTC**, hữu ích khi offset được biết rõ hoặc khi chuyển một thời điểm giữa các cách hiển thị. Nó **không phải** tên vùng, không có lịch DST và không tự xác định một sự kiện xảy ra lúc nào. Khi nghiệp vụ nói “giờ của thành phố/vùng qua nhiều ngày”, hãy dùng `ZoneId` của vùng để giữ đúng quy tắc lịch sử và thay đổi theo thời gian.

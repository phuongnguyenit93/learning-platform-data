# LocalDateTime thành Instant cần ZoneOffset phù hợp

Trong Java, `LocalDateTime` chứa **ngày và giờ trên đồng hồ** (ví dụ `2024-03-01T09:00`) nhưng **không chứa múi giờ, offset UTC hoặc một thời điểm tuyệt đối**. Ngược lại, `Instant` chỉ một **thời điểm duy nhất** trên trục thời gian, độc lập với việc người dùng đang ở Việt Nam hay New York.

Để chuyển `LocalDateTime` thành `Instant`, Java cần biết **độ lệch UTC (`ZoneOffset`) phù hợp với chính ngày giờ đó**:

```java
LocalDateTime local = LocalDateTime.of(2024, 3, 1, 9, 0);
ZoneOffset offset = ZoneOffset.of("+07:00");
Instant instant = local.toInstant(offset);
// 2024-03-01T02:00:00Z
```

Đây là đoạn minh họa cần `import java.time.*;`. `toInstant(offset)` **không tự tìm múi giờ** và **không kiểm tra offset có thật sự thuộc một thành phố hay không**. Nó áp offset mà người gọi cung cấp. Nếu offset bị chọn sai, mã có thể chạy bình thường nhưng `Instant` thu được sai về ý nghĩa nghiệp vụ.

> **Nguyên tắc:** `LocalDateTime + ZoneOffset → Instant` chỉ đúng khi offset đã được xác định bằng dữ liệu hoặc quy tắc đáng tin. Nếu nghiệp vụ nói đến **múi giờ của một địa điểm**, hãy sử dụng `ZoneId` và `ZoneRules` để lấy/kiểm tra offset tại **ngày giờ cụ thể**, đặc biệt quanh DST.

## 1. Vì sao LocalDateTime không tự suy ra được Instant?

Cùng chuỗi ngày và giờ địa phương `2024-03-01T09:00` có thể biểu diễn **nhiều thời điểm UTC** khác nhau:

| LocalDateTime | Offset được áp | Instant tương ứng |
| --- | --- | --- |
| `2024-03-01T09:00` | `+07:00` | `2024-03-01T02:00:00Z` |
| `2024-03-01T09:00` | `Z` / `+00:00` | `2024-03-01T09:00:00Z` |
| `2024-03-01T09:00` | `-05:00` | `2024-03-01T14:00:00Z` |

Cả ba giá trị `LocalDateTime` đều có cùng ngày, giờ, phút. Điều khác nhau là thông tin offset **được bổ sung từ bên ngoài**.

Công thức khái niệm:

```text
Instant (UTC) = LocalDateTime - ZoneOffset
```

Với `09:00+07:00`, ta lấy 09:00 **trừ** 7 giờ để được 02:00 UTC. Với `09:00-05:00`, ta lấy 09:00 **cộng** 5 giờ để được 14:00 UTC. Dấu của offset đặc biệt dễ nhầm:

- `+07:00`: giờ địa phương nhanh hơn UTC 7 giờ.
- `-05:00`: giờ địa phương chậm hơn UTC 5 giờ.
- `Z`: chênh lệch 0 giây, tương đương `ZoneOffset.UTC`.

Một `LocalDateTime` không có trường offset; bản thân nó không thể quyết định trong những kết quả trên kết quả nào đúng.

### Ba khái niệm cần phân biệt

| Kiểu Java | Chứa gì? | Có thể tự xác định một thời điểm duy nhất? |
| --- | --- | --- |
| `LocalDateTime` | Ngày, giờ, phút, giây, nano giây | **Không** |
| `ZoneOffset` | Số giây lệch cố định so với UTC | **Không** nếu đứng riêng |
| `Instant` | Một mốc thời gian tuyệt đối | **Có** |
| `OffsetDateTime` | LocalDateTime + ZoneOffset | **Có**, chuyển được sang `Instant` |
| `ZonedDateTime` | Ngày giờ + ZoneId + offset đã phân giải | **Có**, chuyển được sang `Instant` |
| `ZoneId` dạng vùng | ID như `America/New_York` với các quy tắc thay đổi theo thời gian | Chưa đủ nếu không có ngày giờ/thời điểm |

`ZoneOffset` là một kiểu con của `ZoneId`, nhưng **offset cố định không tương đương với múi giờ địa lý**. `-05:00` có thể đúng ở New York vào một ngày mùa đông, nhưng không đúng vào một số ngày mùa hè.

## 2. API trực tiếp: LocalDateTime.toInstant(ZoneOffset)

Phương thức:

```java
Instant instant = localDateTime.toInstant(offset);
```

- `localDateTime`: ngày/giờ theo lịch ISO, không có thông tin múi giờ.
- `offset`: `java.time.ZoneOffset`, độ lệch UTC mà bạn **chủ động chỉ định**.
- Giá trị trả về: `java.time.Instant`, giữ độ chính xác tới nano giây.
- `LocalDateTime` không bị thay đổi vì các kiểu `java.time` này bất biến.
- Nếu `offset == null`, phương thức không thể thực hiện chuyển đổi; phải truyền offset thực sự, không dùng `null` thay cho “máy tự chọn”.

Ví dụ có offset được hợp đồng xác nhận:

```java
import java.time.*;

LocalDateTime entered = LocalDateTime.of(2024, 3, 1, 9, 0);
ZoneOffset knownOffset = ZoneOffset.ofHours(7);

Instant instant = entered.toInstant(knownOffset);
System.out.println(instant); // 2024-03-01T02:00:00Z
```

Đoạn này minh họa lời gọi và cần đặt trong một phương thức. Nó **đúng về ngữ nghĩa** nếu nguồn dữ liệu cam kết rằng “09:00” đang là giờ với offset `+07:00`. Nếu nguồn chỉ ghi “09:00 New York”, gán `+07:00` là sai dù chương trình vẫn tạo một `Instant`.

### Khi nào có thể truyền thẳng ZoneOffset?

- Payload có trường offset đáng tin cậy, chẳng hạn `2024-03-01T09:00:00+07:00`.
- Giao thức định nghĩa rõ mọi `LocalDateTime` trong trường đó là **giờ UTC**; khi ấy dùng `ZoneOffset.UTC`.
- Thiết bị cố định hoặc hợp đồng nghiệp vụ **thật sự dùng offset cố định**, không yêu cầu tính theo luật múi giờ vùng.
- Bạn đang chuyển giá trị có sẵn `OffsetDateTime`; tốt hơn nên dùng ngay `offsetDateTime.toInstant()` thay vì tách offset và local time rồi ghép lại.

Không nên chọn offset theo thói quen, vị trí máy chủ, ngôn ngữ người dùng hoặc offset “hiện tại” của một thành phố khi dữ liệu thuộc ngày khác.

## 3. Một lựa chọn offset sai có thể làm sai thời điểm dù không có lỗi Java

Xét cùng giờ nhập `2024-03-01T09:00`:

```java
LocalDateTime local = LocalDateTime.of(2024, 3, 1, 9, 0);

Instant correctIfPlus7 = local.toInstant(ZoneOffset.of("+07:00"));
Instant mistakenIfUtc = local.toInstant(ZoneOffset.UTC);

System.out.println(correctIfPlus7); // 2024-03-01T02:00:00Z
System.out.println(mistakenIfUtc);   // 2024-03-01T09:00:00Z
```

Đây là đoạn minh họa cần `import java.time.*;`. Hai kết quả lệch **7 giờ**. Java không thể biết hợp đồng nào đúng nên nó không phát sinh ngoại lệ; trách nhiệm nằm ở việc xác định **ý nghĩa của dữ liệu nguồn**.

Một sai lầm tương tự là:

```java
// CẢNH BÁO: chỉ đúng nếu "local" thực sự được định nghĩa là giờ UTC!
Instant assumedUtc = local.toInstant(ZoneOffset.UTC);
```

Đừng gắn `UTC` chỉ vì ứng dụng chạy trên máy chủ UTC. Múi giờ hệ điều hành không định nghĩa múi giờ của **giờ mà người dùng đã nhập**.

## 4. Khi dữ liệu có tên vùng, hãy tìm offset theo vùng và ngày giờ

Giả sử người dùng đặt lịch **09:00 tại New York**. Vùng `America/New_York` đổi offset giữa mùa đông và mùa hè. Dùng `ZoneId` là đúng với ý định “giờ địa phương ở New York”:

```java
ZoneId newYork = ZoneId.of("America/New_York");

LocalDateTime winter = LocalDateTime.of(2024, 1, 15, 9, 0);
LocalDateTime summer = LocalDateTime.of(2024, 7, 15, 9, 0);

ZonedDateTime winterZoned = winter.atZone(newYork);
ZonedDateTime summerZoned = summer.atZone(newYork);

System.out.println(winterZoned.getOffset()); // -05:00
System.out.println(summerZoned.getOffset()); // -04:00

System.out.println(winterZoned.toInstant());
// 2024-01-15T14:00:00Z
System.out.println(summerZoned.toInstant());
// 2024-07-15T13:00:00Z
```

Đây là đoạn minh họa cần `import java.time.*;`. Cả hai lịch hẹn đều là **09:00 tại New York**; nhưng offset được xác định từ zone rules ở hai ngày khác nhau. Với yêu cầu này, cách trực tiếp thường là:

```java
Instant instant = local.atZone(zone).toInstant();
```

Biến `local` phải là `LocalDateTime`, `zone` là `ZoneId` đã được lựa chọn đúng. Lời gọi trên dùng **quy tắc mặc định** của `atZone` để xử lý giờ địa phương khi DST tạo gap/overlap. Nếu ứng dụng phải **từ chối giờ không tồn tại hoặc bắt người dùng chọn một trong hai offset**, cần xử lý các trường hợp đó riêng (mục 5).

### Dùng ZoneRules khi cần kiểm soát đầy đủ

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2024, 7, 15, 9, 0);

List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);
// Danh sách chứa một offset: -04:00

ZoneOffset offset = valid.get(0);
Instant instant = local.toInstant(offset);
// 2024-07-15T13:00:00Z
```

Đoạn minh họa cần `import java.time.*;` và `import java.util.List;`. Chỉ được gọi `get(0)` như vậy khi đã **xác nhận** danh sách có đúng một phần tử. Ở ranh giới DST, danh sách có thể có **0 hoặc 2 phần tử**; đừng vô tình tạo `IndexOutOfBoundsException` hoặc chọn một phương án nghiệp vụ không xác nhận.

## 5. DST: “ZoneOffset phù hợp” có thể không tồn tại hoặc không duy nhất

Chuyển từ `LocalDateTime` sang `Instant` theo một **vùng địa lý** có ba trường hợp khác nhau. Hỏi `zone.getRules().getValidOffsets(local)` để lấy các offset hợp lệ cho **chính ngày/giờ này**:

| Số offset hợp lệ | Trạng thái | Ý nghĩa |
| --- | --- | --- |
| 1 | Giờ bình thường | Có đúng một `Instant` tương ứng |
| 0 | *Gap* | Giờ đồng hồ không tồn tại trong vùng vào ngày đó |
| 2 | *Overlap* | Một giờ đồng hồ xuất hiện hai lần với hai offset |

### 5.1. Gap: không có offset hợp lệ

Ở New York vào **10/03/2024**, đồng hồ nhảy từ 01:59:59 lên 03:00. Vì vậy `2024-03-10T02:30` là một `LocalDateTime` hợp lệ theo lịch ISO nhưng **không tồn tại như giờ địa phương New York**.

```java
ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);

List<ZoneOffset> offsets =
        newYork.getRules().getValidOffsets(gap);

System.out.println(offsets); // []
```

Đoạn minh họa cần `java.time.*` và `java.util.List`. Nếu gọi:

```java
ZonedDateTime adjusted = gap.atZone(newYork);
System.out.println(adjusted);
// 2024-03-10T03:30-04:00[America/New_York]
```

`atZone` dùng chính sách mặc định **đẩy giờ nằm trong gap tiến lên theo độ dài gap**. Đây có thể là cách xử lý chấp nhận được cho một số tính năng lịch, nhưng **không được mặc nhiên thay một cuộc hẹn 02:30 thành 03:30** nếu người dùng hoặc hợp đồng nghiệp vụ yêu cầu từ chối thời gian không tồn tại.

Quan trọng hơn, `gap.toInstant(ZoneOffset.of("-05:00"))` **vẫn tạo ra một `Instant`** vì `toInstant(offset)` chỉ dùng offset truyền vào; nó không biết ràng buộc `America/New_York`. Instant tạo ra sẽ tương ứng với **03:30 ở New York** tại ngày đó, không phải 02:30 như ý định gốc. Vì vậy không thể dựa vào việc chuyển thành công để kết luận offset phù hợp với vùng.

Khi cần **chế độ nghiêm ngặt** (*strict*):

```java
ZonedDateTime.ofStrict(
        gap, ZoneOffset.of("-05:00"), newYork);
// Ném DateTimeException vì -05:00 không hợp lệ
// cho LocalDateTime này trong America/New_York.
```

Lời gọi minh họa cố ý ném ngoại lệ; để chạy tiếp phải bắt `DateTimeException`. Trong ví dụ này, **không có offset hợp lệ nào** với giờ 02:30 tại vùng New York.

### 5.2. Overlap: có hai offset hợp lệ

Ngày **03/11/2024** tại New York, đồng hồ lùi nên `01:30` diễn ra **hai lần**, một lần `-04:00` và một lần `-05:00`.

```java
ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime repeated = LocalDateTime.of(2024, 11, 3, 1, 30);

List<ZoneOffset> offsets =
        newYork.getRules().getValidOffsets(repeated);

System.out.println(offsets); // [-04:00, -05:00]

Instant first = repeated.toInstant(offsets.get(0));
Instant second = repeated.toInstant(offsets.get(1));

System.out.println(first);  // 2024-11-03T05:30:00Z
System.out.println(second); // 2024-11-03T06:30:00Z
```

Đoạn minh họa cần `import java.time.*;` và `import java.util.List;`. Hai kết quả cách nhau **một giờ thực**, dù `LocalDateTime` là cùng một giá trị. Nếu quan trọng về đơn hàng, chuyến bay, thanh toán hoặc thông báo, hãy lưu lựa chọn offset (hoặc `Instant` đã phân giải) để dữ liệu không bị nhập nhằng.

Mặc định, `repeated.atZone(newYork)` thường chọn **offset xuất hiện sớm hơn**, trong ví dụ là `-04:00`; `withLaterOffsetAtOverlap()` chuyển sang offset xuất hiện sau nếu cần. Đây là chính sách mặc định của API, không nhất thiết là quy tắc nghiệp vụ bạn muốn.

### 5.3. Chiến lược phân giải tường minh

Nếu input gồm `LocalDateTime` và `ZoneId`, một quy trình nghiệp vụ chặt chẽ là:

1. Lấy `List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local)`.
2. Nếu danh sách **rỗng**: từ chối giờ không tồn tại hoặc áp một chính sách điều chỉnh **được ghi rõ**.
3. Nếu có **một phần tử**: dùng offset đó, chẳng hạn `local.toInstant(offsets.get(0))`.
4. Nếu có **hai phần tử**: yêu cầu người dùng chọn hoặc áp quy tắc “lần đầu/lần sau” đã được thống nhất; lưu lựa chọn.
5. Có thể dùng `ZonedDateTime.ofStrict(local, chosenOffset, zone)` để kiểm tra offset được chọn có **hợp lệ tại local date-time và zone**. Khi đã có `ZonedDateTime` hợp lệ, gọi `toInstant()`.

Đừng cố dùng `zone.getRules().getOffset(Instant.now())` để tính offset cho một lịch hẹn ở ngày khác. Offset cần được xác định cho **ngày giờ của lịch hẹn**, không phải tại thời điểm chạy chương trình.

## 6. Ví dụ Java 17+ hoàn chỉnh, đã kiểm chứng

Tạo tệp **`LocalDateTimeToInstantDemo.java`**:

```java
import java.time.*;
import java.util.List;

public class LocalDateTimeToInstantDemo {
    public static void main(String[] args) {
        LocalDateTime vietnamLocal = LocalDateTime.of(2024, 3, 1, 9, 0);
        ZoneOffset vietnamOffset = ZoneOffset.of("+07:00");

        Instant instant = vietnamLocal.toInstant(vietnamOffset);
        System.out.println("Vietnam local: " + vietnamLocal);
        System.out.println("With +07:00: " + instant);
        System.out.println("Mistaken as UTC: " + vietnamLocal.toInstant(ZoneOffset.UTC));
        System.out.println("Round trip: "
                + LocalDateTime.ofInstant(instant, vietnamOffset));

        ZoneId newYork = ZoneId.of("America/New_York");
        LocalDateTime winter = LocalDateTime.of(2024, 1, 15, 9, 0);
        LocalDateTime summer = LocalDateTime.of(2024, 7, 15, 9, 0);
        ZoneOffset winterOffset = newYork.getRules().getValidOffsets(winter).get(0);
        ZoneOffset summerOffset = newYork.getRules().getValidOffsets(summer).get(0);
        System.out.println("NY winter offset: " + winterOffset);
        System.out.println("NY summer offset: " + summerOffset);
        System.out.println("NY winter instant: " + winter.toInstant(winterOffset));
        System.out.println("NY summer instant: " + summer.toInstant(summerOffset));

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("NY gap valid offsets: "
                + newYork.getRules().getValidOffsets(gap));
        System.out.println("NY gap atZone: " + gap.atZone(newYork));
        try {
            ZonedDateTime.ofStrict(gap, ZoneOffset.of("-05:00"), newYork);
            System.out.println("NY gap ofStrict: accepted");
        } catch (DateTimeException ex) {
            System.out.println("NY gap ofStrict: rejected");
        }

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        List<ZoneOffset> candidates = newYork.getRules().getValidOffsets(overlap);
        System.out.println("NY overlap offsets: " + candidates);
        System.out.println("NY overlap first instant: " + overlap.toInstant(candidates.get(0)));
        System.out.println("NY overlap second instant: " + overlap.toInstant(candidates.get(1)));
    }
}
```

Trong thư mục chứa tệp:

```bash
javac LocalDateTimeToInstantDemo.java
java LocalDateTimeToInstantDemo
```

**stdout chính xác**, đã xác minh qua `javac --release 17` và `java`:

```text
Vietnam local: 2024-03-01T09:00
With +07:00: 2024-03-01T02:00:00Z
Mistaken as UTC: 2024-03-01T09:00:00Z
Round trip: 2024-03-01T09:00
NY winter offset: -05:00
NY summer offset: -04:00
NY winter instant: 2024-01-15T14:00:00Z
NY summer instant: 2024-07-15T13:00:00Z
NY gap valid offsets: []
NY gap atZone: 2024-03-10T03:30-04:00[America/New_York]
NY gap ofStrict: rejected
NY overlap offsets: [-04:00, -05:00]
NY overlap first instant: 2024-11-03T05:30:00Z
NY overlap second instant: 2024-11-03T06:30:00Z
```

Các kết quả chứng minh:

- Đúng offset `+07:00` → 09:00 địa phương tương ứng 02:00 UTC.
- Gán nhầm `UTC` không ném lỗi nhưng tạo `Instant` khác 7 giờ.
- Với cùng `LocalDateTime` 09:00 New York, offset mùa đông và mùa hè khác nhau.
- Gap DST có **0 offset hợp lệ**; `atZone` điều chỉnh giờ, còn `ofStrict` từ chối.
- Overlap DST có **2 offset hợp lệ**, do đó có hai `Instant` ứng viên khác nhau.

**Lưu ý:** Đoạn `get(0)` ở ví dụ mùa đông/mùa hè đã cố ý chọn hai thời điểm bình thường có đúng một offset hợp lệ. Đừng sao chép thao tác đó cho ngày giờ tùy ý khi chưa xét gap/overlap.

## 7. Các con đường chuyển đổi tương đương và khi nào nên chọn

### 7.1. LocalDateTime + ZoneOffset

```java
Instant instantA = local.toInstant(offset);
```

Cách gọn nhất nếu **đã có offset phù hợp**. Dữ liệu nguồn phải bảo đảm offset, vì API này không tự tra zone rules.

### 7.2. Qua OffsetDateTime

```java
OffsetDateTime value = local.atOffset(offset);
Instant instantB = value.toInstant();
```

`instantA.equals(instantB)` sẽ là `true` khi cả hai được tạo từ cùng `local` và `offset`. `OffsetDateTime` hữu ích khi bạn cần giữ cả **ngày giờ địa phương và offset** trong đối tượng/API, ví dụ chuỗi `2024-03-01T09:00:00+07:00`.

### 7.3. Qua ZonedDateTime với ZoneId

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instantC = local.atZone(zone).toInstant();
```

Phù hợp khi đầu vào là **giờ của một khu vực cụ thể**, cần quy tắc DST/lịch sử. Tuy nhiên, `atZone` có quy tắc phân giải **gap/overlap mặc định**. Nếu ứng dụng yêu cầu kiểm tra nghiêm ngặt, sử dụng `getValidOffsets` và `ZonedDateTime.ofStrict` như mục 5.

### 7.4. Instant → LocalDateTime: phải biết vùng hoặc offset

Phép chuyển ngược không có một “giờ địa phương chuẩn” duy nhất:

```java
Instant instant = Instant.parse("2024-03-01T02:00:00Z");

LocalDateTime atPlusSeven =
        LocalDateTime.ofInstant(instant, ZoneOffset.of("+07:00"));
// 2024-03-01T09:00

LocalDateTime atUtc =
        LocalDateTime.ofInstant(instant, ZoneOffset.UTC);
// 2024-03-01T02:00
```

Đoạn minh họa cần `import java.time.*;`. Cùng một `Instant` có thể hiển thị thành những `LocalDateTime` khác nhau tùy vùng. **Khứ hồi chỉ bảo toàn local date-time khi sử dụng cùng offset**:

```java
LocalDateTime original = LocalDateTime.of(
        2024, 3, 1, 9, 0, 123_456_789);
ZoneOffset offset = ZoneOffset.of("+07:00");

LocalDateTime restored = LocalDateTime.ofInstant(
        original.toInstant(offset), offset);

System.out.println(restored.equals(original)); // true
```

Độ chính xác nano giây được giữ trong quá trình chuyển `LocalDateTime ↔ Instant` nếu giá trị nằm trong miền mà `Instant` hỗ trợ và dùng offset phù hợp. Đoạn này cũng chỉ là ví dụ bên trong một phương thức Java.

## 8. Tại sao không nên chọn ZoneOffset từ “múi giờ hiện tại”?

Giả sử nhân viên nhập một cuộc hẹn ở New York **tháng 7**, nhưng máy chủ đang chạy **tháng 1**. Lấy offset của New York tại `Instant.now()` sẽ thu `-05:00` vào tháng 1, trong khi cuộc hẹn tháng 7 cần `-04:00`. Vì vậy lịch hẹn sẽ bị tính sai một giờ.

Ví dụ **cần tránh**:

```java
// Dễ sai: offset được lấy ở thời điểm hiện tại, không phải ngày hẹn.
ZoneOffset currentOffset = zone.getRules().getOffset(Instant.now());
Instant appointment = local.toInstant(currentOffset);
```

Đây là mã minh họa với `zone` và `local` đã khai báo; nó còn phụ thuộc giờ chạy hệ thống nên kiểm thử không ổn định. Cách an toàn hơn:

```java
List<ZoneOffset> candidates = zone.getRules().getValidOffsets(local);

if (candidates.size() == 1) {
    Instant appointment = local.toInstant(candidates.get(0));
    // Sử dụng appointment theo nghiệp vụ.
} else {
    // 0: giờ không tồn tại; 2: giờ bị lặp.
    // Áp chính sách đã được thiết kế, không đoán offset.
}
```

Đoạn minh họa trên nằm bên trong phương thức, với `zone: ZoneId`, `local: LocalDateTime` đã có; cần `java.time.*` và `java.util.List`. Nếu nghiệp vụ chọn quy tắc mặc định của `atZone` một cách **có chủ đích**, bạn cũng có thể dùng `local.atZone(zone).toInstant()`, nhưng hãy biết rõ hành vi đó.

## 9. Nhận timestamp từ API: parse theo dữ liệu thực có sẵn

Phân biệt đầu vào:

| Chuỗi | Thông tin có sẵn | Kiểu Java phù hợp |
| --- | --- | --- |
| `2024-03-01T09:00:00` | Ngày + giờ, không có offset | `LocalDateTime` |
| `2024-03-01T09:00:00+07:00` | Ngày + giờ + offset | `OffsetDateTime` |
| `2024-03-01T02:00:00Z` | Một thời điểm UTC | `Instant` |
| `2024-03-01T09:00:00+07:00[Asia/Ho_Chi_Minh]` | Ngày giờ + vùng + offset | `ZonedDateTime` |

Ví dụ khi API đã đưa offset:

```java
OffsetDateTime received =
        OffsetDateTime.parse("2024-03-01T09:00:00+07:00");

Instant instant = received.toInstant();
// 2024-03-01T02:00:00Z
```

Đoạn minh họa cần import `java.time.*`. Đừng parse payload đã có offset rồi gọi `toLocalDateTime()` và làm mất offset, trừ khi nghiệp vụ thật sự chỉ muốn ngày/giờ đồng hồ. Nếu cố gắng tái tạo `Instant` từ `LocalDateTime` đã mất offset, nguồn gốc thời điểm có thể **không phục hồi được**.

Nếu API chỉ có `LocalDateTime`, cần **bổ sung zone/offset theo hợp đồng** trước khi chuyển. Không dùng `ZoneId.systemDefault()` hoặc `ZoneOffset.UTC` như một “mặc định an toàn” nếu dữ liệu thật chưa chỉ ra điều đó.

### Lưu trữ sự kiện và lịch hẹn

- **Sự kiện đã xảy ra** như `createdAt`, `paidAt`, `sentAt`: thường lưu `Instant` hoặc timestamp UTC có quy ước DB/driver rõ ràng; hiển thị qua `instant.atZone(viewerZone)`.
- **Lịch hẹn tương lai theo địa điểm**: thường giữ **`LocalDateTime + ZoneId`** và quy tắc xử lý DST để giữ ý định “09:00 tại Paris”. Có thể lưu thêm `Instant` đã phân giải nếu cần thực thi thông báo/đặt chỗ chính xác.
- **Giao thức mang offset thực sự**: `OffsetDateTime` bảo toàn offset gốc của thông điệp; `toInstant()` khi cần đồng bộ sự kiện.

Tên các kiểu dữ liệu như `TIMESTAMP`, `DATETIME` hoặc `TIMESTAMP WITH TIME ZONE` không có hành vi y hệt nhau ở mọi cơ sở dữ liệu. Cần kiểm tra cách driver/JPA/JDBC ghi và đọc, tránh giả định DB sẽ tự bảo toàn zone IANA hoặc UTC đúng hợp đồng.

## 10. Lỗi phổ biến và cách nhận biết

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `local.toInstant(ZoneOffset.UTC)` cho mọi input | Sự kiện bị lệch nếu giờ nguồn không phải UTC | Dùng offset được xác nhận hoặc phân giải `ZoneId` |
| Chọn `+07:00` chỉ vì server ở Việt Nam | Giờ nguồn có thể thuộc vùng khác | Lấy zone/offset từ dữ liệu nghiệp vụ |
| Dùng offset New York mùa đông cho mùa hè | Sai một giờ | Tra `ZoneRules` theo ngày giờ |
| Dùng `getValidOffsets(local).get(0)` mà không kiểm tra size | Crash ở gap; tự chọn ở overlap | Xử lý ba trường hợp 0/1/2 |
| Coi `toInstant` là phép xác thực múi giờ | Offset không cần hợp lệ với một zone cụ thể | Dùng `ofStrict` hoặc kiểm tra quy tắc |
| Nghĩ `LocalDateTime` có sẵn một `Instant` | Thiếu offset/zone | Cung cấp thông tin đã được xác nhận |
| Nhầm dấu của offset | UTC lệch nhiều giờ | `Instant = local - offset` |
| Dùng `Instant.now()` để chọn offset của ngày lịch hẹn | Sai khi mùa/thời gian khác | Tra theo `LocalDateTime` hoặc tạo `ZonedDateTime` đúng chính sách |
| Chỉ lưu `LocalDateTime` cho giao dịch đa vùng | Không khôi phục được thời điểm chính xác | Lưu `Instant` hoặc cả offset/zone |
| Thêm chữ `Z` trực tiếp vào chuỗi local time | Gán sai ý nghĩa UTC | Chuyển với offset đúng, rồi format `Instant` |
| Nhầm offset với ZoneId của thành phố | Mất quy tắc DST và lịch sử | Dùng ID IANA khi nghiệp vụ là vùng |
| Cho rằng mọi ngày địa phương dài đúng 24 giờ | DST có thể làm ngày thực dài 23/25 giờ | Dùng `ZonedDateTime` / `Instant` để tính thời lượng thực |

## 11. Checklist kiểm thử

| Ca thử | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Offset +07:00 | `LocalDateTime.of(2024,3,1,9,0).toInstant(+07:00)` | `2024-03-01T02:00:00Z` |
| Offset UTC | Cùng local time ở trên với `UTC` | `2024-03-01T09:00:00Z` |
| Offset âm -05:00 | Cùng local time với `-05:00` | `2024-03-01T14:00:00Z` |
| Giờ mùa đông New York | `2024-01-15T09:00` | `-05:00` → `14:00Z` |
| Giờ mùa hè New York | `2024-07-15T09:00` | `-04:00` → `13:00Z` |
| DST gap | `2024-03-10T02:30` New York | 0 offset hợp lệ; `ofStrict` từ chối |
| DST overlap | `2024-11-03T01:30` New York | 2 offset, 2 `Instant` khác nhau |
| Khứ hồi với cùng offset | `LocalDateTime → Instant → LocalDateTime` | Giữ lại giá trị gốc, kể cả nano giây |
| Khứ hồi với offset khác | Chuyển về local time bằng offset khác | Có thể khác ngày/giờ địa phương |
| Payload ISO có offset | Parse `OffsetDateTime` | Giữ offset và tính đúng `Instant` |
| Offset ngoài miền | `ZoneOffset.of("+19:00")` | Ném `DateTimeException` |

Trong JUnit 5, một bài kiểm thử có thể dùng `assertEquals` để so sánh hai `Instant` mong đợi và `assertThrows(DateTimeException.class, ...)` khi muốn bảo đảm `ZonedDateTime.ofStrict` từ chối một offset không hợp lệ theo quy tắc vùng. Các ca kiểm thử tại ranh giới DST có giá trị hơn việc chỉ thử lúc giữa ngày bình thường.

## 12. Chọn đường chuyển đổi nhanh

| Thông tin bạn đang có | Muốn nhận | Cách làm phù hợp |
| --- | --- | --- |
| `LocalDateTime` + `ZoneOffset` đã xác thực | `Instant` | `local.toInstant(offset)` |
| `LocalDateTime` + `ZoneOffset` | Ngày/giờ vẫn kèm offset | `local.atOffset(offset)` |
| `OffsetDateTime` | `Instant` | `value.toInstant()` |
| `LocalDateTime` + `ZoneId` của vùng | `Instant` với chính sách mặc định | `local.atZone(zone).toInstant()` |
| `LocalDateTime` + `ZoneId`, cần chặt chẽ với DST | `Instant` không mơ hồ | Kiểm tra `getValidOffsets`, chọn hợp lệ, có thể `ofStrict` |
| `Instant` + `ZoneOffset` | `LocalDateTime` | `LocalDateTime.ofInstant(instant, offset)` |
| `Instant` + `ZoneId` vùng | `ZonedDateTime` | `instant.atZone(zone)` |
| Hai `Instant` | Thời lượng thực | `Duration.between(start, end)` |

**Ghi nhớ:** `LocalDateTime` mô tả **giờ trên đồng hồ**, còn `Instant` mô tả **một thời điểm tuyệt đối**. Phép `local.toInstant(offset)` chỉ đúng khi **`ZoneOffset` thực sự phù hợp với nguồn dữ liệu**. Nếu giờ gắn với một thành phố, dùng `ZoneId` và quy tắc của ngày đó; tại gap/overlap DST phải có quyết định tường minh thay vì tự đoán.

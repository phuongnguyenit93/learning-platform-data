# Thời gian, múi giờ, định dạng chuẩn và đơn vị đo

Trong REST API, một giá trị chỉ có ích khi client và server hiểu cùng một ý nghĩa. Chuỗi `2026-11-17T09:00:00` chưa cho biết đó là thời điểm nào trên toàn cầu; số `1500` chưa cho biết đó là gam, kilôgam hay mili giây. JSON hợp lệ về cú pháp vẫn có thể tạo ra hợp đồng dữ liệu mơ hồ.

Bài học thuộc chương **Biểu diễn dữ liệu** của module **INTEGRATION_API_REST**. Trọng tâm là thiết kế biểu diễn của resource để thời gian và đại lượng đo có ý nghĩa rõ ràng, có thể mô tả bằng OpenAPI, kiểm tra ở biên HTTP và xử lý nhất quán trong Java/Spring hoặc nền tảng tương đương. Các quyết định này cũng ảnh hưởng đến lọc dữ liệu, phân trang, cache, idempotency và lỗi trả cho client.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt thời điểm tuyệt đối, ngày theo lịch, giờ địa phương, lịch hẹn và khoảng thời gian.
- Chọn biểu diễn ngày giờ có offset, hiểu khi nào cần lưu thêm mã múi giờ.
- Quy định định dạng, độ chính xác, quy tắc chuẩn hóa và giới hạn dữ liệu trong hợp đồng API.
- Thiết kế bộ lọc thời gian và giá trị đo có đơn vị rõ ràng.
- Dùng các kiểu `java.time`, `BigDecimal` và nguồn thời gian `Clock` đúng vai trò.
- Xác định các tình huống cần kiểm thử ở biên giao tiếp.

## 2. Xác định ý nghĩa trước khi chọn kiểu dữ liệu

Đừng bắt đầu bằng câu hỏi “trường này là string hay number?”. Hãy hỏi “giá trị này mô tả điều gì trong nghiệp vụ?”.

| Khái niệm | Ví dụ trong resource | Biểu diễn JSON gợi ý | Kiểu Java phù hợp |
| --- | --- | --- | --- |
| Một thời điểm trên dòng thời gian | Lúc server nhận phép đo | `"2026-11-17T02:00:00.123Z"` | `Instant` |
| Ngày theo lịch, không có giờ | Ngày sinh, ngày nghỉ | `"2000-05-20"` | `LocalDate` |
| Giờ trên đồng hồ, chưa gắn ngày | Giờ mở cửa | `"08:30:00"` | `LocalTime` |
| Ngày giờ địa phương chưa xác định offset | Giờ người dùng chọn cho lịch hẹn | `"2026-11-20T09:00:00"` | `LocalDateTime` |
| Ngày giờ kèm độ lệch UTC | Dữ liệu nhận từ đối tác | `"2026-11-17T09:00:00+07:00"` | `OffsetDateTime` |
| Ngày giờ gắn quy tắc múi giờ | Lịch diễn ra tại một địa điểm | Ngày giờ địa phương và `timeZone` | `ZonedDateTime`, `ZoneId` |
| Độ dài thời gian | Timeout, thời lượng xử lý | `1500` trong trường `timeoutMs` | `Duration` |
| Khoảng theo lịch | Gia hạn một tháng | `{"months": 1}` theo hợp đồng riêng | `Period` |

Các kiểu này diễn đạt những khái niệm khác nhau trong [API `java.time`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html). Chọn đúng kiểu giúp ngăn việc dùng ngày sinh như một timestamp hoặc dùng giờ địa phương như thời điểm tuyệt đối.

### 2.1. Ngày sinh không phải nửa đêm UTC

Với ngày sinh, biểu diễn phù hợp là:

```json
{
  "birthDate": "2000-05-20"
}
```

Nếu đổi thành `2000-05-20T00:00:00Z`, client ở một offset âm có thể hiển thị ngày trước đó. Sai lệch xuất hiện vì API đã biến một ngày theo lịch thành một thời điểm. Đừng thêm giờ và múi giờ vào dữ liệu vốn không có những ý nghĩa đó.

Ngược lại, `createdAt`, `receivedAt` hoặc `paidAt` thường cần một thời điểm tuyệt đối để các hệ thống đối chiếu sự kiện.

### 2.2. Thời điểm xảy ra và thời điểm ghi nhận là hai trường khác nhau

Thiết bị có thể mất kết nối rồi gửi dữ liệu muộn:

```json
{
  "measuredAt": "2026-11-17T02:00:00.000Z",
  "receivedAt": "2026-11-17T02:05:10.000Z"
}
```

`measuredAt` do thiết bị khai báo; `receivedAt` do server cấp khi tiếp nhận. Thời gian từ client cần kiểm tra theo chính sách độ trễ và sai lệch đồng hồ. Nó không tự trở thành bằng chứng đáng tin chỉ vì có định dạng chuẩn.

Nếu nghiệp vụ yêu cầu thứ tự tiếp nhận chính xác, cần thêm cơ chế thứ tự hoặc phiên bản do server quản lý. Hai sự kiện có thể có cùng timestamp; đồng hồ của hai máy cũng có thể lệch nhau.

## 3. UTC, offset và múi giờ

### 3.1. Hai chuỗi khác nhau có thể cùng một thời điểm

Hai giá trị sau tương đương về thời điểm:

```text
2026-11-17T09:00:00+07:00
2026-11-17T02:00:00Z
```

`+07:00` diễn đạt độ lệch so với UTC; đổi sang UTC phải trừ bảy giờ. Không được chỉ xóa phần offset rồi gắn chữ `Z` vào chuỗi cũ.

```java
import java.time.Instant;
import java.time.OffsetDateTime;

OffsetDateTime supplied =
        OffsetDateTime.parse("2026-11-17T09:00:00+07:00");
Instant instant = supplied.toInstant();

System.out.println(instant); // 2026-11-17T02:00:00Z
```

Với trường biểu diễn một sự kiện đã xảy ra, API có thể nhận offset hợp lệ rồi trả kết quả chuẩn hóa về UTC. Nếu offset ban đầu có giá trị nghiệp vụ hoặc cần phục vụ truy vết, hãy lưu nó trong trường riêng theo hợp đồng.

### 3.2. Offset không chứa quy tắc múi giờ

`+07:00` là một độ lệch. `Asia/Ho_Chi_Minh` là mã múi giờ chứa quy tắc chuyển đổi giữa giờ địa phương và thời điểm. Một offset riêng lẻ không mô tả lịch sử hoặc quy tắc thay đổi giờ theo mùa của một vùng.

Ví dụ lịch hẹn:

```json
{
  "localStart": "2026-11-20T09:00:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
```

Cặp dữ liệu này thể hiện ý định “9 giờ tại địa điểm đã chọn”. Khi xử lý, server tra quy tắc của `timeZone` để xác định thời điểm tương ứng. Đừng suy múi giờ từ ngôn ngữ giao diện, địa chỉ IP hay múi giờ mặc định của JVM.

Tránh các tên viết tắt như `CST` trong hợp đồng công khai vì chúng có thể gây nhầm lẫn. Dùng mã vùng được hệ thống hỗ trợ và kiểm tra giá trị tại biên API.

### 3.3. Lịch hẹn tương lai cần chính sách khi quy tắc thay đổi

Hai nhu cầu sau khác nhau:

- Một sự kiện toàn cầu đã được chốt thời điểm: giữ nguyên `Instant`, thay đổi cách hiển thị theo múi giờ người xem.
- Một lịch diễn ra lúc 9 giờ địa phương: giữ giờ địa phương và mã múi giờ làm ý định chính; xác định cách tính lại thời điểm nếu quy tắc múi giờ thay đổi.

Với lịch lặp, cần lưu cả quy tắc lặp, múi giờ và chính sách giải quyết giờ không tồn tại hoặc bị lặp. Lưu duy nhất offset của lần đầu tiên không đủ để tính các lần sau. Hệ thống có thể lưu thêm thời điểm đã tính để tìm kiếm, nhưng phải nêu rõ giá trị nào là nguồn sự thật.

### 3.4. Một giờ địa phương có thể không ánh xạ duy nhất

Ở vùng có thay đổi giờ theo mùa, một giờ trên đồng hồ có thể:

- Ánh xạ đến một thời điểm duy nhất trong trường hợp bình thường.
- Không tồn tại khi đồng hồ chuyển tiến qua một khoảng giờ.
- Xuất hiện hai lần khi đồng hồ được chuyển lùi.

Không nên để mặc định của thư viện quyết định thay cho hợp đồng đặt lịch. Ví dụ, API có thể từ chối giờ không tồn tại và yêu cầu client chọn offset khi giờ bị lặp.

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public final class ScheduleResolver {
    private ScheduleResolver() {}

    public static Instant resolve(
            LocalDateTime local,
            String timeZone,
            ZoneOffset chosenOffset) {

        ZoneId zone = ZoneId.of(timeZone);
        List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException("LOCAL_TIME_DOES_NOT_EXIST");
        }
        if (chosenOffset != null && !valid.contains(chosenOffset)) {
            throw new IllegalArgumentException("OFFSET_NOT_VALID_FOR_ZONE");
        }
        if (valid.size() > 1 && chosenOffset == null) {
            throw new IllegalArgumentException("AMBIGUOUS_LOCAL_TIME");
        }

        ZoneOffset resolved = chosenOffset != null
                ? chosenOffset
                : valid.get(0);
        return local.toInstant(resolved);
    }
}
```

Phương thức `getValidOffsets` cho phép phân biệt các trường hợp này; xem [tài liệu `ZoneRules`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime)). Ví dụ giả định `local` và `timeZone` đã qua kiểm tra bắt buộc; mã múi giờ không hợp lệ cũng phải được chuyển thành lỗi đầu vào, thay vì lỗi `500`.

## 4. Chọn định dạng truyền trên HTTP

### 4.1. Dùng một tập quy tắc cụ thể

[RFC 3339](https://www.rfc-editor.org/rfc/rfc3339.html#section-5.6) mô tả định dạng timestamp cho giao tiếp Internet, là một profile của ISO 8601. Với trường biểu diễn thời điểm, dạng quen thuộc là ngày, chữ `T`, giờ và offset hoặc `Z`.

Đừng chỉ ghi “theo ISO 8601” rồi để mỗi client chọn một cách khác nhau. Hãy quy định dạng được nhận và dạng được trả về. Trong bài này, API phép đo sử dụng chính sách riêng sau:

| Thuộc tính | Quy định của API ví dụ |
| --- | --- |
| Dữ liệu đầu vào | Chuỗi ngày giờ có giây, chữ `T` hoa, có `Z` hoa hoặc offset `±HH:mm` |
| Phần lẻ của giây | Không có hoặc có từ một đến ba chữ số |
| Dữ liệu đầu ra | UTC, luôn có đúng ba chữ số mili giây, kết thúc bằng `Z` |
| Năm | Bốn chữ số; năm đầu vào và năm sau chuẩn hóa đều trong `0000`–`9999` |
| Giá trị không nhận | Giờ địa phương thiếu offset, offset `-00:00`, giây nhuận `:60`, chuỗi rỗng |
| Ngày giờ không tồn tại | Từ chối, không tự chỉnh sang ngày giờ kế tiếp |

Đây là tập đầu vào mà API lựa chọn hỗ trợ, không phải tuyên bố rằng mọi biểu diễn nằm ngoài bảng đều sai theo mọi chuẩn ngày giờ. Việc giới hạn rõ giúp các thư viện phía client và server có hành vi có thể dự đoán.

```json
{
  "acceptedInput": "2026-11-17T09:00:00.12+07:00",
  "canonicalOutput": "2026-11-17T02:00:00.120Z"
}
```

Định dạng dễ đọc theo vùng như `17/11/2026 09:00` phù hợp với giao diện người dùng. Không dùng nó làm dạng truyền mặc định giữa các dịch vụ.

### 4.2. Độ chính xác là một phần của hợp đồng

Nếu client gửi nano giây nhưng database chỉ giữ mili giây, hệ thống phải chọn một chính sách: từ chối, cắt bớt hoặc làm tròn. Chính sách phải được công bố và áp dụng ở một điểm thống nhất.

API ví dụ từ chối đầu vào có hơn ba chữ số phần lẻ, kể cả khi các chữ số thừa đều bằng không. Với thời gian do server sinh, server cắt phần nhỏ hơn mili giây trước khi lưu và trả về. Nhờ đó, biểu diễn phản ánh đúng dữ liệu đã lưu.

Không trả chín chữ số phần lẻ rồi âm thầm chỉ lưu ba chữ số. Client có thể dùng giá trị vừa nhận để so sánh, tạo bộ lọc hoặc ký dữ liệu và gặp kết quả không ổn định.

### 4.3. Epoch phải công bố đơn vị và mốc

Nếu hệ thống chọn số thay cho chuỗi ngày giờ, hãy đặt tên và mô tả rõ:

```json
{
  "occurredAtEpochMs": 1700000000000,
  "timeoutMs": 1500
}
```

Hai số có ý nghĩa khác nhau: trường đầu là số mili giây tính từ mốc Unix epoch; trường sau là độ dài chờ. Không dùng chung mô tả “time in milliseconds” cho cả hai.

Đơn vị giây và mili giây khác nhau một nghìn lần. Không tự đoán đơn vị dựa vào số chữ số. Với hệ sinh thái JavaScript, số nguyên vượt `2^53 - 1` không còn được biểu diễn chính xác bằng kiểu `Number`; epoch nano giây hiện đại thường vượt giới hạn này. Nếu cần truyền số nguyên lớn, cân nhắc chuỗi thập phân và công bố cách parse.

Timestamp dùng số không tự giải quyết được bài toán múi giờ, độ tin cậy của đồng hồ hoặc tính duy nhất của sự kiện.

### 4.4. Timestamp trong JSON khác HTTP-date

HTTP có cú pháp ngày giờ riêng cho các header sử dụng `HTTP-date`. Ví dụ:

```http
Last-Modified: Tue, 17 Nov 2026 02:00:00 GMT
```

Không đưa trực tiếp chuỗi RFC 3339 của JSON vào `Last-Modified`. `Retry-After` có thể là ngày giờ HTTP hoặc số giây trì hoãn; hãy mô tả đúng cách API sử dụng. Những quy định này nằm trong [RFC 9110 về định dạng ngày giờ](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6.7) và [`Retry-After`](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).

## 5. Phân biệt độ dài thời gian và khoảng theo lịch

### 5.1. Timeout không phải ngày giờ

Một timeout 1.500 mili giây là độ dài thời gian. Nó không cần múi giờ:

```json
{
  "timeoutMs": 1500,
  "retention": "PT15M"
}
```

`PT15M` ở đây được hợp đồng định nghĩa là 15 phút. Nếu chọn chuỗi duration, hãy nói rõ các thành phần được hỗ trợ, có cho phép số âm không và giới hạn lớn nhất. Không nhận mọi kiểu khoảng ISO 8601 chỉ vì ví dụ đơn giản parse được.

Một số nguyên có hậu tố đơn vị thường dễ dùng cho timeout. Một chuỗi duration có thể dễ đọc khi cần nhiều mức thời lượng. Chọn một biểu diễn nhất quán cho từng trường.

### 5.2. Hai mươi bốn giờ và một ngày theo lịch có thể khác nhau

```java
import java.time.Duration;
import java.time.Period;
import java.time.ZonedDateTime;

ZonedDateTime afterElapsedTime = start.plus(Duration.ofHours(24));
ZonedDateTime afterCalendarDay = start.plus(Period.ofDays(1));
```

Đoạn mã giả định biến `start` là một `ZonedDateTime`. Phép cộng đầu thể hiện 24 giờ trôi qua; phép cộng sau thể hiện thêm một ngày theo lịch tại vùng đó. Khi đi qua lần chuyển giờ, hai kết quả có thể khác nhau. Java cũng quy định một ngày trong [`Duration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html) là 24 giờ.

Tương tự, “một tháng” không phải số giây cố định. Với gia hạn vào cuối tháng, cần xác định ngày đích khi tháng tiếp theo không có ngày tương ứng. Đây là quy tắc nghiệp vụ phải được mô tả, không nên phát sinh ngẫu nhiên từ phép chuyển đổi sang giây.

Để đo thời gian thực thi trong một tiến trình, dùng nguồn thời gian đơn điệu như `System.nanoTime()` và lấy chênh lệch. Không đưa giá trị `nanoTime()` ra API như một timestamp; nó không có mốc lịch dùng chung giữa các hệ thống.

## 6. Bộ lọc thời gian và phân trang

### 6.1. Dùng khoảng nửa mở để nối các khoảng liền nhau

Với collection resource, có thể thiết kế:

```http
GET /parcel-measurements?from=2026-11-17T00%3A00%3A00Z&to=2026-11-18T00%3A00%3A00Z
```

Quy ước `from <= measuredAt < to`, viết gọn là `[from, to)`. Một bản ghi đúng tại `to` thuộc khoảng tiếp theo. Nhờ vậy, các khoảng liên tiếp không bị trùng bản ghi tại ranh giới.

Trong truy vấn dữ liệu, ý tưởng là:

```sql
WHERE measured_at >= :from
  AND measured_at < :to
```

Hợp đồng phải nói rõ đang lọc theo `measuredAt` hay `receivedAt`, có bắt buộc cả hai tham số không, khoảng tối đa là bao lâu và lỗi khi `from >= to`. Đừng dùng tên `date` cho một bộ lọc thực chất cần hai thời điểm.

Khi đặt offset có dấu cộng trong query, hãy để thư viện URI mã hóa giá trị; dấu `+` cần được truyền thành `%2B` nếu bộ giải mã query có quy tắc coi `+` là dấu cách.

### 6.2. “Dữ liệu của một ngày” cần múi giờ nghiệp vụ

Muốn lấy dữ liệu ngày `2026-11-17` theo `Asia/Ho_Chi_Minh`, hãy xác định đầu ngày đó và đầu ngày tiếp theo theo múi giờ đã chọn, rồi đổi hai mốc sang `Instant`.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate day = LocalDate.parse("2026-11-17");
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = day.atStartOfDay(businessZone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(businessZone).toInstant();
```

Với ví dụ này, khoảng tương ứng là từ `2026-11-16T17:00:00Z` đến trước `2026-11-17T17:00:00Z`. Với vùng có chuyển giờ, không nên mặc định mọi ngày đều dài 24 giờ. `atStartOfDay` chọn thời điểm hợp lệ đầu ngày theo quy tắc vùng; nếu nghiệp vụ đòi hỏi xử lý khác ở ngày có chuyển đổi đặc biệt, cần quy định riêng.

Tránh cách ghép `23:59:59.999` làm cuối ngày. Cách đó gắn logic nghiệp vụ vào độ chính xác lưu trữ và dễ bỏ sót dữ liệu khi hệ thống tăng độ phân giải.

### 6.3. Timestamp không phải khóa phân trang duy nhất

Nếu nhiều phép đo có cùng `receivedAt`, chỉ dùng điều kiện `receivedAt > lastSeenTime` sẽ bỏ qua một số bản ghi bằng mốc cuối trang trước. Một thứ tự như `(receivedAt, id)` giúp phân biệt các bản ghi cùng timestamp:

```sql
ORDER BY received_at ASC, id ASC
```

Cursor phải mang đủ thông tin để tiếp tục theo cùng thứ tự. Cơ chế này còn cần chính sách khi dữ liệu được chèn muộn hoặc bị cập nhật trong lúc phân trang. Thứ tự ổn định không tự tạo snapshot của collection.

## 7. Biểu diễn đơn vị đo

### 7.1. Không để một con số đứng một mình

Biểu diễn mơ hồ:

```json
{
  "mass": 1500,
  "length": 30,
  "temperature": 25
}
```

Hai thiết kế thường dùng là đặt đơn vị trong tên trường hoặc đặt giá trị và đơn vị trong cùng object.

| Thiết kế | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| Đơn vị cố định trong tên | `"massG": 1500` | API chỉ có một đơn vị, cần dữ liệu gọn |
| Object đại lượng | `"mass": {"value": "1.500", "unit": "kg"}` | Cần đơn vị tường minh hoặc hỗ trợ chuyển đổi |

Đơn vị cố định vẫn phải được mô tả trong schema. Với object đại lượng, bắt buộc cả `value` và `unit`; không tự lấy đơn vị từ sở thích cá nhân của người dùng.

### 7.2. Dùng mã đơn vị, tách khỏi nhãn hiển thị

API có thể quy định `kg`, `g`, `mm` và `ms` là các mã được chấp nhận, có phân biệt hoa thường. Giao diện tự hiển thị “kilôgam”, “gam” hoặc nhãn dịch tương ứng. Không dùng chuỗi `"1,5 kg"` làm dữ liệu số cần tính toán.

Các mã trong ví dụ là enum do API định nghĩa. Nếu hệ thống áp dụng một bộ mã chuẩn bên ngoài, cần nêu tên bộ mã, phiên bản và phạm vi hỗ trợ; đừng gọi một tập enum tự đặt là chuẩn quốc tế.

Nếu hai đơn vị mô tả hai loại đại lượng khác nhau, không được chuyển đổi chỉ bằng một bảng hệ số chung. Chuyển gam sang kilôgam khác với chuyển lít sang kilôgam; trường hợp thứ hai còn cần ngữ cảnh như khối lượng riêng.

### 7.3. Chọn đơn vị chuẩn hóa cho lưu trữ và response

Giả sử API nhận `g` hoặc `kg` và luôn trả `kg`:

```json
{
  "input": {"value": "1500", "unit": "g"},
  "output": {"value": "1.500", "unit": "kg"}
}
```

Hợp đồng phải công bố việc chuẩn hóa, miền giá trị và sai số chấp nhận được. Nếu cần lưu giá trị nguyên gốc do thiết bị báo về, lưu riêng; đừng ghi đè ý nghĩa của trường chuẩn hóa.

Tránh trả hai trường `massKg` và `massG` có thể được cập nhật độc lập. Hai giá trị cùng mô tả một đại lượng rất dễ mất đồng bộ. Nếu cần nhiều cách biểu diễn, nên có một giá trị nguồn và những giá trị dẫn xuất do server tính.

### 7.4. Một số phép chuyển đổi cần quy tắc riêng

| Tình huống | Điều cần ghi rõ |
| --- | --- |
| Mili giây và giây | Hệ số chuyển đổi và chính sách khi không chia hết |
| Kilôgam và gam | Độ phân giải, giới hạn nhỏ nhất/lớn nhất và số chữ số phần lẻ |
| Độ C và kelvin | Có thành phần cộng lệch mốc, không chỉ nhân hệ số |
| `MB` và `MiB` | Nếu hỗ trợ, nêu rõ `MB = 1.000.000 byte`, `MiB = 1.048.576 byte` |
| Tỉ lệ và phần trăm | `0.15` là tỉ lệ 15%; `15` có thể là số phần trăm nếu schema quy định |
| Độ chính xác đo và số chữ số hiển thị | Ba chữ số phần lẻ không chứng minh thiết bị đo chính xác đến mức đó |

Tên trường như `progressRatio` hoặc `progressPercent` giúp giảm nhầm lẫn. Miền giá trị của chúng cũng khác nhau, chẳng hạn `[0, 1]` và `[0, 100]` nếu nghiệp vụ định nghĩa tiến độ trong các khoảng này.

### 7.5. Số thập phân và chính sách làm tròn

Hệ thống có thể chọn số nguyên theo đơn vị nhỏ nhất, JSON number hoặc chuỗi thập phân. Chọn theo độ chính xác cần giữ và khả năng của client.

Ví dụ dưới đây dùng chuỗi để giữ biểu diễn thập phân và công bố rằng `value` là chuỗi số, không phải JSON number:

```json
{
  "mass": {
    "value": "1.500",
    "unit": "kg"
  }
}
```

Quy tắc ví dụ: dấu thập phân là dấu chấm, không có dấu phân cách hàng nghìn, không dùng dạng số mũ, không nhận số âm hoặc bằng không, tối đa ba chữ số phần lẻ ở đầu vào. Sau chuyển đổi, khối lượng phải biểu diễn chính xác tới `0.001 kg` và không vượt `1000.000 kg`.

Trong Java, khởi tạo `BigDecimal` từ chuỗi khi cần giữ giá trị thập phân chính xác. `new BigDecimal(0.1)` bắt đầu từ một số nhị phân gần đúng. Khi thay đổi scale, hãy chọn rõ làm tròn hay từ chối; API ví dụ chọn từ chối nếu phải mất thông tin.

Không dùng số `0` làm ký hiệu “không đo được” nếu `0` là giá trị hợp lệ của đại lượng. Nếu cho phép thiếu hoặc chưa biết, mô tả rõ sự khác nhau giữa thiếu field và `null`. JSON cũng không có các literal số `NaN` hay `Infinity` hợp lệ để thay cho trạng thái lỗi.

## 8. Hợp đồng REST hoàn chỉnh cho một phép đo

Giả sử resource `/parcel-measurements` lưu phép cân kiện hàng. Request gồm thời điểm đo và khối lượng; server cấp định danh và thời điểm nhận.

```http
POST /parcel-measurements HTTP/1.1
Content-Type: application/json

{
  "measuredAt": "2026-11-17T09:00:00.12+07:00",
  "mass": {
    "value": "1500",
    "unit": "g"
  }
}
```

Response minh họa:

```http
HTTP/1.1 201 Created
Location: /parcel-measurements/pm-42
Content-Type: application/json

{
  "id": "pm-42",
  "measuredAt": "2026-11-17T02:00:00.120Z",
  "receivedAt": "2026-11-17T02:00:01.456Z",
  "mass": {
    "value": "1.500",
    "unit": "kg"
  }
}
```

Các quyết định cần được ghi thành hợp đồng:

1. `measuredAt` là thời điểm từ nguồn đo; `receivedAt` do server quản lý.
2. Server chuẩn hóa timestamp về UTC với mili giây và khối lượng về kilôgam với ba chữ số phần lẻ.
3. `id` và `receivedAt` không phải dữ liệu mà client được tự đặt trong request tạo mới.
4. Ngoài kiểm tra định dạng, server kiểm tra chính sách dữ liệu quá cũ hoặc đi trước đồng hồ server; ngưỡng cụ thể do nghiệp vụ quyết định.
5. Xác thực và phân quyền quyết định ai được gửi phép đo cho kiện hàng nào. Một payload có thời gian và đơn vị hợp lệ chưa chứng minh người gửi có quyền ghi dữ liệu.

Không cần đưa mọi bài toán HTTP vào cùng một DTO. Hãy giữ payload phản ánh resource; đặt quy tắc xác thực, phân quyền và xử lý lỗi ở đúng lớp chịu trách nhiệm.

### 8.1. Lỗi cần giúp client sửa đúng dữ liệu

Một chính sách có thể là `400 Bad Request` khi dữ liệu không phù hợp kiểu hoặc định dạng API yêu cầu, `422 Unprocessable Content` khi request đã được hiểu nhưng giá trị vi phạm quy tắc nghiệp vụ. Cách phân loại phải nhất quán với hợp đồng chung của API, không phụ thuộc ngẫu nhiên vào nơi exception phát sinh. Ý nghĩa các mã được mô tả trong [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5).

Ví dụ dưới đây thể hiện lỗi độ phân giải sau khi chuyển đổi: `1.5 g` bằng `0.0015 kg`, không thể giữ nguyên ở độ phân giải `0.001 kg`.

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/json

{
  "code": "MASS_RESOLUTION_NOT_SUPPORTED",
  "message": "Khối lượng phải biểu diễn chính xác tới 0.001 kg.",
  "errors": [
    {
      "field": "mass.value",
      "code": "RESOLUTION_EXCEEDED"
    }
  ]
}
```

Mã lỗi ổn định giúp client xử lý tự động; thông điệp có thể được bản địa hóa. Không trả lỗi kiểu “invalid data” cho mọi trường hợp thiếu offset, sai mã đơn vị và vượt giới hạn.

### 8.2. Idempotency và cache phụ thuộc biểu diễn

`1.500 kg` và `1500 g` có thể cùng nghĩa; hai timestamp với offset khác nhau cũng có thể cùng thời điểm. Nếu API dùng khóa idempotency, phải định nghĩa cách xác định request có cùng nội dung: so byte nguyên bản hay so dữ liệu đã chuẩn hóa. Nếu so theo nghĩa, cần parse, validate và chuẩn hóa trước khi so sánh.

Không dùng riêng timestamp hoặc khối lượng làm khóa idempotency. Hai phép đo hợp lệ có thể có cùng giá trị. Khóa idempotency vẫn cần cơ chế quản lý độc lập theo chính sách của endpoint.

Với cache, biểu diễn chuẩn hóa giúp tránh khác biệt không cần thiết giữa các response. Nếu response thay đổi theo múi giờ hoặc hệ đơn vị mà client chọn, URL hoặc cơ chế phân biệt cache phải thể hiện lựa chọn đó. Không tùy ý thay đổi JSON của cùng một cache key theo múi giờ của máy chạy server.

`updatedAt` có độ chính xác mili giây cũng không đảm bảo mỗi lần cập nhật có một giá trị khác nhau. Khi cần kiểm soát cập nhật đồng thời, dùng phiên bản hoặc ETag được thiết kế cho mục đích đó.

## 9. Mô tả trong OpenAPI

Đoạn sau là phần `components` để ghép vào một tài liệu OpenAPI 3.1; nó không phải một tài liệu OpenAPI hoàn chỉnh. Schema tách request khỏi response vì hướng ghi và hướng đọc có thể có đơn vị, độ chính xác khác nhau.

```yaml
components:
  schemas:
    MeasurementTimestampInput:
      type: string
      format: date-time
      maxLength: 29
      pattern: '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,3})?(Z|[+-][0-9]{2}:[0-9]{2})$'
      description: >-
        Thời điểm có offset; chữ T/Z hoa; phần lẻ tối đa 3 chữ số.
        Không nhận -00:00 hoặc giây nhuận. Ngày giờ phải tồn tại;
        năm trước và sau chuẩn hóa UTC nằm trong 0000-9999.
      examples:
        - '2026-11-17T09:00:00.12+07:00'

    CanonicalTimestamp:
      type: string
      format: date-time
      pattern: '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$'
      description: Thời điểm UTC có đúng 3 chữ số mili giây.
      examples:
        - '2026-11-17T02:00:00.120Z'

    MassInput:
      type: object
      additionalProperties: false
      required: [value, unit]
      properties:
        value:
          type: string
          maxLength: 20
          pattern: '^(0|[1-9][0-9]*)(\.[0-9]{1,3})?$'
          description: >-
            Chuỗi thập phân dương; không số mũ, không dấu phân nhóm.
            Sau chuyển đổi phải trong (0, 1000] kg và biểu diễn chính xác
            tới 0.001 kg. Giá trị 0 không hợp lệ về nghiệp vụ.
          examples: ['1500']
        unit:
          type: string
          enum: [g, kg]

    CanonicalMass:
      type: object
      additionalProperties: false
      required: [value, unit]
      properties:
        value:
          type: string
          pattern: '^(0|[1-9][0-9]*)\.[0-9]{3}$'
          description: Khối lượng trong (0, 1000] kg, đúng 3 chữ số phần lẻ.
          examples: ['1.500']
        unit:
          type: string
          enum: [kg]

    ParcelMeasurementRequest:
      type: object
      additionalProperties: false
      required: [measuredAt, mass]
      properties:
        measuredAt:
          $ref: '#/components/schemas/MeasurementTimestampInput'
        mass:
          $ref: '#/components/schemas/MassInput'

    ParcelMeasurementResponse:
      type: object
      additionalProperties: false
      required: [id, measuredAt, receivedAt, mass]
      properties:
        id:
          type: string
        measuredAt:
          $ref: '#/components/schemas/CanonicalTimestamp'
        receivedAt:
          $ref: '#/components/schemas/CanonicalTimestamp'
        mass:
          $ref: '#/components/schemas/CanonicalMass'
```

`format` và `pattern` giúp diễn đạt hợp đồng nhưng không thay thế toàn bộ validation. Pattern về hình dạng không biết tháng hai có bao nhiêu ngày, còn quy tắc chuyển đổi đơn vị hoặc so sánh thời gian cần xử lý riêng. Các công cụ cũng có thể hỗ trợ kiểm tra `format` khác nhau; server vẫn phải tự bảo đảm ràng buộc. Xem [OpenAPI 3.1.1: Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object).

Vì `value` là string, không gắn `minimum` hoặc `maximum` như thể nó là JSON number rồi trông chờ mọi validator hiểu giới hạn số. Ví dụ này mô tả giới hạn trong schema và kiểm tra chúng trong mã nghiệp vụ.

## 10. Triển khai quy tắc biên bằng Java

### 10.1. Parse timestamp và chuẩn hóa số đo

Lớp dưới đây minh họa các quy tắc định dạng và chuẩn hóa của hợp đồng vừa thiết kế. Nó dùng JDK 17 trở lên, không phụ thuộc múi giờ mặc định của máy.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.regex.Pattern;

public final class MeasurementValues {
    private static final Pattern TIMESTAMP_INPUT = Pattern.compile(
            "[0-9]{4}-[0-9]{2}-[0-9]{2}T"
            + "[0-9]{2}:[0-9]{2}:[0-9]{2}"
            + "(?:\\.[0-9]{1,3})?(?:Z|[+-][0-9]{2}:[0-9]{2})");

    private static final Pattern DECIMAL_INPUT = Pattern.compile(
            "(?:0|[1-9][0-9]*)(?:\\.[0-9]{1,3})?");

    private static final DateTimeFormatter UTC_MILLIS =
            new DateTimeFormatterBuilder().appendInstant(3).toFormatter();

    private static final BigDecimal MAX_MASS_KG =
            new BigDecimal("1000.000");

    private MeasurementValues() {}

    public static Instant parseTimestamp(String raw) {
        if (raw == null || raw.length() > 29
                || !TIMESTAMP_INPUT.matcher(raw).matches()
                || raw.endsWith("-00:00")) {
            throw new IllegalArgumentException("INVALID_TIMESTAMP_FORMAT");
        }

        try {
            // Parser kiểm tra ngày, giờ và offset thực sự hợp lệ.
            OffsetDateTime parsed = OffsetDateTime.parse(raw);
            Instant result = parsed.toInstant();
            requireFourDigitUtcYear(result);
            return result;
        } catch (DateTimeException ex) {
            throw new IllegalArgumentException("INVALID_TIMESTAMP_VALUE", ex);
        }
    }

    public static String formatTimestamp(Instant value) {
        requireFourDigitUtcYear(value);
        if (value.getNano() % 1_000_000 != 0) {
            throw new IllegalArgumentException("TIMESTAMP_NOT_MILLI_ALIGNED");
        }
        return UTC_MILLIS.format(value);
    }

    private static void requireFourDigitUtcYear(Instant value) {
        int year = value.atOffset(ZoneOffset.UTC).getYear();
        if (year < 0 || year > 9999) {
            throw new IllegalArgumentException("TIMESTAMP_OUT_OF_RANGE");
        }
    }

    public static BigDecimal massKg(String raw, String unit) {
        if (raw == null || raw.length() > 20
                || !DECIMAL_INPUT.matcher(raw).matches()) {
            throw new IllegalArgumentException("INVALID_MASS_FORMAT");
        }
        if (unit == null) {
            throw new IllegalArgumentException("MASS_UNIT_REQUIRED");
        }

        BigDecimal value = new BigDecimal(raw);
        BigDecimal kg = switch (unit) {
            case "kg" -> value;
            case "g" -> value.movePointLeft(3);
            default -> throw new IllegalArgumentException("UNSUPPORTED_MASS_UNIT");
        };

        if (kg.signum() <= 0 || kg.compareTo(MAX_MASS_KG) > 0) {
            throw new IllegalArgumentException("MASS_OUT_OF_RANGE");
        }
        try {
            return kg.setScale(3, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException("MASS_RESOLUTION_NOT_SUPPORTED", ex);
        }
    }
}
```

Ví dụ sử dụng:

```java
Instant measuredAt = MeasurementValues.parseTimestamp(
        "2026-11-17T09:00:00.12+07:00");
String wireTime = MeasurementValues.formatTimestamp(measuredAt);
String wireMass = MeasurementValues.massKg("1500", "g").toPlainString();

// wireTime = "2026-11-17T02:00:00.120Z"
// wireMass = "1.500"
```

Lớp tiện ích không kiểm tra quan hệ giữa `measuredAt` và thời gian hiện tại; đó là chính sách nghiệp vụ cần nguồn thời gian được truyền vào. Các mã lỗi cũng cần được lớp xử lý HTTP ánh xạ sang response phù hợp, không để `IllegalArgumentException` tự biến thành lỗi máy chủ.

Khi cần formatter tùy chỉnh, đừng dùng nhầm `YYYY` cho năm dương lịch: `Y` trong Java là năm theo tuần, còn `u` là năm; ký hiệu này có thể gây lỗi quanh đầu hoặc cuối năm. Các ý nghĩa pattern và formatter chuẩn được mô tả trong [tài liệu `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).

### 10.2. Đưa nguồn thời gian vào service

```java
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public final class MeasurementClock {
    private final Clock clock;

    public MeasurementClock(Clock clock) {
        this.clock = clock;
    }

    public Instant receivedAt() {
        return clock.instant().truncatedTo(ChronoUnit.MILLIS);
    }
}
```

Trong cấu hình ứng dụng có thể cung cấp `Clock.systemUTC()`; trong kiểm thử cung cấp `Clock.fixed(...)`. Server cắt thời gian nhận tới mili giây trước khi lưu. Việc truyền `Clock` giúp kiểm tra quy tắc “không quá xa trong tương lai” mà không phụ thuộc thời điểm chạy bài kiểm thử.

Trong ứng dụng Spring, DTO đầu vào có thể giữ các trường chuỗi như hợp đồng trên. Luồng xử lý nên là: kiểm tra cấu trúc request, parse và chuẩn hóa, kiểm tra nghiệp vụ/quyền truy cập, lưu resource, rồi tạo DTO response. Nếu dùng serializer tự động cho `java.time`, cần cấu hình và xác nhận JSON thực tế đúng độ chính xác, dạng UTC và cách biểu diễn đã công bố.

### 10.3. Kiểu dữ liệu ở database cũng phải giữ đúng ý nghĩa

Không mặc định tên cột có chữ `timestamp` là đủ. Cần xác định kiểu cột, cách driver ánh xạ, ảnh hưởng của múi giờ session và độ chính xác thực sự được giữ lại. Một kiểu có tên “with time zone” cũng không nhất thiết lưu lại mã vùng gốc mà người dùng gửi.

Với thời điểm sự kiện, mục tiêu là đọc ra cùng một `Instant` đã lưu. Với lịch theo giờ địa phương, cần giữ thêm local date-time và mã vùng nếu chúng là nguồn sự thật. Với số đo, cột thập phân phải có miền giá trị và scale đủ cho đơn vị chuẩn hóa.

Tính nhất quán phải đi xuyên qua request, mã ứng dụng, driver, database và response. Cấu hình múi giờ của một lớp không tự bảo đảm các lớp còn lại đúng.

## 11. Tình huống cần kiểm thử khi hiện thực API

Bảng dưới là gợi ý kiểm thử cho người triển khai, không phải các bài Quiz hay Interview riêng.

| Nhóm | Đầu vào hoặc tình huống | Kỳ vọng |
| --- | --- | --- |
| Cùng thời điểm | `09:00:00+07:00` và `02:00:00Z` cùng ngày | Parse ra cùng `Instant` |
| Chuẩn hóa | Phần lẻ `.12` | Response có `.120Z` sau đổi UTC |
| Thiếu offset | `2026-11-17T09:00:00` | Lỗi định dạng |
| Ngày không tồn tại | `2026-02-30T00:00:00Z` | Lỗi giá trị, không tự sửa |
| Vượt precision | Phần lẻ `.1234` hoặc `.1230` | Từ chối theo hợp đồng đầu vào |
| Biên năm | Offset làm UTC vượt miền bốn chữ số | Từ chối theo giới hạn đã công bố |
| Múi giờ | Giờ địa phương bị lặp hoặc không tồn tại | Áp dụng chính sách đặt lịch đã mô tả |
| Khoảng thời gian | Bản ghi đúng tại `from` hoặc `to` | Có tại `from`, không có tại `to` |
| Ngày nghiệp vụ | Ngày đi qua lần chuyển giờ | Hai mốc lấy theo múi giờ nghiệp vụ |
| Phân trang | Nhiều bản ghi cùng timestamp | Cursor tiếp tục bằng khóa phụ đã chọn |
| Đơn vị | `1500 g` và `1.500 kg` | Cùng giá trị chuẩn hóa `1.500 kg` |
| Độ phân giải | `1.5 g` | Từ chối vì cần `0.0015 kg` |
| Biên khối lượng | `0`, số âm, trên `1000 kg` | Lỗi theo hợp đồng |
| Mã đơn vị | Thiếu đơn vị hoặc gửi `KG` | Từ chối, không đoán đơn vị |
| Dạng số | Chuỗi có dấu phẩy, số mũ, quá dài | Lỗi định dạng |
| Đồng hồ | Nguồn thời gian cố định | Kết quả `receivedAt` tái lập được |
| Lưu và đọc | Gửi, lưu, truy xuất resource | Thời điểm và giá trị chuẩn hóa giữ nguyên |
| Khác môi trường | Chạy với múi giờ JVM khác nhau | Hợp đồng JSON vẫn giống nhau |

Kiểm thử ở lớp HTTP nên xác nhận cả status code, field gây lỗi và JSON thực tế. Kiểm thử tích hợp với database phát hiện việc mất độ chính xác hoặc chuyển đổi giờ ngoài ý muốn mà kiểm thử hàm parse không thấy được.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `LocalDateTime` cho mọi sự kiện | Thiếu dữ kiện xác định thời điểm | Dùng `Instant` hoặc ngày giờ có offset ở biên |
| Đổi ngày sinh thành timestamp UTC | Có thể hiển thị sai ngày ở vùng khác | Dùng `LocalDate` và dạng ngày |
| Thay offset bằng chữ `Z` mà không đổi giờ | Làm sai thời điểm | Parse rồi chuyển đổi về UTC |
| Dùng offset cố định cho lịch lặp | Lịch có thể lệch giờ địa phương | Giữ mã vùng và quy tắc lịch |
| Tính cuối ngày bằng `23:59:59.999` | Phụ thuộc precision, dễ sót bản ghi | Dùng đầu ngày kế tiếp làm cận trên mở |
| Ghi epoch không có đơn vị | Client nhầm giây với mili giây | Đặt hậu tố đơn vị, mô tả mốc |
| Đổi đơn vị của field cũ mà không đổi hợp đồng | Client tính sai nhưng vẫn parse thành công | Giữ nghĩa cũ hoặc có kế hoạch chuyển phiên bản |
| Chuyển mọi số qua `double` | Có thể mất độ chính xác thập phân | Chọn biểu diễn và kiểu số theo yêu cầu |
| Tự làm tròn mà không mô tả | Client không biết dữ liệu bị thay đổi | Công bố chế độ làm tròn hoặc từ chối |
| Dùng timestamp làm khóa duy nhất | Đụng giá trị, mất bản ghi khi phân trang | Dùng định danh và thứ tự phụ rõ ràng |

Một hợp đồng tốt trả lời được bốn câu hỏi cho từng field: **giá trị có ý nghĩa gì, được biểu diễn thế nào, dùng múi giờ hoặc đơn vị nào, và server làm gì khi dữ liệu không phù hợp**. Khi những câu trả lời này nhất quán từ OpenAPI đến mã xử lý và lưu trữ, client có thể tích hợp mà không cần tự đoán.

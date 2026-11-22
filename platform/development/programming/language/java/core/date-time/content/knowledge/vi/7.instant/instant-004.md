# Đọc epoch và xử lý thời điểm trước năm 1970 với `Instant`

Trong hệ thống đặt lịch, audit, nhập dữ liệu lịch sử hoặc đồng bộ timestamp, ta có thể gặp các thời điểm trước `1970-01-01`. Các thời điểm này hoàn toàn hợp lệ. Chúng thường được biểu diễn bằng **epoch âm**, nhưng rất dễ xử lý sai nếu nhầm giây với mili giây, chia số âm theo cách làm tròn về 0 hoặc bỏ qua phần nano giây.

`Instant` trong `java.time` biểu diễn **một mốc duy nhất trên dòng thời gian**, không gắn giờ địa phương hay một `ZoneId` cụ thể. Bài này giải thích cách đọc giá trị epoch, cách `Instant` lưu thời điểm trước năm 1970, các phép chuyển `ofEpochSecond`/`ofEpochMilli`/`toEpochMilli` và rủi ro khi dùng số âm. Tất cả ví dụ được thiết kế cho Java 17 trở lên.

## 1. Mốc epoch thực sự có ý nghĩa gì?

**Unix epoch** là mốc quy ước:

~~~text
1970-01-01T00:00:00Z
~~~

Ký tự `Z` chỉ offset UTC bằng 0. Đây là **điểm gốc của hệ tọa độ thời gian**, không có nghĩa trước thời điểm này không tồn tại lịch hay sự kiện. Ta có thể biểu diễn một instant bằng khoảng cách có dấu tính từ mốc này.

- **Epoch seconds = 0:** đúng nửa đêm UTC ngày 01/01/1970.
- **Epoch seconds dương:** mốc sau epoch.
- **Epoch seconds âm:** mốc trước epoch.
- **Khoảng cách có phần lẻ:** cần thêm thành phần nano giây để mô tả chính xác.

~~~text
Trước epoch                         Epoch                      Sau epoch
... ---- -2s ---- -1s ---- -0,5s ---- 0 ---- +1s ---- +2s ---- ...
                                     ^
                              1970-01-01T00:00:00Z
~~~

Một số mốc để kiểm tra:

| Thời điểm UTC | Epoch seconds + nano | Epoch milliseconds |
| --- | --- | ---: |
| `1969-12-31T23:59:58Z` | -2 giây; 0 nano | -2000 |
| `1969-12-31T23:59:59Z` | -1 giây; 0 nano | -1000 |
| `1969-12-31T23:59:59.500Z` | -1 giây; 500000000 nano | -500 |
| `1969-12-31T23:59:59.999Z` | -1 giây; 999000000 nano | -1 |
| `1970-01-01T00:00:00Z` | 0 giây; 0 nano | 0 |
| `1970-01-01T00:00:00.001Z` | 0 giây; 1000000 nano | 1 |
| `1970-01-01T00:00:01Z` | 1 giây; 0 nano | 1000 |

Dấu âm phụ thuộc vào **instant so với epoch UTC**, không phụ thuộc việc một giao diện hiển thị năm 1969 hay 1970. Cùng một instant có thể hiển thị khác ngày tại hai offset.

## 2. `Instant` lưu giây và phần nano thế nào?

Một `Instant` chứa cặp thành phần quan trọng:

- `getEpochSecond()`: số giây có dấu kể từ epoch, theo quy tắc làm tròn xuống (**floor**) về giây nguyên bên dưới.
- `getNano()`: phần nano giây bên trong giây đó, luôn từ **0** đến **999999999**.

Quan hệ có thể viết:

~~~text
instant = epoch + epochSeconds giây + nanos nano giây
0 <= nanos <= 999_999_999
~~~

Với thời điểm **âm nửa giây**, Java biểu diễn bằng **-1 giây và +500 triệu nano giây**, vì `-1 + 0,5 = -0,5`:

~~~java
Instant halfSecondBefore = Instant.ofEpochMilli(-500);

System.out.println(halfSecondBefore.getEpochSecond()); // -1
System.out.println(halfSecondBefore.getNano());         // 500000000
System.out.println(halfSecondBefore);                   // 1969-12-31T23:59:59.500Z
~~~

Đây là **đoạn minh họa**, cần import `java.time.Instant` khi chạy độc lập. Không thể chỉ nhìn số giây `-1` rồi kết luận instant đó nằm đúng 1 giây trước epoch; phải xem cả nano giây.

Với `Instant.ofEpochMilli(-1)`, cặp thành phần chuẩn hóa lại là `(-1, 999000000)`. Phần nano **không âm** dù timestamp tổng thể âm.

## 3. Tạo và đọc epoch bằng API chuẩn

### 3.1. `Instant.EPOCH` và `parse`

~~~java
Instant epoch = Instant.EPOCH;
Instant before = Instant.parse("1969-12-31T23:59:59Z");
Instant after = Instant.parse("1970-01-01T00:00:01Z");

// epoch.getEpochSecond()  == 0
// before.getEpochSecond() == -1
// after.getEpochSecond()  == 1
~~~

`Instant.parse` dùng chuỗi theo biểu diễn instant có thông tin UTC/offset phù hợp. Một chuỗi địa phương không có offset như `1969-12-31T23:59:59` **chưa đủ thông tin để suy ra instant**. Nếu dữ liệu nguồn có offset, dùng `OffsetDateTime.parse(...).toInstant()` khi phù hợp.

### 3.2. `ofEpochSecond(long)`

~~~java
Instant a = Instant.ofEpochSecond(-2); // 1969-12-31T23:59:58Z
Instant b = Instant.ofEpochSecond(-1); // 1969-12-31T23:59:59Z
Instant c = Instant.ofEpochSecond(1);  // 1970-01-01T00:00:01Z
~~~

Tham số là **giây**. Nếu giá trị thực tế có đơn vị mili giây mà truyền vào đây, kết quả sẽ lệch theo hệ số 1000.

### 3.3. `ofEpochMilli(long)` và `toEpochMilli()`

~~~java
Instant a = Instant.ofEpochMilli(-1);
// 1969-12-31T23:59:59.999Z

Instant b = Instant.ofEpochMilli(-1000);
// 1969-12-31T23:59:59Z

long epochMillis = a.toEpochMilli(); // -1
~~~

`ofEpochMilli(-1)` và `ofEpochSecond(-1)` là **hai thời điểm khác nhau**, cách nhau 999 mili giây. Không suy đơn vị từ một tên biến chung chung như `timestamp`; hợp đồng dữ liệu cần nói rõ `epochSeconds` hay `epochMillis`.

### 3.4. `ofEpochSecond(long, long)` chuẩn hóa nano giây

Overload hai tham số nhận giây và **lượng nano điều chỉnh**. Tham số nano đầu vào có thể vượt một tỷ hoặc mang dấu âm; kết quả `Instant` được chuẩn hóa:

~~~java
Instant a = Instant.ofEpochSecond(-1, 500_000_000);
Instant b = Instant.ofEpochSecond(0, -500_000_000);
Instant c = Instant.ofEpochSecond(-2, 1_500_000_000);

// a.equals(b) && b.equals(c) là true.
// Ba cách đều biểu diễn 1969-12-31T23:59:59.500Z.
~~~

Ví dụ khác:

~~~java
Instant beforeByNano = Instant.ofEpochSecond(0, -1);

// beforeByNano = 1969-12-31T23:59:59.999999999Z
// beforeByNano.getEpochSecond() == -1
// beforeByNano.getNano() == 999999999
~~~

Đừng cố giữ một phần nano âm trong cấu trúc tự tạo. Quy tắc chuẩn hóa của `Instant` là **giây theo floor + nano không âm**.

## 4. Sai lầm thường gặp với phép chia số âm

Để tách mili giây thành giây/nano, có thể cần tính thương và phần dư. Java dùng `/` cho phép chia số nguyên **làm tròn về 0**, `%` có phần dư cùng dấu số bị chia khi khác 0:

~~~java
long millis = -1L;

long secondsByDivision = millis / 1000L;  // 0
long remainderByMod = millis % 1000L;     // -1
~~~

Như vậy cặp `(0, -1)` **không phải biểu diễn chuẩn hóa** của `Instant`. Giây 0 cộng phần mili giây âm vẫn là một thời điểm âm, nhưng `getEpochSecond()` và `getNano()` của `Instant` sẽ cho `(-1, 999000000)`.

Nếu phải tách số âm bằng tay, hãy dùng `Math.floorDiv` và `Math.floorMod`:

~~~java
long millis = -1L;

long seconds = Math.floorDiv(millis, 1000L);    // -1
long millisPart = Math.floorMod(millis, 1000L); // 999

Instant rebuilt = Instant.ofEpochSecond(
        seconds, millisPart * 1_000_000L
);
// rebuilt = 1969-12-31T23:59:59.999Z
~~~

Với số chia dương 1000, `floorMod` luôn trả phần dư từ 0 đến 999. Ví dụ:

| Epoch millis | `millis / 1000` | `millis % 1000` | `floorDiv` | `floorMod` |
| ---: | ---: | ---: | ---: | ---: |
| -1001 | -1 | -1 | -2 | 999 |
| -1000 | -1 | 0 | -1 | 0 |
| -999 | 0 | -999 | -1 | 1 |
| -1 | 0 | -1 | -1 | 999 |
| 0 | 0 | 0 | 0 | 0 |
| 1 | 0 | 1 | 0 | 1 |
| 1001 | 1 | 1 | 1 | 1 |

Đối với `-1001 ms`, kết quả chuẩn là **-2 giây cộng 999 triệu nano giây**, chính là 1,001 giây trước epoch.

**Khuyến nghị:** chỉ cần dựng `Instant` từ mili giây thì gọi thẳng `Instant.ofEpochMilli(millis)`. API này đã xử lý dấu âm; chỉ tự tách khi thật sự cần giao tiếp với định dạng chứa giây và phần lẻ riêng biệt.

## 5. Chuyển nano giây sang mili giây: vì sao `-1 ns` thành `-1 ms`?

`Instant` có độ chính xác nano giây, nhưng epoch milliseconds chỉ có độ chính xác mili giây. `toEpochMilli()` không thể bảo toàn phần nhỏ hơn một mili giây.

Đối với một `Instant` trước epoch có độ lẻ nhỏ hơn 1 ms, kết quả mili giây nguyên tương ứng với **mili giây chứa instant đó**, tức hành vi floor về ranh giới mili giây:

~~~java
Instant oneNanoBefore = Instant.ofEpochSecond(0, -1);

long millis = oneNanoBefore.toEpochMilli(); // -1
~~~

Giải thích: thời điểm âm 1 nano giây vẫn nằm trong khoảng mili giây `[-1 ms, 0 ms)`, vì thế epoch milliseconds bằng `-1`. Không được lấy giá trị xấp xỉ `-0,000001 ms` rồi làm tròn về 0 bằng quy tắc chia nguyên.

| Thời điểm tương đối epoch | `toEpochMilli()` |
| --- | ---: |
| +1 ns | 0 |
| +999999 ns | 0 |
| +1000000 ns | 1 |
| -1 ns | -1 |
| -999999 ns | -1 |
| -1000000 ns | -1 |
| -1000001 ns | -2 |

Ví dụ `Instant.ofEpochMilli(-1)` biểu diễn **âm 1 ms**, còn `Instant.ofEpochSecond(0,-1)` biểu diễn **âm 1 ns**; cả hai có thể cho cùng giá trị `toEpochMilli() == -1` nhưng **không phải cùng instant**.

Chuyển ngược từ mili giây về `Instant` chỉ khôi phục chính xác nếu ban đầu đúng ranh giới mili giây:

~~~java
Instant precise = Instant.parse("1969-12-31T23:59:59.500Z");
Instant restored = Instant.ofEpochMilli(precise.toEpochMilli());

// precise.equals(restored) == true.
~~~

Nếu `precise` có độ chính xác nano giây không chia hết cho 1.000.000 thì bước chuyển xuống mili giây sẽ làm mất thông tin. Hãy giữ `Instant` hoặc sử dụng cặp seconds/nanos khi nghiệp vụ yêu cầu độ chính xác cao.

## 6. Đọc thời điểm trước 1970 bằng chuỗi ISO-8601

Có thể dùng `Instant.parse()` cho các chuỗi cũ hơn epoch:

~~~java
Instant oneSecondBefore =
        Instant.parse("1969-12-31T23:59:59Z");
Instant beginningOf1900 =
        Instant.parse("1900-01-01T00:00:00Z");

// oneSecondBefore.getEpochSecond() == -1
// beginningOf1900.getEpochSecond() == -2208988800L
~~~

Giá trị `-2208988800` là số giây từ mốc 1900/01/01 UTC đến epoch theo quy tắc thời gian của API. Nó nhỏ hơn `Integer.MIN_VALUE` (âm 2.147.483.648), vì vậy **không nên ép timestamp vào `int`**. Các trường epoch seconds nên dùng `long`.

Nếu nguồn thời gian có offset cụ thể, cần quy đổi về instant **bằng offset đó**, chẳng hạn:

~~~java
OffsetDateTime localWithOffset =
        OffsetDateTime.parse("1970-01-01T06:59:59+07:00");
Instant equivalent =
        localWithOffset.toInstant();

// equivalent = 1969-12-31T23:59:59Z
~~~

Ở đây chuỗi địa phương đã sang năm 1970 nhưng instant vẫn âm 1 giây. Nhìn riêng **năm trong chuỗi hiển thị** không đủ để đoán dấu epoch.

Ngược lại, lúc hiển thị một `Instant` cũ bằng offset âm, lịch địa phương có thể nằm xa hơn về ngày hôm trước. Hãy phân biệt **mốc tuyệt đối** với **ngày theo lịch ở một địa phương**.

## 7. So sánh và tính khoảng cách qua epoch

Vì `Instant` cùng tham chiếu một dòng thời gian, các thao tác `isBefore`, `isAfter`, `compareTo` và `Duration.between` vẫn hoạt động nhất quán ở hai phía epoch:

~~~java
Instant before = Instant.parse("1969-12-31T23:59:59Z");
Instant zero = Instant.EPOCH;
Instant after = Instant.parse("1970-01-01T00:00:01Z");

boolean old = before.isBefore(zero);   // true
boolean future = after.isAfter(zero);  // true
Duration span = Duration.between(before, after);
// PT2S
~~~

`PT2S` nghĩa là khoảng thời gian dài 2 giây. Khoảng thời gian không trở thành “âm” chỉ vì điểm bắt đầu đứng trước epoch; dấu `Duration` phụ thuộc **thứ tự hai đối số**. `Duration.between(after,before)` mới trả khoảng âm hai giây.

Với dữ liệu ngày lịch lịch sử mà không có giờ hoặc vùng, `LocalDate` thường hợp lý hơn `Instant`. Ví dụ ngày sinh 01/01/1900 không tự động là `1900-01-01T00:00:00Z`; chuyển ngày sinh thành mốc UTC tùy tiện đã gắn một giả định không có trong dữ liệu.

## 8. Chương trình Java 17+ hoàn chỉnh

Đoạn sau có đầu vào cố định nên kết quả không phụ thuộc đồng hồ hay timezone mặc định của máy. Nó kiểm tra epoch âm, giây/nano chuẩn hóa, chia số âm, phép khôi phục và hiển thị cùng instant với offset cố định.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class NegativeEpochDemo {
    public static void main(String[] args) {
        Instant epoch = Instant.EPOCH;
        Instant before = Instant.ofEpochMilli(-1);
        Instant half = Instant.ofEpochSecond(-1, 500_000_000);
        Instant nanosBefore = Instant.ofEpochSecond(0, -1);
        Instant oldDate = Instant.parse("1900-01-01T00:00:00Z");

        System.out.println("epoch=" + epoch);
        System.out.println("before=" + before);
        System.out.println("before.seconds=" + before.getEpochSecond());
        System.out.println("before.nanos=" + before.getNano());
        System.out.println("before.millis=" + before.toEpochMilli());
        System.out.println("half=" + half);
        System.out.println("half.millis=" + half.toEpochMilli());
        System.out.println("nanosBefore=" + nanosBefore);
        System.out.println("nanosBefore.millis=" + nanosBefore.toEpochMilli());
        System.out.println("oldDate.seconds=" + oldDate.getEpochSecond());

        long millis = -1L;
        System.out.println("naive.seconds=" + (millis / 1000L));
        System.out.println("naive.remainder=" + (millis % 1000L));

        long seconds = Math.floorDiv(millis, 1000L);
        long millisPart = Math.floorMod(millis, 1000L);
        Instant restored =
                Instant.ofEpochSecond(seconds, millisPart * 1_000_000L);

        System.out.println("floor.seconds=" + seconds);
        System.out.println("floor.millisPart=" + millisPart);
        System.out.println("restored.equals=" + restored.equals(before));

        System.out.println("offset+07="
                + before.atOffset(ZoneOffset.ofHours(7)));
        System.out.println("distance=" + Duration.between(before, epoch));
    }
}
~~~

Lưu đúng tên `NegativeEpochDemo.java`, sau đó chạy:

~~~bash
javac NegativeEpochDemo.java
java NegativeEpochDemo
~~~

Kết quả:

~~~text
epoch=1970-01-01T00:00:00Z
before=1969-12-31T23:59:59.999Z
before.seconds=-1
before.nanos=999000000
before.millis=-1
half=1969-12-31T23:59:59.500Z
half.millis=-500
nanosBefore=1969-12-31T23:59:59.999999999Z
nanosBefore.millis=-1
oldDate.seconds=-2208988800
naive.seconds=0
naive.remainder=-1
floor.seconds=-1
floor.millisPart=999
restored.equals=true
offset+07=1970-01-01T06:59:59.999+07:00
distance=PT0.001S
~~~

Đọc chương trình theo thứ tự:

1. `Instant.EPOCH` là mốc 0. `Instant.ofEpochMilli(-1)` đứng trước mốc 1 mili giây, nên in giây `-1` và nano `999000000`.
2. `Instant.ofEpochSecond(-1,500_000_000)` là mốc cách epoch **âm nửa giây**, không phải âm 1,5 giây.
3. `Instant.ofEpochSecond(0,-1)` được chuẩn hóa thành âm một nano giây; khi ép về độ phân giải mili giây, `toEpochMilli()` cho `-1`.
4. Phép chia `/` trên `-1` cho 0, `%` cho -1. `floorDiv` và `floorMod` cho -1 và 999, từ đó `restored` giống `before`.
5. `atOffset(ZoneOffset.ofHours(7))` chỉ thay **cách hiển thị** của cùng instant; epoch không vì thế trở thành dương.
6. `Duration.between(before, epoch)` trả `PT0.001S`: đúng 0,001 giây hay 1 ms.

Trong chương trình, offset `+07:00` là giá trị cố định dùng cho minh họa. **Không suy rằng một ZoneId địa lý có offset +07:00 cho mọi ngày lịch sử**.

## 9. Cẩn thận với mốc lịch sử, múi giờ và giới hạn hệ thống

### 9.1. Múi giờ hiện tại không đại diện cho lịch sử

Offset là độ lệch UTC tại một thời điểm. `ZoneId` như `Asia/Ho_Chi_Minh` có bộ quy tắc vùng, có thể bao gồm các thay đổi lịch sử. Khi chuyển một `LocalDateTime` của năm 1900 hoặc 1969 thành `Instant`, hãy biết chính xác thông tin nguồn: giờ địa phương ở nơi nào, offset nào đã được ghi, hay chỉ là ngày lịch?

Đừng lấy offset **ngày nay** rồi áp ngược cho mọi bản ghi lịch sử. Thời điểm cũ hiển thị theo một `ZoneId` có thể cho offset không quen thuộc; dữ liệu timezone (tzdb) có thể được cập nhật ở các bản runtime khác nhau.

### 9.2. Lịch Gregorian mở rộng về quá khứ

`java.time` với `LocalDate`/`Instant` dùng mô hình lịch ISO, trong đó các quy tắc lịch Gregorian được mở rộng ngược về trước. Điều đó không khẳng định mọi quốc gia ở các thời kỳ lịch sử đều dùng cách ghi ngày Gregorian. Dữ liệu lịch cổ hoặc tài liệu gốc theo hệ lịch khác cần quy tắc chuyển lịch rõ ràng.

Đối với nguồn có yêu cầu chính xác theo thang thời gian chuyên biệt, cần biết rằng Java dùng **Java Time-Scale** và không biểu diễn giây nhuận như một trường “23:59:60” độc lập trong cú pháp `Instant` thông thường. Sự kiện lịch sử ghi theo thang thời gian khác có thể cần phép chuyển đổi chuyên dụng; đừng tự cho rằng một số epoch là đủ để diễn giải mọi mô tả đồng hồ lịch sử.

### 9.3. `Instant` có phạm vi rộng hơn phép chuyển về `long` mili giây

`getEpochSecond()` trả `long` và `toEpochMilli()` cũng trả `long`, nhưng không phải **mọi** giá trị `Instant` đều có thể chuyển thành epoch milliseconds dạng `long`. Với mốc quá xa, `toEpochMilli()` có thể ném `ArithmeticException` vì tràn phạm vi; những phép cộng vượt phạm vi `Instant` cũng có thể ném ngoại lệ.

Tương tự, giá trị `epochSeconds` của năm 1900 là `-2208988800L`, đã vượt `int` có dấu 32-bit. Nếu cố ép vào `int`, giá trị có thể thay đổi hoàn toàn. Không dùng số nguyên 32-bit cho timestamp tổng quát.

### 9.4. Kiểu dữ liệu bên ngoài có thể làm mất độ chính xác

Một API cũ, `java.util.Date` hoặc cột cơ sở dữ liệu chỉ giữ mili giây sẽ không bảo toàn nano giây đầy đủ của `Instant`. Khi chuyển `Instant` sang `Date` hoặc timestamp có precision hạn chế, hãy xác minh dữ liệu sau round-trip ở cả giá trị **âm và dương**.

SQL `DATE` dùng cho ngày theo lịch, không tự xác định múi giờ; SQL `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, trình điều khiển JDBC hoặc ORM có các quy tắc khác nhau giữa hệ quản trị. Đừng suy từ tên kiểu rằng offset hay timezone được bảo toàn. Nếu hệ thống cũ không hỗ trợ epoch âm hoặc ngày trước 1970, cần kiểm tra constraint ở đúng điểm giao tiếp.

### 9.5. Tránh lỗi khi biến đổi đơn vị bằng công thức tự viết

Không phải mọi phép tính tưởng đơn giản đều an toàn:

- `epochMillis / 1000` làm tròn về 0, khác `getEpochSecond()` của `Instant` với mili giây âm chưa tròn giây.
- `epochMillis % 1000` có thể âm; không đưa thẳng phần dư đó thành `nano` mà không chuẩn hóa.
- `getEpochSecond() * 1000` bỏ phần nano, dẫn tới sai tới 999 ms.
- `getEpochSecond() * 1000 + getNano()/1_000_000` có thể ra kết quả đúng với giá trị vừa tầm, nhưng phải chú ý **tràn phép nhân** và mất nano lẻ; `toEpochMilli()` thường an toàn/rõ ý nghĩa hơn.
- Dùng `Math.abs` để xử lý epoch âm có thể làm hỏng dấu; riêng `Math.abs(Long.MIN_VALUE)` còn không thể chuyển thành trị tuyệt đối dương trong `long`.

## 10. Quy trình đọc timestamp an toàn

Khi nhận dữ liệu từ file, API hoặc database, hãy kiểm tra theo thứ tự:

1. **Kiểu ngữ nghĩa:** giá trị là thời điểm tuyệt đối hay chỉ ngày/giờ địa phương?
2. **Đơn vị:** epoch seconds, epoch millis, microseconds hoặc nanoseconds? Ghi rõ vào tên trường/hợp đồng dữ liệu.
3. **Dấu âm:** chấp nhận giá trị trước 1970 nếu nghiệp vụ cho phép; không mặc định timestamp luôn không âm.
4. **Cách dựng `Instant`:** dùng `ofEpochSecond` hoặc `ofEpochMilli` tương ứng; xử lý phần nano bằng API hoặc `floorDiv/floorMod` khi cần.
5. **Độ chính xác:** kiểm tra điểm nào làm mất phần lẻ nano giây khi đổi sang mili giây.
6. **Múi giờ:** chỉ diễn giải giờ địa phương bằng offset/`ZoneId` thích hợp; không lấy mặc định của máy chủ để đoán vùng cho nguồn lịch sử.
7. **Phạm vi và lỗi:** xác minh giới hạn kiểu số, cột DB, JSON, driver; xử lý `DateTimeException`/`ArithmeticException` nếu dữ liệu ngoài phạm vi.
8. **Kiểm thử ranh giới:** `-1001 ms`, `-1000 ms`, `-999 ms`, `-1 ms`, `-1 ns`, `0`, `+1 ns`, `+1 ms`.

## 11. Tự luyện tập

1. `Instant.ofEpochMilli(-1).getEpochSecond()` và `getNano()` lần lượt bằng bao nhiêu? Vì sao nano không phải `-1000000`?
2. Tạo `Instant` bằng `ofEpochSecond(-1,500_000_000)` và `ofEpochSecond(0,-500_000_000)`. Hai instant có bằng nhau không?
3. Từ `-1001L` epoch milliseconds, tính cặp giây/nano chuẩn bằng `floorDiv/floorMod`. Đáp án: `-2` giây và `999000000` nano.
4. Gọi `Instant.ofEpochSecond(0,-1).toEpochMilli()` rồi tạo lại bằng `ofEpochMilli`. Hai instant có còn bằng nhau không? Vì sao?
5. Một API lưu `1900-01-01` là ngày sinh. Dữ liệu đó có cần biểu diễn thành epoch không? Nếu chỉ là ngày lịch, kiểu Java nào phù hợp nhất?
6. In cùng `Instant.ofEpochMilli(-1)` ở offset UTC, `+07:00`, `-05:00`. Vì sao ngày hiển thị khác mà `getEpochSecond()` giống nhau?
7. Viết test với các epoch milli giây `-1001`, `-1000`, `-999`, `-1`, `0`, `1` và khẳng định `Instant.ofEpochMilli(x).toEpochMilli() == x`.

**Ghi nhớ:** thời điểm trước 1970 là **epoch âm hợp lệ**. `Instant` biểu diễn nó bằng **số giây lấy theo floor** cộng **phần nano không âm**. Muốn xử lý đúng, cần biết đơn vị timestamp, sử dụng `ofEpochSecond`/`ofEpochMilli`, cẩn thận với phép chia số âm và nhớ rằng chuyển từ nano giây sang mili giây có thể làm mất độ chính xác.